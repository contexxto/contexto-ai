"""
Motor de ENCAJE — cuánto encaja un inmueble con las NECESIDADES DECLARADAS del usuario.

El pin del Mapa Vivo codifica ENCAJE, no precio (docs/SPEC_Mapa_Vivo.md). Este es el
score 0-100 detrás de "X% de encaje contigo" (tarea #8) y el DELTA del modo COMPARAR.

DISTINTO del motor de intención (app/intencion.py), que mide qué tan CALIENTE está el
lead (preguntó precio, pidió visita → readiness de handoff). Aquí medimos PREFERENCIA:
cuánto responde ESTE inmueble a lo que el usuario dijo que busca.

── Fair Housing (innegociable, tarea #14) ──────────────────────────────────────────
El encaje se keyea a QUÉ buscas, NUNCA a QUIÉN eres. Dos garantías por CONSTRUCCIÓN:
  1. `DIMENSIONES` es una whitelist CERRADA de necesidades (tranquilidad, presupuesto,
     transporte…). El motor SOLO lee esas claves; cualquier atributo de la persona
     (familia, hijos, origen, género, religión…) que llegue en `preferencias` es
     IGNORADO — no está en la whitelist, no puede mover el score.
  2. Las `razones` son DATO + FUENTE ("no juzgamos, medimos y citamos"), nunca veredictos
     de idoneidad ("barrio familiar", "para ti"). Verificable con fair_housing.es_limpio().

Puro: sin I/O, sin DB, sin LLM. Determinístico → auditable y testeable al 100%. La
captura de `preferencias` desde la conversación (LLM → schema fijo) es una capa aparte;
este módulo solo consume el schema ya poblado.
"""
from __future__ import annotations

import math

# ── Whitelist CERRADA de dimensiones de NECESIDAD declarable ────────────────────────
# Agregar una dimensión aquí es una decisión consciente. NADA fuera de esta lista puede
# influir en el encaje: es la barrera estructural de Fair Housing. Toda dimensión es una
# NECESIDAD (algo que el inmueble tiene/no tiene), jamás un rasgo de la persona.
DIMENSIONES: tuple[str, ...] = (
    "tranquilidad",     # bool — quiere ruido bajo
    "caminable",        # bool — quiere poder resolver a pie
    "transporte",       # bool — quiere estar cerca de transporte masivo
    "area_verde",       # bool — quiere verde/parque cerca
    "presupuesto_max",  # número — tope de precio (misma unidad que el precio del inmueble)
    "min_dormitorios",  # int — mínimo de dormitorios
    "acepta_mascotas",  # bool — necesita que acepten mascotas
)

# Peso por dimensión en el promedio ponderado. Presupuesto pesa más: estar sobre el tope
# es una necesidad dura, no un matiz. El resto, equitativo (transparencia sobre finura).
# Ajustar pesos es un refinamiento futuro; v1 prioriza que el número sea explicable.
_PESOS: dict[str, float] = {
    "presupuesto_max": 1.5,
    "tranquilidad": 1.0, "caminable": 1.0, "transporte": 1.0,
    "area_verde": 1.0, "min_dormitorios": 1.0, "acepta_mascotas": 1.0,
}

_RUIDO_S = {"BAJO": 1.0, "MEDIO": 0.5, "ALTO": 0.0}


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


# Coerción defensiva: la señal puede venir de un LLM o de un scraper (string, NaN, bool
# donde se esperaba número). Lo no coaccionable → None = "sin dato": el motor NUNCA
# revienta ni finge un dato; degrada honestamente. Núcleo Fair-Housing = jamás crashea.
def _num(v):
    """A float finito. Rechaza bool (True==1 no es un número declarado), NaN/inf y basura."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else None
    if isinstance(v, str):
        try:
            f = float(v.strip())
        except ValueError:
            return None
        return f if math.isfinite(f) else None
    return None


_BOOL_TRUE = {"true", "si", "sí", "yes", "y", "t", "1"}
_BOOL_FALSE = {"false", "no", "n", "f", "0"}


def _bool(v):
    """A bool real. Strings ambiguas ('no', 'false') se mapean bien; lo demás → None."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in _BOOL_TRUE:
            return True
        if s in _BOOL_FALSE:
            return False
    return None


def _nivel(s: float) -> str:
    """Nivel cualitativo de satisfacción de una dimensión (para ícono en el frontend)."""
    return "alto" if s >= 0.8 else "parcial" if s >= 0.4 else "bajo"


def _razon(dimension, cumple, s, texto, fuente=None, aporta=True):
    """Una línea explicable del encaje: dato + fuente, nunca veredicto de idoneidad."""
    return {"dimension": dimension, "cumple": cumple, "s": s,
            "texto": texto, "fuente": fuente, "aporta": aporta}


# ── Scorers por dimensión ───────────────────────────────────────────────────────────
# Cada uno recibe (valor_declarado, inmueble) y devuelve una razón. `aporta=False` marca
# "sin dato": la dimensión se declaró pero el inmueble no tiene la señal → se explica al
# usuario pero NO entra al promedio (no castigamos ni premiamos lo que no sabemos).

def _score_tranquilidad(_decl, inm) -> dict:
    ruido = inm.get("ruido")
    ruido = ruido.upper() if isinstance(ruido, str) else ruido  # BAJO/MEDIO/ALTO, tolerante a caja
    if ruido not in _RUIDO_S:
        return _razon("tranquilidad", "sin_dato", None,
                      "Buscabas tranquilidad · sin dato de ruido aquí", None, aporta=False)
    s = _RUIDO_S[ruido]
    return _razon("tranquilidad", _nivel(s), s,
                  f"Buscabas tranquilidad · ruido estimado {ruido.lower()}", "estimación por sector")


def _score_caminable(_decl, inm) -> dict:
    ws = _num(inm.get("walk_score"))
    if ws is None:
        return _razon("caminable", "sin_dato", None,
                      "Buscabas caminable · sin caminabilidad calculada aquí", None, aporta=False)
    s = _clamp01(ws / 100)
    return _razon("caminable", _nivel(s), s,
                  f"Buscabas caminable · caminabilidad {int(ws)}/100", "OpenStreetMap")


def _score_transporte(_decl, inm) -> dict:
    mins = _num(inm.get("transporte_min"))  # minutos a pie al transporte masivo más cercano
    if mins is None:
        return _razon("transporte", "sin_dato", None,
                      "Buscabas transporte cerca · sin dato de transporte aquí", None, aporta=False)
    s = (1.0 if mins <= 10 else 0.75 if mins <= 15 else 0.5 if mins <= 25
         else 0.25 if mins <= 35 else 0.1)
    return _razon("transporte", _nivel(s), s,
                  f"Buscabas transporte cerca · masivo a ~{int(mins)} min a pie", "mapa")


def _score_area_verde(_decl, inm) -> dict:
    # Preferimos el parque concreto (min a pie); si no, la cobertura vegetal del sector.
    pmin = _num(inm.get("parque_min"))
    if pmin is not None:
        s = (1.0 if pmin <= 5 else 0.7 if pmin <= 10 else 0.4 if pmin <= 20 else 0.2)
        return _razon("area_verde", _nivel(s), s,
                      f"Buscabas verde · parque a ~{int(pmin)} min a pie", "mapa")
    veg = _num(inm.get("vegetacion"))
    if veg is not None:
        s = _clamp01(veg / 100)
        return _razon("area_verde", _nivel(s), s,
                      f"Buscabas verde · cobertura vegetal ~{int(veg)}%", "estimación por sector")
    return _razon("area_verde", "sin_dato", None,
                  "Buscabas verde · sin dato de áreas verdes aquí", None, aporta=False)


def _score_presupuesto(decl, inm) -> dict:
    precio = _num(inm.get("precio"))
    decl = _num(decl)
    if precio is None or decl is None or decl <= 0:
        return _razon("presupuesto_max", "sin_dato", None,
                      "Diste un presupuesto · sin precio comparable aquí", None, aporta=False)
    if precio <= decl:
        return _razon("presupuesto_max", "alto", 1.0,
                      f"Dentro de tu presupuesto (${int(precio):,} ≤ ${int(decl):,})", "precio publicado")
    exceso = (precio - decl) / decl
    s = 0.4 if exceso <= 0.05 else 0.15 if exceso <= 0.15 else 0.0
    return _razon("presupuesto_max", _nivel(s), s,
                  f"Sobre tu presupuesto (${int(precio):,} vs ${int(decl):,})", "precio publicado")


def _score_min_dormitorios(decl, inm) -> dict:
    d = _num(inm.get("num_dormitorios"))
    decl = _num(decl)
    if d is None or decl is None or decl <= 0:
        return _razon("min_dormitorios", "sin_dato", None,
                      "Pediste un mínimo de dormitorios · sin dato aquí", None, aporta=False)
    d, decl = int(d), int(decl)
    s = 1.0 if d >= decl else 0.4 if d == decl - 1 else 0.0
    txt = (f"Cumple tus {decl}+ dormitorios ({d})" if d >= decl
           else f"Tiene {d} dormitorio(s), pediste {decl}+")
    return _razon("min_dormitorios", _nivel(s), s, txt, "ficha del inmueble")


def _score_acepta_mascotas(_decl, inm) -> dict:
    am = _bool(inm.get("acepta_mascotas"))
    if am is None:
        return _razon("acepta_mascotas", "sin_dato", None,
                      "Necesitas que acepten mascotas · sin dato aquí", None, aporta=False)
    s = 1.0 if am else 0.0
    return _razon("acepta_mascotas", _nivel(s), s,
                  "Acepta mascotas" if am else "No acepta mascotas", "ficha del inmueble")


_SCORERS = {
    "tranquilidad": _score_tranquilidad,
    "caminable": _score_caminable,
    "transporte": _score_transporte,
    "area_verde": _score_area_verde,
    "presupuesto_max": _score_presupuesto,
    "min_dormitorios": _score_min_dormitorios,
    "acepta_mascotas": _score_acepta_mascotas,
}


def _dims_declaradas(preferencias: dict) -> list[str]:
    """Dimensiones DECLARADAS y activas, en el orden canónico de DIMENSIONES.

    Solo mira claves de la whitelist (Fair Housing: lo demás se ignora). Para las bool,
    'declarada' = presente y truthy (declarar False = 'no me importa' → no puntúa). Para
    las numéricas (presupuesto/dormitorios), 'declarada' = presente y no-None.
    """
    prefs = preferencias or {}
    out = []
    for dim in DIMENSIONES:
        if dim not in prefs:
            continue
        val = prefs[dim]
        if dim in ("presupuesto_max", "min_dormitorios"):
            n = _num(val)               # nº válido y POSITIVO: un tope de 0 (o basura) no
            if n is not None and n > 0:  # es una necesidad declarable → se ignora.
                out.append(dim)
        elif val:  # bool truthy
            out.append(dim)
    return out


def calcular_encaje(preferencias: dict, inmueble: dict) -> dict:
    """Encaje 0-100 de `inmueble` con las necesidades DECLARADAS en `preferencias`.

    Devuelve {score, razones, dimensiones_declaradas, dimensiones_evaluadas}:
      - score: int 0-100, o None si no hay NADA que puntuar honestamente (ninguna
        preferencia declarada, o ninguna con señal disponible en el inmueble). None ≠ 0:
        "no sé" no es "no encaja" — el frontend no debe pintar un "0%" falso.
      - razones: lista explicable (dato + fuente). Incluye las 'sin_dato' (aporta=False)
        para ser honestos sobre lo que no sabemos, sin que afecten el número.

    El promedio es ponderado SOLO sobre las dimensiones con señal (aporta=True): no
    castigamos ni premiamos lo que el inmueble no reporta.
    """
    declaradas = _dims_declaradas(preferencias)
    razones = [_SCORERS[dim](preferencias.get(dim), inmueble or {}) for dim in declaradas]
    evaluadas = [r for r in razones if r["aporta"]]

    if not evaluadas:
        return {"score": None, "razones": razones,
                "dimensiones_declaradas": declaradas, "dimensiones_evaluadas": []}

    num = sum(r["s"] * _PESOS[r["dimension"]] for r in evaluadas)
    den = sum(_PESOS[r["dimension"]] for r in evaluadas)
    score = round(100 * num / den)
    return {
        "score": max(0, min(100, score)),
        "razones": razones,
        "dimensiones_declaradas": declaradas,
        "dimensiones_evaluadas": [r["dimension"] for r in evaluadas],
    }


def delta_encaje(preferencias: dict, inmueble_a: dict, inmueble_b: dict) -> dict:
    """El DELTA del modo COMPARAR: dónde gana cada inmueble en lo que al usuario le importa.

    No un "82% vs 76%" frío (docs/SPEC_Mapa_Vivo.md): el trade-off dimensión por dimensión.
    Devuelve {a, b, dimensiones:[{dimension, gana, ...}]} — 'gana' ∈ a|b|empate|sin_dato.
    """
    ea = calcular_encaje(preferencias, inmueble_a)
    eb = calcular_encaje(preferencias, inmueble_b)
    ra = {r["dimension"]: r for r in ea["razones"]}
    rb = {r["dimension"]: r for r in eb["razones"]}

    dims = []
    for dim in _dims_declaradas(preferencias):
        a, b = ra.get(dim), rb.get(dim)
        sa = a["s"] if a and a["aporta"] else None
        sb = b["s"] if b and b["aporta"] else None
        if sa is None or sb is None:
            gana = "sin_dato"
        elif abs(sa - sb) < 1e-9:
            gana = "empate"
        else:
            gana = "a" if sa > sb else "b"
        dims.append({
            "dimension": dim, "gana": gana,
            "a_s": sa, "b_s": sb,
            "a_texto": a["texto"] if a else None,
            "b_texto": b["texto"] if b else None,
        })
    return {"a": {"score": ea["score"]}, "b": {"score": eb["score"]}, "dimensiones": dims}
