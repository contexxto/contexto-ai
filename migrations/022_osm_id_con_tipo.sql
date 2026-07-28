-- ============================================================
-- Migration 022: osm_id lleva el TIPO de objeto OSM ("node/123", "way/456")
--
--   POR QUÉ: el test en vivo del 2026-07-28 (Carlos, sur de Quito) destapó que el
--   script de ingesta solo pedía NODOS a Overpass, y gran parte del mundo real está
--   mapeado como POLÍGONO: en el bbox de Quito había 1.198 parques, 315 iglesias,
--   171 farmacias y 95 puestos de policía como way/relation, todos invisibles.
--   Síntoma visible: "ruta al parque" respondía Plaza Quitumbe a 28 min con el
--   Parque Lineal Calicanto al lado.
--
--   Al pasar la consulta a `nwr` (node+way+relation), los ids numéricos de OSM
--   DEJAN de ser únicos entre sí: el node 123 y el way 123 son objetos distintos.
--   Sin prefijo, el índice único pois_propios_osm_uidx los colapsaría en una sola
--   fila (upsert silencioso de un lugar sobre otro). El formato estándar OSM es
--   "type/id" y es el que adopta el script desde hoy.
--
--   Esta migración prefija las filas existentes (todas eran nodos) para que el
--   próximo upsert las RECONOZCA en vez de cerrarlas y duplicarlas — conservar la
--   fila es la base del punto 3 de la Fase 3 (curación colgada del POI).
--
--   ⚠️ ORDEN: aplicar ANTES de correr el script nuevo. Al revés, la corrida cerraría
--   los ~4.300 POIs de OSM ("id 123 ya no viene del origen") y los re-insertaría
--   con id nuevo, perdiendo la identidad de cada fila.
-- ============================================================

UPDATE pois_propios
SET osm_id = 'node/' || osm_id
WHERE osm_id IS NOT NULL AND position('/' in osm_id) = 0;

-- Verificación: 0 filas sin prefijo
SELECT count(*) AS sin_prefijo FROM pois_propios
WHERE osm_id IS NOT NULL AND position('/' in osm_id) = 0;

-- ============================================================
-- ROLLBACK (solo si el script nuevo NO ha corrido aún):
--   UPDATE pois_propios SET osm_id = substring(osm_id from 'node/(.*)')
--   WHERE osm_id LIKE 'node/%';
-- ============================================================
