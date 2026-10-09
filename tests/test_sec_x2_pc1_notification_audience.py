"""SEC-X2-PC1-NOTIFICATION-AUDIENCE-R0 · LA IDENTIDAD DE QUIEN PIDIÓ CONTACTO PARA Y NO AUTORIZA RECIBIR RESPUESTAS DEL
CORREDOR DE X.

PC-1 (postcheck final 0.2, MAJOR demostrado): `responder_lead`, sin `lead_user_id` en el hilo exacto X, tomaba el de
OTRO hilo autorizado de la sesión. Escenario: sesión anónima con capacidad; la cuenta U_A pide Y (sin chatear: no
reclama); X se pide de forma anónima; la cuenta U_B reclama la sesión (U_A queda sin autoridad: 404). El corredor de X
responde → el aviso se ligaba a U_A: su campana por cuenta mostraba el mensaje y el rescate se lo enviaba por correo.

AHORA el aviso lleva SOLO la identidad del hilo exacto; sin ella queda ligado únicamente a la sesión, cuya lectura
exige la autoridad vigente. La semántica de S3 (U_A pidió X él mismo y después perdió la autoridad) NO cambia aquí:
está pendiente de clasificación en el postcheck y la prueba S3 solo la caracteriza.

PostgreSQL 15 REAL (`TEST_DATABASE_URL`), fixture `base_c1` de SEC-X2-R0 (`chat_sessions` con la puerta real).
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import text

import app.rescate_avisos as rescate
import app.routers.chat as chat
from app.auth import CurrentUser
from tests.test_sec_x2_r0_disclosure_authority import (  # noqa: F401
    DUENO_X, X, Y, _conversacion, _peticion_con, _responde, _uno, base, base_c1, pg)

U_A = CurrentUser(user_id="00000000-0000-4000-8000-0000000000aa", email="ua@ejemplo.invalid", nombre="Cuenta A")
U_B = CurrentUser(user_id="00000000-0000-4000-8000-0000000000bb", email="ub@ejemplo.invalid", nombre="Cuenta B")
CAP = "capacidad-de-prueba-0123456789abcdef0123456789"
TEXTO = "Mensaje del corredor de X"


@pytest.fixture(autouse=True)
def _sin_rate_limit(monkeypatch):
    from app.limiter import limiter
    monkeypatch.setattr(limiter, "enabled", False)


@pytest.fixture
def enviados(base, monkeypatch):
    """Registra cada envío al llamarse (el `disparar` de `base` cierra la corrutina sin ejecutarla)."""
    import app.notifications as notificaciones
    registro: list[dict] = []

    def _registra(**k):
        registro.append(k)

        async def _nada():
            return None
        return _nada()
    monkeypatch.setattr(notificaciones, "send_notification", _registra)
    return registro


async def _sesion_anonima(Sesion, sid):
    async with Sesion() as db:   # el `chat_sessions` real tiene `updated_at` (lo escribe el reclamo); el del fixture no
        await db.execute(text("ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS updated_at timestamptz"))
        await db.commit()
    await _conversacion(Sesion, sid, capacidad=CAP)
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
        await db.execute(text("INSERT INTO push_usuario (user_id, email) VALUES (CAST(:u AS uuid), :e)"),
                         {"u": U_A.user_id, "e": "ua-cuenta@ejemplo.invalid"})
        await db.commit()


async def _pide(sid, activo, user):
    r = await chat.solicitar_handoff(_peticion_con(CAP), sid, None, user, chat.SolicitudHandoff(activo_id=activo))
    assert r["ok"]


async def _reclama_U_B(sid):
    from app.sesion_autoridad import reclamar_sesion_anonima
    await reclamar_sesion_anonima(sid, U_B, CAP)
    for capacidad in (CAP, None):                                  # U_A ya no tiene autoridad sobre la sesión
        with pytest.raises(HTTPException) as e:
            await chat._exigir_autoridad(_peticion_con(capacidad), sid, U_A)
        assert e.value.status_code == 404


async def _aviso_de_X(Sesion, sid) -> dict:
    async with Sesion() as db:
        return dict((await db.execute(text(
            "SELECT destinatario_user_id::text AS usuario, destinatario_session AS sesion FROM notificacion "
            "WHERE session_id = :s AND activo_id = CAST(:a AS uuid)"), {"s": sid, "a": X})).mappings().one())


async def _campana_de(user, sid=None, capacidad=None) -> list:
    return [i["cuerpo"] for i in (await chat.listar_notificaciones(_peticion_con(capacidad), sid, user))["items"]]


async def _rescate(Sesion, enviados) -> list:
    async with Sesion() as db:
        await db.execute(text("UPDATE notificacion SET creada_en = now() - interval '3 hours'"))
        await db.commit()
    async with Sesion() as db:
        await rescate.escanear_rescates(db)
    return [k["email"] for k in enviados if k.get("email")]


@pg
async def test_1_S2_tras_el_reclamo_la_cuenta_que_pidio_Y_no_recibe_el_aviso_de_X(base_c1, enviados):
    Sesion, _ = base_c1
    sid = "session-pc1-s2"
    await _sesion_anonima(Sesion, sid)
    await _pide(sid, Y, U_A)                 # U_A pide Y con la capacidad, sin chatear (no reclama)
    await _pide(sid, X, None)                # X anónimo
    await _reclama_U_B(sid)
    assert (await _responde(Sesion, sid, X, DUENO_X, texto=TEXTO))["ok"]
    assert await _aviso_de_X(Sesion, sid) == {"usuario": None, "sesion": sid}
    assert TEXTO not in await _campana_de(U_A)                                   # ni su campana por cuenta…
    assert await _rescate(Sesion, enviados) == []                                # …ni su correo de rescate
    assert TEXTO in await _campana_de(U_B, sid)                                  # la dueña vigente sí, por la sesión


@pg
async def test_2_control_la_cuenta_que_pidio_X_y_conserva_la_autoridad_recibe_su_aviso(base_c1, enviados):
    Sesion, _ = base_c1
    sid = "session-pc1-ctrl"
    await _sesion_anonima(Sesion, sid)
    await _pide(sid, X, U_A)                 # sin reclamo: U_A conserva la capacidad
    assert (await _responde(Sesion, sid, X, DUENO_X, texto=TEXTO))["ok"]
    assert await _aviso_de_X(Sesion, sid) == {"usuario": U_A.user_id, "sesion": sid}
    assert TEXTO in await _campana_de(U_A)
    assert await _rescate(Sesion, enviados) == ["ua-cuenta@ejemplo.invalid"]


@pg
async def test_3_multinmueble_la_identidad_de_Y_nunca_se_copia_al_aviso_de_X(base_c1, enviados):
    Sesion, _ = base_c1
    sid = "session-pc1-multi"
    await _sesion_anonima(Sesion, sid)
    await _pide(sid, Y, U_A)                 # Y con identidad
    await _pide(sid, X, None)                # X anónimo (sin reclamo: el caso más común)
    assert (await _responde(Sesion, sid, X, DUENO_X, texto=TEXTO))["ok"]
    assert await _aviso_de_X(Sesion, sid) == {"usuario": None, "sesion": sid}
    assert TEXTO not in await _campana_de(U_A)
    assert TEXTO in await _campana_de(None, sid, CAP)                            # quien tiene la capacidad, por la sesión


@pg
async def test_S3_caracterizacion_la_identidad_del_acto_de_X_no_cambia_con_PC1(base_c1, enviados):
    """S3 · SEMÁNTICA PENDIENTE DE CLASIFICAR EN EL POSTCHECK. U_A pidió X ÉL MISMO y después U_B reclamó la sesión:
    el aviso de X sigue yendo a la identidad DEL ACTO de X. Esta prueba no decide si eso es correcto; solo fija que
    la microcorrección de PC-1 (que quita la identidad de OTRO hilo) no lo alteró por accidente."""
    Sesion, _ = base_c1
    sid = "session-pc1-s3"
    await _sesion_anonima(Sesion, sid)
    await _pide(sid, X, U_A)
    await _reclama_U_B(sid)
    assert (await _responde(Sesion, sid, X, DUENO_X, texto=TEXTO))["ok"]
    assert await _aviso_de_X(Sesion, sid) == {"usuario": U_A.user_id, "sesion": sid}
