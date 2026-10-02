"""MODEL RUNTIME BOUNDARY 0.1 · la frontera de runtime de modelos (`app/llm_runtime.py`).

Sustituye a `test_llm_compat_sonnet5.py` (#180) y conserva sus promesas, ahora sobre la frontera:

  1. **Inventario exacto.** Cada llamada al LLM del repo, con su propósito. Una llamada nueva
     obliga a mirarla.
  2. **Guarda AST.** Ningún call site fija `model`, `thinking`, `temperature`, `effort`,
     `tool_choice` ni peculiaridades del proveedor; todos piden su configuración a la frontera por
     propósito. Nadie fuera de ella lee `settings.llm_model` ni escribe un id de modelo. La guarda
     se prueba contra fuentes sintéticas que la infringen: una regla que sólo se ejerce cuando
     alguien la rompe no está medida.
  3. **Cable.** Lo que llega al proveedor en los 8 call sites (capturado con httpx.MockTransport,
     sin red) es lo CALIFICADO: `tests/fixtures/llm_wire_calificado.json`, sacado de bc2a6e3 (4.5)
     y de la Fase B (Sonnet 5 adaptive low), no de este código.
  4. **Falla cerrado.** Modelo sin perfil, propósito sin configuración o capacidad no admitida →
     `ModelConfigError`; nunca los defaults del proveedor, y nunca tragado por un `except`.
"""
import ast
import dataclasses
import json
import pathlib
import re

import anthropic
import httpx
import pytest
from langchain_core.messages import HumanMessage, SystemMessage

import evals.run_evals as run_evals
from app import config, llm_runtime, preferencias, vision
from app.agent import crm_graph, graph
from app.buyer import interprete
from app.llm_runtime import (
    HAIKU_45_JUEZ, REGISTRO, SONNET_5, SONNET_45, SONNET_55, CallPurpose, ModelConfigError, ModelRuntime,
    PurposeConfig, Thinking, ToolObligatoriaAusente, perfil, runtime, runtime_evaluador, validar_perfil,
)
from app.routers import match

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FRONTERA = "app/llm_runtime.py"
M45, M5, M55 = "claude-sonnet-4-5-20250929", "claude-sonnet-5", "claude-sonnet-5-5"
GOLDEN = json.loads((RAIZ / "tests" / "fixtures" / "llm_wire_calificado.json").read_text(encoding="utf-8"))


# ═════════════════════════════ 1-2 · inventario y guarda AST ═════════════════════════════

# Lo que sólo la frontera puede decidir. Si aparece en una llamada al LLM, es un call site que
# vuelve a configurar el modelo por su cuenta.
PROHIBIDOS = {"model", "thinking", "temperature", "top_p", "top_k", "tool_choice", "extra_body",
              "model_kwargs", "output_config", "betas", "extra_headers"}
METODOS_FRONTERA = {"sdk_kwargs", "langchain_kwargs", "http_json"}
FABRICAS_FRONTERA = {"runtime", "runtime_evaluador"}


def _es_llamada_al_llm(n: ast.Call) -> str | None:
    f = n.func
    if isinstance(f, ast.Name) and f.id == "ChatAnthropic":
        return "ChatAnthropic"
    if (isinstance(f, ast.Attribute) and f.attr in ("create", "stream")
            and isinstance(f.value, ast.Attribute) and f.value.attr == "messages"):
        return "messages." + f.attr
    if (isinstance(f, ast.Attribute) and f.attr == "post" and n.args
            and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str)
            and "api.anthropic.com" in n.args[0].value):
        return "http"
    return None


def _proposito_de(expr: ast.AST) -> str | None:
    """`runtime().sdk_kwargs(CallPurpose.X, …)` → "X"; cualquier otra cosa → None."""
    if not (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Attribute)
            and expr.func.attr in METODOS_FRONTERA):
        return None
    fab = expr.func.value
    if not (isinstance(fab, ast.Call) and isinstance(fab.func, ast.Name) and fab.func.id in FABRICAS_FRONTERA):
        return None
    if (expr.args and isinstance(expr.args[0], ast.Attribute) and isinstance(expr.args[0].value, ast.Name)
            and expr.args[0].value.id == "CallPurpose"):
        return expr.args[0].attr
    return None


def _asignaciones(funcion: ast.AST | None) -> dict[str, ast.AST]:
    if funcion is None:
        return {}
    return {t.id: n.value for n in ast.walk(funcion) if isinstance(n, ast.Assign)
            for t in n.targets if isinstance(t, ast.Name)}


def _splat_proposito(valor: ast.AST, asign: dict[str, ast.AST]) -> str | None:
    if isinstance(valor, ast.Name):
        valor = asign.get(valor.id)
    return _proposito_de(valor) if valor is not None else None


def _default_de_llm_model(arbol: ast.Module) -> ast.Constant | None:
    """El nodo literal que es el default de `Settings.llm_model` (`llm_model: str = "<id>"` en el
    cuerpo de `class Settings`, de primer nivel), o None si no tiene exactamente esa forma."""
    for clase in arbol.body:
        if isinstance(clase, ast.ClassDef) and clase.name == "Settings":
            for n in clase.body:
                if (isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)
                        and n.target.id == "llm_model" and isinstance(n.value, ast.Constant)):
                    return n.value
    return None


def _analizar(fuente: str, default_llm_model: str | None = None) -> tuple[list[str], list[str]]:
    """(propósitos de las llamadas al LLM en orden, infracciones).

    Con `default_llm_model`, se admite UN literal de modelo: el NODO que es el default de
    `Settings.llm_model`, y sólo si vale exactamente eso. Otro literal idéntico en el mismo fichero
    (otro campo, el módulo o la misma línea) sigue siendo una infracción."""
    arbol = ast.parse(fuente)
    nodo = _default_de_llm_model(arbol) if default_llm_model else None
    exento = nodo if nodo is not None and nodo.value == default_llm_model else None
    padre_funcion: dict[ast.AST, ast.AST] = {}
    for f in ast.walk(arbol):
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for hijo in ast.walk(f):
                padre_funcion.setdefault(hijo, f)
    propositos, malas = [], []  # (línea, …): se ordenan al final
    for n in ast.walk(arbol):
        if isinstance(n, ast.Attribute) and n.attr == "llm_model":
            malas.append((n.lineno, "lee settings.llm_model fuera de la frontera"))
        if isinstance(n, ast.Name) and n.id in ("THINKING_APAGADO", "temperatura_llm"):
            malas.append((n.lineno, f"{n.id} (conocimiento de modelo disperso)"))
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith("claude-") \
                and n is not exento:
            malas.append((n.lineno, f"id de modelo literal {n.value!r}"))
        if isinstance(n, ast.Dict):
            pares = {k.value: v for k, v in zip(n.keys, n.values) if isinstance(k, ast.Constant)}
            tipo = pares.get("type")
            if isinstance(tipo, ast.Constant) and tipo.value in ("disabled", "adaptive", "enabled") \
                    and set(pares) <= {"type", "budget_tokens", "display"}:
                malas.append((n.lineno, "configuración de thinking literal"))
        if not (isinstance(n, ast.Call) and (clase := _es_llamada_al_llm(n))):
            continue
        asign = _asignaciones(padre_funcion.get(n))
        kws = n.keywords
        if clase == "http":
            cuerpo = next((k.value for k in kws if k.arg == "json"), None)
            if not isinstance(cuerpo, ast.Dict):
                malas.append((n.lineno, "request HTTP al proveedor sin cuerpo literal"))
                continue
            kws_cuerpo = [(k.value if isinstance(k, ast.Constant) else None, v)
                          for k, v in zip(cuerpo.keys, cuerpo.values)]
            directos = {k for k, _ in kws_cuerpo if k is not None}
            splats = [v for k, v in kws_cuerpo if k is None]
        else:
            directos = {k.arg for k in kws if k.arg is not None}
            splats = [k.value for k in kws if k.arg is None]
        for p in sorted(directos & PROHIBIDOS):
            malas.append((n.lineno, f"{clase} fija `{p}` fuera de la frontera"))
        prop = next((x for x in (_splat_proposito(s, asign) for s in splats) if x), None)
        if prop is None:
            malas.append((n.lineno, f"{clase} sin configuración de la frontera por propósito"))
        else:
            propositos.append((n.lineno, prop))
    return [p for _, p in sorted(propositos)], [f"línea {ln}: {t}" for ln, t in sorted(set(malas))]


def _ficheros():
    for base in ("app", "evals", "scripts"):
        for ruta in sorted((RAIZ / base).rglob("*.py")):
            rel = ruta.relative_to(RAIZ).as_posix()
            if rel != FRONTERA:
                yield rel, ruta.read_text(encoding="utf-8")
    yield "main.py", (RAIZ / "main.py").read_text(encoding="utf-8")


def _escaneo():
    inventario, malas = {}, {}
    for rel, fuente in _ficheros():
        # app/config.py define `llm_model` y su default; nada más.
        props, m = _analizar(fuente, default_llm_model=M5 if rel == "app/config.py" else None)
        if props:
            inventario[rel] = props
        if m:
            malas[rel] = m
    return inventario, malas


def test_inventario_exacto_de_llamadas_al_llm_y_su_proposito():
    """Si aparece una llamada nueva (o cambia de propósito), este test obliga a mirarla. Y evita
    que la guarda pase en verde por haber recorrido un árbol vacío."""
    inventario, _ = _escaneo()
    assert inventario == {
        "app/agent/crm_graph.py": ["CRM"],
        "app/agent/graph.py": ["CHAT"],
        "app/buyer/interprete.py": ["INTERPRETE"],
        "app/preferencias.py": ["PREFERENCIAS"],
        "app/routers/match.py": ["MATCH", "MATCH"],
        "app/vision.py": ["VISION"],
        "evals/run_evals.py": ["JUEZ"],
    }
    usados = {p for props in inventario.values() for p in props}
    assert usados == {p.name for p in CallPurpose}, "un propósito sin call site o al revés"


def test_ningun_call_site_configura_el_modelo_fuera_de_la_frontera():
    _, malas = _escaneo()
    assert malas == {}


def test_la_guarda_muerde_con_fuentes_sinteticas():
    sintetica = (
        "async def f():\n"
        "    llm = ChatAnthropic(model=settings.llm_model, temperature=0.2, max_tokens=10)\n"
        "    r = await c().messages.create(**runtime().sdk_kwargs(CallPurpose.CHAT),\n"
        "                                 thinking={'type': 'adaptive'}, max_tokens=10)\n"
        "    s = await c().messages.create(model='claude-sonnet-5', max_tokens=10)\n"
        "    t = await c().messages.create(**kw, extra_body={'output_config': {'effort': 'low'}})\n"
        "    if settings.llm_model.startswith('claude-sonnet-4-5'):\n"
        "        pass\n"
        "    x = temperatura_llm(0.2)\n"
        "    h = httpx.post('https://api.anthropic.com/v1/messages', json={'model': m, 'max_tokens': 5})\n"
    )
    _, malas = _analizar(sintetica)
    assert malas == [
        "línea 2: ChatAnthropic fija `model` fuera de la frontera",
        "línea 2: ChatAnthropic fija `temperature` fuera de la frontera",
        "línea 2: ChatAnthropic sin configuración de la frontera por propósito",
        "línea 2: lee settings.llm_model fuera de la frontera",
        "línea 3: messages.create fija `thinking` fuera de la frontera",
        "línea 4: configuración de thinking literal",
        "línea 5: id de modelo literal 'claude-sonnet-5'",
        "línea 5: messages.create fija `model` fuera de la frontera",
        "línea 5: messages.create sin configuración de la frontera por propósito",
        "línea 6: messages.create fija `extra_body` fuera de la frontera",
        "línea 6: messages.create sin configuración de la frontera por propósito",
        "línea 7: id de modelo literal 'claude-sonnet-4-5'",
        "línea 7: lee settings.llm_model fuera de la frontera",
        "línea 9: temperatura_llm (conocimiento de modelo disperso)",
        "línea 10: http fija `model` fuera de la frontera",
        "línea 10: http sin configuración de la frontera por propósito",
    ]


def test_la_guarda_acepta_las_formas_correctas():
    buena = (
        "async def f():\n"
        "    modelo = runtime().sdk_kwargs(CallPurpose.MATCH, tool_forzada='x')\n"
        "    try:\n"
        "        r = await c().messages.create(**modelo, max_tokens=10, system=s, messages=m)\n"
        "    except Exception:\n"
        "        pass\n"
        "    llm = ChatAnthropic(**runtime().langchain_kwargs(CallPurpose.CHAT), max_tokens=5)\n"
        "    j = runtime_evaluador(J).http_json(CallPurpose.JUEZ)\n"
        "    h = httpx.post('https://api.anthropic.com/v1/messages', json={**j, 'max_tokens': 5})\n"
    )
    assert _analizar(buena) == (["MATCH", "CHAT", "JUEZ"], [])


_DEFAULT = 'class Settings(BaseSettings):\n    llm_model: str = "claude-sonnet-5"\n'


@pytest.mark.parametrize("fuente,malas", [
    (_DEFAULT, []),
    # un segundo literal IDÉNTICO: en otro campo, en el módulo, en la misma línea
    (_DEFAULT + '    respaldo: str = "claude-sonnet-5"\n', ["línea 3: id de modelo literal 'claude-sonnet-5'"]),
    ('MODELO = "claude-sonnet-5"\n' + _DEFAULT, ["línea 1: id de modelo literal 'claude-sonnet-5'"]),
    (_DEFAULT.replace('"\n', '"; x = "claude-sonnet-5"\n'), ["línea 2: id de modelo literal 'claude-sonnet-5'"]),
    # otro id como default, o el mismo fuera de `Settings`
    (_DEFAULT.replace("sonnet-5", "sonnet-5-5"), ["línea 2: id de modelo literal 'claude-sonnet-5-5'"]),
    (_DEFAULT.replace("class Settings", "class Otra"), ["línea 2: id de modelo literal 'claude-sonnet-5'"]),
])
def test_la_excepcion_de_config_es_solo_el_default_de_llm_model(fuente, malas):
    assert _analizar(fuente, default_llm_model=M5) == ([], malas)


def test_config_declara_un_solo_id_de_modelo_y_es_el_default_de_llm_model():
    arbol = ast.parse((RAIZ / "app" / "config.py").read_text(encoding="utf-8"))
    literales = [n for n in ast.walk(arbol)
                 if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value.startswith("claude-")]
    assert literales == [_default_de_llm_model(arbol)] and literales[0].value == M5


# ═════════════════════════════ 3 · lo que llega al proveedor ═════════════════════════════

def _cliente(capturas: list):
    def _h(req):
        capturas.append(json.loads(req.content))
        return httpx.Response(400, json={"type": "error", "error": {
            "type": "invalid_request_error", "message": "captura del test"}})
    return anthropic.AsyncAnthropic(api_key="sk-falsa", max_retries=0,
                                    http_client=httpx.AsyncClient(transport=httpx.MockTransport(_h)))


def _instancia_real(monkeypatch, modulo, constructor):
    """Construye el grafo REAL y devuelve la instancia REAL de ChatAnthropic que creó."""
    creadas, original = [], modulo.ChatAnthropic

    def _fabrica(*a, **kw):
        creadas.append(original(*a, **kw))
        return creadas[-1]

    monkeypatch.setattr(modulo, "ChatAnthropic", _fabrica)
    getattr(modulo, constructor)()
    monkeypatch.setattr(modulo, "ChatAnthropic", original)
    return creadas[0]


async def _capturar_cable(monkeypatch, modelo: str) -> dict[str, dict]:
    monkeypatch.setattr(config.settings, "llm_model", modelo)
    monkeypatch.setattr(config.settings, "anthropic_api_key", "sk-falsa")
    salida, capt = {}, []
    for m in (preferencias, interprete, match, vision):
        monkeypatch.setattr(m, "_client", lambda: _cliente(capt))

    async def una(nombre, corutina):
        capt.clear()
        try:
            await corutina()
        except Exception:  # noqa: BLE001 — la respuesta es un 400 del transporte
            pass
        salida[nombre] = capt[0] if capt else None

    chat = _instancia_real(monkeypatch, graph, "_build_graph")
    chat.__dict__["_async_client"] = _cliente(capt)
    await una("CHAT · graph.llm_node", lambda: chat.bind_tools(graph.AGENT_TOOLS).ainvoke(
        [SystemMessage(graph.SYSTEM_PROMPT.content), HumanMessage("hola")]))
    crm = _instancia_real(monkeypatch, crm_graph, "_build_crm_graph")
    crm.__dict__["_async_client"] = _cliente(capt)
    await una("CRM · crm_graph.llm_node", lambda: crm.bind_tools(crm_graph.CRM_TOOLS).ainvoke(
        [SystemMessage("sistema"), HumanMessage("¿cómo va mi cartera?")]))
    res = [{"activo_id": "a1", "direccion": "Calle 1", "tipo_activo": "Departamento", "walk_score": 80,
            "score_ruido_predictivo": None, "porcentaje_cobertura_vegetal": None, "ficha_vision_raw": None}]
    await una("PREFERENCIAS · extraer_preferencias", lambda: preferencias.extraer_preferencias(["quiero 2 dormitorios"]))
    await una("INTERPRETE · proponer_con_modelo", lambda: interprete.proponer_con_modelo("quiero comprar"))
    await una("MATCH · _refine_brief", lambda: match._refine_brief("algo tranquilo"))
    await una("MATCH · _justificar", lambda: match._justificar("tranquilo", "texto", res))
    await una("VISION · extract_ficha_from_b64", lambda: vision.extract_ficha_from_b64("AAAA"))

    juez = []

    def _post(url, *a, **kw):
        juez.append(kw.get("json"))
        raise httpx.ConnectError("captura del test")

    monkeypatch.setattr(run_evals, "ANTHROPIC_API_KEY", "sk-falsa")
    monkeypatch.setattr(run_evals.httpx, "post", _post)
    run_evals.judge("¿pregunta?", "respuesta", "rúbrica")
    salida["JUEZ · run_evals.judge"] = juez[0] if juez else None
    return salida


PARAMETROS = ("model", "max_tokens", "thinking", "temperature", "tool_choice", "output_config", "stream",
              "top_p", "top_k")


def _parametros(cuerpo: dict) -> dict:
    return {k: cuerpo[k] for k in PARAMETROS if k in cuerpo} | {"_claves": sorted(cuerpo)}


@pytest.mark.parametrize("modelo", [M45, M5])
async def test_el_cable_es_el_calificado_en_los_8_call_sites(monkeypatch, modelo):
    """4.5: idéntico a bc2a6e3. Sonnet 5: chat = Fase B (adaptive + low), resto = #180."""
    cable = await _capturar_cable(monkeypatch, modelo)
    assert set(cable) == set(GOLDEN[modelo])
    for sitio, esperado in GOLDEN[modelo].items():
        assert cable[sitio] is not None, f"{sitio}: no llegó nada al proveedor"
        assert _parametros(cable[sitio]) == esperado, sitio


def test_configuracion_calificada_legible_por_perfil():
    """El mismo contrato del golden, escrito a mano: lo que un humano revisa en un diff."""
    r45, r5 = ModelRuntime(SONNET_45), ModelRuntime(SONNET_5)
    assert r45.langchain_kwargs(CallPurpose.CHAT) == {
        "model": M45, "thinking": {"type": "disabled"}, "temperature": 0.2}
    assert r45.langchain_kwargs(CallPurpose.CRM) == {
        "model": M45, "thinking": {"type": "disabled"}, "temperature": 0.2}
    assert r5.langchain_kwargs(CallPurpose.CHAT) == {
        "model": M5, "thinking": {"type": "adaptive"},
        "model_kwargs": {"extra_body": {"output_config": {"effort": "low"}}}}
    assert r5.langchain_kwargs(CallPurpose.CRM) == {"model": M5, "thinking": {"type": "disabled"}}
    for p, tool in ((CallPurpose.PREFERENCIAS, "registrar_preferencias"),
                    (CallPurpose.INTERPRETE, "registrar_afirmaciones"),
                    (CallPurpose.MATCH, "explicar_match"), (CallPurpose.VISION, "registrar_ficha_visual")):
        for r, m in ((r45, M45), (r5, M5)):
            assert r.sdk_kwargs(p, tool_forzada=tool) == {
                "model": m, "thinking": {"type": "disabled"}, "tool_choice": {"type": "tool", "name": tool}}
    assert r5.sdk_kwargs(CallPurpose.MATCH) == {"model": M5, "thinking": {"type": "disabled"}}
    assert runtime_evaluador("claude-haiku-4-5").http_json(CallPurpose.JUEZ) == {"model": "claude-haiku-4-5"}
    assert r5.http_json(CallPurpose.CHAT) == {"model": M5, "thinking": {"type": "adaptive"},
                                              "output_config": {"effort": "low"}}


def test_el_eval_del_interprete_registra_lo_mismo_que_antes_en_45(monkeypatch):
    """El hash de configuración del eval B no cambia en 4.5: los artefactos siguen comparables."""
    import evals.corpus_interprete as corpus

    monkeypatch.setattr(config.settings, "llm_model", M45)
    monkeypatch.setattr(corpus, "_commit_sha", lambda: "x")
    monkeypatch.setattr(corpus, "_candidate_tree_sha", lambda: "x")
    ident = corpus._identidad_config()
    assert {k: ident[k] for k in ("model", "max_tokens", "tool_choice", "temperature", "thinking")} == {
        "model": M45, "max_tokens": 1500, "tool_choice": {"type": "tool", "name": "registrar_afirmaciones"},
        "temperature": "unset", "thinking": {"type": "disabled"}}
    assert "extra_body" not in ident


# ═════════════════════════════ 4 · falla cerrado ═════════════════════════════

@pytest.mark.parametrize("model_id", ["claude-sonnet-9", "claude-sonnet-4-5", "claude-opus-5", "", "gpt-5"])
def test_modelo_sin_perfil_falla(monkeypatch, model_id):
    monkeypatch.setattr(config.settings, "llm_model", model_id)
    with pytest.raises(ModelConfigError, match="sin perfil registrado"):
        runtime()


def test_modelo_sin_perfil_tumba_el_arranque_del_chat_y_del_crm(monkeypatch):
    monkeypatch.setattr(config.settings, "llm_model", "claude-sonnet-9")
    with pytest.raises(ModelConfigError):
        graph._build_graph()
    with pytest.raises(ModelConfigError):
        crm_graph._build_crm_graph()


async def test_las_micro_llamadas_no_tragan_el_error_de_configuracion(monkeypatch):
    """`extraer_preferencias` y `match` degradan ante un fallo del PROVEEDOR; ante una
    configuración no admitida se detienen: degradar ahí sería esconder un despliegue roto."""
    monkeypatch.setattr(config.settings, "llm_model", "claude-sonnet-9")
    monkeypatch.setattr(config.settings, "anthropic_api_key", "sk-falsa")
    with pytest.raises(ModelConfigError):
        await preferencias.extraer_preferencias(["quiero 2 dormitorios"])
    with pytest.raises(ModelConfigError):
        await match._refine_brief("algo tranquilo")
    with pytest.raises(ModelConfigError):
        await match._justificar("b", "texto", [{"activo_id": "a", "direccion": "d", "tipo_activo": "t"}])
    with pytest.raises(ModelConfigError):
        await interprete.proponer_con_modelo("quiero comprar")
    with pytest.raises(ModelConfigError):
        await vision.extract_ficha_from_b64("AAAA")


def test_el_juez_sin_perfil_detiene_el_eval_en_vez_de_opinar(monkeypatch):
    monkeypatch.setattr(run_evals, "ANTHROPIC_API_KEY", "sk-falsa")
    monkeypatch.setattr(run_evals, "JUDGE_MODEL", "claude-3-5-haiku-latest")
    with pytest.raises(ModelConfigError):
        run_evals.judge("¿hay algo?", "sí", "debe responder")


def test_los_roles_no_se_mezclan(monkeypatch):
    monkeypatch.setattr(config.settings, "llm_model", "claude-haiku-4-5")
    with pytest.raises(ModelConfigError, match="rol 'evaluador'"):
        runtime()
    with pytest.raises(ModelConfigError, match="rol 'producto'"):
        runtime_evaluador(M5)


def test_capacidad_no_admitida_falla():
    # Tool forzada con el razonamiento encendido (el chat de Sonnet 5 es adaptive).
    with pytest.raises(ModelConfigError, match="tool forzada con thinking 'adaptive'"):
        ModelRuntime(SONNET_5).sdk_kwargs(CallPurpose.CHAT, tool_forzada="x")
    # Tool forzada en un perfil que no la admite.
    with pytest.raises(ModelConfigError, match="no admite tool forzada"):
        ModelRuntime(HAIKU_45_JUEZ).sdk_kwargs(CallPurpose.JUEZ, tool_forzada="x")
    # Propósito sin configuración calificada.
    with pytest.raises(ModelConfigError, match="sin configuración calificada"):
        ModelRuntime(SONNET_45).sdk_kwargs(CallPurpose.JUEZ)


def _con(perfil_base, proposito, cfg):
    return dataclasses.replace(perfil_base, propositos={**perfil_base.propositos, proposito: cfg})


@pytest.mark.parametrize("perfil_malo,motivo", [
    (_con(SONNET_45, CallPurpose.CHAT, PurposeConfig(Thinking.ADAPTIVE)), "thinking 'adaptive' no admitido"),
    (_con(SONNET_45, CallPurpose.CHAT, PurposeConfig(Thinking.DISABLED, effort="low")), "effort 'low' no admitido"),
    (_con(SONNET_5, CallPurpose.CHAT, PurposeConfig(Thinking.ADAPTIVE, effort="low", temperature=0.2)),
     "no admite `temperature`"),
    (_con(SONNET_5, CallPurpose.PREFERENCIAS, PurposeConfig(Thinking.OMITIDO)), "omitir `thinking` encendería"),
    (_con(SONNET_5, CallPurpose.CRM, PurposeConfig(Thinking.DISABLED, effort="low")), "effort sin thinking adaptive"),
    (_con(SONNET_5, CallPurpose.CHAT, PurposeConfig(Thinking.ADAPTIVE, effort="max")), "effort 'max' no admitido"),
    (dataclasses.replace(SONNET_5, propositos={k: v for k, v in SONNET_5.propositos.items()
                                               if k is not CallPurpose.VISION}), "que faltan \\['vision'\\]"),
    (_con(HAIKU_45_JUEZ, CallPurpose.CHAT, PurposeConfig(Thinking.OMITIDO)), "que sobran \\['chat'\\]"),
    (dataclasses.replace(SONNET_5, provider="openai"), "sin transporte"),
])
def test_el_registro_rechaza_perfiles_incoherentes(perfil_malo, motivo):
    with pytest.raises(ModelConfigError, match=motivo):
        validar_perfil(perfil_malo)


def test_registro_duplicado_falla():
    with pytest.raises(ModelConfigError, match="duplicado"):
        llm_runtime._registro(SONNET_5, dataclasses.replace(SONNET_45, model_id=M5))


def test_el_registro_es_exactamente_el_de_esta_unidad():
    """Perfiles de producto: 4.5 y Sonnet 5 calificados, 5.5 candidato. El evaluador sólo sirve al juez."""
    assert {m: (p.clave, p.rol) for m, p in REGISTRO.items()} == {
        M45: ("claude-sonnet-4-5", "producto"),
        M5: ("claude-sonnet-5", "producto"),
        M55: ("claude-sonnet-5-5", "producto"),
        "claude-haiku-4-5": ("claude-haiku-4-5", "evaluador"),
    }
    assert perfil(M45) is SONNET_45 and perfil(M5) is SONNET_5
    # 5.5 está registrado para EVALUARLO: no es calificado ni seleccionable sin el permiso explícito.
    assert {m: p.estado for m, p in REGISTRO.items()} == {
        M45: "calificado", M5: "calificado", M55: "candidato", "claude-haiku-4-5": "calificado"}
    assert perfil(M55, permitir_candidato=True) is SONNET_55


@pytest.mark.parametrize("entorno,esperado", [({}, SONNET_5), ({"LLM_MODEL": M45}, SONNET_45)])
def test_el_default_es_sonnet_5_y_llm_model_explicito_elige_45(monkeypatch, entorno, esperado):
    """Sin `LLM_MODEL`, `Settings` resuelve al perfil de Sonnet 5, el que corre en producción desde
    el 2026-10-01. Con `LLM_MODEL` explícito, 4.5 sigue siendo seleccionable: el rollback es sólo
    de entorno mientras Anthropic lo sirva."""
    monkeypatch.delenv("LLM_MODEL", raising=False)
    for k, v in {"POSTGRES_DB": "t", "POSTGRES_USER": "t", "POSTGRES_PASSWORD": "t", **entorno}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(config.settings, "llm_model", config.Settings(_env_file=None).llm_model)
    assert runtime().perfil is esperado


def test_los_tres_defaults_declarativos_coinciden():
    """`Settings`, `render.yaml` y `.env.example` declaran el mismo modelo, y tiene perfil de
    producto. Si uno deriva, el repositorio vuelve a decir un modelo mientras producción corre otro."""
    render = re.search(r"- key: LLM_MODEL\s+value: (\S+)", (RAIZ / "render.yaml").read_text(encoding="utf-8"))
    ejemplo = re.search(r"^LLM_MODEL=(\S+)$", (RAIZ / ".env.example").read_text(encoding="utf-8"), re.M)
    assert render and ejemplo
    assert {config.Settings.model_fields["llm_model"].default, render[1], ejemplo[1]} == {M5}
    assert perfil(M5).rol == "producto"


# ═════════════════════════════ el juez de los evals (de #180) ═════════════════════════════

def test_el_juez_que_no_responde_no_aprueba(monkeypatch):
    """Con el modelo del juez retirado, cada llamada fallaba y contaba como APROBADA."""
    def _post_caido(*_a, **_kw):
        raise httpx.ConnectError("modelo retirado")

    monkeypatch.setattr(run_evals, "ANTHROPIC_API_KEY", "sk-falsa")
    monkeypatch.setattr(run_evals.httpx, "post", _post_caido)
    ok, razon = run_evals.judge("¿hay algo?", "sí", "debe responder")
    assert ok is False
    assert "juez no disponible" in razon


def test_el_juez_por_defecto_no_es_un_modelo_retirado():
    assert not run_evals.JUDGE_MODEL.startswith("claude-3")


# ════════════════ 5 · Sonnet 5.5 · perfil CANDIDATO (SONNET55 QUALIFY 0.1) ════════════════
# Contrato verificado contra la API el 2026-10-01 (arneses/sonnet55_q/resultados/sondas_api.json).

def test_55_es_candidato_y_no_se_elige_sin_permiso_explicito(monkeypatch):
    """Registrado para evaluarlo, nunca seleccionable por accidente: ni por LLM_MODEL a secas ni
    como default."""
    assert config.Settings.model_fields["llm_permitir_candidato"].default is False
    with pytest.raises(ModelConfigError, match="CANDIDATO"):
        perfil(M55)
    monkeypatch.setattr(config.settings, "llm_model", M55)
    monkeypatch.setattr(config.settings, "llm_permitir_candidato", False)
    with pytest.raises(ModelConfigError, match="CANDIDATO"):
        runtime()
    with pytest.raises(ModelConfigError, match="CANDIDATO"):
        graph._build_graph()
    monkeypatch.setattr(config.settings, "llm_permitir_candidato", True)
    assert runtime().perfil is SONNET_55


def test_configuracion_de_55_legible():
    r = ModelRuntime(SONNET_55)
    assert r.langchain_kwargs(CallPurpose.CHAT) == {
        "model": M55, "thinking": {"type": "adaptive"},
        "model_kwargs": {"extra_body": {"output_config": {"effort": "low"}}}}
    assert r.langchain_kwargs(CallPurpose.CRM) == {
        "model": M55, "thinking": {"type": "between_tools"},
        "model_kwargs": {"extra_body": {"output_config": {"effort": "low"}}}}
    assert r.sdk_kwargs(CallPurpose.MATCH) == {
        "model": M55, "thinking": {"type": "between_tools"}, "extra_body": {"output_config": {"effort": "low"}}}
    for p, tool in ((CallPurpose.PREFERENCIAS, "registrar_preferencias"),
                    (CallPurpose.INTERPRETE, "registrar_afirmaciones"),
                    (CallPurpose.MATCH, "explicar_match"), (CallPurpose.VISION, "registrar_ficha_visual")):
        assert r.sdk_kwargs(p, tool_forzada=tool) == {
            "model": M55, "thinking": {"type": "between_tools"},
            "extra_body": {"output_config": {"effort": "low"}}, "tool_choice": {"type": "auto"}}


async def test_el_cable_de_55_en_los_8_call_sites(monkeypatch):
    """Lo que el contrato 5.5 rechaza con 400 no llega nunca al proveedor: ni `disabled`, ni tool
    forzada, ni `temperature`. Las tools viajan IGUAL que en Sonnet 5 (sin `strict`)."""
    monkeypatch.setattr(config.settings, "llm_permitir_candidato", True)
    cable = await _capturar_cable(monkeypatch, M55)
    obligatorias = {"PREFERENCIAS · extraer_preferencias", "INTERPRETE · proponer_con_modelo",
                    "MATCH · _justificar", "VISION · extract_ficha_from_b64"}
    assert obligatorias < set(cable) and set(cable) == set(GOLDEN[M5])
    for sitio, cuerpo in cable.items():
        assert cuerpo is not None, f"{sitio}: no llegó nada al proveedor"
        if sitio.startswith("JUEZ"):
            assert _parametros(cuerpo) == GOLDEN[M5][sitio]
            continue
        assert cuerpo["model"] == M55, sitio
        assert cuerpo["thinking"]["type"] in ("adaptive", "between_tools"), sitio
        assert cuerpo["output_config"]["effort"] in ("low", "medium", "high"), sitio
        assert "temperature" not in cuerpo, sitio
        assert (cuerpo.get("tool_choice") or {}).get("type") in (None, "auto"), sitio
        assert not any(t.get("strict") for t in cuerpo.get("tools") or []), sitio
        if sitio in obligatorias:
            assert cuerpo["tool_choice"] == {"type": "auto"} and len(cuerpo["tools"]) == 1, sitio
    assert cable["CHAT · graph.llm_node"]["thinking"] == {"type": "adaptive"}


@pytest.mark.parametrize("perfil_malo,motivo", [
    (_con(SONNET_55, CallPurpose.PREFERENCIAS, PurposeConfig(Thinking.DISABLED)), "thinking 'disabled' no admitido"),
    (_con(SONNET_55, CallPurpose.CRM, PurposeConfig(Thinking.BETWEEN_TOOLS, effort="xhigh")),
     "effort 'xhigh' no admitido con thinking 'between_tools'"),
    (_con(SONNET_55, CallPurpose.CRM, PurposeConfig(Thinking.BETWEEN_TOOLS, effort="max")),
     "effort 'max' no admitido con thinking 'between_tools'"),
    (_con(SONNET_55, CallPurpose.CRM, PurposeConfig(Thinking.BETWEEN_TOOLS)), "'between_tools' sin effort explícito"),
    (_con(SONNET_55, CallPurpose.CHAT, PurposeConfig(Thinking.ADAPTIVE)), "'adaptive' sin effort explícito"),
    (_con(SONNET_55, CallPurpose.CHAT, PurposeConfig(Thinking.OMITIDO, effort="low")), "omitir `thinking` encendería"),
    (_con(SONNET_5, CallPurpose.CRM, PurposeConfig(Thinking.BETWEEN_TOOLS, effort="low")),
     "thinking 'between_tools' no admitido"),
    (dataclasses.replace(SONNET_55, tool_auto=False), "sin forma de exigir una tool"),
    (dataclasses.replace(SONNET_55, tool_forzada=True), "tool forzada y auto a la vez"),
    (dataclasses.replace(SONNET_55, propositos={k: v for k, v in SONNET_55.propositos.items()
                                                if k is not CallPurpose.VISION}), "que faltan \\['vision'\\]"),
    (dataclasses.replace(SONNET_55, estado="probando"), "estado 'probando' desconocido"),
])
def test_el_registro_rechaza_perfiles_55_incoherentes(perfil_malo, motivo):
    with pytest.raises(ModelConfigError, match=motivo):
        validar_perfil(perfil_malo)


# ── la tool obligatoria: presencia exigida ─────────────────────────────────────────────

class _Bloque:
    def __init__(self, tipo, nombre=None, entrada=None):
        self.type, self.name, self.input = tipo, nombre, entrada


class _Resp:
    def __init__(self, stop, *bloques):
        self.stop_reason, self.content = stop, list(bloques)


def test_input_de_tool():
    con_tool = _Resp("tool_use", _Bloque("text"), _Bloque("tool_use", "t", {"a": 1}))
    for p in (SONNET_5, SONNET_55):
        assert ModelRuntime(p).input_de_tool(con_tool, "t") == {"a": 1}
        for sin in (_Resp("end_turn", _Bloque("text")), _Resp("tool_use", _Bloque("tool_use", "otra", {}))):
            with pytest.raises(ToolObligatoriaAusente, match="sin tool_use"):
                ModelRuntime(p).input_de_tool(sin, "t")
    # Con tool forzada (5) se conserva lo de siempre. Sin ella (5.5) no vale una respuesta truncada
    # o rechazada aunque traiga el tool_use, ni una obligación repartida en varias llamadas: es lo
    # que 5.5 hacía con `strict` (resultados/micro_p_btlow__S55A.jsonl).
    for cortada in (_Resp("max_tokens", _Bloque("tool_use", "t", {"a": 1})),
                    _Resp("refusal", _Bloque("tool_use", "t", {"a": 1})),
                    _Resp("tool_use", _Bloque("tool_use", "t", {"a": 1}), _Bloque("tool_use", "t", {"b": 2}))):
        assert ModelRuntime(SONNET_5).input_de_tool(cortada, "t") == {"a": 1}
        with pytest.raises(ToolObligatoriaAusente, match="max_tokens|refusal|2 llamadas"):
            ModelRuntime(SONNET_55).input_de_tool(cortada, "t")


def _cliente_que_responde(contenido: list, stop: str = "end_turn"):
    def _h(_req):
        return httpx.Response(200, json={
            "id": "msg_x", "type": "message", "role": "assistant", "model": M55, "content": contenido,
            "stop_reason": stop, "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1}})
    return anthropic.AsyncAnthropic(api_key="sk-falsa", max_retries=0,
                                    http_client=httpx.AsyncClient(transport=httpx.MockTransport(_h)))


async def test_55_sin_tool_cae_en_el_fallo_de_siempre_de_cada_proposito_y_queda_registrado(monkeypatch, caplog):
    """Sin tool forzada, el modelo puede contestar en texto. No se degrada en silencio: cada
    propósito cae en el MISMO fallo que ya tenía ante un error del proveedor, y queda en el log."""
    monkeypatch.setattr(config.settings, "llm_model", M55)
    monkeypatch.setattr(config.settings, "llm_permitir_candidato", True)
    monkeypatch.setattr(config.settings, "anthropic_api_key", "sk-falsa")
    solo_texto = [{"type": "text", "text": "No necesito la herramienta."}]
    for m in (preferencias, interprete, match, vision):
        monkeypatch.setattr(m, "_client", lambda: _cliente_que_responde(solo_texto))
    caplog.set_level("WARNING")
    assert await preferencias.extraer_preferencias(["quiero 2 dormitorios"]) == {}
    assert await interprete.proponer_con_modelo("quiero comprar") == ()
    assert await match._justificar("b", "texto", [{"activo_id": "a", "direccion": "d", "tipo_activo": "t"}]) == {}
    with pytest.raises(vision.ExtractionInvalidError):
        await vision.extract_ficha_from_b64("AAAA")
    assert caplog.text.count("tool obligatoria") >= 3, caplog.text
