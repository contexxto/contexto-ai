# 06 — PHASE 0 TRUST GATE REPORT

**Fecha:** 24 de agosto de 2026
**Ejecutor:** Claude Code (sesión del 2026-08-24)
**Plan de referencia:** `Contexto Agentic Decision System — Execution Plan 1.0`, FASE 0
**Alcance autorizado:** E0.1–E0.5 únicamente. Sin Contracts, sin harnesses, sin features.

---

## 0. Resumen

Los cinco cambios de código están hechos, probados y commiteados. **Tres de los cinco gates
quedan cerrados con evidencia; dos quedan parciales**, y lo que les falta no es ingeniería:
son tres interruptores de consola y una corrida supervisada contra la base.

Recomendación al final del documento, en §9.

Un hallazgo cambia el diagnóstico de la auditoría: **la tubería de Overture no estaba
desactualizada, estaba rota.** El release que el script tenía fijado ya no existe en S3.
Detalle en §5, E0.2.

---

## 1. Identificación

| Campo | Valor |
|---|---|
| Repositorio | `C:\Users\DETPC\Desktop\Contexto-AI` |
| Rama | `main` |
| Commit inicial | `937f587f886783ad835cdf862eda30e4ea364848` |
| Commit final | `53f29a27f6787fd564c82032de4998c5a7a0e3c6` |
| Commits creados | 6 |
| Archivos cambiados | 16 (+849 / −73) |
| Suite al empezar | 795 de 796 (**1 fallo preexistente**) |
| Suite al terminar | **829 de 829**, exit 0 |
| Estado en `origin/main` | **6 commits sin pushear** — ver §7 |

### Por qué `main` y no una rama

`00_START_HERE` §9.9 sugiere commits separados y §10 pide reportar *branch*. No se creó rama
porque **este working tree está compartido entre sesiones concurrentes** (durante la ejecución
había otros dos worktrees activos de otras sesiones); crear una rama le cambia la rama a todas.
Se trabajó en `main` commiteando por pathspec explícito, sin `git add -A`, sin tocar los
archivos de despacho ajenos que estaban sin commitear.

---

## 2. Commits

| Commit | Unidad | Asunto |
|---|---|---|
| `badd05b` | — | `test: alinear test del mark con el Brand Kit v2026.1` |
| `f850428` | E0.5 | `ci: gate de pruebas que bloquea` |
| `d6a9896` | E0.1 | `fix(seguridad): exigir X-API-Key en POST /api/v1/assets/` |
| `5081eaf` | E0.3 | `fix(procedencia): la caminabilidad dice una sola verdad` |
| `ab93153` | E0.4 | `feat(encaje): score_version y fuera las heurísticas sin fuente` |
| `53f29a2` | E0.2 | `fix(pois): descubrir el release de Overture y avisar cuando falle` |

### Archivos

**Código de aplicación**
`app/encaje.py` · `app/routers/assets.py` · `app/routers/chat.py`

**Scripts e infraestructura**
`scripts/foso_pois_spike.py` · `scripts/refresco_pois.cmd` · `.github/workflows/pruebas.yml` · `.env.example`

**Tests nuevos**
`tests/test_escritura_catastro_protegida.py` · `tests/test_procedencia_caminabilidad.py` ·
`tests/test_scoring_sin_heuristicas.py` · `tests/test_overture_release.py`

**Tests actualizados**
`tests/test_encaje.py` · `tests/test_orden_encaje.py` · `tests/test_orden_candidatos.py` ·
`tests/test_comparar.py` · `tests/test_generar_qrs.py`

---

## 3. Dos hallazgos previos a tocar código

### 3.1 La suite no estaba verde en HEAD

La auditoría (doc 01) reporta *"795 pasan"*. Son 795 **de 796**:
`tests/test_generar_qrs.py::test_sphere_escala_y_uid_unico` fallaba desde el 2026-08-20, cuando
`32d6110` (migración de marca) reemplazó el SVG del mark y dejó el test esperando los ids de
gradiente de la marca anterior.

No es un fallo de F0, pero **bloqueaba E0.5**: un gate bloqueante sobre una suite roja no se
puede activar. Se corrigió primero, en commit aparte (`badd05b`), alineando el test con la
propiedad que el mark actual sí garantiza. Es la primera vez que la suite está completa en verde.

### 3.2 `main` despliega solo, sin pruebas

`docs/CONTEXTO_AI_ARQUITECTURA.md:303` lo documenta literal: `auto-deploy SIN pruebas ⚠️`.
Cada push a `main` sale a Render en ~4 minutos sin red de seguridad.

Esto invirtió el orden de ejecución: se ejecutó **E0.5 primero** para que E0.1–E0.4 salieran con
gate, en vez del orden del Plan §19 (E0.1 → E0.3 → E0.4 → E0.5 → E0.2). El Plan declara que E0.5
no tiene dependencias, así que adelantarla no viola ninguna; el propio doc 04 usa este argumento
(*"por eso 0.5 va antes"*). **Decisión aprobada por Carlos antes de ejecutar.**

---

## 4. Estado por unidad

| Unidad | Estado | Lo que falta |
|---|---|---|
| E0.1 — Proteger escritura de activos | ✅ **PASS** | — |
| E0.3 — Procedencia de caminabilidad | ✅ **PASS** | — |
| E0.4 — score_version + heurísticas fuera | ✅ **PASS** | — |
| E0.5 — CI gate | ⚠️ **PARCIAL** | 2 interruptores de consola |
| E0.2 — Refresh de POIs | ⚠️ **PARCIAL** | 1 corrida supervisada + sacarlo del PC |

---

## 5. Unidad por unidad

### E0.1 — Proteger la escritura de activos ✅ PASS

**Problema observado en HEAD.** `app/routers/assets.py:2024` — `create_asset(payload,
background, db)`, sin guardia. El daño no era solo insertar filas: el endpoint encola
`_recompute_walk_score`, que llama a Overpass y a Google Routes/Places. **Un desconocido podía
hacernos gastar en APIs de pago, sin tope y sin rate limit.**

**Inventario de la superficie de escritura**, obtenido preguntándole a FastAPI por las
dependencias que resolvió al registrar cada ruta (no por grep):

| | Antes | Después |
|---|---:|---:|
| Endpoints de escritura | 37 | 37 |
| Protegidos | 30 | **31** |
| Sin guardia | 7 | 6 |

Los 6 que siguen abiertos son el flujo público del comprador, y lo son a propósito:
`handoff`, `handoff/mensaje`, `handoff/push` (con `get_optional_user`), `lead-contacto`
(documentado: *"Público — es el propio comprador"*), `chat/comparar` y `assets/mapa/comando`
—este último no escribe en base y está acotado a 40/min—. Cerrarlos rompería la acción final
del MVP (D8 del Plan).

**Solución.** `dependencies=[Depends(verify_api_key)]`, el mismo patrón que ya usaban sus
hermanos de ingesta (`/ingest`, `/ingest/batch`, `/similar`).

**Por qué no rompe nada:** `scripts/hidratar_activos.py:152` —el consumidor real, el de la carga
masiva— **ya enviaba el header `X-API-Key`**. La credencial viajaba desde siempre y nadie la
miraba.

**Tests.** `tests/test_escritura_catastro_protegida.py` (4). No repite lo que ya cubre
`test_auth.py` (la función aislada): comprueba que las **rutas la declaren**. Incluye una red de
regresión sobre toda la escritura de `/assets/` con lista blanca explícita, para que abrir un
endpoint en el futuro exija justificarlo por escrito.

**Antes/después.** El mismo test sobre `937f587`: **2 fallos**, con el mensaje
*"POST /api/v1/assets/ quedó sin guardia: vuelve a aceptar escritura anónima"*. Con el fix: 4 pasan.

**Recomendación no incluida** (para no mezclar alcances): este endpoint sigue sin
`@limiter.limit`, a diferencia de `/ingest` (20/min) y `/ingest/batch` (5/min).

---

### E0.3 — Procedencia de caminabilidad ✅ PASS

**Problema observado en HEAD.** `app/encaje.py:209` afirmaba `"OpenStreetMap"` incondicionalmente.
El `walk_score` nace heurístico y solo se sobrescribe con OSM si Overpass responde; cuando no,
el motor seguía reclamando una medición inexistente.

**Lo que hacía invisible el defecto:** el dato correcto ya estaba en todas partes menos en el
eslabón que importaba.

| Pieza | Estado en HEAD |
|---|---|
| Columna `activos_inmutables.walk_score_fuente` | ✅ existe (`'osm'` / `'heuristico'`) |
| Query de `chat.py:453` | ✅ ya la traía como `caminabilidad_fuente` |
| Card (`_card_from_row`) | ✅ ya la usaba |
| Ficha del anuncio (`_scores_fuente`) | ✅ ya distinguía |
| **`_senales_encaje` → motor** | ❌ **no la pasaba** |

**Solución.** Una línea en `_senales_encaje` para transportar la procedencia, y `_score_caminable`
traduciéndola. Sin procedencia registrada se degrada a estimación, nunca se asciende a OSM;
una procedencia futura sin mapear degrada igual.

**Los tres caminos con un solo fix.** El bloque autoritativo (`encaje_contexto.py:216`) deriva su
rótulo de `razon['fuente']`, así que hereda la corrección — y es justo el texto que el modelo lee
antes de redactar.

**Hallazgo.** Este bug **ya se había corregido una vez**, el 2026-07-03, pero solo del lado de la
ficha (ver la cabecera de `test_scores_fuente.py`: *"el rótulo MENTÍA"*). El mismo error vivía en
dos lugares y se arregló uno. El test nuevo añade el invariante que faltaba: ficha y motor leen
la misma columna y no pueden discrepar.

**Tests.** `tests/test_procedencia_caminabilidad.py` (11), incluido uno que verifica que E0.3
**no toca el número** — corrige el rótulo, no el peso.

**Antes/después.** Sobre `937f587`: **7 fallos**, entre ellos
*"Con walk_score_fuente='heuristico' la ficha y el motor discrepan sobre si hubo medición:
ficha=False, motor=True"*. Con el fix: 11 pasan.

---

### E0.4 — score_version y heurísticas fuera del scoring ✅ PASS

**Problema observado en HEAD, medido:**

| Caso | Antes | Después |
|---|---:|---:|
| Dos inmuebles idénticos salvo ruido (BAJO vs ALTO) | **50 puntos de diferencia** | **0** |
| Dos idénticos salvo vegetación (90% vs 10%) | **80 puntos** | ambos `None` |
| Parque medido (4 min vs 25 min) | 100 vs 20 | **100 vs 20** (intacto) |
| `score_version` en la salida | ausente | `encaje-v0` |

Esa diferencia salía de `scores_heuristicos.scores_para`: una tabla de 7 sectores de Quito
escrita a mano más un desplazamiento derivado del hash SHA-256 de la dirección. `tranquilidad`
era una de las 8 dimensiones de la lista blanca, con peso 1.0.

**Importa más allá de la honestidad:** la factualidad es una de las métricas del benchmark que
decide si la tesis vive. Con esto dentro, la condición D habría medido en parte la calidad de una
invención.

**Qué se retira y qué no.**
- `tranquilidad` → `insufficient_evidence`. Única fuente: la tabla.
- `area_verde` → **solo el camino de vegetación**. El parque concreto (`parque_min`, minutos a pie
  del mapa) sigue puntuando. La dimensión no se apaga entera porque eso tiraría el dato bueno con
  el malo.
- tráfico → no había nada que retirar; nunca fue dimensión puntuable. Queda un test para que no
  se añada algún día por simetría.

Las dimensiones se conservan **visibles**: *"Buscabas tranquilidad · no tenemos medición de ruido
aquí"*, con `aporta=False`. D3 lo pide así: "no lo sabemos" es información; el silencio no.

**`SCORE_VERSION = "encaje-v0"`.** Se documenta en el código qué cambios obligan a subirla. v0
nace ya sin heurísticas; el scoring anterior nunca tuvo versión, así que no hay forma de comparar
contra él salvo por fecha.

#### ⚠️ Efecto secundario que Carlos debe conocer

Declarar `tranquilidad` mete peso en el **denominador de la cobertura** que ninguna ficha puede
llenar. Consecuencia: **cuando el comprador pide tranquilidad, todos los inmuebles quedan
moderados por evidencia**, incluso los de ficha completa. El orden relativo no cambia (afecta a
todos por igual), pero los números absolutos bajan.

Es honesto —si no podemos evaluar algo que la persona pidió, la confianza en el match *es* menor—
pero conviene saberlo antes de comparar scores de antes y después. Tiene test propio:
`test_declarar_tranquilidad_topa_la_cobertura_alcanzable`.

**Tests.** `tests/test_scoring_sin_heuristicas.py` (16). **10 tests existentes cambiaron de
expectativa, ninguno por un bug**: todos usaban el ruido como discriminante y ahora usan
caminabilidad o transporte. Se documentó el porqué en cada uno.

---

### E0.5 — CI gate ⚠️ PARCIAL

**Problema observado en HEAD.** `.github/workflows/` tenía `keepalive.yml` y `vigia-salud.yml`.
**Ninguno ejecutaba `pytest`.**

**Solución.** `.github/workflows/pruebas.yml` — suite completa en push a `main`, en pull request y
a mano. Python 3.11, igual que el Dockerfile.

**Hallazgo de la verificación.** Se probó sobre un worktree limpio (sin `.env`, como el CI):
**27 archivos de test ni siquiera se recolectan.** `app/config.py` declara `postgres_db`,
`postgres_user` y `postgres_password` sin default, así que `Settings()` revienta con
`ValidationError` antes de correr una sola prueba. El job exporta las tres con valores inertes
—las pruebas son offline y no abren conexión—. Un workflow escrito a ciegas habría fallado en su
primera corrida por una razón ajena al código.

**Verificado en las dos direcciones:** suite sana → exit 0; con un test roto inyectado en un
worktree desechable → **exit 1**.

#### Por qué queda PARCIAL

**Este workflow no detiene el auto-deploy de Render por sí solo.** Render observa la rama
directamente; GitHub Actions no es su portero. Faltan dos acciones que no son de código:

1. **Render** → Settings → Build & Deploy → activar **"Wait for CI to pass before deploying"**.
2. **GitHub** → Settings → Branches → branch protection en `main` marcando el check `pruebas`
   como requerido.

Hasta entonces, los tests dejaron de ser invisibles pero **siguen sin bloquear**. El gate F0 del
Plan §6 lista *"tests sin gate"* como condición de fallo, y en rigor sigue sin cumplirse.

---

### E0.2 — Refresh de POIs ⚠️ PARCIAL

#### El diagnóstico de la auditoría se queda corto

La auditoría dice *"release obsoleto"*. La verificación del 2026-08-24 contra el bucket real:

```
releases publicados hoy : 2026-07-22.0 · 2026-08-19.0
fijado en el script     : 2026-06-17.0  → cero objetos en S3
```

**Overture no conserva los releases viejos.** El prefijo fijado ya no existe. La tubería no
estaba desactualizada: **estaba rota, y en silencio**, porque leer un prefijo vacío devuelve cero
filas y cero filas no es un error para DuckDB. Ninguna corrida semanal reciente pudo traer un
solo POI de Overture, y el código de salida seguía diciendo `0`.

**Solución, tres partes.**

1. **El release se descubre.** Se lista el bucket por la API de S3 (un GET con `delimiter`; el
   `glob` de DuckDB no enumera prefijos y devuelve cero filas — probado). Se elige con `max()`,
   no con `[-1]`: **un test cazó ese bug** en la primera versión. `OVERTURE_RELEASE` en el entorno
   lo fija a mano para reproducir una corrida pasada.
2. **Cero filas pasa a ser error duro.** El bbox de un mercado activo siempre tiene comercios. Sin
   este corte el script seguía hasta el cierre de POIs y daba la corrida por buena — que es
   exactamente cómo el fallo pasó semanas inadvertido. Una recarga vacía cerraría los POIs
   existentes por ausencia.
3. **El fallo avisa.** Los códigos de salida tenían señal desde julio, pero terminaban en `logs\`.
   Ahora un error duro manda correo, y `refresco_pois.cmd` avisa al agotar sus reintentos
   (`--solo-avisar`). Sin `RESEND_API_KEY` o `ALERTA_OPS_EMAIL` lo dice por consola y no falla.

**Verificado:** descubrimiento contra el bucket real → `2026-08-19.0`; la variable de entorno
tiene precedencia; `--solo-avisar` corre sin configuración sin romperse.
**Tests:** `tests/test_overture_release.py` (8), sin tocar la red.

#### Por qué queda PARCIAL

1. **No se ejecutó una corrida completa contra la base.** Requiere descargar Overture y reescribir
   `pois_propios` en producción; este gate no autoriza tocar datos vivos. Es la *"corrida completa
   reproducible"* que pide el Plan §6 como evidencia.
2. **Sigue dependiendo del PC del fundador** (tarea de Windows, lunes 17:00). Sacarlo de ahí es
   infraestructura —runner de CI o cron en Render—, no cirugía sobre el script.

---

## 6. Contradicciones detectadas

**C-A · Alcance de E0.2 divergente entre Plan 1.0 y doc 04.**
El Plan §6 pide tres cosas y lo marca **M**: parametrizar release + *"mover el refresh fuera de
dependencia exclusiva del PC del fundador"* + logs/failure signal. El doc 04 lo parte en dos
unidades **S** (0.4 parametrizar, 0.7 alerta) y **no incluye** sacarlo del PC. Se ejecutó lo que
el código permite; la migración de ejecución queda escalada, no resuelta.

**C-B · El protocolo pide `branch`; el repo no admite ramas.** Resuelto trabajando en `main` por
pathspec. Ver §1.

**C-C · Auto-deploy sin gate.** Ver §3.2. Motivó el reorden de unidades.

**C-D · La suite reportada como verde no lo estaba.** Ver §3.1. Corrige la evidencia del doc 01.

**C-E · El diagnóstico de E0.2 subestima el defecto.** Ver §5. No es obsolescencia, es rotura.

**Ninguna contradice las decisiones D1–D9 del Plan.** D3 se aplicó tal como está congelada.

---

## 7. Impacto en producción y requisitos de configuración

### Nada de esto está desplegado todavía

**Los 6 commits están en `main` local, sin pushear.** Al pushear, Render desplegará en ~4 minutos.
Se dejó la decisión a Carlos precisamente porque no hay gate todavía (E0.5 parcial).

### Al desplegar, cambia el comportamiento observable

| Cambio | Efecto |
|---|---|
| `POST /api/v1/assets/` exige `X-API-Key` | Cualquier cliente sin la llave recibe 401. Los scripts conocidos ya la enviaban. **Verificar que `API_KEY` esté configurada en Render antes de pushear** — si estuviera vacía, el check se desactiva y la protección no aplica. |
| Ruido y vegetación fuera del scoring | **Los scores cambian**, y los rankings con ellos. Los inmuebles que el ruido penalizaba suben. Ver el efecto de cobertura en §5, E0.4. |
| Razones nuevas en las tarjetas | Aparece *"no tenemos medición de ruido aquí"* donde antes decía *"ruido estimado bajo"*. El frontend la pinta como cualquier razón no-alta; no requiere cambio de front. |
| Procedencia de caminabilidad | Deja de decir "OpenStreetMap" en los activos cuyo walk score es estimado. |

### Variables de entorno nuevas (ambas opcionales)

- `ALERTA_OPS_EMAIL` — destino de los avisos de fallo del refresco. Vacío = solo consola.
- `OVERTURE_RELEASE` — fija un release concreto. Vacío = se descubre el más reciente (lo normal).

Documentadas en `.env.example`.

### Sin migraciones

Ninguna. `walk_score_fuente` ya existía.

---

## 8. Riesgos y trabajo abierto

### Riesgos de lo entregado

1. **El cambio de scoring altera rankings en producción.** Es el efecto buscado, pero si alguien
   compara un score de antes con uno de después sin mirar `score_version`, sacará conclusiones
   falsas. Ahora hay con qué distinguirlos; antes no.
2. **`verify_api_key` no protege si `API_KEY` está vacía** (por diseño, para dev local). En
   producción debe estar configurada. Verificarlo antes de pushear.
3. **La corrida de POIs sigue sin probarse de extremo a extremo.** El descubrimiento del release
   funciona; el resto del camino (DuckDB → parquet → upsert) no se ejercitó.

### Lo que queda abierto del gate

| # | Qué | Quién | Esfuerzo |
|---|---|---|---|
| 1 | Render → "Wait for CI to pass before deploying" | Carlos | minutos |
| 2 | GitHub → branch protection en `main` con el check `pruebas` | Carlos | minutos |
| 3 | Confirmar `API_KEY` configurada en Render | Carlos | minutos |
| 4 | Una corrida completa de `refresco_pois.cmd` supervisada | Carlos + Claude | ~40 min |
| 5 | Sacar el refresco del PC del fundador | decisión de arquitectura | M |
| 6 | `ALERTA_OPS_EMAIL` en el `.env` local (si no, el aviso solo va a consola) | Carlos | minutos |

Los puntos 1–3 y 6 son de consola. El 4 necesita autorización explícita para escribir en
`pois_propios`. El 5 es la contradicción C-A y merece decisión, no ejecución automática.

### Recomendaciones fuera de alcance, no ejecutadas

- `@limiter.limit` en `POST /api/v1/assets/`, por consistencia con `/ingest`.
- Mover `verify_api_key` de `app/routers/chat.py` a `app/auth.py`. Hoy cinco routers importan una
  guardia de seguridad desde un router de chat. Es deuda conocida y toca la frontera que el doc 02
  quiere trazar; no se tocó para no mezclar con F0.

---

## 9. Recomendación

Contra el criterio de `00_START_HERE` §10 —*"F0 is complete only if all five units have evidence
of PASS"*— y el Gate F0 del Plan §6:

| Condición de fallo del Gate F0 | Estado |
|---|---|
| Escritura crítica anónima | ✅ resuelto |
| Provenance contradictorio | ✅ resuelto |
| Scoring contaminado por heurística sin fuente | ✅ resuelto |
| Pipeline territorial no reproducible | ⚠️ reproducible en código, sin corrida que lo pruebe |
| Tests sin gate | ⚠️ hay gate; no bloquea el deploy |

### `DO NOT ADVANCE`

**No por la calidad de lo entregado, sino porque dos gates dependen de acciones que no son mías.**

Los tres gates que protegen la *calidad del dato* —el que decide si el benchmark medirá algo
real— están cerrados con evidencia reproducible. Los dos que quedan protegen el *proceso*, y su
cierre son tres interruptores de consola y una corrida supervisada.

**Camino más corto a `ADVANCE TO CONTRACTS`:**

1. Verificar `API_KEY` en Render y pushear los 6 commits.
2. Activar el gate en Render y la branch protection en GitHub → **cierra E0.5**.
3. Correr `refresco_pois.cmd` una vez, supervisado, y comprobar que `pois_propios` se repuebla
   desde el release vigente → **cierra E0.2**.

Con eso, F0 queda cerrado sin trabajo de ingeniería adicional. La decisión sobre sacar el refresco
del PC del fundador (C-A) puede tomarse después: no bloquea el benchmark, pero sí la promesa de
*"la capa puede refrescarse sin intervención manual del portátil"*.

---

## 10. Parada

Según `00_START_HERE` §11, la ejecución **se detiene aquí**. No se inicia Contracts / Fase 1 hasta
la revisión de Carlos y ChatGPT sobre este reporte.
