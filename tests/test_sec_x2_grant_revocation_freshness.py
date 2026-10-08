"""SEC-X2-GRANT-REVOCATION-FRESHNESS-R0 · una revocación válida no falla ABIERTA porque su transacción empezó antes.

    USUARIO REVOCA → LA ESCRITURA DE LA REVOCACIÓN FALLA → EL GRANT SIGUE VIVO   = AUTORIDAD QUE FALLA ABIERTA

`app/grant_reenganche.py` revocaba con `revoked_at = now()` en sus dos caminos (la sustitución dentro de un nuevo
«sí» y la revocación explícita). `now()` es el INICIO de la transacción del llamador y la 038 exige
`revoked_at >= granted_at`: si un grant se creaba (y confirmaba) DESPUÉS de que empezara la transacción que lo
revoca, el UPDATE intentaba una hora anterior a su `granted_at`, el CHECK lo rechazaba, el llamador deshacía todo y
el grant quedaba vivo. Ahora las dos revocaciones usan `statement_timestamp()`. El CHECK no se toca.

PostgreSQL 15 real (`TEST_DATABASE_URL`), esquema efímero de TR-2. El grant «concurrente» lo crea el endpoint REAL de
opt-in (`/lead-contacto`, otra conexión que confirma) mientras la transacción bajo prueba (T1) ya está abierta.
Sin la variable, todo se SALTA.
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

from app.autoridad_reenganche import EstadoAutorizacion, autorizar_efecto_reenganche
from app.contracts.consent_grant_v0 import Channel
from app.grant_reenganche import crear_grants_reenganche, revocar_grants_reenganche
from app.sesion_autoridad import Autoridad, PruebaDeAutoridad
from tests.test_tr2_consentimiento import PUSH, _dormida, _post, _sesion, base, pg  # noqa: F401
from tests.test_tr5_consent_grant import _grants_completos

COPY = "REENGAGEMENT_CONSENT_V1"


@pytest.fixture(autouse=True)
def _revocacion(monkeypatch):
    from app.limiter import limiter
    monkeypatch.setattr(limiter, "enabled", False)


async def _lead(Sesion):
    sid, cab = await _sesion(Sesion)
    await _dormida(Sesion, sid)
    return sid, cab


async def _si(sid, cab, *, email=True, push=False):
    """Un «sí» REAL por el endpoint (otra conexión, confirmada)."""
    r = await _post(sid, cab, consent=True, **({"email": "c@ejemplo.invalid"} if email else {}),
                    **({"push_subscription": PUSH} if push else {}))
    assert r.status_code == 200 and r.json()["resultado"] == "activado", r.text


def _prueba(sid) -> PruebaDeAutoridad:
    return PruebaDeAutoridad(autoridad=Autoridad.ANONYMOUS_CAPABILITY, session_id=sid)


def _vivos(grants, canal=None):
    return [g for g in grants if g["revoked_at"] is None and g["used_at"] is None
            and (canal is None or g["channel"] == canal)]


async def _autoriza(Sesion, sid, canales):
    async with Sesion() as db:
        return (await autorizar_efecto_reenganche(
            db, session_id=sid, canales_candidatos=canales, reservar=False)).estado


async def _reloj(db):
    """Hora REAL del servidor (no la de la transacción): acota la de la sentencia que revoca."""
    return (await db.execute(text("SELECT clock_timestamp()"))).scalar()


async def _sql(Sesion, sentencia, params):
    async with Sesion() as db:
        await db.execute(text(sentencia), params)
        await db.commit()


@pg
async def test_A_la_revocacion_explicita_de_una_transaccion_mas_vieja_que_el_grant(base):
    """T1 abre a t0; T2 crea (y confirma) un grant vivo a t1 > t0; T1 revoca. La revocación PROSPERA: revoked_at ≥
    granted_at y el grant deja de autorizar. Con now(), revoked_at = t0 < granted_at → CHECK → rollback → vivo."""
    sid, cab = await _lead(base)
    async with base() as t1:
        t0 = (await t1.execute(text("SELECT now()"))).scalar()
        await asyncio.sleep(0.3)
        await _si(sid, cab)                                    # T2
        gs = await _grants_completos(base, sid)
        assert gs and all(g["granted_at"] > t0 for g in gs), "precondición: el grant nace DESPUÉS de t0"
        antes = await _reloj(t1)
        await revocar_grants_reenganche(t1, sid)
        despues = await _reloj(t1)
        await t1.commit()
    gs = await _grants_completos(base, sid)
    assert gs and all(g["revoked_at"] is not None and g["revoked_at"] >= g["granted_at"] for g in gs)
    assert all(antes <= g["revoked_at"] <= despues for g in gs), "revoked_at no es la hora de la revocación"
    assert await _autoriza(base, sid, ["EMAIL"]) is EstadoAutorizacion.NO_GRANT


@pg
async def test_B_un_nuevo_si_revoca_el_grant_vivo_que_aparecio_mientras_tanto(base):
    """T1 abre a t0; T2 crea un grant vivo de EMAIL a t1 > t0; T1 registra un nuevo «sí» de EMAIL. El grant
    intermedio queda revocado (revoked_at ≥ granted_at), el nuevo se registra y queda UNO vivo por canal."""
    sid, cab = await _lead(base)
    async with base() as t1:
        t0 = (await t1.execute(text("SELECT now()"))).scalar()
        await asyncio.sleep(0.3)
        await _si(sid, cab)                                    # T2: el grant intermedio
        intermedio = (await _grants_completos(base, sid))[0]
        assert intermedio["granted_at"] > t0, "precondición: el grant intermedio nace DESPUÉS de t0"
        antes = await _reloj(t1)
        await crear_grants_reenganche(t1, prueba=_prueba(sid), canales=[Channel.EMAIL], copy_version=COPY,
                                      activo_ref=None)
        despues = await _reloj(t1)
        await t1.commit()
    gs = await _grants_completos(base, sid)
    viejo = next(g for g in gs if g["grant_id"] == intermedio["grant_id"])
    assert viejo["revoked_at"] is not None and viejo["revoked_at"] >= viejo["granted_at"]
    assert antes <= viejo["revoked_at"] <= despues, "revoked_at no es la hora de la sustitución"
    assert len(gs) == 2 and len(_vivos(gs, "EMAIL")) == 1
    assert _vivos(gs, "EMAIL")[0]["grant_id"] != intermedio["grant_id"]


@pg
async def test_C_la_revocacion_ordinaria_sigue_igual(base):
    sid, cab = await _lead(base)
    await _si(sid, cab, push=True)
    async with base() as db:
        antes = await _reloj(db)
        await revocar_grants_reenganche(db, sid)
        despues = await _reloj(db)
        await db.commit()
    gs = await _grants_completos(base, sid)
    assert len(gs) == 2 and _vivos(gs) == [] and all(g["revoked_at"] >= g["granted_at"] for g in gs)
    assert all(antes <= g["revoked_at"] <= despues for g in gs)


@pg
async def test_D_lo_ya_revocado_no_resucita_ni_cambia_su_hora(base):
    sid, cab = await _lead(base)
    await _si(sid, cab)
    async with base() as db:
        await revocar_grants_reenganche(db, sid)
        await db.commit()
    primera = [g["revoked_at"] for g in await _grants_completos(base, sid)]
    await asyncio.sleep(0.2)
    async with base() as db:
        await revocar_grants_reenganche(db, sid)
        await db.commit()
    gs = await _grants_completos(base, sid)
    assert [g["revoked_at"] for g in gs] == primera and _vivos(gs) == []


@pg
async def test_E_un_grant_usado_no_se_reinterpreta_al_revocar(base):
    """El predicado `used_at IS NULL` manda: revocar no le pone `revoked_at` a un grant ya consumido."""
    sid, cab = await _lead(base)
    await _si(sid, cab)
    await _sql(base, "UPDATE consent_grant SET used_at = statement_timestamp() WHERE session_id = :s", {"s": sid})
    async with base() as db:
        await revocar_grants_reenganche(db, sid)
        await db.commit()
    gs = await _grants_completos(base, sid)
    assert gs and all(g["used_at"] is not None and g["revoked_at"] is None for g in gs)


@pg
async def test_E2_un_nuevo_si_no_toca_un_grant_usado_del_mismo_canal(base):
    sid, cab = await _lead(base)
    await _si(sid, cab)
    await _sql(base, "UPDATE consent_grant SET used_at = statement_timestamp() WHERE session_id = :s", {"s": sid})
    async with base() as db:
        await crear_grants_reenganche(db, prueba=_prueba(sid), canales=[Channel.EMAIL], copy_version=COPY,
                                      activo_ref=None)
        await db.commit()
    gs = await _grants_completos(base, sid)
    usados = [g for g in gs if g["used_at"] is not None]
    assert len(usados) == 1 and usados[0]["revoked_at"] is None and len(_vivos(gs, "EMAIL")) == 1


@pg
async def test_F_un_si_de_email_no_revoca_el_grant_de_push(base):
    sid, cab = await _lead(base)
    await _si(sid, cab, push=True)                            # EMAIL + PUSH vivos
    push_antes = _vivos(await _grants_completos(base, sid), "PUSH")
    async with base() as db:
        await crear_grants_reenganche(db, prueba=_prueba(sid), canales=[Channel.EMAIL], copy_version=COPY,
                                      activo_ref=None)
        await db.commit()
    gs = await _grants_completos(base, sid)
    assert _vivos(gs, "PUSH") == push_antes, "un «sí» de EMAIL revocó el grant de PUSH"
    assert len(_vivos(gs, "EMAIL")) == 1


@pg
async def test_G_revocar_sin_grants_vivos_es_idempotente(base):
    sid, _ = await _lead(base)
    async with base() as db:
        await revocar_grants_reenganche(db, sid)
        await revocar_grants_reenganche(db, sid)
        await db.commit()
    assert await _grants_completos(base, sid) == []
