-- ============================================================================
-- Contexto AI · Migración 008 — Auth, Roles y Scoping por usuario
-- ----------------------------------------------------------------------------
-- POR QUÉ
--   Introduce identidad de usuario (Supabase Auth) con 3 roles y cierra la fuga
--   de privacidad: cada conversación queda ligada a su dueño.
--
--   Roles:
--     'cliente'      → consumidor final (busca inmuebles)
--     'corredor'     → vendedor; independiente (agency_id NULL) o de agencia
--     'inmobiliaria' → cuenta paraguas que agrupa/autoriza corredores
--
-- SEGURIDAD / NOTAS
--   - profiles.user_id referencia auth.users (gestionado por Supabase Auth).
--   - Idempotente: CREATE/ADD ... IF NOT EXISTS. Se puede correr más de una vez.
--   - El backend valida el JWT de Supabase y aplica el scoping; estas tablas son
--     el modelo de datos sobre el que se apoya.
-- ============================================================================

-- gen_random_uuid() viene de pgcrypto (suele estar activo en Supabase).
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── Agencias (inmobiliarias = cuenta paraguas) ──────────────────────────────
CREATE TABLE IF NOT EXISTS agencies (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nombre       TEXT NOT NULL,
    owner_user   UUID,                                  -- dueño (auth.users.id)
    invite_code  TEXT NOT NULL DEFAULT upper(substr(replace(gen_random_uuid()::text, '-', ''), 1, 8)),
    creado_en    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_agencies_invite_code ON agencies (invite_code);

-- ── Perfiles de usuario (1:1 con auth.users) ────────────────────────────────
CREATE TABLE IF NOT EXISTS profiles (
    user_id    UUID PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
    rol        TEXT NOT NULL DEFAULT 'cliente'
               CHECK (rol IN ('cliente', 'corredor', 'inmobiliaria')),
    nombre     TEXT,
    agency_id  UUID REFERENCES agencies (id) ON DELETE SET NULL,  -- corredor bajo agencia
    creado_en  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_profiles_agency ON profiles (agency_id);

-- ── Scoping de conversaciones por usuario (cierra la fuga de privacidad) ─────
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS user_id UUID;
CREATE INDEX IF NOT EXISTS ix_chat_sessions_user ON chat_sessions (user_id);

-- ── Propiedad de los activos (quién los publicó) ────────────────────────────
ALTER TABLE activos_inmutables ADD COLUMN IF NOT EXISTS owner_user_id   UUID;
ALTER TABLE activos_inmutables ADD COLUMN IF NOT EXISTS owner_agency_id UUID;
CREATE INDEX IF NOT EXISTS ix_activos_owner_user   ON activos_inmutables (owner_user_id);
CREATE INDEX IF NOT EXISTS ix_activos_owner_agency ON activos_inmutables (owner_agency_id);

COMMENT ON TABLE profiles  IS 'Perfil + rol de cada usuario de Supabase Auth.';
COMMENT ON TABLE agencies  IS 'Inmobiliarias (cuenta paraguas). invite_code une corredores al equipo.';
