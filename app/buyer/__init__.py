"""Buyer Harness de Contexto (FASE 3).

Estado del comprador con procedencia: de dónde salió cada criterio, cuándo, y cuánto
tuvo que interpretar el sistema para construirlo.

**Lo que hay aquí NO son contratos públicos.** Los contratos de F1 viven en
`app/contracts/` y llevan sufijo `V0` (`BuyerContextV0`, `EvidenceRefV0`). Este paquete
contiene representaciones INTERNAS de la costura: se pueden cambiar sin versionar, y
nada fuera de F3 debería depender de sus formas.

Estado en F3.0b: la costura existe y **no es autoritativa**. El runtime productivo sigue
usando el carril legacy (`_user_texts` → `extraer_preferencias` → dict) para preferencias
y ranking. Ver `docs/agentic_decision_system/10_PHASE_3_BUYER_EVIDENCE_INPUT_SEAM.md`.
"""
