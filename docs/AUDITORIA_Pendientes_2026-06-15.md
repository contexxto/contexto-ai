# Auditoría de Pendientes — Contexto AI V2

**Fecha:** 2026-06-15
**Estado infra:** Backend Oregón ✅ healthy · Frontend Vercel ✅ · python-docx instalado local.
**Foco desde la última auditoría (06-13):** rediseño conductual (cápsulas) + capa de inversión + API-first + paquete comercial Ricardo.

---

## ✅ CERRADO DESDE 06-13 (avance enorme)
- **Rediseño conductual:** workflow de CÁPSULAS aplicado (Regla 0) + informe a demanda. Validado.
- **Prueba de esfuerzo (10 intenciones)** + fixes: Metro bidireccional, precisión de zona, tráfico-0, "café", "Walk Score"→Caminabilidad (en la fuente), nombres genéricos ("TRABAJO").
- **QR privado por dispositivo** + saneo de prompt en compartido + fix de scroll del visor compartido + guard anti-eco.
- **API key ROTADA** (vieja muerta, verificada 401).
- **Capa de inversión:** Fase 0 (input de renta) + Fase 1 (`tool_analyze_investment`) + `app/inversion.py` (módulo único) + endpoint REST `GET /assets/{id}/investment` (verificado por curl) + confianza por campo.
- **Estrategia:** North Star "Claude Inmobiliario" + Estrategia API-first (Apaleo) + análisis InmobIA/Invisor.
- **Paquete Ricardo:** one-pager + guion de reunión, ambos en `.docx`.

---

## 🟢 SE PUEDEN CERRAR HOY

### Tus acciones (rápidas)
| # | Pendiente | Acción |
|---|---|---|
| 1 | **Borrar Render Virginia** | Dashboard Render → servicio viejo → Settings → Delete (~1 min). |
| 2 | **Vercel Pro Trial** | Decidir: agregar tarjeta o bajar de plan (⚠️ bajar apaga el Firewall AI Bots). |
| 3 | **2FA en Vercel** | Settings → Authentication → Set Up Authenticator App (~2 min). |

### Código (los hago yo, rápidos)
| # | Pendiente | Esfuerzo |
|---|---|---|
| 4 | **Marcas-ancla / landmarks** (Tuti, Santa María, Quicentro) priorizados en servicios | bajo |
| 5 | **Tests** de las funciones puras de inversión (`analizar_inversion`, `_kpis`, veredictos) | bajo |
| 6 | **Deck** `logo/deck-tmp/deck.js`: "Walk Score" → "Caminabilidad" | trivial |
| 7 | **Hype residual** "as bajo la manga" — reforzar el filtro de tono | trivial |

---

## 🤝 NEGOCIO (con fecha / prioridad)
| # | Pendiente |
|---|---|
| 8 | **Guion + one-pager de Grupo Bolívar** (3 ángulos Ciencuadras/Davivienda/Libertador + manejo de "¿son solo tú?") |
| 9 | **Investigar El Libertador** (ángulo seguros/riesgo) |
| 10 | **NDA**: rellenar corchetes + revisión por abogado |
| 11 | Reporte Fogel/Serhant → .docx (opcional) |

## 🖼️ PRODUCTO
| # | Pendiente |
|---|---|
| 12 | **Página de anuncio `/a/{id}`** (mockups aprobados; falta el React) |
| 13 | **Consistencia ficha-del-activo vs. análisis en vivo** (el activo guarda servicios de `entorno.py` al publicar; el live usa Google — unificar) |
| 14 | Decisión `/near`/`geojson` scores a invitados |
| 15 | Flujo de revisión para inmobiliarias (`estado_revision` existe, sin conectar) |
| 16 | Persistir 👍/👎 a la BD |
| 17 | **Endpoint `/investment` es PÚBLICO** — para B2B producción necesita la capa Identity/OAuth (productización API) |

## 🌳 FOSO DE DATOS (Fase 2-3 de la visión)
| # | Pendiente |
|---|---|
| 18 | **Vision API** — leer fotos/escrituras/planos → ficha + CapEx (el gran salto del "Claude de inversión") |
| 19 | **Scoring API** — score 0-100 por estrategia (flip/value-add/rentar/vivir) |
| 20 | NDVI vegetación · Vista aérea/3D · Elevación (inundación) · SERCOP/zonificación |
| 21 | Pre-hidratación en malla (el foso de escala) |
| 22 | Comparables/Market API de zona desde el catastro acumulado |

## 🔵 INFRA / CALIDAD
| # | Pendiente |
|---|---|
| 23 | Plan Render con más CPU (opcional) · SMTP propio · Google OAuth |
| 24 | `VITE_API_KEY` en bundle (mitigado; a futuro chat por Bearer) |

## ⚪ PILOTO DEL CORREDOR
| # | Pendiente |
|---|---|
| 25 | Subir ~10 propiedades del corredor (hay 1 publicada) |
| 26 | Atribución de referidos |

---

## 🎯 Plan para cerrar HOY
1. **Tú:** borra Render Virginia (#1), decide Vercel Pro (#2), activa 2FA (#3).
2. **Yo:** marcas-ancla (#4) + tests de inversión (#5) + deck rename (#6) + reforzar hype (#7).
→ Con eso quedan cerrados todos los **quick wins** y los **urgentes**. Lo grande (Bolívar, página `/a/{id}`, Vision API) queda como el siguiente bloque, ya con prioridad clara.
