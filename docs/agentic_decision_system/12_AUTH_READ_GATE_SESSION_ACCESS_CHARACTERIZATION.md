# AUTH-READ-GATE.0 — Session Access Characterization & Policy

| | |
|---|---|
| **Baseline** | `03f87f7d559f353609e6e17da32b6f735b0e0ee2` |
| **Rama** | `feat/auth-read-gate-characterization` |
| **Suite** | **1 518 `exit 0`** (1 500 + 18) |
| **Cambios productivos** | **0** |

---

## 1. HALLAZGO EJECUTIVO — la frontera abierta no es solo de lectura

La unidad se autorizó para caracterizar el acceso de **lectura**. Al seguir el hilo apareció
algo mayor:

> **Conocer un `session_id` permite leer la conversación, escribir en ella y —si no tiene
> dueño— apropiársela.**

```
LEER      GET /{id}/history · /handoff · /intencion   →  sin auth
ESCRIBIR  POST /chat                                  →  sin comprobar propiedad
RECLAMAR  POST /chat  → _tag_session_owner            →  COALESCE asigna primer dueño
PUBLICAR  POST /sessions/{id}/share                   →  acepta hilos sin dueño
```

**Cerrar solo `/history` sería una corrección incompleta.** El atacante no necesitaría leer
el hilo: se lo quedaría con un `POST /chat`, y a partir de ahí lo leería legítimamente.

---

## 2. EL CARRIL QR, END-TO-END

```
letrero físico
   └─ URL impresa:  {app}/a/{activo_id}?utm_source=letrero&utm_medium=qr
                    ↑ SOLO el inmueble · sin session_id · sin token
          ↓
   loadFromDeepLink(activo_id)                      [frontend]
          ↓
   ¿localStorage['ctx_qr_' + activo_id] existe?
      SÍ →  GET /{prev}/handoff   ── apiHeaders() ──▶  ¿activo?
             └─ SÍ →  GET /{prev}/history   → reanuda la conversación
      NO →  sid = `qr-{activo}-{device}-{6 al azar}`   ← nace en el CLIENTE
             localStorage[SESSION_KEY] = sid
             localStorage['ctx_qr_'+activo] = sid
          ↓
   POST /chat  { message, session_id: sid }
          ↓
   _tag_session_owner(sid, user)   ← user = None si es anónimo → no etiqueta
          ↓
   checkpointer (thread_id = sid)
```

### Respuestas a las preguntas de la unidad

| Pregunta | Respuesta |
|---|---|
| ¿El QR representa inmueble, conversación o ambas? | **El inmueble.** `/a/{activo_id}` — **[VERIFICADO]** |
| ¿Cuándo existe por primera vez el `session_id`? | Al abrir el deep link, **en el navegador** |
| ¿Quién lo genera en cada carril? | QR y chat normal: **el cliente**. El backend solo si el cliente no lo manda (`default_factory=uuid4`) |
| ¿Necesita recuperar la misma conversación desde otro dispositivo? | **No puede hoy.** La llave está en `localStorage` y el id incluye el `device_id`: otro navegador abre un hilo nuevo |
| ¿Qué información hay en la URL? | Solo `activo_id` + UTM. **Ninguna credencial** |
| ¿`loadFromDeepLink` esconde alguna credencial? | **No.** Sus dos llamadas van con `apiHeaders()`, que para un anónimo es la `X-API-Key` pública del sitio y nada más |
| ¿Qué necesita `/handoff` en el carril anónimo? | Es **esencial**: así el visitante recupera la conversación con el corredor al volver |
| ¿`/intencion` participa en el QR? | **No. Quedó abierto por accidente** — ningún componente del frontend lo llama |
| ¿Y si un anónimo inicia sesión después? | El `COALESCE` le asigna el hilo. Ver §4 |

### Restricción dura para AUTH-READ-GATE.1

**Los letreros ya impresos no llevan credencial y no se pueden cambiar.** Cualquier prueba de
posesión para el QR tiene que poder **emitirse después del escaneo**, no venir en la URL.

---

## 3. FRONTERA 1 · LECTURA

| Endpoint | Auth | Usado por el QR |
|---|---|---|
| `GET /{session_id}/history` | ❌ ninguna | ✅ sí |
| `GET /{session_id}/handoff` | ❌ ninguna | ✅ sí |
| `GET /{session_id}/intencion` | ❌ ninguna | ❌ **no — abierto por accidente** |
| `GET /shared/{token}` | ❌ por diseño | — exige `share_token` **+** `is_public` |
| `GET /sessions` | ✅ `get_optional_user` → `[]` si invitado | — |

`/intencion` es el caso fácil: **no tiene consumidor**. Cerrarlo no rompe nada.

---

## 4. FRONTERA 2 · ESCRITURA Y APROPIACIÓN

### 4.a · Escribir en un hilo ajeno

**[VERIFICADO]** `POST /chat` llama a `_tag_session_owner(payload.session_id, user)` como
**primera instrucción real**, con el `session_id` que envía el cliente, y luego invoca el
grafo con ese `thread_id`. No hay ninguna comprobación de propiedad en medio.

### 4.b · Reclamar un hilo sin dueño

```sql
INSERT INTO chat_sessions (session_id, user_id) VALUES (:sid, :uid)
ON CONFLICT (session_id) DO UPDATE
SET user_id = COALESCE(chat_sessions.user_id, :uid)
```

**El primer autenticado que envíe ese `session_id` se queda con el hilo**, sin demostrar
posesión de nada. Basta con conocer el identificador.

> Esto es exactamente lo que la revisión anticipó: *"conocer `session_id` no debería ser
> suficiente para apropiarse del hilo"*. **Hoy lo es.**

### 4.c · Asimetría entre mutaciones

**[VERIFICADO]**, congelado con test:

| Endpoint | Criterio de propiedad | Acepta hilos sin dueño |
|---|---|---|
| `PATCH /sessions/{id}` (renombrar, fijar) | `WHERE session_id = :sid AND user_id = :uid` | ❌ **no** |
| `DELETE /sessions/{id}` (archivar) | `... OR chat_sessions.user_id IS NULL` | ✅ sí |
| `POST /sessions/{id}/share` | `... OR chat_sessions.user_id IS NULL` | ✅ sí |

Tres endpoints hermanos, **dos criterios distintos**. No parece una decisión deliberada.

### 4.d · El caso más agudo: compartir publica y reclama a la vez

```sql
SET share_token = COALESCE(chat_sessions.share_token, :tok),
    is_public   = true,
    user_id     = COALESCE(chat_sessions.user_id, :uid)
WHERE chat_sessions.user_id = :uid OR chat_sessions.user_id IS NULL
```

Un autenticado que conozca el `session_id` de una conversación anónima puede, en una sola
petición, **quedársela y hacerla públicamente legible**.

### 4.e · El vínculo puede fallar en silencio

`_tag_session_owner` traga toda excepción con `pass`. **No se puede asumir que "sin dueño"
signifique "nunca hubo un autenticado"** — puede significar que la escritura falló.

---

## 5. LO QUE EL `session_id` ES HOY

> **El mismo valor identifica el recurso y da acceso a él.**

Y no cumple ninguna propiedad de credencial:

| Propiedad | ¿La cumple? |
|---|---|
| opaco | ❌ el del QR codifica `qr-{activo}-{device}` |
| rotable | ❌ |
| revocable | ❌ (solo el `share_token` lo es) |
| alta entropía | ⚠️ UUID4 dentro, pero con prefijo predecible |
| emitido por el servidor | ❌ lo genera el cliente |
| propósito acotado | ❌ es el identificador del hilo |

---

## 6. POR QUÉ EL `device_key` NO SIRVE — con la razón correcta

**Precisión adoptada de la revisión.** Que una credencial esté en poder del cliente **no la
invalida**: todo bearer token lo está por definición. Mi formulación anterior era perezosa.

Lo que descarta al `device_key` es otra cosa:

1. **Nunca fue emitido como credencial.** Nació para hacer privada la sesión del QR por
   visitante, no para probar posesión de nada.
2. **No está acotado a una conversación**: es del navegador, y el mismo navegador abre
   muchos hilos.
3. **No está ligado a `chat_sessions`** — sin columna, índice ni FK. **[VERIFICADO]**
4. **Ya tiene un propósito previo y una obligación**: la migración 024 lo declara dato
   personal con supresión asociada. Ampliarlo cambia el tratamiento de un dato existente.

Es una **decisión de producto**, no de arquitectura. Y no hace falta tomarla: §8 propone una
salida que no lo toca.

---

## 7. MATRIZ DE TRANSICIÓN

`actor × propiedad del hilo × credencial × endpoint → hoy / política propuesta`

| # | Hilo | Actor | Credencial | Endpoint | **HOY** | **PROPUESTA** |
|---|---|---|---|---|---|---|
| 1 | `user_id = U1` | U1 auth | — | leer | allow | **allow** |
| 2 | `user_id = U1` | U2 auth | — | leer | **allow** ⚠️ | **deny** |
| 3 | `user_id = U1` | anónimo | ninguna | leer | **allow** ⚠️ | **deny** |
| 4 | `user_id = U1` | anónimo | resume válida antigua | leer | n/a | **deny por defecto** |
| 5 | `user_id = NULL` | anónimo | válida | leer | allow *(sin credencial)* | **allow** |
| 6 | `user_id = NULL` | anónimo | ausente | leer | **allow** ⚠️ | **deny** |
| 7 | `user_id = NULL` | U1 auth | válida | `POST /chat` | claim | **claim** |
| 8 | `user_id = NULL` | U1 auth | ausente | `POST /chat` | **claim** ⚠️ | **no claim** |
| 9 | `user_id = U1` | U2 auth | — | `POST /chat` | **escribe** ⚠️ | **deny** |
| 10 | `user_id = NULL` | U1 auth | ausente | `share` | **claim + publica** ⚠️ | **deny** |
| 11 | `user_id = U1` | U2 auth | — | `PATCH` | deny ✅ | deny |
| 12 | cualquiera | cualquiera | `share_token` + `is_public` | `/shared/{token}` | allow | **allow, sin cambios** |

**Seis filas divergen.** Las marcadas ⚠️ son la deuda.

**Fila 4** merece nota: tras un claim, la credencial anónima debería **revocarse o rotarse**.
Mantenerla sería conservar un segundo acceso bearer a datos ya asociados a una cuenta.

---

## 8. SI HACE FALTA UNA CAPABILITY (evaluación, no implementación)

Contrato evaluado contra el carril QR real:

```
emitida por el servidor · opaca · alta entropía · acotada a la sesión
propósito = reanudar    · revocable · rotable
sin semántica de identidad
no derivada del session_id · no derivada del device_key
almacenado el HASH, no el secreto
```

**Compatible con la restricción dura del §2**: como no puede venir en la URL impresa, tendría
que emitirse en la **respuesta del primer `POST /chat`** del hilo y guardarse en
`localStorage` junto al `session_id` que ya se guarda.

### Transporte — comparación, sin decidir

| Opción | A favor | En contra |
|---|---|---|
| **Query param** | trivial | acaba en logs, historial y `Referer` — **desaconsejado** |
| **Fragmento + header** | no viaja al servidor por accidente | el frontend debe leerlo y reenviarlo; más piezas |
| **Cookie `HttpOnly`** tras intercambio inicial | no accesible a JS; el navegador la envía sola | requiere CORS con credenciales y política de `SameSite`; el QR abre en navegador embebido a veces |

**No se elige.** La decisión depende de una incógnita de producto: cuánto dura de verdad una
conversación de QR. Sin ese dato, cualquier TTL sería arbitrario.

**Y no se implementa nada.** Ni `resume_token`, ni migración, ni cookie, ni header, ni
middleware, ni dependencia, ni 401/403 nuevos, ni cambios de frontend.

---

## 9. LO QUE SIGUE ABIERTO

1. **[DESCONOCIDO]** Cuánto dura una conversación de QR en producto. Bloquea el TTL.
2. **[DESCONOCIDO]** ¿Se espera reanudar desde otro dispositivo? Hoy es imposible; si el
   producto lo quiere, la capability sola no basta.
3. **[DESCONOCIDO]** Volumen de hilos anónimos sin dueño ya existentes. Una política
   retroactiva los dejaría inaccesibles.
4. **[HIPÓTESIS]** El QR es el flujo anónimo dominante — no medido.
5. ¿La asimetría de §4.c fue deliberada? Parece deriva, no diseño.

---

## 10. Gate de cierre

```
AUTH-READ-GATE.1 READY WITH CONSTRAINT
```

**La política se puede especificar** (§7) y el carril QR está entendido de punta a punta (§2).

**Restricciones que AUTH-READ-GATE.1 debe respetar:**

1. **El alcance es mayor que la lectura.** Debe cubrir `POST /chat` (escritura + claim) y
   `share`. Cerrar solo los GET dejaría el claim abierto.
2. **La credencial no puede venir en la URL** — los letreros impresos no cambian.
3. **`/intencion` se puede cerrar sin coste**: no tiene consumidor.
4. **`/handoff` y `/history` sí sostienen el QR**: cerrarlos sin capability rompe producto.
5. **`/shared/{token}` no se toca.**
6. **No usar `device_key`** como credencial (§6).
7. **TTL y transporte quedan sin decidir** hasta resolver §9.1.

**No está BLOCKED**: la semántica del QR quedó resuelta. Lo que falta son datos de producto
para afinar, no para diseñar.

---

**STOP.** Nada implementado. La unidad siguiente será la primera de la fase con cambio
deliberado de comportamiento productivo.
