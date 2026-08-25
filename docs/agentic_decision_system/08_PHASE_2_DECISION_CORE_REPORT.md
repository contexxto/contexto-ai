# FASE 2 — DECISION CORE · Reporte de cierre

**Documento verificable, no narrativa.** Cada cifra de §7 se leyó del runner contra
`67ad58e` —el último HEAD de código— con el árbol limpio, inmediatamente antes de
escribirla; ninguna se copió de un mensaje de commit. Cada afirmación estructural apunta a
un archivo, una línea o un SHA.

**Sobre el SHA de cierre.** Este documento no puede contener el hash del commit que lo
añade: no existe hasta que el commit se crea. Por eso el HEAD de cierre se identifica por
lo que es —el commit que añade este reporte— y por una propiedad **comprobable desde
fuera**: no toca código ni tests. Poner un SHA aquí sería o falso o imposible.

---

## 1. Baseline y alcance

| | |
|---|---|
| **Base inicial** | `84eb2c02747bef7d512e5e86b148c2f4de405530` (merge de F1, PR #123) |
| **HEAD de código probado** | `67ad58ef592ae368c46c5e38edceacbb7eebdc49` — el último commit que toca código o tests. Todas las cifras de §7 se midieron aquí |
| **HEAD de cierre** | el commit que añade este reporte. **Solo documentación**: `git diff --name-only 67ad58e <cierre>` no devuelve nada fuera de `docs/` |
| **Rama** | `feat/decision-core-v0` |
| **Worktree** | `…/scratchpad/f2` — árbol limpio, `git status --porcelain` vacío |
| **Commits** | 14 |
| **Tests** | 1 172 → **1 334** (+162), ambos extremos `exit 0` |
| **PR** | ninguno abierto. F2 se detiene aquí por instrucción. |

### Autorizado

E2.1 extracción de `construir_panel()` · E2.2 `DecisionContextV0` antes de cards/prosa ·
E2.3 evidencia · E2.4 `verificacion_prosa.py` como dependencia del core en modo auditoría.
Prioridad fijada: **PARIDAD → ESTRUCTURA → INTEGRACIÓN → mejora**.

### Explícitamente fuera

- **CRM y handoff** — prohibido tocarlos por esto.
- **Buyer store, persistencia, tracing** — F3 y F6.
- **Assemblers de Place / Property / Buyer** — F4, F5, F3.
- **F3 en cualquier forma.** No se inició.
- **Dos caminos funcionales** (con `session_id` → contrato / sin él → legacy). Prohibido y
  no introducido: sin `session_id` el turno levanta `SessionIdAusente`.

---

## 2. Commit ledger

| # | SHA | Propósito | Archivos | Tests | Hallazgo que lo motivó |
|---|---|---|---|---|---|
| 1 | `df08478` | Oráculo de paridad **antes** de mover nada | +`tests/test_caracterizacion_panel_legado.py` | 40 hoy | Sin oráculo, una extracción de 557 líneas no es verificable |
| 2 | `b18e39a` | Extraer el assembler | +`app/decision/{__init__,assembler}.py`, `routers/chat.py`, 9 tests | — | `construir_panel` decidía dentro de la capa HTTP |
| 3 | `f98b7d0` | `graph.py` deja de importar decisión desde `routers` (C3) | `app/agent/graph.py` | — | Import multilínea que el grep textual no alcanzó |
| 4 | `53683f3` | Congelar Gate C por AST + `ARCH-DEBT-F2-01` | +`tests/test_arquitectura_decision_core.py` | 12 hoy | El criterio original era más amplio que el alcance de F2 |
| 5 | `348f96b` | Primer `DecisionContextV0` real, sin HTTP ni UI | +`app/decision/context.py`, +test | 33 hoy | **Gate F2 literal** |
| 6 | `4ee2295` | El motor declara su `score_version` o no hay contexto | `context.py`, test | — | `or SCORE_VERSION` era mentira silenciosa |
| 7 | `de342b3` | **Invertir la autoridad**: la presentación sigue al ranking | `assembler.py`, `context.py`, +`test_autoridad_de_la_decision.py` | 15 hoy | Dos sitios calculaban el mismo orden; el visible ganaba |
| 8 | `4ac7ca0` | El ranking pasa a vivir **dentro** del contrato | `context.py`, test | — | La autoridad estaba en una función, no en el objeto |
| 9 | `51be776` | El turno **real** decide a través del contrato | `graph.py`, `assembler.py`, `context.py`, `chat.py`, +2 tests | 13 + 3 | El contrato existía y nadie lo consumía: dos cores |
| 10 | `1e501d7` | Una identidad y un instante por ensamblado | `assembler.py`, test | — | `decision_id = session:property` colisionaba entre turnos |
| 11 | `240e17f` | Tabla de procedencia, **antes** de código | +`E2_3_TABLA_DE_PROCEDENCIA.md` | — | Regla de oro: procedencia primero |
| 12 | `e4de559` | Corrección de la tabla tras verificar | mismo doc | — | Dos afirmaciones mías no aguantaron el código |
| 13 | `15801bc` | **E2.3a** — registrar el hueco, no fabricar procedencia | +`evidencia.py`, `context.py`, `graph.py`, +test, doc | 30 | Cero razones con evidencia resoluble |
| 14 | `67ad58e` | **E2.4** — verifier como componente del core | +`decision/verify.py`, `chat.py`, +test | 16 | El router interpretaba gravedades |

Los commits 11 y 12 son documentales. El 12 corrige al 11: **la primera versión de la
tabla afirmaba que faltaban timestamps y que la curación tenía fecha utilizable; ninguna
de las dos cosas resultó exacta.** Queda en el ledger a propósito.

---

## 3. E2.1 — Extracción

**557 líneas salieron de `app/routers/chat.py`; 561 entraron a `app/decision/assembler.py`.**
`construir_panel`, `build_result_cards`, `_card_from_row`, `_senales_encaje`,
`_fetch_cards_rows`, `_fetch_curaciones_batch`, `_recortar_grid`,
`_priorizado_por_el_modelo`, `_collect_asset_ids`, `_user_texts`, `_pois_de_intencion`,
`_min_a_pie`, `_transporte_min`, `_MAX_CARDS`, `_ENCAJE_MIN_GRID`.

**Paridad: 40/40** en `tests/test_caracterizacion_panel_legado.py` (29 funciones,
parametrizadas — mismas 29 en `df08478` que en el HEAD final), escritas *antes* del
movimiento y verdes en todo momento desde entonces.

### Gate C — criterio reformulado, no flexibilizado

El criterio original decía «`agent/` no importa `routers/`». La caracterización demostró
que había **cinco** imports `agent → routers` y **solo uno** pertenecía al carril de
decisión; los otros cuatro son CRM y handoff, que F2 tiene prohibido tocar. Cumplirlo al
pie habría convertido una extracción controlada en una refactorización transversal.

Quedó **formalmente sustituido**:

```
C1  app/decision no importa fastapi ni app.routers
C2  el carril de decisión de agent no depende de app.routers
C3  graph.py no importa decisión desde routers.chat
C4  ningún import agent → routers nuevo respecto al baseline
C5  los preexistentes quedan inventariados como deuda, no como resueltos
```

**12/12 verde.** C1 se parametriza sobre cada `.py` de `app/decision`, así que cubrió
`evidencia.py` y `verify.py` automáticamente al aparecer.

### `ARCH-DEBT-F2-01`

Los cuatro imports que sobreviven, verificados en el HEAD final:

```
app/agent/crm_tools.py → app.routers.assets  (_activos_del_corredor, _funnel_y_orden, …)
app/agent/crm_tools.py → app.routers.assets  (_leads_del_corredor)
app/agent/crm_tools.py → app.routers.chat    (transcript_de_sesion, ensure_handoff_tables)
app/agent/tools.py     → app.routers.chat    (registrar_handoff)
```

Más, fuera de `agent/`: `app/reenganche_cron.py → app.routers.chat`.

El grandfathering es **exacto, no genérico**: se toleran esos imports concretos por
`(fichero, módulo)`. Un quinto hace fallar el gate. Esa es toda la diferencia entre una
excepción registrada y un precedente.

> **Declaración literal exigida:** al cerrar F2 se puede afirmar *«el Decision Core ya
> tiene la dirección de dependencias correcta»*. **NO** se puede afirmar *«`agent/` está
> desacoplado de `routers/`»* — eso **sigue siendo falso globalmente**, y lo será hasta que
> exista una tarea explícita de separación CRM/handoff.

---

## 4. E2.2 — Autoridad

### La evolución completa

| Etapa | Commit | Quién decidía |
|---|---|---|
| 0 · legacy | `84eb2c0` | las cards se ordenaban solas y `_recortar_grid` recalculaba el presupuesto |
| 1 | `de342b3` | el core decide ranking y presupuesto; la presentación **consume** |
| 2 | `4ac7ca0` | el ranking pasa a vivir **dentro** de `DecisionContextV0` |
| 3 | `51be776` | el **turno real** construye el contexto y proyecta a través de él |
| 4 | `1e501d7` | una identidad y un instante por ensamblado |

El cambio estructural que lo hace irreversible: `_recortar_grid(cards, sobre_presupuesto,
protegidos=None)` **ya no recibe `preferencias`**. No es que se le pida no recalcular el
presupuesto: no puede.

**Hasta dónde llega esto, exactamente.** Lo que migró al contrato es el **ranking**. El
veredicto de presupuesto y el corte de visibilidad se decidieron **una sola vez y en el
core**, que es la mitad del problema resuelta — pero **no viven dentro de
`DecisionContextV0`**. La distinción entre "una sola autoridad" y "la autoridad está en el
objeto" se detalla en §10.a; no darla por equivalente es el motivo de esta nota.

### Cinco defectos semánticos, encontrados y cerrados

| Defecto | Qué producía | Cierre |
|---|---|---|
| **`place_id`** | inventar un id sin coordenadas → un lugar que no existe | `CoordenadasAusentes`. Con lat/lon válidos, `point-v0` determinístico por `sha256` (no `hash()`, que es aleatorio por proceso). Sin ellas: **no se inventa, no se excluye en silencio, se escala** |
| **`score_version`** | `or SCORE_VERSION` afirmaba una versión que el motor no declaró | `EncajeSinVersion`. Si el motor declara otra, **se usa la que dice**; no se normaliza |
| **`session_id`** | `session:unknown` o un UUID nuevo → un contexto que valida y no corresponde a nadie | `SessionIdAusente`. Se propaga por `RunnableConfig`, **no** por `AgentState` — probado antes contra `langgraph==0.2.60`, la versión fijada, no la documentada |
| **`decision_id`** | `session:property` colisionaba: la misma propiedad en la misma sesión reusaba identidad entre turnos, aunque cambiaran preferencias o ranking | ámbito por ensamblado |
| **`created_at`** | instantes distintos dentro de un mismo panel → no eran el mismo evento lógico | uno solo por panel |

Las cuatro excepciones de integridad se **re-lanzan antes** del `except Exception` genérico
de `encaje_node`. Si se tragaran, el turno seguiría por el camino legacy y la condición que
habría hecho falso el contexto quedaría invisible — el modo de fallo que F0 se pasó
cerrando. Hay test por AST que verifica el **orden** de los manejadores.

---

## 5. E2.3a — Cobertura de evidencia

### El resultado, sin suavizar

```
razones materiales con evidence_refs resolubles end-to-end = 0
incertidumbres que registran el hueco                      = N (una por razón)
```

**Cero no significa "no hay datos".** El sistema conoce cada valor y lo usó para decidir.
Significa que los contextos que deben **contener y resolver** esa evidencia —`BuyerContextV0`,
`PlaceContextV0`, `PropertyContextV0`— no se ensamblan en runtime. `DecisionContextV0`
guarda `evidence_id` y **cita**; hoy no hay contra qué.

La tabla completa está en [`E2_3_TABLA_DE_PROCEDENCIA.md`](E2_3_TABLA_DE_PROCEDENCIA.md).
Tres hallazgos que la sostienen:

1. **Los timestamps existen y se descartan.** `fecha_publicacion` y `entorno_curacion.creado_en`
   se usan en el `ORDER BY` y no se seleccionan. La fecha existe; la query la tira.
2. **Las preferencias son extracción de un LLM sin traza a la declaración.** Que
   `presupuesto_max == 700` no demuestra que la persona dijera 700. **Ninguna preferencia
   puede citarse hoy como `USER_DECLARED`.**
3. **Existe un timestamp verdadero y no respalda ninguna razón.** `verificado_en_terreno`
   es insignia de tarjeta, no dimensión de scoring.

Se corrigió además la taxonomía antes de que sentara precedente: `walk_score` medido es
`OWN_MEASUREMENT` (no `PUBLIC_DATASET` — OSM es el dato primario, no quien produjo el
82/100), y `verificado_en_terreno` es `OPERATOR_DECLARED` (no `OWN_MEASUREMENT` — lo
declaró un corredor con interés comercial y Contexto solo lo propagó por proximidad).

### El gate

> Ninguna razón que afectó la decisión puede quedar simultáneamente sin `evidence_refs`
> resolubles **y** sin incertidumbre correspondiente.

Escrito sobre la **disyunción**, no sobre el estado de hoy: cuando F4 haga resoluble la
caminabilidad, esa dimensión migra al primer camino y el gate sigue pasando sin tocarlo.

`impact` se **deriva del motor**: `HIGH` desde `encaje._REQUISITOS_DUROS` ∪ la dimensión que
gobierna el corte del panel — no de una lista paralela que divergiría en silencio.

### Deuda por destino

| Destino | Qué cierra |
|---|---|
| **F3** | Traza declaración → preferencia (`presupuesto_max`, `tipo_inmueble`, …) |
| **F4** | `PlaceContextV0` en runtime: caminabilidad *(ya construible)*, transporte, área verde, ruido |
| **F5** | `PropertyContextV0` en runtime: tipo, precio, dormitorios, mascotas |
| **Capa de datos** | Seleccionar los dos timestamps que hoy se descartan en el `ORDER BY` |

### Guardrail

`DimensionSinProcedencia` — una dimensión nueva en `encaje.py` sin fila de procedencia
levanta y se propaga como fallo de integridad. Omitirla produciría exactamente el estado
que el gate prohíbe: una razón que mueve la decisión, invisible en el contrato.

---

## 6. E2.4 — Verifier

```
router  →  app/decision/verify.py  →  app/verificacion_prosa.py
```

`verificacion_prosa.py` **no se reescribió**. Qué cuenta como violación, con qué gravedad y
con qué evidencia sigue decidiéndose allí. Los **34 tests legacy están intactos**.

| | |
|---|---|
| **Mapeo** | `alguna ALTA → FAILED` · `sin ALTA, alguna MEDIA → WARNING` · `cero → PASSED` |
| **Mezclar** | no promedia: una grave con varias leves sigue siendo `FAILED` |
| **Fail-loud** | gravedad fuera de `alta\|media` → `GravedadDesconocida`. No se normaliza |
| **Audit-only** | no bloquea, no reescribe, no reintenta, no retrasa. Verificado por AST: `_auditar_prosa` no tiene `return` con valor ni `raise` |
| **Persistencia** | ninguna. `model_copy(update={"explanation": …})` demuestra que el contrato acepta la pieza; el original queda intacto por ser `frozen` |
| **Observabilidad** | `registrar()` conserva el detalle por código; una línea nueva expresa el veredicto del turno. Logs, **no** métrica persistente ni SLA |

---

## 7. Paridad y resultados finales

Leídos del runner contra `67ad58e` —**el último HEAD de código**— con el árbol limpio,
justo antes de escribir esta tabla.

```
HEAD=67ad58ef592ae368c46c5e38edceacbb7eebdc49   git status --porcelain → vacío
pytest -q  →  exit 0        FAILED/ERROR = 0
```

| Suite | Tests | Estado |
|---|---:|---|
| **Total** | **1 334** | `exit 0` |
| Caracterización (paridad) | 40 | `exit 0` |
| Gate C — arquitectura | 12 | `exit 0` |
| Autoridad de la decisión | 15 | `exit 0` |
| Runtime decide por el contrato | 13 | `exit 0` |
| `DecisionContextV0` real | 33 | `exit 0` |
| Cobertura de evidencia (gate E2.3) | 30 | `exit 0` |
| Verifier como componente | 16 | `exit 0` |
| **`verificacion_prosa` legacy** | **34** | `exit 0` — intactos |
| LangGraph `RunnableConfig` | 3 | `exit 0` |

**Baseline `84eb2c0`: 1 172 tests, `exit 0`.** Medido en un worktree efímero sobre ese SHA,
no recordado. Delta **+162**.

---

## 8. Evaluación requisito por requisito

| Requisito del Plan | Veredicto | Evidencia |
|---|---|---|
| E2.1 · `construir_panel()` fuera de `routers/chat.py` | **PASS** | `b18e39a`; 557 líneas movidas |
| E2.1 · paridad sin cambio observable | **PASS** | 40/40 caracterización |
| E2.1 · Gate C (C1–C5) | **PASS** | 12/12; `ARCH-DEBT-F2-01` inventariado |
| E2.2 · `DecisionContextV0` antes de cards | **PASS** | `348f96b`, `51be776` |
| E2.2 · mismo input → mismo ranking | **PASS** | `test_mismo_input_y_mismo_session_id_dan_la_misma_decision` |
| E2.2 · hard constraints sin cambio | **PASS** | `_REQUISITOS_DUROS` intacto; caracterización cubre el caso |
| E2.2 · independencia de HTTP | **PASS** | subproceso sin `fastapi` en `sys.modules` |
| E2.2 · **orden de cards derivado del contrato** | **PASS** | `DecisionContextV0.ranking` gobierna la proyección: `proyectar_cards` lee **ese campo y nada más** (`context.py:335`) |
| E2.2 · **selección final visible derivada del contrato** | **PARTIAL / ACCEPTED DEVIATION** | La visibilidad final sigue siendo una decisión del **Decision Core** (`decidir_sobre_presupuesto` + `_recortar_grid` + tope `_MAX_CARDS`) **todavía no representada dentro de `DecisionContextV0`**. §10 |
| E2.2 · **bloque autoritativo derivado del contrato** | **PARTIAL / ACCEPTED DEVIATION** | §10 |
| E2.3 · cada razón material referencia evidencia **o** declara insuficiencia | **PASS** | gate de cobertura, 30 tests. Resultado: 0 refs / N incertidumbres |
| E2.3 · nunca fabricar procedencia | **PASS** | tabla de procedencia; `evidence_refs=()` en toda la decisión |
| E2.4 · verifier como dependencia del core | **PASS** | `router → decision.verify → verificacion_prosa` |
| E2.4 · modo auditoría, sin bloqueo | **PASS** | AST sobre `_auditar_prosa` |
| E2.4 · sin cambiar qué es una violación | **PASS** | 34 legacy intactos |
| Buyer store / persistencia | **NOT APPLICABLE** | F3 / F6 |
| Place / Property assemblers | **NOT APPLICABLE** | F4 / F5 |
| CRM y handoff | **NOT APPLICABLE** | fuera de alcance por instrucción |

---

## 9. Gate F2, literal

> *«El primer `DecisionContextV0` real puede generarse sin FastAPI y sin UI.»*

**Demostrado.** `tests/test_decision_context_desde_decision_real.py:261` —
`test_el_objeto_se_construye_sin_fastapi_cargado`. No es una aserción sobre imports en el
mismo intérprete: lanza un **subproceso limpio**, importa `app.decision.context` y verifica

```python
assert 'fastapi' not in sys.modules
assert 'app.routers' not in sys.modules
```

antes de construir un `place_id` real. Un test en el proceso de pytest habría pasado por
accidente, porque otras suites ya cargaron FastAPI.

Complementado por `test_el_modulo_no_importa_fastapi_ni_routers` (AST) y por C1 del Gate C,
que cubre **todos** los módulos de `app/decision`.

**GATE F2 — SATISFECHO.**

---

## 10. Lo que el contrato todavía no gobierna

### El estado real

```
DecisionContext → ranking / orden        PASS
Decision Core   → corte / visibilidad    PASS
DecisionContext → corte / visibilidad    PARTIAL / ACCEPTED DEVIATION
DecisionContext → bloque autoritativo    PARTIAL / ACCEPTED DEVIATION
```

### 10.a · El corte de visibilidad

El contrato gobierna el **orden**, no el **conjunto**. La cadena real del runtime:

```
DecisionContext.ranking → proyectar_cards → cards ordenadas
                        → decidir_sobre_presupuesto(cards, preferencias)
                        → _recortar_grid(cards, sobre_presupuesto)  [encaje < 60]
                        → [:_MAX_CARDS]                             [tope de 6]
                        → cards finalmente visibles
```

`proyectar_cards` lee `decision.ranking` y **ningún otro campo** (`context.py:335`). Las
tres decisiones posteriores —veredicto de presupuesto, umbral `_ENCAJE_MIN_GRID = 60` y
tope `_MAX_CARDS = 6`— pueden cambiar qué tarjetas se ven, y **ninguna está representada
dentro de `DecisionContextV0`**. Los propios tests lo confirman: para probar la autoridad
del presupuesto se hace monkeypatch de `assembler.decidir_sobre_presupuesto`, no de un
campo del contrato.

Lo que **sí** está cerrado es que esas decisiones se toman **una sola vez y en el core**:
`_recortar_grid` ya no recibe `preferencias`, así que no puede recalcular el presupuesto.
Antes había dos sitios comparando precio contra tope y ganaba el visible.

**Por qué no se mete el corte en el contrato hoy.** El campo que le corresponde es
`eligibility.violations` — y `ViolationV0` exige `evidence_refs` **no vacía**, congelado en
E1.5. Con `tipo_inmueble` y `presupuesto_max` en `YES_BUT_LATER` (§5), representar el corte
ahí exigiría fabricar referencias o adelantar F3/F5. **Es el mismo hallazgo de E2.3a, no
uno nuevo.**

### 10.b · El bloque autoritativo

`construir_panel` construye la lista `decisiones`, proyecta las cards a través de ella y
**no la devuelve**: el retorno es `{cards, descartadas, preferencias, priorizado}`. El
bloque que ve el modelo se sigue armando desde ahí.

Haberlo llamado antes **«E2.2 CLOSED / PASS»** fue más fuerte de lo que el texto literal
del Plan permitía. Queda corregido aquí.

### Las cuatro salidas, y por qué ninguna se aceptó

| Salida | Por qué se rechazó |
|---|---|
| Emitir claims materiales **sin refs resolubles** | El Blueprint exige que todo claim material apunte a evidencia. Serían `evidence_id` que validan y no resuelven — la misma familia que `place_id` inventado, `score_version` normalizado y `decision_id` colisionado |
| **Duplicar la procedencia** en un registry temporal dentro de `app/decision/` | Infraestructura no autorizada, y un cuarto sitio donde vive la evidencia. Justo lo que F1 evitó |
| Introducir **Place/Property/Buyer assemblers** antes de su fase | Es F3, F4 y F5. Adelantarlos aquí rompe el orden de fases por conveniencia |
| Cambiar la **salida legacy** | Rompería el objetivo declarado de paridad, que es la prioridad #1 de F2 |

**No es una deuda arbitraria.** El Blueprint exige que todo claim material apunte a
evidencia o quede marcado como incertidumbre; forzar hoy el bloque autoritativo desde
claims sin contextos reales rompería precisamente esa regla. La desviación **no contradice
el orden de las fases: explica por qué ese orden existe.**

---

## 11. Riesgos abiertos

| # | Riesgo | Severidad | Destino |
|---|---|---|---|
| 0 | **El corte de visibilidad vive fuera del contrato**: `decidir_sobre_presupuesto`, umbral 60 y tope 6 cambian el conjunto visible sin quedar representados en `DecisionContextV0`. Se toman en el core y una sola vez, pero el objeto no las lleva | **Alta** | F3–F5 (vía `eligibility.violations`, que hoy exigiría refs inventadas) |
| 1 | Bloque autoritativo todavía legacy: el modelo lee cards, no el contrato | **Alta** | F3–F5 |
| 2 | Preferencias extraídas por LLM sin evidencia de declaración | **Alta** | **F3** |
| 3 | `PropertyContextV0` no ensamblado: precio, tipo, dormitorios y mascotas sin procedencia resoluble | **Alta** | **F5** |
| 4 | `PlaceContextV0` no ensamblado: caminabilidad ya construible, sin dónde resolverse | Media | **F4** |
| 5 | Timestamps disponibles y descartados en el `SELECT` | Media | capa de datos |
| 6 | `ARCH-DEBT-F2-01`: 4 imports `agent → routers` + `reenganche_cron` | Media | tarea transversal CRM/handoff |
| 7 | Verifier audit-only y no persistente: se observa y no se actúa | Baja *(deliberado)* | cuando exista la cifra que justifique bloquear |
| 8 | `conectividad` y `servicios_cercanos` son texto libre parseado con regex | Media | **F4** |
| 9 | `caracteristicas` es JSONB sin tipar — en F1 se documentó un precio que contradecía la transacción | Media | **F5** |

El riesgo #2 es el que **F3 ataca de frente**: pasar de preferencias recalculadas por turno
a un estado persistente, versionado, corregible y con origen por campo.

---

## 12. Recomendación

```
FASE 2 — DECISION CORE
CLOSED / PASS WITH ACCEPTED DEVIATIONS

→ ADVANCE TO BUYER HARNESS — WITH ACCEPTED F2 DEVIATIONS
```

**Fundamento.** El Gate F2 literal está satisfecho y demostrado con un subproceso limpio.
Los cinco tests explícitos del Plan pasan. La paridad se sostuvo en 40/40 durante toda la
fase. La suite final es de **1 334 tests, `exit 0`, cero fallos**, contra el último HEAD de
código —`67ad58e`— con el árbol limpio. El commit que añade este reporte no modifica código
ni tests, así que esa medición sigue siendo representativa de lo que entra al PR.

Las **dos** desviaciones —el corte de visibilidad y el bloque autoritativo— están
**aceptadas con causa demostrada, y son la misma causa**: F2 descubrió, con una auditoría
de procedencia razón por razón, que sus claims materiales no tienen evidencia resoluble
hasta F3–F5. Cerrar cualquiera de las dos hoy exigiría violar una regla del Blueprint,
adelantar tres fases o romper la paridad.

Que aparezcan como dos filas y no como una es deliberado: describen superficies distintas
—qué tarjetas se ven, y qué lee el modelo— aunque las bloquee la misma dependencia.

**Nomenclatura, para que el reporte no se lea mal más adelante:** E2.3a está **cerrado**. La
materialización de refs reales no está *«hecha»* — está **correctamente diferida** a
F3/F4/F5. Eso no es un fallo del trabajo: es el resultado de la auditoría de procedencia.

---

*STOP. No se abre PR y no se inicia F3 hasta revisión.*
