"""F3-DECISION-CORE-EXTRACTION-R0D · el núcleo puro de la decisión visible.

QUÉ CONGELA, y qué NO.

    congela    que `construir_panel` sigue produciendo EXACTAMENTE lo mismo después de
               extraer su tramo puro; que el núcleo recibe las filas YA leídas y no vuelve
               a pedirlas; y que no hace ninguna entrada/salida
    NO congela nada sobre el comprador. R0D es agnóstico del Buyer Harness: no lo importa,
               no lo nombra y no lo consume

## POR QUÉ EXISTE ESTA UNIDAD

El preflight de la comparación en sombra midió que el tramo fila → decisión visible es puro,
pero vivía INLINE dentro de `construir_panel`. Para ejecutar un contrafactual de un solo
campo sobre **las mismas filas** hacía falta poder llamarlo dos veces, y una segunda llamada
a `construir_panel` no sirve: volvería a consultar la base. Otro snapshot, otra ida a la DB.

R0D extrae el núcleo y **no lo llama dos veces**. Eso es la unidad siguiente.

## EL ORÁCULO

`_ESPERADO` son valores medidos sobre `a7fee44` **ANTES** de mover una línea, con el mismo
arnés que se usa aquí. No son «lo que debería dar»: son lo que daba. Si uno cambia, el
refactor cambió comportamiento observable — y eso es un fallo de R0D, no un número que haya
que actualizar.

Cubre los casos que §11 del encargo exige: sin preferencias, mascotas declaradas con dato
true/false/desconocido, mascotas NO declaradas con datos variados, filtros de operación y de
tipo (con y sin coincidencias), presupuesto dentro y fuera, mezcla de dimensiones, empates y
cobertura incompleta — más los dos bordes: sin ids, y más filas que ids.
"""

from __future__ import annotations

import ast
import asyncio
import json
import pathlib

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.decision import assembler

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FUENTE = RAIZ / "app" / "decision" / "assembler.py"
NUCLEO = "_decidir_desde_filas"


def _row(rid, **over):
    """Una fila de catastro tal como la devuelve `_fetch_cards_rows`."""
    row = {
        "id": rid,
        "direccion": f"Dir {rid}",
        "tipo_activo": "Departamento",
        "operacion": "ARRIENDO",
        "precio": 380,
        "imagen_url": None,
        "caminabilidad": 95,
        "caminabilidad_fuente": "osm",
        "ruido": "BAJO",
        "vegetacion": 42,
        "lat": -0.18,
        "lon": -78.48,
        "caracteristicas": {"num_dormitorios": 2, "acepta_mascotas": True},
        "servicios_cercanos": "\U0001F333 Parque a ~300 m",
        "conectividad": "\U0001F687 Metro a ~500 m (7 min a pie)",
    }
    row.update(over)
    return row


def _turno(ids):
    return [
        HumanMessage(content="consulta"),
        ToolMessage(content=json.dumps({"assets": [{"id": i} for i in ids]}),
                    name="tool_search_nearby_assets", tool_call_id="t1"),
        AIMessage(content="Encontré algunas opciones."),
    ]


@pytest.fixture
def catastro(monkeypatch):
    """Sustituye la ÚNICA entrada/salida del panel y CUENTA sus llamadas.

    El contador no es decorativo: T2 se apoya en él para afirmar que el refactor no duplicó
    la adquisición de filas, que es precisamente el modo de fallo que haría inútil al núcleo.
    """
    estado = {"llamadas": 0, "devueltas": None, "ids_pedidos": []}

    def _instalar(rows):
        async def fake_fetch(ids):
            estado["llamadas"] += 1
            estado["ids_pedidos"].append(list(ids))
            estado["devueltas"] = rows
            return (rows, {})

        monkeypatch.setattr(assembler, "_fetch_cards_rows", fake_fetch)
        return estado

    return _instalar


def _panel(catastro, ids, rows, prefs):
    catastro(rows)
    return asyncio.run(assembler.construir_panel(
        _turno(ids), preferencias=prefs, session_id="s-r0d"))


def _nucleo(ids, rows, prefs):
    """El núcleo, llamado DIRECTAMENTE. Sin panel, sin base, sin nada."""
    return assembler._decidir_desde_filas(
        rows, {}, ids=ids, preferencias=prefs, messages=_turno(ids), session_id="s-r0d")


def _ejes(panel):
    """Los ejes que MANDAN. `decision_id`/`created_at` no salen del panel, así que no
    entran: comparar identidad de ensamblado mediría el uuid4, no la decisión."""
    cards = panel["cards"]
    return {
        "orden": [c["id"] for c in cards],
        "descartadas": [c["id"] for c in panel["descartadas"]],
        "claves": sorted(panel.keys()),
        "encaje": {c["id"]: c["encaje"] for c in cards},
        "medido": {c["id"]: c["encaje_medido"] for c in cards},
        "cobertura": {c["id"]: c["encaje_cobertura"] for c in cards},
        "evaluadas": {c["id"]: c["encaje_evaluadas"] for c in cards},
        "declaradas": {c["id"]: c["encaje_declaradas"] for c in cards},
        "duros": {c["id"]: c["duros_incumplidos"] for c in cards},
        "razones": {c["id"]: [r["texto"] for r in (c["encaje_razones"] or [])]
                    for c in cards},
    }


# ── §11 · la matriz de casos, idéntica a la que produjo el oráculo ─────────────────

_PETS_SI = {"acepta_mascotas": True}
_MEZCLA = {"tipo_inmueble": "departamento", "presupuesto_max": 400, "dormitorios": 2,
           "acepta_mascotas": True, "tranquilidad": True, "caminable": True}


def _caso(nombre):
    """La entrada de cada caso. Se construye aquí y NO se comparte con el oráculo: si el
    arnés y los valores esperados salieran del mismo sitio, el test sería una tautología."""
    return {
        "sin_preferencias": (["a", "b", "c"], [_row("a"), _row("b"), _row("c")], {}),
        "mascotas_declaradas_dato_true": (["a", "b"], [_row("a"), _row("b")], _PETS_SI),
        "mascotas_declaradas_dato_false": (
            ["a", "b"],
            [_row("a", caracteristicas={"num_dormitorios": 2, "acepta_mascotas": False}),
             _row("b")], _PETS_SI),
        "mascotas_declaradas_dato_unknown": (
            ["a", "b"],
            [_row("a", caracteristicas={"num_dormitorios": 2}), _row("b")], _PETS_SI),
        "mascotas_mezcla_true_false_unknown": (
            ["a", "b", "c"],
            [_row("a", caracteristicas={"num_dormitorios": 2, "acepta_mascotas": True}),
             _row("b", caracteristicas={"num_dormitorios": 2, "acepta_mascotas": False}),
             _row("c", caracteristicas={"num_dormitorios": 2})], _PETS_SI),
        "mascotas_NO_declaradas_con_datos_variados": (
            ["a", "b", "c"],
            [_row("a", caracteristicas={"num_dormitorios": 2, "acepta_mascotas": True}),
             _row("b", caracteristicas={"num_dormitorios": 2, "acepta_mascotas": False}),
             _row("c", caracteristicas={"num_dormitorios": 2})], {"dormitorios": 2}),
        "filtro_operacion": (
            ["a", "b", "c"],
            [_row("a", operacion="VENTA", precio=250000), _row("b", operacion="ARRIENDO"),
             _row("c", operacion="MONITOREO_PASIVO")], {"operacion": "ARRIENDO"}),
        "filtro_operacion_sin_coincidencias": (
            ["a", "b"],
            [_row("a", operacion="VENTA", precio=250000),
             _row("b", operacion="MONITOREO_PASIVO")], {"operacion": "ARRIENDO"}),
        "filtro_tipo_inmueble": (
            ["a", "b", "c"],
            [_row("a", tipo_activo="Casa"), _row("b", tipo_activo="Departamento"),
             _row("c", tipo_activo=None)], {"tipo_inmueble": "departamento"}),
        "filtro_tipo_sin_coincidencias": (
            ["a", "b"],
            [_row("a", tipo_activo="Casa"), _row("b", tipo_activo="Oficina")],
            {"tipo_inmueble": "departamento"}),
        "presupuesto_dentro_y_fuera": (
            ["a", "b", "c"],
            [_row("a", precio=380), _row("b", precio=710), _row("c", precio=1500)],
            {"presupuesto_max": 700}),
        "mezcla_de_dimensiones": (
            ["a", "b", "c"],
            [_row("a"),
             _row("b", precio=900, ruido="ALTO", caminabilidad=20,
                  caracteristicas={"num_dormitorios": 4, "acepta_mascotas": False}),
             _row("c", tipo_activo="Casa", precio=500,
                  caracteristicas={"num_dormitorios": 2, "acepta_mascotas": True})],
            _MEZCLA),
        "empates": (["a", "b", "c"], [_row("a"), _row("b"), _row("c")],
                    {"dormitorios": 2, "acepta_mascotas": True}),
        "cobertura_incompleta": (
            ["a", "b"],
            [_row("a", ruido=None, vegetacion=None, caminabilidad=None,
                  servicios_cercanos=None, conectividad=None,
                  caracteristicas={"num_dormitorios": 2}),
             _row("b")], _MEZCLA),
        "sin_ids": ([], [], _PETS_SI),
        "mas_filas_que_ids": (["a"], [_row("a"), _row("zz")], _PETS_SI),
    }[nombre]


# ── EL ORÁCULO · medido sobre a7fee44 ANTES de mover una línea ─────────────────────
#
# Generado ejecutando el mismo arnés contra el `construir_panel` pre-refactor. No editar
# para "hacer pasar" nada: si uno de estos números cambia, cambió el comportamiento.

_ESPERADO = {'cobertura_incompleta': {'claves': ['cards',
                                     'descartadas',
                                     'preferencias',
                                     'priorizado',
                                     'relacion_territorial'],
                          'cobertura': {'a': 0.5384615384615384, 'b': 0.8461538461538461},
                          'declaradas': {'a': 6, 'b': 6},
                          'descartadas': [],
                          'duros': {'a': [], 'b': []},
                          'encaje': {'a': 77, 'b': 91},
                          'evaluadas': {'a': 3, 'b': 5},
                          'medido': {'a': 100, 'b': 99},
                          'orden': ['b', 'a'],
                          'razones': {'a': ['Dentro de tu presupuesto ($380 ≤ $400)',
                                            'Es un departamento, como pediste',
                                            'Tiene los 2 dormitorios que pediste'],
                                      'b': ['Dentro de tu presupuesto ($380 ≤ $400)',
                                            'Es un departamento, como pediste',
                                            'Buscabas caminable · caminabilidad 95/100',
                                            'Tiene los 2 dormitorios que pediste',
                                            'Acepta mascotas']}},
 'empates': {'claves': ['cards',
                        'descartadas',
                        'preferencias',
                        'priorizado',
                        'relacion_territorial'],
             'cobertura': {'a': 1.0, 'b': 1.0, 'c': 1.0},
             'declaradas': {'a': 2, 'b': 2, 'c': 2},
             'descartadas': [],
             'duros': {'a': [], 'b': [], 'c': []},
             'encaje': {'a': 100, 'b': 100, 'c': 100},
             'evaluadas': {'a': 2, 'b': 2, 'c': 2},
             'medido': {'a': 100, 'b': 100, 'c': 100},
             'orden': ['a', 'b', 'c'],
             'razones': {'a': ['Tiene los 2 dormitorios que pediste', 'Acepta mascotas'],
                         'b': ['Tiene los 2 dormitorios que pediste', 'Acepta mascotas'],
                         'c': ['Tiene los 2 dormitorios que pediste', 'Acepta mascotas']}},
 'filtro_operacion': {'claves': ['cards',
                                 'descartadas',
                                 'preferencias',
                                 'priorizado',
                                 'relacion_territorial'],
                      'cobertura': {'b': 0.0},
                      'declaradas': {'b': 0},
                      'descartadas': [],
                      'duros': {'b': []},
                      'encaje': {'b': None},
                      'evaluadas': {'b': 0},
                      'medido': {'b': None},
                      'orden': ['b'],
                      'razones': {'b': []}},
 'filtro_operacion_sin_coincidencias': {'claves': ['cards',
                                                   'descartadas',
                                                   'preferencias',
                                                   'priorizado',
                                                   'relacion_territorial'],
                                        'cobertura': {'a': 0.0},
                                        'declaradas': {'a': 0},
                                        'descartadas': [],
                                        'duros': {'a': []},
                                        'encaje': {'a': None},
                                        'evaluadas': {'a': 0},
                                        'medido': {'a': None},
                                        'orden': ['a'],
                                        'razones': {'a': []}},
 'filtro_tipo_inmueble': {'claves': ['cards',
                                     'descartadas',
                                     'preferencias',
                                     'priorizado',
                                     'relacion_territorial'],
                          'cobertura': {'b': 1.0, 'c': 0.0},
                          'declaradas': {'b': 1, 'c': 1},
                          'descartadas': [],
                          'duros': {'b': [], 'c': []},
                          'encaje': {'b': 100, 'c': None},
                          'evaluadas': {'b': 1, 'c': 0},
                          'medido': {'b': 100, 'c': None},
                          'orden': ['b', 'c'],
                          'razones': {'b': ['Es un departamento, como pediste'], 'c': []}},
 'filtro_tipo_sin_coincidencias': {'claves': ['cards',
                                              'descartadas',
                                              'preferencias',
                                              'priorizado',
                                              'relacion_territorial'],
                                   'cobertura': {'a': 1.0},
                                   'declaradas': {'a': 1},
                                   'descartadas': ['b'],
                                   'duros': {'a': ['tipo_inmueble']},
                                   'encaje': {'a': 0},
                                   'evaluadas': {'a': 1},
                                   'medido': {'a': 0},
                                   'orden': ['a'],
                                   'razones': {'a': ['Es una casa, no un departamento']}},
 'mas_filas_que_ids': {'claves': ['cards',
                                  'descartadas',
                                  'preferencias',
                                  'priorizado',
                                  'relacion_territorial'],
                       'cobertura': {'a': 1.0},
                       'declaradas': {'a': 1},
                       'descartadas': [],
                       'duros': {'a': []},
                       'encaje': {'a': 100},
                       'evaluadas': {'a': 1},
                       'medido': {'a': 100},
                       'orden': ['a'],
                       'razones': {'a': ['Acepta mascotas']}},
 'mascotas_NO_declaradas_con_datos_variados': {'claves': ['cards',
                                                          'descartadas',
                                                          'preferencias',
                                                          'priorizado',
                                                          'relacion_territorial'],
                                               'cobertura': {'a': 1.0, 'b': 1.0, 'c': 1.0},
                                               'declaradas': {'a': 1, 'b': 1, 'c': 1},
                                               'descartadas': [],
                                               'duros': {'a': [], 'b': [], 'c': []},
                                               'encaje': {'a': 100, 'b': 100, 'c': 100},
                                               'evaluadas': {'a': 1, 'b': 1, 'c': 1},
                                               'medido': {'a': 100, 'b': 100, 'c': 100},
                                               'orden': ['a', 'b', 'c'],
                                               'razones': {'a': ['Tiene los 2 dormitorios que '
                                                                 'pediste'],
                                                           'b': ['Tiene los 2 dormitorios que '
                                                                 'pediste'],
                                                           'c': ['Tiene los 2 dormitorios que '
                                                                 'pediste']}},
 'mascotas_declaradas_dato_false': {'claves': ['cards',
                                               'descartadas',
                                               'preferencias',
                                               'priorizado',
                                               'relacion_territorial'],
                                    'cobertura': {'b': 1.0},
                                    'declaradas': {'b': 1},
                                    'descartadas': ['a'],
                                    'duros': {'b': []},
                                    'encaje': {'b': 100},
                                    'evaluadas': {'b': 1},
                                    'medido': {'b': 100},
                                    'orden': ['b'],
                                    'razones': {'b': ['Acepta mascotas']}},
 'mascotas_declaradas_dato_true': {'claves': ['cards',
                                              'descartadas',
                                              'preferencias',
                                              'priorizado',
                                              'relacion_territorial'],
                                   'cobertura': {'a': 1.0, 'b': 1.0},
                                   'declaradas': {'a': 1, 'b': 1},
                                   'descartadas': [],
                                   'duros': {'a': [], 'b': []},
                                   'encaje': {'a': 100, 'b': 100},
                                   'evaluadas': {'a': 1, 'b': 1},
                                   'medido': {'a': 100, 'b': 100},
                                   'orden': ['a', 'b'],
                                   'razones': {'a': ['Acepta mascotas'],
                                               'b': ['Acepta mascotas']}},
 'mascotas_declaradas_dato_unknown': {'claves': ['cards',
                                                 'descartadas',
                                                 'preferencias',
                                                 'priorizado',
                                                 'relacion_territorial'],
                                      'cobertura': {'a': 0.0, 'b': 1.0},
                                      'declaradas': {'a': 1, 'b': 1},
                                      'descartadas': [],
                                      'duros': {'a': [], 'b': []},
                                      'encaje': {'a': None, 'b': 100},
                                      'evaluadas': {'a': 0, 'b': 1},
                                      'medido': {'a': None, 'b': 100},
                                      'orden': ['b', 'a'],
                                      'razones': {'a': [], 'b': ['Acepta mascotas']}},
 'mascotas_mezcla_true_false_unknown': {'claves': ['cards',
                                                   'descartadas',
                                                   'preferencias',
                                                   'priorizado',
                                                   'relacion_territorial'],
                                        'cobertura': {'a': 1.0, 'c': 0.0},
                                        'declaradas': {'a': 1, 'c': 1},
                                        'descartadas': ['b'],
                                        'duros': {'a': [], 'c': []},
                                        'encaje': {'a': 100, 'c': None},
                                        'evaluadas': {'a': 1, 'c': 0},
                                        'medido': {'a': 100, 'c': None},
                                        'orden': ['a', 'c'],
                                        'razones': {'a': ['Acepta mascotas'], 'c': []}},
 'mezcla_de_dimensiones': {'claves': ['cards',
                                      'descartadas',
                                      'preferencias',
                                      'priorizado',
                                      'relacion_territorial'],
                           'cobertura': {'a': 0.8461538461538461},
                           'declaradas': {'a': 6},
                           'descartadas': ['b'],
                           'duros': {'a': []},
                           'encaje': {'a': 91},
                           'evaluadas': {'a': 5},
                           'medido': {'a': 99},
                           'orden': ['a'],
                           'razones': {'a': ['Dentro de tu presupuesto ($380 ≤ $400)',
                                             'Es un departamento, como pediste',
                                             'Buscabas caminable · caminabilidad 95/100',
                                             'Tiene los 2 dormitorios que pediste',
                                             'Acepta mascotas']}},
 'presupuesto_dentro_y_fuera': {'claves': ['cards',
                                           'descartadas',
                                           'preferencias',
                                           'priorizado',
                                           'relacion_territorial'],
                                'cobertura': {'a': 1.0},
                                'declaradas': {'a': 1},
                                'descartadas': ['b', 'c'],
                                'duros': {'a': []},
                                'encaje': {'a': 100},
                                'evaluadas': {'a': 1},
                                'medido': {'a': 100},
                                'orden': ['a'],
                                'razones': {'a': ['Dentro de tu presupuesto ($380 ≤ $700)']}},
 'sin_ids': {'claves': ['cards', 'descartadas', 'preferencias', 'priorizado'],
             'cobertura': {},
             'declaradas': {},
             'descartadas': [],
             'duros': {},
             'encaje': {},
             'evaluadas': {},
             'medido': {},
             'orden': [],
             'razones': {}},
 'sin_preferencias': {'claves': ['cards',
                                 'descartadas',
                                 'preferencias',
                                 'priorizado',
                                 'relacion_territorial'],
                      'cobertura': {'a': None, 'b': None, 'c': None},
                      'declaradas': {'a': None, 'b': None, 'c': None},
                      'descartadas': [],
                      'duros': {'a': [], 'b': [], 'c': []},
                      'encaje': {'a': None, 'b': None, 'c': None},
                      'evaluadas': {'a': None, 'b': None, 'c': None},
                      'medido': {'a': None, 'b': None, 'c': None},
                      'orden': ['a', 'b', 'c'],
                      'razones': {'a': [], 'b': [], 'c': []}}}


_CASOS = sorted(_ESPERADO)


# ══ T1-T3 · LA ESTRUCTURA ══════════════════════════════════════════════════════════


def test_T1_construir_panel_sigue_siendo_el_ENTRY_POINT():
    """El núcleo es un detalle interno: los consumidores no cambian.

    Si `graph.py` o `chat.py` empezaran a llamar al núcleo directamente, se saltarían la
    adquisición de filas y R0D habría movido la frontera en vez de dibujarla.
    """
    assert callable(assembler.construir_panel)
    assert callable(assembler.build_result_cards)
    assert hasattr(assembler, NUCLEO), "el núcleo extraído no existe"

    for rel in ("app/agent/graph.py", "app/routers/chat.py"):
        fuente = (RAIZ / rel).read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        llamadas = {getattr(n.func, "id", None) or getattr(n.func, "attr", None)
                    for n in ast.walk(arbol) if isinstance(n, ast.Call)}
        assert NUCLEO not in llamadas, f"{rel} llama al núcleo saltándose el entry point"


def test_T2_un_turno_hace_EXACTAMENTE_una_adquisicion_de_filas(catastro):
    """La propiedad que hace útil al núcleo, y la que un refactor descuidado rompe."""
    ids, rows, prefs = _caso("mezcla_de_dimensiones")
    estado = catastro(rows)
    asyncio.run(assembler.construir_panel(_turno(ids), preferencias=prefs,
                                          session_id="s-r0d"))
    assert estado["llamadas"] == 1, \
        f"se consultó el catastro {estado['llamadas']} veces; el núcleo no puede re-pedir"
    assert estado["ids_pedidos"] == [ids]


def test_T3_el_nucleo_recibe_LAS_MISMAS_filas_por_identidad(catastro, monkeypatch):
    """Más fuerte que «filas equivalentes»: el MISMO objeto.

    Es lo que convierte «mismo universo» de promesa en hecho. Una unidad futura llamará al
    núcleo dos veces con estas filas; si recibiera una copia, dos ejecuciones podrían
    divergir sin que nada lo delatara.
    """
    ids, rows, prefs = _caso("mezcla_de_dimensiones")
    estado = catastro(rows)
    visto = {}

    original = assembler._decidir_desde_filas

    def espia(filas, curaciones, **kw):
        visto["filas"] = filas
        return original(filas, curaciones, **kw)

    monkeypatch.setattr(assembler, NUCLEO, espia)
    asyncio.run(assembler.construir_panel(_turno(ids), preferencias=prefs,
                                          session_id="s-r0d"))

    assert visto["filas"] is estado["devueltas"], \
        "el núcleo recibió una COPIA: el universo dejaría de ser el mismo por construcción"


# ══ T4-T6 · LA PUREZA ══════════════════════════════════════════════════════════════


def _cuerpo_del_nucleo() -> ast.AST:
    arbol = ast.parse(FUENTE.read_text(encoding="utf-8"))
    return next(n for n in ast.walk(arbol)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name == NUCLEO)


_PROHIBIDAS = {"_fetch_cards_rows", "_fetch_curaciones_batch", "extraer_preferencias",
               "execute", "commit", "rollback", "get_db", "AsyncSessionLocal",
               "aupdate_state", "ainvoke", "astream", "httpx", "requests", "urlopen"}
"""Nombres de invocación que delatan entrada/salida. NO lleva `get`/`post`/`request`, y es
deliberado: como marcadores de HTTP son ambiguos —`dict.get` aparece por todas partes— y un
guard que se pone rojo por `row.get("precio")` acaba debilitado hasta volverse inerte. Vale
más una lista corta y exacta que una larga que nadie se atreva a dejar encendida."""


def test_T4_el_nucleo_no_hace_ENTRADA_SALIDA():
    """Guard por AST, no por texto. Se mira lo que el núcleo INVOCA, no lo que menciona."""
    fn = _cuerpo_del_nucleo()

    assert not isinstance(fn, ast.AsyncFunctionDef), \
        "un núcleo `async` puede esperar I/O; éste tiene que ser síncrono"
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)], \
        "el núcleo tiene un `await`: dejó de ser puro"

    invocadas = {getattr(n.func, "id", None) or getattr(n.func, "attr", None)
                 for n in ast.walk(fn) if isinstance(n, ast.Call)}
    fugas = invocadas & _PROHIBIDAS
    assert not fugas, f"el núcleo invoca entrada/salida: {sorted(fugas)}"


def test_T5_el_nucleo_no_llama_al_MODELO():
    fn = _cuerpo_del_nucleo()
    volcado = ast.dump(fn)
    for prohibido in ("extraer_preferencias", "interpretar", "ChatOpenAI", "ainvoke",
                      "llm", "_MODELO"):
        assert prohibido not in volcado, f"el núcleo toca el modelo: {prohibido}"


def test_T6_el_nucleo_no_conoce_la_memoria_del_comprador():
    """R0D es agnóstico del Buyer Harness. Ni importa, ni nombra, ni consume."""
    fn = _cuerpo_del_nucleo()
    volcado = ast.dump(fn)
    for prohibido in ("buyer", "Buyer", "candidato", "Candidato", "computo", "Computo",
                      "pets_allowed_required"):
        assert prohibido not in volcado, f"el núcleo ya conoce al comprador: {prohibido}"

    arbol = ast.parse(FUENTE.read_text(encoding="utf-8"))
    modulos = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.ImportFrom) and n.module:
            modulos.add(n.module)
        elif isinstance(n, ast.Import):
            modulos.update(a.name for a in n.names)
    fugas = {m for m in modulos if m.startswith("app.buy")}
    assert not fugas, f"el assembler importa del comprador: {sorted(fugas)}"


def test_T4b_el_detector_de_ENTRADA_SALIDA_no_es_inerte():
    """LA MITAD NEGATIVA. Un núcleo sintético que llame a la base debe ser detectado.

    Sin esto, T4 podría estar recorriendo un árbol que nunca contiene nada prohibido — que
    es exactamente cómo un guard se vuelve decorativo sin que nadie lo note.
    """
    roto = ast.parse(
        "def _decidir_desde_filas(rows, cur, *, ids, preferencias, messages, session_id):\n"
        "    filas, _ = _fetch_cards_rows(ids)\n"
        "    return filas\n")
    fn = next(n for n in ast.walk(roto) if isinstance(n, ast.FunctionDef))
    invocadas = {getattr(n.func, "id", None) or getattr(n.func, "attr", None)
                 for n in ast.walk(fn) if isinstance(n, ast.Call)}
    assert invocadas & _PROHIBIDAS, "el detector no ve un fetch dentro del núcleo"

    asincrono = ast.parse(
        "async def _decidir_desde_filas(rows):\n"
        "    return await _fetch_cards_rows(rows)\n")
    fn2 = next(n for n in ast.walk(asincrono) if isinstance(n, ast.AsyncFunctionDef))
    assert isinstance(fn2, ast.AsyncFunctionDef)
    assert [n for n in ast.walk(fn2) if isinstance(n, ast.Await)], \
        "el detector no ve un `await`"


# ══ T7-T15 · PARIDAD CONTRA EL ORÁCULO PRE-REFACTOR ════════════════════════════════


@pytest.mark.parametrize("nombre", _CASOS)
def test_T7_T15_paridad_del_panel_caso_a_caso(catastro, nombre):
    """El corazón de R0D: MISMA ENTRADA → MISMA SALIDA, en los 16 casos de §11.

    Cubre de una vez el orden visible (T7), las tarjetas (T8), lo descartado (T9),
    score/razones/cobertura (T10), mascotas true/false/desconocido (T11-T13), los filtros de
    operación y tipo (T14) y el presupuesto con su recorte (T15). Se parametriza en vez de
    escribir nueve tests porque la propiedad es UNA y el caso es el que varía — nueve
    funciones afirmando lo mismo invitarían a relajar una sin mirar las otras.
    """
    ids, rows, prefs = _caso(nombre)
    obtenido = _ejes(_panel(catastro, ids, rows, prefs))
    esperado = _ESPERADO[nombre]

    for eje in ("orden", "descartadas", "claves", "encaje", "medido", "cobertura",
                "evaluadas", "declaradas", "duros", "razones"):
        assert obtenido[eje] == esperado[eje], (
            f"{nombre} · el eje '{eje}' cambió con el refactor\n"
            f"  antes:  {esperado[eje]}\n  ahora:  {obtenido[eje]}")


def test_T15b_el_panel_vacio_conserva_su_ASIMETRIA(catastro):
    """Sin ids, el panel sale por la puerta temprana y NO trae `relacion_territorial`.

    Es una asimetría que ya existía. Se congela precisamente porque un refactor tiene la
    tentación de «arreglarla» de paso, y eso sería cambio de comportamiento disfrazado de
    limpieza.
    """
    ids, rows, prefs = _caso("sin_ids")
    panel = _panel(catastro, ids, rows, prefs)
    assert "relacion_territorial" not in panel
    assert sorted(panel) == _ESPERADO["sin_ids"]["claves"]


# ══ T16 · DETERMINISMO ═════════════════════════════════════════════════════════════


@pytest.mark.parametrize("nombre", ["mezcla_de_dimensiones", "empates",
                                    "cobertura_incompleta"])
def test_T16_mismas_entradas_dan_la_MISMA_salida(nombre):
    """Sobre el núcleo directamente: dos llamadas, sin base de por medio, mismo resultado.

    Es la precondición de la unidad siguiente. Si el núcleo no fuera determinista, un
    contrafactual no podría atribuir su delta al campo alterado — podría venir del ruido.
    """
    ids, rows, prefs = _caso(nombre)
    primera = _ejes(_nucleo(ids, rows, prefs))
    segunda = _ejes(_nucleo(ids, rows, prefs))
    assert primera == segunda


def test_T16b_el_nucleo_por_SI_SOLO_reproduce_el_panel(catastro):
    """Llamarlo directo y llamarlo por el panel dan lo mismo. Es lo que permitirá, más
    adelante, ejecutar el contrafactual sin pasar por la adquisición de filas."""
    for nombre in ("mezcla_de_dimensiones", "filtro_operacion", "presupuesto_dentro_y_fuera"):
        ids, rows, prefs = _caso(nombre)
        por_el_panel = _ejes(_panel(catastro, ids, rows, prefs))
        directo = _ejes(_nucleo(ids, rows, prefs))
        assert por_el_panel == directo, nombre


def test_T16c_el_nucleo_NO_muta_las_filas_que_recibe():
    """Dos ejecuciones sobre las mismas filas exigen que la primera no las ensucie.

    El núcleo enriquece (`servicios_cercanos` curados, `fresco`, `verificado_en`) y lo hace
    sobre `dict(r)` — una copia. Aquí se comprueba, porque si mutara la entrada la segunda
    llamada del contrafactual partiría de un estado distinto.
    """
    import copy

    ids, rows, prefs = _caso("mezcla_de_dimensiones")
    antes = copy.deepcopy(rows)
    _nucleo(ids, rows, prefs)
    assert rows == antes, "el núcleo mutó las filas de entrada"


# ══ T17-T18 · MUTACIONES ═══════════════════════════════════════════════════════════


def test_T17_MUTACION_cambiar_la_logica_de_score_se_detecta(catastro):
    """Si el motor puntuara distinto, la paridad se pondría roja.

    Se muta `calcular_encaje` —no el oráculo— y se comprueba que los ejes congelados dejan
    de coincidir. Sin esto, T7-T15 podrían estar comparando algo que no depende del motor.
    """
    ids, rows, prefs = _caso("mezcla_de_dimensiones")
    real = assembler.calcular_encaje

    def mutado(preferencias, inmueble):
        salida = real(preferencias, inmueble)
        if salida.get("score") is not None:
            salida = {**salida, "score": max(0, salida["score"] - 17)}
        return salida

    assembler.calcular_encaje = mutado
    try:
        obtenido = _ejes(_panel(catastro, ids, rows, prefs))
    finally:
        assembler.calcular_encaje = real

    assert obtenido["encaje"] != _ESPERADO["mezcla_de_dimensiones"]["encaje"], \
        "el oráculo no reacciona a un cambio del motor: sería inerte"


def test_T18_MUTACION_meter_un_fetch_en_el_nucleo_se_detecta():
    """Si alguien devolviera una adquisición de filas al núcleo, T4 lo vería."""
    fuente_mutada = FUENTE.read_text(encoding="utf-8").replace(
        "    by_id: dict[str, dict] = {}",
        "    rows, curaciones = _fetch_cards_rows(ids)\n    by_id: dict[str, dict] = {}",
        1)
    fn = next(n for n in ast.walk(ast.parse(fuente_mutada))
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == NUCLEO)
    invocadas = {getattr(n.func, "id", None) or getattr(n.func, "attr", None)
                 for n in ast.walk(fn) if isinstance(n, ast.Call)}
    assert invocadas & _PROHIBIDAS, \
        "T4 no vería un fetch reintroducido en el núcleo"


def test_T18b_MUTACION_duplicar_la_adquisicion_se_detecta(catastro):
    """Si `construir_panel` pidiera las filas dos veces, T2 lo vería."""
    ids, rows, prefs = _caso("mezcla_de_dimensiones")
    estado = catastro(rows)
    asyncio.run(assembler.construir_panel(_turno(ids), preferencias=prefs,
                                          session_id="s-r0d"))
    asyncio.run(assembler.construir_panel(_turno(ids), preferencias=prefs,
                                          session_id="s-r0d"))
    assert estado["llamadas"] == 2, \
        "el contador de adquisiciones no sube: T2 estaría midiendo nada"
