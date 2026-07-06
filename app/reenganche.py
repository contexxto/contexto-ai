"""
Motor de Reenganche de Contexto — lógica pura (sin I/O, testeable offline).

Decide SI y CÓMO volver a contactar a un interesado que se enfrió, con una regla
que rompe con las plataformas transaccionales: se reengancha APORTANDO VALOR
(el dato verificado que respondía a lo que la persona preguntó), nunca empujando
la transacción ("¿sigues interesado?"). El silencio es la opción por defecto:
sin algo verificado que ofrecer, no se escribe.

Complementa app/intencion.py (que dice DÓNDE está el deseo) con dos dimensiones:
  • TIEMPO  — hace cuánto no interactúa (frescura).
  • VALOR   — qué dato verificado le importa (el ángulo del reenganche).

Principios (ver docs/DISENO_Agente_Reenganche.md):
  - Disparo por VALOR, no por tiempo: se reengancha con dato verificado que calza,
    no por un reloj de intensidad.
  - Honestidad: se lidera con lo verificado, sin inventar ni presionar.
  - Fair Housing: el ángulo NUNCA usa señales de clase protegida (familia/edad/…);
    solo la necesidad transaccional que la persona DECLARÓ (precio/zona/ficha/…).
  - El humano cierra: en Fase 1 la salida es una SUGERENCIA para el corredor.

Determinista → sin costo de LLM, mismo patrón API-first que intencion/inversion.
"""
from __future__ import annotations

from app.intencion import HORAS_DORMIDO  # umbral de inactividad compartido con el embudo

# ── Umbrales (horas) — placeholders a calibrar con el piloto ────────────────
HORAS_MIN_REENGANCHE = HORAS_DORMIDO   # antes de esto el lead sigue "activo": no molestar
DIAS_FRIO_PROFUNDO = 21                # más allá, el lead está muy frío (prioridad baja)
HORAS_ANTI_REPETICION = 24 * 5         # no reenganchar al mismo lead más de ~1 vez cada 5 días

FRESCURA = ("activo", "dormido", "frio_profundo", "desconocida")


def clasificar_frescura(horas_inactividad: float | None) -> str:
    """Clasifica cuán frío está un lead por su inactividad. 'desconocida' si no hay marca."""
    if horas_inactividad is None:
        return "desconocida"
    if horas_inactividad < HORAS_MIN_REENGANCHE:
        return "activo"
    if horas_inactividad < DIAS_FRIO_PROFUNDO * 24:
        return "dormido"
    return "frio_profundo"


# Señal de intención → (tipo de ángulo, frase del dato VERIFICADO que se ofrece).
# El ORDEN es la prioridad al elegir con qué valor reenganchar. Se lidera con lo más
# concreto/decisorio. NUNCA se incluye 'perfil' ni 'contacto'/'corredor' (esos son
# handoff caliente, no reenganche frío). Fair Housing safe por construcción.
_ANGULOS: tuple[tuple[str, str, str], ...] = (
    ("ficha",     "ficha",       "la ficha técnica verificada del inmueble (estado real: estructura, tubería, mantenimiento)"),
    ("precio",    "precio",      "el detalle verificado del precio y de lo que de verdad incluye"),
    ("inversion", "inversion",   "el análisis de inversión sobre datos verificados (no una estimación de portal)"),
    ("zona",      "entorno",     "el dato real del entorno —ruido y caminabilidad medidos, no adjetivos de folleto—"),
    ("comparar",  "comparacion", "la comparación honesta frente a las otras opciones que estabas mirando"),
    ("visita",    "visita",      "todo listo para que veas el inmueble con el dato verificado en la mano"),
)

# Señales que significan "el corredor ya está en la jugada" → NO se reenganchan.
_SENALES_CALIENTES = ("corredor", "contacto")


def _elegir_angulo(senales: dict) -> tuple[str, str] | None:
    """Devuelve (tipo, frase_dato) del primer ángulo con señal presente, o None.
    Recorre _ANGULOS en orden de prioridad. Excluye por construcción la clase
    protegida (no hay entrada 'perfil')."""
    for clave, tipo, frase in _ANGULOS:
        if senales.get(clave):
            return tipo, frase
    return None


def _mejor_novedad(novedades: list[dict] | None, tipo: str) -> dict | None:
    """De una lista de novedades verificadas del inmueble, elige la que refuerza el
    ángulo (misma 'tipo'); si no hay coincidencia, la primera disponible. None si vacío.
    Cada novedad: {'tipo': str, 'etiqueta': str} (etiqueta = frase lista para el mensaje)."""
    if not novedades:
        return None
    validas = [n for n in novedades if isinstance(n, dict) and n.get("etiqueta")]
    if not validas:
        return None
    for n in validas:
        if n.get("tipo") == tipo:
            return n
    return validas[0]


def _componer_mensaje(direccion: str | None, frase_dato: str, novedad: dict | None) -> str:
    """Redacta la sugerencia VALOR-primero para que el corredor la envíe: lidera con el
    dato verificado, cierra sin presión. Honestidad de marca, no empuje transaccional."""
    ref = f"el inmueble de {direccion}" if direccion else "el inmueble que te interesó"
    dato = novedad["etiqueta"] if novedad else frase_dato
    return (
        f"Hola — sobre {ref}: ya tenemos {dato}. "
        f"Es justo lo que te importaba, así que te lo comparto por si te sirve para decidir. "
        f"Sin compromiso; cuando quieras lo vemos."
    )


def evaluar_reenganche(
    *,
    intencion: dict,
    horas_inactividad: float | None = None,
    direccion: str | None = None,
    novedades: list[dict] | None = None,
    horas_desde_ultimo_reenganche: float | None = None,
) -> dict | None:
    """
    Decide si vale la pena reenganchar a un interesado enfriado, y con qué mensaje.

    Devuelve None (el silencio por defecto) salvo que se cumplan TODAS las condiciones:
      1. El lead NO está caliente ni en handoff (esos ya los tiene el corredor).
      2. Tuvo enganche real: una señal transaccional a la que aportar valor.
      3. No es demasiado pronto (horas_inactividad >= HORAS_MIN_REENGANCHE), si se conoce.
      4. No se le reenganchó hace poco (anti-repetición), si se conoce.
      5. Hay un ángulo de valor válido (Fair Housing safe).

    Args:
        intencion: salida de app.intencion.analizar_intencion (usa nivel, estado, senales,
            handoff_sugerido).
        horas_inactividad: horas desde la última interacción del lead (None = desconocida).
        direccion: dirección del inmueble, para personalizar el mensaje.
        novedades: lista de {'tipo','etiqueta'} con datos verificados nuevos del inmueble.
        horas_desde_ultimo_reenganche: para no repetir contacto (None = nunca reenganchado).

    Returns:
        dict {reenganchar, frescura, angulo, novedad, mensaje, tono, canal_sugerido} o None.
    """
    if not isinstance(intencion, dict):
        return None

    nivel = intencion.get("nivel")
    estado = intencion.get("estado")
    senales = intencion.get("senales") or {}

    # 1) Los calientes / en handoff NO se reenganchan: el corredor ya está en la jugada.
    if (
        nivel == "caliente"
        or intencion.get("handoff_sugerido")
        or any(senales.get(k) for k in _SENALES_CALIENTES)
    ):
        return None

    # 3) Demasiado pronto: sigue activo, no molestar. (Solo si conocemos el tiempo.)
    if horas_inactividad is not None and horas_inactividad < HORAS_MIN_REENGANCHE:
        return None

    # 4) Anti-repetición: ya se le escribió hace poco.
    if (
        horas_desde_ultimo_reenganche is not None
        and horas_desde_ultimo_reenganche < HORAS_ANTI_REPETICION
    ):
        return None

    # 2 + 5) Debe haber una señal transaccional a la que aportar valor (Fair Housing safe).
    #        Sin ángulo → no hay a qué volver → silencio.
    angulo = _elegir_angulo(senales)
    if angulo is None:
        return None
    tipo, frase_dato = angulo

    novedad = _mejor_novedad(novedades, tipo)
    return {
        "reenganchar": True,
        "frescura": clasificar_frescura(horas_inactividad),
        "angulo": tipo,
        "novedad": novedad,
        "mensaje": _componer_mensaje(direccion, frase_dato, novedad),
        "tono": "valor",            # aporta valor, no empuja
        "canal_sugerido": "email",  # el que ya existe (Resend); Fase 3 añade WhatsApp
    }
