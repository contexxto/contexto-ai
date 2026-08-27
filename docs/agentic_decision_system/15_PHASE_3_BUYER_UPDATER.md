# 15 · E3.2 — BUYER UPDATER · **PARCIAL: solo las precondiciones**

```
BASELINE        8b96a2faabbdca484888f01069ddcafab373fc8b   (origin/main verificado)
RAMA            feat/f3-buyer-updater

ALCANCE ENTREGADO   §0 prestart · §1 las tres precondiciones · §16 migración 029
ALCANCE PENDIENTE   §2-§15 el updater completo · §20 shadow wiring

GATE E3.2       HOLD   — la mayor parte del checklist sigue sin cumplirse
```

> **Esta unidad NO entregó el Buyer Updater.** Entregó las tres precondiciones que el propio
> prompt ordena resolver antes de tocarlo, más la migración que cierra la tercera. El
> updater, la barrera de Fair Housing, el routing situacional, la resolución de conflictos y
> el shadow wiring **no existen todavía**. El gate es `HOLD` por eso, no por un defecto.

---

## 1 · LAS TRES PRECONDICIONES — CERRADAS

### 1A · `updated_at` es metadata del store `[VERIFICADO]`

**Decisión:** `BuyerContextV0.updated_at` es el **instante de persistencia** de esa revisión.
No es la hora del `HumanMessage` ni un `observed_at` del usuario: `IdentifiedUserMessage` no
lleva timestamp contractual del evento, y fabricarle uno violaría procedencia.

Cambios: el store lo **asigna** junto a `context_revision`, y `_canonico()` excluye ambos.
El updater no debe generar `datetime.now()` dentro del payload semántico.

`[VERIFICADO]` mismo comprador + mismo `source_message_id` + mismo estado semántico +
`updated_at` distintos → idempotente, sin revisión nueva. Un cambio real de estado sigue
produciendo `BuyerIdempotencyConflict` aunque el timestamp coincida.

### 1B · la propiedad de la transacción sigue a la de la sesión `[VERIFICADO]`

```
db=None   → el store abre su sesión y hace commit/rollback
db=…      → el LLAMANTE hace commit/rollback; el store NO toca ninguno
```

Cuatro casos probados contra motor: sesión propia confirma; sesión inyectada respeta el
rollback del llamante; respeta su commit; y al fallar **no deshace trabajo ajeno** que el
store nunca vio.

`FOR UPDATE`, `UNIQUE`, idempotencia y concurrencia siguen intactas.

### 1C · `source_message_id` no vacío, en tres capas `[VERIFICADO]`

```
upstream   IdentifiedUserMessage(min_length=1)   el mensaje nace con identidad
Python     anexar_revision()                      falla antes de tocar la base
esquema    migración 029, CHECK btrim             ninguna otra vía puede colarla
```

La tercera capa importa porque las dos primeras protegen **un** camino: un backfill o un
segundo escritor futuro no pasan por `anexar_revision`.

---

## 2 · HALLAZGO — 1B rompió los tests de E3.1b, y era la señal correcta

`[VERIFICADO]` Al dejar de confirmar sobre sesión inyectada, `test_buyer_store_postgres.py`
**dejó de terminar**. La escritura de preparación quedaba sin confirmar, retenía el
`FOR UPDATE` de la cabeza, y el test de concurrencia —que usa otras conexiones— esperaba ese
bloqueo indefinidamente.

No fue un fallo del cambio: fue el cambio haciendo visible una dependencia que estaba
oculta. Esos tests asumían que el store confirmaba por ellos. Se adaptaron añadiendo el
commit que ahora les corresponde (18 sitios), marcado como `EXPECTED_POLICY_CHANGE`.

También cayó `test_round_trip_exacto_por_el_contrato`, que afirmaba
`leido.updated_at == original.updated_at`. Con 1A eso ya no puede ser cierto; ahora exige que
el instante persistido difiera del que trajo el llamante y conserve zona horaria.

---

## 3 · MIGRACIÓN 029 `[VERIFICADO]`

`CHECK (length(btrim(source_message_id)) > 0)` sobre `buyer_context_revisions`, idempotente
vía `pg_constraint` (`ADD CONSTRAINT` no admite `IF NOT EXISTS`).

**No se editó la 028**: está en `main` y reescribir una migración publicada rompe el supuesto
de que el historial es inmutable.

Probada contra Postgres real por el aplicador de producción: aplica tras la 028, es
idempotente, rechaza `""` y `"   "`, y deja pasar un id normal.

---

## 4 · POSTGRES REAL

```
motor   PostgreSQL 15.4 (postgis/postgis:15-3.3)     producción es 17.6
base    e32_test — dedicada, aislada
```

`TEST_DATABASE_URL` obligatoria, sin fallback a producción, con aborto si la URL contiene
`supabase.com` o `pooler`.

**Ni la 028 ni la 029 se aplicaron en producción.**

---

## 5 · MUTACIONES `[VERIFICADO]`

```
updated_at vuelve a la comparación canónica   → caen 2 tests de 1A
el store vuelve a confirmar sobre db=          → cae el de rollback del llamante
se quita la guarda de message_id vacío         → caen los 4 de 1C en Python
```

`app/buyer/store.py` restaurado y verificado tras cada una.

Las mutaciones §18.4-6 (saltarse Fair Housing, TURN_ONLY→DURABLE, quitar detección de
conflicto semántico) **no se ejecutaron**: no hay código que mutar todavía.

---

## 6 · SUITES

```
buyer store + unidad + precondiciones   44 exit 0
backend sin motor (como CI)          1 736 exit 0   (41 saltados)
frontend                                 0 ficheros tocados
```

---

## 7 · LO QUE NO SE CONSTRUYÓ — el grueso de E3.2

```
§2  arquitectura del updater (extract → sanitize → apply → store)
§3  BuyerMutationV0 · SET/CLEAR/NOOP · DURABLE/TURN_ONLY/AMBIGUOUS
§4  los campos autorizados a mutar
§5  la barrera determinista de Fair Housing
§6  routing situacional (durable vs turn-only vs ambiguo)
§7  la costura de extracción con structured output
§8  mapeo a EvidenceRefV0
§9  field_evidence por path
§10 semántica de correcciones
§11 resolución de conflictos con rebase por touched_paths
§12 idempotencia del pipeline completo
§13 shadow wiring tras add_messages
§14 feature flag + gate de esquema
§15 semántica de error en shadow
```

**Nada de esto está a medias: no está empezado.** No hay código muerto ni costuras
parciales que limpiar.

### Caracterización hecha, que E3.2 hereda `[VERIFICADO]`

- **`app/fair_housing.py` NO sirve como barrera de entrada.** `detectar_steering()` caza
  veredictos de idoneidad de barrio en **salidas**; su propio docstring dice que no es un
  censor de palabras y que sirve para flaguear, no para bloquear. Confirma la advertencia del
  prompt: no asumirla como sanitizador del Buyer.
- **La barrera determinista real del carril legacy es `app/preferencias.py::_sanitizar`**:
  whitelist **cerrada** `encaje.DIMENSIONES` (8 dimensiones) + enum cerrado `_OPERACIONES`.
  Es el patrón correcto a reutilizar, pero está tipada a la forma legacy (dict de
  dimensiones), no a paths de `BuyerContextV0`. El Buyer necesita su propia barrera con el
  mismo principio.
- `extraer_preferencias(list[str])` mezcla historial y pierde identidad de mensaje —
  caracterizado en F3.0a. Sigue siendo autoridad **solo** del carril legacy.

---

## 8 · GATE

```
E3.2   HOLD
```

Se cumplen 3 de los ~22 puntos del checklist: los tres de precondiciones, más
`migración 028/029 NOT APPLIED in production`. El resto depende de código que no existe.

**No es FAIL:** no hay bypass, ni regresión, ni atributo protegido que pueda persistirse —
porque no hay ningún camino que persista nada todavía. El wiring productivo sigue en cero.

### Recomendación

Partir E3.2 en dos unidades. La frontera natural es la que este trabajo ya dejó marcada:

```
E3.2a   precondiciones + migración 029          ← esta rama, lista para PR
E3.2b   updater + Fair Housing + conflictos + shadow wiring
```

La razón no es de esfuerzo, es de revisión: la barrera de Fair Housing y el routing
situacional necesitan una revisión adversarial propia —igual que la tuvo AUTH-READ-GATE— y
mezclarlos con un refactor transaccional hace que ninguna de las dos reciba la atención que
pide.

---

## 9 · PUNTO DE REENTRADA

E3.2b empieza con las tres precondiciones ya cerradas y con la caracterización de §7 hecha.
Lo primero a decidir: si la barrera del Buyer reutiliza `encaje.DIMENSIONES` para
`place_preferences` o define su propia whitelist cerrada.

Sigue abierto de E3.1b, sin tocar: **cómo se identifica una `place_preference` sin usar
posición de array** (§9 del prompt dice STOP antes de inventarlo).
