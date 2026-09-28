"""
Control de CONTACTO EN PROSA — lo que queda de la «puerta suave».

La puerta suave ofrecía avisar por correo cuando apareciera algo que encajara. Se RETIRÓ en
Plan 1.1 · TR-1 (OFD-02 = A): prometía un aviso que ningún código envía — nadie lee las
tablas `contacto` ni `demanda` que llenaba. Pedir un correo para una consecuencia que el
sistema no puede producir es exactamente la promesa falsa que el producto no hace. La puerta
vuelve sólo cuando exista el consumidor, con su propia base de permiso.

Lo que se conserva es el control hermano (B2): el modelo NO puede pedir el contacto en prosa
por su cuenta. Con la puerta retirada ningún turno la tiene abierta, así que el control se
evalúa en todos (`app/verificacion_prosa.py`). Mide; no bloquea ni reescribe.

Puro: sin I/O, sin DB, sin LLM. Determinístico → auditable y testeable al 100%.
"""
from __future__ import annotations

import re
import unicodedata


def _norm(t) -> str:
    """minúsculas sin acentos — matching robusto en español."""
    s = unicodedata.normalize("NFD", t if isinstance(t, str) else "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


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
