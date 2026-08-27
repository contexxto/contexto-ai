# AUTH-READ-GATE.1 — HANDOFF

```
BRANCH                 feat/auth-read-gate-enforcement
BASE DE LA UNIDAD      8a8968da412cd3e1dc6efcb7609ed433fa8b2905
ENTRADA DE 5c          13b949680f5172ba4ab18cb5fc21db7e71086193
CUTOVER DE 5c          5c70e40483cd29ac41dd2fc7d5254e815f0e6d40
EVIDENCIA CASO 5       8b67900dd875a8238ba37551483813cfa31ceb3c

ESTADO                 REVISADO · DECISIÓN = HOLD (ver reporte 13)
SUITE BACKEND          1 665 exit 0   (+102 de autoridad por endpoint)
SUITE FRONTEND         66 exit 0   (35 → 53 → 66)
BUILD FRONTEND         PASS
INVENTARIO 18 ENDPOINTS PASS

PRODUCT CUTOVER        COMPLETE
SECURITY GATE          INCOMPLETE   ← HOLD: Postgres NOT VERIFIED + sin runner de migración
```

---

## ⛔ DECISIÓN DEL GATE — **HOLD**

El informe completo es `docs/agentic_decision_system/13_AUTH_READ_GATE_ENFORCEMENT.md`.

**No es FAIL:** la revisión adversarial de los 18 endpoints —más los 6 de `assets.py` que el
inventario nunca cubrió, y que están correctos— no encontró bypass, autoridad duplicada,
fallback de `session_id` a secas, `device_key` como autoridad, secreto en URL/log/base, claim
no atómico, capacidad sin revocar, ni efecto antes de la puerta. `REGRESSION = 0`.

**No es PASS, por dos hechos concretos:**

1. La sentencia que decide **cada** petición del producto —`SELECT … resume_token_hash,
   resume_revoked_at FROM chat_sessions`— **nunca se ha ejecutado contra PostgreSQL**. No hay
   motor seguro disponible: docker sin demonio, sin servicio, sin binarios, 5432 cerrado, sin
   CLI de Supabase, sin `testcontainers`.
2. **No existe runner de migraciones.** `render.yaml` y `Dockerfile` no aplican nada. Si el
   código se despliega sin `027`, `POST /chat` cae **para todos**, autenticados incluidos.

Para convertirlo en PASS hacen falta esas dos cosas — evidencia y operación, no rediseño.

---

## QUÉ CAMBIÓ EN 5c

`App.jsx` **usa** el modelo de autoridad. Hasta `13b9496` las piezas existían y el producto
las ignoraba; ese era exactamente el hueco entre *"suite verde"* y *"cutover completo"*.

### El cliente ya no fabrica identificadores

Los tres sitios que inventaban un `session_id` piden ahora la sesión al servidor:

| Dónde | Antes | Ahora |
|---|---|---|
| arranque (`useState`) | `'session-' + crypto.randomUUID()` | lo guardado, o `null` → efecto de resolución |
| carril QR (`loadFromDeepLink`) | `` `${qrSessionId(id)}-${aleatorio}` `` | `await bootstrapSession(id)` |
| «nuevo chat» (`resetSession`) | `'session-' + crypto.randomUUID()` | `await bootstrapSession(null)` |

`getOrCreateSession()` y `qrSessionId()` están **eliminados, no sin usar**. Mientras
existieran serían una invitación a volver al modelo en que el identificador *era* la
credencial. El prefijo `qr-{activo}-` lo pone ahora el servidor — es lo que mantiene vivas
las siete consultas de `assets.py` que dependen de él.

### Toda llamada sobre una conversación transporta su capacidad

9 llamadas migradas de `apiHeaders()` a `apiHeadersSesion(sid)`. Quedan **exactamente dos**
con la cabecera genérica, y ninguna lleva `session_id`:

```
POST /push/subscribe    suscripción del navegador
POST /match             imagen suelta
```

`appCutover.test.js` fija ese número en 2. Añadir una tercera llamada sin capacidad rompe el
test — el default correcto pasa a ser `apiHeadersSesion`.

### El secreto se limpia cuando —y solo cuando— deja de valer

- `trasEnvioExitoso()` corre tras fijar la respuesta, en el camino bloqueante **y** en el de
  streaming. **Nunca dentro de un `catch`.** Si se borrara antes de confirmar y el claim
  fallara, el hilo quedaría sin dueño y sin capacidad: inaccesible para siempre.
- `descartarCapacidadRechazada()` en el carril QR y en la comprobación de acceso. **No hay
  reintento sin capacidad** — sería el dual-path que este gate cierra.

### La resolución espera a saber si hay cuenta

`authListo` existe porque la decisión depende de la autenticación: una sesión heredada sin
capacidad se conserva por OWNER si hay cuenta y se abandona si no la hay. Resolver antes
tomaría la rama equivocada y **borraría conversaciones de gente registrada, en silencio**.

---

## LOS SIETE CASOS

Comportamiento del cliente en `sessionFlow.test.js` (18 tests, doble de HTTP que registra
`{op, sid}`); integración en `appCutover.test.js` (13 tests sobre el fuente de `App.jsx`);
**autoridad real del backend** en `tests/test_aislamiento_cross_owner.py` (6 tests).

```
1  QR nuevo                    bootstrap(activo) → id + capacidad          PASS
2  QR revisita                 storeKey → /handoff CON capacidad           PASS
3  legacy anónimo sin cap.     NO se pide nada → bootstrap                 PASS
4  authenticated legacy OWNER  /history SIN capacidad → allow conserva     PASS
5  cross-owner U1 vs U2 REAL   dos mitades, A y B — ver abajo              PASS
6  anon → login → claim        borra el secreto DESPUÉS del éxito          PASS
7  capacidad rechazada         404 → descarta → sin fallback               PASS
```

El caso 3 es el único que **no emite ninguna petición**: preguntar por un `session_id`
heredado sin capacidad sería pedir acceso sin autoridad. Se comprueba que el doble de HTTP
no registra llamada alguna, no que la respuesta sea 404.

### CASO 5 — las dos mitades, y por qué hacen falta las dos

```
A) BACKEND    sesión EXISTENTE con user_id = U2  +  identidad U1  →  404
              tests/test_aislamiento_cross_owner.py

B) FRONTEND   recibido el 404  →  no conservar U2  →  bootstrap
              frontend/src/sessionFlow.test.js
```

**La versión anterior solo tenía B y se presentaba como aislamiento. Era un falso positivo.**
El doble de HTTP del frontend decidía localmente (`existeYEsDeOtro = new Set([SID_DE_U2])`):
demostraba que el cliente reacciona bien a una denegación, no que el backend denegara. El
rótulo está corregido en el fichero y el bloque se llama ahora «mitad B».

**Qué profundidad tiene A.** No hay Postgres en esta suite —no hay `conftest.py`, ni fixture
de base, ni sqlite (y el SQL usa `user_id::text` y `now()`)—. `test_sesion_autoridad.py` ya lo
declaraba en su encabezado. Lo que A añade sobre lo que existía:

| | `test_sesion_autoridad.py` | `test_aislamiento_cross_owner.py` |
|---|---|---|
| entrada | `_decidir(fila, …)`, fila a mano | la tabla, con estado real |
| estado | no hay | lo escribe `crear_sesion()`, código de producto |
| traducción a HTTP | no se ejerce | `_exigir_autoridad` real → 404 |
| el doble | `_DBFalsa` devuelve filas prefabricadas | almacena y devuelve; **no decide** |

`_TablaChatSessions` es un **almacén de filas**, no un doble que responde sí o no — y eso se
verifica, no se afirma: `test_la_tabla_NO_pudo_haber_tomado_la_decision` comprueba que la
lectura emitida por el código real lleva **un solo parámetro** (`sid`), que ninguna identidad
llega a la base, y que la consulta es **idéntica** para U1 y para U2. Misma fila, misma
pregunta, resultados opuestos: la diferencia solo puede venir de `_decidir`.

**Se verificó que el test puede fallar.** Dos mutaciones sobre `_decidir`:

```
dueno = None                     → caen 2 tests, pero NO el del caso 5
                                   (deniega a todos: no aísla el fallo)
if user is not None: → OWNER     → caen 4, incluido el del caso 5   ✔
```

La segunda es la vulnerabilidad real —cualquier autenticado entra en cualquier hilo con
dueño— y el test la caza. `app/sesion_autoridad.py` quedó restaurado byte a byte
(`git diff --quiet` limpio) antes de continuar.

**Lo que A todavía NO prueba:** que Postgres ejecute de verdad ese SQL. Eso es el punto 7 de
la unidad (tests de integración), y está anotado como tal en el propio fichero.

### CASO 6 — no se reabrió, y por qué

El claim server-side ya tenía cobertura previa: 5 tests en `test_sesion_autoridad.py`
(atomicidad, ligadura a la capacidad que autorizó, fallo ruidoso si no toca exactamente una
fila, negativa antes de tocar la base sin secreto). No había laguna que conectar, así que no
se añadió nada — la revisión pedía evidencia solo si faltaba.

---

## HALLAZGO DE 5c — el hueco de `resetSession`

Al volverse asíncrono («nuevo chat» es ahora un viaje al servidor), entre limpiar la pantalla
y recibir el id nuevo `sessionId` seguía siendo **el de la conversación anterior**. Un mensaje
escrito rápido se habría ido al hilo recién cerrado, y en pantalla no habría quedado rastro
porque los mensajes ya estaban limpios.

Se suelta la sesión (`setSessionId(null)`) **antes** de pedir la nueva. Eso obligó a guardar
tres efectos que consultaban por `sessionId` (`/history`, reanudar modo corredor, sondeo de
handoff) y el envío de turno. Es consecuencia directa de que crear una sesión dejó de ser una
línea síncrona: **cualquier código que asuma que `sessionId` siempre existe es sospechoso.**

`pedirCorredor` NO lleva guarda: su CTA solo aparece con mensajes en pantalla, lo que implica
sesión resuelta. Es una suposición razonada, no una omisión — si algún día ese botón aparece
antes, hay que guardarlo.

---

## PATRÓN PROPIO — texto vs. estructura, cuarta vez

Ya iban tres tests míos en esta unidad afirmando sobre **texto** donde debían afirmar sobre
**estructura**. `appCutover.test.js` iba camino de ser el cuarto: `App.jsx` está densamente
comentado y los comentarios nombran `bootstrapSession`, `X-Session-Resume` y
`descartarCapacidadRechazada` — un `grep` habría dado verde sin que el código llamara a nada.

Primer intento: un tokenizador propio para borrar comentarios. **Se comía el 92 % del fuente**
(120 966 → 9 201 caracteres) en cuanto encontraba una plantilla anidada, y ocho tests fallaron
por eso, no por el código.

`codigoDesnudo.js` usa ahora **oxc** —el parser que Vite ya usa para compilar este mismo
fichero— vía `parseSync` de `vite`: 449 comentarios con rangos exactos, 0 errores de parseo.
Lanza si el fichero no parsea, porque un verde sobre un fuente a medias no significa nada.

> **La lección no es "usa un parser".** Es que escribí un tokenizador de 70 líneas teniendo
> uno de verdad a un import de distancia — el mismo reflejo que produjo los tres fallos
> anteriores, una capa más arriba.

---

## CÓMO CORRER LAS SUITES

El worktree no trae `.env` ni venv propios:

```bash
cp /c/Users/DETPC/Desktop/Contexto-AI/.env .env
/c/Users/DETPC/Desktop/Contexto-AI/.venv/Scripts/python.exe -m pytest -q
```

Sin `.env` fallan **37 ficheros en colección** con un `ValidationError` de pydantic — no es un
fallo de código. El `.env` está en `.gitignore`; **no se commitea y conviene borrarlo al
terminar** (es una copia de secretos de producción en un directorio temporal).

Frontend, desde `frontend/`:

```bash
npx vitest run && npm run build
```

---

## TESTS TRANSFORMADOS EN 5c

Cuatro caracterizaciones congelaban el comportamiento viejo del frontend. **No se borran** —
cada una documenta qué congelaba y qué política autorizó el cambio.

| Test | Clase | Qué cambió |
|---|---|---|
| `..._el_session_id_del_QR_ya_NO_nace_en_el_cliente` | `EXPECTED_POLICY_CHANGE` | lo emite bootstrap |
| `..._la_reanudacion_del_QR_sigue_siendo_por_navegador` | `UNCHANGED_INVARIANT` | misma propiedad, **mecanismo distinto** |
| `..._el_handoff_del_QR_ahora_va_con_capacidad` | `EXPECTED_POLICY_CHANGE` | `apiHeaders()` → `apiHeadersSesion(prev)` |
| `..._el_device_id_ya_no_privatiza_la_sesion_del_QR` | `EXPECTED_POLICY_CHANGE` | privacidad por capacidad, no por nombre |

El segundo merece atención: la limitación de producto es idéntica (no hay recuperación entre
dispositivos), pero en `.0` el hilo estaba atado al navegador porque el `device_id` iba
*dentro del identificador* — **adivinable** para quien conozca el esquema, y encima el
`device_key` viaja al servidor en cada llegada (`visita.device_key`, migración 024). Ahora
está atado porque el secreto de 32 bytes vive en ese `localStorage` y en ningún otro sitio.
Misma limitación, garantía distinta. Por eso se transforma en vez de dejarse igual.

El cuarto **refuerza** la conclusión de E3.1a: el `device_key` nunca fue autoridad, y ahora
tampoco lo aparenta.

---

## LINT

```
App.jsx        9 problemas en la base (8a8968d)  →  8 ahora
ficheros nuevos  eslint exit 0
```

Cero problemas nuevos; uno menos. Los dos avisos de `Unused eslint-disable` ya estaban en la
base — deuda preexistente, fuera de alcance a propósito.

---

## LOS 11 ENDPOINTS — antes, ahora y con qué se demuestra

Todos denegados con **404** y —esto es lo que se verifica, no el código de estado— con **cero
efectos laterales**. Los tests viven en `tests/test_autoridad_endpoints.py` (89, parametrizados
sobre los once).

| # | Endpoint | Autoridad ANTES | Autoridad AHORA | Qué permitía |
|---|---|---|---|---|
| 1 | `GET /{sid}/history` | ninguna | `_exigir_autoridad` | leer el hilo entero con solo el id |
| 2 | `GET /{sid}/handoff` | ninguna | `_exigir_autoridad` | leer los mensajes con el corredor |
| 3 | `GET /{sid}/intencion` | ninguna | `_exigir_autoridad` | ver el score de intención de compra |
| 4 | `POST /{sid}/handoff/push` | ninguna | `_exigir_autoridad` | **secuestrar el canal de avisos** del hilo |
| 5 | `POST /{sid}/handoff` | `get_optional_user`, sin puerta | `_exigir_autoridad` | disparar contacto real con el corredor |
| 6 | `POST /{sid}/handoff/mensaje` | `get_optional_user`, sin puerta | `_exigir_autoridad` | **escribir suplantando** al interesado |
| 7 | `POST /comparar` | ninguna | `_exigir_autoridad` | revelar las necesidades declaradas del hilo |
| 8 | `POST /lead-contacto` | ninguna ("público") | `_exigir_autoridad` | **plantar el email y el push de un tercero** |
| 9 | `GET /notificaciones` | `OR` con rama sin autorizar | `_alcances_autorizados` (+B.1) | leer avisos ajenos |
| 10 | `GET /conversaciones` | `OR` con rama sin autorizar | `_alcances_autorizados` | leer la bandeja ajena |
| 11 | `POST /notificaciones/leidas` | `OR` con rama sin autorizar | `_alcances_autorizados` | **marcar leídos los avisos de otro** |

Cobertura, idéntica para los once:

| Propiedad probada | Resultado |
|---|---|
| OWNER sobre su propia sesión | pasa la puerta |
| U1 sobre sesión **existente** de U2 | 404 · sin efectos |
| anónimo con **su** capacidad | pasa la puerta |
| anónimo con capacidad de **otra** sesión | 404 · sin efectos |
| `session_id` a secas, sin capacidad | 404 · sin efectos |
| autenticado sin la capacidad del hilo anónimo | 404 · sin efectos |
| existente-ajena vs. inexistente | **misma** respuesta, byte a byte |

Ninguno de los once es *account-only*: los once sirven al interesado del QR, que no tiene
cuenta, así que el carril anónimo con capacidad se conserva en todos. Lo account-only de este
router (`/sessions`, `/push/subscribe`, los diagnósticos) no está en la lista y sigue con
`get_current_user`.

**El oráculo no es el 404, es el centinela.** Un 404 emitido *después* de escribir sería un
desastre silencioso: el atacante ve un error y el efecto queda hecho. La base falsa atiende
`chat_sessions` —donde vive la autoridad— y levanta un centinela ante cualquier otra tabla. Si
el gate deniega, el centinela no se dispara: no hubo `INSERT`, ni `UPDATE`, ni push, ni
mensaje, ni cambio de estado de leído.

---

## EL GRUPO B — cómo se cerró el `OR`

El fallo no era el `OR`: era que **una de sus dos ramas no tenía autoridad detrás**.

```sql
WHERE (… destinatario_user_id = :u)   OR   (… destinatario_session = :s)
```

`:s` venía del cliente sin comprobar nada. Un autenticado que pasara la sesión de otra persona
leía —o marcaba como leídos— sus avisos por la segunda rama.

**No se arregló añadiendo `_exigir_autoridad` y dejando el `OR` intacto.** El `WHERE` se
compone ahora en `_alcances_autorizados`, que solo **construye** la rama de sesión después de
que la autoridad la haya probado. No hay cláusula que desactivar ni parámetro que colar: lo que
protege es la forma del código, no la disciplina de quien lo edite mañana.

```
modo cuenta    user presente        →  destinatario_user_id = :u    (lo prueba el Bearer)
modo sesión    session_id presente  →  destinatario_session = :s    (lo prueba _exigir_autoridad)
ninguno        ni user ni session   →  respuesta vacía, sin consulta
```

Estar autenticado **no** añade la rama de sesión, y aportar un `session_id` **no** amplía lo que
ya se tenía por cuenta. Son dos alcances independientes que se suman solo cuando ambos están
probados. De paso desaparecieron los `CAST(:u AS uuid) IS NOT NULL AND …`, que existían solo
para neutralizar en tiempo de ejecución una rama que ahora no se emite.

**Por qué la unión sigue existiendo, y no dos consultas separadas:** `Campana.jsx` manda
`session_id` **siempre**, también cuando hay cuenta. Hacer que un `session_id` presente
significara "solo modo sesión" le habría quitado al corredor autenticado sus avisos de cuenta.
La unión es un requisito de producto; lo que no era admisible era una rama sin probar.

---

## B.1 — LA SESIÓN COMO FILTRO vs. COMO RECURSO

Al cerrar los once quedó una asimetría que no era de seguridad sino de **disponibilidad**.

`_alcances_autorizados` usaba `_exigir_autoridad`, que convierte cualquier fallo en 404 y mata
la petición entera. En `GET /{sid}/history` eso es exactamente lo correcto: la conversación **es**
el recurso pedido, y sin ella no hay nada que servir. En la campana no: ahí la conversación es un
**filtro opcional** sobre una lista que ya tiene su propio alcance de cuenta.

El resultado era que un `session_id` viejo, revocado o ajeno guardado en el navegador dejaba a un
usuario autenticado sin **sus propios** avisos. Y `Campana.jsx` se traga el error en silencio, así
que la campana se quedaba vacía sin explicación.

### La matriz, tal como está implementada

| # | cuenta | session_id | Resultado |
|---|---|---|---|
| 1 | no | no | vacío · **no se consulta nada** |
| 2 | no | autorizada | alcance sesión |
| 3 | no | NO autorizada | **404** |
| 4 | sí | no | alcance cuenta · no se lee `chat_sessions` |
| 5 | sí | autorizada | cuenta ∪ sesión |
| 6 | sí | NO autorizada | **alcance cuenta únicamente · NO 404** |

El caso 3 no se relaja: sin cuenta la sesión era el único alcance posible, y responder "vacío" en
vez de 404 afirmaría que la petición fue válida.

Para el autenticado, **una sesión ajena y una inexistente dan el mismo resultado observable**. Si
difirieran, la campana propia sería un oráculo de existencia: se podría averiguar qué `session_id`
existen probándolos contra ella.

### Lo que NO cambió

La rama de sesión **sigue sin construirse** cuando no está probada. Degradar el alcance y
ampliarlo son cosas distintas: esto solo puede devolver *menos*, nunca más. Los datos de la sesión
no demostrada no se entregan en ninguno de los seis casos.

**La tolerancia es exclusiva de los tres híbridos.** En `history`, `handoff`, `intencion`,
`comparar`, `lead-contacto` y las mutaciones del handoff, la conversación es el recurso: autoridad
inválida sigue siendo 404. `test_B1_la_tolerancia_NO_se_extiende_a_los_ocho_directos` caza a quien
generalice el patrón.

### `POST /notificaciones/leidas` — la mutación

Es el único de los tres que escribe. Con la rama de sesión caída, el `UPDATE` solo alcanza filas
cuyo `destinatario_user_id` es el llamante. El parámetro `hilo` es un **filtro**, no una autoridad:
va en `AND` con la condición autorizada, así que pasar el hilo de otra persona no abre ninguna
puerta — simplemente hace que el `UPDATE` no encuentre nada.

Se prueban los dos lados: con el hilo de U2 no se toca nada de U2; con un hilo propio de U1 el
`UPDATE` conserva su rama de cuenta. El segundo importa tanto como el primero — si la degradación
hubiera vaciado también el alcance de cuenta, el arreglo no habría arreglado nada.

### Cómo se observa (y por qué no basta el status code)

El oráculo de B.1 **no es el código de estado**: es el SQL que de verdad se emitió. La tabla falsa
lo registra antes de que salte el centinela, así que los tests afirman sobre las ramas que llegaron
a construirse — `destinatario_session` no puede aparecer en ninguna sentencia cuando la sesión no
está probada, ni siquiera cuando la petición sí prospera por cuenta.

**Cambio en el arnés:** `ensure_handoff_tables` / `ensure_lead_actividad` se neutralizan en la
fixture. Crean el esquema al vuelo y su lista incluye un par de migraciones DML; si se dejaran
correr, el centinela saltaría **ahí** —antes de la consulta real— y sería imposible observar qué
`WHERE` se emitió. No es una excepción cómoda: el bootstrap de esquema no es el efecto del
endpoint y tiene su propio candado de módulo. El centinela sigue estricto con toda sentencia del
endpoint.

### Mutaciones

```
la rama de sesión se añade pese a no estar probada  →  caen 9 tests
la tolerancia se extiende al anónimo (caso 3)       →  caen 13 tests
```

`app/routers/chat.py` restaurado y verificado antes de continuar.

---

## HALLAZGOS DE ESTA UNIDAD

**1 · Dos endpoints se tragan cualquier excepción.** `estado_handoff` devuelve su `vacio` y
`lead_contacto` convierte en 500 **cualquier** `Exception`. El centinela de los tests tuvo que
heredar de `BaseException` para no quedar atrapado ahí — si no, el test habría visto "no hubo
efecto" cuando sí lo hubo: un falso verde en un gate de seguridad. La autoridad va delante de
ambos, así que no los afecta; pero **son endpoints que degradan en silencio** y conviene
saberlo.

**2 · El `vacio` de `estado_handoff` no sirve como denegación.** Devolver "no hay handoff" a
quien no tiene autoridad, y los mensajes a quien sí, distingue la sesión que existe de la que
no. La denegación tiene que ser el 404 de siempre, y por eso el gate va antes del `try`.

**3 · `Campana.jsx` llamaba sin capacidad.** Mandaba `session_id` con `apiHeaders()`, que no
lleva `X-Session-Resume`. Con los endpoints cerrados, la campana de un anónimo habría dado 404.
Migrada a `apiHeadersSesion(sessionId)` — es la única regresión que obligó a tocar frontend, y
`App.jsx` no se tocó.

**4 · Denegar por sesión ajena tumba TODA la petición**, no solo esa rama. Es deliberado: pedir
una conversación que no se puede probar es un intento de acceso, no una preferencia de filtrado.
El coste es que un `session_id` local caducado deja sin campana a un autenticado que sí tiene
avisos de cuenta. Es aceptable porque, tras 5c, el cliente solo conserva sesiones que él mismo
arrancó y cuya capacidad custodia.

---

## POSTGRES — lo que sigue SIN demostrarse

Se investigó, como pedía la unidad, y **no hay vía disponible y segura**:

```
docker              instalado (29.5.2) pero el DEMONIO NO CORRE
testcontainers      no instalado
pytest-postgresql   no instalado
sqlite              no sirve — el SQL usa `user_id::text` y `now()`
DATABASE_URL        apunta a PRODUCCIÓN (Supabase) — descartado de plano
```

Arrancar Docker Desktop y montar el compose es infraestructura pesada para este punto, que es
justo lo que la unidad pidió no hacer. **Queda pendiente y explícito:**

> Ningún test de esta unidad ejecuta el SQL de autoridad contra un Postgres real. Se demuestra
> que **el código real decide** y que **el efecto no ocurre al denegar**. NO se demuestra que
> las sentencias sean válidas para Postgres, ni que los `CAST` se comporten en el motor como
> aquí se asume. Eso es trabajo del punto 7.

Vía más barata cuando se retome: arrancar el demonio de Docker y usar el `docker-compose.yml`
que ya está en el repo, o instalar `testcontainers`. Ninguna de las dos se hizo aquí.

---

## MUTACIONES — la prueba de que estos tests pueden fallar

```
rama de sesión sin autorizar (el fallo original)   →  caen 12 tests
GET /history sin la puerta                          →  caen 7 tests
```

`app/routers/chat.py` quedó restaurado y verificado antes de continuar.

---

## COMPLETADO

```
BACKEND
[✓] 1   migración 027
[✓] 2   capability primitives
[✓] 3   bootstrap atómico (núcleo)
[✓] 4   costura central de autoridad + claim seguro contra TOCTOU
[✓] 5a  bootstrap HTTP
[✓] 5d  enforcement en POST /chat
[✓] 6   LOS 11 ENDPOINTS RESTANTES
[✓] 7   tighten de share / archive / rename

FRONTEND
[✓] 5b  piezas: custodia, bootstrap, transporte, árbol de recuperación
[✓] 5c  INTEGRACIÓN en App.jsx + los siete casos
[✓]     Campana.jsx transporta la capacidad
```

## PENDIENTE

```
[ ] 7   tests de integración — incluye la evidencia Postgres, que sigue abierta
[ ] 8   reporte 13 — debe corregir formalmente a `.0` sobre `update_session`
[ ] 9   revisión completa del diff productivo
[ ] 10  PR + decisión PASS / HOLD / FAIL
```

---

## ESTADO

```
SECURITY ENDPOINT ENFORCEMENT   COMPLETE
PRODUCT CUTOVER                 COMPLETE
SECURITY GATE                   INCOMPLETE
```

El gate sigue incompleto **a propósito**: faltan la integración final, la evidencia Postgres si
resulta viable, el reporte 13, la revisión del diff productivo y la decisión.

---

## DECISIONES CONGELADAS

```
session_id identifica; nunca autoriza
no dual-path inseguro
device_key NO es autoridad
capability por X-Session-Resume
secret NUNCA en URL
secret persistido POR SESIÓN, no global
el backend genera el session_id
conservar prefijo qr-{activo}-  (dependencia de assets.py, 7 sitios)
legacy anonymous sin capability NO se recupera
sesión authenticated legacy SÍ continúa por OWNER
anon → auth exige capability válida
la capability se revoca al hacer claim
/shared/{token} no cambia
404 para ausencia de autoridad y de recurso, indistinguibles
```

---

## HALLAZGO QUE CORRIGE A `.0` (sin resolver en el reporte)

**`AUTH-READ-GATE.0` clasificó `update_session` como `owner-auth`, y era incompleto.**

`update_session` (renombrar / fijar) también reclamaba el hilo, mediante un
`INSERT … ON CONFLICT DO UPDATE SET user_id = COALESCE(...)` **previo** a los `UPDATE`
estrictos. Tras esa sentencia el hilo ya era del llamante, así que el `WHERE … AND
user_id = :uid` de abajo pasaba a cumplirse. **Renombrar una conversación anónima ajena
equivalía a quedársela.**

El test de `.0` no lo cazó porque solo miraba el `WHERE` de los `UPDATE`; la vía de claim iba
en la sentencia anterior. `AUTH-READ-GATE.1` elimina esa vía. **El reporte 13 debe corregir
explícitamente a `.0`.**

---

## NOTA — el 503 del bootstrap ante colisión

El comentario en `bootstrap_session` dice que no se reintenta porque *"reintentar es la puerta
por la que se cuela un id elegido"*. **Esa formulación es demasiado amplia.** Con el diseño
actual, un reintento que vuelva a generar el identificador **exclusivamente en el servidor**
seguiría siendo seguro; lo inseguro sería permitir que el **cliente aporte el id**.

No hay que cambiarlo ahora —un 503 ante una colisión prácticamente imposible (12 bytes
aleatorios) es razonable—, pero no se debe razonar como si todo retry fuera inseguro.

---

## NOTA DE PROCESO — `8f14303`

Ese commit se creó **con la suite del backend en rojo**, porque encadené el test y el commit
en el mismo comando y no leí el resultado antes. `106719b` lo corrige.

**No se reescribe la historia.** Está documentado, el commit siguiente lo deja verde, la rama
no tiene PR y el squash del cierre lo convertirá en un solo commit limpio.

---

## NO HACER

```
no crear otra rama
no rebasear
no abrir PR todavía
no declarar AUTH-READ-GATE.1 PASS
no añadir fallback de session_id-only
no restaurar _tag_session_owner
no emitir capability para una sesión existente
no usar device_key
no poner el secret en query params, logs ni mensajes de error
no refactorizar App.jsx por gusto — 5c fue integración, no limpieza
```

---

## Dónde está cada cosa

| Qué | Dónde |
|---|---|
| Esquema | `migrations/027_session_resume_capability.sql` |
| Primitivas + costura + bootstrap núcleo | `app/sesion_autoridad.py` |
| Bootstrap HTTP + `_exigir_autoridad` + enforcement | `app/routers/chat.py` |
| Tests de la costura | `tests/test_sesion_autoridad.py` (29) |
| Oráculo de `.0`, con 10 tests transformados | `tests/test_caracterizacion_acceso_sesion.py` |
| Oráculo de E3.1a, con 4 transformados | `tests/test_caracterizacion_identidad_buyer.py` |
| Custodia de la capacidad (cliente) | `frontend/src/resumeCapability.js` (+ test) |
| Bootstrap y transporte | `frontend/src/api.js` |
| Árbol de recuperación (decide) | `frontend/src/sessionRecovery.js` (+ test) |
| Orquestación (ejecuta) | `frontend/src/sessionFlow.js` (+ test, 7 casos) |
| Integración real en el producto | `frontend/src/appCutover.test.js` |
| **Caso 5 · A — aislamiento REAL entre cuentas** | `tests/test_aislamiento_cross_owner.py` |
| Caso 5 · B — reacción del cliente al 404 | `frontend/src/sessionFlow.test.js` |
| Comentarios fuera, con parser de verdad | `frontend/src/codigoDesnudo.js` |
| No-fuga del secreto | `frontend/src/noLeak.test.js` |
| Política y matriz de origen | `docs/agentic_decision_system/12_AUTH_READ_GATE_*.md` |

**Los tests transformados no se borran.** Cada uno documenta qué congelaba en `.0` y qué
política autorizó el cambio — son el mecanismo que demuestra que cambió **solo** lo autorizado.
