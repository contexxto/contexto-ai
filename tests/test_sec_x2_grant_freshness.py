"""SEC-X2-GRANT-FRESHNESS-R0 · la autoridad del grant se juzga con la hora de la DECISIÓN, no la del inicio de la
transacción.

    UN PERMISO QUE YA VENCIÓ NO SIGUE VIVO PORQUE EL CRON EMPEZÓ ANTES

`autorizar_efecto_reenganche` comprobaba `granted_at <= now() AND expires_at > now()` y reservaba con
`used_at = now()`. En PostgreSQL `now()` es el INICIO de la transacción. El cron decide dentro de la transacción que
abrió al leer la primera página del barrido (SEC-X2-SCAN-FAIRNESS-R0 recorre todo el universo, así que puede durar);
con `now()`, un grant que venció durante ese recorrido seguía «vigente» y uno que entró en vigor no se veía (y su
reserva habría violado `used_at >= granted_at`, CHECK de la 038). Ahora la vigencia y el consumo usan
`statement_timestamp()`: la hora de ESA sentencia, estable dentro de ella.

El corte del universo dormido del barrido sigue en `now()` a propósito (una foto fija): no se toca.

PostgreSQL 15 real (`TEST_DATABASE_URL`), esquema efímero de TR-2; los grants los crea el endpoint REAL de opt-in
(`_lead_con_grant`) y solo se mueven sus instantes, desde otra sesión, para situar el borde dentro de la transacción.
Sin la variable, todo se SALTA (un skip es «esta evidencia no se recogió»).
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import text

import app.reenganche_cron as cron
import app.routers.chat as chat
from app.autoridad_reenganche import EstadoAutorizacion, autorizar_efecto_reenganche
from tests.test_tr2_consentimiento import _fila, base, pg  # noqa: F401
from tests.test_tr4_reenganche import entorno  # noqa: F401
from tests.test_tr5_consent_grant import _grants_completos, _lead_con_grant

AUTH, NO = EstadoAutorizacion.AUTHORIZED, EstadoAutorizacion.NO_GRANT
CANALES = ["EMAIL", "PUSH"]


@pytest.fixture(autouse=True)
def _frescura(monkeypatch):
    from app.limiter import limiter
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")


async def _mover(Sesion, sid, sql_set: str):
    """Desde OTRA sesión (confirmada): sitúa el borde de vigencia de los grants del lead."""
    async with Sesion() as db:
        await db.execute(text(f"UPDATE consent_grant SET {sql_set} WHERE session_id = :s"), {"s": sid})
        await db.commit()


async def _decide(db, sid, reservar):
    return (await autorizar_efecto_reenganche(db, session_id=sid, canales_candidatos=CANALES, reservar=reservar)).estado


async def _usados(Sesion, sid) -> list:
    return [g["used_at"] for g in await _grants_completos(Sesion, sid)]


@pg
async def test_1_vence_despues_de_abrir_la_transaccion_y_antes_de_decidir(base):
    """Borde de vencimiento DENTRO de una transacción: a t0 el grant está vigente (control: AUTHORIZED sin
    reservar); vence a t1; a t2 > t1, en la MISMA transacción —el mismo now()—, la frontera responde NO_GRANT, sin
    reservar y reservando. Con now() habría seguido AUTHORIZED: la vigencia se juzgaba con la foto de t0."""
    sid, _ = await _lead_con_grant(base)
    await _mover(base, sid, "expires_at = now() + interval '2 seconds'")
    async with base() as db:
        t0 = (await db.execute(text("SELECT now()"))).scalar()       # abre la transacción
        assert await _decide(db, sid, reservar=False) is AUTH        # control: vigente al empezar
        await asyncio.sleep(3)
        assert (await db.execute(text("SELECT now()"))).scalar() == t0, "la prueba exige seguir en la misma transacción"
        assert await _decide(db, sid, reservar=False) is NO, "un grant vencido siguió vivo (reloj de la transacción)"
        assert await _decide(db, sid, reservar=True) is NO
        await db.commit()
    assert await _usados(base, sid) == [None, None], "se consumió un grant vencido"


@pg
async def test_2_entra_en_vigor_despues_de_abrir_la_transaccion_y_antes_de_decidir(base):
    """El inverso: a t0 el grant aún no rige (NO_GRANT); rige desde t1; a t2 > t1, en la MISMA transacción, es
    AUTHORIZED —sin reservar no consume; reservando consume con used_at ≥ granted_at (CHECK de la 038)—."""
    sid, _ = await _lead_con_grant(base)
    await _mover(base, sid, "granted_at = now() + interval '2 seconds'")
    async with base() as db:
        await db.execute(text("SELECT 1"))                            # abre la transacción (t0)
        assert await _decide(db, sid, reservar=False) is NO          # control: aún no rige
        await asyncio.sleep(3)
        assert await _decide(db, sid, reservar=False) is AUTH, "un grant ya vigente no se vio (reloj de la transacción)"
        assert await _usados(base, sid) == [None, None], "decidir sin reservar consumió"
        assert await _decide(db, sid, reservar=True) is AUTH
        await db.commit()
    for g in await _grants_completos(base, sid):
        assert g["used_at"] is not None and g["used_at"] >= g["granted_at"]


@pg
async def test_3_used_at_es_la_hora_de_la_sentencia_que_reserva(base):
    """`used_at` es contemporáneo a la sentencia que reserva, no al inicio de la transacción del llamador."""
    sid, _ = await _lead_con_grant(base)
    async with base() as db:
        t0 = (await db.execute(text("SELECT now()"))).scalar()
        await asyncio.sleep(2)
        antes = (await db.execute(text("SELECT clock_timestamp()"))).scalar()
        assert await _decide(db, sid, reservar=True) is AUTH
        despues = (await db.execute(text("SELECT clock_timestamp()"))).scalar()
        await db.commit()
    for u in await _usados(base, sid):
        assert antes <= u <= despues, (t0, antes, u, despues)
        assert (u - t0).total_seconds() >= 1.5, "used_at quedó con la hora del inicio de la transacción"


@pg
async def test_4_sin_reservar_misma_frescura_y_ningun_consumo(base):
    sid, _ = await _lead_con_grant(base)
    async with base() as db:
        assert await _decide(db, sid, reservar=False) is AUTH
        assert await _decide(db, sid, reservar=False) is AUTH         # sigue autorizando: nada se consumió
        await db.commit()
    assert await _usados(base, sid) == [None, None]


@pg
async def test_5_revocado_o_usado_sigue_fallando_cerrado(base):
    """Revocado (también DURANTE la transacción) o ya usado → NO_GRANT."""
    revocado, _ = await _lead_con_grant(base)
    usado, _ = await _lead_con_grant(base)
    await _mover(base, usado, "used_at = statement_timestamp()")
    async with base() as db:
        assert await _decide(db, revocado, reservar=False) is AUTH    # control
        await _mover(base, revocado, "revoked_at = now()")            # revocación confirmada a mitad
        assert await _decide(db, revocado, reservar=True) is NO
        assert await _decide(db, usado, reservar=True) is NO
        await db.commit()
    assert await _usados(base, revocado) == [None, None]


@pg
async def test_6_dos_workers_no_consumen_el_mismo_grant(base):
    """El primero reserva y retiene su transacción; el segundo espera el bloqueo de fila, re-evalúa la condición
    y ya ve `used_at`: NO_GRANT. Cada grant se consume UNA vez."""
    sid, _ = await _lead_con_grant(base)

    async def worker(espera, retiene):
        async with base() as db:
            await asyncio.sleep(espera)
            estado = await _decide(db, sid, reservar=True)
            await asyncio.sleep(retiene)
            await db.commit()
            return estado
    a, b = await asyncio.wait_for(asyncio.gather(worker(0, 1.5), worker(0.4, 0)), 30)
    assert (a, b) == (AUTH, NO), (a, b)
    usados = await _usados(base, sid)
    assert all(u is not None for u in usados) and len(set(usados)) == 1, "un grant se consumió dos veces"


# ── de punta a punta: el barrido largo ──────────────────────────────────────────────────

def _lenta(entorno, monkeypatch, segundos):
    """La intención del comprador tarda: la fase de lectura del barrido dura más que el borde del grant."""
    doble = chat.intencion_de_sesion

    async def intencion(sid, horas_inactividad=None, activo_id=None):
        await asyncio.sleep(segundos)
        return await doble(sid, horas_inactividad=horas_inactividad, activo_id=activo_id)
    monkeypatch.setattr(chat, "intencion_de_sesion", intencion)


async def _barrer(Sesion):
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
    async with Sesion() as db:
        return await asyncio.wait_for(cron.escanear_reenganches(db), 120)


@pg
async def test_7_el_barrido_no_reserva_un_grant_que_vencio_durante_el_recorrido(monkeypatch, base, entorno):
    """El barrido abre su transacción al leer la primera página (t0); el grant vence durante la fase de lectura
    (t1); la reserva (t2) responde NO_GRANT: ni aviso al comprador, ni grant consumido, ni marca."""
    sid, _ = await _lead_con_grant(base)
    await _mover(base, sid, "expires_at = now() + interval '2 seconds'")
    _lenta(entorno, monkeypatch, 3)
    res = await _barrer(base)
    assert res.get("comprador", 0) == 0 and entorno["email"] == [] and entorno["push"] == []
    assert await _usados(base, sid) == [None, None]
    assert (await _fila(base, sid))["reenganche_enviado_en"] is None


@pg
async def test_8_el_barrido_ve_un_grant_que_entro_en_vigor_durante_el_recorrido(monkeypatch, base, entorno):
    """El inverso de punta a punta: el grant rige desde t1, dentro del recorrido; a t2 se reserva y el comprador
    recibe (con now() habría sido NO_GRANT, y su reserva habría violado used_at ≥ granted_at)."""
    sid, _ = await _lead_con_grant(base)
    await _mover(base, sid, "granted_at = now() + interval '2 seconds'")
    _lenta(entorno, monkeypatch, 3)
    res = await _barrer(base)
    assert res.get("comprador", 0) == 1
    for g in await _grants_completos(base, sid):
        assert g["used_at"] is not None and g["used_at"] >= g["granted_at"]
