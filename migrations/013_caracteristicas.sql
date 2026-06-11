-- ============================================================================
-- Contexto AI · Migración 013 — Características comerciales del inmueble
-- ----------------------------------------------------------------------------
-- Los datos que pide cualquier anuncio: dormitorios, baños, área, sala/comedor,
-- parqueaderos, amoblado, alícuota, precio negociable, etc. Se guardan como
-- JSONB (flexible, sin churn de esquema) y el agente los usa para describir el
-- inmueble. El precio "duro" sigue en transacciones_temporales.
-- ============================================================================

ALTER TABLE activos_inmutables ADD COLUMN IF NOT EXISTS caracteristicas JSONB;
