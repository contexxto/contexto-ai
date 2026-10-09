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
El cerrojo y la comprobación de frescura van SIEMPRE en sentencias distintas: en una sola sentencia (un CTE), la
foto (snapshot) se tomaría ANTES de obtener el cerrojo y no vería lo que confirmó quien acababa de soltarlo.
Todo ello dentro de un SAVEPOINT (`_reservar`): BUSY, NO_GRANT y la autoridad inestable lo deshacen y SUELTAN el
cerrojo; solo una reserva AUTHORIZED lo conserva hasta el COMMIT.

Defensa adicional: `RETURNING expires_at > clock_timestamp() AS vigente_ahora`. Cubre la espera de FILA durante el
Execute: si un escritor que NO coopera con el cerrojo retiene la fila de un grant y aborta, Postgres sigue con la
tupla original sin re-evaluar el WHERE, cuyo `statement_timestamp()` es de ANTES de esa espera. Si una o más filas
dejaron de estar vigentes durante la sentencia, se deshace la reserva ENTERA y es ERROR, no NO_GRANT:
AUTORIDAD INESTABLE DURANTE LA RESERVA ≠ AUSENCIA DE AUTORIDAD (NO_GRANT dejaría pasar la rama del corredor aunque
el comprador conserve autoridad viva en otro canal); el barrido siguiente decide con estado y hora frescos. Una espera
de RELACIÓN no necesita esta defensa en el camino probado: con asyncpg (protocolo extendido) ocurre ANTES del Execute
y la sentencia nace con hora posterior a la espera (observado en PG 15.19 y 17.6; no se afirma para otros drivers
ni protocolos). Nada en la base obliga a cooperar con el cerrojo (no hay trigger ni privilegio), y durante un deploy
solapado un proceso viejo sin cerrojo convive con el nuevo: la garantía es la de los caminos de la app desplegada,
no la de cualquier SQL.

Resultados:
    AUTHORIZED(canales)  sólo esos canales pueden salir (un grant de EMAIL no autoriza PUSH), y SOLO a los destinos
                         que la decisión devuelve (`email_destino`/`push_destino`): los de la MISMA fotografía
                         serializada que reservó los grants (SEC-X2-EGRESS-DESTINATION-FRESHNESS-R0)
    NO_GRANT             el comprador no recibe nada. NO es autoridad para nadie más: el corredor
                         solo recibe con SU propio hecho (`corredor_autorizado`, SEC-X2-EGRESS-R0;
                         el antiguo «el corredor sigue su camino», DR-15, queda retirado)
    ERROR                no se pudo decidir (038 sin aplicar, sesión ocupada, autoridad inestable durante la
                         reserva, sesión inválida o un fallo de la base): nadie recibe nada, para NINGUNA audiencia

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
from app.serial_consentimiento import _clave as clave_de_consentimiento
from app.serial_consentimiento import intentar_serializar_consentimiento

log = logging.getLogger(__name__)


class EstadoAutorizacion(StrEnum):
    AUTHORIZED = "AUTHORIZED"
    NO_GRANT = "NO_GRANT"
    ERROR = "ERROR"


@dataclass(frozen=True)
class DecisionReenganche:
    """La decisión de la frontera. SEC-X2-EGRESS-DESTINATION-FRESHNESS-R0 · GRANT RESERVADO + DESTINO DEL EFECTO =
    UNA MISMA FOTOGRAFÍA SERIALIZADA: `email_destino`/`push_destino` SOLO los llena una reserva AUTHORIZED, con el
    destino vigente leído bajo el MISMO cerrojo que reservó los grants, y solo para los canales autorizados. En
    cualquier otro caso (NO_GRANT, ERROR, o una consulta sin reserva) van a None: una lectura sin reserva no es una
    fotografía autorizada de egreso."""
    estado: EstadoAutorizacion
    canales: frozenset = field(default_factory=frozenset)
    grant_ids: tuple = ()
    email_destino: str | None = None            # destino EMAIL de la fotografía reservada (solo si EMAIL ∈ canales)
    push_destino: object | None = None          # suscripción PUSH de la fotografía reservada (solo si PUSH ∈ canales)


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

        validar session_id (la misma regla que el cerrojo)    inválida → excepción → ERROR, SIN abrir savepoint
        → SAVEPOINT
        → SENTENCIA 1  try-lock de la sesión (sin esperar)    FALSE → deshacer savepoint → ERROR (ocupada)
        → SENTENCIA 2  revalidación + reserva … RETURNING expires_at > clock_timestamp() AS vigente_ahora
              sin filas                              → deshacer savepoint → NO_GRANT (el cerrojo se SUELTA)
              una o más filas con vigente_ahora=FALSE → deshacer savepoint → ERROR (nada consumido, ninguna audiencia)
              todas vigentes → SENTENCIA 3 destino vigente (lead_actividad), bajo el MISMO cerrojo:
                  algún canal reservado sin su destino → deshacer savepoint → ERROR (D1: nada consumido)
                  todos con destino                    → RELEASE SAVEPOINT  → AUTHORIZED + destinos
                                                         (cerrojo hasta el COMMIT)

    El savepoint hace que el barrido retenga cerrojo SOLO de las sesiones cuya autoridad de verdad reservó, no de
    cada lead sin grant. `vigente_ahora` es una defensa ADICIONAL, no la fuente de la autoridad: cubre la espera de
    FILA durante el Execute (un escritor que no coopera con el cerrojo retiene la fila y aborta; el WHERE no se
    re-evalúa y su hora es de antes de la espera). AUTORIDAD INESTABLE ≠ AUSENCIA DE AUTORIDAD: si una sola fila dejó
    de estar vigente durante la sentencia —aunque otra siga viva— la decisión entera es ERROR, nunca NO_GRANT (que
    abriría la rama del corredor) ni una autorización parcial en esa misma foto; el barrido siguiente recalcula y
    podrá autorizar solo el canal que siga vivo. No convierte ningún SQL manual en un camino autorizado.

    SEC-X2-EGRESS-DESTINATION-FRESHNESS-R0 · AUTORIDAD FRESCA + DESTINO OBSOLETO ≠ EGRESO AUTORIZADO. El destino
    (EMAIL → `lead_actividad.lead_email`, PUSH → `lead_actividad.lead_push`) se lee AQUÍ, con el cerrojo de la sesión
    tomado y en la misma transacción que reservó los grants: su único escritor de la app (el «sí» de /lead-contacto)
    toma ese mismo cerrojo antes de escribirlo, así que reserva y destino son una misma fotografía. El llamador envía
    EXACTAMENTE a esos destinos (nunca a una copia anterior al cerrojo ni a una relectura posterior al COMMIT). D1: un
    canal reservado sin su destino es una fotografía inconsistente → ERROR de la decisión entera, sin autorización
    parcial. El conjunto de canales CANDIDATOS lo fija el llamador (la fase 1 del barrido): esta frontera garantiza
    la FRESCURA del destino de los canales que autoriza, no la COMPLETITUD frente a un canal aparecido después."""
    sid = clave_de_consentimiento(session_id)           # ANTES del SAVEPOINT: una sesión inválida no abre nada
    await db.execute(text(f"SAVEPOINT {_SAVEPOINT}"))
    if not await intentar_serializar_consentimiento(db, sid):
        await _deshacer_reserva(db)
        log.warning("Reenganche: sesión ocupada (su autoridad está cambiando) — este barrido no decide.")
        return DecisionReenganche(EstadoAutorizacion.ERROR)
    filas = (await db.execute(text(
        f"UPDATE consent_grant SET used_at = statement_timestamp() WHERE {_CONDICION} "
        "RETURNING grant_id::text AS grant_id, channel, expires_at > clock_timestamp() AS vigente_ahora"),
        {"sid": sid, "canales": canales})).mappings().all()
    if not filas:
        await _deshacer_reserva(db)
        return DecisionReenganche(EstadoAutorizacion.NO_GRANT)
    if not all(f["vigente_ahora"] is True for f in filas):
        await _deshacer_reserva(db)
        log.warning("Reenganche: la autoridad cambió durante la reserva (un grant dejó de estar vigente) — ERROR, "
                    "nada consumido; el barrido siguiente decide.")
        return DecisionReenganche(EstadoAutorizacion.ERROR)
    autorizados = frozenset(f["channel"] for f in filas)
    destino = (await db.execute(text(                  # SENTENCIA 3: el destino vigente, bajo el MISMO cerrojo
        "SELECT lead_email, lead_push FROM lead_actividad WHERE session_id = :sid"), {"sid": sid})).mappings().first()
    email = (destino or {}).get("lead_email") if "EMAIL" in autorizados else None
    push = (destino or {}).get("lead_push") if "PUSH" in autorizados else None
    if ("EMAIL" in autorizados and not email) or ("PUSH" in autorizados and not push):
        await _deshacer_reserva(db)
        log.warning("Reenganche: un canal autorizado no tiene destino vigente — ERROR, nada consumido (D1).")
        return DecisionReenganche(EstadoAutorizacion.ERROR)
    await db.execute(text(f"RELEASE SAVEPOINT {_SAVEPOINT}"))
    return DecisionReenganche(
        EstadoAutorizacion.AUTHORIZED,
        canales=autorizados,
        grant_ids=tuple(sorted(f["grant_id"] for f in filas)),
        email_destino=email,
        push_destino=push,
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
