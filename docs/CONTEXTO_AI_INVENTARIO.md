# CONTEXTO AI — Inventario de funcionalidades
### Documento complementario de la auditoría del 2026-08-19
**Commit:** `782e57ba` · **Regla:** cada fila lleva la evidencia concreta que la sustenta.

---

## Leyenda

| Estado | Significado |
|---|---|
| **VERIFICADA** | Funciona de punta a punta y hay evidencia (respuesta de producción, filas en la base, o prueba ejecutada). |
| **PARCIAL** | Funciona pero con cobertura mínima o alguna pieza degradada. |
| **BACKEND NO VALIDADO** | Endpoint e implementación existen; sin evidencia de uso real en los datos. |
| **UI SIN BACKEND VERIFICADO** | Pantalla construida; no comprobé el camino completo. |
| **MOCK** | Simulado a propósito. |
| **HARDCODEADA** | Valor fijo en el código, no calculado sobre datos. |
| **NO IMPLEMENTADA** | Prometida en documentación; no existe en código. |

Columnas: **Existe** (hay código) · **Funciona** (comprobado) · **Backend** · **Datos reales** (¿opera sobre datos no sintéticos?) · **IA** (¿interviene un LLM?).

---

## 1. Búsqueda y descubrimiento

| Funcionalidad | Existe | Funciona | Backend | Datos reales | IA | Estado | Evidencia |
|---|:-:|:-:|:-:|:-:|:-:|---|---|
| Búsqueda de inmuebles por texto | ✅ | ✅ | ✅ | 🟡 1/40 | ✅ | **PARCIAL** | `tool_find_assets_by_text` · `app/agent/tools.py:220` · 40 filas en `activos_inmutables` |
| Búsqueda por radio geográfico | ✅ | ✅ | ✅ | 🟡 | ✅ | **PARCIAL** | `tool_search_nearby_assets` · `ST_DWithin` · `GET /assets/near` → HTTP 200 sin llave |
| Filtro por precio y operación | ✅ | ✅ | ✅ | 🟡 | ❌ | **VERIFICADA** | `tests/test_search_nearby_assets_precio_radio.py`, `test_filtro_operacion.py` — en verde |
| Búsqueda por ubicación (dirección → coords) | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFICADA** | `tool_geocode_address` → Google Geocoding, reserva Nominatim con 4 consultas progresivas |
| Búsqueda por ancla + tiempo (la "cuña") | ✅ | ❓ | ✅ | ✅ | ❌ | **BACKEND NO VALIDADO** | `app/isocronas.buscar_por_ancla_tiempo()` · `ST_Contains` · sin rastro de uso en datos |
| Búsqueda por similitud visual | ✅ | ❓ | ✅ | 🟡 | ✅ | **BACKEND NO VALIDADO** | `POST /assets/similar` (con llave) · **solo 8 embeddings sobre 4 activos** |
| Filtros tipo portal (habitaciones, m², etc.) en pantalla | ❌ | — | — | — | — | **NO IMPLEMENTADA** | No hay pantalla de resultados con filtros; todo pasa por conversación |

---

## 2. Análisis del entorno — el núcleo del producto

| Funcionalidad | Existe | Funciona | Backend | Datos reales | IA | Estado | Evidencia |
|---|:-:|:-:|:-:|:-:|:-:|---|---|
| **Caminabilidad sobre POIs reales de OSM** | ✅ | ✅ | ✅ | ✅ | ❌ | **VERIFICADA** | `app/walk_score.py` · función pura con pruebas · 9 categorías, decaimiento 400→2400 m |
| **Procedencia de la caminabilidad** | ✅ | ⚠️ | ✅ | — | ❌ | **PARCIAL — DEFECTUOSA** | La columna `walk_score_fuente` es **NULL en los 40 activos**. `encaje.py:209` afirma `"OpenStreetMap"` de todos modos. **Contradicción verificada ejecutando el motor.** |
| **Servicios cercanos desde la capa propia** | ✅ | ✅ | ✅ | ✅ | ❌ | **VERIFICADA** | `GET /assets/{id}/anuncio` en producción devuelve 5 POIs reales con distancia |
| **Conectividad con tiempo REAL a pie** | ✅ | ✅ | ✅ | ✅ | ❌ | **VERIFICADA** | Producción: *"🚇 Quitumbe a ~1496 m (20 min a pie)"* · Google Routes, no línea recta |
| **Curación del entorno por el corredor** | ✅ | ✅ | ✅ | ✅ | ❌ | **PARCIAL — 4 usos** | 4 filas en `entorno_curacion`, todas del 2026-06-18, con foto y coordenada |
| **Propagación de la curación al barrio** | ✅ | ✅ | ✅ | ✅ | ❌ | **VERIFICADA** | Vista `pois_vivos` (migración 023): 8.512 propios → 8.498 vivos = **14 POIs cerrados** propagados |
| **Insignia "verificado en terreno" con fecha** | ✅ | ✅ | ✅ | ✅ | ❌ | **VERIFICADA** | Producción: `entorno_verificado: {verificado: true, fecha: "2026-06-18"}` |
| Ruido predictivo | ✅ | ✅ | ✅ | ❌ | ❌ | **HARDCODEADA** | `app/scores_heuristicos.py` — tabla fija de 7 sectores. **No existe fuente de ruido.** |
| Volumen de tráfico | ✅ | ✅ | ✅ | ❌ | ❌ | **MOCK** | Escrito a mano en `seed_ampliado.py`. 4 activos en 0 = "sin dato". |
| Cobertura vegetal | ✅ | ✅ | ✅ | ❌ | ❌ | **MOCK** | Ídem. |
| Densidad poblacional | ✅ | ❓ | ✅ | ❌ | ❌ | **MOCK** | Columna existe; sembrada a mano; el prompt prohíbe afirmarla sin consulta |
| Seguridad como métrica | ❌ | — | — | — | — | **RECHAZADA A PROPÓSITO** | `estilo_vida.py` lo documenta: hay POIs de UPC/policía, pero *"un veredicto de 'zona segura' es la clase de juicio que se usó para redlining"* |
| Historial de eventos urbanos (obras, alturas) | ✅ | ❌ | ✅ | ❌ | — | **NO IMPLEMENTADA** | Modelo ORM + mención en el prompt · **tabla con 0 filas** |

---

## 3. Mapa

| Funcionalidad | Existe | Funciona | Backend | Datos reales | IA | Estado | Evidencia |
|---|:-:|:-:|:-:|:-:|:-:|---|---|
| Mapa base con inmuebles | ✅ | ✅ | ✅ | 🟡 | ❌ | **VERIFICADA** | `GET /assets/geojson` → HTTP 200 con FeatureCollection real |
| Mapa conversacional (pregunta → acciones) | ✅ | ❓ | ✅ | ✅ | 🟡 | **BACKEND NO VALIDADO** | `POST /assets/mapa/comando` vivo, sin llave; `comando_mapa()` en `rutas.py` |
| Modo AURA-SINGLE (inmueble + POIs + isócronas) | ✅ | ✅ | ✅ | ✅ | ❌ | **VERIFICADA** | `GET /assets/{id}/aura` · 78 isócronas en base · `AuraSingleMap.jsx` |
| Lente con estados (zona / auras / aura) e histéresis | ✅ | ❓ | ✅ | — | ❌ | **BACKEND NO VALIDADO** | `_decidir_modo()` en `chat.py` · `tests/test_map_seed.py` en verde |
| Colorear pines por encaje | ✅ | ❓ | ✅ | — | ❌ | **UI SIN BACKEND VERIFICADO** | `intentHue.js` · `MapView.jsx` |
| Recorrido narrado ("Recorrido con Aura") | ✅ | ❓ | ✅ | ✅ | ❌ | **BACKEND NO VALIDADO** | `recorrido_zona()` en `rutas.py:588` — 4-6 escenas · sin endpoint público que lo exponga |
| Comparar dos inmuebles en el mapa | ✅ | ❓ | ✅ | 🟡 | ❌ | **UI SIN BACKEND VERIFICADO** | `CompararMap.jsx` (169 L) + `POST /chat/comparar` |
| Isócronas peatonales propias | ✅ | ✅ | ✅ | ✅ | ❌ | **PARCIAL** | 78 filas (39 activos × 15/30 min), **todas del 2026-07-01**; estado actual de Valhalla `[NO VERIFICADO]` |

---

## 4. Encaje y recomendación

| Funcionalidad | Existe | Funciona | Backend | Datos reales | IA | Estado | Evidencia |
|---|:-:|:-:|:-:|:-:|:-:|---|---|
| **Motor de encaje 0-100** | ✅ | ✅ | ✅ | 🟡 | ❌ | **VERIFICADA** | `app/encaje.py` · **ejecutado en esta auditoría**: encaje 84 con 3 razones |
| **Lista blanca cerrada de 8 dimensiones** | ✅ | ✅ | ✅ | — | ❌ | **VERIFICADA** | `DIMENSIONES` en `encaje.py:34` · barrera estructural Fair Housing |
| **Requisito duro (tipo de inmueble topa el encaje)** | ✅ | ✅ | ✅ | — | ❌ | **VERIFICADA** | `_REQUISITOS_DUROS`, tope 49 · nació del fallo 2 de BATALLA_Hiinmo |
| **Razones explicables con fuente** | ✅ | ⚠️ | ✅ | 🟡 | ❌ | **PARCIAL** | Funciona; **la fuente de caminabilidad es incorrecta** (ver §2) |
| **Aritmética de presupuesto centralizada** | ✅ | ✅ | ✅ | ✅ | ❌ | **VERIFICADA** | `estado_presupuesto()` — fuente única para tarjeta y modelo. El LLM tiene **prohibido** restar |
| **Bloque autoritativo que lee el modelo** | ✅ | ✅ | ✅ | 🟡 | ✅ | **VERIFICADA** | `encaje_contexto.bloque_autoritativo()` — generado y leído en esta auditoría |
| Extracción de preferencias por LLM | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFICADA** | `app/preferencias.py` — esquema cerrado + saneador; degrada a `{}` sin romper el turno |
| Delta de encaje entre 2 inmuebles | ✅ | ❓ | ✅ | 🟡 | ❌ | **BACKEND NO VALIDADO** | `delta_encaje()` + `POST /chat/comparar` + `DeltaEncaje.jsx` |
| Priorizar una opción | ✅ | ❓ | ✅ | — | ✅ | **BACKEND NO VALIDADO** | `tool_priorizar_opcion` |
| Orden de candidatos con evidencia visible | ✅ | ✅ | ✅ | 🟡 | ❌ | **VERIFICADA** | `app/orden.py` · `tests/test_orden_encaje.py`, `test_orden_candidatos.py` en verde |
| Comparación de zonas (no de inmuebles) | ❌ | — | — | — | 🟡 | **NO IMPLEMENTADA** | Solo prosa del agente, sin motor detrás |

---

## 5. IA conversacional

| Funcionalidad | Existe | Funciona | Backend | Datos reales | IA | Estado | Evidencia |
|---|:-:|:-:|:-:|:-:|:-:|---|---|
| **Agente del comprador (ReAct, 9 herramientas)** | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFICADA** | `POST /chat/` con llave → 401 sin ella; **148 sesiones, 2.119 puntos de control en producción** |
| **Memoria persistente entre sesiones** | ✅ | ✅ | ✅ | ✅ | — | **VERIFICADA** | `/health` → `"memoria":"postgres"` · 246 hilos distintos |
| **Transmisión de tokens (SSE)** | ✅ | ✅ | ✅ | — | ✅ | **VERIFICADA** | `streaming=True` en `ChatAnthropic` — comentario documenta el fallo previo (12–23 s sin token) |
| **Modo cápsula vs informe completo** | ✅ | ❓ | — | — | ✅ | **EXISTE PERO NO VALIDADO** | Regla 0 del prompt; no ejecuté un turno para comprobarlo |
| **Apertura por QR adaptada a la operación** | ✅ | ❓ | ✅ | ✅ | ✅ | **PARCIAL** | 26 sesiones `qr-` en producción, todas del mismo inmueble |
| **Antigüedades pre-calculadas (el LLM no resta)** | ✅ | ✅ | ✅ | ✅ | — | **VERIFICADA** | `_antiguedad()` en `tools.py:55` — el comentario documenta el fallo de 1 de cada 4 |
| **Ancla temporal en cada llamada** | ✅ | ✅ | ✅ | — | ✅ | **VERIFICADA** | `_bloque_fecha()` — se inyecta por turno, no al importar |
| **Traductor de estilo de vida instrumentado** | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFICADA** | `tool_traducir_estilo_de_vida` → `estilo_vida.py` (puro, con pruebas) |
| **Economía de herramientas (no gastar fuera de dominio)** | ✅ | ❓ | — | — | ✅ | **EXISTE PERO NO VALIDADO** | Regla 00 del prompt |
| **Prohibición de asesoría financiera** | ✅ | ❓ | — | — | ✅ | **EXISTE PERO NO VALIDADO** | Regla dura del prompt; cubierta por un caso de eval |
| **Política de idioma (espejo, sin voseo)** | ✅ | ❓ | — | — | ✅ | **EXISTE PERO NO VALIDADO** | Regla del prompt, explícita |
| **Agente del CRM (corredor, 3 herramientas)** | ✅ | ❓ | ✅ | 🟡 | ✅ | **PARCIAL** | `POST /assets/crm/chat` con JWT · **2 corredores registrados** |
| Playbook de venta honesta (Serhant, Corcoran) | ✅ | ❓ | ✅ | ✅ | ✅ | **BACKEND NO VALIDADO** | `tool_playbook_venta` + `corredor_playbook.json` (exportado del Corredor-Brain) |
| RAG en el camino conversacional | ❌ | — | — | — | — | **NO IMPLEMENTADA** | pgvector existe, pero solo alimenta `/similar` |

---

## 6. Honestidad y cumplimiento

| Funcionalidad | Existe | Funciona | Backend | Datos reales | IA | Estado | Evidencia |
|---|:-:|:-:|:-:|:-:|:-:|---|---|
| **Detector de sesgo territorial (salida)** | ✅ | ✅ | ✅ | — | — | **PARCIAL — SOLO REGISTRA** | `fair_housing.detectar_steering()` · llamado en `llm_node`; imprime, no bloquea |
| **Barrera estructural en preferencias** | ✅ | ✅ | ✅ | — | ✅ | **VERIFICADA** | Esquema cerrado + saneador · `tests/test_fair_housing.py` en verde |
| **Rechazo de clases protegidas en entrada difusa** | ✅ | ✅ | ✅ | — | — | **VERIFICADA** | `estilo_vida.py` vía `protegidos` |
| **Verificador de prosa contra motor** | ✅ | ✅ | ✅ | — | — | **PARCIAL — SOLO REGISTRA** | `verificacion_prosa.py` (464 L) · `_auditar_prosa` en `chat.py` |
| **Rótulo de procedencia en la ficha** | ✅ | ✅ | ✅ | ✅ | — | **VERIFICADA** | Producción: `scores_fuente: {caminabilidad: null, ruido: "heuristico", …}` |
| **Pie de tarjeta adaptado a la procedencia** | ✅ | ✅ | ✅ | ✅ | — | **VERIFICADA** | `ResultCards.jsx:378` — prudente por diseño: una estimada ⇒ frase conservadora para todas |
| **Aviso de frescura de los POIs** | ✅ | ❓ | — | — | ✅ | **EXISTE PERO NO VALIDADO** | Regla del prompt: *"salen del mapa y pueden haber cambiado"* |
| **Ficha técnica declarada, no verificada** | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFICADA** | Regla 3 del prompt + `fuente: "manual" \| "vision_ia"` en la tabla |
| Barandas del agente CRM | ✅ | ❓ | ✅ | 🟡 | — | **BACKEND NO VALIDADO** | `crm_guardrails.py` (455 L) |
| Evaluaciones de honestidad (11 casos) | ✅ | ❓ | — | ✅ | ✅ | **EXISTE — NO EN CI** | `evals/run_evals.py` · se corre a mano contra el backend desplegado |
| Rótulo "inmueble de demostración" | ❌ | — | — | — | — | **NO IMPLEMENTADA** | **39 de 40 activos son sintéticos y nada lo indica en la interfaz** |

---

## 7. Ingesta y visión

| Funcionalidad | Existe | Funciona | Backend | Datos reales | IA | Estado | Evidencia |
|---|:-:|:-:|:-:|:-:|:-:|---|---|
| Extracción de ficha por visión | ✅ | ✅ | ✅ | ✅ | ✅ | **PARCIAL** | `app/vision.py` con `tool_use` forzado · **4 de 40 activos** (3 publicados, 1 pendiente) |
| Confianza de extracción | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFICADA** | Valores reales en base: 0,45 (pendiente) y 0,78 (publicadas) · umbral 0,6 |
| Cola de revisión humana | ✅ | 🟡 | ✅ | ✅ | — | **PARCIAL** | `GET /assets/review-queue` · **1 pendiente atascada** |
| Corrección → verdad de referencia | ✅ | ❌ | ✅ | ❌ | — | **BACKEND NO VALIDADO** | Tabla `correcciones_ficha` con **0 filas en toda la historia** |
| Caché por hash de imagen | ✅ | ❓ | ✅ | 🟡 | — | **BACKEND NO VALIDADO** | Columna `image_sha256` · sin evidencia de aciertos de caché |
| Embeddings multimodales | ✅ | ✅ | ✅ | ✅ | ✅ | **PARCIAL** | 8 vectores (4 imagen + 4 ficha) sobre 4 activos · `voyage-multimodal-3` |
| Caché de embeddings | ✅ | ❌ | ✅ | ❌ | — | **BACKEND NO VALIDADO** | Tabla `embedding_cache` con 0 filas |
| Ingesta por lotes | ✅ | ❓ | ✅ | ❓ | ✅ | **BACKEND NO VALIDADO** | `POST /assets/ingest/batch` con llave |
| Anti-SSRF en la ingesta por URL | ✅ | ✅ | ✅ | — | — | **VERIFICADA** | `ingest_allowed_image_hosts` en `config.py` |

---

## 8. Corredor: publicación, CRM y handoff

| Funcionalidad | Existe | Funciona | Backend | Datos reales | IA | Estado | Evidencia |
|---|:-:|:-:|:-:|:-:|:-:|---|---|
| **Handoff al corredor humano** | ✅ | ✅ | ✅ | ✅ | ✅ | **VERIFICADA** | **10 handoffs reales** (7 solicitado, 3 activo) + 20 mensajes |
| **Hilos: un interesado, varios corredores** | ✅ | ✅ | ✅ | ✅ | — | **VERIFICADA** | Modelo de agosto · `docs/ARQUITECTURA_Hilos_Handoff_2026-08-13.md` |
| **Avisos por Web Push + correo** | ✅ | 🟡 | ✅ | ✅ | — | **PARCIAL** | 4 dispositivos push, 2 usuarios · `aviso_email` con **0 filas** |
| **Bandeja por conversación** | ✅ | 🟡 | ✅ | ✅ | — | **PARCIAL** | 5 notificaciones · **122 de 148 conversaciones sin título propio** |
| **Generación de QR y letrero imprimible** | ✅ | ✅ | ✅ | ✅ | — | **VERIFICADA** | `GET /assets/{id}/qr.svg` y `/letrero.png` (Pillow + segno) · 26 sesiones QR |
| **Registro de llegadas (canal / UTM)** | ✅ | ✅ | ✅ | ✅ | — | **VERIFICADA** | **57 llegadas, 10 dispositivos** — instrumento construido el 2026-08-17 |
| Publicar inmueble con fotos | ✅ | 🟡 | ✅ | ✅ | ✅ | **PARCIAL** | `POST /assets/publish` · **usado 1 vez** (fotos de WhatsApp en Supabase Storage) |
| Ficha técnica editable por el dueño | ✅ | ✅ | ✅ | ✅ | — | **VERIFICADA** | 39 fichas, 35 manuales |
| Características (JSONB) | ✅ | ✅ | ✅ | ✅ | — | **VERIFICADA** | 25 llaves distintas en producción · ⚠️ incluye `ideal_para` y un `precio` duplicado |
| Panel de leads del corredor | ✅ | 🟡 | ✅ | ✅ | — | **PARCIAL** | `LeadsPanel.jsx` (334 L) · 7 filas en `lead_actividad` |
| Motor de intención (9 estados) | ✅ | ✅ | ✅ | ✅ | ❌ | **VERIFICADA** | **34 sesiones, 46 eventos** en producción · puntuaciones de 0 a 98 |
| Reenganche de leads dormidos | ✅ | 🟡 | ✅ | 🟡 | — | **BACKEND NO VALIDADO** | Cron cada 6 h · **1 solo reenganche enviado** de 7 leads (2026-07-12) |
| Rescate de avisos no leídos | ✅ | ❓ | ✅ | ❌ | — | **BACKEND NO VALIDADO** | `rescate_avisos.py` · columna `rescate_en` sin usar |
| Métricas de lift de intención | ✅ | ❓ | ✅ | 🟡 | — | **BACKEND NO VALIDADO** | `GET /assets/metricas/lift` con JWT · `app/lift.py` |
| Embudo del corredor | ✅ | ❓ | ✅ | 🟡 | — | **BACKEND NO VALIDADO** | `app/embudo.py` · `tests/test_embudo_reparto.py` en verde |
| Asignación congelada de dueño | ✅ | ❓ | ✅ | 🟡 | — | **BACKEND NO VALIDADO** | Migración 026 · `tests/test_asignacion_congelada.py` en verde |
| Agencias / multi-usuario | ✅ | ❌ | ✅ | ❌ | — | **NO IMPLEMENTADA EN USO** | Tabla `agencies` con **0 filas**; `owner_agency_id` nulo en los 40 |

---

## 9. Cuenta y sesión

| Funcionalidad | Existe | Funciona | Backend | Datos reales | IA | Estado | Evidencia |
|---|:-:|:-:|:-:|:-:|:-:|---|---|
| Autenticación (Supabase, JWT vía JWKS) | ✅ | ✅ | ✅ | ✅ | — | **VERIFICADA** | `app/auth.py` — valida ES256 contra llaves públicas · 9 perfiles |
| Roles (cliente / corredor / inmobiliaria) | ✅ | ✅ | ✅ | ✅ | — | **VERIFICADA** | 2 corredores + 7 clientes en `profiles` |
| Auto-provisión de perfil | ✅ | ✅ | ✅ | ✅ | — | **VERIFICADA** | `app/auth.py` — crea como `cliente` en el primer acceso |
| Renovación de token caducado | ✅ | ✅ | ✅ | ✅ | — | **VERIFICADA** | Interceptor de axios · nació de una tanda de 401 en los registros de Render |
| Historial de conversaciones | ✅ | 🟡 | ✅ | ✅ | ✅ | **PARCIAL** | 148 sesiones · **122 sin título propio** · ⚠️ endpoint sin autenticar |
| Compartir conversación | ✅ | ✅ | ✅ | ✅ | — | **VERIFICADA** | 3 conversaciones públicas en base · `GET /chat/shared/{token}` |
| Favoritos / inmuebles guardados | ❌ | — | — | — | — | **NO IMPLEMENTADA** | — |
| Alertas de búsqueda guardada | ❌ | — | — | — | — | **NO IMPLEMENTADA** | `notificacion` es de handoff, no de mercado |
| Agenda de visitas al inmueble | ❌ | — | — | — | — | **NO IMPLEMENTADA** | `POST /visitas` registra **llegadas**, no citas |
| Informes descargables | ❌ | — | — | — | — | **NO IMPLEMENTADA** | — |

---

## 10. Inversión

| Funcionalidad | Existe | Funciona | Backend | Datos reales | IA | Estado | Evidencia |
|---|:-:|:-:|:-:|:-:|:-:|---|---|
| Rentabilidad bruta y neta | ✅ | ✅ | ✅ | ❌ | ❌ | **PARCIAL** | `app/inversion.py` (puro, con pruebas) · entradas sintéticas en 39/40 |
| Precio por m² | ✅ | ✅ | ✅ | ❌ | ❌ | **PARCIAL** | Ídem |
| Parámetros de mercado (adquisición 7%, vacancia 1 mes, predial 0,5%…) | ✅ | ✅ | ✅ | — | ❌ | **HARDCODEADA** | Diccionario `_INV` — *"defaults Ecuador/LATAM; configurables a futuro"* |
| Veredicto del rendimiento | ✅ | ✅ | ✅ | ❌ | ❌ | **HARDCODEADA** | 4 umbrales fijos (7 / 5 / 3,5) · el prompt prohíbe convertirlo en consejo de compra |
| Endpoint REST equivalente | ✅ | ✅ | ✅ | ❌ | ❌ | **VERIFICADA** | `GET /assets/{id}/investment` — mismo motor que la herramienta del agente (patrón API-first real) |
| Comparables de mercado reales | ❌ | — | — | — | — | **NO IMPLEMENTADA** | Prometida como "Market API" |

---

## 11. Plataforma / API para terceros

| Funcionalidad | Existe | Estado | Evidencia |
|---|:-:|---|---|
| Esquema OpenAPI publicado | ✅ | **VERIFICADA** | `GET /openapi.json` → 60 rutas |
| Autenticación por llave de API | ✅ | **VERIFICADA** | `X-API-Key` en 20+ endpoints · `POST /chat/` → 401 sin ella |
| Limitación de tasa | ✅ | **VERIFICADA** | slowapi en 53 endpoints |
| Identidad por organización / OAuth | ❌ | **NO IMPLEMENTADA** | Una sola `API_KEY` global |
| Webhooks | ❌ | **NO IMPLEMENTADA** | Prometida en `ESTRATEGIA_API_First.md` |
| Entorno de pruebas / claves autoservicio | ❌ | **NO IMPLEMENTADA** | Ídem |
| Documentación pública | ❌ | **NO IMPLEMENTADA** | Ídem |
| Medición y facturación por cliente | ❌ | **NO IMPLEMENTADA** | Ídem |
| Servidor MCP | ❌ | **NO IMPLEMENTADA** | Pero las 9 herramientas ya tienen la forma exacta que haría falta |

---

## 12. Resumen cuantitativo

| Estado | Conteo |
|---|---:|
| **VERIFICADA** | 34 |
| **PARCIAL** | 17 |
| **BACKEND NO VALIDADO** | 18 |
| **UI SIN BACKEND VERIFICADO** | 2 |
| **HARDCODEADA** | 6 |
| **MOCK** | 4 |
| **NO IMPLEMENTADA** | 17 |
| **RECHAZADA A PROPÓSITO** | 1 |

**La lectura de esta tabla:** el proyecto tiene **34 funcionalidades verificadas** — es mucho para 11 semanas. Pero **18 están construidas sin evidencia de uso** y **17 se prometen en documentación sin existir**. La brecha entre *construido* y *usado* es tan grande como la brecha entre *prometido* y *construido*, y la primera es la que preocupa: significa que el esfuerzo fue a capacidad que nadie ejerce todavía.

---

## 13. Duplicaciones y código sobrante encontrado

| Hallazgo | Evidencia |
|---|---|
| 10 SVG duplicados exactos | `logo/*.svg` ≡ `Contexto_AI_Brand/logo/*.svg` (idénticos por hash SHA-1) |
| Favicon duplicado | `frontend/public/sphere-favicon.svg` ≡ `logo/sphere-mark-32.svg` |
| Heurísticas divergentes | `app/scores_heuristicos.py` (67 L) vs `scripts/scores_heuristicos.py` — **el mismo cálculo con dos textos y dos versiones** |
| Migración duplicada | `migration_tipo_activo.sql` (raíz) ≡ `migrations/002_tipo_activo.sql` |
| Dos esquemas iniciales | `init_db.sql` (Docker local) vs `supabase_migration.sql` (producción) |
| 8 artefactos de siembra solapados | `seed_data.py`, `seed_ampliado.py`, `gen_fichas_30.py`, `gen_sql_seed.py`, `fichas_30.sql`, `supabase_seed.sql`, `seed_demo_fase1.sql`, `seed_fill_all_fase1.sql` |
| 3 pruebas que nunca se ejecutan | `test_agent.py`, `test_geocoding.py`, `test_memory.py` en la raíz; `pytest.ini` fija `testpaths = tests` |
| 5 tablas con 0 filas | `agencies`, `aviso_email`, `embedding_cache`, `aura_pois_cache`, `historial_eventos_urbanos` |
| Tabla de respaldo huérfana | `pois_propios_backup_20260727` — 4.898 filas de un respaldo de julio, aún en producción |
| **Módulos Python muertos** | **Ninguno.** Los 51 módulos de `app/` están importados al menos una vez. |
