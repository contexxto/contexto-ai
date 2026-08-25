# 06 — PHASE 0 TRUST GATE REPORT

**Fecha:** 24 de agosto de 2026
**Ejecutor:** Claude Code (sesión del 2026-08-24)
**Plan de referencia:** `Contexto Agentic Decision System — Execution Plan 1.0`, FASE 0
**Alcance autorizado:** E0.1–E0.5 únicamente. Sin Contracts, sin harnesses, sin features.

> **Revisión 3 — FINAL.** Los cinco gates cerrados, mergeados a `main` y verificados contra
> producción. La revisión 1 reportaba `53f29a2`/6 commits/829 tests y la 2 `1fb5e7e`/10/846;
> ambas se escribieron antes de que E0.5 se pudiera probar de verdad. Los números de abajo
> salen de `git`, de `pytest` y de la API de GitHub sobre el estado final.

---

## 0. Resumen

**Los cinco gates cerrados con evidencia, mergeados a `main` y desplegados.**

Lo que más vale de esta fase no es la lista de arreglos: es que **el gate encontró dos defectos
en el propio trabajo del Trust Gate la primera vez que corrió**. Ambos compartían causa —código
que solo funcionaba porque el portátil del fundador tenía cosas que el runner no tiene— y ambos
habrían pasado inadvertidos sin CI. La afirmación "846 pruebas en verde" de la revisión 2 era
cierta **solo en esa máquina**. Está detallado en §3.3, y es el argumento más fuerte de todo el
documento a favor de que E0.5 existiera.

Además, **C-A queda resuelta y probada**: el refresco de POIs corrió en un runner gestionado y
escribió producción, con la correlación temporal medida.

Recomendación en §9.

---

## 1. Identificación

| Campo | Valor |
|---|---|
| Repositorio | `C:\Users\DETPC\Desktop\Contexto-AI` · `github.com/contexxto/contexto-ai` (público) |
| Rama local | `main` |
| Commit inicial | `937f587f886783ad835cdf862eda30e4ea364848` |
| **Commit final en `main`** | **`eeff14c9547f09d527c93bd3d0ef2d21cc556fde`** (merge del PR #119) |
| Commits creados | **12** (sin contar el merge) |
| Archivos cambiados | **22** (+1669 / −81) |
| Suite al empezar | 795 de 796 (**1 fallo preexistente**) |
| **Suite al terminar** | **847 de 847**, exit 0, 58 archivos |
| Estado en `origin/main` | **mergeado** vía PR #119, con `pytest` verde como condición |
| Rama del PR | `ci/trust-gate-f0` (conservada como referencia) |
| Protección de `main` | ruleset **`main protegida`**, `enforcement: active`, bypass vacía |
| Gate de despliegue | Render `contexto-ai-oregon` → `Auto-Deploy: After CI Checks Pass` |

> **Sobre la cifra de pruebas, para que nadie la persiga.** **847** es lo que había al cerrar F0
> (`eeff14c`) y ese número **no se toca**: es la medición de esta fase. Si hoy ves **869**, no hay
> contradicción que investigar — son los 22 tests de `tests/test_resolucion_api_url.py` que entraron
> con el PR #121 (hotfix de la URL muerta), posterior a F0 y ajeno a él. `847 + 22 = 869`. La base
> para FASE 1 es **869 sobre `30354cb`**, verificada en árbol limpio sin `.env`.

### `git status` al cierre

```
 M contenido/state/despacho_state.json      ← salida de la tarea de despacho, ajena a F0
?? contenido/despachos/DESPACHO_2026-08-24.md   ← ídem
?? docs/agentic_decision_system/01..05_*.md     ← los cinco docs de auditoría, ya estaban
                                                   sin trackear al empezar; no se tocaron
```

Ningún código de aplicación queda sin commitear.

### Por qué `main` y no una rama

`00_START_HERE` §9.9 sugiere commits separados y §10 pide reportar *branch*. No se creó rama
local porque **este working tree está compartido entre sesiones concurrentes** (durante la
ejecución había otros dos worktrees activos); crear una rama le cambia la rama a todas. Se
trabajó en `main` commiteando por pathspec explícito.

Para validar el CI sin usar `main` de conejillo, el HEAD se publicó en la rama remota
`ci/trust-gate-f0` con `git push origin HEAD:refs/heads/…`, que **no altera la rama local**.

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
| `8a290ff` | — | `docs: reporte del Trust Gate` (revisión 1) |
| `ea62b67` | E0.1 | `fix(seguridad): API_KEY ausente ya no abre las rutas en producción` |
| `bdd4b68` | C-A | `ci: el refresco de POIs sale del PC del fundador` |
| `1fb5e7e` | — | `docs: reporte del Trust Gate` (revisión 2) |
| `3958c7a` | E0.5 | `fix(pois): el script no mata al intérprete al importarse` ← **lo encontró el gate** |
| `6984b8b` | E0.5 | `fix(ci): el entorno de pruebas necesita las dependencias de scripts/` ← **ídem** |

Los dos últimos no estaban planificados. Salieron de las dos primeras corridas del CI, en rojo.

---

## 3. Hallazgos

### 3.1 La suite no estaba verde en HEAD

La auditoría (doc 01) reporta *"795 pasan"*. Son 795 **de 796**:
`tests/test_generar_qrs.py::test_sphere_escala_y_uid_unico` fallaba desde el 2026-08-20, cuando
`32d6110` (migración de marca) reemplazó el SVG del mark y dejó el test esperando los ids de
gradiente de la marca anterior. Bloqueaba E0.5 —un gate bloqueante sobre suite roja no se puede
activar—, así que se corrigió primero, en commit aparte.

### 3.2 `main` despliega solo, sin pruebas

`docs/CONTEXTO_AI_ARQUITECTURA.md:303` lo documenta literal: `auto-deploy SIN pruebas ⚠️`.
Esto invirtió el orden: se ejecutó **E0.5 primero** para que E0.1–E0.4 salieran con gate. El Plan
§19 declara que E0.5 no tiene dependencias, así que adelantarla no viola ninguna. Decisión
aprobada por el fundador antes de ejecutar.

### 3.3 El gate cazó dos defectos del propio Trust Gate

**Este es el hallazgo principal de la fase.** La primera vez que `pytest` corrió en un runner
—PR #119, commit `1fb5e7e`, el mismo HEAD que la revisión 2 declaraba "846 en verde"— terminó en
**rojo**. Dos veces seguidas, por dos causas distintas con la misma raíz.

**Fallo 1 (`1fb5e7e`).** `scripts/foso_pois_spike.py` cortaba con `sys.exit(1)` en el **cuerpo del
módulo** si faltaba `DATABASE_URL_OVERRIDE`. `tests/test_overture_release.py` importa ese módulo
para probar qué release de Overture se elige —decisión pura, sin red ni base—. En el portátil del
fundador el `.env` trae la variable y las ocho pruebas pasaban; en el runner no hay `.env`, así que
el import mataba al intérprete y el archivo entero **ni se recolectaba**. Arreglado en `3958c7a`
moviendo el corte a `exigir_credencial_de_base()`, que se llama al correr y no al importar.

> Efecto secundario del arreglo, y es el que más importa: `--solo-avisar` ya no necesita la
> credencial. Antes, si el refresco fallaba **porque** faltaba `DATABASE_URL_OVERRIDE`, el aviso
> moría por la misma causa que intentaba reportar.

**Fallo 2 (`3958c7a`).** El mismo módulo importa `duckdb` a nivel de módulo, y `duckdb` está fuera
de `requirements.txt` **a propósito** (Render sirve la API y no tiene por qué instalarlo; vive en
`requirements-pois.txt`). Como `requirements-dev.txt` era solo `requirements.txt` + pytest, el
runner se quedaba sin `duckdb` y el archivo moría otra vez en la recolección, ahora con
`ModuleNotFoundError`. Arreglado en `6984b8b` incluyendo `requirements-pois.txt` por referencia y
metiéndolo en la clave de caché del workflow.

**La raíz común:** las dos veces, código que funcionaba únicamente porque el `.venv` y el `.env`
de una máquina concreta tenían algo que ningún otro entorno tiene. Es exactamente la clase de
dependencia invisible que un gate de CI existe para matar, y la encontró en su primera corrida —
sobre el trabajo de quien escribió el gate.

**Lo que esto obliga a decir con todas las letras:** la afirmación *"846 pruebas en verde"* de la
revisión 2 **era dependiente del entorno**. No estaba comprobada donde importa. La cifra buena,
verificada en un árbol limpio sin `.env` y con las tres variables dummy de `pruebas.yml`, es
**847 de 847**.

---

## 4. Estado por unidad

| Unidad | Estado | Evidencia |
|---|---|---|
| E0.1 — Proteger escritura de activos | ✅ **PASS** | 401 medido contra producción |
| E0.2 — Refresh de POIs | ✅ **PASS** | corrida supervisada + corrida en runner |
| E0.3 — Procedencia de caminabilidad | ✅ **PASS** | 11 pruebas de regresión |
| E0.4 — score_version + heurísticas fuera | ✅ **PASS** | 16 pruebas de regresión |
| E0.5 — CI gate | ✅ **PASS** | prueba negativa: merge bloqueado |
| C-A — Refresco fuera del PC del fundador | ✅ **RESUELTA** | escritura correlacionada en el tiempo |

---

## 5. Unidad por unidad

### E0.1 — Proteger la escritura de activos ✅ PASS

**Problema.** `app/routers/assets.py:2024` — `create_asset(payload, background, db)`, sin guardia.
No solo insertaba filas: encola `_recompute_walk_score`, que llama a Overpass y a Google
Routes/Places. **Un desconocido podía hacernos gastar en APIs de pago, sin tope.**

**Inventario de la superficie de escritura**, preguntándole a FastAPI por las dependencias que
resolvió al registrar cada ruta (no por grep):

| | Antes | Después |
|---|---:|---:|
| Endpoints de escritura | 37 | 37 |
| Protegidos | 30 | **31** |
| Sin guardia | 7 | 6 |

Los 6 restantes son el flujo público del comprador, deliberado: `handoff` ×3 (con
`get_optional_user`), `lead-contacto` (*"Público — es el propio comprador"*), `chat/comparar` y
`assets/mapa/comando` —este no escribe en base y está a 40/min—. Cerrarlos rompería la acción
final del MVP (D8).

**Por qué no rompe nada:** `scripts/hidratar_activos.py:152` —el consumidor real— **ya enviaba
`X-API-Key`**. La credencial viajaba desde siempre y nadie la miraba.

#### Riesgo adicional detectado y cerrado: fail-open silencioso

`verify_api_key` trataba *"API_KEY vacía"* como dev local **siempre**. Bastaba borrar la variable
en el panel de Render para desproteger de golpe todas las rutas con esta guardia —incluida, ya,
la escritura del catastro— sin un error en los logs y sin que ninguna prueba lo notara.

**Verificado contra producción antes de cambiar nada** (peticiones sin llave y con body inválido,
que no escriben):

```
GET  /health                    → 200  {"status":"healthy","database":"up"}
POST /api/v1/assets/ingest      → 401  {"detail":"API key inválida o ausente."}
POST /api/v1/alertas            → 401  {"detail":"API key inválida o ausente."}
```

**`API_KEY` sí está configurada hoy en producción.** El cambio cierra el riesgo de que deje de
estarlo: sin `API_KEY`, en dev no restringe; **en producción responde 503 y lo registra**. 503 y
no 401 a propósito — el cliente no hizo nada mal, el servidor está mal configurado; es el criterio
que ya usaba `app/auth.py` cuando le falta `SUPABASE_URL`.

Cómo se sabe que es producción: `settings.es_produccion`. Si `ENVIRONMENT` está declarado, manda;
si no, se infiere de `RENDER`, que Render inyecta solo en todos sus servicios. Se prefiere a una
variable propia justamente **porque no hay que acordarse de ponerla**: el despliegue real queda
protegido sin configurar nada, y en otro proveedor lo peor que pasa es tener que declarar
`ENVIRONMENT=production` — un fallo ruidoso, no una puerta abierta.

**Tests.** `tests/test_escritura_catastro_protegida.py` (4) + 9 nuevos en `tests/test_auth.py`.
**Antes/después:** sobre `937f587`, 2 fallos con el mensaje *"POST /api/v1/assets/ quedó sin
guardia"*; con el fix, pasan.

**Recomendación no incluida** (para no mezclar alcances): este endpoint sigue sin
`@limiter.limit`, a diferencia de `/ingest` (20/min) y `/ingest/batch` (5/min).

---

### E0.2 — Refresh de POIs ✅ PASS

#### El diagnóstico de la auditoría se queda corto

La auditoría dice *"release obsoleto"*. La verificación contra el bucket real:

```
releases publicados hoy : 2026-07-22.0 · 2026-08-19.0
fijado en el script     : 2026-06-17.0  → AUSENTE, cero objetos
```

**Overture no conserva los releases viejos.** El prefijo fijado había dejado de existir.

#### Evidencia forense: el log del 2026-08-18

```
_duckdb.IOException: IO Error: No files found that match the pattern
"s3://overturemaps-us-west-2/release/2026-06-17.0/theme=places/type=place/*"
   ERROR DURO — no se reintenta. Revisar este log.
==== FIN · codigo final: 1 ====
```

**Esto corrige un matiz de la revisión 1 de este reporte.** Se dijo que el fallo era silencioso
porque "cero filas no es un error para DuckDB". Es inexacto: `read_parquet` con un glob sin
coincidencias **lanza IOException**, y el script salió con código 1 como debía. Lo que falló no
fue la señal, fue el destinatario: **el ruido murió en un log local que nadie abrió**, ocho días.

Datos de la tabla al empezar: `actualizado_en` máximo = **2026-08-11**. Así que la última corrida
buena fue el 11 de agosto, y la tubería lleva rota desde el 18 — no "semanas", como decía la
revisión 1.

#### Corrección de la revisión 2: la tarea programada nunca corrió

Al ir a deshabilitar la tarea de Windows *"Refresco POIs Contexto"* —último paso operativo de
C-A— se descubrió que **nunca llegó a ejecutarse**. Las revisiones 1 y 2 de este documento la
daban por el mecanismo activo del refresco semanal. No lo era.

| Evidencia | Lectura |
|---|---|
| `LastTaskResult: 267011` (`SCHED_S_TASK_HAS_NOT_RUN`) y `LastRunTime` en el centinela `30/11/1999` | Windows dice que la tarea no se ejecutó nunca |
| Disparador: lunes 17:00, `StartBoundary 2026-07-30T17:00` | debería haber disparado los lunes 3, 10, 17 y 24 de agosto |
| Log del lunes 2026-08-03 | primer intento a las **18:19:59** — hora que no cuadra con las 17:00 |
| Log del **martes** 2026-08-18 | primer intento a las **09:04:22** — ni el día ni la hora |
| Lunes 10 y 17 de agosto | **sin log ninguno** |

Las cinco corridas de las que hay log (2026-07-28, 08-03, 08-11, 08-18 y la supervisada de hoy)
se lanzaron **a mano**. El "refresco semanal automático" no existía: dependía de que el fundador
se acordara de correr el `.cmd`.

**Esto no debilita C-A, la agrava.** El diagnóstico de partida —"depende del PC del fundador"— se
quedaba corto: no dependía de la máquina, dependía de la memoria de una persona. Y explica por
qué la tubería pudo quedar rota entre el 18 y el 24: no había nada programado que la reintentara.

*Cautela sobre la certeza:* si la tarea se hubiera borrado y recreado en algún momento, el
historial se reiniciaría y el `HAS_NOT_RUN` sería menos concluyente. Pero las horas de los logs no
coinciden con el disparador en ningún caso, y faltan los dos lunes intermedios; ambas cosas
apuntan a lo mismo con independencia del historial.

**Solución, tres partes.**

1. **El release se descubre.** Se lista el bucket por la API de S3 (un GET con `delimiter`; el
   `glob` de DuckDB no enumera prefijos — probado, devuelve cero filas). Se elige con `max()`,
   no con `[-1]`: **un test cazó ese bug** en la primera versión. `OVERTURE_RELEASE` lo fija a
   mano para reproducir una corrida pasada.
2. **Cero filas pasa a ser error duro.** Cubre el caso de que el release exista pero el bbox no
   devuelva nada; sin este corte el script seguiría hasta el cierre de POIs y una recarga vacía
   cerraría los existentes por ausencia.
3. **El fallo avisa.** Error duro → correo por Resend; y `refresco_pois.cmd` avisa al agotar sus
   reintentos. Sin `RESEND_API_KEY` o `ALERTA_OPS_EMAIL` lo dice por consola y no falla.

#### Preflight de solo lectura (previo a autorizar la escritura)

| | |
|---|---|
| Release resuelto | `2026-08-19.0` |
| Overture en tabla | 2 851 operativos |
| Overture que traería | 2 753 · ratio **0,97** (umbral de guarda 0,50) |
| Cierres previstos | **511** |
| Operaciones | UPSERT por `overture_id`/`osm_id` + `UPDATE operativo=false`. **Sin TRUNCATE ni DELETE** desde la migración 020. Otras ciudades intactas. |

#### Corrida supervisada — autorizada por el fundador y ejecutada

```
Overture release: 2026-08-19.0
2753 POIs Overture (10s)
5651 POIs de OSM (6s)
en la tabla antes: 8512 POIs de 'quito' · cosechados ahora: 8404
upsert: 2753 Overture + 5651 OSM · marcados cerrados: 516
✅ Refresco completo — las dos fuentes respondieron.
==== FIN · codigo final: 0 ====
```

**Verificación antes/después:**

| | antes | después | Δ |
|---|---:|---:|---:|
| Overture total | 2 851 | 3 264 | **+413 altas** |
| Overture operativos | 2 851 | 2 753 | −98 |
| Overture cerrados | 0 | **511** | +511 |
| OSM total | 5 661 | 5 670 | +9 |
| OSM operativos | 5 647 | 5 651 | +4 |
| Total ciudad | 8 512 | 8 934 | +422 |
| `actualizado_en` | 2026-08-11 | **2026-08-25 00:34 UTC** | ✅ |
| Otras ciudades | 0 | 0 | intactas |

- **Cierres: 511, exactamente lo que predijo el preflight.**
- **Errores:** ninguno. Código 0, las dos fuentes respondieron.
- **Duración:** 29 s (Overture 10 s, OSM 6 s, carga el resto).
- **La capa sigue sirviendo:** la consulta de producto (POI más cercano por categoría) devuelve
  las **9 categorías** con **distancias idénticas** a las de antes (salud 68 m, transporte 86 m,
  educación 95 m, supermercado 139 m, seguridad 145 m, farmacia 302 m, parque 314 m,
  iglesia 357 m, centro comercial 441 m).

**Tests:** `tests/test_overture_release.py` (8), sin tocar la red.

---

### E0.3 — Procedencia de caminabilidad ✅ PASS

**Problema.** `app/encaje.py:209` afirmaba `"OpenStreetMap"` incondicionalmente. El `walk_score`
nace heurístico y solo se sobrescribe con OSM si Overpass responde.

**Lo que hacía invisible el defecto:** el dato correcto ya estaba en todas partes menos en el
eslabón que importaba.

| Pieza | Estado en HEAD |
|---|---|
| Columna `walk_score_fuente` | ✅ existe (`'osm'` / `'heuristico'`) |
| Query de `chat.py:453` | ✅ ya la traía como `caminabilidad_fuente` |
| Card (`_card_from_row`) | ✅ ya la usaba |
| Ficha del anuncio (`_scores_fuente`) | ✅ ya distinguía |
| **`_senales_encaje` → motor** | ❌ **no la pasaba** |

**Los tres caminos con un solo fix:** el bloque autoritativo (`encaje_contexto.py:216`) deriva su
rótulo de `razon['fuente']`, así que hereda la corrección — y es justo el texto que el modelo lee
antes de redactar.

**Hallazgo.** Este bug **ya se había corregido una vez**, el 2026-07-03, pero solo del lado de la
ficha (ver `test_scores_fuente.py`: *"el rótulo MENTÍA"*). El mismo error vivía en dos lugares y
se arregló uno. El test nuevo añade el invariante que faltaba: ficha y motor no pueden discrepar.

**Antes/después.** Sobre `937f587`: **7 fallos**, entre ellos *"Con walk_score_fuente='heuristico'
la ficha y el motor discrepan sobre si hubo medición: ficha=False, motor=True"*. Con el fix, 11
pasan. Hay un test explícito de que **E0.3 no toca el número**: corrige el rótulo, no el peso.

---

### E0.4 — score_version y heurísticas fuera del scoring ✅ PASS

**Problema, medido sobre `937f587`:**

| Caso | Antes | Después |
|---|---:|---:|
| Dos inmuebles idénticos salvo ruido (BAJO vs ALTO) | **50 puntos** | **0** |
| Dos idénticos salvo vegetación (90 % vs 10 %) | **80 puntos** | ambos `None` |
| Parque medido (4 min vs 25 min) | 100 vs 20 | **100 vs 20** (intacto) |
| `score_version` | ausente | `encaje-v0` |

Esa diferencia salía de `scores_heuristicos.scores_para`: una tabla de 7 sectores de Quito escrita
a mano más un desplazamiento derivado del hash SHA-256 de la dirección. `tranquilidad` era una de
las 8 dimensiones de la lista blanca, con peso 1.0.

**Importa más allá de la honestidad:** la factualidad es una métrica del benchmark que decide si
la tesis vive. Con esto dentro, la condición D habría medido en parte la calidad de una invención.

**Qué se retira y qué no.**
- `tranquilidad` → `insufficient_evidence`. Única fuente: la tabla.
- `area_verde` → **solo el camino de vegetación**. El parque concreto (`parque_min`, del mapa)
  sigue puntuando. La dimensión no se apaga entera porque eso tiraría el dato bueno con el malo.
- tráfico → no había nada que retirar; nunca fue puntuable. Queda un test para que no se añada
  por simetría sin fuente detrás.

Las dimensiones se conservan **visibles**: *"Buscabas tranquilidad · no tenemos medición de ruido
aquí"*, con `aporta=False`. D3 lo pide así: "no lo sabemos" es información.

#### ⚠️ Efecto secundario que conviene tener presente

Declarar `tranquilidad` mete peso en el **denominador de la cobertura** que ninguna ficha puede
llenar. Consecuencia: **cuando el comprador la pide, todos los inmuebles quedan moderados por
evidencia**, incluso los de ficha completa. El orden relativo no cambia; los números absolutos
bajan. Es honesto, y tiene test propio (`test_declarar_tranquilidad_topa_la_cobertura_alcanzable`).

**Tests.** `tests/test_scoring_sin_heuristicas.py` (16). **10 tests existentes cambiaron de
expectativa, ninguno por un bug**: todos usaban el ruido como discriminante y ahora usan
caminabilidad o transporte.

---

### E0.5 — CI gate ✅ PASS

**Problema.** `.github/workflows/` tenía `keepalive.yml` y `vigia-salud.yml`. **Ninguno ejecutaba
`pytest`.** 796 pruebas que corrían en segundos y no bloqueaban nada.

**Solución.** `.github/workflows/pruebas.yml` — suite completa en push a `main`, en pull request y
a mano. Python 3.11, igual que el Dockerfile.

**Hallazgo de la verificación.** Probado sobre un worktree limpio (sin `.env`, como el CI):
**27 archivos de test ni siquiera se recolectan.** `app/config.py` declara `postgres_db`,
`postgres_user` y `postgres_password` sin default, así que `Settings()` revienta con
`ValidationError` antes de correr una prueba. El job exporta las tres con valores inertes —las
pruebas son offline y no abren conexión—. Un workflow escrito a ciegas habría fallado en su
primera corrida por una razón ajena al código.

**Verificado en local, en las dos direcciones:** suite sana → exit 0; con un test roto inyectado
en un worktree desechable → **exit 1**, que es lo que pone el job en rojo.

#### Las tres corridas reales

El workflow se validó por PR (#119) sobre la rama `ci/trust-gate-f0`, sin usar `main` de
conejillo. **Las dos primeras terminaron en rojo** por defectos reales del propio trabajo —§3.3—.
La tercera pasó.

| Corrida | Commit | Resultado |
|---|---|---|
| 1ª | `1fb5e7e` | ❌ failure — `sys.exit(1)` al importar |
| 2ª | `3958c7a` | ❌ failure — `duckdb` ausente en el runner |
| 3ª | `6984b8b` | ✅ **success** |

#### El nombre del check

El status check se llama **`pytest`** (el nombre del *job*), no `pruebas` (el del *workflow*).
Confirmado por la API antes de configurar nada:
`GET /repos/contexxto/contexto-ai/commits/{sha}/check-runs` → `{"name": "pytest"}`.
Marcar `pruebas` habría dejado el ruleset apuntando a un check inexistente — protección aparente
y ningún bloqueo real.

#### Las dos mitades del gate, activadas

Actions **no es** el portero de Render. Hicieron falta dos interruptores de consola, ambos activos:

1. **GitHub** → ruleset `main protegida`. Verificado por API:
   ```
   enforcement: active   ·   bypass_actors: []   ·   target: ~DEFAULT_BRANCH
   rules: deletion | pull_request (0 aprobaciones)
          required_status_checks -> ['pytest'], strict: true
          non_fast_forward
   ```
   La **lista de excepciones vacía** no es un detalle: el fundador es el dueño del repositorio, y
   con una regla *classic* se la habría saltado por defecto. Sin eso, la prueba negativa de abajo
   no demostraría nada.

2. **Render** (`contexto-ai-oregon`) → `Auto-Deploy` de **`On Commit`** a **`After CI Checks Pass`**.
   Ese `On Commit` era el P0 en su forma más cruda: hasta el 2026-08-24, cualquier commit que
   tocara `main` se desplegaba a producción sin que nadie mirara una sola prueba.

#### Prueba negativa — la evidencia que convierte esto en PASS

En vez de un `assert False` sintético se rompió **algo real**: se quitó `verify_api_key` de
`POST /api/v1/assets/`, o sea se reintrodujo exactamente el P0 que cerró E0.1. Lo que había que
demostrar no era que pytest sepa fallar, sino que **la red de regresión caza una regresión de
seguridad y que la protección de rama impide mezclarla**.

Commit `cc6e597` en la rama temporal `ci/prueba-negativa`, PR #120:

| Comprobación | Resultado |
|---|---|
| Detección local previa | `tests/test_escritura_catastro_protegida.py` falla con *"POST /api/v1/assets/ quedó sin guardia"* |
| `pytest` en el runner | ❌ **failure** a los 26 s |
| Etiqueta del check en el PR | 🔒 **`Required`** |
| Botón *Merge pull request* | **gris, no pulsable** |
| `main` durante toda la prueba | `937f587` — **intacto** |
| Producción | `healthy`, `database: up` — **ningún despliegue** |
| PR #120 | **closed**, `merged: false` |
| Rama `ci/prueba-negativa` | **borrada** |

> **Nota metodológica.** La API devolvió `mergeable_state: unstable`, no `blocked`. Ese campo nació
> con las protecciones *classic* y no refleja los rulesets con fiabilidad. **No se dio por buena esa
> señal**: se comprobó por un lado que las reglas aplican de verdad
> (`GET /repos/.../rules/branches/main` devuelve `required_status_checks -> ['pytest']`) y por otro
> el estado en la interfaz, que es donde el bloqueo ocurre. Un PASS declarado sobre `unstable`
> habría sido exactamente el tipo de afirmación cómoda que esta fase existe para no repetir.

#### Una tercera prueba, no planeada

Al ir a commitear **esta misma revisión del documento**, el intento de empujar directo a `main`
—un push legítimo, desde la línea de comandos, sin PR— fue rechazado por el servidor:

```
remote: - Required status check "pytest" is expected.
! [remote rejected] main -> main (push declined due to repository rule violations)
```

Vale más que las otras dos porque nadie la montó: no viene de la interfaz ni de un commit de
mentira. El gate cerró el camino que hasta esta mañana estaba abierto de par en par, y lo hizo
sobre quien lo construyó.

#### Límite conocido, dicho de frente

El gate protege **el backend en Render**. El frontend se despliega por **Vercel**, que es un carril
aparte y **hoy no está atado a `pytest`**: durante la prueba negativa, Vercel construyó igualmente
un *preview* de la rama rota. Es un entorno efímero y no producción, y el commit roto era de
backend, así que no hubo impacto — pero **queda como hueco real fuera del alcance de F0**.

---

### C-A — El refresco sale del PC del fundador ✅ RESUELTA

Decisión del fundador: el refresco no seguirá dependiendo de esa máquina.

**Mecanismo elegido: GitHub Actions**, no un servicio nuevo. Cubre los seis requisitos sin
construir infraestructura, y el repositorio es público, así que los minutos no se facturan.

| Requisito | Cómo |
|---|---|
| Ejecución programada | `schedule: '0 22 * * 1'` — lunes 22:00 UTC = 17:00 en Quito, la hora que la tarea de Windows tenía configurada (aunque nunca llegara a dispararla; ver E0.2) |
| Ejecución manual | `workflow_dispatch` con selector de ciudad |
| Secretos | `DATABASE_URL_OVERRIDE`, `RESEND_API_KEY`, `ALERTA_OPS_EMAIL`, `NOTIFY_FROM_EMAIL` |
| Logs | Consola de Actions, con los mismos mensajes del script |
| Exit code bloqueante | El step propaga el código; 1 y 2 tumban el job |
| Alerta de fallo | El script avisa por Resend + el step `if: failure()` cubre el caso de agotar reintentos + GitHub notifica el workflow fallido |

Conserva la semántica de códigos (0 / 2 reintentable / 1 duro) y los reintentos por Overpass, con
espera de 10 min en vez de 15.

#### Corrida real en el runner — 2026-08-24

Los cuatro secretos se configuraron en `Settings → Secrets → Actions` y el workflow se lanzó por
`workflow_dispatch` sobre `main` (`eeff14c`), ciudad `quito`. Resultado: **success en 44 s**.

**Esos 44 segundos no se dieron por buenos.** Un refresco real descarga Overture por DuckDB desde
S3 y consulta Overpass; medio minuto era sospechosamente poco, y un job en verde no prueba que haya
hecho el trabajo. Se fue a la base a comprobarlo, con foto antes y después:

| | Antes | Después |
|---|---|---|
| Total Quito | 8.934 | **8.940** (+6) |
| OSM | 5.670 | 5.676 |
| Overture | 3.264 | 3.264 (sello actualizado) |
| `parque` | 533 | **537** |
| `supermercado` | 1.997 | **1.999** |
| Prueba de servicio | 9 categorías | 9 categorías, mismas distancias |

**La correlación temporal cierra el argumento:** la corrida fue de `02:37:47Z` a `02:38:31Z` y el
`max(actualizado_en)` de la tabla quedó en `02:38:24Z` — **dentro de la ventana**. La escritura es
del runner y de nadie más.

Las distancias del inmueble de prueba no se movieron, y es lo correcto: son los POIs más cercanos
por categoría y esos no cambiaron; los seis nuevos entraron más lejos. Ambas fuentes respondieron
(código 0), así que los 44 s son simplemente el camino feliz —sin reintentos de Overpass, con la
caché de pip caliente—. Los ~40 min del `.cmd` eran el peor caso, no el normal.

**Consecuencia operativa:** la tarea de Windows *"Refresco POIs Contexto"* queda **deshabilitada**
(no borrada: sirve de respaldo manual). `scripts/refresco_pois.cmd` se conserva para correr el
refresco a mano en local, que sigue siendo útil para depurar.

**La corrida en el runner es, por tanto, la primera vez que el refresco de POIs se ejecuta de
forma realmente programada e independiente de una persona** — ver la corrección en E0.2 sobre la
tarea de Windows, que nunca llegó a dispararse.

*Aviso menor del runner:* `actions/checkout@v4` y `actions/setup-python@v5` corren sobre Node 20,
que GitHub va a retirar. No rompe nada hoy; toca subir versiones más adelante.

`requirements-pois.txt` aparte de `requirements.txt` a propósito: `duckdb` pesa y el backend no lo
usa. **Estas versiones no estaban declaradas en ninguna parte** — vivían en el venv del portátil;
mientras el refresco corriera solo ahí eso bastaba.

**Verificado en un venv limpio**, sin `.env` y con solo esas dependencias: el script importa y
descubre el release. El workflow no fallará por dependencias en su primera corrida.

**Límite documentado:** el cron de GitHub se estrangula — medido en este repo, mediana 34 min de
retraso, p90 49 min, máximo 109 min. Para un refresco semanal es irrelevante; se anota para que
nadie lo lea como garantía de puntualidad.

`refresco_pois.cmd` se conserva para correr a mano en local y queda marcado como no principal.
**Recomendación: desactivar la tarea programada de Windows** para no duplicar trabajo.

---

## 6. Contradicciones

**C-A · Alcance de E0.2 divergente entre Plan 1.0 y doc 04.** → **RESUELTA por el fundador** y
ejecutada. Ver arriba.

**C-B · El protocolo pide `branch`; el repo no admite ramas locales.** Resuelto trabajando en
`main` por pathspec, y publicando una rama remota para el PR sin tocar la local.

**C-C · Auto-deploy sin gate.** Motivó el reorden de unidades. **Cerrada:** ruleset activo en
GitHub + `After CI Checks Pass` en Render, ambos verificados con la prueba negativa.

**C-D · La suite reportada como verde no lo estaba.** Corrige la evidencia del doc 01.

**C-E · El diagnóstico de E0.2 subestima el defecto.** No es obsolescencia, es rotura: el release
había desaparecido. Con matiz propio: el fallo **sí era ruidoso** (IOException + código 1), lo que
faltaba era que alguien lo leyera.

**Ninguna contradice las decisiones D1–D9.** D3 se aplicó tal como está congelada.

---

## 7. Impacto en producción y configuración

### Estado del despliegue

**Mergeado y desplegado.** PR #119 → `main` (`eeff14c`), con `pytest` verde como condición de
merge. Render construyó y sirvió el código nuevo.

**Verificación funcional contra producción, no por confianza en el panel:** se sondeó
`POST /api/v1/assets/` sin cuerpo y sin `X-API-Key` contra
`https://contexto-ai-oregon.onrender.com`. Devolvió **401**. La distinción importa: con el código
viejo habría devuelto 422 —la validación del cuerpo corre antes que una guardia inexistente—, así
que el 401 prueba que **la dependencia de seguridad está viva en producción**. La sonda no escribe
nada: la guardia corta antes.

`/health` → `{"status":"healthy","database":"up","memoria":"postgres"}`.

**Dos escrituras en datos vivos** en toda la fase, ambas en `pois_propios` y ambas autorizadas: la
corrida supervisada de E0.2 y la corrida en el runner de C-A.

### Comportamiento observable que cambió

| Cambio | Efecto |
|---|---|
| `POST /api/v1/assets/` exige `X-API-Key` | 401 sin llave. Los scripts conocidos ya la enviaban. `API_KEY` está confirmada en producción. |
| Sin `API_KEY` en producción → 503 | Solo aplica si alguien la borra. Es el fail-closed. |
| Ruido y vegetación fuera del scoring | **Los scores cambian**, y los rankings con ellos. Ver el efecto de cobertura en §5, E0.4. |
| Razones nuevas en las tarjetas | Aparece *"no tenemos medición de ruido aquí"*. El frontend la pinta como cualquier razón no-alta; no requiere cambio de front. |
| Procedencia de caminabilidad | Deja de decir "OpenStreetMap" donde el walk score es estimado. |

### Configuración aplicada

**Secretos de GitHub Actions** — los cuatro cargados y verificados por la corrida real:

| Secret | Clasificación | Origen |
|---|---|---|
| `DATABASE_URL_OVERRIDE` | 🔴 **obligatorio** — sin él el job falla en el step de comprobación | copiado de Render, misma base que sirve producción |
| `RESEND_API_KEY` | 🟡 el refresco corre igual, pero el aviso no sale | Render |
| `ALERTA_OPS_EMAIL` | 🟡 ídem — sin destinatario no hay a dónde escribir | `contexxto.ai@gmail.com` |
| `NOTIFY_FROM_EMAIL` | 🟢 tiene default en el script | Render: `Contexto <avisos@contexxto.com>` |

**Sobre el remitente.** El default del script es `onboarding@resend.dev`, el *sandbox* de Resend,
que **solo entrega al correo dueño de la cuenta**: si el destinatario fuera otro, el aviso se
rechazaría justo el día que hiciera falta. No aplica aquí — se verificó por DNS que `contexxto.com`
está verificado en Resend (`resend._domainkey.contexxto.com` publica DKIM y `send.contexxto.com`
publica `v=spf1 include:amazonses.com ~all`), así que el remitente real es válido y el destinatario
puede ser cualquiera. **`NOTIFY_FROM_EMAIL` no debe apuntarse nunca a una dirección de Gmail:**
Resend solo envía desde dominios verificables por DNS, y `gmail.com` no lo es.

**Variables de entorno nuevas, todas opcionales** (documentadas en `.env.example`):
`ALERTA_OPS_EMAIL`, `OVERTURE_RELEASE`, `ENVIRONMENT`.

**Sin migraciones.** `walk_score_fuente` ya existía.

---

## 8. Riesgos y trabajo abierto

### Riesgos de lo entregado

1. **El cambio de scoring altera rankings en producción.** Es el efecto buscado; `score_version`
   existe justo para poder distinguir un número de antes de uno de después.
2. **La corrida de POIs cerró 511 registros de Overture.** Es soft (`operativo=false`),
   reversible, coincide con lo previsto y está lejos del umbral de alarma. Se anota porque es el
   único cambio de datos vivos de la fase.
3. **El aviso por correo del refresco no se ha ejercitado nunca de extremo a extremo.** Las
   credenciales están puestas y el dominio remitente verificado, pero el camino solo se recorre
   cuando el refresco falla, y no ha fallado desde que existe. Se sabe que **no** se rompe sin
   credenciales (hay prueba: `test_avisar_sin_configuracion_no_falla`); lo que no se ha visto es un
   correo llegando. Queda como incógnita honesta.
4. **El frontend en Vercel no está atado a `pytest`.** Ver el límite documentado en E0.5.

### Pendientes

| # | Qué | Quién | Esfuerzo |
|---|---|---|---|
| 1 | Subir `actions/checkout` y `setup-python` cuando GitHub retire Node 20 | quien toque CI | minutos |
| 2 | Decidir si el despliegue del frontend en Vercel debe tener gate | Carlos | decisión |
| 3 | Borrar la rama `ci/trust-gate-f0` cuando ya no sirva de referencia | Carlos | 1 clic |

Todo lo que bloqueaba F0 está hecho. Lo de arriba es higiene, no deuda del gate.

### Recomendaciones fuera de alcance, no ejecutadas

- `@limiter.limit` en `POST /api/v1/assets/`, por consistencia con `/ingest`.
- Mover `verify_api_key` de `app/routers/chat.py` a `app/auth.py`. Hoy cinco routers importan una
  guardia de seguridad desde un router de chat. Toca la frontera que el doc 02 quiere trazar.
- ~~**URL muerta en scripts:** `scripts/generar_qrs.py` y `scripts/hidratar_activos.py` apuntan por
  defecto a `https://contexto-ai.onrender.com`, que devuelve **503**. El servicio vivo es
  `contexto-ai-oregon.onrender.com`. Detectado de paso al verificar producción.~~
  **RESUELTO 2026-08-24:** ambos defaults se resuelven por entorno (`CONTEXTO_API_URL`) con el host
  vivo de respaldo — el mismo patrón que ya usaba `evals/run_evals.py` —, de modo que un cambio de
  hostname se corrija por entorno y no por código. De paso, el `+URL` del User-Agent del scraper
  (`app/vision.py`) dejó de apuntar al host que devuelve 503 y ahora identifica al bot contra
  `contexxto.com`. La regla de resolución quedó fijada en `tests/test_resolucion_api_url.py`.
  Nota de evidencia: está verificado que el host viejo devuelve 503 y el nuevo 200; **no** está
  verificado el mecanismo (un rename del servicio es una hipótesis, no un hecho observado), ni
  cuánto tiempo llevaba roto.
  **La causa estructural sigue viva:** los consumidores internos dependen de un hostname propiedad
  del proveedor de infraestructura. Mientras no exista un endpoint canónico controlado por Contexto,
  un cambio de hostname o de servicio puede volver a romperlos. Ver el registro (1) más abajo.

- **Deuda: dos semánticas de precedencia conviviendo para el `.env`.** El tooling
  (`scripts/*`, `evals/run_evals.py`) resuelve **shell no vacío > `.env` no vacío > respaldo**.
  `app/config.py` hace lo contrario a propósito: carga el `.env` explícitamente **primero** porque
  un shell con la variable en vacío —puesta por otro programa— le pisaba las claves al backend
  (ver el comentario en su cabecera). Ninguna de las dos está mal en su contexto: el backend se
  defiende de un entorno que no controla, el tooling quiere que un override de una corrida suelta
  gane sin editar archivos. Queda **registrada para revisar**, no para unificar de oficio; decidir
  cuál es la regla de la casa toca la frontera de configuración que el doc 02 quiere trazar.
  Fuera del alcance del hotfix de la URL (2026-08-25).

### Registrado el 2026-08-25 — anotado, NO ejecutado

Cuatro puntos que salen del hotfix de la URL y de la revisión que lo aprobó. Ninguno se toca en
ese trabajo; quedan aquí para que no dependan de la memoria de una sesión.

1. **`api.contexxto.com` antes de Partner Layer.** Endpoint canónico controlado por Contexto como
   custom domain de la API. Es la solución estructural: hoy los consumidores internos dependen de
   un hostname del proveedor de infraestructura. **Recién con ese dominio en pie** corresponde
   añadir (a) un test determinista que prohíba `*.onrender.com` en código operativo, (b) un smoke
   post-deploy y (c) un health check sintético programado. Decisión explícita: **no** se añade un
   smoke contra producción como status check bloqueante de cada PR — acoplaría el CI a la
   disponibilidad de un tercero.
2. **Evaluator requerido ausente ⇒ `ERROR`/`INVALID`, nunca `PASS` silencioso — antes del
   Benchmark.** Del mismo linaje que el bug que este hotfix cerró en `run_evals.py`: cuando el
   `.env` no se encontraba, el juez LLM se apagaba solo y la suite terminaba en verde con las
   rúbricas de criterio sin evaluar. Un evaluador que falta tiene que romper la corrida, no
   aprobarla por omisión.
3. **Deuda de precedencia de `app/config.py`** — la del punto anterior a este bloque.
4. ~~**Reconciliar este informe (06)** cuando termine la sesión que lo está modificando en paralelo.
   Al 2026-08-25 hay commits sin publicar de otra sesión que reescriben este archivo, por lo que
   las notas de arriba viven solo en `main` local y quedaron **fuera** del PR del hotfix
   (`fix/contexto-api-url-viva`) para no arrastrar trabajo ajeno ni sembrarle conflictos.~~
   **RESUELTO 2026-08-25.** Reconciliado y publicado contra `30354cb`. Las notas de la sesión del
   hotfix se conservan **tal como las dejó**, sin mover ni reescribir: son observaciones acotadas y
   con su propia distinción entre lo verificado y lo hipotético. Lo único que se añadió encima es
   la nota del conteo de pruebas en §1. Se verificó archivo por archivo que entre `main` local y
   `origin/main` **no difería ningún archivo de código** —solo este informe y
   `scripts/refresco_pois.cmd`—, así que esta publicación no arrastra trabajo ajeno.

---

## 9. Recomendación

| Condición de fallo del Gate F0 (Plan §6) | Estado |
|---|---|
| Escritura crítica anónima | ✅ resuelto |
| Provenance contradictorio | ✅ resuelto |
| Scoring contaminado por heurística sin fuente | ✅ resuelto |
| Pipeline territorial no reproducible | ✅ **resuelto** — corrida completa verificada, dos veces |
| Tests sin gate | ✅ **resuelto** — merge bloqueado con prueba negativa |

### `ADVANCE TO CONTRACTS`

**Las cinco condiciones de fallo del Gate F0 están cerradas con evidencia reproducible**, el código
está en `main` y desplegado, y las dos mitades del gate —GitHub y Render— quedaron probadas con una
regresión de seguridad real, no con un `assert False`.

La razón de fondo para avanzar no es que la lista esté completa. Es que **el sistema demostró que
detecta problemas que sus autores no vieron.** El gate encontró dos defectos en el trabajo de la
propia fase, en su primera y segunda corrida, y ambos eran del tipo que se escapa siempre: código
que funciona en una máquina concreta. Antes de hoy, ese código habría llegado a producción sin que
nadie se enterara — y de hecho llevaba semanas pasando con el release de Overture.

Eso es exactamente lo que un Trust Gate debía comprar antes de dejar avanzar a Contracts: no una
lista de arreglos, sino una razón medida para creerse el siguiente número que produzca el sistema.

**Lo que NO cubre este PASS, para que nadie lo lea de más:**

- El gate protege el backend en Render. **Vercel es un carril aparte y sigue sin gate.**
- El aviso por correo del refresco **nunca se ha visto llegar**; solo está probado que su ausencia
  no rompe nada.
- `score_version = "encaje-v0"` marca la frontera: **cualquier número anterior a esta fase no es
  comparable** con los de después.

---

## 10. Parada

Según `00_START_HERE` §11, la ejecución **se detiene aquí**. FASE 0 queda cerrada; **no se inicia
Contracts / Fase 1** hasta la revisión de Carlos y ChatGPT y una autorización explícita.

### Reproducir cualquier cifra de este documento

| Afirmación | Comando o consulta |
|---|---|
| Suite en 847 | `python -m pytest --collect-only` sobre `eeff14c` |
| Suite verde sin `.env` | `git worktree add --detach <tmp> eeff14c`, exportar `POSTGRES_DB/USER/PASSWORD=test`, `python -m pytest -q` |
| Reglas activas sobre `main` | `GET /repos/contexxto/contexto-ai/rules/branches/main` |
| Nombre del check | `GET /repos/contexxto/contexto-ai/commits/6984b8b/check-runs` |
| Las tres corridas del PR #119 | `GET /repos/contexxto/contexto-ai/actions/runs?branch=ci/trust-gate-f0` |
| Prueba negativa en rojo | `GET /repos/contexxto/contexto-ai/commits/cc6e597/check-runs` |
| PR #120 sin mergear | `GET /repos/contexxto/contexto-ai/pulls/120` → `merged: false` |
| E0.1 vivo en producción | `curl -X POST https://contexto-ai-oregon.onrender.com/api/v1/assets/` → 401 |
| Ventana de la corrida del refresco | `GET /repos/contexxto/contexto-ai/actions/runs/32802129025` |
| Escritura del runner en la base | `SELECT max(actualizado_en) FROM pois_propios WHERE ciudad='quito'` |
| Dominio remitente verificado | `dig TXT resend._domainkey.contexxto.com` y `dig TXT send.contexxto.com` |
