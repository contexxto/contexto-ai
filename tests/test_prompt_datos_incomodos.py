"""
Regresión del prompt del agente (app/agent/graph.py): la regla 5b "PRESENTACIÓN DE DATOS
INCÓMODOS" (la "versión C") debe seguir presente y con su núcleo anti-shading intacto.

Nace del feedback en vivo (2026-07-03): con el deal de vender proyectos de desarrolladores
sobre la mesa, apareció la tentación de OCULTAR datos de entorno desfavorables (ruido) para
no "ahuyentar la venta". Eso rompería el foso de honestidad (P4) — el agente dejaría de ser
testigo neutral. La regla lo prohíbe: el entorno no se edita a conveniencia de quien paga.

Este guardrail es deliberadamente tosco — lee el prompt como TEXTO (sin importar langgraph
ni instanciar el LLM, que necesitarían red/claves) — para que la regla no se borre por
accidente en un refactor del prompt.
"""
from pathlib import Path

_GRAPH = Path(__file__).resolve().parent.parent / "app" / "agent" / "graph.py"


def _prompt_texto() -> str:
    # Normaliza los espacios (colapsa saltos de línea + sangría a un solo espacio) para que
    # las frases que en el código quedan partidas por el ajuste de línea se puedan buscar
    # como texto contiguo. Guardrail robusto a reformateos del prompt.
    return " ".join(_GRAPH.read_text(encoding="utf-8").split())


def test_regla_datos_incomodos_presente():
    assert "PRESENTACIÓN DE DATOS INCÓMODOS" in _prompt_texto()


def test_prohibe_editar_el_entorno_a_conveniencia_de_quien_paga():
    # El corazón del anti-shading, y su extensión clave: ni siquiera para el desarrollador
    # que promociona su proyecto (el escenario que disparó esta regla).
    t = _prompt_texto()
    assert "no se edita a conveniencia" in t
    assert "desarrollador" in t


def test_prohibe_los_dos_extremos_esconder_y_alarmista():
    # La versión C vive en el medio: ni folleto que esconde (A), ni alarma que asusta (B).
    t = _prompt_texto()
    assert "ESCONDER" in t
    assert "ALARMISTA" in t


def test_conserva_el_argumento_de_negocio_no_solo_el_dogma():
    # No debe degradarse a un "sé honesto" vago: conserva la razón de negocio (decir lo
    # desfavorable con rigor es lo que hace CREÍBLE lo favorable), que es lo que lo sostiene
    # frente a la presión comercial del deal con desarrolladores.
    t = _prompt_texto()
    assert "mecanismo de confianza" in t
    assert "estimación, no" in t  # el ejemplo ✅ usa ruido categórico con proveniencia, no dB inventados
