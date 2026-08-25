# 06 — PHASE 0 TRUST GATE REPORT

**Fecha:** 24 de agosto de 2026
**Ejecutor:** Claude Code (sesión del 2026-08-24)
**Plan de referencia:** `Contexto Agentic Decision System — Execution Plan 1.0`, FASE 0
**Alcance autorizado:** E0.1–E0.5 únicamente. Sin Contracts, sin harnesses, sin features.

> **Revisión 2** — reconciliado contra HEAD real. La revisión 1 reportaba `53f29a2`, 6 commits
> y 829 tests: se escribió antes de commitearse a sí misma y antes de que E0.1 y C-A se
> cerraran. Los números de este documento salen de `git` y de `pytest` ejecutados sobre el
> HEAD que aparece abajo.

---

## 0. Resumen

**Cuatro de los cinco gates quedan cerrados con evidencia.** El quinto (E0.5) tiene el código
hecho y verificado en local, y espera un paso que no puedo dar yo: abrir el PR que dispare el
workflow, y activar dos interruptores de consola.

Además, **C-A queda resuelta**: el refresco de POIs ya no depende del PC del fundador.

Recomendación en §9.

---

## 1. Identificación

| Campo | Valor |
|---|---|
| Repositorio | `C:\Users\DETPC\Desktop\Contexto-AI` · `github.com/contexxto/contexto-ai` (público) |
| Rama local | `main` |
| Commit inicial | `937f587f886783ad835cdf862eda30e4ea364848` |
| **Commit final** | **`bdd4b68c434575dc9f4e7a122f344ddf0ff1f52c`** |
| Commits creados | **9** |
| Archivos cambiados | **21** (+1529 / −76) |
| Suite al empezar | 795 de 796 (**1 fallo preexistente**) |
| **Suite al terminar** | **846 de 846**, exit 0, 58 archivos |
| Estado en `origin/main` | **sin pushear** — ver §7 |
| Rama remota temporal | `ci/trust-gate-f0`, publicada para validar el CI por PR |

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

---

## 3. Dos hallazgos previos a tocar código

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

---

## 4. Estado por unidad

| Unidad | Estado | Lo que falta |
|---|---|---|
| E0.1 — Proteger escritura de activos | ✅ **PASS** | — |
| E0.2 — Refresh de POIs | ✅ **PASS** | — |
| E0.3 — Procedencia de caminabilidad | ✅ **PASS** | — |
| E0.4 — score_version + heurísticas fuera | ✅ **PASS** | — |
| E0.5 — CI gate | ⚠️ **PENDIENTE** | abrir el PR + 2 interruptores |
| C-A — Refresco fuera del PC del fundador | ✅ **RESUELTA** | configurar 4 secretos |

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

### E0.5 — CI gate ⚠️ PENDIENTE

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

#### Por qué sigue PENDIENTE

1. **El workflow no se ha ejecutado nunca en GitHub.** Se publicó el HEAD en la rama
   `ci/trust-gate-f0` para validarlo por PR sin usar `main` de conejillo, pero el workflow se
   dispara en `push: [main]` y `pull_request: [main]` — **hace falta abrir el PR**:
   → `https://github.com/contexxto/contexto-ai/pull/new/ci/trust-gate-f0`
   (`gh` no está instalado en esta máquina, así que no puedo abrirlo yo.)
2. **Este workflow no detiene el auto-deploy de Render por sí solo.** Render observa la rama;
   Actions no es su portero. Faltan:
   - **GitHub** → Settings → Branches → branch protection en `main` con el check `pruebas` requerido.
   - **Render** → Settings → Build & Deploy → **"Wait for CI to pass before deploying"**.

**No se considerará PASS** hasta comprobar que una prueba rota impide efectivamente el camino de
despliegue — no solo que pone el commit en rojo.

---

### C-A — El refresco sale del PC del fundador ✅ RESUELTA

Decisión del fundador: el refresco no seguirá dependiendo de esa máquina.

**Mecanismo elegido: GitHub Actions**, no un servicio nuevo. Cubre los seis requisitos sin
construir infraestructura, y el repositorio es público, así que los minutos no se facturan.

| Requisito | Cómo |
|---|---|
| Ejecución programada | `schedule: '0 22 * * 1'` — lunes 22:00 UTC = 17:00 en Quito, la misma hora que tenía la tarea de Windows |
| Ejecución manual | `workflow_dispatch` con selector de ciudad |
| Secretos | `DATABASE_URL_OVERRIDE`, `RESEND_API_KEY`, `ALERTA_OPS_EMAIL`, `NOTIFY_FROM_EMAIL` |
| Logs | Consola de Actions, con los mismos mensajes del script |
| Exit code bloqueante | El step propaga el código; 1 y 2 tumban el job |
| Alerta de fallo | El script avisa por Resend + el step `if: failure()` cubre el caso de agotar reintentos + GitHub notifica el workflow fallido |

Conserva la semántica de códigos (0 / 2 reintentable / 1 duro) y los reintentos por Overpass, con
espera de 10 min en vez de 15.

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

**C-C · Auto-deploy sin gate.** Motivó el reorden de unidades. Se cierra con los dos interruptores
de E0.5.

**C-D · La suite reportada como verde no lo estaba.** Corrige la evidencia del doc 01.

**C-E · El diagnóstico de E0.2 subestima el defecto.** No es obsolescencia, es rotura: el release
había desaparecido. Con matiz propio: el fallo **sí era ruidoso** (IOException + código 1), lo que
faltaba era que alguien lo leyera.

**Ninguna contradice las decisiones D1–D9.** D3 se aplicó tal como está congelada.

---

## 7. Impacto en producción y configuración

### Estado del despliegue

**Los 9 commits están en `main` local, sin pushear.** La rama remota `ci/trust-gate-f0` tiene el
mismo contenido, pero **no dispara deploy** (Render observa `main`).

**La corrida de POIs SÍ escribió en producción** — autorizada explícitamente. Es el único cambio
de datos vivos de toda la fase.

### Al desplegar, cambia el comportamiento observable

| Cambio | Efecto |
|---|---|
| `POST /api/v1/assets/` exige `X-API-Key` | 401 sin llave. Los scripts conocidos ya la enviaban. `API_KEY` está confirmada en producción. |
| Sin `API_KEY` en producción → 503 | Solo aplica si alguien la borra. Es el fail-closed. |
| Ruido y vegetación fuera del scoring | **Los scores cambian**, y los rankings con ellos. Ver el efecto de cobertura en §5, E0.4. |
| Razones nuevas en las tarjetas | Aparece *"no tenemos medición de ruido aquí"*. El frontend la pinta como cualquier razón no-alta; no requiere cambio de front. |
| Procedencia de caminabilidad | Deja de decir "OpenStreetMap" donde el walk score es estimado. |

### Configuración pendiente

**Secretos de GitHub Actions** (Settings → Secrets → Actions), para `refresco-pois`:
- `DATABASE_URL_OVERRIDE` — **obligatorio**; sin él el job falla temprano y con mensaje claro.
- `RESEND_API_KEY`, `ALERTA_OPS_EMAIL`, `NOTIFY_FROM_EMAIL` — para el aviso de fallo.

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
3. **El workflow `refresco-pois` no se ha ejecutado nunca en GitHub.** Está verificado por partes
   (YAML válido, dependencias suficientes en venv limpio, script probado en corrida real), pero
   su primera corrida en el runner sigue siendo su primera corrida. Conviene lanzarla a mano con
   `workflow_dispatch` antes de confiar en el lunes.

### Pendientes

| # | Qué | Quién | Esfuerzo |
|---|---|---|---|
| 1 | Abrir el PR de `ci/trust-gate-f0` → dispara `pruebas` | Carlos | 1 clic |
| 2 | GitHub → branch protection en `main`, check `pruebas` requerido | Carlos | minutos |
| 3 | Render → "Wait for CI to pass before deploying" | Carlos | minutos |
| 4 | Configurar los 4 secretos de Actions | Carlos | minutos |
| 5 | Lanzar `refresco-pois` a mano una vez para estrenarlo | Carlos + Claude | ~5 min |
| 6 | Desactivar la tarea de Windows "Refresco POIs Contexto" | Carlos | minutos |

### Recomendaciones fuera de alcance, no ejecutadas

- `@limiter.limit` en `POST /api/v1/assets/`, por consistencia con `/ingest`.
- Mover `verify_api_key` de `app/routers/chat.py` a `app/auth.py`. Hoy cinco routers importan una
  guardia de seguridad desde un router de chat. Toca la frontera que el doc 02 quiere trazar.

---

## 9. Recomendación

| Condición de fallo del Gate F0 (Plan §6) | Estado |
|---|---|
| Escritura crítica anónima | ✅ resuelto |
| Provenance contradictorio | ✅ resuelto |
| Scoring contaminado por heurística sin fuente | ✅ resuelto |
| Pipeline territorial no reproducible | ✅ **resuelto** — corrida completa verificada |
| Tests sin gate | ⚠️ **pendiente** |

### `DO NOT ADVANCE` — por un solo gate, y a un clic de distancia

Cuatro de los cinco están cerrados con evidencia reproducible, y C-A resuelta. El único que falta
es E0.5, y no por falta de código: el workflow está escrito, verificado en local en ambas
direcciones y esperando en la rama `ci/trust-gate-f0`.

**Para llegar a `ADVANCE TO CONTRACTS`:**

1. Abrir el PR → `https://github.com/contexxto/contexto-ai/pull/new/ci/trust-gate-f0`
   y confirmar que el check `pruebas` termina en verde.
2. Activar la branch protection en GitHub y el gate de CI en Render.
3. Comprobar que **una prueba rota impide el despliegue**, no solo que pinta el commit en rojo.

Hecho eso, actualizo este documento a `ADVANCE TO CONTRACTS` con la evidencia del CI.

---

## 10. Parada

Según `00_START_HERE` §11, la ejecución **se detiene aquí**. No se inicia Contracts / Fase 1 hasta
la revisión de Carlos y ChatGPT.
