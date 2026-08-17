"""
Motor de LLEGADA — de qué canal viene una visita, y con qué evidencia se afirma.

Hasta hoy el sistema no podía responder "¿por dónde entró esta persona?". El campo
`fuente` del CRM era la constante `"QR"` para todo el mundo, no había captura de UTM ni
de referrer en ningún punto del repo, y el QR que se escanea sin escribir se descartaba
sin dejar contador. Es decir: los dos motores de adquisición declarados —el canal de
YouTube y la estrategia AEO— no tenían forma de medirse.

Este módulo es la mitad determinista de ese arreglo: convierte (superficie, utm,
referrer) en un CANAL de una lista cerrada. El registro vive en `app/routers/visitas.py`.

── La regla de honestidad que lo gobierna ──────────────────────────────────────────
Un canal es una AFIRMACIÓN sobre de dónde vino alguien, y se afirma con evidencia:

  · `utm_*`   → evidencia FUERTE: alguien la puso a propósito en el enlace.
  · referrer  → evidencia MEDIA: la pone el navegador y a veces no la manda.
  · ausencia  → NO es evidencia de nada. Se rotula `directo`, que significa
                "no sabemos", nunca "vino solo".

Por eso `directo` no se interpreta como un canal exitoso: es el cajón de lo no medido.
Mismo principio que `encaje.score = None` ("no sé" ≠ "no encaja").

── Privacidad ──────────────────────────────────────────────────────────────────────
El referrer se guarda SIN query string. Es donde viajan tokens, correos y términos de
búsqueda; para clasificar el canal basta el host, y el path da contexto suficiente.
Minimización por diseño, no un filtro añadido después.

Puro: sin I/O, sin DB, sin LLM. Determinístico → auditable y testeable al 100%.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

# ── Listas CERRADAS ─────────────────────────────────────────────────────────────────
# Agregar un canal o una superficie es una decisión consciente, igual que `DIMENSIONES`
# en encaje.py. Lo que no está en la lista se normaliza al cajón honesto, no se inventa.

SUPERFICIES: tuple[str, ...] = (
    "anuncio",                  # /a/{id} — la ficha de UN inmueble (el destino del QR)
    "home",                     # / — la conversación sin inmueble anclado
    "conversacion_compartida",  # /s/{token} — alguien abrió la conversación de otro
)

CANALES: tuple[str, ...] = (
    "campana",          # utm de pago: alguien compró este clic
    "motor_respuesta",  # ChatGPT/Perplexity/Gemini/Copilot — LA tesis AEO, por fin medible
    "buscador",         # Google/Bing/DuckDuckGo — orgánico clásico
    "mensajeria",       # WhatsApp/Telegram — el reenvío entre personas
    "social",           # Instagram/LinkedIn/YouTube/TikTok — orgánico social
    "referido",         # otro sitio externo cualquiera
    "propio",           # navegación dentro de contexto, no es una llegada nueva
    "directo",          # sin referrer y sin utm → NO SABEMOS. No es un logro.
)

_LIM_UTM = 200      # topes defensivos: la URL la controla quien la escribe, no nosotros
_LIM_REFERRER = 500

# Medios que declaran pago. `utm_medium` es lo que mejor lo dice, y viaja explícito.
_MEDIOS_PAGOS = re.compile(r"\b(cpc|ppc|paid|ads?|display|retargeting|social[_-]?paid)\b")

# Host → canal. Se compara por SUFIJO de dominio para que 'www.google.com' y
# 'google.com.ec' caigan igual. El orden importa: el primero que calza gana.
_HOSTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("motor_respuesta", ("chatgpt.com", "chat.openai.com", "openai.com", "perplexity.ai",
                         "claude.ai", "gemini.google.com", "copilot.microsoft.com",
                         "you.com", "phind.com")),
    ("buscador",        ("google.", "bing.com", "duckduckgo.com", "search.brave.com",
                         "ecosia.org", "yahoo.com", "yandex.")),
    ("mensajeria",      ("whatsapp.com", "wa.me", "t.me", "telegram.org", "messenger.com")),
    ("social",          ("instagram.com", "facebook.com", "fb.com", "linkedin.com", "lnkd.in",
                         "tiktok.com", "youtube.com", "youtu.be", "twitter.com", "x.com",
                         "reddit.com", "pinterest.")),
)

# `utm_source` NO es un host: trae nombres sueltos ('youtube', 'meta', 'chatgpt'), que es
# como los escribe quien arma el enlace. Reusar el mapa de hosts para esto no funciona
# ("youtube.com" no está contenido en "youtube") y mandaba todo el tráfico etiquetado a
# `referido` — lo cazó el test. Va aparte, con nombres, y sin tokens de 1-2 letras que
# harían falsos positivos con cualquier cosa.
_FUENTES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("motor_respuesta", ("chatgpt", "openai", "perplexity", "claude", "gemini", "copilot")),
    ("buscador",        ("google", "bing", "duckduckgo", "brave", "ecosia", "yahoo", "yandex")),
    ("mensajeria",      ("whatsapp", "telegram", "messenger")),
    ("social",          ("instagram", "facebook", "meta", "linkedin", "tiktok", "youtube",
                         "twitter", "reddit", "pinterest")),
)


def _texto(v, limite: int) -> str | None:
    """Texto no vacío y acotado, o None. Defensivo: lo que llega es de fuera."""
    if not isinstance(v, str):
        return None
    s = v.strip()[:limite]
    return s or None


def limpiar_referrer(v) -> str | None:
    """Referrer sin query ni fragmento — donde viven tokens, correos y búsquedas.

    Devuelve 'host/path' o None. No es un filtro de seguridad añadido después: es la
    minimización del dato en el único punto donde entra al sistema.
    """
    s = _texto(v, _LIM_REFERRER)
    if not s:
        return None
    try:
        p = urlsplit(s if "//" in s else f"//{s}")
    except ValueError:      # URL malformada → mejor sin dato que con basura
        return None
    host = (p.hostname or "").lower()
    if not host:
        return None
    path = (p.path or "").rstrip("/")
    return f"{host}{path}"[:_LIM_REFERRER]


def _es_propio(host: str, host_propio: str | None) -> bool:
    if not host_propio:
        return False
    h = host_propio.lower().lstrip(".")
    return host == h or host.endswith("." + h)


def clasificar_canal(*, superficie: str | None = None, utm_source=None, utm_medium=None,
                     referrer=None, host_propio: str | None = None) -> str:
    """El canal de una llegada, de la lista cerrada `CANALES`.

    Precedencia, y es a propósito: la UTM manda sobre el referrer porque alguien la
    escribió deliberadamente; el referrer lo pone el navegador y se pierde con
    frecuencia (una app que abre el navegador normalmente no manda ninguno — por eso
    `mensajeria` va a subestimar SIEMPRE, y hay que saberlo al leer el reporte).

    Sin ninguna señal → `directo`, que significa "no sabemos", no "vino solo".
    """
    medium = (_texto(utm_medium, _LIM_UTM) or "").lower()
    source = (_texto(utm_source, _LIM_UTM) or "").lower()

    # 1) Evidencia fuerte: la campaña se declara a sí misma.
    if medium and _MEDIOS_PAGOS.search(medium):
        return "campana"
    if source or medium:
        # Hay UTM pero no es de pago (la firma de un correo, el enlace del canal). Se
        # clasifica por NOMBRE de fuente, no por host: son cosas distintas (ver _FUENTES).
        for canal, nombres in _FUENTES:
            if any(n in source for n in nombres):
                return canal
        return "referido"

    # 2) Evidencia media: el navegador dice de dónde viene.
    limpio = limpiar_referrer(referrer)
    if limpio:
        host = limpio.split("/", 1)[0]
        if _es_propio(host, host_propio):
            return "propio"
        for canal, sufijos in _HOSTS:
            if any(host == s.rstrip(".") or host.endswith("." + s.rstrip(".")) or s in host
                   for s in sufijos):
                return canal
        return "referido"

    # 3) Sin evidencia. El cajón honesto.
    return "directo"


def normalizar_superficie(v) -> str:
    """Superficie de la lista cerrada; `home` como caída por defecto."""
    s = (_texto(v, 40) or "").lower()
    return s if s in SUPERFICIES else "home"


def normalizar_llegada(datos: dict, *, host_propio: str | None = None) -> dict:
    """El payload crudo de una llegada → la fila lista para insertar. Nunca lanza.

    Es la ÚNICA puerta de entrada del dato: acota longitudes, minimiza el referrer y
    resuelve el canal. Que exista un solo punto es lo que permite auditar después qué
    se guardó y por qué.
    """
    d = datos or {}
    superficie = normalizar_superficie(d.get("superficie"))
    utm_source = _texto(d.get("utm_source"), _LIM_UTM)
    utm_medium = _texto(d.get("utm_medium"), _LIM_UTM)
    referrer = limpiar_referrer(d.get("referrer"))
    return {
        "superficie": superficie,
        "canal": clasificar_canal(superficie=superficie, utm_source=utm_source,
                                  utm_medium=utm_medium, referrer=d.get("referrer"),
                                  host_propio=host_propio),
        "utm_source": utm_source,
        "utm_medium": utm_medium,
        "utm_campaign": _texto(d.get("utm_campaign"), _LIM_UTM),
        "utm_content": _texto(d.get("utm_content"), _LIM_UTM),
        "referrer": referrer,
    }
