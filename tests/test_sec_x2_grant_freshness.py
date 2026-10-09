"""SEC-X2-GRANT-FRESHNESS-R0 · la autoridad del grant se juzga con la hora de la DECISIÓN, no la del inicio de la
transacción.

    UN PERMISO QUE YA VENCIÓ NO SIGUE VIVO PORQUE EL CRON EMPEZÓ ANTES

`autorizar_efecto_reenganche` comprobaba `granted_at <= now() AND expires_at > now()` y reservaba con
`used_at = now()`. En PostgreSQL `now()` es el INICIO de la transacción. El cron decide dentro de la transacción que
abrió al leer la primera página del barrido (SEC-X2-SCAN-FAIRNESS-R0 recorre todo el universo, así que puede durar);
con `now()`, un grant que venció durante ese recorrido seguía «vigente» y uno que entró en vigor no se veía
(NO_GRANT). Ahora la vigencia y el consumo usan `statement_timestamp()`: la hora de ESA sentencia, estable dentro de
ella (la condición y `used_at` usan el mismo instante, así que `used_at >= granted_at`, CHECK de la 038, se cumple;
una implementación MIXTA —condición fresca, `used_at = now()`— lo violaría, y lo atrapan test_2/test_3/test_8).

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
    """El primero reserva y retiene su transacción. Cada grant se consume UNA vez.

    SEC-X2-CONSENT-SERIALIZATION-R0 (actualización esperada, D-CRON = B): el segundo ya NO espera el bloqueo de
    fila —la espera era justo la ventana de GF-R1—. Encuentra el cerrojo de consentimiento de la sesión ocupado y
    no decide: ERROR inmediato (el cron lo omite), sin consumir nada. Antes: esperaba y daba NO_GRANT."""
    sid, _ = await _lead_con_grant(base)

    async def worker(espera, retiene):
        async with base() as db:
            await db.execute(text("SELECT 1"))          # conectado ANTES de medir
            await asyncio.sleep(espera)
            reloj = asyncio.get_running_loop().time
            t = reloj()
            estado = await _decide(db, sid, reservar=True)
            duro = reloj() - t
            await asyncio.sleep(retiene)
            await db.commit()
            return estado, duro
    (a, _), (b, espera_b) = await asyncio.wait_for(asyncio.gather(worker(0, 1.5), worker(0.4, 0)), 30)
    assert (a, b) == (AUTH, EstadoAutorizacion.ERROR), (a, b)
    assert espera_b < 0.5, f"el segundo worker ESPERÓ ({espera_b:.2f} s): la reserva no debe esperar (D-CRON = B)"
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


class _Filas:
    def __init__(self, filas):
        self._f = filas

    def mappings(self):
        return self

    def all(self):
        return list(self._f)


class _ConInicio:
    """Envuelve la sesión del barrido y captura el `corte` de su primera página: corte + 48 h = `now()` de la
    transacción del barrido (t0). Con eso la prueba verifica su PROPIA precondición (t0 antes del borde del grant)."""

    def __init__(self, db):
        self._db, self.corte = db, None

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "FROM lead_actividad" in sql and "ORDER BY ultima_actividad" in sql:
            filas = (await self._db.execute(stmt, params)).mappings().all()
            if self.corte is None and filas:
                self.corte = filas[0]["corte"]
            return _Filas(filas)
        return await self._db.execute(stmt, params)

    async def commit(self):
        await self._db.commit()

    async def rollback(self):
        await self._db.rollback()


async def _barrer(Sesion):
    """Devuelve (resumen, t0): t0 = el `now()` de la transacción en la que el barrido decide."""
    from datetime import timedelta
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
    async with Sesion() as db:
        espia = _ConInicio(db)
        res = await asyncio.wait_for(cron.escanear_reenganches(espia), 120)
    assert espia.corte is not None, "el barrido no leyó ninguna página"
    return res, espia.corte + timedelta(hours=48)


@pg
async def test_7_el_barrido_no_reserva_un_grant_que_vencio_durante_el_recorrido(monkeypatch, base, entorno):
    """El barrido abre su transacción al leer la primera página (t0); el grant vence durante la fase de lectura
    (t1); la reserva (t2) responde NO_GRANT: ni aviso al comprador, ni grant consumido, ni marca."""
    sid, _ = await _lead_con_grant(base)
    await _mover(base, sid, "expires_at = now() + interval '2 seconds'")
    _lenta(entorno, monkeypatch, 3)
    res, t0 = await _barrer(base)
    vence = min(g["expires_at"] for g in await _grants_completos(base, sid))
    assert t0 < vence, f"precondición: el barrido empezó DESPUÉS del vencimiento ({t0} ≥ {vence}); la prueba no mide nada"
    assert res.get("comprador", 0) == 0 and entorno["email"] == [] and entorno["push"] == []
    assert await _usados(base, sid) == [None, None]
    assert (await _fila(base, sid))["reenganche_enviado_en"] is None


@pg
async def test_8_el_barrido_ve_un_grant_que_entro_en_vigor_durante_el_recorrido(monkeypatch, base, entorno):
    """El inverso de punta a punta: el grant rige desde t1, dentro del recorrido; a t2 se reserva y el comprador
    recibe (con now() habría sido NO_GRANT: la vigencia se juzgaba con el inicio del barrido)."""
    sid, _ = await _lead_con_grant(base)
    await _mover(base, sid, "granted_at = now() + interval '2 seconds'")
    _lenta(entorno, monkeypatch, 3)
    res, t0 = await _barrer(base)
    rige = min(g["granted_at"] for g in await _grants_completos(base, sid))
    assert t0 < rige, f"precondición: el barrido empezó DESPUÉS de que el grant rigiera ({t0} ≥ {rige}); no mide nada"
    assert res.get("comprador", 0) == 1
    for g in await _grants_completos(base, sid):
        assert g["used_at"] is not None and g["used_at"] >= g["granted_at"]
