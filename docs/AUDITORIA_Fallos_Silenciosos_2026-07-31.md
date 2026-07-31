# Auditoría — fallos silenciosos (2026-07-31)

Auditoría del código real de `app/` contra la política de "sin fallos silenciosos" de Houston
(gethouston.ai, MIT). **17 sitios** que tragan excepciones. La mayoría son legítimos y están
justificados en el comentario. Tres no lo son, y uno es serio.

> **Por qué importa aquí y no en abstracto:** el cuello de botella declarado de Contexto es
> adopción/conversión. Un fallo silencioso es la clase de defecto que no aparece en ninguna
> métrica — y cuando el fallo está en el *camino de instrumentación*, envenena la métrica misma.
> Esta auditoría es la precondición de que
> [RITUALES_DE_DATOS_CONTEXTO.md](RITUALES_DE_DATOS_CONTEXTO.md) diga la verdad.

---

## 🔴 1. GRAVE — la instrumentación de intención se traga todo

**`app/routers/chat.py:1264-1314`** — `registrar_intencion()` envuelve su cuerpo COMPLETO en
`try: … except Exception: pass`.

Esa función es el **único camino de escritura** de las dos tablas que sostienen la North Star:

- `intencion_sesion` (upsert del estado actual)
- `intencion_evento` (**el log append-only que ES la serie del lift**)

Y se invoca desde dos sitios, ambos fire-and-forget:

- `chat.py:741` → `asyncio.create_task(registrar_intencion(...))`
- `chat.py:806` → `_aio.create_task(registrar_intencion(...))`

### Por qué es grave

Si falla, **nadie se entera nunca**: ni log, ni contador, ni toast. La consecuencia no es "se pierde
un dato", es peor: **un registro que falla parcialmente es indistinguible de menos demanda.** El
reporte semanal leería menos intenciones y la conclusión natural sería "no está llegando gente" —
cuando la causa real sería un error de escritura.

Es exactamente el problema que el propio doc de rituales llama *"cero no es poco, cero es roto"*,
pero en su forma más peligrosa: **no se puede detectar**, porque no hay señal que distinguir.

### El disparador concreto no es hipotético

`app/models.py:238-246` define tres `CheckConstraint` sobre `intencion_sesion`:

```sql
estado IN ('anonimo','identificado','explorando','enganchado',
           'intencion','confirmado','completado','returning','dormido')
nivel  IN ('frio','tibio','caliente')
score  BETWEEN 0 AND 100
```

Si `app/intencion.py` alguna vez computa un `estado` fuera de esa lista, o un `score` de 101, el
insert falla — y con el `except: pass`, **falla en silencio para siempre**, sesión tras sesión, sin
una sola línea de log. Un cambio en el clasificador puede apagar la North Star sin que nada avise.

### Arreglo mínimo (no cambia el comportamiento no-bloqueante)

Mantener la garantía de "jamás rompe el chat" — que es correcta — pero **hacer el fallo visible**:

```python
log = logging.getLogger("intencion")  # el repo ya usa logging.getLogger (crm.tools, crm.guardrails)

except Exception as exc:  # noqa: BLE001 — jamás rompe el chat, pero JAMÁS en silencio
    log.error("registrar_intencion falló para session=%s: %s", session_id, exc, exc_info=True)
```

Best-effort y silencioso no son lo mismo. La política de Houston lo dice con precisión: la única
excepción legítima es *"no hay hilo de UI al cual notificar"* — y ahí se registra con nivel
`error`, nunca `warning`, y el conteo se revisa en el ritual diario.

**Además, subir el conteo de fallos al ritual diario:** un contador de `registrar_intencion` fallidos
es la única forma de saber que la serie del lift está sana. Sin él, el número semanal es un acto de fe.

---

## 🟠 2. MEDIO — el `create_task` pierde excepciones por diseño

**`chat.py:741` y `chat.py:806`.** El `try/except` de la línea 739-742 solo cubre la **creación** de
la tarea, no su ejecución. Una excepción dentro de la corrutina viaja al event loop, no al `try`.

Hoy queda tapado porque `registrar_intencion` ya se traga todo por dentro (hallazgo #1). Al arreglar
#1, este deja de importar. **Anotado para que nadie "arregle" #1 quitando el try interno y creando una
regresión invisible.**

---

## 🟡 3. LEVE — el match se degrada sin decirlo

**`app/routers/match.py:95`** → devuelve `texto[:400]` (el texto crudo) cuando falla la generación
de la frase.
**`app/routers/match.py:161`** → devuelve `{}` cuando falla `explicar_match`.

El `{}` significa **"ningún inmueble tiene explicación de por qué encaja"**. El usuario ve
resultados desnudos y no distingue "el motor no encontró razones" de "la llamada falló". Es
degradación de calidad invisible, en la superficie donde Contexto se diferencia de un portal de
filtros — precisamente el punto de la batalla contra Hiinmo.

No hace falta romper el flujo: basta un `log.warning` con el `activo_id` afectado para que aparezca
en el conteo diario.

---

## ✅ Lo que está BIEN y no hay que tocar

Once de los diecisiete sitios llevan justificación explícita en el comentario y son la categoría
"apagado deliberado" de la política:

- `chat.py:62` — *"etiquetar no debe romper el chat"*
- `chat.py:825` — *"persistir el foco es un extra"*
- `chat.py:1226` — *"marcar actividad jamás debe romper el chat"*
- `chat.py:1637` — *"tablas de handoff aún no existen"*
- `assets.py:1901` — *"best-effort; nunca debe tumbar nada"*
- `crm_guardrails.py:205, 270` — *"JSON malformado / token raro no debe tumbar el guardrail"*
- `reenganche_cron.py:307` — `asyncio.CancelledError`, que es control de flujo, no un fallo

Esta disciplina de comentar el porqué **ya es mejor que el promedio** y es la mitad del trabajo. Lo
que falta es la otra mitad: que además de no romper, **dejen rastro**.

Sin comentario que los justifique, para revisar: `app/agent/tools.py:355`, `chat.py:893`,
`chat.py:1061`, `app/rutas.py:381`, `app/rutas.py:586`.

---

## Prioridad

| # | Sitio | Severidad | Costo | Efecto |
|---|---|---|---|---|
| 1 | `chat.py:1313` | 🔴 Grave | 2 líneas | La North Star deja de poder apagarse en silencio |
| 2 | `chat.py:741`, `806` | 🟠 Medio | 0 (lo cubre #1) | Evita una regresión invisible al tocar #1 |
| 3 | `match.py:95`, `161` | 🟡 Leve | 2 líneas | Visibilidad de la degradación del diferenciador |

El #1 son dos líneas y protege la única métrica que sostiene el case study de MAKLO.

---

## Regla para lo que venga

De la constitución de Houston, adaptada — vale la pena pegarla en `CLAUDE.md`:

> Un `except` puede decidir **no romper el flujo**. No puede decidir **no dejar rastro**.
> Si no hay superficie de usuario a la cual notificar, hay un `log.error` y un contador.
> Best-effort ≠ silencioso.

Patrones prohibidos, con el caso más caro para Contexto arriba del todo:

1. **Una consulta fallida degradada a lista vacía.** Una lista vacía por error se ve idéntica a una
   lista vacía legítima: *"no hay inmuebles en esa zona"* cuando la verdad es *"la consulta falló"*.
   El usuario se va, no reclama, y el embudo lo registra como falta de demanda.
2. `except Exception: pass` sin comentario que justifique el porqué.
3. `except Exception: log.warning(...)` y continuar dentro de un bucle donde se esperaba progreso.
4. `create_task` sin `add_done_callback` que capture la excepción.
5. `.get(clave, default)` para tapar un dato que debería existir.

---

*Auditoría hecha el 2026-07-31 sobre `main` (`8f458ca`). Patrones tomados de la política de beta de
Houston (gethouston.ai, MIT) — ver `houston-capture/DESTILADO_WHABER_CONTEXTO.md` §G. Los hallazgos,
las líneas y el análisis de impacto son de Contexto.*
