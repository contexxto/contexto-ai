# PLAN — Migración del Map-Chat: Google Maps → Stack propio (`pois_propios` + Valhalla)

> **Estado:** documentado, NO ejecutado. Pendiente de aprobación de Carlos para arrancar Fase 1.
> **Fecha:** 2026-07-08 · **Autor:** exploración de 4 agentes + síntesis (Claude Code)
> **Relacionados:** `docs/SPEC_Foso_Capa_de_Datos.md`, `docs/DEPLOY_Valhalla.md`, `CLAUDE.md` (líneas ~71-76: "Google es puente transitorio").

---

## 1. Por qué (motivación)

- **Fragilidad operativa (evidencia en vivo):** el 2026-07-08 el map-chat tuvo un **P1** — `"parque más cercano"` devolvía *"No pude procesar tu pregunta"*. Causa raíz: latencia/timeout intermitente de **Google** (Places + Directions, secuenciales, hasta ~16s). Se puso un parche defensivo (`asyncio.wait_for` + graceful + AbortController), pero **la raíz es la dependencia de Google**.
- **Foso:** el diferenciador de Contexto NO es el polígono/isócrona (que Google acaba de **commoditizar** con su nueva Isochrones API) — es el **dato verificado, honesto, con proveniencia** ("estimación vs medición", "verificado por el corredor"). El stack propio (Overture+OSM almacenables) es territorial y no replicable (Patrón Valencia **P7**). Google no puede ofrecer eso.
- **Costo:** Google Places/Directions son **pago por llamada**. Valhalla + PostGIS = costo fijo (zero-burn, T3/T4).
- **Decisión ya zanjada** (`CLAUDE.md`): Google es un **puente transitorio**; el norte es poseer la capa propia.

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

### 2.3 🚨 El hallazgo crítico

**La tabla `pois_propios` está VACÍA en producción.** El script de ingesta se escribió pero **nunca corrió** (`scripts/foso_pois_spike.py:254` consulta el conteo; hoy es 0). Por eso **todo cae a Google**.

Esto explica el P1 de hoy: `"parque más cercano"` pegó a Google (y timeouteó) **porque no hay dato propio que lo responda**.

> **⚠️ Verificar antes de Fase 1:** confirmar el conteo real de `pois_propios` en la DB de prod (`SELECT categoria, count(*) FROM pois_propios GROUP BY 1`). Todo el plan asume tabla vacía/incompleta.

### 2.4 Valhalla — solo isócronas hoy, sin routing

- Integrado **solo** para `/isochrone` peatonal: `app/isocronas.py:48` (`POST {valhalla_url}/isochrone`, `costing=pedestrian`).
- URL: `app/config.py:50` (`valhalla_url = 'http://localhost:8002'`); Docker: `docker-compose.valhalla.yml`; deploy: `docs/DEPLOY_Valhalla.md`.
- **NO** hay routing punto-a-punto (`/route`) — las rutas peatonales siguen en Google (`_ruta_a_pie`).
- Valhalla soporta `/route` nativo (mismo motor, `costing=pedestrian`), pero **falta confirmar que el deployment lo expone** + validar calidad/latencia vs Google en Quito.

---

## 3. Plan por fases

### 🟢 Fase 1 — Poblar datos + cablear ruta-a-categoría (mayor palanca, menor riesgo)

**Objetivo:** que las consultas de POIs/nearest del map-chat usen la DB propia, no Google.

1. **Datos (ops):** correr `scripts/foso_pois_spike.py` contra la DB de prod → Overture (6 cat) + OSM (transporte), bbox Quito.
   - Overture: gratis (DuckDB/S3 anónimo). Licencia **CDLA Permissive 2.0** (sin share-alike) para las 6 cat; OSM transporte = **ODbL** (requiere atribución).
   - **Requiere:** acceso de escritura a la DB de prod (Supabase).
2. **Código (pequeño, en rama):** el branch "ruta a X" del map-chat (`comando_mapa` → `_nearest_categoria`, `app/rutas.py:571-595`) hoy va **directo a Google**. Cablearlo a **propio-primero → Google fallback**, reusando `_PROPIOS_ENTORNO_SQL` (ya existe). Mismo patrón que `_servicios_con_coords`.
3. **Verificar paridad:** para N puntos de prueba en Quito, comparar POI-propio vs Google (¿devuelve el "más cercano" razonable?). Rótulo de proveniencia `fuente:propio`.

**Impacto:** elimina el grueso de la dependencia de Google **Places** + **arregla la raíz del P1 de hoy** (parque más cercano → DB propia, rápido, sin timeout).
**Riesgo:** bajo (mayormente datos; el código reusa lo que ya existe). **Esfuerzo:** medio (ops + cambio chico).

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

## 4. Recomendación

**Empezar por Fase 1.** Es el 80/20: mayormente datos, cambio de código mínimo (reusa la arquitectura existente), y **elimina la raíz del bug de hoy** además de recortar el grueso de la dependencia de Google. Fase 2 (routing) después, con validación cuidadosa. Fase 3 es mantenimiento continuo.

### Qué se necesita para arrancar Fase 1
- ✅ Aprobación de Carlos.
- 🔑 Acceso de escritura a la DB de prod (Supabase) para correr la ingesta.
- 🔍 Verificar primero el conteo real de `pois_propios` (§2.3).

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
