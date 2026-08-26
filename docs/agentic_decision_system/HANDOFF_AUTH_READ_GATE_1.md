# AUTH-READ-GATE.1 — HANDOFF

```
BRANCH                 feat/auth-read-gate-enforcement
BASE DE LA UNIDAD      8a8968da412cd3e1dc6efcb7609ed433fa8b2905
HEAD DE CONTINUACIÓN   009bc759d37c97183b49106f620362bc1ba6b7b9

ESTADO                 IN PROGRESS
SUITE                  1 557 exit 0
INVENTARIO 18 ENDPOINTS PASS
```

---

## ⛔ LA RAMA NO ES DESPLEGABLE EN ESTE COMMIT

`POST /chat` ya exige una sesión creada por bootstrap y autoridad válida, pero el frontend
actual todavía:

- no llama a `POST /sessions/bootstrap`
- no conserva el `resume_secret`
- no envía `X-Session-Resume`
- no hace reset seguro de las sesiones legacy

**Backend nuevo + frontend viejo rompe el chat anónimo.** Es deliberado mientras se construye
la rebanada, y **no es un estado aceptable para PR ni para merge**.

> **No confundir "suite verde" con "cutover completo".** `009bc75` demuestra que la nueva
> política del backend es consistente consigo misma. **Todavía no demuestra que el producto
> pueda usarla.**

---

## COMPLETADO

```
[✓] 1   migración 027
[✓] 2   capability primitives
[✓] 3   bootstrap atómico (núcleo)
[✓] 4   costura central de autoridad
[✓]     claim seguro contra TOCTOU / mal uso
[✓] 5a  bootstrap HTTP
[✓] 5d  enforcement en POST /chat
[✓] 7   tighten de share / archive / rename
```

## PENDIENTE

```
[ ] 5b  frontend: bootstrap + almacenamiento de capability + header
[ ] 5c  QR: nuevo / revisita / reset legacy
[ ] 6   proteger los 11 endpoints restantes
[ ] 10  tests integrales + reporte 13
```

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

## SIGUIENTE ORDEN

```
1.  abstracción de almacenamiento de capability en el frontend
2.  bootstrap desde el frontend
3.  QR: nuevo / revisita / legacy
4.  hacer pasar el chat end-to-end
5.  proteger los 11 endpoints restantes con la MISMA costura
6.  revisar campana/bandeja — especialmente el `OR user/session`
7.  tests de integración
8.  frontend build/tests
9.  reporte 13
10. revisión completa del diff antes de PR
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
| Política y matriz de origen | `docs/agentic_decision_system/12_AUTH_READ_GATE_*.md` |

**Los tests transformados no se borran.** Cada uno documenta qué congelaba en `.0` y qué
política autorizó el cambio — son el mecanismo que demuestra que cambió **solo** lo autorizado.
