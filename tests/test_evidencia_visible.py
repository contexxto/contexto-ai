"""
La EVIDENCIA del encaje, visible — que el porcentaje nunca viaje solo cuando se calculó
con datos parciales.

El motor promedia únicamente las necesidades CON señal ("no castigamos lo que no
sabemos", app/encaje.py). El efecto colateral es que un inmueble con ficha incompleta
puede puntuar MÁS alto que uno bien documentado. El orden ya lo corrige (app/orden.py,
por peso); esto cubre la otra mitad: que la persona lo VEA y que el modelo no pueda
afirmar lo que no se midió.

Dos superficies, un solo origen (el resultado de calcular_encaje) para que no diverjan:
  · la tarjeta → conteos (`encaje_evaluadas` / `encaje_declaradas`), que es como cuentan
    las personas;
  · el bloque autoritativo → la misma frase, para que la prosa la copie.
"""
import asyncio
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.encaje_contexto import bloque_autoritativo
from app.routers import chat


# ── El bloque que lee el modelo ─────────────────────────────────────────────────────

def _card(cid="a", encaje=82, ev=3, decl=6, **over):
    c = {"id": cid, "direccion": f"Dir {cid}", "precio": 700, "operacion": "arriendo",
         "encaje": encaje, "encaje_evaluadas": ev, "encaje_declaradas": decl,
         "encaje_razones": [], "duros_incumplidos": []}
    c.update(over)
    return c


def test_el_modelo_ve_sobre_cuanto_se_midio():
    txt = bloque_autoritativo([_card(ev=3, decl=6)], {"presupuesto_max": 800})
    assert "MEDIDO SOBRE 3 DE 6" in txt
    # Le damos la frase hecha, como con el conteo de presupuesto: no se la pedimos.
    assert "calculado sobre 3 de las 6 cosas que pediste" in txt
    assert "PROHIBIDO" in txt and "encaja perfecto" in txt


def test_medicion_completa_no_ensucia_el_bloque():
    # Si se midió todo, el número no necesita asterisco: la línea se calla.
    txt = bloque_autoritativo([_card(ev=6, decl=6)], {"presupuesto_max": 800})
    assert "MEDIDO SOBRE" not in txt


@pytest.mark.parametrize("ev,decl", [
    (None, 6), (3, None), (3, 0), (6, 6), (7, 6), ("3", 6), (True, 6),
])
def test_conteos_ausentes_o_raros_no_rompen_el_bloque(ev, decl):
    # Una tarjeta de historial viejo (sin los campos) o un dato raro NO debe ensuciar el
    # prompt ni tumbar el turno: simplemente no se declara la evidencia.
    txt = bloque_autoritativo([_card(ev=ev, decl=decl)], {"presupuesto_max": 800})
    assert "MEDIDO SOBRE" not in txt
    assert "82% de encaje" in txt  # el resto del bloque sigue intacto


def test_la_evidencia_convive_con_el_veredicto_de_presupuesto():
    # Las dos advertencias van en la misma línea sin pisarse (son fallos distintos).
    txt = bloque_autoritativo([_card(precio=900, ev=2, decl=5)], {"presupuesto_max": 800})
    assert "MEDIDO SOBRE 2 DE 5" in txt
    assert "SOBRE TU TOPE" in txt.upper()


# ── Los conteos que la tarjeta recibe ───────────────────────────────────────────────

def _row(rid, **over):
    row = {
        "id": rid, "direccion": f"Dir {rid}", "tipo_activo": "Departamento",
        "operacion": "arriendo", "precio": 700, "imagen_url": None,
        "caminabilidad": None, "ruido": None, "vegetacion": None,
        "lat": -0.18, "lon": -78.48, "caracteristicas": {"num_dormitorios": 2},
        "servicios_cercanos": None, "conectividad": None,
    }
    row.update(over)
    return row


def _panel(monkeypatch, rows, prefs):
    async def fake_fetch(_ids):
        return (rows, {})

    async def fake_prefs(_textos):
        return prefs

    monkeypatch.setattr(chat, "_fetch_cards_rows", fake_fetch)
    monkeypatch.setattr(chat, "extraer_preferencias", fake_prefs)
    messages = [
        HumanMessage(content="Busco algo así"),
        ToolMessage(content=json.dumps({"assets": [{"id": r["id"]} for r in rows]}),
                    name="tool_find_assets_by_text", tool_call_id="t1"),
        AIMessage(content="Encontré estas opciones."),
    ]
    return asyncio.run(chat.build_result_cards(messages))


def test_la_tarjeta_lleva_los_conteos(monkeypatch):
    prefs = {"tipo_inmueble": "departamento", "presupuesto_max": 800,
             "tranquilidad": True, "caminable": True}
    cards = _panel(monkeypatch, [_row("parcial")], prefs)

    c = cards[0]
    # 4 necesidades declaradas; solo tipo y presupuesto tienen señal en esta ficha.
    assert c["encaje_declaradas"] == 4
    assert c["encaje_evaluadas"] == 2
    # Y la cobertura por PESO viaja aparte, para el orden (presupuesto pesa 1.5).
    assert c["encaje_cobertura"] == pytest.approx(2.5 / 4.5)


def test_sin_preferencias_no_hay_conteos_que_mostrar(monkeypatch):
    cards = _panel(monkeypatch, [_row("A")], {})
    assert cards[0]["encaje"] is None
    assert cards[0]["encaje_evaluadas"] is None
    assert cards[0]["encaje_declaradas"] is None


def test_los_conteos_de_la_tarjeta_y_del_bloque_son_el_mismo_dato(monkeypatch):
    """La garantía que importa: pantalla y prosa salen del MISMO cálculo, así que no
    pueden contar historias distintas (la razón de ser de encaje_contexto.py)."""
    prefs = {"tipo_inmueble": "departamento", "presupuesto_max": 800,
             "tranquilidad": True, "caminable": True, "area_verde": True}
    cards = _panel(monkeypatch, [_row("parcial")], prefs)
    txt = bloque_autoritativo(cards, prefs)

    ev, decl = cards[0]["encaje_evaluadas"], cards[0]["encaje_declaradas"]
    assert ev < decl
    assert f"MEDIDO SOBRE {ev} DE {decl}" in txt
    assert f"calculado sobre {ev} de las {decl} cosas que pediste" in txt
