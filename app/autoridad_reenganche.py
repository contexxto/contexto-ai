"""Plan 1.1 · TR-5 — LA frontera de autoridad del reenganche al comprador.

    ¿Este efecto de reenganche al comprador está autorizado AHORA, y por qué canales?

Es el ÚNICO sitio que lo responde (`03_` §5.3: «un solo lugar donde se decide si un efecto está
autorizado… ningún consumidor saliente decide su propio permiso»). El cron consume el
resultado y no vuelve a interpretar grants; `consent_reenganche_at` ya no autoriza nada.

Evalúa, en UNA sentencia: principal (el de la sesión del lead, o la cuenta dueña de esa sesión)
· audience PRINCIPAL_SELF · purpose REENGAGEMENT · action NOTIFY_VERIFIED_UPDATE · canal
exacto · vigencia (granted_at ≤ ahora < expires_at) · no revocado · no usado · mode once (standing
no se autoriza en TR-5) · case_ref NULL · y que el lead no esté CERRADO.

SEC-X2-GRANT-FRESHNESS-R0 · «ahora» es `statement_timestamp()`: la hora de ESTA sentencia, no
`now()` (el inicio de la TRANSACCIÓN del llamador). El cron decide dentro de una transacción que
empezó al leer la primera página del barrido; con `now()`, un grant que venció durante ese recorrido
seguía «vigente» —la vigencia se juzgaba con una foto del principio— y uno que entró en vigor
durante él no se veía (NO_GRANT). La autoridad se juzga en el momento de la decisión: el INICIO de
esta sentencia. Es estable durante ella (a diferencia de `clock_timestamp()`), así que la condición y
`used_at` usan el mismo instante (y `used_at >= granted_at`, CHECK de la 038, se cumple siempre).
El corte del universo dormido del barrido SÍ usa `now()` a propósito (reenganche_cron.py): allí lo
útil es una foto fija.

Con `reservar=True` además CONSUME (used_at = statement_timestamp()) cada grant que autoriza, en la
transacción del llamador: `UPDATE … WHERE used_at IS NULL … RETURNING`. Consumo ANTES de enviar: mejor perder
un aviso que duplicarlo.

SEC-X2-CONSENT-SERIALIZATION-R0 · LA RESERVA NO ESPERA (D-CRON = B). Antes de reservar, en una SENTENCIA PROPIA,
intenta el cerrojo de consentimiento de la sesión (`app/serial_consentimiento.py`) SIN esperar:
  · si otra transacción lo tiene (un «sí», un «no», una baja u otro barrido cambiando la autoridad de esa
    sesión) → ERROR: «sesión ocupada, este barrido no decide sobre ella». El cron ya trata ERROR como lead
    omitido para las DOS audiencias, sin marca, sin presupuesto y sin efecto; el barrido siguiente la reevalúa.
    BUSY jamás es NO_GRANT (que dejaría pasar la rama del corredor) ni una reserva sin cerrojo;
  · si el cerrojo es de esta transacción, ninguno de los escritores de `app/` inventariados (todos toman el mismo
    cerrojo antes de escribir; tests/test_sec_x2_consent_serialization.py::test_20) retiene filas de grant de esa
    sesión, así que la reserva —la sentencia SIGUIENTE, con su propio `statement_timestamp()`— no espera sus
    bloqueos de fila: no hay «espera → el titular aborta → condición sin re-evaluar», y un grant que venció
    mientras otro tenía el cerrojo se ve VENCIDO (GF-R1 cerrado frente a esos escritores).
El cerrojo y la comprobación de frescura van SIEMPRE en sentencias distintas: un CTE heredaría la hora de antes.
Todo ello dentro de un SAVEPOINT (`_reservar`): BUSY y NO_GRANT lo deshacen y SUELTAN el cerrojo; solo una reserva
AUTHORIZED lo conserva hasta el COMMIT. Defensa adicional: `RETURNING expires_at > clock_timestamp()`; si un grant
dejó de estar vigente durante la propia sentencia (una espera de relación, o un escritor que no coopera con el
cerrojo), se deshace la reserva y es NO_GRANT. Nada en la base obliga a cooperar (no hay trigger ni privilegio), y
durante un deploy solapado un proceso viejo sin cerrojo convive con el nuevo: la garantía es la de los caminos de
la app desplegada, no la de cualquier SQL.

Resultados:
    AUTHORIZED(canales)  sólo esos canales pueden salir (un grant de EMAIL no autoriza PUSH)
    NO_GRANT             el comprador no recibe nada. NO es autoridad para nadie más: el corredor
                         solo recibe con SU propio hecho (`corredor_autorizado`, SEC-X2-EGRESS-R0;
                         el antiguo «el corredor sigue su camino», DR-15, queda retirado)
    ERROR                no se pudo decidir (p. ej. 038 sin aplicar): nadie recibe nada

SEC-X2-EGRESS-R0 · DOS AUDIENCIAS, DOS AUTORIDADES. Este módulo responde también la de la otra
audiencia del reenganche —el corredor del inmueble exacto— con `corredor_autorizado`, que no lee
grants ni amplía la frontera PRINCIPAL_SELF: NO_GRANT PARA LA AUDIENCIA A ≠ AUTORIDAD PARA LA B.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import text

from app.contracts.consent_grant_v0 import Channel
from app.serial_consentimiento import intentar_serializar_consentimiento

log = logging.getLogger(__name__)


class EstadoAutorizacion(StrEnum):
    AUTHORIZED = "AUTHORIZED"
    NO_GRANT = "NO_GRANT"
    ERROR = "ERROR"


@dataclass(frozen=True)
class DecisionReenganche:
    estado: EstadoAutorizacion
    canales: frozenset = field(default_factory=frozenset)
    grant_ids: tuple = ()


_CONDICION = (
    "session_id = :sid "
    "AND audience = 'PRINCIPAL_SELF' AND purpose = 'REENGAGEMENT' "
    "AND action = 'NOTIFY_VERIFIED_UPDATE' AND channel = ANY(:canales) "
    "AND mode = 'once' AND case_ref IS NULL "
    "AND revoked_at IS NULL AND used_at IS NULL "
    "AND granted_at <= statement_timestamp() AND expires_at > statement_timestamp() "
    "AND ( (principal_kind = 'PSEUDONYMOUS_SESSION_PRINCIPAL' AND principal_session_id = :sid "
    "       AND proof_basis = 'RESUME_SECRET_POSSESSION') "
    "   OR (principal_kind = 'AUTHENTICATED_PRINCIPAL' AND principal_auth_user_id = "
    "       (SELECT cs.user_id FROM chat_sessions cs WHERE cs.session_id = :sid)) ) "
    "AND NOT EXISTS (SELECT 1 FROM lead_actividad la "
    "                WHERE la.session_id = :sid AND la.reenganche_cerrado_en IS NOT NULL)"
)


async def autorizar_efecto_reenganche(
    db,
    *,
    session_id: str,
    canales_candidatos,
    reservar: bool,
) -> DecisionReenganche:
    """La decisión. `canales_candidatos` son los canales con destino en `lead_actividad`; la
    salida dice cuáles de ellos (y sólo ellos) pueden usarse. La hora es la de Postgres."""
    canales = sorted({Channel(c).value for c in canales_candidatos})
    if not canales:
        return DecisionReenganche(EstadoAutorizacion.NO_GRANT)
    try:
        existe = (await db.execute(
            text("SELECT to_regclass('public.consent_grant') IS NOT NULL"))).scalar()
        if not existe:
            log.error("Reenganche: consent_grant no existe (¿038 sin aplicar?) — ERROR de autoridad.")
            return DecisionReenganche(EstadoAutorizacion.ERROR)
        if reservar:
            return await _reservar(db, session_id, canales)
        sql = f"SELECT grant_id::text AS grant_id, channel FROM consent_grant WHERE {_CONDICION}"
        filas = (await db.execute(text(sql), {"sid": session_id, "canales": canales})).mappings().all()
    except Exception as exc:  # noqa: BLE001 — sin decisión no hay efecto
        log.error("Reenganche: la frontera de autoridad falló (%s) — ERROR.", type(exc).__name__)
        return DecisionReenganche(EstadoAutorizacion.ERROR)
    if not filas:
        return DecisionReenganche(EstadoAutorizacion.NO_GRANT)
    return DecisionReenganche(
        EstadoAutorizacion.AUTHORIZED,
        canales=frozenset(f["channel"] for f in filas),
        grant_ids=tuple(sorted(f["grant_id"] for f in filas)),
    )


_SAVEPOINT = "reserva_reenganche"


async def _deshacer_reserva(db) -> None:
    """ROLLBACK TO SAVEPOINT + RELEASE: deshace lo que la reserva hizo (`used_at`) y SUELTA el cerrojo de
    consentimiento si se tomó dentro del savepoint (comprobado en PG 15.19 y 17.6); los cerrojos de antes quedan."""
    await db.execute(text(f"ROLLBACK TO SAVEPOINT {_SAVEPOINT}"))
    await db.execute(text(f"RELEASE SAVEPOINT {_SAVEPOINT}"))


async def _reservar(db, session_id: str, canales: list) -> DecisionReenganche:
    """La reserva (consumo) con la frontera de serialización, dentro de un SAVEPOINT. Una excepción sube al
    llamador (`autorizar_efecto_reenganche` → ERROR), como antes.

        SAVEPOINT
        → SENTENCIA 1  try-lock de la sesión (sin esperar)    FALSE → deshacer savepoint → ERROR (ocupada)
        → SENTENCIA 2  revalidación + reserva … RETURNING expires_at > clock_timestamp() AS vigente_ahora
              sin filas                          → deshacer savepoint → NO_GRANT (y el cerrojo se SUELTA)
              alguna fila con vigente_ahora=FALSE → deshacer savepoint → NO_GRANT (used_at NO persiste)
              todas vigentes                      → RELEASE SAVEPOINT  → AUTHORIZED (cerrojo hasta el COMMIT)

    El savepoint hace que el barrido retenga cerrojo SOLO de las sesiones cuya autoridad de verdad reservó
    (acotadas por su presupuesto), no de cada lead sin grant. `vigente_ahora` es una defensa ADICIONAL, no la
    fuente de la autoridad: si la sentencia de reserva esperó un bloqueo de RELACIÓN (p. ej. el ACCESS EXCLUSIVE de
    un DDL) o la retuvo un escritor que no coopera con el cerrojo, su `statement_timestamp()` es de antes de esa
    espera; un grant que venció durante ella no se consume. No convierte ningún SQL manual en un camino autorizado.
    Todo o nada: con varios canales, si UNO no sigue vigente no se reserva ninguno (NO_GRANT)."""
    await db.execute(text(f"SAVEPOINT {_SAVEPOINT}"))
    if not await intentar_serializar_consentimiento(db, session_id):
        await _deshacer_reserva(db)
        log.warning("Reenganche: sesión ocupada (su autoridad está cambiando) — este barrido no decide.")
        return DecisionReenganche(EstadoAutorizacion.ERROR)
    filas = (await db.execute(text(
        f"UPDATE consent_grant SET used_at = statement_timestamp() WHERE {_CONDICION} "
        "RETURNING grant_id::text AS grant_id, channel, expires_at > clock_timestamp() AS vigente_ahora"),
        {"sid": session_id, "canales": canales})).mappings().all()
    if not filas or not all(f["vigente_ahora"] is True for f in filas):
        await _deshacer_reserva(db)
        if filas:
            log.warning("Reenganche: el grant dejó de estar vigente durante la reserva — NO_GRANT, nada consumido.")
        return DecisionReenganche(EstadoAutorizacion.NO_GRANT)
    await db.execute(text(f"RELEASE SAVEPOINT {_SAVEPOINT}"))
    return DecisionReenganche(
        EstadoAutorizacion.AUTHORIZED,
        canales=frozenset(f["channel"] for f in filas),
        grant_ids=tuple(sorted(f["grant_id"] for f in filas)),
    )


async def corredor_autorizado(db, *, session_id: str, activo_id) -> bool:
    """SEC-X2-EGRESS-R0 · audiencia B: ¿puede el corredor del inmueble EXACTO X recibir un efecto
    automático del reenganche sobre este lead (aviso o entrada al experimento tocado/holdout)?

    Solo con el hecho X2 de divulgación: la persona PIDIÓ contacto para (session_id, X), es decir,
    `handoff_sesion.principal_requested_at IS NOT NULL` en la fila de ese par. Es el mismo hecho que
    abre el hilo al corredor (`assets._assert_sesion_del_activo`); aquí no se inventa otro.

    NO lo dan: el prefijo `qr-` ni ninguna atribución (`lead_actividad.activo_id` dice de dónde
    vino, no qué autorizó), ser dueño del inmueble, que el comprador no tenga grant, estar en el
    CRM, el score, estar dormido ni el grupo del experimento. Tampoco lee `consent_grant`: un grant
    del comprador no abre al corredor.

    Un activo o una sesión vacíos, o cualquier fallo de lectura → False (falla cerrado). En ese
    caso deshace la transacción del llamador: el cron lo consulta ANTES de reservar ningún grant,
    así que el rollback no puede tirar un permiso ya consumido."""
    if not session_id or not activo_id:
        return False
    try:
        return bool((await db.execute(
            text("SELECT 1 FROM handoff_sesion WHERE session_id = :s "
                 "AND activo_id = CAST(:a AS uuid) AND principal_requested_at IS NOT NULL"),
            {"s": session_id, "a": str(activo_id)})).scalar())
    except Exception as exc:  # noqa: BLE001 — sin el hecho no hay efecto
        log.error("Reenganche: no se pudo leer la autoridad del corredor (%s) — sin efecto.",
                  type(exc).__name__)
        await db.rollback()
        return False
