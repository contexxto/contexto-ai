# PROJECT AI — MASTER STRATEGY
## Línea Base 0.3 · Contexto AI

**Fecha:** 29 de agosto de 2026
**Estado:** Documento de trabajo estratégico · **DIRECCIÓN ESTRATÉGICA**, no autoridad de ejecución
**Sustituye a:** `history/PROJECT_AI_MASTER_STRATEGY_0.2.md` (24-ago-2026), que se conserva íntegro como baseline histórico
**Fuente primaria de esta revisión:** `CONTEXTO_AI_DECLARACION_FRONTERA_0.1_2026-08-29.md`

---

## 0. Cómo leer este documento

Se conserva la regla de lectura de la 0.2, sin cambios:

- **HECHO** — existe evidencia directa.
- **VALIDADO** — un tercero o usuario lo confirmó.
- **HIPÓTESIS** — creemos que puede funcionar, pero falta evidencia.
- **EXPERIMENTO** — estamos intentando demostrar una hipótesis.
- **DECISIÓN** — hemos decidido avanzar en una dirección.
- **NO SABEMOS** — todavía no tenemos evidencia suficiente.

**Regla del Proyecto AI:** no convertir una hipótesis en una verdad simplemente porque encaja bien en la narrativa.

> ⚠️ **Lo que este documento NO es.**
> No es una orden de implementación. La autoridad de ejecución la tienen, en este orden, el repositorio,
> `Contexto_Agentic_Decision_System_Execution_Plan_1.0.md`, el gate vigente y el Blueprint 0.1.
> Ver `../INDEX.md` §2. Este documento condiciona **compatibilidad futura**; no abre scope.

---

## Changelog 0.2 → 0.3

### QUÉ CAMBIÓ

1. **El framing de la compañía.** De *"comprender el contexto físico de un lugar"* a *"infraestructura de
   capacidades locales verificables para decisiones del mundo físico"*. El lugar deja de ser el techo de la
   tesis y pasa a ser **la primera capa demostrada** de una frontera más amplia.
2. **La unidad canónica se nombra explícitamente:** la **decisión**, no el chat ni el listing.
3. **Aparece el mapa de contexto 360** (21 dimensiones) como *mapa de capacidades potenciales*.
4. **Aparece `Context Fabric`** como hipótesis de arquitectura: capacidades componibles seleccionadas
   según la decisión.
5. **El método de expansión se nombra:** ciudad × jurisdicción × clase de decisión.
6. **El foso se desdobla en dos.** `DATA MOAT` (lo que la 0.2 y `CLAUDE.md` ya sostenían) y
   `COMPANY MOAT — HYPOTHESIS` (lo que la Declaración añade). Ver §10.
7. **La reutilización pasa de supuesto a métrica.** La 0.2 la asumía en su §8 condición 5; la 0.3 exige
   medirla (`reuse ratio`, `new-jurisdiction integration time`).
8. **Stripe y Enter entran como analogías estructurales** de abstracción y profundidad vertical.

### POR QUÉ

Porque la tesis de la 0.2 —contexto del lugar— resultó ser un recorte de un problema mayor que apareció
al mirar una decisión inmobiliaria real de punta a punta: una propiedad no existe sólo en un punto del
mapa, existe dentro de un sistema institucional, jurídico y económico local. La 0.2 ya lo bordeaba en su
§21 (*"¿qué significa este lugar para esta decisión?"*); la Declaración lo nombra.

Y porque la apuesta temporal cambió de forma: a medida que la inteligencia de los modelos de frontera se
abarata, el cuello de botella se desplaza hacia el contexto local, institucional y temporal que un modelo
nuevo **no trae de fábrica**.

### EVIDENCIA

- **[VERIFICADO — interno]** El Blueprint 0.1 ya exigía que el Place Harness preguntara qué necesita una
  decisión concreta en vez de recuperar "todo sobre el lugar", y que el Buyer Agent fuera un orquestador
  delgado. La dirección nueva **extiende** ese diseño, no lo contradice.
- **[VERIFICADO — interno]** El Execution Plan 1.0 ya contiene `Context Selector` en E4.3.
- **[VERIFICADO — externo]** Zillow publicó (25-mar-2026) una arquitectura de agente central que coordina
  skills verticales. `[EXT-04][EXT-05]` de la Declaración.
- **[VERIFICADO — externo]** OpenAI Frontier (5-feb-2026) identifica contexto, permisos y límites —no la
  inteligencia del modelo— como el cuello para poner agentes en producción. `[EXT-02]`.
- **[VERIFICADO — local]** PUGS 2024 de Quito y Registro de la Propiedad del DMQ documentan la
  fragmentación y la especificidad jurisdiccional del contexto que hace falta. `[EXT-11]`–`[EXT-14]`.
- **[NO DEMUESTRA]** Nada de lo anterior demuestra que Contexto tenga mercado pagador, ni que la
  hipótesis multiindustria sea correcta, ni que la infraestructura sea económicamente integrable.

### QUÉ NO CAMBIA

- **Real Estate primero. Quito primero. Contexxto es el primer cliente del core.**
- `PERSON × PROPERTY × PLACE × OBJECTIVE → DECISION → ACTION` sigue siendo el core de validación vigente.
- El baseline competitivo obligatorio de la 0.2 §8 sigue en pie: **LLM + inventario + Google Maps/Places/
  Routes + datos públicos.** Contexto no se compara contra "no tener contexto".
- Las decisiones de fundador congeladas siguen congeladas (household, ruido/tráfico/vegetación sin
  evidencia, core-first, ground truth, inventario del benchmark).
- Las prohibiciones de la 0.2 §23 siguen vigentes: no API pública, no marketplace de datos, no expansión
  internacional, no diez verticales, no arquitectura comercial final.
- **El Execution Plan 1.0 no se modifica por este documento.** El orden de fases no cambia.

### HIPÓTESIS ABIERTAS

- Que exista un comprador para la mejora (Gate 8 de la Declaración).
- Qué porcentaje del core sobrevive a una segunda ciudad (Gate 7). **NO SABEMOS.**
- Qué capacidad demuestra primero reutilización fuera de una sola transacción (Gate 6).
- Si el contexto institucional (derechos, regulación, valoración) cambia materialmente una decisión de
  compra o sólo la decora. **Ésa es la pregunta que el experimento de la Declaración §17 debe responder.**

---

# 1. La tesis de trabajo (revisada)

> **Contexto AI está intentando construir, ciudad por ciudad, una infraestructura de capacidades locales
> verificables para que humanos y agentes puedan comprender una situación del mundo físico, tomar una
> decisión de alta consecuencia y actuar dentro de límites explícitos.**

La tesis de la 0.2 —comprender el contexto físico de un lugar— **no se retira y no era incorrecta.** Se
reclasifica: es la **primera capa** de esta infraestructura, la única con implementación real hoy, y sigue
siendo el activo técnico con mayor apalancamiento de la compañía.

Lo que cambia es el techo. El lugar responde *qué implica estar allí*. Una decisión de alta consecuencia
sobre un inmueble necesita además saber *qué derechos existen sobre él*, *qué permite hacer la norma*,
*qué rango de valor se sostiene*, *qué riesgos lo afectan* y *qué cuesta realmente poseerlo*. Ese contexto
es local, tiene vigencia, tiene autoridad y no aparece en un modelo por ser más grande.

**Contexxto** sigue siendo la primera aplicación comercial y **el primer cliente del core**.

### Estado
**HIPÓTESIS DECLARATORIA.** La infraestructura existe parcialmente —una capa, la del lugar— y todavía
debemos demostrar que las demás capas son construibles, reutilizables y económicamente defendibles.

---

# 2. La unidad de la compañía: la decisión

La unidad canónica no es la conversación, el listing ni la llamada a un modelo. Es una **decisión
reconstruible**.

```text
PERSON × OBJECTIVE × PROPERTY × PLACE × CONTEXTO RELEVANTE
        → DECISION → TRACE → ACTION → OUTCOME
```

**[VERIFICADO]** El diseño vigente ya separa `BuyerContextV0`, `PropertyContextV0`, `PlaceContextV0`,
`DecisionContextV0` y `DecisionTraceV0`, y ordena calcular antes de narrar. Los vocabularios están
escritos en el repositorio (FASE 1, cerrada).

**[VERIFICADO — y es la brecha real]** Según los reportes de fase del repositorio, **esos contratos
todavía no tienen consumidor en el producto.** La brecha vigente no es de diseño: es de integración. Ver
`../16_PHASE_3_BUYER_STATE_BOUNDARY.md` y el reporte de la unidad E3.2b en curso.

La pregunta de la compañía deja de ser *"¿qué responde el agente?"* y pasa a ser *"¿qué decisión estamos
intentando sostener y qué capacidades deben participar para sostenerla?"*.

---

# 3. La frontera 360 — mapa de capacidades potenciales

> ⚠️ **Esto es un MAPA, no un schema.** Ninguna de estas dimensiones está autorizada a entrar al código,
> a los contratos V0 ni al scoring por aparecer aquí. Entra una dimensión cuando una decisión concreta y
> un gate la exigen, no antes. **FUTURE HYPOTHESIS.**

Persona y objetivo · Identidad del activo · Activo físico · Edificio y gobernanza · **Lugar** ·
Jurisdicción y derechos · Regulación urbanística · Valoración · Mercado · Finanzas · Fiscal/TCO · Riesgo y
resiliencia · Ambiental/habitabilidad · Infraestructura · Movilidad real · Transacción/procedimiento ·
Seguros · Actores e incentivos · Tiempo · Conocimiento humano local · Evidencia y autoridad.

El catálogo completo, con la pregunta que responde cada capacidad, vive en la Declaración §4 y §20.

**Regla que no se negocia:** una visión 360 **no** significa recuperar todos los datos siempre. Significa
disponer del mapa y seleccionar sólo lo materialmente necesario para la decisión. `unknown` e
`insufficient_evidence` siguen siendo resultados válidos y preferibles a la precisión fabricada.

De estas 21 dimensiones, **una está construida** (Lugar), **cuatro están contratadas sin consumidor**
(Persona, Activo, Decisión, Trace) y **dieciséis no existen**. Escribirlas juntas en una lista no las
acerca a existir.

---

# 4. Context Fabric — hipótesis de arquitectura

**[HIPÓTESIS DE ARQUITECTURA · no autorizada para implementación]**

```text
CONTEXT SELECTOR → CAPABILITY PLAN → STRUCTURED RESULTS → DECISION ENGINE → TRACE
```

El agente pregunta *"¿qué necesito saber para esta decisión?"*. Un `Context Selector` construye un plan de
capacidades. Un `Capability Registry` —hipotético— sabría qué capacidades existen, con qué versiones,
jurisdicciones, inputs, outputs, evidencia y límites.

Una compra residencial no tiene por qué invocar zoning profundo si no cambia la decisión; un desarrollo
inmobiliario sí. Un banco puede necesitar valoración, derechos y riesgo; un turista no.

**La reutilización nace de la composición, no de construir un producto multiindustria genérico.**

Dos aclaraciones que evitan malentendidos caros:

- **`Context Selector` no es un componente nuevo ni un componente existente.** Es el **target ya previsto
  por E4.3** del Execution Plan 1.0. No se crea un segundo selector. No se implementa aquí.
- **`Capability architecture` ≠ `microservice architecture`.** El desarrollo completo de esta distinción,
  con los criterios de extracción física, vive en `CONTEXT_CAPABILITY_ARCHITECTURE_0.1.md`.

---

# 5. Capability-first: una capacidad no pertenece a una transacción

**[HIPÓTESIS DE REUTILIZACIÓN]**

La prueba de que construimos infraestructura y no features desechables es que el mismo servicio lógico
participe en más de un flujo: `Valuation` sirve a compra, venta, crédito, seguro, inversión y desarrollo;
`Risk` a comprador, banco, aseguradora, desarrollador y municipio; `Place/Mobility` a vivienda, oficinas,
retail, turismo y planificación.

El vertical no desaparece: **cambia la composición.**

**Principio fundador que esto instala:**

> `CAPABILITY REUSE BY DESIGN ≠ PREMATURE IMPLEMENTATION`

Diseñar de modo que una capacidad **pueda** reutilizarse es gratis o casi gratis. Construirla antes de que
una decisión la exija es scope no autorizado. Una feature nueva **debería preferir una primitiva reusable
del core cuando eso no añada complejidad prematura material** — y cuando la añada, gana la simplicidad.

---

# 6. El agente como orquestador, no como experto monolítico

El agente no debería mejorar en "saberlo todo" sino en **saber qué necesita una decisión y delegar** en
capacidades con contratos: comprender el objetivo → resolver identidad → determinar contexto material →
reutilizar lo verificado → invocar lo que falta → aplicar restricciones fuera del LLM → detectar conflicto
o ausencia de dato → pedir revisión humana cuando el riesgo lo exija → construir `DecisionContext` →
registrar `DecisionTrace` → proponer acción → pasar por un gate de autoridad antes de ejecutar → conectar
el outcome.

**[VERIFICADO — externo]** AWS aplica límites de pago en la capa de infraestructura; Google y Mastercard
trabajan con instrucciones preautorizadas e intención verificable. `[EXT-07][EXT-08][EXT-09]`.

**[INFERIDO]** El patrón es transferible: **las restricciones críticas y la autoridad no deben depender de
que el modelo recuerde obedecerlas.** Esto ya es doctrina en el repositorio y la dirección nueva la
refuerza, no la relaja.

---

# 7. El método de expansión: ciudad × jurisdicción × clase de decisión

**[HIPÓTESIS]**

```text
CONTEXT CORE + COUNTRY/JURISDICTION PACK + CITY PACK + DOMAIN/DECISION PROFILE
```

La geografía deja de ser un mercado de lanzamiento y pasa a ser **la unidad de construcción del contexto
local**.

**NO SABEMOS** qué porcentaje será reusable entre ciudades. Ese desconocimiento debe convertirse en una
métrica, no en una promesa. Un "Quito Pack" no sería un dataset: sería la capacidad operacional de
resolver identidad predial, PUGS, derechos, movilidad, riesgos, infraestructura, valoración local,
mercado, procedimientos y evidencia — con fuentes y versiones.

**Regla de cobertura:** una ciudad está *cubierta* no cuando tenemos muchos datos, sino cuando podemos
sostener **una clase definida de decisiones** con cobertura, evidencia, freshness y límites medibles.

**Quito primero.** Ninguna segunda ciudad se abre en esta etapa.

---

# 8. Real Estate como primer laboratorio (sin cambios respecto de 0.2)

Se mantiene íntegra la §13 de la 0.2. Real Estate es el primer campo de aplicación porque la decisión
inmobiliaria depende intensamente del lugar y porque tenemos un producto real donde medirla.

Lo que la 0.3 añade es **por qué Real Estate es además un buen laboratorio de la tesis nueva**: es un
dominio donde el contexto institucional (derechos, norma, valoración, riesgo) es simultáneamente
material, local, versionado y verificable. Si la tesis de capacidades no se sostiene aquí, no se sostiene.

---

# 9. Sustitutos y baseline competitivo (sin cambios respecto de 0.2)

El sustituto realista sigue siendo **Google Maps Platform + un LLM de frontera + datos del portal + un buen
sistema de prompts, tools y reglas**. Contexto no puede basar su ventaja en mostrar mapas, tener POIs
públicos, calcular distancias, geocodificar, hacer búsqueda conversacional ni usar un LLM.

La 0.3 no relaja este baseline. Lo endurece: la pregunta del benchmark no es si Contexto *se ve mejor*,
sino **qué información material o decisión correcta obtiene que el baseline no puede producir de forma
razonable**.

---

# 10. El foso, en dos capas

> **Esta sección reconcilia la doctrina de `CLAUDE.md` (jun-2026) con la Declaración de Frontera §10.
> Ninguna de las dos se declara incorrecta.**

### `DATA MOAT` — vigente, decidido, en construcción

Datos propios y acumulables: OSM/Overture normalizados y almacenados, catastro vivo del corredor, ruteo
propio, procedencia, fechas, verificaciones. **Es la decisión de fundador de junio de 2026 y sigue en
pie.** Google es el puente, no el destino.

### `COMPANY MOAT — HYPOTHESIS` — hipótesis nueva, no demostrada

Identidad resuelta entre sistemas · contexto local con vigencia y ámbito de aplicación · reglas
normalizadas y su aplicabilidad · evidence graph con autoridad · metodologías locales de cálculo ·
historial de conflictos y correcciones · red de verificación humana · datasets de evals por decisión ·
`DecisionTrace` reproducible · outcomes conectados · coste decreciente de incorporar una jurisdicción
nueva.

### La relación entre las dos

**Los datos siguen siendo necesarios. La doctrina nueva sostiene que los datos por sí solos no son
suficientes.**

Poseer la capa de datos protege contra la dependencia de un proveedor y contra el coste variable — que es
exactamente lo que `CLAUDE.md` decidió resolver, y lo resuelve. Lo que **no** protege por sí solo es
contra un competidor que descargue los mismos datos abiertos. Esa segunda pregunta la responde —si se
demuestra— el `COMPANY MOAT`: el know-how operacional codificado sobre qué fuente confiar, qué regla
aplica, qué dato no se puede persistir, qué excepción invalida el cálculo, qué profesional debe revisar y
qué outcome contradijo al sistema.

Ese aprendizaje no desaparece cuando sale un modelo mejor. Un modelo mejor lo vuelve más barato de
explotar.

### Estado

`DATA MOAT`: **DECISIÓN** vigente, en ejecución.
`COMPANY MOAT`: **HIPÓTESIS DE DEFENSIBILIDAD.** Todavía no existe evidencia suficiente para llamarlo foso.

---

# 11. Stripe y Enter — analogías estructurales, no equivalencias de negocio

**Stripe** es referencia de **abstracción**: `PaymentIntent` encapsula un flujo complejo con estado,
lifecycle, autenticaciones adicionales y cambios regulatorios regionales. Contexto no copia pagos; aprende
a representar un proceso difícil mediante objetos con lifecycle explícito.

**Enter** es referencia de **profundidad vertical**: la unidad durable es el caso, y alrededor de ella se
combinan fuentes, documentos, estado estructurado, reglas, evidencia, revisión humana y outcome.

**La aspiración no es "ser el Stripe del real estate".** Es tener disciplina de infraestructura:
contratos claros, complejidad absorbida, observabilidad, reversibilidad, jurisdicción y reliability.

---

# 12. Falsación: qué tendríamos que demostrar

La visión sólo gana legitimidad si supera esta secuencia. Los gates son de la Declaración §15 y **no son
fases de ejecución** — no reemplazan ni reordenan las FASES del Execution Plan 1.0.

| Gate | Qué demuestra |
|---|---|
| 1 · DECISION LIFT | Mejores decisiones que el mejor baseline permitido, no respuestas más bonitas |
| 2 · EVIDENCE INTEGRITY | Claims materiales con provenance y freshness; el dato faltante degrada explícitamente |
| 3 · EXPERT CORRECTION | Podemos medir cuándo un profesional corrige al sistema y convertirlo en mejora |
| 4 · CASE REPLAY | Una decisión se reconstruye desde contexts, tool outputs, rules, versiones y evidence refs |
| 5 · OUTCOME LINK | Conectamos decisiones con resultados sin confundir correlación comercial con calidad factual |
| 6 · REUSE | Una segunda clase de decisión reutiliza capacidades sin reconstrucción total |
| 7 · CITY TRANSFER | Una segunda ciudad mide qué % del core se conserva y qué adapters exige |
| 8 · BUYER | Alguien paga por la mejora o integra la capacidad |

**Si fallan, reducimos la tesis.** La arquitectura no convierte una ambición en un negocio.

### Métricas de madurez

`% de claims materiales con evidence_ref válido` · `% de features con status measured/derived/estimated/insufficient_evidence` ·
`freshness SLA por capability` · `conflict rate` y tiempo de resolución · `expert override rate` ·
`critical error rate` · `decision lift vs baseline` · `trace replay success rate` ·
`outcome attribution coverage` · **`reuse ratio`** · **`new-jurisdiction integration time/cost`** ·
`% de lógica crítica fuera del LLM` · `human-review rate` · coste y latencia por decision profile.

---

# 13. Qué NO se autoriza con este documento

Este documento amplía la frontera estratégica. **No amplía el scope.**

**NO:** reescribir el monolito en microservicios · crear una ontología universal · construir motores
legales de cualquier país · autodenominarnos plataforma multiindustria · construir MCP, A2A o Partner
Layer por anticipación · abrir una segunda ciudad · crear `Legal Service`, `Valuation Service` o
`Risk Service` · añadir `LegalContextV0`, `ValuationContextV0` o `RiskContextV0` al backlog · añadir
campos a los contratos V0 "por si acaso" · cambiar el scoring · automatizar asesoría jurídica sin
revisión · llamar "tasación" a una estimación no profesional · crear un score 360 único que oculte
incertidumbre.

**SÍ:** diseñar contratos que no impidan esta evolución · preservar jurisdicción, evidencia y tiempo ·
identificar cada feature nueva como capacidad reusable o flujo vertical · medir cuándo una separación
física de servicio está justificada.

**Se mantienen además las prohibiciones de la 0.2 §23**, que no fueron levantadas.

---

# 14. Principios declaratorios

1. **CONTEXTO ANTES QUE GENERACIÓN.** La prosa nunca reemplaza al objeto fuente.
2. **APLICABILIDAD ANTES QUE ACUMULACIÓN.** Importa qué regla aplica, no cuántos documentos guardamos.
3. **EVIDENCIA ANTES QUE CONFIANZA.** Todo claim material señala fuente, fecha y metodología.
4. **`unknown` ES UN RESULTADO.** `insufficient_evidence` es preferible a la precisión fabricada.
5. **CÁLCULO ANTES QUE NARRACIÓN.** Aritmética, constraints y reglas críticas fuera del LLM cuando se pueda.
6. **LA DECISIÓN ES LA UNIDAD.** El chat es una interfaz; la decisión debe sobrevivirla.
7. **TRACE ES PARTE DEL PRODUCTO.** No reconstruir el porqué retrospectivamente.
8. **ACTION ≠ DECISION.** Autoridad y mandato son fronteras separadas.
9. **`LOGICAL SERVICE FIRST → SIMPLE DEPLOYMENT → EXTRACT ONLY WITH EVIDENCE`.** No microservicios por ideología.
10. **LOCAL POR DISEÑO.** Jurisdicción, vigencia y ciudad son first-class.
11. **HUMANO CUANDO LA RESPONSABILIDAD LO EXIJA.** La revisión profesional es estructural, no un disclaimer.
12. **OUTCOME CIERRA EL LOOP.**
13. **PRODUCTOS CONSUMEN EL CORE.** Contexxto valida la infraestructura; no la encierra.
14. **REUSO DEBE MEDIRSE.** "Multiindustria" sólo existe cuando una segunda composición reutiliza sin rehacer.
15. **LA ARQUITECTURA SE GANA CON EVIDENCIA.** No construir la plataforma futura por anticipación.

---

# 15. Doctrina fundadora de esta etapa

Contexto debe conservar las dos mitades y no confundirlas:

**AMBICIÓN** — construir infraestructura contextual del mundo físico que pueda convertirse en una
categoría mayor.

**DISCIPLINA** — Real Estate primero; Quito primero; una decisión primero; evidencia antes que
arquitectura; matar ideas buenas que distraen de la prueba principal.

> **"La ambición determina qué problema vale la pena intentar.
> La evidencia determina si tenemos derecho a seguir intentándolo."**

---

# 16. Principio final

> **No estamos intentando construir una IA que conozca el mundo.**
>
> **Estamos intentando convertir el contexto local —físico, institucional, económico, temporal y humano—
> en capacidades computables, versionadas y verificables que un agente pueda componer para sostener una
> decisión reconstruible.**

Contexxto es el primer cliente. Real Estate es la primera prueba. Quito es el primer territorio.

**Estado de la tesis: ABIERTA.**
**Siguiente objetivo: EVIDENCIA.**
