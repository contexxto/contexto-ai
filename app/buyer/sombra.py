"""E3.2b.4 · Shadow wiring — la memoria del comprador corre, y no cambia nada.

Primera vez que esta cadena toca producción. Y lo hace **sin autoridad sobre la
conversación**: observa el turno, escribe su propia memoria y no participa en lo que el
usuario lee.

```
turno del chat  →  responde el carril legacy      ← ÚNICO que habla con el usuario
                →  actualizar_en_sombra(...)       ← esto. No devuelve nada al turno.
```

## Por qué sombra y no "ya está integrado"

Que el pipeline corra y que el producto mejore son dos afirmaciones distintas, y mezclarlas
haría imposible saber cuál falló. Esta unidad demuestra tres cosas y ninguna más:

```
1  procesa el HumanMessage REAL de un usuario autenticado
2  persiste sin romper el carril legacy
3  cualquier fallo suyo queda aislado y observable
```

Consumir `unresolved_questions` para repreguntar es otra unidad. Hasta que exista, el
sistema registra preguntas que nadie hace — y decirlo así evita el peor final posible para
toda esta fase: dar por cerrado el ciclo porque el pipeline "ya corre".

## Las cuatro puertas, en orden

```
FLAG      apagada por defecto. Sin ella no se ejecuta ni una línea del updater.
AUTH      sin usuario autenticado no hay raíz: un anónimo no crea estado durable.
COSTURA   `ultimo_mensaje_usuario_identificado` — F3.0b, que llevaba desde su
          creación sin consumidor. Éste es el primero.
ESQUEMA   si las tablas no están, se registra UNA vez y se calla. Un despliegue sin
          migrar no puede convertir cada turno en una traza de error.
```

## Aislamiento

`asyncio.create_task` sobre una corrutina que **no propaga nada**. Es el mismo patrón que
`registrar_intencion` y `marcar_actividad_lead`, y por el mismo motivo: el turno ya
respondió cuando esto empieza. Si el updater falla, falla solo.

Lo que sí hace es dejar rastro: cada desenlace se registra con su `EstadoActualizacion`, así
que se puede leer qué está haciendo la sombra sin que nada de eso llegue al usuario.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.buyer.actualizador import EstadoActualizacion, actualizar
from app.buyer.mensaje import ultimo_mensaje_usuario_identificado
from app.config import settings

logger = logging.getLogger(__name__)

_TABLAS = ("buyer_context_heads", "buyer_context_revisions")

_esquema_ausente_avisado = False
"""Se avisa UNA vez, no en cada turno. Un despliegue sin migrar es una condición estable:
repetir la traza en cada mensaje ahogaría el log sin añadir información."""


async def _hay_esquema(db) -> bool:
    from sqlalchemy import text

    global _esquema_ausente_avisado
    for tabla in _TABLAS:
        existe = (await db.execute(
            text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{tabla}"})).scalar()
        if not existe:
            if not _esquema_ausente_avisado:
                _esquema_ausente_avisado = True
                logger.warning(
                    "buyer shadow inactivo: falta la tabla %s. Aplicar las migraciones 028 "
                    "y 029 antes de activar el flag.", tabla)
            return False
    return True


async def actualizar_en_sombra(user, messages) -> None:
    """Procesa el último mensaje del usuario contra su memoria durable. **No devuelve nada.**

    Se llama con `asyncio.create_task` DESPUÉS de que el turno respondió. No tiene forma de
    influir en la respuesta ni de retrasarla: si tardara, tarda sola; si falla, falla sola.

    El `retrieved_at` sale de aquí y no del reducer — R-IDEMP-1: es el instante REAL en que
    procesamos, y el reducer no tiene reloj a propósito. Que un reintento traiga otro
    instante es correcto y la igualdad canónica ya lo ignora para esta evidencia.
    """
    try:
        if not settings.buyer_updater_shadow:
            return
        if user is None or not (getattr(user, "user_id", "") or "").strip():
            # Un anónimo no tiene raíz. No es un error del turno: es que no hay comprador.
            return

        mensaje = ultimo_mensaje_usuario_identificado(messages)
        if mensaje is None:
            return

        from app.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            if not await _hay_esquema(db):
                return
            resultado = await actualizar(
                user.user_id, mensaje,
                retrieved_at=datetime.now(timezone.utc), db=db)
            if resultado.persistido:
                await db.commit()
            else:
                await db.rollback()

        _registrar(resultado, mensaje)

    except Exception as e:  # noqa: BLE001 — LA GARANTÍA DE ESTA UNIDAD
        # El turno ya respondió. Una excepción aquí no puede alcanzarlo, y tragarla en
        # silencio dejaría la sombra invisible: se registra con traza para que el fallo sea
        # observable sin ser propagable.
        logger.exception("buyer shadow falló y quedó aislado (%s)", type(e).__name__)


def _registrar(resultado, mensaje) -> None:
    """El rastro que hace la sombra legible. Cada desenlace tiene su nivel.

    `FALLIDO` va a `error` porque significa que el mismo mensaje produjo dos estados
    distintos — o el intérprete no es determinista, o hay un replay corrupto. `CONFLICTO` va
    a `warning`: es una actualización que NO se aplicó y alguien tendrá que decidir qué hacer
    con ella. El resto es informativo.
    """
    nivel = {
        EstadoActualizacion.FALLIDO: logging.ERROR,
        EstadoActualizacion.CONFLICTO: logging.WARNING,
    }.get(resultado.estado, logging.INFO)

    logger.log(
        nivel, "buyer shadow · mensaje=%s estado=%s revision=%s%s",
        mensaje.message_id, resultado.estado.value, resultado.revision,
        f" motivo={resultado.motivo}" if resultado.motivo else "")
