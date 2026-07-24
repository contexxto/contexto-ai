-- ============================================================
-- Migration 018: Persistencia del Motor de Intención — intencion_sesion + intencion_evento
--   Fase 0 del MOTOR_Intencion_Contexto.md ("instrumentar, sin UI"): guardar el
--   estado + score EXPLICABLE que app/intencion.py calcula por sesión, para que el
--   embudo sea MEDIBLE (lift de intención, handoffs calificados — la North Star metric).
--
--   Dos tablas:
--     · intencion_sesion  — estado ACTUAL por sesión (upsert cada turno).
--     · intencion_evento  — log append-only (una fila por CAMBIO de estado) → serie
--                            temporal para medir el LIFT y las transiciones del embudo.
--
--   Llave: session_id (text) = el thread_id del agente (patrón qr-{session} / crm-{user}),
--   el mismo que usan chat_sessions (006) y handoff_mensaje. NO se pone FK dura a
--   chat_sessions: las sesiones ANÓNIMAS (estado 0, que queremos medir) pueden no tener
--   fila allí. session_id es la llave compartida, no una dependencia.
--
--   Fair Housing (fair_housing.py / COMPLIANCE_FairHousing_AgentSpec): 'senales' guarda
--   SOLO señales transaccionales declaradas (precio/visita/ficha/zona/uso), nunca
--   composición del hogar ni proxies de clase protegida. Es lo que el motor ya computa.
-- ============================================================

-- ── Estado ACTUAL por sesión ────────────────────────────────
CREATE TABLE IF NOT EXISTS intencion_sesion (
    session_id       text PRIMARY KEY,
    activo_id        uuid REFERENCES activos_inmutables(id) ON DELETE SET NULL,
    estado           text NOT NULL,
    nivel            text NOT NULL,
    score            integer NOT NULL DEFAULT 0,
    handoff_sugerido boolean NOT NULL DEFAULT false,
    turnos           integer NOT NULL DEFAULT 0,
    razones          jsonb NOT NULL DEFAULT '[]'::jsonb,
    senales          jsonb NOT NULL DEFAULT '{}'::jsonb,
    resumen          text,
    primer_visto     timestamptz NOT NULL DEFAULT now(),
    actualizado_en   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS intencion_sesion_estado_idx ON intencion_sesion (estado);
CREATE INDEX IF NOT EXISTS intencion_sesion_activo_idx ON intencion_sesion (activo_id);
CREATE INDEX IF NOT EXISTS intencion_sesion_handoff_idx ON intencion_sesion (handoff_sugerido) WHERE handoff_sugerido;

-- Constraints (idempotentes: Postgres no soporta ADD CONSTRAINT IF NOT EXISTS)
ALTER TABLE intencion_sesion DROP CONSTRAINT IF EXISTS ck_intencion_estado;
ALTER TABLE intencion_sesion ADD  CONSTRAINT ck_intencion_estado
    CHECK (estado IN ('anonimo','identificado','explorando','enganchado',
                      'intencion','confirmado','completado','returning','dormido'));

ALTER TABLE intencion_sesion DROP CONSTRAINT IF EXISTS ck_intencion_nivel;
ALTER TABLE intencion_sesion ADD  CONSTRAINT ck_intencion_nivel
    CHECK (nivel IN ('frio','tibio','caliente'));

ALTER TABLE intencion_sesion DROP CONSTRAINT IF EXISTS ck_intencion_score;
ALTER TABLE intencion_sesion ADD  CONSTRAINT ck_intencion_score
    CHECK (score BETWEEN 0 AND 100);

-- ── Log append-only de cambios de estado (para medir el lift) ─
CREATE TABLE IF NOT EXISTS intencion_evento (
    id               bigserial PRIMARY KEY,
    session_id       text NOT NULL,
    activo_id        uuid,
    estado           text NOT NULL,
    nivel            text NOT NULL,
    score            integer NOT NULL DEFAULT 0,
    handoff_sugerido boolean NOT NULL DEFAULT false,
    creado_en        timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS intencion_evento_sesion_idx ON intencion_evento (session_id, creado_en);
CREATE INDEX IF NOT EXISTS intencion_evento_estado_idx ON intencion_evento (estado, creado_en);

-- Verificación (debe devolver 2)
SELECT count(*) AS tablas_creadas
FROM information_schema.tables
WHERE table_name IN ('intencion_sesion','intencion_evento');

-- ============================================================
-- ROLLBACK:
--   DROP TABLE IF EXISTS intencion_evento;
--   DROP TABLE IF EXISTS intencion_sesion;
-- ============================================================
