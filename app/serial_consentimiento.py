"""SEC-X2-CONSENT-SERIALIZATION-R0 · UNA SESIÓN = UNA FRONTERA DE SERIALIZACIÓN DE SU AUTORIDAD.

    AUTORIDAD CONCURRENTE SOBRE UNA MISMA SESIÓN → UN ÚNICO ORDEN → UN ESTADO FINAL RECONSTRUIBLE.

Toda escritura material de la autoridad de reenganche de una sesión —el «sí» (sustituir + crear grants), el «no»
y la baja (revocar), y la reserva del cron (consumir)— se serializa con UN cerrojo transaccional de Postgres:

    pg_advisory_xact_lock(ESPACIO_CONSENTIMIENTO, hashtext(session_id))       (bloqueante: «sí», «no», baja)
    pg_try_advisory_xact_lock(ESPACIO_CONSENTIMIENTO, hashtext(session_id))   (sin espera: la reserva del cron)

Por qué cierra los tres residuales del postcheck:
  · RF-R1 · «sí» y «no» concurrentes ya no se cruzan: el segundo espera al primero y actúa sobre su resultado
    confirmado; el estado final es el del ORDEN DEL CERROJO, en `consent_grant` y en `lead_actividad` a la vez.
  · RF-R2 · los órdenes internos (`lead_actividad`→`consent_grant` en el «sí», al revés en el «no») solo los
    ejecuta quien tiene el cerrojo de ESA sesión: el ciclo deja de existir (no se confía en que Postgres lo
    detecte). Cada camino interactivo toma UN solo cerrojo y lo toma ANTES de tocar esas tablas (también antes
    del DDL de `_preparar_lead_actividad_en_transaccion`).
  · GF-R1 · el cron NUNCA espera (D-CRON = B): si la sesión está ocupada, la reserva no decide (ERROR → el lead
    se omite en ese barrido, para las dos audiencias, sin marca ni presupuesto) y el barrido siguiente decide con
    estado y hora frescos. Si el cerrojo es suyo, ninguno de los escritores de `app/` inventariados retiene filas
    de grant de esa sesión, así que la reserva —una sentencia POSTERIOR, con su propio `statement_timestamp()`— no
    espera esos bloqueos de fila. La reserva va en un SAVEPOINT (`autoridad_reenganche._reservar`): BUSY y NO_GRANT
    lo deshacen y sueltan el cerrojo; solo AUTHORIZED lo conserva hasta el COMMIT.

La garantía es la de los caminos de la app desplegada que usan este módulo (inventario de `app/`, test_20): nada en
la base obliga a cooperar con el cerrojo (no hay trigger ni privilegio), y durante un deploy solapado un proceso
viejo sin cerrojo convive con el nuevo.

Reglas de la clave (no negociables):
  · el espacio es ESTE (`ESPACIO_CONSENTIMIENTO`); la sesión es `consent_grant.session_id` (el lead), la MISMA
    cadena en los cuatro escritores. Nada de `hash()` de Python, `activo_id`, canal, prefijo `qr-` ni `user_id`.
  · forma (int4, int4): otro espacio de `pg_locks` que la de un solo argumento int8; no choca con otros usos.
  · una colisión de `hashtext` (32 bits) solo serializa de más: cada decisión de autoridad filtra
    `WHERE session_id = :sid` y jamás concede entre sesiones.
  · el cerrojo es de la TRANSACCIÓN (se suelta en COMMIT/ROLLBACK) y reentrante en ella. Nunca locks de SESIÓN.

FALLA CERRADO: `pg_advisory_xact_lock(ns, hashtext(NULL))` devuelve NULL, NO bloquea nada y NO falla (funciones
STRICT, observado en el preflight). Por eso la sesión se valida AQUÍ, antes del SQL: None, vacía, en blanco o no
`str` → `SesionNoSerializable`, y ningún cerrojo ambiguo ni escritura de autoridad.
"""
from __future__ import annotations

from sqlalchemy import text

# Espacio propio del cerrojo de consentimiento (int4). 0x5EC2 = «SEC-X2». Cambiarlo con despliegues solapados
# partiría la frontera en dos: dos procesos con espacios distintos no se serializarían entre sí.
ESPACIO_CONSENTIMIENTO = 0x5EC2

_BLOQUEANTE = "SELECT pg_advisory_xact_lock(CAST(:ns AS integer), hashtext(CAST(:sid AS text)))"
_SIN_ESPERA = "SELECT pg_try_advisory_xact_lock(CAST(:ns AS integer), hashtext(CAST(:sid AS text)))"


class SesionNoSerializable(ValueError):
    """La sesión no sirve como clave del cerrojo: no se toma ninguno y no se escribe autoridad."""


def _clave(session_id) -> str:
    # El mismo contrato que la autoridad de sesión (`sesion_autoridad`): cadena no vacía ni en blanco. Se usa TAL
    # CUAL (sin normalizar): la clave tiene que ser exactamente el `session_id` que llevan los grants.
    if not isinstance(session_id, str) or not session_id.strip():
        raise SesionNoSerializable("session_id inválido para la frontera de consentimiento")
    return session_id


async def serializar_consentimiento(db, session_id) -> None:
    """Toma (o re-toma: es reentrante) el cerrojo de consentimiento de `session_id` en la transacción de `db`,
    ESPERANDO si otra transacción lo tiene. Para los caminos interactivos («sí», «no», baja). Sentencia propia."""
    sid = _clave(session_id)
    await db.execute(text(_BLOQUEANTE), {"ns": ESPACIO_CONSENTIMIENTO, "sid": sid})


async def intentar_serializar_consentimiento(db, session_id) -> bool:
    """Intenta el MISMO cerrojo SIN esperar. True = es de esta transacción; False = otra transacción está
    cambiando la autoridad de esa sesión. Para la reserva del cron (D-CRON = B). Sentencia propia: la comprobación
    de frescura va en una sentencia POSTERIOR, nunca en la misma (un CTE heredaría la hora de antes)."""
    sid = _clave(session_id)
    return bool((await db.execute(text(_SIN_ESPERA), {"ns": ESPACIO_CONSENTIMIENTO, "sid": sid})).scalar())
