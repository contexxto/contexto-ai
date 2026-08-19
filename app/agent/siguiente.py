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

── Lo que lo hace seguro ───────────────────────────────────────────────────────────────
1. PLANTILLAS FIJAS, nunca prosa libre. Hoy ninguna lleva slots variables: son literales.
   El test adversarial de `test_siguiente.py` prueba cada una contra `evaluar_salida_crm`,
   el mismo guardián del CRM. Si alguna vez vuelve a haber un slot, su valor debe salir del
   propio tool_json — jamás del LLM ni del cliente.
2. VERBOS, no cifras. Ninguna plantilla afirma un número ("¿a cuáles de los dormidos
   escribo?", no "¿a los 12 dormidos?") — así queda estructuralmente fuera de la clase de
   riesgo `cifra_cartera` que ese guardián vigila.
3. SIN GATE EXPLÍCITO de modo/owner: cada regla ancla a la HUELLA de un tool_json concreto.
   No hace falta preguntarle a quién le habla: el tool_json correcto solo puede aparecer si
   el modo correcto llamó a esa tool.

── Por qué NO hay una regla para el timeline de un lead (retirada el 2026-08-19) ───────
La hubo, y funcionaba: con `tool_timeline_de_lead` + `reenganche_sugerido` proponía
"Redáctame el mensaje para retomar a {nombre}". Se verificó en producción y salía bien.
Se retiró por REDUNDANTE, no por rota. En la pantalla del Copiloto, cuando ese chip
aparecía, el corredor ya tenía delante otras dos rutas al mismo sitio:
  · el recuadro "REENGANCHE SUGERIDO · APORTA VALOR", con el mensaje YA redactado y su
    botón "Usar en la respuesta" — o sea, el resultado servido, no una pregunta que lleva
    a él;
  · el chip permanente del Copiloto "Prepárame un mensaje para retomar a {nombre}".
Un tercer botón que dice lo mismo con otro verbo no añade: resta claridad en un panel
estrecho. La lección para futuras reglas: mirar la PANTALLA donde va a aparecer, no solo
la huella que deja la tool. Esta regla se diseñó desde el backend y por eso duplicaba algo
que la interfaz ya resolvía mejor.
Quedan las reglas de CARTERA, donde el chip sí aporta: aparece porque la tool ACABA de
reportar algo, frente a los chips permanentes del Estratega, que son genéricos.

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


def derivar_siguiente(tool_jsons: list[str]) -> str | None:
    """El próximo mensaje que el corredor podría enviar, listo para mandar tal cual si hace
    clic — o None si el turno no dejó ninguna apertura clara. Ver el docstring del módulo
    para qué lo hace seguro y por qué no hace falta un parámetro `modo`.

    PRECEDENCIA: "a quién le escribo" gana a "cómo configuro el registro". La segunda es un
    nudge de SETUP — importa una vez, no turno a turno — así que cede ante cualquier cosa
    accionable hoy.
    """
    dicts = _parsear(tool_jsons)

    # 1) Cartera con dormidos — accionable ahora.
    for d in dicts:
        if _es_stats_embudo(d) and (d.get("dormidos") or 0) > 0:
            return "¿A cuáles de los dormidos les escribo primero?"

    # 2) Sin registro de llegadas — nudge de SETUP, cede ante lo anterior.
    for d in dicts:
        if _es_stats_embudo(d) and (d.get("reparto") or {}).get("hay_registro") is False:
            return "¿Cómo empiezo a registrar las llegadas?"

    return None
