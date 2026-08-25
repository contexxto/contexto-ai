# 07 — PHASE 1 CONTRACTS REPORT

**Fecha:** 25 de agosto de 2026
**Ejecutor:** Claude Code (sesión del 2026-08-24/25)
**Plan de referencia:** `Contexto Agentic Decision System — Execution Plan 1.0`, FASE 1
**Alcance autorizado:** E1.1–E1.6, contratos únicamente
**Fase anterior:** `06_PHASE_0_TRUST_GATE_REPORT.md` — `ADVANCE TO CONTRACTS`, aprobado

---

## 0. Resumen

**Los seis contratos están cerrados, versionados y probados.** 262 pruebas propias; la
suite completa pasa de 869 a **1 131**, exit 0, verificada en árbol limpio sin `.env`.

Lo que esta fase compró no son seis ficheros de Pydantic. Es que **las tres mentiras que
FASE 0 tuvo que cazar a mano ahora son imposibles de construir**:

| Defecto que cerró F0 | Cómo lo impide ahora el contrato |
|---|---|
| E0.3 — la caminabilidad afirmaba "OpenStreetMap" sobre un número estimado | `PlaceMeasureV0.status=available` **exige** `evidence`, y la procedencia vive en `EvidenceRefV0.source_type` |
| E0.4 — ruido y vegetación movían el score ±50 y ±80 sin fuente | `unknown` e `insufficient_evidence` **prohíben** `value`. No hay dónde poner el número |
| El precio duplicado del JSONB ($200 vs $180 en un activo real) | `PropertyAttribute` rechaza nueve variantes de llave de precio; el precio solo existe en `transaction.price` |

En F0 esas tres cosas se arreglaron. En F1 dejan de poder volver.

**Recomendación en §9, con una condición.**

---

## 1. Identificación

| Campo | Valor |
|---|---|
| Repositorio | `github.com/contexxto/contexto-ai` (público) |
| Base | `e97afb2` (`origin/main` tras el merge del PR #122) |
| Rama de trabajo | `feat/contracts-evidence-v0`, en worktree propio |
| Commits | **12** |
| Archivos | **16**, +5 033 líneas, 0 eliminadas |
| Suite antes | 869 |
| **Suite después** | **1 131**, exit 0 |
| Pruebas nuevas | **262** |
| Ubicación | `app/contracts/`, según `02_CURRENT_TO_TARGET_ARCHITECTURE.md` §5 |

**Nada de lo entregado se consume todavía.** Ningún módulo de `app/` importa
`app.contracts`. El comportamiento del producto no cambia.

### Régimen de trabajo

Rama y worktree propios desde `origin/main`, según el régimen vigente desde el
2026-08-25. `main` local no se tocó. Cada unidad se verificó en **árbol limpio sin
`.env`** antes de commitear — la disciplina que F0 aprendió por las malas cuando el gate
cazó dos defectos que solo existían fuera del portátil del fundador.

---

## 2. Estado por unidad

| Unidad | Contrato | Líneas | Pruebas | Estado |
|---|---|---:|---:|---|
| E1.1 | `EvidenceRefV0` | 321 | 36 | ✅ |
| E1.2 | `BuyerContextV0` | 497 | 52 | ✅ |
| E1.3 | `PropertyContextV0` | 354 | 48 | ✅ |
| E1.4 | `PlaceContextV0` | 320 | 45 | ✅ |
| E1.5 | `DecisionContextV0` | 309 | 39 | ✅ |
| E1.6 | `DecisionTraceV0` | 278 | 42 | ✅ |
| — | `common_v0.py` (compartidos) | 52 | — | ✅ |

---

## 3. Los seis contratos

### E1.1 — `EvidenceRefV0` · `app/contracts/evidence_v0.py`

**Propósito.** La procedencia de un dato, no el dato. Se adjunta al valor, que vive
aparte, porque el mismo valor puede llegar por dos caminos con credibilidad distinta y
el ranking tiene que poder distinguirlos.

**Schema.** `contract_version` · `evidence_id` · `source_type` · `provider` ·
`source_id` · `observed_at` · `retrieved_at` · `confidence` · `methodology` ·
`persistence_policy` · `cache_ttl_seconds` · `limitations`.

**Congelado.**
- `observed_at` **sin default**. Si cayera a `retrieved_at`, todo dato traído hoy
  afirmaría describir hoy — que es E0.3 literal.
- `confidence: float | None` en `[0,1]`. `None` ≠ `0.0`: uno se abstiene, el otro afirma.
  No se convierten categorías de proveedor a números arbitrarios.
- `heuristic_estimate` exige `limitations` no vacía.
- **No existe `source_type="unknown"`.** Fabricar una evidencia para decir "no tengo
  evidencia" es inventarse una procedencia para representar su ausencia. La ausencia la
  declara el contrato consumidor.
- Ningún proveedor es estructura: `provider` es un valor de texto, no un campo por API.
- `cacheable_temporarily` exige `cache_ttl_seconds`; las otras dos lo prohíben.
- Instantes con zona horaria; `frozen`; `limitations` es tupla.

**Abierto.** `provider`, `source_id` y `methodology` son texto libre por diseño.

**Ejemplos del repo.** `source_type` cubre los orígenes reales: Overture y OSM
(`public_dataset`), Google Places y Valhalla (`provider_api`), `pois_propios` y walk
score (`own_measurement`), lo que dice la persona (`user_declared`), lo que dice un
corredor (`operator_declared`), y la estimación por zona que E0.3 destapó
(`heuristic_estimate`).

**No contiene.** El valor. Geometría. Nada de dominio.

**Deuda.** `provider` como texto libre admite `"google"` y `"google_places"` como cosas
distintas. Es el precio de no meter el catálogo de proveedores en el contrato; se
resuelve con una convención, no con un enum.

---

### E1.2 — `BuyerContextV0` · `app/contracts/buyer_v0.py`

**Propósito.** El estado de conocimiento sobre quien decide. Parcial por definición:
casi todo puede ser `None`, y lo que falta se nombra en `unresolved_questions` en vez de
rellenarse con un supuesto.

**Schema.** `version` · `context_revision` · `buyer_id` · `objective` · `financial` ·
`property_requirements` · `mobility` · `place_preferences` · `hard_constraints` ·
`soft_preferences` · `tradeoffs` · `stage` · `field_evidence` · `unresolved_questions` ·
`updated_at`.

**Congelado.**
- **`household` no existe, y es estructural.** No basta excluirlo del scoring: si el
  campo existe, alguien lo llena, y lo que se llena termina puntuando. Una prueba recorre
  el JSON Schema entero buscando 16 términos protegidos.
- La necesidad se expresa como requisito **del inmueble**: `bedrooms_min`, `area_m2_min`,
  `pets_allowed_required`, `accessibility_requirements`. *"Familia de cuatro"* describe a
  la persona; *"tres dormitorios"* describe al inmueble y se verifica contra él.
- **Los cuatro registros no se funden.** Una prueba falla si aparece cualquier campo
  `weight`/`score`/`importance`/`priority`.
- Restricciones y preferencias son `DecisionCriterionV0` —dimensión, operador, valor,
  procedencia—, no prosa. Guardarlas como texto obligaría a reparsear con un LLM cada vez
  que alguien quisiera comprobarlas.
- `CriterionOrigin` (`stated`/`inferred`) y `CriterionStatus` (`active`/`retracted`) son
  **ejes separados**. Con un enum único, retirar un criterio borraba de dónde salió.
- `anchor_id` obligatorio y único; **no se deriva** del label ni de las coordenadas.
- `version` (contrato) ≠ `context_revision` (estado).

**Abierto — y es la decisión más deliberada de la fase.**
`stage: str | None`, vocabulario **sin cerrar**. Valores como
`orienting/narrowing/validating/committing` son razonables pero son una **hipótesis sobre
cómo decide la gente**, sin evidencia de producto detrás. Congelarlos les daría la misma
fuerza que a un hecho medido.

> **Coste asumido, dicho sin adornos.** La primera versión tenía una prueba mecánica que
> importaba los `ESTADOS` de `app/intencion.py` y exigía intersección vacía. Al abrir el
> vocabulario **esa garantía se perdió**: mientras `stage` sea `str`, nada impide
> escribir ahí `"enganchado"`. La ortogonalidad entre el eje de DECISIÓN (este) y el de
> VENTA (`intencion.py`) queda documentada pero no forzada por el tipo. Queda una prueba
> que se cae si alguien borra esa explicación del módulo — la única salvaguarda que
> resta. **La garantía vuelve cuando se cierre el vocabulario.**

**No contiene.** Updater, store, historial, diff, resolución de conflictos, herramientas,
`compute_travel_to_anchor`. Todo eso es Buyer Harness.

**Límite que el módulo declara de sí mismo.** Que las categorías protegidas no sean
**estructura** está garantizado y probado. Que no aparezcan en el **texto libre** de una
restricción, no: un contrato no vigila prosa. Eso es `app/fair_housing.py` y otra fase.

---

### E1.3 — `PropertyContextV0` · `app/contracts/property_v0.py`

**Propósito.** Un inmueble tal como lo conocemos a través de un proveedor.

**Schema.** `contract_version` · `property_id` · `provider_id` · `provider_type` ·
`provider_listing_url` · `location` · `attributes` · `transaction` · `media` ·
`provenance` · `quality`.

**Congelado.**
- **Lo permanente y lo efímero no se mezclan.** `location`/`attributes` describen el
  activo físico; `transaction` describe el listing. `transaction` es **opcional**: un
  inmueble sin listing activo es un estado normal.
- **El precio vive en un solo sitio.** Ancla un defecto real del doc 03: sobre un activo
  REAL el JSONB traía `$200` mientras la transacción decía `$180`. Nueve variantes de
  llave rechazadas, más llaves únicas.
- **`(provider_id, property_id)` es la identidad externa.** Hoy no existe —cero
  apariciones de `provider`/`tenant`/`external_id` en `app/`—, y esa ausencia es lo que
  bloquea integrar a un tercero.
- **`inventory_class` obligatorio y sin default**: `live` · `demo` · `test` · `unknown`.
  Las fichas de Quito están hidratadas para pruebas; sin este campo un registro hidratado
  y uno real son indistinguibles. **`provider_type` no es señal de esto** — son ejes
  independientes, y hay prueba.
- Aquí `unknown` **sí** es válido, a diferencia de E1.1: no se fabrica una evidencia, se
  declara que desconocemos una propiedad de un registro que existe.

**Abierto.** `transaction.availability` (el Blueprint tiene su vocabulario y el
inventario actual no lo implementa) y `provider_type` (solo hay un valor evidenciado).

**Ejemplos del repo.** `ActivoInmutable` + `TransaccionTemporal` ya acertaban con la
separación; `tipo_operacion ∈ {venta, arriendo}` fija `Operation` en dos valores
evidenciados.

**No contiene.** Adaptadores, migraciones, persistencia, Partner Layer,
`decision_eligible`, reglas de benchmark, filtros del agente.

**Deuda.** El adaptador que convierta `ActivoInmutable` en este contrato **no existe**
— ver §5.

---

### E1.4 — `PlaceContextV0` · `app/contracts/place_v0.py`

**Propósito.** Lo que sabemos de un punto, con el respaldo de cada cosa. El doc 03 lo
resume: *"~40 % del contrato, ~75 % del dato — el dato está, el contrato no"*.

**Schema.** `contract_version` · `place_id` · `location` · `assembled_at` ·
`walkability` · `nearest_transit` · `nearby_places` · `travel_to_anchors` ·
`isochrones` · `environment` · `limitations`. Todo lo respaldado por evidencia va
envuelto en `PlaceMeasureV0[T]`.

**Congelado — la regla central de la fase.**

```
dimensión AUSENTE      → no evaluada / no solicitada / no ensamblada en ESTE contexto
available              → hay valor defendible Y la evidencia que lo sostiene
unknown                → la dimensión está en el contexto, su valor se desconoce
insufficient_evidence  → se evaluó y la evidencia no alcanza
```

Dos invariantes hacen todo el trabajo: `unknown`/`insufficient_evidence` **prohíben**
`value`; `available` **exige** `evidence` no vacía. Con eso, *"ruido sin evidencia no
puede traer valor"* es estructural para **toda** dimensión, no solo para las tres que
E0.4 nombró.

Además: `PlaceMeasureV0` es **genérica** —la regla es la misma para todas las
dimensiones, y repetirla por dimensión sería repetirla mal en alguna—; `assembled_at`
(contexto) y `observed_at` (medida) son campos distintos; ningún string humano como
representación primaria; la isócrona exige `Polygon`/`MultiPolygon` válido.

**Abierto.** `NearestTransitV0.mode` y `NearbyPlaceV0.category` son texto — el catálogo
cambia por ciudad y un enum congelaría el de Quito.

**Ejemplos del repo.** `isocronas.py` pide a Valhalla contornos peatonales con
`polygons=true` y el repo ya los persiste con `json.dumps` — por eso la isócrona entra:
el dato existe. Las nueve categorías de `pois_propios` alimentan `NearbyPlaceV0`.

**No contiene.** Scoring, pesos, ranking, `decision_eligible`, Place Harness,
refactor de `rutas.py`, `compute_travel_to_anchor`.

---

### E1.5 — `DecisionContextV0` · `app/contracts/decision_v0.py`

**Propósito.** Qué se decidió sobre qué, bajo qué reglas, y qué evidencia sustenta cada
afirmación.

**Schema.** `contract_version` · `decision_id` · `created_at` · `buyer` · `property` ·
`place` · `score_version` · `anchor_ids` · `eligibility` · `match` · `strengths` ·
`tradeoffs` · `uncertainties`.

**Congelado.**
- **Referencia, no contenido.** `BuyerContextRefV0` (`buyer_id` + `context_revision`),
  `PropertyContextRefV0` (el par de identidad de E1.3), `PlaceContextRefV0`. Una prueba
  comprueba sobre `$defs` que ningún contexto viaja entero.
- **La evidencia se cita, no se copia.** `evidence_refs` son `evidence_id`, no objetos.
  Un duplicado se desincroniza: si alguien corrige una `EvidenceRefV0` en su contexto, la
  copia seguiría afirmando lo viejo.
- **Las afirmaciones materiales exigen ≥1 referencia.** Una fortaleza sin evidencia es
  *"este barrio es tranquilo"* sin nada detrás. La excepción es `uncertainties`: existen
  a menudo **porque** faltan datos.
- **Ausente ≠ vacío.** `eligibility=None` es "no se evaluó"; `violations=()` es "se
  evaluó y está limpio". La segunda es una afirmación mucho más fuerte.
- Las anclas se referencian **solo** por `anchor_id`. No hay ningún campo de label.
- `place_id` obligatorio en la referencia aunque sea opcional en `PlaceContextV0`.

**No valida — y es deliberado.** No comprueba que los `anchor_ids` existan en el
`BuyerContextV0` referenciado. **No puede**: no tiene el contexto delante. Fingir esa
validación daría una garantía falsa. Hay una prueba que construye una referencia rota sin
error, para dejar escrito dónde **no** vive esa comprobación.

**Deuda.** El invariante `anchor_id ∈ BuyerContextV0.commute_anchors` queda pendiente
para el assembler de F2. Y **F2 tendrá que asignar `place_id`** a los contextos que hoy
se calculan al vuelo, o no podrán entrar en una decisión.

---

### E1.6 — `DecisionTraceV0` · `app/contracts/trace_v0.py`

**Propósito.** La trayectoria auditable de una ejecución completada.

**Schema.** `contract_version` · `trace_id` · `task_id` · `buyer_ref` ·
`inventory_snapshot_id` · `model_config_hash` · `provider_calls` · `facts_used` ·
`derived_features` · `policies_applied` · `uncertainties` · `ranking` ·
`final_output_hash` · `created_at`.

**Congelado.**
- `facts_used` registra lo que **entró** en la decisión, no lo disponible. Un contexto
  puede traer veinte dimensiones y la decisión haber mirado tres.
- **Ausencia declarada, no omitida.** `inventory_snapshot_id` y `model_config_hash` van
  **sin default**: hay que declarar que no los hay. Un campo que desaparece en silencio
  es indistinguible de uno que nadie rellenó.
- **V0 son ejecuciones completadas.** Sin `running`/`pending`/`failed`/`cancelled`/
  `partial`. `final_output_hash` obligatorio.
- **Nada sensible.** `ProviderCallV0` no tiene campos para claves, tokens, cabeceras,
  payloads, respuestas ni URLs firmadas. Hay prueba por nombre de campo.
- `DerivedFeatureV0.methodology` obligatorio: una feature sin metodología recrea el
  problema que cerró F0.
- El ranking preserva `(provider_id, property_id)`; `rank ≥ 1`; `score` exige
  `score_version`; los empates son legítimos, el mismo inmueble dos veces no.

**Asimetría con E1.5, deliberada.** Aquí `evidence_ids` **puede estar vacío**. La traza
registra lo que pasó, huecos incluidos: una llamada que falló no produce evidencia.
Exigirla obligaría a inventarse ids para que el objeto validara, y la traza dejaría de
ser un registro fiel para volverse una redacción.

**Abierto.** `provider`, `operation` y `PolicyAppliedV0.outcome`.

**No contiene.** Instrumentación, persistencia, hooks de LangGraph, benchmark runner,
prompts, razonamiento del modelo, transcripts.

**Deuda.** La política *"traza válida para benchmark ⇒ snapshot y hash presentes"*
pertenece a F6 y **no está congelada aquí**, por decisión explícita.

---

## 4. Compartidos — `app/contracts/common_v0.py`

`ContractBase` (frozen + `extra="forbid"`), `Money` (Decimal + ISO 4217 obligatoria) y
`TravelMode`. Existe por una razón concreta: si `property_v0` importara `Money` de
`buyer_v0`, acoplaría el contrato del inmueble al del comprador — dirección equivocada,
porque un inmueble existe sin que haya nadie buscándolo.

---

## 5. Fixtures, adapters y lo que NO se construyó

**Fixtures.** Los hay, pero **viven en los ficheros de prueba** como helpers
(`_medida`, `_comprador`, `_inmueble`, `_lugar`, `_decision`, `_traza`,
`_traza_representativa`), no como ficheros congelados aparte. E1.6 tiene además un
fixture mínimo y otro representativo, según su gate.

**Adapters.** **Ninguno.** No hay conversión `ActivoInmutable → PropertyContextV0`, ni
`analizar_zona() → PlaceContextV0`, ni `calcular_encaje() → DecisionContextV0`.

**Esto diverge del Execution Plan 1.0 §1, y hay que decirlo con todas las letras.** El
Plan describe F1 incluyendo adaptadores y derivación desde funciones existentes:

| Plan §1 | Lo entregado |
|---|---|
| 1.2 `PlaceContextV0` **desde** `analizar_zona()` | contrato puro, sin derivación |
| 1.3 `DecisionContextV0` **desde** `calcular_encaje()` | contrato puro, sin derivación |
| 1.4 `PropertyContextV0` **+ adaptador local**, 40 activos → 40 objetos válidos | contrato puro, sin adaptador |
| 1.5 `BuyerContextV0` **+ tabla + versionado**, historial | contrato puro; `context_revision` declarado pero sin store |
| 1.6 Fixtures del loop: 1 buyer + 10 properties + places, congelados | no existen |

La divergencia es **deliberada y dirigida**: las instrucciones de esta fase excluyeron
explícitamente adapters, migraciones, persistencia y assembler, y acotaron F1 a
representar. No es un descuido, pero **cambia qué significa "Gate F1 superado"** — ver §9.

---

## 6. Deuda introducida

1. **`stage` sin enum** cuesta la prueba mecánica de ortogonalidad con `intencion.py`.
   Documentado, no forzado.
2. **Los adaptadores no existen**, así que ningún contrato se ha ejercitado contra dato
   real. Están probados contra ejemplos escritos a mano; nadie ha intentado meter los 40
   activos reales por `PropertyContextV0` para ver qué se rompe.
3. **`place_id`** no tiene generador. F2 tendrá que proveerlo.
4. **`provider` como texto libre** admite variantes del mismo proveedor.
5. **`DerivedFeatureV0.value` no admite objetos anidados** — inmutabilidad por encima de
   generalidad, deliberado.
6. **Validación cruzada ausente por diseño**: `anchor_id` y `evidence_id` no se resuelven
   contra nada. F2/F6.

---

## 7. Contradicciones con Plan y Blueprint

**C-F.** El alcance de F1 en el Plan §1 incluye adapters, tabla y fixtures del loop; las
instrucciones de esta sesión lo redujeron a contratos. **Resuelta por dirección
explícita**, registrada en §5.

**C-G.** El Plan §1.3 menciona `evidence_refs` para `DecisionContextV0`. La primera
versión los omitió por evitar el snapshot; **corregido**: se citan por `evidence_id` sin
embeber objetos.

**C-H.** El Blueprint define un vocabulario para `transaction.availability` que **no se
pudo consultar** en esta sesión. Se dejó abierto en vez de inventar uno. Debe adoptarse
el del Blueprint antes de que alguien escriba valores a mano.

**C-I.** `EvidenceRefV0` prohíbe `unknown` y `PropertyProvenanceV0.inventory_class` lo
permite. **No es incoherencia**: en un caso se fabricaría una evidencia inexistente; en
el otro se declara desconocer una propiedad de un registro que sí existe. Está probado y
explicado en ambos módulos.

---

## 8. Suite

| | |
|---|---|
| Antes de F1 | 869 |
| **Después** | **1 131**, exit 0 |
| Nuevas | 262 |
| Verificación | árbol limpio **sin `.env`**, con las tres variables dummy de `pruebas.yml` |
| Regresiones | ninguna — las 869 anteriores siguen pasando |

**Ningún módulo de `app/` importa `app.contracts`.** El comportamiento del producto es
idéntico al de antes de esta fase.

---

## 9. Recomendación

### `ADVANCE TO DECISION CORE` — con una condición explícita

Los seis contratos cumplen lo que se les pidió, y cumplen algo más difícil de medir: **la
forma del objeto ahora impide la clase de error que costó FASE 0.** No porque alguien
recuerde la regla, sino porque el objeto no se construye si se viola.

La condición es esta: **lo que el Plan §1 incluía en F1 y esta fase no entregó
—adapters, tabla del comprador, fixtures del loop— tiene que quedar asignado a F2 de
forma explícita, o cancelado de forma explícita.** No puede quedarse en el limbo de "ya
se hizo la fase 1". Concretamente:

1. `ActivoInmutable → PropertyContextV0`, y correrlo contra los 40 activos reales. **Es
   la primera prueba de fuego de verdad**: hasta que dato real pase por estos contratos,
   están probados contra ejemplos que yo mismo escribí.
2. Generación de `place_id`.
3. El invariante `anchor_id ∈ BuyerContextV0.commute_anchors` en el assembler.
4. Consultar el Blueprint y cerrar `transaction.availability`.
5. Fixtures del loop congelados (Plan §1.6), si se siguen queriendo.

**Lo que este PASS no dice:**

- No dice que los contratos encajen con el dato real. Nadie lo ha intentado.
- No dice que `stage` esté resuelto. Está deliberadamente sin resolver.
- No dice que las categorías protegidas estén controladas: lo están **estructuralmente**,
  no en el texto libre.
- No dice nada sobre rendimiento, tamaño de serialización ni coste de almacenamiento.

---

## 10. Parada

La ejecución **se detiene aquí**. No se inicia F2 / Decision Core hasta revisión de
Carlos y ChatGPT y autorización explícita.

### Reproducir cualquier cifra

| Afirmación | Cómo |
|---|---|
| Suite en 1 131 | `python -m pytest --collect-only` sobre la rama |
| Verde sin `.env` | `git worktree add --detach <tmp> <sha>`, exportar `POSTGRES_DB/USER/PASSWORD=test`, `python -m pytest -q` |
| 262 pruebas de contratos | `python -m pytest tests/test_contracts_*.py --collect-only` |
| Nadie consume los contratos | `grep -rn "app.contracts" app/ --include=*.py` → solo el propio paquete |
| Ningún contexto embebido | `DecisionContextV0.model_json_schema()["$defs"]` |
| Nada sensible en las llamadas | `set(ProviderCallV0.model_fields)` |
