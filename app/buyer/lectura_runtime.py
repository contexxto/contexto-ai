"""F3-TOOLS-MIN-1B · la sonda que demuestra QUIÉN llega al lector, no QUÉ se leyó.

LEVEL 1. `leer_contexto_del_principal` (1A) demostró que el lector es correcto — pero con
un principal **fabricado por las pruebas**. Lo que aquí se demuestra es la otra mitad, que
ninguna prueba de 1A podía dar:

```
Authorization: Bearer <jwt>
   → _decode → claims["sub"]        firma verificada contra JWKS
   → CurrentUser                    app/auth.py:165, único productor
   → chat()                         tras autoridad y tras la reclamación
   → observar_lectura_runtime       ESTO
   → leer_contexto_del_principal    el MISMO objeto, no una copia ni un id
```

Capacidad frente a autoridad efectiva. 1A era lo primero; esto es lo segundo.

## LO QUE ESTA SONDA DEVUELVE, Y POR QUÉ NO ES EL CONTEXTO

Devuelve un **desenlace**, nunca el `BuyerContextV0`. No es pudor: es la frontera de LEVEL 1
hecha de tipos en vez de disciplina. Si esta función devolviera el contexto, el siguiente que
pase por `chat.py` podría pasarlo al prompt, al encaje o al panel **sin tocar este fichero**,
y la unidad que prometía «disponible pero no usado» se habría convertido en otra cosa sin que
el diff lo delate. Lo leído se descarta al salir del `try`. Deliberado.

## LAS CUATRO PUERTAS, EN ORDEN

```
FLAG       buyer_context_read_shadow — PROPIO, apagado por defecto
AUTH       sin principal no hay raíz: el anónimo NO se lee y NO se inventa
COHORTE    allowlist fail-closed; vacía = nadie; sin comodín
LECTURA    y su fallo queda AISLADO del turno
```

**El flag es PROPIO y no el del updater**, y esa separación es una decisión, no una copia:
leer y escribir son capacidades distintas. `buyer_updater_shadow` enciende algo que hace
`commit()` sobre la memoria de una persona; esto enciende un `SELECT`. Reutilizar un booleano
para los dos obligaría a encender la escritura para poder observar la lectura, que es
exactamente el trueque que no queremos ofrecer.

**La cohorte sí se reutiliza**, y sólo su mitad pura. Se importa `sombra._habilitados`, que
lee `BUYER_SHADOW_ALLOWLIST`, normaliza a minúsculas y descarta las entradas vacías. No se
reutiliza `sombra._autorizado` porque su aviso nombra `BUYER_UPDATER_SHADOW`: emitido desde
el camino de lectura, señalaría al operador la variable equivocada. Y no se reescribe el
parser: dos parsers de la misma lista divergen, y el que divergiría es el que decide quién
entra.

## AWAITED, NO `create_task` — y por qué aquí sí

`marcar_actividad_lead`, `registrar_intencion` y `actualizar_en_sombra` son fire-and-forget
porque su valor no depende de haber terminado dentro del turno. El de esta sonda **sí**: la
propiedad que demuestra es «la lectura se completó con el principal correcto», y una tarea
suelta cuyo desenlace nadie espera no demuestra ninguna de las dos cosas — ni que terminó, ni
con quién.

Se paga con latencia, y por eso está acotada por flag ∧ allowlist. **No se dirá que esta
unidad tiene cero coste**: añade un `SELECT` y una conexión del pool, y el techo del Session
Pooler son 15 clientes por proyecto (incidente del 2026-08-18).

## FALLA ABIERTA HACIA EL TURNO

Un fallo de la sonda no puede tumbar un chat que iba bien. Se captura, se registra el
desenlace y el turno continúa. Lo que NO se hace es tragarlo en silencio: sin rastro, una
sonda rota sería indistinguible de un canary apagado.

## NADA SENSIBLE EN EL LOG

Ni el contexto, ni presupuesto, ni preferencias, ni `unresolved_questions`, ni el correo, ni
el `user_id` crudo, ni el JWT, ni el secreto de reanudación. Sólo el desenlace —vocabulario
cerrado—, la duración y, cuando existe, el número de revisión, que es un entero sin contenido.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import StrEnum

from app.buyer.lectura import PrincipalNoAutenticado, leer_contexto_del_principal
from app.buyer.sombra import _habilitados
from app.config import settings

logger = logging.getLogger(__name__)


class DesenlaceLectura(StrEnum):
    """Vocabulario CERRADO. Cada valor lleva a un diagnóstico distinto.

    Se separan a propósito los tres que un booleano fundiría en «no se leyó»:
    `DESACTIVADA` es el canary apagado, `FUERA_DE_COHORTE` es alguien que no está en la
    lista, y `SIN_PRINCIPAL` es un anónimo. Confundirlos mandaría al operador a mirar la
    variable equivocada.
    """

    DESACTIVADA = "desactivada"
    SIN_PRINCIPAL = "sin_principal"
    FUERA_DE_COHORTE = "fuera_de_cohorte"
    LEIDO = "leido"
    SIN_CONTEXTO = "sin_contexto"
    FALLO = "fallo"


@dataclass(frozen=True)
class ObservacionLectura:
    """El resultado de la sonda. **No contiene el `BuyerContextV0`, y no puede contenerlo.**

    `revision` es un entero o `None`; es lo único que sobrevive de lo leído, y no dice nada
    del comprador — sólo cuántas veces se ha actualizado su estado.
    """

    desenlace: DesenlaceLectura
    revision: int | None = None
    duracion_ms: int | None = None

    @property
    def hubo_lectura(self) -> bool:
        """¿Se llegó a consultar la base? `SIN_CONTEXTO` cuenta: se consultó y no había."""
        return self.desenlace in (DesenlaceLectura.LEIDO, DesenlaceLectura.SIN_CONTEXTO)


def _en_cohorte(user_id: str) -> bool:
    """Fail-closed: la única forma de entrar es pertenecer.

    Sin rama de comodín, y su ausencia es la propiedad: `"*"`, `"all"` o `"1"` son
    identificadores literales que nadie tiene. Sin `in` sobre la cadena cruda, que dejaría
    entrar a cualquier id que sea trozo de otro.
    """
    return user_id.strip().lower() in _habilitados()


async def observar_lectura_runtime(principal, *, db=None) -> ObservacionLectura:
    """Ejecuta la lectura del canary y devuelve **sólo su desenlace**.

    Args:
        principal: el `CurrentUser` que produjo la frontera autenticada. **El objeto
            original**, no una copia ni un id reconstruido — la continuidad de esa
            referencia es lo que la unidad viene a demostrar.
        db: sesión opcional; se pasa tal cual al lector.

    Returns:
        `ObservacionLectura`. **Nunca** el `BuyerContextV0`.
    """
    if not settings.buyer_context_read_shadow:
        return ObservacionLectura(DesenlaceLectura.DESACTIVADA)

    # El anónimo no se lee y no se inventa. Se comprueba ANTES de la cohorte y antes de la
    # base: un turno sin sujeto no debe consumir ni una conexión del pool.
    user_id = (getattr(principal, "user_id", "") or "").strip() if principal is not None else ""
    if not user_id:
        return ObservacionLectura(DesenlaceLectura.SIN_PRINCIPAL)

    if not _en_cohorte(user_id):
        # El rechazo NO se registra: es el caso normal —todo usuario no-canary pasa por aquí
        # en cada turno— y anotarlo convertiría el log en una lista de quién conversó.
        return ObservacionLectura(DesenlaceLectura.FUERA_DE_COHORTE)

    arranque = time.monotonic()
    try:
        contexto = await leer_contexto_del_principal(principal, db=db)
    except PrincipalNoAutenticado:
        # No debería ocurrir: la puerta AUTH de arriba ya lo descartó. Si ocurre, es que las
        # dos nociones de «sin raíz» han divergido, y eso hay que verlo.
        _registrar(DesenlaceLectura.FALLO, None, arranque, "principal_no_autenticado")
        return ObservacionLectura(DesenlaceLectura.FALLO,
                                  duracion_ms=_ms(arranque))
    except Exception as e:  # noqa: BLE001 — LA GARANTÍA: el turno nunca cae por la sonda
        _registrar(DesenlaceLectura.FALLO, None, arranque, type(e).__name__)
        return ObservacionLectura(DesenlaceLectura.FALLO, duracion_ms=_ms(arranque))

    desenlace = (DesenlaceLectura.SIN_CONTEXTO if contexto is None
                 else DesenlaceLectura.LEIDO)
    revision = None if contexto is None else contexto.context_revision
    _registrar(desenlace, revision, arranque, None)
    # `contexto` muere aquí. Ver el encabezado del módulo: es la frontera de LEVEL 1.
    return ObservacionLectura(desenlace, revision=revision, duracion_ms=_ms(arranque))


def _ms(arranque: float) -> int:
    return int((time.monotonic() - arranque) * 1000)


def _registrar(desenlace: DesenlaceLectura, revision: int | None,
               arranque: float, causa: str | None) -> None:
    """El rastro. Vocabulario cerrado, duración y revisión; nada del comprador.

    `FALLO` va a `error` porque significa que el canary no está midiendo lo que dice medir.
    El resto es informativo. La `causa` es el NOMBRE DE LA CLASE de la excepción, nunca su
    mensaje: un mensaje puede arrastrar una cadena de conexión o un fragmento del estado.
    """
    nivel = logging.ERROR if desenlace is DesenlaceLectura.FALLO else logging.INFO
    logger.log(nivel, "buyer read canary · desenlace=%s revision=%s ms=%s%s",
               desenlace.value, revision, _ms(arranque),
               f" causa={causa}" if causa else "")
