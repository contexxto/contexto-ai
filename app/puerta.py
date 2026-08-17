"""
La PUERTA SUAVE — cuándo se puede ofrecer avisar, y quién lo decide.

Contexto tiene una sola puerta de identidad y es la más cara del embudo: el correo
existe únicamente en `handoff_sesion.lead_email`, o sea que la única forma de dejar de
ser anónimo es PEDIR UN CORREDOR — el acto de mayor compromiso del recorrido. Antes de
eso todo es anónimo; después, todo es del corredor. Puertas suaves: cero.

Esta es la primera, y es una sola: *"¿te aviso cuando aparezca algo así?"*.

── Por qué esto es un MÓDULO y no una línea en el prompt ───────────────────────────
Porque una regla de conducta escrita en un prompt no es un control. El caso de estudio
está en la sesión que originó esto: un archivo público que ordenaba "marca cada cifra
como inferida" y publicaba igual cifras inferidas sin marcar.

Entonces el modelo NO decide cuándo pedir el dato. El backend emite una directiva —el
mismo patrón de `map_seed` y `chart_seed`— y el frontend renderiza la puerta. El modelo
narra; el motor autoriza. Consecuencia buscada: el modelo **no puede** ponerse insistente
aunque el prompt se degrade, porque la puerta no es texto que él escriba. Y el control
hermano de este módulo (`detectar_solicitud_contacto`) caza el único resquicio que
quedaba — que la pida en prosa por su cuenta.

── El momento: el CALLEJÓN HONESTO ─────────────────────────────────────────────────
La tentación es un umbral ("a los 3 turnos, pide el correo"). Eso es acoso con reloj. El
único momento en que pedir el dato es un servicio y no un peaje:

    criterio declarado  +  nada que de verdad encaje

Ahí la frase se sostiene sola —"hoy no tengo nada que te calce, ¿te aviso?"— y es útil
precisamente porque el inventario es escaso. El otro disparador legítimo es que lo pida
la persona.

── Las dos LÍNEAS ROJAS ────────────────────────────────────────────────────────────
1. El SCORE DE INTENCIÓN no dispara la puerta. El handoff mide "quiero hablar con un
   humano"; la alerta mide "quiero que me avises". Usar el score para pedir el correo
   convertiría el motor de intención en un motor de acoso.
2. Nada de lo que se lee aquí entra al scoring del encaje. Este módulo solo LEE el
   resultado del motor; no lo alimenta.

Puro: sin I/O, sin DB, sin LLM. Determinístico → auditable y testeable al 100%.
"""
from __future__ import annotations

import re
import unicodedata

# Encaje mínimo para considerar que algo SÍ le sirve a la persona. Por encima del corte
# del panel (_ENCAJE_MIN_GRID = 60): que una opción sea mostrable no significa que sea lo
# que pidió. Entre 60 y 70 hay tarjetas que se enseñan con su número honesto y que no
# justifican cerrar la búsqueda — ahí ofrecer avisar sigue siendo un servicio.
ENCAJE_SUFICIENTE = 70

# Lo que la alerta promete, palabra por palabra. Va en la directiva y no en el prompt: es
# la promesa acotada que separa esto de una lista de correo, y no puede reescribirla el
# modelo según le parezca.
PROMESA = "Te escribo solo cuando aparezca algo que encaje con esto. Nada más."


def _norm(t) -> str:
    """minúsculas sin acentos — matching robusto en español."""
    s = unicodedata.normalize("NFD", t if isinstance(t, str) else "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


# ── Disparador 2: lo pide la persona ────────────────────────────────────────────────
# Alta precisión a propósito: es mejor no abrir la puerta que abrirla donde nadie la
# pidió. Exige una forma de PEDIDO explícito, no la mera aparición de "aviso".
_PIDE_AVISO = re.compile(
    r"\b(avisa\w*|avisenme|notifica\w*|escribe\w*me|contacta\w*me)\b"
    r"|\bme (avisas|escribes|notificas|contactas)\b"
    r"|\bcuando (tengas?|aparezca|salga|haya)\b"
    r"|\bme puedes? avisar\b"
)


def pidio_aviso(texto) -> bool:
    """La persona pidió que le avisen. Determinista y de alta precisión."""
    return bool(_PIDE_AVISO.search(_norm(texto)))


# ── El control hermano: el modelo pidiendo datos por su cuenta ──────────────────────
# Si la puerta la abre el motor, entonces que el modelo pida contacto EN PROSA es una
# violación detectable. Se cazan formas de SOLICITUD (imperativo o pregunta directa), no
# la mención del correo: "el corredor te escribirá a tu correo" es legítimo y frecuente
# después de un handoff, y marcarlo inundaría el contador de falsos positivos —
# el mismo criterio de alta precisión de `fair_housing.detectar_steering`.
_SOLICITA_CONTACTO: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(dejame|dejeme|dame|deme|pasame|paseme|comparteme|envia\w*me|mandame)\s+"
                r"(tu|su)\s+(correo|email|e-mail|mail|telefono|numero|whatsapp|contacto)\b"),
     "pide el contacto en imperativo"),
    (re.compile(r"\b(cual|cuales)\s+es\s+(tu|su)\s+"
                r"(correo|email|e-mail|mail|telefono|numero|whatsapp)\b"),
     "pregunta directa por el contacto"),
    (re.compile(r"\b(necesito|requiero|me hace falta)\s+(tu|su)\s+"
                r"(correo|email|e-mail|mail|telefono|numero|whatsapp|contacto)\b"),
     "declara necesitar el contacto"),
    (re.compile(r"\b(escribe|escriba|deja|deje|pon|ponga|ingresa|ingrese)\s+"
                r"(tu|su)\s+(correo|email|e-mail|mail|telefono|numero)\b"),
     "instruye a escribir el contacto"),
    (re.compile(r"\bpara (enviarte|mandarte|avisarte|escribirte)\b"
                r"(?:(?![.!?]).){0,40}\b(tu|su)\s+(correo|email|mail|telefono|numero)\b"),
     "condiciona el aviso a entregar el contacto"),
]


def detectar_solicitud_contacto(texto) -> list[tuple[str, str]]:
    """(frase, motivo) por cada solicitud de contacto en la prosa. Vacío = limpio.

    Se evalúa SOLO cuando el motor NO autorizó la puerta en ese turno: con la puerta
    abierta, la directiva ya lleva su propio texto y el modelo puede nombrarla.
    """
    n = _norm(texto)
    hits: list[tuple[str, str]] = []
    for rx, motivo in _SOLICITA_CONTACTO:
        m = rx.search(n)
        if m:
            hits.append((m.group(0).strip(), motivo))
    return hits


# ── La decisión ─────────────────────────────────────────────────────────────────────

def _hay_algo_que_sirva(cards) -> bool:
    """¿Alguna opción del panel es de verdad lo que la persona pidió?

    Exige las DOS cosas: sin requisito duro incumplido (no es otro tipo de inmueble) y
    con encaje suficiente. Una tarjeta topada a 49 por ser una casa cuando pidió
    departamento no cierra la búsqueda de nadie.
    """
    for c in cards or []:
        if not isinstance(c, dict) or (c.get("duros_incumplidos") or []):
            continue
        enc = c.get("encaje")
        if isinstance(enc, (int, float)) and not isinstance(enc, bool) and enc >= ENCAJE_SUFICIENTE:
            return True
    return False


def criterio_whitelist(preferencias: dict) -> dict:
    """Las preferencias declaradas, RECORTADAS a la whitelist del motor de encaje.

    Es lo que se persiste en `demanda.criterio`, y el recorte no es cosmético: el
    extractor puede emitir claves fuera de `DIMENSIONES` (un `perfil`, un atributo de la
    persona que se coló en la conversación). Guardarlas dejaría en la base exactamente lo
    que la whitelist cerrada existe para mantener fuera del scoring — y una tabla de
    demanda con clase protegida adentro es un problema mayor que el que resuelve.
    """
    from app.encaje import DIMENSIONES

    prefs = preferencias or {}
    return {d: prefs[d] for d in DIMENSIONES
            if d in prefs and prefs[d] not in (None, False, "")}


def _criterio_legible(preferencias: dict) -> list[str]:
    """Lo que la persona declaró, en sus términos, para que la puerta lo repita.

    Solo lee la whitelist del motor de encaje: si una clave no puntúa, tampoco se
    enuncia. Así la puerta no puede reintroducir en prosa un atributo de la persona que
    el scoring ya excluye por construcción.
    """
    from app.encaje import DIMENSIONES

    etiquetas = {
        "tipo_inmueble": lambda v: str(v),
        "presupuesto_max": lambda v: f"hasta ${int(round(float(v))):,}",
        "dormitorios": lambda v: f"{int(v)} dormitorio(s)",
        "tranquilidad": lambda _v: "tranquilo",
        "caminable": lambda _v: "caminable",
        "transporte": lambda _v: "cerca del transporte",
        "area_verde": lambda _v: "con área verde cerca",
        "acepta_mascotas": lambda _v: "que acepte mascotas",
    }
    out = []
    for dim in DIMENSIONES:
        v = (preferencias or {}).get(dim)
        if v in (None, False, "") or dim not in etiquetas:
            continue
        try:
            out.append(etiquetas[dim](v))
        except (TypeError, ValueError):
            continue
    return out


def evaluar_puerta(*, preferencias: dict | None, cards: list | None,
                   ya_ofrecida: bool = False, pidio_corredor: bool = False,
                   texto_usuario: str | None = None) -> dict | None:
    """La directiva de puerta del turno, o None si NO corresponde ofrecer nada.

    None es la respuesta por defecto y la más frecuente: la puerta se abre en un caso
    concreto, no cuando "ya toca".

    Las cinco reglas de no-presión, aquí como código:
      1. Nunca como condición → la directiva es informativa; el panel se muestra igual.
      2. Nunca en mitad de la respuesta → viaja en el panel, que va DESPUÉS de la prosa.
      3. Una vez → `ya_ofrecida` corta.
      4. El "no" se respeta → el caller persiste `ya_ofrecida` al declinar.
      5. La promesa es acotada y se dice → `PROMESA`, fija, no la escribe el modelo.
    """
    if ya_ofrecida or pidio_corredor:
        return None

    criterio = _criterio_legible(preferencias or {})
    if not criterio:
        # LÍNEA ROJA: sin criterio declarado no hay puerta. Ni por turnos, ni por score.
        return None

    if pidio_aviso(texto_usuario):
        motivo = "lo_pidio"
    elif not _hay_algo_que_sirva(cards):
        motivo = "callejon_honesto"
    else:
        return None

    return {
        "motivo": motivo,
        "criterio": criterio,
        # Lo que se guardará en `demanda.criterio`, ya recortado a la whitelist. Viaja en
        # la directiva para que la demanda registre lo que el MOTOR leyó, no lo que el
        # frontend interprete.
        "criterio_raw": criterio_whitelist(preferencias or {}),
        "promesa": PROMESA,
        # Lo que el frontend pinta. Va aquí y no en el prompt para que no pueda
        # reescribirse turno a turno en algo más insistente.
        "titulo": ("¿Te aviso cuando aparezca algo así?" if motivo == "callejon_honesto"
                   else "¿Te aviso cuando aparezca?"),
        "detalle": (" · ".join(criterio))[:300],
    }
