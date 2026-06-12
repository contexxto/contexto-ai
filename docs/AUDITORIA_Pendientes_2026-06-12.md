# Auditoría de Pendientes — Contexto AI V2

**Fecha:** 2026-06-12
**Estado infra:** Backend Oregón ✅ (200) · Virginia suspendido ✅ (503, sin doble cobro) · 61 tests verdes · Migraciones 008–013 aplicadas.

---

## 🔴 URGENTES / con fecha límite

| # | Pendiente | Acción | Quién |
|---|---|---|---|
| 1 | **Rotar la API key** (`ContextoAI-Prod-2026` quedó visible en el chat) | Nueva clave robusta → mismo valor en Oregón (`API_KEY`) y Vercel (`VITE_API_KEY`) + redeploy frontend | Carlos (post-reunión) |
| 2 | **Vercel Pro Trial expira en 8 días** | Decidir: agregar tarjeta o bajar de plan. ⚠️ Si bajas de Pro, el Firewall **"AI Bots"** que activaste hoy **se desactiva** | Carlos |
| 3 | **Borrar el Render viejo de Virginia** | En 2–3 días, si todo sigue estable (Settings → Delete) | Carlos |

---

## 🤝 NEGOCIO — Grupo Bolívar (sesión por agendar)

| # | Pendiente | Acción |
|---|---|---|
| 4 | **One-pager "Contexto × Grupo Bolívar"** | Armar documento con los 3 ángulos (Ciencuadras/portal, Davivienda/banco, El Libertador/seguros) |
| 5 | **Guion de demo (15 min)** adaptado a esa audiencia | 3 ángulos de valor en vivo |
| 6 | **Investigar a fondo El Libertador** | Afinar el ángulo de seguros/riesgo de arriendo |
| 7 | **NDA** | Rellenar corchetes + **revisión por abogado** (Ecuador/Colombia) antes de firmar |
| 8 | **Reporte Fogel/Serhant → .docx** | Si lo quiere compartir como material |

---

## 🖼️ PRODUCTO

| # | Pendiente | Nota |
|---|---|---|
| 9 | **Construir la página de anuncio real `/a/{id}`** | Mockups (móvil + escritorio) aprobados; falta el componente React real |
| 10 | **Decisión `/near`** | Hoy muestra scores a invitados a propósito (gancho de conversión). ¿Cerrarlo también? |
| 11 | **Flujo de revisión para inmobiliarias** | `estado_revision` existe; la ficha hoy se publica directo. Conectar la "Revisión" de agencias |
| 12 | **Persistir 👍/👎** del agente a la BD | Hoy es solo local |

---

## 🌳 FOSO DE DATOS — señales pendientes

| # | Pendiente | Nota |
|---|---|---|
| 13 | **Vegetación NDVI real** (Sentinel-2 / Earth AI) | Hoy es heurístico; sería automático |
| 14 | **Vista aérea / 3D** (Aerial View API de Google) | Para el "hero" de la página de anuncio. Demo Key cubre prototipo |
| 15 | **Elevación** (pendiente / vista / riesgo de inundación) | Señal nueva, barata; relevante para Quito (laderas/quebradas) |
| 16 | **Landmarks grandes** | Que Quicentro Sur aparezca aunque esté > radio (hoy gana el más cercano) |
| 17 | **Riesgo futuro** (SERCOP / zonificación) | Ingerir shapefiles de obras y restricciones de altura |
| 18 | **Pre-hidratación en malla de Quito** | El verdadero foso de costo/escala. Diseñado, no construido |

---

## 🔵 INFRA / ESCALA

| # | Pendiente | Nota |
|---|---|---|
| 19 | **Plan de Render con más CPU** | Queda ~0.45s base por request (Starter). Subir plan si se quiere "instantáneo". Opcional |
| 20 | **SMTP propio** para confirmación de correo | Al escalar; hoy se confirma manual por SQL |
| 21 | **Google OAuth** (login con Google) | Diferido — requiere Google Cloud setup |
| 22 | **`VITE_API_KEY` en el bundle** (extraíble) | No es secreto real; mitigado por rate limit + auth. A futuro: mover el chat a auth por usuario (Bearer) |

---

## ⚪ PILOTO DEL CORREDOR

| # | Pendiente | Nota |
|---|---|---|
| 23 | **Subir las ~10 propiedades del corredor amigo** | Ya con "Mis publicaciones" + características + ficha técnica + fotos. Usar GUIA_Ingesta_Corredor |
| 24 | **Atribución** | Trackear qué corredor/usuario refirió a cada visitante enganchado (motor de crecimiento) |

---

## ✅ CERRADO HOY (para contexto)
Walk Score real (OSM) · Conectividad (Metro/terminal) · Servicios cercanos (Google Places) · Ficha técnica + características + fotos · "Mis publicaciones" · modo vista/editar/grabar · migración a Oregón (latencia) · caché de perfil/lista · fixes de API key · **seguridad: robots.txt + AI Bots deny + rate limiting + geojson flaco** · NDA + reportes · pitch 3 min.

---

*Auditoría generada para seguimiento. Prioridad sugerida: 🔴 (1–3) → 🤝 Grupo Bolívar (4–8) → 🖼️ página de anuncio (9).*
