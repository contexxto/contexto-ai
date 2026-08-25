# 07 — PHASE 1 CONTRACTS REPORT

**Fecha:** 25 de agosto de 2026
**Ejecutor:** Claude Code (sesión del 2026-08-24/25)
**Plan de referencia:** `Contexto Agentic Decision System — Execution Plan 1.0`, FASE 1
**Alcance autorizado:** E1.1–E1.6, contratos únicamente
**Fase anterior:** `06_PHASE_0_TRUST_GATE_REPORT.md` — `ADVANCE TO CONTRACTS`, aprobado

---

## 0. Resumen

**Los seis contratos están cerrados, versionados y probados contra el repositorio real.**
290 pruebas propias; la suite completa pasa de 869 a **1 159**, exit 0, verificada en
árbol limpio sin `.env`.

> **Revisión 2.** La primera fue rechazada en revisión por cuatro motivos, los cuatro
> correctos: C-F estaba mal formulada (§7), `transaction.availability` se dejó abierto
> cuando el Blueprint sí lo define (§3, E1.3), faltaban ejemplos derivados de estructuras
> reales del repo (§5), y `DecisionContextV0` no tenía cinco campos de su mínimo (§3,
> E1.5). Los cuatro están corregidos y verificados mecánicamente.

Lo que esta fase compró no son seis ficheros de Pydantic. Es que **las tres mentiras que
FASE 0 tuvo que cazar a mano ahora son imposibles de construir**:

| Defecto que cerró F0 | Cómo lo impide ahora el contrato |
|---|---|
| E0.3 — la caminabilidad afirmaba "OpenStreetMap" sobre un número estimado | `PlaceMeasureV0.status=available` **exige** `evidence`, y la procedencia vive en `EvidenceRefV0.source_type` |
| E0.4 — ruido y vegetación movían el score ±50 y ±80 sin fuente | `unknown` e `insufficient_evidence` **prohíben** `value`. No hay dónde poner el número |
| El precio duplicado del JSONB ($200 vs $180 en un activo real) | `PropertyAttribute` rechaza nueve variantes de llave de precio; el precio solo existe en `transaction.price` |

En F0 esas tres cosas se arreglaron. En F1 dejan de poder volver.

**Recomendación en §9.**

---

## 1. Identificación

| Campo | Valor |
|---|---|
| Repositorio | `github.com/contexxto/contexto-ai` (público) |
| Base | `e97afb2` (`origin/main` tras el merge del PR #122) |
| Rama de trabajo | `feat/contracts-evidence-v0`, en worktree propio |
| Commits | **14** |
| Archivos | **18**, ~+6 000 líneas, 0 eliminadas |
| Suite antes | 869 |
| **Suite después** | **1 159**, exit 0 |
| Pruebas nuevas | **290** |
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
| E1.3 | `PropertyContextV0` | 380 | 51 | ✅ |
| E1.4 | `PlaceContextV0` | 320 | 45 | ✅ |
| E1.5 | `DecisionContextV0` | 309 | 39 | ✅ |
| E1.6 | `DecisionTraceV0` | 278 | 42 | ✅ |
| — | `common_v0.py` (compartidos) | 90 | — | ✅ |
| — | **compatibilidad con el repo real** | — | **25** | ✅ |

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

**`transaction.availability` — cerrado con el vocabulario del Blueprint 0.1:**
`available | reserved | sold | unknown`. Adoptado tal cual, con enum, schema, round-trip
y pruebas. El inventario actual guarda texto libre en `estado_anuncio` (solo se ha
observado `"disponible"`); el mapeo lo hará el adaptador de F5. El contrato distingue
`None` —el listing no declara nada— de `UNKNOWN` —lo declara y dice que no se sabe—.

**Abierto.** `provider_type`: solo hay un valor evidenciado (`"contexto"`, Plan §1.4), y
una taxonomía de tipos de proveedor inventada desde un caso congelaría una hipótesis
sobre un mercado que aún no conocemos.

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

**Schema.** `contract_version` · `decision_id` · `created_at` · `objective` · `buyer` ·
`property` · `place` · `score_version` · `ranking` · `anchor_ids` · `eligibility` ·
`match` · `strengths` · `tradeoffs` · `uncertainties` · `recommended_next_action` ·
`explanation` · `trace_id`.

> **Los cinco últimos entraron en la revisión 2.** La comprobación mecánica del mínimo
> los encontró **ausentes** —`objective`, `ranking`, `recommended_next_action`,
> `explanation.verification_status`, `trace_id`— y se implementaron antes del merge.
> `trace_id` merece nota aparte: la revisión 1 tenía una prueba que afirmaba su
> **ausencia**, por una lectura mía demasiado literal de "`evidence_refs` no se confunde
> con `trace_id`". Los dos deben existir y decir cosas distintas: uno dice qué sustenta
> cada afirmación, el otro qué ejecución la generó.

`ranking` usa `RankingEntryV0`, **compartido con la traza** (E1.6): son el mismo hecho
visto desde dos sitios, y duplicar el tipo habría permitido que divergieran.
`ExplanationV0` **no guarda la prosa** —se deriva de las afirmaciones materiales—, solo
si pasó por verificación.

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

## 5. Fixtures, ejemplos reales y reparto de fases

### 5.1 Compatibilidad con el repositorio real — **la prueba de fuego**

Hasta la revisión 1, los seis contratos estaban probados contra ejemplos **que escribí
yo**. `tests/test_contracts_compatibilidad_repo.py` los enfrenta a las formas reales del
repo: las columnas de `ActivoInmutable` y `TransaccionTemporal`, lo que devuelve
`calcular_encaje()`, lo que devuelve `walk_score`, la forma de `preferencias` que vive en
`AgentState`, y lo poco que hoy se puede saber de una ejecución.

**25 pruebas, y ni un dato inventado.** Es la regla que gobierna ese archivo: cuando una
capacidad actual no puede poblar un campo, se usa `None` / `unknown` /
`insufficient_evidence` / `limitations`.

| Contrato | Fuente real | Lo que el repo NO tiene, declarado como hueco |
|---|---|---|
| `EvidenceRefV0` | `walk_score_fuente` ∈ {`osm`, `heuristico`, `NULL`} | `observed_at=None` — OSM no dice de cuándo es |
| `BuyerContextV0` | `preferencias` del checkpoint | `stage=None` — el repo no tiene eje de decisión |
| `PropertyContextV0` | `ActivoInmutable` + `TransaccionTemporal` | `inventory_class=UNKNOWN`, `completeness=None`, sin URL de listing |
| `PlaceContextV0` | `walk_score`, `pois_propios` | ruido y tráfico en `insufficient_evidence`, sin valor |
| `DecisionContextV0` | retorno de `calcular_encaje()` | `trace_id=None`, `recommended_next_action=None`, `context_revision=None` |
| `DecisionTraceV0` | lo observable del flujo actual | `inventory_snapshot_id=None`, `model_config_hash=None`, `latency_ms=None` |

Tres resultados que valen más que el resto:

1. **El precio contradictorio no llega.** El activo real trae `caracteristicas.precio=200`
   y `transaccion.precio=180`. El atributo **no se puede construir**, y el contrato queda
   con un solo precio y un `warning` que dice qué pasó.
2. **La heurística de ruido no puede traer valor.** `score_ruido_predictivo` existe en la
   tabla como `String(10)`. Entra como dimensión explicada, con `value=None`. Hay una
   prueba de que intentar meterla como valor **no construye el objeto**.
3. **La caminabilidad medida y la estimada son distinguibles.** Las dos ramas de
   `walk_score_fuente` producen evidencias que responden distinto a `es_medicion`. E0.3
   cerrado en el contrato.

**No son adaptadores.** Viven en `tests/`, y hay una prueba que verifica que ningún
módulo de `app/` los importa.

### 5.2 Reparto de fases — corrección de la revisión 1

La revisión 1 afirmaba que adapters, store y assembler *"quedaron fuera de F1 por
desviación dirigida"*. **Eso estaba mal.** El Execution Plan 1.0 no los asigna a F1; cada
uno tiene su fase:

| Pieza | Fase |
|---|---|
| Decision assembler | **F2** |
| Buyer store / versionado | **F3** |
| Place structured assembler | **F4** |
| Inventory adapter local | **F5** |
| Trace instrumentation / store | **F6** |

No hay divergencia que justificar: F1 entregó lo que F1 debía entregar.

## 6. Deuda introducida

1. **`stage` sin enum** cuesta la prueba mecánica de ortogonalidad con `intencion.py`.
   Documentado, no forzado. Se cierra cuando haya evidencia de uso.
2. **`explanation.verification_status` queda abierto.** El Blueprint define el campo, pero
   su lista de valores no se pudo consultar en esta sesión, y `verificacion_prosa.py` no
   la resuelve —devuelve hallazgos con gravedad `alta`/`media`, no un estado—. **Inventarlo
   habría sido el error de `stage`.** Debe cerrarse con el vocabulario del Blueprint antes
   de que alguien escriba valores a mano. Ver C-J.
3. **`place_id` no tiene generador.** F2/F4 tendrán que proveerlo: `PlaceContextRefV0` lo
   exige y `PlaceContextV0` lo tiene opcional.
4. **`provider` como texto libre** admite variantes del mismo proveedor
   (`"google"` vs `"google_places"`). Se resuelve con convención, no con enum.
5. **`DerivedFeatureV0.value` no admite objetos anidados** — inmutabilidad por encima de
   generalidad, deliberado.
6. **Validación cruzada ausente por diseño**: `anchor_id` y `evidence_id` no se resuelven
   contra nada. F2/F6.

## 7. Contradicciones con Plan y Blueprint

**C-F. — RETIRADA.** La revisión 1 afirmaba que el Plan §1 asignaba a F1 el Buyer store,
el Place assembler y el inventory adapter, y que quedaron fuera por desviación dirigida.
**Era una lectura equivocada del Plan.** Esas piezas nunca fueron entregables de F1; están
repartidas entre F2 y F6 según §5.2. No hay contradicción que registrar.

**C-G. — CERRADA.** El Plan §1.3 menciona `evidence_refs` para `DecisionContextV0`. La
revisión 1 los omitió por evitar el snapshot; ahora se citan por `evidence_id` sin embeber
objetos.

**C-H. — CERRADA.** `transaction.availability` adopta el vocabulario del Blueprint 0.1:
`available | reserved | sold | unknown`, con enum, schema, round-trip y pruebas.

**C-I.** `EvidenceRefV0` prohíbe `unknown` y `PropertyProvenanceV0.inventory_class` lo
permite. **No es incoherencia**: en un caso se fabricaría una evidencia inexistente; en el
otro se declara desconocer una propiedad de un registro que sí existe. Probado y explicado
en ambos módulos.

**C-J. — ABIERTA.** `explanation.verification_status` está definido en el Blueprint pero su
vocabulario no se pudo consultar. Queda como `str` abierto, declarado como deuda (§6.2).
**Es la única contradicción viva con el Blueprint al cerrar F1.**

## 8. Suite

| | |
|---|---|
| Antes de F1 | 869 |
| **Después** | **1 159**, exit 0 |
| Nuevas | 290 (265 de contrato + 25 de compatibilidad) |
| Verificación | árbol limpio **sin `.env`**, con las tres variables dummy de `pruebas.yml` |
| Regresiones | ninguna — las 869 anteriores siguen pasando |

**Ningún módulo de `app/` importa `app.contracts`.** El comportamiento del producto es
idéntico al de antes de esta fase.

---

## 9. Recomendación

### `ADVANCE TO DECISION CORE`

El Gate F1 literal queda satisfecho:

| Requisito | Estado |
|---|---|
| Contrato | ✅ los seis, versionados con `Literal` |
| Schema | ✅ JSON Schema generado y probado en los seis |
| Fixtures | ✅ mínimos, representativos, y **de compatibilidad con el repo real** |
| Validación | ✅ invariantes propias, no solo tipos |
| Tests | ✅ 290 |
| Suite completa | ✅ 1 159, exit 0, sin `.env` |

Y no se introdujo nada de lo prohibido: sin persistencia, sin instrumentación, sin
assembler, sin hooks de LangGraph, sin ejecución de benchmark, sin integración de
partners. **Ningún módulo de `app/` importa `app.contracts`.**

Lo que hace que esto sea un PASS y no un trámite: **los contratos ya se enfrentaron al
dato real** y lo representaron sin inventar nada. El activo con dos precios, la heurística
de ruido sin medición y la caminabilidad de procedencia ambigua —los tres defectos que F0
cazó a mano— entran ahora por un contrato que los declara como lo que son o directamente
no se construye.

**Lo que este PASS sigue sin decir:**

- No hay adaptador de producción. Los fixtures demuestran que la representación es
  posible; construirla es F5, F4 y F2.
- `stage` sigue deliberadamente sin resolver, y `verification_status` con él (C-J).
- Las categorías protegidas están controladas **estructuralmente**, no en el texto libre.
- Nada sobre rendimiento, tamaño de serialización ni coste de almacenamiento.

## 10. Parada

La ejecución **se detiene aquí**. No se inicia F2 / Decision Core hasta revisión de
Carlos y ChatGPT y autorización explícita.

### Reproducir cualquier cifra

| Afirmación | Cómo |
|---|---|
| Suite en 1 159 | `python -m pytest --collect-only` sobre la rama |
| Verde sin `.env` | `git worktree add --detach <tmp> <sha>`, exportar `POSTGRES_DB/USER/PASSWORD=test`, `python -m pytest -q` |
| 290 pruebas de contratos | `python -m pytest tests/test_contracts_*.py --collect-only` |
| El mínimo de `DecisionContextV0` | `set(DecisionContextV0.model_json_schema()["properties"])` |
| Los contratos representan el repo | `python -m pytest tests/test_contracts_compatibilidad_repo.py` |
| Nadie consume los contratos | `grep -rn "app.contracts" app/ --include=*.py` → solo el propio paquete |
| Ningún contexto embebido | `DecisionContextV0.model_json_schema()["$defs"]` |
| Nada sensible en las llamadas | `set(ProviderCallV0.model_fields)` |
