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
2. ✅ **HECHO (2026-07-27).** **Código:** `comando_mapa` ya no llama a Google directo. Nuevo
   `_nearest_propio()` (`app/rutas.py`) = espejo de `_nearest_categoria` contra `pois_propios`:
   mismo radio (3 km), misma preferencia de marca dentro del margen, mismo shape + `fuente:"propio"`.
   El branch hace **propio-primero → Google solo por hueco**.
   - Cubre las 7 categorías de `pois_propios`. **`iglesia` y `seguridad` siguen yendo a Google**
     (no están en la capa; es la deuda de Fase 3 de abajo) — verificado con espía: de 4 consultas,
     las únicas que llegaron a Google fueron esas dos.
   - "metro" / "terminal" en la frase mapean a subtipos propios (`metro|estacion_tren|estacion` /
     `terminal_bus`), espejo de los `includedTypes` de Google.
   - **Sin clave de Google el branch ya no muere.** Antes devolvía "El mapa interactivo necesita
     Google Maps activo" para todo; ahora resuelve el destino con capa propia e ilumina el punto
     (la línea de ruta sigue necesitando Google — eso es Fase 2). El chequeo de clave se movió al
     único ramal que depende de Google de punta a punta (el tour).
   - ⚠️ **Trampa encontrada:** `:param::tipo` **rompe** en SQLAlchemy — el `::` del cast se come el
     bindparam y el parámetro queda literal en el SQL (la query devolvía 0 filas en silencio, tapada
     por el `except`). Usar `CAST(:param AS tipo)`. Anotado en el código.
3. ✅ **PARIDAD MEDIDA CONTRA GOOGLE (2026-07-27), sin gastar cuota.** Se comparó el top-1 propio
   por categoría contra `servicios_cercanos` — el texto que Google dejó guardado en cada inmueble
   entre el 06 y el 11-jun-2026, **tres semanas antes** de que existiera la capa propia (01-jul), así
   que no hay circularidad. 219 comparaciones sobre 40 inmuebles.

   | categoría | casos | mismo lugar | propio ≤ Google | dif. mediana |
   |---|---|---|---|---|
   | parque | 29 | 5 | 27 | **−401 m** |
   | centro_comercial | 34 | 10 | 28 | −154 m |
   | educacion | 39 | 2 | 24 | −78 m |
   | salud | 39 | 3 | 22 | −19 m |
   | supermercado | 39 | 16 | 25 | −1 m |
   | farmacia | 39 | 22 | 19 | +1 m |
   | **TOTAL** | **219** | **57 (26%)** | **159 (73%)** | **−62 m** |

   **El 26% de "mismo lugar" engaña en los dos sentidos.** A favor: hay coincidencias que el
   comparador no detecta por nombre ("Cruz Hospital Psiquiátrico San Lorenzo" = "Exhospicio San
   Lázaro"), y **Google trae basura visible** — devolvía `semáforo` a 1.105 m como parque,
   `EQ. RECONTEC 09` a 453 m, `PY Tecnologia` como centro comercial y `PlusMedical;Pro Shape Gym`
   como salud. En contra: dos fuentes pueden dar lugares distintos e igualmente válidos.

   **Transporte NO se pudo medir:** el texto guardado de Google no lo incluye (sus 8 categorías son
   seguridad, farmacia, supermercado, educación, centro comercial, salud, iglesia y parque). Queda
   sin comparación la categoría con más puntos de la capa (2.044).

   **Sigue sin verificarse:** el trazado de ruta contra el servicio real y el camino de fallback —
   el entorno local no tiene clave de Google; eso se probó por flujo de control con clave simulada.
   Riesgo concreto no descartado: una coordenada de Overture puede caer en el centro del polígono de
   un parque, donde Google no encuentre calle para trazar (antes el destino venía del propio Google,
   así que siempre era ruteable).

**Impacto ya obtenido:** el branch "ruta a X" dejó de gastar cuota de Google en las 7 categorías
propias, y con ello desaparece la causa plausible del P1 del 2026-07-08 (§2.3).

### 🟡 Fase 2 — Routing con Valhalla `/route` (reemplazar Google Directions)

**Objetivo:** dibujar la línea de ruta peatonal ("Ilumino la ruta") desde Valhalla, no Google.

1. Confirmar que el Valhalla desplegado (Render) expone `/route` (test curl `costing=pedestrian`).
2. Implementar `_ruta_a_pie_valhalla()` paralela a la de Google (`app/rutas.py:173-198`).
3. **Validar calidad/latencia vs Google** en Quito — cobertura de aceras (footways) OSM en periferia es el riesgo.
4. Cutover gradual: **Valhalla-primero, Google fallback** (espejo del patrón híbrido de POIs).

**Impacto:** elimina la dependencia de Google **Routes**. **Riesgo:** medio (calidad de aceras OSM). **Esfuerzo:** alto (código nuevo + validación + posible config/deploy de Valhalla).

### 🔵 Fase 3 — Frescura y acumulación (continuo)

> **Ampliada 2026-07-27** con el diagnóstico del ciclo de actualización. El orden de los tres
> primeros puntos **no es preferencia, es dependencia**: el 3 sin el 1 se destruye en el primer
> refresco, y hacer el 2 antes que el 1 institucionaliza el borrado.

**Estado del dato hoy:** los 4.898 POIs tienen `actualizado_en = 2026-07-01`, sobre release Overture
`2026-06-17.0` clavado a mano en el script. El transporte es una captura Overpass del mismo día.
**Nada los renueva:** sin tarea programada, sin disparador, sin aviso. Overture publica versiones
fechadas (fijar la versión es deliberado, por reproducibilidad — pero fijar sin renovar es congelar);
OSM es continuo.

**El hallazgo que ordena esta fase (verificado 2026-07-27):** `entorno_curacion` **NO apunta a
`pois_propios`**. Está ligada al inmueble (`activo_id`) y guarda el nombre del lugar como texto libre
+ acción (`cerrado`|`agregado`) + lat/lon + foto. Consecuencia: cuando un corredor marca que una
farmacia cerró, ese conocimiento **queda atrapado en el contexto de ese inmueble**; el POI sigue vivo
para todos los demás inmuebles del barrio, y la misma farmacia fantasma se le muestra al siguiente
comprador. **El "foso sobre el foso" de la SPEC §1.8 —el corredor confirma o cierra un POI— no está
construido:** hay una capa de puntos y una capa de correcciones, y no se tocan.

**1. ✅ HECHO (2026-07-27) — Restricción única sobre el identificador de origen.**
`migrations/020_pois_propios_id_origen_unico.sql`, aplicada en prod. Dos índices **parciales**
(`WHERE ... IS NOT NULL`) porque las columnas son mutuamente excluyentes: `pois_propios_overture_uidx`
y `pois_propios_osm_uidx`. Verificado 0 duplicados antes de crearlos. La migración deja además un
respaldo `pois_propios_backup_20260727` (4.898 filas) — era la primera recarga real de la tabla.
*No resuelve la conflación Overture↔OSM (mismo lugar en ambas fuentes = dos filas); eso tiene su
receta aparte en la SPEC §1.6 (≤60 m + nombre similar por trigram) y sigue pendiente.*

**2. ✅ HECHO (2026-07-27) — Refresco como upsert.** El script ya no hace `DELETE`+`INSERT`: hace
`ON CONFLICT (overture_id|osm_id) DO UPDATE` por fuente, y lo que ya no viene del origen se marca
**`operativo=false`, no se borra** (un POI que desaparece del mapa puede ser un cierre real o un
borrado erróneo: conservar la fila permite revertir y deja historial). La fila **sobrevive al
refresco con su `id`**, que es lo que hace posible el punto 3.
Primera corrida real: 2.851 Overture + 3.924 OSM upserted, **3 marcados cerrados**, 0 borrados.
Ahora sí tiene sentido una tarea mensual (Overture) / semanal (OSM) — ✅ **PROGRAMADA 2026-07-28**:
tarea de Windows **"Refresco POIs Contexto"**, lunes 14:00 (una hora antes del radar), vía
`scripts/refresco_pois.cmd quito`. Una sola tarea semanal cubre ambas fuentes: re-consultar
Overture cuesta ~10 s contra S3 y solo cambia con el release mensual; separar cadencias no paga.
Detalles operativos:
- **Reintentos**: 3 intentos espaciados 15 min. Overpass falló 2 de 3 veces el 2026-07-27; un
  fallo no corrompe nada (código 2 = fuente caída, POIs de OSM intactos), pero dejaba la corrida
  a medias. Código 1 = error duro, no se reintenta.
- **Señal**: `foso_pois_spike.py` ya no sale siempre 0 — `_salir()` devuelve 0/2 según si las
  dos fuentes respondieron. `--sin-validacion` omite el paso 4 (comparación legible para humanos)
  en corridas programadas.
- **Log**: `logs/refresco_pois_<ciudad>_<fecha>.log` (ignorado por git). Si la máquina estaba
  apagada el lunes, `StartWhenAvailable` la corre al encender.
- **Verificada de punta a punta** el 2026-07-28: corrida real vía el lanzador → código 0,
  7.189 operativos, 0 cerrados (idempotente); y el camino de error duro corta sin reintentar.

> ### ⚠️ INCIDENTE 2026-07-27 — el cierre masivo (leer antes de programar cualquier cron)
> En la segunda corrida, **Overpass devolvió 504 en sus dos endpoints**. `pull_osm` degradaba a
> lista vacía, y la primera versión de `CERRAR_AUSENTES` —que miraba las dos fuentes juntas—
> concluyó que los 3.924 POIs de OSM "ya no existían en el origen" y **los marcó cerrados**.
> Producción quedó en 2.851 operativos de 6.775 hasta que se revirtió.
>
> **Por qué la guarda existente no saltó:** era `if not pois: abortar`, y `pois` NO estaba vacío —
> Overture sí había traído sus 2.851. La guarda miraba el total, no cada fuente.
>
> **La lección:** *"no pude consultar el origen" no es "el POI ya no existe".* Un pipeline que
> borra o cierra por ausencia necesita distinguir las dos cosas, siempre.
>
> **Arreglado con tres cambios** (verificados con un simulacro que reproduce el 504):
> 1. `pull_osm` devuelve **None** cuando Overpass cae (≠ `[]`, que sería "no hay resultados").
> 2. El cierre es **por fuente** (`CERRAR_OVERTURE` / `CERRAR_OSM`) y se salta entera la fuente
>    que no respondió.
> 3. **Guarda de caída brusca:** si una fuente trae menos del 50% (`UMBRAL_CAIDA`) de lo que ya
>    había en la tabla, se asume respuesta parcial y no se cierra nada de ella.
>
> Que el modelo fuera "marcar cerrado" y no "borrar" es lo que hizo el incidente reversible con un
> solo `UPDATE`. Si el refresco hubiera sido el `DELETE`+`INSERT` anterior, se habrían perdido 3.924
> filas y habría hecho falta recargar desde el origen — con Overpass caído, imposible en ese momento.

**2b. ✅ OSM sumado para comercio de barrio (2026-07-27) — cierra la brecha de paridad.**
Medido en el bbox de Quito: OSM tenía **1.078 `shop=convenience`** (la tienda de esquina, que **no
existía** en la capa), 601 farmacias vs 466 de Overture y 341 supermercados vs 311. Era exactamente
la brecha contra Google (+84 m en farmacia, +24 m en supermercado). Se sumó OSM a esas dos categorías
—mismo patrón que ya se usaba en transporte— con el minimarket distinguible en `categoria_overture`.
En salud NO se sumó: Overture gana 858 a 498.
**Resultado: 4.898 → 6.775 POIs operativos.** farmacia 466→1.025, supermercado 311→1.632.
Paridad: farmacia +84 m → **+1 m**, supermercado +24 m → **−1 m** (ver §3 Fase 1 paso 3).
*Regla de calidad: el comercio SIN nombre no entra ("Encontré Farmacia a 200 m" es peor que caer a
Google); el transporte sin nombre sí, porque una parada anónima sigue sirviendo.*
**Nota legal:** OSM es ODbL → almacenable **con atribución**. Los términos de Google Maps Platform
no permiten guardar el contenido de Places: arrastrar sus resultados a `pois_propios` se descartó por
eso, no por dificultad técnica. (Verificar los términos vigentes antes de apoyar una decisión en ello.)

**3. ✅ HECHO (2026-08-04) — Enganchar la curación al POI.** `entorno_curacion.poi_id` referencia
una fila de `pois_propios` (migración 023, aplicada y verificada en prod). Cada visita de terreno
**se acumula y se propaga** a todos los inmuebles del barrio en vez de morir en la ficha donde se
capturó. Es el foso que no se puede descargar de ninguna API — y el único de los tres que construye
ventaja en vez de mantenerla.

**La decisión de diseño que lo hace sobrevivir:** la verificación **NO** se escribe sobre
`pois_propios`. El upsert del refresco semanal incluye `operativo = EXCLUDED.operativo`, así que un
`operativo=false` puesto por un corredor sería **resucitado por el cron del lunes** — Overture sigue
listando el local abierto. La fila sobrevive al refresco (migración 020), pero sus columnas se pisan.
Por eso la curación es un **overlay de lectura**, el mismo patrón que ya usaba el texto:

| Manda | En |
|---|---|
| origen (Overture/OSM) | nombre, geom, dirección, marca, confianza |
| el humano | si el lugar EXISTE |

Lo resuelve la vista **`pois_vivos`**: (1) la observación humana más reciente por POI gana sobre el
origen; (2) entre humanas gana la más reciente (un local reabre); (3) sin observación humana decide
`operativo`. Las 5 lecturas de entorno de `app/rutas.py` apuntan a la vista, **nunca** a la tabla.
Tercera acción `confirmado` ("estuve ahí, sigue abierto"), que puede sostener vivo un POI que el
origen dio de baja.

**Verificado en prod el 2026-08-04** (transacción con rollback, sin dejar rastro): un POI operativo
desaparece de `pois_vivos` al marcarlo cerrado; uno dado de baja por el origen revive al confirmarlo;
un `confirmado` posterior le gana a un `cerrado` anterior. `vivos_con_overlay == operativos_origen`
(8.489) con 0 curaciones enganchadas → la vista es inocua mientras nadie haya caminado.

`tests/test_curacion_propaga.py` (8 tests) guarda el invariante por los dos frentes: que ninguna
lectura vuelva a `pois_propios` y que el upsert del refresco no toque columnas de verificación.
Son **estáticos a propósito**: el fallo aquí no lanza excepción —la query devuelve filas válidas,
solo ignora al corredor— y no hay DB de pruebas en el repo.

⚠️ **Deuda consciente — alcance de la autorización.** `_assert_owner` valida que el corredor sea
dueño de ESE inmueble, pero una curación con `poi_id` afecta a toda la ciudad. Con un puñado de
corredores de confianza es el trato buscado (la verdad local compartida ES el foso); con decenas
hace falta **quórum**: N observaciones independientes antes de ocultar un POI para todos.

**Otros pendientes de la fase (sin dependencia entre sí):**
- ✅ ~~Categorías faltantes: **iglesia, seguridad**~~ — **RESUELTO 2026-07-27** (migración 021 +
  ingesta OSM: `place_of_worship` 276, `police` 127). Eran las dos únicas que el branch "ruta a X"
  mandaba a Google, y las que Google respondía **peor**: verificado en vivo con clave real,
  "iglesia más cercana" devolvía *"Wilson Maldonado"* y "UPC más cercano" *"ABOGADOS EN LINES"*.
  Ahora devuelven "Capilla Católica de Adoración…" y "Punto Nube" (nomenclatura real de la policía
  de Quito, junto a UPC Río Coca, GOE y retenes). **El branch ya no llama a Google en ninguna
  categoría** — solo quedaría para puntos fuera del bbox de la ciudad cargada.
  **Rótulo revisado (Fair Housing):** `_CAT_LABEL` pasó de "🛡️ seguridad" a "🛡️ UPC (policía
  comunitaria)" y `entorno.py` de "Seguridad (UPC)" a "UPC (policía comunitaria)". La UPC es un
  lugar con dirección, como un hospital; "seguridad" a secas se lee como una cualidad del barrio,
  que el canon prohíbe afirmar. Con dato malo la ambigüedad pasaba desapercibida; con dato bueno, no.
- **Atribución Overture/ODbL en UI:** hay menciones sueltas a OpenStreetMap en 3 vistas y **nada de
  Overture** hacia el usuario final; 2.047 POIs ODbL sirviendo en prod piden atribución formal.
  Alinea con el foso de honestidad — es discurso de proveniencia, cumplirlo es barato.
- **Métricas:** conteo de POIs por categoría/ciudad persistido (salud del foso). Con la columna
  `ciudad` ya existente esto es una query, no un desarrollo.
- **`parque` = 109 POIs** en todo Quito (umbral `CONF_MIN` 0.70, el más exigente). Invisible con
  inventario concentrado; primer hueco en abrirse con inventario disperso.
- ✅ ~~**Expansión:** bbox para nuevas ciudades~~ — **RESUELTO 2026-07-27** (migración 019 + registro
  `CIUDADES`; ver §4). Falta solo medir el bbox real de cada mercado nuevo antes de abrirlo.

**Cuándo:** nada de esto duele con 40 inmuebles demo y 0 corredores reales. El punto 3 es el que
construye lo irreplicable, y su disparador natural es **corredores visitando inventario real**.

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
