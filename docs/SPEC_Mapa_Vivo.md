# SPEC_Mapa_Vivo

> El mapa como intérprete visual de la intención conversacional. No un filtro de pines-precio: un lector de la charla que pinta el razonamiento del agente y el foso (datos de entorno verificados con proveniencia).

**Fecha:** 26 jun 2026 · **Origen:** discusión de visión (fundador) + grounding en código real (MapView.jsx, App.jsx, app/agent/tools.py, app/rutas.py). · **Estado:** spec — no implementado.
> ⚠️ Las referencias `archivo:línea` son al momento del grounding; confirmar en el build.

---

## Por qué

Realtor/Zillow/Redfin tratan el mapa como un **filtro hecho visual**: query → caen pines-precio → salida pasiva. Y obligan a alternar `Lista ⇄ Mapa` (dos modos que conmutas con un toggle).

Nuestro mapa es un **lector de la conversación**: interpreta qué quisiste decir y lo pinta. Es el narrador visual del razonamiento del agente y del foso. **El pin codifica ENCAJE + VERIFICACIÓN, no precio.**

- **Disciplina anti-portal:** NO replicar el muro de pines-precio. NO hay toggle Lista/Mapa: la conversación y el mapa son **una sola superficie que co-evoluciona**; el mapa siempre está leyendo.
- **Frase guía:** "no le dices que la caminabilidad es 95 — le pintas los 7 minutos a pie llenos de vida real".

---

## Anatomía — Modos (UN continuo, no tres features)

El lente sigue la **PRECISIÓN de la intención**, de más contextual a más preciso. Es el espinazo visual del embudo.

| Modo | Cuándo nace | Qué pinta | Foco |
|------|-------------|-----------|------|
| **ZONA** | Intención de búsqueda ("depas en La Carolina cerca de parques") | Encuadra el polígono de la zona; pinta los POIs verificados que el usuario pidió (parques en verde, cafés como puntos = el foso); colorea cada resultado por **ENCAJE, no por precio**. El mapa = evidencia de por qué cada resultado encaja. | `bbox` |
| **AURAS** | Interés en pocos candidatos | El aura de cada candidato: POIs cercanos por inmueble + su tiempo a pie. | `[id, id, …]` |
| **AURA-SINGLE** | Eligió uno | Re-centra en ESE inmueble; dibuja su **isócrona peatonal** (a cuánto llegas a pie), POIs cercanos con tiempo, capas ruido/verde/tráfico como el **entorno vivido** del punto. El "letrero inteligente" hecho espacio e interactivo. | `[id]` |
| **COMPARAR** | Dos inmuebles | Dos auras en el mismo encuadre, resaltando el **DELTA** — dónde difieren en lo que al usuario le importa ("este: parque a 3 min pero ruido alto; el otro: silencio pero Metro a 15"). Es el encaje relativo (tarea #8) hecho visual: no un "82% vs 76%" frío, sino dos auras superpuestas donde se VE el trade-off. | `[idA, idB]` |

---

## La directiva de mapa (MECANISMO ÚNICO)

Lo que hace que esto sea **UN sistema y no tres pantallas**. Cada turno del agente emite una **directiva de mapa estructurada**; el mapa la interpreta. El mapa es una **función pura de la directiva + el estado de la charla**.

```json
{
  "modo": "zona | auras | aura | comparar",
  "foco": "bbox | [id] | [idA, idB]",
  "capas": ["parques", "cafes", "ruido", "verde", "isocrona"],
  "pines": [
    { "id": "...", "encaje": 0.82, "badge": "parque a 3 min", "fresco": true }
  ]
}
```

**Separación razonamiento/visual:** el agente RAZONA y emite intención estructurada; el mapa RENDERIZA. Misma separación que el código ya respeta en `app/routers/chat.py::build_result_cards` (separa lo que ve el LLM de lo que renderiza el frontend). La directiva extiende ese principio al mapa.

> El pin **NO** lleva precio. Lleva `encaje` (color/intensidad) + `fresco` (verificación con proveniencia).

---

## Invocación (nace en la conversación)

**La pieza clave de UX.** El mapa **NO vive en el rail/barra como un botón frío** ("una herramienta más para apretar"). **NACE EN LA CONVERSACIÓN.**

- Se asoma **en el hilo**, en el momento en que la intención lo pide, como una **invitación viva** que dice "ábreme" (zona encuadrada, pines latiendo). Al tocarla se despliega a la superficie completa.
- **Mismo patrón que las ResultCards** que ya aparecen inline bajo el mensaje del agente: la invitación de mapa se monta igual — una **semilla de mapa viva** que pertenece a ESE turno, contextual y efímera.
- Cuando la charla avanza, la semilla **se actualiza** o una nueva se ofrece en el nuevo momento.
- **El mapa es algo que la conversación PRODUCE, no chrome de navegación.**

**Seam de montaje (espeja ResultCards exactamente):**
- `Message.jsx:251` — punto EXACTO donde montar el componente paralelo a ResultCards. Patrón: `{!isUser && msg.mapSeed && <div style={{paddingLeft: AVATAR_INDENT}}><MapSeed .../></div>}`.
- `AVATAR_INDENT = 42px` — alineación obligatoria con texto/tarjetas/nudge para no romper el layout.
- Usar la prop `isLast` (ya disponible en `App.jsx:1309-1315`) si la semilla solo debe latir en el último turno.
- **NO** cambiar `view` a `'map'` (eso es pantalla completa). Usar un estado adicional `mapInlineOpen` para el despliegue; `view='map'` queda solo como modo full-screen heredado.

---

## De dónde sale cada dato

| Campo de la directiva | Fuente real HOY | Estado |
|-----------------------|-----------------|--------|
| `foco: bbox` | Calcular sobre `msg.results` (lat/lon ya presentes) | Falta helper; lat/lon listos en `tool_find_assets_by_text` (`app/agent/tools.py:115`) |
| `pines[].id / encaje` | `app/routers/chat.py::build_result_cards:218` (`_pois_de_intencion`, reordena por distancia) | Apoyado; `encaje` necesita amarrar tarea #8 |
| `pines[].badge` | `pois: [{emoji, texto, distancia_m, minutos}]` de ResultCards | Apoyado |
| `pines[].fresco` | Proveniencia del foso: `servicios_cercanos` (Google Places→OSM) + overlay `entorno_curacion` | Apoyado; falta flag explícito |
| `capas: [parques, cafes]` | `app/rutas.py::analizar_zona:355` → `_servicios_con_coords:53` | **Falta emitir lat/lon por POI** (hoy solo `distancia_m`) |
| `capas: [ruido, verde]` | GeoJSON data-driven paint (`RUIDO_COLOR`), heurístico por sector + jitter | Apoyado — **marcar honestamente como "estimación por zona"** |
| `capas: [isocrona]` | NO existe; hoy solo polyline 2D ancho (glow) como "área de influencia" | **Trabajo duro (2C)** |
| Lat/lon por inmueble (render) | `tool_find_assets_by_text:115` (`ST_Y/ST_X`, 6 decimales) | Listo |
| Lat/lon en `tool_search_nearby_assets:40` | NO devuelve coords al agente | Falta agregar al output |

> **Proveniencia honesta:** `ruido`/`verde`/`tráfico` son heurísticos por sector (no medición real) → la UI debe rotularlos como estimación. `servicios_cercanos` puede traer un POI cerrado → la curación del corredor (`entorno_curacion`) es el único guardrail; `fresco` refleja eso.

---

## Estados y transiciones

El mapa es función pura de `(directiva, estado_charla)`. La directiva del turno N+1 transiciona el lente:

```
ZONA  ──(usuario fija interés en pocos)──▶  AURAS
AURAS ──(elige uno)──────────────────────▶  AURA-SINGLE
AURA-SINGLE ──(pide un segundo)──────────▶  COMPARAR
COMPARAR ──(descarta uno)────────────────▶  AURA-SINGLE
cualquiera ──(nueva búsqueda)────────────▶  ZONA
```

- **Animar el razonamiento:** cuando el agente dice "amplié a 3 km", el mapa anima la expansión (espeja el `radio_searched_m` progresivo de `tool_search_nearby_assets:40`, 800m→3km→6km). Cuando dice "es caminable", dibuja la isócrona.
- **Persistencia entre turnos:** hoy `AgentState` NO persiste contexto espacial → cada turno olvida zoom/capas. **Añadir `spatial_context` en `app/agent/state.py`** (`{lat, lon, zoom, layers_active, focus_mode}`) para que la transición no pierda el estado del turno anterior (riesgo "Session State Drift").
- **Limpieza de capas:** `MapView.jsx::capasRef` rastrea capas temporales; consolidar limpieza en transición (hoy hay cleanup en click, no en cambio de modo → riesgo marker-leak con animaciones encadenadas).

---

## Temperatura emocional — la transición zona→aura y el pin-anillo

El mapa no solo cambia de modo; cambia de **TEMPERATURA**. La transición zona→aura es el *beat* emocional del producto: de **"estoy evaluando"** (analítico, frío, rígido) a **"estoy donde quiero estar"** (cálido, íntimo, vivo). Dos ejes.

**Eje 1 — la profundidad de la intención CALIENTA el mapa.**
- **ZONA** — paleta fría/estructurada (`teal #2DBDB6` + slate/muted). Es un SONDEO: bordes crispos, pines como datos. Rígido, preciso, informacional.
- **AURAS** — los candidatos empiezan a templar; el frío gana un matiz cálido.
- **AURA-SINGLE** — calidez plena: el inmueble RESPLANDECE; la isócrona/POIs se pintan como **luz cálida**, no líneas frías. El mapa respira. Es el pago emocional.
- **COMPARAR** — dos auras cálidas, pero el DELTA en un acento analítico (vuelves a decidir).

El warming es literal en la paleta existente: **`teal #2DBDB6` → `gold #E8B84B`**. Frío teal (evaluando) → cálido gold (este es). Usa tokens que el producto ya tiene (`C` en `ResultCards.jsx`/`AnuncioView.jsx`).

**Eje 2 — el TIPO de intención tiñe la calidez (lo que buscas, NO quién eres).**
La calidez de destino se keyea al `tipo_activo` / propósito declarado. Misma mecánica para todos; solo cambia el sueño:
- **Hogar (casa/depto)** → ámbar dorado (`#E8B84B`) — la hoguera, "te imaginas viviendo aquí".
- **Oficina** → cálido enfocado/sobrio — productividad, "aquí rindes".
- **Inversión** → dorado-verde de valor/confianza — "esto crece", firme, no romántico.
- **Terreno** → tonos tierra/horizonte — potencial, amplitud, el lienzo en blanco.
- **Local comercial** → coral (`#E0685A`) vibrante — flujo, energía, "aquí pasa gente".

**La transición como ARRIBO (no un corte):** la cámara se acerca CONTIGO al inmueble; los pines vecinos se recogen/desvanecen; el teal hace cross-fade a la paleta cálida del intent; el **aura FLORECE desde el pin** (isócrona/POIs como luz radiando). Un *beat* de quietud al aterrizar — el mapa exhala. De lo angular/grid a lo orgánico/radiante. "Estoy donde quiero estar." Reusa `agregarRutaAnimada` (`MapView.jsx:108`, 3 capas glow/línea/flow) re-coloreado al hue cálido.

**El pin-anillo de encaje (instrumento emocional).** Un anillo que dice tres cosas a la vez:
- **ARCO** = % de encaje (se llena en reloj).
- **TEMPERATURA/HUE** = profundidad + tipo: teal en ZONA → hue cálido del intent en AURA (se entibia al seleccionar, animado).
- **BORDE/HALO** = verificación (`fresco`): borde sólido brillante = verificado; suave/punteado = "según el mapa". Al elegir, el halo FLORECE en el hue del intent.

En ZONA los anillos son fríos, finos, uniformes (datos). En AURA-SINGLE el anillo elegido se vuelve un **halo cálido que respira** — "este es tuyo".

**Guardrail (honestidad + Fair Housing — innegociable):** la calidez es REGISTRO, no pulgar en la balanza. El arco de encaje, los tiempos a pie y el flag `fresco` siguen siendo verdad; el glow NO infla el dato. Y la calidez se keyea a **QUÉ buscas** (hogar/oficina/inversión), **NUNCA a QUIÉN eres** (eso sería *steering*) — misma paleta para todos.

**Amarre de marca:** "Cada lugar tiene un aura" se vuelve LITERAL aquí — el aura es ese resplandor cálido del instante en que el lugar deja de ser un dato y se vuelve tu próximo hogar/oficina/inversión. El tagline no era marketing: era la especificación de este momento.

---

## Móvil primero

- La semilla inline reusa el patrón **scroll-snap** de ResultCards; altura máxima fija o lazy-height para no secuestrar el scroll del chat.
- Respetar `AVATAR_INDENT` y el `calc(100% - 32px)` ya usado por chat-bar/aura-card — **testear en iPhone SE** (riesgo de solapamiento documentado en `MapView.jsx`).
- Despliegue a superficie completa como overlay sobre el chat (`mapInlineOpen`), no como cambio de tab `view='map'`.
- `Suspense` debe envolver **solo** el componente de mapa para no bloquear el resto del hilo; considerar pre-fetch de MapLibre en `useEffect` si la semilla aparece seguido (hoy lazy-load pesado en `App.jsx:1133`).

---

## Dónde se conecta (archivos:símbolos reales)

**Frontend**
- `Message.jsx:251` — seam de montaje de la semilla inline (espeja ResultCards).
- `App.jsx:251-255` — patrón `{!isUser && msg.X?.length && <div><Comp/></div>}` con `AVATAR_INDENT`.
- `App.jsx:656` — `aiMsg.results = data.results`: añadir aquí `aiMsg.mapSeed = data.map_seed` (nueva propiedad del response).
- `App.jsx:484-500` — restauración de historial: incluir `mapSeed: m.map_seed || null`.
- `App.jsx:1118-1138` — render full-screen heredado de `MapView` (`view==='map'`); el inline NO pasa por aquí.
- `MapView.jsx:290` — `ejecutarAcciones(acciones)`: ya maneja `tour|ruta|puntos`; **extender** a `bbox|isocrona|heatmap` + modo zona/auras/aura/comparar.
- `MapView.jsx:108` — `agregarRutaAnimada(map,id,coords,color)`: reusar para auras/isócronas (3 capas: glow/línea/flow).
- `MapView.jsx:456` — carga GeoJSON: hoy trae TODO el catastro sin filtro → para 2A filtrar a `msg.results`.
- `frontend/src/api.js` — nuevo endpoint `POST /api/v1/location/{lat}/{lon}/directive` (devuelve directiva serializada).

**Backend**
- `app/routers/chat.py::build_result_cards:218` — ya enriquece con `servicios_cercanos`; **añadir coords + `encaje` + `fresco`** a cada pin.
- `app/routers/chat.py` `ChatResponse:329` — **nuevo field `map_seed` / `map_directive`** (serializar explícito; no asumir que viaja en `results[]`).
- `app/rutas.py::analizar_zona:355` — fuente única de zona; devolver `servicios[]` con `{lat, lon, categoria, emoji, distancia_m}`.
- `app/rutas.py::_servicios_con_coords:53` — **EMITIR lat/lon** por item (hoy solo `distancia_m`).
- `app/rutas.py::comando_mapa:432` — parametrizar `modo` (zona/auras/aura/comparar) y persistir en `AgentState`.
- `app/agent/tools.py::tool_search_nearby_assets:40` — agregar lat/lon al output.
- `app/agent/tools.py::tool_analyze_location:410` — devolver POIs con `{lat, lon, distancia_m, nombre, categoria}` (hoy texto plano).
- `app/agent/state.py` — `spatial_context` en `AgentState`.
- `app/rutas.py::_ruta_a_pie:87` — base de la isócrona (Google Routes WALK) para 2C.

**Amarres con otros SPECs/tareas**
- **Fase 2 de SPEC_Tarjeta_Resultado:** `results → MapView` por props, sync lista⇄mapa, pin con badge/%encaje.
- **Tarea #7** (Mapa Vivo / isócronas) → Fases 2C/2D.
- **Tarea #8** (encaje relativo) → modo COMPARAR y el campo `encaje`.
- **"Letrero inteligente":** el QR podría abrir directo en AURA-SINGLE.

---

## Plan por fases (ROI descendente)

**2A — barato, 80% del wow** (se apoya en lo que ya hay)
- `results → pines` + sync lista⇄mapa + pin por `encaje`/`badge`; espeja el conjunto del turno.
- Semilla inline en `Message.jsx:251` (nueva prop `msg.mapSeed`); filtrar GeoJSON a `msg.results`.
- Backend: `map_seed` en `ChatResponse`; bbox calculado sobre coords ya disponibles.
- **Modo ZONA** completo.

**2B — vista-aura de un inmueble**
- POIs + capas centradas con **radios/distancias reales que ya tenemos, sin routing**.
- Emitir lat/lon por POI (`_servicios_con_coords:53`, `analizar_zona:355`).
- **Modos AURAS + AURA-SINGLE** (sin isócrona aún; usar radios/distancias).
- Se amarra al "letrero inteligente".

**2C — isócronas peatonales REALES** (tarea #7, escalón duro)
- Grafo peatonal de OSM + ruteo a pie. Hoy NO existe (solo polyline 2D glow).
- Opciones: **VROOM/OSRM** (open-source, auto-hosteado, sin key) o Mapbox/Google Isochrone (pago).
- Enfoque recomendado: **pre-calcular malla isócrona de Quito** (bandas 5/10/15/20/30 min) como `POLYGON` en PostGIS, query por `ST_Contains` (<5ms), recálculo nocturno.
- `ejecutarAcciones` extiende a `isocrona`.

**2D — el mapa como ENTRADA**
- Dibujas una isócrona / tocas un parque → **alimenta la intención de vuelta al agente**.
- Cierra el bucle: mapa deja de ser solo salida y se vuelve un input estructurado a la conversación.

---

## Lo que NO copiamos

- **El muro de pines-precio.** El pin codifica ENCAJE + VERIFICACIÓN, nunca precio.
- **El toggle Lista ⇄ Mapa.** Una sola superficie que co-evoluciona; el mapa siempre lee.
- **El mapa-como-filtro pasivo.** El nuestro es lector activo del razonamiento (anima "amplié a 3 km", dibuja "es caminable").
- **El mapa-como-botón del rail.** Nace en el hilo como invitación viva y efímera, no como chrome de navegación permanente.
- **El "82% vs 76%" frío.** Comparar muestra dos auras superpuestas donde se VE el trade-off, no un número.
- **El muro de datos sin proveniencia.** Heurísticos rotulados como estimación; POIs verificados vía curación; `fresco` honesto.
