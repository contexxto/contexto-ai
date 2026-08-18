"""
`derivar_siguiente` — el próximo paso que el CRM Vivo sugiere tras un turno, en el MISMO
espíritu que `panel_seed.py` (puro, determinista, testeable sin LLM, cero llamadas) pero
mirando el lado de SALIDA: no la pregunta del corredor, sino lo que las tools YA trajeron
en este turno.

── Por qué existe ──────────────────────────────────────────────────────────────────────
El comprador (`graph.py`, regla 3) cierra CADA turno con un gancho — "1-3 opciones para
seguir" — y ese patrón resultó ser un vector de riesgo real (ver `verificacion_prosa._gancho`).
El corredor no tenía el equivalente: el Estratega y el Copiloto esperan a que pregunten más
("Luego, si te preguntan más, profundizas"). Esto le da al corredor la misma continuidad, pero
construida DESDE CERO como dato estructurado — nunca como prosa libre que un LLM podría
inflar, prometer de más, o segmentar por clase protegida.

── Las tres reglas que lo hacen seguro ─────────────────────────────────────────────────
1. PLANTILLAS FIJAS, nunca prosa libre. El único slot variable ({nombre}) sale del propio
   JSON de `tool_timeline_de_lead` — la MISMA tool que ya lo calculó — nunca del LLM ni del
   cliente. El test adversarial de `test_siguiente.py` prueba cada plantilla contra
   `evaluar_salida_crm`, el mismo guardián del CRM.
2. VERBOS, no cifras. Ninguna plantilla afirma un número ("¿a cuáles de los dormidos
   escribo?", no "¿a los 12 dormidos?") — así queda estructuralmente fuera de la clase de
   riesgo `cifra_cartera` que ese guardián vigila.
3. SIN GATE EXPLÍCITO de modo/owner: cada regla ancla a la HUELLA de un tool_json concreto,
   y el Estratega ni siquiera tiene `tool_timeline_de_lead` en su lista de tools
   (`ESTRATEGA_TOOLS`) — la regla del timeline es hermética por construcción, igual que el
   scope de owner en `crm_tools.py`. No hace falta preguntarle a quién le habla: el tool_json
   correcto solo puede aparecer si el modo correcto lo llamó.

── Por qué SOLO el turno actual (`tool_jsons_del_turno`, no `..._de_conversacion`) ─────
El Estratega suele traer la cartera UNA vez al abrir (kickoff) y luego referenciar esos
números sin re-llamar la tool (`crm_guardrails.tool_jsons_de_conversacion`, mismo motivo).
Si `derivar_siguiente` mirara TODO el hilo, la sugerencia de "dormidos" quedaría pegada para
siempre después del kickoff, aunque el corredor ya la haya resuelto. Mirando solo el turno
actual, la sugerencia aparece cuando la tool ACABA de reportar algo — y calla en los turnos
de seguimiento que no volvieron a consultarla.
"""
from __future__ import annotations

import json


def _parsear(tool_jsons: list[str]) -> list[dict]:
    """Los tool_jsons del turno, ya cargados como dict — ignora silenciosamente lo que no
    parsea o no es un objeto (defensivo: un tool_json roto no puede tumbar la sugerencia)."""
    out: list[dict] = []
    for j in tool_jsons or []:
        try:
            d = json.loads(j)
        except (TypeError, ValueError):
            continue
        if isinstance(d, dict):
            out.append(d)
    return out


def _es_stats_embudo(d: dict) -> bool:
    """Huella de `tool_stats_embudo`: única tool del CRM que trae AMBAS claves juntas."""
    return "total_interesados" in d and "reparto" in d


def _es_timeline(d: dict) -> bool:
    """Huella de `tool_timeline_de_lead`: única tool del CRM que trae AMBAS claves juntas."""
    return "lead" in d and "transcript" in d


def derivar_siguiente(tool_jsons: list[str]) -> str | None:
    """El próximo mensaje que el corredor podría enviar, listo para mandar tal cual si hace
    clic — o None si el turno no dejó ninguna apertura clara. Ver el docstring del módulo
    para las tres reglas que lo hacen seguro y por qué no hace falta un parámetro `modo`.

    PRECEDENCIA, de más a menos específico: un interesado NOMBRADO con reenganche listo es
    más accionable que una cifra de cartera; y "no hay registro" es un nudge de SETUP (menos
    urgente turno a turno que "a quién le escribo") — por eso va último.
    """
    dicts = _parsear(tool_jsons)

    # 1) Un interesado NOMBRADO con reenganche ya redactado por el motor — lo más específico.
    for d in dicts:
        if _es_timeline(d) and d.get("reenganche_sugerido"):
            nombre = (d.get("lead") or "").strip()
            if nombre:
                return f"Redáctame el mensaje para retomar a {nombre}"

    # 2) Cartera con dormidos — accionable, sin nombrar a nadie todavía.
    for d in dicts:
        if _es_stats_embudo(d) and (d.get("dormidos") or 0) > 0:
            return "¿A cuáles de los dormidos les escribo primero?"

    # 3) Sin registro de llegadas — nudge de SETUP, el menos urgente de los tres.
    for d in dicts:
        if _es_stats_embudo(d) and (d.get("reparto") or {}).get("hay_registro") is False:
            return "¿Cómo empiezo a registrar las llegadas?"

    return None
