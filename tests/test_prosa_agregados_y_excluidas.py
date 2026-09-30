"""H3 · prosa ↔ panel autoritativo: dos clases de fallo YA demostradas, nada más.

(a) `agregado_requisito_duro` — una afirmación agregada sobre un requisito duro que el panel no
    sostiene. Caso real (claude-sonnet-5, 2026-09-30): «tengo 5 departamentos en arriendo que
    aceptan mascotas», con 5 tarjetas de las que sólo 3 lo confirman (una no tiene dato y otra
    NO acepta). Sólo se denuncia la SOBRE-afirmación (N > confirmadas); la sub-afirmación
    («ninguna confirma») es D5 y queda fuera de esta unidad.

(b) `excluida_presentada` — el precio de un inmueble que el panel excluyó de la recomendación,
    presentado como candidato. Caso real (claude-sonnet-5-5, 2026-09-30, `tipo_pedido`): «En
    Cumbayá también hay casas dentro de tu tope. Una está en Calle Pampite E5-40, a $139,000…».
    Esas casas salieron de la búsqueda pero el panel las filtró (no son departamento): no están
    en `cards` ni en `descartadas`. Nombrarlas como información sigue permitido; atribuirles
    su precio con un encuadre de encaje («dentro de tu tope», «✅», «te conviene»), no.

Las respuestas reales y sus paneles están en `fixtures/prosa_modelos_2026-09-30.json`: paneles
reconstruidos con `construir_panel` sobre inventario SINTÉTICO y verificados contra lo grabado.
Todas las demás respuestas reales de ese archivo son el control de falsos positivos.
"""
import json
import re
from pathlib import Path

import pytest

from app.verificacion_prosa import verificar_prosa

FIXTURE = Path(__file__).parent / "fixtures" / "prosa_modelos_2026-09-30.json"
CASOS = {c["id"]: c for c in json.loads(FIXTURE.read_text(encoding="utf-8"))["casos"]}
D2 = "claude-sonnet-5/reps#2/presupuesto_no_se_ablanda+zona"
TIPO = "claude-sonnet-5-5/paridad55b#1/tipo_pedido_no_se_estira"
NUEVOS = {"agregado_requisito_duro", "excluida_presentada"}


def _codigos(violaciones, codigo):
    return [v for v in violaciones if v["codigo"] == codigo]


# ── reproducción de los dos defectos reales ────────────────────────────────────────────
def test_D2_la_sobre_afirmacion_de_mascotas_se_detecta():
    c = CASOS[D2]
    v = _codigos(verificar_prosa(c["reply"], c["cards"], c["preferencias"], c["descartadas"]),
                 "agregado_requisito_duro")
    assert len(v) == 1
    assert v[0]["gravedad"] == "alta"
    assert "5" in v[0]["detalle"] and "3" in v[0]["detalle"]
    assert "aceptan mascotas" in v[0]["evidencia"]


def test_tipo_pedido_el_precio_de_una_excluida_presentada_como_candidata_se_detecta():
    c = CASOS[TIPO]
    v = _codigos(verificar_prosa(c["reply"], c["cards"], c["preferencias"], c["descartadas"],
                                 vistas=c["vistas"]), "excluida_presentada")
    montos = {int(re.sub(r"\D", "", m)) for x in v for m in re.findall(r"\$[\d.,]+", x["detalle"])}
    assert {139000, 145000} <= montos
    assert all(x["gravedad"] == "alta" for x in v)


@pytest.mark.parametrize("cid", sorted(set(CASOS) - {D2, TIPO}))
def test_sin_falsos_positivos_en_las_demas_respuestas_reales(cid):
    c = CASOS[cid]
    v = verificar_prosa(c["reply"], c["cards"], c["preferencias"], c["descartadas"], vistas=c["vistas"])
    assert not [x for x in v if x["codigo"] in NUEVOS], [x for x in v if x["codigo"] in NUEVOS]


# ── (a) agregado sobre requisito duro: bordes ──────────────────────────────────────────
def _card(i, precio, mascotas):
    razones = [{"texto": f"Dentro de tu presupuesto (${precio} ≤ $700)", "cumple": "alto", "fuente": "precio publicado"}]
    if mascotas is True:
        razones.append({"texto": "Acepta mascotas", "cumple": "alto", "fuente": "ficha del inmueble"})
    elif mascotas is False:
        razones.append({"texto": "No acepta mascotas", "cumple": "bajo", "fuente": "ficha del inmueble"})
    return {"id": f"c{i}", "direccion": f"Calle {i}, Quito", "precio": precio, "operacion": "ARRIENDO",
            "tipo_activo": "Departamento", "encaje": 80, "encaje_razones": razones}


PANEL = [_card(1, 600, True), _card(2, 620, True), _card(3, 640, False), _card(4, 660, None)]
PREFS = {"presupuesto_max": 700, "acepta_mascotas": True}


@pytest.mark.parametrize("texto,denuncia", [
    ("Todos aceptan mascotas.", True),
    ("Tengo 4 departamentos que aceptan mascotas.", True),
    ("Los 3 departamentos de la lista aceptan a tu perro.", True),
    ("Las dos primeras aceptan mascotas.", False),
    ("Tengo 2 opciones que aceptan mascotas.", False),
    ("No todos aceptan mascotas: revisa cada ficha.", False),
    ("Ninguno acepta mascotas.", False),
    ("Dos entran en tu tope de $700 y aceptan perro.", False),
    ("La de $600 acepta mascotas.", False),
])
def test_agregado_mascotas_bordes(texto, denuncia):
    v = _codigos(verificar_prosa(texto, PANEL, PREFS), "agregado_requisito_duro")
    assert bool(v) is denuncia, v


def test_sin_dimension_evaluada_no_hay_evidencia_y_calla():
    """Si el panel no evaluó mascotas (la persona no lo pidió), no hay verdad contra qué medir."""
    panel = [_card(1, 600, None), _card(2, 620, None)]
    assert not _codigos(verificar_prosa("Todos aceptan mascotas.", panel, {"presupuesto_max": 700}),
                        "agregado_requisito_duro")


def test_el_literal_del_motor_es_el_que_audita_el_verificador():
    """Si el motor cambia el texto de su razón, el verificador no puede quedarse contando otra cosa."""
    from app.encaje import RAZON_ACEPTA_MASCOTAS, RAZON_NO_ACEPTA_MASCOTAS, _score_acepta_mascotas
    assert _score_acepta_mascotas(True, {"acepta_mascotas": True})["texto"] == RAZON_ACEPTA_MASCOTAS
    assert _score_acepta_mascotas(True, {"acepta_mascotas": False})["texto"] == RAZON_NO_ACEPTA_MASCOTAS


# ── (b) excluida presentada como candidata: bordes ─────────────────────────────────────
MOSTRADA = {"id": "m1", "direccion": "Av. Interoceánica y Chimborazo, Cumbayá, Quito", "precio": 210000,
            "operacion": "VENTA", "tipo_activo": "Departamento", "encaje": 46, "encaje_razones": []}
VISTAS = [{"id": "m1", "direccion": MOSTRADA["direccion"], "precio": 210000, "tipo_activo": "Departamento",
           "operacion": "VENTA"},
          {"id": "x1", "direccion": "Calle Pampite E5-40, Cumbayá, Quito", "precio": 139000,
           "tipo_activo": "Casa", "operacion": "VENTA"},
          # Cuesta EXACTAMENTE el tope: la prosa que nombra el tope no le está atribuyendo precio.
          {"id": "x2", "direccion": "Vía Lumbisí 12, Cumbayá, Quito", "precio": 150000,
           "tipo_activo": "Casa", "operacion": "VENTA"}]
TOPE = {"presupuesto_max": 150000}


@pytest.mark.parametrize("texto,denuncia", [
    ("También hay una casa dentro de tu presupuesto en Pampite, a $139,000.", True),
    ("En Cumbayá hay casas dentro de tu tope.\nUna está en Calle Pampite, a $139,000.", True),
    ("En Cumbayá hay casas dentro de tu tope.\n\nOtra cosa: Pampite queda a $139,000 de nada.", False),
    ("En Cumbayá hay casas dentro de tu tope. Una está en Calle Pampite, a $139,000.", True),
    ("- ✅ Casa en Pampite: $139,000", True),
    ("Hay una casa en Pampite a $139,000, pero no es departamento.", False),
    ("La casa de Pampite, a $139,000, no entra en tu presupuesto.", False),
    ("El departamento de la Interoceánica cuesta $210,000 y se pasa de tu tope.", False),
    ("En Cumbayá también hay casas, pero no son departamentos.", False),
    ("Dentro de tu tope de $150,000 no encontré departamentos de 2 dormitorios.", False),
])
def test_excluida_bordes(texto, denuncia):
    v = _codigos(verificar_prosa(texto, [MOSTRADA], TOPE, vistas=VISTAS), "excluida_presentada")
    assert bool(v) is denuncia, v


def test_el_camino_vivo_le_pasa_al_verificador_lo_que_el_modelo_vio(monkeypatch):
    """`_auditar_prosa` (stream y no-stream) deriva `vistas` de los ToolMessages del turno. Sin
    este cableado, el chequeo (b) existiría en el módulo y no correría nunca en producción."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from app.routers import chat as chat_mod

    c = CASOS[TIPO]
    tool = ToolMessage(json.dumps({"assets": [
        {"id": a["id"], "direccion_estandarizada": a["direccion"], "precio": a["precio"],
         "tipo_activo": a["tipo_activo"], "operacion": a["operacion"]} for a in c["vistas"]]}),
        tool_call_id="t0", name="tool_find_assets_by_text")
    mensajes = [HumanMessage("Departamento de 2 dormitorios en venta en Cumbayá hasta 150000 dólares."),
                AIMessage("", tool_calls=[{"name": "tool_find_assets_by_text",
                                           "args": {"query": "Cumbayá"}, "id": "t0"}]),
                tool]
    registradas = []
    monkeypatch.setattr(chat_mod, "registrar_prosa", lambda v, *_a, **_k: registradas.extend(v))
    chat_mod._auditar_prosa("s-cableado", c["reply"], {
        "cards": c["cards"], "preferencias": c["preferencias"], "descartadas": c["descartadas"],
        "messages": mensajes})
    assert _codigos(registradas, "excluida_presentada")


def test_sin_vistas_el_chequeo_calla():
    """El eval contra el endpoint no recibe las herramientas del turno: sin universo, no hay
    exclusión que demostrar y el chequeo no inventa una."""
    texto = "También hay una casa dentro de tu presupuesto en Pampite, a $139,000."
    assert not _codigos(verificar_prosa(texto, [MOSTRADA], TOPE), "excluida_presentada")
