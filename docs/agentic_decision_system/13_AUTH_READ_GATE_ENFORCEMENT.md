# 13 · AUTH-READ-GATE.1 — ENFORCEMENT

> **session_id identifica una conversación; nunca demuestra autoridad sobre ella.**

```
RAMA          feat/auth-read-gate-enforcement
SHA INICIAL   8a8968da412cd3e1dc6efcb7609ed433fa8b2905
SHA FINAL     09bae2883ec6dca05bd7699a309a1808b2cc96a5

backend       1 665 exit 0
frontend         66 exit 0
build         PASS
inventario    18/18 · 0 sin clasificar

DECISIÓN      PASS   (era HOLD; resuelto en §16)
```

> **§16 · HOLD RESOLUTION** es la sección que cierra la decisión. El HOLD estaba justificado:
> ejecutar contra PostgreSQL real destapó **dos defectos que habrían tumbado el producto en el
> primer despliegue**, y ninguno era detectable sin el motor.

---

## 1 · SCOPE

Convertir el `session_id` de credencial de facto en identificador, en los 18 endpoints de
`app/routers/chat.py` donde participa del acceso al estado del hilo.

**Fuera de alcance, y conviene decirlo porque el número "18" puede engañar:** el inventario
cubre `chat.py`. Existen **6 endpoints session-scoped en `app/routers/assets.py`**
(`/crm/chat`, `/crm/thread` ×2, `/metricas/lift`, `/{activo_id}/leads/{session_id}/conversacion`,
`/{activo_id}/leads/{session_id}/responder`). Se auditaron en esta revisión: **todos exigen
`get_current_user` y, los dos que reciben `session_id`, además `_assert_owner(activo_id, user)`
y `_assert_sesion_del_activo(session_id, activo_id)`. Modelo de autoridad distinto —dueño del
inmueble, no de la conversación— y correcto.** No son un agujero abierto; son otra frontera.

---

## 2 · MODELO MENTAL

```
session_id           identificador           no autoriza nada, nunca
sujeto autenticado   autoridad de DUEÑO      claims.sub == chat_sessions.user_id
resume capability    autoridad de POSESIÓN   secreto de 32 bytes, hash en base
public share         capacidad explícita     /shared/{token} + is_public
```

Tres autoridades disjuntas. Un hilo con dueño **no** se abre con capacidad (aceptarlo sería
conservar un segundo acceso bearer en silencio); un hilo sin dueño **solo** se abre con ella.

### Modelo de amenaza

El atacante conoce o adivina un `session_id`. Antes eso bastaba para leer la conversación
entera, escribir en ella, redirigir sus notificaciones push, plantar un contacto, disparar un
handoff real con un corredor y —si el hilo no tenía dueño— **quedárselo** renombrándolo.

Los `session_id` no eran secretos operativos: viajaban en `?s=` de enlaces compartidos, se
componían con un esquema público (`qr-{activo}-{device}`) y el `device_key` se persistía en
servidor en cada llegada.

---

## 3 · INVENTARIO 18/18 — desde el código final

Reconstruido con `_inventario()` sobre `09bae28`, no copiado del handoff.

| # | Método · ruta | Categoría | Autoridad final | Anón | Owner | Muta | Cambió desde `8a8968d` | Test |
|---|---|---|---|---|---|---|---|---|
| 1 | `GET /{sid}/history` | ANON_CAP | `_exigir_autoridad` | sí | sí | no | ninguna → autoridad | `test_autoridad_endpoints` |
| 2 | `GET /{sid}/handoff` | ANON_CAP | `_exigir_autoridad` | sí | sí | no | ninguna → autoridad | idem |
| 3 | `GET /{sid}/intencion` | ANON_CAP | `_exigir_autoridad` | sí | sí | no | ninguna → autoridad | idem |
| 4 | `POST /{sid}/handoff/push` | ANON_CAP | `_exigir_autoridad` | sí | sí | **sí** | ninguna → autoridad | idem |
| 5 | `POST /{sid}/handoff` | ANON_CAP | `_exigir_autoridad` | sí | sí | **sí** | sin puerta → autoridad | idem |
| 6 | `POST /{sid}/handoff/mensaje` | ANON_CAP | `_exigir_autoridad` | sí | sí | **sí** | sin puerta → autoridad | idem |
| 7 | `POST /comparar` | ANON_CAP | `_exigir_autoridad` | sí | sí | no | ninguna → autoridad | idem |
| 8 | `POST /lead-contacto` | ANON_CAP | `_exigir_autoridad` | sí | sí | **sí** | ninguna → autoridad | idem |
| 9 | `GET /notificaciones` | HÍBRIDO | `_alcances_autorizados` | sí | sí | no | `OR` sin autorizar → B.1 | `test_B1_*` |
| 10 | `GET /conversaciones` | HÍBRIDO | `_alcances_autorizados` | sí | sí | no | `OR` sin autorizar → B.1 | `test_B1_*` |
| 11 | `POST /notificaciones/leidas` | HÍBRIDO | `_alcances_autorizados` | sí | sí | **sí** | `OR` sin autorizar → B.1 | `test_B1_*` |
| 12 | `POST /` (chat) | ANON_CAP | `_exigir_autoridad` + claim | sí | sí | **sí** | apropiación → autoridad | `test_caracterizacion_acceso_sesion` |
| 13 | `PATCH /sessions/{sid}` | OWNER | `get_current_user` + `WHERE user_id` | no | sí | **sí** | **reclamaba el hilo** (§7) | `test_REGRESION_las_tres_mutaciones_exigen_ser_dueno` |
| 14 | `DELETE /sessions/{sid}` | OWNER | `get_current_user` + `WHERE user_id` | no | sí | **sí** | `OR user_id IS NULL` retirado | idem |
| 15 | `POST /sessions/{sid}/share` | OWNER | `get_current_user` + `WHERE user_id` | no | sí | **sí** | ya no reclama al publicar | `test_REGRESION_compartir_ya_no_reclama_el_hilo` |
| 16 | `DELETE /sessions/{sid}/share` | OWNER | `get_current_user` + `WHERE user_id` | no | sí | **sí** | acotado a dueño | idem |
| 17 | `GET /sessions` | OWNER | `WHERE cs.user_id = :uid` | no | sí | no | sin cambios | `test_el_usuario_anonimo_no_tiene_lista` |
| 18 | `GET /shared/{token}` | PUBLIC_SHARE | `share_token` + `is_public` | público | — | no | **sin cambios (congelado)** | `test_el_hilo_compartido_SI_exige_una_condicion` |

Suma exacta: **18**. `POST /sessions/bootstrap` no está en la lista porque **crea**, no accede
a estado existente.

---

## 4 · CAMBIOS DE 200 → DENEGADO — número exacto

**17 comportamientos endpoint-nivel** que antes tenían éxito y ahora se deniegan, más **1
pérdida de compatibilidad deliberada**.

| Clase | N.º | Qué era válido antes | Reemplazo legítimo |
|---|---|---|---|
| `EXPECTED_POLICY_CHANGE` · lectura/escritura solo con `session_id` | **8** (#1-8) | conocer el id bastaba | `X-Session-Resume` de ESE hilo, o Bearer del dueño |
| `EXPECTED_POLICY_CHANGE` · rama de sesión sin autorizar | **3** (#9-11) | `OR destinatario_session = :s` sin comprobar | la rama solo se construye tras autoridad |
| `EXPECTED_POLICY_CHANGE` · escritura y apropiación en el turno | **1** (#12) | `COALESCE` asignaba dueño al primero que enviara el id | claim tras capacidad válida |
| `EXPECTED_POLICY_CHANGE` · mutaciones de dueño | **4** (#13-16) | un autenticado renombraba/archivaba/publicaba un hilo anónimo ajeno | ser el dueño |
| `EXPECTED_POLICY_CHANGE` · contrato | **1** | `POST /chat` sin `session_id` → el servidor inventaba uno (`default_factory=uuid4`) → 200 | `POST /sessions/bootstrap` primero; ahora 422 |
| **Pérdida de compatibilidad** | **1 clase** | sesiones anónimas anteriores al gate | no recuperable — el frontend abre una nueva |
| `UNCHANGED_INVARIANT` | — | `/shared/{token}`, prefijo `qr-{activo}-`, `/a/{activo}` físico, reanudación por navegador | sin cambios |
| `REGRESSION` | **0** | — | — |

**La pérdida de compatibilidad no se puede arreglar y conviene entender por qué:** los hilos
anónimos previos nacieron sin fila autoritativa, así que no existe forma criptográficamente
honesta de emitirles una capacidad hoy — cualquiera que conociera el id la reclamaría.

---

## 5 · CICLO DE VIDA DEL SECRETO — código y prueba por flecha

| Flecha | Código | Test |
|---|---|---|
| id aleatorio del servidor | `_nuevo_session_id` | `test_el_cliente_ya_no_elige_el_identificador` |
| secreto crudo (32 B) | `generar_secreto` | `test_el_secreto_tiene_entropia_suficiente_y_no_se_repite` |
| SHA-256 persistido, crudo jamás | `_ejecutar_creacion` | `test_lo_que_se_guarda_es_el_hash_y_no_el_secreto` |
| se entrega UNA vez | `BootstrapResponse` | `test_el_bootstrap_anonimo_emite_secreto_y_guarda_solo_el_hash` |
| custodia con espacio de nombres | `resumeCapability.js` | `resumeCapability.test.js` · aislamiento |
| transporte en cabecera, nunca URL | `apiHeadersSesion` | `noLeak.test.js` (barrido de `src/`) |
| comparación en tiempo constante | `_coincide` → `hmac.compare_digest` | `test_la_comparacion_es_en_tiempo_constante` |
| capacidad → `ANONYMOUS_CAPABILITY` | `_decidir` | `test_el_anonimo_con_la_capacidad_correcta_entra` |
| claim atómico ligado a la capacidad | `_ejecutar_claim` | `test_el_claim_liga_el_UPDATE_a_la_capacidad_que_lo_autorizo` |
| claim que no reclama → falla ruidosa | `len(filas) != 1` | `test_un_claim_que_no_reclama_nada_FALLA_en_vez_de_callar` |
| revocación en la MISMA sentencia | `_ejecutar_claim` | `test_el_claim_asigna_dueno_y_revoca_en_la_MISMA_sentencia` |
| borrado local **tras** el éxito | `limpiarCapacidadTrasClaim` | `sessionFlow.test.js` caso 6 |
| rechazo → descartar, sin reintento | `descartarCapacidadRechazada` | `sessionFlow.test.js` caso 7 |
| dueño solo por identidad coincidente | `_decidir` | `test_aislamiento_cross_owner.py` |
| share público, carril aparte | `get_shared` | `test_el_hilo_compartido_SI_exige_una_condicion` |

**Ninguna flecha queda solo documentada.** Todas tienen código y test.

---

## 6 · CORRECCIÓN FORMAL A `AUTH-READ-GATE.0` — `update_session`

Esto no es un detalle menor y se registra como corrección explícita del informe anterior.

**Qué se creyó en `.0`:** `update_session` (renombrar / fijar) se clasificó como `owner-auth`.
La comprobación era `get_current_user` presente y `WHERE … AND user_id = :uid` en los `UPDATE`.

**Qué mostró `.1`:** la clasificación era **incompleta y el endpoint era explotable**. Antes de
los `UPDATE` estrictos había un

```sql
INSERT INTO chat_sessions (…) VALUES (…)
ON CONFLICT (session_id) DO UPDATE SET user_id = COALESCE(chat_sessions.user_id, :uid)
```

Ese `COALESCE` asignaba dueño a cualquier hilo que no lo tuviera. Y era peor de lo que parece:
**tras esa sentencia el hilo ya era del llamante**, de modo que el `WHERE … AND user_id = :uid`
de abajo pasaba a cumplirse. **Renombrar una conversación anónima ajena equivalía a quedársela.**

**Por qué el test de `.0` no lo cazó:** solo miraba el `WHERE` de los `UPDATE`. La vía de
apropiación vivía en la sentencia **anterior**. Es el fallo de método de esta unidad: se
verificó la cláusula que se esperaba encontrar, no el camino completo.

**Qué cambió:** la vía está eliminada. `update_session` no contiene ningún `INSERT` ni
`COALESCE`; solo dos `UPDATE` con `WHERE session_id = :sid AND user_id = :uid`.

**Qué lo demuestra:** verificación **estructural** sobre el AST —no búsqueda de texto, porque
los comentarios siguen nombrando `_tag_session_owner` al explicar qué se retiró:

```
ast.unparse(chat.py)  →  _tag_session_owner              0 apariciones
                         COALESCE(chat_sessions.user_id)  0 apariciones
                         INSERT INTO chat_sessions        0 literales
update_session         →  INSERT: False · COALESCE: False · user_id = :uid ×2
```

Tests: `test_REGRESION_ya_no_existe_via_de_apropiacion_por_identificador`,
`test_REGRESION_las_tres_mutaciones_exigen_ser_dueno`,
`test_REGRESION_ya_no_hay_etiquetado_silencioso_de_dueno`.

---

## 7 · B.1 · ALCANCES HÍBRIDOS

La sesión significa dos cosas distintas según el endpoint, y eso cambia qué debe pasar cuando
no se puede probar.

| | cuenta | session_id | Resultado |
|---|---|---|---|
| 1 | no | no | vacío, sin consultar |
| 2 | no | autorizada | alcance sesión |
| 3 | no | **no autorizada** | **404** |
| 4 | sí | no | alcance cuenta |
| 5 | sí | autorizada | cuenta ∪ sesión |
| 6 | sí | **no autorizada** | **solo cuenta · NO 404** |

El caso 6 es disponibilidad, no permisos: los datos de la sesión no demostrada **no se
entregan** en ninguna de las seis filas. La rama de sesión no se **construye** sin autoridad,
así que degradar solo puede devolver menos, nunca más.

La tolerancia es exclusiva de los tres híbridos;
`test_B1_la_tolerancia_NO_se_extiende_a_los_ocho_directos` caza a quien la generalice.

---

## 8 · EVIDENCIA CROSS-OWNER REAL

El primer intento fue un falso positivo: el doble de HTTP del frontend decidía localmente
(`existeYEsDeOtro = new Set([...])`), así que probaba la reacción del cliente y **nada** del
backend. Corregido en `8b67900`, con el rótulo del test arreglado.

La evidencia válida (`tests/test_aislamiento_cross_owner.py`): la sesión de U2 la crea
`crear_sesion()` —código de producto, el `user_id` lo escribe su propio `INSERT`— y la
denegación la produce `_exigir_autoridad` real. La tabla **almacena filas; no autoriza**, y eso
se verifica: la lectura emitida lleva un único parámetro (`sid`), ninguna identidad llega a la
base, y la consulta es **idéntica** para U1 y para U2. Misma fila, misma pregunta, resultados
opuestos.

### Mutaciones — la prueba de que los tests pueden fallar

```
_decidir: dueno = None                        → caen 2, pero NO el del caso 5 (no aísla)
_decidir: if user is not None → OWNER         → caen 4, incluido el caso 5      ✔
_alcances: rama de sesión sin autorizar       → caen 12
_alcances: tolerancia extendida al anónimo    → caen 13
GET /history sin la puerta                    → caen 7
la rama se añade pese a no estar probada      → caen 9
```

Los ficheros productivos quedaron restaurados y verificados tras cada mutación.

---

## 9 · MIGRACIÓN 027 — `SQL REVIEWED`, **no** `SQL EXECUTED`

| Propiedad | Veredicto |
|---|---|
| Idempotencia | ✅ `ADD COLUMN IF NOT EXISTS` ×4, `CREATE INDEX IF NOT EXISTS` |
| Correr dos veces | ✅ sin efecto |
| Nullable / defaults | ✅ las 3 columnas de capacidad son nullable |
| `NOT NULL DEFAULT false` | ⚠️ metadata-only **solo en PG ≥ 11**. Supabase cumple; queda anotado |
| Filas legacy con dueño | ✅ `user_id` presente → OWNER, sin capacidad |
| Filas legacy anónimas | ✅ hash `NULL` → denegado (pérdida deliberada, §4) |
| Secreto crudo | ✅ nunca se guarda; solo SHA-256 |
| Constraints que rompan al desplegar | ✅ ninguna: sin `UNIQUE`, sin FK, sin `NOT NULL` sobre datos existentes |
| Rollback | ✅ documentado, con el orden correcto (código primero) |

### ⚠️ Hallazgo — el índice no hace lo que dice

```sql
CREATE INDEX IF NOT EXISTS ix_chat_sessions_resume_vivo
    ON chat_sessions (session_id)
    WHERE resume_token_hash IS NOT NULL AND resume_revoked_at IS NULL;
```

El comentario lo justifica como *"búsqueda por hash en cada petición anónima: sin índice sería
un scan del catálogo"*. **Es falso en dos sentidos.** El índice es sobre `session_id`, no sobre
el hash; y la única consulta de autoridad es `WHERE session_id = :sid`, donde `session_id` ya
es **PRIMARY KEY**. La comparación del hash ocurre en Python (`_coincide`), no en SQL.

El índice es inofensivo pero **no aporta nada**, y su comentario induce a error a quien lo lea.
No se toca en esta unidad (no es un blocker de seguridad); queda para el siguiente que abra el
fichero.

---

## 10 · POSTGRES — `NOT VERIFIED`

Se reinvestigó en esta revisión, sin escribir en producción:

```
docker daemon        NO CORRE  (npipe dockerDesktopLinuxEngine no existe)
servicio Postgres    ninguno en Windows
psql / pg_ctl        no están en PATH
puerto 5432          cerrado
supabase CLI         no instalado
testcontainers       no instalado
pytest-postgresql    no instalado
DATABASE_URL         producción (Supabase) — descartado de plano
```

**No hay PostgreSQL seguro y no productivo disponible. No se simula que lo haya.**

```
POSTGRES INTEGRATION = NOT VERIFIED
```

### ⚠️ Y no hay runner de migraciones

`render.yaml` y `Dockerfile` **no aplican migraciones**. No existe un paso automático que
garantice que `027` corra antes de que el código nuevo reciba tráfico.

**Consecuencia si se despliega el código sin la migración:** `_fila_de_sesion` hace
`SELECT … resume_token_hash, resume_revoked_at FROM chat_sessions`. Sin esas columnas la
consulta **falla**, y como `_exigir_autoridad` corre en **cada** turno de `POST /chat`, el chat
deja de funcionar **para todo el mundo, autenticados incluidos**. No es una degradación parcial:
es una caída total del producto.

Esa sentencia exacta **nunca se ha ejecutado contra Postgres**.

---

## 11 · DEUDA OBSERVADA — no se arregla aquí

**A · `except Exception` amplios.** `estado_handoff` devuelve su `vacio` y `lead_contacto`
convierte en 500 **cualquier** excepción. Pueden ocultar fallos de base, de serialización o de
tipos, y presentarlos como "no hay handoff" o como un 500 genérico. **No saltan el gate**: la
autoridad se ejecuta *antes* del `try` en ambos. Se detectó porque el centinela de los tests
tuvo que heredar de `BaseException` para no quedar atrapado — si no, el test habría visto "no
hubo efecto" cuando sí lo hubo. Recomendación posterior: acotar a las excepciones esperadas.

**B · `pedirCorredor` sin guarda de `sessionId`.** Depende de que su CTA solo aparezca con
mensajes en pantalla, lo que implica sesión resuelta. **Es un supuesto de producto, no una
garantía estructural.** Si ese botón cambia de sitio, la llamada saldría con `session_id` nulo.
No es un fallo de autoridad —un `null` no autoriza nada— sino de robustez.

**C · Índice muerto en 027** (§9).

Ninguna de las tres bloquea el gate.

---

## 12 · REGRESIÓN DE PRODUCTO — estado final

```
QR nuevo                          PASS   sessionFlow.test.js · appCutover.test.js
QR revisita                       PASS   idem
legacy anónimo reset              PASS   idem (no emite ninguna petición)
authenticated legacy OWNER        PASS   idem
cross-owner                       PASS   test_aislamiento_cross_owner.py (backend real)
anon → login → claim              PASS   sessionFlow + test_sesion_autoridad (claim server-side)
capacidad rechazada               PASS   sessionFlow.test.js
aislamiento entre varios QR       PASS   resumeCapability.test.js (claves con espacio de nombres)
/a/{activo} físico                PASS   test_el_QR_codifica_el_INMUEBLE_no_una_conversacion
prefijo qr-{activo}-              PASS   test_el_bootstrap_conserva_el_prefijo_del_QR
Campana · fallback a cuenta (B.1) PASS   test_B1_autenticado_con_sesion_AJENA_recibe_solo_su_cuenta
Campana · capacidad anónima       PASS   test_B1_anonimo_con_SU_capacidad_recibe_el_alcance_de_sesion
/shared/{token}                   PASS   sin cambios · test congelado
no-leak                           PASS   noLeak.test.js barre todo src/
```

---

## 13 · REQUISITOS DE DESPLIEGUE

**Orden obligatorio, y no hay automatismo que lo garantice:**

1. Aplicar `migrations/027_session_resume_capability.sql` **antes** de desplegar el código.
2. Verificar que devuelve `columnas_creadas = 4`.
3. Desplegar backend y frontend **juntos**: el backend exige `X-Session-Resume` y un frontend
   viejo no lo envía.
4. Rollback: **código primero, esquema después.** Revertir solo el esquema con el gate
   desplegado deja el carril anónimo inaccesible.

---

## 14 · DECISIÓN

```
HOLD
```

**No es FAIL.** La revisión adversarial de los 18 endpoints —más los 6 de `assets.py` que el
inventario no cubría— no encontró bypass, autoridad duplicada, fallback de `session_id` a
secas, `device_key` usado como autoridad, secreto en URL/log/base, claim no atómico, capacidad
sin revocar, ni camino donde el efecto ocurra antes de la puerta. El aislamiento entre dueños
está demostrado con estado real y código real, y las seis mutaciones confirman que los tests
pueden fallar. `REGRESSION = 0`.

**No es PASS, y por una razón concreta, no por prudencia genérica.** La sentencia que decide
cada petición del producto —`SELECT … resume_token_hash, resume_revoked_at FROM chat_sessions`—
**nunca se ha ejecutado contra PostgreSQL**, y **no existe runner que garantice que la migración
027 corra antes que el código**. Si se despliega en el orden equivocado, el fallo no es parcial:
`POST /chat` cae para todos los usuarios, autenticados incluidos. Declarar PASS sería afirmar
una confianza sobre el motor y sobre la secuencia de despliegue que esta unidad no ha producido.

La lógica de autoridad está probada. Su ejecución contra un motor real, no.

### Qué falta exactamente para convertir el HOLD en PASS

1. **Un PostgreSQL no productivo** (arrancar el demonio de Docker y usar el `docker-compose.yml`
   del repo, o instalar `testcontainers`) y ejecutar contra él, como mínimo: migración 027 ·
   bootstrap anónimo · bootstrap OWNER · lectura OWNER · cross-owner U1/U2 · capacidad propia ·
   capacidad ajena · claim anon→OWNER · revocación posterior · las consultas híbridas de
   `_alcances_autorizados` · el `UPDATE` de notificaciones acotado por alcance.
2. **Un paso de migración en el despliegue**, o una comprobación de arranque que falle rápido y
   con un mensaje claro si faltan las columnas de 027.

Ninguna de las dos exige rediseño. Son evidencia y operación, no código de producto.

---

## 15 · LIMITACIONES CONOCIDAS

- **Postgres no ejecutado** (§10) — la limitación material que motiva el HOLD.
- **Sesiones anónimas previas al gate no recuperables** (§4) — deliberado e irreparable.
- **Sin caducidad de la capacidad.** `revoked_at` existe y el claim revoca, pero no hay TTL: no
  se sabe cuánto dura de verdad una conversación de QR y un TTL inventado expulsaría gente en
  mitad de su recorrido.
- **La capacidad es un portador.** Quien la tenga entra, sea quien sea. Vive en `localStorage`,
  o sea por navegador. Esto **no** rehabilita `thread_id` como raíz del Buyer (E3.1a): la raíz
  sigue siendo `claims.sub`.
- **El inventario es de `chat.py`.** Los 6 endpoints session-scoped de `assets.py` se auditaron
  y están correctos, pero no están bajo esta costura.
- **`codigoDesnudo.js` vive en `frontend/src/`** y depende de `vite`. No es alcanzable desde el
  entry, así que no entra al bundle (verificado: el build pasa), pero es infraestructura de test
  en un directorio de producción.

---

# 16 · HOLD RESOLUTION

```
SHA de entrada   a02f69090c9b2e8a2d4aa8e329972bdf53b459a5
HOLD-1           CERRADO   Postgres real ejecutado
HOLD-2           CERRADO   readiness de arranque + migración explícita

DECISIÓN NUEVA   PASS
```

**Y el HOLD estaba justificado: el motor real encontró dos defectos que habrían tumbado el
producto en el primer despliegue.** Ninguno era detectable sin él.

---

## 16.1 · Producción, inspección read-only

```
motor            PostgreSQL 17.6 (Supabase, aws-1-us-west-2)
columnas de 027  0/4
índice           AUSENTE
PROD_SCHEMA_027  NOT_APPLIED
```

Solo `information_schema` y `pg_indexes`. Cero DDL, cero DML.

Que la 027 no esté aplicada en ningún entorno permitió corregirla sin reescribir historia, y
confirma que HOLD-2 era un riesgo vivo y no teórico.

---

## 16.2 · 🔴 DEFECTO 1 — el bootstrap habría fallado **siempre**

`_ejecutar_creacion` insertaba con:

```sql
VALUES (:sid, :uid, :h, CASE WHEN :h IS NULL THEN NULL ELSE now() END, true)
```

Dentro de `CASE WHEN … IS NULL` **Postgres no tiene columna de la que deducir el tipo del
parámetro**. Con `asyncpg`, que usa el protocolo extendido, la sentencia falla **al
prepararse**:

```
asyncpg.exceptions.AmbiguousParameterError:
could not determine data type of parameter $3
```

**Alcance del fallo: total.** No afectaba a un caso raro — reventaba `POST /sessions/bootstrap`
para **las sesiones anónimas y las autenticadas por igual**. Como el frontend de 5c ya no
fabrica identificadores y **toda** conversación nace del bootstrap, nadie habría podido abrir
un chat. El gate entero habría caído en el primer minuto de producción.

**Por qué ningún test lo cazó:** los 102 tests de autoridad usan una tabla en memoria que
almacena filas; ninguno parsea SQL, así que ninguno podía descubrir que la sentencia era
inválida para el motor. Ahí está exactamente el límite que el HOLD señalaba.

**Y el repo ya conocía este error.** Los endpoints de la campana llevan desde hace tiempo un
comentario que lo explica: *"Los CAST no son adorno: con el parámetro en NULL, Postgres no
puede deducir su tipo … revienta con AmbiguousParameterError — el endpoint devolvía 500 y la
campana salía vacía sin decir nada."* El mismo fallo se repitió en el bootstrap.

**Corregido:** `CAST(:sid AS text)`, `CAST(:uid AS uuid)`, `CAST(:h AS text)`, incluido dentro
del `CASE`. Verificado contra el motor.

**Barrido posterior:** se buscó el mismo patrón (`:param IS [NOT] NULL` sin `CAST`) en todos
los literales SQL de `app/`. **Cero apariciones restantes.**

---

## 16.3 · 🔴 DEFECTO 2 — el aplicador de migraciones no sabía aplicar la migración

La primera versión de `aplicar_migracion` mandaba el fichero entero por
`session.execute(text(sql))`. `asyncpg` prepara cada sentencia, y **una sentencia preparada es
una sentencia**:

```
cannot insert multiple commands into a prepared statement
```

Es decir: el mecanismo escrito para cerrar HOLD-2 habría fallado justo el día que se necesitara.

**Corregido** bajando al protocolo simple del driver (`driver_connection.execute`), que sí
acepta un script. **No** se trocea por `;` — un `;` dentro de un literal (los `COMMENT ON … IS
'…'` de la 027 son candidatos naturales) partiría la sentencia por la mitad; es la misma trampa
de "texto vs. estructura" de toda esta unidad.

Los tests de integración aplican la 027 **con el aplicador de producción**, no con una copia:
si el aplicador no sabe ejecutar el fichero, los tests fallan.

---

## 16.4 · Motor de pruebas

```
contenedor   contexto_db · postgis/postgis:15-3.3 (del docker-compose.yml del repo)
motor        PostgreSQL 15.4
base         auth_gate_test — creada vacía y aislada; NO es contexto_v2 (la de desarrollo)
```

`TEST_DATABASE_URL` es obligatoria y **no** cae por defecto a `settings.database_url`: estos
tests crean sesiones, reclaman hilos y revocan capacidades. La fixture además aborta si la URL
contiene `supabase.com` o `pooler`. Doble candado contra escribir en producción.

**Diferencia de versión, dicha claramente:** las pruebas corren en **PG 15.4** y producción es
**PG 17.6**. Para lo que la 027 y la autoridad usan —`ADD COLUMN IF NOT EXISTS`, `NOT NULL
DEFAULT`, `ON CONFLICT … DO NOTHING RETURNING`, `CAST`, `now()`, inferencia de tipos de
parámetro— el comportamiento es estable entre 15 y 17. No es el mismo motor y no se afirma que
lo sea.

---

## 16.5 · Lo ejecutado contra el motor real — 17 tests

```
MIGRACIÓN 027
 ✓ primera ejecución PASS, cuatro columnas con tipo y nulabilidad correctos
 ✓ creada_por_servidor: boolean NOT NULL DEFAULT false
 ✓ SEGUNDA ejecución PASS — idempotencia real, no declarada
 ✓ filas legacy sobreviven; el DEFAULT las rellena sin reescribir la tabla
 ✓ legacy con dueño → OWNER; legacy anónima → denegada (pérdida deliberada)

AUTORIDAD (app/sesion_autoridad.py real, sin db= inyectado)
 ✓ bootstrap anónimo: user_id NULL, hash guardado, resume_issued_at sellado,
   creada_por_servidor=true, y el secreto crudo NO aparece en NINGUNA columna de la fila
 ✓ bootstrap autenticado: user_id real, sin capacidad emitida
 ✓ el prefijo qr-{activo}- sobrevive y el LIKE de assets.py lo encuentra
 ✓ cross-owner: U2 entra, U1 no — ni con un secreto inventado
 ✓ capacidad propia → ANONYMOUS_CAPABILITY; ajena, ninguna, o id inexistente → denegado
 ✓ claim: user_id asignado y resume_revoked_at sellado, VERIFICADO leyendo la fila
 ✓ tras el claim la capacidad vieja no sirve ni al anónimo ni a otro autenticado;
   el nuevo dueño entra por identidad
 ✓ claim sobre hilo ajeno: rowcount 0 → levanta, y la fila de U2 queda intacta
 ✓ ON CONFLICT con id existente: NO se re-emite capacidad (el hash original no cambia)

HÍBRIDOS (_alcances_autorizados real, SQL ejecutado)
 ✓ solo cuenta → solo los avisos de U1
 ✓ cuenta ∪ sesión propia autorizada → ambos
 ✓ sesión REAL de U2 → SOLO cuenta; cero filas de U2
 ✓ anónimo sin capacidad → 404
 ✓ marcar leídas con sesión ajena → rowcount 1 (solo el de cuenta);
   los avisos de U2 siguen SIN LEER, verificado leyendo la base después
```

---

## 16.6 · HOLD-2 — mecanismo de despliegue

`app/esquema_requerido.py`:

| | |
|---|---|
| `exigir_esquema()` | comprobación de arranque; levanta `EsquemaIncompleto` si faltan columnas |
| `aplicar_migracion()` | acto **explícito**, nunca automático |
| `python -m app.esquema_requerido [--aplicar]` | uso operativo |

La comprobación es **lo primero** del `lifespan`, antes del checkpointer y de los cron
(verificado por AST, no por texto). **No se aplica DDL al arrancar**: con varias réplicas sería
una carrera, y un despliegue fallido dejaría el esquema a medias sin que nadie lo pidiera.

Fallar al arrancar es deliberado. Un proceso que arranca sin las columnas pasa el health check,
Render lo da por bueno, y el error acaba en la cara del usuario. Así el despliegue no progresa
y la versión anterior sigue sirviendo.

**10 tests:** cada una de las cuatro columnas por separado (ninguna es opcional), tabla entera
ausente, el mensaje nombra columna y migración pero **no** filtra conexión ni valores, la
comprobación no contiene ningún verbo de escritura, va la primera en el `lifespan`, y el
arranque no migra.

---

## 16.7 · La migración, corregida antes de aplicarse

Se retiró `ix_chat_sessions_resume_vivo`. Su comentario decía *"búsqueda por hash en cada
petición anónima"* y era falso por partida doble: el índice era sobre `session_id` —ya PRIMARY
KEY, nunca habría un plan mejor— y la única consulta de autoridad no filtra por el hash en
absoluto; la comparación ocurre en Python con `hmac.compare_digest` sobre la fila recuperada.

Un índice sobre el hash tampoco serviría y sería **contraproducente**: indexar el material de
una capacidad facilita confirmarla por sondeo. El fichero documenta ahora por qué **no** hay
índice, en vez de llevar uno decorativo con una justificación inventada.

Legítimo porque `PROD_SCHEMA_027 = NOT_APPLIED`: no se reescribe una migración ya aplicada.

---

## 16.8 · Estado final de las suites

```
integración Postgres     17 exit 0   ← evidencia nueva
readiness de esquema     10 exit 0   ← evidencia nueva
backend sin motor      1 692 exit 0  (17 saltados)
backend CON motor      1 692 exit 0  (0 saltados)
frontend                  66 exit 0
build                     PASS
inventario                18/18 · 0 sin clasificar
```

```
POSTGRES INTEGRATION = VERIFIED   (PG 15.4; producción es 17.6 — §16.4)
MIGRATION 027 = SQL REVIEWED · SQL EXECUTED · IDEMPOTENT
```

---

## 16.9 · DECISIÓN — `PASS`

Los dos bloqueadores están cerrados con evidencia, no con argumentos:

- **HOLD-1** — el SQL de autoridad se ejecutó contra PostgreSQL real y **encontró dos defectos
  que habrían tumbado el producto entero**. Ambos corregidos y verificados.
- **HOLD-2** — existe comprobación de arranque que se niega a servir con el esquema
  incompleto, y un mecanismo explícito de migración con su runbook.

No apareció bypass, regresión ni defecto estructural. Los dos fallos encontrados eran de
**ejecución** (tipos de parámetro y protocolo del driver), no de diseño: el modelo de autoridad
resistió el contacto con el motor sin un solo cambio.

```
AUTH-READ-GATE.1   PASS
RECOMENDACIÓN      OPEN PR
```

**El PR no se abre en esta unidad.**

### Requisito de despliegue, sin el cual el PASS no vale

1. Aplicar `migrations/027_session_resume_capability.sql` en producción **antes** de desplegar.
   `python -m app.esquema_requerido --aplicar`, o el SQL a mano.
2. El arranque lo verifica solo: si falta algo, el despliegue falla en vez de servir roto.
3. Backend y frontend **juntos** — el backend exige `X-Session-Resume` y un frontend viejo no
   lo envía.
4. Rollback: **código primero, esquema después.**

### Lo que sigue sin demostrarse

- Las pruebas corren en **PG 15.4**; producción es **17.6** (§16.4).
- No hay test de carga ni de concurrencia real sobre el claim. La atomicidad está probada por
  `rowcount` contra el motor, no con dos clientes compitiendo.
- Los 6 endpoints session-scoped de `assets.py` (§1) se auditaron por lectura, no por
  ejecución.
