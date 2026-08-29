# DECISIONES ABIERTAS · VIGENTES

**Actualizado:** 29 de agosto de 2026
**Qué es:** el lugar donde viven las decisiones que **no puede tomar el arquitecto** y que todavía no
están cerradas.

> ⚠️ **Esto NO es un backlog técnico.** Ninguna entrada de este archivo autoriza código, contratos,
> schemas ni estimaciones. Una decisión sale de aquí cuando el fundador la cierra; entra al backlog
> cuando el Execution Plan vigente la incorpora. Son dos pasos, no uno.

**Relación con el `05_OPEN_DECISIONS_FOR_FOUNDERS`:** aquel documento es un **artefacto histórico de
auditoría** (agosto 2026), no está versionado en el repositorio y **no se reescribe**. Varias de sus seis
decisiones ya se cerraron y viven hoy en `00_START_HERE_CLAUDE_CODE.md` §6. Este archivo es el lugar
vigente para lo que sigue abierto.

---

## Decisiones abiertas

### D-A · ¿Qué capacidad institucional entra primero, después del benchmark de Real Estate?

**La pregunta.** Cuando el benchmark de la decisión de compra muestre qué afirmaciones materiales el
sistema no puede sostener, habrá una lista de candidatas: derechos y título, regulación urbanística,
rango de valoración, riesgo, TCO. Sólo una puede ser la primera.

**Por qué no se decide ahora.** Decidirla antes del benchmark es decidirla sin el dato que la responde:
cuál de esas ausencias **cambió** una decisión y cuál sólo la decoró.

**Qué evidencia haría falta.** El resultado del benchmark de decisión, con el desglose de qué claim
faltante fue material.

**Qué NO autoriza.** Nada. Ninguna de las candidatas tiene contrato, harness ni backlog.

---

### D-B · ¿Cómo definimos que una ciudad o jurisdicción está "cubierta"?

**La pregunta.** "Cobertura" no puede significar "tenemos muchos datos". La formulación de trabajo es:
una ciudad está cubierta cuando podemos sostener **una clase definida de decisiones** con cobertura,
evidencia, freshness y límites medibles. Falta convertir eso en un umbral concreto.

**Por qué no se decide ahora.** Sin una segunda ciudad y sin la primera clase de decisión cerrada, el
umbral se fijaría en el vacío y se cumpliría por construcción.

**Qué evidencia haría falta.** Una clase de decisión sostenida de punta a punta en Quito, con sus huecos
medidos.

**Qué NO autoriza.** Abrir una segunda ciudad. Quito primero.

---

### D-C · ¿Cómo representamos la autoridad y la aplicabilidad de una fuente local?

**La pregunta.** Dos fuentes locales pueden contradecirse y no valen lo mismo. Un geoservicio municipal,
un certificado del Registro de la Propiedad, un perito calificado y una observación de campo tienen
autoridad distinta sobre ámbitos distintos. Falta decidir cómo se representa eso y quién resuelve el
conflicto.

**Por qué no se decide ahora.** Hoy hay **una** capacidad con fuentes reales. Un modelo de autoridad
diseñado con un solo caso se diseña sobre ese caso.

**Qué evidencia haría falta.** Al menos dos fuentes que se contradigan de verdad sobre el mismo sujeto, y
el registro de cómo se resolvió.

**Qué NO autoriza.** Un `evidence graph`, una ontología de fuentes ni campos nuevos en los contratos V0.
La disciplina que sí aplica hoy —procedencia, fecha, metodología, `insufficient_evidence`— ya es canon y
no espera a esta decisión.

---

### D-D · ¿Qué capacidad demuestra primero reutilización fuera de una sola transacción?

**La pregunta.** La hipótesis de infraestructura dice que una capacidad debería servir a más de un flujo.
Falta elegir cuál se pone a prueba primero: `Valuation`, `Risk`, `Place/Mobility` o `Jurisdiction`.

**Por qué no se decide ahora.** Elegir la candidata antes de tener una segunda clase de decisión es
elegir la respuesta antes de la pregunta.

**Qué evidencia haría falta.** Una segunda clase de decisión con demanda real —no hipotética— que
comparta capacidad con la primera.

**Qué NO autoriza.** Construir ninguna de las cuatro.

---

### D-E · ¿Qué métrica define que una segunda ciudad reutiliza *suficientemente* el core?

**La pregunta.** El `reuse ratio` y el coste de integración de una jurisdicción nueva son las métricas
propuestas. Falta el umbral: ¿qué número separa "hay un core reutilizable" de "hay dos productos"?

**Por qué no se decide ahora.** Fijar el umbral **después** de ver el resultado es fijarlo para aprobar.
Fijarlo **antes** de tener el método de medición es fijarlo sin unidades. El método está en
`canon/CONTEXT_CAPABILITY_ARCHITECTURE_0.1.md` §9; el umbral falta.

**Qué evidencia haría falta.** El método de medición aplicado a un caso real, aunque sea pequeño.

**Qué NO autoriza.** Una segunda ciudad.

**Nota de disciplina.** Mientras esta cifra no exista, "reutilizable" se escribe como hipótesis en
cualquier documento, deck o conversación con un tercero.

---

### D-F · ¿Qué condición justifica extraer una capacidad lógica como microservicio?

**La pregunta.** Los siete criterios candidatos están escritos (`CONTEXT_CAPABILITY_ARCHITECTURE_0.1.md`
§6): carga o latencia propia, aislamiento regulatorio o de seguridad, SLA distinto, ownership separado,
tecnología especializada, escalado independiente, reutilización externa real. Falta decidir si basta uno
o hacen falta varios, y quién lo autoriza.

**Por qué no se decide ahora.** No hay ningún candidato a extracción. La decisión no bloquea nada.

**Qué evidencia haría falta.** Un componente que cumpla al menos uno de los siete **con datos medidos**.

**Qué NO autoriza.** Ningún microservicio. El monolito debe volverse más modular, no distribuirse.

---

## Decisiones de proceso pendientes

### P-1 · ¿Entran al repositorio los documentos de auditoría `01`–`05`?

**Estado: NO por ahora** (decisión del 29-ago-2026). Se tratan como evidencia histórica y el bootstrap
ya no los requiere. La decisión se puede revisar; hasta entonces, no se buscan ni se citan como plan.

### P-2 · ¿Entran al `canon/` las referencias estratégicas (Nexor, Enter, Zillow, HomeSelf, Agentic Commerce, tesis de confianza delegada)?

**Estado: abierto.** Hoy viven fuera del repositorio y la Declaración las registra con identificador
`INT-`. Si alguna se vuelve necesaria para trabajar, entra por la misma vía que el resto del canon: copia
literal en `canon/`, referenciada desde `INDEX.md`.

---

## Deuda documental · no bloqueante

### DD-1 · Clasificar las menciones de `MCP` en `docs/`

**Qué es.** La auditoría de coherencia del 29-ago-2026 encontró ocho archivos con la sigla `MCP` y no los
clasificó uno por uno. El muestreo indica que son **tooling de Claude Code y referencias técnicas**, no
una API MCP de producto ni una autorización de Partner Layer.

**Por qué no bloquea.** El canon no necesita cero menciones ambiguas. Necesita que una sesión nueva no
pueda inferir mal qué está autorizada a construir — y eso ya está cerrado en tres lugares que sí mandan:
`00_START_HERE` §7, `canon/CONTEXT_CAPABILITY_ARCHITECTURE_0.1.md` §5 y
`canon/PROJECT_AI_MASTER_STRATEGY_0.3.md` §13, los tres prohibiendo MCP, A2A, API externa y Partner Layer
antes de su gate.

**Si alguien la retoma:** clasificar cada mención como CURRENT CANON · HISTORICAL SNAPSHOT · REFERENCE ·
CONTRADICTION, y sólo anotar las de la última categoría. No reescribir las demás.
