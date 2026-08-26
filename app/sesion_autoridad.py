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


async def reclamar_sesion_anonima(session_id: str, user: CurrentUser, *, db=None) -> None:
    """Un hilo anónimo pasa a pertenecer a una cuenta, y su capacidad se revoca.

    **Solo debe llamarse después de que `autorizar_acceso_a_sesion` haya devuelto
    `ANONYMOUS_CAPABILITY`.** El claim sin capacidad es exactamente el agujero que este gate
    cierra: antes, cualquier autenticado que conociera el id se quedaba con el hilo.

    La revocación va en la MISMA sentencia que la asignación de dueño: si fueran dos, una
    caída entre ambas dejaría un hilo con dueño y una capacidad viva — el segundo acceso
    bearer silencioso que la política prohíbe.
    """
    if db is not None:
        await _ejecutar_claim(db, session_id, user)
        return
    async with AsyncSessionLocal() as propio:
        await _ejecutar_claim(propio, session_id, user)


async def _ejecutar_claim(db, session_id: str, user: CurrentUser) -> None:
    await db.execute(
        text("UPDATE chat_sessions "
             "SET user_id = :uid, resume_revoked_at = now(), updated_at = now() "
             "WHERE session_id = :sid AND user_id IS NULL"),
        {"sid": session_id, "uid": user.user_id},
    )
    await db.commit()
