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

## Correcciones aplicadas

1. **Los dos pools bajan a un presupuesto común:** 4 + 2 (SQLAlchemy) + 6 (checkpointer)
   = **12**, con 3 de margen. Configurables por entorno (`DB_POOL_SIZE`,
   `DB_MAX_OVERFLOW`, `CHECKPOINTER_POOL_SIZE`) y declarados en `render.yaml`.
2. **`pool_recycle=3600`** en SQLAlchemy: el pooler corta conexiones ociosas y no sirve
   reutilizarlas muertas.
3. **La degradación ahora grita** (banner de 72 caracteres en el arranque, con la causa y
   qué hacer), en vez de una línea `[WARN]` perdida entre el ruido de startup.

## Pendiente (no resuelto aquí)

- **El techo de 15 sigue siendo el techo.** Dev local y producción comparten proyecto de
  Supabase, así que con ambos arriba el consumo se duplica. Las salidas reales son el
  **pooler en modo transacción** (puerto 6543, admite muchos más clientes) o un proyecto
  de Supabase separado para desarrollo. Decisión pendiente.
- **Una alarma que detecte esto.** Hoy `/health` devuelve 200 con la memoria rota. Debería
  reportar el modo del checkpointer, para que un chequeo externo pueda distinguir
  "vivo" de "vivo pero amnésico".
