# Auditoría de Pendientes — Contexto AI V2

**Fecha:** 2026-06-13
**Estado infra:** Backend Oregón ✅ healthy · Virginia suspendido (sin doble cobro) · Frontend Vercel ✅ · Migraciones 008–013 aplicadas.
**Foco de la sesión de hoy:** mapa conversacional premium + fuente única de verdad + ubicación estilo Uber + precisión/verificabilidad.

---

## ✅ CERRADO HOY (2026-06-13)

- **Fuente única de verdad** `analizar_zona()` — home (agente) y mapa devuelven lo mismo (mismo Metro, servicios, caminabilidad).
- **Ubicación unificada** — captura una vez por cualquier entrada (home/mapa), `watchPosition` en segundo plano (modelo Uber), posición compartida (`ctx_lastpos`) + consentimiento compartido.
- **Recorrido con Aura** — tour narrado de 4-6 escenas con datos reales (+ pulidos: Metro priorizado, nombres limpios).
- **UX estilo Google Maps** — chips de categoría, tarjeta de aura proactiva, íconos/colores semánticos, crosshair flotante.
- **Rutas premium** — glow pulsante + estela de puntos en flujo + dibujado progresivo.
- **Barra de búsqueda unificada** (home = mapa): ubicación + dictado por voz + enviar.
- **Precisión/verificabilidad** — "Walk Score" → "Caminabilidad" (riesgo de marca) + atribución de fuentes (Google · OpenStreetMap).
- **Fixes** — "qué hay cerca" determinístico (búsqueda por categoría); permiso de ubicación accionable; panel izquierdo redundante eliminado; logo único giratorio.
- **Estrategia** — análisis InmobIA/Ricardo (Mazatlán): es cliente/partner (licencia del motor), no inversión.

---

## 🔴 URGENTES / con fecha

| # | Pendiente | Nota | Quién |
|---|---|---|---|
| 1 | **Rotar la API key** | `ContextoAI-Prod-2026` quedó visible en chat **y se usó en pruebas curl esta sesión** → rotar ya. Nueva clave → Oregón (`API_KEY`) + Vercel (`VITE_API_KEY`) + redeploy. | Carlos |
| 2 | **One-pager para Ricardo / InmobIA** | Reunión la **próxima semana**. Menú A–D (API de zona / mapa embebido / powered-by / captura de intención) + revenue-share por cita. | Claude→Carlos |
| 3 | **Vercel Pro Trial** | Decidir pago. Si bajas de Pro, se apaga el Firewall "AI Bots". | Carlos |
| 4 | **Borrar Render Virginia** | Suspendido y estable hace días → borrar (Settings → Delete). | Carlos |

---

## 🤝 NEGOCIO

| # | Pendiente | Nota |
|---|---|---|
| 5 | **One-pager "Contexto × Grupo Bolívar"** | 3 ángulos (Ciencuadras/portal · Davivienda/banco · El Libertador/seguros). |
| 6 | **Guion de demo (15 min)** | Adaptado a la audiencia; incluir el "muéstrale su ciudad en vivo". |
| 7 | **Investigar El Libertador** | Ángulo seguros/riesgo de arriendo. |
| 8 | **NDA** | Rellenar corchetes + revisión por abogado (Ecuador/Colombia) antes de firmar. |
| 9 | **Reporte Fogel/Serhant → .docx** | Opcional, si lo quiere compartir. |

---

## 🖼️ PRODUCTO

| # | Pendiente | Nota |
|---|---|---|
| 10 | **Página de anuncio real `/a/{id}`** | Mockups (móvil + escritorio) aprobados; falta el componente React. |
| 11 | **Consistencia ficha del activo vs. análisis en vivo** | 🆕 El activo guarda `servicios_cercanos` desde `entorno.py` (al publicar); el análisis en vivo usa `analizar_zona` (Google). Unificar el recompute del activo a la misma fuente para que el pin coincida con "qué hay cerca". |
| 12 | **Decisión `/near` / `/geojson`** | Hoy muestra scores a invitados a propósito (gancho). ¿Mantener o cerrar? |
| 13 | **Flujo de revisión para inmobiliarias** | `estado_revision` existe; conectar la "Revisión" de agencias. |
| 14 | **Persistir 👍/👎** del agente a la BD | Hoy es solo local. |
| 15 | **Marcas-ancla / landmarks** | 🆕 Priorizar marcas reconocibles (Tuti, Santa María, Quicentro) aunque no sean lo más cercano. Hoy gana el más cercano por categoría. |

---

## 🌳 FOSO DE DATOS

| # | Pendiente | Nota |
|---|---|---|
| 16 | **Vegetación NDVI real** (Sentinel-2) | Hoy heurístico. |
| 17 | **Vista aérea / 3D** (Aerial View API) | Para el hero de la página de anuncio. |
| 18 | **Elevación** (riesgo de inundación) | Relevante por quebradas de Quito. |
| 19 | **Riesgo futuro** (SERCOP / zonificación) | Ingerir shapefiles de obras/restricciones. |
| 20 | **Pre-hidratación en malla de Quito** | El verdadero foso de costo/escala. Diseñado, no construido. |

---

## 🔵 INFRA / CALIDAD

| # | Pendiente | Nota |
|---|---|---|
| 21 | **Tests de lo nuevo** | 🆕 `recorrido_zona`, `analizar_zona`, `comando_mapa`, `_servicios_con_coords`, `_nombre_limpio` sin cobertura. Añadir tests (al menos los puros: `_nombre_limpio`, `_min_pie`, `_interpreta_walk`, `_aura`). |
| 22 | **Deck `logo/deck-tmp/deck.js`** | 🆕 Aún dice "Walk Score" — actualizar a "Caminabilidad" por consistencia. |
| 23 | **Plan de Render con más CPU** | ~0.45s base; opcional. |
| 24 | **SMTP propio** | Hoy confirmación manual por SQL. |
| 25 | **Google OAuth** | Diferido. |
| 26 | **`VITE_API_KEY` en el bundle** | No es secreto real; mitigado por rate limit + auth. A futuro: chat por Bearer. |

---

## ⚪ PILOTO DEL CORREDOR

| # | Pendiente | Nota |
|---|---|---|
| 27 | **Subir ~10 propiedades del corredor amigo** | Toda la maquinaria lista (Mis publicaciones + características + ficha + fotos). |
| 28 | **Atribución de referidos** | Trackear qué corredor/usuario refirió a cada visitante (motor de crecimiento). |

---

## 🧭 Prioridad sugerida
1. 🔴 **Rotar API key** (5 min, único hueco de seguridad real, ahora más expuesta).
2. 📄 **One-pager Ricardo** (tiene fecha — reunión próxima semana).
3. 🗑️ **Borrar Virginia** + decidir **Vercel Pro**.
4. 🖼️ **Página `/a/{id}`** + #11 (consistencia ficha) — lo que ve el comprador real.
5. 📄 **One-pager Grupo Bolívar** (el pez grande).

*Tickets nuevos de esta sesión: #2, #11, #15, #21, #22.*
