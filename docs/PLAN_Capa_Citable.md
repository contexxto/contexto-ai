# Plan — La Capa Pública Citable ("que la IA te recomiende")

**Fecha:** 20 jun 2026
**Origen:** convergencia de 8 señales (Nadella, Esri, Realtor.com, Eva/Aino, Aravind/Perplexity,
Cynthia Wu, Habi/búsqueda agéntica) + los teardowns de Zillow/Redfin. Todas apuntan a lo mismo:
el **foso (la verdad del lugar) debe volverse el CANAL** (ser citado por la IA).

---

## El movimiento (el norte)

> Hacer la verdad del lugar **pública, estructurada y citable por la IA** → cuando alguien le pregunta
> a ChatGPT/Claude/Perplexity/Gemini por una zona, **te cita a TI** → el interesado llega solo.
> *"De ranking a recomendación", hecho producto.*

## Por qué AHORA

- **61% de las búsquedas inmobiliarias ya empiezan en una IA** (17%→67% en 18 meses). México, 2º del mundo en respuestas con IA.
- El roadshow probó que **empujar el producto a mano es duro.** La capa citable hace que **se distribuya solo.**
- **Compone** (más zonas = más superficie citada) y es **market-agnostic** (Quito hoy, Mazatlán mañana).

---

## El plan (lean, por incrementos)

### Paso 0 — confirmar el vacío (hoy, costo cero)
Preguntar a ChatGPT / Perplexity / Gemini: *"¿Cómo es vivir en [zona], Quito?"* → ver qué tan
**genérica/pobre** es la respuesta y **qué citan**.

### ✅ Resultado del Paso 0 (20 jun) — RE-APUNTA el plan
Probamos en vivo (ChatGPT, Gemini, búsqueda web), en Quito y Mazatlán. Hallazgo honesto:
- **Barrios famosos / zonas conocidas:** la IA ya da respuestas **excelentes** (La Floresta: nuanced,
  calle por calle, honesta). **AHÍ NO competimos** — describir lugares conocidos es commodity.
- **Lo ESPECÍFICO / no documentado / verificable:** la IA es **ciega**. No conoce el inmueble/lote real,
  no verifica quién cumple, no está fresca, no conecta. Cada respuesta pide *"tráeme lo concreto"*.

→ **El plan se re-apunta:** la capa citable **NO es para barrios famosos.** Es para **inmuebles
específicos + lugares no documentados + dato verificado-fresco** — lo que la IA citaría porque **no lo
tiene.** El foso pasa de *"describir"* a *"verificar lo específico + conectar"*.

### Increment A — páginas citables de lo ESPECÍFICO (no de barrios famosos)
- Página **pública (sin login)** por **INMUEBLE/lote verificado** y por **lugar NO documentado** (no barrios famosos).
- Dato **específico y verificado:** caminabilidad, **rutas reales (Google)**, servicios, entorno
  **confirmado por el corredor + fecha de frescura** — lo que la IA NO puede generar ni verificar.
- **URL semántica** (`/quito/[inmueble-o-sector]/`) → compartible, indexable.
- **Marcado** (schema.org / texto claro) para que la IA la **cite** — porque no tiene otra fuente.
- Empezar con **1 inmueble/lugar fuerte** → medir si la IA lo cita → escalar.

### Increment B — el encaje relativo a la intención
- Titular **"X% de encaje con lo que buscas"** (relativo), no "zona 87/100" (absoluto = ranking, gameable).

### Increment C — telemetría de intenciones
- Registrar **qué intenciones busca la gente** desde el día 1 = activo de demanda defendible.

---

## 🛑 Lo que NO hacemos ahora (disciplina P5)
- **El Mapa Vivo / isócronas** (la jugada maestra) — **DESPUÉS.** Distribución primero, lienzo después.
- Nada de portal de inventario, mapa de pines de precio, ni micro-frontends.

## 🎯 La métrica del movimiento
*Que cuando le preguntes a una IA por una zona de Quito, te cite a TI.*

---

## Conexión con docs
- [`UX_Patrones_Zillow_Redfin.md`](UX_Patrones_Zillow_Redfin.md) — URL semántica = ser citable por la IA (AEO).
- [`VISION_Sistema_Vivo.md`](VISION_Sistema_Vivo.md) — "de ranking a recomendación" (ahora con números: 61% empieza en IA).
- [`INTELIGENCIA_y_PLAN_2026-06-16.md`](INTELIGENCIA_y_PLAN_2026-06-16.md) — Habi/búsqueda agéntica, Cynthia (el dato es el muro).
- [`BRUJULA_Modelo_Mazatlan.md`](BRUJULA_Modelo_Mazatlan.md) — mismo motor + misma capa citable, otra cuña (terrenos).
