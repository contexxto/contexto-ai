# Investigación — Motores de Intención: cómo los players globales convierten intención en transacción

**Fecha:** 2026-06-15
**Autor:** Contexto AI (estrategia)
**Propósito:** Benchmark global previo a diseñar el motor de intención de Contexto. Cómo PropTech, CRMs con IA, agentes conversacionales y el comercio por WhatsApp llevan a una persona desde el deseo hasta la transacción.

> *Nota de método: síntesis de fuentes públicas (jun 2026). Las URLs están al final. Donde no encontré dato específico, lo digo.*

---

## TL;DR — los 5 principios universales
Todos los líderes, sin importar la industria, convergen en el mismo patrón:

1. **La etapa = un estado de intención**, no una casilla administrativa.
2. **Señales en vivo → score explicable** (y honesto: por qué sube).
3. **Automatización en las transiciones** + disparadores **proactivos** (adelantarse al usuario).
4. **El humano entra en el pico de intención** (live-transfer), no antes.
5. **Se cobra y se mide por RESULTADO**, no por actividad.

---

## 1. Portales PropTech (Zillow, Compass, Redfin, Rightmove)
**Qué hacen hoy:** Migraron de "filtros por palabra clave" a **búsqueda en lenguaje natural que interpreta intención**. Zillow tiene NL search desde 2023 y lanzó integración con ChatGPT (oct 2025), con expansión de su "AI mode" en 2026. Compass y Redfin desarrollan buscadores IA propios; Homes.com lanzó "Smart Search". Europa occidental (donde no existe el agente de comprador) va años adelante en búsqueda *buyer-led*.

**El dato que importa:** ya circulan tesis públicas de que **la IA agéntica está volviendo obsoletos a Zillow / Rightmove / Zoopla** — "el colapso de los agregadores SaaS de anuncios".

**Lección para Contexto:** la apuesta contra el "anuncio efímero" **ya se está cumpliendo**. La conversación con intención es la nueva puerta de entrada. Contexto está del lado correcto de la disrupción — pero hay que correr.

## 2. Motores de IA para conversión inmobiliaria (Ylopo, Structurely, Lofty)
**Qué hacen hoy:** detectan **señales de alta intención** y **transfieren al humano SOLO cuando el lead está listo para transar**. Ylopo (AI² = texto + voz IA) revive bases dormidas y hace *live-transfer* al agente cuando detecta intención alta. Structurely: IA de calificación por texto/voz tan humana que la confunden con persona. Lofty: CRM + comunicación todo-en-uno.

**Resultado documentado:** conversión de leads fríos sube de **4% a 15%** con asistentes de voz IA. Ylopo ganó el "Best of PropTech 2025" de Inman por activación y follow-up con IA.

**Lección para Contexto:** el **corredor entra en el pico de intención**, no antes (modelo "la IA califica, el humano cierra"). Y hay oro en **reactivar bases dormidas** (re-escaneos de QR, conversaciones viejas).

## 3. CRM con modelo de intención (HubSpot)
**Qué hacen hoy:** ciclo de vida en 8 etapas (Subscriber → Lead → MQL → SQL → Opportunity → Customer → Evangelist → Other) + **lead scoring por ML** sobre cientos de variables, con **explicabilidad** (muestran *qué señales* contribuyeron al score) + **workflows que automatizan en cada transición** de etapa (correos, cambio de etapa, alerta a ventas).

**Lección para Contexto:** las etapas son **estados**; el score debe ser **explicable** (≈ principio de honestidad de Contexto); cada transición **dispara automatización**. Es el esqueleto del CRM de Whaber, ya validado a escala global.

## 4. Agentes de IA con precio por resultado (Fin, Decagon, Sierra) — el hallazgo más jugoso
**Qué hacen hoy:** se cobran y se miden por **outcome**, no por actividad.

| Agente | Modelo de precio | Métrica clave |
|---|---|---|
| Intercom **Fin** | **$0.99 por outcome (resolución)**, sin cargo por asiento del agente | 67% de resolución; +40M conversaciones resueltas |
| **Decagon** | ~$0.99/conversación + ~$50k/año plataforma | Duolingo 80% deflexión; Chime 70% |
| **Sierra** | ~$150k–$1.5M/año (no público) | despliegues enterprise multicanal |

Hunter Douglas atribuye **$1M en ingresos** a conversaciones 100% manejadas por IA. Matiz clave: pagar "$1 por interacción" sale más caro que "$1 por resolución" cuando la IA resuelve el 60% — en el primer caso pagas también por el 40% que falla.

**Lección para Contexto:** el mundo se mueve a **cobrar por resultado**. Para la API de Contexto es una mina: cobrar por **outcome** (visita calificada, cierre, ficha verificada) en vez de por consulta. Y medir al agente por **resultados, no por chats**.

## 5. Comercio conversacional en WhatsApp (Yalo) + la realidad de costos
**Qué hacen hoy:** flujo **"Welcome & Qualify"** — la IA saluda y hace **una pregunta calificadora** para entender la intención de entrada. En LATAM el patrón es **descubrir en TikTok y convertir en WhatsApp** (93% de smartphones usan WhatsApp a diario). WhatsApp Payments empuja a cerrar todo el ciclo dentro de una sola conversación.

**Corrección importante (actualiza lo que hablamos):** desde el **1 de julio 2025** WhatsApp cambió de "ventana de 24h" a **cobro por mensaje**:
- Mensajes **iniciados por el cliente** (servicio, dentro de 24h): **GRATIS**.
- **Reabrir o contactar proactivamente** (plantillas): **cuesta** — marketing $0.025–$0.1365, utility/auth $0.004–$0.045 por mensaje, según país.

**Lección para Contexto:** el instinto era correcto y ahora más fino. WhatsApp es **canal reactivo gratis**, pero **actuar proactivamente sobre la intención cuesta y no lo controlas**. → Ser **dueño del runtime** (agente + sesiones QR de Contexto) sigue siendo la jugada; WhatsApp queda como **puerta/notificación**, no como runtime.

## 6. Disparadores conductuales (comercio agéntico 2026)
**Qué hacen hoy:** triggers proactivos sobre señales de vacilación: carrito >2 min sin checkout, **exit intent**, navegación de alto valor, visitante que regresa, "lingering" en una página. La IA monitorea en vivo (scroll, tiempo en página, sentimiento) y **se adelanta** a ofrecer ayuda. Deloitte: 68% de retailers adoptarán IA agéntica en 12-14 meses.

**Lección para Contexto:** el motor de intención es **proactivo y en tiempo real** — el valor está en **actuar antes de que el usuario pregunte**. Es justo lo que al CRM de Whaber le faltaba (las ventanas se vencían solas, sin acción automática).

---

## Qué significa para Contexto (puente al diseño del motor)
- Contexto ya tiene los **principios 1–4 a medio construir** (el CRM de Whaber + el agente de Contexto). El **principio 5 (outcome-based)** es terreno virgen y una mina para la API.
- El **runtime propio** (agente + sesiones QR) es la pieza que a los demás les cuesta: pelean con el costo de WhatsApp o dependen de portales de terceros.
- El **foso de dato verificado** + el **motor de intención** = algo que **ni los portales** (datos efímeros) **ni los CRM** (sin dato del activo) tienen juntos. Esa es la posición defendible.

**Siguiente paso:** mapear el motor de intención a Contexto — estados, señales/disparadores, qué se automatiza, dónde entra el corredor y qué se cobra por resultado. (Documento aparte: "Mapa del Motor de Intención de Contexto".)

---

## Fuentes
- Ylopo / Inman Best of PropTech 2025: einpresswire.com/article/868954997
- Guía AI real estate lead gen 2025: propphy.com/blog/real-estate-ai-lead-generation-2025-guide
- Yalo comercio conversacional: yalo.ai/blog/yalo-conecta-the-future-digital-and-conversational
- WhatsApp commerce LATAM: sherlockcomms.com/whatsapp-commerce-in-latin-america
- HubSpot lifecycle marketing 2026: arisegtm.com/blog/hubspot-lifecycle-marketing
- AI lead scoring / intent signals HubSpot: content.hubjoy.co/ai-lead-scoring-secrets-intent-signals-hubspot-tips-for-2026
- Fin AI pricing por outcome: fin.ai/learn/ai-customer-service-agent-pricing-comparison
- Decagon vs Sierra 2026: eesel.ai/blog/decagon-vs-sierra
- Zillow búsqueda conversacional/NL: onlinemarketplaces.com/articles/zillow-puts-its-ai-promises-to-the-test-with-new-conversational-tool
- IA agéntica vs portales: 2tokens.org/blog/agentic-ai-is-making-zillow-rightmove-and-zoopla-obsolete-the-collapse-of
- WhatsApp pricing jul-2025: ycloud.com/blog/whatsapp-api-pricing-update
- Comercio agéntico 2026 / triggers: zipchat.ai/blog/agentic-commerce-2026-guide
