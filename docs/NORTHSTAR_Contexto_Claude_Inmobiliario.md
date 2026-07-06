# Contexto AI — El motor que convierte la intención en una venta que se sostiene, sobre la verdad verificada del lugar
### North Star · Brújula de producto y narrativa

**Fecha:** 2026-06-15

---

## La visión en una frase

> **Que la intención de una persona se vuelva una venta que se sostiene — encajando su deseo con el lugar real (verificado) y con lo que de verdad puede pagar.**

No la que te vende (portales). No la enciclopedia que describe zonas (ChatGPT/Google). **La asesora honesta que verifica el activo en el terreno y razona si vivir, rentar o invertir tiene sentido — con la evidencia en la mano.** Por eso el comprador confía; y por eso el corredor, la inmobiliaria o el desarrollador recibe un lead calificado, no un "alguien preguntó".

*La IA en la que confías para la decisión financiera más grande de tu vida.*

> **Nota interna (uso técnico / sala de inversión — NO para copy público):** la analogía "el
> Claude inmobiliario" resume la marca que heredamos —confianza, honestidad, razonamiento,
> seguridad ("el Claude de X" ≠ "el ChatGPT de X")—. Es un anclaje útil frente a un inversor
> tech, pero JAMÁS el titular de cara a un corredor o comprador: ahí se lidera con el valor
> (que su próximo lead llegue calificado y su venta se sostenga en la verdad del lugar). Por eso
> salió del título de esta brújula.

---

## La tesis (lo que nos separa de todos)

> **Donde otros describen, Contexto verifica y razona.**

- **Google / ChatGPT** describen la zona y muestran lugares → *commodity*. No lo peleamos.
- **Invisor** (España) calcula la inversión sobre datos **scrapeados y no verificables** — su propio output admite *"confianza catastral: NULA"*. Es su techo.
- **Contexto** razona la inversión sobre **datos verificados en el terreno** (ficha técnica, QR, fotos, corredor). Donde Invisor dice *"no puedo verificar"*, Contexto dice *"verificado: tubería 2023, cédula sí, impermeabilización al día."*

**La frase que define la guerra:**
> *"Donde otros dicen 'confianza nula', Contexto dice 'verificado en el terreno'."*
Eso no se copia scrapeando — requiere haber **estado** en el inmueble.

---

## El foso (3 capas que se refuerzan)

1. 🏠 **Catastro Vivo verificado** — datos por coordenada que acumulan en el tiempo (ficha técnica de mantenimiento, evidencia fotográfica, QR en sitio). Imposible de replicar sin operar en el territorio.
2. 📈 **Inteligencia de inversión** — traduce precio + estado + renta de zona en margen, yield y riesgo real; detecta el *deal-killer* que mata la operación. Razonamiento sobre verdad verificada.
3. 🛡️ **Confianza / honestidad** — no inventa, distingue dato verificado de estimación, revela lo que el anuncio oculta, y transfiere la responsabilidad del comprador (datos + corredor humano).

> El segundo foso, contraintuitivo: en LATAM el dato público es **pobre** (no hay Idealista/INE/Catastro como en España). Eso frena a los scrapers — y **convierte el dato que Contexto acumula en aún más valioso y defendible.** La escasez que nos frena, nos protege.

---

## El motor del foso: el sistema vivo

> **Contexto no es un buscador de inmuebles. Es el sistema de conocimiento VIVO de la habitabilidad — que se vuelve más inteligente con cada corredor y cada cliente que lo toca.**

El chat, las fichas y la UI son la superficie *commoditizable*. El **loop que aprende** (corredor confirma/corrige/agrega → catastro mejora → mejores respuestas → más leads → más corredores aportan) es lo que **compone** y no se copia. Validado casi línea por línea por el ensayo de Satya Nadella sobre la *AI-driven economy* (jun 2026). Cuatro principios que de aquí se derivan:

1. **El loop ES el producto, no una feature.** El compounding del aprendizaje es el foso; lo demás se commoditiza.
2. **Portabilidad = doctrina de arquitectura.** El conocimiento vive en PostGIS propio + formato portable (OKF). *"El modelo lo alquilas, no lo posees."*
3. **Evals en plata.** Medir handoffs calificados, no minutos ni vanity.
4. **El handoff humano es la espina, no el fallback.** *"La venta es fricción humana"*; la IA da contexto, el humano cierra.

> Derivación completa, paralelos con Nadella y contrapunto honesto en `VISION_Sistema_Vivo.md`.

---

## El stack de capacidades (cómo se construye — modelo AI-nativo)

Operación: **Carlos (visión/orquestación) + Gemini (estrategia) + Claude (ejecución técnica y cerebro del agente).** Envía como un equipo de 10 con el burn de uno.

| Capa | Estado |
|---|---|
| 🗣️ Asesor que razona (conversación honesta, cápsulas, revela riesgo) | ✅ |
| 🧰 Orquestación (geocode, ficha, habitabilidad, rutas, mapa) | ✅ |
| 👁️ **Visión multimodal** — fotos → estado; escrituras/planos/cédula → datos verificados | 🔨 palanca clave |
| 📈 **Capa de inversión** — yield, margen, riesgo, escenarios | 🔨 el vertical nuevo |
| 🌳 Foso de datos — catastro vivo + pre-hidratación + captura de intención | 🌱 por escalar |

---

## La capa de distribución: API-first (infraestructura, patrón Apaleo)
El producto es el foso; **la API es la distribución.** Contexto no se vende como "una app" — se integra como **el motor de inteligencia inmobiliaria que la banca, los fondos y las constructoras consumen en vez de construir** (igual que Apaleo es el PMS que el hotel integra, no construye). La web y el agente son *clientes* del mismo API.
- **Hoy:** API-first como **arquitectura** (`app/inversion.py` lo consumen el agente y `GET /assets/{id}/investment`).
- **Con design partner (InmobIA/Bolívar):** se expone el API de negocio (Ficha/Investment/Scoring/Market) — *que el integrador hale la API a existir*.
- **Con tracción:** plataforma de developers (sandbox, Swagger, OAuth, webhooks, Store).
- **Efecto de red:** cada integrador que consume **hidrata el catálogo** → foso más profundo.
> Detalle en `ESTRATEGIA_API_First.md`. Reencuadra el pitch a Bolívar: no "compra mi app", sino "integra mi motor en Ciencuadras/Davivienda".

---

## Hoja de ruta (sin perder foco — *scope mata, profundidad gana*)

- **Fase 1 — ahora:** asesor honesto de habitabilidad + ficha técnica. Piloto del corredor (Quito). *(Casi listo.)*
- **Fase 2 — el salto:** (a) **visión** que hidrata el catastro desde fotos/documentos; (b) **capa de inversión** (yield/margen/riesgo/escenarios), montada sobre dato verificado. *Aquí superamos la barra de Invisor.*
- **Fase 3 — escala:** pre-hidratación de ciudades + B2B (InmobIA México, Grupo Bolívar) como **distribución** del motor.

> 📌 *Nota de enriquecimiento de datos (futuro, no pivote):* la **capa ambiental** (hoy "cobertura vegetal" heurística) puede alimentarse de **satélite real** vía Google Earth Engine (NDVI). Google ya tiene agentes geoespaciales sobre Earth Engine para lo ambiental/planetario — es **fuente de datos complementaria, no competidor** (su capa es ambiental/global; la nuestra, habitabilidad local + dato del corredor). Doctrina de portabilidad intacta: no se cambia el stack, solo se considera Earth Engine como fuente de la capa verde cuando toque escalar.

---

## Por qué ahora / por qué nosotros
- **AI-nativo:** iteramos en horas lo que a un equipo tradicional le toma meses.
- **LATAM:** mercado menos saturado, dato público débil → el dato verificado es el moat.
- **Producto vivo:** ya está en producción, con datos reales, honesto y conversacional.

## North Star metric
**Decisiones inmobiliarias mejor informadas** (no minutos de uso): profundidad de análisis, % que llega a la ficha verificada, conversión a contacto con corredor, retorno por valor. El enganche ético produce lealtad y referidos — más rentable que la adicción.

---

*La pregunta para un socio (Bolívar, inversionista) no es "¿es buena la idea?". Es: "esto va a existir — ¿entro temprano o lo veo pasar?".*
