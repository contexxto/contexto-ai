"""AUTH-READ-GATE.1 — la autoridad sobre una conversación, en un solo sitio.

    session_id identifica una conversación; nunca demuestra autoridad sobre ella.

Antes de este módulo, conocer el `session_id` bastaba para leer el hilo, escribir en él y
—si no tenía dueño— apropiárselo o publicarlo. Eran 18 endpoints con `session_id` en el
acceso, 12 de ellos sin ninguna prueba real (ver `docs/agentic_decision_system/12_*.md`).

Las cuatro cosas que ahora son distintas:

    session_id         identificador          — no autoriza nada
    auth subject       autoridad del dueño    — claims.sub
    resume capability  autoridad del anónimo  — secreto emitido al CREAR la sesión
    share_token        capacidad pública      — su ruta propia, sin cambios

UNA sola costura para las doce, a propósito: doce comprobaciones parecidas divergen en
cuanto una se toca, y la que se olvida es la que queda abierta.

NADA DE ESTE MÓDULO REGISTRA EL SECRETO. Ni en logs, ni en excepciones, ni en detalles de
error. Lo que se guarda en la base es su SHA-256; el secreto existe una vez, en la
respuesta del bootstrap, y después solo lo tiene el cliente.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text

from app.auth import CurrentUser
from app.database import AsyncSessionLocal

# 32 bytes de `secrets.token_urlsafe` ≈ 256 bits de entropía. Con eso no hace falta pepper
# ni KMS todavía: adivinarlo no es un modelo de amenaza realista.
_BYTES_SECRETO = 32


class Autoridad(StrEnum):
    """QUIÉN autoriza, no solo si autoriza.

    Un booleano bastaría para dejar pasar la petición y sería suficiente hoy; pero el
    llamador necesita distinguir los casos —el claim solo aplica a `ANONYMOUS_CAPABILITY`,
    y el filtrado de avisos cambia según quién seas—. Devolver la clase evita que cada
    endpoint la vuelva a deducir por su cuenta y llegue a una conclusión distinta.
    """

    OWNER = "owner"
    """La cuenta autenticada es la dueña del hilo (`claims.sub == chat_sessions.user_id`)."""

    ANONYMOUS_CAPABILITY = "anonymous_capability"
    """Hilo sin dueño y el llamador presentó la capacidad de reanudación correcta."""

    PUBLIC_SHARE = "public_share"
    """Reservado para `/shared/{token}`, que conserva su ruta propia. No lo emite este
    módulo: se declara aquí para que el vocabulario de autoridad viva completo en un sitio."""


class AccesoDenegado(Exception):
    """No se presentó ninguna autoridad utilizable sobre este hilo.

    Deliberadamente **no lleva detalle**: el mensaje viaja al cliente y distinguir "el hilo
    no existe" de "existe y no es tuyo" permitiría enumerar propiedad. El llamador decide
    el código HTTP; este módulo no revela por qué falló.
    """


def generar_secreto() -> str:
    """Un secreto de reanudación nuevo. Solo el bootstrap debería llamarlo."""
    return secrets.token_urlsafe(_BYTES_SECRETO)


def hash_de(secreto: str) -> str:
    """SHA-256 hex. Es lo ÚNICO que se persiste."""
    return hashlib.sha256(secreto.encode("utf-8")).hexdigest()


def _coincide(secreto: str | None, hash_guardado: str | None) -> bool:
    """Comparación en tiempo constante.

    `==` sobre cadenas corta en el primer byte distinto, y esa diferencia de tiempo es
    medible: permitiría adivinar el hash byte a byte. `compare_digest` no.
    """
    if not secreto or not hash_guardado:
        return False
    return hmac.compare_digest(hash_de(secreto), hash_guardado)


async def _fila_de_sesion(db, session_id: str) -> dict | None:
    fila = (await db.execute(
        text("SELECT session_id, user_id::text AS user_id, resume_token_hash, "
             "       resume_revoked_at "
             "FROM chat_sessions WHERE session_id = :sid"),
        {"sid": session_id},
    )).mappings().first()
    return dict(fila) if fila else None


async def autorizar_acceso_a_sesion(
    session_id: str,
    user: CurrentUser | None,
    resume_secret: str | None,
    *,
    db=None,
) -> Autoridad:
    """La única puerta. Levanta `AccesoDenegado` si no hay autoridad.

    El orden de las comprobaciones no es casual:

      1. **Hilo con dueño → solo el dueño.** Ni siquiera una capacidad válida antigua sirve:
         si la conversación pasó a pertenecer a una cuenta, el bearer anónimo se revocó, y
         aceptarlo sería conservar un segundo acceso en silencio.
      2. **Hilo sin dueño → capacidad obligatoria.** Da igual que quien pregunte esté
         autenticado: sin la capacidad no demuestra posesión de ESE hilo.
      3. **Sin fila → denegado.** Cubre a la vez el id inventado y la sesión anónima
         anterior al gate, que no puede reanudarse (ver migración 027).
    """
    if not isinstance(session_id, str) or not session_id.strip():
        raise AccesoDenegado()

    if db is not None:
        return _decidir(await _fila_de_sesion(db, session_id), user, resume_secret)
    async with AsyncSessionLocal() as propio:
        return _decidir(await _fila_de_sesion(propio, session_id), user, resume_secret)


def _decidir(fila: dict | None, user: CurrentUser | None, resume_secret: str | None) -> Autoridad:
    """La regla, separada de cómo se obtuvo la fila: así se puede probar sin base."""
    if fila is None:
        # Ni el id inventado ni el hilo anterior al gate se distinguen aquí — y es correcto
        # que no se distingan: la respuesta debe ser la misma para no filtrar existencia.
        raise AccesoDenegado()

    dueno = fila.get("user_id")
    if dueno:
        if user is not None and user.user_id == dueno:
            return Autoridad.OWNER
        raise AccesoDenegado()

    vigente = fila.get("resume_revoked_at") is None
    if vigente and _coincide(resume_secret, fila.get("resume_token_hash")):
        return Autoridad.ANONYMOUS_CAPABILITY

    raise AccesoDenegado()


class SesionCreada(BaseModel):
    """Lo que devuelve el bootstrap. El secreto viaja **una sola vez**, aquí."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    resume_secret: str | None = None
    """`None` para sesiones con dueño: ahí manda la identidad autenticada y una capacidad
    anónima sería un segundo acceso bearer sin motivo."""


def _nuevo_session_id(activo_id: str | None) -> str:
    """El servidor elige el identificador. El cliente ya no.

    Se conserva el prefijo `qr-{activo}-` porque **hay siete sitios de `assets.py` que
    dependen de él** (`LIKE 'qr-{activo}-%'` y `startswith`) para reconstruir el lead del
    letrero. Lo que cambia es el componente final: antes era el `device_id` del navegador,
    ahora es aleatorio del servidor. El `device_key` no entra en la autoridad.
    """
    aleatorio = secrets.token_urlsafe(12)
    return f"qr-{activo_id}-{aleatorio}" if activo_id else f"session-{aleatorio}"


async def crear_sesion(
    user: CurrentUser | None, activo_id: str | None = None, *, db=None
) -> SesionCreada:
    """Crea una sesión NUEVA y, si es anónima, emite su capacidad de reanudación.

    **Esta es la frontera que hacía falta.** El `INSERT … ON CONFLICT DO NOTHING RETURNING`
    distingue de forma atómica "acaba de nacer" de "ya existía": si no devuelve fila, el id
    ya estaba tomado y **no se emite capacidad**. Sin esa distinción, la regla ingenua
    —"si no trae token, emito uno"— dejaría que cualquiera que conozca un `session_id`
    existente pidiera una capacidad válida para él, cambiando una puerta abierta por otra
    con apariencia de seguridad.

    Como el identificador lo genera el servidor con 12 bytes aleatorios, el conflicto es
    prácticamente imposible; el `ON CONFLICT` está por corrección, no por probabilidad.
    """
    if db is not None:
        return await _ejecutar_creacion(db, user, activo_id)
    async with AsyncSessionLocal() as propio:
        return await _ejecutar_creacion(propio, user, activo_id)


async def _ejecutar_creacion(db, user: CurrentUser | None, activo_id: str | None) -> SesionCreada:
    session_id = _nuevo_session_id(activo_id)
    secreto = None if user else generar_secreto()

    resultado = await db.execute(
        text(
            "INSERT INTO chat_sessions "
            "  (session_id, user_id, resume_token_hash, resume_issued_at, creada_por_servidor) "
            "VALUES (:sid, :uid, :h, CASE WHEN :h IS NULL THEN NULL ELSE now() END, true) "
            "ON CONFLICT (session_id) DO NOTHING "
            "RETURNING session_id"
        ),
        {"sid": session_id, "uid": user.user_id if user else None,
         "h": hash_de(secreto) if secreto else None},
    )
    if len(resultado.fetchall()) != 1:
        await db.rollback()
        raise AccesoDenegado()   # el id ya existía: NO se emite capacidad para él
    await db.commit()
    return SesionCreada(session_id=session_id, resume_secret=secreto)


async def reclamar_sesion_anonima(
    session_id: str, user: CurrentUser, resume_secret: str, *, db=None
) -> None:
    """Un hilo anónimo pasa a pertenecer a una cuenta, y su capacidad se revoca.

    **SEGURO POR CONSTRUCCIÓN, no por disciplina del llamador.** La versión anterior confiaba
    en que alguien hubiera autorizado antes: hacía `UPDATE … WHERE user_id IS NULL` sin
    ligarse a la capacidad que dio permiso y sin mirar cuántas filas tocó. Eso dejaba dos
    agujeros:

      · **TOCTOU** — entre la autorización y el `UPDATE`, otra petición podía reclamar el
        hilo o revocar la capacidad. El `WHERE` seguía cumpliéndose para el segundo llamador
        si llegaba antes, y el estado observado ya no era el autorizado.
      · **Mal uso** — un llamador futuro que olvidara autorizar produciría exactamente el
        agujero que este gate cierra, sin que nada fallara.

    Ahora la condición de autorización **está dentro de la sentencia**: el hash tiene que
    seguir siendo el mismo, la capacidad tiene que seguir vigente y el hilo tiene que seguir
    sin dueño. Si algo cambió, no se actualiza nada y se levanta `AccesoDenegado`.

    `RETURNING session_id` + `rowcount` es lo que convierte "no pasó nada" en un error en vez
    de en un silencio: un claim que no reclama debe doler, no seguir adelante.
    """
    if not resume_secret:
        raise AccesoDenegado()
    if db is not None:
        return await _ejecutar_claim(db, session_id, user, resume_secret)
    async with AsyncSessionLocal() as propio:
        return await _ejecutar_claim(propio, session_id, user, resume_secret)


async def _ejecutar_claim(db, session_id: str, user: CurrentUser, resume_secret: str) -> None:
    resultado = await db.execute(
        text(
            "UPDATE chat_sessions "
            "   SET user_id = :uid, resume_revoked_at = now(), updated_at = now() "
            " WHERE session_id        = :sid "
            "   AND user_id           IS NULL "          # sigue sin dueño
            "   AND resume_token_hash = :h "             # es LA capacidad que autorizó
            "   AND resume_revoked_at IS NULL "          # y sigue vigente
            "RETURNING session_id"
        ),
        {"sid": session_id, "uid": user.user_id, "h": hash_de(resume_secret)},
    )
    filas = resultado.fetchall()
    if len(filas) != 1:
        # Ni una fila (el estado cambió, o nunca hubo autoridad) ni más de una (imposible con
        # `session_id` como PK, pero comprobarlo cuesta nada y una PK puede cambiar).
        await db.rollback()
        raise AccesoDenegado()
    await db.commit()
