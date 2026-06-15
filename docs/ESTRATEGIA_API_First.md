# Contexto como plataforma API-first
### "El motor de inteligencia inmobiliaria que la banca de inversión y las constructoras integran, en lugar de construir"

**Fecha:** 2026-06-15 · **Patrón de referencia:** Apaleo (PMS hotelero API-first) aplicado a real estate.

---

## ⏱️ Nota de secuenciación (leer primero — el *cuándo*)
- **API-first como ARQUITECTURA: desde ya.** La web y el agente son *clientes* de la misma lógica. (Ya implementado: `app/inversion.py` lo consumen el agente y `GET /assets/{id}/investment`.)
- **API-first como PLATAFORMA de desarrolladores (sandbox público, Swagger, OAuth, webhooks, Store): con un design partner.** El Store de Apaleo es estado FINAL, no inicio. No construir el portal en el vacío.
- **La jugada:** que el **primer integrador hale la API a existir.** InmobIA (Ricardo) ya pide consumir el motor = primer consumidor real. Grupo Bolívar = el grande. *Deja que ellos paguen por construir la API; no la construyas antes.*

---

## La tesis (patrón Apaleo aplicado a real estate)
Apaleo no le vende "software" al hotel: le vende un **motor API-first** que el sector integra como infraestructura. El hotel no construye su PMS — lo consume. Contexto hace lo mismo para inversión inmobiliaria: un fondo, un banco de inversión o una constructora **no monta su propio sistema de análisis** (ficha verificable + scoring + inteligencia de inversión); lo consume vía API. El producto "lo hace todo" y ellos integran.

## Lo que Contexto toma de la arquitectura Apaleo
1. **MACH / API-first:** microservicios, REST, cloud-native, headless. La UI es *un cliente más* del mismo API.
2. **Contexto en dos niveles** (como cuenta↔propiedad de Apaleo):
   - **Organización** (fondo/banco/constructora): cartera, usuarios, tesis.
   - **Activo** (`/{ASSET_CODE}/...`): ficha, análisis, scoring, escenarios.
3. **Sin lock-in / data ownership:** el cliente es dueño de sus datos; sin fees de set-up como gancho de adopción.
4. **Sandbox + self-service API keys:** docs, Swagger, sandbox reseteable → "low-touch prototyping".
5. **Ecosistema / Store:** terceros construyen sobre Contexto.

## Taxonomía de APIs (esquema Business / Development / Setup)

### Business APIs (el corazón — el foso)
- **Ficha API** — ficha técnica verificable: catastro, superficie útil real, año, uso, estado. Devuelve **nivel de confianza por campo** (honestidad nativa).
- **Investment Analysis API** — yields (bruta/neta/cash-on-cash/TIR), cashflow, P&L, escenarios vivir/rentar/invertir, margen ajustado al estado real. *(MVP vivo: `GET /assets/{id}/investment`.)*
- **Scoring API** — score 0–100 por estrategia (alquiler/flipping/value-add/desarrollo) + veredicto + riesgos críticos (jurídico, cédula, financiabilidad, zona).
- **Market API** — €/m² vs barrio, comparables, demanda, demografía por zona.
- **Vision API** — multimodal de fotos/escrituras/planos → extrae ficha y deduce CapEx de reforma.

### Development APIs
- **Identity API** — OAuth 2.0 (credenciales las gestiona el cliente; nunca se hardcodean).
- **Webhooks API** — eventos: "nuevo activo que supera tu tesis", "cambio de precio", "alerta de riesgo".
- **UI Integration API** — incrustar componentes (ficha, gauge de score) en el CRM/ERP del cliente.

### Setup / Catalog APIs
- **Portfolio API** — alta y gestión masiva de carteras (= la pre-hidratación de la Fase 3).
- **Thesis API** — define la tesis del cliente (umbrales de yield/riesgo/geografía) que parametriza scoring y alertas.
- **Sources API** — conecta orígenes (portales, feeds, catastro) para hidratar el catálogo.

## Casos de uso B2B
- **Banca de inversión / fondos:** due diligence de carteras, screening contra tesis, monitorización de riesgo, P&L por activo embebido.
- **Constructoras / promotoras:** viabilidad de suelo, escenarios vivir/rentar/vender, demanda antes de comprar.
- **Proptech / portales:** embeben scoring + ficha vía UI API.
- **Servicers / banca minorista (REOs):** valoración y priorización de adjudicados.

## Por qué gana (el foso, no el commodity)
Describir zonas/mostrar mapas es commodity (Google/LLMs gratis). El foso de Contexto-API es: (a) **ficha verificable con confianza por campo**, (b) **inteligencia de inversión que traduce descuento en margen real ajustado al estado del activo**, (c) **honestidad sobre la incertidumbre**. Distribuir eso como API convierte a cada banco/fondo/constructora en un canal — y cuanto más se integra, más datos hidratan el catálogo y más profundo el foso.

## Principios de build (Claude Code)
- Diseñar primero el **API**; la web es un consumidor (headless).
- Rutas estilo Apaleo: `api.contexto.../{org}/...` y `.../{asset_code}/{module}`.
- Devolver **niveles de confianza** en cada recurso — el diferenciador.
- Sandbox + datos de muestra + Swagger para adopción self-service B2B (cuando haya design partner).
- Webhooks para "el mercado te llega filtrado" (lo que Invisor vende a 49 €/mes, tú como evento de API).

## Estado actual (qué ya es API-first)
- ✅ `app/inversion.py` (lógica única) consumida por el agente y por `GET /assets/{id}/investment`.
- ✅ Endpoints REST: `/geojson`, `/mapa/comando`, `/mapa/aura`, `/{id}/rutas`, `/{id}/caracteristicas`.
- 🔨 Próximo: confianza-por-campo consistente, Scoring API, Vision API, Thesis/Portfolio (con design partner).
