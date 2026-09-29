"""ConsentGrantV0 — evidencia del permiso de la persona para un comportamiento futuro (Plan 1.1 · TR-5).

Canon: `03_TARGET_DOMAIN_MODEL_DECISION_0.2.md` §5.2–§5.4 (huellas verificadas contra el acta
del 28-sep-2026) y OFD-03 = C acotado. Resoluciones de fundador del 28-sep: TR5-A (30 días),
TR5-B (`used_at` como metadato de ciclo de vida, sin `revocation_source`), TR5-C (valores
exactos de abajo) y TR5-D (un grant por canal).

──────────────────────────────────────────────────────────────────────────────────
QUÉ ES Y QUÉ NO ES
──────────────────────────────────────────────────────────────────────────────────

Es la primitiva concreta que ALIMENTA `AuthorityEnvelope`; no es un segundo sistema de
autoridad. Mapa canónico:

    principal_ref → principal_ref · audience → audience_refs · purpose → purpose_ref
    scope → action_scopes / egress_scopes · granted_at/expires_at → issued_at/expires_at
    provenance → approval_refs / authority_provenance

El SLICE que materializa TR-5 es el del reenganche al comprador y nada más. No hay
disclosure, límites monetarios, jurisdicción ni autonomía: eso es F5/F8.

`PrincipalRefV0` NO es un tercer sistema de identidad: nombra el resultado de la frontera que
ya existe (`app/sesion_autoridad.py`). Correo, teléfono, push y dispositivo NUNCA establecen
el principal.

`used_at` no está aquí a propósito: el contrato congelado (§5.3) no lo tiene. Es metadato de
PERSISTENCIA del ciclo de vida GRANTED → (USED si once) → EXPIRED / REVOKED y vive en la tabla
(`migrations/038_consent_grant_reenganche.sql`); `estado_de_ciclo` lo interpreta.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

CONTRACT_VERSION = "consent_grant_v0"


class ProofBasis(StrEnum):
    """Con qué se probó la autoridad sobre la sesión (`03_` §5.4)."""

    OWNER_SESSION = "OWNER_SESSION"
    """Declarado por el canon; SIN productor en TR-5 (la cuenta dueña produce
    `AUTHENTICATED_PRINCIPAL`, no un principal de sesión)."""

    RESUME_SECRET_POSSESSION = "RESUME_SECRET_POSSESSION"


class AuthenticatedPrincipal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["AUTHENTICATED_PRINCIPAL"] = "AUTHENTICATED_PRINCIPAL"
    auth_user_id: str = Field(..., min_length=1)


class PseudonymousSessionPrincipal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: Literal["PSEUDONYMOUS_SESSION_PRINCIPAL"] = "PSEUDONYMOUS_SESSION_PRINCIPAL"
    session_id: str = Field(..., min_length=1)
    proof_basis: ProofBasis


PrincipalRefV0 = Annotated[
    Union[AuthenticatedPrincipal, PseudonymousSessionPrincipal], Field(discriminator="kind")
]


class Audience(StrEnum):
    PRINCIPAL_SELF = "PRINCIPAL_SELF"
    """El contenido del efecto llega sólo al propio principal: ni corredor ni partner (G7d)."""


class Purpose(StrEnum):
    REENGAGEMENT = "REENGAGEMENT"


class Action(StrEnum):
    NOTIFY_VERIFIED_UPDATE = "NOTIFY_VERIFIED_UPDATE"
    """Un dato verificado nuevo sobre el inmueble de la sesión: lo que el cron envía."""


class Channel(StrEnum):
    EMAIL = "EMAIL"
    PUSH = "PUSH"


class Mode(StrEnum):
    ONCE = "once"
    STANDING = "standing"
    """Válido en el contrato; SIN productor en TR-5, y la frontera no lo autoriza."""


class GrantScope(BaseModel):
    """`scope = { acción + UN canal de salida }` (TR5-D: un grant por canal)."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    action: Action
    channel: Channel


class ConsentGrantV0(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    contract_version: Literal["consent_grant_v0"] = CONTRACT_VERSION
    grant_id: str = Field(..., min_length=1)
    principal_ref: PrincipalRefV0
    audience: Audience
    purpose: Purpose
    scope: GrantScope
    mode: Mode
    granted_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    case_ref: str | None = None
    provenance: dict

    @model_validator(mode="after")
    def _ventana(self):
        if self.expires_at <= self.granted_at:
            raise ValueError("expires_at debe ser posterior a granted_at")
        if self.revoked_at is not None and self.revoked_at < self.granted_at:
            raise ValueError("revoked_at no puede ser anterior a granted_at")
        return self


class EstadoDeCiclo(StrEnum):
    GRANTED = "GRANTED"
    USED = "USED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


def estado_de_ciclo(grant: ConsentGrantV0, *, used_at: datetime | None, ahora: datetime) -> EstadoDeCiclo:
    """GRANTED → (USED si once) → EXPIRED / REVOKED, con `used_at` de la persistencia.

    USED nunca se infiere de `revoked_at`, ni de `reenganche_enviado_en`, ni del grupo del
    experimento: sólo de `used_at` en un grant `once`."""
    if grant.revoked_at is not None:
        return EstadoDeCiclo.REVOKED
    if grant.mode is Mode.ONCE and used_at is not None:
        return EstadoDeCiclo.USED
    if ahora >= grant.expires_at:
        return EstadoDeCiclo.EXPIRED
    return EstadoDeCiclo.GRANTED
