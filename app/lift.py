"""
Lift de Intención — lógica PURA (sin I/O, testeable offline). Ver docs/DISENO_Metrica_Lift_Intencion.md.

Mide el North Star ("handoffs que cierran + lift de intención") sobre el dato PROPIO del piloto, no una
vanity metric espejo de un portal. Construida contra una crítica adversarial: cada número se ancla a un
EVENTO OBSERVABLE (pidió corredor, volvió tras el touch), NUNCA a un Δscore (que sería el clasificador
auto-reportándose = circular). Reglas de oro:

  - UNIDAD = LEAD, nunca el snapshot (los leads activos generan más filas y sesgarían todo promedio).
  - Si N < umbral, se devuelve N + estado 'acumulando', JAMÁS un ratio (un % sobre N=4 miente porque
    *parece* dato).
  - Los resultados solo cuentan leads MADUROS (≥N días o handoff alcanzado); los censurados ('en vuelo',
    aún no terminan su recorrido) se reportan aparte, nunca promediados.
  - El holdout (grupo_holdout) es el contrafactual: sin él, la reactivación es correlación con narrativa.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

# Un lead se considera "maduro" (su desenlace ya es interpretable) a los N días de su primera
# actividad, o antes si ya alcanzó el handoff. Placeholder a calibrar con el piloto.
DIAS_MADUREZ = 7
# Bajo este N NO se reporta un ratio, solo el conteo crudo + status 'acumulando'.
UMBRAL_N = 5


def grupo_holdout(session_id: str | None, pct: int) -> str:
    """'holdout' | 'tocado' por hash ESTABLE del session_id (auditable, no gameable, no depende del
    proceso ni del reloj). pct = % que se retiene como control (0 → nadie; 100 → todos)."""
    if pct <= 0:
        return "tocado"
    if pct >= 100:
        return "holdout"
    h = int(hashlib.sha1((session_id or "").encode("utf-8")).hexdigest(), 16)
    return "holdout" if (h % 100) < pct else "tocado"


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def es_maduro(primera_actividad: datetime | None, handoff: bool,
              ahora: datetime, dias: int = DIAS_MADUREZ) -> bool:
    """Maduro = el desenlace ya es interpretable: alcanzó handoff (el resultado que importa) o pasaron
    ≥ 'dias' desde su primera actividad. Evita mezclar 'malos' con 'jóvenes' (censura por recorrido
    incompleto)."""
    if handoff:
        return True
    pa = _aware(primera_actividad)
    if pa is None:
        return False
    return (ahora - pa) >= timedelta(days=dias)


def reactivo(ultima_actividad: datetime | None, elegible_en: datetime | None) -> bool:
    """EVENTO de reactivación: el lead tuvo actividad DESPUÉS de volverse elegible al reenganche
    (volvió). No es un Δscore — es un hecho observable en la marca de tiempo."""
    ua, ee = _aware(ultima_actividad), _aware(elegible_en)
    if ua is None or ee is None:
        return False
    return ua > ee


def tasa_o_estado(numerador: int, denominador: int, umbral: int = UMBRAL_N) -> dict:
    """{n, de, tasa, status}. Si el denominador < umbral → tasa=None y status='acumulando' (NUNCA un
    ratio sobre N minúsculo). Con N suficiente → status='listo' y la tasa redondeada."""
    if denominador < umbral:
        return {"n": numerador, "de": denominador, "tasa": None, "status": "acumulando"}
    return {"n": numerador, "de": denominador, "tasa": round(numerador / denominador, 3), "status": "listo"}


def resumen_lift(leads: list[dict], actividad_por_sid: dict[str, dict], ahora: datetime,
                 *, umbral: int = UMBRAL_N, dias: int = DIAS_MADUREZ) -> dict:
    """Métrica de lift, unidad = LEAD, anclada a evento. Puro.

    leads: un dict por lead (unidad correcta), con al menos {session_id, estado, handoff:bool}.
    actividad_por_sid: {session_id: {primera_actividad, ultima_actividad, reenganche_grupo,
                        reenganche_elegible_en}} (de lead_actividad).
    ahora: datetime de referencia (inyectado para testeabilidad).
    """
    total = len(leads)
    con_handoff = sum(1 for l in leads if l.get("handoff"))

    funnel: dict[str, int] = {}
    maduros = en_vuelo = 0
    for l in leads:
        funnel[l["estado"]] = funnel.get(l["estado"], 0) + 1
        act = actividad_por_sid.get(l.get("session_id"), {})
        if es_maduro(act.get("primera_actividad"), bool(l.get("handoff")), ahora, dias):
            maduros += 1
        else:
            en_vuelo += 1

    # Reenganche: reactivación tocado vs holdout, SOLO entre los que se volvieron elegibles.
    grupos = {"tocado": {"n": 0, "reactivados": 0}, "holdout": {"n": 0, "reactivados": 0}}
    for act in actividad_por_sid.values():
        if not act.get("reenganche_elegible_en"):
            continue
        g = act.get("reenganche_grupo") or "tocado"
        if g not in grupos:
            g = "tocado"
        grupos[g]["n"] += 1
        if reactivo(act.get("ultima_actividad"), act.get("reenganche_elegible_en")):
            grupos[g]["reactivados"] += 1

    def _reeng(g: dict) -> dict:
        # n = LEADS en el grupo; reactivados = numerador (evento). tasa = reactivados/n (None si N chico).
        # Estructura sin colisión de claves con tasa_o_estado (cuyo 'n' es el numerador).
        t = tasa_o_estado(g["reactivados"], g["n"], umbral)
        return {"n": g["n"], "reactivados": g["reactivados"], "tasa": t["tasa"], "status": t["status"]}

    return {
        "handoff": {
            **tasa_o_estado(con_handoff, total, umbral),
            "_ancla": "evento: el interesado pidió corredor (no es un score)",
            "_denominador": "interesados que interactuaron (congelado y explícito)",
        },
        "reenganche": {
            "tocado": _reeng(grupos["tocado"]),
            "holdout": _reeng(grupos["holdout"]),
            "_ancla": "evento: actividad después de volverse elegible (volvió), no Δscore",
            "_lectura": "tocado vs holdout — sin diferencia sostenida al madurar, el touch automático "
                        "no está causando la reactivación (regresión a la media / vuelta espontánea)",
        },
        "funnel": funnel,
        "cohortes": {
            "maduros": maduros, "en_vuelo": en_vuelo,
            "_nota": f"resultados solo sobre maduros (≥{dias} días o handoff); 'en vuelo' aún no terminan",
        },
        "total_leads": total,
        "_proveniencia": (f"Números propios del piloto (motor de intención + eventos), no comparados con "
                          f"portales. Ratios solo con N≥{umbral}; bajo eso, conteo + status 'acumulando'."),
    }
