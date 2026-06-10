-- ============================================================================
-- Contexto AI · Migración 011 — Entorno destacado (servicios cercanos)
-- ----------------------------------------------------------------------------
-- Resumen legible de los "imanes de vida" cercanos: centro comercial, colegios,
-- iglesia, UPC (seguridad), salud, parques, supermercado, farmacia — con nombre
-- y distancia. Se genera al publicar/recalcular (Google Places en vivo si hay
-- API key; si no, OpenStreetMap como base). El agente lo usa para hacer fabuloso
-- el informe del inmueble.
-- Ej.: "🛍️ Quicentro Sur a ~600 m · 🏫 Unidad Educativa Quitumbe a ~300 m · ⛪ ..."
-- ============================================================================

ALTER TABLE activos_inmutables ADD COLUMN IF NOT EXISTS servicios_cercanos TEXT;
