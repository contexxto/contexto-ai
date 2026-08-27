-- ============================================================
-- Migration 028: el estado del comprador deja de vivir solo en el hilo (E3.1b)
--
--   QUÉ AÑADE: el almacén durable y versionado del `BuyerContextV0`. Dos tablas —una
--   cabeza por comprador y un historial append-only de revisiones— y nada más. No hay
--   extracción, ni interpretación, ni conexión con el agente: eso es E3.2.
--
--   POR QUÉ CABEZA + REVISIONES, y no una fila que se sobrescribe. Una sola fila mutable
--   resolvería "cuál es el estado actual" y rompería las otras tres cosas que ya sabemos
--   que pasan antes de meter un LLM en el camino:
--
--     1. HISTORIA. Un estado que se pisa no puede explicarse. "¿Por qué el sistema cree
--        que quiero tres dormitorios?" deja de tener respuesta en cuanto la siguiente
--        actualización borra la anterior.
--     2. REINTENTOS. El mismo mensaje puede procesarse dos veces (retry de red, replay de
--        una cola). Sin `UNIQUE (buyer_id, source_message_id)` eso produce dos revisiones
--        del mismo hecho.
--     3. CONCURRENCIA. Un mismo comprador puede tener dos conversaciones abiertas. Sin
--        una revisión sobre la que hacer control optimista, la segunda escritura pisa a la
--        primera y la pérdida es silenciosa.
--
--   POR QUÉ JSONB Y NO TABLAS NORMALIZADAS: no hay todavía evidencia de producto que
--   diga cómo se van a consultar los criterios, las anclas o los tradeoffs. Normalizar
--   ahora es fijar una forma que aún no conocemos. El snapshot completo preserva el
--   contrato, permite round-trip exacto y no impide normalizar después. Lo que **no** se
--   negocia es que se rehidrate siempre a través de `BuyerContextV0`: un `dict` leído de
--   la base no es un BuyerContext hasta que el contrato lo valida.
--
--   RAÍZ DE IDENTIDAD: `auth.users.id`, el sujeto autenticado. E3.1a lo dejó decidido y
--   AUTH-READ-GATE.1 lo reforzó: ni `session_id`, ni `thread_id`, ni `device_key` sirven
--   como raíz — su conocimiento otorga acceso, así que no identifican a nadie.
--
--   **NO hay comprador durable anónimo.** El visitante sin cuenta no tiene fila aquí; su
--   memoria sigue acotada al hilo. Inventarle una identidad (cookie, device, sesión)
--   sería reintroducir por la puerta de atrás lo que el gate acaba de cerrar.
--
--   NO SE APLICA EN PRODUCCIÓN EN ESTA UNIDAD. El store no está conectado a nada; el
--   momento de migrar producción es cuando se conecte al flujo real (E3.2+).
--
--   Idempotente: se puede correr varias veces.
-- ============================================================

-- ── La cabeza: cuál es la revisión vigente de cada comprador ─────────────────
--
-- Existe separada del historial por dos razones. Una es de lectura: "el estado actual"
-- es una consulta por clave primaria, no un `ORDER BY … LIMIT 1` sobre el historial. La
-- otra es de escritura, y es la importante: da una fila **única por comprador** sobre la
-- que serializar (`SELECT … FOR UPDATE`), que es lo que hace demostrable el control de
-- concurrencia. Sin ella, dos escrituras simultáneas no tienen nada que bloquear.
CREATE TABLE IF NOT EXISTS buyer_context_heads (
    -- Misma FK que usa `profiles` desde la 008. `profiles` NO sirve como raíz: es una
    -- proyección local que puede no estar provisionada, y la existencia del comprador no
    -- puede depender de eso. La raíz es el sujeto autenticado.
    buyer_id          UUID PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
    current_revision  INTEGER     NOT NULL CHECK (current_revision >= 0),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMENT ON TABLE buyer_context_heads IS
    'Revisión vigente del BuyerContextV0 de cada comprador. Una fila por sujeto '
    'autenticado. Es también el punto de serialización del control de concurrencia.';

-- ── El historial: append-only, nunca se actualiza ───────────────────────────
CREATE TABLE IF NOT EXISTS buyer_context_revisions (
    buyer_id          UUID        NOT NULL
                      REFERENCES buyer_context_heads (buyer_id) ON DELETE CASCADE,
    context_revision  INTEGER     NOT NULL CHECK (context_revision >= 0),

    -- El `id` del HumanMessage que motivó esta revisión. Es el identificador que ya
    -- existe en el hilo (LangGraph se lo asigna); no se fabrica ni se deriva del texto.
    source_message_id TEXT        NOT NULL,

    -- El `BuyerContextV0` completo. Se rehidrata SIEMPRE por el contrato.
    context_json      JSONB       NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),

    PRIMARY KEY (buyer_id, context_revision),

    -- LA INVARIANTE DE IDEMPOTENCIA. Un mensaje produce como mucho una revisión de ese
    -- comprador. Es una restricción de la base y no una comprobación en Python a
    -- propósito: bajo concurrencia, comprobar-y-luego-insertar tiene una ventana; el
    -- índice único no la tiene.
    CONSTRAINT uq_buyer_context_revisions_mensaje UNIQUE (buyer_id, source_message_id)
);

COMMENT ON TABLE buyer_context_revisions IS
    'Historial append-only del BuyerContextV0. NUNCA se hace UPDATE ni DELETE sobre estas '
    'filas: se borran solo por cascada al eliminarse la cuenta.';
COMMENT ON COLUMN buyer_context_revisions.source_message_id IS
    'HumanMessage.id que motivó la revisión. NO se guarda el texto del mensaje: la '
    'conversación tiene su propio almacenamiento y duplicar el texto duplicaría PII.';

-- Historial de un comprador en orden. La PK ya cubre (buyer_id, context_revision), pero
-- el recorrido natural del historial es cronológico descendente.
CREATE INDEX IF NOT EXISTS ix_buyer_revisions_historia
    ON buyer_context_revisions (buyer_id, context_revision DESC);

-- Verificación (debe devolver 2)
SELECT count(*) AS tablas_creadas
FROM information_schema.tables
WHERE table_name IN ('buyer_context_heads', 'buyer_context_revisions');

-- ROLLBACK:
--   DROP TABLE IF EXISTS buyer_context_revisions;
--   DROP TABLE IF EXISTS buyer_context_heads;
--   Sin datos productivos que preservar mientras el store no esté conectado (E3.1b no
--   lo aplica en producción). En cuanto se conecte, revertir BORRA el historial del
--   comprador — y ese historial es justamente lo que no se puede reconstruir.
