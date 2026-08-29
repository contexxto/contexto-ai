# CONTEXTO AI — AGENTIC DECISION SYSTEM
## Execution Plan 1.0

**Fecha:** 24 de agosto de 2026  
**Estado:** Línea base de ejecución  
**Base técnica auditada:** `main` · HEAD `937f587f886783ad835cdf862eda30e4ea364848`  
**Producto de referencia:** Contexxto / Real Estate  
**Propósito:** convertir el Blueprint 0.1 y la verdad del repositorio en una secuencia de construcción, prueba y validación que pueda producir evidencia suficiente para decidir si Contexto merece existir como Agentic Decision System integrable por portales y otros actores de Real Estate.

---

# 0. Decisión ejecutiva

Contexto entra en **modo ejecución**.

No se abre una nueva fase de investigación general. No se reescribe el producto. No se lanza todavía una plataforma B2B, un servidor MCP público ni un producto multiindustria.

El objetivo de esta línea base es construir y probar un único sistema:

> **Un Buyer Agent capaz de comprender a un comprador, consumir inventario, comprender el lugar de cada activo, producir un ranking verificable, explicar trade-offs y proponer una siguiente acción; y demostrar si ese sistema toma decisiones materialmente mejores que un stack moderno LLM + inventario + Google Maps.**

La arquitectura central queda congelada para esta fase:

```text
BuyerContextV0
      +
PropertyContextV0
      +
PlaceContextV0
      ↓
DecisionContextV0
      ↓
Buyer Agent
      ↓
Discover → Compare → Explain → Act
```

Los tres harnesses se mantienen separados conceptualmente:

- **Buyer Harness:** qué sabemos del comprador y cómo evoluciona.
- **Place Harness:** qué sabemos del lugar, con qué evidencia y qué parte es relevante para esta decisión.
- **Decision Harness:** cómo se combinan comprador + activo + lugar para filtrar, puntuar, comparar, explicar y actuar.

**Contexxto será el primer cliente del core.** No se congela como una maqueta; se congela el desarrollo lateral. Toda nueva capacidad de Contexxto debe consumir o validar el nuevo core.

---

# 1. Qué sabemos al comenzar

## 1.1 Estado técnico verificado

Claude Code auditó el repositorio real en HEAD `937f587` y ejecutó 795 pruebas en verde. La API de producción estaba sana y exponía 60 rutas. La base había avanzado 24 commits desde la auditoría del 19 de agosto.

El hallazgo estructural es claro:

> **Aproximadamente 35–40 % del Blueprint ya existe de alguna forma, pero principalmente como sustancia dispersa, no como contratos versionados y consumibles.**

La cobertura relativa es desigual:

| Componente | Sustancia aproximada | Lectura operativa |
|---|---:|---|
| BuyerContext / Buyer Harness | ~30–40 % | Brecha principal. Hay extractor, no harness persistente. |
| PropertyContext | ~45–60 % | Buen modelo físico/listing; falta identidad de proveedor y contrato partner-ready. |
| PlaceContext / Place Harness | ~40 % contrato / ~75 % dato | El dato existe; la salida se aplana a prosa. |
| DecisionContext / Decision Harness | ~50–55 % | Pieza más madura. Cálculo determinista antes de narrar ya existe. |
| DecisionTrace | ~5–15 % | Trayectoria implícita en checkpoints, no una decisión reconstruible. |
| Partner Layer | ~0 % | Debe construirse solo después de probar el core, salvo el adapter mínimo de inventario. |

## 1.2 Activo técnico con mayor apalancamiento

La pieza más madura no es el chat ni los POIs. Es el patrón ya implementado en el nodo `encaje`:

```text
LLM
 ↓
tools
 ↓
encaje determinista
 ↓
contexto autoritativo
 ↓
LLM
 ↓
verificación de prosa
```

El sistema ya calcula antes de narrar. Ese principio se conserva y se expande.

## 1.3 Brecha principal

El Buyer Harness está menos avanzado de lo que asumía el Blueprint.

Hoy:

- existen 9 preferencias planas;
- se extraen con LLM;
- se sanea contra un esquema cerrado;
- el transcript persiste en LangGraph;
- las preferencias se recalculan por turno.

No existen aún:

- `buyer_id` estable;
- BuyerContext persistido como objeto;
- versionado;
- diff;
- evidencia por campo;
- resolución de contradicciones;
- trade-offs explícitos;
- commute anchors;
- unresolved questions.

## 1.4 Place: dato rico, contrato pobre

Contexto tiene PostGIS, 8.512 POIs propios, fuentes, confidence, distancias, caminabilidad, transporte e isócronas parciales. Sin embargo, parte de esa riqueza cruza la frontera de salida como cadenas como:

```text
🚇 Quitumbe a ~1496 m (20 min a pie)
```

El dato estructurado existe aguas arriba. La tarea es dejar de perder estructura en la última capa.

## 1.5 Riesgos bloqueantes aún abiertos

Antes de usar el sistema como evidencia estratégica siguen abiertos cuatro P0 revalidados en HEAD:

1. endpoint de escritura de activos sin autenticación;
2. refresco Overture roto;
3. procedencia de walkability inconsistente;
4. tests que no bloquean despliegue.

Además, ruido/tráfico/vegetación siguen provenientes de heurísticas sin fuente y al menos tranquilidad influye en scoring.

---

# 2. Decisiones de fundador congeladas en Plan 1.0

Estas decisiones dejan de estar abiertas para esta fase.

## D1 — Household

**Decisión:** `household` no forma parte de las variables de decisión de `BuyerContextV0`.

Contexto modelará **necesidades**, no composición familiar:

- `bedrooms_min`;
- `area_min_m2`;
- mascotas cuando corresponda;
- movilidad;
- accesibilidad;
- presupuesto;
- restricciones y preferencias expresadas.

Si un partner entrega un campo household, podrá conservarse como dato recibido en una capa separada, sin acceso al scoring residencial ni al contexto del modelo usado para recomendar.

## D2 — Fuente del inventario real

**Decisión:** prioridad A = portal; respaldo = inmobiliaria/desarrollador.

No se construirá un scraper como estrategia primaria para resolver el benchmark.

El objetivo es obtener 100–500 propiedades reales con permiso de uso para prueba, porque una muestra de partner valida simultáneamente:

- compatibilidad de inventario;
- normalización;
- utilidad de la decisión;
- viabilidad de integración.

## D3 — Ruido, tráfico y vegetación

**Decisión:** salen del scoring v0 mientras no exista fuente defendible.

Permanecen, si se muestran, como:

```text
status: insufficient_evidence
```

No deben mover el ranking.

Un camino futuro puede reintroducir estas dimensiones con medición real o fuente verificable.

## D4 — Producto vs capa

**Decisión:** **core first; Contexxto as reference product.**

Contexxto no se abandona. Se detienen features que no contribuyan a:

- BuyerContext;
- PropertyContext;
- PlaceContext;
- DecisionContext;
- DecisionTrace;
- top-5 + trade-offs + next action;
- benchmark;
- partner pilot.

AuraReal y otras líneas no forman parte del plan hasta nueva decisión explícita.

## D5 — Ground truth

**Decisión:** métricas divididas.

**Determinista:**

- cumplimiento de hard constraints;
- factualidad de números;
- consistencia prosa ↔ motor;
- evidencia disponible;
- errores críticos.

**Humana / ciega:**

- utilidad del ranking;
- preferencia entre resultados;
- claridad de trade-offs;
- utilidad para decidir;
- disposición a actuar.

Un LLM puede servir como auxiliar de análisis, nunca como juez final de GO/KILL.

## D6 — Google y persistencia

**Decisión:** separar de inmediato `runtime-only` de `persistable`; no asumir legalidad de cache/persistencia por memoria.

Antes de una Partner Layer externa se hará revisión específica de términos vigentes aplicada a los campos usados.

Objetivo técnico: reducir persistencia de valores derivados de Google cuando una alternativa propia/abierta sea razonable, incluyendo verificar Valhalla para rutas peatonales punto-a-punto.

## D7 — Mercado del primer benchmark

**Decisión:** Quito es el mercado técnico por defecto mientras la capa propia siga concentrada allí.

Un partner puede cambiar la ciudad del piloto solo si se construye previamente la cobertura mínima necesaria. No se expandirá a múltiples ciudades por anticipado.

## D8 — Acción final del MVP

**Decisión:** la primera acción externa es `request_information / contact` reutilizando el handoff existente.

Agendar visitas, negociar, ofertar o coordinar financiamiento quedan fuera del primer loop.

## D9 — Lift material

**Gate provisional que se congela antes de ejecutar el benchmark:**

Contexto debe superar al mejor baseline permitido por al menos **10 puntos porcentuales en el score combinado**, sin aumentar errores críticos, y ser preferido en evaluación ciega de ranking en al menos **70 % de los casos evaluables**.

Si D ≈ baseline o el lift proviene solo de buyer memory sin aporte material de Place/Decision, la tesis de infraestructura debe reducirse.

---

# 3. Principio de ejecución

No habrá fases que terminen solo en “feature completada”.

Cada unidad de trabajo debe cerrar este ciclo:

```text
CAPACIDAD
   ↓
CAMBIO TÉCNICO
   ↓
TEST / EVAL
   ↓
EVIDENCIA
   ↓
DECISIÓN DESBLOQUEADA
```

Un cambio que no reduce una incertidumbre de producto, confiabilidad, integración o negocio no entra al plan.

---

# 4. Arquitectura objetivo mínima

No se crean microservicios. El monolito modular permanece.

```text
app/
├── contracts/
│   ├── buyer_v0.py
│   ├── property_v0.py
│   ├── place_v0.py
│   ├── decision_v0.py
│   └── trace_v0.py
│
├── buyer/
│   ├── updater.py
│   ├── store.py
│   └── stage.py
│
├── place/
│   ├── providers/
│   ├── selector.py
│   ├── assembler.py
│   └── spatial.py
│
├── decision/
│   ├── assembler.py
│   ├── scoring.py
│   ├── tradeoffs.py
│   ├── verify.py
│   └── trace.py
│
├── inventory/
│   └── adapters/
│       ├── contexto.py
│       └── partner.py
│
├── agent/
└── routers/
```

Reglas de frontera:

1. `agent/` no importa desde `routers/`.
2. `routers/` solo adapta HTTP; no ensambla decisiones.
3. los contracts no conocen nombres de proveedor como campos estructurales;
4. la fuente se representa en `evidence`;
5. Google, OSM, Overture, Valhalla y futuros providers son implementaciones, no producto;
6. la prosa se deriva de objetos estructurados, no al revés;
7. el LLM interpreta y explica; no es la autoridad de cálculo.

---

# 5. Workstreams sincronizados

El plan se ejecuta en tres carriles que convergen en el benchmark y el piloto.

```text
PRODUCT                    ENGINEERING                 VALIDATION / BUSINESS
   │                            │                              │
JTBD top-5                Hygiene + contracts           Inventario real
Buyer journey             Harness extraction            Buyer briefs
Trade-offs                Decision loop                 Benchmark rubric
Next action               Trace/evals                   Portal outreach
   │                            │                              │
   └────────────────────────────┼──────────────────────────────┘
                                ↓
                         BENCHMARK + PILOT
```

## Product

Debe responder qué experiencia demuestra valor:

> “Encuéntrame las cinco mejores propiedades para mi situación y explícame qué sacrifico en cada una.”

## Engineering

Debe hacer que esa experiencia sea:

- estructurada;
- reproducible;
- testeable;
- trazable;
- consumible por Contexxto y posteriormente por un partner.

## Validation / Business

Debe producir:

- propiedades reales;
- briefs reales;
- evaluadores;
- baseline serio;
- partner que acepte comparar sobre su inventario.

---

# 6. FASE 0 — TRUST GATE

**Objetivo:** hacer confiable la materia prima antes de medir la tesis.

**Hipótesis que protege:** cualquier lift debe provenir del sistema, no de datos contaminados o etiquetas falsas.

## E0.1 — Proteger escritura de activos

**Cambio:** autenticación/autorización obligatoria en `POST /api/v1/assets/` y revisión de endpoints costosos abiertos relacionados con el loop.

**Reutiliza:** auth JWT/API key existente.

**Test:** request sin credenciales falla; request autorizado funciona; suite completa verde.

**Evidencia:** test automatizado + listado de endpoints revisados.

**Done:** no existe escritura anónima en la superficie usada por el producto.

**Tamaño:** S.

## E0.2 — Reparar y automatizar refresh de POIs

**Cambio:** dejar de fijar release obsoleto; seleccionar release vigente de Overture; mover el refresh fuera de dependencia exclusiva del PC del fundador; añadir logs y failure signal.

**Test:** dry-run / staging o mecanismo seguro; registro de última actualización; fallo visible.

**Evidencia:** una corrida completa reproducible.

**Done:** la capa puede refrescarse sin intervención manual del portátil.

**Tamaño:** M.

## E0.3 — Corregir provenance de walkability

**Cambio:** `encaje.py` no puede afirmar OSM sin evidencia; provenance viaja desde fuente real hasta DecisionContext.

**Test:** fixtures con fuente OSM, fuente desconocida y fallback.

**Evidencia:** mismo activo produce una sola verdad en ficha, motor y prosa.

**Done:** no hay contradicción conocida.

**Tamaño:** S.

## E0.4 — Score versioning + retirar heurísticas no sustentadas

**Cambio:** introducir `score_version`; ruido/tráfico/vegetación dejan de mover scoring v0.

**Test:** fixture antes/después; transparencia sobre dimensiones no evaluadas.

**Evidencia:** `insufficient_evidence` en vez de score inventado.

**Done:** ningún dato sin fuente material altera el ranking.

**Tamaño:** S/M.

## E0.5 — CI gate

**Cambio:** workflow que ejecute suite crítica/completa antes del deploy o merge a producción.

**Test:** branch/commit que rompe un test no puede pasar gate.

**Evidencia:** CI visible.

**Done:** tests dejan de ser decorativos.

**Tamaño:** S.

### Gate F0

No se inicia benchmark si cualquiera de estas condiciones falla:

- escritura crítica anónima;
- pipeline territorial no reproducible;
- provenance contradictorio;
- scoring contaminado por heurística sin fuente;
- tests sin gate.

---

# 7. FASE 1 — CONTRACTS

**Objetivo:** crear las unidades estables del producto antes de ampliar UI o partner API.

## E1.1 — Shared evidence primitive

Definir una primitive común:

```text
EvidenceRefV0
- evidence_id
- source_type
- source_id
- observed_at
- retrieved_at
- confidence
- methodology
- persistence_policy
- limitations[]
```

No es un producto adicional; evita que cada contrato invente su propia procedencia.

## E1.2 — BuyerContextV0

Versión mínima para el primer loop:

```text
buyer_id
version
objective
financial.budget_max
property_requirements
mobility.commute_anchors[]
place_preferences
hard_constraints[]
soft_preferences[]
tradeoffs[]
stage
field_evidence[]
unresolved_questions[]
updated_at
```

**Excluido:** household como variable de decisión.

## E1.3 — PropertyContextV0

Mínimo:

```text
property_id
provider_id
provider_type
provider_listing_url
location
transaction
attributes
media
provenance
quality
```

`provider_id` puede ser `contexto` en el adapter local.

## E1.4 — PlaceContextV0

V0 solo incluye features con evidencia o estado explícito:

- identidad de lugar;
- walkability con método/fuente;
- nearest transit;
- travel-to-anchor;
- servicios/POIs estructurados;
- isócronas si Valhalla está operativo;
- evidence[];
- freshness;
- limitations[];
- insufficient-evidence states.

No incluye ruido/tráfico/vegetación como variables de ranking.

## E1.5 — DecisionContextV0

Mínimo:

```text
decision_id
buyer_context_version
property_id
place_id
objective
eligibility
match.score
match.score_version
match.dimensions[]
strengths[]
tradeoffs[]
uncertainties[]
ranking
recommended_next_action
explanation.verification_status
trace_id
created_at
```

## E1.6 — DecisionTraceV0

Mínimo para reproducir benchmark:

```text
trace_id
task_id
buyer_context_version
inventory_snapshot_id
model_config_hash
provider_calls[]
facts_used[]
derived_features[]
policies_applied[]
uncertainties[]
ranking[]
final_output_hash
```

### Tests de Fase 1

- JSON schema / Pydantic validation;
- round-trip serialization;
- fixtures mínimos;
- backward compatibility adapters donde aplique;
- `unknown` / `insufficient_evidence` como estados válidos.

### Gate F1

Todos los contracts tienen:

- versión;
- schema;
- fixture;
- validación;
- ejemplo real del repositorio;
- reglas de evidencia;
- definición explícita de qué no contiene.

---

# 8. FASE 2 — DECISION CORE EXTRACTION

**Objetivo:** convertir la pieza más madura en un core independiente de HTTP/UI sin cambiar comportamiento.

## E2.1 — Extraer `construir_panel()`

Mover la lógica funcional de `app/routers/chat.py` a:

```text
app/decision/assembler.py
```

El objetivo inicial es **paridad**, no mejora.

**Resultado esperado:** `graph.py` y `router/chat.py` consumen `decision/assembler.py`; `agent/` deja de importar desde `routers/`.

## E2.2 — DecisionContext antes de cards/prosa

Cambiar el flujo:

```text
rows
 ↓
DecisionContextV0
 ↓
current cards + authoritative prompt block
```

No:

```text
rows → cards/text → inferir contexto
```

## E2.3 — Evidence refs

Cada razón material de encaje debe poder referenciar evidencia estructurada o declarar que no hay suficiente evidencia.

## E2.4 — Verifier como componente de core

`verificacion_prosa.py` se conserva. En esta fase sigue en modo audit para no bloquear producto hasta medir falsos positivos.

### Tests

- parity tests contra outputs actuales;
- same input → same ranking;
- hard constraints no cambian;
- no dependencia HTTP;
- cards actuales derivadas del nuevo objeto.

### Gate F2

El primer `DecisionContextV0` real puede generarse sin FastAPI y sin UI.

---

# 9. FASE 3 — BUYER HARNESS V0

**Objetivo:** pasar de preferencias recalculadas por turno a un estado de comprador persistente, versionado y corregible.

## E3.1 — Buyer store

Crear persistencia explícita para BuyerContext.

Requisitos:

- buyer_id estable;
- version incremental;
- timestamps;
- current version;
- historial/diff;
- posibilidad de borrar/corregir;
- mínima retención necesaria.

No duplicar el transcript: el BuyerContext es estado derivado, no otra conversación.

## E3.2 — Buyer updater

Flujo:

```text
current BuyerContext
+
new user evidence
↓
proposed patch
↓
policy/sanitization
↓
conflict detection
↓
new version
```

Reglas:

1. explícito > inferido;
2. inferencia nunca se vuelve hard constraint silenciosamente;
3. corrección del usuario invalida inferencia previa;
4. cada campo material conserva origen/confianza;
5. conflicto no resuelto entra a `unresolved_questions`.

## E3.3 — Hard vs soft

Mover de un único hardcode global a restricciones del comprador, dentro de whitelist segura.

No todo debe convertirse en preferencia ponderada.

## E3.4 — Commute anchors

Nueva capacidad prioritaria:

```text
label
lat
lon
mode
max_minutes
importance
```

No se requiere inferir automáticamente domicilio/trabajo. El usuario puede declarar un ancla explícita.

## E3.5 — Trade-off capture

Ejemplos:

```text
acepto menos área a cambio de mejor movilidad
acepto mayor precio a cambio de reducir commute
acepto alejarme del centro si mantengo acceso al Metro
```

Se modela como preferencia del comprador; no como conclusión del LLM.

## E3.6 — Stage de decisión

No reemplazar `intencion.py`.

Mantener dos ejes:

- `decision_stage`: discovery → narrowing → comparing → ready_to_contact;
- `commercial_intent`: señal actual de `intencion.py`.

### Tools mínimas

- `get_buyer_context`;
- `update_buyer_context`.

Las demás resoluciones pueden ser funciones internas.

### Tests

- explicit beats inferred;
- correction works;
- diff exists;
- protected fields cannot enter ranking state;
- unresolved conflict is surfaced;
- same transcript does not create uncontrolled version churn;
- anchors serialize correctly.

### Gate F3

Un comprador puede:

1. expresar preferencias;
2. recibir recomendaciones;
3. corregir una preferencia;
4. cambiar una prioridad;
5. conservar el cambio en la siguiente sesión;
6. ver que el ranking cambia por una razón trazable.

---

# 10. FASE 4 — PLACE HARNESS V0

**Objetivo:** convertir datos territoriales existentes en un contrato agent-ready con selección contextual.

## E4.1 — Desaplanar `rutas.py`

Separar conceptualmente:

- providers;
- assembler;
- formatter humano.

El formatter deja de ser la fuente de verdad.

## E4.2 — Provider seam mínima

No crear framework universal.

Interfaz mínima para:

- capa propia/PostGIS;
- OSM/Overpass/Nominatim donde siga vivo;
- Google runtime;
- Valhalla.

## E4.3 — Context selector

Nueva pregunta del sistema:

> ¿Qué información del lugar necesita esta decisión específica?

Ejemplo:

- comprador sin auto + commute anchor → transit + walk time + servicios esenciales;
- comprador con prioridad parque → parques + walk time;
- comprador sin preferencia de vida nocturna → no recuperar esa dimensión.

Objetivo: reducir costo, latencia y ruido de contexto.

## E4.4 — `compute_travel_to_anchor`

Reutilizar cálculo existente de rutas peatonales donde sea posible y exponerlo estructurado.

## E4.5 — Evidence + limitations

Cada feature material debe ser:

```text
measured / derived / estimated / insufficient_evidence
```

con fuente, fecha y metodología cuando corresponda.

## E4.6 — Persistence policy

Toda evidencia distingue:

- persistable;
- cacheable-temporarily;
- runtime-only.

No se persiste contenido de terceros por conveniencia técnica sin política explícita.

### Tests

- same location returns structured schema;
- no emoji/string parsing is needed downstream;
- evidence refs are stable;
- missing data degrades explicitly;
- selector only asks required dimensions;
- provider failure produces limitation, not invented fact.

### Gate F4

El agente y un cliente de máquina pueden consumir `PlaceContextV0` sin interpretar prosa.

---

# 11. FASE 5 — FIRST AGENTIC DECISION LOOP

**Objetivo:** completar el producto mínimo que demuestra la tesis.

## JTBD

> “Encuéntrame las cinco propiedades que mejor encajan conmigo y explícame qué sacrifico en cada una.”

## Flujo obligatorio

```text
1. load/update BuyerContext
2. load inventory snapshot
3. cheap hard filters
4. normalize PropertyContext
5. select place dimensions
6. enrich only survivors
7. assemble PlaceContext
8. compute DecisionContext
9. rank
10. generate trade-offs
11. verify explanation
12. show top 5
13. propose request_info/contact
```

## E5.1 — Inventory adapter local

El código de búsqueda no consulta directamente tablas desde cada tool. Implementar una interfaz mínima que permita:

- Contexto local ahora;
- CSV/API partner después.

## E5.2 — Hard filters first

Evitar enriquecer propiedades que ya incumplen restricciones duras.

Esto reduce costo y prepara portal scale.

## E5.3 — Trade-off engine v0

Debe producir objetos, no solo copy.

Trade-off válido requiere:

- sacrificio;
- beneficio;
- severidad;
- evidencia;
- relación con una preferencia del BuyerContext.

## E5.4 — Ranking + uncertainty

Un score no puede ocultar cobertura baja.

Cada ranking debe poder mostrar:

- qué dimensiones aportaron;
- cuáles no tienen datos;
- qué hard constraints se aplicaron;
- versión del score.

## E5.5 — Next action

Primera acción:

```text
request_information / contact
```

Reutilizar handoff existente con consentimiento.

## E5.6 — Contexxto consume contracts

No rediseñar frontend. Migrar el flujo actual a consumir las nuevas estructuras manteniendo UX suficiente para prueba.

### Gate F5 — Demo interna canónica

Con un brief como:

> Presupuesto máximo 180.000. No quiero depender del automóvil. Acepto menos metros si reduzco mi commute. Quiero acceso a parque y transporte.

Contexto debe entregar top 5 y para cada opción:

- hard constraints;
- strengths;
- trade-offs;
- uncertainty;
- evidence;
- next action.

Y una corrección del comprador debe alterar la decisión sin perder el historial.

---

# 12. FASE 6 — DECISION TRACE + EVAL INFRASTRUCTURE

**Objetivo:** convertir la demo en evidencia reproducible.

## E6.1 — DecisionTraceV0

Registrar por tarea:

- buyer version;
- inventory snapshot;
- model/config hash;
- provider calls;
- facts used;
- derived features;
- policies;
- uncertainties;
- ranking;
- final output hash.

No construir observabilidad universal de agentes.

## E6.2 — Benchmark freeze

Cada corrida congela:

- modelo;
- prompt/system version;
- schema versions;
- score version;
- dataset;
- buyer brief version;
- provider configuration;
- date/time window cuando aplique.

## E6.3 — Eval harness

Reutilizar patrón de `evals/run_evals.py`.

Separar:

**Machine-gradable**
- hard constraint violations;
- factuality;
- unsupported claims;
- evidence coverage;
- trace completeness;
- latency/cost.

**Human-gradable**
- ranking preference;
- trade-off usefulness;
- clarity;
- actionability.

### Gate F6

Una recomendación puede reproducirse y auditarse después de la sesión.

---

# 13. FASE 7 — CONTEXTO BUYER DECISION BENCHMARK

**Objetivo:** probar si Contexto mejora la decisión frente a alternativas realistas.

## 13.1 Dataset

- 100–500 propiedades reales;
- un mercado por corrida;
- campos mínimos normalizables;
- snapshot congelado;
- permiso de uso claro.

## 13.2 Buyer briefs

Preferencia: compradores reales.

Fallback inicial para calibración: briefs sintéticos escritos antes de observar outputs, claramente separados de la evaluación final.

## 13.3 Brazos

Mantener mismo modelo principal y mismo inventario.

### A — Inventory only

LLM + listing/property data.

### B — Google agent baseline

LLM + inventory + Maps Grounding Lite / capacidades permitidas.

### C — Strong commodity stack

LLM + inventory + Google/otras APIs permitidas + buyer memory básica.

### D — Contexto

Buyer Harness + Place Harness + Decision Harness + evidence + trace.

## 13.4 Métricas

### Reliability

- critical error rate;
- hard constraint violations;
- unsupported claim rate;
- explanation factuality.

### Decision quality

- blind ranking preference;
- shortlist usefulness;
- trade-off usefulness;
- decision confidence del evaluador.

### Infrastructure

- evidence coverage;
- trace completeness;
- latency;
- cost per completed shortlist;
- provider dependency.

## 13.5 Criterio GO / HOLD / REDUCE

### GO — BUILD THIN INFRASTRUCTURE

- D supera al mejor baseline ≥10 pp en score combinado;
- D no aumenta errores críticos;
- D es preferido ≥70 % en ranking ciego;
- el lift es atribuible a más que buyer memory aislada;
- al menos un partner quiere continuar a integración.

### HOLD — KEEP AS VERTICAL CAPABILITY

- hay mejora de producto, pero no justifica una capa independiente;
- o el lift depende de una sola feature fácilmente replicable;
- o el costo/latencia no es partner-ready.

### REDUCE / KILL THESIS

- commodity stack ≈ Contexto;
- Contexto pierde en factualidad;
- PlaceContext no cambia decisiones;
- la complejidad no produce valor suficiente.

---

# 14. FASE 8 — PARTNER LAYER MINIMUM

**Inicio:** solo después de GO técnico o cuando un partner real requiera un adapter para aportar el dataset.

Excepción: `InventoryAdapter` mínimo puede aparecer antes para ingerir la muestra del benchmark.

## E8.1 — External identity

Añadir:

```text
provider_id
external_property_id
provider_listing_url
received_at
last_updated_at
```

Sin reescribir el activo físico permanente.

## E8.2 — Bulk ingestion

- CSV primero si acelera piloto;
- API/feed cuando el partner lo requiera;
- idempotencia;
- upsert;
- validation report.

## E8.3 — Partner auth

Solo nivel piloto:

- API key/credential por partner;
- tenant identity;
- scopes mínimos;
- rate limit por partner;
- audit logs básicos.

No OAuth autoservicio todavía.

## E8.4 — Observability mínima

- request count;
- p50/p95 latency;
- error rate;
- properties processed;
- evidence coverage;
- cost per decision/enrichment;
- provider failures.

## E8.5 — Contract surface

Exponer solo lo que el piloto necesita:

- inventory ingest;
- decision request;
- decision result;
- evidence/trace reference.

No API pública general.

### Gate F8

Un tercero puede entregar una muestra, obtener resultados y repetir la integración sin intervención manual sobre la base.

---

# 15. FASE 9 — PORTAL PILOT 0.1

**Propuesta:**

> “Entréguenos una muestra de su inventario. Contexto evalúa esos mismos activos contra briefs de compradores y comparamos si nuestra capa de decisión mejora ranking, explicación y calidad de la acción sin pedirles migrar su producto.”

## Secuencia

1. muestra de inventario;
2. mapping del feed;
3. normalización;
4. enrichment;
5. buyer briefs;
6. ranking paralelo;
7. evaluación ciega;
8. integración mínima en un flujo;
9. medición de comportamiento;
10. decisión de continuación.

## Métricas partner

- % inventario procesable;
- integration effort;
- context coverage;
- p95 latency;
- factuality;
- ranking preference;
- CTR recommendation;
- shortlist → request info/contact;
- lead quality;
- willingness to continue/pay.

## Gate F9

El piloto solo se considera validación comercial si el partner acepta continuar, ampliar o pagar sobre evidencia observada. Interés verbal sin siguiente paso no cuenta.

---

# 16. Carril comercial paralelo — empieza ahora

Engineering no debe esperar al partner; Business no debe esperar al benchmark terminado.

## B0 — Preparar partner target profile

Buscar portal/inmobiliaria/desarrollador con:

- inventario digital con lat/lon;
- acceso técnico rápido;
- capacidad de entregar 100–500 propiedades;
- disposición a piloto limitado;
- comprador digital suficiente;
- interés en agentes/recomendaciones;
- mercado donde podamos cubrir contexto.

## B1 — Material de conversación

No vender “Place Intelligence platform”.

Pitch inicial:

> “Queremos probar sobre su propio inventario si un agente que combina contexto del comprador, lugar, evidencia y reglas produce una shortlist mejor que un agente genérico.”

## B2 — Data request mínima

Solicitar:

- external property id;
- lat/lon;
- price/currency;
- operation;
- property type;
- bedrooms/bathrooms/area cuando exista;
- listing URL;
- availability;
- update timestamp.

No pedir CRM, identidad de compradores ni toda la base.

## B3 — Portal discovery questions

1. ¿Cómo rankean hoy?
2. ¿Qué buyer signals capturan?
3. ¿Qué datos de lugar usan?
4. ¿Tienen agente propio?
5. ¿Qué métrica quieren mejorar?
6. ¿Qué error les preocupa más: mala relevancia, poca explicación, lead débil, baja conversión?
7. ¿Qué pueden compartir para un piloto?
8. ¿Qué tendría que demostrar Contexto para justificar integración?

---

# 17. Responsabilidades: Carlos × Claude Code × ChatGPT

## Carlos — Founder / Product owner

Responsable de:

- priorización final;
- acceso a partners;
- decisiones de negocio;
- aceptación de riesgos;
- selección de mercado/partner;
- reclutamiento de evaluadores/compradores;
- aprobación GO/HOLD/KILL.

No debe resolver detalles de implementación que el código ya puede responder.

## Claude Code — Technical owner of truth

Responsable de:

- implementar sobre repositorio real;
- preservar tests y comportamiento;
- abrir fronteras de arquitectura mínimas;
- producir evidence de cada gate;
- identificar contradicciones del plan contra el código;
- no construir fases futuras por anticipado.

Cada entrega de Claude debe incluir:

```text
COMMIT / BRANCH
OBJETIVO
ARCHIVOS CAMBIADOS
CAPACIDAD HABILITADA
TESTS EJECUTADOS
RESULTADO
REGRESIONES / RIESGOS
EVIDENCIA DEL GATE
DECISIONES AÚN ABIERTAS
```

## ChatGPT — Product / architecture / validation counterpart

Responsable de:

- mantener Plan 1.0 como fuente de dirección;
- revisar contra Blueprint/Master Strategy;
- convertir outputs técnicos en criterios de producto;
- diseñar fixtures, evals y benchmark rubric;
- analizar cada gate con evidencia;
- preparar materiales del portal pilot;
- detectar sobreconstrucción o desalineación;
- actualizar el plan solo cuando evidencia nueva lo justifique.

---

# 18. Protocolo de trabajo con Claude Code

No enviar “implementa Plan 1.0 completo”.

Se trabaja un gate por vez.

## Ciclo

1. Carlos/ChatGPT entregan **unidad de ejecución**.
2. Claude Code verifica HEAD y dependencias.
3. Claude implementa la unidad mínima.
4. Claude ejecuta tests.
5. Claude devuelve reporte estructurado.
6. ChatGPT revisa contra objetivo/producto/evidencia.
7. Carlos acepta, modifica o detiene.
8. Solo entonces se abre la siguiente unidad.

## Regla de scope

Claude puede corregir un defecto bloqueante descubierto durante una unidad, pero no debe aprovechar la tarea para:

- refactor general;
- migrar framework;
- mejorar UI no relacionada;
- abrir multi-ciudad;
- crear plugin systems;
- cambiar modelo LLM por preferencia;
- añadir features de CRM.

---

# 19. Las primeras 12 unidades de ejecución

Este es el orden inicial que puede enviarse a Claude Code.

| # | Unidad | Dependencia | Gate |
|---|---|---|---|
| 1 | E0.1 proteger endpoint de escritura | ninguna | Trust |
| 2 | E0.3 provenance walkability | ninguna | Trust |
| 3 | E0.4 score_version + excluir heurísticas | E0.3 parcial | Trust |
| 4 | E0.5 CI gate | ninguna | Trust |
| 5 | E0.2 reparar refresh POIs | ninguna | Trust |
| 6 | E1.1 shared EvidenceRef + schema skeletons | F0 | Contracts |
| 7 | E1.2–E1.6 contracts v0 + fixtures | #6 | Contracts |
| 8 | E2.1 extraer `construir_panel()` con paridad | F1 | Decision Core |
| 9 | E2.2 generar DecisionContext antes de cards/prosa | #8 | Decision Core |
| 10 | E3.1 Buyer store + versionado | F2 | Buyer Harness |
| 11 | E3.2 Buyer updater + correction/diff | #10 | Buyer Harness |
| 12 | E3.4 commute anchors + tool de travel | #11 | Buyer/Place |

Después de la unidad 12 se reevalúa el siguiente bloque usando evidencia real de complejidad y regresiones.

---

# 20. Definition of Done global

Ninguna unidad está terminada si solo “funciona en mi máquina”.

Debe cumplir, cuando aplique:

1. **Código:** capacidad mínima implementada.
2. **Tests:** unit/integration/eval relevantes.
3. **Backward compatibility:** Contexxto no se rompe salvo cambio explícito aprobado.
4. **Provenance:** no se inventan fuentes.
5. **Unknown state:** ausencia de dato se representa.
6. **Security:** no se abre superficie innecesaria.
7. **Traceability:** versión/config identificable cuando afecta decisión.
8. **Documentation:** contrato/ADR actualizado.
9. **Evidence:** salida que permite verificar el gate.
10. **Decision:** se sabe qué siguiente incertidumbre queda desbloqueada.

---

# 21. Qué NO construir durante Plan 1.0

Hasta que un gate lo justifique:

- microservicios;
- Kubernetes;
- nuevo frontend;
- nuevo portal;
- nuevo dominio multiindustria;
- universal plugin framework;
- marketplace;
- foundation model propio;
- vector/data lake general;
- OAuth autoservicio;
- billing platform;
- servidor MCP público;
- multi-ciudad por anticipado;
- agenda de visitas compleja;
- negociación automática;
- financiamiento;
- CRM nuevo;
- AuraReal nuevo;
- scores de barrio universales;
- nuevas métricas sin fuente.

---

# 22. Señales de stop / redirección

El plan debe detener o reducir alcance si ocurre cualquiera:

## Stop técnico

- contracts obligan a reescritura mucho mayor que la estimada;
- data quality no puede elevarse a nivel reproducible;
- DecisionContext no puede desacoplarse sin romper producto repetidamente;
- latencia/costo del loop es inviable incluso con hard filters/context selection.

## Stop producto

- BuyerContext persistente no mejora consistencia de decisión;
- trade-offs no son útiles para compradores;
- PlaceContext agrega información pero no cambia shortlist;
- compradores prefieren búsqueda tradicional + humano sin beneficio del agente.

## Stop estratégico

- Google/commodity stack iguala Contexto;
- partner puede reconstruir el lift con muy poco esfuerzo;
- portal no reconoce valor en una capa externa;
- restricciones contractuales impiden el uso necesario de datos;
- no se consigue inventario real con permiso razonable.

---

# 23. KPIs de Plan 1.0

## Trust

- % datos materiales con evidencia;
- pipeline freshness;
- CI pass rate;
- unsupported-scoring dimensions = 0.

## Buyer

- context update correctness;
- correction success rate;
- unresolved conflict rate;
- preguntas hasta shortlist útil;
- shortlist acceptance.

## Place

- evidence coverage;
- insufficient-evidence rate;
- provider disagreement;
- travel-to-anchor coverage;
- context selection efficiency.

## Decision

- hard constraint violation rate;
- score reproducibility;
- trade-off usefulness;
- explanation factuality;
- trace completeness.

## Agent

- tool success rate;
- unnecessary tool calls;
- time to shortlist;
- cost per shortlist;
- completion rate.

## Partner

- % inventory processed;
- integration effort;
- p95 latency;
- ranking lift;
- contact/lead lift;
- willingness to continue/pay.

---

# 24. Artefactos que deben existir al final

## Core

1. `BuyerContextV0` schema + code + fixtures.
2. `PropertyContextV0` schema + adapter local.
3. `PlaceContextV0` schema + structured assembler.
4. `DecisionContextV0` schema + assembler.
5. `DecisionTraceV0` schema + store/log.
6. `EvidenceRefV0` shared primitive.

## Harnesses

7. Buyer updater/store.
8. Place selector/provider seam.
9. Decision assembler/tradeoffs/verifier.
10. First Agentic Decision Loop.

## Validation

11. benchmark dataset manifest;
12. buyer brief set;
13. baseline configurations;
14. evaluator rubric;
15. benchmark results;
16. GO/HOLD/REDUCE memo.

## Partner

17. inventory adapter spec;
18. pilot data checklist;
19. minimal API/OpenAPI draft;
20. portal pilot scorecard.

---

# 25. Primer movimiento inmediato

El Plan 1.0 queda activo con **FASE 0 — TRUST GATE**.

La primera orden a Claude Code debe ser limitada a E0.1–E0.5, sin iniciar Contracts hasta cerrar y evidenciar F0.

En paralelo, el carril de producto/negocio debe iniciar dos trabajos sin esperar al código:

1. **Partner shortlist:** identificar candidatos capaces de aportar inventario real y velocidad de piloto.
2. **Benchmark recruitment:** preparar perfiles de compradores/evaluadores y data agreement mínimo.

ChatGPT debe preparar, antes de cerrar F0:

- spec final de los cinco contracts + EvidenceRef;
- acceptance tests conceptuales del first decision loop;
- benchmark rubric congelada;
- data request mínima para partner.

---

# 26. Prompt de arranque para Claude Code — FASE 0

```text
Estamos ejecutando Contexto Agentic Decision System — Execution Plan 1.0.

Trabaja únicamente en FASE 0 — TRUST GATE.
No avances a Contracts ni refactors de harnesses.

HEAD de referencia del plan: 937f587.

Unidades:
E0.1 Proteger POST /api/v1/assets/ y verificar la superficie de escritura usada por el producto.
E0.2 Reparar el refresh de POIs para no depender de un release Overture obsoleto ni de una ejecución silenciosa; proponer la automatización mínima segura.
E0.3 Corregir la procedencia de walkability de extremo a extremo: motor, tarjeta y bloque autoritativo deben decir la misma verdad.
E0.4 Introducir score_version y sacar ruido/tráfico/vegetación del scoring mientras no tengan evidencia suficiente; mantenerlas como insufficient_evidence si el producto necesita comunicarlas.
E0.5 Añadir un CI gate que ejecute la suite crítica/completa antes de que un cambio pueda considerarse listo para producción.

Restricciones:
- no reescribir arquitectura;
- no tocar frontend salvo corrección estrictamente necesaria para provenance;
- no crear contracts todavía;
- no cambiar LangGraph;
- no añadir features;
- no desplegar cambios no auditados;
- preservar comportamiento salvo los defectos que esta fase corrige.

Entrega al terminar:
1. commit/branch;
2. archivos cambiados;
3. tests añadidos/modificados;
4. suite ejecutada y resultado;
5. evidencia específica para cada E0.x;
6. riesgos/regresiones;
7. qué parte de F0 queda abierta;
8. recomendación GO/NO-GO para comenzar FASE 1.

No declares F0 cerrado si cualquiera de los cinco gates no tiene evidencia.
```

---

# 27. Qué significa ganar Plan 1.0

Plan 1.0 no gana porque Contexto tenga más arquitectura.

Gana si produce una respuesta defendible a estas cinco preguntas:

1. **¿Podemos representar persistentemente al comprador sin convertir el LLM en memoria opaca?**
2. **¿Podemos representar el lugar con evidencia estructurada sin depender de prosa o un proveedor único?**
3. **¿Podemos combinar comprador + activo + lugar en una decisión trazable y útil?**
4. **¿Esa decisión supera materialmente a un stack moderno commodity?**
5. **¿Un portal considera que la diferencia merece integración o pago?**

Si la respuesta a 4 o 5 es no, el resultado correcto no es seguir construyendo por inercia. Es reducir la tesis.

Si ambas son sí, Contexto habrá pasado de una arquitectura prometedora a la primera evidencia de un producto B2B agentic integrable.

---

# 28. Base de evidencia interna

Este Plan 1.0 reconcilia los siguientes artefactos:

- `Contexto Real Estate — Agentic Decision System: Product & Technical Blueprint 0.1`.
- `01 — Blueprint Alignment Audit`, auditado sobre HEAD `937f587`.
- `02 — Current → Target Architecture`, auditado sobre HEAD `937f587`.
- `03 — Tool & Context Inventory`, auditado sobre HEAD `937f587`.
- `05 — Open Decisions for Founders`, auditado sobre HEAD `937f587`.
- `Contexto AI — Master Strategy 0.2`.
- Auditoría técnica de Contexto AI del 19 de agosto de 2026.
- `Mapa de Infraestructura Contexto AI + Contexto Agent Benchmark 0.1`.

**Nota:** el paquete recibido contenía los documentos técnicos anteriores; este Plan consolida las recomendaciones verificadas y las decisiones de fundador adoptadas en la conversación. Cualquier diferencia futura entre el plan y el repositorio debe resolverse a favor de evidencia nueva del código y registrarse como cambio de línea base.

---

# 29. Regla de actualización de línea base

Plan 1.0 solo se modifica cuando ocurre uno de estos eventos:

- un gate produce evidencia que contradice una premisa;
- un partner real impone una restricción no prevista;
- una fuente contractual/legal invalida una persistencia o provider;
- el benchmark cambia una hipótesis;
- una decisión explícita del fundador cambia prioridad.

Cada modificación debe indicar:

```text
QUÉ CAMBIÓ
POR QUÉ
EVIDENCIA
IMPACTO EN FASES
DECISIÓN
NUEVA VERSIÓN
```

Hasta entonces, este documento es la línea base de ejecución.
