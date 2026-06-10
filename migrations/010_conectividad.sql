-- ============================================================================
-- Contexto AI · Migración 010 — Conectividad (señal de plusvalía por transporte)
-- ----------------------------------------------------------------------------
-- Guarda un resumen legible de los hubs de transporte masivo cercanos (Metro,
-- Terminal terrestre, estaciones) con su distancia. Se extrae automáticamente
-- de OpenStreetMap al publicar (mismos POIs del Walk Score) y lo usa el agente
-- para destacar la conectividad — un catalizador de valorización.
-- Ej.: "🚇 Quitumbe a ~280 m · 🚉 Terminal Terrestre Quitumbe a ~450 m"
-- ============================================================================

ALTER TABLE activos_inmutables ADD COLUMN IF NOT EXISTS conectividad TEXT;
