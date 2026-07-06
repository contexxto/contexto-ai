"""Tests de la métrica de lift de intención (app/lift.py) — lógica pura, event-anchored.
Ver docs/DISENO_Metrica_Lift_Intencion.md."""
from datetime import datetime, timedelta, timezone

import pytest

from app.lift import (
    es_maduro, grupo_holdout, reactivo, resumen_lift, tasa_o_estado,
)

UTC = timezone.utc
AHORA = datetime(2026, 7, 6, 12, 0, tzinfo=UTC)


def _hace(dias=0, horas=0):
    return AHORA - timedelta(days=dias, hours=horas)


# ── grupo_holdout: hash estable, no gameable, respeta el pct ─────────────────
def test_holdout_estable():
    assert grupo_holdout("qr-abc-123", 20) == grupo_holdout("qr-abc-123", 20)


def test_holdout_extremos():
    assert grupo_holdout("cualquier", 0) == "tocado"      # 0 → nadie retenido
    assert grupo_holdout("cualquier", 100) == "holdout"   # 100 → todos
    assert grupo_holdout(None, 20) in ("tocado", "holdout")  # no crashea con None


def test_holdout_distribucion_aproximada():
    sids = [f"qr-sesion-{i}" for i in range(2000)]
    holdout = sum(1 for s in sids if grupo_holdout(s, 20) == "holdout")
    assert 0.15 <= holdout / len(sids) <= 0.25   # ~20% con tolerancia


# ── es_maduro: handoff o ≥N días; evita censura por recorrido incompleto ─────
def test_maduro_por_handoff():
    assert es_maduro(_hace(dias=0), handoff=True, ahora=AHORA) is True   # handoff → maduro ya


def test_maduro_por_tiempo():
    assert es_maduro(_hace(dias=8), handoff=False, ahora=AHORA) is True
    assert es_maduro(_hace(dias=2), handoff=False, ahora=AHORA) is False  # en vuelo


def test_maduro_sin_fecha():
    assert es_maduro(None, handoff=False, ahora=AHORA) is False


def test_maduro_naive_datetime():
    # una fecha sin tz no debe romper (se asume UTC)
    assert es_maduro(datetime(2026, 6, 1, 12, 0), handoff=False, ahora=AHORA) is True


# ── reactivo: EVENTO (volvió tras ser elegible), no Δscore ───────────────────
def test_reactivo_volvio():
    assert reactivo(ultima_actividad=_hace(dias=1), elegible_en=_hace(dias=5)) is True


def test_reactivo_no_volvio():
    assert reactivo(ultima_actividad=_hace(dias=6), elegible_en=_hace(dias=5)) is False


def test_reactivo_faltan_datos():
    assert reactivo(None, _hace(dias=5)) is False
    assert reactivo(_hace(dias=1), None) is False


# ── tasa_o_estado: NUNCA un ratio sobre N minúsculo ──────────────────────────
def test_tasa_acumulando_bajo_umbral():
    r = tasa_o_estado(2, 4, umbral=5)
    assert r["tasa"] is None and r["status"] == "acumulando" and r["n"] == 2 and r["de"] == 4


def test_tasa_lista_con_n_suficiente():
    r = tasa_o_estado(3, 10, umbral=5)
    assert r["tasa"] == 0.3 and r["status"] == "listo"


# ── resumen_lift: unidad = lead, handoff = evento, holdout como contrafactual ─
def test_resumen_lift_escenario():
    leads = [
        {"session_id": "s1", "estado": "intencion", "handoff": True},    # pidió corredor
        {"session_id": "s2", "estado": "enganchado", "handoff": False},  # en vuelo (reciente)
        {"session_id": "s3", "estado": "dormido", "handoff": False},     # tocado, reactivó
        {"session_id": "s4", "estado": "dormido", "handoff": False},     # holdout, no reactivó
    ]
    actividad = {
        "s1": {"primera_actividad": _hace(dias=10), "ultima_actividad": _hace(dias=1),
               "reenganche_grupo": None, "reenganche_elegible_en": None},
        "s2": {"primera_actividad": _hace(dias=1), "ultima_actividad": _hace(dias=1),
               "reenganche_grupo": None, "reenganche_elegible_en": None},
        "s3": {"primera_actividad": _hace(dias=20), "ultima_actividad": _hace(dias=1),
               "reenganche_grupo": "tocado", "reenganche_elegible_en": _hace(dias=5)},
        "s4": {"primera_actividad": _hace(dias=20), "ultima_actividad": _hace(dias=6),
               "reenganche_grupo": "holdout", "reenganche_elegible_en": _hace(dias=5)},
    }
    r = resumen_lift(leads, actividad, AHORA, umbral=5)

    # handoff: 1 de 4 — bajo umbral → sin ratio, con N crudo visible
    assert r["handoff"]["n"] == 1 and r["handoff"]["de"] == 4
    assert r["handoff"]["tasa"] is None and r["handoff"]["status"] == "acumulando"

    # funnel crudo por estado
    assert r["funnel"] == {"intencion": 1, "enganchado": 1, "dormido": 2}

    # cohortes: s1(handoff), s3, s4 maduros; s2 en vuelo
    assert r["cohortes"]["maduros"] == 3 and r["cohortes"]["en_vuelo"] == 1

    # reenganche: tocado reactivó (s3), holdout no (s4) — el contrafactual
    assert r["reenganche"]["tocado"]["n"] == 1 and r["reenganche"]["tocado"]["reactivados"] == 1
    assert r["reenganche"]["holdout"]["n"] == 1 and r["reenganche"]["holdout"]["reactivados"] == 0

    assert r["total_leads"] == 4


def test_resumen_lift_reporta_tasa_con_n_suficiente():
    # 6 leads, 3 con handoff → N≥umbral → sí reporta tasa
    leads = [{"session_id": f"s{i}", "estado": "intencion", "handoff": i < 3} for i in range(6)]
    r = resumen_lift(leads, {}, AHORA, umbral=5)
    assert r["handoff"]["status"] == "listo" and r["handoff"]["tasa"] == 0.5


def test_resumen_lift_vacio():
    r = resumen_lift([], {}, AHORA)
    assert r["total_leads"] == 0 and r["handoff"]["n"] == 0 and r["funnel"] == {}


# ── smokes de montaje ────────────────────────────────────────────────────────
def test_endpoint_lift_registrado():
    import main
    paths = {getattr(r, "path", "") for r in main.app.routes}
    assert "/api/v1/assets/metricas/lift" in paths


def test_cron_holdout_pct_default():
    from app.reenganche_cron import _holdout_pct
    assert _holdout_pct() == 20  # default aprobado para el piloto
