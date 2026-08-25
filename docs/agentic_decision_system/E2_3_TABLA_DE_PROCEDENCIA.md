# E2.3 — Tabla de procedencia · razón legacy → ¿EvidenceRefV0 posible?

**Fase:** F2 · E2.3 · **paso previo obligatorio, sin código**
**Base:** `feat/decision-core-v0 = 1e501d7`
**Regla de oro:** si no se puede construir un `EvidenceRefV0` **verdadero** desde datos que
ya existen, la salida es `insufficient_evidence` o ausencia de claim. Nunca fabricar
procedencia para conservar una razón legacy.

`YES_NOW` significa *"puedo construirlo hoy con evidencia real y resoluble"*, **no**
*"puedo fabricar un objeto que valide"*. Esa distinción es toda la tabla.

---

## 0. Dos hallazgos que condicionan TODAS las filas

Antes de la tabla, porque cambian su lectura entera.

### 0.1 La fila del inmueble no trae NINGÚN timestamp

El `SELECT` de `_fetch_cards_rows` devuelve `id, direccion, tipo_activo, imagen_url,
caminabilidad, caminabilidad_fuente, ruido, vegetacion, servicios_cercanos, conectividad,
lat, lon, caracteristicas, operacion, precio`.

**No selecciona `created_at`, ni `updated_at`, ni `fecha_publicacion`** — esta última solo
aparece dentro del `ORDER BY` del `LATERAL`, para elegir la transacción vigente; nunca sale.

Consecuencia directa: para cualquier dato del inmueble, `EvidenceRefV0.observed_at` sería
`None` —correcto y permitido— pero **`retrieved_at` también carece de fuente real**. Lo
único honesto disponible es *"cuándo lo leímos"*, que es el instante del ensamblado. Eso
es legítimo para `retrieved_at`, pero conviene decirlo: **no sabemos de cuándo es el dato,
solo cuándo lo miramos**.

### 0.2 Las preferencias son extracción de un LLM, sin traza a la declaración

`extraer_preferencias(mensajes_usuario)` llama al modelo con una tool y devuelve
`_sanitizar(block.input)`: un dict plano. **No conserva qué frase produjo qué campo**, ni
el índice del mensaje, ni la confianza del extractor.

Esto importa mucho más de lo que parece. Que `preferencias["presupuesto_max"] == 700`
**no demuestra** que la persona dijera "700". Pudo decir "hasta setecientos", "unos 700",
"no más de 700 pero puedo estirarme", o el modelo pudo inferirlo de un contexto más largo.

Un `EvidenceRefV0` con `source_type=USER_DECLARED` afirmaría que **la persona lo declaró**.
Lo que tenemos es que **un modelo lo extrajo**. Son cosas distintas, y `SourceType` ya
tiene el valor correcto para la segunda: `HEURISTIC_ESTIMATE` — con su `limitations`
obligatoria.

**Ninguna preferencia puede citarse hoy como `USER_DECLARED`.** Resolverlo es F3 (Buyer
Harness), donde la extracción conserve la declaración que la originó.

---

## 1. La tabla

Las ocho dimensiones de `app/encaje.py::DIMENSIONES`, cada una con sus razones reales.

### 1.1 `tipo_inmueble` — requisito duro

| | |
|---|---|
| **Razón legacy** | *"Es un departamento, como pediste"* / *"Es una casa, no un departamento"* |
| **Dato exacto** | `row.tipo_activo` normalizado vs `preferencias.tipo_inmueble` normalizado |
| **Dónde vive hoy** | `activos_inmutables.tipo_activo` (columna tipada) |
| **Quién lo afirmó** | El inventario propio. Lo cargó un corredor o el seed. |
| **Naturaleza** | Declaración del proveedor sobre su propio activo |
| **Timestamp** | ✗ ninguno (§0.1) |
| **¿Evidencia del dato o del cálculo?** | Del **cálculo**. La comparación es determinista y verificable; que el activo *sea* un departamento es una declaración sin verificar. |
| **`EvidenceRefV0` posible** | **YES_BUT_LATER** |
| **Por qué no ahora** | `source_type=OPERATOR_DECLARED` sería correcto, pero `source_id` debería apuntar al registro del inmueble — y esa identidad la da `PropertyContextV0`, que no se ensambla en runtime hasta F5. Citar un `evidence_id` que no resuelve contra nada es una referencia rota a propósito. |
| **Tratamiento** | La razón se conserva como texto legacy. **Sin claim material en `DecisionContextV0`** hasta F5. |

### 1.2 `presupuesto_max`

| | |
|---|---|
| **Razón legacy** | *"Dentro de tu presupuesto ($380 ≤ $700)"* / *"Sobre tu tope por $10"* |
| **Dato exacto** | `row.precio` (de `transacciones_temporales`, la vigente) vs `preferencias.presupuesto_max` |
| **Dónde vive hoy** | `transacciones_temporales.precio`, vía `LATERAL` con `estado_anuncio='ACTIVO'` |
| **Quién lo afirmó** | El **precio**: el proveedor. El **tope**: extracción LLM (§0.2). |
| **Naturaleza** | Precio = declaración del proveedor · Tope = inferencia del modelo |
| **Timestamp** | ✗ `fecha_publicacion` existe en la tabla pero **no se selecciona** |
| **¿Evidencia del dato o del cálculo?** | La aritmética es verificable y determinista. **Ninguno de sus dos inputs tiene procedencia trazable hoy.** |
| **`EvidenceRefV0` posible** | **YES_BUT_LATER** (precio) · **NO como `USER_DECLARED`** (tope) |
| **Nota fuerte** | Es la razón que el bloque autoritativo pide copiar literal, y la de mayor peso (1.5). Que su procedencia sea la más débil de las ocho es exactamente el tipo de asimetría que conviene tener escrita. |
| **Tratamiento** | Razón legacy intacta. Sin claim material hasta que exista `PropertyContextV0` en runtime (F5) y traza de declaración (F3). |

### 1.3 `caminable`

| | |
|---|---|
| **Razón legacy** | *"Buscabas caminable · caminabilidad 82/100"*, con `fuente` = `"OpenStreetMap"` o `"estimación por zona"` |
| **Dato exacto** | `row.caminabilidad` (0-100) + `row.caminabilidad_fuente` ∈ {`osm`, `heuristico`, `NULL`} |
| **Dónde vive hoy** | `activos_inmutables.walk_score` + `walk_score_fuente` |
| **Quién lo afirmó** | Medición propia sobre dataset público (OSM), **o** heurística de zona |
| **Naturaleza** | **Depende de la fila.** Es la única dimensión que ya distingue medición de estimación — el arreglo de E0.3. |
| **Timestamp** | ✗ ninguno |
| **¿Evidencia del dato o del cálculo?** | Del dato: `walk_score_fuente` es procedencia real, registrada por el sistema que la calculó. |
| **`EvidenceRefV0` posible** | **YES_NOW** ⭐ — la única |
| **Cómo** | `osm` → `PUBLIC_DATASET` + `provider="osm"` + `methodology="walk_score sobre red peatonal OSM"`. `heuristico`/`NULL` → `HEURISTIC_ESTIMATE` + `limitations=("no es medición sobre red…",)`. `observed_at=None` (OSM no dice de cuándo). `retrieved_at` = instante del ensamblado. |
| **Dónde se resuelve el id** | Aquí está el matiz: la evidencia **pertenece a `PlaceContextV0`**, que tampoco se ensambla en runtime. Se puede *construir* honestamente hoy; **no hay dónde resolverla**. |
| **Tratamiento** | Ver §2: es la fila que decide la forma de E2.3. |

### 1.4 `transporte`

| | |
|---|---|
| **Razón legacy** | *"masivo a ~7 min a pie"*, `fuente="mapa"` |
| **Dato exacto** | `_transporte_min(row.conectividad)` — minutos parseados del texto |
| **Dónde vive hoy** | `activos_inmutables.conectividad`, **texto libre** |
| **Quién lo afirmó** | Google Routes (si el texto trae `(19 min a pie)`) o distancia OSM ÷ 80 m/min |
| **Naturaleza** | Medición de proveedor **o** derivación heurística — **y el texto no siempre lo distingue** |
| **Timestamp** | ✗ ninguno |
| **¿Evidencia del dato o del cálculo?** | Del cálculo. El input es **prosa parseada con regex**, no un campo tipado. |
| **`EvidenceRefV0` posible** | **YES_BUT_LATER**, y con reserva |
| **La reserva** | `"mapa"` es una fuente demasiado vaga para `provider`. Google Routes y OSM no son lo mismo y hoy se colapsan en la misma palabra. Distinguirlos exige tipar `conectividad`, que es F4. |
| **Tratamiento** | Razón legacy intacta. Sin claim material. **Registrar como deuda**: la fuente real existe pero está enterrada en texto. |

### 1.5 `area_verde`

| | |
|---|---|
| **Razón legacy** | *"parque a ~4 min a pie"*, `fuente="mapa"` · o `INSUFICIENTE` |
| **Dato exacto** | `_min_a_pie(row.servicios_cercanos, _EMOJI_PARQUE)` |
| **Dónde vive hoy** | `activos_inmutables.servicios_cercanos`, texto de OSM ya curado por el corredor |
| **Quién lo afirmó** | OSM + posible curación humana (Catastro Vivo) |
| **Naturaleza** | Dataset público, con overlay humano cuando existe |
| **Timestamp** | ⚠️ **parcial** — `entorno_curacion` sí tiene fecha, y `verificado_en_terreno` llega en la fila; el POI base de OSM no |
| **¿Evidencia del dato o del cálculo?** | Mixto: el parque medido es dato; los minutos son derivación (`distancia ÷ 80`) |
| **`EvidenceRefV0` posible** | **YES_BUT_LATER** |
| **Matiz que vale oro** | Es la única dimensión donde **ya existe un timestamp real** (la curación). Cuando F4 tipe los POIs, esta fila puede ser la primera con `observed_at` verdadero. |
| **Tratamiento** | Razón legacy intacta. Sin claim material. E0.4 ya la sacó del scoring cuando solo hay `vegetacion`. |

### 1.6 `dormitorios`

| | |
|---|---|
| **Razón legacy** | *"N dormitorios"*, `fuente="ficha del inmueble"` |
| **Dato exacto** | `caracteristicas.num_dormitorios` |
| **Dónde vive hoy** | JSONB `caracteristicas` — **sin tipar, 25 llaves observadas** |
| **Quién lo afirmó** | El corredor que cargó la ficha |
| **Naturaleza** | Declaración del operador, sin verificar |
| **Timestamp** | ✗ ninguno |
| **¿Evidencia del dato o del cálculo?** | Del cálculo. El input viene del mismo JSONB que en F1 se documentó con **un precio que contradecía la transacción**. |
| **`EvidenceRefV0` posible** | **YES_BUT_LATER** |
| **Tratamiento** | Sin claim material. `PropertyContextV0` ya tipa esto (`PropertyAttribute`); F5 lo hará real. |

### 1.7 `acepta_mascotas`

| | |
|---|---|
| **Razón legacy** | *"Acepta mascotas"* / *"No acepta mascotas"*, `fuente="ficha del inmueble"` |
| **Dato exacto** | `caracteristicas.acepta_mascotas` (bool) |
| **Resto** | Idéntico a §1.6 |
| **`EvidenceRefV0` posible** | **YES_BUT_LATER** |
| **Nota** | Es la dimensión que en producción llevó al modelo a priorizar una opción con motivo declarado. Un booleano de un JSONB sin tipar sosteniendo una recomendación es, en sí mismo, algo que conviene tener anotado. |

### 1.8 `tranquilidad` (ruido)

| | |
|---|---|
| **Razón legacy** | *"Buscabas tranquilidad · no tenemos medición de ruido aquí"* → `INSUFICIENTE`, `fuente=None`, `aporta=False` |
| **Dato exacto** | `row.ruido` = `score_ruido_predictivo`, `String(10)` con valores tipo `"BAJO"` |
| **Quién lo afirmó** | Nadie: es un **campo predictivo sin medición** detrás |
| **`EvidenceRefV0` posible** | **INSUFFICIENT** |
| **Tratamiento** | **Ya es correcto y no se toca.** E0.4 lo sacó del scoring y le dejó su estado explícito. En `DecisionContextV0` corresponde `UncertaintyV0` —que admite `evidence_refs=()`— y **nunca** un `StrengthV0`. |

### 1.9 Vegetación y tráfico — sin razón propia

`row.vegetacion` (`porcentaje_cobertura_vegetal`) y `volumen_trafico_historico` **ya no
generan razón**: E0.4 los retiró. `volumen_trafico_historico` está además en `0` para todo
el inventario.

| **`EvidenceRefV0` posible** | **NO_CLAIM** |
|---|---|
| **Tratamiento** | No aparecen en `DecisionContextV0` ni como incertidumbre, salvo que la persona declare la dimensión — y entonces como `UncertaintyV0`, igual que el ruido. |

---

## 2. El hallazgo que decide la forma de E2.3

Contando: **una** fila es `YES_NOW` (caminabilidad), **seis** son `YES_BUT_LATER`, **una**
`INSUFFICIENT`, **dos** `NO_CLAIM`.

Y la única `YES_NOW` tiene un problema propio: la evidencia de caminabilidad **pertenece a
`PlaceContextV0`**, que no se ensambla en runtime. `DecisionContextV0.evidence_refs` guarda
`evidence_id`, y el diseño de F1 dice explícitamente que **la evidencia vive en los
contextos referenciados** — la decisión los cita, no los almacena.

Hoy no existe ese sitio. Las tres opciones y por qué descarto dos:

| Opción | Veredicto |
|---|---|
| Construir un "registry temporal" de evidencia en `app/decision/` | ❌ Es infraestructura nueva no autorizada, y crearía un cuarto sitio donde vive la evidencia. Justo lo que F1 evitó. |
| Emitir `evidence_refs` con ids que hoy no resuelven contra nada | ❌ Referencias rotas producidas conscientemente. El propio prompt de F2 lo prohíbe. |
| **Ensamblar `PlaceContextV0` en runtime para la caminabilidad** | ⚠️ Es **F4**. Fuera del alcance de F2. |

**Conclusión: E2.3, tal como se especificó, no se puede completar dentro del alcance de
F2 sin violar una de sus propias reglas.**

---

## 3. Lo que sí se puede hacer en E2.3, y lo propongo

No es "no hacer nada". Hay dos cosas honestas y con valor:

**3.1 · Las incertidumbres SÍ se pueden emitir hoy.** `UncertaintyV0` admite
`evidence_refs=()` precisamente porque una incertidumbre suele existir **porque faltan
datos**. Las razones que hoy salen con estado `INSUFICIENTE` o `sin_dato` pueden
convertirse en `DecisionContextV0.uncertainties` **sin fabricar nada**: son el caso donde
la ausencia de evidencia es el contenido, no un obstáculo.

Con su `impact` del vocabulario del Blueprint — y ahí sí hay un juicio que tomar, porque
`impact` es obligatorio.

**3.2 · `eligibility.violations` es representable.** Los `duros_incumplidos` que ya calcula
el motor son una violación de criterio real… pero `ViolationV0` exige `evidence_refs` **no
vacía** (congelado en E1.5). Con la §1.1 en `YES_BUT_LATER`, **tampoco se puede emitir
hoy**.

Así que queda **solo 3.1**: emitir incertidumbres, que es la parte que no necesita
procedencia.

---

## 4. Recomendación

**Redefinir E2.3 a lo que el alcance de F2 permite hacer con verdad:**

1. **Emitir `uncertainties`** desde las razones sin evidencia (`INSUFICIENTE`, `sin_dato`),
   con su `impact`. Cero procedencia fabricada.
2. **No emitir** `strengths`, `tradeoffs`, `match.dimensions` ni `eligibility.violations`:
   los cuatro exigen `evidence_refs` no vacía y hoy no hay dónde resolverla.
3. **Registrar la tabla como deuda con fase asignada:** seis dimensiones esperan F4/F5.
4. **Dejar `evidence_refs` vacío en toda la decisión**, y que eso sea el resultado
   *correcto* de E2.3 — no un pendiente.

La alternativa —mover E2.3 entera después de F4/F5— también es defendible. **No la tomo
yo.**

Lo que no haría en ningún caso es emitir un `StrengthV0` con un `evidence_id` que no
resuelve, para que la fase "cierre". Sería la cuarta de la misma familia que
`place_id`, `score_version` y `decision_id`: un objeto que valida, y es falso.
