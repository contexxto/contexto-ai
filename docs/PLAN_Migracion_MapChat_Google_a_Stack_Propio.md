# PLAN — Migración del Map-Chat: Google Maps → Stack propio (`pois_propios` + Valhalla)

> **Estado:** Fase 1 **a medias** — los datos SÍ están cargados (paso 1 hecho), el cableado del
> map-chat NO (paso 2 pendiente). Ver §2.3, corregido contra producción el 2026-07-27.
> **Fecha:** 2026-07-08 · **Autor:** exploración de 4 agentes + síntesis (Claude Code)
> **Corregido:** 2026-07-27 (sesión Claude Code con Carlos) — la premisa central de este plan
> ("`pois_propios` está vacía") era **FALSA**. Verificada contra la DB de prod, no inferida.
> **Relacionados:** [`docs/SPEC_Foso_Capa_de_Datos.md`](SPEC_Foso_Capa_de_Datos.md), [`docs/DEPLOY_Valhalla.md`](DEPLOY_Valhalla.md), [`CLAUDE.md`](../CLAUDE.md) (líneas ~71-76: "Google es puente transitorio").

---

## 1. Por qué (motivación)

- **Fragilidad operativa (evidencia en vivo):** el 2026-07-08 el map-chat tuvo un **P1** — `"parque más cercano"` devolvía *"No pude procesar tu pregunta"*. Causa raíz: latencia/timeout intermitente de **Google** (Places + Directions, secuenciales, hasta ~16s). Se puso un parche defensivo (`asyncio.wait_for` + graceful + AbortController), pero **la raíz es la dependencia de Google**.
- **Foso:** el diferenciador de Contexto NO es el polígono/isócrona (que Google acaba de **commoditizar** con su nueva Isochrones API) — es el **dato verificado, honesto, con proveniencia** ("estimación vs medición", "verificado por el corredor"). El stack propio (Overture+OSM almacenables) es territorial y no replicable (Patrón Valencia **P7**). Google no puede ofrecer eso.
- **Costo:** Google Places/Directions son **pago por llamada**. Valhalla + PostGIS = costo fijo (zero-burn, T3/T4).
- **Decisión ya zanjada** ([`CLAUDE.md`](../CLAUDE.md)): Google es un **puente transitorio**; el norte es poseer la capa propia.

---

## 2. Estado actual (hallazgos de la exploración)

### 2.1 Puntos donde el map-chat llama a Google (`app/`)

| Función | Archivo:línea | API Google | Qué hace |
|---|---|---|---|
| `_ruta_a_pie()` | `app/rutas.py:187` | **Routes** (computeRoutes, WALK) | Ruta peatonal punto-a-punto (la línea "Ilumino la ruta") |
| `_nearest_categoria()` | `app/rutas.py:261` | **Places** (searchNearby) | POI más cercano de una categoría |
| `_servicios_con_coords()` | `app/rutas.py:130` | **Híbrido** | Propio-primero → Google fallback por categorías faltantes |
| `recorrido_zona()` | `app/rutas.py:347` | Orquesta Places+Routes | Tour narrado (4-6 escenas) |
| `_mejor_transporte()` | `app/rutas.py:331` | Places | Prioriza Metro/tren sobre bus |
| `rutas_desde()` | `app/rutas.py:621` | Routes (lote) | Rutas a N servicios (endpoint aura) |
| `_entorno_google()` | `app/entorno.py:152` | Places (batch 8 cat) | Enriquece fichas de inmueble |
| `_geocode_google()` | `app/agent/tools.py:316` | Geocoding | address→coords (ingesta) — *fuera de scope map-chat* |

> `_reverse_geocode()` (`tools.py:406`) ya usa **OSM Nominatim** (gratis), no Google.

### 2.2 La arquitectura híbrida YA EXISTE (construida ~80%)

- Modelo ORM `PoiPropio`: `app/models.py:121-155` (id, nombre, categoria [7 valores], categoria_overture, geom Point SRID 4326, fuente [overture|osm], confianza, overture_id, osm_id, marca, direccion, operativo, actualizado_en).
- Migración: `migrations/014_pois_propios.sql` (tabla + índices GIST + CHECK constraints).
- Query KNN "más cercano por categoría": `app/rutas.py:64-75` (`_PROPIOS_ENTORNO_SQL`, `ST_DWithin` 1500m + `<->` KNN).
- Query transporte masivo: `app/rutas.py:77-89` (`_PROPIOS_TRANSPORTE_SQL`, prioriza metro/tren/terminal sobre parada_bus).
- Consumo: `_servicios_propios()` `app/rutas.py:92-127` — propio-primero, fallback graceful a Google.
- Fallback: `_servicios_con_coords()` `app/rutas.py:130-172` — solo Google para lo que falte.
- Script de ingesta: `scripts/foso_pois_spike.py` — Overture (6 cat, bbox Quito, DuckDB/S3 anónimo, umbrales confianza 0.55-0.70) + Overpass OSM (transporte).

### 2.3 ~~🚨 El hallazgo crítico~~ → CORREGIDO 2026-07-27 (verificado contra prod)

> **Lo que decía este apartado era falso.** Afirmaba: *"La tabla `pois_propios` está VACÍA en
> producción. El script nunca corrió. Por eso todo cae a Google"*, y atribuía a eso el P1 del
> 2026-07-08. **Nunca se verificó contra la base.** Se conserva el error escrito porque su
> propagación —dos planes lo repitieron durante 19 días— es la lección: el propio apartado pedía
> "verificar antes de Fase 1" y nadie corrió la consulta. Cuesta 30 segundos.

**El estado real (consulta de solo lectura contra la DB de prod, 2026-07-27):**

`pois_propios` tiene **4.898 POIs de Quito**, cargados el **2026-07-01** (una sola corrida:
`min(actualizado_en) = max(actualizado_en)`). Todos operativos.

| categoría | fuente | n |
|---|---|---|
| transporte | osm | 2.047 |
| educacion | overture | 964 |
| salud | overture | 858 |
| farmacia | overture | 466 |
| supermercado | overture | 311 |
| centro_comercial | overture | 143 |
| parque | overture | **109** |

2.851 con `overture_id` + 2.047 con `osm_id` = 4.898 (cuadra).

**Cobertura medida sobre los 40 inmuebles con geometría:** 38 tienen las 6 categorías de entorno
resueltas por capa propia a 1.500 m; 1 tiene 5 de 6; 1 tiene 4 de 6. Los 40 tienen transporte propio
a 3 km. **Google rellena 3 huecos de 280 posibles** (2 de `centro_comercial`, 1 de `parque`) — es el
fallback marginal que el diseño buscaba, no la fuente primaria.

**El hallazgo real, que sí sigue abierto:** hay **dos caminos de código** y solo uno usa el foso.

- ✅ `_servicios_con_coords()` (entorno de la ficha) → propio-primero, consume los 4.898.
- ❌ `comando_mapa()` (`app/rutas.py:562-581`, el "ruta a la farmacia" del map-chat) → toma
  `settings.google_maps_api_key` y llama a `_nearest_categoria()` **directo a Google Places, sin
  consultar `pois_propios`**. Si no hay clave de Google, el branch aborta entero.

**Esa es la causa plausible del P1 del 2026-07-08:** `"parque más cercano"` entra por `comando_mapa`
→ Google → timeout, **con 109 parques propios cargados desde el 1 de julio que nunca se consultaron**.
No fue falta de dato: fue que ese camino no lo mira. *(Plausible, no probado — no hay traza del
request original.)*

### 2.4 Valhalla — solo isócronas hoy, sin routing

- Integrado **solo** para `/isochrone` peatonal: `app/isocronas.py:48` (`POST {valhalla_url}/isochrone`, `costing=pedestrian`).
- URL: `app/config.py:50` (`valhalla_url = 'http://localhost:8002'`); Docker: `docker-compose.valhalla.yml`; deploy: [`docs/DEPLOY_Valhalla.md`](DEPLOY_Valhalla.md).
- **NO** hay routing punto-a-punto (`/route`) — las rutas peatonales siguen en Google (`_ruta_a_pie`).
- Valhalla soporta `/route` nativo (mismo motor, `costing=pedestrian`), pero **falta confirmar que el deployment lo expone** + validar calidad/latencia vs Google en Quito.

---

## 3. Plan por fases

### 🟡 Fase 1 — Poblar datos + cablear ruta-a-categoría (A MEDIAS — ver estado por paso)

**Objetivo:** que las consultas de POIs/nearest del map-chat usen la DB propia, no Google.

1. ✅ **HECHO (2026-07-01).** **Datos (ops):** `scripts/foso_pois_spike.py` corrió contra prod →
   4.898 POIs (Overture 6 cat + OSM transporte), bbox Quito. Verificado 2026-07-27 (§2.3).
   - Overture: gratis (DuckDB/S3 anónimo). Licencia **CDLA Permissive 2.0** (sin share-alike) para las 6 cat; OSM transporte = **ODbL** (requiere atribución).
   - ⚠️ **Deuda que dejó:** sin cron de refresco (release Overture `2026-06-17.0`, congelado) y
     **atribución incompleta en UI** — hay menciones sueltas a OpenStreetMap en 3 vistas, Overture
     no aparece atribuido al usuario final. Los 2.047 POIs ODbL exigen atribución formal.
2. ❌ **PENDIENTE — es lo que queda de esta fase.** **Código (pequeño, en rama):** el branch
   "ruta a X" del map-chat (`comando_mapa` → `_nearest_categoria`, `app/rutas.py:562-581`) sigue yendo
   **directo a Google** (verificado 2026-07-27). Cablearlo a **propio-primero → Google fallback**,
   reusando `_PROPIOS_ENTORNO_SQL` (ya existe). Mismo patrón que `_servicios_con_coords`.
   **Con la tabla ya poblada, este paso es puro código y de bajo riesgo.**
3. ❌ **PENDIENTE. Verificar paridad:** para N puntos de prueba en Quito, comparar POI-propio vs Google (¿devuelve el "más cercano" razonable?). Rótulo de proveniencia `fuente:propio`. El paso 4 del propio script hace esta comparación.

**Impacto de lo que falta (paso 2):** que el map-chat deje de pegarle a Google en cada "ruta a X"
teniendo el dato en casa — es la raíz plausible del P1 del 2026-07-08 (§2.3).
**Riesgo:** bajo. **Esfuerzo:** chico (el dato ya está; es cablear una rama que ya existe al lado).

### 🟡 Fase 2 — Routing con Valhalla `/route` (reemplazar Google Directions)

**Objetivo:** dibujar la línea de ruta peatonal ("Ilumino la ruta") desde Valhalla, no Google.

1. Confirmar que el Valhalla desplegado (Render) expone `/route` (test curl `costing=pedestrian`).
2. Implementar `_ruta_a_pie_valhalla()` paralela a la de Google (`app/rutas.py:173-198`).
3. **Validar calidad/latencia vs Google** en Quito — cobertura de aceras (footways) OSM en periferia es el riesgo.
4. Cutover gradual: **Valhalla-primero, Google fallback** (espejo del patrón híbrido de POIs).

**Impacto:** elimina la dependencia de Google **Routes**. **Riesgo:** medio (calidad de aceras OSM). **Esfuerzo:** alto (código nuevo + validación + posible config/deploy de Valhalla).

### 🔵 Fase 3 — Completar (continuo)

- Categorías faltantes en capa propia: **iglesia, seguridad** (vía OSM; hoy `entorno.py` usa 8 cat pero `pois_propios` solo 7).
- **Frescura:** cron de refresco (Overture mensual / OSM Geofabrik semanal) — hoy no existe.
- **Atribución ODbL en UI** (columna `fuente` ya existe; falta exponerla) — alinea con el foso de honestidad.
- **Métricas:** conteo de POIs por categoría/ciudad persistido (monitoreo de salud del foso).
- **Expansión:** bbox para nuevas ciudades (Puebla/Linden) — hoy `pois_propios` es solo Quito.

---

## 4. Recomendación — REESCRITA 2026-07-27

> La recomendación original ("empezar por Fase 1: es mayormente datos") ya no aplica: **los datos
> están puestos desde el 2026-07-01**. Lo que queda de la Fase 1 es solo el paso 2, que es código.

**Cerrar el paso 2 de la Fase 1** — cablear `comando_mapa` a propio-primero. Es el único cambio que
convierte 4.898 POIs ya cargados y pagados en cero llamadas a Google para el "ruta a X" del map-chat.
Bajo riesgo, esfuerzo chico, y quita la causa plausible del P1. Fase 2 (routing con Valhalla) después,
con validación de calidad de aceras. Fase 3 es mantenimiento continuo.

**Pero no es urgente por sí solo.** Con 40 inmuebles demo y 0 corredores reales, el ahorro es
teórico. El disparador honesto es **inventario real** (mesa MAKLO 2026-07-29): ahí las consultas
dejan de ser de demo y la latencia de Google entra al camino crítico de un comprador de verdad.
Ver `PLAN_Producto_6meses_2026-07.md` §0.5 — el cuello de botella sigue siendo adopción, no capacidad.

### Qué se necesita para cerrar la Fase 1
- ✅ ~~Acceso de escritura a la DB de prod~~ — ya no hace falta, la ingesta ya corrió.
- 🔍 ~~Verificar el conteo real~~ — hecho 2026-07-27: 4.898 POIs (§2.3).
- 🔨 Una rama de código sobre `app/rutas.py:562-581` + medir paridad (paso 3).

### Deuda separada, no bloqueante
- **Refresco:** sin cron; el dato es del release Overture `2026-06-17.0` cargado el 01-jul.
- **Atribución ODbL/Overture** incompleta en UI (§3, Fase 1 paso 1).
- ✅ ~~**Multi-ciudad:** `scripts/foso_pois_spike.py` hace `TRUNCATE pois_propios` sin acotar por
  región y **ninguna migración define columna de ciudad** — correrlo con el bbox de otra ciudad
  **borraría Quito**.~~ **RESUELTO 2026-07-27** (`migrations/019_pois_propios_ciudad.sql`, aplicada y
  verificada en prod: 4.898 POIs → `ciudad='quito'`, 0 nulos, índice y CHECK activos):
  - Columna `ciudad` con `NOT NULL DEFAULT 'quito'`, índice `pois_propios_ciudad_idx` y CHECK de slug
    limpio (minúsculas, sin espacios) — probado que rechaza `'Puebla DF'`.
  - El script recarga con `DELETE ... WHERE ciudad = :c`, **nunca `TRUNCATE`**. Imprime cuántos
    reemplaza y qué mercados deja intactos.
  - Registro `CIUDADES` que ata slug ↔ bbox en la misma entrada (imposible cargar el bbox de una
    ciudad con el nombre de otra) + CLI: `python scripts/foso_pois_spike.py <ciudad>`. Ciudad
    desconocida aborta antes de tocar red o DB.
  - Guarda extra: si la cosecha devuelve 0 POIs, **aborta antes del DELETE** — así un fallo de
    Overture/Overpass ya no puede dejar un mercado vacío.
  - `app/models.py::PoiPropio` refleja la columna y el CHECK.
  - **Las queries de lectura NO cambiaron**: `_PROPIOS_ENTORNO_SQL` / `_PROPIOS_TRANSPORTE_SQL`
    filtran por proximidad (`ST_DWithin`), y un POI de otro mercado nunca cae en el radio. La ciudad
    es unidad de **carga**, no de consulta. *(Supuesto anotado en la migración: mercados a cientos de
    km. Revisar si algún día se cargan dos ciudades conurbadas.)*
  - **Pendiente al abrir mercado nuevo:** medir su bbox en un visor real y añadirlo a `CIUDADES`. Los
    de Puebla y Mazatlán quedaron como comentarios sin coordenadas — **a propósito, no se inventaron**.
- **`parque` = 109 POIs** para todo Quito, la cobertura más floja (umbral `CONF_MIN` 0.70, el más
  exigente). Con inventario disperso será el primer hueco en abrirse; es un número en el script.

---

## 5. Riesgos / gaps documentados (de la exploración)

- `pois_propios` es **solo Quito** (bbox `-78.60..-78.40`, `-0.35..-0.05`); fuera de eso → Google obligatorio.
- Categorías desalineadas: `entorno.py` (8) vs `pois_propios` CHECK (7) — iglesia/seguridad sin fuente Overture.
- Sin caché de resultados entre requests (cada pregunta reconsulta).
- `_TIMEOUT` global (hoy 5s tras el parche); `asyncio.gather` sin timeout individual por llamada.
- Ruido/tráfico/vegetación siguen siendo heurísticos por sector (7 sectores), NO en `pois_propios`.
- Marca/brand matching: columna existe pero no pre-poblada desde Overture.
- Freshness: Overture mensual / OSM semanal, sin cron.
- `google_maps_api_key`: sin hot-reload (cambio requiere reinicio).

---

## 6. Contexto estratégico (playbook de fundador)

Corrido por el Whaber Founder Playbook el 2026-07-08 a raíz del lanzamiento de la **Google Isochrones API** (promocionada por Martin Kleppe / Ubilabs, partner Google Maps Platform):

- **Veredicto:** la API de Google **NO es amenaza — es validación** (Contexto hizo isócronas peatonales antes de que existiera la API; P3). El foso nunca fue el polígono; es el dato verificado (**P7, P4**).
- **Punto técnico:** el core de Contexto es **peatonal**, donde la ventaja estrella de Google (tráfico en vivo) es **irrelevante** (nadie camina en un atasco).
- **Dirección:** esta migración (Google → propio) es exactamente el norte correcto; el P1 de hoy lo refuerza, no lo revierte.
- **Oportunidad de relación (no de dependencia):** Kleppe/Ubilabs = contacto de **Radar** (T13/T38); Google Maps = sponsor potencial (T24). Contexto tiene un caso de isócronas peatonales en **producción real en LATAM** — material de "dar valor primero" (T36).

> **Frase ancla:** *"Google acaba de convertir la isócrona en commodity. Nuestro foso nunca fue el polígono — es que el corredor lo verificó en terreno."*
