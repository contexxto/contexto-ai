"""F3-SHADOW-DECISION-RUNTIME-R0G · las puertas, la captura y el aislamiento visible.

QUÉ CONGELA, y qué NO.

    congela    que apagado no cuesta NADA; que una captura que no corresponde al panel visto
               corta el paso ANTES de leer memoria y ANTES de correr el núcleo; que la
               lectura del comprador cuesta 0 ó 1 SELECT según el camino; y que el resultado
               sombra no puede llegar a nada visible
    NO congela que el comprador mejore la recomendación

La derivación de la operación vive en `test_buyer_decision_shadow.py`.
"""

from __future__ import annotations

import ast
import asyncio
import datetime as dt
import json
import pathlib

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.buyer import decision_shadow as ds
from app.buyer.boundary import ClearPetsRequired, SetBedroomsMin, SetPetsRequired
from app.buyer.candidato import DesenlaceCandidato, ObservacionCandidato
from app.buyer.decision_shadow import (
    ClaseCaptura, ClaseDelta, FuenteDelEstado, OperacionMascotas, RelacionPersistencia,
    observar_sombra_de_decision,
)
from app.buyer.extractor import AfirmacionDurable, LoteExtraccion
from app.buyer.reductor import reducir
from app.contracts.buyer_v0 import BuyerContextV0
from app.decision import assembler
from app.decision import runtime_capture as rc

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CHAT = RAIZ / "app" / "routers" / "chat.py"
MODULO = RAIZ / "app" / "buyer" / "decision_shadow.py"

T0 = dt.datetime(2026, 9, 14, 12, 0, tzinfo=dt.timezone.utc)
A = "11111111-1111-4111-8111-111111111111"
IDS = ["pet-si", "pet-no", "pet-nd"]
PREFS = {"dormitorios": 2}


class _Usuario:
    def __init__(self, user_id=A):
        self.user_id = user_id


def _row(rid, pets):
    car = {"num_dormitorios": 2}
    if pets is not None:
        car["acepta_mascotas"] = pets
    return {
        "id": rid, "direccion": f"Dir {rid}", "tipo_activo": "Departamento",
        "operacion": "ARRIENDO", "precio": 380, "imagen_url": None,
        "caminabilidad": 95, "caminabilidad_fuente": "osm", "ruido": "BAJO",
        "vegetacion": 42, "lat": -0.18, "lon": -78.48, "caracteristicas": car,
        "servicios_cercanos": "\U0001F333 Parque", "conectividad": "\U0001F687 Metro",
    }


def _universo():
    return [_row("pet-si", True), _row("pet-no", False), _row("pet-nd", None)]


def _mensajes():
    return [
        HumanMessage(content="consulta"),
        ToolMessage(content=json.dumps({"assets": [{"id": i} for i in IDS]}),
                    name="tool_search_nearby_assets", tool_call_id="t1"),
        AIMessage(content="ok"),
    ]


@pytest.fixture
def encendido(monkeypatch):
    """Las cuatro puertas abiertas. Cada test que mida una puerta la cierra a mano."""
    monkeypatch.setattr(ds.settings, "buyer_shadow_decision_compare", True, raising=False)
    monkeypatch.setattr(ds.settings, "buyer_current_turn_candidate_shadow", True)
    monkeypatch.setattr(ds.settings, "buyer_updater_shadow", False)
    from app.buyer import sombra
    monkeypatch.setattr(sombra.settings, "buyer_shadow_allowlist", A)
    monkeypatch.setattr(ds.settings, "buyer_shadow_allowlist", A, raising=False)


@pytest.fixture
def catastro(monkeypatch):
    estado = {"llamadas": 0, "rows": None}

    def _instalar(rows=None):
        estado["rows"] = _universo() if rows is None else rows

        async def fake(_ids):
            estado["llamadas"] += 1
            return (estado["rows"], {})

        monkeypatch.setattr(assembler, "_fetch_cards_rows", fake)
        return estado

    return _instalar


@pytest.fixture
def lector():
    """Cuenta los SELECT de memoria. Es el instrumento de T11-T15."""
    estado = {"lecturas": 0, "contexto": None}

    async def leer(_user):
        estado["lecturas"] += 1
        return estado["contexto"]

    estado["fn"] = leer
    return estado


def _lote(*mutaciones):
    return LoteExtraccion(source_message_id="m-1",
                          afirmaciones=[AfirmacionDurable(motivo="m", mutacion=x)
                                        for x in mutaciones])


def _contexto(*lotes):
    ctx = BuyerContextV0(buyer_id=A, updated_at=T0)
    for lote in lotes:
        ctx = reducir(ctx, lote, T0)
    return ctx


class _Candidato:
    def __init__(self, lote, contexto):
        self.lote = lote
        self.contexto = contexto


class _Computo:
    def __init__(self, candidato):
        self.candidato = candidato


def _observacion(lote=None, contexto=None, desenlace=DesenlaceCandidato.CALCULADO):
    if lote is None and contexto is None:
        return ObservacionCandidato(desenlace)
    return ObservacionCandidato(desenlace, computo=_Computo(_Candidato(lote, contexto)))


def _piezas(observacion):
    """La observación, DESCOMPUESTA. Nunca viaja entera.

    R0B congeló que `ObservacionCandidato` no se pasa a nadie, y la propiedad protege de que
    alguien acabe leyéndole el desenlace o la duración para decidir con ellos. El comparador
    recibe exactamente las dos piezas que necesita.
    """
    return {"desenlace_candidato": observacion.desenlace, "computo": observacion.computo}


def _correr(user, observacion, *, caja_abierta=True, panel=None, lector_fn=None,
            prefs=None, cards=None, descartadas=None):
    async def main():
        if not caja_abierta:
            return await observar_sombra_de_decision(
                user, **_piezas(observacion), cards=cards or [], descartadas=descartadas or [],
                preferencias=prefs or PREFS, messages=_mensajes(), session_id="s",
                leer_memoria=lector_fn)
        with rc.capturar_entradas_de_decision():
            real = panel or await assembler.construir_panel(
                _mensajes(), preferencias=prefs or PREFS, session_id="s")
            return await observar_sombra_de_decision(
                user, **_piezas(observacion),
                cards=real["cards"] if cards is None else cards,
                descartadas=real["descartadas"] if descartadas is None else descartadas,
                preferencias=prefs or PREFS, messages=_mensajes(), session_id="s",
                leer_memoria=lector_fn)

    return asyncio.run(main())


# ══ T1-T3 · APAGADO NO CUESTA NADA ═════════════════════════════════════════════════


def test_T1_con_el_flag_de_compare_APAGADO_no_se_hace_nada(catastro, lector, monkeypatch):
    """Es el estado por defecto y el de todo despliegue hoy. Cero, literalmente."""
    monkeypatch.setattr(ds.settings, "buyer_shadow_decision_compare", False, raising=False)
    monkeypatch.setattr(ds.settings, "buyer_current_turn_candidate_shadow", True)
    catastro()
    obs = _correr(_Usuario(), _observacion(_lote(SetPetsRequired()), _contexto()),
                  lector_fn=lector["fn"])
    assert obs is None
    assert lector["lecturas"] == 0


def test_T2_con_el_flag_del_CANDIDATO_apagado_no_se_hace_nada(encendido, catastro, lector,
                                                              monkeypatch):
    monkeypatch.setattr(ds.settings, "buyer_current_turn_candidate_shadow", False)
    catastro()
    assert _correr(_Usuario(), _observacion(_lote(SetPetsRequired()), _contexto()),
                   lector_fn=lector["fn"]) is None
    assert lector["lecturas"] == 0


def test_T3_fuera_de_la_cohorte_no_se_hace_nada(encendido, catastro, lector):
    catastro()
    assert _correr(_Usuario("otro-uid"), _observacion(_lote(SetPetsRequired()), _contexto()),
                   lector_fn=lector["fn"]) is None
    assert lector["lecturas"] == 0


def test_T3b_un_anonimo_no_compara(encendido, catastro, lector):
    catastro()
    for anon in (None, _Usuario(""), _Usuario("   ")):
        assert _correr(anon, _observacion(_lote(SetPetsRequired()), _contexto()),
                       lector_fn=lector["fn"]) is None
    assert lector["lecturas"] == 0


def test_el_UPDATER_no_es_requisito(encendido, catastro, lector, monkeypatch):
    """Comparar no exige permiso de escritura. Con el updater apagado el experimento
    funciona y la relación con la persistencia es `NO_INTENTADA`."""
    monkeypatch.setattr(ds.settings, "buyer_updater_shadow", False)
    catastro()
    obs = _correr(_Usuario(), _observacion(_lote(SetPetsRequired()), _contexto()),
                  lector_fn=lector["fn"])
    assert obs is not None and obs.corridas_del_nucleo == 1
    assert obs.relacion_persistencia is RelacionPersistencia.NO_INTENTADA


# ══ T4-T7 · LA CAPTURA MANDA ═══════════════════════════════════════════════════════


def test_T4_sin_captura_no_hay_comparacion(encendido, catastro, lector):
    """Cero lecturas y cero corridas: no se compara «de todos modos»."""
    catastro()
    obs = _correr(_Usuario(), _observacion(_lote(SetPetsRequired()), _contexto()),
                  caja_abierta=False, cards=[{"id": "x", "encaje": 1}],
                  lector_fn=lector["fn"])
    assert obs.captura is ClaseCaptura.AUSENTE
    assert obs.delta is ClaseDelta.NO_COMPARABLE
    assert obs.corridas_del_nucleo == 0 and obs.lecturas_del_comprador == 0
    assert lector["lecturas"] == 0


def test_T5_una_captura_VACIA_no_habilita_nada(encendido, catastro, lector):
    """Un turno sin activos registra VACIA; comparar contra eso no significaría nada."""
    catastro()

    async def main():
        with rc.capturar_entradas_de_decision():
            await assembler.construir_panel([HumanMessage(content="hola")],
                                            preferencias=PREFS, session_id="s")
            return await observar_sombra_de_decision(
                _Usuario(), **_piezas(_observacion(_lote(SetPetsRequired()), _contexto())),
                cards=[], descartadas=[], preferencias=PREFS, messages=_mensajes(),
                session_id="s", leer_memoria=lector["fn"])

    obs = asyncio.run(main())
    assert obs.captura is ClaseCaptura.VACIA
    assert obs.corridas_del_nucleo == 0 and lector["lecturas"] == 0


def test_T6_M5_una_captura_DESALINEADA_corta_antes_de_gastar(encendido, catastro, lector):
    """El artefacto visible que se le pasa NO es el que produjo la captura."""
    catastro()
    obs = _correr(_Usuario(), _observacion(_lote(SetPetsRequired()), _contexto()),
                  cards=[{"id": "otro", "encaje": 50}], descartadas=[],
                  lector_fn=lector["fn"])
    assert obs.captura is ClaseCaptura.NO_COINCIDE
    assert obs.delta is ClaseDelta.NO_COMPARABLE
    assert obs.corridas_del_nucleo == 0, "se comparó pese al desalineamiento"
    assert lector["lecturas"] == 0, "se leyó memoria pese al desalineamiento"


def test_T7_con_la_captura_ALINEADA_se_compara(encendido, catastro, lector):
    catastro()
    obs = _correr(_Usuario(), _observacion(_lote(SetPetsRequired()), _contexto()),
                  lector_fn=lector["fn"])
    assert obs.captura is ClaseCaptura.COINCIDE
    assert obs.corridas_del_nucleo == 1


# ══ T8-T10 · OPERACIÓN DESDE EL TURNO ══════════════════════════════════════════════


def test_T8_T9_el_turno_manda_y_no_cuesta_SELECT(encendido, catastro, lector):
    catastro()
    for mutacion, esperada in ((SetPetsRequired(), OperacionMascotas.REQUERIR),
                               (ClearPetsRequired(), OperacionMascotas.RETIRAR)):
        obs = _correr(_Usuario(), _observacion(_lote(mutacion), _contexto()),
                      lector_fn=lector["fn"])
        assert obs.operacion is esperada
        assert obs.fuente is FuenteDelEstado.TURNO_ACTUAL
    assert lector["lecturas"] == 0


def test_T10_una_ambigua_del_turno_no_corre_el_nucleo(encendido, catastro, lector):
    from app.buyer.boundary import BuyerFieldV0
    from app.buyer.extractor import AfirmacionAmbiguous

    catastro()
    lote = LoteExtraccion(source_message_id="m-1", afirmaciones=[
        AfirmacionAmbiguous(motivo="dudoso", campo=BuyerFieldV0.PETS_REQUIRED)])
    obs = _correr(_Usuario(), _observacion(lote, _contexto()), lector_fn=lector["fn"])
    assert obs.operacion is OperacionMascotas.NO_COMPARABLE
    assert obs.corridas_del_nucleo == 0 and lector["lecturas"] == 0


# ══ T11-T15 · LA MEMORIA, Y CUÁNTO CUESTA ══════════════════════════════════════════


@pytest.mark.parametrize("lotes, esperada", [
    ((_lote(SetPetsRequired()),), OperacionMascotas.REQUERIR),
    ((_lote(SetPetsRequired()), _lote(ClearPetsRequired())), OperacionMascotas.RETIRAR),
])
def test_T11_T12_con_computo_la_memoria_sale_del_candidato_SIN_select(
        encendido, catastro, lector, lotes, esperada):
    """El turno tocó OTRO campo, así que el cómputo ya cargó la base: cero SELECT."""
    catastro()
    memoria = _contexto(*lotes)
    # El turno de ahora toca dormitorios, no mascotas. El contexto del candidato conserva
    # el valor Y la evidencia de mascotas de la memoria previa.
    contexto_del_turno = reducir(memoria, _lote(SetBedroomsMin(bedrooms_min=3)), T0)
    obs = _correr(_Usuario(),
                  _observacion(_lote(SetBedroomsMin(bedrooms_min=3)), contexto_del_turno),
                  lector_fn=lector["fn"])
    assert obs.operacion is esperada
    assert obs.fuente is FuenteDelEstado.MEMORIA_PERSISTIDA
    assert obs.lecturas_del_comprador == 0 and lector["lecturas"] == 0


@pytest.mark.parametrize("lotes, esperada, fuente", [
    ((_lote(SetPetsRequired()),), OperacionMascotas.REQUERIR,
     FuenteDelEstado.MEMORIA_PERSISTIDA),
    ((_lote(SetPetsRequired()), _lote(ClearPetsRequired())), OperacionMascotas.RETIRAR,
     FuenteDelEstado.MEMORIA_PERSISTIDA),
    ((), OperacionMascotas.SIN_SENAL, FuenteDelEstado.NINGUNA),
])
def test_T13_T14_T15_sin_afirmaciones_se_lee_UNA_vez(encendido, catastro, lector,
                                                     lotes, esperada, fuente):
    """El único desenlace que es silencio legítimo. Exactamente un SELECT, ni dos."""
    catastro()
    lector["contexto"] = _contexto(*lotes) if lotes else None
    obs = _correr(_Usuario(), _observacion(desenlace=DesenlaceCandidato.SIN_AFIRMACIONES),
                  lector_fn=lector["fn"])
    assert obs.operacion is esperada and obs.fuente is fuente
    assert lector["lecturas"] == 1, f"se leyó {lector['lecturas']} veces"
    assert obs.lecturas_del_comprador == 1


# ══ T36 · UN CANDIDATO QUE FALLÓ NO ES SILENCIO ════════════════════════════════════


@pytest.mark.parametrize("desenlace", [
    DesenlaceCandidato.FALLO, DesenlaceCandidato.SIN_MENSAJE,
    DesenlaceCandidato.SIN_PRINCIPAL, DesenlaceCandidato.FUERA_DE_COHORTE,
    DesenlaceCandidato.DESACTIVADA,
])
def test_T36_un_candidato_no_silencioso_NO_cae_a_la_memoria(encendido, catastro, lector,
                                                            desenlace):
    """«No hubo afirmaciones» y «no sabemos qué pasó» son cosas distintas.

    Usar la memoria persistida cuando el candidato falló sería fingir que conocemos el estado
    del turno. Falla cerrado: sin lectura y sin corrida.
    """
    catastro()
    lector["contexto"] = _contexto(_lote(SetPetsRequired()))
    obs = _correr(_Usuario(), _observacion(desenlace=desenlace), lector_fn=lector["fn"])
    assert obs.delta is ClaseDelta.NO_COMPARABLE
    assert obs.corridas_del_nucleo == 0
    assert lector["lecturas"] == 0, "se cayó a la memoria tras un fallo del candidato"


# ══ T19-T25 · EL EXPERIMENTO ═══════════════════════════════════════════════════════


def test_T19_T20_T21_usa_la_captura_y_no_pide_nada_mas(encendido, catastro, lector):
    """Una sola consulta de inventario en todo el turno: la del panel visible."""
    estado = catastro()
    obs = _correr(_Usuario(), _observacion(_lote(SetPetsRequired()), _contexto()),
                  lector_fn=lector["fn"])
    assert estado["llamadas"] == 1, f"segunda consulta de inventario: {estado['llamadas']}"
    assert obs.corridas_del_nucleo == 1


def test_T22_acuerdo_da_SIN_DELTA(encendido, catastro, lector):
    """El legacy ya exige mascotas y el comprador también: la sombra es indistinguible."""
    catastro()
    obs = _correr(_Usuario(), _observacion(_lote(SetPetsRequired()), _contexto()),
                  prefs={**PREFS, "acepta_mascotas": True}, lector_fn=lector["fn"])
    assert obs.operacion is OperacionMascotas.REQUERIR
    assert obs.delta is ClaseDelta.SIN_DELTA
    assert not obs.top1_cambio and obs.movimientos_de_rejilla == 0


def test_T23_T25_la_memoria_produce_un_delta_ESPERADO_con_movimiento_de_rejilla(
        encendido, catastro, lector):
    """El hilo no habla de mascotas; la memoria sí. R0E predijo exactamente esto: el activo
    que no las acepta cae bajo el corte y sale de la rejilla — no es un filtro duro."""
    catastro()
    lector["contexto"] = _contexto(_lote(SetPetsRequired()))
    obs = _correr(_Usuario(), _observacion(desenlace=DesenlaceCandidato.SIN_AFIRMACIONES),
                  lector_fn=lector["fn"])

    assert obs.operacion is OperacionMascotas.REQUERIR
    assert obs.fuente is FuenteDelEstado.MEMORIA_PERSISTIDA
    assert obs.delta is ClaseDelta.DELTA_ESPERADO
    assert obs.visibles == 3 and obs.sombra == 2
    assert obs.movimientos_de_rejilla == 1
    assert not obs.top1_cambio
    assert obs.deltas_de_score >= 1 and obs.deltas_de_cobertura >= 1


def test_T24_una_retirada_del_turno_no_revive_la_memoria(encendido, catastro, lector):
    """Memoria que exige + retirada ahora → se retira. Y como el legacy del turno tampoco
    las trae, no hay delta: la sombra coincide con lo visible."""
    catastro()
    lector["contexto"] = _contexto(_lote(SetPetsRequired()))
    obs = _correr(_Usuario(), _observacion(_lote(ClearPetsRequired()), _contexto()),
                  lector_fn=lector["fn"])
    assert obs.operacion is OperacionMascotas.RETIRAR
    assert obs.fuente is FuenteDelEstado.TURNO_ACTUAL
    assert obs.delta is ClaseDelta.SIN_DELTA
    assert lector["lecturas"] == 0


# ══ T30-T32 · AISLAMIENTO VISIBLE ══════════════════════════════════════════════════


def test_T30_T31_el_artefacto_visible_no_se_toca(encendido, catastro, lector):
    """Lo que se le pasa al comparador sale intacto: ni las tarjetas ni lo descartado."""
    import copy

    catastro()

    async def main():
        with rc.capturar_entradas_de_decision():
            panel = await assembler.construir_panel(_mensajes(), preferencias=PREFS,
                                                    session_id="s")
            antes = copy.deepcopy({"cards": panel["cards"],
                                   "descartadas": panel["descartadas"]})
            await observar_sombra_de_decision(
                _Usuario(), **_piezas(_observacion(_lote(SetPetsRequired()), _contexto())),
                cards=panel["cards"], descartadas=panel["descartadas"],
                preferencias=PREFS, messages=_mensajes(), session_id="s",
                leer_memoria=lector["fn"])
            return antes, panel

    antes, panel = asyncio.run(main())
    assert panel["cards"] == antes["cards"]
    assert panel["descartadas"] == antes["descartadas"]


def test_T32_M6_el_resultado_sombra_no_se_asigna_a_NADA_visible():
    """Guard AST sobre `chat.py`: el retorno del comparador entra en el registro y en nada más."""
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    llamadas = [n for n in ast.walk(arbol) if isinstance(n, ast.Call)
                and getattr(n.func, "id", None) == "observar_sombra_de_decision"]
    assert len(llamadas) == 2, f"{len(llamadas)} sitios de comparación; se esperaban 2"

    for n in ast.walk(arbol):
        if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            assert "observar_sombra_de_decision" not in ast.dump(n), \
                "el resultado sombra se está guardando en una variable"

    # El único consumidor es el registro.
    for llamada in llamadas:
        envolventes = [c for c in ast.walk(arbol) if isinstance(c, ast.Call)
                       and any(x is llamada for x in ast.walk(c)) and c is not llamada]
        nombres = {getattr(c.func, "id", None) for c in envolventes}
        assert "registrar_sombra_de_decision" in nombres, \
            "el resultado no va al registro: ¿a dónde va?"


def test_T32b_el_detector_de_fuga_visible_NO_es_inerte():
    """LA MITAD NEGATIVA de T32 (mutación M6)."""
    roto = ast.parse(
        "async def f(state):\n"
        "    state['cards'] = await observar_sombra_de_decision(u, o)\n")
    asignaciones = [n for n in ast.walk(roto)
                    if isinstance(n, (ast.Assign, ast.AnnAssign, ast.AugAssign))
                    and "observar_sombra_de_decision" in ast.dump(n)]
    assert asignaciones, "el detector no ve la asignación del resultado sombra"


def test_T34_el_modulo_sombra_no_entra_en_el_grafo_ni_en_el_config():
    """Ni el grafo ni el estado pueden conocerlo: el comprador sigue fuera."""
    for rel in ("app/agent/graph.py", "app/agent/state.py"):
        fuente = (RAIZ / rel).read_text(encoding="utf-8")
        assert "decision_shadow" not in fuente, f"{rel} conoce la sombra de decisión"

    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, ast.FunctionDef) and n.name == "_langgraph_config")
    for prohibido in ("sombra", "shadow", "mascotas", "pets"):
        assert prohibido not in ast.dump(fn), f"el config transporta {prohibido}"


def test_el_registro_no_saca_NADA_sensible(encendido, catastro, lector, caplog):
    """Clases y conteos. Sin ids de activo, sin preferencias crudas, sin el comprador."""
    catastro()
    with caplog.at_level("INFO"):
        ds.registrar(_correr(_Usuario(), _observacion(_lote(SetPetsRequired()), _contexto()),
                             lector_fn=lector["fn"]))

    (registro,) = [r.getMessage() for r in caplog.records if "decision shadow" in r.message]
    for prohibido in (A, "pet-si", "pet-no", "pet-nd", "acepta_mascotas", "dormitorios"):
        assert prohibido not in registro, f"el log filtró {prohibido}"
    assert "operacion=requerir" in registro and "corridas=1" in registro


# ══ T35 · CONCURRENCIA ═════════════════════════════════════════════════════════════


def test_T35_dos_turnos_concurrentes_no_mezclan_observaciones(encendido, monkeypatch):
    """Cada turno con su buzón y su universo. La observación de A no puede traer métricas
    derivadas de la captura de B.

    UN solo doble del catastro que DESPACHA por los ids pedidos, y no dos parches del módulo:
    `monkeypatch.setattr` es global, así que dos turnos concurrentes parcheando por su cuenta
    se pisan y el test mediría al último en escribir, no al aislamiento. Es el mismo error de
    método que la barrera de E3.2b.3a vino a corregir — el estímulo tiene que garantizar lo
    que el nombre promete.
    """
    universos = {"a-1": [_row("a-1", True)], "pet-si": _universo()}
    obs = {}

    async def fake(ids):
        await asyncio.sleep(0)          # cede el control al otro turno, a propósito
        return (universos[ids[0]], {})

    monkeypatch.setattr(assembler, "_fetch_cards_rows", fake)

    def _turno_con(ids):
        return [HumanMessage(content="consulta"),
                ToolMessage(content=json.dumps({"assets": [{"id": i} for i in ids]}),
                            name="tool_search_nearby_assets", tool_call_id="t1"),
                AIMessage(content="ok")]

    async def turno(etiqueta, ids):
        with rc.capturar_entradas_de_decision():
            panel = await assembler.construir_panel(_turno_con(ids), preferencias=PREFS,
                                                    session_id=f"s-{etiqueta}")
            await asyncio.sleep(0)
            obs[etiqueta] = await observar_sombra_de_decision(
                _Usuario(), **_piezas(_observacion(_lote(SetPetsRequired()), _contexto())),
                cards=panel["cards"], descartadas=panel["descartadas"],
                preferencias=PREFS, messages=_turno_con(ids), session_id=f"s-{etiqueta}")

    async def ambos():
        await asyncio.wait_for(
            asyncio.gather(turno("A", ["a-1"]), turno("B", IDS)), timeout=10)

    asyncio.run(ambos())
    assert obs["A"].visibles == 1, "A midió el universo de B"
    assert obs["B"].visibles == 3, "B midió el universo de A"
    assert obs["A"].movimientos_de_rejilla == 0, "A heredó el movimiento de rejilla de B"
    assert obs["B"].movimientos_de_rejilla == 1


# ══ M1 · MUTACIÓN ══════════════════════════════════════════════════════════════════


def test_M1_MUTACION_una_segunda_consulta_de_inventario_se_detecta(encendido, catastro,
                                                                    lector):
    """El contador sube si alguien vuelve a pedir filas. Si no subiera, T20 sería inerte."""
    estado = catastro()
    _correr(_Usuario(), _observacion(_lote(SetPetsRequired()), _contexto()),
            lector_fn=lector["fn"])
    antes = estado["llamadas"]

    asyncio.run(assembler._fetch_cards_rows(IDS))       # la mutación, sólo aquí
    assert estado["llamadas"] == antes + 1, \
        "el contador no distingue una consulta de ninguna: sería inerte"


def test_el_comparador_no_invoca_NADA_caro():
    """Estructural: ni panel productivo, ni fetch, ni extractor, ni intérprete, ni tools."""
    arbol = ast.parse(MODULO.read_text(encoding="utf-8"))
    invocadas = {getattr(n.func, "id", None) or getattr(n.func, "attr", None)
                 for n in ast.walk(arbol) if isinstance(n, ast.Call)}
    for prohibido in ("construir_panel", "build_result_cards", "_fetch_cards_rows",
                      "extraer_preferencias", "interpretar_mensaje", "ainvoke", "astream",
                      "execute", "commit", "anexar_revision"):
        assert prohibido not in invocadas, f"el comparador invoca {prohibido}"

    nucleo = [n for n in ast.walk(arbol) if isinstance(n, ast.Call)
              and getattr(n.func, "id", None) == "_decidir_desde_filas"]
    assert len(nucleo) == 1, f"{len(nucleo)} llamadas al núcleo; se esperaba exactamente 1"
