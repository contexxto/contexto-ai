# F3.0b — Buyer Evidence Input Seam

| | |
|---|---|
| **Baseline** | `6f8477e1609e52306280a4450541b1b02a5c140e` (`origin/main`, F3.0a mergeada) |
| **Rama** | `feat/f3-buyer-evidence-input-seam` |
| **Suite** | **1 467 `exit 0`** (1 441 + 26) |
| **Archivos** | `app/buyer/{__init__,mensaje}.py` (nuevos) · `tests/test_buyer_evidence_input_seam.py` |
| **Cambios a `app/` existente** | **0** |

---

## CURRENT

```
messages  →  _user_texts()  →  [str, str, …]  →  extraer_preferencias()  →  dict  →  encaje
                   ↑
              L1: se pierde el id (assembler.py:188)
```

El carril legacy **sigue siendo la autoridad productiva**. No se tocó.

## TARGET

```
LEGACY  (autoridad productiva, sin cambios)
   messages → _user_texts → extraer_preferencias(list[str]) → dict → encaje actual

F3      (construido en esta unidad, NO autoritativo)
   messages → ultimo_mensaje_usuario_identificado() → IdentifiedUserMessage(message_id, text) → [STOP]
                                                                              ↑
                                                            aquí entra E3.2 (updater)
```

**L2 no se arregla: se elimina por diseño.** El carril nuevo procesa **el mensaje nuevo como
unidad separada**, así que no existe el blob concatenado. `extraer_preferencias` puede seguir
uniendo los últimos 12 mientras F3.0b no sea autoritativa — esta unidad **no refactoriza el
extractor antiguo** para intentar hacerlo atribuible.

---

## IDENTITY SEMANTICS

> **El `message_id` se toma, no se fabrica.**

| Regla | Cómo se garantiza |
|---|---|
| Sale del `HumanMessage.id` del estado | `ultimo_mensaje_usuario_identificado` lo lee; no lo construye |
| No lo propone un LLM | ningún modelo participa en esta costura |
| No se deriva del texto | test: dos turnos con el mismo texto → ids distintos |
| No lo genera F3 | test por AST: el módulo **no importa** `uuid`, `random`, `secrets`, `hashlib`, `time`, `datetime`, ni llama a `hash()` |

**Por qué un hash del texto no sirve** — dos turnos idénticos (`"sí"`, `"y qué más?"`)
colapsarían en el mismo id, y una corrección posterior sería indistinguible de la declaración
original. La identidad tiene que ser del *evento*, no del *contenido*.

### Selección — determinista, y lo que **no** promete

El **último** `HumanMessage` con contenido no vacío. Selección por posición, sin heurística.

El filtro de vacíos es **el mismo** que usa el legacy `_user_texts`, para que los dos carriles
no discrepen sobre qué cuenta como mensaje del usuario.

> **Distinción congelada:**
> ```
> identificado ≠ nuevo
> último       ≠ sin procesar
> ```

La función devuelve el último mensaje del transcript. **No sabe si ya fue procesado**, y no
puede saberlo: la novedad no es propiedad del transcript, es propiedad del **estado
persistido**. Un retry, un replay, una reanudación del grafo o una ejecución duplicada
devolverían el mismo `message_id` — y eso es correcto, es el mismo mensaje.

Por eso se llama `ultimo_mensaje_usuario_identificado` y no `mensaje_nuevo_de`: el nombre
anterior prometía una garantía que la implementación no da. Hoy no era un bug porque el carril
está desconectado; cuando E3.2 lo conecte, sí lo sería. Hay dos tests que lo fijan — uno
comprueba que dos llamadas sobre el mismo estado devuelven el mismo id, y otro que ninguna
función pública del módulo contenga "nuevo" en su nombre.

### Invariante que esto impone a E3.1

**La idempotencia se resuelve en el store, no en la selección.**

```
mismo buyer_id  +  mismo source_message_id  +  mismo cambio propuesto
        →  NO dos revisiones independientes del BuyerContext
```

Una misma declaración fuente no puede producir dos mutaciones del `BuyerContext` solo porque
el runtime la reprocese. Estaba implícito en el gate original de F3 (*"same transcript, no
uncontrolled churn"*); esta unidad lo vuelve **estructural**: al no prometer novedad aguas
arriba, obliga a que la garantía viva donde puede cumplirse.

### Verificado en runtime

```
HumanMessage(content=…)          id = None      ← así lo construye chat.py
tras ainvoke                     id = UUID4     ← lo asigna add_messages
segundo turno                    id nuevo; el del primero intacto
ultimo_mensaje_usuario_identificado(estado)         devuelve ESE id, no uno propio
```

---

## FAIL-CLOSED RULE

```
sin mensajes del usuario          →  None                    (no es fallo)
mensaje sin `id`                  →  MensajeSinIdentidad     (fail-closed)
```

**`None` ≠ excepción, a propósito.** "No hay nada que procesar" y "no puedo proceder con
honestidad" son cosas distintas: la misma distinción ausente-≠-vacío que gobierna los
contratos de F1.

**El fail-closed es solo del carril nuevo.** El legacy sigue funcionando y el producto no se
rompe. Se levanta en vez de rellenar porque un id inventado produciría una `EvidenceRefV0`
que valida y miente sobre su propio origen — la misma familia que `place_id` inventado,
`score_version` normalizado y `decision_id` colisionado, que F2 se pasó cerrando.

En condiciones normales no debería ocurrir: `add_messages` asigna el id al ingerir. Que
ocurra significa que el mensaje llegó por un camino que no pasó por el grafo, y eso conviene
que duela.

---

## FAIR HOUSING BOUNDARY

**La costura transporta texto libre. No lo convierte en nada.**

```
IdentifiedUserMessage.text  =  el mensaje literal, SIN sanitizar
```

Eso es deliberado y es también el riesgo: si alguien derivara criterios desde este texto sin
atravesar la barrera determinista, habría creado **una cuarta vía que rodea la única capa que
no depende de que el modelo obedezca**.

### Dónde debe ocurrir la barrera

```
IdentifiedUserMessage.text          ← texto libre, sin filtrar
        ↓
   [ E3.2 · updater ]
        ↓
   ⛔ BARRERA DETERMINISTA OBLIGATORIA AQUÍ
      · whitelist cerrada de dimensiones (equivalente a `_sanitizar`)
      · descarte de todo atributo protegido
        ↓
   criterios del Buyer
```

**Invariante congelado:** ningún criterio del Buyer puede derivarse de `text` sin pasar por
una barrera con la misma garantía que `_sanitizar` — whitelist cerrada, enums cerrados,
descarte de lo ajeno. Que la barrera sea la misma función o una equivalente es decisión de
E3.2; que exista, no.

### Qué garantiza esta unidad hoy

| Garantía | Test |
|---|---|
| `IdentifiedUserMessage` no tiene campos de preferencia | `model_fields == {message_id, text}` |
| No hay intersección con `DIMENSIONES` | verificado |
| El objeto es `frozen` + `extra="forbid"` | nadie le añade `familia` en runtime |
| `_sanitizar` intacta | FH-3 sigue siendo la única puerta |
| Ningún módulo de producción importa `app.buyer` | test por AST |

**No se persiste ningún atributo protegido como campo derivado. No se crea representación de
household ni de familia.**

---

## SITUATIONAL ROUTING POLICY

**`BuyerContextV0` NO se modifica.** Política congelada conceptualmente:

```
criterio durable            →  candidato a BuyerContext
petición/objetivo del turno →  NO BuyerContext
ambiguo                     →  no persistir / unresolved
```

### El caso obligatorio

> *"¿Cuál de estos es el más caminable?"*

**F3.0a demostró** que esa frase produce `caminable: True` en el dict legacy, y que esa
dimensión **cambió el ranking en producción**. Lo que F3.0b añade: la costura **no clasifica**.

Entrega `message_id` + `text` y nada más. Que `IdentifiedUserMessage` no tenga ningún campo
de preferencia es lo que hace **estructuralmente imposible** que la clasificación ocurra aquí
por accidente.

**Una mención de una dimensión no equivale a estado durable del comprador.** El clasificador
semántico lo hará el updater (E3.2). **No se implementa en esta unidad.**

---

## EVIDENCEREF MAPPING

Cuando E3.2 construya evidencia de una declaración del usuario:

```python
EvidenceRefV0(
    source_type = SourceType.USER_DECLARED,
    source_id   = identificado.message_id,   # ← el HumanMessage.id, sin transformar
    …
)
```

**No se construye aquí, y la razón es concreta:** `EvidenceRefV0` exige `retrieved_at`,
`methodology` y una `PersistencePolicy`. Ninguna de las tres está congelada para el Buyer, y
decidirlas ahora sería decidir por E3.2 sin evidencia. La costura deja el `source_id`
**disponible**; construir la referencia es de la fase que sepa responder las otras tres.

**Regla ya congelada en revisión, que sigue vigente:** evidencia `USER_DECLARED` **no
autoriza** `origin=stated`. `source_type` describe la evidencia; `origin`, cuánto interpretó
el sistema; `methodology` documenta la transformación. Un `message_id` correcto no convierte
una inferencia en una declaración.

**Granularidad honesta:** el id es **de mensaje, no de afirmación**. Un mensaje puede declarar
varias necesidades (*"departamento de 2 dormitorios bajo $700"*), así que `source_id` da
granularidad de mensaje, no de frase. Es suficiente para `EvidenceRefV0`; insuficiente para
señalar la frase exacta — eso es territorio de `TRUST-ID-01`.

---

## WHAT E3.1 CAN NOW BUILD

Con la costura en su sitio, E3.1 puede empezar sabiendo:

1. **Cada criterio podrá citar el mensaje que lo originó**, con un id real y estable.
2. **El store debe ser idempotente por evidencia de origen** — ver §IDENTITY SEMANTICS.
   `(buyer_id, source_message_id)` no puede producir dos revisiones.
3. **El store no necesita releer 12 mensajes.** El camino es incremental:
   `BuyerContext actual + IdentifiedUserMessage → updater → nueva revisión`.
4. **La barrera Fair Housing va entre la costura y el store**, no dentro del store.

### ⛔ Bloqueador real antes de construir tablas

**`thread_id` no puede ser `buyer_id`.** F3.0a demostró que identifica *conversación*, no
*persona*. Un store cuya clave primaria sea una incógnita es arquitectura falsa.

Antes de E3.1b (Buyer Store) hace falta caracterizar qué identidad existe **hoy** para:

```
usuario autenticado        →  ¿hay un user_id estable? probablemente sea la raíz correcta
usuario anónimo            →  ¿qué hay, si algo?
múltiples conversaciones   →  ¿se relacionan entre sí?
relogin / sesión nueva     →  ¿se reconecta con lo anterior?
```

Para anónimos, **no inventar una identidad cross-session** sin revisar cómo funcionan de
verdad el frontend y el auth. Eso sugiere partir la fase:

```
F3.0b  →  merge  →  E3.1a Buyer Identity Characterization  →  E3.1b Buyer Store
```

No es una fase artificial: la clave primaria del store no se puede diseñar mientras *"buyer"*
siga siendo una incógnita.

## WHAT E3.2 MUST DO

```
current BuyerContextV0  +  IdentifiedUserMessage  →  proposed update
```

**La interfaz no se declara en código en esta unidad**, y es una decisión consciente: hacerlo
exigiría nombrar el tipo del *proposed update*, que no está congelado — y nombrarlo aquí sería
inventar el `PreferenceObservationV0` que el encargo prohíbe. Queda como firma documentada.

E3.2 debe, como mínimo:

- **atravesar la barrera determinista** antes de derivar cualquier criterio (§FAIR HOUSING);
- **clasificar** durable / turn-only / ambiguo, con el caso de caminabilidad como aceptación;
- **decidir `origin`** por campo — `stated` solo si el criterio conserva fielmente lo dicho;
- **poblar `methodology`** con la transformación aplicada (obligatorio en `EvidenceRefV0`);
- **no colapsar trade-offs** (*"puedo estirarme"* → `UnresolvedQuestion`, no `budget_max=750`);
- **decidir `PersistencePolicy`**, hoy sin congelar.

---

## DEFERRED QUESTIONS

1. **¿Qué es "el comprador" sin login?** `thread_id` es la conversación. Abierta desde F3.0a.
2. **¿`PersistencePolicy` para evidencia de usuario?** Bloquea construir `EvidenceRefV0`.
3. **¿Cómo se retracta?** *"$450"* → *"mejor $600"*: ¿corrección del mismo criterio o dos con
   `RETRACTED`? Afecta al modelo de identidad del criterio.
4. **¿Dónde vive *situational vs persistent*?** Única distinción sin hogar en F1. Esta unidad
   la evita no clasificando; E3.2 no podrá.
5. **¿La ventana de 12 se toca?** Irrelevante para el carril nuevo (incremental), pero el
   legacy sigue con ella mientras sea autoritativo.
6. **[DESCONOCIDO]** estabilidad del `message id` ante compactación de historial. Nadie
   compacta hoy; no asumirlo.
7. **¿Cuándo pasa el carril nuevo a ser autoritativo?** F3.0b lo deja desconectado a
   propósito. La transición es una decisión con su propio riesgo de paridad.

---

## Gate de cierre

| # | Criterio | Estado |
|---|---|---|
| 1 | El nuevo `HumanMessage` llega con su id real | ✅ probado end-to-end con el grafo |
| 2 | Selección determinista | ✅ último `HumanMessage` útil |
| 3 | No se fabrica identidad | ✅ funcional + AST |
| 4 | `EvidenceRef.source_id ← message_id` posible | ✅ documentado, no construido |
| 5 | Fair Housing sin bypass | ✅ barrera documentada + 5 garantías con test |
| 6 | *Situational* no obliga a cambiar `BuyerContextV0` | ✅ la costura no clasifica |
| 7 | Legacy ranking idéntico | ✅ nadie importa `app.buyer`; `_user_texts` intacto |
| 8 | Cero store / DB / migrations | ✅ |
| 9 | Cero cambios a contratos F1 | ✅ el módulo no importa `app.contracts` |
| 10 | Suite completa verde | ✅ **1 467 `exit 0`** |
| 11 | Reporte suficiente para empezar E3.1 | ✅ |

**F3.0b — PASS.**

---

## Notas de ejecución

1. **La costura queda desconectada a propósito.** El encargo permitía que fuera "no
   autoritativa"; se optó por **no cablearla en absoluto**. Cablearla aunque fuera de forma
   inerte habría añadido una llamada al camino caliente del chat cuyo único efecto sería
   poder fallar. El test de paridad verifica por AST que ningún módulo de producción la
   importe — y ese test se volverá rojo el día que E3.2 la conecte, que es justo cuando debe
   revisarse.

2. **No se declaró la interfaz de E3.2 en código.** Requeriría nombrar el tipo del *proposed
   update*, que no está congelado. Documentada como firma; no inventada.

3. **`app/buyer/` es paquete interno, no contratos.** Sin sufijo `V0`, fuera de
   `app/contracts/`, y con el docstring diciéndolo. La distinción importa: estas formas se
   pueden cambiar sin versionar.
