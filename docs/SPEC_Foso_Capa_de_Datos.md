# SPEC — El Foso: poseer la capa de datos (Valhalla + POIs propios)

> **Estado:** plano build-ready (jun-2026). Todos los comandos/SQL/esquemas fueron
> **verificados contra fuentes oficiales** en una investigación adversarial. Cuando
> arranquemos, este documento es la fuente; no hay que re-investigar.
>
> **Norte (CLAUDE.md):** poseer la capa de datos en vez de alquilar APIs. **Google = el
> puente, no el destino.** Este spec construye los dos ladrillos que permiten soltar
> Google Places (POIs) y quedarnos sin depender de nadie para el alcance (isócronas).
>
> **Ladrillos, en orden:** **#18** (capa de POIs propia — reemplaza Google Places) →
> **#7** (isócronas Valhalla — el "30 min a lo que te importa").

---

## 0. Por qué (el foso, en una línea)

La **isócrona** es un commodity (cualquiera la compra a Google/TravelTime). Lo
irreplicable es cruzarla con el **Catastro Vivo** (entorno verificado por el corredor).
Números que respaldan el wedge (verificados): **Zoopla +300% conversiones** (3× vs
distancia) al añadir búsqueda por tiempo-de-viaje; **Redfin 2× anuncios vistos, +47%
tours**. El ancla debe ser **genérica** (trabajo/colegio/hospital/familia): NAR-2025 el
commute como prioridad cayó 52%→31%, no hardcodear "trabajo".

**Disciplina Fair Housing:** filtrar por "cerca de X colegio" puede correlacionar con
clase protegida → lo cubre el guardrail #14 (`app/fair_housing.py`), mantenerlo.

---

## 1. LADRILLO #18 — Capa de POIs propia (reemplaza Google Places)

### 1.1 La simplificación clave (esto lo hace liviano)

**Overture Places YA conflada OpenStreetMap + Meta + Microsoft + Foursquare internamente.**
Por eso NO hacemos conflación manual OSM↔Overture para la mayoría de categorías:

| Categoría | Fuente | Por qué |
|---|---|---|
| salud, farmacia, supermercado, educación, parque, centro_comercial | **Overture Places, directo** | Ya conflada, con `confidence` nativa y proveniencia por-POI |
| **transporte** (bus/Metro) | **OSM directo** (Geofabrik/Overpass) | Overture Places es débil en paradas de transporte público; el theme `transportation` de Overture son segmentos/conectores (calles), NO paradas etiquetadas |

Reemplaza `app/rutas.py::_servicios_con_coords` (hoy 7 llamadas a Google Places Nearby por
punto) por **una query PostGIS** contra nuestra tabla `pois_propios`.

### 1.2 Licencia — SÍ podemos guardar y servir

- **Overture Places** = CDLA Permissive 2.0 (Meta/Microsoft/PinMeTo/…) + Apache 2.0
  (Foursquare) + CC0 (AllThePlaces). **Sin ODbL, sin share-alike viral.** Guardar,
  transformar, servir comercialmente: permitido. Requisito: atribución.
- **OSM (transporte)** = ODbL → atribución + share-alike sobre esa porción. Mantener
  la parte OSM **separable y atribuida** (la columna `fuente` lo permite).
- **Atribución mínima en la app:** `Overture Maps Foundation, overturemaps.org` y, para
  la porción de transporte, `© OpenStreetMap contributors, ODbL`.

### 1.3 Acceso a Overture Places (bbox Quito)

- Bucket público anónimo (sin credenciales): `s3://overturemaps-us-west-2/`, región `us-west-2`.
- Path del theme (fijar versión para reproducibilidad; hay release mensual):
  `release/2026-06-17.0/theme=places/type=place/*`
- **Vía recomendada = DuckDB** (filtra por bbox y columnas del lado servidor → baja solo
  Quito, ~pocos miles de POIs, no los 72M globales). Falta `duckdb` en el venv → `pip install duckdb`
  (binario autocontenido, no arrastra pyarrow/geopandas).

```sql
-- pip install duckdb ; luego: duckdb -c "<esto>"
INSTALL spatial; INSTALL httpfs;
LOAD spatial; LOAD httpfs;
SET s3_region='us-west-2';

COPY (
  SELECT
    id,                                    -- GERS id (estable entre releases → dedupe futuro)
    names.primary            AS nombre,
    taxonomy.primary         AS categoria,  -- ⚠️ usar taxonomy/basic_category, NO categories (legacy, se ELIMINA sep-2026)
    basic_category           AS categoria_basica,
    taxonomy.hierarchy       AS jerarquia,   -- VARCHAR[]: hierarchy[1] = L0 (health_and_medical, retail, education…)
    confidence,                              -- 0..1, confianza NATIVA de Overture (filtro + proveniencia)
    operating_status,                        -- filtrar 'closed'
    ST_Y(geometry)           AS lat,
    ST_X(geometry)           AS lon,
    addresses[1].freeform    AS direccion,
    brand.names.primary      AS marca,
    sources                  AS proveniencia -- qué dataset dio cada valor (la narrativa del foso)
  FROM read_parquet(
    's3://overturemaps-us-west-2/release/2026-06-17.0/theme=places/type=place/*'
  )
  WHERE bbox.xmin BETWEEN -78.60 AND -78.40   -- lon (Quito)
    AND bbox.ymin BETWEEN  -0.35 AND  -0.05   -- lat (Quito)
    AND confidence > 0.5                       -- 0.95 = alta calidad; 0.5 = más recall. Ajustar.
    AND (operating_status IS NULL OR operating_status <> 'closed')
) TO 'quito_places.parquet' (FORMAT PARQUET);
```

> Alternativa sin SQL: `pip install overturemaps` →
> `overturemaps download --bbox=-78.6,-0.35,-78.4,-0.05 -f geoparquet --type=place -o quito_places.parquet`
> (orden del bbox: `west,south,east,north`).

### 1.4 Mapeo de categorías Overture → nuestras 6

Códigos leaf reales (verificados en el CSV oficial). **No** hacer match solo por leaf —
usar también el prefijo de jerarquía (`taxonomy.hierarchy`) para más recall:

```python
CAT_LEAF = {
  "salud":            ["hospital", "doctor", "medical_center", "urgent_care_clinic"],
  "farmacia":         ["pharmacy", "drugstore"],
  "supermercado":     ["supermarket", "grocery_store"],
  "educacion":        ["school", "college_university", "preschool"],
  "parque":           ["park", "playground"],
  "centro_comercial": ["shopping_center", "department_store"],
}
# ⚠️ OJO con el fallback por L0 (verificado, tiene trampas en la jerarquía real):
#   - farmacia vive bajo L0 'retail' (NO 'health_and_medical')
#   - park vive bajo 'attractions_and_activities'; playground bajo 'active_life' (dos L0 distintos)
#   → NO asumir hierarchy[1] == leaf. Usar hierarchy[0]=L0 y taxonomy.primary=leaf.
```

### 1.5 Transporte desde OSM (la única porción ODbL)

Fuente: extracto Ecuador de Geofabrik (`https://download.geofabrik.de/south-america/ecuador-latest.osm.pbf`,
~113 MB) o la Overpass API (public, sin auth) para un bbox de Quito. Tags a tomar:

```
highway=bus_stop | public_transport=platform|stop_position|station
railway=station|halt|subway_entrance | amenity=bus_station
```

### 1.6 Esquema PostGIS `pois_propios`

```sql
CREATE TABLE IF NOT EXISTS pois_propios (
    id            bigserial PRIMARY KEY,
    nombre        text,
    categoria     text NOT NULL,                    -- salud|farmacia|supermercado|educacion|parque|centro_comercial|transporte
    geom          geometry(Point, 4326) NOT NULL,
    fuente        text NOT NULL,                    -- 'overture' | 'osm'  (para atribución/licencia por-registro)
    confianza     real,                             -- 0..1 (de Overture; para OSM derivar de versión/consenso)
    overture_id   text,                             -- GERS id (dedupe entre releases)
    osm_id        text,
    marca         text,
    direccion     text,
    operativo     boolean DEFAULT true,             -- operating_status != 'closed'
    actualizado_en timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pois_propios_geom_gix ON pois_propios USING GIST (geom);
CREATE INDEX IF NOT EXISTS pois_propios_cat_idx  ON pois_propios (categoria);
```

Conflación **liviana** (solo si añadimos OSM sobre Overture y queremos evitar duplicar el
mismo lugar): considerar el mismo POI si están a **≤ 60 m** y el nombre normalizado
coincide (similitud trigram `pg_trgm` ≥ 0.5). Para transporte es mayormente aditivo (OSM
aporta lo que Overture no tiene), así que el riesgo de duplicado es bajo.

### 1.7 La query que reemplaza `_servicios_con_coords`

Dado el `lat/lon` de un inmueble, el POI más cercano **por categoría** (KNN con `<->`,
acotado con `ST_DWithin`, distancia real en metros con `geography`):

```sql
-- :lat, :lon = punto del inmueble ; :max_m = radio (p.ej. 1500)
SELECT DISTINCT ON (categoria)
       categoria, nombre, marca,
       ST_Y(geom) AS lat, ST_X(geom) AS lon,
       ROUND(ST_Distance(geom::geography,
             ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography))::int AS distancia_m,
       confianza, fuente
FROM pois_propios
WHERE operativo
  AND ST_DWithin(geom::geography,
                 ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :max_m)
ORDER BY categoria,
         geom <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326);   -- KNN por índice GIST
```

Devuelve exactamente el shape que hoy produce Google Places
(`{nombre, lat, lon, distancia_m, cat}`) → **AURA-SINGLE y el agente no cambian de contrato**,
solo cambia la fuente de la que sale.

### 1.8 Catastro Vivo encima (sin re-arquitecturar)

La tabla `entorno_curacion` (existente) ya hace overlay del corredor sobre el texto de
`servicios_cercanos`. Con `pois_propios` como base, el mismo overlay aplica: el corredor
**confirma** (sube confianza / marca verificado) o **cierra** (`operativo=false`) un POI.
Ese cruce —POI abierto × verificación humana con fecha— es **el foso sobre el foso**:
ni Redfin ni Google lo tienen.

### 1.9 Cutover de Google Places

1. Job batch llena `pois_propios` (Overture + OSM transporte) para Quito.
2. `_servicios_con_coords` gana una rama: si `pois_propios` tiene cobertura del punto →
   query PostGIS; si no (fuera de Quito) → Google Places como **fallback** (el puente).
3. Invalidar `aura_pois_cache` de los inmuebles afectados.
4. Medir paridad (mismos POIs top-1 que Google en una muestra) antes de apagar Google
   en Quito.

---

## 2. LADRILLO #7 — Isócronas peatonales (Valhalla auto-hospedado)

### 2.1 Levantar Valhalla (Docker) con Ecuador

Imagen oficial: **`ghcr.io/valhalla/valhalla-scripted:latest`** (la `scripted` trae el
`run.sh` que orquesta el build). Construye los tiles **sola** al arrancar con el `.pbf`.

```bash
mkdir -p custom_files
docker run -dt --name valhalla -p 8002:8002 \
  -v $PWD/custom_files:/custom_files \
  -e tile_urls=https://download.geofabrik.de/south-america/ecuador-latest.osm.pbf \
  -e use_tiles_ignore_pbf=True \      # si ya hay tiles, NO reconstruye al reiniciar
  -e build_admins=True \              # necesario: sin admin polygons, isócronas/ruteo degradan
  -e build_time_zones=True \
  -e build_elevation=False \          # peatonal urbano: no necesita elevación
  -e server_threads=2 \               # ⚠️ 'server_threads' (NO 'concurrency'): acota RAM del build
  ghcr.io/valhalla/valhalla-scripted:latest
docker logs -f valhalla               # espera 'Tile build complete' + server en :8002
```

Recursos (honestos): Ecuador ~113 MB PBF → build en **minutos** (≈5-15 min, 2-4 GB RAM),
una vez por refresco de OSM. En operación (solo servir) Valhalla mmap-ea los tiles:
**512 MB-1 GB RAM**, pocos cientos de MB en disco.

### 2.2 Request de isócrona PEATONAL (15 y 30 min)

```bash
curl -s -X POST http://localhost:8002/isochrone \
  -H 'Content-Type: application/json' \
  -d '{
        "locations":[{"lat":-0.1807,"lon":-78.4678}],
        "costing":"pedestrian",
        "contours":[{"time":15},{"time":30}],
        "polygons":true,          
        "denoise":0.5,            
        "generalize":50           
      }'
# Respuesta: GeoJSON FeatureCollection; cada Feature = Polygon/MultiPolygon,
# properties.metric='time', properties.contour=15|30.
```

- `polygons:true` → polígonos cerrados (con `false` da linestrings, inservibles para
  point-in-polygon). `denoise:0.5` limpia islas peatonales sueltas. `generalize:50` (m)
  simplifica vértices.

### 2.3 Pre-computar + cachear (inventario FIJO)

Job batch: por cada inmueble, **una** llamada `/isochrone` (los 2 contornos en un request),
upsert a PostGIS. Mismo patrón que `aura_pois_cache`.

```sql
CREATE TABLE IF NOT EXISTS isocronas_inmueble (
    id          bigserial PRIMARY KEY,
    activo_id   uuid NOT NULL,                      -- FK a activos_inmutables
    minutos     integer NOT NULL,                   -- 15 | 30
    geom        geometry(MultiPolygon, 4326) NOT NULL,
    generado_en timestamptz NOT NULL DEFAULT now(),
    UNIQUE (activo_id, minutos)
);
CREATE INDEX IF NOT EXISTS isocronas_inmueble_geom_gix ON isocronas_inmueble USING GIST (geom);

-- Insert desde una feature (geojson = json.dumps(feature['geometry'])):
INSERT INTO isocronas_inmueble (activo_id, minutos, geom)
VALUES (:activo_id, :minutos,
        ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326)))
ON CONFLICT (activo_id, minutos)
DO UPDATE SET geom = EXCLUDED.geom, generado_en = now();
```

### 2.4 El wedge — búsqueda por ANCLA + TIEMPO

El ancla (trabajo del usuario) NO está pre-computada → **1 llamada en vivo** a `/isochrone`
(o cachear anclas comunes: zonas de oficinas de Quito). Con el polígono del ancla, filtrar
el inventario con `ST_Contains`:

```sql
-- :ancla_geojson = isócrona del ancla ; :ancla_lat/:ancla_lon = punto del ancla
WITH ancla AS (
  SELECT ST_SetSRID(ST_GeomFromGeoJSON(:ancla_geojson), 4326) AS poly,
         ST_SetSRID(ST_MakePoint(:ancla_lon, :ancla_lat), 4326) AS pt
)
SELECT a.id, a.direccion_estandarizada,
       ST_Distance(a.geom::geography, ancla.pt::geography) AS metros_al_ancla
FROM activos_inmutables a, ancla
WHERE ST_Contains(ancla.poly, a.geom)                 -- el inmueble cae DENTRO de la isócrona
ORDER BY metros_al_ancla ASC;
```

Point-in-polygon local sobre pocos miles de puntos = trivial. Quito es el caso ideal:
topografía + tráfico donde el radio euclidiano miente (500 m pueden ser 25 min cuesta arriba).

### 2.5 Dónde corre Valhalla (decisión de infra)

**NO en el web service de FastAPI en Render** (proceso efímero, sin disco persistente para
los tiles). Opciones:
- **(a)** Servicio Docker separado en Render (Private Service / Background Worker) + Persistent
  Disk ~2-5 GB para `/custom_files`.
- **(b)** VM barata con Docker (Hetzner/Fly.io/DO), ~4-6 USD/mes, control total.
- **(c) Efímero:** como el inventario es fijo y las isócronas por-inmueble se pre-computan
  UNA vez, se puede levantar Valhalla temporal, correr el batch que llena `isocronas_inmueble`,
  y apagarlo. Valhalla solo queda vivo para el wedge del ancla (y con anclas cacheadas, casi
  ni eso). **Empezar por (c) para el spike; (a)/(b) cuando el wedge en vivo lo pida.**

---

## 3. Secuencia de ejecución (qué primero)

1. **Spike #18 (local):** `pip install duckdb`, correr el SQL de §1.3, cargar `quito_places.parquet`
   a `pois_propios` en Supabase (script que lee `.env`), validar que la query de §1.7 devuelve
   POIs sensatos para 3-4 inmuebles de prueba vs. lo que da Google hoy. **De-risquea todo el ladrillo.**
2. **Cutover #18:** rama en `_servicios_con_coords` (PostGIS primero, Google fallback) + medir paridad.
3. **Spike #7 (local/efímero):** Docker Valhalla + Ecuador, computar 1 isócrona peatonal, pintarla.
4. **Batch #7:** llenar `isocronas_inmueble` para el inventario; overlay en el Mapa Vivo (2C).
5. **Wedge:** UI de "ancla + tiempo" → isócrona del ancla → `ST_Contains` filtra el inventario.

**Criterio de apagar Google en Quito:** paridad de POIs verificada + `pois_propios`
refrescándose (job mensual con el release de Overture) + transporte OSM cubierto.

---

## 4. Riesgos y deuda conocida

- **Fidelidad peatonal de Valhalla** depende de aceras/`footway` de Quito en OSM; donde OSM
  sea pobre, cae a la red vial. Mitigación: la propia capa OSM/Overture mejora con el tiempo;
  medir contra rutas reales antes de confiar ciegamente.
- **`categories` legacy de Overture se elimina ~sep-2026** → el pipeline debe usar
  `taxonomy.primary`/`basic_category` desde el día 1 (ya reflejado en §1.3).
- **Overture es mensual** → job de refresco que re-baja el bbox y hace upsert por `overture_id`.
- **Overpass rate limits** si usamos la API en vez del extracto Geofabrik para OSM transporte.

---

## 5. Lo que quedó verificado (para no re-investigar)

- Bucket/versión/SQL de Overture, esquema de columnas, taxonomía, licencia (CDLA sin
  share-alike): **confirmado** contra docs.overturemaps.org.
- Comando Docker de Valhalla, request `/isochrone`, esquemas y SQL de PostGIS
  (`ST_GeomFromGeoJSON`/`ST_Multi`/`ST_Contains`/`ST_DWithin`/KNN `<->`): **confirmado**
  contra valhalla.github.io y postgis.net.
- Correcciones aplicadas del review: `server_threads` (no `concurrency`), imagen
  `valhalla-scripted`, `taxonomy` en vez de `categories` legacy, trampas del fallback por L0.
