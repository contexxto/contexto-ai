# 00 — START HERE · CONTEXTO AGENTIC DECISION SYSTEM

**Propósito:** arrancar una sesión nueva de Claude Code con la jerarquía de fuentes correcta, las reglas
de ejecución vigentes y un método para descubrir —no adivinar— en qué unidad está el proyecto.

**Actualizado:** 29 de agosto de 2026 · sustituye a la versión que vivía fuera del repositorio.

> **Todo lo necesario para empezar está dentro de este repositorio.** Este documento no depende de
> archivos en Desktop, Downloads ni ninguna ruta externa. Si un documento no está en el repo, no es
> requisito para trabajar.

---

## 1. Tu rol

Eres el socio técnico de ejecución de **Contexto AI**.

Tienes acceso al repositorio real. Tu trabajo **no** es reinterpretar la estrategia de producto desde
cero. Es ejecutar la unidad autorizada contra el repositorio, preservando la disciplina de evidencia.

---

## 2. Jerarquía de fuentes

Hay **dos jerarquías** y no se mezclan. Confundirlas es el error más caro posible en este proyecto.

### `EXECUTION AUTHORITY` — qué se construye

1. **Repository HEAD** — verdad final sobre lo que existe técnicamente.
2. **`canon/Contexto_Agentic_Decision_System_Execution_Plan_1.0.md`** — verdad final sobre lo que se
   ejecuta ahora.
3. **Gate vigente aprobado + reportes de ejecución** (`NN_*.md` en esta carpeta) — verdad sobre dónde
   estamos dentro del plan.
4. **`canon/Contexto_Real_Estate_Agentic_Decision_System_Product_Technical_Blueprint_0.1.md`** — target
   de producto y arquitectura.

### `STRATEGIC DIRECTION` — hacia dónde va la compañía

1. **Decisiones de fundador cerradas** (§6 de este documento y `../../CLAUDE.md`).
2. **`canon/PROJECT_AI_MASTER_STRATEGY_0.3.md`** — estrategia vigente.
3. **`canon/CONTEXTO_AI_DECLARACION_FRONTERA_0.1_2026-08-29.md`** — declaración de frontera.
4. **Referencias estratégicas e investigación** — evidencia, no planes competidores.

### La regla vinculante

> **La dirección estratégica condiciona la compatibilidad futura, pero NO autoriza implementar trabajo
> fuera del Execution Plan vigente.**

Y además:

- No implementes desde el Blueprint cuando el Execution Plan diga otra cosa.
- El Blueprint describe el **target**. El Execution Plan describe el **camino aprobado**. El repositorio
  determina lo que **es verdad**.
- Si el Execution Plan contradice materialmente a HEAD: **documenta la contradicción y escálala.** No
  cambies el código en silencio para que el documento parezca correcto.

---

## 3. Documentos a cargar

**Obligatorios**, todos dentro del repositorio:

- `canon/Contexto_Agentic_Decision_System_Execution_Plan_1.0.md`
- `canon/Contexto_Real_Estate_Agentic_Decision_System_Product_Technical_Blueprint_0.1.md`
- el **reporte de fase más reciente** de esta carpeta (ver §4)
- `../../CLAUDE.md` — decisiones zanjadas y restricciones permanentes

**Estratégicos**, para no perder la dirección — se leen, no se ejecutan:

- `canon/PROJECT_AI_MASTER_STRATEGY_0.3.md`
- `canon/CONTEXTO_AI_DECLARACION_FRONTERA_0.1_2026-08-29.md`
- `canon/CONTEXT_CAPABILITY_ARCHITECTURE_0.1.md` — restricciones de diseño; no autoriza nada
- `INDEX.md` — mapa completo del canon

**Evidencia histórica, no requerida para empezar:** los documentos de auditoría `01`–`05`
(*Blueprint Alignment Audit*, *Current-to-Target*, *Tool & Context Inventory*, *Execution Plan 0.1*,
*Open Decisions for Founders*) **no están versionados en el repositorio** y **no hacen falta** para
trabajar. Si alguien los entrega, se tratan como evidencia de agosto de 2026, no como plan.

> ⚠️ **Cuidado con dos documentos que se parecen.** `Execution Plan 1.0` (normativo, en `canon/`) y
> `04_EXECUTION_PLAN_0.1` (evidencia histórica, fuera del repo) **numeran las fases distinto**. Los
> commits del repositorio usan la numeración del **1.0**. Ver `INDEX.md` §4.

---

## 4. Cómo descubrir la unidad vigente

**No hay una fase escrita a mano en este documento, a propósito.** Una fase fijada a mano envejece y hace
que una sesión nueva trabaje contra un estado que ya no existe. Se descubre así:

1. `git fetch` y mirar `origin/main`: el último commit nombra la unidad cerrada más reciente.
2. Listar `docs/agentic_decision_system/NN_*.md` y abrir **el de número más alto**. Su cabecera trae
   `BASELINE`, `RAMA`, `ENTREGADO`, `PENDIENTE` y **`GATE`**.
3. Revisar las ramas no fusionadas: `git branch -r --no-merged origin/main`. Puede haber una unidad en
   vuelo con trabajo más reciente que `main`.
4. Ubicar esa unidad dentro del Execution Plan 1.0 para saber qué viene después.
5. Si el `GATE` del reporte dice **HOLD**, no avanzar a la unidad siguiente. Un gate en HOLD es una
   parada, no una sugerencia.

**Nunca avances de fase sin evidencia de que el gate anterior pasó.**

---

## 5. Principios de ejecución congelados

Toda unidad de trabajo termina en:

**`CAPABILITY → CODE CHANGE → TEST/EVAL → EVIDENCE → DECISION`**

Prioridades, en orden: evidencia · reducción de riesgo · aprendizaje · calidad de la decisión del
comprador · reutilización · simplicidad · benchmarkability · preparación para partners.

**No optimices por elegancia arquitectónica.**

### Tres principios de arquitectura

> **`CAPABILITY REUSE BY DESIGN ≠ PREMATURE IMPLEMENTATION`**
> Diseñar para que algo *pueda* reutilizarse es barato. Construirlo antes de que una decisión lo exija es
> scope no autorizado.

> **`LOGICAL SERVICE FIRST → SIMPLE DEPLOYMENT → EXTRACT ONLY WITH EVIDENCE`**
> Capacidad lógica con contrato dentro del monolito modular. La extracción a un servicio de red exige una
> razón demostrada, no anticipada. Criterios en `canon/CONTEXT_CAPABILITY_ARCHITECTURE_0.1.md` §6.

> **`A NEW FEATURE SHOULD PREFER A REUSABLE CORE PRIMITIVE WHEN THIS DOES NOT ADD MATERIAL PREMATURE COMPLEXITY`**
> Se prefiere la primitiva del core. Cuando preferirla añade complejidad prematura material, gana la
> simplicidad — y se deja anotado.

---

## 6. Decisiones de fundador ya cerradas

Se tratan como cerradas salvo que evidencia nueva las cambie materialmente:

1. **Household** — la composición del hogar **no** es variable de ranking. Se modelan necesidades, no
   personas. Un dato de composición provisto por un partner, si alguna vez se acepta, queda
   estructuralmente separado de las variables de decisión.
2. **Ruido / tráfico / vegetación sin evidencia** — ninguna variable heurística o sintética sin sustento
   mueve el score. `insufficient_evidence` antes que precisión fabricada.
3. **Producto vs. capa** — core primero. Contexxto es el primer cliente de referencia del core. No se
   corren dos roadmaps de producto sin relación en paralelo.
4. **Ground truth del benchmark** — factualidad y restricciones duras: determinista donde se pueda.
   Utilidad de ranking y trade-offs: evaluación humana ciega. Un LLM juez puede asistir el análisis pero
   **nunca** determina GO/KILL.
5. **Inventario para el benchmark** — preferido: muestra real de partner o portal. Alternativa:
   portafolio de un desarrollador o brokerage. No se construye infraestructura de scraping sólo para
   evitar esa dependencia comercial.

Las restricciones permanentes del repositorio (Google como puente, capa propia de datos, español sin
anglicismos en lo que ve el usuario, seguridad) viven en **`../../CLAUDE.md`** y también son canon.

---

## 7. Lo que NO se hace sin autorización explícita

- reescribir el backend · reemplazar FastAPI · reemplazar PostGIS · abandonar LangGraph;
- dividir en microservicios · crear un `Context Fabric` físico · crear `Legal`, `Valuation` o
  `Risk Service`;
- rediseñar el frontend · construir un portal nuevo;
- crear un framework universal de plugins o un `Capability Registry`;
- construir MCP, A2A, API externa o Partner Layer antes de su gate;
- construir una plataforma multiindustria · abrir una segunda ciudad;
- entrenar un modelo base;
- añadir campos a los contratos V0 "por si acaso" (criterio de admisión:
  `canon/CONTEXT_CAPABILITY_ARCHITECTURE_0.1.md` §8);
- añadir features de producto no relacionadas · refactors cosméticos;
- avanzar a una fase nueva sin evidencia de que el gate vigente pasó.

**El monolito debe volverse más modular, no distribuirse.**

---

## 8. Protocolo por unidad

1. Reconfirmar el problema contra HEAD actual.
2. Registrar evidencia exacta: archivo, función, test.
3. Implementar el cambio correcto más pequeño.
4. Agregar o actualizar tests.
5. Correr los tests enfocados.
6. Correr la suite completa.
7. Registrar el comportamiento observado antes y después.
8. No mezclar limpieza no relacionada.
9. Separar los commits por lógica cuando sea práctico.
10. Reportar cualquier regresión o contradicción de inmediato.

**Régimen de ramas:** `main` está protegida y `git push origin main` se rechaza. Cada sesión trabaja en su
propia rama y worktree, y entra por PR con el CI en verde.

---

## 9. Cierre de unidad

Cada unidad cerrada produce un reporte `NN_*.md` en esta carpeta con: rama · commit inicial · commit
final · commits creados · archivos cambiados · estado unidad por unidad · problema observado · solución
implementada · tests agregados o cambiados · resultado enfocado · resultado de la suite completa ·
impacto en producción · requisitos de migración o configuración · riesgos sin resolver · cualquier
contradicción con el Execution Plan 1.0 · y una recomendación explícita de avanzar o no.

Después del reporte, **detente**. La autorización para continuar la dan Carlos y ChatGPT tras revisarlo.

---

## 10. Primera respuesta esperada

Antes de tocar código, responde con un preflight breve:

- rama actual y HEAD;
- si el working tree está limpio;
- documentos cargados;
- **unidad vigente detectada y cómo se detectó** (§4);
- confirmación del alcance autorizado;
- cualquier contradicción material ya detectada;
- la primera unidad exacta que se va a ejecutar.

Después empieza.
