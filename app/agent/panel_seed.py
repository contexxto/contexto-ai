"""panel_seed — directiva de PANEL del Estratega (dashboard vivo, ver docs/SPEC_Analisis_Vivo.md).

El backend DECIDE el foco (FSM del lente, NO el LLM en texto libre): mapea la pregunta del corredor a un
foco del vocabulario CERRADO. El dashboard (AnalisisPanel) es función de esta directiva + /metricas/lift.

Puro y determinista → testeable sin LLM. NO inventa cifras: solo elige QUÉ resaltar; los números salen
SIEMPRE de resumen_lift (/metricas/lift). El vocabulario es TRANSACCIONAL (etapa/handoff/frescura/
madurez), NUNCA clase protegida → Fair Housing por construcción.

Sobre el `caption`: en Fase A es SIEMPRE None (sin riesgo — el panel ya narra el _ancla honesto de
/metricas/lift). REQUISITO al crecer: cuando un futuro fase lo genere NARRADO POR EL LLM, DEBE enrutarse
por evaluar_salida_crm (fail-close de cifra_cartera + FH, §5 de DISENO_Superpoderes_Agentes_CRM) ANTES
de emitirse. Ese cableado AÚN NO existe → hoy no se debe emitir un caption no-None desde el LLM.
"""
from __future__ import annotations

import re
import unicodedata

# Vocabulario CERRADO de focos (Fase A: los 4 de cartera; 'lead' llega en Fase C).
FOCOS = ("handoff", "embudo", "reenganche", "cohortes")


def _norm(s: str | None) -> str:
    """Minúsculas sin acentos (para matchear 'atasca'/'atascá'/'ATASCA' igual)."""
    if not s:
        return ""
    n = unicodedata.normalize("NFKD", s)
    return "".join(c for c in n if not unicodedata.combining(c)).lower()


# (foco, patrón) — ORDEN = prioridad de especificidad. El primero que matchea gana.
# reenganche/embudo/cohortes son más específicos que handoff (que también es el "default" temático),
# por eso van antes. Todo transaccional; ningún patrón alude a clase protegida.
_REGLAS: list[tuple[str, re.Pattern[str]]] = [
    ("reenganche", re.compile(r"reenganch|dormid|reactiv|recuper|retomar|volver a contactar|revivir")),
    ("embudo", re.compile(r"embudo|funnel|atasc|atora|atra[np]|estanc|cuello|se traba|se frena|frena|etapa")),
    ("cohortes", re.compile(r"cohorte|madur|en vuelo")),
    ("handoff", re.compile(r"handoff|piden? (un )?corredor|pidieron corredor|cerrando|cierres|"
                           r"conversi|north ?star|estoy cerrando")),
]


def derivar_foco(mensaje: str | None) -> str | None:
    """Foco del dashboard a partir de la pregunta del corredor, o None si no hay señal clara (→ el
    frontend CONSERVA el foco actual: 'no salta sin señal'). Acento-insensible, primera regla que matchea."""
    n = _norm(mensaje)
    for foco, rx in _REGLAS:
        if rx.search(n):
            return foco
    return None


def derivar_panel_seed(mensaje: str | None, *, modo: str) -> dict | None:
    """Directiva de panel del turno — SOLO para el Estratega (el dashboard es SU lente; el Copiloto es
    por-lead y no lo dirige). Devuelve {foco, resalta, caption} o None si no aplica / no hay señal.

    Fase A: foco ∈ {handoff, embudo, reenganche, cohortes}; resalta=None (el resalte por etapa/cohorte
    específico es Fase B, necesita el payload del funnel); caption=None (el panel ya narra el _ancla
    honesto de /metricas/lift). El campo se mantiene en el contrato para no romperlo al crecer."""
    if modo != "estratega":
        return None
    foco = derivar_foco(mensaje)
    if foco is None:
        return None
    return {"foco": foco, "resalta": None, "caption": None}
