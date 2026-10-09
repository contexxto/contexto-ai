"""SEC-X2-EGRESS-DESTINATION-FRESHNESS-R0 · GRANT RESERVADO + DESTINO DEL EFECTO = UNA MISMA FOTOGRAFÍA SERIALIZADA.

    AUTORIDAD FRESCA + DESTINO OBSOLETO ≠ EGRESO AUTORIZADO

El defecto (reproducido en e13a185): el barrido leía `lead_email`/`lead_push` en su fase 1, SIN el cerrojo, reservaba
la autoridad FRESCA bajo el cerrojo y enviaba al destino de la FASE 1: un «sí» que cambiaba `a@` → `b@` entre la fase 1
y la reserva hacía que se consumiera el grant de `b@` y el aviso saliera a `a@` (igual con la suscripción push).

Ahora la frontera (`autoridad_reenganche._reservar`) lee el destino vigente de cada canal autorizado DESPUÉS de tomar
el cerrojo de la sesión y en la misma transacción que reservó los grants, y lo devuelve con AUTHORIZED
(`email_destino`/`push_destino`); el barrido envía EXACTAMENTE ahí (sin la copia de la fase 1 ni relectura tras el
COMMIT). D1: un canal reservado sin su destino → ERROR de la decisión entera. D2 (fuera de alcance, caracterizado):
los canales CANDIDATOS siguen saliendo de la fase 1.

PostgreSQL 15 REAL (`TEST_DATABASE_URL`), barrido REAL (`escanear_reenganches`) y endpoint REAL `/lead-contacto`;
barreras deterministas: el barrido se detiene en su fase 1 (tras leer la página) o justo tras su reserva AUTHORIZED.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest
from sqlalchemy import event, text

import app.autoridad_reenganche as AR
import app.notifications as notif
import app.reenganche_cron as cron
import app.routers.chat as chat
import app.serial_consentimiento as SC
from app.autoridad_reenganche import EstadoAutorizacion, autorizar_efecto_reenganche
from tests.test_tr2_consentimiento import _dormida, _fila, _post, _sesion, base, pg  # noqa: F401
from tests.test_tr4_reenganche import entorno  # noqa: F401
from tests.test_tr5_consent_grant import _grants_completos

AUTH, NO, ERR = EstadoAutorizacion.AUTHORIZED, EstadoAutorizacion.NO_GRANT, EstadoAutorizacion.ERROR
P1 = {"endpoint": "https://push.prueba.test/viejo", "keys": {"p256dh": "a", "auth": "b"}}
P2 = {"endpoint": "https://push.prueba.test/nuevo", "keys": {"p256dh": "c", "auth": "d"}}
_ESTA_BASE = "database = (SELECT oid FROM pg_database WHERE datname = current_database())"
_LEER_DESTINO = "SELECT lead_email, lead_push FROM lead_actividad"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    from app.limiter import limiter
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")


_SUELTAS: list = []


@pytest.fixture
async def suelta(base):
    """Suelta toda barrera pendiente ANTES del teardown de `base` (una aserción fallida no puede dejar un barrido o
    un endpoint detenido con bloqueos tomados)."""
    yield
    for ev in _SUELTAS:
        ev.set()
    _SUELTAS.clear()
    await asyncio.sleep(0.5)


# ── andamiaje ─────────────────────────────────────────────────────────────────────────────────────────────────────

async def _barrer(Sesion, gancho_commit=None):
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
    async with Sesion() as db:
        if gancho_commit is not None:
            original = db.commit

            async def commit():
                await original()
                await gancho_commit()
            db.commit = commit
        return await cron.escanear_reenganches(db)


def _pausa_fase1(monkeypatch):
    """El barrido se detiene en su fase 1, DESPUÉS de leer la página (con el destino de la fase 1)."""
    dentro, sigue = asyncio.Event(), asyncio.Event()
    _SUELTAS.append(sigue)
    original = chat.intencion_de_sesion

    async def lenta(*a, **k):
        if not dentro.is_set():
            dentro.set()
            await sigue.wait()
        return await original(*a, **k)
    monkeypatch.setattr(chat, "intencion_de_sesion", lenta)
    return dentro, sigue


def _pausa_tras_reserva(monkeypatch):
    """El barrido se detiene justo DESPUÉS de una reserva AUTHORIZED (cerrojo retenido hasta su COMMIT)."""
    reservado, sigue = asyncio.Event(), asyncio.Event()
    _SUELTAS.append(sigue)
    original = AR.autorizar_efecto_reenganche

    async def autorizar_y_pausar(*a, **k):
        d = await original(*a, **k)
        if k.get("reservar") and d.estado is AUTH and not reservado.is_set():
            reservado.set()
            await sigue.wait()
        return d
    monkeypatch.setattr(AR, "autorizar_efecto_reenganche", autorizar_y_pausar)
    return reservado, sigue


async def _alguien_espera_el_cerrojo(Sesion):
    for _ in range(200):
        async with Sesion() as db:
            if (await db.execute(text(
                    "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' AND NOT granted "
                    f"AND classid = :ns AND {_ESTA_BASE}"), {"ns": SC.ESPACIO_CONSENTIMIENTO})).scalar():
                return True
        await asyncio.sleep(0.05)
    return False


async def _lead(Sesion, email=None, push=None):
    sid, cab = await _sesion(Sesion)
    await _dormida(Sesion, sid)
    cuerpo = {**({"email": email} if email else {}), **({"push_subscription": push} if push else {})}
    if cuerpo:
        assert (await _post(sid, cab, consent=True, **cuerpo)).json()["resultado"] == "activado"
    return sid, cab


async def _si(sid, cab, email=None, push=None):
    cuerpo = {**({"email": email} if email else {}), **({"push_subscription": push} if push else {})}
    return await _post(sid, cab, consent=True, **cuerpo)


def _correos(entorno):
    return [e["to"] for e in entorno["email"]]


def _pushes(entorno):
    return [str(p) for p in entorno["push"]]


async def _sql(Sesion, q, p=None):
    async with Sesion() as db:
        await db.execute(text(q), p or {})
        await db.commit()


def _por_canal(gs, canal):
    return [g for g in gs if g["channel"] == canal]


def _sin_marca(f):
    return f["reenganche_enviado_en"] is None and f["reenganche_grupo"] is None


# ══ A · el defecto: cambio de destino entre la fase 1 y la reserva (orden C) ══════════════════════════════════════

@pg
async def test_01_EMAIL_a_b_entre_fase1_y_reserva_sale_a_b_nunca_a(monkeypatch, base, suelta, entorno):
    sid, cab = await _lead(base, email="a@ejemplo.invalid")
    dentro, sigue = _pausa_fase1(monkeypatch)
    b = asyncio.create_task(_barrer(base))
    await asyncio.wait_for(dentro.wait(), 10)                        # fase 1 vio a@
    assert (await asyncio.wait_for(_si(sid, cab, email="b@ejemplo.invalid"), 10)).json()["resultado"] == "activado"
    sigue.set()
    res = await asyncio.wait_for(b, 30)
    gs = _por_canal(await _grants_completos(base, sid), "EMAIL")
    assert res["comprador"] == 1 and _correos(entorno) == ["b@ejemplo.invalid"], _correos(entorno)
    assert gs[0]["revoked_at"] is not None and gs[0]["used_at"] is None and gs[1]["used_at"] is not None


@pg
async def test_02_PUSH_viejo_nuevo_entre_fase1_y_reserva_sale_al_nuevo(monkeypatch, base, suelta, entorno):
    sid, cab = await _lead(base, push=P1)
    dentro, sigue = _pausa_fase1(monkeypatch)
    b = asyncio.create_task(_barrer(base))
    await asyncio.wait_for(dentro.wait(), 10)
    await asyncio.wait_for(_si(sid, cab, push=P2), 10)
    sigue.set()
    res = await asyncio.wait_for(b, 30)
    assert res["comprador"] == 1 and len(entorno["push"]) == 1
    assert "push.prueba.test/nuevo" in _pushes(entorno)[0] and "viejo" not in _pushes(entorno)[0]


@pg
async def test_03_cambio_ANTES_del_barrido_sale_al_nuevo(monkeypatch, base, suelta, entorno):
    sid, cab = await _lead(base, email="a@ejemplo.invalid")
    await _si(sid, cab, email="b@ejemplo.invalid")
    res = await _barrer(base)
    assert res["comprador"] == 1 and _correos(entorno) == ["b@ejemplo.invalid"]


@pg
async def test_04_los_dos_canales_cambian_entre_fase1_y_reserva(monkeypatch, base, suelta, entorno):
    sid, cab = await _lead(base, email="a@ejemplo.invalid", push=P1)
    dentro, sigue = _pausa_fase1(monkeypatch)
    b = asyncio.create_task(_barrer(base))
    await asyncio.wait_for(dentro.wait(), 10)
    await asyncio.wait_for(_si(sid, cab, email="b@ejemplo.invalid", push=P2), 10)
    sigue.set()
    await asyncio.wait_for(b, 30)
    assert _correos(entorno) == ["b@ejemplo.invalid"] and len(entorno["push"]) == 1
    assert "push.prueba.test/nuevo" in _pushes(entorno)[0]


@pg
async def test_04b_el_destino_se_lee_DESPUES_del_cerrojo(monkeypatch, base, suelta, entorno):
    """Un «sí» completo y confirmado justo ANTES de que la reserva obtenga el cerrojo (dentro de la misma decisión):
    el destino de los dos canales tiene que ser el que dejó ese acto. Una lectura previa al cerrojo (en la misma o en
    otra conexión) daría la foto vieja."""
    sid, cab = await _lead(base, email="a@ejemplo.invalid", push=P1)
    original = AR.intentar_serializar_consentimiento
    hecho: list = []

    async def con_un_si_justo_antes(db, s):
        if not hecho:
            hecho.append(True)
            assert (await _si(sid, cab, email="b@ejemplo.invalid", push=P2)).json()["resultado"] == "activado"
        return await original(db, s)
    monkeypatch.setattr(AR, "intentar_serializar_consentimiento", con_un_si_justo_antes)
    async with base() as db:
        d = await autorizar_efecto_reenganche(db, session_id=sid, canales_candidatos=["EMAIL", "PUSH"], reservar=True)
        await db.commit()
    assert d.estado is AUTH and d.email_destino == "b@ejemplo.invalid", d
    assert "push.prueba.test/nuevo" in str(d.push_destino), d


# ══ B · órdenes ya serializados (A, D) ═══════════════════════════════════════════════════════════════════════════

@pg
async def test_05_cron_PRIMERO_el_efecto_reservado_conserva_a(monkeypatch, base, suelta, entorno):
    """Orden A: el barrido reserva G_a con a@ y confirma; el cambio a b@ llega DESPUÉS: el efecto reservado salió a a@
    y G_b queda vivo (para el futuro), sin consumir."""
    sid, cab = await _lead(base, email="a@ejemplo.invalid")
    res = await _barrer(base)
    await _si(sid, cab, email="b@ejemplo.invalid")
    gs = _por_canal(await _grants_completos(base, sid), "EMAIL")
    assert res["comprador"] == 1 and _correos(entorno) == ["a@ejemplo.invalid"]
    assert gs[0]["used_at"] is not None and gs[1]["used_at"] is None and gs[1]["revoked_at"] is None


@pg
async def test_06_el_escritor_espera_el_cerrojo_del_cron_y_el_efecto_usa_la_foto_reservada(
        monkeypatch, base, suelta, entorno):
    """Orden D: con la reserva hecha (cerrojo retenido), un «sí» con b@ ESPERA el advisory; el efecto sale a a@ (la
    foto reservada); tras el COMMIT el «sí» aplica b@ y crea G_b vivo."""
    sid, cab = await _lead(base, email="a@ejemplo.invalid")
    reservado, sigue = _pausa_tras_reserva(monkeypatch)
    b = asyncio.create_task(_barrer(base))
    await asyncio.wait_for(reservado.wait(), 10)
    t_si = asyncio.create_task(_si(sid, cab, email="b@ejemplo.invalid"))
    assert await _alguien_espera_el_cerrojo(base), "el «sí» no esperó el cerrojo del barrido"
    sigue.set()
    await asyncio.wait_for(b, 30)
    assert (await asyncio.wait_for(t_si, 30)).json()["resultado"] == "activado"
    assert _correos(entorno) == ["a@ejemplo.invalid"]
    assert (await _fila(base, sid))["lead_email"] == "b@ejemplo.invalid"


# ══ C · multicanal y vínculo canal ↔ destino ═══════════════════════════════════════════════════════════════════════

@pg
async def test_07_solo_EMAIL(monkeypatch, base, suelta, entorno):
    await _lead(base, email="solo@ejemplo.invalid")
    res = await _barrer(base)
    assert res["comprador"] == 1 and _correos(entorno) == ["solo@ejemplo.invalid"] and not entorno["push"]


@pg
async def test_08_solo_PUSH(monkeypatch, base, suelta, entorno):
    await _lead(base, push=P1)
    res = await _barrer(base)
    assert res["comprador"] == 1 and not entorno["email"] and len(entorno["push"]) == 1
    assert "push.prueba.test/viejo" in _pushes(entorno)[0]


@pg
async def test_09_EMAIL_y_PUSH_cada_uno_a_su_destino(monkeypatch, base, suelta, entorno):
    sid, _ = await _lead(base, email="ambos@ejemplo.invalid", push=P1)
    async with base() as db:
        d = await autorizar_efecto_reenganche(db, session_id=sid, canales_candidatos=["EMAIL", "PUSH"], reservar=True)
        await db.rollback()
    assert d.estado is AUTH and d.email_destino == "ambos@ejemplo.invalid" and "viejo" in str(d.push_destino)
    res = await _barrer(base)
    assert res["comprador"] == 1 and _correos(entorno) == ["ambos@ejemplo.invalid"] and len(entorno["push"]) == 1


@pg
async def test_10_un_canal_cambia_y_el_otro_permanece(monkeypatch, base, suelta, entorno):
    sid, cab = await _lead(base, email="a@ejemplo.invalid", push=P1)
    dentro, sigue = _pausa_fase1(monkeypatch)
    b = asyncio.create_task(_barrer(base))
    await asyncio.wait_for(dentro.wait(), 10)
    await asyncio.wait_for(_si(sid, cab, push=P2), 10)              # solo PUSH cambia
    sigue.set()
    await asyncio.wait_for(b, 30)
    assert _correos(entorno) == ["a@ejemplo.invalid"] and "push.prueba.test/nuevo" in _pushes(entorno)[0]


# ══ D · D1: canal autorizado sin destino → ERROR de la decisión entera ════════════════════════════════════════════

@pg
async def test_11_D1_canal_autorizado_sin_destino_es_ERROR_sin_efecto_ni_marca(monkeypatch, base, suelta, entorno):
    """La fase 1 vio el destino; antes de la reserva desaparece (escritura directa de prueba: no hay escritor de la
    app que lo anule). La reserva EMAIL quedaría sin destino → ERROR: nada consumido, sin marca, sin corredor."""
    sid, _ = await _lead(base, email="a@ejemplo.invalid")
    dentro, sigue = _pausa_fase1(monkeypatch)
    b = asyncio.create_task(_barrer(base))
    await asyncio.wait_for(dentro.wait(), 10)
    await _sql(base, "UPDATE lead_actividad SET lead_email = NULL WHERE session_id = :s", {"s": sid})
    sigue.set()
    res = await asyncio.wait_for(b, 30)
    assert res["comprador"] == 0 and res["corredores"] == 0 and not entorno["email"] and not entorno["push"]
    assert all(g["used_at"] is None for g in await _grants_completos(base, sid))
    assert _sin_marca(await _fila(base, sid))


@pg
async def test_12_D1_con_dos_canales_ERROR_revierte_el_used_at_de_TODOS(base, suelta):
    sid, _ = await _lead(base, email="a@ejemplo.invalid", push=P1)
    await _sql(base, "UPDATE lead_actividad SET lead_push = NULL WHERE session_id = :s", {"s": sid})
    async with base() as db:
        d = await autorizar_efecto_reenganche(db, session_id=sid, canales_candidatos=["EMAIL", "PUSH"], reservar=True)
        await db.commit()
    assert d.estado is ERR and d.email_destino is None and d.push_destino is None, d
    gs = await _grants_completos(base, sid)
    assert sorted(g["channel"] for g in gs) == ["EMAIL", "PUSH"] and all(g["used_at"] is None for g in gs)


# ══ E · lo que NO puede salir ═════════════════════════════════════════════════════════════════════════════════════

@pg
async def test_13_un_destino_sin_grant_no_sale(monkeypatch, base, suelta, entorno):
    """Grant solo de EMAIL; la sesión TAMBIÉN tiene suscripción push (sin grant): solo sale el correo."""
    sid, _ = await _lead(base, email="a@ejemplo.invalid")
    await _sql(base, "UPDATE lead_actividad SET lead_push = CAST(:p AS jsonb) WHERE session_id = :s",
               {"s": sid, "p": '{"endpoint": "https://push.prueba.test/sin-grant", "keys": {"p256dh": "x", "auth": "y"}}'})
    res = await _barrer(base)
    assert res["comprador"] == 1 and _correos(entorno) == ["a@ejemplo.invalid"] and not entorno["push"]


@pg
async def test_14_un_canal_NO_candidato_no_recibe_destino_aunque_tenga_grant(base, suelta):
    sid, _ = await _lead(base, email="a@ejemplo.invalid", push=P1)
    async with base() as db:
        d = await autorizar_efecto_reenganche(db, session_id=sid, canales_candidatos=["EMAIL"], reservar=True)
        await db.commit()
    assert d.estado is AUTH and d.canales == frozenset({"EMAIL"}) and d.email_destino == "a@ejemplo.invalid"
    assert d.push_destino is None
    assert all(g["used_at"] is None for g in _por_canal(await _grants_completos(base, sid), "PUSH"))


# ══ F · BUSY / NO_GRANT / inestable / sin reserva: ningún destino ════════════════════════════════════════════════

@pg
async def test_15_BUSY_no_devuelve_destino_ni_lo_lee(base, suelta):
    sid, _ = await _lead(base, email="a@ejemplo.invalid")
    motor = base.kw["bind"].sync_engine
    leidas: list[str] = []

    def anota(conn, cursor, statement, *a):
        if statement.startswith(_LEER_DESTINO):
            leidas.append(statement)
    async with base() as titular:
        await SC.serializar_consentimiento(titular, sid)
        event.listen(motor, "before_cursor_execute", anota)
        try:
            async with base() as db:
                d = await autorizar_efecto_reenganche(db, session_id=sid, canales_candidatos=["EMAIL"], reservar=True)
                await db.commit()
        finally:
            event.remove(motor, "before_cursor_execute", anota)
        await titular.rollback()
    assert d.estado is ERR and d.email_destino is None and d.push_destino is None and leidas == []


@pg
async def test_16_NO_GRANT_no_devuelve_destino(base, suelta):
    sid, _ = await _lead(base)                                    # sin «sí»: sin grants
    await _sql(base, "UPDATE lead_actividad SET lead_email = 'x@ejemplo.invalid' WHERE session_id = :s", {"s": sid})
    async with base() as db:
        d = await autorizar_efecto_reenganche(db, session_id=sid, canales_candidatos=["EMAIL"], reservar=True)
        await db.commit()
    assert d.estado is NO and d.email_destino is None and d.push_destino is None


@pg
async def test_17_autoridad_INESTABLE_R2_sigue_siendo_ERROR_sin_destino(base, suelta):
    """Un escritor que no coopera retiene la fila del grant; el grant vence durante la espera; aborta → ERROR (R2),
    sin destino y sin consumo."""
    sid, _ = await _lead(base, email="a@ejemplo.invalid")
    await _sql(base, "UPDATE consent_grant SET expires_at = clock_timestamp() + interval '3 seconds' "
                     "WHERE session_id = :s", {"s": sid})
    titular = base()
    try:
        await titular.execute(text("SELECT 1 FROM consent_grant WHERE session_id = :s FOR UPDATE"), {"s": sid})
        async with base() as db:
            await db.execute(text("SET LOCAL lock_timeout = '20s'"))
            pid = (await db.execute(text("SELECT pg_backend_pid()"))).scalar()
            t = asyncio.create_task(autorizar_efecto_reenganche(
                db, session_id=sid, canales_candidatos=["EMAIL"], reservar=True))
            for _ in range(200):
                async with base() as o:
                    if (await o.execute(text("SELECT 1 FROM pg_stat_activity WHERE pid = :p AND wait_event_type = "
                                             "'Lock'"), {"p": pid})).first():
                        break
                await asyncio.sleep(0.05)
            for _ in range(200):
                async with base() as o:
                    if (await o.execute(text("SELECT bool_and(expires_at < clock_timestamp()) FROM consent_grant "
                                             "WHERE session_id = :s"), {"s": sid})).scalar():
                        break
                await asyncio.sleep(0.05)
            await titular.rollback()
            d = await asyncio.wait_for(t, 15)
            await db.commit()
    finally:
        await titular.rollback()
        await titular.close()
    assert d.estado is ERR and d.email_destino is None and d.push_destino is None, d
    assert all(g["used_at"] is None for g in await _grants_completos(base, sid))


@pg
async def test_20_reservar_False_no_devuelve_destinos(base, suelta):
    """Una consulta SIN reserva no es una fotografía autorizada de egreso: AUTHORIZED, pero sin destinos."""
    sid, _ = await _lead(base, email="a@ejemplo.invalid", push=P1)
    async with base() as db:
        d = await autorizar_efecto_reenganche(db, session_id=sid, canales_candidatos=["EMAIL", "PUSH"], reservar=False)
    assert d.estado is AUTH and d.email_destino is None and d.push_destino is None


# ══ G · COMMIT → envío con EXACTAMENTE el destino reservado ══════════════════════════════════════════════════════

@pg
async def test_18_el_envio_ocurre_DESPUES_del_COMMIT_de_la_reserva(monkeypatch, base, suelta, entorno):
    sid, _ = await _lead(base, email="a@ejemplo.invalid")
    visto: list = []
    enviar = notif._send_email

    async def enviar_y_mirar(**kw):
        async with base() as o:                                   # otra conexión: solo ve lo CONFIRMADO
            visto.append((await o.execute(text("SELECT bool_and(used_at IS NOT NULL) FROM consent_grant "
                                               "WHERE session_id = :s AND channel = 'EMAIL' AND revoked_at IS NULL"),
                                          {"s": sid})).scalar())
        return await enviar(**kw)
    monkeypatch.setattr(notif, "_send_email", enviar_y_mirar)
    res = await _barrer(base)
    assert res["comprador"] == 1 and visto == [True], visto


@pg
async def test_19_el_envio_usa_el_destino_reservado_aunque_b_se_confirme_justo_tras_el_COMMIT(
        monkeypatch, base, suelta, entorno):
    """La reserva toma a@; un «sí» con b@ espera el cerrojo; el barrido confirma y, ANTES de enviar, se deja que ese
    «sí» confirme b@ (barrera tras el COMMIT). El envío tiene que usar a@: ninguna relectura posterior al COMMIT."""
    sid, cab = await _lead(base, email="a@ejemplo.invalid")
    reservado, sigue = _pausa_tras_reserva(monkeypatch)
    t_si: list = []

    async def tras_commit():
        if reservado.is_set() and t_si and not t_si[0].done():
            await asyncio.wait_for(t_si[0], 15)                    # el «sí» confirma b@ ANTES del envío
    b = asyncio.create_task(_barrer(base, gancho_commit=tras_commit))
    await asyncio.wait_for(reservado.wait(), 10)
    t_si.append(asyncio.create_task(_si(sid, cab, email="b@ejemplo.invalid")))
    assert await _alguien_espera_el_cerrojo(base)
    sigue.set()
    await asyncio.wait_for(b, 30)
    assert (await _fila(base, sid))["lead_email"] == "b@ejemplo.invalid", "precondición: b@ quedó confirmado"
    assert _correos(entorno) == ["a@ejemplo.invalid"], _correos(entorno)


# ══ H · D2 (fuera de alcance): caracterización, no requisito ═════════════════════════════════════════════════════

@pg
async def test_21_D2_un_canal_añadido_tras_la_fase1_no_entra_en_ese_barrido(monkeypatch, base, suelta, entorno):
    """CANDIDATE-CHANNEL COMPLETENESS ≠ DESTINATION FRESHNESS. La fase 1 no tenía PUSH; un «sí» lo añade antes de la
    reserva: este barrido NO lo incorpora (los candidatos siguen saliendo de la fase 1). Documenta el límite; si un
    cambio empezara a recalcular los candidatos bajo el cerrojo, esta prueba lo señalaría."""
    sid, cab = await _lead(base, email="a@ejemplo.invalid")
    dentro, sigue = _pausa_fase1(monkeypatch)
    b = asyncio.create_task(_barrer(base))
    await asyncio.wait_for(dentro.wait(), 10)
    await asyncio.wait_for(_si(sid, cab, push=P2), 10)
    sigue.set()
    await asyncio.wait_for(b, 30)
    assert _correos(entorno) == ["a@ejemplo.invalid"] and not entorno["push"]
    assert all(g["used_at"] is None for g in _por_canal(await _grants_completos(base, sid), "PUSH"))


def test_22_estructural_el_cron_no_materializa_el_destino_con_la_foto_de_la_fase1():
    fuente = inspect.getsource(cron._escanear_reenganches)
    bloque = fuente[fuente.index("a_comprador.append({"):fuente.index('"mensaje": c["decision"]["mensaje"]')]
    assert "veredicto.email_destino" in bloque and "veredicto.push_destino" in bloque
    assert 'f["lead_email"]' not in bloque and 'f["lead_push"]' not in bloque
