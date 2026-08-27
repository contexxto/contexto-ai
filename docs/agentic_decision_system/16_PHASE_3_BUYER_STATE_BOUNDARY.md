# 16 · E3.2b.0 — BUYER STATE BOUNDARY · **CARACTERIZACIÓN, sin decisiones congeladas**

```
BASELINE   662a269a5bb6920775d0de8d9a3d70c2cc0bee60   (origin/main verificado, sin avance)
RAMA       feat/f3-buyer-state-boundary

ENTREGADO   §0 prestart · §1 caracterización
PENDIENTE   §3 matriz · §14 boundary.py · §16-17 tests · D-B1..D-B9

GATE        HOLD — sin decisiones congeladas todavía
```

> Esta unidad entrega **la caracterización que la matriz necesita como entrada**, no la
> matriz. Las nueve decisiones D-B1..D-B9 siguen abiertas a propósito: tres condiciones de
> STOP del §19 se materializaron y ninguna debe resolverse improvisando.

---

## 1 · FORMA REAL DEL CONTRATO `[VERIFICADO]`

```
BuyerContextV0
  objective              Objective            enum CERRADO: buy | rent | invest | unknown
  financial.budget_max   Money | None
  property_requirements
    bedrooms_min         int | None
    area_m2_min          float | None
    pets_allowed_required bool | None
    accessibility_requirements  tuple[str, ...]      ← texto libre
  place_preferences      tuple[PlacePreference, ...]
  mobility.commute_anchors  tuple[CommuteAnchorV0, ...]    E3.4
  hard_constraints / soft_preferences / tradeoffs           E3.3 / E3.5
  stage                  str | None                         E3.6 · texto libre
  field_evidence         tuple[FieldEvidence, ...]

Money            amount: Decimal (REQ) · currency: str (REQ, sin enum, sin default)
PlacePreference  dimension: str (libre) · direction: Direction (more|less|unspecified)
FieldEvidence    field: str (libre) · evidence: EvidenceRefV0
```

**Cuatro campos escribibles-por-contrato son texto libre**: `accessibility_requirements`,
`PlacePreference.dimension`, `Money.currency`, `FieldEvidence.field`. Que el contrato lo
permita no autoriza al updater — es exactamente la distinción del §2.

---

## 2 · TRES CONDICIONES DE STOP MATERIALIZADAS `[VERIFICADO]`

### A · `accessibility_requirements` no tiene vocabulario NI consumidor

Barrido de `app/` (excluyendo `contracts/` y tests): **cero apariciones**. No existe
`step_free_access` ni catálogo equivalente en ningún sitio del repo.

El §11 lo anticipa: *"si no hay vocabulario existente y respaldado, marcar el path NOT
WRITABLE y dejar la decisión para una unidad posterior"*. Inventar una ontología de
accesibilidad sin datos ni consumidor sería crear vocabulario que nadie puede verificar —
y en un campo donde el error tiene consecuencias legales.

**Indicación fuerte: `NOT WRITABLE EN E3.2b.0`.** No congelado.

### B · `place_preferences` tampoco tiene consumidor, y `dimension` es texto libre

Barrido: **cero consumidores** fuera del contrato. Eso tiene dos consecuencias opuestas y
conviene no mezclarlas:

- **A favor de la opción A** (identidad = `dimension`): no hay consumidor que romper, así
  que congelar "una preferencia activa por dimensión" no rompe nada hoy.
- **En contra de habilitarlo**: habilitar escritura crea estado durable que **nada downstream
  puede usar todavía**. El §7 advierte justo eso — la whitelist debe describir capacidades
  que podamos razonar, no todo lo que el usuario pueda desear.

Y `dimension: str` sin whitelist significa que habilitarlo **exige** decidir primero su
vocabulario cerrado. No es un path que se pueda abrir "tal cual".

### C · `Money.currency` es obligatorio, `str`, sin enum ni default

"presupuesto 900" no puede construir un `Money` sin moneda. El §12 prohíbe inferirla por
locale o contexto, y no existe fuente determinista congelada que la herede.

Además la propia `currency` es texto libre: aunque la moneda venga explícita, el updater no
puede aceptar cualquier cadena. Hace falta un enum cerrado, y **el contrato no lo trae**.

**Indicación: `budget_max` solo escribible con moneda explícita Y contra un enum cerrado que
esta unidad tendría que definir.** No congelado.

---

## 3 · `encaje.DIMENSIONES` — el mapeo no es uno a uno `[VERIFICADO]`

```
legacy                    dónde caería en BuyerContextV0
tipo_inmueble             sin path — el contrato no modela tipo de inmueble
presupuesto_max           financial.budget_max          (pero legacy es número pelado, no Money)
dormitorios               property_requirements.bedrooms_min   ⚠ legacy es EXACTO, el contrato es MIN
acepta_mascotas           property_requirements.pets_allowed_required
caminable                 place_preference
transporte                place_preference
area_verde                place_preference
tranquilidad              place_preference — ver abajo
```

Dos desajustes que no son de nombre sino de semántica:

- **`dormitorios` legacy es EXACTO** ("los que pidió, no N o más") y el contrato dice
  `bedrooms_min`. Copiar la dimensión sin más cambiaría el significado del dato.
- **`presupuesto_max` legacy es un número sin moneda**; `Money` la exige. El puente entre los
  dos carriles no es directo.

Y **`tranquilidad`** es el caso que el §7 marca: reintroducirla como estado durable crearía
una capacidad que hoy no podemos medir ni defender. Indicación: no escribible.

**Conclusión de D-B9 (indicada, no congelada): `DIMENSIONES` sirve como REFERENCIA de
vocabulario para `place_preferences`, no como whitelist a copiar.**

---

## 4 · LO QUE FALTA — y por qué no se improvisó

```
D-B1  qué paths son writable                    ABIERTA
D-B2  tipo exacto por path                      ABIERTA
D-B3  dominio cerrado por path                  ABIERTA
D-B4  operaciones por path (SET / CLEAR)        ABIERTA
D-B5  normalización determinista                ABIERTA
D-B6  semántica de NO MATCH                     indicada: NO PERSIST (§2), sin implementar
D-B7  identidad de place_preferences            ABIERTA · ver §2B
D-B8  accessibility escribible o diferido       indicada: DIFERIR · ver §2A
D-B9  reutilización de DIMENSIONES              indicada: solo referencia · ver §3
```

Ninguna está congelada. La caracterización acota las opciones; congelarlas es el trabajo de
la siguiente sesión, con contexto entero.

**No se escribió `app/buyer/boundary.py`.** Escribir la implementación antes de cerrar la
matriz invertiría el orden que esta unidad existe para imponer.

---

## 5 · ESTADO

```
prestart              PASS   origin/main sin avance · worktree nuevo · baseline verde
caracterización       PASS
matriz                NO EMPEZADA
boundary.py           NO EMPEZADO
tests adversariales   NO EMPEZADOS
mutaciones            NO EJECUTADAS

cambios en app/       0
cambios en migrations/ 0
cambios en frontend/   0

GATE E3.2b.0          HOLD
```

## 6 · PUNTO DE REENTRADA

Sesión nueva desde este worktree o uno equivalente. Empezar por **D-B8, D-B9 y D-B7**, que
son las que la caracterización ya deja casi resueltas, y solo después D-B1..D-B5.

La pregunta que ordena el resto: **¿qué paths tienen hoy un consumidor capaz de usarlos?**
Los tres candidatos con texto libre —accessibility, place_preferences, currency— no lo
tienen, y esa ausencia es un argumento a favor de un V0 más estrecho de lo que sugiere la
lista de campos candidatos del §4 del prompt.
