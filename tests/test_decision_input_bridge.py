"""F3-DECISION-INPUT-BRIDGE-R0F · el cable graph → chat, y lo que NO puede llevar.

QUÉ CONGELA, y qué NO.

    congela    que las entradas exactas de la decisión visible quedan disponibles fuera del
               grafo, por referencia, sin segunda consulta, sin tocar `AgentState`, sin tocar
               `RunnableConfig` y sin aparecer en ningún checkpoint; y que sin buzón el panel
               se comporta EXACTAMENTE igual
    NO congela nada sobre el comprador. R0F no compara, no proyecta mascotas, no lee
               `BuyerContext` y no crea ningún flag

## LA DIRECCIÓN

```
DECISIÓN / INVENTARIO  ──→  buzón per-request  ──→  CHAT     ✅
COMPRADOR              ──→  GRAFO                            ❌ nunca
```

La segunda flecha está prohibida por algo medible: `AgentState` se checkpointea entero y
`get_checkpoint_metadata` copia a `checkpoints.metadata` toda clave escalar de
`configurable`. Por eso el cable va al revés — sale inventario, no entra comprador — y por
eso T7/T8/T9/T10 son cuatro tests y no un comentario.

## POR QUÉ UNA CAJA MUTABLE

Las tareas de asyncio COPIAN el contexto. Un `set()` hecho dentro de una tarea hija rebinda
su copia y no se ve fuera; lo que sí cruza es la referencia a un objeto mutable. T22 y T23
son las mutaciones que demuestran que esa distinción es la que sostiene el puente.
"""

from __future__ import annotations

import ast
import asyncio
import json
import pathlib

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.decision import assembler
from app.decision import runtime_capture as rc

RAIZ = pathlib.Path(__file__).resolve().parent.parent
ASSEMBLER = RAIZ / "app" / "decision" / "assembler.py"
CAPTURA = RAIZ / "app" / "decision" / "runtime_capture.py"
CHAT = RAIZ / "app" / "routers" / "chat.py"


def _row(rid, **over):
    row = {
        "id": rid, "direccion": f"Dir {rid}", "tipo_activo": "Departamento",
        "operacion": "ARRIENDO", "precio": 380, "imagen_url": None,
        "caminabilidad": 95, "caminabilidad_fuente": "osm", "ruido": "BAJO",
        "vegetacion": 42, "lat": -0.18, "lon": -78.48,
        "caracteristicas": {"num_dormitorios": 2, "acepta_mascotas": True},
        "servicios_cercanos": "\U0001F333 Parque a ~300 m",
        "conectividad": "\U0001F687 Metro a ~500 m (7 min a pie)",
    }
    row.update(over)
    return row


IDS = ["a", "b", "c"]
PREFS = {"dormitorios": 2, "presupuesto_max": 700}


def _turno(ids=IDS):
    return [
        HumanMessage(content="consulta"),
        ToolMessage(content=json.dumps({"assets": [{"id": i} for i in ids]}),
                    name="tool_search_nearby_assets", tool_call_id="t1"),
        AIMessage(content="Encontré algunas opciones."),
    ]


@pytest.fixture
def catastro(monkeypatch):
    """La ÚNICA entrada/salida del panel, sustituida y contada."""
    estado = {"llamadas": 0, "rows": None, "curaciones": None}

    def _instalar(rows=None, curaciones=None):
        estado["rows"] = [_row(i) for i in IDS] if rows is None else rows
        estado["curaciones"] = {} if curaciones is None else curaciones

        async def fake_fetch(_ids):
            estado["llamadas"] += 1
            return (estado["rows"], estado["curaciones"])

        monkeypatch.setattr(assembler, "_fetch_cards_rows", fake_fetch)
        return estado

    return _instalar


def _panel(ids=IDS, prefs=PREFS):
    return asyncio.run(assembler.construir_panel(_turno(ids), preferencias=prefs,
                                                 session_id="s-r0f"))


def _ejes(panel):
    cards = panel["cards"]
    return {
        "orden": [c["id"] for c in cards],
        "descartadas": [c["id"] for c in panel["descartadas"]],
        "encaje": {c["id"]: c["encaje"] for c in cards},
        "cobertura": {c["id"]: c["encaje_cobertura"] for c in cards},
        "razones": {c["id"]: [r["texto"] for r in (c["encaje_razones"] or [])]
                    for c in cards},
    }


# ══ T1 · SIN BUZÓN, R0D EXACTO ═════════════════════════════════════════════════════


def test_T1_sin_buzon_el_panel_es_EXACTAMENTE_el_de_R0D(catastro):
    """La captura es observabilidad opcional. Sin contexto activo no pasa nada: ni error,
    ni aviso, ni salida distinta. Es el estado de toda la suite que no la instala."""
    catastro()
    assert rc.caja_actual() is None

    sin_buzon = _ejes(_panel())
    with rc.capturar_entradas_de_decision():
        con_buzon = _ejes(_panel())

    assert sin_buzon == con_buzon


def test_T20_el_buzon_no_toca_el_panel_en_NINGUN_eje(catastro):
    """Más explícito que T1: orden, tarjetas, descartadas, encaje, cobertura y razones."""
    for prefs in ({}, PREFS, {"acepta_mascotas": True}, {"operacion": "ARRIENDO"}):
        catastro()
        sin = _ejes(_panel(prefs=prefs))
        with rc.capturar_entradas_de_decision():
            con = _ejes(_panel(prefs=prefs))
        assert sin == con, prefs


# ══ T2-T5 · LO QUE LLEGA, Y QUE ES LO MISMO ════════════════════════════════════════


def test_T2_con_buzon_activo_llegan_las_entradas(catastro):
    estado = catastro()
    with rc.capturar_entradas_de_decision() as caja:
        _panel()
        assert caja.hay_captura
        assert [r["id"] for r in caja.entradas.rows] == [r["id"] for r in estado["rows"]]
        assert caja.entradas.ids == IDS


def test_T3_las_filas_capturadas_SON_las_que_usó_el_núcleo(catastro, monkeypatch):
    """Identidad, no equivalencia. Es la propiedad entera del puente: si fuera una copia,
    una segunda ejecución del núcleo ya no correría sobre el mismo universo."""
    estado = catastro()
    vistas = {}
    real = assembler._decidir_desde_filas

    def espia(rows, curaciones, **kw):
        vistas["rows"] = rows
        vistas["curaciones"] = curaciones
        return real(rows, curaciones, **kw)

    monkeypatch.setattr(assembler, "_decidir_desde_filas", espia)

    with rc.capturar_entradas_de_decision() as caja:
        _panel()

    assert caja.entradas.rows is vistas["rows"] is estado["rows"]
    assert all(a is b for a, b in zip(caja.entradas.rows, estado["rows"]))


def test_T4_las_curaciones_capturadas_SON_las_del_núcleo(catastro, monkeypatch):
    estado = catastro(curaciones={"a": [{"nota": "x"}]})
    vistas = {}
    real = assembler._decidir_desde_filas

    def espia(rows, curaciones, **kw):
        vistas["curaciones"] = curaciones
        return real(rows, curaciones, **kw)

    monkeypatch.setattr(assembler, "_decidir_desde_filas", espia)

    with rc.capturar_entradas_de_decision() as caja:
        _panel()

    assert caja.entradas.curaciones is vistas["curaciones"] is estado["curaciones"]


def test_T5_capturar_NO_añade_una_segunda_consulta_de_inventario(catastro):
    estado = catastro()
    with rc.capturar_entradas_de_decision():
        _panel()
    assert estado["llamadas"] == 1, \
        f"el catastro se consultó {estado['llamadas']} veces: el puente re-leyó inventario"


# ══ T6 · EL NÚCLEO SIGUE PURO ══════════════════════════════════════════════════════


def test_T6_el_nucleo_NO_lee_estado_ambiente():
    """`_decidir_desde_filas` no puede conocer el `ContextVar`: sigue siendo una función pura
    de sus argumentos. El depósito ocurre en `construir_panel`, donde las entradas ya existen
    y todavía no se ha decidido nada."""
    arbol = ast.parse(ASSEMBLER.read_text(encoding="utf-8"))
    nucleo = next(n for n in ast.walk(arbol)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == "_decidir_desde_filas")
    volcado = ast.dump(nucleo)
    for prohibido in ("depositar", "caja_actual", "capturar_entradas_de_decision",
                      "ContextVar", "runtime_capture"):
        assert prohibido not in volcado, f"el núcleo toca el canal: {prohibido}"

    panel = next(n for n in ast.walk(arbol)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and n.name == "construir_panel")
    llamadas = {getattr(n.func, "id", None) for n in ast.walk(panel)
                if isinstance(n, ast.Call)}
    assert "depositar" in llamadas, "nadie deposita: el puente no existiría"


# ══ T7-T10 · EL PUENTE NO PUEDE LLEVAR AL COMPRADOR ════════════════════════════════


_PROHIBIDO_EN_EL_PUENTE = ("buyer", "principal", "user_id", "email", "pets", "mascotas",
                           "budget", "presupuesto", "preferencias", "candidato", "computo")
"""Nombres del COMPRADOR que el puente no puede nombrar.

Sin `token` ni `jwt`, y es deliberado: `token` es el identificador que devuelve
`ContextVar.set()` y que hace falta para restaurar el contexto exterior. Incluirlo ponía el
guard rojo por la variable que sostiene T17 — la octava vez que en este repositorio una lista
de subcadenas colisiona con un nombre legítimo. Lo que se vigila aquí son identificadores del
comprador; que no viaje una credencial lo garantiza T7 por los CAMPOS del dataclass, que es
una comprobación estructural y no léxica."""


def test_T7_el_tipo_de_captura_no_tiene_DONDE_poner_al_comprador():
    """Por los campos del dataclass, no por intención: lo que no existe no se puede llenar."""
    campos = set(rc.DecisionInputCapture.__dataclass_fields__)
    assert campos == {"rows", "curaciones", "ids"}, f"la captura creció: {sorted(campos)}"

    fuente = CAPTURA.read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    modulos = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.ImportFrom) and n.module:
            modulos.add(n.module)
        elif isinstance(n, ast.Import):
            modulos.update(a.name for a in n.names)
    assert not any(m.startswith("app.buy") for m in modulos), \
        "el módulo del puente importa del comprador"

    # Y ningún nombre del comprador aparece como identificador del módulo.
    nombres = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
    nombres |= {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
    for prohibido in _PROHIBIDO_EN_EL_PUENTE:
        assert not any(prohibido in n for n in nombres), \
            f"el puente nombra algo del comprador: {prohibido}"


def test_T8_la_captura_no_entra_en_AgentState():
    estado = (RAIZ / "app" / "agent" / "state.py").read_text(encoding="utf-8")
    for prohibido in ("captura", "capture", "rows", "curaciones", "runtime_capture"):
        assert prohibido not in estado, f"AgentState ganó una clave del puente: {prohibido}"


def test_T9_la_captura_no_entra_en_RunnableConfig():
    """`configurable` es la superficie que `get_checkpoint_metadata` copia a la tabla de
    checkpoints para todo valor escalar. Por eso el puente no pasa por ahí."""
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.FunctionDef) and n.name == "_langgraph_config")
    volcado = ast.dump(fn)
    for prohibido in ("captura", "capture", "rows", "curaciones", "caja"):
        assert prohibido not in volcado, f"el config transporta el puente: {prohibido}"


def test_T10_ni_el_grafo_ni_el_estado_importan_el_modulo_del_puente():
    """Si el grafo lo importara, el siguiente paso natural sería meterlo en el estado — y de
    ahí al checkpoint. Se cierra antes de que exista la tentación."""
    for rel in ("app/agent/graph.py", "app/agent/state.py"):
        fuente = (RAIZ / rel).read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        modulos = set()
        for n in ast.walk(arbol):
            if isinstance(n, ast.ImportFrom) and n.module:
                modulos.add(n.module)
            elif isinstance(n, ast.Import):
                modulos.update(a.name for a in n.names)
        assert "app.decision.runtime_capture" not in modulos, f"{rel} importa el puente"


# ══ T11-T13 · AISLAMIENTO ENTRE PETICIONES ═════════════════════════════════════════


def test_T11_T12_dos_peticiones_CONCURRENTES_no_se_ven(monkeypatch):
    """La propiedad crítica. Dos turnos a la vez, cada uno con su buzón.

    Se fuerza el entrelazado con un `await` entre la lectura del catastro y el depósito: sin
    él, cada turno podría terminar antes de que el otro empiece y el test mediría al
    planificador en vez de al aislamiento — la misma lección que la barrera de E3.2b.3a.
    """
    filas = {"A": [_row("a-1")], "B": [_row("b-1")]}
    cajas = {}

    async def turno(etiqueta):
        async def fake_fetch(_ids):
            await asyncio.sleep(0)          # cede el control al otro turno, a propósito
            return (filas[etiqueta], {})

        monkeypatch.setattr(assembler, "_fetch_cards_rows", fake_fetch)
        with rc.capturar_entradas_de_decision() as caja:
            await assembler.construir_panel(_turno(["a-1"]), preferencias=PREFS,
                                            session_id=f"s-{etiqueta}")
            await asyncio.sleep(0)
            cajas[etiqueta] = caja.entradas.rows

    async def ambos():
        await asyncio.wait_for(asyncio.gather(turno("A"), turno("B")), timeout=10)

    asyncio.run(ambos())

    assert cajas["A"] is filas["A"], "A no capturó lo suyo"
    assert cajas["B"] is filas["B"], "B no capturó lo suyo"
    assert cajas["A"] is not cajas["B"], "los dos turnos compartieron captura"


def test_T13_cada_turno_empieza_con_un_buzon_VACIO(catastro):
    """Secuencial: el segundo turno no puede heredar nada del primero."""
    catastro()
    with rc.capturar_entradas_de_decision() as primera:
        _panel()
    assert primera.hay_captura

    with rc.capturar_entradas_de_decision() as segunda:
        assert segunda is not primera
        assert not segunda.hay_captura, "el buzón nuevo llegó con la captura del anterior"


def test_T13b_el_canal_NO_es_un_singleton_de_modulo():
    """Estructural: nadie guarda una caja a nivel de módulo ni indexada por sesión."""
    arbol = ast.parse(CAPTURA.read_text(encoding="utf-8"))
    asignaciones = [n for n in arbol.body if isinstance(n, (ast.Assign, ast.AnnAssign))]
    destinos = []
    for n in asignaciones:
        objetivos = n.targets if isinstance(n, ast.Assign) else [n.target]
        destinos += [t.id for t in objetivos if isinstance(t, ast.Name)]

    assert destinos == ["_captura_actual"], \
        f"el módulo guarda estado suelto además del canal: {destinos}"
    volcado = ast.dump(arbol)
    for prohibido in ("session_id", "thread_id", "registry", "cache"):
        assert prohibido not in volcado, f"el canal se indexa por {prohibido}"


# ══ T14-T17 · CICLO DE VIDA ════════════════════════════════════════════════════════


def test_T14_tras_un_turno_correcto_el_canal_queda_limpio(catastro):
    catastro()
    with rc.capturar_entradas_de_decision():
        _panel()
    assert rc.caja_actual() is None


def test_T15_tras_una_EXCEPCION_el_canal_queda_limpio():
    class Roto(RuntimeError):
        pass

    with pytest.raises(Roto):
        with rc.capturar_entradas_de_decision():
            raise Roto("el turno se rompió")
    assert rc.caja_actual() is None


def test_T16_la_CANCELACION_limpia_y_SE_PROPAGA():
    """Las dos mitades. Convertir un `CancelledError` en éxito por instrumentar el puente
    sería el tipo de fallo que no se nota hasta que importa."""
    async def turno():
        with rc.capturar_entradas_de_decision():
            await asyncio.sleep(10)

    async def main():
        t = asyncio.create_task(turno())
        await asyncio.sleep(0)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
        return rc.caja_actual()

    assert asyncio.run(main()) is None


def test_T17_un_contexto_ANIDADO_restaura_el_exterior():
    """`reset(token)` y no `set(None)`: con `None` el turno exterior se quedaría ciego."""
    with rc.capturar_entradas_de_decision() as fuera:
        assert rc.caja_actual() is fuera
        with rc.capturar_entradas_de_decision() as dentro:
            assert rc.caja_actual() is dentro is not fuera
        assert rc.caja_actual() is fuera, "cerrar el interior dejó ciego al exterior"
    assert rc.caja_actual() is None


# ══ T18-T19 · LOS DOS CAMINOS LO INSTALAN ══════════════════════════════════════════


@pytest.mark.parametrize("funcion", ["_stream_agent", "chat"])
def test_T18_T19_los_dos_caminos_abren_su_propio_buzon(funcion):
    """Mismo context manager en los dos: la semántica se reutiliza, no se duplica."""
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == funcion)

    withs = [n for n in ast.walk(fn) if isinstance(n, (ast.With, ast.AsyncWith))]
    aperturas = [w for w in withs
                 if "capturar_entradas_de_decision" in ast.dump(w)]
    assert len(aperturas) == 1, \
        f"{funcion}() abre {len(aperturas)} buzones; se esperaba exactamente 1"

    # Y el grafo corre DENTRO: un buzón abierto después no vería nada.
    (apertura,) = aperturas
    grafo = [n for n in ast.walk(apertura) if isinstance(n, ast.Call)
             and "compiled_graph" in ast.dump(n)]
    assert grafo, f"{funcion}() ejecuta el grafo FUERA del buzón"


def test_T19b_nadie_mas_abre_un_buzon_en_produccion():
    """El dueño del turno es quien lo abre. Si un productor hiciera `set()`, la caja dejaría
    de ser la del turno y el aislamiento se volvería una cuestión de suerte."""
    for rel in ("app/decision/assembler.py", "app/agent/graph.py"):
        fuente = (RAIZ / rel).read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        llamadas = {getattr(n.func, "id", None) or getattr(n.func, "attr", None)
                    for n in ast.walk(arbol) if isinstance(n, ast.Call)}
        assert "capturar_entradas_de_decision" not in llamadas, f"{rel} abre un buzón"
        assert "set" not in (llamadas & {"set"}) or "_captura_actual" not in fuente


# ══ T21 · LA CARACTERIZACIÓN SIGUE INTACTA ═════════════════════════════════════════


def test_T21_la_caracterizacion_de_R0D_no_se_movio(catastro):
    """Los ejes congelados sobre `a7fee44` siguen valiendo con el puente instalado.

    No se reimplanta el oráculo de 16 casos —vive en `test_decision_core_extraction.py` y
    pasa sin modificarse—: aquí se comprueba que instalar el buzón no mueve el caso más rico.
    """
    catastro(rows=[_row("a"), _row("b", precio=900, ruido="ALTO", caminabilidad=20,
                                   caracteristicas={"num_dormitorios": 4,
                                                    "acepta_mascotas": False}),
                   _row("c", tipo_activo="Casa", precio=500)])
    prefs = {"tipo_inmueble": "departamento", "presupuesto_max": 400, "dormitorios": 2,
             "acepta_mascotas": True, "tranquilidad": True, "caminable": True}

    sin = _ejes(_panel(prefs=prefs))
    with rc.capturar_entradas_de_decision():
        con = _ejes(_panel(prefs=prefs))
    assert sin == con


# ══ T22-T25 · MUTACIONES ═══════════════════════════════════════════════════════════


def test_T22_MUTACION_una_caja_COMPARTIDA_rompe_el_aislamiento(monkeypatch):
    """Si el canal fuera un singleton de módulo, dos turnos escribirían encima."""
    compartida = rc.DecisionCaptureBox()
    filas = {"A": [_row("a-1")], "B": [_row("b-1")]}

    for etiqueta in ("A", "B"):
        compartida.entradas = rc.DecisionInputCapture(rows=filas[etiqueta],
                                                      curaciones={}, ids=["x"])
    assert compartida.entradas.rows is filas["B"], \
        "una caja compartida no se pisa: el test no mide nada"
    assert compartida.entradas.rows is not filas["A"], \
        "A perdió su captura — esto es exactamente lo que el diseño per-request evita"


def test_T23_MUTACION_rebindear_desde_una_tarea_hija_NO_cruza():
    """La mutación que explica por qué la caja es mutable.

    Rebindear el `ContextVar` dentro de una tarea sólo cambia SU copia. Mutar el contenedor
    compartido sí se ve fuera. Si `depositar` hiciera `set()` en vez de escribir en la caja,
    el puente no transportaría nada y ningún test de panel lo notaría.
    """
    async def main():
        # 1 · rebind desde una tarea hija: invisible fuera.
        async def rebinda():
            rc._captura_actual.set(rc.DecisionCaptureBox())

        with rc.capturar_entradas_de_decision() as caja:
            await asyncio.create_task(rebinda())
            tras_rebind = rc.caja_actual()

            # 2 · mutar la caja compartida: visible fuera.
            async def deposita():
                rc.depositar([_row("z")], {}, ["z"])

            await asyncio.create_task(deposita())
            return tras_rebind is caja, caja.hay_captura

    sobrevive, deposito_visible = asyncio.run(main())
    assert sobrevive, "el rebind de la tarea hija se coló al contexto del turno"
    assert deposito_visible, "mutar la caja compartida no cruzó: el puente no funcionaría"


def test_T24_MUTACION_copiar_las_filas_se_detecta(catastro):
    """Si la captura guardara una copia, T3 se pondría rojo. Aquí se prueba el detector."""
    import copy

    estado = catastro()
    with rc.capturar_entradas_de_decision() as caja:
        _panel()

    copiadas = copy.deepcopy(caja.entradas.rows)
    assert caja.entradas.rows is estado["rows"], "la captura ya no es por referencia"
    assert copiadas is not estado["rows"] and copiadas == estado["rows"], \
        "el detector de identidad no distingue una copia de la referencia"


def test_T25_MUTACION_añadir_un_campo_del_comprador_se_detecta():
    """Si alguien ampliara la captura con algo del comprador, T7 lo vería."""
    campos = set(rc.DecisionInputCapture.__dataclass_fields__)
    mutado = campos | {"buyer_id"}
    assert mutado != {"rows", "curaciones", "ids"}, \
        "el guard de campos no reacciona a un campo nuevo: sería inerte"
    assert any("buyer" in c for c in mutado)
    assert not any("buyer" in c for c in campos)
