-- ============================================================
-- Migration 025: la primera PUERTA SUAVE de identidad (F1 del PLAN_Onboarding_Ecosistema)
--
--   POR QUÉ: hasta hoy el correo de un interesado existía SOLO en
--   `handoff_sesion.lead_email`. O sea que la única forma de dejar de ser anónimo era
--   PEDIR UN CORREDOR — el acto de mayor compromiso de todo el recorrido. Todo lo
--   anterior era anónimo y todo lo posterior era del corredor: Contexto convertía en el
--   escalón más difícil y no capturaba nada en ningún otro punto. Puertas suaves: cero.
--
--   Esta es la primera, y es UNA sola: "¿te aviso cuando aparezca algo así?".
--   Se abre solo en el callejón honesto (criterio declarado + nada que encaje) o cuando
--   la persona lo pide. La decide `app/puerta.py`, no el modelo.
--
--   EL NOMBRE. El plan las llamaba `lead`; aquí es `contacto`. `LEAD` es palabra clave
--   en PostgreSQL (función de ventana) y, aunque como nombre de tabla se admite, no vale
--   la pena el riesgo por un nombre. `contacto` además dice lo que es: una persona que
--   dejó un canal, venga de la alerta o del handoff.
--
--   `demanda` ES EL ACTIVO. No es una tabla de apoyo: guarda QUÉ pidió cada persona y si
--   había algo que se lo diera. Las filas con `hubo_match = false` son la demanda NO
--   CUBIERTA de Quito — qué busca la gente que el inventario no tiene. Es la munición
--   para hablar con un promotor y material para el canal, y no existe en ningún otro
--   lado porque nadie más captura la intención declarada, solo clics en filtros.
--
--   PRIVACIDAD. El correo es dato personal con consentimiento explícito y finalidad
--   ACOTADA (avisar cuando algo encaje), declarada en el propio texto de la puerta. No
--   habilita marketing: eso sería otra finalidad y necesitaría su propia base. Un
--   borrado debe alcanzar `contacto`, `demanda`, `visita` y `handoff_sesion`.
--
--   Idempotente: se puede correr varias veces.
-- ============================================================

CREATE TABLE IF NOT EXISTS contacto (
    id          bigserial PRIMARY KEY,
    email       text        NOT NULL,
    session_id  text        NOT NULL,
    device_key  text,
    -- El canal por el que llegó (de su primera `visita`). Contestar "¿de qué canal
    -- vienen los correos que capturamos?" es media razón de existir de F0.
    canal       text,
    -- 'alerta' | 'handoff'. La misma tabla sirve a las dos puertas: la suave y la dura.
    origen      text        NOT NULL DEFAULT 'alerta',
    -- Si la identidad nació anclada a un inmueble concreto. NULL = búsqueda por criterio.
    activo_id   uuid,
    creado_en   timestamptz NOT NULL DEFAULT now(),
    -- Reintentar la misma alerta NO duplica: la puerta se ofrece una vez, pero la red
    -- puede fallar y el usuario reintentar. La idempotencia va en el esquema, no en la fe.
    CONSTRAINT contacto_email_sesion_unico UNIQUE (email, session_id)
);

CREATE TABLE IF NOT EXISTS demanda (
    id            bigserial PRIMARY KEY,
    contacto_id   bigint      REFERENCES contacto(id) ON DELETE CASCADE,
    session_id    text        NOT NULL,
    -- Las preferencias DECLARADAS tal cual las leyó el motor (whitelist cerrada de
    -- app/encaje.py). jsonb para poder agregar por dimensión sin migrar cada vez.
    criterio      jsonb       NOT NULL,
    criterio_texto text,
    -- ★ El campo que convierte esta tabla en un activo: ¿había algo que le sirviera?
    -- false = demanda no cubierta. Es lo que se le enseña a un promotor.
    hubo_match    boolean     NOT NULL,
    -- 'callejon_honesto' | 'lo_pidio' — por qué se abrió la puerta (auditoría).
    motivo        text,
    activo_id     uuid,
    creado_en     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS contacto_creado_en_idx ON contacto (creado_en DESC);
CREATE INDEX IF NOT EXISTS contacto_session_idx   ON contacto (session_id);

-- El reporte que importa: la demanda que NO se pudo satisfacer, más reciente primero.
CREATE INDEX IF NOT EXISTS demanda_sin_match_idx ON demanda (creado_en DESC)
    WHERE hubo_match = false;
CREATE INDEX IF NOT EXISTS demanda_contacto_idx ON demanda (contacto_id);
