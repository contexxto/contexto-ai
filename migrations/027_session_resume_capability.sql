-- ============================================================
-- Migration 027: la conversación deja de autorizarse a sí misma (AUTH-READ-GATE.1)
--
--   POR QUÉ: hasta hoy `session_id` cumplía dos papeles incompatibles — identificaba la
--   conversación Y daba acceso a ella. Conocer el identificador bastaba para leer el hilo
--   (`/history`, `/handoff`, `/intencion`), escribir en él (`POST /chat`) y, si no tenía
--   dueño, apropiárselo (`COALESCE` en `_tag_session_owner`) o publicarlo (`share`).
--   El inventario completo son 18 endpoints; 12 dependían de esa autoridad implícita.
--   Caracterizado en docs/agentic_decision_system/12_AUTH_READ_GATE_*.md.
--
--   session_id identifica una conversación; nunca demuestra autoridad sobre ella.
--
--   LO QUE AÑADE: una capacidad de REANUDACIÓN para los hilos anónimos. El servidor emite
--   un secreto al CREAR la sesión y guarda solo su hash; el cliente lo presenta en cada
--   petición. Un hilo con dueño no la necesita: ahí manda la identidad autenticada.
--
--   POR QUÉ HASH Y NO EL SECRETO: si la base se filtrara, los secretos en claro serían
--   llaves reutilizables de conversaciones ajenas. Con SHA-256 y 32 bytes de entropía no
--   hace falta pepper ni KMS todavía; si algún día se añade, esta columna es el sitio.
--
--   POR QUÉ SIN EXPIRACIÓN AÚN: no sabemos cuánto dura de verdad una conversación de QR,
--   y un TTL inventado expulsaría a gente en mitad de su recorrido. `revoked_at` existe
--   desde el primer día igualmente: "sin caducidad automática" NO es "irrevocable" — al
--   reclamar un hilo anónimo, su capacidad se revoca en el acto.
--
--   LOS HILOS ANÓNIMOS PREVIOS NO TIENEN FILA AQUÍ, y eso no se puede arreglar: nacieron
--   sin registro autoritativo (`_tag_session_owner` retornaba antes de insertar para los
--   anónimos). No existe forma criptográficamente honesta de emitirles una capacidad
--   ahora: cualquiera que conociera el id la reclamaría. Se quedan sin reanudar, y el
--   frontend abre una sesión nueva. Es una pérdida deliberada de compatibilidad.
--
--   Idempotente: se puede correr varias veces.
-- ============================================================

-- ── La capacidad de reanudación ──────────────────────────────────────────────
-- Solo para hilos anónimos. Un hilo con `user_id` se autoriza por identidad.
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS resume_token_hash    TEXT;
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS resume_issued_at     TIMESTAMPTZ;
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS resume_revoked_at    TIMESTAMPTZ;

COMMENT ON COLUMN chat_sessions.resume_token_hash IS
    'SHA-256 hex del secreto de reanudación. NUNCA el secreto. NULL = sin capacidad '
    '(hilo con dueño, o sesión anterior al gate que no puede reanudarse).';
COMMENT ON COLUMN chat_sessions.resume_revoked_at IS
    'Se sella al reclamar el hilo una cuenta. Desde ese instante solo autoriza el dueño: '
    'mantener viva la capacidad sería conservar un segundo acceso bearer en silencio.';

-- SIN ÍNDICE NUEVO, Y ES DELIBERADO.
--
-- Una versión anterior de esta migración creaba un índice parcial sobre `session_id`
-- justificado como "búsqueda por hash en cada petición anónima". Era falso por partida
-- doble: el índice era sobre `session_id` —que ya es PRIMARY KEY, así que nunca habría un
-- plan mejor— y la única consulta de autoridad es
--
--     SELECT … FROM chat_sessions WHERE session_id = :sid
--
-- que no filtra por el hash en absoluto: la comparación ocurre en Python, en tiempo
-- constante (`hmac.compare_digest`), sobre la fila ya recuperada. Un índice sobre el hash
-- tampoco serviría, y además sería contraproducente — indexar el material de una capacidad
-- facilita confirmarla por sondeo.
--
-- Se retira antes de aplicarla en ningún entorno (verificado: producción está en
-- `PROD_SCHEMA_027 = NOT_APPLIED`). Si algún día la autoridad busca POR hash, el índice
-- correcto será sobre `resume_token_hash` y habrá que sopesar ese riesgo entonces.

-- ── La frontera de creación ──────────────────────────────────────────────────
-- Distingue "esta sesión acaba de nacer" de "este id ya existía". Sin esto, la regla
-- ingenua —"si no trae token, emito uno"— dejaría que cualquiera que conozca un
-- session_id existente pidiera una capacidad válida para él: cambiaríamos una puerta
-- abierta por otra con apariencia de seguridad, que es peor porque no se ve.
-- El bootstrap usa `INSERT ... ON CONFLICT DO NOTHING RETURNING`: si no devuelve fila,
-- el id ya existía y NO se emite capacidad.
ALTER TABLE chat_sessions ADD COLUMN IF NOT EXISTS creada_por_servidor BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN chat_sessions.creada_por_servidor IS
    'true = el session_id lo generó el bootstrap del servidor. false = fila creada por el '
    'camino legacy (etiquetado de dueño), donde el id lo eligió el cliente.';

-- Verificación (debe devolver 4)
SELECT count(*) AS columnas_creadas
FROM information_schema.columns
WHERE table_name = 'chat_sessions'
  AND column_name IN ('resume_token_hash', 'resume_issued_at',
                      'resume_revoked_at', 'creada_por_servidor');

-- ROLLBACK:
--   ALTER TABLE chat_sessions
--     DROP COLUMN IF EXISTS resume_token_hash,
--     DROP COLUMN IF EXISTS resume_issued_at,
--     DROP COLUMN IF EXISTS resume_revoked_at,
--     DROP COLUMN IF EXISTS creada_por_servidor;
--   OJO: revertir deja los 12 endpoints sin autoridad de reanudación. Si el código del
--   gate sigue desplegado, el carril anónimo queda inaccesible — revertir código primero.
