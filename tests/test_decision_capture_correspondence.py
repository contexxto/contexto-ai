"""F3-DECISION-CAPTURE-CORRESPONDENCE-R0F1 · la captura corresponde al panel que se vio.

QUÉ CONGELA, y qué NO.

    congela    que la captura vigente son las entradas de la ÚLTIMA decisión que de verdad
               existió; que una tentativa fallida posterior no la pisa; y que un panel vacío
               no deja viva una captura obsoleta
    NO congela nada sobre el comprador. R0F1 es infraestructura de decisión: no compara, no
               proyecta, no lee `BuyerContext` y no crea flags

## EL DEFECTO QUE CIERRA

El grafo es un bucle —`tools → encaje → llm`—, así que `construir_panel` corre una vez por
ronda de herramientas. Con el depósito por delante de la decisión, esta secuencia dejaba una
captura mentirosa:

```
ronda 1   decide A   éxito     → el panel visible es A
ronda 2   deposita B → revienta → el nodo conserva el panel A
                                  y la caja se había quedado con B
```

Un contrafactual sobre B comparado contra el panel A no mide el campo: mide el arnés.

## LA CORRESPONDENCIA LA DA EL FLUJO DE CONTROL, NO LOS IDS

Cotejar «los ids capturados == los ids visibles» **no basta**, y T5/T6 lo demuestran con el
caso adversarial: dos ejecuciones pueden dar ids, orden y scores idénticos partiendo de filas
distintas —una señal que las preferencias legacy no miran, como mascotas, no mueve el panel
pero sí movería un contrafactual—. Un comparador por ids aceptaría la captura equivocada.

El witness existe para que un consumidor futuro pueda **negarse a comparar**; no es lo que
establece la identidad.
"""

from __future__ import annotations

import asyncio
import json
import pathlib

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.decision import assembler
from app.decision import runtime_capture as rc
from app.decision.runtime_capture import Correspondencia, DesenlaceCaptura

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def _row(rid, pets=True, **over):
    """Activos que sólo se diferencian en una señal que el legacy NO mira.

    `acepta_mascotas` es la palanca perfecta para el caso adversarial: cambia las filas sin
    cambiar el panel, siempre que las preferencias no declaren mascotas.
    """
    row = {
        "id": rid, "direccion": f"Dir {rid}", "tipo_activo": "Departamento",
        "operacion": "ARRIENDO", "precio": 380, "imagen_url": None,
        "caminabilidad": 95, "caminabilidad_fuente": "osm", "ruido": "BAJO",
        "vegetacion": 42, "lat": -0.18, "lon": -78.48,
        "caracteristicas": {"num_dormitorios": 2, "acepta_mascotas": pets},
        "servicios_cercanos": "\U0001F333 Parque a ~300 m",
        "conectividad": "\U0001F687 Metro a ~500 m (7 min a pie)",
    }
    row.update(over)
    return row


IDS = ["a", "b"]
PREFS = {"dormitorios": 2, "presupuesto_max": 700}
"""SIN mascotas a propósito: es lo que hace que la señal de mascotas no toque el panel."""


def _turno(ids=IDS):
    return [
        HumanMessage(content="consulta"),
        ToolMessage(content=json.dumps({"assets": [{"id": i} for i in ids]}),
                    name="tool_search_nearby_assets", tool_call_id="t1"),
        AIMessage(content="Encontré algunas opciones."),
    ]


@pytest.fixture
def catastro(monkeypatch):
    """Permite encadenar varias rondas, cada una con SUS filas — como el bucle del grafo."""
    estado = {"llamadas": 0, "rondas": [], "ids": IDS}

    def _programar(*rondas):
        """Cada ronda es `(rows, curaciones)` o una excepción a levantar."""
        estado["rondas"] = list(rondas)

        async def fake_fetch(_ids):
            estado["llamadas"] += 1
            ronda = estado["rondas"].pop(0)
            if isinstance(ronda, BaseException):
                raise ronda
            return ronda

        monkeypatch.setattr(assembler, "_fetch_cards_rows", fake_fetch)
        return estado

    return _programar


def _panel(ids=None, prefs=PREFS):
    return asyncio.run(assembler.construir_panel(
        _turno(ids or IDS), preferencias=prefs, session_id="s-r0f1"))


def _romper_el_nucleo(monkeypatch, cuando):
    """Hace que el núcleo reviente en la llamada número `cuando` (1-indexada)."""
    real = assembler._decidir_desde_filas
    veces = {"n": 0}

    def quizas_revienta(*a, **kw):
        veces["n"] += 1
        if veces["n"] == cuando:
            raise RuntimeError("el núcleo reventó en esta ronda")
        return real(*a, **kw)

    monkeypatch.setattr(assembler, "_decidir_desde_filas", quizas_revienta)
    return veces


# ══ T1 · EL COMMIT VA DESPUÉS DE DECIDIR ═══════════════════════════════════════════


def test_T1_la_captura_se_compromete_TRAS_una_decision_exitosa(catastro):
    filas = [_row("a"), _row("b")]
    catastro((filas, {}))

    with rc.capturar_entradas_de_decision() as caja:
        panel = _panel()

    assert caja.desenlace is DesenlaceCaptura.DECISION
    assert caja.commits == 1
    assert caja.entradas.rows is filas
    assert caja.entradas.witness == rc.huella_del_panel(panel)


# ══ T2-T3 · UNA TENTATIVA FALLIDA NO PISA LA CAPTURA ═══════════════════════════════


def test_T2_T3_exito_A_luego_fallo_B_deja_la_captura_A(catastro, monkeypatch):
    """EL defecto que R0F1 cierra, reproducido tal cual.

    El nodo del grafo atrapa la excepción operacional y conserva el panel A. La caja tiene
    que conservar A también: si guardara B, un contrafactual compararía las entradas de una
    decisión que nadie llegó a ver.
    """
    filas_a = [_row("a"), _row("b")]
    filas_b = [_row("a", pets=False), _row("b", pets=False)]
    catastro((filas_a, {}), (filas_b, {}))
    _romper_el_nucleo(monkeypatch, cuando=2)

    with rc.capturar_entradas_de_decision() as caja:
        _panel()                                   # ronda 1 · A, éxito
        assert caja.entradas.rows is filas_a

        with pytest.raises(RuntimeError):
            _panel()                               # ronda 2 · B, revienta

        assert caja.entradas.rows is filas_a, \
            "una tentativa fallida pisó la captura de la decisión vigente"
        assert caja.entradas.rows is not filas_b
        assert caja.commits == 1, "un intento fallido no puede contar como commit"


# ══ T4 · DOS ÉXITOS · GANA EL ÚLTIMO ═══════════════════════════════════════════════


def test_T4_exito_A_luego_exito_B_deja_la_captura_B(catastro):
    filas_a = [_row("a"), _row("b")]
    filas_b = [_row("a"), _row("b")]
    catastro((filas_a, {}), (filas_b, {}))

    with rc.capturar_entradas_de_decision() as caja:
        _panel()
        assert caja.entradas.rows is filas_a
        _panel()

    assert caja.entradas.rows is filas_b, "la segunda decisión vigente no quedó capturada"
    assert caja.entradas.rows is not filas_a
    assert caja.commits == 2


# ══ T5-T6 · MISMO PANEL, FILAS DISTINTAS ═══════════════════════════════════════════


def test_T5_mismo_panel_visible_y_filas_DISTINTAS_captura_la_correcta(catastro):
    """El caso adversarial. Las dos rondas producen un panel idéntico —los ids, el orden y
    los scores coinciden— porque las preferencias no declaran mascotas. Las filas difieren
    justo en esa señal.

    La captura tiene que ser la de B **por flujo de control**, no porque algo del resultado
    lo delate: nada lo delata.
    """
    filas_a = [_row("a", pets=True), _row("b", pets=True)]
    filas_b = [_row("a", pets=False), _row("b", pets=False)]
    catastro((filas_a, {}), (filas_b, {}))

    with rc.capturar_entradas_de_decision() as caja:
        panel_a = _panel()
        panel_b = _panel()

    assert rc.huella_del_panel(panel_a) == rc.huella_del_panel(panel_b), \
        "el fixture no es adversarial: los paneles ya se distinguen solos"
    assert caja.entradas.rows is filas_b
    assert caja.entradas.rows is not filas_a


def test_T6_cotejar_por_IDS_seria_insuficiente(catastro):
    """La mitad negativa de T5: se demuestra que el detector ingenuo no sirve.

    Si la correspondencia se fundara en «ids capturados == ids visibles», A pasaría por
    buena estando equivocada. Por eso el fundamento es el commit y el witness es sólo una
    comprobación adicional.
    """
    filas_a = [_row("a", pets=True), _row("b", pets=True)]
    filas_b = [_row("a", pets=False), _row("b", pets=False)]
    catastro((filas_a, {}), (filas_b, {}))

    with rc.capturar_entradas_de_decision() as caja:
        _panel()
        ids_a = [r["id"] for r in caja.entradas.rows]
        panel_b = _panel()

    ids_visibles = [c["id"] for c in panel_b["cards"]]
    assert ids_a == ids_visibles == [r["id"] for r in filas_b], \
        "los ids no distinguen las dos rondas: por eso no pueden ser el fundamento"
    assert caja.entradas.rows is filas_b, "el flujo de control sí distingue"


# ══ T7 · PANEL VACÍO ═══════════════════════════════════════════════════════════════


def test_T7_un_panel_vacio_NO_deja_viva_la_captura_anterior(catastro):
    """Un turno sin activos sustituye al panel anterior. Conservar la captura previa
    afirmaría que corresponde a lo vigente — el mismo defecto por la puerta de atrás."""
    filas_a = [_row("a"), _row("b")]
    catastro((filas_a, {}))

    with rc.capturar_entradas_de_decision() as caja:
        _panel()
        assert caja.hay_captura

        panel_vacio = asyncio.run(assembler.construir_panel(
            [HumanMessage(content="hola")], preferencias=PREFS, session_id="s-r0f1"))

    assert panel_vacio["cards"] == []
    assert caja.desenlace is DesenlaceCaptura.VACIA
    assert caja.entradas is None, "no se inventan filas: nunca pasaron por el núcleo"
    assert not caja.hay_captura


def test_T7b_el_catastro_degradado_tambien_registra_VACIA(catastro):
    """La otra salida temprana: el catastro degradó. Mismo razonamiento.

    Degradar es devolver `None`, no lanzar — así está documentado `_fetch_cards_rows` y así
    lo consume `construir_panel`. Con `preferencias` explícitas una excepción se PROPAGA (no
    hay `gather(return_exceptions=True)` en esa rama), y ése es otro camino: el de T2/T3,
    donde tampoco se compromete nada.
    """
    catastro(([_row("a")], {}), None)

    with rc.capturar_entradas_de_decision() as caja:
        _panel()
        assert caja.hay_captura
        panel = _panel()

    assert panel["cards"] == []
    assert caja.desenlace is DesenlaceCaptura.VACIA and caja.entradas is None


# ══ T8-T9 · EL WITNESS ═════════════════════════════════════════════════════════════


def test_T8_el_witness_COINCIDE_con_el_panel_visible(catastro):
    catastro(([_row("a"), _row("b")], {}))
    with rc.capturar_entradas_de_decision() as caja:
        panel = _panel()
    assert rc.cotejar(caja, panel) is Correspondencia.COINCIDE


def test_T9_un_witness_DESALINEADO_se_detecta(catastro):
    """Para que un consumidor futuro falle CERRADO en vez de comparar contra otro panel."""
    catastro(([_row("a"), _row("b")], {}))
    with rc.capturar_entradas_de_decision() as caja:
        panel = _panel()

    otro = {"cards": [{**panel["cards"][0], "encaje": 1}], "descartadas": []}
    assert rc.cotejar(caja, otro) is Correspondencia.NO_COINCIDE
    assert rc.cotejar(None, panel) is Correspondencia.SIN_CAPTURA
    assert rc.cotejar(rc.DecisionCaptureBox(), panel) is Correspondencia.SIN_CAPTURA

    vacia = rc.DecisionCaptureBox(desenlace=DesenlaceCaptura.VACIA)
    assert rc.cotejar(vacia, panel) is Correspondencia.VACIA


def test_T9b_el_witness_cubre_los_ejes_que_importan(catastro):
    """Orden visible, descartadas, encaje, medido, cobertura, razones y duros.

    No lleva `score_version`: no viaja en la tarjeta —es una constante de módulo— y meterlo
    aquí sería describir un campo que no existe.
    """
    catastro(([_row("a"), _row("b")], {}))
    with rc.capturar_entradas_de_decision() as caja:
        panel = _panel()

    visibles, descartadas = caja.entradas.witness
    assert len(visibles) == len(panel["cards"]) and len(descartadas) == 0
    (id_, encaje, medido, cobertura, razones, duros) = visibles[0]
    assert id_ == panel["cards"][0]["id"]
    assert encaje == panel["cards"][0]["encaje"]
    assert medido == panel["cards"][0]["encaje_medido"]
    assert cobertura == panel["cards"][0]["encaje_cobertura"]
    assert razones and isinstance(razones, tuple)
    assert isinstance(duros, tuple)

    # Cambiar cualquiera de esos ejes tiene que mover la huella.
    for campo, valor in (("encaje", 3), ("encaje_medido", 3), ("encaje_cobertura", 0.1),
                         ("duros_incumplidos", ["tipo_inmueble"])):
        alterado = {"cards": [{**panel["cards"][0], campo: valor}], "descartadas": []}
        assert rc.huella_del_panel(alterado) != rc.huella_del_panel(
            {"cards": panel["cards"][:1], "descartadas": []}), campo


# ══ T10-T13 · LO QUE R0F YA GARANTIZABA, SIGUE ═════════════════════════════════════


def test_T10_sin_buzon_el_panel_no_cambia(catastro):
    catastro(([_row("a"), _row("b")], {}), ([_row("a"), _row("b")], {}))
    assert rc.caja_actual() is None
    sin = _panel()
    with rc.capturar_entradas_de_decision():
        con = _panel()
    assert [c["id"] for c in sin["cards"]] == [c["id"] for c in con["cards"]]
    assert rc.huella_del_panel(sin) == rc.huella_del_panel(con)


def test_T11_T12_identidad_de_filas_y_curaciones(catastro):
    filas = [_row("a"), _row("b")]
    cur = {"a": [{"nota": "x"}]}
    catastro((filas, cur))
    with rc.capturar_entradas_de_decision() as caja:
        _panel()
    assert caja.entradas.rows is filas
    assert caja.entradas.curaciones is cur


def test_T13_comprometer_no_añade_consultas_de_inventario(catastro):
    estado = catastro(([_row("a"), _row("b")], {}))
    with rc.capturar_entradas_de_decision():
        _panel()
    assert estado["llamadas"] == 1


# ══ T14-T15 · EL FALLBACK DE CHAT ══════════════════════════════════════════════════


def test_T14_T15_el_fallback_se_resuelve_por_la_MISMA_semantica(catastro, monkeypatch):
    """`build_result_cards` llama a `construir_panel`, así que no necesita regla especial.

    Si el fallback tiene éxito, su commit sustituye al anterior porque es la decisión
    vigente. Si revienta, no compromete nada y sobrevive la captura previa. La semántica de
    commit lo resuelve sola — que es justo lo que se pedía: nada de reglas por nombre.
    """
    filas_1 = [_row("a"), _row("b")]
    filas_2 = [_row("a"), _row("b")]
    catastro((filas_1, {}), (filas_2, {}))

    with rc.capturar_entradas_de_decision() as caja:
        _panel()
        assert caja.entradas.rows is filas_1
        asyncio.run(assembler.build_result_cards(_turno(), session_id="s-r0f1",
                                                 preferencias=PREFS))
        assert caja.entradas.rows is filas_2, "el fallback exitoso no sustituyó la captura"

    # Y si el fallback revienta, la captura vigente se conserva.
    catastro((filas_1, {}), (filas_2, {}))
    _romper_el_nucleo(monkeypatch, cuando=2)
    with rc.capturar_entradas_de_decision() as caja:
        _panel()
        with pytest.raises(RuntimeError):
            asyncio.run(assembler.build_result_cards(_turno(), session_id="s-r0f1",
                                                     preferencias=PREFS))
        assert caja.entradas.rows is filas_1


# ══ T16-T18 · LÍMITES QUE NO SE MUEVEN ═════════════════════════════════════════════


def test_T16_el_nucleo_sigue_sin_saber_que_existe_la_captura():
    import ast

    arbol = ast.parse((RAIZ / "app" / "decision" / "assembler.py").read_text(encoding="utf-8"))
    nucleo = next(n for n in ast.walk(arbol)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == "_decidir_desde_filas")
    volcado = ast.dump(nucleo)
    for prohibido in ("comprometer", "caja_actual", "ContextVar", "runtime_capture",
                      "witness"):
        assert prohibido not in volcado, f"el núcleo toca el canal: {prohibido}"


def test_T17_el_puente_sigue_sin_nada_del_comprador():
    import ast

    campos = set(rc.DecisionInputCapture.__dataclass_fields__)
    assert campos == {"rows", "curaciones", "ids", "witness"}

    arbol = ast.parse((RAIZ / "app" / "decision" / "runtime_capture.py")
                      .read_text(encoding="utf-8"))
    modulos = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.ImportFrom) and n.module:
            modulos.add(n.module)
        elif isinstance(n, ast.Import):
            modulos.update(a.name for a in n.names)
    assert not any(m.startswith("app.buy") for m in modulos)

    identificadores = {n.id for n in ast.walk(arbol) if isinstance(n, ast.Name)}
    identificadores |= {n.attr for n in ast.walk(arbol) if isinstance(n, ast.Attribute)}
    for prohibido in ("buyer", "principal", "user_id", "pets_operation", "candidato"):
        assert not any(prohibido in i for i in identificadores), prohibido


def test_T18_ni_AgentState_ni_el_config_ganaron_nada():
    import ast

    estado = (RAIZ / "app" / "agent" / "state.py").read_text(encoding="utf-8")
    for prohibido in ("captura", "capture", "witness", "runtime_capture", "commit"):
        assert prohibido not in estado, f"AgentState ganó {prohibido}"

    arbol = ast.parse((RAIZ / "app" / "routers" / "chat.py").read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.FunctionDef) and n.name == "_langgraph_config")
    volcado = ast.dump(fn)
    for prohibido in ("captura", "capture", "witness", "commit"):
        assert prohibido not in volcado, f"el config transporta {prohibido}"


# ══ T19-T20 · AISLAMIENTO Y LIMPIEZA ═══════════════════════════════════════════════


def test_T19_dos_turnos_CONCURRENTES_comprometen_cada_uno_lo_suyo(monkeypatch):
    filas = {"A": [_row("a-1")], "B": [_row("b-1")]}
    vistas = {}

    async def turno(etiqueta):
        async def fake_fetch(_ids):
            await asyncio.sleep(0)
            return (filas[etiqueta], {})

        monkeypatch.setattr(assembler, "_fetch_cards_rows", fake_fetch)
        with rc.capturar_entradas_de_decision() as caja:
            await assembler.construir_panel(_turno(["a-1"]), preferencias=PREFS,
                                            session_id=f"s-{etiqueta}")
            await asyncio.sleep(0)
            vistas[etiqueta] = caja.entradas.rows

    async def ambos():
        await asyncio.wait_for(asyncio.gather(turno("A"), turno("B")), timeout=10)

    asyncio.run(ambos())
    assert vistas["A"] is filas["A"] and vistas["B"] is filas["B"]
    assert vistas["A"] is not vistas["B"]


def test_T20_la_limpieza_sigue_intacta(catastro):
    catastro(([_row("a")], {}))
    with rc.capturar_entradas_de_decision():
        _panel()
    assert rc.caja_actual() is None

    class Roto(RuntimeError):
        pass

    with pytest.raises(Roto):
        with rc.capturar_entradas_de_decision():
            raise Roto("x")
    assert rc.caja_actual() is None

    async def cancelado():
        t = asyncio.create_task(_turno_largo())
        await asyncio.sleep(0)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
        return rc.caja_actual()

    async def _turno_largo():
        with rc.capturar_entradas_de_decision():
            await asyncio.sleep(10)

    assert asyncio.run(cancelado()) is None


# ══ T21-T24 · MUTACIONES ═══════════════════════════════════════════════════════════


def test_T21_MUTACION_comprometer_ANTES_de_decidir_se_detecta():
    """Es la posición de la llamada lo que corrige R0F1, así que la posición se afirma."""
    import ast

    fuente = (RAIZ / "app" / "decision" / "assembler.py").read_text(encoding="utf-8")
    roto = fuente.replace(
        "    comprometer(rows, curaciones, ids, panel)\n    return panel",
        "    comprometer(rows, curaciones, ids, {})\n"
        "    panel = _decidir_desde_filas(rows, curaciones, ids=ids,\n"
        "                                 preferencias=preferencias, messages=messages,\n"
        "                                 session_id=session_id)\n    return panel", 1)
    assert roto != fuente, "el ancla de la mutación ya no existe"

    def _orden(src):
        fn = next(n for n in ast.walk(ast.parse(src))
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == "construir_panel")
        nucleo = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
                  and getattr(n.func, "id", None) == "_decidir_desde_filas"]
        commit = [n.lineno for n in ast.walk(fn) if isinstance(n, ast.Call)
                  and getattr(n.func, "id", None) == "comprometer"]
        return max(commit) > max(nucleo)

    assert _orden(fuente), "el código real compromete después de decidir"
    assert not _orden(roto), "el detector de posición no ve la inversión: sería inerte"


def test_T22_MUTACION_que_un_fallo_PISE_la_captura_se_detecta(catastro, monkeypatch):
    """Si el commit volviera delante del núcleo, T2/T3 se pondrían rojos. Aquí se demuestra
    que el detector distingue las dos situaciones."""
    filas_a = [_row("a")]
    filas_b = [_row("b")]

    catastro((filas_a, {}), (filas_b, {}))
    _romper_el_nucleo(monkeypatch, cuando=2)
    with rc.capturar_entradas_de_decision() as caja:
        _panel()
        with pytest.raises(RuntimeError):
            _panel()
        correcto = caja.entradas.rows

    # La mutación, simulada sobre la caja: comprometer sin que la decisión existiera.
    with rc.capturar_entradas_de_decision() as caja2:
        rc.comprometer(filas_a, {}, ["a"], {"cards": [], "descartadas": []})
        rc.comprometer(filas_b, {}, ["b"], {"cards": [], "descartadas": []})
        mutado = caja2.entradas.rows

    assert correcto is filas_a, "el código real conserva la decisión vigente"
    assert mutado is filas_b, "el detector no distingue un commit indebido: sería inerte"


def test_T23_MUTACION_cotejar_solo_por_IDS_se_detecta(catastro):
    """Los ids coinciden en las dos rondas; el witness también, porque el panel es idéntico.

    Es exactamente por eso que ninguno de los dos puede ser el fundamento: lo único que
    distingue A de B es cuál corrió last y tuvo éxito.
    """
    filas_a = [_row("a", pets=True)]
    filas_b = [_row("a", pets=False)]
    catastro((filas_a, {}), (filas_b, {}))

    with rc.capturar_entradas_de_decision() as caja:
        panel_a = _panel()
        panel_b = _panel()

    assert rc.huella_del_panel(panel_a) == rc.huella_del_panel(panel_b)
    assert rc.cotejar(caja, panel_a) is Correspondencia.COINCIDE, \
        "el witness no puede distinguir A de B — y no pretende hacerlo"
    assert caja.entradas.rows is filas_b, "sólo el flujo de control resuelve la identidad"


def test_T24_MUTACION_copiar_las_filas_se_detecta(catastro):
    import copy

    filas = [_row("a"), _row("b")]
    catastro((filas, {}))
    with rc.capturar_entradas_de_decision() as caja:
        _panel()

    copiadas = copy.deepcopy(caja.entradas.rows)
    assert caja.entradas.rows is filas
    assert copiadas is not filas and copiadas == filas, \
        "el detector de identidad no distingue una copia de la referencia"
