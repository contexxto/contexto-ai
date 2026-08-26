# AUTH-READ-GATE.1 — HANDOFF

```
BRANCH                 feat/auth-read-gate-enforcement
BASE DE LA UNIDAD      8a8968da412cd3e1dc6efcb7609ed433fa8b2905
HEAD DE CONTINUACIÓN   106719b2f3c56b9a6655277b43200a99bbe2bf5c

ESTADO                 IN PROGRESS · 5b COMPLETE · 5c PENDING
SUITE BACKEND          1 557 exit 0
SUITE FRONTEND         35 exit 0
INVENTARIO 18 ENDPOINTS PASS
```

---

## ⛔ LA RAMA SIGUE SIN SER DESPLEGABLE

`POST /chat` exige una sesión creada por bootstrap y autoridad válida. El frontend **ya tiene
todas las piezas** para cumplirlo — pero **`App.jsx` todavía no las usa**:

| | |
|---|---|
| llamar a `POST /sessions/bootstrap` | ✅ existe `bootstrapSession()` |
| conservar el `resume_secret` | ✅ existe `resumeCapability.js` |
| enviar `X-Session-Resume` | ✅ existe `apiHeadersSesion()` |
| decidir reanudar vs. abrir nueva | ✅ existe `sessionRecovery.js` |
| **cablearlo en el componente** | ❌ **5c — pendiente** |

Mientras `App.jsx` siga creando el `session_id` en el cliente y llamando con `apiHeaders()`,
**el chat anónimo está roto contra este backend**. Es deliberado mientras se construye la
rebanada, y **no es un estado aceptable para PR ni para merge**.

> **No confundir "suite verde" con "cutover completo".** `106719b` demuestra que la política
> es consistente y que las piezas del cliente funcionan aisladas. **Todavía no demuestra que
> el producto las use.**

---

## COMPLETADO

```
BACKEND
[✓] 1   migración 027
[✓] 2   capability primitives
[✓] 3   bootstrap atómico (núcleo)
[✓] 4   costura central de autoridad
[✓]     claim seguro contra TOCTOU / mal uso
[✓] 5a  bootstrap HTTP
[✓] 5d  enforcement en POST /chat
[✓] 7   tighten de share / archive / rename

FRONTEND · 5b COMPLETE
[✓] storage session_id → resume_secret  (claves con espacio de nombres)
[✓] Vitest mínimo — sin jsdom ni Testing Library
[✓] job CI `frontend` separado del de pytest
[✓] bootstrapSession()
[✓] apiHeadersSesion(sessionId)
[✓] sessionRecovery.js — el árbol, fuera de React
[✓] no-leak sobre el camino INTEGRADO, no solo el módulo
```

### Validación en `106719b`

```
backend                1 557 exit 0
frontend               35 tests PASS
frontend build         PASS
ficheros nuevos        eslint limpio (exit 0)
lint global            deuda preexistente (39 errores) · NO es gate, a propósito
```

## PENDIENTE

```
[ ] 5c  QR: nuevo / revisita / reset legacy — cablear en App.jsx
[ ] 6   proteger los 11 endpoints restantes
[ ] 10  tests integrales + reporte 13
```

## ESTADO

```
5b COMPLETE
5c PENDING
PRODUCT CUTOVER INCOMPLETE
SECURITY GATE INCOMPLETE
```

**Sigue sin ser desplegable**: el frontend ya sabe crear sesiones y transportar la capacidad,
pero `App.jsx` todavía no usa `sessionRecovery`, así que el carril QR no está cableado.

---

## NOTA DE PROCESO — `8f14303`

Ese commit se creó **con la suite del backend en rojo**, porque encadené el test y el commit
en el mismo comando y no leí el resultado antes. La suite avisaba; el fallo fue de lectura.

`106719b` lo corrige: era un `EXPECTED_POLICY_CHANGE` legítimo —el octavo— que había que
transformar de todos modos.

**No se reescribe la historia.** Está documentado, el commit siguiente lo deja verde, la rama
no tiene PR y el squash del cierre lo convertirá en un solo commit limpio. Un rebase ahora
añadiría riesgo y cero valor.

**Patrón propio a vigilar:** tres veces en esta unidad un test mío ha mirado **texto** donde
debía mirar **estructura** — SQL con espacios de alineación, `COALESCE` dentro de un
comentario, y el JSDoc entre dos funciones. Los tres se arreglaron acotando al AST o al cuerpo
real. Conviene escribirlos así desde el principio.

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

## HALLAZGO NUEVO — corrige a `.0`

**`AUTH-READ-GATE.0` clasificó `update_session` como `owner-auth`, y era incompleto.**

`update_session` (renombrar / fijar) también reclamaba el hilo, mediante un
`INSERT … ON CONFLICT DO UPDATE SET user_id = COALESCE(...)` **previo** a los `UPDATE`
estrictos. Y era peor de lo que parecía: tras esa sentencia el hilo ya era del llamante, así
que el `WHERE … AND user_id = :uid` de abajo pasaba a cumplirse. **Renombrar una conversación
anónima ajena equivalía a quedársela.**

El test de `.0` no lo cazó porque solo miraba el `WHERE` de los `UPDATE`; la vía de claim iba
en la sentencia anterior.

`AUTH-READ-GATE.1` elimina esa vía. **El reporte 13 debe corregir explícitamente a `.0`.**

---

## NOTA — el 503 del bootstrap ante colisión

El comentario en `bootstrap_session` dice que no se reintenta porque *"reintentar es la puerta
por la que se cuela un id elegido"*. **Esa formulación es demasiado amplia y conviene no
perpetuarla.**

Con el diseño actual, un reintento que vuelva a generar el identificador **exclusivamente en
el servidor** seguiría siendo seguro. Lo inseguro sería permitir que el **cliente aporte el
id** en el reintento.

No hay que cambiarlo ahora —un 503 ante una colisión prácticamente imposible (12 bytes
aleatorios) es razonable—, pero **no se debe razonar como si todo retry fuera inseguro**.
Es nota, no bloqueo.

---

## PRÓXIMA SESIÓN — **solo 5c**

Cablear `sessionRecovery` en `App.jsx`. Las piezas ya existen; falta usarlas.

```
1. QR nuevo
   → bootstrap → session_id + capability → history/chat

2. QR revisita
   → mismo session_id → su capability → reanudación

3. legacy anónimo sin capability
   → NO intentar por session_id → limpiar referencia → bootstrap

4. authenticated legacy OWNER
   → intentar contra el backend SIN capability → allow conserva

5. authenticated con sesión real de OTRA cuenta
   → U1 recibe 404 → bootstrap
   ⚠️ usar deliberadamente una sesión EXISTENTE de U2.
      Un id inventado probaría manejo de inexistencia, NO aislamiento entre propietarios.

6. anon → login → claim
   → capability válida → claim → borrar capability local DESPUÉS del éxito
   → las siguientes llamadas van por OWNER

7. capability rechazada o revocada
   → 404 → limpiar el secreto → SIN fallback de session_id a secas
```

### Exigido al cerrar 5c

```
frontend tests PASS          QR new PASS
frontend build PASS          QR revisit PASS
backend full suite PASS      legacy anon reset PASS
no-leak PASS                 authenticated legacy owner PASS
                             cross-owner REAL PASS
                             anon→login claim PASS
                             secret local borrado tras claim PASS
```

Estado esperado al terminar:

```
PRODUCT CUTOVER COMPLETE
SECURITY GATE INCOMPLETE
```

**No tocar todavía los 11 endpoints. No abrir PR. No declarar AUTH-READ-GATE.1 PASS.**

---

## ORDEN COMPLETO RESTANTE

```
5c  QR: nuevo / revisita / legacy  ← próxima sesión, sola
6   los 11 endpoints con la MISMA costura
    · campana/bandeja: reescribir el `OR user/session`, no solo añadir autorización
7   tests de integración
8   reporte 13 — debe corregir formalmente a `.0` sobre `update_session`
9   revisión completa del diff productivo
10  PR
```

**Sobre el punto 6:** no basta con añadir una dependencia de FastAPI. El problema está en la
consulta —`WHERE (user…) OR (destinatario_session = :s)`—: la rama de `session_id` solo puede
ejecutarse tras validar la capability **de ese mismo hilo**, y un autenticado no debe obtener
acceso adicional por aportar un `session_id`.

**Sobre el punto 5:** los 11 endpoints son
`GET /{id}/history` · `GET /{id}/handoff` · `POST /{id}/handoff` ·
`POST /{id}/handoff/mensaje` · `POST /{id}/handoff/push` · `GET /{id}/intencion` ·
`POST /comparar` · `POST /lead-contacto` · `GET /notificaciones` · `GET /conversaciones` ·
`POST /notificaciones/leidas`.

La costura ya existe: `_exigir_autoridad(request, session_id, user)` en `app/routers/chat.py`.

---

## NO HACER

```
no crear otra rama
no rebasear
no abrir PR todavía
no añadir fallback de session_id-only
no restaurar _tag_session_owner
no emitir capability para una sesión existente
no usar device_key
no poner el secret en query params, logs ni mensajes de error
```

---

## Dónde está cada cosa

| Qué | Dónde |
|---|---|
| Esquema | `migrations/027_session_resume_capability.sql` |
| Primitivas + costura + bootstrap núcleo | `app/sesion_autoridad.py` |
| Bootstrap HTTP + `_exigir_autoridad` + enforcement | `app/routers/chat.py` |
| Tests de la costura | `tests/test_sesion_autoridad.py` (29) |
| Oráculo de `.0`, con 7 tests ya transformados | `tests/test_caracterizacion_acceso_sesion.py` |
| Oráculo de E3.1a, con 2 transformados | `tests/test_caracterizacion_identidad_buyer.py` |
| Custodia de la capacidad (cliente) | `frontend/src/resumeCapability.js` (+ test) |
| Bootstrap y transporte | `frontend/src/api.js` |
| Árbol de recuperación | `frontend/src/sessionRecovery.js` (+ test) |
| No-fuga del secreto | `frontend/src/noLeak.test.js` |
| Política y matriz de origen | `docs/agentic_decision_system/12_AUTH_READ_GATE_*.md` |

**Los tests transformados no se borran.** Cada uno documenta qué congelaba en `.0` y qué
política autorizó el cambio — son el mecanismo que demuestra que cambió **solo** lo autorizado.
