"""F3-TOOLS-MIN-1B · lo que congela la sonda de lectura en runtime.

QUÉ DEMUESTRA ESTE FICHERO, y qué NO.

    demuestra   que el `CurrentUser` nacido en la frontera autenticada —el objeto, no una
                copia ni un id reconstruido— llega intacto hasta el lector, y que nada que
                el modelo, el body o el estado puedan escribir cambia de quién se lee
    NO demuestra que el BuyerContext gobierne una decisión. En LEVEL 1 está DISPONIBLE en
                runtime y no lo consume nadie: la sonda devuelve un desenlace y descarta
                el contexto

1A probó que el lector es correcto, con un principal FABRICADO por las pruebas. Esto prueba
la otra mitad: la procedencia. Capacidad frente a autoridad efectiva.
"""

from __future__ import annotations

import ast
import asyncio
import datetime as dt
import pathlib
import uuid

import pytest

from app.buyer import lectura_runtime as lr
from app.buyer.lectura import PrincipalNoAutenticado
from app.buyer.lectura_runtime import (
    DesenlaceLectura,
    ObservacionLectura,
    observar_lectura_runtime,
)
from app.contracts.buyer_v0 import BuyerContextV0, Objective

RAIZ = pathlib.Path(__file__).resolve().parent.parent
APP = RAIZ / "app"
MODULO = APP / "buyer" / "lectura_runtime.py"
CHAT = APP / "routers" / "chat.py"

A = str(uuid.uuid4())
B = str(uuid.uuid4())
CUANDO = dt.datetime(2026, 9, 11, 12, 0, tzinfo=dt.timezone.utc)


# ── Dobles ─────────────────────────────────────────────────────────────────────────


class _Resultado:
    def __init__(self, fila):
        self._fila = fila

    def mappings(self):
        return self

    def first(self):
        return self._fila


class _Sesion:
    def __init__(self, head=None, buyer_id=A):
        self.sentencias: list[str] = []
        self.commits = 0
        self._head, self._buyer_id = head, buyer_id

    async def execute(self, stmt, params=None):
        self.sentencias.append(str(stmt))
        if (params or {}).get("b") != self._buyer_id or self._head is None:
            return _Resultado(None)
        return _Resultado({"buyer_id": self._buyer_id, "context_revision": self._head,
                           "context_json": BuyerContextV0(
                               buyer_id=self._buyer_id, objective=Objective.RENT,
                               updated_at=CUANDO).model_dump(mode="json")})

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass


def _principal_desde_claims(claims: dict):
    """Construye el sujeto COMO LO HACE `app/auth.py:165`: `user_id = claims["sub"]`.

    Empezar desde los claims y no desde un id suelto es lo que hace que T4b mida procedencia
    y no sólo el paso de un parámetro.
    """
    from app.auth import CurrentUser
    return CurrentUser(user_id=claims["sub"], email=claims.get("email"))


def _mutaciones(sesion) -> list[str]:
    return [s for s in sesion.sentencias
            if any(v in s.upper() for v in ("INSERT", "UPDATE", "DELETE", "FOR UPDATE"))]


@pytest.fixture
def canary(monkeypatch):
    """Canary encendido para A. Devuelve un ayudante para reconfigurarlo."""
    def _configurar(flag=True, allowlist=A):
        monkeypatch.setattr(lr.settings, "buyer_context_read_shadow", flag, raising=False)
        monkeypatch.setattr(lr.settings, "buyer_shadow_allowlist", allowlist, raising=False)
    _configurar()
    return _configurar


# ══ T1 · FLAG OFF ══════════════════════════════════════════════════════════════════


async def test_T1_flag_apagado_no_llama_al_lector(canary, monkeypatch):
    canary(flag=False)
    llamadas = []
    monkeypatch.setattr(lr, "leer_contexto_del_principal",
                        lambda *a, **k: llamadas.append(1))
    sesion = _Sesion(head=0)
    obs = await observar_lectura_runtime(_principal_desde_claims({"sub": A}), db=sesion)
    assert obs.desenlace is DesenlaceLectura.DESACTIVADA
    assert llamadas == [] and sesion.sentencias == []
    assert obs.hubo_lectura is False


# ══ T2 · ALLOWLIST VACÍA ═══════════════════════════════════════════════════════════


@pytest.mark.parametrize("lista", ["", "   ", ",", ",,"])
async def test_T2_allowlist_vacia_no_lee_a_nadie(canary, lista):
    canary(flag=True, allowlist=lista)
    sesion = _Sesion(head=0)
    obs = await observar_lectura_runtime(_principal_desde_claims({"sub": A}), db=sesion)
    assert obs.desenlace is DesenlaceLectura.FUERA_DE_COHORTE
    assert sesion.sentencias == []


@pytest.mark.parametrize("comodin", ["*", "all", "1", "true", "%"])
async def test_T2b_no_existe_comodin(canary, comodin):
    """Fail-closed: un comodín es un identificador literal que nadie tiene."""
    canary(flag=True, allowlist=comodin)
    sesion = _Sesion(head=0)
    obs = await observar_lectura_runtime(_principal_desde_claims({"sub": A}), db=sesion)
    assert obs.desenlace is DesenlaceLectura.FUERA_DE_COHORTE
    assert sesion.sentencias == []


async def test_T2c_pertenecer_a_la_lista_SI_lee(canary):
    """LA MITAD POSITIVA: sin ella, «nadie lee» sería cierto y vacío."""
    canary(flag=True, allowlist=f"otro,{A.upper()} , tercero")
    obs = await observar_lectura_runtime(_principal_desde_claims({"sub": A}), db=_Sesion(head=2))
    assert obs.desenlace is DesenlaceLectura.LEIDO and obs.revision == 2


async def test_T2d_un_id_que_es_TROZO_de_otro_no_entra(canary):
    """Sin `in` sobre la cadena cruda: un prefijo no es pertenencia."""
    canary(flag=True, allowlist=A)
    obs = await observar_lectura_runtime(_principal_desde_claims({"sub": A[:8]}), db=_Sesion())
    assert obs.desenlace is DesenlaceLectura.FUERA_DE_COHORTE


# ══ T3 · USUARIO AUTENTICADO ═══════════════════════════════════════════════════════


async def test_T3_el_runtime_lee_al_usuario_autenticado(canary):
    obs = await observar_lectura_runtime(_principal_desde_claims({"sub": A}), db=_Sesion(head=4))
    assert obs.desenlace is DesenlaceLectura.LEIDO
    assert obs.revision == 4 and obs.hubo_lectura


async def test_T3_sin_memoria_se_consulto_igual(canary):
    """`SIN_CONTEXTO` no es `FUERA_DE_COHORTE`: aquí SÍ se consultó la base."""
    sesion = _Sesion()
    obs = await observar_lectura_runtime(_principal_desde_claims({"sub": A}), db=sesion)
    assert obs.desenlace is DesenlaceLectura.SIN_CONTEXTO
    assert obs.revision is None and obs.hubo_lectura
    assert len(sesion.sentencias) == 1


# ══ T3b · PRINCIPAL FALSIFICADO ════════════════════════════════════════════════════


def test_T3b_chat_pasa_EL_principal_y_nada_derivable(canary=None):
    """La llamada en `chat.py` recibe exactamente `user`.

    No `payload.*`, no `request.*`, no un id sacado del estado ni del cuerpo. Se mira el
    AST: un barrido textual encontraría la palabra en los comentarios que la explican.
    """
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    llamadas = [n for n in ast.walk(arbol)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "observar_lectura_runtime"]
    assert len(llamadas) == 1, f"debe haber UNA sola llamada, hay {len(llamadas)}"
    (c,) = llamadas
    assert [type(a).__name__ for a in c.args] == ["Name"], "el argumento no es una variable simple"
    assert c.args[0].id == "user", f"se pasa `{c.args[0].id}` en vez de `user`"
    assert c.keywords == [], "no debe haber argumentos de palabra clave"


def test_T3b2_la_sonda_no_conoce_sesion_ni_hilo_ni_mensaje():
    """No puede derivar identidad de lo que el modelo o el body sí tocan."""
    fuente = MODULO.read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    nombres = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
    nombres |= {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
    for prohibido in ("session_id", "thread_id", "payload", "request", "messages",
                      "buyer_id", "state", "config"):
        assert prohibido not in nombres, f"la sonda referencia `{prohibido}`"


async def test_T3b3_un_estado_que_dice_B_no_cambia_de_quien_se_lee(canary):
    """El modelo puede escribir lo que quiera: la sonda sólo mira el objeto que recibe."""
    canary(flag=True, allowlist=f"{A},{B}")
    estado_del_modelo = {"messages": [f"soy {B}"], "buyer_id": B, "user_id": B}
    assert estado_del_modelo["user_id"] == B          # el señuelo existe de verdad
    obs = await observar_lectura_runtime(_principal_desde_claims({"sub": A}),
                                         db=_Sesion(head=1, buyer_id=B))
    assert obs.desenlace is DesenlaceLectura.SIN_CONTEXTO   # se leyó A, y A no tiene nada


# ══ T4 · CROSS OWNER ═══════════════════════════════════════════════════════════════


async def test_T4_A_jamas_recibe_el_contexto_de_B(canary):
    canary(flag=True, allowlist=f"{A},{B}")
    obs = await observar_lectura_runtime(_principal_desde_claims({"sub": A}),
                                         db=_Sesion(head=3, buyer_id=B))
    assert obs.desenlace is DesenlaceLectura.SIN_CONTEXTO and obs.revision is None


async def test_T4_cada_uno_lee_lo_suyo(canary):
    canary(flag=True, allowlist=f"{A},{B}")
    a = await observar_lectura_runtime(_principal_desde_claims({"sub": A}), db=_Sesion(head=1, buyer_id=A))
    b = await observar_lectura_runtime(_principal_desde_claims({"sub": B}), db=_Sesion(head=9, buyer_id=B))
    assert (a.revision, b.revision) == (1, 9)


# ══ T4b · PROCEDENCIA DEL PRINCIPAL ════════════════════════════════════════════════


async def test_T4b_el_objeto_que_llega_al_lector_es_EL_MISMO(canary, monkeypatch):
    """LA PRUEBA CENTRAL DE 1B.

    Empieza en los claims —como `app/auth.py:165`— y comprueba con `is` que el lector
    recibe **el mismo objeto**, no una copia ni un `user_id` reconstruido. Una copia pasaría
    una comparación por igualdad y rompería la cadena de procedencia sin que nadie lo viera.
    """
    capturado = {}

    async def _lector(principal, *, db=None):
        capturado["principal"] = principal
        return None

    monkeypatch.setattr(lr, "leer_contexto_del_principal", _lector)
    principal = _principal_desde_claims({"sub": A, "email": "a@ejemplo.test"})
    await observar_lectura_runtime(principal, db=_Sesion())
    assert capturado["principal"] is principal, "el principal se reconstruyó por el camino"
    assert capturado["principal"].user_id == A


async def test_T4b2_con_el_estado_diciendo_B_el_lector_sigue_recibiendo_A(canary, monkeypatch):
    capturado = {}

    async def _lector(principal, *, db=None):
        capturado["principal"] = principal
        return None

    monkeypatch.setattr(lr, "leer_contexto_del_principal", _lector)
    canary(flag=True, allowlist=f"{A},{B}")
    _ = {"model_says": B, "tool_call": {"buyer_id": B}}     # señuelos
    principal = _principal_desde_claims({"sub": A})
    await observar_lectura_runtime(principal, db=_Sesion())
    assert capturado["principal"].user_id == A
    assert capturado["principal"].user_id != B


def test_T4b3_el_espia_SABE_ver_una_reconstruccion():
    """LA MITAD NEGATIVA: si `is` no distinguiera copia de original, T4b sería vacía."""
    from app.auth import CurrentUser
    original = CurrentUser(user_id=A)
    copia = CurrentUser(user_id=A)
    assert copia == original and copia is not original


# ══ T5 · ANÓNIMO ═══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("anonimo", [None, "", "   "])
async def test_T5_el_anonimo_no_se_lee_y_no_se_inventa(canary, anonimo):
    from app.auth import CurrentUser
    principal = None if anonimo is None else CurrentUser(user_id="x").model_copy(
        update={"user_id": anonimo})
    sesion = _Sesion(head=0)
    obs = await observar_lectura_runtime(principal, db=sesion)
    assert obs.desenlace is DesenlaceLectura.SIN_PRINCIPAL
    assert sesion.sentencias == [] and obs.revision is None


async def test_T5b_el_anonimo_no_levanta_excepcion_hacia_el_turno(canary):
    """1A levanta `PrincipalNoAutenticado`; la sonda NO la deja salir al chat."""
    obs = await observar_lectura_runtime(None, db=_Sesion())
    assert isinstance(obs, ObservacionLectura)


# ══ T6 · SESIÓN RECLAMADA ══════════════════════════════════════════════════════════


def test_T6_el_seam_va_DESPUES_de_la_reclamacion():
    """El orden importa: si la sonda corriera antes del claim, un hilo recién reclamado
    leería con `user` correcto pero antes de que la propiedad se moviera."""
    fuente = CHAT.read_text(encoding="utf-8")
    i_autoridad = fuente.index("autoridad = await _exigir_autoridad")
    i_claim = fuente.index("await reclamar_sesion_anonima")
    i_sonda = fuente.index("await observar_lectura_runtime")
    i_branch = fuente.index("    if stream:")
    assert i_autoridad < i_claim < i_sonda < i_branch


def test_T6b_el_session_id_NO_se_usa_como_identidad_de_comprador():
    """`session_id`/`thread_id` son autoridad del HILO, no identidad del comprador.
    Derivar comprador de ellos sería fabricar identidad desde una capacidad."""
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    fuente_plana = ast.dump(arbol)
    for prohibido in ("session_id", "thread_id", "resume"):
        assert prohibido not in fuente_plana


# ══ T7 · CAMINO DE SÓLO LECTURA ════════════════════════════════════════════════════


async def test_T7_N_lecturas_no_emiten_escritura_ni_revision(canary):
    sesion = _Sesion(head=1)
    for _ in range(5):
        await observar_lectura_runtime(_principal_desde_claims({"sub": A}), db=sesion)
    assert len(sesion.sentencias) == 5
    assert _mutaciones(sesion) == [] and sesion.commits == 0


async def test_T7b_la_sonda_no_invoca_al_updater(canary, monkeypatch):
    import app.buyer.sombra as sombra
    llamadas = []
    monkeypatch.setattr(sombra, "actualizar", lambda *a, **k: llamadas.append(1),
                        raising=False)
    await observar_lectura_runtime(_principal_desde_claims({"sub": A}), db=_Sesion(head=0))
    assert llamadas == []


def test_T7c_la_sonda_no_afirma_privilegios_de_base():
    """`CODE PATH READ-ONLY` ≠ `POSTGRES PRIVILEGES READ-ONLY`. El módulo no lo promete."""
    fuente = MODULO.read_text(encoding="utf-8").lower()
    assert "privilegio" not in fuente and "read only" not in fuente


# ══ T8 · FALLA ABIERTA ═════════════════════════════════════════════════════════════


@pytest.mark.parametrize("boom", [RuntimeError, ConnectionError, ValueError,
                                  PrincipalNoAutenticado])
async def test_T8_un_fallo_del_lector_no_rompe_el_turno(canary, monkeypatch, boom):
    async def _revienta(principal, *, db=None):
        raise boom("simulado")

    monkeypatch.setattr(lr, "leer_contexto_del_principal", _revienta)
    obs = await observar_lectura_runtime(_principal_desde_claims({"sub": A}), db=_Sesion())
    assert obs.desenlace is DesenlaceLectura.FALLO
    assert obs.revision is None


async def test_T8b_el_fallo_se_REGISTRA_no_se_traga(canary, monkeypatch, caplog):
    async def _revienta(principal, *, db=None):
        raise RuntimeError("simulado")

    monkeypatch.setattr(lr, "leer_contexto_del_principal", _revienta)
    with caplog.at_level("ERROR"):
        await observar_lectura_runtime(_principal_desde_claims({"sub": A}), db=_Sesion())
    assert any("canary" in r.message or "canary" in r.getMessage() for r in caplog.records)


async def test_T8c_el_log_NO_lleva_nada_sensible(canary, caplog):
    with caplog.at_level("INFO"):
        await observar_lectura_runtime(
            _principal_desde_claims({"sub": A, "email": "secreto@ejemplo.test"}),
            db=_Sesion(head=3))
    texto = " ".join(r.getMessage() for r in caplog.records)
    assert A not in texto, "el user_id crudo aparece en el log"
    assert "secreto@ejemplo.test" not in texto
    assert "presupuesto" not in texto and "budget" not in texto


# ══ T9 · UN SOLO SEAM ══════════════════════════════════════════════════════════════


def _llamadores(objetivos: set[str], ficheros) -> list[str]:
    hallados = []
    for f in ficheros:
        try:
            arbol = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
            continue
        for n in ast.walk(arbol):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in objetivos:
                hallados.append(f"{f.name}:{n.lineno}")
            elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in objetivos:
                hallados.append(f"{f.name}:{n.lineno}")
    return hallados


def _ficheros_de_app(excluir):
    return [p for p in sorted(APP.rglob("*.py")) if p not in excluir] + [RAIZ / "main.py"]


def test_T9_hay_EXACTAMENTE_un_seam_productivo():
    """Un solo llamador. Dos ramas duplicadas es el defecto exacto de E3.2b.4."""
    assert _llamadores({"observar_lectura_runtime"}, _ficheros_de_app({MODULO})) == \
        [f"chat.py:{_linea_de_la_sonda()}"]


def _linea_de_la_sonda() -> int:
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    return next(n.lineno for n in ast.walk(arbol)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                and n.func.id == "observar_lectura_runtime")


def test_T9_los_llamadores_del_lector_de_1A_son_un_conjunto_EXACTO():
    """De 0 a 1 en 1B, de 1 a 2 en R0G — y cada salto lo exigió esta guarda antes de ocurrir.

    Se congelan NOMBRES, no un conteo: `len(...) == 2` lo cumplirían también dos llamadores
    equivocados, y entonces la guarda dejaría de vigilar lo único que importa —QUIÉN lee la
    memoria del comprador—. Sin comodín y sin `startswith("app/buyer")`.
    """
    fuera_de_la_sonda = _llamadores({"leer_contexto_del_principal"},
                                    _ficheros_de_app({MODULO, APP / "buyer" / "lectura.py"}))
    # Por fichero, no por línea: el número se mueve con cualquier comentario.
    assert {h.split(":")[0] for h in fuera_de_la_sonda} == {"decision_shadow.py"}, (
        f"alguien más llama al lector: {fuera_de_la_sonda}")
    assert len(fuera_de_la_sonda) == 1, (
        f"el comparador lo llama {len(fuera_de_la_sonda)} veces; una lectura por turno")

    dentro = _llamadores({"leer_contexto_del_principal"}, [MODULO])
    assert len(dentro) == 1, f"la sonda lo llama {len(dentro)} veces"


def test_T9b_el_censo_SABE_ver_un_segundo_llamador(tmp_path):
    """LA MITAD NEGATIVA."""
    f = tmp_path / "otro.py"
    f.write_text("observar_lectura_runtime(user)\n", encoding="utf-8")
    assert _llamadores({"observar_lectura_runtime"}, [f]) != []


# ══ T10 · SIN CONSUMIDOR DE PRODUCTO ═══════════════════════════════════════════════


def test_T10_la_observacion_NO_PUEDE_transportar_el_contexto():
    """La frontera de LEVEL 1 es de TIPOS, no de disciplina: si `ObservacionLectura`
    pudiera llevar el `BuyerContextV0`, el siguiente lo enchufaría al prompt sin tocar
    `lectura_runtime.py` y el diff no lo delataría."""
    campos = set(ObservacionLectura.__dataclass_fields__)
    assert campos == {"desenlace", "revision", "duracion_ms"}
    obs = ObservacionLectura(DesenlaceLectura.LEIDO, revision=1, duracion_ms=2)
    assert not any(isinstance(v, BuyerContextV0) for v in vars(obs).values())


def test_T10b_chat_DESCARTA_el_resultado():
    """La llamada es una sentencia de expresión, no una asignación: nada se queda con ella."""
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    for n in ast.walk(arbol):
        if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            volcado = ast.dump(n)
            assert "observar_lectura_runtime" not in volcado, (
                "el resultado de la sonda se está guardando en una variable")


def test_T10c_el_contexto_no_cruza_a_estado_ni_config_ni_prompt():
    """Ni `AgentState`, ni `_langgraph_config`, ni el prompt cambian por esta unidad."""
    estado = (APP / "agent" / "state.py").read_text(encoding="utf-8")
    for prohibido in ("buyer", "principal", "user_id", "CurrentUser"):
        assert prohibido not in estado, f"`{prohibido}` entró en AgentState"
    cfg = ast.parse(CHAT.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(cfg)
              if isinstance(n, ast.FunctionDef) and n.name == "_langgraph_config")
    volcado = ast.dump(fn)
    for prohibido in ("buyer", "principal", "user_id"):
        assert prohibido not in volcado, f"`{prohibido}` entró en _langgraph_config"


def test_T10d_la_sonda_no_arrastra_superficie_de_producto():
    """Sus imports de `app.*` son exactamente tres. Lo demás es stdlib.

    Se afirma sobre el subconjunto `app.*` y no sobre el conjunto entero a propósito: atar
    la prueba a la lista literal de módulos estándar la rompería el día que alguien añada un
    `import logging`, y eso no es superficie de producto. Lo que hay que vigilar es qué
    partes del SISTEMA toca.
    """
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    modulos = {n.module or "" for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)}
    modulos |= {a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
    propios = {m for m in modulos if m.startswith("app.")}
    assert propios == {"app.buyer.lectura", "app.buyer.sombra", "app.config"}, propios
    for prohibido in ("app.agent", "app.routers", "app.encaje", "app.orden",
                      "app.preferencias", "app.place", "app.decision", "app.contracts"):
        assert not any(m.startswith(prohibido) for m in modulos), f"toca {prohibido}"


# ══ T11 · PARIDAD ══════════════════════════════════════════════════════════════════


_AGENT_TOOLS_ESPERADAS = [
    "tool_find_assets_by_text", "tool_geocode_address", "tool_search_nearby_assets",
    "tool_fetch_asset_lifecycle_specs", "tool_analyze_location", "tool_analyze_investment",
    "tool_connect_with_broker", "tool_traducir_estilo_de_vida", "tool_priorizar_opcion",
]


def test_T11_el_toolset_productivo_no_cambia():
    arbol = ast.parse((APP / "agent" / "tools.py").read_text(encoding="utf-8"))
    for n in ast.walk(arbol):
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "AGENT_TOOLS" for t in n.targets):
            assert [e.id for e in n.value.elts] == _AGENT_TOOLS_ESPERADAS
            return
    raise AssertionError("no se encontró AGENT_TOOLS")


def test_T11b_el_estado_inicial_del_turno_no_gana_claves():
    """`_estado_inicial_del_turno` es el único constructor del estado (STATE-LINEAGE-R1).
    Si la sonda hubiera añadido una clave, el panel o la prosa podrían cambiar."""
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.FunctionDef) and n.name == "_estado_inicial_del_turno")
    ret = next(n for n in ast.walk(fn) if isinstance(n, ast.Return))
    claves = {k.value for k in ret.value.keys}
    assert claves == {"messages", "spatial_context", "sql_results", "cards",
                      "descartadas", "encaje_contexto"}


async def test_T11c_el_desenlace_no_depende_del_turno_solo_del_sujeto(canary):
    """La sonda no mira el mensaje: dos turnos distintos del mismo sujeto dan lo mismo."""
    s1, s2 = _Sesion(head=7), _Sesion(head=7)
    p = _principal_desde_claims({"sub": A})
    assert (await observar_lectura_runtime(p, db=s1)).revision == \
           (await observar_lectura_runtime(p, db=s2)).revision


# ══ T12 · SIN ESCAPE DINÁMICO ══════════════════════════════════════════════════════


def test_T12_no_hay_carga_dinamica_que_burle_el_censo():
    """Mientras no exista, los censos AST de T9/T10 cubren la superficie."""
    sospechosos = []
    for f in _ficheros_de_app(set()):
        arbol = ast.parse(f.read_text(encoding="utf-8"))
        for n in ast.walk(arbol):
            if isinstance(n, ast.Name) and n.id == "__import__":
                sospechosos.append(f"{f.name}:{n.lineno}")
            if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("importlib"):
                sospechosos.append(f"{f.name}:{n.lineno}")
            if isinstance(n, ast.Import) and any(a.name.startswith("importlib") for a in n.names):
                sospechosos.append(f"{f.name}:{n.lineno}")
    assert sospechosos == [], f"carga dinámica: los censos AST hay que revisarlos ({sospechosos})"


# ══ T13 · CONTROL NEGATIVO ═════════════════════════════════════════════════════════


async def test_T13a_neutralizar_el_FLAG_se_detecta(canary):
    """Si el flag dejara de gobernar, T1 tendría que ponerse roja."""
    canary(flag=False)
    apagada = await observar_lectura_runtime(_principal_desde_claims({"sub": A}), db=_Sesion(head=1))
    canary(flag=True)
    encendida = await observar_lectura_runtime(_principal_desde_claims({"sub": A}), db=_Sesion(head=1))
    assert apagada.desenlace is not encendida.desenlace


async def test_T13b_neutralizar_la_ALLOWLIST_se_detecta(canary):
    canary(flag=True, allowlist="")
    fuera = await observar_lectura_runtime(_principal_desde_claims({"sub": A}), db=_Sesion(head=1))
    canary(flag=True, allowlist=A)
    dentro = await observar_lectura_runtime(_principal_desde_claims({"sub": A}), db=_Sesion(head=1))
    assert fuera.desenlace is DesenlaceLectura.FUERA_DE_COHORTE
    assert dentro.desenlace is DesenlaceLectura.LEIDO


async def test_T13c_neutralizar_la_GUARDA_DE_ANONIMO_se_detecta(canary):
    """Si el anónimo dejara de cortarse, llegaría al lector y éste levantaría."""
    with pytest.raises(PrincipalNoAutenticado):
        await lr.leer_contexto_del_principal(None, db=_Sesion())
    assert (await observar_lectura_runtime(None, db=_Sesion())).desenlace \
        is DesenlaceLectura.SIN_PRINCIPAL


def test_T13d_neutralizar_el_SEAM_UNICO_se_detecta(tmp_path):
    f = tmp_path / "segundo_seam.py"
    f.write_text("async def otro(u):\n    await observar_lectura_runtime(u)\n", encoding="utf-8")
    assert len(_llamadores({"observar_lectura_runtime"}, [f])) == 1


async def test_T13e_neutralizar_la_PROCEDENCIA_se_detecta():
    """Si alguien reconstruyera el principal desde `user_id`, `is` lo vería y `==` no.

    Es la mitad negativa de T4b: demuestra que la aserción de identidad distingue el objeto
    original de una copia con los mismos campos — que es exactamente la forma en que una
    cadena de procedencia se rompe sin que nadie lo note.
    """
    from app.auth import CurrentUser
    capturado = {}

    async def _sonda_rota(principal):
        capturado["p"] = CurrentUser(user_id=principal.user_id)   # copia, no el original

    original = CurrentUser(user_id=A)
    await _sonda_rota(original)
    assert capturado["p"] == original, "la copia es igual en contenido…"
    assert capturado["p"] is not original, "…y aun así T4b la distingue"
