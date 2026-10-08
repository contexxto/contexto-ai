"""Plan 1.1 · TR-5 — productor y revocación de `ConsentGrantV0` para el reenganche al comprador.

UN productor: `POST /api/v1/chat/lead-contacto` con `consent=true`, que es la acción explícita
de la persona (G7f: el agente nunca produce un grant; `app/agent/` no importa este módulo, y
`tests/test_tr5_consent_grant.py` lo impone). UNA revocación: `_reducir_autoridad_reenganche`
(control de la UI y enlace de baja firmado de TR-2).

Quién DECIDE si un efecto está autorizado no vive aquí: vive en `app/autoridad_reenganche.py`,
la frontera única. Este módulo sólo escribe evidencia de permiso y la retira.

Valores fijados por el fundador el 28-sep-2026 (TR5-A..D):

    purpose  REENGAGEMENT · audience PRINCIPAL_SELF · action NOTIFY_VERIFIED_UPDATE
    mode     once (standing existe en el contrato, sin productor)
    expires  granted_at + 30 días · un grant POR CANAL (EMAIL | PUSH)

SEC-X2-GRANT-REVOCATION-FRESHNESS-R0 · LAS DOS REVOCACIONES usan `revoked_at = statement_timestamp()`
(la hora de ESA sentencia), no `now()` (el inicio de la transacción del llamador). La 038 exige
`revoked_at >= granted_at`: con `now()`, una transacción que empezó ANTES de que se creara un grant
(un «sí» concurrente) intentaba revocarlo con una hora anterior a su `granted_at`, el CHECK rechazaba el
UPDATE, el llamador deshacía todo y el grant seguía VIVO —una baja válida que fallaba ABIERTA—. El CHECK
no se toca: es el productor el que debe cumplir el invariante.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app.contracts.consent_grant_v0 import (
    Action,
    Audience,
    AuthenticatedPrincipal,
    Channel,
    ConsentGrantV0,
    GrantScope,
    Mode,
    ProofBasis,
    PseudonymousSessionPrincipal,
    Purpose,
)
from app.sesion_autoridad import Autoridad, PruebaDeAutoridad

VIGENCIA_DIAS = 30

# ── La promesa mostrada: la resuelve el SERVIDOR, nunca el cliente ─────────────────────
# El cliente manda sólo el identificador; el texto exacto sale de aquí y se guarda en la
# provenance. Debe ser IDÉNTICO a `COPY_AVISO.titulo` de frontend/src/avisoReenganche.js (lo
# comprueba tests/test_tr5_consent_grant.py). Un texto nuevo es una versión nueva, no una
# edición de ésta: los grants ya emitidos citan la versión que la persona vio.
COPIES_DE_CONSENTIMIENTO: dict[str, str] = {
    "REENGAGEMENT_CONSENT_V1": (
        "Activa esta opción para poder recibir, como máximo, un aviso si aparece un dato "
        "verificado nuevo sobre este inmueble. Puedes desactivarla cuando quieras."
    ),
}
SUPERFICIE = "P5"


def copy_de_consentimiento(version: str | None) -> str | None:
    """El texto exacto de una versión conocida, o None si no se reconoce."""
    return COPIES_DE_CONSENTIMIENTO.get(version) if version else None


def principal_de(prueba: PruebaDeAutoridad):
    """`PrincipalRefV0` a partir de la autoridad ya decidida. El cliente no lo elige.

    OWNER                 → AUTHENTICATED_PRINCIPAL(user_id)
    ANONYMOUS_CAPABILITY  → PSEUDONYMOUS_SESSION_PRINCIPAL(session_id, RESUME_SECRET_POSSESSION)
    """
    if prueba.autoridad is Autoridad.OWNER and prueba.owner_user_id:
        return AuthenticatedPrincipal(auth_user_id=prueba.owner_user_id)
    if prueba.autoridad is Autoridad.ANONYMOUS_CAPABILITY:
        return PseudonymousSessionPrincipal(
            session_id=prueba.session_id, proof_basis=ProofBasis.RESUME_SECRET_POSSESSION)
    raise ValueError(f"autoridad sin principal de grant: {prueba.autoridad}")


async def _tabla_existe(db) -> bool:
    return bool((await db.execute(
        text("SELECT to_regclass('public.consent_grant') IS NOT NULL"))).scalar())


async def crear_grants_reenganche(
    db,
    *,
    prueba: PruebaDeAutoridad,
    canales: list[Channel],
    copy_version: str,
    activo_ref: str | None,
) -> str:
    """Registra UN grant por canal presentado, en la transacción del llamador (la misma que
    probó la autoridad). Devuelve el `approval_event_ref` que comparten los grants del acto.

    Antes de insertar revoca los grants VIVOS de la misma sesión, propósito y canal: un nuevo
    «sí» sustituye al anterior, nunca lo reactiva. Sin la tabla (038 sin aplicar) falla: un
    opt-in que no se puede registrar no se da por activado."""
    copy = copy_de_consentimiento(copy_version)
    if copy is None:
        raise ValueError("versión de copy desconocida")
    if not canales:
        raise ValueError("sin canal no hay grant")
    principal = principal_de(prueba)
    evento = str(uuid.uuid4())
    provenance = {
        "approval_event_ref": evento,
        "surface": SUPERFICIE,
        "consent_copy_version": copy_version,
        "consent_copy_exact": copy,
        "authority_basis": prueba.autoridad.value,
        "session_id": prueba.session_id,
        "activo_ref": activo_ref,
    }
    if prueba.capability_issued_at:
        provenance["capability_issued_at"] = prueba.capability_issued_at

    ahora = datetime.now(timezone.utc)
    for canal in canales:
        # El contrato valida la forma antes de tocar la base; la hora real la pone Postgres.
        ConsentGrantV0(
            grant_id=evento, principal_ref=principal, audience=Audience.PRINCIPAL_SELF,
            purpose=Purpose.REENGAGEMENT,
            scope=GrantScope(action=Action.NOTIFY_VERIFIED_UPDATE, channel=canal),
            mode=Mode.ONCE, granted_at=ahora, expires_at=ahora + timedelta(days=VIGENCIA_DIAS),
            provenance=provenance,
        )

    valores = [c.value for c in canales]
    await db.execute(
        text("UPDATE consent_grant SET revoked_at = statement_timestamp() "
             "WHERE session_id = :s AND purpose = 'REENGAGEMENT' AND channel = ANY(:canales) "
             "  AND revoked_at IS NULL AND used_at IS NULL"),
        {"s": prueba.session_id, "canales": valores},
    )
    autenticado = isinstance(principal, AuthenticatedPrincipal)
    for canal in valores:
        await db.execute(
            text(
                "INSERT INTO consent_grant (contract_version, session_id, principal_kind, "
                "  principal_auth_user_id, principal_session_id, proof_basis, audience, purpose, "
                "  action, channel, mode, expires_at, case_ref, provenance) "
                "VALUES ('consent_grant_v0', :s, :kind, CAST(:uid AS uuid), :psid, :proof, "
                "  'PRINCIPAL_SELF', 'REENGAGEMENT', 'NOTIFY_VERIFIED_UPDATE', :canal, 'once', "
                f"  now() + interval '{VIGENCIA_DIAS} days', NULL, "
                "  jsonb_set(CAST(:prov AS jsonb), '{occurred_at}', to_jsonb(now())))"
            ),
            {"s": prueba.session_id, "kind": principal.kind,
             "uid": principal.auth_user_id if autenticado else None,
             "psid": None if autenticado else principal.session_id,
             "proof": None if autenticado else principal.proof_basis.value,
             "canal": canal, "prov": json.dumps(provenance)},
        )
    return evento


async def revocar_grants_reenganche(db, session_id: str) -> None:
    """Revoca TODOS los grants REENGAGEMENT vivos de la sesión (todos los canales), en la
    transacción del llamador. Sólo reduce: nunca crea, nunca reactiva (`revoked_at` jamás
    vuelve a NULL). Sin la tabla no hay grants que revocar, y la baja sigue funcionando."""
    if not await _tabla_existe(db):
        return
    await db.execute(
        text("UPDATE consent_grant SET revoked_at = statement_timestamp() "
             "WHERE session_id = :s AND purpose = 'REENGAGEMENT' "
             "  AND revoked_at IS NULL AND used_at IS NULL"),
        {"s": session_id},
    )
