# F3.0a — Caracterización de la frontera de extracción

**Unidad de EVIDENCIA, no de implementación.** Cero cambios funcionales de aplicación.

| | |
|---|---|
| **Baseline** | `f6dbd7518875347c099d8393eb5ee21ec43fe5b9` (`origin/main`) |
| **Rama** | `feat/f3-buyer-extraction-characterization` |
| **Worktree** | efímero desde `origin/main` — el checkout local divergido **no se usó ni se saneó** |
| **Suite** | **1 441 `exit 0`** (1 409 + 32 nuevos) |
| **Cambios en `app/`** | **0** (`git diff --stat -- app/` vacío) |

Etiquetas: **[VERIFICADO]** comprobado con herramienta · **[OBSERVADO]** visto en producción
· **[INFERIDO]** deducido de código sin ejecutar · **[DESCONOCIDO]** no determinado.

---

## 1. CURRENT PIPELINE

```
POST /api/v1/chat/  ──> HumanMessage(content=texto)          chat.py:447 / :562
                          · sin id explícito
                          ↓
                     add_messages (LangGraph)                 ← asigna UUID4
                          ↓
                     checkpointer  AsyncPostgresSaver          graph.py:14-15, :811
                     (MemorySaver al importar; se recompila en el lifespan)
                          ↓
                     encaje_node(state, config)                graph.py:~749
                       turno = nº de HumanMessage
                       si preferencias_turno != turno:
                          ↓
                     _user_texts(messages)                     assembler.py:186-189
                       └─ devuelve  [m.content …]  ← ⛔ AQUÍ SE PIERDE LA IDENTIDAD
                          ↓
                     extraer_preferencias(list[str])           preferencias.py:145
                       textos[-12:]                            preferencias.py:156
                       "\n".join(f"- {t}")  → UN solo mensaje  preferencias.py:164
                          ↓
                     tool registrar_preferencias (schema cerrado)
                          ↓
                     _sanitizar(block.input) → dict plano      preferencias.py:168
                          ↓
                     AgentState.preferencias: dict | None      state.py
                          ↓
                     Decision Core (encaje, ranking, corte)
```

---

## 2. Respuestas a las nueve preguntas

### Q1 · ¿Qué unidad entra a `extraer_preferencias`?

**[VERIFICADO] Una `list[str]`. Nada más.**

```python
def _user_texts(messages) -> list[str]:
    return [m.content for m in messages
            if isinstance(m, HumanMessage) and isinstance(m.content, str) and m.content.strip()]
```

| Metadato | ¿Llega? |
|---|---|
| texto | ✅ |
| `HumanMessage` (objeto) | ❌ |
| `id` | ❌ |
| timestamp | ❌ |
| thread / session | ❌ |
| orden explícito | ❌ (solo posición en la lista) |

**[VERIFICADO]** La firma no admite identidad: `extraer_preferencias(mensajes_usuario: list[str])`.
No es que se pierda dentro — **no cabe en el parámetro**.

### Q2 · ¿Existe hoy un `message_id` estable utilizable como `EvidenceRef.source_id`?

**[VERIFICADO] SÍ, y es el hallazgo más accionable de esta unidad.**

Probado en runtime contra las versiones fijadas (`langchain_core 0.3.63`):

```
1) HumanMessage(content="hola").id            →  None     ← así lo construye chat.py
2) tras ainvoke, en el estado                 →  'db8d3571-d484-4e33-ad51-08afbace028b'
3) tras un SEGUNDO turno, el id del primero   →  idéntico
4) round-trip por JsonPlusSerializer          →  idéntico
```

`add_messages` asigna un **UUID4** al ingerir, el id **sobrevive entre turnos** y **sobrevive
a la serialización del checkpointer** (`JsonPlusSerializer`, el mismo que usa
`AsyncPostgresSaver`).

**Conclusión:** la identidad de mensaje **ya existe, es estable y está persistida**. El
problema no es crearla — es que `_user_texts` la descarta tres capas antes del extractor.

### Q3 · ¿En qué línea exacta se pierde la procedencia?

**[VERIFICADO] `app/decision/assembler.py:188`** — `[m.content for m in messages …]`.

Es el único punto donde un objeto con identidad se convierte en texto anónimo. Todo lo que
viene después (schema del tool, `_sanitizar`, el dict, `AgentState`) ya opera sobre datos
sin procedencia; ninguna costura posterior puede recuperarla.

**Pérdida secundaria [VERIFICADO]:** `preferencias.py:164` concatena los mensajes en **un
solo turno de usuario** (`"Mensajes del usuario:\n- uno\n- dos\n- tres"`). Aunque el extractor
recibiera identidad, el modelo no vería mensajes separados a los que atribuir. Son **dos**
pérdidas independientes, y arreglar solo la primera no bastaría.

### Q4 · ¿Reconstruye desde transcript o actualiza estado previo?

**[VERIFICADO] Reconstruye.** El extractor no recibe el estado anterior; su petición solo
lleva `model`, `system`, `tools`, `tool_choice`, `messages`. `encaje_node` cachea por turno
(`preferencias_turno == nº de HumanMessage`) pero, al cambiar el turno, **re-deriva todo
desde cero**. No hay acumulación ni corrección: hay recálculo.

### Q5 · ¿Qué pasa con una preferencia válida que sale de los últimos 12 mensajes?

**[VERIFICADO] Desaparece, y de forma definitiva.**

Con 13 mensajes humanos, el primero no llega al modelo: `textos[-12:]` recorta sobre los
textos **ya filtrados** (los vacíos no ocupan lugar). Y como el extractor reconstruye desde
transcript, **no queda ningún rastro** de que esa necesidad se declaró.

Es la pérdida más silenciosa del pipeline: la necesidad sigue siendo verdad para la persona
y el sistema deja de verla por una constante de recorte de tokens.

### Q6 · ¿Y si la extracción falla tras haber tenido preferencias válidas?

**[VERIFICADO] Devuelve `{}` y ese `{}` reemplaza lo anterior.**

```python
except Exception as e:
    logger.warning("extraer_preferencias degradó a {} …")
return {}
```

`{}` **no significa "no sé"**: significa *ausencia de necesidades declaradas*, indistinguible
de "la persona no ha pedido nada". `encaje_node` escribe ese `{}` en el estado junto con
`preferencias_turno = turno`, así que **dentro de ese turno no se reintenta**.

**El fallo es transitorio** —el turno siguiente relee el transcript y recupera— **salvo que
la declaración además haya salido de la ventana de 12**. Ahí Q5 y Q6 se componen y la pérdida
es permanente.

### Q7 · ¿Qué distinciones semánticas NO puede representar el dict?

**[VERIFICADO]** El dict es `{dimensión: escalar}`. Las ocho distinciones no están vacías:
**no existen**.

| Distinción | Hoy | ¿Ya en F1? |
|---|---|---|
| `stated` vs `inferred` | ❌ | ✅ `CriterionOrigin` |
| hard vs soft | ❌ | ✅ `hard_constraints` / `soft_preferences` |
| persistent vs situational | ❌ | ❌ **tampoco en F1** |
| tradeoff | ❌ | ✅ `Tradeoff` |
| unresolved | ❌ | ✅ `UnresolvedQuestion` |
| operador (EQ/LTE/GTE…) | ❌ | ✅ `Operator` |
| evidencia por campo | ❌ | ✅ `DecisionCriterionV0.evidence` |
| corrección / retracción | ❌ | ✅ `CriterionStatus` |

**Nota:** *persistent vs situational* es la única que **tampoco** tiene hogar en
`BuyerContextV0`. Ver §7.

Además **[VERIFICADO]**: `caminable: False` se descarta en `_sanitizar` (solo se registra la
necesidad afirmada). "No me importa caminar" y "no lo mencionó" colapsan en el mismo estado.

### Q8 · ¿Qué protección Fair Housing hay que preservar exactamente?

**[VERIFICADO] Tres barreras en capas, las tres con test de caracterización:**

1. **Schema del tool cerrado** — `properties` == `DIMENSIONES ∪ {operacion}`. El LLM no puede
   emitir un campo de persona porque no existe.
2. **Prohibición en el prompt** — *"NUNCA infieras una preferencia a partir de QUIÉN es la
   persona"*, nombrando hijos, edad, nacionalidad, origen, religión, género, discapacidad.
3. **`_sanitizar`** — whitelist cerrada + enums cerrados (`operacion`, `tipo_inmueble`).
   Aunque el LLM alucine, nada ajeno llega al motor.

**Invariante para F3: cualquier costura nueva debe pasar por la barrera 3, o replicarla.**
Un canal paralelo que lleve "observaciones" sin sanitizar sería una cuarta vía que rodea la
única capa que no depende de que el modelo obedezca.

### Q9 · ¿Qué parte del checkpointer es transcript y qué parte podría ser Buyer state?

**[VERIFICADO] Todo lo que hay es transcript de conversación. No hay Buyer store.**

`AsyncPostgresSaver` persiste `AgentState` por `thread_id` (= `session_id`). Contiene
`messages`, `spatial_context`, `sql_results`, `preferencias`, `preferencias_turno`, `cards`,
`descartadas`, `encaje_contexto`.

`preferencias` **parece** Buyer state y no lo es:

- es **caché de turno**, no historial — su llave es el conteo de mensajes;
- **se reemplaza entera** cada turno, no se actualiza;
- **no versiona**, no registra correcciones ni retracciones;
- muere con la sesión: `thread_id` es la conversación, no la persona.

**No equiparar persistencia de conversación con Buyer store.** Que el dict sobreviva al
reinicio no lo convierte en estado del comprador: lo convierte en un caché durable de una
derivación que se recalcula igualmente.

---

## 3. LOSS POINTS

| # | Punto | Qué se pierde | Evidencia |
|---|---|---|---|
| **L1** | `assembler.py:188` | identidad del mensaje (`id`), timestamp, sesión | [VERIFICADO] |
| **L2** | `preferencias.py:164` | separación entre mensajes — van concatenados en uno | [VERIFICADO] |
| **L3** | `preferencias.py:156` | todo lo declarado antes de los últimos 12 textos | [VERIFICADO] |
| **L4** | `preferencias.py:168` | operador, dureza, origen, vigencia, evidencia, corrección | [VERIFICADO] |
| **L5** | `_sanitizar` (bools) | la diferencia entre "no lo quiero" y "no lo dijo" | [VERIFICADO] |
| **L6** | `preferencias.py:169-171` | el estado anterior, sustituido por `{}` ante fallo | [VERIFICADO] |

**L1 es la raíz**; L2 la duplica aguas abajo. Cualquier costura de F3.0b tiene que resolver
**las dos**, o la procedencia seguirá sin poder atribuirse a un mensaje concreto.

---

## 4. FAIR HOUSING INVARIANTS

Congelados, con test:

```
FH-1  properties(tool) == DIMENSIONES ∪ {operacion}
FH-2  el prompt prohíbe inferir desde rasgos de la persona
FH-3  _sanitizar descarta toda clave fuera de la whitelist
FH-4  operacion y tipo_inmueble son enums cerrados
```

**Ninguno se modifica en esta unidad.**

---

## 5. REAL SMOKE CASES

### CASO A — *"Ahora muéstrame solo lo que esté bajo $450"* [OBSERVADO 2026-08-25 20:09]

- **Qué llega al extractor:** el texto suelto, sin marca de que "solo" expresa dureza.
- **Qué puede emitir hoy:** `{"presupuesto_max": 450.0}` — **[VERIFICADO]** idéntico al que
  produce *"hasta $450, pero puedo estirarme"*. El schema no tiene dónde poner la dureza.
- **Dónde se pierde el HARD:** L4. `presupuesto_max` es un `number`; no hay `operator` ni
  `hard/soft`.
- **[VERIFICADO] El $470 sigue visible:**

```
límite = 450 × 1,10 = 495
$380 visible · $470 visible · $495 visible · $496 cortado · $550 cortado · $710 cortado
```

Ante *"solo bajo $450"*, un inmueble de **$470 permanece en pantalla**. El sistema resuelve a
favor del presupuesto flexible **en silencio, por una constante**, sin que nadie haya
declarado esa interpretación. **No se corrige aquí.**

### CASO B — *"¿Cuál de estos es el más caminable?"* [OBSERVADO 2026-08-25 20:12]

- **Por qué cabe `caminable: True`:** es una dimensión del schema y la frase la menciona.
- **[VERIFICADO] No existe eje situacional:** ni en `DIMENSIONES` ni en el tool schema hay
  vigencia, alcance ni "objetivo del turno".
- **No se afirma** que la persona declarara una preferencia persistente. Lo que se afirma es
  que **el esquema no puede distinguir las dos cosas**: sea cual sea la verdad, la representa
  igual. En producción esa dimensión **cambió el ranking**.

### CASO C — *"Necesito al menos 3 dormitorios"*

- **[VERIFICADO] El extractor registra 3.** El prompt (regla 3b) ordena registrar el número
  nombrado y no expandirlo a mínimo. **Eso es normalización fiel del número.**
- **[VERIFICADO] La pérdida está en el OPERADOR**, y es medible:

```
pidió "al menos 3"  →  {dormitorios: 3}
  inmueble con 3 →  s=1.0  "Tiene los 3 dormitorios que pediste"
  inmueble con 4 →  s=0.6  "Tiene 4 dormitorios, pediste 3"    ← penalizado
  inmueble con 5 →  s=0.6
```

Un inmueble de 4 satisface *"al menos 3"* por completo y el motor lo puntúa **0,6**, con una
razón que presenta tener de más como defecto. **No es un error de `encaje.py`**: hace
exactamente lo que `{dormitorios: 3}` le permite expresar.

- **[VERIFICADO] `BuyerContextV0` ya sabe representarlo:**

```python
DecisionCriterionV0(dimension="bedrooms", operator=Operator.GTE, value=3,
                    origin=CriterionOrigin.STATED)
```

**No hace falta contrato nuevo. Hace falta una costura que lo alimente.**

### CASO D — ventana de 12 [VERIFICADO]

Con 13 mensajes humanos, el modelo recibe los **12 últimos**; el primero no aparece. El
recorte va sobre textos ya filtrados: los vacíos no consumen cupo.

### CASO E — fallo de extracción [VERIFICADO]

Timeout en un turno nuevo → `{}`, sin reintento. Recupera al turno siguiente **si** la
declaración sigue dentro de la ventana.

---

## 6. MESSAGE IDENTITY FINDING

> **La identidad de mensaje que F3 necesita ya existe, es estable y está persistida.**
> Se descarta en `assembler.py:188`, tres capas antes de que el extractor pueda usarla.

`HumanMessage.id` — UUID4 asignado por `add_messages`, estable entre turnos, conservado por
`JsonPlusSerializer`. **[VERIFICADO]** en los cuatro puntos.

**Caveats honestos:**

- **[VERIFICADO]** con `MemorySaver` en proceso y con round-trip del serializador.
  **[INFERIDO]** para `AsyncPostgresSaver` end-to-end: usa el mismo serde, pero no se probó
  contra una base real (habría exigido red/DB, fuera de alcance).
- **[DESCONOCIDO]** si el id es estable ante compactación de historial o migración de
  checkpointer. Nadie lo hace hoy; conviene no asumirlo.
- El id es **de mensaje, no de afirmación**. Un mensaje puede declarar varias necesidades
  ("departamento de 2 dormitorios bajo $700"), así que `source_id` a nivel de mensaje da
  granularidad de mensaje, no de campo — suficiente para `EvidenceRefV0`, insuficiente para
  señalar la frase exacta.

---

## 7. CHECKPOINTER ≠ BUYER STORE

| | Checkpointer hoy | Lo que F3 necesita |
|---|---|---|
| Llave | `thread_id` = conversación | comprador |
| Contenido | transcript + caché derivado | criterios con procedencia |
| Actualización | reemplazo por turno | corrección versionada |
| Historial | de mensajes | de criterios |
| Retracción | ✗ | ✅ `CriterionStatus.RETRACTED` |
| Vida | la sesión | más que la sesión |

`AgentState.preferencias` es **caché de derivación**, no estado del comprador. Confundirlos
llevaría a "ya tenemos persistencia" cuando lo que hay es una conversación guardada.

**Además [VERIFICADO]:** *persistent vs situational* (Caso B) **no tiene hogar ni en
`BuyerContextV0`**. Las otras siete distinciones de Q7 sí. Es una pregunta abierta de diseño
de F3, no un hueco de la costura de extracción.

---

## 8. CURRENT → TARGET MATRIX

Lo deseado va aquí, **no como tests rojos**. Todos los tests de esta unidad son verdes y
describen el presente.

| # | CURRENT | TARGET | Bloqueado por |
|---|---|---|---|
| 1 | `_user_texts` → `list[str]` | unidad con `id` + texto | L1 |
| 2 | mensajes concatenados en uno | mensajes separados y atribuibles | L2 |
| 3 | `{presupuesto_max: 450}` | `operator=LTE` + `hard/soft` explícito | L4 |
| 4 | *"al menos 3"* → `EQ 3` | `operator=GTE, value=3` | L4 |
| 5 | pregunta comparativa = preferencia | situational vs persistent | L4 + **hueco en F1** |
| 6 | `{}` ante fallo | "no se pudo determinar" ≠ "no pidió nada" | L6 |
| 7 | ventana de 12 sin rastro | criterio vigente sobrevive a la ventana | L3 |
| 8 | `caminable: False` descartado | negación explícita ≠ ausencia | L5 |
| 9 | sin evidencia | `EvidenceRefV0(source_type=USER_DECLARED, source_id=<message id>)` | L1 + L2 |

**Regla ya congelada en revisión (no reabrir):** evidencia `USER_DECLARED` **no autoriza**
`origin=stated`. `source_type` describe la evidencia; `origin`, cuánto interpretó el sistema;
`methodology` documenta la transformación.

---

## 9. OPEN QUESTIONS

1. **¿Dónde vive *situational vs persistent*?** Única distinción sin hogar en F1. ¿Campo
   nuevo, convención sobre `CriterionStatus`, o decisión de la costura de no persistir?
2. **¿`source_id` a nivel de mensaje basta?** Da granularidad de mensaje, no de frase. ¿Es
   suficiente para `EvidenceRefV0` en F3, o hay que esperar a `TRUST-ID-01`?
3. **¿Qué es "el comprador" sin login?** `thread_id` es la conversación. Un Buyer store
   necesita una llave que hoy no existe para usuarios anónimos.
4. **¿Cómo se retracta?** Si dice "$450" y luego "mejor $600", ¿corrección del mismo criterio
   o dos criterios con `RETRACTED`? Afecta al modelo de identidad.
5. **¿La ventana de 12 se toca?** Subirla cuesta tokens; eliminarla exige estado acumulado.
   Es decisión de producto, no solo técnica.
6. **[DESCONOCIDO]** estabilidad del `message id` ante compactación de historial.

---

## 10. RECOMMENDED F3.0 SEAM

> **La costura mínima que preserva evidencia ANTES de que `_sanitizar` devuelva el dict.**
> Se proponen alternativas. **No se implementa ninguna.**

El criterio de mínimo: **resolver L1 y L2 sin tocar contratos, sin store, sin DB y sin
cambiar la salida actual.** Las tres opciones mantienen `extraer_preferencias` devolviendo el
mismo dict; cambian **qué más** queda disponible.

### Opción 1 — enriquecer la entrada, devolver la salida en paralelo

`_user_texts` devuelve `(id, texto)`; el extractor numera los mensajes en el prompt y el tool
gana un campo de atribución. Devuelve `(dict, atribuciones)`.

- ✅ Resuelve L1 y L2. Reutiliza la barrera FH-3 sobre el mismo dict.
- ⚠️ Toca el tool schema — **hay que demostrar que no debilita FH-1**.
- ⚠️ Depende de que el modelo atribuya bien: es una afirmación suya, no un hecho.

### Opción 2 — un mensaje, una extracción

Llamar al extractor por mensaje y componer. La atribución es **estructural**, no declarada
por el modelo.

- ✅ Procedencia **sin depender de que el modelo obedezca** — la lección de TRUST-HOTFIX-01.
- ⚠️ N llamadas por turno: coste y latencia en el camino caliente.
- ⚠️ Pierde contexto entre mensajes ("y que acepte mascotas" referido al anterior).

### Opción 3 — costura de solo lectura, sin tocar el extractor

Registrar en paralelo qué mensajes se enviaron y con qué ids, sin cambiar el prompt ni el
schema. No atribuye campo→mensaje; **acota el conjunto** de mensajes que pudieron originarlo.

- ✅ La más pequeña. Cero riesgo Fair Housing, cero cambio de comportamiento.
- ✅ Da `source_id` **múltiple** honesto: "salió de alguno de estos 12".
- ⚠️ No resuelve L2: no distingue cuál de los 12.

### Lectura

**La 3 es la única que no arriesga nada y ya mejora el estado actual** (hoy no se sabe ni
qué mensajes se enviaron). La **2 es la única que produce procedencia estructural**, y esa
propiedad es exactamente la que TRUST-HOTFIX-01 demostró que importa: *no depender de que el
modelo diga la verdad sobre sí mismo*.

**No se elige aquí.** La decisión necesita el coste real de la opción 2, que esta unidad no
midió.

---

## 11. Gate de cierre

| # | Criterio | Estado |
|---|---|---|
| 1 | Baseline confirmado sobre `f6dbd75` | ✅ |
| 2 | Comportamiento actual reproducido sin red | ✅ 32 tests, cliente doblado |
| 3 | Los dos casos reales del smoke caracterizados | ✅ A y B |
| 4 | *"al menos 3 dormitorios"* caracterizado | ✅ con la pérdida medida |
| 5 | Ventana de 12 demostrada | ✅ |
| 6 | Failure semantics demostradas | ✅ incl. composición con Q5 |
| 7 | Punto exacto de pérdida identificado | ✅ `assembler.py:188` (+ L2) |
| 8 | Message identity demostrada | ✅ existe, estable, persistida |
| 9 | Fair Housing sin cambios | ✅ 3 barreras con test |
| 10 | Cero cambios funcionales de app | ✅ `git diff app/` vacío |
| 11 | Suite completa verde | ✅ **1 441 `exit 0`** |
| 12 | Reporte suficiente para decidir F3.0b | ✅ §8, §9, §10 |

**F3.0a — PASS.**

---

## 12. Hechos que contradicen o matizan el prompt de la unidad

Se listan porque el encargo lo pide explícitamente.

1. **`app/intencion.py` no contiene `registrar_intencion`.** El módulo expone `_norm` y
   `analizar_intencion`. **[VERIFICADO]** `registrar_intencion` está **definida dentro del
   router**, en `app/routers/chat.py:1121`. No afecta a las conclusiones —no está en la ruta
   de extracción de preferencias— pero conviene anotarlo por dos razones: la lectura
   obligatoria no fue la esperada, y es lógica de persistencia viviendo en la capa de
   transporte, la misma familia de `ARCH-DEBT-F2-01`. **No se toca en esta unidad.**

2. **La pregunta 2 asumía que había que demostrar la *ausencia* de identidad.** El resultado
   fue el contrario: **existe**. Eso cambia la naturaleza de F3.0b — no hay que inventar
   identidad, hay que dejar de tirarla.

3. **El encargo pedía identificar "la línea exacta" (singular) donde se pierde la
   procedencia. Son dos**, independientes: `assembler.py:188` (identidad) y
   `preferencias.py:164` (separación entre mensajes). Arreglar solo la primera no permitiría
   atribuir campo→mensaje.

4. **`persistent vs situational` no tiene hogar en `BuyerContextV0`.** El encargo la listaba
   junto a las otras siete distinciones de Q7 como si todas fueran representables una vez
   superada la frontera de extracción. Las otras siete sí; esta no.
