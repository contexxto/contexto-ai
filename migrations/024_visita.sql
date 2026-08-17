-- ============================================================
-- Migration 024: la LLEGADA se registra (F0 del PLAN_Onboarding_Ecosistema)
--
--   POR QUÉ: el sistema no podía responder "¿por dónde entró esta persona?".
--
--     · `fuente` en el CRM era la constante 'QR' para todo el mundo, incluidos los
--       leads que no vinieron de un QR (desde el fix del 2026-08-05 se listan igual).
--     · No había captura de utm ni de document.referrer en NINGÚN punto del repo.
--     · El QR que alguien escanea y no escribe se descartaba sin dejar contador —
--       y es la señal más fuerte del sistema: esa persona estaba parada frente al
--       inmueble, con el letrero delante.
--
--   Consecuencia: los dos motores de adquisición declarados (el canal de YouTube y
--   la estrategia AEO) no tenían forma de medirse. Se iba a invertir en dos canales
--   que el sistema no podía ver.
--
--   QUÉ ES ESTA TABLA. Un LOG DE EVENTOS append-only, no un estado. Una fila por
--   llegada; la deduplicación se hace al consultar, no al escribir. Es deliberado:
--   dos escaneos del mismo letrero en un día son dos escaneos, y colapsarlos al
--   escribir destruiría el dato que esta tabla existe para capturar.
--
--   LA PARTE ALTA DEL EMBUDO que esto hace visible por primera vez:
--       visitas → conversaciones → ancladas a un inmueble → piden corredor
--   Hoy solo se ve el último escalón, y el cuello de botella declarado (adopción y
--   conversión) vive justo en los dos invisibles.
--
--   PRIVACIDAD. `referrer` se guarda SIN query string (ahí viajan tokens, correos y
--   términos de búsqueda); lo minimiza `app/llegada.py::limpiar_referrer` en el único
--   punto donde el dato entra. `device_key` es un identificador en línea: cuenta como
--   dato personal aunque no traiga nombre, así que una supresión debe alcanzar TAMBIÉN
--   esta tabla, no solo handoff_sesion.
--
--   Idempotente: se puede correr varias veces.
-- ============================================================

CREATE TABLE IF NOT EXISTS visita (
    id           bigserial PRIMARY KEY,
    session_id   text        NOT NULL,
    -- NULL = llegó SIN inmueble anclado (home, campaña de zona, búsqueda orgánica).
    -- Que sea nullable es el punto: hoy el lead se reconstruye barriendo el
    -- checkpointer por el prefijo 'qr-{activo}-', y por eso una conversación sin
    -- inmueble no existe para nadie. Aquí sí existe.
    activo_id    uuid,
    -- Listas CERRADAS, definidas en app/llegada.py (SUPERFICIES / CANALES). No se
    -- valida con un CHECK a propósito: la lista va a crecer y una migración por cada
    -- canal nuevo es peor que un valor raro que el reporte deja ver.
    superficie   text        NOT NULL,
    canal        text        NOT NULL,
    utm_source   text,
    utm_medium   text,
    utm_campaign text,
    utm_content  text,
    referrer     text,
    device_key   text,
    creado_en    timestamptz NOT NULL DEFAULT now()
);

-- El reporte semanal por canal: "¿cuántas llegadas de cada canal esta semana?"
CREATE INDEX IF NOT EXISTS visita_creado_en_idx ON visita (creado_en DESC);

-- Los escaneos de UN inmueble: lo que el corredor quiere saber de su letrero.
CREATE INDEX IF NOT EXISTS visita_activo_idx ON visita (activo_id, creado_en DESC)
    WHERE activo_id IS NOT NULL;

-- El canal de UNA sesión: lo consulta el CRM para que `fuente` deje de ser 'QR' fijo.
CREATE INDEX IF NOT EXISTS visita_session_idx ON visita (session_id);
