# ADDENDUM DE COMPATIBILIDAD · BLUEPRINT 0.1

**Fecha:** 29 de agosto de 2026
**Aplica a:** `Contexto_Real_Estate_Agentic_Decision_System_Product_Technical_Blueprint_0.1.md`
**Origen:** `CONTEXTO_AI_DECLARACION_FRONTERA_0.1_2026-08-29.md`

---

## 0. Qué es esto y qué no es

Este addendum **no modifica el Blueprint 0.1**, que se conserva íntegro y sigue siendo el target
técnico/producto de la fase Real Estate. No hay Blueprint 0.2.

Su única función es dejar registrado, para una sesión futura, **qué evaluamos y por qué el target no
cambió**, de modo que nadie tenga que rehacer el razonamiento — ni concluya, leyendo la Declaración de
Frontera, que el Blueprint quedó obsoleto.

---

## 1. La evaluación: ¿cambia el target inmediato?

La pregunta obligada era si la nueva dirección exige cambiar el target de
`Buyer / Property / Place / Decision / Trace`.

**Respuesta: NO.** No hay contradicción material. Tres razones:

1. **La Declaración extiende el Blueprint; no lo corrige.** El Blueprint ya exige que el Place Harness
   pregunte *qué información necesita una decisión específica* en lugar de recuperar "todo sobre el
   lugar" (§10), y que el Buyer Agent sea un **orquestador** que invoca herramientas, no un experto
   monolítico (§12). La tesis de "agente que compone capacidades" es una generalización de algo que el
   Blueprint ya pedía para el lugar.

2. **Los cinco contratos siguen siendo los correctos para la decisión que estamos validando.** La
   frontera 360 describe dimensiones que **una decisión de compra podría necesitar**; no describe objetos
   que falten en el modelo actual. `PERSON × PROPERTY × PLACE × OBJECTIVE → DECISION → ACTION` sigue
   siendo el core de validación.

3. **La brecha vigente no es de diseño.** Los contratos están escritos y todavía no tienen consumidor en
   el producto. Cambiar el target antes de que el target actual esté conectado añadiría diseño sobre una
   brecha de integración.

**Conclusión:** basta un addendum. No se justifica un Blueprint 0.2, y proponerlo sería sustituir una
brecha de integración por una de arquitectura.

---

## 2. Lo que NO se añade al backlog

`OUT OF CURRENT SCOPE`, por ausencia de dependencia real con una decisión o un gate:

- `LegalContextV0`, `ValuationContextV0`, `RiskContextV0`, `InsuranceContextV0`, `MarketContextV0` y
  cualquier otro contrato derivado de la frontera 360;
- campos nuevos en los contratos V0 existentes "para dejar preparado" — ver
  `CONTEXT_CAPABILITY_ARCHITECTURE_0.1.md` §8;
- harnesses adicionales al Buyer / Place / Decision del Blueprint;
- adelantar el Partner Layer (§16 del Blueprint) o cualquier superficie externa antes de su gate.

---

## 3. Dónde vive la compatibilidad futura

Las restricciones de diseño que la Declaración impone —ejes transversales, distinción entre capacidad
lógica y microservicio, criterios de extracción, regla de no-anticipación— **no viven en el Blueprint**.
Viven en:

> `CONTEXT_CAPABILITY_ARCHITECTURE_0.1.md`

Ese documento no autoriza construcción. Condiciona **cómo** se hace lo que ya estaba autorizado.

---

## 4. Nota sobre el `Context Selector` (§7 y §10 del Blueprint)

El `Context Selector` del que habla la Declaración **es** el de **E4.3 del Execution Plan 1.0**, coherente
con el principio de selección de dimensiones que el Blueprint ya describe para el Place Harness.

- No es un componente existente. **`FUTURE HYPOTHESIS`.**
- No se crea un segundo selector.
- No se implementa fuera de FASE 4 y de su gate.

---

## 5. Nota sobre el `Decision Case Loop` (Declaración §17)

La Declaración propone un `Decision Case Loop` en Quito: tomar una decisión de compra real y descubrir
empíricamente **qué afirmaciones materiales el sistema no puede sostener hoy**.

**Clasificación canónica:** posible **instanciación futura del `First Agentic Decision Loop`** ya previsto
como **FASE 5** del Execution Plan 1.0 — sujeta a su gate.

- **No es un carril de ejecución paralelo.** No hay dos loops.
- **No adelanta la FASE 5** ni ninguna otra fase.
- La propia Declaración lo condiciona: *"debe ocurrir después del gate actual y sin interrumpir la
  ejecución autorizada"*.
- Si algún día se ejecuta, su valor esperado es un **mapa empírico** de qué contexto cambia una decisión
  y cuál es ruido — no un producto 360.

---

## 6. Estado

El Blueprint 0.1 **sigue vigente y sin cambios** como target de la fase Real Estate.
Este addendum es una nota de compatibilidad. No altera contratos, alcance, secuencia ni gates.
