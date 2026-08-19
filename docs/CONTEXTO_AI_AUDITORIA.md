# CONTEXTO AI
## Auditoría integral del estado actual

**Fecha de la auditoría:** 2026-08-19
**Repositorio auditado:** `C:\Users\DETPC\Desktop\Contexto-AI`
**Rama / commit:** `main` @ `782e57ba3bf0fdf3f7a3a3b94fad0aa5f5f60069` — *"docs(render): el blueprint no es la fuente de verdad de las variables"* (2026-08-19 08:48 -05:00)
**Versión declarada de la API:** `2.0.0` (`main.py`, confirmada en el `openapi.json` de producción)
**Auditor:** Claude Code (sesión de solo lectura)

---

### Cómo leer este documento

Cada afirmación lleva su etiqueta de confianza. La regla fue: **si no lo pude demostrar contra código, configuración, base de datos o una respuesta real de producción, no lo afirmo.**

| Etiqueta | Significado |
|---|---|
| `[VERIFICADO]` | Comprobado ejecutando algo: una consulta a la base, una llamada a producción, una corrida de tests, o leyendo el código que lo implementa. |
| `[EXISTE PERO NO VALIDADO]` | El código está y parece correcto, pero no comprobé que funcione de punta a punta. |
| `[BACKEND NO VALIDADO]` | Hay endpoint e implementación, pero no encontré evidencia de uso real en los datos. |
| `[UI SIN BACKEND VERIFICADO]` | Hay pantalla; no comprobé el camino completo hasta el dato. |
| `[MOCK]` | Simulado a propósito. |
| `[HARDCODEADO]` | Valor fijo en el código. |
| `[NO VERIFICADO]` | No lo pude comprobar. Se dice así, no se rellena. |

**Qué NO se hizo:** no se modificó un solo archivo del proyecto, no se instaló nada, no se desplegó nada, no se escribió en la base de datos. Todas las consultas fueron `SELECT`. Las sondas contra producción fueron `GET`, más dos `POST` con cuerpo deliberadamente inválido para medir la puerta de autenticación sin escribir nada.

---

## 1. Resumen ejecutivo

Contexto AI es un **producto real, desplegado y funcionando** — no una maqueta. Hay una API sana en producción con 60 rutas, una aplicación web servida en dominio propio, una base PostGIS con datos vivos, un agente conversacional con memoria persistente, y 771 pruebas automáticas en verde. La velocidad de construcción es notable: 784 commits en ~11 semanas.

Y al mismo tiempo: **el producto todavía no tiene tracción, y su inventario es casi enteramente sintético.**

Los tres hechos que ordenan todo lo demás:

1. **Hay 40 inmuebles en producción. 39 usan fotos de banco de imágenes (`images.unsplash.com`) y todos fueron creados en junio de 2026.** Un solo inmueble tiene fotos reales de un corredor. Desde el 2026-06 **no se ha dado de alta ni un inmueble nuevo**. El "sistema vivo" — el bucle de contribución del corredor que la constitución del proyecto declara *"el producto, no una funcionalidad"* — ha producido, en dos meses y medio, **4 actos de curación, todos el mismo día (2026-06-18), del mismo corredor, sobre el mismo inmueble**. `[VERIFICADO]`

2. **El activo técnico más valioso no es el agente: es la capa propia de datos de entorno.** 8.512 puntos de interés de Quito (Overture Places + OpenStreetMap), almacenados en PostGIS con procedencia y confianza, servidos como fuente primaria del entorno con Google solo de relleno, y con un mecanismo de curación que propaga la verificación de un corredor a todo el barrio. Eso sí es difícil de copiar y sí es propio. **Pero su tubería de refresco está rota desde el 2026-08-18.** `[VERIFICADO]`

3. **La honestidad —que el proyecto trata como su foso— está instrumentada de verdad en varias capas, y filtrada en una.** Hay un motor determinista de encaje con lista blanca cerrada anti-discriminación, un verificador que contrasta la prosa del modelo contra los números del motor, un detector de sesgo territorial, y rótulos de procedencia en la ficha. Pero el mismo número de caminabilidad se presenta como *"OpenStreetMap"* en el bloque que lee el modelo y como *"estimación por zona, todavía sin contrastar"* en la tarjeta que lee la persona — en el mismo turno, para el único inmueble real del sistema. `[VERIFICADO]` (§16, hallazgo H-3).

**Distancia a un producto real:** técnicamente, cerca — el andamiaje está construido. Comercialmente, lejos — no hay inventario real, no hay tráfico (10 dispositivos distintos en agosto), y la hipótesis central (que un corredor contribuya verdad de terreno de forma sostenida) tiene una sola observación a favor y dos meses de silencio en contra.

**Riesgo mayor:** que el equipo siga construyendo capacidad sobre una hipótesis de adopción no validada. Todo lo construido desde julio (CRM Vivo, reenganche, embudo, avisos, puerta suave, hilos de handoff) sirve a un volumen de leads que hoy es **10 handoffs en total**.

---

## 2. Qué es Contexto AI

Reconstruido desde el código, no desde el material de venta.

**Lo que el sistema hace hoy, técnicamente:** dado un punto en el mapa (coordenadas del usuario, una dirección geocodificada o un inmueble del catastro propio), calcula y presenta el **entorno medido** de ese punto —caminabilidad, servicios cercanos con nombre y distancia, conectividad al transporte masivo con tiempo real a pie— y conversa sobre él con un agente que tiene prohibido afirmar lo que no consultó. Cuando la persona muestra intención de transacción, la transfiere a un corredor humano dentro del mismo chat.

**La unidad de negocio del modelo de datos** — y esto es lo más inteligente del diseño — es la separación entre:
- `activos_inmutables`: la **coordenada permanente** y todo lo que se acumula sobre ella (entorno, ficha técnica, fotos, verificaciones).
- `transacciones_temporales`: el **anuncio efímero** (operación, precio, estado).

El anuncio caduca; el activo y su historial quedan. Esa es la tesis de "Catastro Vivo" hecha esquema. `[VERIFICADO]` — `app/models.py`

**Lo que declara ser** (según `docs/NORTHSTAR_Contexto_Claude_Inmobiliario.md`): *"la asesora honesta que verifica el activo en el terreno y razona si vivir, rentar o invertir tiene sentido"*. La comparación con lo verificado está en §16.

**El eslogan** — *"Cada lugar tiene un aura"* — aparece literalmente en la portada de producción, en el letrero imprimible (`app/routers/assets.py:352`) y en la filosofía de marca. Qué es "aura" técnicamente: §8.7.

---

## 3. Estado actual

### 3.1 Producción — comprobada en vivo el 2026-08-19

| Servicio | Comprobación | Resultado |
|---|---|---|
| API | `GET https://contexto-ai-oregon.onrender.com/health` | `{"status":"healthy","service":"Contexto AI V2","database":"up","memoria":"postgres"}` HTTP 200 `[VERIFICADO]` |
| Esquema de la API | `GET /openapi.json` | HTTP 200 · **60 rutas** · versión 2.0.0 `[VERIFICADO]` |
| Web | `GET https://contexxto.com` | HTTP 200, título *"Contexto · Cada lugar tiene un aura"*, pantalla de entrada con 8 intenciones `[VERIFICADO]` |
| Base de datos | Consulta directa (solo lectura) | PostGIS 3.3.7 + pgvector 0.8.0, 33 tablas `[VERIFICADO]` |
| Memoria del agente | Campo `memoria` de `/health` | `"postgres"` — el checkpointer persistente está montado `[VERIFICADO]` |

El endpoint `/health` **distingue "vivo" de "vivo pero amnésico"**, y devuelve 200 a propósito incluso degradado para no provocar reinicios en bucle en Render. Es una decisión bien razonada, documentada en el propio código y en `docs/INCIDENTE_2026-08-18_Pools.md`. `[VERIFICADO]`

### 3.2 Actividad — la parte incómoda

| Señal | Junio | Julio | Agosto (19 días) |
|---|---|---|---|
| Commits | 337 | 339 | 108 |
| Conversaciones nuevas | 104 | 35 | **9** |
| Handoffs a corredor | 2 | 4 | 4 |
| Inmuebles dados de alta | 40 | **0** | **0** |
| Curaciones de entorno | 4 (todas el 18-jun) | 0 | 0 |

`[VERIFICADO]` — consultas de agregado sobre `chat_sessions`, `handoff_sesion`, `activos_inmutables`, `entorno_curacion`; `git log`.

Otros totales de producción: **9 perfiles** (2 corredores, 7 clientes), **57 llegadas registradas desde 10 dispositivos distintos** (todas de agosto — el instrumento se construyó el 2026-08-17), **34 sesiones con intención medida**, **20 mensajes de handoff**, **0 correcciones de ficha**.

**Lectura honesta:** la máquina se construyó más rápido de lo que consiguió a quién servir. El pico de uso fue junio (cuando el fundador y su círculo la probaban); desde entonces el uso cae mientras la capacidad sube.

---

## 4. Arquitectura

Ver `CONTEXTO_AI_ARQUITECTURA.md` para el detalle y los diagramas. Resumen:

**No es un monorepo.** Es un repositorio único con dos aplicaciones que se despliegan por separado:
- `app/` + `main.py` → API FastAPI, contenedor Docker, Render.
- `frontend/` → aplicación React/Vite, Vercel.

No hay paquetes compartidos, ni workspaces, ni gestor de monorepo. Los contratos entre las dos partes son los JSON de la API, sin tipos generados ni cliente compartido. `[VERIFICADO]`

**Tamaño real del código:**
- Backend: **16.106 líneas** de Python en 51 módulos. Los dos más grandes concentran casi un tercio: `app/routers/chat.py` (2.484) y `app/routers/assets.py` (2.452).
- Frontend: **10.918 líneas** en 40 archivos. `App.jsx` solo tiene **2.211 líneas**.
- Pruebas: 52 archivos, 771 casos.
`[VERIFICADO]` — `wc -l`

**Estilo arquitectónico:** monolito modular por dominio con una regla explícita y bien aplicada de **"lógica pura, sin red ni base de datos"** para los motores de decisión (`encaje.py`, `intencion.py`, `inversion.py`, `fair_housing.py`, `estilo_vida.py`, `verificacion_prosa.py`, `walk_score.py`). Esa separación es lo que hace que 771 pruebas corran en 95 segundos sin base de datos ni claves. Es una decisión de diseño de calidad alta y consistente. `[VERIFICADO]`

---

## 5. Producto

### 5.1 Qué puede hacer hoy una persona

Reconstruido de `frontend/src/App.jsx`, `Launcher.jsx`, `intencionesEntrada.js` y comprobado contra la portada en vivo.

**Pantalla de entrada** (`contexxto.com`): título *"¿Con qué te ayudo hoy?"*, ocho accesos, el eslogan y un botón principal *"Analiza dónde estás"*. `[VERIFICADO — visto en producción]`

#### Flujo A — Analizar dónde estoy (el más directo)
1. La persona pulsa *"Analiza dónde estás"* → el navegador pide su ubicación.
2. El agente llama `tool_analyze_location(lat, lon)`.
3. Ese camino ejecuta `app/rutas.analizar_zona()`: geocodificación inversa (Nominatim) + caminabilidad (Overpass/OSM en vivo) + servicios (capa propia, Google de relleno) + tiempo real a pie al transporte (Google Routes).
4. Responde en "modo cápsula": una respuesta corta con un dato memorable y 2–3 caminos para seguir.

`[VERIFICADO — código completo trazado]` · `[EXISTE PERO NO VALIDADO — no ejecuté un turno real para no gastar cuota ni escribir datos]`

#### Flujo B — Escanear el QR de un letrero
1. El corredor imprime un letrero con QR (`GET /assets/{id}/letrero.png`, generado con Pillow y `segno`).
2. Quien lo escanea aterriza en `/a/{id}` → se crea una sesión `qr-{uuid}` y se registra la llegada.
3. El agente abre en cápsula con un dato del inmueble, adaptando los caminos a la operación (arriendo vs venta — tiene prohibido ofrecer "¿es buena inversión?" para un arriendo).

`[VERIFICADO]` — hay **26 sesiones con prefijo `qr-`** en producción y 5 registros de `lead_actividad` de ese origen, todos sobre el mismo inmueble.

#### Flujo C — Explorar el mapa
Mapa MapLibre GL con los inmuebles (`/assets/geojson`), mapa conversacional (`POST /assets/mapa/comando` → traduce una pregunta en acciones de mapa: rutas, pines, categorías), modo AURA-SINGLE con isócronas peatonales, y modo comparar.

`[EXISTE PERO NO VALIDADO]` — código completo en `MapView.jsx` (1.002 líneas), `AuraSingleMap.jsx`, `CompararMap.jsx`; endpoints vivos en el `openapi.json` de producción.

#### Flujo D — Ver la ficha pública de un inmueble
`GET /assets/{id}/anuncio` es público a propósito. **Comprobado en vivo** con el único inmueble real: devuelve dirección, operación, precio, caminabilidad 94, ruido, vegetación, tráfico, conectividad (*"🚇 Quitumbe a ~1496 m (20 min a pie)"*), 5 servicios con distancia, 3 servicios *"confirmado por el corredor"*, 4 fotos reales y `entorno_verificado: {verificado: true, fecha: "2026-06-18"}`. `[VERIFICADO]`

#### Flujo E — Pedir un corredor (handoff)
El agente ofrece conectar; con el sí explícito llama `tool_connect_with_broker`; se crea `handoff_sesion`, se avisa al corredor por Web Push y correo, y ambos conversan dentro del chat.

`[VERIFICADO]` — 10 handoffs reales (7 *solicitado*, 3 *activo*) y 20 mensajes en producción.

#### Flujo F — Publicar un inmueble (corredor autenticado)
Alta con fotos → `POST /assets/publish` → enriquecimiento del entorno en segundo plano → ficha técnica → características → QR y letrero.

`[EXISTE PERO NO VALIDADO EN USO CONTINUO]` — el camino existe y se usó **una vez** (el inmueble de julio con fotos de WhatsApp). Ningún alta desde entonces.

#### Flujo G — CRM del corredor
Panel de leads, chat con el CRM en lenguaje natural (segundo agente con sus propias herramientas), estación de revisión de extracciones de visión, curación del entorno.

`[EXISTE PERO NO VALIDADO]` — 709 líneas en `CRM.jsx` + 292 en `CRMChat.jsx`, endpoints vivos. En datos: 2 corredores, 4 curaciones, 0 correcciones de ficha. **La estación de revisión tiene 1 ficha pendiente esperando desde hace semanas.**

#### Flujo H — Comparar dos inmuebles
`POST /chat/comparar` → delta de encaje entre dos inmuebles según las necesidades declaradas.

`[EXISTE PERO NO VALIDADO]` — endpoint vivo y sin autenticación; `DeltaEncaje.jsx` lo pinta.

### 5.2 Lo que NO puede hacer
- No hay búsqueda por filtros al estilo portal (no existe una pantalla de resultados con filtros).
- No hay favoritos, ni historial de inmuebles vistos, ni alertas guardadas de búsqueda. La tabla `notificacion` es de avisos de handoff, no de alertas de mercado.
- No hay agenda de visitas (`POST /visitas` registra **llegadas**, o sea de dónde vino alguien, no visitas al inmueble).
- No hay comparación de zonas como funcionalidad propia (solo prosa del agente).
- No hay generación de informes descargables.

---

## 6. Funcionalidades

El inventario exhaustivo, funcionalidad por funcionalidad con su evidencia, está en **`CONTEXTO_AI_INVENTARIO.md`**. Resumen de conteo:

| Estado | Cuántas | Ejemplos |
|---|---|---|
| **VERIFICADA** | 14 | entorno con capa propia, conectividad con Routes, handoff, QR/letrero, encaje, verificador de prosa, memoria persistente |
| **PARCIAL** | 11 | visión (4 de 40 activos), embeddings (8 de 40), curación (4 usos), CRM (2 corredores), isócronas (congeladas en julio) |
| **BACKEND NO VALIDADO** | 9 | reenganche, rescate de avisos, cuña por ancla+tiempo, similitud, métricas de lift, embudo |
| **UI ONLY / SIN BACKEND VERIFICADO** | 3 | recorrido narrado, comparar zonas, algunas rutas del mapa |
| **HARDCODEADA** | 4 | scores heurísticos por sector, parámetros de inversión, umbrales de intención, síntesis de "aura" |
| **NO IMPLEMENTADA** (pero prometida en docs) | 6 | Market API, Scoring API por estrategia, webhooks, OAuth de terceros, sandbox, multi-ciudad real |

---

## 7. Datos

### 7.1 Inventario real de la base de producción (2026-08-19)

`[VERIFICADO]` — consulta directa de solo lectura contra Supabase.

| Tabla | Filas | Lectura |
|---|---:|---|
| `activos_inmutables` | **40** | El catastro entero. **Todos creados entre el 2026-06-06 y el 2026-06-11** — una ventana de 5 días. |
| `transacciones_temporales` | 40 | 17 venta ($95.100–$300.000), 23 arriendo ($180–$1.910) |
| `ficha_tecnica_mantenimiento` | 39 | 35 manuales, 4 de visión (3 publicadas, 1 pendiente) |
| `pois_propios` | **8.512** | La capa propia. Solo ciudad `quito`. |
| `pois_vivos` (vista) | 8.498 | La anterior menos 14 cerrados por curación |
| `isocronas_inmueble` | 78 | 39 activos × (15 y 30 min). **Todas generadas el 2026-07-01** |
| `chat_sessions` | 148 | 122 sin título propio |
| `checkpoints` | 2.119 | 246 hilos de conversación |
| `intencion_sesion` / `intencion_evento` | 34 / 46 | Motor de intención con datos reales |
| `handoff_sesion` / `handoff_mensaje` | 10 / 20 | |
| `visita` | 57 | 10 dispositivos distintos, todo agosto |
| `profiles` | 9 | 2 corredores, 7 clientes |
| `entorno_curacion` | 4 | Todas del 2026-06-18 |
| `activo_embeddings` | 8 | 4 de imagen + 4 de ficha, sobre 4 activos |
| `correcciones_ficha` | **0** | El bucle de verdad-de-referencia nunca se usó |
| `agencies`, `aviso_email`, `embedding_cache`, `aura_pois_cache`, `historial_eventos_urbanos` | **0** | Construidas, nunca usadas |

### 7.2 Fuentes de datos

| Fuente | Tipo | Ciudad | Qué aporta | Formato | Frecuencia | Uso actual | Verificado |
|---|---|---|---|---|---|---|---|
| **Overture Places** | Terceros abiertos | Quito | 2.851 POIs (educación, salud, farmacia, supermercado, centro comercial, parque), confianza media **0,767** | Parquet vía DuckDB sobre S3 anónimo | Semanal — **ROTA desde 08-18** | Fuente **primaria** del entorno | `[VERIFICADO]` |
| **OpenStreetMap (Overpass)** | Público (ODbL) | Quito | 5.661 POIs (transporte 2.082, supermercado 1.686, farmacia 726, iglesia 557, parque 405, seguridad 205) | JSON Overpass | Semanal — misma tarea | Fuente primaria de transporte; motor de caminabilidad en vivo | `[VERIFICADO]` |
| **Google Geocoding API** | Terceros (pago) | Quito | Dirección → coordenadas | REST | En vivo por consulta | `tool_geocode_address`, camino preferente | `[VERIFICADO — código]` |
| **Google Routes API** | Terceros (pago) | Cualquiera | Tiempo real a pie por calles + polilínea | REST | En vivo | Conectividad y rutas del mapa | `[VERIFICADO — dato en producción: "20 min a pie"]` |
| **Google Places (New)** | Terceros (pago) | Cualquiera | POIs de relleno donde la capa propia no llega | REST | En vivo | **Solo relleno** desde el cambio de julio | `[VERIFICADO — código `_servicios_con_coords`]` |
| **Nominatim (OSM)** | Público | Mundo | Geocodificación inversa: barrio, ciudad, país | REST | En vivo | **Único camino** para el nombre del lugar | `[VERIFICADO]` ⚠️ contradice la constitución (§16, H-6) |
| **Valhalla auto-hospedado** | Propio (sobre OSM) | Ecuador | Isócronas peatonales | Docker + REST | Bajo demanda | 78 isócronas guardadas, todas del 01-jul | `[VERIFICADO en datos]` · estado actual del servicio `[NO VERIFICADO]` |
| **Anthropic Claude** | Terceros (pago) | — | Agente comprador, agente CRM, extractor de preferencias, visión | SDK/REST | Por turno | Núcleo conversacional | `[VERIFICADO]` |
| **Voyage AI** | Terceros (pago) | — | Embeddings multimodales 1024-dim | REST | Por ingesta | 8 vectores generados | `[VERIFICADO en datos]` |
| **Corredor (aportación humana)** | **Propio** | Quito | 4 curaciones de entorno con foto y coordenada, 1 inmueble real, 35 fichas técnicas declaradas | Formulario web | Ad-hoc | El único dato que nadie más tiene | `[VERIFICADO]` |
| **Supabase Auth + Storage** | Terceros | — | Identidad y almacenamiento de fotos/evidencias | SDK | — | 9 perfiles, fotos reales alojadas | `[VERIFICADO]` |
| Datos de estudio (parroquias) | Derivado propio | Quito | 40 parroquias con centroide "vivido" + equipamiento a 15 min a pie | JSON en `docs/` | Puntual (05-ago) | Material de contenido, **no** conectado al producto | `[VERIFICADO]` |

### 7.3 Clasificación por naturaleza

- **DATOS PROPIOS (el foso real):** las 4 curaciones de entorno con foto y coordenada, el inmueble real con sus fotos, las 35 fichas técnicas declaradas, las 78 isócronas pre-computadas, los 8.512 POIs ya procesados y almacenados, y —el más subestimado— **las 2.119 filas de conversación real**.
- **DATOS PÚBLICOS:** OSM (ODbL) y Overture (permisiva). El proyecto documentó explícitamente que ambos permiten almacenar y servir, a diferencia de Google. `[VERIFICADO — docs/SPEC_Foso_Capa_de_Datos.md §1.2]`
- **DATOS DE TERCEROS (alquilados):** Google Geocoding/Routes/Places, Anthropic, Voyage, Supabase, Resend.
- **DATOS GENERADOS:** las 4 extracciones de visión, los 8 embeddings.
- **DATOS SIMULADOS `[MOCK]`:** **39 de los 40 inmuebles.** Direcciones plausibles de Quito escritas a mano en `seed_ampliado.py` (*"Dataset: 30 activos ultra-realistas"*), fotos de `images.unsplash.com`, precios inventados, y valores de ruido/tráfico/vegetación tecleados uno por uno en el propio script. **Un solo `owner_user_id` es dueño de los 40.**

> ⚠️ **Esto es lo más importante de esta sección.** El sistema presenta 40 inmuebles con la misma seriedad visual y conversacional que el único real. La ficha del anuncio sí rotula ruido, vegetación y tráfico como *"estimación por zona (heurístico)"* — pero **no existe ningún rótulo que distinga un inmueble de demostración de uno verificado**. Coincide con la nota de memoria del fundador: *nunca decir "inventario real"*. Se sostiene, pero por disciplina humana, no por diseño del producto.

### 7.4 Licencias, límites y riesgo de proveedor

| Riesgo | Detalle | Severidad |
|---|---|---|
| **Google prohíbe almacenar** | Su condición de servicio impide guardar POIs, mallas o isócronas derivadas. El proyecto lo sabe y por eso construyó la capa propia. Mientras Routes/Geocoding sigan en el camino vivo, ese dato **no se puede acumular**. | Alto — es el techo estructural del foso |
| **Tubería de Overture rota** | `scripts/foso_pois_spike.py:58` fija `release/2026-06-17.0`; Overture rotó el lanzamiento y S3 ya no lo tiene. Log del 08-18: `IOException: No files found`. Corridas correctas: 07-28, 08-03, 08-11. | **Crítico** — el foso está congelado |
| **La tubería corre en el PC del fundador** | `scripts/refresco_pois.cmd`, tarea de Windows los lunes 17:00, escribiendo a la Supabase de producción. Sin el portátil encendido no hay refresco. | Alto |
| **Un solo mercado** | Los 8.512 POIs son `ciudad='quito'`. La migración 019 preparó la multi-ciudad, pero no hay una segunda ciudad cargada. | Medio — bloquea Mazatlán/Puebla |
| **Techo de conexiones de Supabase** | 15 clientes en modo sesión, repartidos a mano entre dos pools (4+2 y 6). Ya causó un incidente de 1h26m el 2026-08-18. | Medio — mitigado, no resuelto |
| **Voyage/Anthropic/Resend** | Claves de terceros; sin control de gasto visible en el repositorio. | Medio |

---

## 8. Inteligencia artificial

### 8.1 Proveedores y modelos `[VERIFICADO]`

| Uso | Proveedor | Modelo | Dónde |
|---|---|---|---|
| Agente del comprador | Anthropic | `claude-sonnet-4-5-20250929` (`LLM_MODEL`) | `app/agent/graph.py` |
| Agente del CRM | Anthropic | mismo | `app/agent/crm_graph.py` |
| Extractor de preferencias | Anthropic | mismo, con herramienta forzada | `app/preferencias.py` |
| Extracción visual de fichas | Anthropic | Claude con visión, `tool_use` forzado | `app/vision.py` |
| Juez de evaluaciones (opcional) | Anthropic | modelo barato (haiku) | `evals/run_evals.py` |
| Embeddings multimodales | Voyage AI | `voyage-multimodal-3`, 1024 dim | `app/embeddings.py` |

Temperatura 0,2; máximo 2.048 tokens; transmisión activada (sin ella el turno corría 12–23 s sin emitir un solo token). `[VERIFICADO]`

### 8.2 Orquestación

LangGraph 0.2.60, grafo ReAct de **tres nodos** — y el tercero es la mejor decisión de ingeniería del proyecto:

```
START → llm ⇄ tools → encaje → llm → END
```

El nodo `encaje` se intercala **entre las herramientas y la segunda pasada del modelo**. Puntúa los inmuebles que la búsqueda encontró y le entrega al modelo, como contexto autoritativo, **las mismas tarjetas que la persona verá**. `[VERIFICADO]`

Existe porque en agosto se documentó el fallo contrario (`docs/BATALLA_Hiinmo_vs_Contexto_2026-07-31.md`): en tres corridas idénticas las tarjetas daban números idénticos y la prosa cambiaba cada vez, incluyendo afirmar que un inmueble de $710 estaba *"dentro de tu presupuesto de $700"*. El motor calculaba **después** de que el modelo escribía. Ahora calcula antes. Ese diagnóstico —*"la causa no era el modelo: era que el modelo nunca veía lo que el motor había calculado"*— es el tipo de razonamiento que separa un equipo serio de uno que parchea prompts.

### 8.3 Herramientas del agente (9) `[VERIFICADO]` — `app/agent/tools.py`

| Herramienta | Qué hace | Fuente |
|---|---|---|
| `tool_find_assets_by_text` | Busca inventario por texto en el catastro propio | PostGIS |
| `tool_geocode_address` | Dirección → coordenadas | Google, con Nominatim de reserva |
| `tool_search_nearby_assets` | Inventario en un radio, con filtro de precio/operación | PostGIS |
| `tool_fetch_asset_lifecycle_specs` | Ficha completa del inmueble, **con las antigüedades ya calculadas** | PostGIS |
| `tool_analyze_location` | Habitabilidad de cualquier punto del planeta | Capa propia + Google + OSM |
| `tool_analyze_investment` | Rentabilidad bruta/neta, precio/m² | `app/inversion.py` (puro) |
| `tool_connect_with_broker` | Handoff al humano | DB + avisos |
| `tool_traducir_estilo_de_vida` | Concepto difuso → dato objetivo, servicio, "sin dato" o rechazo | `app/estilo_vida.py` (puro) |
| `tool_priorizar_opcion` | Marca una opción como priorizada en el panel | Estado |

**Detalle que merece elogio:** `tool_fetch_asset_lifecycle_specs` **calcula las antigüedades en Python y se las entrega hechas al modelo.** El comentario explica por qué: *"con solo el ancla temporal en el prompt seguía fallando una de cada cuatro (ene/2025 salía como 'hace ~7 meses' en vez de 19). Un prompt orienta una resta; no la garantiza."* Eso es exactamente la doctrina correcta —arreglar en la capa de datos, no en el prompt— y está aplicada, no solo escrita.

### 8.4 El prompt de sistema

**568 líneas** dentro de `app/agent/graph.py`. Es simultáneamente el activo de producto más denso del proyecto y su mayor deuda de mantenibilidad.

Contiene, entre otras: economía de herramientas (no llamar APIs de pago fuera de dominio), modo cápsula vs informe completo, atribución sin juicio (Fair Housing), aritmética prohibida, coherencia arriendo/venta, política de idioma con prohibición explícita del voseo rioplatense, proveniencia obligatoria por dato, frescura de los puntos de interés, honestidad bidireccional del transporte, prohibición de asesoría financiera, y presentación obligatoria de datos incómodos.

Es un documento de producto notable —codifica juicio real, con contraejemplos concretos de fallos vividos— pero **vive dentro de un módulo de Python, sin versionado propio, sin pruebas de regresión automáticas en integración continua, y sin forma de comparar dos versiones sin leer un `git diff` de 500 líneas.** `[VERIFICADO]`

### 8.5 Barandas y evaluación

| Capa | Qué hace | Estado |
|---|---|---|
| `app/preferencias.py` | Esquema **cerrado**: el modelo no puede emitir un campo de identidad porque no existe en la herramienta. Más un saneador que descarta cualquier clave fuera de la lista blanca. | `[VERIFICADO]` |
| `app/encaje.py` | Lista blanca **cerrada** de 8 dimensiones de necesidad. Nada fuera de ella puede mover el número. | `[VERIFICADO]` |
| `app/estilo_vida.py` | Traductor instrumentado de conceptos difusos a 4 destinos, con rechazo explícito de clases protegidas. | `[VERIFICADO]` |
| `app/fair_housing.py` | Detector determinista de veredictos de idoneidad territorial en la **salida** del agente. | `[VERIFICADO — pero solo registra en el log, no bloquea]` |
| `app/verificacion_prosa.py` | Contrasta la prosa contra los números del motor: presupuesto ablandado, encabezado falso, cifra sin procedencia, opción descartada ofrecida, orden alterado, gancho de venta. | `[VERIFICADO — en vivo solo registra]` |
| `app/agent/crm_guardrails.py` | 455 líneas de barandas para el agente del corredor. | `[EXISTE PERO NO VALIDADO EN USO]` |
| `evals/run_evals.py` | 11 casos de honestidad, tres mecanismos (regex, prosa-vs-motor, juez LLM). | `[EXISTE — se corre a mano contra el backend desplegado, NO en integración continua]` |

**El punto crítico:** los dos guardianes más importantes —el detector de sesgo territorial y el verificador de prosa— **están en producción en modo observación, no en modo bloqueo.** El propio código lo dice: *"por ahora solo registra en el log: primero hay que conocer la tasa real de desobediencia; el día que la cifra lo justifique, el interruptor para bloquear ya está puesto."* Es una decisión defendible. Pero **no encontré dónde se lee esa tasa.** No hay panel, ni métrica agregada, ni consulta que la resuma. El interruptor está puesto y el instrumento que debía decidir cuándo accionarlo no se está leyendo. `[VERIFICADO — ausencia comprobada]`

### 8.6 Respuestas a las preguntas de la Fase 8

| Pregunta | Respuesta |
|---|---|
| ¿Puede consultar datos? | Sí — PostGIS directo desde las herramientas. `[VERIFICADO]` |
| ¿Puede consultar mapas? | Sí — Google Places/Routes, OSM/Overpass, capa propia. `[VERIFICADO]` |
| ¿Puede ejecutar funciones / calcular? | Sí, con herramientas. **Y tiene prohibido calcular él mismo** (aritmética de presupuesto y antigüedades vienen resueltas). `[VERIFICADO]` |
| ¿Tiene memoria? | Sí — `AsyncPostgresSaver` de LangGraph. 2.119 puntos de control, 246 hilos. Degrada a memoria volátil si el pool no abre (causa del incidente del 08-18). `[VERIFICADO]` |
| ¿Tiene RAG? | **No en el camino conversacional.** Hay pgvector y 8 embeddings, pero alimentan `POST /assets/similar` (similitud imagen/ficha), no la recuperación del agente. `[VERIFICADO]` |
| ¿Tiene agentes? | Dos: comprador y CRM del corredor, con grafos y herramientas separadas. `[VERIFICADO]` |
| ¿Hay flujos de trabajo? | Sí, deterministas: cron de reenganche (6 h), rescate de avisos, enriquecimiento en segundo plano al publicar. `[VERIFICADO en código]` · `[BACKEND NO VALIDADO en datos]` |
| ¿Sabe de dónde vienen sus afirmaciones? | **Parcialmente.** Cada razón de encaje lleva un campo `fuente`, y el prompt exige nombrarla. Pero la caminabilidad se etiqueta "OpenStreetMap" sin mirar la procedencia real (§16, H-3). |
| ¿Puede citar fuentes? | Sí, y lo hace: *"registrados en el mapa"*, *"confirmado por el corredor"*, *"estimación por sector"*, *"precio publicado"*. `[VERIFICADO — visto en el bloque autoritativo generado]` |
| ¿Distingue hecho de inferencia? | Sí, por diseño explícito: ruido/tráfico/vegetación son siempre *"estimación, no medición"*; la ficha técnica es siempre *"declarada, no verificada"*. `[VERIFICADO]` |
| ¿Expresa incertidumbre y sabe decir "no sé"? | Sí, y está instrumentado: la vía `sin_dato` de `estilo_vida.py` devuelve *"es un interés legítimo que hoy NO tenemos verificado"*, y el prompt prohíbe concluir ausencia desde un campo vacío (*"ausencia de dato ≠ ausencia de Metro"*). `[VERIFICADO]` |

### 8.7 El concepto de "AURA" — qué es realmente

Investigado a fondo porque es la promesa central de marca.

**No existe un "índice de aura".** No hay campo, ni tabla, ni función que lo calcule. `[VERIFICADO — búsqueda exhaustiva en app/]`

"Aura" es, hoy, **cuatro cosas distintas con el mismo nombre**:

1. **Marca / filosofía visual** — `docs/branding/PHILOSOPHY_Aura_Cartografica.md`: fondo carbón, halo turquesa, dorado para el punto verificado. Es el eslogan de la portada y del letrero impreso. **Concepto visual.**

2. **Un modo de mapa** — `AURA-SINGLE` (`GET /assets/{id}/aura`): el inmueble re-centrado con sus POIs georreferenciados e isócronas peatonales. **Funcionalidad real y verificable.**

3. **Una tarjeta ligera** — `GET /assets/mapa/aura` → `aura_zona()`: barrio (Nominatim) + caminabilidad + titular. **Funcionalidad real.**

4. **Una frase de síntesis** — la función `_aura()` en `app/rutas.py:557`. **Esto es lo que más se parece a "el aura de un lugar", y son siete condicionales encadenados:** `[HARDCODEADO]`

```python
def _aura(ws, parque, transporte) -> str:
    verde, metro = parque is not None, transporte is not None
    if ws and ws >= 85 and verde and metro: return "conveniencia urbana con pulmón verde"
    if ws and ws >= 85 and metro:           return "vida urbana conectada, todo a un paso"
    if verde and not metro:                 return "un remanso residencial, verde y tranquilo"
    if metro:                               return "una zona bien conectada con la ciudad"
    if ws and ws >= 70:                     return "un barrio práctico para el día a día"
    return "una zona en crecimiento, con carácter propio"
```

**La cadena real, de punta a punta:**

```
ENTRADAS        coordenada (lat, lon)
   ↓
TRANSFORMACIÓN  Overpass/OSM   → POIs en 1.600 m
                Nominatim      → barrio, ciudad
                capa propia    → servicio más cercano por categoría
                Google Routes  → tiempo real a pie al transporte
   ↓
MÉTRICAS        caminabilidad 0–100 (9 categorías ponderadas, decaimiento por distancia)
                ruido BAJO/MEDIO/ALTO   ← heurística por sector  [HARDCODEADO]
                vegetación %            ← heurística por sector  [HARDCODEADO]
                tráfico veh/día         ← heurística por sector  [HARDCODEADO]
   ↓
MODELO          ninguno. Sin aprendizaje automático, sin ajuste, sin calibración.
   ↓
SALIDA          una frase de un catálogo de seis + prosa del LLM alrededor
```

**Lo único que sí es un cálculo defendible es la caminabilidad** (`app/walk_score.py`): 9 categorías con peso, decaimiento por distancia (1,0 a ≤400 m, 0,0 a ≥2.400 m), rendimientos decrecientes para las categorías densas. Es una reimplementación honesta de la metodología pública de Walk Score. El proyecto es correcto al no usar esa marca registrada y llamarlo *"Caminabilidad"*.

**Conclusión sobre "aura":** hoy es **branding + un modo de mapa + una heurística de seis frases**. No es un modelo, no es un índice compuesto, no es propiedad intelectual defendible. Es una promesa de marca bien hecha sobre una base de cálculo delgada. **Eso no es malo — pero no debe presentarse como algoritmo.**

---

## 9. Verificación — la tesis sometida a auditoría

> *"Contexto verifica el entorno antes de recomendar."*

Sometida a examen, afirmación por afirmación.

| Afirmación posible | ¿De dónde sale? | Evidencia | Método | ¿Reproducible? | ¿Auditable? | ¿Fuente? | ¿Fecha? | ¿Confianza? | Veredicto |
|---|---|---|---|---|---|---|---|---|---|
| **"Caminabilidad 94"** | `walk_score` del activo | POIs de OSM contados con decaimiento — **o** heurística por sector | Determinístico | Sí (función pura, con pruebas) | Sí | ⚠️ **Se afirma "OpenStreetMap" sin comprobarlo** | No | No | 🟡 **El número es sólido; su etiqueta miente** |
| **"El Metro a ~20 min a pie"** | `conectividad` | Google Routes, caminata real por calles | Determinístico (API externa) | Sí | Parcial (no se guarda la respuesta cruda) | Sí, implícita | No | No | 🟢 **La afirmación más sólida del sistema** |
| **"Farmacia X a ~165 m"** | `servicios_cercanos` | `pois_vivos` (Overture/OSM) con distancia PostGIS | Determinístico | Sí | Sí (hay `overture_id`/`osm_id` y confianza) | Sí | Sí (`actualizado_en`) | Sí (Overture: 0,767) | 🟢 **Verificable** — el prompt exige además decir *"salen del mapa y pueden haber cambiado"* |
| **"Confirmado por el corredor"** | `entorno_curacion` | Un humano estuvo ahí, con **foto y coordenada** | Registro humano | No (es un hecho, no un cálculo) | **Sí, con evidencia fotográfica** | Sí, nominal | Sí | Máxima | 🟢 **Lo mejor que tiene el sistema.** 4 registros. |
| **"Zona tranquila"** | El agente **tiene prohibido decirlo** | — | — | — | — | — | — | — | 🟢 **Correctamente rechazada.** El prompt obliga a devolver el juicio al usuario: *"el ruido aquí es estimación por sector ~bajo (no medición) — juzga tú si encaja."* |
| **"Ruido MEDIO"** | `score_ruido_predictivo` | **Tabla fija de 7 sectores de Quito** con un desplazamiento pseudoaleatorio derivado de la dirección | `[HARDCODEADO]` | Sí (determinista por dirección) | Sí (el código está a la vista) | Se rotula *"heurístico"* | No | No | 🟡 **Honestamente rotulada, pero es una invención con formato de dato.** No hay ninguna fuente de ruido. |
| **"Tráfico ~9.000 veh/día"** | `volumen_trafico_historico` | Escrito a mano en `seed_ampliado.py` | `[MOCK]` | — | — | *"heurístico"* | No | No | 🔴 **No hay fuente de tráfico.** El prompt manda redondear y decir *"estimado"*; para los 4 activos en 0 manda decir *"no medido"* — pero el número existe en la ficha. |
| **"Vegetación ~26%"** | `porcentaje_cobertura_vegetal` | Ídem | `[MOCK]` | — | — | *"heurístico"* | No | No | 🔴 Igual que el anterior. |
| **"Buena conectividad"** | Prosa del agente | Datos de conectividad reales | Generado por IA sobre dato real | No (prosa) | Solo por el verificador de prosa, **que solo registra** | Sí | No | No | 🟡 |
| **"Buena inversión"** | `tool_analyze_investment` | Precio, área, renta estimada, alícuota | Determinístico (`app/inversion.py`) | Sí | Sí | Sí | No | No | 🟡 **El cálculo es limpio; las entradas son sintéticas** en 39 de 40. El prompt prohíbe convertirlo en consejo de compra. |
| **"Zona familiar"** | **Prohibida en cuatro capas** | — | — | — | — | — | — | — | 🟢 **Correctamente bloqueada** |

### Veredicto sobre la tesis

**La tesis es cierta para el ENTORNO. Es falsa para las MÉTRICAS DE CONFORT.**

- ✅ **Servicios, transporte y distancias: verificados de verdad**, con procedencia, con confianza, con fecha, y con una capa humana de confirmación en terreno que ningún competidor tiene.
- ❌ **Ruido, tráfico y cobertura vegetal —los tres que más suenan a "calidad de vida medida"— no tienen ninguna fuente.** Son una tabla de siete sectores de Quito con desplazamiento determinista. `app/scores_heuristicos.py`, 67 líneas.

El proyecto **es honesto sobre esto** en la ficha (los rotula "heurístico", "estimación por zona, no medición") y en el prompt. Eso lo salva de mentir. Pero **no lo salva de que "verificamos el entorno" sea una afirmación a medias**: se verifica lo que se puede contar, y se estima —con formato de dato— lo que no.

**Lo que faltaría para que la tesis fuera entera:** una fuente real de ruido (sensores propios, modelo de tráfico, o el corredor midiendo con el móvil en la visita — que es la vía coherente con el foso).

---

## 10. Inteligencia geoespacial

### 10.1 Lo que existe `[VERIFICADO]`

| Capacidad | Implementación | Estado |
|---|---|---|
| Coordenadas | `Geometry(POINT, 4326)` en PostGIS | ✅ |
| Polígonos | `Geometry(MULTIPOLYGON, 4326)` para isócronas | ✅ |
| Radios | `ST_DWithin` sobre `geography` (metros reales) | ✅ |
| Isócronas | Valhalla peatonal, 15 y 30 min, pre-computadas | ✅ 78 guardadas |
| Distancias | `ST_Distance(::geography)` + Haversine puro en `walk_score.py` | ✅ |
| Tiempos | **Google Routes (caminata real)** con reserva a metros÷80 | ✅ |
| Punto en polígono | `ST_Contains` — la "cuña" ancla+tiempo | `[BACKEND NO VALIDADO]` |
| Geocodificación | Google, reserva Nominatim con 4 consultas progresivas | ✅ |
| Geocodificación inversa | **Nominatim únicamente** | ✅ funciona, ⚠️ contradice la constitución |
| Barrios/parroquias | 40 parroquias del DMQ con centroide corregido, en `docs/` | ⚠️ **no conectado al producto** |
| Agrupación | — | ❌ no existe |
| Límites administrativos en producto | — | ❌ no existe (`geography_columns` = 0 filas) |

### 10.2 La joya metodológica

`docs/ESTUDIO_Habitabilidad_Medida_Quito_2026-08.md` documenta un hallazgo real y bien argumentado: **el centroide geométrico oficial de una parroquia de Quito no es donde vive la gente.** Con centroides oficiales, parroquias urbanas devolvían **cero servicios** porque su centro geométrico cae en la ladera del Pichincha. Cochapamba: 3.512 m entre el centroide oficial y el "centro vivido".

Ese es exactamente el tipo de error que esta auditoría debía buscar ("centroides", "radios circulares") — **y el equipo ya lo encontró, lo documentó y lo corrigió.** El estudio también reemplazó el radio circular de 1.200 m por isócronas reales por calles. `[VERIFICADO]`

### 10.3 Errores potenciales que sí encontré

| Riesgo | Evidencia | Severidad |
|---|---|---|
| **531 pares (nombre, categoría) duplicados en `pois_propios`** | Consulta directa. La conflación Overture+OSM no deduplica por proximidad. | Media — infla el conteo de caminabilidad y puede mostrar el "mismo" lugar dos veces |
| **Nombres de POI sucios** | En producción: `"PlusMedical;Pro Shape Gym"` (dos negocios concatenados), `"EQ. RECONTEC 0"`. Hay un filtro (`_NOMBRES_GENERICOS`, `limpiar_texto_servicios`) pero no cubre esto. | Media — daña la credibilidad justo en la superficie que más se muestra |
| **Categorías forzadas** | `"Panadería la cesta del sabor"` aparece como 🛒 supermercado; OSM aporta **1.686 "supermercados"** en Quito (incluye tiendas de barrio). | Media — infla la caminabilidad de forma sistemática |
| **Caminabilidad de 100** | `"Av. 24 de Mayo y Cuenca, La Loma"` = 100. Un valor saturado es sospechoso por definición. | Baja — pero es un número que se muestra |
| **Isócronas congeladas** | Las 78 son del 2026-07-01. Un inmueble nuevo depende de que Valhalla esté vivo; su estado hoy es `[NO VERIFICADO]`. | Media |
| **Sin corrección peatonal local** | El propio `CLAUDE.md` reconoce que Google Routes ignora atajos peatonales reales (cita el Terminal de Quitumbe). Se aceptó a conciencia. | Baja — decisión consciente |
| **`spatial_ref_sys` con 8.500 filas** | Es la tabla estándar de PostGIS, no dato propio. Se aclara para que nadie la cuente como activo. | — |

---

## 11. Experiencia de usuario

### 11.1 Pantallas principales

| Pantalla | Archivo | Propósito | Usuario | Problemas detectados |
|---|---|---|---|---|
| **Lanzador** | `Launcher.jsx` (103 líneas) | Entrada limpia con 8 intenciones | Cualquiera | Sin explicación de qué es el producto antes de actuar; el único texto es el eslogan |
| **Chat** | `App.jsx` (2.211 líneas) | Conversación con tarjetas, mapa, comparar | Comprador/arrendatario | **Archivo desproporcionado**; concentra toda la orquestación |
| **Tarjetas de resultado** | `ResultCards.jsx` (385) | Inmuebles con % de encaje y sus razones | Comprador | Bien hecho: el pie de página adapta el texto a la procedencia real |
| **Mapa vivo** | `MapView.jsx` (1.002) | Exploración, lente con estados (zona/auras/aura) | Comprador | Segundo archivo más grande |
| **Ficha pública** | `AnuncioView.jsx` (394) | Lo que abre el QR | Público | **Muestra `ideal_para: "Familia de 4 personas"`** (§16, H-7) |
| **CRM** | `CRM.jsx` (709) + `CRMChat.jsx` (292) | Cartera del corredor + agente | Corredor | 2 corredores reales |
| **Estación de revisión** | `ReviewStation.jsx` (346) | Aprobar/corregir extracciones de visión | Corredor | **1 ficha pendiente sin atender; 0 correcciones en la historia** |
| **Publicar** | `PublishAsset.jsx` (229) + `Caracteristicas.jsx` (314) + `FichaTecnica.jsx` (251) | Alta de inmueble | Corredor | Usado 1 vez |
| **Curar entorno** | `ActualizarEntorno.jsx` (366) | Marcar cerrado / agregar servicio con foto | Corredor | **Usado 4 veces, un solo día** |
| **Campana / bandeja** | `Campana.jsx` (185) | Avisos agrupados por conversación | Ambos | Reconstruida tras la auditoría de 14 defectos del 12-ago |
| **Web de marca** | `QueEs.jsx` (210) en `/que-es` | Explicar el producto | Prospecto | Se renderiza **en lugar de** la app — buena decisión de rendimiento |

### 11.2 Evaluación por criterio

| Criterio | Valoración | Evidencia |
|---|---|---|
| **Claridad de la promesa** | 🟡 | El lanzador no dice qué es el producto. La explicación vive en `/que-es`, a la que solo se llega si la buscas. |
| **Jerarquía** | 🟢 | Cápsulas cortas, 1–3 opciones, gancho al final. Doctrina explícita y bien aplicada. |
| **Incorporación** | 🔴 | **No existe, por decisión documentada** (`docs/PLAN_Onboarding_Ecosistema.md`: *"no hay onboarding en la puerta, una sola puerta suave y la abre el motor"*). Coherente, pero la primera vez el usuario no sabe qué puede pedir más allá de los 8 accesos. |
| **Confianza y fuentes** | 🟢 | El mejor aspecto: procedencia rotulada, insignia "verificado en terreno" **con fecha**, aviso de frescura. |
| **Incertidumbre** | 🟢 | *"No tengo cargada la conectividad de este inmueble"* está instrumentado, no improvisado. |
| **Velocidad** | 🟡 | El turno tarda ~18 s de punta a punta (comentado en `App.jsx:827`). Hay transmisión por SSE. El *keepalive* existe porque el arranque en frío costaba 30–60 s. |
| **Móvil** | 🟢 | PWA completa: `manifest.webmanifest`, service worker, iconos maskable, notificaciones push, instrucciones específicas para iOS. |
| **Accesibilidad** | 🔴 `[NO VERIFICADO]` | **No encontré ni una sola prueba, auditoría ni anotación de accesibilidad.** Los estilos son en línea, no hay `aria-*` sistemático. |
| **Estados vacíos / errores / carga** | 🟢 | `ErrorBoundary.jsx`, degradación explícita en cada camino, mensajes accionables (*"Reintenta o pídeme algo como 'ruta al Metro'"*). |
| **Retroalimentación** | 🟡 | La campana funciona; no hay forma de que el usuario reporte un dato incorrecto. |

---

## 12. Seguridad

### 12.1 Secretos — limpio `[VERIFICADO]`

- `.env` está en `.gitignore` (junto con `.env.*`, salvo `.env.example`).
- **Nunca fue commiteado**: `git log --all -- .env` está vacío.
- Búsqueda de patrones de clave (`sk-ant-`, `AIza…`, `service_role`) sobre 40 commits: **solo menciones textuales en documentación**, ningún valor.
- El `.env` local tiene 13 variables, incluidas la de Anthropic, la de Google Maps y la URL completa de la base de producción — **correctamente fuera del repositorio**.

**No hay ningún secreto expuesto en el repositorio.** Es un resultado poco común y merece decirse.

### 12.2 Hallazgos de seguridad

#### 🔴 CRÍTICO — `POST /api/v1/assets/` sin autenticación en producción

```
POST https://contexto-ai-oregon.onrender.com/api/v1/assets/   (sin cabecera, cuerpo {})
→ HTTP 422   (error de validación, NO 401/403)
```

`[VERIFICADO — sonda real contra producción, cuerpo inválido a propósito para no escribir]`

En `app/routers/assets.py:2024`, `create_asset` no declara `verify_api_key` ni `get_current_user`. **Cualquiera en internet con un cuerpo válido puede insertar un inmueble en el Catastro Vivo de producción**, con la dirección y las coordenadas que quiera. Y como el endpoint encola el enriquecimiento en segundo plano (`_recompute_walk_score`), cada inserción **consume cuota real de Overpass y de Google**.

Impacto: contaminación del activo central del proyecto + amplificación de coste. El endpoint es el que usan los scripts de carga masiva, que sí pasan `CONTEXTO_API_KEY` — pero el servidor no la exige.

#### 🟠 ALTO — `GET /api/v1/chat/{session_id}/history` sin autenticación

```
GET .../api/v1/chat/auditoria-id-inexistente-000/history  → HTTP 200
```
`[VERIFICADO]`

Quien tenga un `session_id` lee la conversación completa. Está mitigado porque los identificadores son UUID v4 (`crypto.randomUUID()`), no adivinables. Pero:
1. Un enlace compartido, un registro de servidor o un historial de navegador filtra la conversación entera.
2. **Cada llamada dispara una llamada al LLM** (`extraer_preferencias`) para reconstruir las tarjetas. Un endpoint anónimo y sin llave que gasta tokens por petición es una vía de amplificación de coste.

#### 🟡 MEDIO — Otros endpoints abiertos que gastan dinero
`POST /assets/mapa/comando`, `GET /assets/{id}/rutas`, `GET /assets/{id}/aura`, `POST /chat/comparar` — todos sin llave. Los tres primeros llaman a Google. Están limitados por tasa (30–40/min **por IP**), lo que acota pero no impide el abuso distribuido. `[VERIFICADO]`

#### 🟡 MEDIO — DDL en tiempo de ejecución
`ensure_walk_score_fuente_column`, `ensure_curacion_table`, `ensure_aura_cache_table` y el bloque `_DDL` de `visitas.py` ejecutan `ALTER TABLE` / `CREATE TABLE` **desde el manejador de la petición**. Funciona y es idempotente, pero significa que el esquema de producción se modifica por tráfico HTTP y no por un proceso de migración controlado. `[VERIFICADO]`

### 12.3 Lo que sí está bien

- **Autenticación:** JWT de Supabase validado contra JWKS público (ES256), con caché de llaves. El backend **nunca maneja el secreto**. Diseño correcto. `[VERIFICADO]`
- **Autorización:** `_assert_owner` en todos los endpoints de edición; el CRM filtra por corredor.
- **CORS:** lista explícita de orígenes, sin comodín. Métodos acotados.
- **Limitación de tasa:** slowapi en **53 endpoints**.
- **Anti-SSRF:** `ingest_allowed_image_hosts` para la ingesta por URL.
- **`robots.txt`:** la API se declara no indexable.
- **Recuperación de sesión caducada:** interceptor de axios que renueva una sola vez, con protección contra bucles y contra condiciones de carrera. Bien pensado.
- **Datos personales:** el sistema captura correo y teléfono solo en el handoff. `lead_actividad` tiene un campo de consentimiento (`consent_reenganche_at`). **No encontré política de privacidad ni de retención.** `[NO VERIFICADO]`
- **Analítica / rastreo:** **ninguna herramienta de terceros.** No hay Google Analytics, ni Sentry, ni PostHog. `[VERIFICADO]` — bueno para la privacidad, malo para la observabilidad (§15).

---

## 13. Calidad técnica

### 13.1 Lo bueno — y es mucho

1. **La disciplina de "lógica pura".** Siete motores sin red ni base de datos. Es lo que permite 771 pruebas en 95 s. Decisión de arquitectura de calidad alta.
2. **Los comentarios explican el *porqué*, no el *qué*.** Casi cada decisión no obvia cita el incidente que la provocó, con fecha y a veces con el commit. Es la mejor documentación del repositorio y sobrevive a la rotación de personas.
3. **Fuente única de verdad, aplicada.** `analizar_zona()` alimenta al agente y al mapa; `estado_presupuesto()` alimenta la tarjeta y el bloque del modelo; `inversion.py` alimenta la herramienta y el endpoint REST.
4. **Degradación explícita y ruidosa.** Tras la auditoría de fallos silenciosos de julio, cada `except` que degrada **avisa** (`_avisar_capa_caida`, `logger.warning` con contexto).
5. **Nombres en español, consistentes.** `encaje`, `intencion`, `puerta`, `llegada`, `embudo`, `reenganche`. Coherente con la regla de la constitución.

### 13.2 Lo malo

| Problema | Evidencia | Severidad |
|---|---|---|
| **Dos archivos monstruo en el backend** | `chat.py` 2.484 líneas, `assets.py` 2.452. **30% del backend en 2 de 51 archivos.** `assets.py` mezcla catastro, QR, letreros, mapa, inversión, CRM, leads, reenganche, métricas, entorno, ficha y características. | **Alta** |
| **Un archivo monstruo en el frontend** | `App.jsx` 2.211 líneas: enrutamiento, sesión, geolocalización, chat, handoff, publicación, mapa, CRM. | **Alta** |
| **Sin tipos** | Frontend en JavaScript plano. `frontend/README.md` es la plantilla por defecto de Vite y **recomienda TypeScript** — nunca se adoptó. | Media |
| **Dependencia circular estructural** | `graph.py` importa de `routers/chat.py` **dentro de la función** para evitar el ciclo. Al menos 5 importaciones diferidas por esta causa. Síntoma de capas mal separadas. | Media |
| **Duplicación de heurísticas** | `app/scores_heuristicos.py` (67 líneas) y `scripts/scores_heuristicos.py` **han divergido**. Dos verdades para el mismo cálculo. | Media |
| **10 archivos SVG duplicados exactos** | `logo/` ≡ `Contexto_AI_Brand/logo/` (comprobado por hash). | Baja |
| **8 artefactos de siembra solapados** | `seed_data.py`, `seed_ampliado.py`, `gen_fichas_30.py`, `gen_sql_seed.py`, `fichas_30.sql`, `supabase_seed.sql`, `seed_demo_fase1.sql`, `seed_fill_all_fase1.sql`. Ninguno indica cuál generó los 40 activos vivos. | Media |
| **Migración duplicada** | `migration_tipo_activo.sql` (raíz) ≡ `migrations/002_tipo_activo.sql`. Y `init_db.sql` vs `supabase_migration.sql`. | Baja |
| **3 pruebas huérfanas** | `test_agent.py`, `test_geocoding.py`, `test_memory.py` en la raíz. `pytest.ini` fija `testpaths = tests` → **nunca se ejecutan.** | Baja |
| **Manejo de excepciones muy amplio** | Muchos `except Exception: # noqa: BLE001`. Justificados uno a uno, pero la superficie total es grande. | Media |
| **El prompt como código** | 568 líneas de producto dentro de un `.py`, sin versionado propio ni comparación entre versiones. | **Alta** (de producto) |

### 13.3 Código muerto

**No encontré módulos muertos.** Los 51 módulos de `app/` están importados al menos una vez. `[VERIFICADO — análisis del grafo de importaciones]`

Lo que sí está **inerte**: 5 tablas construidas y nunca usadas (`agencies`, `aviso_email`, `embedding_cache`, `aura_pois_cache`, `historial_eventos_urbanos` — todas con 0 filas). El modelo `HistorialEventoUrbano` existe en el ORM, el prompt lo menciona (*"Restricción de altura SHP en lote vecino"*), y **jamás se ha poblado**.

### 13.4 Documentación

~180 documentos en `docs/`. Es el activo intelectual más grande del proyecto y, a la vez, un riesgo: **una prueba propia del repositorio (`tests/test_afirmaciones_docs.py`) señala 8 documentos que "afirman estado sin bloque verificable"** —entre ellos `SPEC_Foso_Capa_de_Datos.md` y `REPORTE_FaseB_Completa.md`— y aun así **la prueba pasa** (solo imprime un aviso). El guardián existe y no muerde. `[VERIFICADO — salida de pytest]`

---

## 14. Tests

### 14.1 Ejecución real `[VERIFICADO]`

```
$ ./.venv/Scripts/python.exe -m pytest
771 passed, 10 warnings in 95.21s
```

**PASÓ — 771 de 771.**

### 14.2 Composición

| Tipo | Cuántos | Estado |
|---|---|---|
| Unitarios de lógica pura | ~50 archivos | ✅ El grueso |
| Con dobles de prueba | 19 archivos | ✅ |
| Con cliente HTTP / base de datos | **1** (`test_health_memoria.py`) | ✅ |
| Extremo a extremo reales | **0** | ❌ **No existen** |
| De IA (honestidad) | `evals/` — 11 casos | ⚠️ **A mano, contra el backend desplegado. NO en integración continua** |
| Geoespaciales | `test_walk_score.py`, `test_map_seed.py` | ✅ funciones puras |
| De validación de datos | `test_scores_fuente.py`, `test_afirmaciones_docs.py` | ⚠️ el segundo avisa pero no falla |
| Cobertura medida | — | ❌ **No hay `pytest-cov` ni informe** `[VERIFICADO — ausencia]` |

### 14.3 Lectura crítica

771 pruebas en verde es una cifra excelente **para lo que cubren**: los motores deterministas. La cobertura de los caminos que realmente fallan en producción —los que tocan la base, la red y el LLM— es **casi nula**, y eso explica por qué las auditorías de fallos silenciosos de julio y agosto encontraron 14 defectos "tirando de un solo hilo". Doce de los catorce fallaban en silencio. Ninguna prueba los habría cazado, porque ninguna prueba levanta la aplicación contra una base.

**El proyecto sabe esto** y lo escribió: `tests/test_evals_prosa.py` existe precisamente porque *"`evals/run_evals.py` corre a mano contra el backend desplegado, así que nadie se entera si un día deja de estar conectado"*. Buen diagnóstico, arreglo parcial.

---

## 15. Infraestructura

| Pregunta | Respuesta | Confianza |
|---|---|---|
| ¿Dónde está desplegado? | API: **Render**, Docker, plan *starter*, región Oregón. Web: **Vercel**. Base: **Supabase**. | `[VERIFICADO]` |
| ¿Hay producción? | **Sí, sana ahora mismo.** | `[VERIFICADO]` |
| ¿Hay preproducción? | **No.** Un solo entorno. | `[VERIFICADO]` |
| ¿Hay desarrollo? | Sí, local — **pero apunta a la MISMA base de producción.** `CLAUDE.md` lo advierte: *"dev local ataca la MISMA Supabase que producción"*. Causa directa del incidente del 08-18. | `[VERIFICADO]` |
| ¿Cómo se despliega? | Auto-despliegue de `main`: Render (~3-4 min, construye Docker) y Vercel. | `[VERIFICADO]` |
| ¿Hay integración continua? | **NO.** El único flujo de GitHub Actions es `keepalive.yml`, que solo hace `curl /health`. **Cero pruebas, cero análisis estático, cero puertas antes de desplegar.** | `[VERIFICADO]` |
| ¿Variables de entorno? | Sí — **y `render.yaml` NO es la fuente de verdad.** El propio archivo lo advierte (commit de hoy): el servicio corre con variables puestas a mano en el panel. | `[VERIFICADO]` |
| ¿Migraciones? | 25 archivos `.sql` numerados, **aplicados a mano**. Sin Alembic. Más DDL en caliente desde endpoints. | `[VERIFICADO]` |
| ¿Copias de seguridad? | `[NO VERIFICADO]` — depende del plan de Supabase, fuera del alcance del repositorio. |
| ¿Observabilidad? | **Casi ninguna.** Sin Sentry, sin métricas, sin trazas, sin panel. Solo `print()` y `logging` a la salida estándar de Render. `pg_stat_statements` está instalada. | `[VERIFICADO]` |
| ¿Registros? | Los de Render (efímeros) + 4 archivos de registro locales del refresco de POIs. | `[VERIFICADO]` |
| ¿Dominio y TLS? | `contexxto.com`, HTTPS. | `[VERIFICADO]` |
| ¿Límites conocidos? | Supabase: 15 conexiones en modo sesión (repartidas 4+2 / 6). Resend: 3.000 correos/mes. Render *starter*: 1 instancia. | `[VERIFICADO]` |
| ¿Costes? | Render *starter* $7/mes + Render *standard* para Valhalla + Supabase + Vercel + Anthropic + Google Maps + Voyage + Resend. **Ninguna cifra real ni control de gasto en el repositorio.** | `[NO VERIFICADO]` |

**El punto más grave de esta sección:** *"Evitar desplegar backend con testers activos"* es una instrucción en `CLAUDE.md`. Es la definición de no tener preproducción. Y **desplegar no ejecuta ni una prueba**, con 771 disponibles.

---

## 16. Realidad vs narrativa

La sección obligatoria. Cada fila es una afirmación que aparece en la documentación, la marca o el material de venta del proyecto, contrastada con lo que el código y los datos demuestran.

| # | NARRATIVA ACTUAL | REALIDAD VERIFICADA |
|---|---|---|
| **H-1** | *"El loop de contribución del corredor **es el producto** (el sistema vivo)"* — `CLAUDE.md` | **4 curaciones en toda la historia, todas el 2026-06-18, un corredor, un inmueble. Cero desde entonces.** El bucle está construido, probado y desierto. Es una hipótesis, no un producto. `[VERIFICADO]` |
| **H-2** | *"Catastro Vivo e Inmutable — API de Inteligencia Inmobiliaria"* — descripción de la API en producción | **40 inmuebles. 39 con fotos de banco de imágenes. Todos de junio. Un solo dueño.** El catastro tiene un (1) inmueble real. `[VERIFICADO]` |
| **H-3** | *"La caminabilidad viene marcada con su procedencia real; JAMÁS afirmes 'comercios reales / OpenStreetMap' para una caminabilidad estimada: no puede decir una cosa en la pantalla y otra en el chat"* — prompt, regla 1.1 | **El sistema comete exactamente ese error.** `app/encaje.py:209` etiqueta la fuente como `"OpenStreetMap"` **siempre**, sin mirar `walk_score_fuente`. **Los 40 activos de producción tienen `walk_score_fuente = NULL`.** Ejecutado con el inmueble real: el bloque autoritativo que lee el modelo dice `caminabilidad 94/100 [OpenStreetMap]`, mientras `/anuncio` del **mismo inmueble** devuelve `scores_fuente.caminabilidad: null` y la tarjeta rotula *"estimación por zona, todavía sin contrastar con los comercios del sector"*. **El mismo número, dos afirmaciones opuestas, en el mismo turno.** `[VERIFICADO — ejecución directa del motor]` |
| **H-4** | *"El foso: poseer la capa de datos... reproducible por nosotros"* — `CLAUDE.md` | La capa **existe y es real** (8.512 POIs propios sirviendo el entorno). **Pero su tubería de refresco está rota desde el 2026-08-18** (`release/2026-06-17.0` de Overture ya no existe en S3) **y corre en el portátil del fundador como tarea de Windows.** Un foso que depende de un PC encendido los lunes. `[VERIFICADO — registros de logs/]` |
| **H-5** | *"Contexto verifica el entorno antes de recomendar"* | **Verdad a medias.** Servicios, transporte y distancias: verificados con procedencia y confianza. **Ruido, tráfico y vegetación: una tabla fija de 7 sectores de Quito con desplazamiento pseudoaleatorio** (`app/scores_heuristicos.py`, 67 líneas). No hay ninguna fuente de ruido ni de tráfico. Se rotula como estimación —lo cual salva la honestidad— pero *"verificamos el entorno"* cubre la mitad del entorno. `[VERIFICADO]` |
| **H-6** | *"Se ABANDONA OpenStreetMap / Nominatim... NO revertir el geocoder a Nominatim... si dudo, la dirección es siempre hacia Google"* — decisión zanjada, `CLAUDE.md` | **`_reverse_geocode` usa Nominatim como ÚNICO camino, sin alternativa de Google.** Es la fuente del nombre del barrio que ve **todo** usuario en `analizar_zona`, `aura_zona` y `recorrido_zona`. La decisión zanjada no se cumple en el camino más visitado del producto. `[VERIFICADO]` |
| **H-7** | *"PROHIBIDO que dictamines la idoneidad de un barrio para un grupo o perfil... nunca digas 'ideal para criar niños'"* — prompt, regla de atribución | El inmueble real de producción tiene almacenado **`ideal_para: "Familia de 4 personas"`**, `AnuncioView.jsx:283` lo pinta como *"✨ Ideal para: Familia de 4 personas"*, y **la regla 8a del propio prompt ordena usarlo**: *"'Ideal para …' (usa el campo `ideal_para` si existe, o infiérelo del perfil)"*. La baranda anti-discriminación y el campo de venta se contradicen dentro del mismo documento. `[VERIFICADO]` |
| **H-8** | *"Suite automática que verifica que el agente no miente... la vara es el eval, no el demo"* — `evals/README.md` | **Los evals se corren a mano.** No hay integración continua. Y los dos guardianes vivos —detector de sesgo territorial y verificador de prosa— **solo escriben en el registro; no bloquean.** El código dice que se activará *"el día que la cifra lo justifique"*: **no encontré dónde se lee esa cifra.** `[VERIFICADO — ausencia comprobada]` |
| **H-9** | *"Capacidades operativas (todas en producción)... la maquinaria para recibir, enriquecer, revisar y publicar un activo ya existe y funciona"* — `REPORTE_Hidratacion_Activos_Reales.md` | **Cierto y engañoso a la vez.** La maquinaria funciona; se usó **una vez** desde que se escribió (junio). Cola de revisión: **1 ficha pendiente, 0 correcciones en la historia**. Existe ≠ está en uso. `[VERIFICADO]` |
| **H-10** | *"Cada lugar tiene un aura"* | **No existe un índice de aura.** Hay marca, un modo de mapa, y **una función de 7 condicionales** que devuelve una de 6 frases. `[VERIFICADO — app/rutas.py:557]` |
| **H-11** | *"API-first... el motor que la banca de inversión y las constructoras integran"* — `ESTRATEGIA_API_First.md` | La **arquitectura** sí es API-first (lógica pura consumida por agente y REST). La **plataforma** no existe: sin OAuth de terceros, sin webhooks, sin entorno de pruebas, sin documentación pública, sin claves autoservicio, y con Market API y Scoring API **no implementadas**. El propio documento lo secuencia bien (*"deja que el primer integrador hale la API a existir"*) — la narrativa externa no siempre lo hace. `[VERIFICADO]` |
| **H-12** | *"39 activos → QR + letrero imprimible"* | El generador funciona. **Hay 26 sesiones de QR en producción y todas apuntan al mismo inmueble.** Un letrero impreso en la calle, no 39. `[VERIFICADO]` |

> **Lo que hay que reconocerle al proyecto:** casi todas estas brechas ya están señaladas *dentro del propio repositorio* — en las auditorías de fallos silenciosos, en el reporte de hidratación, en las notas de degradación. **La cultura de honestidad interna es real y poco común.** El problema no es que el equipo se engañe: es que la narrativa externa se escribe desde lo construido, y lo construido se adelantó mucho a lo adoptado.

---

## 17. Activos

Los 10 más valiosos, ordenados por valor defendible.

| # | Activo | Estado | Valor | Reutilizable | Riesgo |
|---|---|---|---|---|---|
| **1** | **Capa propia de POIs con procedencia** — 8.512 puntos, Overture+OSM, confianza por punto, en PostGIS, sirviendo como fuente primaria | ✅ En producción | **Muy alto.** Es lo único que Google no permite tener. | **Altísima** — turismo, comercio minorista, logística, seguros, urbanismo | Tubería rota (08-18); una sola ciudad; corre en un PC |
| **2** | **Curación de entorno propagada por barrio** — el corredor marca un local cerrado con foto y coordenada, y desaparece para **todos** los inmuebles del sector (vista `pois_vivos`, migración 023) | ✅ Construido, **4 usos** | **El foso sobre el foso.** Requiere haber estado ahí. | Alta — cualquier vertical con "el dato del mapa está desactualizado" | **Adopción cero comprobada** |
| **3** | **Motor de encaje determinista con lista blanca anti-discriminación** | ✅ En producción, con pruebas | Alto — auditable al 100%, defendible ante un regulador | Alta — cualquier recomendación regulada | La etiqueta de fuente miente (H-3) |
| **4** | **El prompt de sistema (568 líneas)** — juicio de producto codificado con contraejemplos de fallos reales | ✅ En producción | **Alto y subestimado.** Es meses de aprendizaje destilado. | Media — específico del dominio | Sin versionado, sin pruebas en integración continua, en un `.py` |
| **5** | **Verificador de prosa contra motor** — mide si el modelo obedeció al ranking | ✅ Construido | Alto — es la respuesta correcta a "un prompt es una petición, no una garantía" | **Muy alta** — cualquier sistema donde un LLM narra números | Solo registra; nadie lee la tasa |
| **6** | **2.119 puntos de control de conversación real** (246 hilos) | ✅ En producción | Alto para producto — es el corpus de qué pregunta la gente sobre un lugar | Media (datos personales) | Sin explotar; sin política de retención |
| **7** | **Motor de intención explicable** — 9 estados, puntuación con razones, sin LLM | ✅ En producción (34 sesiones) | Medio-alto — el handoff en el pico es diferencial frente a un CRM | Alta — cualquier venta consultiva | Umbrales sin calibrar (*"placeholder"* en el código) |
| **8** | **Estudio de habitabilidad de 40 parroquias** + hallazgo del "centro vivido" | ✅ Publicado (05-ago) | Medio-alto — munición de credibilidad y de contenido | Alta | **No conectado al producto** |
| **9** | **Isócronas peatonales propias (Valhalla)** — 78 pre-computadas | ✅ Construido | Medio-alto — Google prohíbe guardarlas; estas son propias | Alta — logística, comercio, urbanismo | Congeladas en jul-01; estado del servicio no verificado |
| **10** | **771 pruebas verdes en 95 s** | ✅ | Medio — permite tocar los motores sin miedo | Interna | No cubren base, red ni LLM; sin integración continua |

**Mención aparte: el cuerpo documental** (~180 documentos con el porqué de cada decisión). No es un activo de producto, pero es lo que haría que un ingeniero nuevo fuera productivo en días en vez de semanas. Vale más que buena parte del código.

---

## 18. Gaps

20 brechas, con severidad y categoría.

| # | Brecha | Severidad | Categoría |
|---|---|---|---|
| 1 | **No hay inventario real.** 1 de 40 inmuebles es de verdad. Sin inventario, ningún flujo tiene valor comercial. | **CRÍTICO** | NEGOCIO |
| 2 | **`POST /assets/` abierto en producción** — cualquiera escribe en el catastro y gasta cuota de Google. | **CRÍTICO** | TÉCNICO |
| 3 | **Tubería del foso rota** desde el 08-18 (lanzamiento de Overture fijo en el código). | **CRÍTICO** | DATOS |
| 4 | **El bucle del corredor no está validado.** 4 curaciones, 0 en dos meses. Es la hipótesis central del negocio. | **CRÍTICO** | NEGOCIO |
| 5 | **La procedencia de la caminabilidad miente** al modelo (H-3), rompiendo la regla de honestidad que es el foso declarado. | **ALTO** | IA |
| 6 | **Sin integración continua.** 771 pruebas que no bloquean ningún despliegue. | **ALTO** | TÉCNICO |
| 7 | **Sin preproducción.** Desarrollo local apunta a la base de producción; ya causó un incidente de 1h26m. | **ALTO** | OPERACIÓN |
| 8 | **Sin observabilidad.** Cero errores agregados, cero métricas, cero trazas. Un fallo se descubre "por casualidad". | **ALTO** | OPERACIÓN |
| 9 | **Sin fuente de ruido/tráfico/vegetación.** Tres de las cuatro métricas de confort son inventadas. | **ALTO** | DATOS |
| 10 | **Los guardianes no muerden.** Sesgo territorial y verificador de prosa solo registran; nadie lee la tasa. | **ALTO** | IA |
| 11 | **`ideal_para` contradice Fair Housing** dentro del propio prompt (H-7). | **ALTO** | PRODUCTO |
| 12 | **La tubería de datos corre en un portátil.** Sin servidor, sin alerta, sin redundancia. | **ALTO** | OPERACIÓN |
| 13 | **Una sola ciudad.** Los pilotos de Mazatlán y Puebla necesitan una segunda carga que nadie ha hecho. | **ALTO** | DATOS |
| 14 | **Historial de chat sin autenticación** + gasto de LLM por petición anónima. | **MEDIO** | TÉCNICO |
| 15 | **Deuda estructural:** 3 archivos de >2.000 líneas concentran el 30% del código. | **MEDIO** | TÉCNICO |
| 16 | **122 de 148 conversaciones sin título propio** — la bandeja es ilegible. | **MEDIO** | UX |
| 17 | **Nada distingue un inmueble de demostración de uno real** en la interfaz. Solo la disciplina humana evita la afirmación falsa. | **MEDIO** | PRODUCTO |
| 18 | **Sin incorporación.** Decisión consciente, pero el nuevo usuario no sabe qué puede pedir. | **MEDIO** | UX |
| 19 | **Accesibilidad sin auditar** — cero evidencia de trabajo en accesibilidad. | **MEDIO** | UX |
| 20 | **Sin control ni visibilidad de costes.** Ninguna cifra de gasto en Google/Anthropic/Voyage en ningún sitio. | **MEDIO** | NEGOCIO |

---

## 19. Qué NO hacer

Esta sección importa tanto como el roadmap.

### ❌ No construir la plataforma de API pública
Sin webhooks, sin OAuth de terceros, sin entorno de pruebas, sin documentación pública. **El propio `ESTRATEGIA_API_First.md` ya acertó**: *"deja que el primer integrador hale la API a existir; no la construyas antes"*. Hacer caso a ese documento.

### ❌ No añadir una segunda ciudad todavía
Quito tiene 8.512 POIs, 40 inmuebles (39 falsos), 1 corredor activo y 9 usuarios en agosto. **Duplicar la superficie antes de validar la primera multiplica el coste sin multiplicar el aprendizaje.** Además la tubería de POIs está rota: una segunda ciudad heredaría el mismo fallo.

### ❌ No construir más CRM
`CRM.jsx` (709) + `CRMChat.jsx` (292) + `crm_graph.py` + `crm_tools.py` + `crm_guardrails.py` (455) + `panel_seed.py` + `siguiente.py` + `embudo.py` + `reenganche.py` + `reenganche_cron.py` + `lift.py` ≈ **2.500 líneas para 2 corredores y 10 handoffs.** La relación capacidad/uso ya es extrema.

### ❌ No construir agenda de visitas, favoritos, alertas de búsqueda ni comparador de zonas
Son funcionalidades de portal. Contexto **no es un portal** — es una capa de verificación de entorno. Añadirlas es crecimiento por acumulación y borra la diferencia.

### ❌ No perseguir el "modelo de aura"
No hace falta aprendizaje automático. La caminabilidad ya es defendible. **Lo que falta no es un modelo mejor: son fuentes de datos que hoy no existen** (ruido, tráfico). Un modelo sobre datos inventados es peor que una heurística rotulada como tal.

### ❌ No refactorizar los tres archivos grandes ahora
Duele, pero no está bloqueando nada. Con 771 pruebas verdes y un solo desarrollador, la ganancia es interna. **Primero: cerrar el agujero de `POST /assets/`, arreglar la tubería de POIs, y poner integración continua.** Esos sí bloquean.

### ❌ No publicar más contenido con la palabra "verificado" sin el asterisco
Hasta que exista una fuente de ruido y tráfico, *"verificamos el entorno"* cubre la mitad. El material de venta debe decir qué mitad.

### ⚠️ Hipótesis todavía NO validadas — nombrarlas
1. Que un corredor contribuya verdad de terreno de forma **sostenida** (evidencia: 4 actos, un día).
2. Que el comprador prefiera el entorno verificado por encima del inventario (evidencia: 9 conversaciones en agosto).
3. Que el handoff en el pico de intención valga más que un lead de portal (evidencia: 10 handoffs, ningún cierre registrado).
4. Que el QR físico genere tráfico (evidencia: 26 sesiones, un letrero).
5. Que una PYME inmobiliaria pague por esto (evidencia: **cero ingresos comprobables en el repositorio**).

### 🚩 Dónde acecha la acumulación de funcionalidades
El proyecto lleva tres meses construyendo *hacia adentro* — instrumentos, medidores, motores, barandas — todos excelentes, todos sirviendo un volumen de uso que cabe en una hoja. El siguiente instrumento no traerá el primer inmueble real.

---

## 20. Madurez

| Dimensión | Nota | Justificación |
|---|---:|---|
| **Producto** | **2,5** | Prototipo avanzado con usuarios reales pero mínimos. Flujos completos; sin ajuste al mercado demostrado. |
| **Frontend** | **3,5** | Funcional y desplegado, PWA completa, buena degradación. Baja: `App.jsx` de 2.211 líneas, sin tipos, sin accesibilidad auditada. |
| **Backend** | **4,0** | Producto validable: 60 rutas vivas, arquitectura limpia en los motores, degradación explícita. Baja: dos archivos de 2.400 líneas y un endpoint de escritura sin autenticar. |
| **Datos** | **2,0** | Prototipo. **8.512 POIs reales (fuerte) vs 39 de 40 inmuebles falsos (fatal)**. Tres métricas sin fuente. Tubería rota. |
| **Geoespacial** | **4,0** | Lo mejor del proyecto: PostGIS, isócronas propias, tiempos reales por calles, y un hallazgo metodológico propio (el "centro vivido"). Baja: duplicados y ruido de categorías. |
| **IA** | **3,5** | Funcional y bien pensada: grafo de 3 nodos con el motor antes de la prosa, herramientas que calculan por el modelo, barandas en 4 capas. Baja: un error de procedencia y los guardianes en modo observación. |
| **Verificación** | **3,0** | Funcional para lo contable (servicios, transporte), inexistente para lo medible (ruido). Instrumentado con seriedad; incompleto en cobertura. |
| **UX** | **3,0** | Funcional. Buenas decisiones de confianza y de incertidumbre. Sin incorporación, sin accesibilidad, con la bandeja ilegible. |
| **Infraestructura** | **2,0** | Prototipo desplegado. Un entorno, sin integración continua, sin preproducción, migraciones a mano, DDL en caliente, tubería en un portátil. |
| **Seguridad** | **2,5** | Buenos cimientos (JWT/JWKS, CORS, limitación de tasa, cero secretos filtrados) con **un agujero crítico** de escritura sin autenticar. |
| **Escalabilidad** | **2,0** | Una instancia, 15 conexiones repartidas a mano, un incidente ya ocurrido, cron dentro de la aplicación asumiendo instancia única. |
| **Testing** | **3,0** | 771 en verde es real. Pero 0 pruebas extremo a extremo, 0 cobertura medida, 0 en integración continua. |
| **Observabilidad** | **1,0** | Concepto. `print()` y `logging`. Un incidente de 1h26m se descubrió *"por casualidad, mirando otra cosa"*. |
| **Modelo de negocio** | **1,5** | Entre concepto y prototipo. Arquitectura que soporta varios modelos; cero ingresos comprobables; el pagador definido en documentos pero no en datos. |

**Media ponderada ≈ 2,7 / 5 — prototipo avanzado con un backend cercano a producto validable y unos cimientos de datos y operación que no lo acompañan.**

---

## 21. Roadmap

El detalle con priorización por impacto × esfuerzo × riesgo está en **`CONTEXTO_AI_ROADMAP.md`**. Resumen:

- **30 días — VALIDAR.** Cerrar el agujero de escritura, reparar la tubería del foso, poner integración continua, y **conseguir 10 inmuebles reales de un corredor**. La pregunta a responder: *¿un corredor carga y cura sin que Carlos esté encima?*
- **60 días — CONSTRUIR.** Solo lo que los 30 días demuestren que hace falta: una fuente real de ruido (la vía del corredor midiendo en la visita), rótulo de "demostración" en el inventario sintético, activar los guardianes en modo bloqueo, y observabilidad mínima.
- **90 días — DEMOSTRAR.** Un caso completo y medible: N inmuebles reales → M conversaciones → K handoffs → 1 cierre atribuible. Con eso se puede hablar con un integrador o un inversor. Sin eso, no.

---

## 22. Potencial multiindustria

La pregunta correcta no es *"¿en qué otras industrias sirve el producto?"* sino **"¿qué pieza es transferible?"**. La respuesta: **la capa de entorno con procedencia + curación humana propagada**. El resto es específico del sector inmobiliario.

| Industria | Problema | Datos necesarios | Reutilización | Datos nuevos | Potencial |
|---|---|---|---|---|---|
| **Inmobiliario** | Asimetría de información sobre el entorno | Los actuales | 100% | — | **Actual** |
| **Turismo / hotelería** | *"¿Cómo es el barrio del hotel? ¿Se puede caminar de noche?"* | POIs + isócronas + ruido | **~85%** — es literalmente el mismo cálculo sobre otro tipo de inmueble | Estacionalidad, horarios | 🟢 **El más alto.** Y encaja con Whaber (travel-ops). |
| **Comercio minorista** | *"¿Dónde abro? ¿Cuánta gente pasa a pie?"* | POIs de competencia + isócronas + flujo peatonal | **~70%** — la isócrona es la unidad de análisis del comercio | Tránsito peatonal, gasto por zona | 🟢 Alto — y hay quien paga por informes de ubicación |
| **Urbanismo / gobierno** | *"¿Qué parroquias tienen desierto de servicios a 15 min a pie?"* | Los actuales | **~90% — ya está hecho.** El estudio de 40 parroquias es entregable | Datos censales | 🟢 Alto en credibilidad, bajo en ingresos (ciclo largo) |
| **Seguros** | Riesgo por micro-ubicación | POIs + isócronas + siniestralidad | ~40% | Siniestralidad geolocalizada (no la tienen) | 🟡 Medio |
| **Logística / movilidad** | Última milla, cobertura de reparto | Isócronas Valhalla | ~50% — pero necesita ciclista/vehículo, no peatonal | Tráfico en tiempo real | 🟡 Medio — mercado muy servido |
| **Banca** | Tasación asistida y riesgo de garantía | Ficha verificable + entorno | ~50% | Comparables de transacciones reales (no los tienen) | 🟡 Medio — ciclo de venta larguísimo |
| **Salud** | Accesibilidad a servicios de salud a pie | POIs de salud + isócronas | ~60% | Capacidad y tiempos de espera | 🟡 Medio |
| **Educación** | Zonificación escolar | POIs educativos + isócronas | ~60% | Cupos, resultados | 🟠 Bajo — y **Fair Housing lo hace delicado** |
| **Construcción / promoción** | Viabilidad de un solar | Entorno + normativa | ~45% | Normativa, catastro oficial (**no lo tienen**) | 🟡 Medio |
| **Energía / agricultura** | — | — | ~10% | Casi todo | 🔴 Bajo |
| **Entretenimiento** | Programación por zona | POIs de ocio | ~30% | Aforos, agendas | 🔴 Bajo |

**Conclusión:** los tres candidatos reales son **turismo/hotelería, comercio minorista y urbanismo**, y los tres reutilizan la misma pieza: *"qué hay alcanzable a pie desde aquí, medido y con procedencia"*. **Ninguno debería tocarse antes de validar el primero.**

---

## 23. Hospitalidad Urbana

La investigación de accesibilidad, legibilidad, identidad, experiencia y percepción urbana.

**Qué existe hoy en el código con esa forma:**
- **Accesibilidad** → caminabilidad, isócronas, tiempos reales a pie. `[VERIFICADO — implementado]`
- **Legibilidad** → el modo cápsula, la traducción de dato a vida cotidiana (*"el Metro a ~7 min: sales sin carro"*), el "recorrido con aura". `[VERIFICADO — implementado]`
- **Identidad** → la función `_aura()`. `[HARDCODEADO — 6 frases]`
- **Percepción / experiencia** → **no existe.** No hay ninguna medición de cómo se *siente* un lugar.
- **Contexto urbano** → el estudio de 40 parroquias. `[VERIFICADO — pero fuera del producto]`

**Veredicto: (B) debe ser una funcionalidad de Contexto — y (C) una línea de investigación que la alimente. NO un producto independiente.**

Por qué:
1. **No como producto independiente (A):** no tiene quién pague. Los compradores de "hospitalidad urbana" son ayuntamientos y academia — ciclos de venta de años y presupuestos que no sostienen una empresa joven. Y desviaría al único equipo que hay.
2. **Sí como funcionalidad (B):** es exactamente la diferencia con un portal. Un portal dice *"3 dormitorios, 85 m²"*. La hospitalidad urbana dice *"puedes resolver la vida a pie, pero el Metro te queda a 20 minutos"*. **El sistema ya hace esto** — el prompt lo llama *"del dato al deseo"* y lo tiene reglado. La funcionalidad ya está; lo que falta es la palabra que la nombra.
3. **Sí como investigación (C):** el estudio de las 40 parroquias y el hallazgo del "centro vivido" son investigación de hospitalidad urbana de calidad publicable. **Es el mejor motor de credibilidad y de contenido que tiene el proyecto**, y cuesta poco porque los datos ya están.
4. **La advertencia:** "legibilidad" e "identidad" son juicios cualitativos. El proyecto tiene una doctrina explícita —*atribución, no juicio*— que prohíbe al sistema dictaminar el carácter de un barrio. **Cualquier avance por aquí debe respetar esa línea**, o se rompe el activo más valioso (la neutralidad) por una funcionalidad bonita. `_aura()` ya camina por el filo: *"un remanso residencial, verde y tranquilo"* es un juicio del sistema sobre un barrio.

**Lo que sí haría:** medir "hospitalidad" solo con lo contable (equipamiento alcanzable a pie, diversidad de categorías, continuidad de la red peatonal) y **dejar que la persona ponga el adjetivo**. Es la misma disciplina de la atribución, aplicada a una nueva dimensión.

---

## 24. Agentes de IA

> ¿Puede Contexto convertirse en una herramienta que agentes externos consulten?

### Lo que YA existe para soportarlo `[VERIFICADO]`

| Pieza | Estado |
|---|---|
| **Lógica pura separada de la interfaz** | ✅ `inversion.py`, `encaje.py`, `intencion.py`, `estilo_vida.py`, `walk_score.py` — sin red, sin base, determinista |
| **Endpoints REST que devuelven la misma verdad que el agente** | ✅ `GET /assets/{id}/investment`, `/anuncio`, `/aura`, `/rutas`, `/geojson`, `POST /mapa/comando` |
| **Esquema OpenAPI publicado** | ✅ 60 rutas, vivo y accesible |
| **Autenticación por llave de API** | ✅ Cabecera `X-API-Key`, en 20+ endpoints |
| **Limitación de tasa por cliente** | ✅ 53 endpoints |
| **Respuestas estructuradas con procedencia** | ✅ `scores_fuente`, `encaje_razones[].fuente`, `entorno_verificado.fecha` |
| **Herramientas ya escritas como herramientas** | ✅ 9 herramientas con esquema y descripción — **son, literalmente, las herramientas de un servidor MCP** |

**Esto es más de lo que parece.** El paso de "agente propio" a "herramienta que otros agentes consultan" es corto: las 9 herramientas ya tienen firma, descripción en inglés y salida JSON. Envolverlas en un servidor MCP es trabajo de días, no de meses. Y encaja exactamente con el `whaber-oracle-mcp` del ecosistema Whaber.

### Lo que FALTARÍA

| Falta | Esfuerzo | Por qué importa |
|---|---|---|
| **Servidor MCP** que exponga las herramientas | Bajo (días) | Es el envoltorio, no el motor |
| **Identidad por organización** (OAuth o llaves por cliente) | Medio | Hoy hay **una** `API_KEY` global. No se puede facturar ni limitar por cliente. |
| **Respuestas con evidencia citable y estable** | Medio | Un agente externo necesita `poi_id`, `fecha`, `confianza` y una URL permanente. Hoy la evidencia viene como texto con emojis (*"💊 Vanttive a ~303 m"*) — legible para humanos, frágil para máquinas. |
| **Contrato de "no sé"** | Bajo | El sistema ya sabe decirlo en prosa; falta un campo estructurado (`cobertura: "sin datos"` existe pero no está normalizado en todas las respuestas). |
| **Cobertura** | **Alto** | Un agente externo preguntará por Bogotá, Ciudad de México o Lima. Hoy la respuesta honesta es *"solo Quito"*. **Esta es la barrera real, y es de datos, no de código.** |
| **Medición y facturación** | Medio | Sin esto no hay modelo de negocio de API. |

### Veredicto

**Técnicamente, Contexto está a semanas de ser consultable por agentes externos. Comercialmente, está a una ciudad y media de tener algo que valga la pena consultar.**

El cuello de botella **no es la interfaz — es la cobertura geográfica de la capa propia.** Un agente que pregunta *"¿zona adecuada para X?"* y recibe *"solo cubrimos Quito"* no vuelve.

**La contradicción estratégica que hay que resolver:** el `ESTRATEGIA_API_First.md` dice *"deja que el primer integrador hale la API a existir"*. Es una regla sabia para una API B2B con contrato. **Pero para una API que consumen agentes, no hay integrador que la hale: o está y la descubren, o no existe.** Son dos jugadas distintas y el proyecto tiene una sola doctrina para ambas.

---

## 25. Hipótesis estratégica

> **¿Podría Contexto evolucionar de "IA inmobiliaria que verifica el entorno" a "infraestructura de contexto para que la IA comprenda el mundo físico"?**

### La hipótesis, en una frase honesta

Los modelos de lenguaje saben describir un lugar y **no saben verificarlo**. Pueden decirte cómo es Cumbayá en general; no pueden decirte si la farmacia de la esquina sigue abierta. Contexto está construyendo justo esa capa: **el dato de entorno fresco, con procedencia, con fecha, y con una persona que estuvo ahí.**

### Qué tendría que ser VERDAD para que funcione

| Condición | Estado hoy | Distancia |
|---|---|---|
| **1. Que el dato fresco de terreno sea escaso y valioso** | ✅ **Cierto**, y estructuralmente: Google prohíbe almacenar, Overture se actualiza mensualmente, OSM es desigual en LATAM | **Ya es verdad** |
| **2. Que exista un mecanismo barato de captura de frescura** | 🟡 **Construido, no validado.** La curación propagada es elegante — 4 usos. | **La apuesta entera está aquí** |
| **3. Que alguien pague por consultarla** | 🔴 **Sin evidencia.** Cero ingresos comprobables. | Lejos |
| **4. Que la cobertura llegue a masa crítica** | 🔴 Una ciudad, 8.512 POIs, tubería rota | Lejos |
| **5. Que el dato sea confiable** | 🟡 Confianza de Overture 0,767; 531 duplicados; nombres sucios | Media |
| **6. Que se pueda entregar a máquinas, no solo a humanos** | 🟡 REST sí; evidencia como texto con emojis, no estructurada | Cerca |

### Qué tendría que construirse
1. **Un motor de frescura**: por qué un POI necesita re-verificación, quién lo verifica, cuánto cuesta. Hoy la curación es voluntaria y gratuita — eso no escala.
2. **Cobertura multi-ciudad de verdad** (la migración 019 lo preparó; nadie cargó una segunda).
3. **Evidencia estructurada y citable** (identificador, fecha, confianza, foto — no una cadena con emojis).
4. **Identidad, medición y facturación por organización.**

### Qué tendría que demostrarse
**Una sola cosa, y es medible:** que la capa propia de Contexto responde una pregunta de entorno **mejor que Google Places**, de forma reproducible y en un lugar concreto. El proyecto ya tiene el instrumento (`foso_pois_spike.py` compara lado a lado). **No encontré el resultado publicado.** Ese es el experimento más barato y de mayor valor que puede correr.

### Qué sería difícil de copiar
- ✅ **La verdad de terreno con foto, coordenada y fecha.** Requiere haber estado ahí. Un scraper no puede.
- ✅ **La propagación por barrio.** Una verificación mejora todos los inmuebles del sector — el rendimiento compuesto que un competidor no puede alcanzar comprando datos.
- ✅ **La doctrina de honestidad instrumentada.** No es el código, es el juicio destilado: 568 líneas de prompt, 4 capas de barandas, un verificador de prosa. Copiar el código es fácil; llegar a saber *por qué* cada regla está ahí toma meses de fallos.
- ❌ **Los POIs de Overture/OSM.** Son públicos. Cualquiera los baja. **No son foso** — son el suelo.
- ❌ **La caminabilidad.** Metodología pública, reimplementable en un día.

### Qué podría matarla

| Amenaza | Probabilidad | Impacto |
|---|---|---|
| **Que el corredor no contribuya.** Toda la tesis descansa en que una persona ocupada dedique tiempo gratis a curar datos. | **Alta** — evidencia: 4 actos en 2 meses | **Fatal** |
| **Que Google/Overture cierren la brecha.** Si Overture mejora la frescura en LATAM, el foso se evapora. | Media | Alto |
| **Que el mercado no valore la verificación.** Que la gente prefiera más inventario a más verdad. | Media | Alto |
| **Agotamiento del fundador.** 784 commits en 11 semanas, un solo desarrollador, cinco cerebros de conocimiento, tres pilotos y una tubería que corre en su portátil. | **Alta** | **Fatal** |
| **Un competidor con distribución.** Hiinmo (auditado por el propio equipo) tiene una "IA" peor y 28 agentes de una asociación. **La distribución le gana a la tecnología en un mercado sin educar.** | Alta | Alto |

### Mi lectura, sin adornos

**La hipótesis grande es coherente y la pieza correcta ya está construida.** No es marketing: la capa de POIs propia con curación propagada *es* infraestructura de contexto físico, en pequeño.

**Pero el orden importa y hoy está invertido.** El proyecto está construyendo la infraestructura antes de demostrar que el mecanismo de captura funciona. Y el mecanismo de captura —el corredor contribuyendo— tiene **una observación a favor y dos meses de silencio en contra**.

**La pregunta que decide el futuro de Contexto no es técnica.** Es: *¿por qué un corredor ocupado dedicaría veinte minutos a curar el entorno de un inmueble?* Hoy la respuesta del producto es *"porque el dato queda para siempre y mejora todo el barrio"*. Es una respuesta de fundador, no de corredor. **La respuesta que funcionaría es: "porque el lead que llega ya sabe lo que quiere y cierra más rápido".** Y eso todavía no se ha demostrado ni una vez.

---

## 26. Conclusiones

### 1. ¿Qué es Contexto AI hoy?
Un producto desplegado y funcionando: API sana con 60 rutas, aplicación web en dominio propio, base PostGIS con 8.512 puntos de interés propios, agente conversacional con memoria persistente y 771 pruebas en verde. **Y simultáneamente un piloto con 1 inmueble real, 2 corredores, 9 conversaciones en agosto y 10 handoffs en toda su historia.**

### 2. ¿Qué se ha construido realmente?
Una **plataforma de verificación de entorno** con un motor determinista de encaje, un agente con barandas en cuatro capas, una capa propia de datos geoespaciales, isócronas peatonales propias, un bucle de curación humana que propaga por barrio, un CRM con su propio agente, y un cuerpo documental de ~180 documentos que explican el porqué de cada decisión. En 11 semanas.

### 3. ¿Qué funciona?
La API, la web, la memoria del agente, la capa propia de POIs sirviendo el entorno real, la conectividad con tiempo real a pie, el handoff con avisos, el generador de QR y letreros, el motor de encaje, la ficha pública, y la curación (4 veces). **Todo verificado contra producción.**

### 4. ¿Qué no funciona?
La tubería de refresco del foso (rota desde el 08-18). El bucle del corredor (construido, desierto). La cola de revisión (1 pendiente, 0 correcciones). La procedencia de la caminabilidad (afirma OpenStreetMap para valores sin procedencia). Los guardianes de honestidad (registran, no bloquean, y nadie lee la tasa). Los títulos de conversación (122 de 148 genéricos). Y **el endpoint de alta de inmuebles está abierto a internet**.

### 5. ¿Cuál es el activo más importante?
**La capa propia de POIs con procedencia + el mecanismo de curación propagada por barrio.** Es lo único que Google contractualmente no permite tener, lo único que exige haber estado en el territorio, y lo único con rendimiento compuesto. Todo lo demás —el agente, el CRM, las tarjetas— es reconstruible en semanas por cualquier equipo competente.

*(Con una mención: el prompt de 568 líneas y las ~180 notas de decisión son el segundo activo, y el más subestimado.)*

### 6. ¿Cuál es la mayor debilidad?
**No hay evidencia de que alguien fuera del círculo del fundador quiera esto.** 9 conversaciones en agosto, 10 dispositivos distintos, 1 inmueble real, 0 ingresos. Todo lo construido desde julio sirve a un volumen que cabe en una hoja. La debilidad no es técnica: es que la capacidad se adelantó tres meses a la demanda.

### 7. ¿Cuál es la hipótesis tecnológica?
Que **el dato de entorno fresco, con procedencia y verificado por una persona en el terreno, es escaso, valioso y acumulable** — y que quien lo posea tendrá algo que ni Google (que prohíbe almacenarlo) ni un scraper (que no puede estar ahí) pueden replicar. **La hipótesis es sólida y la pieza está construida.**

### 8. ¿Cuál es la hipótesis de negocio?
Que un corredor o inmobiliaria pagará por recibir **leads calificados sobre verdad verificada** en vez de "alguien preguntó", y que contribuirá esa verdad como parte del trato. **Esta hipótesis tiene una observación a favor (4 curaciones, un día de junio) y dos meses de silencio en contra. Es el mayor riesgo abierto del proyecto.**

### 9. ¿Cuál es la oportunidad?
A corto plazo, ser la capa de verificación de entorno del mercado inmobiliario de Quito y demostrarlo con un caso completo. A medio plazo, **turismo/hotelería** — la reutilización es del ~85% y encaja con el resto del ecosistema Whaber. A largo plazo, infraestructura de contexto físico consultable por agentes de IA — técnicamente a semanas, comercialmente a una cobertura geográfica de distancia.

### 10. ¿Cuál es el principal riesgo?
**Seguir construyendo.** El proyecto tiene un fundador solo, 784 commits en 11 semanas, cinco cerebros de conocimiento, tres pilotos abiertos, una tubería crítica corriendo en su portátil, y una relación capacidad/uso cada vez más extrema. El riesgo no es que el producto falle técnicamente — es que se agote quien lo construye antes de que aparezca quien lo use.

### 11. ¿Qué hacer inmediatamente después?

En este orden, y sin funcionalidades nuevas:

1. **Cerrar `POST /api/v1/assets/`** — una línea de dependencia. Hoy.
2. **Reparar la tubería del foso** — parametrizar el lanzamiento de Overture en vez de fijarlo. Esta semana.
3. **Corregir la procedencia de la caminabilidad** en `encaje.py` — es el foso declarado contradiciéndose a sí mismo. Esta semana.
4. **Poner integración continua** — las 771 pruebas ya existen; solo hay que conectarlas al despliegue. Esta semana.
5. **Ir a por 10 inmuebles reales de UN corredor**, con Carlos midiendo cuánto le cuesta a esa persona, no cuánto le cuesta a Carlos. **Esta es la única que importa de verdad.** Las cuatro anteriores son higiene; esta es la validación.

---

*Auditoría realizada el 2026-08-19 sin modificar un solo archivo del proyecto. Todas las consultas a la base fueron `SELECT`. Todas las sondas a producción fueron `GET`, salvo dos `POST` con cuerpo inválido para medir la puerta de autenticación sin escribir datos.*
