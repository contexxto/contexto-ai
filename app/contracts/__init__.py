"""Contratos del sistema de decisión — Pydantic + JSON Schema, versionados.

FASE 1 (Contracts) del Contexto Agentic Decision System. Aquí viven las unidades
estables que el resto del sistema intercambia. La frontera la fija
`docs/agentic_decision_system/02_CURRENT_TO_TARGET_ARCHITECTURE.md` §5.

Regla de la casa: **lo que se congela mal aquí se arrastra a todas las fases.** Por eso
cada contrato lleva su versión dentro del objeto y ninguno se reescribe en sitio: una
regla nueva que rompa compatibilidad crea un `v1`, no muta el `v0`.

Estado (2026-08-25):
  · E1.1 `EvidenceRefV0`     — hecho, en `evidence_v0.py`
  · E1.2 `BuyerContextV0`    — hecho, en `buyer_v0.py`
  · E1.3 `PropertyContextV0` — hecho, en `property_v0.py`
  · E1.4 `PlaceContextV0`    — hecho, en `place_v0.py`
  · E1.5 `DecisionContextV0` — hecho, en `decision_v0.py`
  · E1.6 `DecisionTraceV0`   — hecho, en `trace_v0.py`

Los seis quedan cerrados el 2026-08-25. Esta fase es de contratos, no de integración:
nada de aquí cambia todavía el comportamiento del producto, y nadie los consume.

Regla de alcance de F1: si una decisión adicional no hace falta para representar el
contrato y probarlo, no se congela en V0. No se inventa infraestructura futura.
"""

from app.contracts.buyer_v0 import (
    CONTRACT_VERSION as BUYER_CONTEXT_V0_VERSION,
)
from app.contracts.buyer_v0 import (
    BuyerContextV0,
    CommuteAnchorV0,
    CriterionOrigin,
    CriterionStatus,
    DecisionCriterionV0,
    Direction,
    FieldEvidence,
    Financial,
    Mobility,
    Money,
    Objective,
    Operator,
    PlacePreference,
    PropertyRequirements,
    Tradeoff,
    UnresolvedQuestion,
)
from app.contracts.place_v0 import (
    CONTRACT_VERSION as PLACE_CONTEXT_V0_VERSION,
)
from app.contracts.place_v0 import (
    GeoPoint,
    IsochroneV0,
    MeasureStatus,
    NamedMeasureV0,
    NearbyPlaceV0,
    NearestTransitV0,
    PlaceContextV0,
    PlaceMeasureV0,
    TravelToAnchorV0,
)
from app.contracts.common_v0 import ContractBase, Money, Objective, RankingEntryV0, TravelMode
from app.contracts.decision_v0 import (
    CONTRACT_VERSION as DECISION_CONTEXT_V0_VERSION,
)
from app.contracts.decision_v0 import (
    BuyerContextRefV0,
    DecisionContextV0,
    DecisionTradeoffV0,
    ExplanationV0,
    Impact,
    NextActionType,
    RecommendedNextActionV0,
    Severity,
    VerificationStatus,
    EligibilityV0,
    MatchDimensionV0,
    MatchV0,
    PlaceContextRefV0,
    PropertyContextRefV0,
    StrengthV0,
    UncertaintyV0,
    ViolationV0,
)
from app.contracts.evidence_v0 import (
    CONTRACT_VERSION as EVIDENCE_REF_V0_VERSION,
)
from app.contracts.evidence_v0 import (
    EvidenceRefV0,
    PersistencePolicy,
    SourceType,
    ahora,
)
from app.contracts.property_v0 import (
    CONTRACT_VERSION as PROPERTY_CONTEXT_V0_VERSION,
)
from app.contracts.trace_v0 import (
    CONTRACT_VERSION as DECISION_TRACE_V0_VERSION,
)
from app.contracts.trace_v0 import (
    CallStatus,
    DecisionTraceV0,
    DerivedFeatureV0,
    FactUsedV0,
    PolicyAppliedV0,
    ProviderCallV0,
    TraceRankingEntryV0,
    TraceUncertaintyV0,
)
from app.contracts.property_v0 import (
    PROVIDER_TYPE_CONTEXTO,
    Availability,
    InventoryClass,
    Location,
    Media,
    Operation,
    PropertyAttribute,
    PropertyContextV0,
    PropertyProvenanceV0,
    Quality,
    Transaction,
)

__all__ = [
    # E1.1 — evidencia
    "EvidenceRefV0",
    "EVIDENCE_REF_V0_VERSION",
    "SourceType",
    "PersistencePolicy",
    "ahora",
    # E1.2 — comprador
    "BuyerContextV0",
    "BUYER_CONTEXT_V0_VERSION",
    "Objective",
    "Direction",
    "Operator",
    "CriterionOrigin",
    "CriterionStatus",
    "DecisionCriterionV0",
    "TravelMode",
    "Money",
    "Financial",
    "PropertyRequirements",
    "CommuteAnchorV0",
    "Mobility",
    "PlacePreference",
    "Tradeoff",
    "UnresolvedQuestion",
    "FieldEvidence",
    # E1.3 — inmueble
    "PropertyContextV0",
    "PROPERTY_CONTEXT_V0_VERSION",
    "PROVIDER_TYPE_CONTEXTO",
    "Operation",
    "Location",
    "PropertyAttribute",
    "Transaction",
    "Media",
    "InventoryClass",
    "PropertyProvenanceV0",
    "Quality",
    # E1.4 — lugar
    "PlaceContextV0",
    "PLACE_CONTEXT_V0_VERSION",
    "PlaceMeasureV0",
    "MeasureStatus",
    "GeoPoint",
    "NearestTransitV0",
    "NearbyPlaceV0",
    "TravelToAnchorV0",
    "IsochroneV0",
    "NamedMeasureV0",
    # E1.5 — decisión
    "DecisionContextV0",
    "DECISION_CONTEXT_V0_VERSION",
    "BuyerContextRefV0",
    "PropertyContextRefV0",
    "PlaceContextRefV0",
    "EligibilityV0",
    "ViolationV0",
    "MatchV0",
    "MatchDimensionV0",
    "StrengthV0",
    "DecisionTradeoffV0",
    "UncertaintyV0",
    # E1.6 — traza
    "DecisionTraceV0",
    "DECISION_TRACE_V0_VERSION",
    "ProviderCallV0",
    "CallStatus",
    "FactUsedV0",
    "DerivedFeatureV0",
    "PolicyAppliedV0",
    "TraceUncertaintyV0",
    "TraceRankingEntryV0",
    # compartidos
    "ContractBase",
    "Money",
    "TravelMode",
    "RankingEntryV0",
    "Availability",
    "ExplanationV0",
    "VerificationStatus",
    "Severity",
    "Impact",
    "NextActionType",
    "RecommendedNextActionV0",
]
