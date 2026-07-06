"""
Motor de Intención de Contexto — lógica pura (sin I/O, testeable offline).

Clasifica DÓNDE está el deseo de una persona dentro de su recorrido inmobiliario
(de "anónimo" a "intención de transacción") a partir de señales observables en la
conversación: qué preguntó, qué herramientas usó el agente, cuántas veces volvió.

Principios (ver docs/MOTOR_Intencion_Contexto):
  - La etapa es un ESTADO de intención, no una casilla.
  - El score es EXPLICABLE: siempre se puede decir POR QUÉ (honestidad de marca).
  - El humano (corredor) entra en el PICO de intención (handoff), no antes.

Es la "lógica única" del patrón API-first (como app/inversion.py): la consumen el
agente, el panel del corredor y la API B2B. Determinista → sin costo de LLM.
"""
from __future__ import annotations

import re
import unicodedata

# ── Estados del embudo (en orden del recorrido) ─────────────────────────────
ESTADOS = [
    "anonimo", "identificado", "explorando", "enganchado",
    "intencion", "confirmado", "completado", "returning", "dormido",
]

# Un lead que estuvo enganchado y no interactúa hace >= estas horas está "dormido"
# (candidato a reenganche por VALOR). Umbral compartido con app/reenganche.py.
# Placeholder a calibrar con el piloto.
HORAS_DORMIDO = 48

_ACCION = {
    "anonimo": "Saludar y hacer UNA pregunta calificadora (¿qué zona o qué buscas?).",
    "identificado": "Ofrecer 1–3 caminos en cápsula; dejar que el usuario tire del hilo.",
    "explorando": "Curaduría de 1–3 opciones con el porqué de cada una.",
    "enganchado": "Profundizar en el inmueble/zona; resaltar el dato verificado.",
    "intencion": "Ofrecer agendar una visita o conectar con el corredor.",
    "intencion_handoff": "HANDOFF: notificar al corredor con el resumen de intención.",
    "dormido": "Reenganche por VALOR: ofrecer el dato verificado que preguntó, sin presionar.",
}

_EMOJI = {"frio": "🔵", "tibio": "🟡", "caliente": "🔥"}
_NIVEL_LABEL = {"frio": "Frío", "tibio": "Tibio", "caliente": "Intención alta"}


def _norm(texto: str) -> str:
    """minúsculas + sin acentos → matching robusto en español."""
    t = unicodedata.normalize("NFD", texto or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t.lower()


# Señales (regex sobre el texto normalizado del usuario) → (peso, razón).
_SENALES = {
    "precio":    (re.compile(r"\bprecio|cuanto (cuesta|vale|sale)|\bvalor\b|negociab|cu[aá]nto es"), 18, "Preguntó el precio"),
    "visita":    (re.compile(r"\bvisit|\bagendar|disponib|conocerlo|\bver (el|la|ese|este|los)|cuando (puedo|podemos)|ir a ver"), 28, "Quiere visitar/ver el inmueble"),
    "ficha":     (re.compile(r"\bficha|t[eé]cnic|tuber|construcc|estructura|cableado|impermeab|mantenimiento|estado del"), 18, "Pidió la ficha técnica"),
    "inversion": (re.compile(r"rentabilidad|\byield\b|inversi|invertir|me deja|retorno|plusval|cap rate|\broi\b|cu[aá]nto produce"), 20, "Evalúa la inversión"),
    "contacto":  (re.compile(r"contacto|corredor|due[nñ]o|agente|llamar|tel[eé]fono|n[uú]mero|hablar con|whatsapp"), 32, "Pidió contacto humano"),
    "comparar":  (re.compile(r"comparar|versus|\bvs\b|cu[aá]l (es )?(mejor|conviene)|diferencia|otra opci|otras opciones"), 12, "Compara opciones"),
    "zona":      (re.compile(r"como es vivir|caminab|\bruido\b|segur|servicios|barrio|vecind|transporte|\bmetro\b|colegio|parque|vida de barrio"), 8, "Explora la zona"),
    # Fair Housing: la composición del hogar (familia/hijos/esposa/mascota) es CLASE
    # PROTEGIDA (familial status) y NO debe puntuar ni segmentar. Solo cuenta la
    # necesidad transaccional DECLARADA por el usuario (uso/presupuesto/mudanza).
    # Ver docs/COMPLIANCE_FairHousing_AgentSpec_2026-06-23.md.
    "perfil":    (re.compile(r"para vivir|presupuesto|me mudo|mudarme"), 8, "Declaró su necesidad (uso/presupuesto)"),
}


def analizar_intencion(
    *,
    mensajes_usuario: list[str],
    herramientas_usadas: int = 0,
    turnos: int | None = None,
    es_qr: bool = False,
    uso_tool_inversion: bool = False,
    pidio_corredor: bool = False,
    horas_inactividad: float | None = None,
) -> dict:
    """
    Analiza la intención de una sesión a partir de señales observables.

    Args:
        mensajes_usuario: textos enviados por el usuario (sin el [Contexto del sistema]).
        herramientas_usadas: nº de tool calls del agente en la sesión.
        turnos: nº de turnos del usuario (si None, se infiere de mensajes_usuario).
        es_qr: True si la sesión nació de escanear el QR de un inmueble.
        uso_tool_inversion: True si el agente corrió el análisis de inversión.
        horas_inactividad: horas desde la última interacción del lead. Si supera
            HORAS_DORMIDO y el lead ya se había enganchado (y no está caliente), el
            estado se marca 'dormido' — candidato a reenganche por valor. None = se
            ignora la dimensión temporal (comportamiento por defecto, retrocompatible).

    Returns:
        dict con: estado, nivel, score (0–100), razones, senales, handoff_sugerido,
        accion_sugerida, resumen.
    """
    msgs = [m for m in (mensajes_usuario or []) if isinstance(m, str) and m.strip()]
    if turnos is None:
        turnos = len(msgs)
    blob = _norm(" \n ".join(msgs))

    score = 0
    razones: list[str] = []
    detectadas: dict[str, bool] = {}

    if es_qr:
        score += 10
        razones.append("Llegó por el QR de un inmueble")
        detectadas["qr"] = True

    for clave, (rx, peso, razon) in _SENALES.items():
        if rx.search(blob):
            detectadas[clave] = True
            score += peso
            razones.append(razon)

    # Amplitud de exploración = nº de MENSAJES distintos que tocan la zona
    # (no palabras sueltas en un mismo mensaje). Distingue "explora varias"
    # (explorando) de "profundiza en una" (enganchado).
    _rx_zona = _SENALES["zona"][0]
    n_msgs_zona = sum(1 for m in msgs if _rx_zona.search(_norm(m)))

    # La inversión también se detecta por el uso de la herramienta (señal fuerte y limpia).
    if uso_tool_inversion and not detectadas.get("inversion"):
        detectadas["inversion"] = True
        score += 20
        razones.append("Corrió el análisis de inversión")

    # Pedir hablar con el corredor es el PICO de intención (in-platform handoff).
    if pidio_corredor:
        detectadas["corredor"] = True
        score += 35
        razones.insert(0, "Pidió hablar con el corredor")

    # Herramientas usadas (profundidad de exploración): aporta poco, con tope.
    if herramientas_usadas:
        score += min(herramientas_usadas * 4, 12)

    # Profundidad de conversación (engagement): +2 por turno extra, tope 10.
    if turnos and turnos > 1:
        score += min((turnos - 1) * 2, 10)

    # Amplitud de exploración: tocar la zona en 2+ mensajes distintos es búsqueda
    # activa (recorrer/comparar varias zonas), no una línea de curiosidad. Un
    # explorador real es un lead tibio, no frío → la amplitud suma al score.
    if n_msgs_zona >= 2:
        score += min((n_msgs_zona - 1) * 10, 20)
        razones.append("Explora la zona en varios mensajes")

    score = max(0, min(score, 100))

    # ── Derivar el ESTADO (precedencia de mayor a menor intención) ──────────
    transaccion = any(detectadas.get(k) for k in ("contacto", "visita", "precio", "ficha", "inversion", "corredor"))
    handoff = bool(detectadas.get("contacto") or detectadas.get("visita") or detectadas.get("corredor")) or score >= 70

    if transaccion:
        estado = "intencion"
    elif detectadas.get("zona") or detectadas.get("perfil"):
        # ¿explora varias (explorando) o profundiza en una (enganchado)?
        estado = "explorando" if (detectadas.get("comparar") or n_msgs_zona >= 2) else "enganchado"
    elif msgs:
        estado = "identificado"
    else:
        estado = "anonimo"

    # ── Nivel (frío/tibio/caliente) ─────────────────────────────────────────
    if handoff or score >= 65:
        nivel = "caliente"
    elif score >= 30:
        nivel = "tibio"
    else:
        nivel = "frio"

    # ── Frescura: un lead que se enganchó y no vuelve hace rato está 'dormido' ─
    # (candidato a reenganche por VALOR, no por tiempo — ver app/reenganche.py).
    # Solo si NO está caliente (a esos ya los tiene el corredor) y llegó a mostrar
    # exploración/intención real. Placeholder del embudo que aquí cobra vida.
    if (
        horas_inactividad is not None
        and horas_inactividad >= HORAS_DORMIDO
        and nivel != "caliente"
        and estado in ("explorando", "enganchado", "intencion")
    ):
        estado = "dormido"
        razones.append("Se enfrió: sin interactuar hace tiempo")

    accion = _ACCION["intencion_handoff"] if (estado == "intencion" and handoff) \
        else _ACCION.get(estado, _ACCION["anonimo"])

    if not razones:
        razones = ["Recién llega — sin señales aún"]

    resumen = f"{_EMOJI[nivel]} {_NIVEL_LABEL[nivel]} — " + ", ".join(razones[:3]).lower()

    return {
        "estado": estado,
        "nivel": nivel,
        "score": score,
        "razones": razones,
        "senales": detectadas,
        "handoff_sugerido": handoff,
        "accion_sugerida": accion,
        "resumen": resumen,
        "turnos": turnos,
    }
