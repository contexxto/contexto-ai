# 16 · E3.2b.0 — BUYER STATE BOUNDARY

```
BASELINE   662a269a5bb6920775d0de8d9a3d70c2cc0bee60   (origin/main verificado, sin avance)
RAMA       feat/f3-buyer-state-boundary

ENTREGADO   caracterización · D-B1..D-B9 congeladas · boundary.py · 161 tests · M1-M6

backend     1 901 exit 0        frontend  0 ficheros
GATE        PASS
```

> La caracterización de §1-§3 se conserva porque es **lo que justifica** las decisiones. Las
> nueve están congeladas en §7 y la frontera está implementada y probada.

---

---

# SNAPSHOT DE CARACTERIZACIÓN — previo a congelar D-B1..D-B9

> **§1-§6 son evidencia histórica.** Describen el estado *antes* de que las nueve decisiones
> se congelaran, y se conservan porque son **lo que las justifica**: sin ellas, D-B7 y D-B8
> parecerían prudencia arbitraria en vez de la consecuencia de que ninguno de esos paths
> tiene consumidor ni vocabulario.
>
> El estado **actual** está en §7-§12. Donde estas secciones digan "abierta", "no congelado"
> o "no se escribió", léase *"no lo estaba entonces"*.

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

Money            amount: Decimal (REQ) · currency: str (REQ) con pattern ^[A-Z]{3}$
PlacePreference  dimension: str (libre) · direction: Direction (more|less|unspecified)
FieldEvidence    field: str (libre) · evidence: EvidenceRefV0
```

**Tres campos escribibles-por-contrato son texto libre**: `accessibility_requirements`,
`PlacePreference.dimension` y `FieldEvidence.field`. Que el contrato lo permita no autoriza
al updater — es exactamente la distinción del §2.

`Money.currency` es un cuarto caso y **es distinto**: lleva `pattern=^[A-Z]{3}$`, así que no
es texto libre. Pero eso **restringe la forma, no el dominio**: `ZZZ` y `EUR` pasan igual que
`USD` (verificado ejecutando el contrato). La conclusión no cambia —el updater necesita un
enum cerrado— pero el motivo sí: no es que falte restricción, es que la que hay no distingue
una moneda real de tres letras cualesquiera.

---

## 2 · TRES CONDICIONES DE STOP MATERIALIZADAS `[VERIFICADO]`

### A · `accessibility_requirements` no tiene vocabulario NI consumidor

Barrido de `app/` (excluyendo `contracts/` y tests): **cero apariciones**. No existe
`step_free_access` ni catálogo equivalente en ningún sitio del repo.

El §11 lo anticipa: *"si no hay vocabulario existente y respaldado, marcar el path NOT
WRITABLE y dejar la decisión para una unidad posterior"*. Inventar una ontología de
accesibilidad sin datos ni consumidor sería crear vocabulario que nadie puede verificar —
y en un campo donde el error tiene consecuencias legales.

**Indicación de entonces: `NOT WRITABLE`.** Congelada después como **D-B8** (§7).

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

Y aunque la moneda venga explícita, `^[A-Z]{3}$` no basta: acepta `ZZZ` y `EUR` igual que
`USD`. Valida forma, no dominio. Hace falta un enum cerrado del updater, y **el contrato no
lo trae** — ni debería, porque el contrato es general y el updater es una frontera más
estrecha.

**Indicación de entonces:** `budget_max` solo con moneda explícita y enum cerrado propio.
Congelada después como **D-B3** — el enum es `BuyerCurrencyV0 = USD | MXN` (§7).

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

**Congelada después como D-B9:** `DIMENSIONES` es REFERENCIA de vocabulario, no whitelist
a copiar (§7).

---

## 4 · LO QUE FALTABA AL CERRAR LA CARACTERIZACIÓN

```
D-B1  qué paths son writable                    abierta entonces
D-B2  tipo exacto por path                      abierta entonces
D-B3  dominio cerrado por path                  abierta entonces
D-B4  operaciones por path (SET / CLEAR)        abierta entonces
D-B5  normalización determinista                abierta entonces
D-B6  semántica de NO MATCH                     indicada: NO PERSIST
D-B7  identidad de place_preferences            indicada: diferir · ver §2B
D-B8  accessibility escribible o diferido       indicada: diferir · ver §2A
D-B9  reutilización de DIMENSIONES              indicada: solo referencia · ver §3
```

**Las nueve están congeladas en §7.** En aquel momento no lo estaban, y `boundary.py` no
existía: escribir la implementación antes de cerrar la matriz habría invertido el orden que
esta unidad existe para imponer. Ese orden se respetó.

---

## 5 · ESTADO DE LA FASE DE CARACTERIZACIÓN

```
prestart              PASS   origin/main sin avance · worktree nuevo · baseline verde
caracterización       PASS
```

Lo que en su momento figuró aquí como *NO EMPEZADO* —matriz, `boundary.py`, tests y
mutaciones— está entregado y se documenta en §7-§11. El gate final es **PASS**.

## 6 · PUNTO DE REENTRADA HISTÓRICO — ya consumido

Este era el plan al cerrar la caracterización: empezar por D-B8, D-B9 y D-B7 y solo después
D-B1..D-B5. **Se siguió, y las nueve están cerradas en §7.**

Se conserva porque la pregunta que lo ordenaba resultó ser la correcta y sirve para las
unidades siguientes: **¿qué paths tienen hoy un consumidor capaz de usarlos?** Los tres
candidatos con texto libre no lo tenían, y esa ausencia es lo que justificó un V0 de cinco
paths en vez de siete.

> **El punto de reentrada ACTUAL es §12 · E3.2b.1.**

---

# ESTADO ACTUAL

---

## 7 · D-B1..D-B9 — CONGELADAS PARA V0

```
D-B1  writable      objective · financial.budget_max · bedrooms_min · area_m2_min
                    · pets_allowed_required                    (CINCO, y ninguno más)
      no writable   accessibility · place_preferences · mobility · hard/soft · tradeoffs
                    · stage · unresolved_questions · field_evidence como input
                    · buyer_id · context_revision · updated_at
D-B2  tipos         Objective · Decimal+enum · StrictInt · StrictFloat · sin campo (pets)
D-B3  dominios      BUY|RENT|INVEST · USD|MXN · >=1 · >0 finito · SET solo afirma
D-B4  operaciones   clases concretas; sin PATCH/MERGE/APPEND ni operation:str
D-B5  normalización ninguna — la frontera no interpreta lenguaje
D-B6  no-match      NO PERSIST, garantizado al construir el resultado
D-B7  place_prefs   DIFERIDO — sin consumidor y sin vocabulario
D-B8  accessibility DIFERIDO — sin ontología defendible
D-B9  DIMENSIONES   referencia, no whitelist
```

## 8 · API de `app/buyer/boundary.py`

```
BuyerCurrencyV0        USD | MXN
BuyerMutationV0        unión discriminada de 10 variantes
ruta_contractual(m)    la clase → el path del contrato. Un solo parámetro.
Disposicion            DURABLE | TURN_ONLY | AMBIGUOUS | REJECTED
ResultadoFrontera      solo DURABLE puede llevar mutación
autorizar(m) · no_persistir(disposicion, motivo)
```

**Garantías por FORMA, no por validación posterior:**

- Los atributos protegidos **no tienen dónde escribirse**.
- `SetPetsRequired()` no lleva campo: `False` no es representable.
- Los `Clear*` no llevan payload.
- `DURABLE` sin mutación y no-`DURABLE` con mutación **fallan al construir**.
- La ruta se deriva de la clase; la firma no ofrece por dónde pasar un destino.

## 9 · MUTACIONES M1-M6 `[VERIFICADO]`

```
M1  variante genérica en la unión     → caen los 2 tests de coherencia unión↔mapeo
M2  currency abierta por patrón       → caen EUR y ZZZ
M3  SetPetsRequired gana value: bool  → caen el meta-test y los de payload
M4  SetObjective acepta UNKNOWN       → cae el de UNKNOWN
M5  AMBIGUOUS puede llevar mutación   → caen los 3 de disposición
M6  ruta_contractual acepta la ruta   → cae el de firma cerrada
```

**M1 y M6 no cayeron en el primer intento, y eso encontró dos huecos reales.**

M1 destapó que **la unión y el mapeo de rutas podían divergir** sin que ningún test lo
notara. Inocuo hoy —`autorizar` rechaza lo que no está en el mapeo— pero deja dos listas que
describen lo mismo: quien añadiera una mutación legítima tocaría solo una, y el fallo
aparecería como un `REJECTED` inexplicable en vez de como un test rojo. Cerrado exigiendo que
sean el mismo conjunto en ambas direcciones.

M6 falló por estar mal construida: añadía un parámetro que nadie usaba, y eso no rompe
ninguna propiedad. La garantía real era que **la firma no ofrezca por dónde pasar un
destino**, y ahora hay un test que la fija.

## 10 · HALLAZGOS DE IMPLEMENTACIÓN `[VERIFICADO]`

**`Decimal` no estricto aceptaba `"900"`** y lo convertía. Eso es interpretar una cadena, y
D-B5 se lo reserva al extractor. Corregido con `strict=True`.

**`StrictFloat` admite `int` pero excluye `bool`.** Verificado, no supuesto: `50` entra como
`50.0` —es un float exacto— y `True` se rechaza pese a ser subclase de `int`. Es justo la
línea correcta, y hay un test que la documenta.

**Los docstrings sobreviven a `ast.unparse`.** El test de pureza se acusaba a sí mismo,
porque el módulo se explica nombrando lo que no usa. Se podan del AST — la misma trampa
texto-vs-estructura que persigue a esta rama desde AUTH-READ-GATE.

## 11 · GATE

```
E3.2b.0   PASS

boundary            161 tests exit 0
backend completo  1 901 exit 0
frontend              0 ficheros
```

Sin LLM, sin base, sin store, sin migraciones, sin producción.

## 12 · PUNTO DE REENTRADA · E3.2b.1

El extractor nace **debajo** de una frontera ya cerrada. Su contrato de salida es
`BuyerMutationV0`: no puede proponer un path, ni una operación, ni un valor fuera de dominio,
porque el tipo no lo admite.

Lo que E3.2b.1 debe traer es el routing situacional —durable / turn-only / ambiguous— y la
interpretación de lenguaje que esta unidad se prohibió a propósito.
