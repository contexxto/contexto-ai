"""SEC-X2-LIFT-SCOPE-R0 · la métrica de reenganche se acota al par EXACTO (session_id, activo_id).

    PERSON/SESSION CONTINUITY ≠ ASSET-SCOPED METRIC MEMBERSHIP

`/metricas/lift` obtenía los leads del corredor por inmueble, pero después leía `lead_actividad` con
`session_id` como ÚNICA clave. Una sesión interesada en X y en Y tiene una sola fila de actividad (PK =
session_id), fijada al inmueble de su primera escritura; esa fila —el grupo tocado/holdout y la
elegibilidad del experimento de X— entraba al lift del corredor de Y. Ahora:

  · cada lead que llega a `resumen_lift` es (sesión, inmueble) y lleva su `activo_id`;
  · la observación de actividad se identifica por la tupla (session_id, activo_id) — sin claves
    sintéticas; indexar por sesión sola es un error de contrato (TypeError);
  · `metricas_lift` lee `lead_actividad` por el PAR exacto en SQL; una fila con activo_id NULL, o de otro
    inmueble, no coincide con ningún par; un lead sin inmueble exacto no tiene observación.
  · nada se infiere del prefijo `qr-` ni del «último inmueble» de la sesión. Sin backfill.

Bloques:
  A · `resumen_lift`, puro.
  B · el endpoint REAL `metricas_lift` sobre PostgreSQL 15 (`TEST_DATABASE_URL`), con `lead_actividad`
      creada por su DDL real en un esquema efímero. Los leads del corredor vienen de un doble de
      `_leads_del_corredor` (su `activo_id` lo fija `_leads_de_activo`, ver C1). Sin la variable, B se
      SALTA: un skip es «esta evidencia no se recogió».
  C · costuras (el lead del CRM trae su inmueble; el SQL une por las dos columnas).
"""
from __future__ import annotations

import ast
import inspect
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import app.routers.assets as assets
import app.routers.chat as chat
from app.lift import par_observacion, resumen_lift

RAIZ = Path(__file__).resolve().parents[1]
UTC = timezone.utc
AHORA = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
X = "11111111-1111-1111-1111-111111111111"
Y = "22222222-2222-2222-2222-222222222222"
Z = "33333333-3333-3333-3333-333333333333"
S = f"qr-{X}-aaaaaaaa-0000-0000-0000-000000000001"     # la sesión llegó por el QR de X


def _hace(dias=0):
    return AHORA - timedelta(days=dias)


def _obs(grupo, *, elegible_dias=5, ultima_dias=1, primera_dias=20):
    """Una fila de lead_actividad elegible al reenganche que, además, volvió tras volverse elegible."""
    return {"primera_actividad": _hace(primera_dias), "ultima_actividad": _hace(ultima_dias),
            "reenganche_grupo": grupo, "reenganche_elegible_en": _hace(elegible_dias)}


def _lead(sid, activo, estado="dormido", handoff=False):
    return {"session_id": sid, "activo_id": activo, "estado": estado, "handoff": handoff}


def _reeng(r):
    return r["reenganche"]["tocado"]["n"], r["reenganche"]["holdout"]["n"]


# ══ A · resumen_lift, puro ═══════════════════════════════════════════════════════════════

def test_A1_la_historia_de_X_no_altera_la_metrica_de_Y():
    """El caso del mandato: la misma sesión tiene historia tocado/elegible para X, y pertenece a la
    métrica del corredor de Y. X no cambia los conteos tocado/holdout de Y, ni su madurez."""
    r = resumen_lift([_lead(S, Y)], {(S, X): _obs("tocado")}, AHORA, umbral=1)
    assert _reeng(r) == (0, 0)
    assert r["reenganche"]["tocado"]["reactivados"] == 0
    assert r["cohortes"]["maduros"] == 0 and r["cohortes"]["en_vuelo"] == 1, \
        "la primera_actividad de X volvió «maduro» al lead de Y"


def test_A2_la_observacion_exacta_de_X_cuenta_para_X():
    r = resumen_lift([_lead(S, X)], {(S, X): _obs("tocado")}, AHORA, umbral=1)
    assert _reeng(r) == (1, 0) and r["reenganche"]["tocado"]["reactivados"] == 1
    assert r["cohortes"]["maduros"] == 1


def test_A3_null_no_cuenta_para_una_metrica_acotada_por_inmueble():
    """Ni un lead sin inmueble lee la observación de su sesión, ni una observación sin inmueble cuenta."""
    r = resumen_lift([_lead(S, None)], {(S, X): _obs("tocado")}, AHORA, umbral=1)
    assert _reeng(r) == (0, 0)
    r = resumen_lift([_lead(S, X)], {(S, None): _obs("tocado")}, AHORA, umbral=1)
    assert _reeng(r) == (0, 0)
    r = resumen_lift([_lead(S, "no-es-un-uuid")], {(S, "no-es-un-uuid"): _obs("tocado")}, AHORA, umbral=1)
    assert _reeng(r) == (0, 0), "un inmueble inválido no es un inmueble exacto"


def test_A4_el_inmueble_equivocado_no_cuenta():
    r = resumen_lift([_lead(S, X)], {(S, Z): _obs("holdout")}, AHORA, umbral=1)
    assert _reeng(r) == (0, 0)


def test_A5_la_misma_sesion_en_dos_inmuebles_son_dos_observaciones_explicitas():
    """Dos leads (S, X) y (S, Y): cada uno con su observación; ninguna se funde ni se reasigna."""
    leads = [_lead(S, X), _lead(S, Y)]
    r = resumen_lift(leads, {(S, X): _obs("tocado"), (S, Y): _obs("holdout")}, AHORA, umbral=1)
    assert _reeng(r) == (1, 1) and r["total_leads"] == 2
    r = resumen_lift(leads, {(S, X): _obs("tocado")}, AHORA, umbral=1)
    assert _reeng(r) == (1, 0), "la observación de X contó también para el lead de Y"
    assert r["cohortes"]["maduros"] == 1 and r["cohortes"]["en_vuelo"] == 1


def test_A6_un_par_repetido_cuenta_una_sola_vez_en_el_experimento():
    r = resumen_lift([_lead(S, X), _lead(S, X)], {(S, X): _obs("tocado")}, AHORA, umbral=1)
    assert _reeng(r) == (1, 0)


def test_A7_una_observacion_sin_lead_no_cuenta():
    """Solo cuentan los pares que algún lead de ESTA métrica identifica."""
    r = resumen_lift([_lead(S, X)], {(S, X): _obs("tocado"), ("otra-sesion", X): _obs("holdout")},
                     AHORA, umbral=1)
    assert _reeng(r) == (1, 0)


def test_A8_nada_se_infiere_del_prefijo_qr():
    """La sesión se llama `qr-X-…`, pero el lead no trae inmueble: sin inmueble exacto no hay
    observación, aunque la de (S, X) exista."""
    assert par_observacion(S, None) is None
    r = resumen_lift([{"session_id": S, "estado": "dormido", "handoff": False}], {(S, X): _obs("tocado")},
                     AHORA, umbral=1)
    assert _reeng(r) == (0, 0)


def test_A9_el_contrato_por_sesion_sola_es_un_error_no_una_metrica_contaminada():
    with pytest.raises(TypeError):
        resumen_lift([_lead(S, X)], {S: _obs("tocado")}, AHORA)


def test_A10_el_par_es_el_uuid_canonico():
    """El mismo inmueble escrito en mayúsculas es el mismo par (UUID canónico); otro UUID no."""
    assert par_observacion(S, X.upper()) == (S, X)
    r = resumen_lift([_lead(S, X.upper())], {(S, X): _obs("tocado")}, AHORA, umbral=1)
    assert _reeng(r) == (1, 0)
    assert par_observacion("", X) is None and par_observacion(None, X) is None


def test_A11_metrica_normal_de_un_inmueble_sin_cambios():
    """Un solo inmueble: lo mismo que antes (los pares coinciden con las sesiones)."""
    leads = [_lead("s1", X, "intencion", True), _lead("s2", X, "enganchado"),
             _lead("s3", X), _lead("s4", X)]
    act = {
        ("s1", X): {"primera_actividad": _hace(10), "ultima_actividad": _hace(1),
                    "reenganche_grupo": None, "reenganche_elegible_en": None},
        ("s2", X): {"primera_actividad": _hace(1), "ultima_actividad": _hace(1),
                    "reenganche_grupo": None, "reenganche_elegible_en": None},
        ("s3", X): _obs("tocado"),
        ("s4", X): _obs("holdout", ultima_dias=6),
    }
    r = resumen_lift(leads, act, AHORA, umbral=5)
    assert r["handoff"]["n"] == 1 and r["handoff"]["de"] == 4
    assert r["funnel"] == {"intencion": 1, "enganchado": 1, "dormido": 2}
    assert r["cohortes"]["maduros"] == 3 and r["cohortes"]["en_vuelo"] == 1
    assert r["reenganche"]["tocado"] == {"n": 1, "reactivados": 1, "tasa": None, "status": "acumulando"}
    assert r["reenganche"]["holdout"] == {"n": 1, "reactivados": 0, "tasa": None, "status": "acumulando"}
    assert "no son comparables" in r["reenganche"]["_alcance"], "la discontinuidad queda etiquetada"


# ══ B · el endpoint REAL sobre PostgreSQL ═══════════════════════════════════════════════

URL = os.getenv("TEST_DATABASE_URL", "")
pg = pytest.mark.skipif(not URL, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas")


@pytest.fixture
async def base(monkeypatch):
    """Esquema propio y efímero; `lead_actividad` la crea su DDL REAL (`ensure_lead_actividad`)."""
    from app.config import settings
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    if settings.database_url and URL.split("@")[-1] in settings.database_url:
        pytest.fail("TEST_DATABASE_URL apunta a la base del producto. Abortado.")
    esquema = "lsc_" + uuid.uuid4().hex[:10]
    admin = create_async_engine(URL, poolclass=NullPool)
    async with admin.begin() as cx:
        await cx.execute(text(f"CREATE SCHEMA {esquema}"))
    motor = create_async_engine(URL, poolclass=NullPool,
                                connect_args={"server_settings": {"search_path": esquema}})
    Sesion = async_sessionmaker(motor, expire_on_commit=False)
    async with motor.begin() as cx:
        await cx.execute(text("CREATE TABLE intencion_evento (session_id text, estado text)"))
    monkeypatch.setattr(chat, "_lead_actividad_ready", False)
    async with Sesion() as db:
        await chat.ensure_lead_actividad(db)
    try:
        yield Sesion
    finally:
        await motor.dispose()
        async with admin.begin() as cx:
            await cx.execute(text(f"DROP SCHEMA {esquema} CASCADE"))
        await admin.dispose()


async def _fila(Sesion, sid, activo, grupo, *, elegible_dias=5, ultima_dias=1):
    from sqlalchemy import text
    async with Sesion() as db:
        await db.execute(text(
            "INSERT INTO lead_actividad (session_id, activo_id, primera_actividad, ultima_actividad, "
            "  reenganche_grupo, reenganche_elegible_en, reenganche_enviado_en) "
            "VALUES (:s, CAST(:a AS uuid), now() - interval '20 days', now() - make_interval(days => :u), "
            "        :g, now() - make_interval(days => :e), "
            "        CASE WHEN :g = 'tocado' THEN now() - make_interval(days => :e) END)"),
            {"s": sid, "a": activo, "g": grupo, "e": elegible_dias, "u": ultima_dias})
        await db.commit()


async def _lift(Sesion, monkeypatch, leads):
    """La lectura REAL (`metricas_lift`), con los leads del corredor dados."""
    async def del_corredor(db, *_a, **_k):
        return [{"session_id": sid, "activo_id": activo, "estado": "dormido", "handoff_estado": None}
                for sid, activo in leads]
    monkeypatch.setattr(assets, "_leads_del_corredor", del_corredor)
    usuario = SimpleNamespace(rol="corredor", user_id=str(uuid.uuid4()), agency_id=None)
    async with Sesion() as db:
        return await assets.metricas_lift.__wrapped__(request=None, user=usuario, db=db)


@pg
async def test_B1_la_fila_de_X_no_entra_al_lift_del_corredor_de_Y(base, monkeypatch):
    """La sesión llegó por el QR de X (su fila de actividad es de X, tocado y elegible) y pidió
    contacto también para Y: es lead de Y. El corredor de Y no ve el experimento de X."""
    await _fila(base, S, X, "tocado")
    out = await _lift(base, monkeypatch, [(S, Y)])
    assert _reeng(out) == (0, 0) and out["reenganche"]["tocado"]["reactivados"] == 0
    assert out["cohortes"]["maduros"] == 0, "la primera_actividad de X volvió maduro al lead de Y"


@pg
async def test_B2_la_fila_exacta_de_X_cuenta_para_X(base, monkeypatch):
    await _fila(base, S, X, "tocado")
    out = await _lift(base, monkeypatch, [(S, X)])
    assert _reeng(out) == (1, 0) and out["reenganche"]["tocado"]["reactivados"] == 1
    assert out["cohortes"]["maduros"] == 1


@pg
async def test_B3_una_fila_con_activo_null_no_cuenta(base, monkeypatch):
    """Un cierre de una sesión sin QR deja `activo_id` NULL (`_reducir_autoridad_reenganche`): esa fila
    no pertenece a ningún inmueble y no entra a ninguna métrica acotada."""
    sid = "sesion-sin-qr-1"
    await _fila(base, sid, None, "holdout")
    out = await _lift(base, monkeypatch, [(sid, X), (sid, Y)])
    assert _reeng(out) == (0, 0)


@pg
async def test_B4_el_inmueble_equivocado_no_cuenta(base, monkeypatch):
    await _fila(base, S, Z, "holdout")
    out = await _lift(base, monkeypatch, [(S, X)])
    assert _reeng(out) == (0, 0)


@pg
async def test_B5_la_misma_sesion_en_dos_inmuebles_del_mismo_corredor(base, monkeypatch):
    """El corredor es dueño de X y de Y; la sesión es lead de los dos. Son dos leads (dos pares) y la
    única fila (la de X) cuenta una sola vez, para X."""
    await _fila(base, S, X, "tocado")
    out = await _lift(base, monkeypatch, [(S, X), (S, Y)])
    assert _reeng(out) == (1, 0) and out["total_leads"] == 2
    assert out["cohortes"]["maduros"] == 1 and out["cohortes"]["en_vuelo"] == 1


@pg
async def test_B6_metrica_normal_de_un_inmueble_sin_cambios(base, monkeypatch):
    """Control: un inmueble, leads propios; el resultado es el que daba la lectura por sesión."""
    for i, grupo in enumerate(("tocado", "tocado", "holdout")):
        await _fila(base, f"qr-{X}-n{i}", X, grupo, ultima_dias=1 if i != 2 else 6)
    out = await _lift(base, monkeypatch, [(f"qr-{X}-n{i}", X) for i in range(3)])
    assert _reeng(out) == (2, 1)
    assert out["reenganche"]["tocado"]["reactivados"] == 2 and out["reenganche"]["holdout"]["reactivados"] == 0


@pg
async def test_B7_sin_inmueble_exacto_no_se_lee_lead_actividad(base, monkeypatch):
    """Leads sin `activo_id` (como el doble de la prueba de la 044): no hay par que buscar, la métrica
    no se rompe y la fila de su sesión no cuenta, aunque el prefijo diga X."""
    await _fila(base, S, X, "tocado")
    llamadas = []
    real = chat.ensure_lead_actividad

    async def espia(db):
        llamadas.append(1)
        return await real(db)
    monkeypatch.setattr(chat, "ensure_lead_actividad", espia)
    out = await _lift(base, monkeypatch, [(S, None)])
    assert _reeng(out) == (0, 0) and llamadas == []
    assert out["total_leads"] == 1


# ══ C · costuras ═════════════════════════════════════════════════════════════════════════

def test_C1_el_lead_del_crm_trae_su_inmueble_exacto():
    """`_leads_de_activo(X)` fija `activo_id = X` en cada lead: el inmueble del par sale del recorrido del
    corredor por SUS inmuebles, nunca de la sesión."""
    fuente = inspect.getsource(assets._leads_de_activo)
    assert '"activo_id": str(activo_id)' in fuente
    fuente_lift = inspect.getsource(assets.metricas_lift)
    assert '"activo_id": l.get("activo_id")' in fuente_lift


def test_C2_el_sql_del_lift_une_por_las_dos_columnas():
    """Por la tupla exacta, no por la sesión sola: ningún SELECT de lead_actividad del lift filtra solo
    por session_id, y la unión compara también el inmueble."""
    arbol = ast.parse(inspect.getsource(assets.metricas_lift).lstrip())
    textos = [n.value for n in ast.walk(arbol) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    sql = next(t for t in textos if "FROM lead_actividad" in t)
    assert "la.session_id = par.session_id AND la.activo_id = par.activo_id" in sql
    assert "session_id = ANY(" not in sql
