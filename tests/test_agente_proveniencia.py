"""Regresión del prompt + tools del agente: la PROVENIENCIA del entorno (fuente + frescura +
quién-verificó) debe narrarse en el chat con la MISMA verdad que muestra la ficha /a/{id}.

Cierra el lazo de honestidad de Mejora A/B: el foso es visible en anuncio, tarjeta y mapa;
ahora el agente lo dice con las mismas palabras. Dos invariantes:

1. El prompt tiene la regla paraguas de proveniencia y ya NO hardcodea "comercios reales"
   para toda caminabilidad — key off de walk_score_fuente ('osm' vs 'heuristico'), el mismo
   dato que la UI. Sin esto el agente sobre-reclamaría OSM para un score heurístico (el bug
   exacto que Mejora B eliminó de la pantalla, aquí en la voz del agente).
2. Las tools SÍ le entregan walk_score_fuente — una regla que le pida narrar una proveniencia
   que no ve sería una invitación a alucinar.

Guardrails toscos (leen el código como TEXTO, sin instanciar langgraph/LLM que necesitan red).
"""
from pathlib import Path

_APP = Path(__file__).resolve().parent.parent / "app" / "agent"
_GRAPH = _APP / "graph.py"
_TOOLS = _APP / "tools.py"


def _texto(p: Path) -> str:
    # Colapsa saltos + sangría a un espacio: frases partidas por el ajuste de línea se buscan
    # como texto contiguo. Robusto a reformateos.
    return " ".join(p.read_text(encoding="utf-8").split())


def test_regla_paraguas_de_proveniencia_presente():
    t = _texto(_GRAPH)
    assert "PROVENIENCIA (regla paraguas" in t


def test_paraguas_nombra_las_tres_senales():
    # Fuente del dato + frescura del mapa + confirmación del corredor: las tres, o no es paraguas.
    t = _texto(_GRAPH)
    assert "la FUENTE del dato" in t
    assert "la FRESCURA" in t
    assert "el CORREDOR" in t
    assert "(confirmado por el corredor)" in t  # la señal más fresca, nombrada explícitamente


def test_caminabilidad_no_sobre_reclama_osm_para_score_heuristico():
    # El corazón del fix: la caminabilidad se rotula por su procedencia real, no siempre "OSM".
    t = _texto(_GRAPH)
    assert "estimación por zona" in t  # la rama heurística existe y se nombra
    assert 'JAMÁS afirmes "comercios reales' in t  # la prohibición de sobre-reclamar
    # NINGÚN ejemplo del prompt (incluido el "Formato exacto" del encaje, que el agente COPIA
    # literal) debe afirmar "comercios reales de la cuadra/zona" de forma INCONDICIONAL: ese era el
    # bug residual que la revisión adversaria cazó (graph.py:152 hardcodeaba OSM para todo score).
    assert "comercios reales de la cuadra" not in t


def test_no_filtra_las_etiquetas_internas_de_fuente_al_usuario():
    # Guard anti-jerga: 'osm'/'heuristico' son valores crudos de BD; el prompt debe prohibir
    # explícitamente escribirlos al usuario y exigir la traducción a español.
    t = _texto(_GRAPH)
    assert "ETIQUETAS INTERNAS" in t


def test_tool_analyze_location_tambien_expone_procedencia():
    # La 4ª ruta que sirve caminabilidad (motor en vivo) también trae su fuente, para que el
    # agente aplique la MISMA regla de proveniencia y no quede una superficie incoherente.
    assert "caminabilidad_fuente" in _TOOLS.read_text(encoding="utf-8")


def test_coherencia_declarada_con_la_ficha_del_inmueble():
    # La regla ancla la voz del agente a la pantalla: misma verdad, no una versión optimista.
    t = _texto(_GRAPH)
    assert "no puede decir una cosa en la pantalla" in t


def test_tools_entregan_walk_score_fuente_al_agente():
    # Sin este dato en las tools, la regla pediría narrar algo que el agente no ve → alucinaría.
    # Las tres SELECT del agente (search por radio, búsqueda por texto, specs por id) lo traen.
    t = _TOOLS.read_text(encoding="utf-8")
    assert t.count("a.walk_score_fuente") >= 3
