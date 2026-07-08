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

# Vocabulario CERRADO de focos: 4 de cartera + 'lead' (Fase C — puente al Copiloto).
FOCOS = ("handoff", "embudo", "reenganche", "cohortes", "lead")


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


# Referencia a UN interesado (foco 'lead', Fase C): email, id corto (#xxxx), o el patrón de una pregunta
# POR-PERSONA ("cuentame de X", "y de X", "el interesado X"). Se detecta DESPUÉS de los focos de cartera
# (si la pregunta es de cartera ya matcheó antes) → 'lead' es el último recurso.
_RE_LEAD_EMAIL = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}")
_RE_LEAD_ID = re.compile(r"#\s*([a-z0-9]{3,})")
_RE_LEAD_TRIGGER = re.compile(
    r"\b(?:cuenta?me|hablame|dime|muestrame|que (?:hay|pasa|sabemos|onda) (?:de|con)|"
    r"y (?:de|con)|el (?:interesado|lead|cliente|prospecto)|sobre|acerca de)\b")
# Extrae la cola tras el PRIMER conector (re.search escanea izq→der) → CONSERVA el nombre real:
# "cuentame de juan perez de mi cartera" -> "juan perez de mi cartera" (incluye el nombre; el frontend
# lo tokeniza y descarta las palabras de agregado). El greedy anterior soltaba el nombre.
_RE_LEAD_TAIL = re.compile(r"\b(?:de|con|del|interesado|lead|cliente|prospecto)\s+(.+)$")
# Palabras de AGREGADO/cartera y conectores: si la cola es SOLO esto (ningún token parece nombre), NO es
# un lead → el derivador no lo clasifica como 'lead' (evita que 'cuéntame de la cartera' caiga a foco lead).
_STOP_LEAD = frozenset({
    "cartera", "carteras", "pipeline", "embudo", "funnel", "numeros", "metricas", "metrica", "leads",
    "interesados", "clientes", "prospectos", "todo", "todos", "toda", "todas", "nada", "nuevo", "nueva",
    "mis", "tus", "sus", "los", "las", "una", "del", "con", "que", "por", "para", "esto", "eso",
})


def _referencia_lead(n: str) -> str | None:
    """Extrae (best-effort, sobre texto YA normalizado) la referencia a UN interesado: email > #id > la
    cola de una pregunta por-persona. None si no parece per-lead. La resolución REAL la hace el frontend
    contra /mine/leads (owner-scoped): una sobre-extracción es INOFENSIVA (sin match → sin puente). El
    Estratega NUNCA recibe dato del lead → respeta la frontera FH (el detalle por-interesado es del Copiloto)."""
    m = _RE_LEAD_EMAIL.search(n)
    if m:
        return m.group(0)
    m = _RE_LEAD_ID.search(n)
    if m:
        return m.group(1)
    if _RE_LEAD_TRIGGER.search(n):
        m = _RE_LEAD_TAIL.search(n)
        ref = (m.group(1) if m else "").strip(" ?.!,;:").strip()
        # ¿la cola tiene ALGÚN token que parezca nombre (>=3, no palabra de agregado)? Si no → no es un lead
        # ("cuéntame de la cartera" / "del pipeline" → None, conserva el foco actual del dashboard).
        if not any(len(t) >= 3 and t not in _STOP_LEAD for t in ref.split()):
            return None
        return ref[:60] or None
    return None


def derivar_foco(mensaje: str | None) -> str | None:
    """Foco del dashboard a partir de la pregunta del corredor, o None si no hay señal clara (→ el
    frontend CONSERVA el foco actual: 'no salta sin señal'). Acento-insensible, primera regla que matchea.
    Los focos de CARTERA tienen prioridad; 'lead' (per-interesado → puente al Copiloto) es el último recurso."""
    n = _norm(mensaje)
    for foco, rx in _REGLAS:
        if rx.search(n):
            return foco
    if _referencia_lead(n):
        return "lead"
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
    # foco 'lead' → resalta lleva la REFERENCIA cruda (best-effort) para que el frontend la resuelva contra
    # /mine/leads y ofrezca el PUENTE al Copiloto. Los demás focos: resalta=None (el resalte fino se deriva
    # en el panel, Fase B). caption sigue None (ver docstring del módulo).
    resalta = _referencia_lead(_norm(mensaje)) if foco == "lead" else None
    return {"foco": foco, "resalta": resalta, "caption": None}
