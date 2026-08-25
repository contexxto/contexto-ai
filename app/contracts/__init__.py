"""Contratos del sistema de decisión — Pydantic + JSON Schema, versionados.

FASE 1 (Contracts) del Contexto Agentic Decision System. Aquí viven las unidades
estables que el resto del sistema intercambia. La frontera la fija
`docs/agentic_decision_system/02_CURRENT_TO_TARGET_ARCHITECTURE.md` §5.

Regla de la casa: **lo que se congela mal aquí se arrastra a todas las fases.** Por eso
cada contrato lleva su versión dentro del objeto y ninguno se reescribe en sitio: una
regla nueva que rompa compatibilidad crea un `v1`, no muta el `v0`.

Estado (2026-08-25):
  · E1.1 `EvidenceRefV0` — hecho, en `evidence_v0.py`
  · E1.2 `BuyerContextV0`    — pendiente
  · E1.3 `PropertyContextV0` — pendiente
  · E1.4 `PlaceContextV0`    — pendiente
  · E1.5 `DecisionContextV0` — pendiente
  · E1.6 `DecisionTraceV0`   — pendiente

Esta fase es de contratos, no de integración: nada de aquí cambia todavía el
comportamiento del producto.
"""

from app.contracts.evidence_v0 import (
    CONTRACT_VERSION as EVIDENCE_REF_V0_VERSION,
)
from app.contracts.evidence_v0 import (
    EvidenceRefV0,
    PersistencePolicy,
    SourceType,
    ahora,
)

__all__ = [
    "EvidenceRefV0",
    "EVIDENCE_REF_V0_VERSION",
    "SourceType",
    "PersistencePolicy",
    "ahora",
]
