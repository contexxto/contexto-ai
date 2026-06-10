-- ============================================================================
-- Contexto AI · Migración 009 — Compartir conversación (enlace público de lectura)
-- ----------------------------------------------------------------------------
-- Permite generar un enlace público de SOLO LECTURA de una conversación (estilo
-- Claude). El dueño activa "cualquiera con el enlace"; puede revocarlo (is_public
-- = false). El token es el identificador del enlace público.
-- ============================================================================

ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS share_token TEXT;
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS is_public  BOOLEAN NOT NULL DEFAULT false;
CREATE UNIQUE INDEX IF NOT EXISTS uq_chat_sessions_share_token
    ON chat_sessions (share_token) WHERE share_token IS NOT NULL;
