# Auditoría de Pendientes — Contexto AI

**Fecha:** 2026-06-23
**Hito del día:** Call con Linden Inmobiliaria (Puebla) → piloto acordado ✅
**Pendiente inmediato:** documentación y requerimientos de Linden (llegan mañana o estos días)

---

## ✅ CERRADO HOY (23 jun)

- **Obsidian MCP** conectado a Claude Code via HTTP — notas accesibles desde cualquier sesión.
- **Quick wins #13-16 verificados** — todos ya estaban hechos desde la semana del 15 jun:
  - Marcas-ancla (Tuti, Santa María, Quicentro) priorizadas en `rutas.py`
  - Tests de inversión (`test_inversion.py`, 6 tests)
  - Deck: "Walk Score" → "Caminabilidad"
  - Filtro anti-hype "as bajo la manga" en `graph.py`
- **Bug corregido en `intencion.py`** — explorador que compara 2+ zonas era marcado "frío"; ahora sube a "tibio" (fix: `n_msgs_zona` suma al score). 44/44 tests verdes.
- **Demo Linden preparado y validado** en `contexxto.com` — 3 casos reales de Quito.
- **Guion de descubrimiento** guardado en vault (`GUION_Descubrimiento_Linden_2026-06-23.md`).
- **Call Linden exitosa** → piloto acordado.

---

## 🔴 INMEDIATO — Tú (acciones rápidas sin código)

| # | Pendiente | Dónde |
|---|---|---|
| 1 | **Borrar Render Virginia** (servidor viejo) | Dashboard Render → servicio viejo → Delete |
| 2 | **Decidir Vercel Pro Trial** | Agregar tarjeta o bajar plan (⚠️ bajar apaga Firewall AI Bots) |
| 3 | **Activar 2FA en Vercel** | Settings → Authentication |

---

## 🟠 LINDEN — Piloto (bloqueado hasta recibir documentación)

| # | Pendiente | Estado |
|---|---|---|
| 4 | Recibir documentación y requerimientos de Linden | Esperando (mañana/estos días) |
| 5 | Definir alcance técnico del piloto con sus datos | Depende de #4 |
| 6 | **Integración WhatsApp** (el canal principal de Linden) | Alcance del piloto |
| 7 | **Localización Puebla** — zonas, marcas-ancla MX, impuestos MX | Alcance del piloto |
| 8 | **Ruteo a N asesores** (hoy el handoff es a 1 corredor) | Alcance del piloto |
| 9 | **Asignar corredor a propiedades** del catastro (script listo, falla DNS local) | Pendiente técnico menor |

---

## 🟡 NEGOCIO — Mazatlán/Ricardo (portón antes de UX nueva)

| # | Pendiente |
|---|---|
| 10 | **Validar con Ricardo** — desarrolladores Mazatlán antes de construir UX nueva |
| 11 | Plan estratégico Mazatlán según validación |

---

## 🟡 PRODUCTO (construir DESPUÉS de validar Mazatlán)

| # | Pendiente | Nota |
|---|---|---|
| 12 | Página de anuncio `/a/{id}` (mockups aprobados, falta React) | Tier 1 del foso |
| 13 | Badges de verificación + frescura en UX | Tier 1 del foso |
| 14 | Handoff como clímax en la UX | Tier 1 del foso |
| 15 | Encaje relativo a intención: *"X% de encaje contigo"* | Tier 2 |
| 16 | Consistencia ficha-activo vs. análisis en vivo | Tier 2 |
| 17 | Persistir 👍/👎 a BD | Tier 2 |
| 18 | Endpoint `/investment` público → OAuth para B2B | Tier 2 |

---

## 🔵 INFRA / CALIDAD

| # | Pendiente |
|---|---|
| 19 | DNS local no resuelve Supabase (impide correr scripts locales contra prod) |
| 20 | `VITE_API_KEY` en bundle (mitigado; a futuro chat por Bearer) |

---

## ⚪ FOSO DE DATOS (Fase 2-3, no urgente)

Vision API · Scoring API · NDVI · Comparables de catastro · Pre-hidratación en malla

---

## 🎯 Próximo bloque natural

1. **Hoy/mañana:** cerrar #1-3 (Render + Vercel — son tuyas, 5 min cada una)
2. **Al recibir docs Linden:** diseñar alcance del piloto (#4-8)
3. **En paralelo:** agendar con Ricardo para Mazatlán (#10)
