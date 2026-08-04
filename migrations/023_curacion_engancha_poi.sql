-- ============================================================
-- Migration 023: la curación del corredor se cuelga del POI (Fase 3, punto 3)
--
--   POR QUÉ: hoy `entorno_curacion` cuelga de `activo_id` y guarda el nombre del
--   lugar como TEXTO LIBRE. Cuando un corredor marca que una farmacia cerró, ese
--   conocimiento queda atrapado en la ficha donde se capturó: el POI sigue vivo para
--   todos los demás inmuebles del barrio y la misma farmacia fantasma se le muestra
--   al siguiente comprador. Había una capa de puntos y una capa de correcciones, y
--   no se tocaban.
--
--   Esto las une. Es el "foso sobre el foso" de SPEC_Foso_Capa_de_Datos.md §1.8:
--   POI abierto × verificación humana con fecha. No se descarga de ninguna API.
--
--   ⚠️ LA DECISIÓN DE DISEÑO CENTRAL — por qué la verificación NO se escribe en
--   `pois_propios`: el refresco semanal (scripts/foso_pois_spike.py, tarea de Windows
--   los lunes 14:00) hace ON CONFLICT DO UPDATE con `operativo = EXCLUDED.operativo`.
--   Si el corredor marcara `operativo=false` sobre la fila del POI, el cron del lunes
--   la RESUCITARÍA en silencio — Overture sigue listando el local como abierto. La
--   fila sobrevive al refresco (migración 020), pero sus columnas se pisan.
--
--   Por eso la curación es un OVERLAY DE LECTURA, el mismo patrón que ya usa
--   app/entorno_curacion.py para el texto ("el catastro base NO se toca; la curación
--   es una capa encima, reversible"). Reparto de autoridad:
--       origen (Overture/OSM) manda en  → nombre, geom, dirección, marca, confianza
--       el humano manda en              → si el lugar EXISTE
--
--   Regla de resolución (la implementa la vista `pois_vivos`):
--     1. La observación humana MÁS RECIENTE por POI gana sobre el origen.
--     2. Entre humanos, gana la más reciente (un local puede reabrir).
--     3. Sin observación humana, decide el origen (`operativo`).
--
--   Compatible hacia atrás: `poi_id IS NULL` = curación de texto libre (lugares que
--   no existen en la capa propia). Ese camino sigue intacto por `aplicar_curacion()`.
-- ============================================================

-- ── 1. La tabla, por si este es un despliegue limpio ────────────────────────
-- `entorno_curacion` NO nace de una migración: la crea en caliente
-- `ensure_curacion_table()` en el primer request que la toca. En una DB nueva la
-- vista de abajo fallaría. Espejo exacto de _CURACION_DDL en app/entorno_curacion.py.
CREATE TABLE IF NOT EXISTS entorno_curacion (
    id             bigserial PRIMARY KEY,
    activo_id      uuid NOT NULL,
    accion         text NOT NULL,
    nombre         text NOT NULL,
    categoria      text,
    distancia_m    integer,
    lat            double precision,
    lon            double precision,
    foto           text,
    corredor_id    uuid,
    creado_en      timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_entorno_cur_activo ON entorno_curacion (activo_id);

-- ── 2. El enganche ──────────────────────────────────────────────────────────
-- ON DELETE SET NULL y no CASCADE: si algún día se borrara la fila del POI, la
-- observación del corredor (que caminó hasta ahí) NO se tira — degrada a curación
-- de texto libre, que es el camino que ya existía.
ALTER TABLE entorno_curacion
    ADD COLUMN IF NOT EXISTS poi_id bigint
    REFERENCES pois_propios (id) ON DELETE SET NULL;

-- Sirve la vista de abajo: "la observación más reciente de este POI".
CREATE INDEX IF NOT EXISTS ix_entorno_cur_poi
    ON entorno_curacion (poi_id, creado_en DESC)
    WHERE poi_id IS NOT NULL;

-- ── 3. La vista que resuelve el overlay ─────────────────────────────────────
-- Columnas ENUMERADAS a propósito, no `p.*`: con `*`, un futuro ALTER TABLE sobre
-- pois_propios haría que CREATE OR REPLACE VIEW intente meter la columna nueva en
-- medio de las de verificación, y Postgres lo rechaza. Enumerar obliga a que quien
-- añada una columna decida explícitamente si la vista la expone.
CREATE OR REPLACE VIEW pois_vivos AS
SELECT
    p.id,
    p.nombre,
    p.categoria,
    p.categoria_overture,
    p.geom,
    p.fuente,
    p.confianza,
    p.overture_id,
    p.osm_id,
    p.marca,
    p.direccion,
    p.operativo,
    p.ciudad,
    p.actualizado_en,
    -- La insignia: quién lo verificó en terreno y cuándo. NULL = nadie lo ha pisado.
    c.creado_en    AS verificado_en,
    c.corredor_id  AS verificado_por,
    c.accion       AS verificacion_accion
FROM pois_propios p
LEFT JOIN LATERAL (
    SELECT accion, creado_en, corredor_id
    FROM entorno_curacion
    WHERE poi_id = p.id
    ORDER BY creado_en DESC
    LIMIT 1
) c ON true
-- Regla 1 y 2: el humano más reciente dijo "cerrado" → fuera, diga lo que diga el origen.
WHERE COALESCE(c.accion, '') <> 'cerrado'
-- Regla 3: sin humano decide el origen; con un 'confirmado' humano el POI vive aunque
-- el origen lo haya dado de baja (el corredor estuvo ahí; Overture es de hace un mes).
  AND (p.operativo OR c.accion = 'confirmado');

COMMENT ON VIEW pois_vivos IS
    'pois_propios con el overlay de curación del corredor aplicado. Las lecturas de '
    'entorno deben usar ESTA vista, no la tabla: la tabla es el origen crudo y el '
    'refresco semanal la sobrescribe. Ver migración 023.';

-- ── Verificación ────────────────────────────────────────────────────────────
-- (a) La vista existe y no pierde filas cuando todavía no hay curación enganchada:
SELECT
    (SELECT count(*) FROM pois_propios WHERE operativo) AS operativos_origen,
    (SELECT count(*) FROM pois_vivos)                   AS vivos_con_overlay,
    (SELECT count(*) FROM entorno_curacion
      WHERE poi_id IS NOT NULL)                         AS curaciones_enganchadas;
-- Esperado en la primera aplicación: operativos_origen = vivos_con_overlay,
-- curaciones_enganchadas = 0 (las filas viejas quedan con poi_id NULL, por diseño:
-- su nombre es texto libre y re-atarlo a un POI a posteriori sería adivinar).

-- (b) La FK apunta a donde debe:
SELECT conname, confrelid::regclass AS referencia
FROM pg_constraint
WHERE conrelid = 'entorno_curacion'::regclass AND contype = 'f';

-- ============================================================
-- ROLLBACK:
--   DROP VIEW IF EXISTS pois_vivos;
--   DROP INDEX IF EXISTS ix_entorno_cur_poi;
--   ALTER TABLE entorno_curacion DROP COLUMN IF EXISTS poi_id;
--   (revertir antes app/rutas.py a FROM pois_propios, o las lecturas de entorno
--    quedan apuntando a una vista que ya no existe)
-- ============================================================
