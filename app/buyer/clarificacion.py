"""BUYER-UNRESOLVED-CONSUMER-R1 · la primera autoridad productiva de la memoria del comprador.

Cierra el hueco que la reentrada nombró: las `unresolved_questions` **se producen desde E3.2 y no
las consume nadie**. Aquí el producto aprende a hacer UNA pregunta —la que este turno abrió— y
nada más.

## LA FRONTERA, Y ES DELIBERADAMENTE PEQUEÑA

No se concede autoridad a `BuyerContextV0`. Se concede a una sola afirmación:

    «este turno dejó una ambigüedad persistida, y ésta es la pregunta determinista que la resuelve»

Entregar el contexto entero al modelo porque ya existe sería ampliar la superficie sin una
frontera falsable. Esto sí la tiene: **una pregunta, de una dimensión, con texto del producto**.

## DE DÓNDE SALE LA PREGUNTA, Y DE DÓNDE NO

Del `BuyerContextV0` **resultante de la persistencia**, nunca de una segunda lectura del mensaje.
El turno ya se interpretó una vez —`computar_candidato`— y reinterpretarlo daría otra extracción:
se decidiría con un candidato y se preguntaría por otro. Aquí no hay LLM, ni extractor, ni parsing.

El TEXTO es el que `reductor._pregunta_de` ya fija por dimensión. Ese módulo lo explica mejor que
esta cabecera: *«no se persiste el motivo del modelo … la pregunta es del producto, no del
modelo»*. El motivo libre del proponente **no puede llegar a la persona**, y como aquí sólo se
copia `question` del contrato, no hay por dónde.

## SÓLO LA NUEVA. NO LAS PENDIENTES

Se compara la base contra el resultado por `about_field`, y sólo sale lo que este turno **abrió**.

Es una decisión de producto, no una optimización: repetir en cada turno una pregunta que la
persona ya ignoró convierte la aclaración en ruido, y el ruido se aprende a ignorar. Si alguien
calla sobre su presupuesto tres veces, preguntárselo una cuarta no es memoria, es insistencia.

## ORDEN

El del contrato. `reductor` ya materializa las preguntas en un orden determinista
—`sorted(abiertas, key=lambda c: c.value)`— así que basta respetar el de la tupla resultante y
tomar la primera nueva. **No se reordena aquí**, y menos por criterio del modelo: dos ordenaciones
del mismo estado darían dos preguntas distintas y la idempotencia dejaría de significar nada.

## LAS CINCO PUERTAS

```
FLAG        buyer_unresolved_product — PROPIO, apagado de fábrica
COHORTE     buyer_shadow_allowlist, fail-closed, sin comodín
CÓMPUTO     tiene que existir un ComputoCandidato válido de ESTE turno
PERSISTENCIA el ResultadoUpdater tiene que decir que se persistió
NOVEDAD     el turno tiene que haber abierto una pregunta que antes no estaba
```

La cuarta es la que ordena el tiempo: **la aclaración no puede verse antes de saber que la
tentativa de persistencia terminó bien**. Preguntar por algo que no quedó guardado produciría un
turno siguiente que vuelve a preguntar lo mismo, y la persona vería a Contexto olvidando en vivo.

## LO QUE NO SALE

Ni `buyer_id`, ni evidencia, ni `source_message_id`, ni la revisión, ni el presupuesto anterior,
ni el contexto, ni el motivo del modelo. La salida tiene **dos claves** y se construye campo a
campo desde el contrato —nunca por volcado—, que es lo que hace imposible que un campo nuevo del
contrato se cuele solo a la respuesta.
"""
from __future__ import annotations

from app.buyer.sombra import _habilitados
from app.config import settings

__all__ = ["clarificacion_nueva_del_turno", "clarificacion_del_turno"]


def _preguntas(contexto) -> tuple:
    """Las `unresolved_questions` de un contexto, tolerando el `None`.

    `contexto` puede faltar —una base inexistente es un comprador nuevo— y eso no es un error:
    es el caso en que TODAS las preguntas son nuevas.
    """
    if contexto is None:
        return ()
    return tuple(getattr(contexto, "unresolved_questions", ()) or ())


def clarificacion_nueva_del_turno(computo, resultado) -> dict | None:
    """La pregunta que ESTE turno abrió, o `None`. **Pura: sin I/O, sin reloj, sin modelo.**

    Args:
        computo: el `ComputoCandidato` de este turno. Su `contexto_base` es el estado ANTES.
        resultado: el `ResultadoUpdater` de la persistencia. Su `contexto` es el estado DESPUÉS.

    Returns:
        `{"question": str, "about_field": str}` — dos claves, ninguna más — o `None` si el turno
        no abrió ninguna pregunta nueva, si no hubo persistencia, o si falta cualquiera de las
        dos piezas.

    La identidad es `about_field`. Una pregunta sin `about_field` no se ofrece: sin ella no se
    puede saber si es la misma que ya estaba, y tampoco sería accionable para quien la responda.
    """
    if computo is None or resultado is None:
        return None
    if not getattr(resultado, "persistido", False):
        # Ni siquiera se mira el delta. Preguntar por algo que no se guardó es prometer una
        # memoria que no existe.
        return None

    antes = {q.about_field for q in _preguntas(computo.contexto_base) if q.about_field}
    for q in _preguntas(resultado.contexto):
        if not q.about_field or q.about_field in antes:
            continue
        # Campo a campo, nunca por volcado: si mañana el contrato gana un campo, no se cuela.
        return {"question": q.question, "about_field": q.about_field}
    return None


def _en_cohorte(user_id: str) -> bool:
    """Fail-closed: la única forma de entrar es pertenecer.

    Se reutiliza `sombra._habilitados` —el parser normalizado de `BUYER_SHADOW_ALLOWLIST`— y no
    se reescribe: dos parsers de la misma lista divergen, y el que divergiría sería el que decide
    a quién se le habla.
    """
    return user_id.strip().lower() in _habilitados()


def clarificacion_del_turno(user, computo, resultado) -> dict | None:
    """Las cinco puertas, en orden, y la pregunta si las cinco se abren.

    Éste es el único punto que `chat.py` necesita llamar. Devuelve `None` en cuanto una puerta se
    cierra, sin tocar nada: un turno fuera de cohorte no paga ni la comparación.

    El orden importa: FLAG antes que COHORTE, y COHORTE antes que mirar al comprador. Un anónimo
    no tiene `user_id`, así que sale en la segunda puerta y nunca llega a las que leen estado.
    """
    if not settings.buyer_unresolved_product:
        return None
    user_id = (getattr(user, "user_id", "") or "").strip() if user is not None else ""
    if not user_id or not _en_cohorte(user_id):
        return None
    return clarificacion_nueva_del_turno(computo, resultado)
