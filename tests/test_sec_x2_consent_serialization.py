"""SEC-X2-CONSENT-SERIALIZATION-R0 · UNA SESIÓN = UNA FRONTERA DE SERIALIZACIÓN DE SU AUTORIDAD.

    SÍ / NO / SUSTITUCIÓN / RESERVA NO PUEDEN OBSERVARSE COMO ESCRITURAS INDEPENDIENTES SOBRE LA MISMA AUTORIDAD.

Cierra los tres residuales del SECURITY POSTCHECK (reproducidos en `85ad3c3` con la sonda del postcheck):
  · RF-R1 · un «no» concurrente respondía «desactivado» con el grant del «sí» VIVO;
  · RF-R2 · «sí» (lead_actividad → consent_grant) y «no» (consent_grant → lead_actividad) formaban un ciclo (40P01);
  · GF-R1 · la reserva del cron esperaba la fila de un titular que ABORTABA y consumía un grant VENCIDO.

Mecanismo (`app/serial_consentimiento.py`): `pg_advisory_xact_lock(ESPACIO, hashtext(session_id))` bloqueante en los
caminos interactivos, tomado ANTES de tocar `lead_actividad` (incluido su DDL) y `consent_grant`; y la reserva del
cron con `pg_try_advisory_xact_lock` en una sentencia PROPIA y SIN ESPERA (D-CRON = B): sesión ocupada → ERROR → el
lead se omite en ese barrido (ninguna audiencia, sin marca, sin presupuesto) y el barrido siguiente lo reevalúa con
hora fresca.

PostgreSQL 15 REAL (`TEST_DATABASE_URL`), dos o más conexiones. Los «titulares» son los ENDPOINTS REALES detenidos a
mitad de su transacción (con el cerrojo tomado y lo escrito sin confirmar) por `_Pausa`, que envuelve una función que
el endpoint llama; el barrido es el REAL (`escanear_reenganches`). Sin la variable, todo se SALTA.
"""
from __future__ import annotations

import asyncio
import inspect
import re

import pytest
from sqlalchemy import event, text

import app.autoridad_reenganche as AR
import app.grant_reenganche as GR
import app.reenganche_cron as cron
import app.routers.chat as chat
import app.serial_consentimiento as SC
from app.autoridad_reenganche import EstadoAutorizacion, autorizar_efecto_reenganche
from tests.test_tr2_consentimiento import ACTIVO, PUSH, _dormida, _fila, _post, _sesion, base, pg  # noqa: F401
from tests.test_tr4_reenganche import entorno  # noqa: F401
from tests.test_tr5_consent_grant import _grants_completos

AUTH, NO, ERR = EstadoAutorizacion.AUTHORIZED, EstadoAutorizacion.NO_GRANT, EstadoAutorizacion.ERROR


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    from app.limiter import limiter
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    monkeypatch.setenv("REENGANCHE_BAJA_SECRET", "s" * 48)


_PAUSAS: list = []


@pytest.fixture
async def suelta(base):
    """Si una aserción falla con un titular detenido (o con una mutación aplicada), su transacción seguiría viva y el
    DROP SCHEMA de `base` esperaría para siempre. Depende de `base`, así que se desmonta ANTES: suelta (abortando)
    toda pausa pendiente."""
    yield
    pendientes = [p for p in _PAUSAS if not p._sigue.is_set()]
    for p in pendientes:
        p.soltar(abortar=True)
    _PAUSAS.clear()
    if pendientes:
        await asyncio.sleep(1.0)


# ── andamiaje ─────────────────────────────────────────────────────────────────────────────────────────────────────

class _Pausa:
    """Envuelve `modulo.nombre` (una función async que el endpoint llama DENTRO de su transacción). La PRIMERA llamada
    ejecuta la original y se DETIENE —con el cerrojo de consentimiento y lo escrito sin confirmar— hasta `soltar()`;
    `soltar(abortar=True)` hace que levante después, así que el endpoint deshace su transacción (titular que ABORTA).
    Las llamadas siguientes pasan directas."""

    def __init__(self, monkeypatch, modulo, nombre):
        self.dentro, self._sigue, self._abortar, self.n = asyncio.Event(), asyncio.Event(), False, 0
        _PAUSAS.append(self)
        original = getattr(modulo, nombre)

        async def envoltura(*a, **k):
            self.n += 1
            if self.n > 1:
                return await original(*a, **k)
            r = await original(*a, **k)
            self.dentro.set()
            await self._sigue.wait()
            if self._abortar:
                raise RuntimeError("el titular aborta")
            return r
        monkeypatch.setattr(modulo, nombre, envoltura)

    def soltar(self, abortar=False):
        self._abortar = abortar
        self._sigue.set()


def _pausa_si(monkeypatch):
    """El «sí» se detiene DESPUÉS de sustituir y crear sus grants (filas de grant y de lead_actividad sin confirmar)."""
    return _Pausa(monkeypatch, chat, "crear_grants_reenganche")


def _pausa_no(monkeypatch):
    """El «no» (y la baja) se detienen DESPUÉS de revocar (filas de grant sin confirmar), antes de lead_actividad."""
    return _Pausa(monkeypatch, chat, "revocar_grants_reenganche")


async def _si(sid, cab, email="c@ejemplo.invalid", push=True):
    return await _post(sid, cab, consent=True, email=email, **({"push_subscription": PUSH} if push else {}))


async def _no(sid, cab):
    return await _post(sid, cab, consent=False)


async def _lead(Sesion, email="c@ejemplo.invalid", *, grant=True, push=True):
    sid, cab = await _sesion(Sesion)
    await _dormida(Sesion, sid)
    if grant:
        r = await _si(sid, cab, email, push)
        assert r.json() == {"ok": True, "resultado": "activado"}
    return sid, cab


async def _vivos(Sesion, sid):
    return [g for g in await _grants_completos(Sesion, sid) if g["revoked_at"] is None and g["used_at"] is None]


async def _frontera(Sesion, sid):
    async with Sesion() as db:
        return (await autorizar_efecto_reenganche(db, session_id=sid, canales_candidatos=["EMAIL", "PUSH"],
                                                  reservar=False)).estado


_ESTA_BASE = "database = (SELECT oid FROM pg_database WHERE datname = current_database())"


async def _esperas(Sesion):
    """Tipos de bloqueo que alguien ESPERA ahora mismo en ESTA base de pruebas (no en todo el clúster: el arnés u
    otra base no pueden dar un falso aprobado). Los bloqueos de transacción (`transactionid`) no llevan base:
    se cuentan los de los backends conectados a esta base."""
    async with Sesion() as db:
        return sorted(r[0] for r in (await db.execute(text(
            "SELECT l.locktype FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
            "WHERE NOT l.granted AND a.datname = current_database()"))).all())


async def _esperas_advisory(Sesion):
    """Esperas del cerrojo de CONSENTIMIENTO (su espacio, forma de dos claves) en ESTA base."""
    async with Sesion() as db:
        return (await db.execute(text(
            "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted AND classid = :ns "
            f"AND objsubid = 2 AND {_ESTA_BASE}"), {"ns": SC.ESPACIO_CONSENTIMIENTO})).scalar()


async def _barrer(Sesion):
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
    async with Sesion() as db:
        return await cron.escanear_reenganches(db)


async def _espera_que(cond, hasta=5.0):
    fin = asyncio.get_running_loop().time() + hasta
    while asyncio.get_running_loop().time() < fin:
        if await cond():
            return True
        await asyncio.sleep(0.05)
    return False


# ══ A · SERIALIZACIÓN (RF-R1) ═════════════════════════════════════════════════════════════════════════════════════

@pg
async def test_01_si_primero_no_despues_el_no_espera_y_el_final_es_SIN_autoridad(monkeypatch, base, suelta):
    """I1 · el «sí» gana el cerrojo; el «no» ESPERA en el cerrojo (no en una fila) y, al obtenerlo, revoca lo que el
    «sí» confirmó: estado final = NO_GRANT, y «desactivado» es VERDAD (antes: «desactivado» con 1 grant vivo)."""
    sid, cab = await _lead(base, grant=False)
    pausa = _pausa_si(monkeypatch)
    t_si = asyncio.create_task(_si(sid, cab))
    await asyncio.wait_for(pausa.dentro.wait(), 10)
    t_no = asyncio.create_task(_no(sid, cab))
    assert await _espera_que(lambda: _esperas_advisory(base)), "el «no» no quedó esperando el cerrojo"
    assert not t_no.done()
    pausa.soltar()
    r_si, r_no = await asyncio.wait_for(asyncio.gather(t_si, t_no), 30)
    assert r_si.json()["resultado"] == "activado" and r_no.json()["resultado"] == "desactivado"
    assert await _vivos(base, sid) == [] and await _frontera(base, sid) is NO


@pg
async def test_02_no_primero_si_despues_el_final_es_CON_autoridad(monkeypatch, base, suelta):
    """I2 · el «no» gana el cerrojo y revoca lo visible; el «sí» espera y después crea: final = AUTHORIZED."""
    sid, cab = await _lead(base)
    pausa = _pausa_no(monkeypatch)
    t_no = asyncio.create_task(_no(sid, cab))
    await asyncio.wait_for(pausa.dentro.wait(), 10)
    t_si = asyncio.create_task(_si(sid, cab, "d@ejemplo.invalid"))
    assert await _espera_que(lambda: _esperas_advisory(base)), "el «sí» no quedó esperando el cerrojo"
    pausa.soltar()
    r_no, r_si = await asyncio.wait_for(asyncio.gather(t_no, t_si), 30)
    assert r_no.json()["resultado"] == "desactivado" and r_si.json()["resultado"] == "activado"
    vivos = await _vivos(base, sid)
    assert sorted(g["channel"] for g in vivos) == ["EMAIL", "PUSH"] and await _frontera(base, sid) is AUTH


@pg
async def test_03_sustitucion_concurrente_bajo_el_mismo_cerrojo(monkeypatch, base, suelta):
    """Dos «sí» de la misma sesión: el segundo espera, sustituye al primero y queda UNO vivo por canal; sin 500 ni
    choque con el índice único `consent_grant_vivo_por_canal`."""
    sid, cab = await _lead(base, grant=False)
    pausa = _pausa_si(monkeypatch)
    t1 = asyncio.create_task(_si(sid, cab, "a@ejemplo.invalid"))
    await asyncio.wait_for(pausa.dentro.wait(), 10)
    t2 = asyncio.create_task(_si(sid, cab, "b@ejemplo.invalid"))
    assert await _espera_que(lambda: _esperas_advisory(base))
    pausa.soltar()
    r1, r2 = await asyncio.wait_for(asyncio.gather(t1, t2), 30)
    assert r1.status_code == r2.status_code == 200
    gs = await _grants_completos(base, sid)
    assert sorted(g["channel"] for g in gs if g["revoked_at"] is None) == ["EMAIL", "PUSH"]
    assert sorted(g["channel"] for g in gs if g["revoked_at"] is not None) == ["EMAIL", "PUSH"]
    assert (await _fila(base, sid))["lead_email"] == "b@ejemplo.invalid", "el último acto manda"


@pg
async def test_04_la_reserva_no_decide_mientras_otro_cambia_la_autoridad(monkeypatch, base, suelta):
    """La reserva usa el MISMO cerrojo, sin esperar: con un «sí» en curso devuelve ERROR en el acto y no consume;
    al confirmarse el «sí», la reserva siguiente sí autoriza."""
    sid, cab = await _lead(base)
    pausa = _pausa_si(monkeypatch)
    t_si = asyncio.create_task(_si(sid, cab, "d@ejemplo.invalid"))
    await asyncio.wait_for(pausa.dentro.wait(), 10)
    async with base() as db:
        d = await asyncio.wait_for(autorizar_efecto_reenganche(
            db, session_id=sid, canales_candidatos=["EMAIL", "PUSH"], reservar=True), 0.5)
        await db.commit()
    assert d.estado is ERR
    pausa.soltar()
    await asyncio.wait_for(t_si, 30)
    assert all(g["used_at"] is None for g in await _grants_completos(base, sid))
    async with base() as db:
        d2 = await autorizar_efecto_reenganche(db, session_id=sid, canales_candidatos=["EMAIL", "PUSH"],
                                               reservar=True)
        await db.commit()
    assert d2.estado is AUTH


@pg
async def test_05_la_misma_sesion_se_serializa(base, suelta):
    """El helper: dos transacciones con el MISMO session_id → la segunda espera (visible en pg_locks) hasta el
    COMMIT de la primera."""
    sid = "qr-" + ACTIVO + "-misma"
    async with base() as a, base() as b:
        await SC.serializar_consentimiento(a, sid)
        t = asyncio.create_task(SC.serializar_consentimiento(b, sid))
        assert await _espera_que(lambda: _esperas_advisory(base)) and not t.done()
        await a.commit()
        await asyncio.wait_for(t, 5)
        await b.commit()


@pg
async def test_06_sesiones_distintas_no_se_serializan(monkeypatch, base, suelta):
    """Un «sí» detenido en S1 no frena un «sí» en S2 (ni al helper con otra sesión)."""
    s1, c1 = await _lead(base, grant=False)
    s2, c2 = await _lead(base, grant=False)
    pausa = _pausa_si(monkeypatch)
    t1 = asyncio.create_task(_si(s1, c1))
    await asyncio.wait_for(pausa.dentro.wait(), 10)
    r2 = await asyncio.wait_for(_si(s2, c2), 5)
    assert r2.json()["resultado"] == "activado" and not t1.done()
    async with base() as db:
        assert await asyncio.wait_for(SC.intentar_serializar_consentimiento(db, s2), 1) is True
        assert await SC.intentar_serializar_consentimiento(db, s1) is False
        await db.rollback()
    pausa.soltar()
    await asyncio.wait_for(t1, 30)


# ══ B · GF-R1 · el cron NO espera: sesión ocupada → omisión cerrada → el barrido siguiente reevalúa ═══════════════

async def _cron_con_titular(monkeypatch, base, entorno, *, abortar, vence=None):
    """Titular = un «no» REAL detenido tras revocar (filas de grant retenidas). Barrido 1 mientras retiene; después el
    titular confirma o ABORTA; barrido 2 sin contención. Devuelve todo lo observado."""
    sid, cab = await _lead(base)
    if vence is not None:
        async with base() as db:
            await db.execute(text("UPDATE consent_grant SET expires_at = now() + make_interval(secs => :v) "
                                  "WHERE session_id = :s"), {"s": sid, "v": vence})
            await db.commit()
    pausa = _pausa_no(monkeypatch)
    t_no = asyncio.create_task(_no(sid, cab))
    await asyncio.wait_for(pausa.dentro.wait(), 10)
    reloj = asyncio.get_running_loop().time
    t0 = reloj()
    b1 = asyncio.create_task(_barrer(base))
    await asyncio.sleep(1.0)
    b1_termino_con_el_titular_dentro = b1.done()
    if vence is not None:
        await asyncio.sleep(vence + 0.5)                               # el grant VENCE con el titular dentro
    pausa.soltar(abortar=abortar)
    r1 = await asyncio.wait_for(b1, 30)
    dur1 = reloj() - t0
    r_no = await asyncio.wait_for(t_no, 30)
    fila1 = await _fila(base, sid)
    usados1 = [g["used_at"] for g in await _grants_completos(base, sid)]
    correos1 = len(entorno["email"])
    r2 = await _barrer(base)
    return {"sid": sid, "r1": r1, "r2": r2, "r_no": r_no, "b1_sin_esperar": b1_termino_con_el_titular_dentro,
            "dur1": dur1, "fila1": fila1, "usados1": usados1, "correos1": correos1,
            "usados2": [g["used_at"] for g in await _grants_completos(base, sid)],
            "correos2": len(entorno["email"]), "fila2": await _fila(base, sid)}


def _sin_marca(f):
    return f["reenganche_enviado_en"] is None and f["reenganche_grupo"] is None and f["reenganche_elegible_en"] is None


@pg
async def test_07_titular_CONFIRMA_cron_ocupado_y_despues_NO_GRANT(monkeypatch, base, suelta, entorno):
    o = await _cron_con_titular(monkeypatch, base, entorno, abortar=False)
    assert o["b1_sin_esperar"] and o["r1"]["comprador"] == 0 and o["correos1"] == 0
    assert o["r_no"].json()["resultado"] == "desactivado"
    assert o["r2"]["comprador"] == 0 and o["correos2"] == 0, "revocado: el barrido siguiente da NO_GRANT"
    assert all(u is None for u in o["usados2"])


@pg
async def test_08_titular_ABORTA_cron_ocupado_y_el_siguiente_reevalua(monkeypatch, base, suelta, entorno):
    """Control: el titular aborta y el grant sigue VIGENTE → el barrido 1 no decide; el 2 sí avisa. Ocupado = diferido,
    no perdido ni decidido con autoridad vieja."""
    o = await _cron_con_titular(monkeypatch, base, entorno, abortar=True)
    assert o["r_no"].status_code == 500
    assert o["b1_sin_esperar"] and o["r1"]["comprador"] == 0 and o["correos1"] == 0
    assert all(u is None for u in o["usados1"])
    assert o["r2"]["comprador"] == 1 and o["correos2"] == 1


@pg
async def test_09_el_grant_VENCE_mientras_el_titular_tiene_el_cerrojo_GF_R1(monkeypatch, base, suelta, entorno):
    """GF-R1 discriminante (antes: AUTHORIZED con el grant vencido y 1 correo + 1 push). El titular retiene, el grant
    vence, el titular ABORTA: el barrido 1 no decide, el 2 ve el grant VENCIDO con hora fresca → NO_GRANT."""
    o = await _cron_con_titular(monkeypatch, base, entorno, abortar=True, vence=2)
    assert o["b1_sin_esperar"] and o["r1"]["comprador"] == 0
    assert o["r2"]["comprador"] == 0 and o["correos2"] == 0 and not entorno["push"]
    assert all(u is None for u in o["usados2"]), "se consumió un grant vencido"


@pg
async def test_10_el_cron_no_espera(monkeypatch, base, suelta, entorno):
    o = await _cron_con_titular(monkeypatch, base, entorno, abortar=False)
    assert o["b1_sin_esperar"], "el barrido esperó al titular (D-CRON = B: nunca espera)"


@pg
async def test_11_el_cron_ocupado_no_marca(monkeypatch, base, suelta, entorno):
    o = await _cron_con_titular(monkeypatch, base, entorno, abortar=True)
    assert _sin_marca(o["fila1"]), o["fila1"]


@pg
async def test_12_el_cron_ocupado_no_consume_presupuesto(monkeypatch, base, suelta, entorno):
    """Presupuesto 1. El lead ocupado va PRIMERO en el cursor; el segundo (libre y autorizado) igual recibe: la
    omisión no gastó la unidad."""
    monkeypatch.setenv("REENGANCHE_CRON_LIMITE", "1")
    ocupado, cab = await _lead(base, "ocupado@ejemplo.invalid", push=False)
    libre, _ = await _lead(base, "libre@ejemplo.invalid", push=False)
    async with base() as db:
        await db.execute(text("UPDATE lead_actividad SET ultima_actividad = now() - interval '9 days' "
                              "WHERE session_id = :s"), {"s": ocupado})
        await db.commit()
    pausa = _pausa_no(monkeypatch)
    t_no = asyncio.create_task(_no(ocupado, cab))
    await asyncio.wait_for(pausa.dentro.wait(), 10)
    r = await asyncio.wait_for(_barrer(base), 10)
    pausa.soltar(abortar=True)
    await asyncio.wait_for(t_no, 30)
    assert r["comprador"] == 1 and [e["to"] for e in entorno["email"]] == ["libre@ejemplo.invalid"]
    assert _sin_marca(await _fila(base, ocupado))


@pg
async def test_13_el_cron_ocupado_no_escribe_used_at(monkeypatch, base, suelta, entorno):
    o = await _cron_con_titular(monkeypatch, base, entorno, abortar=True)
    assert all(u is None for u in o["usados1"])


@pg
async def test_14_el_barrido_siguiente_obtiene_el_cerrojo(monkeypatch, base, suelta, entorno):
    o = await _cron_con_titular(monkeypatch, base, entorno, abortar=True)
    assert o["r2"]["comprador"] == 1 and all(u is not None for u in o["usados2"]), "el barrido 2 no decidió"


@pg
async def test_15_el_barrido_siguiente_ve_el_grant_expirado_NO_GRANT(monkeypatch, base, suelta, entorno):
    o = await _cron_con_titular(monkeypatch, base, entorno, abortar=True, vence=2)
    assert await _frontera(base, o["sid"]) is NO and all(u is None for u in o["usados2"])
    assert _sin_marca(o["fila2"])


# ══ C · RF-R2 · el ciclo ya no existe ════════════════════════════════════════════════════════════════════════════

@pg
async def test_16_no_hay_ciclo_si_no_en_ningun_orden(monkeypatch, base, suelta):
    """Los dos órdenes del ciclo de RF-R2. El segundo espera SOLO el cerrojo (ningún bloqueo de fila/transacción en
    espera): no llegó a tocar las filas que el primero retiene. Los dos terminan 200 y el final sigue el orden."""
    for primero in ("no", "si"):
        sid, cab = await _lead(base)
        pausa = _pausa_no(monkeypatch) if primero == "no" else _pausa_si(monkeypatch)
        t1 = asyncio.create_task(_no(sid, cab) if primero == "no" else _si(sid, cab, "e@ejemplo.invalid"))
        await asyncio.wait_for(pausa.dentro.wait(), 10)
        t2 = asyncio.create_task(_si(sid, cab, "f@ejemplo.invalid") if primero == "no" else _no(sid, cab))
        assert await _espera_que(lambda: _esperas_advisory(base))
        assert await _esperas(base) == ["advisory"], f"{primero}: el segundo espera algo más que el cerrojo"
        pausa.soltar()
        r1, r2 = await asyncio.wait_for(asyncio.gather(t1, t2), 30)
        assert r1.status_code == r2.status_code == 200, (primero, r1.text, r2.text)
        assert (await _frontera(base, sid)) is (AUTH if primero == "no" else NO), primero


@pg
async def test_17_no_hay_ciclo_si_con_DDL_y_cron(monkeypatch, base, suelta, entorno, caplog):
    """La trampa D.2 del preflight: el cron retiene AccessShare sobre lead_actividad desde su fase 1; un «sí» con el
    DDL pendiente (`_lead_actividad_ready=False`) toma el cerrojo y queda esperando ACCESS EXCLUSIVE detrás del cron.
    Si el cron ESPERARA el cerrojo, ciclo duro. Con try-lock: el cron omite la sesión, confirma, y el «sí» termina."""
    import logging
    caplog.set_level(logging.WARNING, logger="app.autoridad_reenganche")
    sid, cab = await _lead(base)
    dentro, sigue = asyncio.Event(), asyncio.Event()
    _PAUSAS.append(type("P", (), {"_sigue": sigue, "soltar": lambda self, abortar=False: sigue.set()})())
    intencion = chat.intencion_de_sesion

    async def intencion_lenta(*a, **k):
        if not dentro.is_set():
            dentro.set()
            await sigue.wait()                              # el cron, detenido en su fase 1 (AccessShare retenido)
        return await intencion(*a, **k)
    monkeypatch.setattr(chat, "intencion_de_sesion", intencion_lenta)
    b = asyncio.create_task(_barrer(base))
    await asyncio.wait_for(dentro.wait(), 10)
    monkeypatch.setattr(chat, "_lead_actividad_ready", False)   # el «sí» de un proceso que aún no preparó la tabla
    t_si = asyncio.create_task(_si(sid, cab, "g@ejemplo.invalid"))

    async def si_espera_la_tabla():
        async with base() as db:
            return bool((await db.execute(text(
                "SELECT 1 FROM pg_locks WHERE NOT granted AND locktype = 'relation' "
                f"AND mode = 'AccessExclusiveLock' AND relation = to_regclass('lead_actividad') AND {_ESTA_BASE}"
            ))).first())
    assert await _espera_que(si_espera_la_tabla), "precondición: el «sí» no llegó a esperar ACCESS EXCLUSIVE"
    sigue.set()
    r = await asyncio.wait_for(b, 30)
    # Sin inferencia temporal (no depende de `deadlock_timeout`): el cron llegó a la sesión y la encontró OCUPADA
    # (el aviso de BUSY), sin que su frontera fallara. Un cron que ESPERARA el cerrojo formaría el ciclo duro: o
    # Postgres lo aborta a él (la frontera «falló» por 40P01, sin aviso de BUSY) o aborta al «sí» (500).
    mensajes = [x.getMessage() for x in caplog.records if x.name == "app.autoridad_reenganche"]
    assert any("sesión ocupada" in m for m in mensajes), mensajes
    assert not any("frontera de autoridad falló" in m for m in mensajes), mensajes
    r_si = await asyncio.wait_for(t_si, 30)
    assert r_si.status_code == 200 and r_si.json()["resultado"] == "activado", r_si.text
    assert r["comprador"] == 0 and not entorno["email"], "el cron decidió sobre una sesión ocupada"
    assert all(g["used_at"] is None for g in await _grants_completos(base, sid))


@pg
async def test_18_no_hay_ciclo_no_con_cron(monkeypatch, base, suelta, entorno):
    o = await _cron_con_titular(monkeypatch, base, entorno, abortar=False)
    assert o["b1_sin_esperar"] and o["r_no"].status_code == 200 and o["r1"]["comprador"] == 0


@pg
async def test_23_la_reserva_revalida_DESPUES_de_obtener_el_cerrojo(monkeypatch, base, suelta):
    """Lo que valía ANTES del cerrojo no autoriza: si un «no» completo se confirma justo antes de que la reserva
    obtenga el cerrojo, la sentencia de reserva (posterior al cerrojo) ve el grant revocado → NO_GRANT, sin consumo.

    El «no» interno corre en SU propia conexión con `lock_timeout` de PostgreSQL: con el código correcto termina en
    el acto (la reserva todavía no retiene nada); si la reserva ya retuviera filas de grant ANTES del cerrojo (M8),
    el «no» no puede completar, Postgres lo corta en 2 s (55P03), su transacción se revierte y la conexión se cierra:
    la prueba falla rápido y sin dejar nada vivo (antes: un ciclo entre la prueba y la base, invisible para Postgres)."""
    from sqlalchemy.exc import DBAPIError
    sid, cab = await _lead(base)
    original = AR.intentar_serializar_consentimiento
    cortado: list = []

    async def con_un_no_justo_antes(db, s):
        async with base() as otra:                          # otro acto, completo y confirmado, con límite en PG
            try:
                await otra.execute(text("SET LOCAL lock_timeout = '2s'"))
                await chat._reducir_autoridad_reenganche(otra, sid, cerrar=False)
                await otra.commit()
            except DBAPIError as exc:
                await otra.rollback()
                cortado.append(type(getattr(exc, "orig", exc)).__name__)
                raise AssertionError("el «no» no pudo completar: la reserva retenía filas ANTES del cerrojo")
        return await original(db, s)
    monkeypatch.setattr(AR, "intentar_serializar_consentimiento", con_un_no_justo_antes)
    async with base() as db:
        d = await autorizar_efecto_reenganche(db, session_id=sid, canales_candidatos=["EMAIL", "PUSH"],
                                              reservar=True)
        await db.commit()
    assert not cortado, f"el «no» interno fue cortado por lock_timeout: {cortado}"
    assert d.estado is NO and all(g["used_at"] is None for g in await _grants_completos(base, sid))


# ══ R1 · SAVEPOINT y frescura después de una espera ═══════════════════════════════════════════════════════════════

async def _cerrojo_libre(Sesion, sid):
    """¿Otra conexión (en autocommit de una sentencia) puede tomar AHORA el cerrojo de la sesión?"""
    async with Sesion() as db:
        libre = await SC.intentar_serializar_consentimiento(db, sid)
        await db.rollback()
    return libre


@pg
async def test_25_NO_GRANT_suelta_el_cerrojo_AUTHORIZED_lo_conserva(base, suelta):
    """R1 · el barrido retiene cerrojo SOLO de las sesiones cuya autoridad reservó. Con la transacción del barrido
    ABIERTA: tras un NO_GRANT el cerrojo de esa sesión ya está libre; tras un AUTHORIZED sigue tomado hasta el
    COMMIT. Antes de R1, cada lead sin grant retenía su cerrojo hasta el COMMIT, sin cota."""
    sin_grant, _ = await _lead(base, grant=False)
    con_grant, _ = await _lead(base)
    async with base() as db:
        d1 = await autorizar_efecto_reenganche(db, session_id=sin_grant, canales_candidatos=["EMAIL"], reservar=True)
        d2 = await autorizar_efecto_reenganche(db, session_id=con_grant, canales_candidatos=["EMAIL", "PUSH"],
                                               reservar=True)
        assert (d1.estado, d2.estado) == (NO, AUTH)
        assert await _cerrojo_libre(base, sin_grant) is True, "NO_GRANT retuvo el cerrojo"
        assert await _cerrojo_libre(base, con_grant) is False, "AUTHORIZED soltó el cerrojo antes del COMMIT"
        await db.commit()
    assert await _cerrojo_libre(base, con_grant) is True
    assert all(g["used_at"] is not None for g in await _grants_completos(base, con_grant))


@pg
async def test_26_BUSY_deshace_el_savepoint_y_la_transaccion_sigue_sana(monkeypatch, base, suelta):
    """BUSY → ERROR sin efectos: no queda savepoint colgado, la transacción del barrido sigue usable y lo que ya
    había reservado (otra sesión, AUTHORIZED) se conserva con su cerrojo.

    La transacción del «barrido» lleva `lock_timeout` de PostgreSQL: con el código correcto no espera nada; si una
    mutación dejara a la reserva esperar las filas del titular detenido, Postgres la corta en 2 s y la prueba falla
    rápido (sin un ciclo entre la prueba y la base)."""
    previa, _ = await _lead(base)
    ocupada, cab = await _lead(base)
    pausa = _pausa_no(monkeypatch)
    t_no = asyncio.create_task(_no(ocupada, cab))
    await asyncio.wait_for(pausa.dentro.wait(), 10)
    motor = base.kw["bind"].sync_engine
    vistas: list[str] = []

    def anota(conn, cursor, statement, *a):
        if "reserva_reenganche" in statement or "pg_try_advisory_xact_lock" in statement \
                or "UPDATE consent_grant SET used_at" in statement:
            vistas.append(statement)
    async with base() as db:
        await db.execute(text("SET LOCAL lock_timeout = '2s'"))
        event.listen(motor, "before_cursor_execute", anota)
        try:
            d1 = await autorizar_efecto_reenganche(db, session_id=previa, canales_candidatos=["EMAIL", "PUSH"],
                                                   reservar=True)
            d2 = await autorizar_efecto_reenganche(db, session_id=ocupada, canales_candidatos=["EMAIL", "PUSH"],
                                                   reservar=True)
        finally:
            event.remove(motor, "before_cursor_execute", anota)
        assert (d1.estado, d2.estado) == (AUTH, ERR)
        # La secuencia exacta: AUTHORIZED libera su savepoint; BUSY lo DESHACE y lo libera. Ninguno queda colgado.
        etapas = ["try" if "pg_try_advisory" in q else "reserva" if "UPDATE consent_grant" in q
                  else q.split(" reserva_reenganche")[0] for q in vistas]
        assert etapas == ["SAVEPOINT", "try", "reserva", "RELEASE SAVEPOINT",
                          "SAVEPOINT", "try", "ROLLBACK TO SAVEPOINT", "RELEASE SAVEPOINT"], etapas
        assert (await db.execute(text("SELECT 1"))).scalar() == 1, "la transacción quedó abortada"
        assert await _cerrojo_libre(base, previa) is False
        await db.commit()
    pausa.soltar(abortar=True)
    await asyncio.wait_for(t_no, 30)
    assert all(g["used_at"] is not None for g in await _grants_completos(base, previa))
    assert all(g["used_at"] is None for g in await _grants_completos(base, ocupada))


@pg
async def test_27_una_espera_de_RELACION_antes_del_Execute_nace_con_hora_fresca(base, suelta):
    """Comportamiento OBSERVADO (no es la prueba de `vigente_ahora`; esa es test_28): con el protocolo de asyncpg
    (extendido), una espera de bloqueo de RELACIÓN —aquí un ACCESS EXCLUSIVE sobre `lead_actividad` que no coopera—
    ocurre ANTES del Execute, así que la sentencia de reserva recibe un `statement_timestamp()` POSTERIOR a la espera:
    un grant que venció durante ella ya no cumple el WHERE → NO_GRANT, `used_at` NULL. Coincide en PG 15.19 y 17.6
    (evidencia/…/sonda_reloj_relacion_pg15.txt y _pg17.txt); no se afirma para otros drivers ni protocolos."""
    sid, _ = await _lead(base)
    async with base() as db:
        await db.execute(text("UPDATE consent_grant SET expires_at = now() + interval '1500 milliseconds' "
                              "WHERE session_id = :s"), {"s": sid})
        await db.commit()
    titular = base()
    try:
        await titular.execute(text("LOCK TABLE lead_actividad IN ACCESS EXCLUSIVE MODE"))
        async with base() as db:
            t = asyncio.create_task(autorizar_efecto_reenganche(
                db, session_id=sid, canales_candidatos=["EMAIL", "PUSH"], reservar=True))

            async def reserva_espera_la_tabla():
                async with base() as d:
                    return bool((await d.execute(text(
                        "SELECT 1 FROM pg_locks WHERE NOT granted AND locktype = 'relation' "
                        f"AND relation = to_regclass('lead_actividad') AND {_ESTA_BASE}"))).first())
            assert await _espera_que(reserva_espera_la_tabla), "precondición: la reserva no esperó la relación"
            await asyncio.sleep(2.0)                                     # el grant VENCE durante la espera
            await titular.rollback()
            d = await asyncio.wait_for(t, 15)
            await db.commit()
    finally:
        await titular.close()
    assert d.estado is NO, d
    assert all(g["used_at"] is None for g in await _grants_completos(base, sid)), "se consumió un grant vencido"


@pg
async def test_28_vencido_durante_una_espera_de_FILA_la_defensa_deshace_la_reserva(base, suelta):
    """La carrera que cubre `RETURNING expires_at > clock_timestamp() AS vigente_ahora` (y que discrimina M17).

    A · un escritor que NO coopera con el cerrojo bloquea la fila del grant (`SELECT … FOR UPDATE`, sin advisory).
    B · la reserva obtiene el advisory (nadie más lo tiene) e INICIA su sentencia ANTES del vencimiento: su WHERE se
        evalúa con ese `statement_timestamp()` y queda ESPERANDO la fila (la espera de fila ocurre DURANTE el Execute).
    El grant VENCE durante la espera. A hace ROLLBACK: Postgres sigue con la tupla original SIN re-evaluar el WHERE
    (el mecanismo original de GF-R1). Con la defensa: `vigente_ahora = false` → ROLLBACK TO SAVEPOINT → NO_GRANT,
    `used_at` NULL y el advisory de B (tomado dentro del savepoint) ya está libre. Sin ella (M17): AUTHORIZED.

    Sincronización determinista por la base (no solo sleeps): A tiene el bloqueo; B espera un bloqueo de FILA (su pid
    en pg_locks/pg_stat_activity); la sentencia de B empezó ANTES de `expires_at`; el vencimiento ocurrió ANTES de
    soltar A. `lock_timeout` local en B y limpieza explícita de A.

    R2 (actualización esperada): una fila que deja de estar vigente durante la reserva es AUTORIDAD INESTABLE → ERROR
    (antes de R2: NO_GRANT). El resto no cambia: nada consumido y el advisory del savepoint libre."""
    sid, _ = await _lead(base)
    async with base() as db:
        await db.execute(text("UPDATE consent_grant SET expires_at = clock_timestamp() + interval '3 seconds' "
                              "WHERE session_id = :s"), {"s": sid})
        await db.commit()

    async def una(q, p=None):
        async with base() as d:
            return (await d.execute(text(q), p or {})).first()

    titular = base()
    try:
        assert await titular.execute(text("SELECT 1 FROM consent_grant WHERE session_id = :s FOR UPDATE"),
                                     {"s": sid}) is not None                         # A: fila bloqueada, sin advisory
        async with base() as db:
            await db.execute(text("SET LOCAL lock_timeout = '20s'"))
            pid_b = (await db.execute(text("SELECT pg_backend_pid()"))).scalar()
            t = asyncio.create_task(autorizar_efecto_reenganche(
                db, session_id=sid, canales_candidatos=["EMAIL", "PUSH"], reservar=True))

            async def b_espera_la_fila():
                fila = await una("SELECT 1 FROM pg_stat_activity WHERE pid = :p AND wait_event_type = 'Lock' "
                                 "AND wait_event IN ('transactionid', 'tuple')", {"p": pid_b})
                return fila is not None
            assert await _espera_que(b_espera_la_fila, 10), "precondición: la reserva no llegó a esperar la fila"
            empezo_antes, = await una(
                "SELECT a.query_start < g.expires_at FROM pg_stat_activity a, consent_grant g "
                "WHERE a.pid = :p AND g.session_id = :s AND g.channel = 'EMAIL'", {"p": pid_b, "s": sid})
            assert empezo_antes, "precondición: la sentencia de reserva empezó DESPUÉS del vencimiento"

            async def ya_vencio():
                fila = await una("SELECT bool_and(expires_at < clock_timestamp()) FROM consent_grant "
                                 "WHERE session_id = :s", {"s": sid})
                return bool(fila[0])
            assert await _espera_que(ya_vencio, 10), "precondición: el grant no venció durante la espera"
            await titular.rollback()                                        # A aborta: B sigue sin re-evaluar
            d = await asyncio.wait_for(t, 15)
            libre_antes_del_commit = await _cerrojo_libre(base, sid)
            await db.commit()
    finally:
        await titular.rollback()
        await titular.close()
    assert d.estado is ERR, f"esperaba ERROR (autoridad inestable durante la reserva): {d}"
    assert all(g["used_at"] is None for g in await _grants_completos(base, sid)), "used_at persistió"
    assert libre_antes_del_commit, "el advisory tomado dentro del savepoint no se liberó"


@pg
async def test_29_autoridad_INESTABLE_no_es_NO_GRANT_ni_abre_la_rama_del_corredor(monkeypatch, base, suelta, entorno):
    """R2 · AUTORIDAD INESTABLE DURANTE LA RESERVA ≠ AUSENCIA DE AUTORIDAD.

    La sesión S tiene dos grants de actos y canales distintos —A (EMAIL) a punto de vencer, B (PUSH) vigente— y el
    hecho X2 del corredor (con NO_GRANT, la rama del corredor actuaría). Presupuesto 1 y un lead LIBRE (EMAIL)
    después de S en el cursor.

    Barrido 1: un escritor que NO coopera retiene la fila de A; la reserva de S (A + B) empieza ANTES del vencimiento
    y espera; A vence; el escritor aborta → `vigente_ahora` falso en A → ERROR para TODA la decisión: nada consumido
    (A y B con used_at NULL), ni comprador ni corredor para S, sin marca y SIN presupuesto (el lead libre lo usa).
    Barrido 2: foto fresca → A ya no aplica, B sigue → AUTHORIZED solo B: push al comprador, nada al corredor."""
    from tests.test_tr2_consentimiento import _pide_corredor
    monkeypatch.setenv("REENGANCHE_CRON_LIMITE", "1")
    sid, cab = await _sesion(base)
    await _dormida(base, sid)
    assert (await _post(sid, cab, consent=True, email="inestable@ejemplo.invalid")).json()["resultado"] == "activado"
    assert (await _post(sid, cab, consent=True, push_subscription=PUSH)).json()["resultado"] == "activado"
    vivos = await _vivos(base, sid)
    assert sorted(g["channel"] for g in vivos) == ["EMAIL", "PUSH"], "precondición: dos grants de actos distintos"
    await _pide_corredor(base, sid)
    libre, _ = await _lead(base, "libre@ejemplo.invalid", push=False)
    async with base() as db:
        await db.execute(text("UPDATE lead_actividad SET ultima_actividad = now() - interval '9 days' "
                              "WHERE session_id = :s"), {"s": sid})
        await db.execute(text("UPDATE consent_grant SET expires_at = clock_timestamp() + interval '4 seconds' "
                              "WHERE session_id = :s AND channel = 'EMAIL' AND revoked_at IS NULL"), {"s": sid})
        await db.commit()

    async def una(q, p=None):
        async with base() as d:
            return (await d.execute(text(q), p or {})).first()

    titular = base()
    try:
        await titular.execute(text("SELECT 1 FROM consent_grant WHERE session_id = :s AND channel = 'EMAIL' "
                                   "AND revoked_at IS NULL FOR UPDATE"), {"s": sid})   # A retenida, sin advisory
        b1 = asyncio.create_task(_barrer(base))

        async def reserva_espera_la_fila():
            return await una("SELECT 1 FROM pg_stat_activity WHERE datname = current_database() "
                             "AND wait_event_type = 'Lock' AND wait_event IN ('transactionid', 'tuple') "
                             "AND query LIKE '%UPDATE consent_grant SET used_at%'") is not None
        assert await _espera_que(reserva_espera_la_fila, 10), "precondición: la reserva de S no esperó la fila de A"
        empezo_antes, = await una(
            "SELECT a.query_start < g.expires_at FROM pg_stat_activity a, consent_grant g "
            "WHERE a.datname = current_database() AND a.wait_event_type = 'Lock' "
            "AND a.query LIKE '%UPDATE consent_grant SET used_at%' "
            "AND g.session_id = :s AND g.channel = 'EMAIL' AND g.revoked_at IS NULL", {"s": sid})
        assert empezo_antes, "precondición: la reserva empezó DESPUÉS del vencimiento de A"

        async def a_vencio():
            fila = await una("SELECT expires_at < clock_timestamp() FROM consent_grant WHERE session_id = :s "
                             "AND channel = 'EMAIL' AND revoked_at IS NULL", {"s": sid})
            return bool(fila[0])
        assert await _espera_que(a_vencio, 10), "precondición: A no venció durante la espera"
        await titular.rollback()                                   # el escritor aborta: la reserva sigue
        r1 = await asyncio.wait_for(b1, 30)
    finally:
        await titular.rollback()
        await titular.close()
    correos1 = [e["to"] for e in entorno["email"]]
    assert r1["comprador"] == 1 and correos1 == ["libre@ejemplo.invalid"], (r1, correos1)   # presupuesto intacto
    assert r1["corredores"] == 0 and r1["holdout"] == 0 and sid not in entorno["holdout"], r1
    assert not entorno["push"], "barrido 1: nadie recibe push"
    assert all(g["used_at"] is None for g in await _grants_completos(base, sid)), "barrido 1 consumió algo de S"
    assert _sin_marca(await _fila(base, sid))

    r2 = await _barrer(base)
    assert r2["comprador"] == 1 and r2["corredores"] == 0 and r2["holdout"] == 0, r2
    assert [e["to"] for e in entorno["email"]] == correos1, "barrido 2: no debía salir ningún correo"
    assert len(entorno["push"]) == 1 and "push.prueba.test/x" in str(entorno["push"][0]), entorno["push"]
    usados = {g["channel"]: g["used_at"] for g in await _grants_completos(base, sid) if g["revoked_at"] is None}
    assert usados["PUSH"] is not None and usados["EMAIL"] is None, usados


@pg
async def test_24_ocupado_no_es_NO_GRANT_el_corredor_tampoco_recibe(monkeypatch, base, suelta, entorno):
    """BUSY ≠ NO_GRANT: con el hecho X2 del corredor, un NO_GRANT del comprador deja pasar la rama del corredor;
    la sesión OCUPADA no decide para NINGUNA audiencia. Control: tras confirmarse la revocación, el barrido
    siguiente da NO_GRANT al comprador y el corredor SÍ recibe."""
    from tests.test_tr2_consentimiento import _pide_corredor
    sid, cab = await _lead(base)
    await _pide_corredor(base, sid)
    pausa = _pausa_no(monkeypatch)
    t_no = asyncio.create_task(_no(sid, cab))
    await asyncio.wait_for(pausa.dentro.wait(), 10)
    r1 = await asyncio.wait_for(_barrer(base), 10)
    corredor1, holdout1 = list(entorno["corredor"]), list(entorno["holdout"])
    pausa.soltar()
    await asyncio.wait_for(t_no, 30)
    assert r1["comprador"] == 0 and r1["corredores"] == 0 and r1["holdout"] == 0 and not entorno["email"]
    assert sid not in holdout1 and _sin_marca(await _fila(base, sid))
    r2 = await _barrer(base)
    assert r2["comprador"] == 0 and r2["corredores"] == 1, "control: con NO_GRANT real la rama B sí actúa"


# ══ D · FALLA CERRADO ═════════════════════════════════════════════════════════════════════════════════════════════

class _DbEspia:
    def __init__(self):
        self.sql = []

    async def execute(self, stmt, params=None):
        self.sql.append(str(stmt))
        raise AssertionError("no debía llegar SQL")


@pytest.mark.parametrize("malo", [None, "", "   ", 123, b"qr-x"])
async def test_19_session_id_invalida_falla_antes_del_SQL(malo):
    """`pg_advisory_xact_lock(ns, hashtext(NULL))` NO bloquea y NO falla (STRICT): NULL no puede llegar al SQL. El
    helper, los escritores y la reserva fallan cerrado sin ninguna sentencia de cerrojo ni de autoridad."""
    db = _DbEspia()
    with pytest.raises(SC.SesionNoSerializable):
        await SC.serializar_consentimiento(db, malo)
    with pytest.raises(SC.SesionNoSerializable):
        await SC.intentar_serializar_consentimiento(db, malo)
    with pytest.raises(SC.SesionNoSerializable):
        await GR.revocar_grants_reenganche(db, malo)
    assert db.sql == []

    class _DbReserva(_DbEspia):
        """Acepta to_regclass y las sentencias de SAVEPOINT; el try-lock responde «ocupada»; cualquier otra cosa
        (la reserva) es un error. Así la prueba alcanza de verdad la validación de la sesión."""
        async def execute(self, stmt, params=None):
            q = str(stmt)
            self.sql.append(q)

            class R:
                def __init__(self, v):
                    self.v = v

                def scalar(self):
                    return self.v
            if "to_regclass" in q:
                return R(True)
            if q.startswith(("SAVEPOINT", "ROLLBACK TO SAVEPOINT", "RELEASE SAVEPOINT")):
                return R(None)
            if "pg_try_advisory_xact_lock" in q:
                return R(False)
            raise AssertionError("no debía llegar SQL de reserva")

    # Control: con una sesión VÁLIDA el doble sí recorre SAVEPOINT → try-lock → ROLLBACK TO → RELEASE (ocupada).
    ok = _DbReserva()
    d_ok = await autorizar_efecto_reenganche(ok, session_id="qr-control", canales_candidatos=["EMAIL"], reservar=True)
    etapas = [q.split("(")[0].split(" reserva")[0] for q in ok.sql]
    assert d_ok.estado is ERR and etapas == ["SELECT to_regclass", "SAVEPOINT", "SELECT pg_try_advisory_xact_lock",
                                             "ROLLBACK TO SAVEPOINT", "RELEASE SAVEPOINT"], etapas
    # Con la sesión inválida: ERROR y la validación ocurre ANTES del SAVEPOINT (R2): ni savepoint, ni cerrojo, ni
    # reserva; solo la consulta previa de existencia de la tabla.
    dr = _DbReserva()
    d = await autorizar_efecto_reenganche(dr, session_id=malo, canales_candidatos=["EMAIL"], reservar=True)
    assert d.estado is ERR, d
    assert [q for q in dr.sql if "to_regclass" not in q] == [], dr.sql


# ══ E · estructura de la frontera ═════════════════════════════════════════════════════════════════════════════════

def _cuerpo(fn) -> str:
    return inspect.getsource(fn)


def test_20_los_unicos_escritores_de_consent_grant_pasan_por_la_frontera():
    """Inventario cerrado: en `app/` solo escriben `consent_grant` crear/revocar (grant_reenganche) y la reserva
    (autoridad_reenganche), y en cada una el cerrojo va ANTES de la primera sentencia sobre la tabla."""
    import pathlib
    raiz = pathlib.Path(__file__).resolve().parents[1] / "app"
    escritores = set()
    for py in raiz.rglob("*.py"):
        s = py.read_text(encoding="utf-8")
        if re.search(r"(INSERT\s+INTO|UPDATE|DELETE\s+FROM|TRUNCATE)\s+(public\.)?consent_grant\b", s):
            escritores.add(py.relative_to(raiz).as_posix())
    assert escritores == {"grant_reenganche.py", "autoridad_reenganche.py"}, escritores
    for fn, cerrojo in ((GR.crear_grants_reenganche, "serializar_consentimiento("),
                        (GR.revocar_grants_reenganche, "serializar_consentimiento("),
                        (AR._reservar, "intentar_serializar_consentimiento(")):
        c = _cuerpo(fn)
        i_sql = min(m.start() for m in re.finditer(r"UPDATE consent_grant|INSERT INTO consent_grant", c))
        assert cerrojo in c and c.index(cerrojo) < i_sql, fn.__name__
    # una sola definición de la clave y del espacio
    for py in raiz.rglob("*.py"):
        if py.name != "serial_consentimiento.py":
            assert "advisory" not in py.read_text(encoding="utf-8"), py.name


def test_21_ningun_camino_con_el_cerrojo_escribe_chat_sessions():
    for fn in (chat.lead_contacto, chat.baja_aviso, chat._reducir_autoridad_reenganche, GR.crear_grants_reenganche,
               GR.revocar_grants_reenganche, AR.autorizar_efecto_reenganche):
        assert not re.search(r"(UPDATE|INSERT\s+INTO|DELETE\s+FROM)\s+chat_sessions", _cuerpo(fn)), fn.__name__


@pg
async def test_22_el_cerrojo_precede_al_DDL_y_a_toda_sentencia_de_autoridad(monkeypatch, base, suelta):
    """Espía de sentencias en el «sí» (con el DDL pendiente), el «no» y la baja REALES: el cerrojo va antes de la
    primera sentencia sobre `lead_actividad` (ALTER incluido) y sobre `consent_grant`."""
    from app import baja_aviso
    motor = base.kw["bind"].sync_engine
    vistas: list[str] = []

    def anota(conn, cursor, statement, *a):
        vistas.append(statement)
    event.listen(motor, "before_cursor_execute", anota)
    try:
        sid, cab = await _lead(base, grant=False)
        for nombre, accion in (("si", lambda: _si(sid, cab)), ("no", lambda: _no(sid, cab)),
                               ("baja", None)):
            monkeypatch.setattr(chat, "_lead_actividad_ready", False)
            vistas.clear()
            if accion is None:
                from tests.test_tr2_consentimiento import _cliente
                async with _cliente() as c:
                    r = await c.post("/api/v1/chat/baja-aviso", json={"t": baja_aviso.emitir(sid), "accion": "cerrar"})
            else:
                r = await accion()
            assert r.status_code == 200, (nombre, r.text)
            i_lock = next(i for i, s in enumerate(vistas) if "pg_advisory_xact_lock" in s)
            materiales = [i for i, s in enumerate(vistas)
                          if re.search(r"(ALTER TABLE|INSERT INTO|UPDATE)\s+lead_actividad|"
                                       r"(INSERT INTO|UPDATE)\s+consent_grant", s)
                          and "CREATE TABLE IF NOT EXISTS" not in s]
            if nombre == "baja":   # su DDL va en una transacción PROPIA confirmada antes (ensure_lead_actividad)
                materiales = [i for i in materiales if "ALTER TABLE" not in vistas[i]]
            assert materiales and i_lock < min(materiales), (nombre, vistas[:12])
    finally:
        event.remove(motor, "before_cursor_execute", anota)
