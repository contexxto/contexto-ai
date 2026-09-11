# 18 · E3.2 — ACTA CONSOLIDADA DE EVIDENCIA · BUYER UPDATER

```
ESTADO FINAL   E3.2 · BUYER UPDATER = CLOSED / PASS
MANDATOS       E3.2-CONSOLIDATED-EVIDENCE-ACT-R1   (reconstrucción de la evidencia)
               E3.2-CLOSE-ACT-COMMIT-R1            (adjudicación de cierre)
FECHA          2026-09-11
BASE           427565554aa572754545f3cbcfa51b94bf568d79   (origin/main)
RAMA           docs/e3-2-consolidated-evidence
CODIGO TOCADO  NINGUNO. Cero cambios en app/, tests/, migrations/, frontend/, .github/.
ORIGEN         E3.2-EVIDENCE-CLOSURE-AUDIT-R1 detectó cinco subunidades en main sin acta.
               Este documento las reconcilia; no reabre ninguna.
```

> **Lo que este cierre NO dice.** `E3.2 = CLOSED / PASS` cierra **la construcción y la
> evidencia** del Buyer Updater. **No** significa `BUYER_CONTEXT_PRODUCTIVE = YES` y **no**
> significa `Gate F3 = PASS`. Ambos siguen abiertos:
>
> ```
> BUYER_CONTEXT_PRODUCTIVE = NO
> GATE F3                  = HOLD / NOT PASSED
> ```

> **Numeración.** `18_` estaba libre: no existe en `origin/main`, no existe en ningún commit
> de ninguna rama (`git log --all --diff-filter=A -- 'docs/agentic_decision_system/18_*'`
> devuelve vacío) y no existía sin rastrear. Sin conflicto.

---

## 1 · Alcance

Cubre las subunidades de **E3.2 — Buyer updater** (`Execution Plan 1.0` §9) que quedaron en
`origin/main` **sin informe §20**, y reconcilia el estado final de toda la cadena.

**Corte documental exacto.** El informe `17` se reescribió por última vez en `7a875e2`
(= E3.2b.3). Su índice declara `ENTREGADO` hasta E3.2b.3, lista `PENDIENTE shadow wiring
(E3.2b.4)` y cierra con `GATE HOLD — la costura completa existe y está probada; nadie la
llama todavía`. **Todo commit posterior a `7a875e2` entró en main sin acta.**

**Qué NO cubre este documento:** E3.1 (informes `11` y `14`), E3.3–E3.6 (no iniciadas), las
tools mínimas de F3 (no iniciadas), Place y Voice.

### 1.1 · Corrección de un hallazgo de la auditoría previa

`E3.2-EVIDENCE-CLOSURE-AUDIT-R1` señaló que el informe `15`, línea 30, dice
`shadow wiring · §20   E3.2b.4 — NO AUTORIZADO`, y lo marcó como discrepancia de
autorización abierta.

**Queda resuelto, y en la dirección contraria a la que la ausencia de acta sugería.** El
adjudicador confirma que la secuencia ocurrió durante la ejecución: E3.2b.4 se autorizó,
**falló**, y ese fallo autorizó la unidad correctiva E3.2b.4a. La frase del informe `15` es
un **snapshot anterior a esa secuencia** y no representa el estado final.

La lección procedimental se conserva: **la ausencia de un acta versionada no prueba ausencia
de adjudicación**, y por eso este documento existe.

---

## 2 · Commits

Los commits de la cadena en `origin/main`, en orden (`git log --reverse --grep='E3\.2b'`):

```
662a269  2026-08-27  E3.2a · Buyer Store Preconditions
e65b8ab  2026-08-27  E3.2b.0 · Buyer State Boundary
1b84120  2026-08-27  docs(buyer): caracterizacion del extractor y routing (sin implementar)
67b3c6d  2026-08-27  feat(buyer): extractor determinista + routing (E3.2b.1, parcial)
714dc4c  2026-08-27  docs(buyer): congelar C1-C5 en el reporte 17 · 4 defectos de 1a
9f5e8f7  2026-08-28  feat(buyer): BuyerFieldV0 (1a-A parcial)
824b7e4  2026-08-28  docs(buyer): corregir una afirmacion falsa sobre StrEnum
0878f76  2026-08-28  E3.2b.1a-A · routing semántico estructural (§3-§7)
78d67e6  2026-08-28  E3.2b.1a-B · verificador de evidencia exacta + autorización de Clear
ffc39f0  2026-08-28  E3.2b.1a-B.1 · evidencia local, positiva y vinculada
5d7578e  2026-08-28  E3.2b.1a-B.2 · mascotas fail-closed
0e61110  2026-08-28  E3.2b.1a-B.3 · predicado de admisión de mascotas
1cd80a8  2026-08-28  E3.2b.1b · intérprete text → Afirmacion
4df379d  2026-08-28  E3.2b.1b.1 · integridad y estabilidad del eval semántico
da80bb9  2026-08-28  E3.2b.1b.2 · oracle semántico exacto
5d11a9f  2026-08-28  E3.2b.2 · buyer reducer V0 · el lote se vuelve memoria
7a875e2  2026-08-28  E3.2b.3 · orquestador del updater · procesar exactamente una vez
bc76024  2026-08-28  E3.2b.3a · CANDIDATO · concurrencia + Postgres real en CI
6211252  2026-08-28  E3.2b.4 · CANDIDATO · shadow wiring del Buyer Updater
7bb7942  2026-08-28  E3.2b.5 · CANDIDATO · allowlist fail-closed para la sombra
c42fb99  2026-08-28  E3.2b.3a · REOPEN EVIDENCE ONLY · la concurrencia deja de ser un volado
94ee869  2026-08-29  E3.2b.4a · la sombra también observa el turno stream
0baaa5f  2026-08-29  E3.2b.6 · G16 · la guarda acredita la moneda con el mercado del despliegue
```

**El orden no es lineal**, y eso es parte del acta: `3a` se reabrió **después** de que `4` y
`5` ya estuvieran en main.

---

## 3 · Cronología por subunidad

### E3.2b.1a\* — frontera y extractor

```
COMMIT(S)                 9f5e8f7 · 824b7e4 · 0878f76 · 78d67e6 · ffc39f0 · 5d7578e · 0e61110
INITIAL STATUS            ENTREGADO (informe 17)
REOPEN IF ANY             ninguno
DEFECT FOUND              cuatro defectos de 1a, congelados como C1–C5 en el informe 17 y
                          cerrados por las revisiones B, B.1, B.2 y B.3
CORRECTIVE UNIT           interna (la propia cadena B.*)
FINAL ADJUDICATED STATUS  CLOSED / PASS
CODE IN MAIN              app/buyer/extractor.py · app/buyer/boundary.py
TEST EVIDENCE             test_buyer_extractor 170 passed · test_buyer_boundary 171 passed
CI/REAL-DB EVIDENCE       no aplica (puro, sin I/O)
KNOWN LIMITATION          sin soporte de coreferencia en V0 (B.2 retiró la excepción
                          anafórica de mascotas, fail-closed y declarado)
UNCERTAINTY UNLOCKED      supimos que una afirmación sin mutación (AMBIGUOUS, rechazo)
                          necesita su propia dimensión para poder competir con la
                          declaración durable que viene a invalidar; sin BuyerFieldV0,
                          "120000 USD… no, 100000" conservaba los 120000.
```

### E3.2b.1b\* — intérprete

```
COMMIT(S)                 1cd80a8 · 4df379d · da80bb9
INITIAL STATUS            ENTREGADO (informe 17; 1b y 1b.1 en el índice, 1b.2 en el cuerpo §586)
REOPEN IF ANY             ninguno
DEFECT FOUND              el oracle del eval dejaba pasar el silencio: seis casos negativos
                          se cumplían igual con el modelo callado (cerrado por 1b.2)
CORRECTIVE UNIT           1b.2 · oracle semántico exacto
FINAL ADJUDICATED STATUS  CLOSED / PASS
CODE IN MAIN              app/buyer/interprete.py · evals/corpus_interprete.py ·
                          evals/estabilidad_interprete.py
TEST EVIDENCE             test_buyer_interprete 44 passed · I1/I2/I3 congelados;
                          20/20 en 3 corridas, 0 GRAVE, 0 MEDIA, 0 LEVE (informe 17)
CI/REAL-DB EVIDENCE       no aplica
KNOWN LIMITATION          el eval mide al intérprete contra un corpus, no al producto
UNCERTAINTY UNLOCKED      supimos que un eval con oracle laxo no distingue "el modelo acertó"
                          de "el modelo no dijo nada", y que había que arreglar el eval antes
                          de poder creerle.
```

### E3.2b.2 — reducer

```
COMMIT(S)                 5d11a9f
INITIAL STATUS            ENTREGADO (informe 17, actualizado por este mismo commit)
REOPEN IF ANY             ninguno
DEFECT FOUND              —
FINAL ADJUDICATED STATUS  CLOSED / PASS
CODE IN MAIN              app/buyer/reductor.py · app/buyer/store.py (+40)
TEST EVIDENCE             test_buyer_reductor 39 passed · test_buyer_store_unidad 26 passed
CI/REAL-DB EVIDENCE       no aplica (puro)
KNOWN LIMITATION          escribe CINCO claves — objective · financial ·
                          property_requirements · field_evidence · unresolved_questions.
                          NUNCA hard_constraints, soft_preferences, tradeoffs, stage,
                          place_preferences ni mobility.commute_anchors, que existen en el
                          contrato SIN productor.
UNCERTAINTY UNLOCKED      supimos que el lote de afirmaciones puede volverse memoria de forma
                          determinista, y que `retrieved_at` tiene que venir del orquestador
                          y no del reducer (R-IDEMP-1 congelada).
```

### E3.2b.3 — orquestador

```
COMMIT(S)                 7a875e2
INITIAL STATUS            ENTREGADO (informes 15 y 17, actualizados por este mismo commit)
REOPEN IF ANY             ninguno (pero ver 3a, que es su prueba de concurrencia)
FINAL ADJUDICATED STATUS  CLOSED / PASS
CODE IN MAIN              app/buyer/actualizador.py · extractor.py (+12) · reductor.py (+8)
TEST EVIDENCE             test_buyer_actualizador 37 passed
CI/REAL-DB EVIDENCE       ver 3a
KNOWN LIMITATION          no-op idempotente y concurrencia ENTRE mensajes; la concurrencia de
                          PRIMERA escritura la cubre 3a
UNCERTAINTY UNLOCKED      supimos que un mensaje produce como mucho una revisión, y que la
                          idempotencia se consulta ANTES que el conflicto de revisión.
```

### E3.2b.3a — concurrencia de primera escritura

```
COMMIT(S)                 bc76024  (CANDIDATO, NO PASS — así lo dice su propio mensaje)
                          c42fb99  (REOPEN EVIDENCE ONLY)
INITIAL STATUS            CANDIDATO / HOLD
REOPEN IF ANY             SÍ · c42fb99 · REOPEN EVIDENCE ONLY
DEFECT FOUND              DEFECTO DE EVIDENCIA, NO DE PRODUCCIÓN. Los tres tests decían
                          "dos escritores concurrentes" pero su único estímulo era
                          `asyncio.gather`, que NO garantiza solapamiento. El assert medía
                          el planificador, no el contrato. Cero cambios en actualizador.py,
                          store.py o locks en la reapertura.
CORRECTIVE UNIT           el propio c42fb99 (arnés con barrera + cuarto test secuencial)
FINAL ADJUDICATED STATUS  RE-CLOSED / PASS
CODE IN MAIN              app/buyer/actualizador.py (+49, barrera y BARRERA_TIMEOUT) ·
                          .github/workflows/pruebas.yml (servicio postgres:15 efímero)
TEST EVIDENCE             test_buyer_actualizador_postgres — exige base real
CI/REAL-DB EVIDENCE       CI_EVIDENCE_REFERENCE = HISTORICAL / NOT LOCALLY REPRODUCIBLE
KNOWN LIMITATION          ver §4
UNCERTAINTY UNLOCKED      demostramos que la concurrencia de primera escritura no produce dos
                          revisiones cuando la barrera interviene — y, con el control de
                          mutación, que quien lo impide es LA BARRERA y no la suerte del
                          planificador.
```

### E3.2b.4 — shadow wiring (no-stream)

```
COMMIT(S)                 6211252  (CANDIDATO)
INITIAL STATUS            CANDIDATO
REOPEN IF ANY             SÍ
DEFECT FOUND              EL CAMINO STREAM NO QUEDABA CUBIERTO. `chat()` retorna el
                          StreamingResponse en el `if stream:` y el wiring de la sombra vivía
                          33 líneas más abajo. Con `?stream=true` —el camino que usa la
                          gente— `actualizar_en_sombra` NUNCA se invocaba. En producción:
                          200 OK y cero filas en `buyer_context_heads`.
                          No falló el updater, ni el store, ni el reducer, ni Postgres:
                          falló LA COSTURA.
CORRECTIVE UNIT           E3.2b.4a
FINAL ADJUDICATED STATUS  REOPEN / FAIL   — INMUTABLE. No se convierte retrospectivamente
                                            en PASS: el PASS pertenece a la unidad
                                            correctiva 4a.
CODE IN MAIN              app/buyer/sombra.py · app/config.py (flag) · app/routers/chat.py (+7)
TEST EVIDENCE             test_buyer_sombra 22 passed
CI/REAL-DB EVIDENCE       la sombra no necesita base real para sus pruebas de aislamiento
KNOWN LIMITATION          su guarda `test_la_sombra_NO_toca_la_respuesta_ni_las_tarjetas`
                          exigía `len(llamadas) == 1` sobre todo el fichero: un PROXY que
                          valía mientras hubiera UN solo camino. Reescrito en 4a.
UNCERTAINTY UNLOCKED      descubrimos que el wiring no cubría `stream=true`, y por qué se
                          coló: `_stream_agent` no tenía UN SOLO test, siendo la rama que su
                          propio código llama dos veces "el camino que usa la gente de verdad".
```

### E3.2b.4a — stream shadow wiring hotfix

```
COMMIT(S)                 94ee869
INITIAL STATUS            unidad correctiva autorizada por el FAIL de E3.2b.4
REOPEN IF ANY             ninguno
PURPOSE                   minimal stream shadow wiring hotfix
FINAL ADJUDICATED STATUS  CLOSED / PASS
CODE IN MAIN              app/routers/chat.py (+17)
                          TRES líneas de producción:
                            · `_stream_agent(message, session_id, user=None)`
                            · `asyncio.create_task(actualizar_en_sombra(user, _msgs))`
                              dentro del bloque que recupera el estado final
                            · el endpoint pasa `user` al cruzar el branch
TEST EVIDENCE             test_buyer_sombra_stream 13 passed (fichero nuevo, 342 líneas) ·
                          test_buyer_sombra reescrito (guarda por camino, no por fichero)
CI/REAL-DB EVIDENCE       desplegado a producción en d2a0325 (preflight local del 2026-08-29)
KNOWN LIMITATION          observa el turno; sigue sin autoridad sobre la conversación
UNCERTAINTY UNLOCKED      demostramos que el camino SSE entra también a la sombra, y que
                          cablear una capa en un endpoint con DOS ramas exige probar las dos.
```

**Verificación contra el árbol (2026-09-11):** el arreglo sigue presente.
`app/routers/chat.py:17` importa `actualizar_en_sombra`; hay **dos** puntos de llamada —
`:1024` dentro de `_stream_agent` (camino SSE) y `:1150` en el camino no-stream — y
`_stream_agent` conserva el parámetro `user` en su firma (`:915`).

### E3.2b.5 — allowlist fail-closed

```
COMMIT(S)                 7bb7942  (CANDIDATO)
INITIAL STATUS            CANDIDATO
REOPEN IF ANY             ninguno
FINAL ADJUDICATED STATUS  CLOSED / PASS
CODE IN MAIN              app/buyer/sombra.py (+64) · app/config.py (+8)
TEST EVIDENCE             test_buyer_shadow_allowlist 22 passed (fichero nuevo, 281 líneas) ·
                          test_buyer_sombra 22 passed
CI/REAL-DB EVIDENCE       no aplica
KNOWN LIMITATION          ver §5
UNCERTAINTY UNLOCKED      demostramos que el flag por sí solo no habilita a nadie: gobierna
                          `flag ∧ allowlist`, y con la allowlist vacía no corre para nadie.
```

### E3.2b.6 — G16 · moneda del mercado del despliegue

```
COMMIT(S)                 0baaa5f
INITIAL STATUS            entregado, sin acta
REOPEN IF ANY             ninguno
DEFECT FOUND (que corrige) turno REAL de producción, canary G14, 2026-08-29:
                          "…presupuesto máximo de 900 dólares"
                            → modelo: SetBudgetMax(900, USD)  correcto, 5/5 corridas
                            → guarda: `_MONEDA_ISO[USD] = \busd\b`, no halla "usd"
                            → AMBIGUOUS → budget_max = null + repregunta por la moneda
                          El dato existía en el raw del modelo y desaparecía en NUESTRA capa
                          determinista. No era el LLM.
FINAL ADJUDICATED STATUS  CLOSED / PASS · CODE+CI      ← adjudicado 2026-09-11
CODE IN MAIN              app/buyer/extractor.py (+45) · app/config.py (+41,
                          `BUYER_MARKET_CURRENCY`, vacío por defecto, ISO-4217 o fallo
                          de arranque)
TEST EVIDENCE             test_buyer_market_currency 23 passed (fichero nuevo, 247 líneas)
CI/REAL-DB EVIDENCE       el código está contenido en d2a0325; CI del release = 2340 / 0 / 0
KNOWN LIMITATION          `BUYER_MARKET_CURRENCY` vacío = comportamiento pre-G16
                          (fail-closed). Ver la precondición de activación en §6.1.
                          La regla es una conjunción de TRES y el orden importa: la mutación
                          propone USD ∧ el texto nombra la denominación en su misma cláusula
                          ∧ el mercado del despliegue declara USD.
UNCERTAINTY UNLOCKED      supimos que una regla correcta en abstracto —"hay ocho dólares en
                          el mundo"— puede estar equivocada en la plaza donde el producto
                          opera, y que el coste era convertir la forma más común de decir un
                          presupuesto en una repregunta falsa.
```

---

## 4 · E3.2b.3a · reproducibilidad actual ≠ evidencia histórica

```
FINAL STATUS                      RE-CLOSED / PASS
CURRENT_REPRODUCTION_LIMITATION   los tests de concurrencia exigen PostgreSQL real y aparecen
                                  SKIPPED sin TEST_DATABASE_URL.
                                  Medido el 2026-09-11:
                                    test_buyer_actualizador_postgres  ...  4 skipped
                                    test_buyer_store_postgres         ... 15 skipped
                                  Esto NO revierte el PASS histórico: es una limitación del
                                  entorno de reproducción, no un veredicto sobre el código.
CI_EVIDENCE_REFERENCE             HISTORICAL / NOT LOCALLY REPRODUCIBLE
                                  (no se cita ningún run id: no hay ninguno disponible
                                   localmente y no se inventa)
```

**Evidencia local disponible del cierre**, toda ella verificable sin red:

1. **`.github/workflows/pruebas.yml`** en `origin/main` declara el servicio
   `postgres:15` efímero con `POSTGRES_DB: buyer_store_test` y
   `TEST_DATABASE_URL: postgresql+asyncpg://test:test@localhost:5432/buyer_store_test`,
   con el comentario que lo justifica: *«la concurrencia del buyer updater (dos escritores
   sobre la misma fila) sólo se puede demostrar con FOR UPDATE y un UNIQUE reales. Un doble
   en memoria prueba la política, no la serialización.»*

2. **El mensaje de `bc76024`** declara explícitamente `COMMIT CANDIDATO, NO PASS` y enumera
   los cuatro defectos reproducidos antes de tocar nada — entre ellos que
   `rutas_divergentes(None, …)` devolvía las cinco rutas, y que el doble del store mentía
   (`(actual or 0) + 1` frente al real `0 if actual is None else actual + 1`).

3. **El mensaje de `c42fb99`** conserva la medición con control de mutación, que es la
   evidencia de gate:

   ```
   test viejo, 20 repeticiones contra Postgres real ....... 19 verde / 1 ROJO
   test viejo + 50 ms antes del segundo escritor .......... ROJO determinista
   arnés nuevo, 20 repeticiones ........................... 20 verde
   arnés nuevo + los mismos 50 ms ......................... VERDE
   arnés nuevo con la barrera desactivada + 50 ms ......... ROJO
   ```

   Las dos últimas son el control: sin ellas, un verde no distinguiría «arreglado» de «hoy
   tuvo suerte». Y declara la regresión medida: **2261 passed / 0 skipped con Postgres real
   local; 2213 passed / 48 skipped sin base.**

4. **El diff de `c42fb99`** toca **un solo fichero**, `tests/test_buyer_actualizador_postgres.py`
   (+99/−5). Cero cambios en producción — coherente con `REOPEN EVIDENCE ONLY`.

---

## 5 · E3.2b.5 · mecanismo, reconstruido del repositorio

```
FINAL STATUS = CLOSED / PASS
```

- **Fail-closed por construcción.** `app/buyer/sombra.py::_autorizado` sólo puede devolver
  `True` perteneciendo al conjunto. No hay rama de comodín, *«y su ausencia es la propiedad
  —no una omisión—: `"*"`, `"all"` o `"1"` son identificadores literales que nadie tiene»*.
- **`flag ∧ allowlist`.** `settings.buyer_updater_shadow` (bool) **y** pertenencia a
  `settings.buyer_shadow_allowlist`. Cualquier otra combinación → **nadie**.
- **Allowlist vacía = nadie.** Y no es reposo silencioso: se registra una vez en `warning`,
  porque *«flag encendido con allowlist vacía es una configuración rota —alguien creyó que
  activó el canary— pero es estable»*.
- **Sin `in` sobre la cadena cruda** de configuración, que dejaría entrar a cualquier id que
  sea trozo de otro. Normalización a minúsculas porque un `user_id` es un UUID hex.
- **El rechazo NO se registra**: es el caso normal y anotarlo convertiría el log en una lista
  de quién conversó.
- **Cinco puertas en orden**, declaradas en el docstring del módulo: `FLAG`, `AUTH`,
  `ALLOWLIST`, `COSTURA`, `ESQUEMA`.
- **Tests:** `test_buyer_shadow_allowlist` 22 passed.
- **Limitación actual:** ambos valores por defecto están apagados
  (`buyer_updater_shadow = False`, `buyer_shadow_allowlist = ""`), así que hoy la sombra
  **no corre para nadie** en ningún despliegue que no los declare.

---

## 6 · E3.2b.6 · adjudicación

```
FINAL STATUS = CLOSED / PASS · CODE+CI      (Carlos + ChatGPT, 2026-09-11)
```

Fundamento registrado:

- **commit `0baaa5f`**;
- **el defecto proviene de un canary real** del 2026-08-29, no de un supuesto;
- **el modelo produjo `SetBudgetMax(900, USD)` correctamente, 5/5 corridas** — la pérdida no
  era del LLM;
- **la pérdida ocurría en nuestra guarda determinista**: `_MONEDA_ISO[USD] = \busd\b` no
  hallaba `"usd"` en `"900 dólares"`, y el presupuesto acababa en `null` más una repregunta
  por la moneda;
- **`test_buyer_market_currency` = 23 passed**;
- **el código está contenido en `d2a0325`**;
- **CI del release = 2340 / 0 / 0**.

**Alcance exacto del PASS.** Es `CODE+CI`: el código es correcto y el release que lo contiene
pasó CI. **No se afirma que esté verificado activo en producción** — no existe evidencia
suficiente para esa afirmación, y el Buyer Updater no es productivo hoy.

### 6.1 · Precondición de activación · `BUYER_MARKET_CURRENCY`

```
BUYER_MARKET_CURRENCY vacío  →  comportamiento pre-G16  →  fail-closed
```

**Antes de activar el Buyer Updater en cualquier despliegue**, `BUYER_MARKET_CURRENCY` debe
estar:

1. **definido explícitamente** (no heredado ni vacío);
2. **validado como ISO-4217** — `app/config.py` ya lo exige: tres letras o **fallo de
   arranque**, deliberadamente, para que un `dolares` mal escrito no sea indistinguible de un
   canary averiado;
3. **coherente con el mercado servido** — hoy Quito, Ecuador dolarizado.

**La ausencia de esta configuración NO revierte el PASS de la unidad**, porque el Buyer
Updater no es productivo. **Pero SÍ bloquea cualquier activación o canary del updater**: sin
ella se reproduce exactamente el defecto que G16 vino a corregir, y la primera unidad que
consuma `unresolved_questions` preguntaría algo que la persona ya dijo.

```
CODE PASS   ≠   EFFECTIVE DEPLOYMENT CONFIGURATION
```

---

## 7 · Estado productivo al final de E3.2

**Lo que EXISTE:**

```
BuyerContext persistence      SÍ   migrations/028 · buyer_context_heads + _revisions
BuyerContext versioning       SÍ   context_revision incremental · historial append-only
                                   · UNIQUE(buyer_id, source_message_id)
Updater                       SÍ   app/buyer/actualizador.py
Correction semantics          SÍ   cinco mutaciones Clear* en la unión cerrada
Shadow wiring                 SÍ   app/buyer/sombra.py + chat.py (no-stream)
Stream shadow wiring          SÍ   chat.py:1024, dentro de _stream_agent (E3.2b.4a)
Fail-closed allowlist         SÍ   flag ∧ allowlist, sin comodín
```

**Y aun así:**

```
BUYER_CONTEXT_PRODUCTIVE = NO
```

Porque, todo medido contra `origin/main`:

- **`buyer_updater_shadow = False` por defecto**;
- **`buyer_shadow_allowlist = ""`** — vacía = nadie, sin comodín;
- **no existe lector de `BuyerContext` fuera de su propio writer** — `cargar_ultima` tiene
  exactamente dos llamadores y los dos están dentro de `actualizador.py`; el único importador
  de `app.buyer` fuera del paquete es `chat.py:17 → actualizar_en_sombra`, que es una vía de
  **escritura**;
- **`BuyerContext` no alimenta el ranking** — el carril productivo sigue siendo
  `_user_texts → extraer_preferencias → dict`, recalculado por turno;
- **`BuyerContext` no alimenta la respuesta**;
- **`unresolved_questions` no tiene consumidor** — `reductor.py:263` las fabrica y
  `sombra.py` lo dice sin adorno: *«el sistema registra preguntas que nadie hace»*.

**No se llama «productivo» a código fusionado.** Está fusionado, probado y apagado.

---

## 8 · Evidencia de pruebas

Medido el 2026-09-11, con `PYTHONDONTWRITEBYTECODE=1`, `python -B`, `-p no:cacheprovider`:

| Suite | Resultado |
|---|---|
| `test_buyer_extractor` | **170 passed** |
| `test_buyer_boundary` | **171 passed** |
| `test_buyer_interprete` | **44 passed** |
| `test_buyer_reductor` | **39 passed** |
| `test_buyer_actualizador` | **37 passed** |
| `test_buyer_sombra` | **22 passed** |
| `test_buyer_sombra_stream` | **13 passed** |
| `test_buyer_shadow_allowlist` | **22 passed** |
| `test_buyer_market_currency` | **23 passed** |
| `test_buyer_store_unidad` | **26 passed** |
| `test_buyer_evidence_input_seam` | **29 passed** |
| `test_buyer_precondiciones_e32` | **6 passed, 12 skipped** |
| `test_buyer_actualizador_postgres` | **4 skipped** — exige `TEST_DATABASE_URL` |
| `test_buyer_store_postgres` | **15 skipped** — exige `TEST_DATABASE_URL` |
| **Focal Buyer** | **602 passed · 31 skipped · 0 failed** |
| **Suite completa** | **3080 passed, 49 skipped · exit 0** |

---

## 9 · Limitaciones actuales

1. **La sombra está apagada para todos** por defecto (`flag=False ∧ allowlist=""`).
2. **`unresolved_questions` no tiene consumidor.** Se producen preguntas que nadie hace.
3. **El reducer escribe cinco claves.** `hard_constraints`, `soft_preferences`, `tradeoffs`,
   `stage`, `place_preferences` y `mobility.commute_anchors` existen en `BuyerContextV0`
   **sin productor**.
4. **La evidencia de `3a` no se reproduce sin PostgreSQL real.** Ver §4.
5. **Sin coreferencia en V0** (E3.2b.1a-B.2, fail-closed y declarado).
6. **`BUYER_MARKET_CURRENCY` vacío** revierte al comportamiento pre-G16 y **bloquea la
   activación** del updater. Ver §6.1.

---

## 10 · Definition of Done §20 · puntos 8–10

| Subunidad | 8 · DOCUMENTATION | 9 · GATE EVIDENCE | 10 · UNCERTAINTY UNLOCKED |
|---|---|---|---|
| **1a\*** | informe 17 + §3 de este acta | 341 pruebas focales | una afirmación sin mutación necesita dimensión propia para invalidar una declaración durable |
| **1b\*** | informe 17 + §3 | 44 pruebas + eval 20/20 ×3 | un oracle laxo no distingue acierto de silencio; hubo que arreglar el eval antes de creerle |
| **2** | informe 17 + §3 | 65 pruebas | el lote se vuelve memoria de forma determinista; el reloj lo pone el orquestador |
| **3** | informes 15 y 17 + §3 | 37 pruebas | un mensaje produce como mucho una revisión; idempotencia antes que conflicto |
| **3a** | este acta, §3 y §4 | control de mutación en `c42fb99`: barrera desactivada → **ROJO** | demostramos que la concurrencia de primera escritura no produce dos revisiones cuando la barrera interviene |
| **4** | este acta, §3 | 22 pruebas + el fallo observado en producción (200 OK, cero filas) | descubrimos que el wiring no cubría `stream=true` |
| **4a** | este acta, §3 | 13 pruebas nuevas sobre `_stream_agent` + verificación en el árbol | demostramos que el camino SSE entra también a la sombra |
| **5** | este acta, §3 y §5 | 22 pruebas; `_autorizado` no tiene rama de comodín | demostramos que el flag por sí solo no habilita usuarios: gobierna `flag ∧ allowlist` |
| **6** | este acta, §3 y §6 | 23 pruebas + CI 2340/0/0 del release que lo contiene | supimos que una regla correcta en abstracto puede ser falsa en la plaza donde opera el producto |

**Punto 10 de E3.2 en conjunto, sin adorno:** el pipeline del Buyer Updater corre de extremo
a extremo —interpreta, enruta, reduce, versiona, persiste y se aísla— **y el producto sigue
sin leerlo**. Eso es lo que esta fase desbloqueó y lo que no.

---

## 11 · Elementos sin resolver

| # | Elemento | Dueño |
|---|---|---|
| 1 | **Consumo de `unresolved_questions`** — pendiente desde el informe 15 | unidad futura |
| 2 | **Lector de `BuyerContext` fuera del writer** — sin él, Gate F3 §3–§6 son indemostrables | `F3-TOOLS-MIN-1A`, no autorizada |
| 3 | **Reproducir la evidencia de `3a`** localmente exige levantar PostgreSQL real | opcional |
| 4 | **`BUYER_CONTEXT_PRODUCTIVE = NO`** — integración productiva del updater | fase futura |
| 5 | **`GATE F3 = HOLD / NOT PASSED`** | F3 |

`E3.2b.6` ya no figura aquí: quedó adjudicada `CLOSED / PASS · CODE+CI` en §6.

---

## 12 · Recomendación

1. **E3.2 queda cerrada.** No se reabre ninguna subunidad; la genealogía de §3 es inmutable.
2. **No abrir `F3-TOOLS-MIN-1A`** hasta que Carlos + ChatGPT lo autoricen expresamente.
3. Cuando se abra, decidir **de antemano** si es *costura caracterizada* (criterio de PASS:
   existe, es correcta, es inerte, con `PRODUCTION_READ_CALLERS = 0` declarado como propiedad
   medida) o *costura con consumidor no-LLM*. Sin esa decisión previa reaparece el patrón de
   `PLAN04-2.3-R0A`: código puro, cero llamadores, imposible de cerrar.
4. **Antes de cualquier activación o canary del updater**, satisfacer la precondición de §6.1
   (`BUYER_MARKET_CURRENCY` definido, ISO-4217, coherente con el mercado).

---

## 13 · Estado final

```
E3.2b.1a*                 CLOSED / PASS
E3.2b.1b*                 CLOSED / PASS
E3.2b.2                   CLOSED / PASS
E3.2b.3                   CLOSED / PASS
E3.2b.3a                  RE-CLOSED / PASS   · CI HISTORICAL / NOT LOCALLY REPRODUCIBLE
E3.2b.4                   REOPEN / FAIL      · INMUTABLE
   └→ E3.2b.4a            CLOSED / PASS
E3.2b.5                   CLOSED / PASS
E3.2b.6                   CLOSED / PASS · CODE+CI

CAN_E3_2_CLOSE            YES
E3_2_FINAL_STATUS         CLOSED / PASS

BUYER_CONTEXT_PRODUCTIVE  NO
GATE F3                   HOLD / NOT PASSED
PLACE                     PRESERVE / DO NOT EXPAND
VOICE                     NOT STARTED
F3-TOOLS-MIN-1A           NOT STARTED
```

> **E3.2 cierra la construcción y evidencia del Buyer Updater. No cierra su integración
> productiva ni Gate F3.**
