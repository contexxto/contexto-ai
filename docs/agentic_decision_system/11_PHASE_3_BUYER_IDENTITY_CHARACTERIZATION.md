# E3.1a — Buyer Identity Characterization

| | |
|---|---|
| **Baseline** | `d298eb5310961e783b0c86a3d84ee98b93a05623` |
| **Rama** | `feat/f3-buyer-identity-characterization` |
| **Suite** | **1 498 `exit 0`** (1 469 + 29) |
| **Código productivo tocado** | **0** (`app/`, `frontend/`, `migrations/` sin cambios) |

Niveles: **[VERIFICADO]** comprobado con herramienta · **[OBSERVADO]** leído en el fuente y
congelado con test · **[INFERIDO]** deducido sin ejecutar · **[HIPÓTESIS]** · **[DESCONOCIDO]**.

---

## 1. EXECUTIVE FINDING

**Existe una identidad de cuenta fuerte para autenticados. No existe identidad de persona
para anónimos. Y `thread_id` no puede ser raíz del Buyer — no por inestabilidad, sino porque
conocerlo otorga acceso.**

Tres hechos gobiernan todo lo demás:

1. **[VERIFICADO]** `CurrentUser.user_id = claims["sub"]` — el sujeto autenticado, o sea
   `auth.users.id`. `profiles.user_id` es su **proyección local 1:1** (PK con FK a
   `auth.users` y `ON DELETE CASCADE`), no la identidad misma. Contexto no posee esa
   identidad: la posee Supabase.
2. **[VERIFICADO]** `GET /{session_id}/history` **no declara ninguna dependencia de
   autenticación**. Conocer el `session_id` basta para leer la conversación completa. El
   `session_id` es un **portador de capacidad**, no una identidad verificada.
3. **[VERIFICADO]** Ya existe un identificador anónimo durable y persistido en servidor
   —`device_key`—, **y el repositorio ya lo clasifica como dato personal** sujeto a supresión.

La arquitectura del Buyer **puede ser asimétrica**, y probablemente deba serlo.

---

## 2. IDENTITY ENTITIES FOUND

| Entidad | Qué identifica | Quién la genera | Dónde vive | Llega al backend | Se persiste |
|---|---|---|---|---|---|
| `claims.sub` → `CurrentUser.user_id` | **persona/cuenta** | Supabase Auth | JWT (memoria del cliente) | ✅ `Authorization: Bearer` | ✅ `profiles.user_id` (PK, FK) |
| `session_id` | **conversación** | frontend (`localStorage`) o backend (`uuid4` si falta) | `localStorage.contexto_ai_session_id` | ✅ cuerpo de la petición | ✅ `chat_sessions.session_id` (PK) + checkpointer |
| `device_key` | **navegador/dispositivo** | frontend (`crypto.randomUUID`) | `localStorage.contexto_ai_device_id` | ✅ campo propio | ✅ `visita.device_key`, `contacto.device_key` |
| `chat_sessions.user_id` | **vínculo** cuenta↔conversación | backend | Postgres | — | ✅ nullable, indexado, sin FK |
| access token | sesión de auth | Supabase | variable de módulo en `api.js` **+ storage propio de supabase-js** | ✅ | ⚠️ ver abajo |

> **CORRECCIÓN.** Una versión anterior de este reporte afirmaba *"el access token vive en
> memoria, no en `localStorage`"*. **Es falso**, y era una afirmación de seguridad. Lo correcto:
>
> - **[VERIFICADO]** Contexto **no** guarda el token por su cuenta: `api.js` lo mantiene en una
>   variable de módulo y no escribe en `localStorage`.
> - **[VERIFICADO]** `supabaseClient.js` instancia `createClient(url, anon)` **sin opciones de
>   auth**.
> - **[CONTRATO DEL PROVEEDOR]** El valor por defecto de `supabase-js` es
>   `persistSession: true`, que **sí persiste la sesión de auth en `localStorage`**.
> - **[VERIFICADO]** `logout()` llama a `signOut({ scope: 'local' })`, que limpia ese storage —
>   pero **no** toca `SESSION_KEY` ni `DEVICE_KEY`, que son claves propias de Contexto.
>
> **No confundir tres cosas distintas:**
> `storage de sesión de Supabase` ≠ `contexto_ai_session_id` ≠ `contexto_ai_device_id`.

---

## 3. AUTHENTICATED FLOW

```
supabase-js  →  JWT (ES256, JWKS)  →  Authorization: Bearer
                                          ↓
                       _decode()  exige claims  exp + sub
                                          ↓
                       user_id = claims["sub"]        ← identidad de CUENTA
                                          ↓
                       profiles (auto-provisión rol 'cliente')
                                          ↓
                       _tag_session_owner(session_id, user)
                                          ↓
                       chat_sessions.user_id = COALESCE(existente, nuevo)
```

**[VERIFICADO]** El token se valida contra las llaves **públicas** de Supabase; el backend no
maneja secretos. Rechaza tokens sin `sub`.

**Estabilidad, con el nivel de evidencia exacto:**

- **[VERIFICADO]** Dentro del flujo autenticado que modela este repo, la identidad es la misma:
  el backend siempre la deriva de `claims["sub"]`, nunca la genera.
- **[INFERIDO / contrato del proveedor]** Que la misma cuenta conserve el mismo `sub` entre
  relogin, navegadores y dispositivos. Es el contrato de Supabase y es razonable, pero **no se
  probó end-to-end en esta unidad** — habría exigido un entorno real multi-dispositivo, y no
  hace falta para cerrar E3.1a.
- **[DESCONOCIDO]** Si sobrevive a cambio de email o de proveedor de login.

---

## 4. ANONYMOUS FLOW

**[VERIFICADO] En el backend, un anónimo no tiene identidad de persona.** No hay id de
invitado, ni placeholder: `get_optional_user` devuelve `None`.

**[VERIFICADO]** `GET /sessions` devuelve `{"sessions": []}` para invitados. **No hay
continuidad anónima enumerable del lado del servidor.**

Pero el navegador **sí** conserva continuidad:

- **[OBSERVADO]** `contexto_ai_session_id` en `localStorage` sobrevive recargas y cierres del
  navegador. La conversación del anónimo persiste **en su navegador**.
- **[OBSERVADO]** `contexto_ai_device_id` (UUID) idem. Su propósito declarado es acotado:
  hacer privada la sesión del QR por visitante (`qr-{activo}-{device}`).

### ⚠️ El `device_key` es infraestructura anónima que YA existe — y ya está clasificada

**[VERIFICADO]** No se queda en el cliente:

```
App.jsx  device_key: getDeviceId()   →   visita.device_key      (migración 024)
                                     →   contacto.device_key    (migración 025, alertas.py)
```

Y la migración 024 lo dice con todas las letras:

> *"`device_key` es un identificador en línea: **cuenta como dato personal** aunque no traiga
> nombre, así que una supresión debe alcanzar TAMBIÉN esta tabla."*

**Reutilizarlo como raíz del Buyer no sería una decisión de arquitectura: sería ampliar el
alcance de un dato personal ya declarado como tal, con obligación de supresión asociada.**
E3.1a no la toma. Ver §16.

**[VERIFICADO]** Hoy **no** está ligado a la propiedad de la conversación: no hay columna,
índice ni FK que lo relacione con `chat_sessions`. Vive en analítica y captación.

---

## 5. MULTI-THREAD FLOW

**[VERIFICADO] La relación 1:N usuario→conversaciones existe y es consultable.**

```sql
chat_sessions.session_id  TEXT PRIMARY KEY        -- = thread_id del checkpointer
chat_sessions.user_id     UUID                    -- nullable, NO único
CREATE INDEX ix_chat_sessions_user ON chat_sessions (user_id);
```

`user_id` no es único → un usuario tiene muchas conversaciones. `GET /sessions` las lista
filtrando por usuario autenticado.

**[VERIFICADO] El vínculo es best-effort.** `_tag_session_owner` traga toda excepción con
`pass`. Si la escritura falla, la conversación **queda sin dueño y nadie se entera**.
Consecuencia para E3.1b: la relación existe pero **no está garantizada**.

---

## 6. LOGOUT / RELOGIN FLOW

**[VERIFICADO] `logout()` no borra `SESSION_KEY` ni `DEVICE_KEY`.** Limpia la sesión de
Supabase y el token en memoria; el `localStorage` de identidad queda intacto.

**Relogin:** misma cuenta → mismo `sub` → misma identidad. **[VERIFICADO]** estable.

### Consecuencia de privacidad, derivada de dos hechos verificados

```
1. logout no borra el session_id del navegador
2. GET /{session_id}/history no exige autenticación
        ↓
tras cerrar sesión, el navegador sigue apuntando al MISMO hilo —ya etiquetado con el
user_id anterior— y ese hilo se puede leer sin credencial
```

**[VERIFICADO]** los dos hechos por separado. **[INFERIDO]** la explotabilidad concreta: no se
ejecutó contra un entorno real, y los `session_id` son UUID4 no adivinables. Se reporta como
**consecuencia estructural**, no como vulnerabilidad medida. **No se corrige aquí.**

---

## 7. ANONYMOUS → AUTHENTICATED

**[VERIFICADO] Existe linkage parcial, y es el `COALESCE`:**

```sql
INSERT INTO chat_sessions (session_id, user_id) VALUES (:sid, :uid)
ON CONFLICT (session_id) DO UPDATE
SET user_id = COALESCE(chat_sessions.user_id, :uid)
```

Un hilo con `user_id` **NULL** (anónimo) **sí puede adquirir dueño** cuando esa misma persona
inicia sesión y sigue enviando el mismo `session_id` — que es lo que ocurre, porque el
`localStorage` no se limpia al login.

**Primer dueño gana:** una vez asignado, otro usuario **no** puede reasignarlo.

**Lo que NO existe [VERIFICADO]:**

- migración de conversaciones **anteriores** del mismo navegador (solo se liga la que está en
  curso);
- vínculo `device_key` → `user_id` en ninguna tabla;
- reconciliación de historial al iniciar sesión.

Es decir: **hay adopción del hilo activo, no account-linking.**

---

## 8. THREAD_ID SEMANTICS

| Pregunta | Respuesta |
|---|---|
| ¿Quién lo genera? | **Ambos.** Frontend normalmente (`'session-' + uuid4`); backend si falta (`default_factory=uuid4`) — **[VERIFICADO]** |
| ¿Sobrevive a recarga? | ✅ `localStorage` |
| ¿Sobrevive a logout? | ✅ no se limpia |
| ¿Sobrevive a otro navegador? | ❌ |
| ¿Se asocia a `user_id`? | ✅ en `chat_sessions`, best-effort |
| ¿Puede reutilizarlo otro usuario? | **No para adueñárselo** (COALESCE). **Sí para leerlo** (§9) |
| ¿Es opaco? | ❌ **[VERIFICADO]** el del QR codifica estructura: `chat.py` extrae el `activo_id` por posición fija de `qr-{activo}-{device}` |
| ¿Puede colisionar? | UUID4 → colisión accidental despreciable. **Deliberada: sí**, el formato QR es determinista por (inmueble × dispositivo) |

**Que el `session_id` transporte datos** —qué inmueble, qué navegador— significa que no es una
llave neutral. Cambiar su formato rompería el parseo de `assets.py` y `chat.py`.

---

## 9. AUTHORIZATION BOUNDARY

**El hallazgo que decide la pregunta central de esta unidad.**

**[VERIFICADO] por AST**, inventario congelado con test:

| Operación | Auth |
|---|---|
| `PATCH /sessions/{id}` (renombrar) | ✅ `get_current_user` |
| `DELETE /sessions/{id}` (archivar) | ✅ `get_current_user` |
| `POST/DELETE /sessions/{id}/share` | ✅ `get_current_user` |
| `GET /sessions` (listar) | ✅ `get_optional_user` → `[]` si invitado |
| **`GET /{session_id}/history`** | ❌ **ninguna** |
| **`GET /{session_id}/handoff`** | ❌ **ninguna** |
| **`GET /{session_id}/intencion`** | ❌ **ninguna** |
| `GET /shared/{token}` | ❌ por diseño — exige `share_token` **y** `is_public = true` |

**Las mutaciones exigen dueño; las lecturas no.**

`/shared/{token}` es la excepción legítima y demuestra el contraste: allí sí hay una condición
explícita de acceso. En `/history` no hay ninguna.

> **Identidad ≠ autorización.** Un `session_id` estable no sirve como raíz del Buyer si
> conocerlo permite acceder al hilo sin verificar propietario. Ese es exactamente el estado
> actual.

**No se corrige en esta unidad.** Queda como hallazgo con test que lo congela: si la frontera
se mueve, el test lo detecta.

---

## 10. PERSISTENCE & LIFETIME

| Identificador | Vida | Se borra con |
|---|---|---|
| `sub` / `user_id` | permanente | eliminar la cuenta en Supabase (`ON DELETE CASCADE` → `profiles`) |
| `session_id` | indefinida en `localStorage` | limpiar datos del navegador · nueva conversación |
| `device_key` | indefinida en `localStorage` | limpiar datos del navegador |
| `chat_sessions.user_id` | permanente en Postgres | supresión manual |
| `visita.device_key` / `contacto.device_key` | permanente | **debe alcanzarlas una supresión** (nota 024) |
| sesión de auth (storage de supabase-js) | persistida por defecto en `localStorage` **[contrato del proveedor]** | `signOut({scope:'local'})` |
| access token en `api.js` | variable de módulo, se repuebla al recargar | logout · recarga |

---

## 11. IDENTITY MATRIX

| Caso | Identidad disponible | Estabilidad | Cross-thread | Cross-session | Backend verificable | ¿Candidata a buyer root? |
|---|---|---|---|---|---|---|
| **autenticado** | `claims.sub` = `auth.users.id` | **alta** — [VERIFICADO] en el flujo del repo; [INFERIDO] cross-device | ✅ 1:N vía `chat_sessions.user_id` | ✅ | ✅ JWT firmado, validado contra JWKS | **YES** |
| **anónimo** | ninguna de persona; `session_id` + `device_key` de navegador | media (`localStorage`) | ❌ `session_id` es 1:1 con hilo | ✅ solo mismo navegador | ⚠️ `device_key` sí llega y se persiste, pero **no autenticado** | **NO** — ver §13 |
| **múltiples chats** | `user_id` | alta | ✅ | ✅ | ✅ | **YES** (misma raíz que autenticado) |
| **relogin** | `user_id` | alta | ✅ | ✅ | ✅ | **YES** |
| **anon→login** | adopción del hilo activo vía `COALESCE` | parcial | ❌ solo el hilo en curso | ❌ no migra historial previo | ✅ verificable en `chat_sessions` | **ONLY_WITH_CONSTRAINTS** |

---

## 12. WHAT CAN BE A BUYER ROOT

> **La raíz es `claims.sub` = `auth.users.id` — el sujeto autenticado.**
> **`profiles.user_id` es una proyección local 1:1 de esa identidad, no la identidad.**

La distinción no es estética. La identidad **nace** en el sujeto autenticado; el perfil es una
representación local que el backend **auto-provisiona** (`_load_or_provision_profile` inserta
la fila la primera vez que ve al usuario).

```
auth subject  →  propiedad del Buyer      ← la raíz
profile       →  metadata de producto (rol, nombre, agencia)
```

**No al revés.** Si E3.1b hiciera depender la existencia del Buyer de que una fila de
`profiles` esté correctamente provisionada, ataría la identidad a un efecto secundario
best-effort. El store puede usar una FK o un valor equivalente a ese UUID; lo que no debe es
tratar el perfil como fuente.

Razones **[VERIFICADO]**:

1. Identifica **persona/cuenta**, no sesión ni conversación.
2. Firmado por un tercero (Supabase) y validado contra JWKS: **no es autoafirmado**.
3. Estable dentro del flujo autenticado modelado por el repo (§3, con su nivel de evidencia).
4. Ya tiene 1:N con conversaciones, con índice.
5. `profiles.user_id` ya referencia `auth.users(id)` con `ON DELETE CASCADE` — el borrado de
   cuenta ya arrastra la proyección local.
6. **Conocerlo no otorga acceso**: hace falta un JWT válido.

El punto 6 es el que ninguna otra identidad del sistema cumple.

---

## 13. WHAT CANNOT

| Candidato | Por qué no |
|---|---|
| **`thread_id` / `session_id`** | Identifica **conversación**, no persona. 1:1 con hilo. Y **[VERIFICADO]** conocerlo permite leer el hilo sin auth: es capacidad, no identidad |
| **`device_key`** | Identifica **navegador**, no persona. Se pierde al cambiar de dispositivo, se comparte entre personas que usan el mismo. Y **el repo ya lo clasifica como dato personal con obligación de supresión**: ampliarle el alcance es decisión de producto, no de arquitectura |
| **access token** | Efímero por diseño, en memoria |
| **`email`** | `[DESCONOCIDO]` si es obligatorio y único en este proyecto de Supabase; y es mutable |
| **Identidad anónima nueva** | **Explícitamente fuera de alcance.** Crear una cookie/UUID persistente solo porque E3.1b lo necesitaría sería fabricar continuidad que el producto hoy no tiene |

---

## 14. UNKNOWN / UNPROVEN

1. **[DESCONOCIDO]** ¿El proyecto de Supabase permite cuentas anónimas
   (`signInAnonymously`)? No hay evidencia en el repo. Si existiera, cambiaría §11.
2. **[DESCONOCIDO]** ¿Qué ocurre exactamente si `_tag_session_owner` falla en producción?
   Traga la excepción sin log. **No hay forma de saber cuántos hilos quedaron huérfanos.**
3. **[INFERIDO]** Explotabilidad concreta de §9. Verificado el hecho estructural, no ejecutado
   contra un entorno real.
4. **[DESCONOCIDO]** ¿Hay RLS en Supabase sobre estas tablas? El backend usa conexión directa
   a Postgres, así que **[INFERIDO]** RLS no aplica a esta ruta.
5. **[DESCONOCIDO]** Estabilidad de `sub` ante cambio de email o proveedor de login.
6. **[HIPÓTESIS]** El QR es el flujo anónimo dominante. Si es así, el Buyer anónimo importa más
   de lo que sugiere la falta de identidad — no se midió.

---

## 15. IMPLICATIONS FOR E3.1b

1. **`buyer_id` puede ser `profiles.user_id`** para autenticados. No hace falta surrogate.
2. **El Buyer durable solo existe para autenticados.** Para anónimos, la memoria queda
   acotada al hilo (que es lo que ya hay).
3. **El vínculo hilo↔usuario no está garantizado** (best-effort). Un store que asuma que toda
   conversación tiene dueño se equivocará.
4. **La idempotencia sigue siendo `(buyer_id, source_message_id)`**, congelada en F3.0b. Con
   `buyer_id` resuelto para autenticados, ya es implementable.
5. **No apoyarse en `thread_id` para autorizar nada.** §9 muestra que hoy no autoriza.
6. **La asimetría es la respuesta correcta.** No diseñar identidad artificial para conseguir
   simetría entre autenticado y anónimo.

---

## 16. DEFERRED PRODUCT DECISIONS

Decisiones que **no** son técnicas y E3.1a no toma:

1. **¿Debe existir Buyer anónimo?** Si sí, exige crear continuidad que hoy no existe —o
   ampliar el alcance del `device_key`, que ya es dato personal declarado.
2. **¿Ampliar el `device_key` al Buyer?** Consecuencia directa: la obligación de supresión de
   la migración 024 se extendería al Buyer Store.
3. **¿Migrar el Buyer anónimo al iniciar sesión?** Hoy solo se adopta el hilo activo.
4. **¿Cerrar la frontera de §9?** Añadir auth a `/history` es un cambio de comportamiento con
   riesgo de romper el flujo del QR, que depende de leer sin cuenta.
5. **¿Qué pasa con el Buyer al borrar la cuenta?** `profiles` cae por cascada; un Buyer Store
   nuevo necesitaría la misma garantía.

---

## Gate de cierre

| # | Pregunta | Respuesta |
|---|---|---|
| 1 | Qué identifica a un autenticado | `claims.sub` → `profiles.user_id` ✅ |
| 2 | Qué identifica a un anónimo | Ninguna identidad de persona; `session_id` + `device_key` de navegador ✅ |
| 3 | Relación user ↔ thread | 1:N vía `chat_sessions.user_id`, indexada, **best-effort** ✅ |
| 4 | Múltiples chats | Soportado; `GET /sessions` filtra por usuario ✅ |
| 5 | Logout / relogin | `sub` estable; `localStorage` **no** se limpia ✅ |
| 6 | anon→login linking | Parcial: adopción del hilo activo por `COALESCE` ✅ |
| 7 | Quién autoriza el acceso a un hilo | **Nadie, en lectura** ✅ |
| 8 | Qué identidad sobrevive entre sesiones | Solo `claims.sub` con evidencia ✅ |
| 9 | Qué NO puede ser `buyer_id` | `thread_id`, `device_key`, token, email ✅ |
| 10 | Incógnitas que bloquean E3.1b | §14 — ninguna bloquea el carril autenticado ✅ |

---

## Recomendación

```
E3.1b READY WITH CONSTRAINT

RAÍZ VERIFICADA
    claims.sub  =  auth.users.id          ← el sujeto autenticado
    profiles.user_id                      ← proyección local 1:1, NO la identidad

RESTRICCIONES
    1. el Buyer durable existe SOLO para autenticados;
       para anónimos NO se crea identidad — la memoria queda acotada al hilo
    2. no apoyarse en thread_id para autorizar (§9)
    3. no atar la existencia del Buyer a que la fila de `profiles` esté provisionada
```

### Secuencia recomendada — con un paso intermedio

El hallazgo de §9 no obliga a corregirlo dentro de E3.1a, pero **sí cambia el orden de lo que
viene**:

```
E3.1a  ──▶  PR · CI · merge
              ↓
        AUTH-READ-GATE          ← proteger /history, /handoff, /intencion por ownership,
              ↓                    preservando /shared/{token} como acceso público explícito
        E3.1b Buyer Store
```

**Por qué antes y no después.** El Buyer Harness aumenta la sensibilidad de lo que se asocia a
una persona: criterios, presupuesto, correcciones, anclas y trazas. Aunque el store tenga sus
propios endpoints protegidos, dejar legible por `session_id` la conversación asociada a ese
mismo usuario sería construir memoria durable encima de una frontera que acabamos de descubrir
abierta.

**No es una vulnerabilidad explotada** —los `session_id` son UUID4 y no se hizo prueba
ofensiva— pero sí un **control de autorización ausente [VERIFICADO]**, y eso basta para
tratarlo como deuda de seguridad **antes** de persistir memoria del comprador.

La asimetría no es una carencia del diseño: es lo que el producto es hoy. Inventar una
identidad anónima para lograr simetría sería fabricar continuidad que el sistema no tiene —
la misma clase de error que F2 y F3.0b se pasaron cerrando con `place_id` y `message_id`.

**STOP.** No se construyen tablas, migraciones ni store.
