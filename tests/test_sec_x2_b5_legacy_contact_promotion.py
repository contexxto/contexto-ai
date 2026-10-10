"""SEC-X2-B5-LEGACY-CONTACT-PROMOTION-R0 · NUEVA AUTORIDAD DE HANDOFF ≠ AUTORIDAD PARA REUTILIZAR CONTACTO LEGACY.

El censo C0 de producción (2026-10-09, B-5 = OBSERVED_NONZERO) halló 10 filas de `handoff_sesion` sin marca de
autoridad (`principal_requested_at` aún no existe allí; #195 la añade sin backfill) y 6 con correo, push o usuario
escritos antes de cualquier acto. ANTES (d483899): un acto nuevo promovía esa fila y CONSERVABA ese contacto
(COALESCE con lo histórico y el push intacto), y el corredor podía responder hacia él; el correo de rescate,
además, tomaba «cualquier `lead_email` de la sesión» (LIMIT 1), sin el inmueble ni la marca.

AHORA:
  - PROMOCIÓN de una fila histórica → contacto = SOLO el del acto actual (NULL si es anónimo), push NULL;
  - REPETICIÓN de un hilo ya autorizado → lo nuevo actualiza, la ausencia no borra, el push vigente queda;
  - RESCATE → el correo del hilo exacto `(sesión, inmueble del aviso)` y solo si está autorizado; si no, nada.
La fila legacy no se borra y ninguna otra fila se toca.

PostgreSQL 15 REAL (`TEST_DATABASE_URL`) con el `_HANDOFF_DDL` real (fixture `base` de SEC-X2-R0).
"""
from __future__ import annotations

import json

import pytest
from sqlalchemy import text

import app.rescate_avisos as rescate
import app.routers.chat as chat
from tests.test_sec_x2_r0_disclosure_authority import (  # noqa: F401
    DUENO_X, X, Y, _responde, _uno, base, pg)

OLD_USER = "00000000-0000-4000-8000-0000000c0de0"
NEW_USER = "00000000-0000-4000-8000-0000000bee10"
OTRO_USER = "00000000-0000-4000-8000-0000000bee20"
OLD_EMAIL = "old@ejemplo.invalid"
OLD_PUSH = {"endpoint": "https://push.prueba.test/legacy", "keys": {"p256dh": "a", "auth": "b"}}
PUSH_ACTUAL = {"endpoint": "https://push.prueba.test/actual", "keys": {"p256dh": "c", "auth": "d"}}


@pytest.fixture(autouse=True)
def _sin_rate_limit(monkeypatch):
    from app.limiter import limiter
    monkeypatch.setattr(limiter, "enabled", False)


@pytest.fixture
def enviados(base, monkeypatch):
    """Registra los argumentos de CADA envío en el momento de la llamada (el `disparar` del fixture `base` cierra
    la corrutina sin ejecutarla, así que el registro no puede depender de que corra)."""
    import app.notifications as notificaciones
    registro: list[dict] = []

    def _registra(**k):
        registro.append(k)

        async def _nada():
            return None
        return _nada()

    monkeypatch.setattr(notificaciones, "send_notification", _registra)
    return registro


# ── andamiaje ─────────────────────────────────────────────────────────────────────────────────────────────────

async def _legado(Sesion, sid, activo, *, user=OLD_USER, email=OLD_EMAIL, push=OLD_PUSH):
    """Fila HISTÓRICA: contacto escrito antes de cualquier acto, marca NULL (así entra hoy cada fila de producción
    al candidato)."""
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
        await db.execute(text(
            "INSERT INTO handoff_sesion (session_id, activo_id, estado, lead_user_id, lead_email, push_subscription, "
            "  principal_requested_at, creado_en, actualizado_en) "
            "VALUES (:s, CAST(:a AS uuid), 'activo', CAST(:u AS uuid), :e, CAST(:p AS jsonb), NULL, "
            "        now() - interval '30 days', now() - interval '30 days')"),
            {"s": sid, "a": activo, "u": user, "e": email, "p": json.dumps(push) if push else None})
        await db.commit()


async def _contacto(Sesion, sid, activo) -> dict:
    async with Sesion() as db:
        f = (await db.execute(text(
            "SELECT lead_user_id::text AS usuario, lead_email AS email, push_subscription AS push, "
            "       principal_requested_at AS marca "
            "FROM handoff_sesion WHERE session_id = :s AND activo_id = CAST(:a AS uuid)"),
            {"s": sid, "a": activo})).mappings().first()
    return dict(f)


async def _aviso(Sesion, sid, activo):
    """Un aviso SIN LEER y vencido para el interesado anónimo de `sid` (hilo `activo`, o sin inmueble)."""
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
        await db.execute(text(
            "INSERT INTO notificacion (destinatario_user_id, destinatario_session, titulo, cuerpo, url, session_id, "
            "  activo_id, creada_en) "
            "VALUES (NULL, :s, 'Te respondieron', 'Hola', '/', :s, CAST(:a AS uuid), now() - interval '3 hours')"),
            {"s": sid, "a": activo})
        await db.commit()


async def _rescatar(Sesion) -> dict:
    async with Sesion() as db:
        return await rescate.escanear_rescates(db)


def _correos(enviados) -> list:
    return sorted(k["email"] for k in enviados if k.get("email"))


# ══ 1 · registrar_handoff: PROMOCIÓN ≠ REPETICIÓN ═════════════════════════════════════════════════════════════

@pg
async def test_A_promocion_anonima_de_una_fila_legacy_descarta_usuario_correo_y_push(base):
    Sesion, _ = base
    sid = "session-b5a"
    await _legado(Sesion, sid, X)
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]
    c = await _contacto(Sesion, sid, X)
    assert c["marca"] is not None
    assert (c["usuario"], c["email"], c["push"]) == (None, None, None), c


@pg
async def test_B_promocion_autenticada_lleva_SOLO_el_contacto_del_acto_actual(base):
    Sesion, _ = base
    sid = "session-b5b"
    await _legado(Sesion, sid, X)
    assert (await chat.registrar_handoff(sid, activo_id=X, lead_user_id=NEW_USER,
                                         lead_email="nuevo@ejemplo.invalid"))["ok"]
    c = await _contacto(Sesion, sid, X)
    assert c["marca"] is not None
    assert (c["usuario"], c["email"], c["push"]) == (NEW_USER, "nuevo@ejemplo.invalid", None), c


@pg
async def test_C_repetir_una_solicitud_ya_autorizada_no_borra_el_contacto_vigente(base):
    """REPETICIÓN ≠ PROMOCIÓN: sin valor nuevo nada se borra (push incluido); un valor nuevo actualiza."""
    Sesion, _ = base
    sid = "session-b5c"
    assert (await chat.registrar_handoff(sid, activo_id=X, lead_user_id=NEW_USER,
                                         lead_email="actual@ejemplo.invalid"))["ok"]
    async with Sesion() as db:                     # el push vigente, como lo engancha /handoff/push
        await db.execute(text(
            "UPDATE handoff_sesion SET push_subscription = CAST(:p AS jsonb) "
            "WHERE session_id = :s AND principal_requested_at IS NOT NULL"),
            {"s": sid, "p": json.dumps(PUSH_ACTUAL)})
        await db.commit()
    marca = (await _contacto(Sesion, sid, X))["marca"]
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]            # repetición anónima
    c = await _contacto(Sesion, sid, X)
    assert (c["usuario"], c["email"], c["marca"]) == (NEW_USER, "actual@ejemplo.invalid", marca), c
    assert c["push"] == PUSH_ACTUAL, c
    assert (await chat.registrar_handoff(sid, activo_id=X, lead_user_id=OTRO_USER,
                                         lead_email="otro@ejemplo.invalid"))["ok"]
    c = await _contacto(Sesion, sid, X)
    assert (c["usuario"], c["email"], c["push"], c["marca"]) == (
        OTRO_USER, "otro@ejemplo.invalid", PUSH_ACTUAL, marca), c


# ══ 4 · el corredor responde: nunca hacia el push ni la identidad legacy ════════════════════════════════════

@pg
async def test_D_la_respuesta_del_corredor_a_una_fila_promovida_nunca_usa_el_push_ni_el_usuario_legacy(
        base, enviados):
    Sesion, _ = base
    sid = "session-b5d"
    await _legado(Sesion, sid, X)
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]
    assert (await _responde(Sesion, sid, X, DUENO_X))["ok"]
    assert len(enviados) == 1 and enviados[0]["push_subscription"] is None, enviados
    assert all("legacy" not in json.dumps(k.get("push_subscription")) for k in enviados)
    # La campana del interesado no se liga a la identidad legacy.
    assert await _uno(Sesion, "SELECT count(*) FROM notificacion WHERE destinatario_user_id IS NOT NULL") == 0
    assert await _uno(Sesion, "SELECT count(*) FROM notificacion WHERE destinatario_session = :s", s=sid) == 1


# ══ 3 · rescate por correo: el hilo exacto autorizado o nada ════════════════════════════════════════════════

@pg
async def test_E_rescate_de_X_sin_correo_no_sale_al_correo_historico_de_Y(base, enviados):
    Sesion, _ = base
    sid = "session-b5e"
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]           # X autorizado, sin correo
    await _legado(Sesion, sid, Y)                                           # Y histórico con old@
    await _aviso(Sesion, sid, X)
    r = await _rescatar(Sesion)
    assert r == {"rescatados": 0, "avisos": 1} and enviados == [], (r, enviados)
    assert await _uno(Sesion, "SELECT count(*) FROM notificacion WHERE rescate_en IS NULL") == 0  # marcado igual


@pg
async def test_E2_rescate_de_un_hilo_historico_no_usa_su_correo_legacy(base, enviados):
    """Un aviso con inmueble cuyo hilo sigue histórico (p. ej., uno de antes del deploy): sin marca no hay correo."""
    Sesion, _ = base
    sid = "session-b5e2"
    await _legado(Sesion, sid, X)
    await _aviso(Sesion, sid, X)
    assert (await _rescatar(Sesion))["rescatados"] == 0 and enviados == []


@pg
async def test_E3_rescate_de_X_no_cruza_al_correo_de_OTRO_hilo_autorizado_de_la_sesion(base, enviados):
    Sesion, _ = base
    sid = "session-b5e3"
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]                              # X sin correo
    assert (await chat.registrar_handoff(sid, activo_id=Y, lead_email="y@ejemplo.invalid"))["ok"]  # Y con y@
    await _aviso(Sesion, sid, X)
    assert (await _rescatar(Sesion))["rescatados"] == 0 and enviados == []


@pg
async def test_E4_un_aviso_sin_inmueble_no_tiene_hilo_exacto_y_no_rescata(base, enviados):
    Sesion, _ = base
    sid = "session-b5e4"
    assert (await chat.registrar_handoff(sid, activo_id=X, lead_email="x@ejemplo.invalid"))["ok"]
    await _aviso(Sesion, sid, None)
    assert (await _rescatar(Sesion))["rescatados"] == 0 and enviados == []


@pg
async def test_F_rescate_usa_exactamente_el_correo_actual_del_hilo_y_nunca_el_historico(base, enviados):
    Sesion, _ = base
    sid = "session-b5f"
    assert (await chat.registrar_handoff(sid, activo_id=X, lead_email="current@ejemplo.invalid"))["ok"]
    await _legado(Sesion, sid, Y)
    await _aviso(Sesion, sid, X)
    await _aviso(Sesion, sid, Y)                     # el aviso del hilo histórico no aporta destino
    r = await _rescatar(Sesion)
    assert r == {"rescatados": 1, "avisos": 2} and _correos(enviados) == ["current@ejemplo.invalid"], (r, enviados)


@pg
async def test_F2_dos_hilos_autorizados_con_correos_distintos_un_correo_a_cada_uno(base, enviados):
    Sesion, _ = base
    sid = "session-b5f2"
    assert (await chat.registrar_handoff(sid, activo_id=X, lead_email="x@ejemplo.invalid"))["ok"]
    assert (await chat.registrar_handoff(sid, activo_id=Y, lead_email="y@ejemplo.invalid"))["ok"]
    await _aviso(Sesion, sid, X)
    await _aviso(Sesion, sid, Y)
    assert (await _rescatar(Sesion))["rescatados"] == 2
    assert _correos(enviados) == ["x@ejemplo.invalid", "y@ejemplo.invalid"]


# ══ G · ninguna escritura ni backfill sobre las demás filas históricas ════════════════════════════════════════

@pg
async def test_G_promover_y_rescatar_no_escribe_ninguna_otra_fila_historica(base, enviados):
    Sesion, _ = base
    sid = "session-b5g"
    await _legado(Sesion, sid, X)
    await _legado(Sesion, sid, Y, user=NEW_USER, email="otra@ejemplo.invalid")
    await _legado(Sesion, "session-b5g-otra", X, user=OTRO_USER, email="ajena@ejemplo.invalid")
    foto = ("SELECT to_jsonb(h)::text FROM handoff_sesion h "
            "WHERE NOT (session_id = :s AND activo_id = CAST(:a AS uuid)) ORDER BY session_id, activo_id")

    async def _resto():
        async with Sesion() as db:
            return [r[0] for r in (await db.execute(text(foto), {"s": sid, "a": X})).all()]
    antes = await _resto()
    assert (await chat.registrar_handoff(sid, activo_id=X))["ok"]
    await _aviso(Sesion, sid, Y)
    await _rescatar(Sesion)
    assert await _resto() == antes and len(antes) == 2
    assert await _uno(Sesion, "SELECT count(*) FROM handoff_sesion") == 3          # nada se borra
    assert (await _contacto(Sesion, sid, X))["marca"] is not None


# ══ sin base: el rescate sin inmueble no consulta nada ═══════════════════════════════════════════════════════

async def test_H_sin_inmueble_el_rescate_no_consulta_el_handoff_de_la_sesion():
    class _Espia:
        consultas: list = []

        async def execute(self, *a, **k):
            self.consultas.append(a)
            raise AssertionError("no debía consultar")
    db = _Espia()
    assert await rescate._correo_de(db, None, "session-b5h", None) is None
    assert db.consultas == []
