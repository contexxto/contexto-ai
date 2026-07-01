"""
Captura de PREFERENCIAS declaradas del usuario — el INPUT del motor de encaje (app/encaje.py).

LLM → schema FIJO y CERRADO. Lee lo que el usuario dijo en la conversación y extrae SOLO las
necesidades que declaró explícitamente, en las 7 dimensiones de encaje.DIMENSIONES.

── Fair Housing (innegociable, tarea #14) ──────────────────────────────────────────────
Tres barreras, en capas:
  1. El TOOL SCHEMA solo tiene las 7 dimensiones-necesidad → el LLM no puede emitir un
     campo "familia/hijos/origen/…" porque no existe en el schema.
  2. El PROMPT prohíbe inferir preferencias a partir de QUIÉN es la persona ("tengo hijos"
     NO se traduce a área verde ni a más dormitorios).
  3. El SANITIZADOR (`_sanitizar`) descarta cualquier clave fuera de encaje.DIMENSIONES y
     cualquier tipo inválido → aunque el LLM alucine, nada ajeno llega al motor.

Degrada a {} ante CUALQUIER fallo (sin API key, timeout, JSON malo): el chat nunca se rompe;
simplemente no hay encaje ese turno (mejor sin dato que un dato inventado o un 500).
"""
from __future__ import annotations

import logging
import math

import anthropic
import httpx

from app.config import settings
from app.encaje import DIMENSIONES

logger = logging.getLogger(__name__)

_BOOL_DIMS = {"tranquilidad", "caminable", "transporte", "area_verde", "acepta_mascotas"}
_NUM_DIMS = {"presupuesto_max", "min_dormitorios"}

_SYSTEM = (
    "Eres un extractor de PREFERENCIAS declaradas para una búsqueda inmobiliaria. Lee lo que "
    "el usuario dijo y registra SOLO las necesidades sobre el inmueble o su entorno que expresó "
    "EXPLÍCITAMENTE. Reglas innegociables:\n"
    "1. Registra una dimensión SOLO si el usuario la pidió. Si no la mencionó, déjala fuera.\n"
    "2. NUNCA infieras una preferencia a partir de QUIÉN es la persona. Si menciona familia, "
    "hijos, edad, nacionalidad, origen, religión, género, discapacidad, etc., IGNÓRALO por "
    "completo: no lo traduzcas a ninguna preferencia (ej.: 'tengo hijos' NO implica área verde, "
    "ni más dormitorios, ni tranquilidad; 'me mudo con mi pareja' NO implica nada).\n"
    "3. presupuesto_max: el número que dijo como tope (misma moneda). min_dormitorios: entero.\n"
    "Llama SIEMPRE a la herramienta registrar_preferencias."
)

_TOOL = {
    "name": "registrar_preferencias",
    "description": "Registra las necesidades DECLARADAS por el usuario (solo las que pidió).",
    "input_schema": {
        "type": "object",
        "properties": {
            "tranquilidad": {"type": "boolean", "description": "pidió tranquilidad / poco ruido"},
            "caminable": {"type": "boolean", "description": "pidió poder resolver a pie / caminable"},
            "transporte": {"type": "boolean", "description": "pidió estar cerca de transporte masivo (Metro/parada)"},
            "area_verde": {"type": "boolean", "description": "pidió áreas verdes / parque cerca"},
            "presupuesto_max": {"type": "number", "description": "tope de precio que declaró (solo si lo dijo)"},
            "min_dormitorios": {"type": "integer", "description": "mínimo de dormitorios que pidió (solo si lo dijo)"},
            "acepta_mascotas": {"type": "boolean", "description": "necesita que acepten mascotas"},
        },
    },
}


def _sanitizar(bruto) -> dict:
    """Blinda la salida del LLM: solo claves de la whitelist CERRADA y tipos válidos. Es la
    última barrera Fair Housing — aunque el LLM alucine un campo ajeno, aquí se descarta."""
    if not isinstance(bruto, dict):
        return {}
    out: dict = {}
    for k, v in bruto.items():
        if k not in DIMENSIONES:            # whitelist cerrada: nada ajeno pasa
            continue
        if k in _BOOL_DIMS:
            if v is True:                   # solo registramos la necesidad AFIRMADA
                out[k] = True
        elif k in _NUM_DIMS:
            if isinstance(v, bool):         # True==1 no es un número que el usuario declaró
                continue
            try:
                n = float(v.strip() if isinstance(v, str) else v)
            except (TypeError, ValueError):
                continue
            if math.isfinite(n) and n > 0:  # descarta NaN, ±inf y no-positivos
                out[k] = int(n) if k == "min_dormitorios" else n
    return out


_client_singleton: anthropic.AsyncAnthropic | None = None


def _client() -> anthropic.AsyncAnthropic:
    """Cliente Anthropic reutilizado entre turnos (singleton perezoso). Crear uno por turno
    fugaría un httpx.AsyncClient (pool de sockets) en el camino caliente del chat; se
    construye una vez, dentro del loop del primer uso real, con el control de SSL local."""
    global _client_singleton
    if _client_singleton is None:
        verify = settings.ssl_verify.lower() != "false"
        _client_singleton = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            http_client=httpx.AsyncClient(verify=verify, timeout=20.0),
        )
    return _client_singleton


async def extraer_preferencias(mensajes_usuario: list[str]) -> dict:
    """Extrae las preferencias declaradas de los mensajes del usuario → dict de la whitelist.

    Degradable: sin API key / sin mensajes / error del LLM / JSON malo → {} (no encaje, sin
    romper). El resultado alimenta app.encaje.calcular_encaje, que solo lee estas dimensiones.
    """
    if not settings.anthropic_api_key:
        return {}
    textos = [t.strip() for t in (mensajes_usuario or []) if isinstance(t, str) and t.strip()]
    if not textos:
        return {}
    conversacion = "\n".join(f"- {t}" for t in textos[-12:])  # acota tokens a los últimos turnos
    try:
        resp = await _client().messages.create(
            model=settings.llm_model,
            max_tokens=400,
            system=_SYSTEM,
            tools=[_TOOL],
            tool_choice={"type": "tool", "name": "registrar_preferencias"},
            messages=[{"role": "user", "content": f"Mensajes del usuario:\n{conversacion}"}],
        )
        for block in resp.content:
            if getattr(block, "type", "") == "tool_use" and getattr(block, "name", "") == "registrar_preferencias":
                return _sanitizar(block.input)
    except Exception as e:  # noqa: BLE001 — el encaje es un extra; jamás debe romper el chat
        logger.warning("extraer_preferencias degradó a {} (%s: %s)", type(e).__name__, e)
    return {}
