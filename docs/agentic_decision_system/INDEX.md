# ÍNDICE · CONTEXTO AGENTIC DECISION SYSTEM

**Actualizado:** 29 de agosto de 2026

Mapa del canon del sistema de decisión. Si una sesión nueva sólo puede leer un archivo antes de empezar,
que sea **`00_START_HERE_CLAUDE_CODE.md`**.

---

## 1. Por dónde empezar

| Quiero… | Voy a… |
|---|---|
| arrancar una sesión de trabajo | `00_START_HERE_CLAUDE_CODE.md` |
| saber **qué se construye ahora** | `canon/Contexto_Agentic_Decision_System_Execution_Plan_1.0.md` + el reporte `NN_` más alto |
| saber **qué existe de verdad** | el repositorio. `git log origin/main` |
| saber **hacia dónde va la compañía** | `canon/PROJECT_AI_MASTER_STRATEGY_0.3.md` |
| entender el target de producto | `canon/Contexto_Real_Estate_..._Blueprint_0.1.md` |
| saber si algo futuro está permitido | `canon/CONTEXT_CAPABILITY_ARCHITECTURE_0.1.md` |
| ver qué está sin decidir | `OPEN_DECISIONS_VIGENTES.md` |

---

## 2. Las dos jerarquías

**No se mezclan.** Una dice qué se construye; la otra, hacia dónde vamos.

### `EXECUTION AUTHORITY`

1. **Repository HEAD** — lo que existe técnicamente.
2. **Execution Plan 1.0** — lo que se ejecuta ahora.
3. **Gate vigente + reportes `NN_`** — dónde estamos dentro del plan.
4. **Blueprint 0.1** — el target de producto y arquitectura.

### `STRATEGIC DIRECTION`

1. **Decisiones de fundador cerradas** — `00_START_HERE` §6 y `../../CLAUDE.md`.
2. **Master Strategy 0.3** — estrategia vigente.
3. **Declaración de Frontera 0.1** — dirección declarada.
4. **Referencias e investigación** — evidencia, no planes.

> **Regla vinculante:** la dirección estratégica condiciona la compatibilidad futura, pero **no autoriza
> implementar trabajo fuera del Execution Plan vigente**.

---

## 3. El canon, archivo por archivo

### `canon/` — documentos de autoridad

| Archivo | Qué es | Autoridad |
|---|---|---|
| `Contexto_Agentic_Decision_System_Execution_Plan_1.0.md` | Plan normativo. FASE 0 → 6, gates por evidencia | **Ejecución · nivel 2** |
| `Contexto_Real_Estate_Agentic_Decision_System_Product_Technical_Blueprint_0.1.md` | Target: contratos Buyer/Property/Place/Decision/Trace, harnesses, benchmark, Partner Layer | **Ejecución · nivel 4** |
| `BLUEPRINT_0.1_ADDENDUM_COMPATIBILIDAD.md` | Por qué la frontera no cambió el target del Blueprint | Nota de compatibilidad |
| `PROJECT_AI_MASTER_STRATEGY_0.3.md` | Estrategia de compañía vigente + changelog 0.2→0.3 | **Estrategia · nivel 2** |
| `CONTEXTO_AI_DECLARACION_FRONTERA_0.1_2026-08-29.md` | Declaración fundadora. Copia literal, no normativa | **Estrategia · nivel 3** |
| `CONTEXT_CAPABILITY_ARCHITECTURE_0.1.md` | Restricciones de compatibilidad futura. **No autoriza nada** | Restricción de diseño |
| `history/PROJECT_AI_MASTER_STRATEGY_0.2.md` | Baseline histórico (24-ago-2026). No se edita | Histórico |

### Raíz de esta carpeta — bootstrap y decisiones

| Archivo | Qué es |
|---|---|
| `00_START_HERE_CLAUDE_CODE.md` | Bootstrap de sesión. Punto de entrada |
| `INDEX.md` | Este archivo |
| `OPEN_DECISIONS_VIGENTES.md` | Decisiones abiertas que necesitan al fundador. **No es backlog técnico** |

### Reportes de ejecución — evidencia, no plan

Serie `NN_`, en orden cronológico de unidad ejecutada. Cada uno documenta una unidad cerrada con su gate:

| # | Unidad |
|---|---|
| `06` | FASE 0 · Trust Gate (E0.1–E0.5) |
| `07` | FASE 1 · Contracts |
| `08` | FASE 2 · Decision Core |
| `09` | FASE 3 · Caracterización de la extracción del comprador |
| `10` | FASE 3 · Evidence input seam |
| `11` | FASE 3 · Caracterización de identidad del comprador |
| `12` | AUTH-READ-GATE.0 · Caracterización de acceso a sesión |
| `13` | AUTH-READ-GATE.1 · Enforcement |
| `14` | FASE 3 · Buyer store versionado |
| `15` | FASE 3 · Buyer updater |
| `16` | FASE 3 · Buyer state boundary |
| — | `E2_3_TABLA_DE_PROCEDENCIA.md` · `HANDOFF_AUTH_READ_GATE_1.md` |

> **Puede haber reportes con número más alto en ramas no fusionadas.** El índice refleja lo que está en
> `main`. Para la unidad realmente vigente, seguir el método de `00_START_HERE` §4 — incluye revisar
> `git branch -r --no-merged origin/main`.

---

## 4. ⚠️ Dos documentos que se parecen y no son lo mismo

Este es el error de navegación más probable del proyecto:

| | `Execution Plan 1.0` | `04_EXECUTION_PLAN_0.1` |
|---|---|---|
| Dónde | `canon/`, en el repositorio | **No versionado.** Documento de auditoría de agosto-2026 |
| Autoridad | **Normativa.** Es el plan que se ejecuta | Evidencia histórica |
| FASE 3 | **Buyer Harness V0** | `DECISION LOOP` (top-5 + trade-offs) |
| FASE 5 | First Agentic Decision Loop | `PARTNER LAYER` |

**Los commits del repositorio (`E0.x`, `E1.x`, `E2.x`, `E3.x`) usan la numeración del 1.0.** Cuando un
reporte dice "FASE 3", habla del Buyer Harness. Si un documento suelto dice "F3" y habla de un decision
loop, es el 0.1 y **no es el plan vigente**.

---

## 5. Qué NO está en este repositorio

Por decisión explícita, y para que nadie los busque creyendo que faltan por error:

- **Documentos de auditoría `01`–`05`** (agosto 2026): evidencia histórica que derivó el Execution Plan.
  No son requisito para trabajar (`00_START_HERE` §3).
- **Referencias estratégicas** (Buyer Harness, Nexor, Agentic Commerce, Enter, Zillow, HomeSelf, tesis de
  confianza delegada): insumos de investigación. La Declaración §22 y §23 los registra con su
  identificador `INT-` / `EXT-`.

Si alguno de estos documentos se necesita como canon en el futuro, entra por la misma vía que el resto:
copia literal en `canon/`, referenciada desde aquí.

---

## 6. Fuera de esta carpeta, pero también canon

- **`../../CLAUDE.md`** — decisiones zanjadas y restricciones permanentes del repositorio: Google como
  puente, capa propia de datos (`DATA MOAT`), español sin anglicismos en lo que ve el usuario, seguridad.
  **Es canon vigente y de lectura obligatoria.**
- **`../` (`docs/`)** — auditorías, análisis de competidores, estudios y estrategia de contenido. Son
  evidencia fechada, no plan.
