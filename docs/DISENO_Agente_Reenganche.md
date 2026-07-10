# Diseño — Agente de Reenganche (nurture por valor verificado)

### Documento ancla · se itera EN ESTE MISMO doc con cada aprendizaje del piloto

**Creado:** 2026-07-06 · **Estado:** Fase 1 en construcción · **Dueño:** Carlos + Contexto

> **Idea en una línea.** El corredor lleva la relación con el interesado; cuando el interesado se
> enfría, un agente lo retoma — pero con un ángulo que **rompe** con las plataformas transaccionales:
> reengancha **aportando valor** (el dato verificado que respondía a lo que la persona preguntó),
> **nunca empujando** la transacción ("¿sigues interesado?"). El silencio es la opción por defecto:
> si no hay algo verificado que ofrecer, no se escribe.

---

## 1. Por qué (el hueco que nadie llena)

Felipe Restrepo (VP Growth de Habi) enseña públicamente el método comercial más claro del sector:
embudo `interesado→contactado→calificado→agendado→visitado→oferta`, con SLA por etapa, **6 intentos
de contacto** y costo por lead. Es riguroso — y es **intensidad por tiempo**: *"soy intenso hasta que
el cliente me diga que no."* Funciona, pero es exactamente el empuje que el comprador ya rechaza.

El estudio [`ESTUDIO_Adopcion_IA_Real_Estate_2026-07.md`](ESTUDIO_Adopcion_IA_Real_Estate_2026-07.md) lo cuantificó (cifras verificadas):
- La confianza del comprador en la IA para elegir casa **cayó de 30% a 16% en un año** (Cotality 2026)
  — cae *precisamente* cuando se siente manipuladora.
- **44% pagaría** por que un humano **verifique** una recomendación automatizada.
- El patrón ganador global es **copiloto** (Sierra, S.MPLE, Leo): la IA absorbe el trabajo frío,
  el humano cierra. Los virtual-ISA genéricos (Lofty et al.) reengancan por *scoring conductual* —
  puro tiempo/comportamiento, sin verdad del lugar.

**El hueco:** nadie reengancha por **valor verificado**. Contexto puede — porque es lo único que
tiene y que una plataforma transaccional no puede copiar sin desmontar su lógica de urgencia.

---

## 2. El principio que lo cambia todo: **disparar por VALOR, no por tiempo**

| | Plataforma transaccional / virtual-ISA | Agente de Reenganche de Contexto |
|---|---|---|
| **Disparador** | Reloj de intensidad (cada X horas) | **Dato nuevo y verificado que le calza** |
| **Mensaje** | "¿Sigues interesado?" | "Verificamos *lo que te importaba*: aquí está." |
| **Default** | Insistir | **Silencio** (sin valor, no se escribe) |
| **Objetivo** | Cerrar la transacción | Aportar a una decisión de vida |
| **Quién habla** | Bot que empuja | Agente que retoma la relación del corredor |

Es la misma honestidad que ya rige el producto (regla de **PROVENIENCIA**: no inventar, distinguir
verificado de estimación) aplicada al **timing y el motivo** del contacto, no solo a su contenido.

---

## 3. Alineación con el canon (no contradice nada)

- **`PRODUCTO_Encaje_Financiero_Neutral.md:49`** ya lo anticipó: *"agentes de IA en las etapas frías
  (interesado→calificado→agendado); humano cierra visita→oferta."* Este doc lo implementa.
- **`intencion.py`** ya definía los estados `completado`, `returning`, `dormido` — placeholders sin
  lógica, esperando este motor. Fase 1 activa `dormido`.
- **Fair Housing (`COMPLIANCE_FairHousing_AgentSpec`):** el ángulo del reenganche **jamás** usa señales
  de clase protegida (familia/edad/nacionalidad/…). Solo la necesidad transaccional que la persona
  **declaró** (precio/zona/ficha/inversión/visita). El motor lo bloquea por construcción.
- **Humano cierra:** en Fase 1 la salida es una **sugerencia para el corredor**, no un envío autónomo.

---

## 4. Arquitectura y estado del terreno (auditado 2026-07-06)

**Ya existe y se reutiliza:**
- Motor de intención (`app/intencion.py`) — embudo de 9 estados, score explicable, determinista.
- Handoff al corredor (`tool_connect_with_broker` → `registrar_handoff`) con notificación email+push.
- Persistencia de conversación (checkpointer de LangGraph en Postgres).
- Canal de salida email (Resend, `app/notifications.py`) y Web Push — hoy solo **reactivos**.

**Faltaba (lo que abren las fases):**
- Marca de **última interacción** por lead (no había timestamp de negocio) → **Fase 1**.
- Un **scheduler** para disparar por inactividad → **Fase 2**.
- Un canal **outbound real** (WhatsApp Business API) para que el agente escriba primero → **Fase 3**.

---

## 5. Las tres fases

### Fase 1 — El cerebro + la base (esta entrega) · *humano en el lazo, sin autonomía*
1. **`app/reenganche.py`** — motor puro y determinista (patrón API-first, como `intencion`/`inversion`):
   - `clasificar_frescura(horas_inactividad)` → `activo | dormido | frio_profundo | desconocida`.
   - `evaluar_reenganche(...)` → decide **si** reenganchar y **con qué ángulo/mensaje**, o `None`
     (el silencio por defecto). Reglas: nunca a leads calientes/en handoff; nunca demasiado pronto;
     nunca sin una señal transaccional a la que aportar valor; anti-repetición.
2. **`intencion.py`** — activa el estado `dormido` vía parámetro opcional `horas_inactividad`.
3. **Persistir última interacción** — tabla `lead_actividad` (runtime `ensure_*`), actualizada en
   cada turno de un QR-lead.
4. **Superficie en el CRM** (`/assets/mine/leads`) — cada lead trae `frescura` y, cuando hay disparo
   genuino, una **`reenganche.sugerencia`** que el corredor puede enviar (por el `wa.me` o su canal).

> **Qué NO hace la Fase 1 (a propósito):** no envía nada solo. La regla del "dato NUEVO" (novedad con
> fecha de verificación) se gatilla parcialmente aquí (usa el estado verificado actual del inmueble
> como refuerzo) y se completa en Fase 2 con timestamps de verificación por dato.

### Fase 2 — El disparador proactivo
- **`ultima_interaccion` + timestamps de verificación por dato** → detectar "novedad desde la última
  vez que habló". Un **Render Cron Job** revisa leads `dormido` contra novedades verificadas y, solo
  si hay valor genuino, dispara reenganche por **email** (Resend, ya listo). Activa `returning`
  (dormido que vuelve). Decisión de negocio: ¿auto-envío o cola de aprobación del corredor?

### Fase 3 — El canal que convierte en LatAm
- **WhatsApp Business API** (Twilio o Meta Cloud API) para outbound real. Decisión de **costo por
  conversación + aprobación de plantillas de Meta** — es de negocio, no solo técnica. Gate explícito
  de Carlos antes de construir.

---

## 6. El motor de decisión (contrato de Fase 1)

`evaluar_reenganche(*, intencion, horas_inactividad, direccion, novedades, horas_desde_ultimo_reenganche)`
devuelve `None` **salvo** que se cumplan todas:
- El lead **no** está caliente ni en handoff (esos ya los tiene el corredor).
- Tuvo **enganche real** (una señal transaccional: precio/ficha/zona/inversión/visita/comparar).
- **No** es demasiado pronto (`horas_inactividad ≥ HORAS_MIN_REENGANCHE`, hoy 48h).
- **No** se le reenganchó hace poco (anti-repetición, hoy ~5 días).

Si procede, elige el **ángulo = lo que la persona mostró que le importa** (nunca clase protegida) y
compone un mensaje **valor-primero**, honesto y sin presión ("por si te sirve", "sin compromiso").

---

## 7. Métrica (North Star de esta pieza)

No "mensajes enviados" (vanity), sino **leads dormidos revividos con valor**:
`% de leads dormido→activo tras un reenganche por valor`, medido en el flujo del propio corredor
(coherente con la métrica de lift de intención del piloto Linden — nunca espejo de cifras ajenas).
Guardarraíl ético: tasa de opt-out / "no me escribas" por debajo de un umbral (si sube, el disparador
está empujando, no aportando).

---

## 8. Preguntas abiertas (a zanjar con el piloto)

- Umbrales reales de `dormido` / anti-repetición (hoy 48h / 5d — placeholders a calibrar).
- ¿El reenganche de Fase 2 se auto-envía o entra a una cola que el corredor aprueba? (canon: humano cierra).
- ¿Qué cuenta como "novedad verificada" suficiente para romper el silencio? (ficha completada,
  caminabilidad heurístico→OSM real, nuevo POI propio, cambio de precio, curación de Catastro Vivo…).
- Fase 3: ¿Twilio vs. Meta Cloud API? Costo por conversación en EC/MX.

---

## Changelog (iterar aquí)

- **2026-07-06 — v0.1** — Doc ancla creado. Arranca Fase 1 (motor puro `reenganche.py`, activación de
  `dormido`, tabla `lead_actividad`, sugerencia en el CRM). Disparador por valor definido; autonomía
  y WhatsApp diferidos a Fase 2/3.
- **2026-07-06 — v0.2** — Fase 1 mergeada (PR #75) + **rediseño visual del CRM** (KPIs, funnel rail,
  conversación destilada inline).
- **2026-07-06 — v0.3 — Fase 2 (cron DENTRO de la app, sin WhatsApp)** — `app/reenganche_cron.py`:
  tarea de fondo en el `lifespan` (plan `starter` de Render no duerme) que barre leads dormidos, corre
  el motor Fase 1 y **avisa al CORREDOR** por los canales que la app ya tiene (Web Push + email/Resend).
  Endpoint manual `POST /assets/reenganche/scan` para piloto/demo. Config por entorno
  (`REENGANCHE_CRON_ENABLED|INTERVAL|LIMITE`).
  - **Hallazgo honesto de canal (importante):** los leads dormidos-no-calientes **no dejaron contacto
    propio** (no pidieron corredor → sin email ni push del comprador). Por eso el cron avisa al
    **corredor**, no al comprador. Alcanzar al comprador directo exige **capturar su contacto en el
    chat** o **WhatsApp** — ese es el verdadero contenido de una futura Fase 3, no "otro canal".
  - Supuesto operativo: una sola instancia web. El anti-repetición (`reenganche_enviado_en`) hace
    inocuo un doble-barrido si algún día se escala horizontalmente.
  - **Pendiente de decisión (piloto):** ¿auto-enviar el mensaje al comprador cuando SÍ tengamos su
    canal (contacto capturado), o mantener siempre el humano-envía? Calibrar intervalo (hoy 6 h).
- **2026-07-06 — v0.4 — Fase 3 (alcanzar al COMPRADOR directo, con la app)** — captura del canal del
  comprador **con consentimiento explícito**, usando lo que la app ya tiene (Web Push/VAPID + email/Resend).
  - `lead_actividad` gana `lead_email`, `lead_telefono`, `lead_push` (jsonb), `consent_reenganche_at`.
  - Endpoint público `POST /api/v1/chat/lead-contacto` (lo llama el comprador, sin auth): guarda su
    canal + consentimiento ligado a su sesión de QR.
  - Frontend: botón **"🔔 Avísame de novedades verificadas"** en el chat del comprador (reusa
    `ensurePushSubscription` + el service worker existentes).
  - Cron: si el comprador dejó canal + consentimiento y `REENGANCHE_AUTO_LEAD` (default on), el mensaje
    de valor le llega **a ÉL directo** (email/push, deep-link a `/a/{id}`); si no, se avisa al corredor
    (Fase 2). Sin WhatsApp: es el propio canal de la app.
  - **Sigue honesto:** el comprador recibe SOLO lo que pidió recibir (opt-in), y solo cuando hay dato
    verificado que le calza (motor Fase 1). WhatsApp/SMS queda como canal adicional futuro (el teléfono
    capturado lo habilita, y de momento lo puede usar el corredor a mano).
