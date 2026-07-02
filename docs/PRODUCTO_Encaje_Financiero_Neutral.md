# Encaje Financiero Neutral — Documento de Producto y Estrategia B2B

> **Contexto AI · Quito · 2026-07-02**
> La conveniencia de Habi, sin su captura. Feature de simulación de crédito neutral + estrategia B2B vs B2C.
>
> *Producido con investigación multi-agente: marco Expedia (comparables verificados: Rocket–Redfin $1.75B, Zillow, Creditas, QuintoAndar), teardown de Habi/AVI Capital (2 webinars) y verificación adversarial Fair Housing. La v1 del feature fue **tumbada** por la revisión adversarial (hacía steering financiero) y este doc adopta las 7 correcciones obligatorias.*

---

## 1. Tesis ejecutiva

El *wedge* de Contexto es ofrecer **la conveniencia de Habi** (saber en 30 segundos qué puedes pagar, qué te aprobarían, y cómo sube tu aprobación si bajas deuda) **desde la neutralidad estructural que Habi no puede tener**: varios bancos + Mutualistas + BIESS compiten por cada lead calificado, y Contexto es el **único dueño del cliente y del dato**.

Habi es el mejor benchmark de **ejecución** (velocidad, certidumbre, herramienta gratis para el corredor, método de embudo) y el peor de **estructura** (vendedor + prestamista + portal a la vez; crédito cautivo a inventario propio; balance propio de entrada).

**La regla que gobierna todo el documento:** donde Habi amarra al cliente a *su* plata y *su* casa, Contexto orquesta a *varios* prestamistas compitiendo por un lead neutral.

- **Ingreso principal y foso:** la **suscripción de corredores** (SaaS).
- **El crédito es un feature de conversión** co-brand, *no* la línea de ingreso.
- **Neutralidad + Fair Housing duro + inventario verificado = recurso escaso no-clonable.** Habi no puede replicarlo sin desmontar su iBuyer/balance.

---

## 2. Posicionamiento vs Habi (el wedge)

Habi solo puede responder una pregunta: **"¿alcanza *mi* plata para *mi* casa?"** — porque es simultáneamente vendedor, prestamista y portal, con neutralidad cero. El cliente nunca sabe si el "encaje" o la tasa que ve es lo mejor para *él* o para el balance de Habi.

Contexto responde **dos preguntas que Habi estructuralmente NO puede**:
1. **¿Qué casa encaja con *tu* vida?** (Mapa Vivo + motor de encaje + entorno real conflado, sin proxies protegidos).
2. **¿Qué prestamista encaja con *tu* perfil?** (marketplace donde compiten N bancos + BIESS mostrado honestamente aunque no se monetice).

> **Posicionamiento de una línea:** *"La conveniencia de Habi, sin dueño oculto. Contexto no te vende una casa ni te presta plata: te muestra la verdad del entorno y hace que los prestamistas compitan por ti."*

La neutralidad no es cortesía ética: es un activo no-clonable, porque **en el instante en que Habi presta de su balance, pierde la capacidad de ser neutral.** Contexto puede ser Habi para el cliente; Habi no puede ser Contexto sin desmontar su negocio.

**Marco Expedia aplicado:** en proptech+crédito lo escaso es la *demanda de alta intención + inventario verificado*; el crédito es *commodity* (bancos + BIESS compiten por prestar). Prueba en dinero: en 2025 **Rocket (un prestamista) pagó ~$1.75B por Redfin (un portal)** — el capital compró la demanda, no al revés. Contexto controla el cuello de botella escaso; no lo regala volviéndose lead-gen tonto.

---

## 3. Teardown de Habi

### 3.1 Qué COPIAR (ejecución)
- **Aprobación con fricción casi cero:** replicar la magia UX de "con 3 datos sé qué puedes pagar", pero como **pre-calificación multi-banco** ("con tu presupuesto veo con cuáles de N bancos + BIESS calificas y por cuánto"). *Copias la magia; cambias el dueño del resultado.*
- **Certidumbre como beneficio:** Habi vende tasa garantizada + desembolso rápido amarrando al cliente a su balance. Contexto vende la misma certidumbre **haciendo competir balances ajenos** ("te traigo ofertas en firme de varios bancos, comparables lado a lado, en X días").
- **Herramienta gratuita de pre-calificación para el corredor** (el caballo de Troya): darla como feature de la suscripción, pero **neutral** ("este perfil encaja mejor con Banco A por tasa, con BIESS por plazo"). Hace ver mejor al corredor ante su cliente = adicción.
- **Simulador de "estirar presupuesto"** bajando deuda ("si bajas $200 de cuota de tarjetas, entran más opciones a tu alcance").
- **Educar al corredor** sobre cómo piensan los bancos (score, DTI con cuota ≤40% del ingreso, consistencia). Contexto educa *mejor*: enseña a leer a *varios* prestamistas.
- **Método comercial completo:** embudo inverso (100→50→25→6→2), metas de ingreso, foco en un nicho/zona, métricas diarias, SLA por etapa, 6 intentos de contacto, matemática de CAC, ~10% de comisión en marketing.
- **Agentes de IA en las etapas frías** (interesado→calificado→agendado); humano cierra visita→oferta. Contexto ya tiene la mitad construida (el agente de chat + Mapa Vivo).

### 3.2 Qué NO copiar (estructura)
- **Crédito cautivo a inventario propio** — *línea roja absoluta.* Habi financia solo "los inmuebles de AVI" con precio preferencial. Atar crédito a inventario destruiría el motor de encaje y el Catastro Vivo (pasaría de verificado-neutral a vitrina-propia).
- **Ser vendedor + prestamista + portal a la vez** — neutralidad cero; colisiona de frente con Fair Housing y con la promesa de verdad del Mapa Vivo.
- **Internalizar el balance de entrada** — capital-intensivo, cíclico, riesgo de crédito/fondeo. Solo como **opcionalidad tardía** (vía FIDC/fintech, trayectoria Creditas) si el margen resulta grande y tras conservar cliente+dato.
- **Convertir al corredor en "broker financiero" cautivo** — el kickback mono-banco de Habi (1% para que empuje a AVI) es un incentivo para vender el producto de Habi, no el mejor para el cliente.
- **Reordenar/atenuar inventario según el bolsillo** — *la falla que tumbó el diseño v1.* Es steering financiero encubierto y disparate impact.
- **Monetizar el orden del comparador de prestamistas** — el día que un banco pague por "posición", el comparador es pay-to-play y Contexto es lead-gen tonto.

---

## 4. El feature "Encaje Financiero"

### 4.1 Concepto
Cada tarjeta de inmueble puede mostrar, **además** del "% de encaje con tu intención" (vida/entorno), un **"% de encaje financiero"** que responde una sola pregunta: *"¿este inmueble entra en mi bolsillo con condiciones reales de mercado?"*. No es un score de riesgo del usuario ni una nota moral.

> **CORRECCIÓN CENTRAL (la revisión adversarial tumbó la v1 con `aguanta:false`):** el encaje financiero es una **capa opt-in puramente informativa** — un dato más en la tarjeta — que **NUNCA reordena, filtra ni atenúa el inventario por defecto.** El orden primario del Mapa Vivo sigue siendo el encaje de vida, y el universo de inmuebles mostrado es **idéntico** con o sin dato financiero. El usuario ve el mismo mapa que vería sin haber ingresado su presupuesto. Ocultar/resaltar por presupuesto solo ocurre bajo un *toggle explícito activado por el usuario* (apagado por default) — la decisión es del usuario, jamás del sistema.

Esto convierte el motor de encaje en el activo escaso (demanda de alta intención) sin volvernos vendedor+prestamista como Habi, y sin caer en steering.

### 4.2 Inputs y outputs
**Inputs (estimación, client-side, sin buró):**
1. Ingreso mensual del hogar — *"Suma lo que entra al hogar cada mes."*
2. Cuota mensual de otras deudas — *"Lo que ya te descuentan al mes."* (habilita el simulador de estirar presupuesto)
3. Ahorro disponible para la entrada — *"Cuánto tienes para el pago inicial."*
4. *(opcional)* "¿Aportas al IESS? ¿Cuántos meses seguidos?" — habilita el carril BIESS honestamente (13 aportes seguidos si eres dependiente).

**NO se pide en esta capa:** cédula, número de tarjeta, buró de crédito, empleador, consulta a Experian/Equifax. Se separa deliberadamente la **estimación** (client-side, sin dato sensible, sin huella) de la **pre-aprobación** (con consentimiento explícito).

**Outputs (versionados, no hardcode):**
- **Capacidad de cuota** = (ingreso_hogar × DTI_max) − cuota_deudas_actuales. DTI por carril (banca privada 30–35%, tope prudencial ~40%).
- **Monto aprobable** = valor presente de esa cuota dada tasa y plazo por carril (BIESS ~2,99–4,99% a 25–30 años; bancos privados tasa mayor a menor plazo).
- **Aporte inicial requerido** = precio − monto_aprobable_max, contra el ahorro declarado.
- **"% de encaje financiero"** = función de dos brechas (cuota + entrada), **gradual y no binaria**; se recalcula por inmueble (tasa/plazo/LTV cambian con precio y carril). *Solo informativo en la tarjeta: no toca el orden del mapa.*

### 4.3 Estados y microcopy
- **Estado 0 — Sin dato:** medallón gris. *"Encaje financiero — añade tu presupuesto."* CTA: *"Calcula qué puedes pagar (30 seg, sin buró)."* No se atenúa ningún inmueble.
- **Estado 1 — Estimación:** medallón con color y %, etiqueta fija **"estimación"** + info. Fila en el detalle: *"Cuota estimada $X/mes · Entrada aprox $Y · Te alcanzaría ~$Z de crédito."*
  - Banner de honestidad *siempre* visible: *"Esto es una estimación con datos que TÚ ingresaste y tasas públicas de referencia. No es una oferta de crédito ni una aprobación."*
  - Confianza junto al formulario: *"Hacemos la estimación en tu dispositivo. No consultamos tu buró ni pedimos tu cédula todavía — eso solo pasa si TÚ decides pedir una pre-aprobación real."*
- **Estado 2 — Pre-aprobado por un prestamista** (solo si el usuario lo pidió y un prestamista respondió): check + sello *"Pre-aprobado por [N] prestamistas."* *"[Banco A] y [BIESS] indicaron un monto pre-aprobado. Sujeto a verificación y avalúo."* El rótulo "estimación, no oferta" **permanece hasta carta formal**.
- **Regla de microcopy:** nunca mostrar un número pre-aprobado sin nombrar **quién lo emitió y su vigencia**.
- **Marca de honestidad aspiracional** (alto encaje de vida + bajo encaje financiero): *"Encaja con tu vida, aprieta el bolsillo"* — se muestra **a propósito** para no esconder aspiración ni sesgar hacia lo barato.

### 4.4 Presentación neutral de prestamistas + handoff
Pantalla **"Cómo financiarlo"** dentro del inmueble: tabla comparadora, una fila por prestamista (bancos + Mutualistas + **BIESS, mostrado aunque no se monetice**). Columnas: tasa referencial, cuota estimada, plazo máx, entrada, tiempo a desembolso, requisitos clave.

- **El orden se fija por una función PÚBLICA y VERSIONADA de variables del *usuario*** (costo total del crédito, cuota, plazo, tiempo) — **nunca por fee del prestamista**. Selector: *"ordenar por: cuota más baja / menor tasa / más rápido."*
- Si hay monetización: **success-fee fijo e idéntico por prestamista**, revelado en pantalla, que **no altera el ranking**. Contenido pagado (si lo hubiera) va **fuera** del ranking, rotulado "Patrocinado".
- Nota al pie: *"Contexto no presta dinero ni cobra por posicionar a un prestamista. Ganamos con la suscripción de corredores, no con tu crédito."*

**Handoff (subasta invisible):** al pulsar "Pedir pre-aprobación real" → consentimiento granular: *"Vamos a enviar tu solicitud a los prestamistas que elijas para que compitan por tu crédito. Compartimos [ingreso, deuda declarada, monto buscado]. NO compartimos tus datos de contacto hasta que TÚ aceptes una oferta."*
- El usuario elige 1..N prestamistas (multi-check, no exclusivo).
- Contexto genera un **lead anonimizado por token** (sin teléfono/email/cédula), fija SLA, recibe ofertas estructuradas mostradas **lado a lado dentro de Contexto**; solo al aceptar una se libera el contacto a *ese* prestamista.
- **El banco responde a través de Contexto, nunca contacta al cliente directo.**
- **El historial del Mapa Vivo (intención/entorno) JAMÁS se comparte con el prestamista.**

---

## 5. Reglas Fair Housing duras (gate de lanzamiento, no disclaimer)
1. El motor usa **solo variables económicas** (ingreso, deuda, ahorro, precio). Jamás edad, género, composición familiar, barrio de origen, nacionalidad ni proxies.
2. **Motor ciego a geografía:** tasa/plazo/DTI/LTV se calculan solo desde perfil económico + precio. **Prohibido que barrio/zona/código postal entre al cálculo** (evita redlining algorítmico).
3. **Prohibido reordenar, filtrar, jerarquizar o atenuar** el inventario según capacidad de pago. Usar el bolsillo para decidir qué casas/barrios ve cada usuario reproduce segregación residencial = *disparate impact*, aunque ninguna variable protegida entre al modelo.
4. El encaje financiero es **capa opt-in informativa**; ocultar/resaltar por presupuesto solo bajo toggle explícito del usuario (default apagado), con aviso: *"Estás ocultando N inmuebles; puedes ver todo cuando quieras."*
5. El **orden del comparador** se rige por función pública, versionada y auditable de variables del usuario; nunca por fee del prestamista.
6. **Estimación sin huella vs pre-aprobación con consentimiento:** al pedir pre-aprobación (a) se envía dato mínimo, (b) Contexto = único *data controller* con contrato de encargado que prohíbe re-uso/marketing del banco, (c) el banco responde vía Contexto, (d) el historial del Mapa Vivo nunca se comparte.
7. **Incentivo al corredor agnóstico al banco:** se paga por *calificar/encajar bien* (lead que avanza), no por dirigir a un prestamista. La herramienta muestra siempre ≥2 opciones + BIESS; prohibido un CTA "enviar solo a Banco X".
8. **Gradiente, nunca bloqueo:** la brecha financiera se muestra como gradiente con acciones (bajar deuda, carril BIESS a mayor plazo), jamás como medallón bloqueante ni descalificación.
9. **Auditoría cableada (P4):** log versionado de inputs/outputs del scoring + test recurrente de disparate impact (distribución de inmuebles/zonas mostrados entre cohortes) como **gate de lanzamiento**. Sin test verde, no se construye. La auditabilidad es parte del foso.

---

## 6. Playbook de brokers (profundizar el foso denso-local)
- Empaquetar la **herramienta gratuita de pre-calificación neutral** como feature estrella de la suscripción.
- Incluir el **método comercial de Habi** como contenido (embudo inverso, metas, nicho, métricas, SLA, 6 intentos, CAC, ~10% en marketing).
- **Educación** sobre criterios de *varios* prestamistas (menos leads muertos = más cierres = más renovaciones).
- **IA en las etapas frías**; el corredor humano cierra. Aprovecha el agente de chat + Mapa Vivo ya construidos.
- Incentivo **solo por calificar/encajar bien**, agnóstico al prestamista. La herramienta cablea la neutralidad: siempre ≥2 opciones + BIESS; sin botón "enviar solo a Banco X".
- El corredor independiente sigue siendo el **"gerente de la transacción"** y el cliente del producto; Contexto adopta la *intensidad*, no la captura vertical.

*Esto ata al corredor a Contexto y combate el **multi-homing** (que liste el inventario verificado en 5 portales) — la mayor amenaza al foso, que es denso-local, no winner-take-all nacional.*

---

## 7. Estructura de negocio recomendada
**CO-BRAND MARKETPLACE DE CRÉDITO NEUTRAL** (estilo QuintoAndar/La Haus).
- **Ingreso principal y foso:** suscripción de corredores (SaaS del piloto).
- **Crédito = feature de conversión:** Contexto retiene marca + cliente + dato y hace competir a varios bancos + Mutualistas + BIESS por cada lead calificado.
- **Contexto = único data controller** (contrato de encargado con cada banco; prohibición de re-uso/marketing sobre el lead).
- **Nunca** exclusividad legal con un banco; **nunca** ceder el CRM ni el cliente; **BIESS** honesto aunque no se monetice.
- **Monetización del crédito (si existe):** success-fee fijo e idéntico por prestamista, revelado, que no altera el ranking.
- **Opcionalidad tardía (no punto de partida):** migrar a balance propio vía FIDC/fintech (trayectoria Creditas) *solo* si el margen resulta grande y tras conservar cliente+dato.

*Habi es el anti-patrón estructural: no ser vendedor+prestamista+portal, no atar crédito a inventario, no convertir al corredor en broker financiero cautivo.*

---

## 8. Líneas rojas
- El encaje financiero **nunca** reordena, filtra ni atenúa el inventario por defecto.
- El orden del comparador **nunca** depende de un fee del prestamista.
- **Nunca** exclusividad legal con un banco; **nunca** ceder el CRM ni el cliente.
- Contexto = único data controller; el historial del Mapa Vivo **jamás** se comparte; el banco responde vía Contexto.
- **Nunca** atar el crédito a inventario propio (destruye el motor de encaje).
- **Nunca** ser contraparte de la transacción (consejero neutral, no vendedor ni prestamista).
- **Nunca** incentivar al corredor por dirigir a un prestamista único.
- Ningún número pre-aprobado sin emisor + vigencia; rótulo "estimación, no oferta" hasta carta formal.
- No consultar buró ni pedir cédula en la capa de estimación.
- BIESS siempre con sus ventajas reales aunque no deje ingreso.

---

## 9. Secuencia por etapas
- **Etapa 0 (piloto actual):** consolidar Catastro Vivo verificado + Mapa Vivo con entorno conflado + motor de encaje de vida con guardrail Fair Housing. *El activo escaso base.*
- **Etapa 1 — Encaje financiero como estimación client-side:** 3–4 inputs sin buró, motor de capacidad/DTI/monto/entrada versionado, medallón informativo (Estados 0 y 1). **No tocar el orden del mapa.** Validar honestidad del microcopy con usuarios.
- **Etapa 2 — Herramienta gratuita del corredor (neutral):** pre-calificación + mapa de opciones ≥2 prestamistas + BIESS + simulador de estirar presupuesto + método comercial. Sube el valor de la suscripción.
- **Etapa 3 — Comparador multi-prestamista dentro del inmueble:** tabla con función de orden pública/versionada, BIESS honesto, nota de neutralidad. Todavía sin handoff.
- **Etapa 4 — Handoff / subasta invisible:** consentimiento granular, leads anonimizados por token, SLA, ofertas lado a lado dentro de Contexto, liberación de contacto solo al aceptar. Contratos de encargado con cada banco. Estado 2. Fijar el modelo de ingreso (success-fee fijo idéntico) sin alterar ranking.
- **Etapa 5 (opcionalidad tardía, condicional):** evaluar balance propio vía FIDC/fintech *solo* si el margen resulta grande y con cliente+dato retenidos.

---

## 10. Métricas de éxito
- **Foso:** retención/renovación de la suscripción de corredores; NRR; nº de corredores activos con Catastro Vivo verificado.
- **Activación:** % que completa los inputs de estimación (sin buró); tiempo a primera estimación (<30 seg).
- **Calidad del lead (embudo estilo Habi):** conversión interesado→…→oferta; reducción de leads muertos por corredor.
- **Neutralidad demostrable:** nº de prestamistas que compiten por lead (objetivo ≥3 incl. BIESS); % de leads con ≥2 ofertas comparadas antes de aceptar.
- **Certidumbre:** tiempo mediano solicitud→oferta en firme; dispersión de tasas/cuotas (evidencia de competencia).
- **Retención del activo:** % de solicitudes en que Contexto sigue siendo único data controller y el banco no contacta directo (objetivo 100%); fugas de contacto = 0.
- **Fair Housing:** funciones de orden versionadas/logueadas; auditorías sin disparate impact; **0 reordenamientos por bolsillo**.
- **Crédito como feature (no P&L):** % de leads que aceptan oferta, medido como *asistente de conversión de la venta inmobiliaria*.

---

## 11. Riesgos abiertos
- **Modelo de ingreso del crédito sin fijar:** definir el success-fee fijo idéntico sin caer en pay-to-play (trampa Expedia).
- **Contratos de encargado con bancos ecuatorianos:** viabilidad de que respondan vía Contexto y no re-usen/contacten. Sin esto, la neutralidad es papel mojado.
- **Fuente de buró propia** para la pre-aprobación (no depender de Experian Advance como Habi); filtro Fair Housing en cualquier consulta.
- **Parámetros de mercado versionados** (DTI por carril, tasas BIESS/bancos, LTV): gobernanza y actualización; hardcode = estimaciones erróneas.
- **Disparate impact regulatorio:** proceso de auditoría formal + evidencia logueada para defenderse.
- **Incentivos con el corredor:** que el pago por calificar bien no derive de facto en empuje a un banco (p. ej. el que cierra más rápido).
- **BIESS honesto vs conversión monetizable:** verificar que la suscripción absorbe el costo de mostrar BIESS sin presión a esconderlo.
- **Adopción del piloto:** toda la tesis depende de que la suscripción de corredores sea un foso real. Validar disposición a pagar antes de invertir pesado en el stack de crédito.

---

### Apéndice — Nota metodológica
Este documento integra tres pasadas de investigación multi-agente (jul 2026):
1. **Marco Expedia** — B2B infraestructura invisible vs marca de consumo; fact-check web (Q1 2026: B2B +22% vs consumidor +10%; margen y "no CAC" matizados).
2. **Contexto B2B vs B2C** — comparables verificados (Rocket–Redfin $1.75B, Rocket–Mr.Cooper $14.2B, Zillow ~7% crédito, Creditas internalizó, QuintoAndar/La Haus marketplace neutral, BIESS Ecuador).
3. **Teardown de Habi + diseño del feature** — verificación adversarial que tumbó la v1 (steering financiero) y forzó las 7 correcciones aquí adoptadas.
