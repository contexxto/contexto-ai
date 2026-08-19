# Incidente 2026-08-18 — producción sin historial (degradación silenciosa)

**Duración:** ~6:06 PM → 7:32 PM (1h 26m). **Detección:** por casualidad, mirando otra cosa.

## Síntoma

Producción respondía **200 en todo** — nada estaba "caído". Pero:

- Todas las conversaciones aparecían como "Conversación sin título".
- Ninguna conversación abría.
- El menú no mostraba el rol de corredor (CRM ausente).

## Causa raíz

**Dos pools independientes contra un mismo techo de 15**, sin que ninguno supiera del otro:

| Pool | Dónde | Máximo (antes) |
|---|---|---|
| SQLAlchemy (datos) | `app/database.py` | 10 + 20 = **30** |
| AsyncPostgresSaver (checkpointer) | `app/agent/graph.py` | **10** |

Total posible: **40** contra el límite de **15** del Session Pooler de Supabase
(`EMAXCONNSESSION: max clients reached in session mode`).

Esto no era nuevo: venía produciendo fallos intermitentes sin patrón desde antes
(`visita no registrada (InternalServerError)` en los logs).

## Qué lo volvió visible

Un deploy reinició producción **mientras un backend de desarrollo local, apuntando a la
MISMA base de Supabase, tenía tomadas las conexiones**. El checkpointer no pudo abrir su
pool al arrancar y `setup_checkpointer()` cayó a su rama de degradación:

```python
except Exception as exc:
    print(f"  [WARN] Postgres checkpointer no disponible ({exc}); usando MemorySaver")
```

El grafo arrancó con `MemorySaver` — memoria vacía, sin historial. La app siguió sirviendo
todo con 200, porque los datos (`chat_sessions`) sí cargaban por SQLAlchemy; lo que faltaba
era el **estado** de cada conversación, que vive en el checkpointer.

En `chat.py` el fallo quedaba doblemente enterrado, porque el título se calcula así:

```python
try:
    state = await agent_graph.compiled_graph.aget_state(...)
    titulo_auto = ...
except Exception:
    pass                       # ← se traga el error, una vez por conversación
titulo = (r["titulo"] or None) or titulo_auto or "Conversación sin título"
```

## Lo que lo hizo peligroso

No fue el agotamiento de conexiones — fue que **la degradación no falla ruidosamente**.
Un servicio caído se nota en un minuto. Un servicio que responde 200 sin memoria puede
correr días. Las alarmas de salud (`/health` → 200) no lo detectan por diseño.

## Corrección al diagnóstico de arriba (auditoría del 2026-08-19)

**La primera versión de este documento culpaba por igual a los dos pools. Era impreciso**, y
la imprecisión importaba porque escondía el modo de fallo real:

`AsyncConnectionPool` no reclama `max_size` al arrancar: `open(wait=True)` bloquea hasta
conseguir **`min_size`**, cuyo default en psycopg_pool es **4**. O sea, el checkpointer solo
necesitaba 4 conexiones y no las consiguió en 10 segundos. Quien se había comido el techo
era el pool de SQLAlchemy, con su máximo de 30.

Dos consecuencias que la primera versión no veía:

- **Bajar el checkpointer de 10 a 6 apenas influyó.** Lo que resolvió el incidente fue
  bajar SQLAlchemy de 30 a 6. El límite superior del checkpointer nunca fue el problema.
- **El modo de fallo seguía vivo tras el "arreglo".** Con `min_size=4` y `timeout=10`
  intactos, cualquier presión sobre el techo durante un arranque reproduce el incidente
  igual. Corregido en el commit de esta auditoría: `min_size=1` (arranca con una y crece
  bajo demanda) y `timeout=30`.

## Correcciones aplicadas

1. **Los dos pools bajan a un presupuesto común:** 4 + 2 (SQLAlchemy) + 6 (checkpointer)
   = **12**, con 3 de margen. Configurables por entorno (`DB_POOL_SIZE`,
   `DB_MAX_OVERFLOW`, `CHECKPOINTER_POOL_SIZE`) y declarados en `render.yaml`.
   ⚠️ Verificar en Render → Environment que esas variables estén realmente aplicadas: el
   servicio tiene variables que NO están en `render.yaml` (p. ej. `ALLOWED_ORIGINS`), señal
   de que se configuran a mano. Si no están, produccion corre con los defaults del código
   —que coinciden— pero la declaración del blueprint es decorativa.
2. **El arranque del checkpointer deja de ser todo-o-nada:** `min_size=1` + `timeout=30`.
   Esta es la corrección que de verdad cierra el modo de fallo (ver la sección anterior).
3. **Los scripts sueltos dejan de poder agotar el techo solos:** `scripts/asignar_corredor.py`,
   `spike_commute_hora_pico.py` y `foso_pois_spike.py` abrían engines con el pool por
   defecto de SQLAlchemy (5+10 = **15**, el techo entero). Pasan a `NullPool` — usan una
   conexión secuencial y no tienen por qué reservar más.
4. **La degradación ahora grita** (banner de 72 caracteres en el arranque, con la causa y
   qué hacer), en vez de una línea `[WARN]` perdida entre el ruido de startup.
5. **`/health` reporta el modo de la memoria** (`"memoria": "postgres" | "volatil"`), para
   que un chequeo externo distinga "vivo" de "vivo pero amnésico". Sigue devolviendo 200
   aun degradado a propósito — ver el docstring del endpoint.
6. `pool_recycle=3600` en SQLAlchemy. **Nota honesta:** `pool_pre_ping=True` ya cubría el
   caso de conexiones muertas; esto es redundante. Se deja porque no estorba, pero no
   cuenta como parte del arreglo.

## Pendiente (no resuelto aquí)

- ~~**El techo de 15 sigue siendo el techo.**~~ **Resuelto para desarrollo el 2026-08-19:**
  `app/database.py` detecta el puerto y aplica la configuración que toca. Apuntando el
  `.env` local al **6543** (Transaction Pooler), PgBouncer multiplexa y la competencia con
  producción desaparece de raíz, en vez de repartirse un techo que no daba (5 + 12 = 17
  contra 15). Producción sigue en 5432 sin cambios.
  Probado de extremo a extremo contra el pooler real, no solo en tests: 6 consultas
  parametrizadas repetidas + 1 sobre `profiles`, sin colisión de prepared statements.
  **Para adoptarlo, cambia el puerto en tu `.env` local.** Con el 6543, los tres valores
  de pool documentados en `.env.example` dejan de importar (NullPool no agrupa).
- ~~**Nadie lee `/health`.**~~ **Resuelto el 2026-08-19:** `.github/workflows/vigia-salud.yml`
  lee el CUERPO (no el código HTTP, que es 200 a propósito aun degradado) y falla el job
  —lo que dispara el correo de GitHub— si `status != "healthy"`, diciendo qué hacer según
  el caso. Distinto del keepalive, que solo despierta al servicio.
  **Su límite honesto, medido y no estimado** (60 corridas del keepalive, 18-19 ago):
  GitHub estrangula el cron — mediana **34 min**, p90 **49 min**, máximo **109 min**.
  Típicamente avisa mucho antes que las 1h26m que costó la vez que pasó, pero **en su peor
  caso no habría ayudado gran cosa**. Y el estrangulamiento varía: una medición de
  principios de agosto dio mediana de 89 min. Si hiciera falta detección en minutos, la
  salida es un monitor externo con chequeo por palabra clave en el cuerpo.
  Además, si los correos de GitHub Actions se filtran o se ignoran, la alarma no existe.
- **El solape de deploys no está medido.** Render levanta la instancia nueva mientras la
  vieja sirve, así que durante esa ventana conviven dos presupuestos (12 + 12) contra el
  techo de 15. El deploy del 19-08 pasó sin incidente, pero con el backend local apagado;
  no se ha probado el caso con presión real.
