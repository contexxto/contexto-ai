-- ============================================================
-- Migration 026: la ASIGNACIÓN congela al dueño (F2 del PLAN_Onboarding_Ecosistema)
--
--   POR QUÉ: hoy el dueño de un lead se resuelve EN VIVO. `_leads_del_corredor` parte de
--   `activos_inmutables WHERE owner_user_id = :u` y barre; `handoff_sesion` guarda el
--   inmueble pero no a quién se le entregó. El dueño no es un dato del handoff: es una
--   consulta que se rehace cada vez.
--
--   Consecuencia: el día que un corredor pierde el mandato de un inmueble —o la ficha
--   pasa a otra inmobiliaria— TODOS sus leads históricos se mudan con él. El CRM del
--   corredor anterior se vacía de conversaciones que sí atendió, el nuevo hereda un
--   historial que nunca trabajó, y la métrica de lift se reescribe sola hacia atrás. Un
--   cambio de mandato no puede reescribir el pasado.
--
--   LA REGLA: snapshot, no puntero. Al momento del handoff se guarda QUIÉN era el dueño
--   entonces, y esa fila ya no se mueve. El inmueble puede cambiar de manos mañana; la
--   entrega de ayer siguió siendo de quien la recibió.
--
--   ALCANCE DE ESTA MIGRACIÓN — se escribe, todavía no se lee. La tabla empieza a
--   acumular desde ya, pero el CRM sigue resolviendo por `activos_inmutables`. Cambiar
--   la fuente de verdad AHORA vaciaría los CRM: los handoffs anteriores a esta migración
--   no tienen fila aquí, y desaparecerían de la vista de todo el mundo. Primero se
--   acumula historia; el cambio de lectura es su propio paso, con su propio respaldo.
--
--   Idempotente: se puede correr varias veces.
-- ============================================================

CREATE TABLE IF NOT EXISTS asignacion (
    id               bigserial   PRIMARY KEY,
    session_id       text        NOT NULL,
    activo_id        uuid        NOT NULL,
    -- CONGELADOS: copia del dueño en el momento de la entrega, no una referencia viva.
    -- Sin FK a propósito — una FK con ON UPDATE arrastraría el cambio y volvería a atar
    -- el pasado al presente, que es justo lo que esta tabla evita.
    owner_user_id    uuid,
    owner_agency_id  uuid,
    -- 'handoff' hoy; deja sitio para 'alerta' y para la asignación de campaña (F4).
    origen           text        NOT NULL DEFAULT 'handoff',
    -- El canal de la primera visita de la sesión: con qué canal se ganó esta entrega.
    canal            text,
    creado_en        timestamptz NOT NULL DEFAULT now(),
    -- Un hilo por (sesión × inmueble), igual que handoff_sesion: pedir un segundo
    -- corredor por OTRO inmueble es otra asignación, no un reemplazo de la primera.
    CONSTRAINT asignacion_sesion_activo_unica UNIQUE (session_id, activo_id)
);

-- El CRM del futuro: "dame lo que se me asignó a mí", sin pasar por el inmueble.
CREATE INDEX IF NOT EXISTS asignacion_owner_idx ON asignacion (owner_user_id, creado_en DESC);
CREATE INDEX IF NOT EXISTS asignacion_agency_idx ON asignacion (owner_agency_id, creado_en DESC)
    WHERE owner_agency_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS asignacion_session_idx ON asignacion (session_id);
