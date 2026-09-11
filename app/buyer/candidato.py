"""F3-CURRENT-TURN-CANDIDATE-R0B · el estado que ESTE turno produciría, en sombra.

La pieza que faltaba para responder la pregunta que bloqueó LEVEL 2: la memoria persistida
siempre es la del turno ANTERIOR, y conceder autoridad a un valor viejo pisaría la corrección
que la persona acaba de decir. Aquí se calcula —sin persistir y sin decidir— el estado que el
turno actual produciría.

```
BuyerContext persistido N-1     (1A/1B · principal confiable)
        +
HumanMessage canónico N         (R0A · id acuñado por el servidor)
        ↓  computar_candidato  ← LA MISMA política de E3.2, no una copia
CandidatoTurno N
        ↓
se descarta
```

## UNA POLÍTICA, DOS MODOS

`actualizador.computar_candidato` es la primera mitad de `actualizar()`, **extraída**, y
`actualizar()` la llama. No hay dos implementaciones de precedencia, conflicto,
`explícito > inferido`, corrección ni moneda: hay una, y vive donde siempre vivió. Este
módulo no decide nada sobre el comprador; decide **si mirar**.

## POR QUÉ EL ARTEFACTO LLEVA EL LOTE

`interpretar_mensaje` usa el LLM, y dos llamadas sobre el mismo texto pueden no coincidir.
Si R0C reinterpretara para persistir, decidiríamos con un candidato y guardaríamos otro. El
`CandidatoTurno` lleva la extracción exacta para que la unidad que persista use **este**
cómputo y no uno nuevo. Es la diferencia entre converger y parecerse.

## LAS CUATRO PUERTAS

```
FLAG       buyer_current_turn_candidate_shadow — PROPIO, apagado por defecto
AUTH       sin principal no hay comprador: el anónimo no se computa ni se inventa
COHORTE    allowlist fail-closed; vacía = nadie; sin comodín
IDENTIDAD  el mensaje tiene que traer el id canónico de R0A, o no se computa
```

**Tercer flag, y es deliberado.** `buyer_updater_shadow` enciende una escritura;
`buyer_context_read_shadow` enciende un `SELECT`; éste enciende además **una llamada al
LLM**. Tres costes distintos, tres interruptores. Reutilizar uno obligaría a pagar el caro
para observar el barato.

## DOBLE INTERPRETACIÓN — DECLARADA, NO ESCONDIDA

Con este flag Y `buyer_updater_shadow` encendidos a la vez, el mismo turno se interpreta
**DOS veces**: una aquí, antes de la decisión, y otra en `actualizar_en_sombra` después. R0B
no lo arregla —unir candidato y persistencia es R0C— pero tampoco lo disimula: mientras
existan dos interpretaciones independientes **no se puede afirmar que el candidato y lo
persistido converjan**, y las pruebas lo miden en vez de suponerlo.

## LO QUE NO HACE

No persiste (cero `anexar_revision`, cero `commit`). No entra en `AgentState` ni en
`RunnableConfig` ni en el prompt. No llega a `construir_panel`. No cambia ranking, panel,
prosa ni herramientas. No concede autoridad: `CURRENT_AUTHORITY_WHITELIST` sigue vacía.

## NADA SENSIBLE EN EL LOG

Ni el contexto, ni el candidato, ni presupuesto, ni mascotas, ni `unresolved_questions`, ni
el `user_id` crudo, ni el correo, ni el token. Sólo el desenlace —vocabulario cerrado—, la
duración, la revisión base y cuántas afirmaciones trajo el lote.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import StrEnum

from app.buyer.actualizador import CandidatoTurno, ComputoCandidato, computar_candidato
from app.buyer.mensaje import ultimo_mensaje_usuario_identificado
from app.buyer.sombra import _habilitados
from app.config import settings

logger = logging.getLogger(__name__)


class DesenlaceCandidato(StrEnum):
    """Vocabulario CERRADO. Cada valor lleva a un diagnóstico distinto."""

    DESACTIVADA = "desactivada"
    SIN_PRINCIPAL = "sin_principal"
    FUERA_DE_COHORTE = "fuera_de_cohorte"
    SIN_MENSAJE = "sin_mensaje"
    SIN_AFIRMACIONES = "sin_afirmaciones"
    CALCULADO = "calculado"
    FALLO = "fallo"


@dataclass(frozen=True)
class ObservacionCandidato:
    """El desenlace, con el CÓMPUTO COMPLETO cuando lo hay.

    A DIFERENCIA de `ObservacionLectura` (1B), esto **sí** transporta el cómputo: R0C lo
    necesita para persistir exactamente este candidato en vez de reinterpretar el turno.

    LLEVA EL `ComputoCandidato`, NO SÓLO EL `CandidatoTurno` (R0C). El artefacto por sí solo
    no basta para un rebase correcto: `rutas_divergentes(base, ultima)` necesita la **base
    completa**, y `base_context_revision` es un entero del que no se puede reconstruir. Con
    sólo el artefacto, la fase de persistencia tendría que volver a cargar «la revisión que
    cree que era la base» — y eso es exactamente perder información y adivinarla después.

    `candidato` queda como **propiedad derivada**, no como segundo campo: dos copias
    independientes del mismo dato pueden divergir, y la que divergiría sería la que decide.
    """

    desenlace: DesenlaceCandidato
    computo: ComputoCandidato | None = None
    duracion_ms: int | None = None

    @property
    def candidato(self) -> CandidatoTurno | None:
        """El artefacto, derivado del cómputo. Nunca una copia almacenada aparte."""
        return self.computo.candidato if self.computo is not None else None

    @property
    def hubo_computo(self) -> bool:
        return self.desenlace is DesenlaceCandidato.CALCULADO


def _en_cohorte(user_id: str) -> bool:
    """Fail-closed, y sin comodín: la única forma de entrar es pertenecer."""
    return user_id.strip().lower() in _habilitados()


async def observar_candidato_del_turno(principal, mensajes, *, retrieved_at,
                                       proponente=None, db=None) -> ObservacionCandidato:
    """Calcula el candidato de este turno y devuelve su desenlace. **No persiste nada.**

    Args:
        principal: el `CurrentUser` de la frontera autenticada. El objeto original.
        mensajes: los mensajes del turno; el último del usuario debe traer el id canónico.
        retrieved_at: el instante del procesamiento, inyectado. El mismo que verá el reductor.
        proponente: intérprete inyectable — lo usan las pruebas para ser deterministas.
        db: sesión opcional; se pasa tal cual.
    """
    if not settings.buyer_current_turn_candidate_shadow:
        return ObservacionCandidato(DesenlaceCandidato.DESACTIVADA)

    user_id = (getattr(principal, "user_id", "") or "").strip() if principal is not None else ""
    if not user_id:
        # Un anónimo no tiene comprador. Se sale antes de la cohorte y antes de la base.
        return ObservacionCandidato(DesenlaceCandidato.SIN_PRINCIPAL)

    if not _en_cohorte(user_id):
        return ObservacionCandidato(DesenlaceCandidato.FUERA_DE_COHORTE)

    arranque = time.monotonic()
    try:
        mensaje = ultimo_mensaje_usuario_identificado(mensajes)
        if mensaje is None:
            return ObservacionCandidato(DesenlaceCandidato.SIN_MENSAJE,
                                        duracion_ms=_ms(arranque))

        computo = await computar_candidato(
            user_id, mensaje, retrieved_at=retrieved_at, proponente=proponente, db=db)
    except Exception as e:  # noqa: BLE001 — LA GARANTÍA: el turno nunca cae por la sonda
        _registrar(DesenlaceCandidato.FALLO, None, arranque, type(e).__name__)
        return ObservacionCandidato(DesenlaceCandidato.FALLO, duracion_ms=_ms(arranque))

    if computo.candidato is None:
        _registrar(DesenlaceCandidato.SIN_AFIRMACIONES, None, arranque, computo.motivo)
        return ObservacionCandidato(DesenlaceCandidato.SIN_AFIRMACIONES,
                                    duracion_ms=_ms(arranque))

    _registrar(DesenlaceCandidato.CALCULADO, computo.candidato, arranque, None)
    return ObservacionCandidato(DesenlaceCandidato.CALCULADO,
                                computo=computo, duracion_ms=_ms(arranque))


def _ms(arranque: float) -> int:
    return int((time.monotonic() - arranque) * 1000)


def _registrar(desenlace: DesenlaceCandidato, candidato: CandidatoTurno | None,
               arranque: float, causa: str | None) -> None:
    """El rastro. Nada del comprador: ni valores, ni campos tocados, ni preguntas abiertas.

    `FALLO` va a `error` porque significa que el canary no mide lo que dice medir. La `causa`
    es el NOMBRE DE LA CLASE de la excepción, nunca su mensaje: un mensaje puede arrastrar
    una cadena de conexión o un fragmento del estado.
    """
    nivel = logging.ERROR if desenlace is DesenlaceCandidato.FALLO else logging.INFO
    logger.log(nivel,
               "buyer candidate canary · desenlace=%s base_revision=%s afirmaciones=%s ms=%s%s",
               desenlace.value,
               None if candidato is None else candidato.base_context_revision,
               None if candidato is None else len(candidato.lote.afirmaciones),
               _ms(arranque), f" causa={causa}" if causa else "")
