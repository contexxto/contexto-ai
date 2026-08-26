# AUTH-READ-GATE.1 — HANDOFF

```
BRANCH                 feat/auth-read-gate-enforcement
BASE DE LA UNIDAD      8a8968da412cd3e1dc6efcb7609ed433fa8b2905
ENTRADA DE 5c          13b949680f5172ba4ab18cb5fc21db7e71086193

ESTADO                 IN PROGRESS · 5c COMPLETE
SUITE BACKEND          1 557 exit 0
SUITE FRONTEND         66 exit 0   (35 → 53 → 66)
BUILD FRONTEND         PASS
INVENTARIO 18 ENDPOINTS PASS

PRODUCT CUTOVER        COMPLETE
SECURITY GATE          INCOMPLETE   ← 11 endpoints sin cerrar
```

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

Comportamiento en `sessionFlow.test.js` (18 tests, doble de HTTP que registra `{op, sid}`);
integración en `appCutover.test.js` (13 tests sobre el fuente de `App.jsx`).

```
1  QR nuevo                    bootstrap(activo) → id + capacidad          PASS
2  QR revisita                 storeKey → /handoff CON capacidad           PASS
3  legacy anónimo sin cap.     NO se pide nada → bootstrap                 PASS
4  authenticated legacy OWNER  /history SIN capacidad → allow conserva     PASS
5  cross-owner U1 vs U2 REAL   404 → bootstrap                             PASS
6  anon → login → claim        borra el secreto DESPUÉS del éxito          PASS
7  capacidad rechazada         404 → descarta → sin fallback               PASS
```

El caso 3 es el único que **no emite ninguna petición**: preguntar por un `session_id`
heredado sin capacidad sería pedir acceso sin autoridad. Se comprueba que el doble de HTTP
no registra llamada alguna, no que la respuesta sea 404.

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

## COMPLETADO

```
BACKEND
[✓] 1   migración 027
[✓] 2   capability primitives
[✓] 3   bootstrap atómico (núcleo)
[✓] 4   costura central de autoridad + claim seguro contra TOCTOU
[✓] 5a  bootstrap HTTP
[✓] 5d  enforcement en POST /chat
[✓] 7   tighten de share / archive / rename

FRONTEND
[✓] 5b  piezas: custodia, bootstrap, transporte, árbol de recuperación
[✓] 5c  INTEGRACIÓN en App.jsx + los siete casos
```

## PENDIENTE

```
[ ] 6   proteger los 11 endpoints restantes
[ ] 7   tests de integración
[ ] 8   reporte 13 — debe corregir formalmente a `.0` sobre `update_session`
[ ] 9   revisión completa del diff productivo
[ ] 10  PR
```

---

## ⚠️ LA RAMA TODAVÍA NO ES DESPLEGABLE

El producto ya usa el modelo de autoridad, pero **11 endpoints siguen abiertos**. Un
`session_id` filtrado todavía lee la bandeja, el handoff y la intención de otra persona.

```
GET  /{id}/history          GET  /{id}/handoff         POST /{id}/handoff
POST /{id}/handoff/mensaje  POST /{id}/handoff/push    GET  /{id}/intencion
POST /comparar              POST /lead-contacto        GET  /notificaciones
GET  /conversaciones        POST /notificaciones/leidas
```

La costura ya existe: `_exigir_autoridad(request, session_id, user)` en `app/routers/chat.py`.

**Sobre la campana/bandeja:** no basta con añadir una dependencia de FastAPI. El problema está
en la consulta —`WHERE (user…) OR (destinatario_session = :s)`—: la rama de `session_id` solo
puede ejecutarse tras validar la capability **de ese mismo hilo**, y un autenticado no debe
obtener acceso adicional por aportar un `session_id`.

> **Nota de secuencia:** el frontend ya manda `X-Session-Resume` en las 9 llamadas. Cerrar los
> 11 endpoints es, por tanto, activar una comprobación cuyo transporte ya está en producción
> de la rama — no un cambio de contrato con el cliente.

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
| Comentarios fuera, con parser de verdad | `frontend/src/codigoDesnudo.js` |
| No-fuga del secreto | `frontend/src/noLeak.test.js` |
| Política y matriz de origen | `docs/agentic_decision_system/12_AUTH_READ_GATE_*.md` |

**Los tests transformados no se borran.** Cada uno documenta qué congelaba en `.0` y qué
política autorizó el cambio — son el mecanismo que demuestra que cambió **solo** lo autorizado.
