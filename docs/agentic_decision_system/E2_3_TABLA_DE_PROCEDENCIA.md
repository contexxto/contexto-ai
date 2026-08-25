# E2.3a — Tabla de procedencia · qué parte de la decisión se puede demostrar

**Fase:** F2 · E2.3a · **Base:** `feat/decision-core-v0`
**Regla de oro:** si no se puede construir un `EvidenceRefV0` **verdadero** desde datos que
ya existen, la salida es `insufficient_evidence` o ausencia de claim. Nunca fabricar
procedencia para conservar una razón legacy.

---

## 0. Las dos columnas que hay que separar

La primera versión de esta tabla clasificó la caminabilidad como `YES_NOW` y se contradijo
tres párrafos después. El error fue mezclar dos preguntas distintas bajo una sola columna:

| Pregunta | Qué significa |
|---|---|
| **¿Construible?** | ¿Sé armar un `EvidenceRefV0` honesto con los datos que hay? |
| **¿Resoluble en runtime?** | ¿Puede la decisión **citarlo** contra algo que exista al decidir? |

`DecisionContextV0` guarda `evidence_id`, no objetos: la evidencia vive en los contextos
referenciados. Una evidencia construible pero no resoluble produce una **referencia rota
emitida a propósito** — que es peor que no emitirla, porque valida.

Con las columnas separadas, el resultado real es:

> **Hoy hay cero razones materiales con evidencia resoluble de punta a punta.**
> No una. Cero.

---

## 1. Los tres hallazgos de infraestructura

### 1.1 Los timestamps existen en la base y se descartan en el `SELECT`

No es que el dato no tenga fecha. Se la usa para ordenar y se la tira. Mismo patrón, dos
veces:

| Timestamp | Existe en | Uso actual | ¿Llega a la decisión? |
|---|---|---|---|
| `fecha_publicacion` | `transacciones_temporales` | `ORDER BY … LIMIT 1` del `LATERAL` | ✗ no se selecciona |
| `creado_en` | `entorno_curacion` | `ORDER BY creado_en DESC` | ✗ no se selecciona |

`created_at` / `updated_at` de `activos_inmutables` tampoco se seleccionan.

Reparable —dos columnas en dos `SELECT`— pero es cambio de comportamiento en la capa de
datos y **F2 es paridad**. Va como deuda, no como arreglo dentro de E2.3a.

### 1.2 Las preferencias son extracción de un LLM, sin traza a la declaración

`extraer_preferencias` (`app/preferencias.py:145`) devuelve `_sanitizar(block.input)`: un
dict plano. No conserva qué frase produjo qué campo, ni el índice del mensaje, ni la
confianza del extractor.

Que `preferencias["presupuesto_max"] == 700` **no demuestra que la persona dijera 700**.
Un `EvidenceRefV0` con `USER_DECLARED` afirmaría que *la persona lo declaró*; lo que
tenemos es que *un modelo lo extrajo*. Son cosas distintas y el enum ya distingue: el
segundo caso es `HEURISTIC_ESTIMATE`, con `limitations` obligatoria.

**Ninguna preferencia puede citarse hoy como `USER_DECLARED`.** Lo cierra F3.

### 1.3 Existe UN timestamp verdadero, y no respalda ninguna razón

`verificacion_de_entorno` (`app/rutas.py:247`) devuelve `{activo_id: 'AAAA-MM-DD'}`: cuándo
un corredor **pisó físicamente** algún lugar de ese entorno. Y sí llega a la fila, como
`row["verificado_en_terreno"]`.

Es la única procedencia del flujo con `observed_at` real. Con dos matices que son parte de
la evidencia, no notas al pie:

- Es **de entorno y se propaga por proximidad** — el corredor verifica la farmacia parado
  en A y B enfrente hereda la insignia. Eso es `limitations`, obligatoria.
- **No respalda ninguna de las 17 razones.** Es insignia de tarjeta, no dimensión de
  scoring. La evidencia más fuerte que tenemos no sostiene ningún claim del panel.

---

## 2. La tabla

| # | Dimensión | Dato exacto | Origen real | ¿Construible? | ¿Resoluble hoy? | Estado E2.3a | Cierra |
|---|---|---|---|---|---|---|---|
| 1 | `tipo_inmueble` | `tipo_activo` vs pref | operador declara | ⚠️ sin `source_id` | ✗ | `YES_BUT_LATER` | **F5** |
| 2 | `presupuesto_max` | `precio` vs pref | proveedor / LLM | ⚠️ precio sí, tope no | ✗ | `YES_BUT_LATER` | **F5 + F3** |
| 3 | `caminable` | `walk_score` + `walk_score_fuente` | Contexto sobre OSM | ✅ **sí** | ✗ | `YES_BUT_LATER` | **F4** |
| 4 | `transporte` | regex sobre `conectividad` | Routes **o** OSM | ✗ fuente indistinguible | ✗ | `YES_BUT_LATER` | **F4** |
| 5 | `area_verde` | regex sobre `servicios_cercanos` | OSM + curación | ✗ | ✗ | `YES_BUT_LATER` | **F4** |
| 6 | `dormitorios` | `caracteristicas` JSONB | corredor | ⚠️ | ✗ | `YES_BUT_LATER` | **F5** |
| 7 | `acepta_mascotas` | `caracteristicas` JSONB | corredor | ⚠️ | ✗ | `YES_BUT_LATER` | **F5** |
| 8 | `tranquilidad` | `score_ruido_predictivo` | **nadie** | ✗ | ✗ | `INSUFFICIENT` | — |
| — | vegetación, tráfico | — | E0.4 los retiró | — | — | `NO_CLAIM` | — |
| ★ | `verificado_en_terreno` | `max(pois_vivos.verificado_en)` | corredor en terreno | ✅ **sí, con fecha** | ✗ | sin claim al que colgarse | **F4** |

**La fila 3 es la que cambió.** Se sabe construir —`walk_score_fuente` es procedencia real,
el arreglo de E0.3— pero tendría que citarse contra un `PlaceContextV0` que no se ensambla
en runtime. Construible ≠ resoluble.

Dos notas que no conviene que pasen de largo: la razón de **mayor peso (1.5) es la de
procedencia más débil**, y es la que el bloque autoritativo manda copiar literal. Y la fila
4 colapsa Google Routes y OSM en la misma palabra, `"mapa"`, demasiado vaga para un
`provider`.

### 2.1 Dos clasificaciones de `SourceType`, corregidas

| Dato | Clasificación anterior | Correcta | Por qué |
|---|---|---|---|
| `walk_score` medido | `PUBLIC_DATASET` | **`OWN_MEASUREMENT`** | El contrato lo define como *"calculado por Contexto sobre dato primario"*. OSM es el dato primario subyacente; **no es quien produjo el 82/100**. Exige `methodology`. |
| `walk_score` heurístico | `HEURISTIC_ESTIMATE` | **`HEURISTIC_ESTIMATE`** ✓ | Sin cambio. Exige `limitations`. |
| `verificado_en_terreno` | `OWN_MEASUREMENT` | **`OPERATOR_DECLARED`** | Lo declaró un corredor —que *"tiene interés comercial en el resultado"*— y Contexto solo lo propagó por proximidad. El enum no tiene `OPERATOR_OBSERVED`; `OPERATOR_DECLARED` con metodología y limitación explícitas es lo conservador. |

No afecta ninguna razón hoy. Se fija ahora para que no quede como precedente al llegar F4.

---

## 3. Desviación del Plan, declarada

El Execution Plan de F2 pedía esta cadena:

```
rows → DecisionContextV0 → cards actuales + bloque autoritativo del prompt
```

El estado real, verificado en el código:

| Flecha | Estado |
|---|---|
| `DecisionContext → cards` | **PASS** — `proyectar_cards` obedece al `ranking` del contrato |
| `DecisionContext → bloque autoritativo` | **TODAVÍA NO** |

`construir_panel` construye la lista `decisiones`, usa una para proyectar las cards y
**no las devuelve en el panel**: el retorno es `{cards, descartadas, preferencias,
priorizado}`. El bloque que ve el modelo se sigue armando desde ahí, no desde el contrato.

Decir antes **"E2.2 CLOSED / PASS"** fue más fuerte de lo que el texto literal del Plan
permitía. Esta tabla explica por qué la segunda flecha no se puede cerrar limpio: el
`DecisionContext` todavía no puede llevar las razones materiales sin inventar
`evidence_refs`.

**No es deuda técnica: es una dependencia arquitectónica descubierta por evidencia.** Va
al reporte de F2 sin maquillar.

---

## 4. Qué hace E2.3a, entonces

El Plan no pide "poner refs donde se pueda". Pide que **cada razón material pueda
referenciar evidencia estructurada o declarar que no hay suficiente**. Omitir del contrato
las seis dimensiones que sí afectan la decisión incumpliría la segunda mitad.

`UncertaintyV0` es la única afirmación cuya evidencia puede estar vacía, y lo es
exactamente por esto. Así que:

```
para cada razón MATERIAL que participó en la decisión:
    evidencia resoluble  → claim material + evidence_refs
    sin evidencia        → UncertaintyV0 que registra el hueco
```

Lo que la incertidumbre afirma **no** es "no sabemos el valor" — el sistema lo conoce y lo
usó. Afirma algo más preciso e incómodo: *conocemos el valor que movió la decisión, pero
todavía no podemos probar de dónde salió.*

`impact` se **deriva del motor**, no se fija a ojo:

| | Regla | Dimensiones hoy |
|---|---|---|
| `HIGH` | el hueco puede cambiar elegibilidad o sacar una opción de la vista | `tipo_inmueble` (requisito duro → topa a 49 < umbral 60 del panel), `presupuesto_max` (gobierna el corte de `_recortar_grid`) |
| `MEDIUM` | mueve score y ranking, no elegibilidad | el resto, cuando `aporta=True` |
| `LOW` | no altera la decisión hoy | cualquiera con `aporta=False` |

`HIGH` se deriva de `encaje._REQUISITOS_DUROS`, no de una lista paralela: agregar un
requisito duro allá sube el impacto acá solo, y hay un test que lo fija.

**No se emiten** `eligibility.violations`, `match.dimensions`, `strengths` ni `tradeoffs`:
las cuatro exigen `evidence_refs` no vacía —`ViolationV0` lo tiene congelado desde E1.5— y
no hay dónde resolverlas.

### El gate

> Ninguna razón que afectó la decisión puede quedar simultáneamente **sin `evidence_refs`
> resolubles Y sin incertidumbre correspondiente.**

Está escrito sobre la disyunción, no sobre el estado de hoy: cuando F4 haga resoluble la
caminabilidad, esa dimensión migra al primer camino y el gate sigue pasando sin tocarlo.

Resultado medido hoy:

```
afirmaciones materiales con evidencia = 0
incertidumbres que explican el hueco  = N (una por razón)
```

Eso no es un fracaso de E2.3. Es la primera vez que el sistema sabe de forma estructurada
qué parte de su propia decisión todavía no puede demostrar.

---

## 5. Deuda por destino

| Destino | Qué cierra |
|---|---|
| **F3** — Buyer Harness | Traza declaración → preferencia. Hoy ninguna preferencia es `USER_DECLARED`. |
| **F4** — Place | `PlaceContextV0` en runtime: caminabilidad (ya construible), transporte, área verde, ruido, verificación de terreno. Tipar `conectividad` y los POIs. |
| **F5** — Property | `PropertyContextV0` en runtime: tipo, precio, dormitorios, mascotas. Tipar `caracteristicas`. |
| **Capa de datos** | Seleccionar `fecha_publicacion` y `entorno_curacion.creado_en` para que `observed_at` deje de ser `None` por descarte. |
