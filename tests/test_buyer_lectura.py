"""F3-TOOLS-MIN-1A · lo que congela la costura de lectura del BuyerContext.

QUÉ DEMUESTRA ESTE FICHERO, y qué NO.

    demuestra   que Contexto puede obtener correctamente el BuyerContextV0 persistido de un
                comprador autorizado: la revisión vigente, con su número, sin escribir nada,
                y sin que un principal pueda alcanzar la memoria de otro
    NO demuestra que el producto lo use. `PRODUCTION_READ_CALLERS = 0` es una CONDICIÓN DE
                PASS de esta unidad (§G), no una limitación descubierta al final

LA MITAD NEGATIVA. Cada guarda que pueda quedarse verde estando rota lleva su prueba
gemela, que construye la infracción y exige que la sonda la vea. Sin eso, un fichero de
pruebas demuestra que hoy nadie infringe la regla, no que la regla esté vigilada — y en
este repositorio esa diferencia ya costó ocho guardas inertes.
"""

from __future__ import annotations

import ast
import datetime as dt
import pathlib
import uuid

import pytest

from app.buyer import lectura
from app.buyer.lectura import PrincipalNoAutenticado, leer_contexto_del_principal
from app.contracts.buyer_v0 import BuyerContextV0, Objective

RAIZ = pathlib.Path(__file__).resolve().parent.parent
APP = RAIZ / "app"
MODULO = APP / "buyer" / "lectura.py"

A = str(uuid.uuid4())
B = str(uuid.uuid4())
CUANDO = dt.datetime(2026, 9, 11, 12, 0, tzinfo=dt.timezone.utc)


# ── El doble de sesión ─────────────────────────────────────────────────────────────
#
# Registra CADA sentencia y cada parámetro, y cuenta commits. No es un atajo: es lo que
# permite afirmar «esta lectura no escribió» mirando el SQL que de verdad se emitió, en vez
# de mirar el estado después y confiar en que nadie lo repuso.


class _Principal:
    """Cualquier objeto con `user_id`, que es lo que el seam existente acepta."""

    def __init__(self, user_id):
        self.user_id = user_id


class _Resultado:
    def __init__(self, fila):
        self._fila = fila

    def mappings(self):
        return self

    def first(self):
        return self._fila


class _Sesion:
    """Base del comprador, con head explícito. Honra la semántica de `current_revision`."""

    def __init__(self, revisiones=None, head=None, buyer_id=A):
        self.sentencias: list[str] = []
        self.parametros: list[dict] = []
        self.commits = 0
        self.rollbacks = 0
        self._revisiones = revisiones or {}
        self._head = head
        self._buyer_id = buyer_id

    def _fila(self, params):
        if (params or {}).get("b") != self._buyer_id or self._head is None:
            return None
        return {"buyer_id": self._buyer_id, "context_revision": self._head,
                "context_json": self._revisiones[self._head]}

    async def execute(self, stmt, params=None):
        self.sentencias.append(str(stmt))
        self.parametros.append(params)
        return _Resultado(self._fila(params))

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _json(objective=Objective.UNKNOWN, buyer_id=A) -> dict:
    return BuyerContextV0(buyer_id=buyer_id, objective=objective,
                          updated_at=CUANDO).model_dump(mode="json")


def _sesion_con(head=0, buyer_id=A, objectives=None) -> _Sesion:
    objectives = objectives or {head: Objective.UNKNOWN}
    return _Sesion({r: _json(o, buyer_id) for r, o in objectives.items()},
                   head=head, buyer_id=buyer_id)


def _mutaciones(sesion) -> list[str]:
    """Las sentencias que NO son lectura. La lista vacía es la propiedad."""
    return [s for s in sesion.sentencias
            if any(v in s.upper() for v in ("INSERT", "UPDATE", "DELETE", "FOR UPDATE"))]


# ══ T1 · EXISTENCIA ════════════════════════════════════════════════════════════════


async def test_T1_devuelve_el_contexto_real_cuando_existe():
    ctx = await leer_contexto_del_principal(_Principal(A), db=_sesion_con(head=3))
    assert isinstance(ctx, BuyerContextV0)
    assert ctx.buyer_id == A


# ══ T2 · NONE ══════════════════════════════════════════════════════════════════════


async def test_T2_sin_contexto_persistido_devuelve_None():
    assert await leer_contexto_del_principal(_Principal(A), db=_Sesion()) is None


async def test_T2b_None_es_None_y_no_un_contexto_fabricado():
    """Un `BuyerContextV0` vacío sería indistinguible de un comprador real sin preferencias,
    y el llamador no podría saber si hay memoria o si se la acabamos de inventar."""
    r = await leer_contexto_del_principal(_Principal(A), db=_Sesion())
    assert r is None and not isinstance(r, BuyerContextV0)


# ══ T3 · REVISION ══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("rev", [0, 1, 7, 42])
async def test_T3_la_revision_devuelta_es_la_persistida(rev):
    ctx = await leer_contexto_del_principal(_Principal(A), db=_sesion_con(head=rev))
    assert ctx.context_revision == rev


async def test_T3b_la_revision_viene_de_la_FILA_y_no_del_json():
    """El `context_json` guardado lleva su propio `context_revision`, y el store lo pisa con
    el de la fila. Si algún día se leyera del json, una revisión renumerada mentiría."""
    sesion = _Sesion({5: {**_json(), "context_revision": 999}}, head=5)
    ctx = await leer_contexto_del_principal(_Principal(A), db=sesion)
    assert ctx.context_revision == 5


# ══ T4 · READ ONLY ═════════════════════════════════════════════════════════════════


async def test_T4_N_lecturas_no_emiten_una_sola_escritura():
    sesion = _sesion_con(head=2)
    for _ in range(5):
        await leer_contexto_del_principal(_Principal(A), db=sesion)
    assert len(sesion.sentencias) == 5
    assert _mutaciones(sesion) == []
    assert sesion.commits == 0 and sesion.rollbacks == 0


async def test_T4b_la_sonda_de_escritura_SABE_ver_una_mutacion():
    """LA MITAD NEGATIVA: si `_mutaciones` mirase mal, «cero escrituras» sería cierto y
    vacío para siempre."""
    sesion = _sesion_con()
    await sesion.execute("INSERT INTO buyer_context_revisions VALUES (1)", {})
    assert _mutaciones(sesion) != []


# ══ T5 · LATEST ════════════════════════════════════════════════════════════════════


async def test_T5_con_varias_revisiones_devuelve_la_VIGENTE_no_la_ultima():
    """El head es 1 y existen 0, 1 y 2. Devolver la 2 —«la más alta»— sería tan incorrecto
    como devolver la 0, y es el error que parece correcto."""
    sesion = _Sesion({0: _json(Objective.UNKNOWN), 1: _json(Objective.RENT),
                      2: _json(Objective.BUY)}, head=1)
    ctx = await leer_contexto_del_principal(_Principal(A), db=sesion)
    assert ctx.context_revision == 1
    assert ctx.objective is Objective.RENT


async def test_T5b_la_consulta_PIDE_el_head_y_no_un_maximo():
    """La otra mitad, y la que de verdad ata la propiedad al motor: el doble honra el head
    porque se lo dijimos, pero es el SQL quien tiene que pedirlo. Si la consulta usara
    `ORDER BY context_revision DESC LIMIT 1`, este doble seguiría verde y producción
    devolvería una revisión que el head no reconoce."""
    sesion = _sesion_con(head=1)
    await leer_contexto_del_principal(_Principal(A), db=sesion)
    sql = " ".join(sesion.sentencias[0].split()).lower()
    assert "r.context_revision = h.current_revision" in sql
    assert "order by" not in sql


# ══ T6 · ISOLATION ═════════════════════════════════════════════════════════════════


async def test_T6_cada_principal_lee_lo_suyo():
    assert (await leer_contexto_del_principal(
        _Principal(A), db=_sesion_con(head=0, buyer_id=A))).buyer_id == A
    assert (await leer_contexto_del_principal(
        _Principal(B), db=_sesion_con(head=0, buyer_id=B))).buyer_id == B


async def test_T6b_un_principal_NO_alcanza_la_memoria_de_otro():
    """La base sólo tiene a B; A pide y no recibe nada. El filtro es el `buyer_id` que salió
    del principal, no un parámetro que alguien pudiera pasar."""
    assert await leer_contexto_del_principal(
        _Principal(A), db=_sesion_con(head=0, buyer_id=B)) is None


def test_T6c_la_capacidad_NO_TIENE_por_donde_recibir_un_buyer_id():
    """LA PROPIEDAD ESTRUCTURAL, y la razón de que esta unidad exista.

    `store.cargar_ultima(buyer_id, ...)` acepta una cadena cualquiera. Esta capacidad no:
    su firma es `(principal, *, db)`. Un aislamiento comprobado con un `if` vive mientras
    nadie lo borre; una firma sin el parámetro no se puede infringir sin cambiar la firma,
    y eso aparece en el diff.
    """
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "leer_contexto_del_principal")
    posicionales = [a.arg for a in fn.args.args]
    solo_clave = [a.arg for a in fn.args.kwonlyargs]
    assert posicionales == ["principal"], f"la firma cambió: {posicionales}"
    assert solo_clave == ["db"], f"apareció un argumento de palabra clave: {solo_clave}"
    assert fn.args.vararg is None and fn.args.kwarg is None, (
        "*args/**kwargs reabrirían por detrás la superficie que la firma cierra")
    todos = posicionales + solo_clave
    assert not any("buyer" in a or "id" == a for a in todos), f"entra un id ajeno: {todos}"


# ══ T7 · PRINCIPAL AUSENTE O INVÁLIDO ══════════════════════════════════════════════
#
# GOBIERNA LA EXCEPCIÓN TIPADA, no `None`. Decidido antes de implementar: para quien LEE,
# «no hay sujeto» y «este sujeto no tiene estado» llevan a acciones opuestas —pedir que
# inicie sesión, o preguntarle qué busca—, y un único `None` obligaría a adivinar.


@pytest.mark.parametrize("malo", [None, "", "   ", "\t\n"])
async def test_T7_un_principal_sin_raiz_levanta_excepcion_tipada(malo):
    principal = None if malo is None else _Principal(malo)
    with pytest.raises(PrincipalNoAutenticado):
        await leer_contexto_del_principal(principal, db=_sesion_con(head=0))


async def test_T7b_sin_raiz_NO_se_toca_la_base():
    """Se sale antes de consultar: un principal sin raíz no consume ni una conexión."""
    sesion = _sesion_con(head=0)
    with pytest.raises(PrincipalNoAutenticado):
        await leer_contexto_del_principal(_Principal("  "), db=sesion)
    assert sesion.sentencias == []


async def test_T7c_sin_raiz_JAMAS_devuelve_el_contexto_de_otro():
    """El peor desenlace posible de esta unidad, y el único inaceptable."""
    sesion = _sesion_con(head=0, buyer_id=B)
    for malo in (None, _Principal(""), _Principal("   ")):
        with pytest.raises(PrincipalNoAutenticado):
            await leer_contexto_del_principal(malo, db=sesion)
    assert sesion.sentencias == []


async def test_T7d_PrincipalNoAutenticado_NO_se_confunde_con_ausencia_de_contexto():
    """Los dos desenlaces tienen que ser distinguibles por el llamador."""
    assert await leer_contexto_del_principal(_Principal(A), db=_Sesion()) is None
    with pytest.raises(PrincipalNoAutenticado):
        await leer_contexto_del_principal(None, db=_Sesion())


# ══ T8 · CERO LLAMADORES PRODUCTIVOS ═══════════════════════════════════════════════


def _ficheros_de_app():
    return [p for p in sorted(APP.rglob("*.py")) if p != MODULO] + [RAIZ / "main.py"]


def _llamadores(objetivos: set[str], ficheros) -> list[str]:
    """Censo por AST, no por texto: el comentario que explica una guarda cita la guarda, y
    un barrido textual se detecta a sí mismo. Ya pasó dos veces en este repositorio."""
    hallados = []
    for f in ficheros:
        try:
            arbol = ast.parse(f.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):  # pragma: no cover
            continue
        for n in ast.walk(arbol):
            if isinstance(n, ast.ImportFrom) and (n.module or "").endswith("buyer.lectura"):
                hallados.append(f"{f.name}:{n.lineno} import")
            elif isinstance(n, ast.Import) and any("buyer.lectura" in a.name for a in n.names):
                hallados.append(f"{f.name}:{n.lineno} import")
            elif isinstance(n, ast.Name) and n.id in objetivos:
                hallados.append(f"{f.name}:{n.lineno} {n.id}")
            elif isinstance(n, ast.Attribute) and n.attr in objetivos:
                hallados.append(f"{f.name}:{n.lineno} .{n.attr}")
    return hallados


_OBJETIVOS = {"leer_contexto_del_principal", "PrincipalNoAutenticado"}


def test_T8_PRODUCTION_READ_CALLERS_es_cero():
    """VERDE A PROPÓSITO. No es un defecto: 1A construye la capacidad y 1B decide quién la
    consume. La unidad que cablee un lector tendrá que cambiar esta guarda deliberadamente,
    que es justo lo que se quiere — que nadie la conecte sin darse cuenta."""
    assert _llamadores(_OBJETIVOS, _ficheros_de_app()) == []


def test_T8b_el_censo_SABE_ver_un_llamador(tmp_path):
    """LA MITAD NEGATIVA: un censo que mirase el sitio equivocado daría cero para siempre."""
    falso = tmp_path / "falso.py"
    falso.write_text("from app.buyer.lectura import leer_contexto_del_principal\n",
                     encoding="utf-8")
    assert _llamadores(_OBJETIVOS, [falso]) != []


# ══ T9 · SIN SUPERFICIE DE PRODUCTO ════════════════════════════════════════════════


def _lista_literal(fuente: pathlib.Path, nombre: str) -> list[str]:
    """El contenido de una lista de nombres, leído del AST y sin importar el módulo: cargar
    `app/agent/tools.py` arrastraría langchain y el cliente de Anthropic."""
    arbol = ast.parse(fuente.read_text(encoding="utf-8"))
    for n in ast.walk(arbol):
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == nombre for t in n.targets):
            return [e.id for e in n.value.elts if isinstance(e, ast.Name)]
    raise AssertionError(f"no se encontró `{nombre}` en {fuente.name}")


_AGENT_TOOLS_ESPERADAS = [
    "tool_find_assets_by_text", "tool_geocode_address", "tool_search_nearby_assets",
    "tool_fetch_asset_lifecycle_specs", "tool_analyze_location", "tool_analyze_investment",
    "tool_connect_with_broker", "tool_traducir_estilo_de_vida", "tool_priorizar_opcion",
]


def test_T9_AGENT_TOOLS_no_cambia():
    assert _lista_literal(APP / "agent" / "tools.py", "AGENT_TOOLS") == _AGENT_TOOLS_ESPERADAS


def _decoradores(nodo) -> list[str]:
    """El nombre de cada decorador, POR AST. `@tool` y `@tools.tool` cuentan igual."""
    fuera = []
    for d in nodo.decorator_list:
        objetivo = d.func if isinstance(d, ast.Call) else d
        if isinstance(objetivo, ast.Name):
            fuera.append(objetivo.id)
        elif isinstance(objetivo, ast.Attribute):
            fuera.append(objetivo.attr)
    return fuera


def test_T9b_la_capacidad_no_esta_registrada_como_tool():
    """Una tool visible al modelo puede invocarse, su resultado entra al contexto y puede
    cambiar la respuesta. Eso es consumo productivo y pertenece a 1B.

    SE MIRA EL AST, NO EL TEXTO, y la primera versión de esta prueba es la razón: decía
    `"@tool" not in fuente` y se puso roja contra un módulo que no tiene un solo decorador
    —encontró la frase «ni lleva `@tool`» de su propio docstring—. Es el mismo defecto que
    este repositorio ya había registrado dos veces, con `importorskip` y con
    `"osm" if pois else None`: **una guarda textual se detecta a sí misma.**
    """
    assert "leer_contexto_del_principal" not in _lista_literal(
        APP / "agent" / "tools.py", "AGENT_TOOLS")
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    for n in ast.walk(arbol):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert "tool" not in _decoradores(n), f"`{n.name}` está decorada como tool"


def test_T9b2_el_lector_de_decoradores_SABE_ver_un_tool():
    """LA MITAD NEGATIVA: un lector que mirase el sitio equivocado daría «sin decorar» para
    siempre. Cubre las tres formas: `@tool`, `@tool(...)` y `@tools.tool`."""
    for fuente in ("@tool\ndef f(): ...", "@tool()\ndef f(): ...", "@tools.tool\ndef f(): ..."):
        fn = ast.parse(fuente).body[0]
        assert "tool" in _decoradores(fn), f"no vio el decorador en: {fuente!r}"
    assert _decoradores(ast.parse("def f(): ...").body[0]) == []


def test_T9c_ni_el_agente_ni_los_routers_importan_la_capacidad():
    """El prompt, el ranking, el panel y la prosa viven detrás de estos dos paquetes. Si
    ninguno importa el módulo, ninguno pudo cambiar por su causa."""
    superficie = [p for p in sorted((APP / "agent").rglob("*.py"))]
    superficie += [p for p in sorted((APP / "routers").rglob("*.py"))]
    superficie += [APP / "encaje.py", APP / "orden.py", APP / "preferencias.py", RAIZ / "main.py"]
    assert _llamadores(_OBJETIVOS, superficie) == []


def test_T9d_la_capacidad_no_arrastra_superficie_de_producto():
    """Sus imports son el store y el contrato. Nada de routers, agente, encaje ni config."""
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    modulos = {n.module for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)}
    assert modulos == {"__future__", "app.buyer.store", "app.contracts.buyer_v0"}, modulos


# ══ T10 · CONTROL NEGATIVO ═════════════════════════════════════════════════════════
#
# No basta con que las pruebas pasen: hay que demostrar que rechazarían una función rota.
# Cada caso construye una implementación defectuosa PLAUSIBLE y ejerce contra ella la misma
# afirmación que usa su prueba positiva.


async def _roto_fabrica_contexto(principal, *, db=None):
    return BuyerContextV0(buyer_id=A, updated_at=CUANDO)


async def _roto_ignora_el_principal(principal, *, db=None):
    return await lectura.cargar_ultima(B, db=db)


async def _roto_devuelve_revision_ajena(principal, *, db=None):
    ctx = await leer_contexto_del_principal(principal, db=db)
    return None if ctx is None else ctx.model_copy(update={"context_revision": 99})


async def _roto_escribe_al_leer(principal, *, db=None):
    await db.execute("UPDATE buyer_context_heads SET updated_at = now()", {})
    return await leer_contexto_del_principal(principal, db=db)


async def test_T10a_la_suite_detecta_un_contexto_FABRICADO():
    assert await _roto_fabrica_contexto(_Principal(A), db=_Sesion()) is not None, (
        "la sonda de T2 no vería una función que inventa contexto")


async def test_T10b_la_suite_detecta_una_lectura_CROSS_OWNER():
    sesion = _sesion_con(head=0, buyer_id=B)
    fugado = await _roto_ignora_el_principal(_Principal(A), db=sesion)
    assert fugado is not None and fugado.buyer_id == B, (
        "la sonda de T6b no vería una función que ignora al principal")


async def test_T10c_la_suite_detecta_una_REVISION_incorrecta():
    ctx = await _roto_devuelve_revision_ajena(_Principal(A), db=_sesion_con(head=3))
    assert ctx.context_revision != 3, "la sonda de T3 no vería una revisión falseada"


async def test_T10d_la_suite_detecta_una_ESCRITURA_durante_la_lectura():
    sesion = _sesion_con(head=0)
    await _roto_escribe_al_leer(_Principal(A), db=sesion)
    assert _mutaciones(sesion) != [], "la sonda de T4 no vería una escritura al leer"


async def test_T10e_la_suite_detecta_que_el_principal_invalido_devuelva_algo():
    """Si la excepción se degradara a `None`, T7 dejaría de distinguir los dos desenlaces."""
    async def _roto_degrada(principal, *, db=None):
        try:
            return await leer_contexto_del_principal(principal, db=db)
        except PrincipalNoAutenticado:
            return None

    assert await _roto_degrada(None, db=_Sesion()) is None
    with pytest.raises(PrincipalNoAutenticado):
        await leer_contexto_del_principal(None, db=_Sesion())
