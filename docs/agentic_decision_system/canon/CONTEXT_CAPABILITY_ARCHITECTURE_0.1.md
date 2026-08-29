# CONTEXT CAPABILITY ARCHITECTURE 0.1
## Restricciones de compatibilidad futura · Contexto AI

**Fecha:** 29 de agosto de 2026
**Tipo:** documento de arquitectura (design doc / ADR) · **no es un plan de implementación**
**Deriva de:** `CONTEXTO_AI_DECLARACION_FRONTERA_0.1_2026-08-29.md` y `PROJECT_AI_MASTER_STRATEGY_0.3.md`
**Autoridad:** ninguna sobre ejecución. Ver `../INDEX.md` §2.

---

## 0. Propósito y regla de lectura

Este documento existe para **convertir una declaración estratégica en restricciones de diseño**, sin
autorizar ninguna construcción. Su pregunta es:

> Si algún día Contexto compone capacidades de contexto, ¿qué decisiones tomadas hoy lo harían
> innecesariamente caro o imposible — y cuáles hay que evitar sin pagar complejidad ahora?

Cada afirmación lleva una etiqueta y la etiqueta manda:

| Etiqueta | Significado |
|---|---|
| **`CURRENT / VERIFIED`** | Existe hoy en el repositorio y está verificado |
| **`DESIGN CONSTRAINT`** | Regla vinculante para el trabajo que ya está autorizado. No añade scope; condiciona cómo se hace lo que ya se iba a hacer |
| **`FUTURE HYPOTHESIS`** | Puede llegar a existir. **No autorizado.** No entra a backlog, ni a schema, ni a estimación |
| **`OUT OF CURRENT SCOPE`** | Explícitamente prohibido en esta etapa |

> ⚠️ **Nada en este documento autoriza código.** Un elemento pasa de `FUTURE HYPOTHESIS` a construible
> únicamente cuando el Execution Plan vigente lo incorpora y su gate lo permite.

---

## 1. `Context Selector` — selector de contexto material

**`FUTURE HYPOTHESIS` con precedente ya escrito.**

El `Context Selector` responde: *¿qué información necesita **esta** decisión?* — en lugar de recuperar
todo lo que se sabe del lugar.

**No es un componente nuevo de esta declaración.** Ya está previsto como **E4.3 del Execution Plan 1.0**
(FASE 4 — Place Harness V0), con este objetivo textual: reducir coste, latencia y ruido de contexto.
Sus ejemplos ya están escritos allí: un comprador sin auto con commute anchor necesita transit, walk time
y servicios esenciales; un comprador sin preferencia de vida nocturna **no** debe recuperar esa dimensión.

**Reglas:**

- `DESIGN CONSTRAINT` — **No se crea un segundo selector.** Si algún día se implementa, se implementa
  E4.3. Cualquier otro "selector de contexto" que aparezca en el código es una duplicación a rechazar
  en revisión.
- `OUT OF CURRENT SCOPE` — implementarlo ahora. FASE 4 no está autorizada; la unidad vigente es E3.2b.
- `DESIGN CONSTRAINT` — lo que la frontera 360 aporta a E4.3 es únicamente que el selector, cuando se
  construya, no debería asumir que las únicas dimensiones posibles son las del lugar.

---

## 2. `Capability Registry`

**`FUTURE HYPOTHESIS`. No es un componente requerido hoy y puede no serlo nunca.**

Un registro conocería: qué capacidades existen, versión, jurisdicciones cubiertas, inputs, outputs, tipo
de evidencia y límites declarados.

- `OUT OF CURRENT SCOPE` — construir un registry, un sistema de plugins, un mecanismo de descubrimiento
  dinámico o cualquier indirección para "registrar capacidades".
- `DESIGN CONSTRAINT` — mientras haya **una sola** capacidad real (Place), un registry es puro coste.
  La regla de activación es aritmética: **con menos de tres capacidades reales y en uso, el registry es
  una tabla en un documento, no código.**
- `DESIGN CONSTRAINT` — lo que sí se preserva hoy sin coste: que cada capacidad futura pueda **declarar
  su jurisdicción y su vigencia**, porque eso es un campo, no una arquitectura.

---

## 3. `ContextCapabilityResult` — contrato conceptual candidato

**`FUTURE HYPOTHESIS`. Contrato conceptual. `OUT OF CURRENT SCOPE` implementarlo.**

Forma candidata, para que capacidades muy distintas pudieran hablar el mismo lenguaje:

```text
capability · version · subject · jurisdiction · geographic_scope · temporal_scope
result · evidence · methodology · confidence · freshness · limitations · conflicts
unknowns · requires_human_review · persistence_policy · computed_at
```

**Lo que importa hoy no es el contrato, es la observación que lo produjo:** los contratos V0 que ya
existen —`PlaceContextV0` sobre todo— ya cargan varias de estas nociones (status por feature, evidencia,
limitations, `insufficient_evidence`). Si un día hay una segunda capacidad, la pregunta será si su
resultado se parece lo suficiente a esto como para que `DecisionTraceV0` lo consuma sin casos especiales.

- `DESIGN CONSTRAINT` — **no se añade ningún campo de esta lista a un contrato V0 existente** para
  "prepararse". Ver §8.
- `DESIGN CONSTRAINT` — si aparece una capacidad nueva **exigida por un gate**, su resultado debería
  mirarse contra esta lista antes de inventar una forma distinta. Mirar es gratis; adoptar no es
  obligatorio.

---

## 4. Ejes transversales

**`DESIGN CONSTRAINT`.** Estos seis ejes aplican a cualquier capacidad —incluida la única que existe hoy—
y son la parte de este documento con efecto real e inmediato:

| Eje | Regla |
|---|---|
| **Subject / entity identity** | Toda afirmación es sobre una entidad identificada. Si no se puede decir de qué parcela, unidad o listing se habla, la afirmación no es material |
| **Jurisdiction** | Una regla o un dato sin ámbito de aplicación no es utilizable para decidir. Es first-class, no metadato decorativo |
| **Time / freshness** | `observed_at`, vigencia y obsolescencia. Un dato sin fecha no es verificable |
| **Evidence / authority** | Fuente, metodología y **quién tiene autoridad** para afirmarlo. No toda fuente vale lo mismo |
| **Limitations / unknowns** | `unknown` e `insufficient_evidence` son resultados válidos. El dato ausente degrada explícitamente; no se rellena |
| **Human review** | La revisión profesional es estructural cuando la responsabilidad lo exige, no un disclaimer al pie |

**Ninguno de los seis es nuevo.** Los seis ya son doctrina del repositorio: la FASE 1 dejó `unknown` e
`insufficient_evidence` prohibiendo `value`; el hotfix de procedencia de caminabilidad existió justamente
porque una métrica reportaba autoridad contradictoria por caminos distintos. Lo que este documento hace es
**nombrarlos como ejes reutilizables**, no inventarlos.

---

## 5. `logical capability` ≠ `network microservice`

**`DESIGN CONSTRAINT`. Ésta es la distinción central del documento.**

> **`Capability architecture` ≠ `microservice architecture`.**

Una **logical capability** es una unidad de responsabilidad con un contrato explícito: qué pregunta
responde, qué recibe, qué devuelve, con qué evidencia y con qué límites. **Vive dentro del monolito
modular.** Es una frontera de código, no de red.

Un **network microservice** es un proceso desplegado por separado, con su propio ciclo de vida,
despliegue, observabilidad, versionado de API, modos de fallo y latencia.

El patrón aceptado, y el único:

```text
logical capability → contract → implementation in modular monolith
                   → evidence → optional later extraction
```

O, en la forma corta que va en el bootstrap de sesión:

> `LOGICAL SERVICE FIRST → SIMPLE DEPLOYMENT → EXTRACT ONLY WITH EVIDENCE`

**`OUT OF CURRENT SCOPE`, sin excepción y sin discusión pendiente:** `Legal Service`, `Valuation Service`,
`Risk Service`, un `Context Fabric` físico, MCP, A2A, Partner Layer, API externa, o cualquier
microservicio. Nada de esto queda autorizado por esta sincronización documental.

**El monolito debe volverse más modular, no distribuirse.** Es la regla que el repositorio ya tenía; la
dirección nueva la refuerza.

---

## 6. Criterios de extracción física de un servicio

**`DESIGN CONSTRAINT` para una decisión futura.** Extraer un servicio exige una razón concreta, no una
preferencia estética. Al menos una de éstas, demostrada con datos, no anticipada:

1. **Carga o latencia propia** — el componente tiene un perfil que degrada al resto.
2. **Aislamiento regulatorio o de seguridad** — datos que no pueden compartir proceso o frontera.
3. **SLA distinto** — disponibilidad o consistencia que el monolito no puede ofrecer.
4. **Ownership separado** — otro equipo con otro ciclo de release. *(Contexto no tiene esto hoy.)*
5. **Tecnología especializada** — un runtime que el monolito no puede alojar razonablemente.
6. **Escalado independiente** — el componente escala por un eje distinto al de la aplicación.
7. **Reutilización externa real** — un consumidor fuera de Contexto que ya existe y ya lo pide.

`DESIGN CONSTRAINT` — **"vamos a necesitarlo" no es ninguno de los siete.** La ausencia de evidencia es
evidencia de que no hay que extraer.

---

## 7. Composición de capabilities por decisión

**`FUTURE HYPOTHESIS`.**

La hipótesis de composición dice que un `decision profile` selecciona qué capacidades participan: una
compra residencial compone distinto que un arrendamiento, un crédito o una decisión de desarrollo. El
catálogo de composiciones candidatas vive en la Declaración §21.

- `CURRENT / VERIFIED` — hoy existe **una** composición y **una** capacidad con implementación real. No
  hay composición que probar.
- `DESIGN CONSTRAINT` — el vertical **no desaparece** en esta hipótesis. Cada dominio puede requerir
  experiencia, datos y modelos propios sobre una base común. "Componible" no significa "genérico".
- `OUT OF CURRENT SCOPE` — construir un motor de composición, un DSL de perfiles de decisión o
  configuración dinámica de capacidades.

---

## 8. Regla de no-anticipación en los contratos V0

**`DESIGN CONSTRAINT`. Es la regla operativa más importante de este documento.**

> **No se añade un campo, una abstracción, una interfaz o un punto de extensión a un contrato V0
> "por si acaso".**

Un campo que nadie escribe y nadie lee no es preparación: es una promesa no verificada dentro de un objeto
que sí se verifica. Y en un sistema cuya doctrina es que todo claim material tenga procedencia, un campo
vacío que viaja al contexto del modelo es exactamente el tipo de superficie donde aparecen las
afirmaciones sin fuente.

**Criterio de admisión de un campo nuevo a un contrato V0:**

1. Una unidad autorizada del Execution Plan vigente lo exige, **y**
2. hay un productor real que lo escribe, **y**
3. hay un consumidor real que lo lee, **y**
4. hay un test que falla si no está.

Si falla cualquiera de los cuatro: no entra. Se anota en `../OPEN_DECISIONS_VIGENTES.md` y espera.

`OUT OF CURRENT SCOPE` — `LegalContextV0`, `ValuationContextV0`, `RiskContextV0`, `InsuranceContextV0` y
cualquier otro contrato de dimensión de la frontera 360.

---

## 9. Cómo mediremos reutilización cuando llegue una segunda decisión

**`FUTURE HYPOTHESIS` — método, no compromiso de calendario.**

Hoy no se puede medir reutilización: hay una sola composición. Cuando exista una segunda clase de decisión
o una segunda ciudad, éstas son las preguntas que la miden — y hay que fijarlas **antes** de construir la
segunda, o la medición se contamina:

- **`reuse ratio`** — de las capacidades que la segunda decisión necesita, ¿qué proporción se usó **sin
  modificar el contrato**? Modificar el contrato para que "encaje" cuenta como no-reuso.
- **Coste del adapter** — cuánto código nuevo hace falta para conectar lo existente, medido aparte del
  código de la capacidad nueva.
- **`new-jurisdiction integration time/cost`** — cuánto cuesta la segunda ciudad frente a la primera. Si
  no baja, no hay core reutilizable: hay dos productos.
- **Contratos que sobrevivieron sin cambios** — cuáles aguantaron el contacto con el segundo caso.
- **Contratos que se rompieron y por qué** — es el dato más informativo de los cinco, y el que más se
  pierde si no se registra en el momento.

`DESIGN CONSTRAINT` — mientras estas cifras no existan, **"reutilizable" es una hipótesis y se escribe
como hipótesis**, en cualquier documento, deck o conversación con un tercero.

---

## 10. Resumen operativo

**Lo que este documento cambia hoy:** nada del código. Los seis ejes transversales del §4 y la regla de
no-anticipación del §8 aplican al trabajo que ya estaba autorizado.

**Lo que este documento prohíbe:** todo lo marcado `OUT OF CURRENT SCOPE`.

**Lo que este documento autoriza:** nada.

**La unidad técnica vigente sigue siendo la que determinan el repositorio y el gate vigente.**
