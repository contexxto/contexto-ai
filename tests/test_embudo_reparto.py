"""
Tests del REPARTO del embudo (app/embudo.py) — el CRM deja de contar solo sobrevivientes.

El defecto que cierran: `tool_stats_embudo` decía "tienes 12 interesados" y eran 12 **de
los que el sistema pudo atribuir**. Quien llegó a una ficha y se fue sin escribir no
estaba en ningún lado. Y esa cifra pasaba TODOS los guardrails, porque no era falsa ni
inventada: era verdadera sobre un universo truncado.

Lo que más se prueba aquí es la ventana. El registro de llegadas nació con F0, así que
para todo lo anterior no hay dato — y "0 se fueron sin escribir" sería una mentira, no un
cero. Misma regla que `encaje.score = None`.

Puros: sin DB, sin red.
"""
import pytest

from app.embudo import componer_reparto, frase_del_reparto


# ── Sin registro: se dice, no se traduce a cero ─────────────────────────────────────

def test_sin_registro_de_llegadas_no_inventa_ceros():
    r = componer_reparto(interesados=12, piden_corredor=3)
    assert r["hay_registro"] is False
    # No aparecen los escalones que no se pueden medir.
    assert "se_fueron_sin_escribir" not in r and "llegadas" not in r
    # Y lo dice con palabras, para que el modelo no tenga que inferirlo.
    assert "no hay registro" in r["_frase_obligatoria"].lower()
    # Lo que SÍ se sabe se sigue reportando.
    assert r["interesados"] == 12 and r["piden_corredor"] == 3


def test_sin_registro_nunca_afirma_que_no_entro_nadie():
    r = componer_reparto(interesados=0, piden_corredor=0)
    frase = r["_frase_obligatoria"].lower()
    assert "0 llegaron" not in frase and "nadie" not in frase


# ── Con registro: el embudo completo ────────────────────────────────────────────────

def test_el_reparto_expone_los_dos_escalones_que_faltaban():
    r = componer_reparto(llegadas=140, sesiones_que_llegaron=96, interesados=31,
                         piden_corredor=7, desde="2026-08-06")
    assert r["hay_registro"] is True
    assert r["sesiones_que_llegaron"] == 96 and r["interesados"] == 31
    assert r["se_fueron_sin_escribir"] == 65   # el número que antes no existía


def test_la_frase_obligatoria_trae_el_reparto_hecho():
    r = componer_reparto(llegadas=140, sesiones_que_llegaron=96, interesados=31,
                         piden_corredor=7, desde="2026-08-06")
    f = r["_frase_obligatoria"]
    # No se le pide al modelo que la componga: se le entrega, como el conteo de presupuesto.
    assert "96" in f and "31" in f and "7" in f
    assert "65" in f and "sin escribir" in f
    assert "2026-08-06" in f      # la ventana viaja con la cifra


def test_la_ventana_se_declara_siempre_que_exista():
    con = componer_reparto(llegadas=10, sesiones_que_llegaron=10, interesados=2,
                           desde="2026-08-06")
    sin = componer_reparto(llegadas=10, sesiones_que_llegaron=10, interesados=2)
    assert "2026-08-06" in con["_frase_obligatoria"]
    assert "desde el" not in sin["_frase_obligatoria"]


def test_nadie_se_fue_sin_escribir_es_un_cero_legitimo():
    # Distinto de "no hay registro": aquí SÍ se midió y el resultado es cero.
    r = componer_reparto(llegadas=5, sesiones_que_llegaron=5, interesados=5)
    assert r["se_fueron_sin_escribir"] == 0
    assert "sin escribir" not in r["_frase_obligatoria"]   # no se subraya un cero


# ── Las dos fuentes se cuentan distinto: no se restan a ciegas ──────────────────────

def test_si_la_resta_sale_negativa_se_omite_en_vez_de_explicarla_mal():
    # `visita` cuenta sesiones; el embudo dedupe por dispositivo. Un negativo significa
    # que la resta no aplica (p.ej. leads previos al registro de llegadas), y publicar
    # "-4 se fueron sin escribir" sería peor que no publicar nada.
    r = componer_reparto(llegadas=3, sesiones_que_llegaron=3, interesados=7)
    assert "se_fueron_sin_escribir" not in r
    assert r["hay_registro"] is True and r["interesados"] == 7


def test_la_proveniencia_avisa_que_son_dispositivos_no_personas():
    for r in (componer_reparto(interesados=4),
              componer_reparto(llegadas=9, sesiones_que_llegaron=9, interesados=4)):
        assert "DISPOSITIVOS" in r["_proveniencia"]


# ── Defensivo ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("basura", [None, "muchos", -3, True, [], {}, float("nan")])
def test_conteos_basura_no_revientan(basura):
    r = componer_reparto(llegadas=basura, sesiones_que_llegaron=basura,
                         interesados=basura, piden_corredor=basura)
    assert isinstance(r["_frase_obligatoria"], str)
    assert r["interesados"] >= 0


def test_frase_del_reparto_tolera_un_dict_incompleto():
    assert isinstance(frase_del_reparto({}), str)
    assert isinstance(frase_del_reparto({"hay_registro": True}), str)


# ── El contrato con la tool del CRM ─────────────────────────────────────────────────

def test_la_tool_del_estratega_expone_el_reparto_y_su_frase():
    """Si alguien quita el reparto de la tool, el Estratega vuelve a poder narrar el total
    solo — que es exactamente el defecto que F2 cierra."""
    import inspect

    from app.agent import crm_tools

    # @tool envuelve la función en un StructuredTool: hay que desenvolverla para leerla.
    fn = (getattr(crm_tools.tool_stats_embudo, "coroutine", None)
          or getattr(crm_tools.tool_stats_embudo, "func", None))
    assert fn is not None, "no se pudo desenvolver tool_stats_embudo"
    src = inspect.getsource(fn)
    assert '"reparto": reparto' in src
    assert '"_frase_obligatoria"' in src
    # Y el prompt del Estratega tiene que exigirla.
    from app.agent.crm_graph import SYSTEM_PROMPT_ESTRATEGA
    prompt = SYSTEM_PROMPT_ESTRATEGA.content
    assert "REPARTO NO SE OMITE" in prompt and "_frase_obligatoria" in prompt


def test_el_crm_visual_tambien_recibe_el_reparto():
    """El endpoint del CRM lo devuelve JUNTO al embudo, no en una llamada aparte: si
    hubiera que pedirlo por separado, la pantalla podría pintar el total sin él — que es
    el número-sobre-universo-truncado que F2 vino a cerrar."""
    import inspect

    from app.routers import assets

    src = inspect.getsource(assets.mine_leads)
    assert "_reparto_del_corredor" in src
    assert '"reparto": reparto' in src


def test_la_pantalla_no_traduce_sin_registro_a_un_cero():
    """El contrato visual: sin registro se dice, y el 'se fueron sin escribir' solo se
    resalta si hubo pérdida (un cero ahí es legítimo y no merece énfasis)."""
    from pathlib import Path

    crm = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "CRM.jsx"
           ).read_text(encoding="utf-8")
    assert "d.reparto.hay_registro ?" in crm
    assert "Todavía no hay registro de llegadas" in crm
    assert "d.reparto.se_fueron_sin_escribir > 0" in crm
    # Y la proveniencia: son dispositivos, no personas.
    assert "dispositivos, no personas" in crm
