# 14 · E3.1b — BUYER STORE V0 · persistencia versionada

```
BASELINE      c8429575bce84c15f65890f59433f706f4b87893   (origin/main verificado)
RAMA          feat/f3-buyer-store-versioning
WORKTREE      nuevo, desde origin/main

backend sin motor   1 721 exit 0   (32 saltados)
backend con motor   1 721 exit 0   (0 saltados)
buyer store         15 integración + 14 unidad
frontend            0 ficheros tocados

GATE E3.1b    PASS
```

---

## 1 · SCOPE

El almacén durable y versionado del `BuyerContextV0`. **Solo eso.**

```
identidad durable → snapshot persistido → revisiones monotónicas
→ historial append-only → idempotencia por mensaje → protección contra escrituras rancias
```

### Qué NO se construyó, y sigue sin existir

`[VERIFICADO]` — hay un test que lo comprueba barriendo todo `app/` y `main.py`:

```
updater · extracción de preferencias · interpretación de mensajes
clasificación hard/soft · resolución de commute · tradeoffs · inferencia de etapa
conexión con el agente · cambios de ranking · cambios de UI · endpoints públicos
```

**Cero wiring productivo.** `assembler.py`, el grafo del agente, `/chat`, el frontend y el
Decision Core siguen sin saber que el store existe.
`test_NADIE_en_produccion_llama_todavia_al_store` lo fija: si alguien conecta el store "de
paso", el test cae. Conectarlo es E3.2.

---

## 2 · IDENTIDAD DEL COMPRADOR

```
buyer_id = auth.users.id = claims.sub     el sujeto autenticado
```

`[VERIFICADO]` La FK es real y se ejerce contra Postgres: un `buyer_id` sin cuenta detrás
falla con violación de clave foránea (`test_un_buyer_id_sin_cuenta_no_puede_persistir`).

**`profiles` NO es la raíz.** Es una proyección local que puede no estar provisionada, y la
existencia del comprador no puede depender de eso. La 028 referencia `auth.users` igual que
la 008.

**No hay comprador durable anónimo.** No se creó `anonymous_buyer_id`, ni `guest_id`, ni
cookie, ni mapeo `device_key → buyer`. El visitante sin cuenta no tiene fila; su memoria
sigue acotada al hilo. `test_ni_session_id_ni_device_key_aparecen_en_el_store` barre el
código **desnudo** (por AST) y el SQL sin comentarios — los comentarios sí nombran esos
identificadores, precisamente para explicar por qué están excluidos.

---

## 3 · ESQUEMA — migración 028

```
buyer_context_heads
  buyer_id          UUID PK  REFERENCES auth.users(id) ON DELETE CASCADE
  current_revision  INTEGER  NOT NULL CHECK (>= 0)
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()

buyer_context_revisions
  buyer_id          UUID     NOT NULL REFERENCES buyer_context_heads(buyer_id) ON DELETE CASCADE
  context_revision  INTEGER  NOT NULL CHECK (>= 0)
  source_message_id TEXT     NOT NULL
  context_json      JSONB    NOT NULL
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now()

  PRIMARY KEY (buyer_id, context_revision)
  UNIQUE      (buyer_id, source_message_id)   ← la invariante de idempotencia
```

**Por qué cabeza + historial y no una fila mutable.** Una sola fila resolvería "cuál es el
estado actual" y rompería las tres cosas que ya sabemos que pasan: la historia deja de poder
explicarse, los reintentos duplican revisiones, y dos conversaciones simultáneas se pisan en
silencio. La cabeza además da la **fila única sobre la que serializar** — sin ella, dos
escritores concurrentes no tienen nada que bloquear.

**Por qué JSONB.** No hay evidencia de producto sobre cómo se consultarán criterios, anclas
o tradeoffs. Normalizar ahora fija una forma que aún no conocemos. El snapshot preserva el
contrato, permite round-trip exacto y no impide normalizar después. Lo innegociable: se
rehidrata **siempre** por `BuyerContextV0` — un `dict` de la base no es un BuyerContext
hasta que el contrato lo valida.

**No se guarda el texto del mensaje**, solo `source_message_id`. La conversación tiene su
propio almacenamiento; duplicarlo aquí duplicaría PII sin ganar nada. `[VERIFICADO]` por
test sobre el esquema y sobre el código.

---

## 4 · SEMÁNTICA DE REVISIONES

```
sin estado + expected_revision=None   →  revisión 0
estado N   + expected_revision=N      →  revisión N+1
estado N   + expected_revision≠N      →  BuyerRevisionConflict, cero escrituras
```

**La revisión la asigna el store**, nunca el llamante ni el modelo. `expected_revision` es
lo que el llamante *creía* que había al leer; el store sobrescribe el `context_revision` que
venga en el contexto para que no haya dos fuentes de verdad del número.

---

## 5 · IDEMPOTENCIA

`(buyer_id, source_message_id)` identifica una mutación que no puede producir dos revisiones.

| Caso | Resultado |
|---|---|
| mismo mensaje, **mismo** payload | devuelve la revisión existente · `creada=False` · 0 escrituras |
| mismo mensaje, payload **distinto** | `BuyerIdempotencyConflict` · 0 escrituras |

**El segundo caso es el que importa.** Si la misma evidencia produce dos estados, lo que hay
delante es un extractor no determinista, un replay corrupto, o la misma evidencia
interpretada de dos formas. Devolver lo viejo en silencio dejaría ese fallo invisible.
**La idempotencia no puede ocultar divergencia.**

La comparación se hace sobre la forma canónica (JSON con claves ordenadas) y **excluye
`context_revision`**: es metadato del store, no estado del comprador. Incluirlo haría que el
mismo snapshot pareciera distinto solo por haber sido numerado, y produciría conflictos
falsos que acusarían al extractor de algo que no hizo.

**El orden de comprobación no es casual:** la idempotencia se mira *antes* que el conflicto
de revisión. Un reintento llega con el `expected_revision` viejo y parecería concurrencia —
sería un diagnóstico equivocado: no hay dos escritores, hay uno que repite.

---

## 6 · CONCURRENCIA OPTIMISTA

```
INSERT … ON CONFLICT DO NOTHING   (crea la cabeza si no existe)
SELECT … FOR UPDATE               (serializa a los escritores del mismo comprador)
comprobar idempotencia → comprobar revisión → INSERT revisión → UPDATE cabeza → COMMIT
```

`[VERIFICADO] contra Postgres real, con dos conexiones distintas.` Dos transacciones
escribiendo desde `expected_revision=0`: exactamente una crea la revisión 1, la otra recibe
`BuyerRevisionConflict`. El historial queda en `[0, 1]` — sin revisión duplicada y sin lost
update.

Las dos garantías duras viven **en la base**, no en Python. Comprobar-y-luego-insertar tiene
una ventana entre la comprobación y la escritura; un índice único y un bloqueo de fila no la
tienen.

---

## 7 · POSTGRES REAL — la evidencia

```
motor    PostgreSQL 15.4 (postgis/postgis:15-3.3, del docker-compose del repo)
base     buyer_store_test — dedicada, creada vacía
```

`TEST_DATABASE_URL` es obligatoria, **no** cae por defecto a `settings.database_url`, y la
fixture aborta si la URL contiene `supabase.com` o `pooler`. Estos tests hacen `DROP TABLE`.

**`auth.users` en pruebas:** la fixture crea el mínimo (`id uuid primary key`) para ejercer
la FK de verdad, incluido el borrado en cascada. **No se relajó la FK para que los tests
pasaran**; se reprodujo el entorno donde esa FK es válida.

**La 028 se aplica por su camino real** (`app.esquema_requerido.aplicar_migracion`), no por
una copia del SQL. Es la lección de AUTH-READ-GATE.1, donde el aplicador tenía un fallo que
los tests no veían porque ejecutaban el SQL por otra vía.

### 15 tests de integración

```
✓ la 028 aplica desde cero · crea las dos tablas · el UNIQUE existe en la BASE
✓ la 028 es idempotente (segunda pasada, esquema idéntico)
✓ primer estado → revisión 0
✓ round-trip exacto por el contrato
✓ segundo mensaje → revisión 1
✓ el historial conserva la revisión 0 sin tocar
✓ reintento con mismo payload → no crea fila, devuelve la existente
✓ mismo mensaje con payload distinto → BuyerIdempotencyConflict, 0 escrituras
✓ expected_revision rancia → BuyerRevisionConflict, 0 escrituras
✓ DOS CONEXIONES REALES compitiendo → 1 gana, 1 conflicto, revisiones [0,1]
✓ dos compradores no mezclan revisiones (mismo message_id en ambos es legítimo)
✓ contexto de otro comprador → falla antes de persistir
✓ borrar la cuenta borra cabeza e historial por cascada
✓ buyer_id sin cuenta → violación de FK
✓ fila que no valida → BuyerContextCorrupto, nunca se presenta como contexto válido
```

### Mutaciones — la prueba de que los tests pueden fallar

```
quitar FOR UPDATE                      → cae el test de concurrencia real
la idempotencia traga la divergencia   → cae el de payload distinto
no comprobar la identidad del comprador → cae el de contexto ajeno
```

`app/buyer/store.py` quedó restaurado y verificado tras cada mutación.

---

## 8 · CICLO DE VIDA

`[VERIFICADO]` Borrar la fila de `auth.users` elimina la cabeza **y** todo el historial por
cascada en dos saltos (`auth.users → heads → revisions`).

`[OBSERVADO]` En producción `auth.users` lo gestiona Supabase; el borrado real de una cuenta
pasa por su flujo. La cascada se probó contra un `auth.users` reproducido, no contra el de
Supabase.

---

## 9 · FAIR HOUSING

**El Buyer Store NO es la barrera de sanitización.** Acepta un `BuyerContextV0` ya construido
y no mira su contenido.

La conversión determinista de texto libre a criterios persistibles pertenece a E3.2 y tiene
que ocurrir **antes** de llegar aquí. No se abrió un segundo camino de extracción "para
facilitar los tests" — eso sería precisamente el atajo por el que la barrera deja de existir.
`test_el_store_no_extrae_ni_interpreta` lo fija.

---

## 10 · PRECONDICIONES DE E3.2 — verificadas, no resueltas

Las tres salieron de la revisión de código del PR #131. **No son deuda difusa: son hechos
comprobados que E3.2 tiene que decidir antes de conectar el store.** Viven aquí y no en la
descripción del PR porque este documento es el handoff.

### 1 · `updated_at` participa hoy en la comparación de idempotencia

`[VERIFICADO]` `_canonico()` excluye `context_revision` pero **no** `updated_at`. Dos
`BuyerContextV0` semánticamente iguales cuyo `updated_at` difiera en un segundo se comparan
como payloads distintos, y un reintento del mismo `source_message_id` produciría
`BuyerIdempotencyConflict`.

**Los tests de E3.1b no podían revelarlo.** Sus fixtures usan un timestamp fijo
(`2026-08-27T12:00Z` literal), así que el reintento es determinista **por construcción**. No
es que el test pasara por suerte: la propiedad no era observable con esa entrada.

E3.2 debe decidir explícitamente qué significa `updated_at`:

- si es el timestamp **del evento** que originó el estado, forma parte del hecho y debe
  participar en la idempotencia;
- si es el timestamp **de persistencia** del store, es metadato: lo asigna el store o se
  excluye de la comparación, igual que `context_revision`.

**No cambiar esta semántica sin tomar antes esa decisión.** Y no se añade aquí un test que
fije una de las dos opciones: convertiría una pregunta de diseño de E3.2 en una decisión
accidental de E3.1b.

### 2 · `anexar_revision(…, db=sesion)` asume propiedad exclusiva de la transacción

`[VERIFICADO]` El store ejecuta `commit()` y `rollback()` incluso sobre una sesión inyectada.
Es correcto mientras esa sesión contenga **solo** trabajo del Buyer Store, que es el caso en
E3.1b.

E3.2 no debe reutilizar una sesión con otras escrituras pendientes sin decidir primero quién
posee `commit`/`rollback` y dónde termina la transacción. Es una precondición no escrita, y
las precondiciones no escritas se rompen cuando llega el segundo llamante.

### 3 · `source_message_id` vacío no lo rechaza ni el store ni el esquema

`[VERIFICADO]` `NOT NULL` impide `NULL`, no `""`. La cadena vacía atraviesa la validación del
store y llega hasta la base.

Hoy la garantía de no-vacío vive **upstream**, en `IdentifiedUserMessage(message_id` con
`min_length=1)`, así que E3.1b no tiene ningún camino productivo que pueda persistir una
cadena vacía —tampoco tiene consumidor productivo—.

Antes de conectar el store, E3.2 debe mantener esa costura como camino obligatorio o añadir
validación defensiva en el store. **No atribuir esta garantía al esquema:** el esquema no la
da.

---

## 10b · LECCIÓN DE COBERTURA

Una suite verde demuestra únicamente las propiedades que **sus entradas hacen observables**.
En E3.1b el timestamp fijo hizo invisible la interacción entre `updated_at` y la idempotencia:
el `assert` era correcto y la fixture impedía que llegara a ejercerse.

Es la misma familia que los dos defectos que Postgres destapó en AUTH-READ-GATE.1 —evidencia
que parecía cubrir algo y no lo cubría—, con una diferencia: allí lo encontró un motor real,
aquí lo encontró una lectura del código.

**Antes de dar una invariante por cubierta, comprobar no solo el `assert` sino que la fixture
pueda producir el estado que debería hacerla fallar.**

---

## 10c · OTROS LÍMITES CONOCIDOS

- `[DESCONOCIDO]` **La 028 no se aplicó en producción.** Deliberado: el store no está
  conectado a nada. Migrar producción se decide cuando se conecte al flujo real.
- `[OBSERVADO]` Las pruebas corren en **PG 15.4**; producción es **17.6**. Para lo que la 028
  usa (`CREATE TABLE IF NOT EXISTS`, FK, `UNIQUE`, `CHECK`, `FOR UPDATE`) el comportamiento
  es estable entre esas versiones. No es el mismo motor y no se afirma que lo sea.
- `[HIPÓTESIS]` JSONB sin normalizar es la forma correcta *para v0*. Si las consultas futuras
  necesitan filtrar por criterio, habrá que normalizar — el historial lo permite sin pérdida.
- `[DESCONOCIDO]` No hay política de retención ni de poda del historial. Un comprador muy
  activo acumulará revisiones sin límite.
- `[DESCONOCIDO]` `BuyerContextCorrupto` detecta filas que dejaron de validar, pero **no hay
  migración de contratos**: si `BuyerContextV0` evoluciona de forma incompatible, las filas
  viejas fallan al leerse. Es ruidoso a propósito, pero es trabajo pendiente.

---

## 11 · DECISIONES DIFERIDAS A E3.2+

```
quién construye el BuyerContextV0 (el updater)
cómo se resuelve un BuyerRevisionConflict (fundir estados, o reintentar sobre el nuevo)
la barrera determinista de Fair Housing antes del store
conectar el store al assembler / al grafo / a /chat
aplicar la 028 en producción
normalización de criterios, si la evidencia la justifica
```

---

## 12 · GATE E3.1b

```
[✓] buyer root = sujeto autenticado          [✓] BuyerContextV0 round-trip
[✓] sin comprador durable anónimo            [✓] ciclo de vida por cascada probado
[✓] historial append-only                    [✓] migración ejecutada contra Postgres real
[✓] revisión monotónica                      [✓] concurrencia contra Postgres real
[✓] el store controla context_revision       [✓] integración PG con 0 skips
[✓] idempotencia (buyer_id, message_id)      [✓] backend completo verde
[✓] replay divergente falla ruidosamente     [✓] cero wiring productivo
[✓] concurrencia optimista sin lost updates  [✓] documentación completa
```

```
GATE E3.1b        PASS
RECOMENDACIÓN     OPEN PR
```

---

## 13 · PUNTO DE REENTRADA PARA E3.2

El store existe, está probado contra motor real y **nadie lo llama**. E3.2 empieza por
decidir quién construye el `BuyerContextV0` y qué atraviesa la barrera determinista antes de
persistirlo.

Lo que E3.2 hereda ya resuelto: identidad, versionado, historia, idempotencia y concurrencia.
Lo que tiene que traer: el updater, la barrera de Fair Housing, y la política de resolución
de conflictos.

**Y tres decisiones que no puede saltarse**, verificadas en la revisión de #131 y detalladas
en §10: qué significa `updated_at` para la idempotencia, quién posee la transacción cuando se
inyecta una sesión, y dónde vive la garantía de que `source_message_id` no llega vacío.
Ninguna es opcional: las tres se rompen justo al conectar el store.
