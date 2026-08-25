"""E2.4 — el verificador de prosa, como componente del Decision Core.

Una costura, no una reescritura. `app/verificacion_prosa.py` no se toca: qué cuenta como
violación sigue decidiéndose allá, con sus mismos códigos, gravedades y evidencias. Lo
único que se agrega aquí es la **proyección** de esos hallazgos al vocabulario que
`ExplanationV0` ya congeló en F1.

La dirección de la dependencia es el punto:

    router  →  decision.verify  →  verificacion_prosa

y no al revés. Antes el router leía hallazgos crudos; interpretar la gravedad allí habría
puesto una regla de decisión en la capa de transporte, que es justo lo que F2 vino a sacar
de ahí.

QUÉ NO HACE ESTO, y conviene que quede escrito porque la tentación es real:

  · no bloquea, no reescribe, no reintenta y no retrasa la respuesta de la persona. La
    auditoría sigue siendo POST-RESPUESTA y en observación. Bloquear sin saber la
    frecuencia con que la prosa desobedece sería apostar el turno de un usuario real a una
    corazonada — el razonamiento completo está en el docstring del router;
  · no persiste el `ExplanationV0`. Guardarlo exigiría meter los `DecisionContextV0`
    completos en el checkpointer o construir un store, y eso es F6. Que el objeto sea
    válido se demuestra con `model_copy`, no con infraestructura nueva;
  · no lleva contadores. `verificacion_prosa.registrar` sigue siendo el dueño de su
    observabilidad; duplicarla aquí daría dos cifras del mismo hecho.

La función es pura: sin I/O, sin FastAPI, sin LLM, sin estado.
"""

from __future__ import annotations

from app.contracts.decision_v0 import ExplanationV0, VerificationStatus
from app.verificacion_prosa import ALTA, MEDIA, verificar_prosa


class GravedadDesconocida(RuntimeError):
    """Un hallazgo con una gravedad fuera de `alta | media`.

    Es un fallo de programación, no un dato raro: significa que alguien agregó una
    gravedad en `verificacion_prosa.py` sin decidir cómo se proyecta. Normalizarla en
    silencio —mandarla a `WARNING` "por si acaso"— haría que una violación nueva y grave
    se reportara como leve para siempre, sin que nadie se entere.

    En producción llega al `except Exception` del router y queda en el log sin tumbar el
    turno: el guardián jamás rompe la respuesta de la persona. En la suite falla ruidoso,
    que es donde tiene que doler.
    """


def _estado(hallazgos: list[dict]) -> VerificationStatus:
    """Semántica del Blueprint, tal como la documenta `VerificationStatus`."""
    gravedades = {h.get("gravedad") for h in hallazgos}

    if desconocidas := gravedades - {ALTA, MEDIA}:
        raise GravedadDesconocida(
            f"gravedad(es) {sorted(map(str, desconocidas))} sin proyección a "
            f"VerificationStatus. Decidir el mapeo explícitamente; no se normaliza sola."
        )
    if ALTA in gravedades:
        return VerificationStatus.FAILED
    if MEDIA in gravedades:
        return VerificationStatus.WARNING
    return VerificationStatus.PASSED


def auditar_explicacion(
    reply: str,
    cards: list[dict] | None,
    preferencias: dict | None = None,
    descartadas: list[dict] | None = None,
) -> tuple[ExplanationV0, list[dict]]:
    """Audita la prosa ya emitida y proyecta el veredicto al contrato.

    Devuelve las DOS cosas a propósito:

      · el `ExplanationV0`, que es lo que un `DecisionContextV0` puede citar;
      · los hallazgos LEGACY íntegros —mismo `codigo`, `gravedad`, `detalle`, `evidencia`,
        mismo orden—, porque `registrar()` y los evals los consumen tal cual y comprimirlos
        al estado perdería justo la frase que hace accionable el informe.

    Un estado sin sus hallazgos diría "algo falló" sin decir qué. Unos hallazgos sin estado
    obligarían a cada consumidor a reinterpretar la gravedad por su cuenta, que es el
    problema que esta costura elimina.
    """
    hallazgos = verificar_prosa(reply, cards, preferencias, descartadas)
    return ExplanationV0(verification_status=_estado(hallazgos)), hallazgos
