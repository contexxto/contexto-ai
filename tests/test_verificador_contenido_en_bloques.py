"""G18 · TR1-B · el verificador de prosa vuelve a recibir texto.

EL FALLO, observado en el turno REAL del canary (2026-08-29, SHA 94ee869):

```
verificacion_prosa fallo (TypeError: expected string or bytes-like object, got 'list')
```

`_ultima_respuesta` está anotada `-> str` y devuelve `m.content` en crudo. Con herramientas
atadas, Anthropic NO manda `content` como str: manda una lista de bloques tipados. Ese objeto
llegaba al verificador y reventaba en el primer regex:

```
_ultima_respuesta → list
  → auditar_explicacion → verificar_prosa
    → _cifra_sin_procedencia → _montos_en → _MONTO.finditer(lista)  ← TypeError
```

LO QUE ESO COSTABA. Las siete verificaciones viven en UNA sola expresión sumada, así que el
fallo en la tercera abortaba todas — incluida `_caminabilidad_procedencia` (TRUST-HOTFIX-01)
y `_gancho`, que cubre tono y Fair Housing. El `except` de `_auditar_prosa` lo degradaba a un
`warning` y el turno se servía igual: **el guardián quedaba fail-open sin que nada lo dijera**.

La ironía es que la normalización correcta YA existía quince líneas más abajo, en
`_texto_del_chunk`, escrita para el mismo formato y el mismo motivo. Este arreglo la reutiliza
en vez de escribir una segunda interpretación del formato de Anthropic.

## Lo que esta unidad NO hace

Devuelve la VISTA, no la prevención. El verificador sigue siendo audit-only: tras esto, un
turno que fabrique procedencia quedará registrado como `failed` y **la afirmación falsa
seguirá llegando al usuario**. Impedirlo es otra unidad (TR1-A). Aquí no se toca ninguna regla,
ni severidades, ni el prompt, ni el encaje.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from app.decision.verify import auditar_explicacion
from app.routers.chat import _ultima_respuesta
from app.verificacion_prosa import ALTA, verificar_prosa

PROSA_FALSA = ("La zona es de las más caminables de Quito (caminabilidad 100, calculada "
               "sobre los comercios reales del sector) — tienes todo a pie.")
PROSA_HONESTA = ("La zona es caminable (caminabilidad 100, estimada por zona) — "
                 "tienes comercios cerca.")


def _bloques(texto):
    """La forma REAL que manda Anthropic con herramientas atadas."""
    return [{"type": "text", "text": texto, "index": 0}]


def _cards(fuente=None):
    """El activo REAL del canary. `walk_score_fuente` es NULL en los 40 de producción."""
    return [{"id": "activo-1", "titulo": "Calle Alemania E12-34 y González Suárez, Quito",
             "precio": 630, "caminabilidad": 100, "caminabilidad_fuente": fuente}]


# ══ 1 · el tipo que prometía la anotación ═══════════════════════════════════════════


@pytest.mark.parametrize("contenido", [
    "texto plano",
    _bloques("texto en bloques"),
    [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}],
])
def test_la_ultima_respuesta_SIEMPRE_es_texto(contenido):
    """La anotación decía `-> str` y no se cumplía. Es la raíz de todo lo demás."""
    reply = _ultima_respuesta([HumanMessage(content="hola"), AIMessage(content=contenido)])

    assert isinstance(reply, str), f"devolvió {type(reply).__name__}"


def test_el_turno_con_bloques_NO_revienta_el_verificador():
    """EL FALLO DE PRODUCCIÓN. Antes de G18 esto levantaba `TypeError` y con él se perdía
    la auditoría entera del turno."""
    reply = _ultima_respuesta([AIMessage(content=_bloques(PROSA_FALSA))])

    auditar_explicacion(reply, _cards(), None, None)   # no levanta


# ══ 2 · el guard de equivalencia ════════════════════════════════════════════════════


@pytest.mark.parametrize("prosa", [PROSA_FALSA, PROSA_HONESTA])
def test_str_y_BLOQUES_producen_el_MISMO_veredicto(prosa):
    """El test más valioso de la unidad: la forma del transporte no puede cambiar el
    juicio. Si un turno con herramientas se auditara distinto que el mismo texto plano,
    tendríamos dos verdades sobre la misma respuesta — que es justo la familia de defecto
    que TRUST-REGRESSION-1 vino a cerrar."""
    plano = _ultima_respuesta([AIMessage(content=prosa)])
    bloques = _ultima_respuesta([AIMessage(content=_bloques(prosa))])

    assert plano == bloques
    assert (verificar_prosa(plano, _cards()) == verificar_prosa(bloques, _cards()))


# ══ 3 · el guard que el turno real necesitaba, encendido otra vez ═══════════════════


def test_con_bloques_se_DETECTA_la_procedencia_fabricada():
    """El caso exacto de producción: `walk_score_fuente` es NULL y la prosa afirma que la
    caminabilidad se midió sobre comercios reales.

    No basta con dejar de reventar: hay que demostrar que el guard concreto vuelve a morder.
    """
    reply = _ultima_respuesta([AIMessage(content=_bloques(PROSA_FALSA))])

    violaciones = verificar_prosa(reply, _cards(fuente=None))
    codigos = [v["codigo"] for v in violaciones]

    assert "caminabilidad_procedencia_falsa" in codigos, codigos
    falsa = next(v for v in violaciones if v["codigo"] == "caminabilidad_procedencia_falsa")
    assert falsa["gravedad"] == ALTA


def test_una_prosa_HONESTA_no_se_marca():
    """Control del anterior: sin esto, un detector que marcara todo también pasaría."""
    reply = _ultima_respuesta([AIMessage(content=_bloques(PROSA_HONESTA))])

    codigos = [v["codigo"] for v in verificar_prosa(reply, _cards(fuente=None))]

    assert "caminabilidad_procedencia_falsa" not in codigos, codigos


def test_con_procedencia_REAL_tampoco_se_marca():
    """Si la caminabilidad sí salió de comercios reales, afirmarlo es correcto."""
    reply = _ultima_respuesta([AIMessage(content=_bloques(PROSA_FALSA))])

    codigos = [v["codigo"] for v in verificar_prosa(reply, _cards(fuente="osm"))]

    assert "caminabilidad_procedencia_falsa" not in codigos, codigos


# ══ 4 · lo que NO debe inventarse ═══════════════════════════════════════════════════


def test_los_bloques_NO_textuales_no_aportan_texto():
    """Un `input_json_delta` no es prosa. Y **trae su propia clave `text`**, que es justo lo
    que hace peligrosa esta discriminación: filtrar por `type` no es cosmético.

    El estímulo lleva a propósito bloques no textuales CON `text`. Con bloques que no la
    tuvieran, quitar el filtro no cambiaría nada y este test daría verde por la razón
    equivocada — lo demostró una mutación que se escapó en la primera pasada.

    Si el filtro cae, el JSON parcial de la llamada a herramienta acaba en lo que el
    verificador cree que dijo el modelo y, por el otro consumidor, en la burbuja del usuario.
    """
    contenido = [{"type": "input_json_delta", "text": '{"zona": "La Flor'},
                 {"type": "text", "text": "Encontré una opción."},
                 {"type": "input_json_delta", "text": 'esta"}'}]

    reply = _ultima_respuesta([AIMessage(content=contenido)])

    assert reply == "Encontré una opción."
    assert "zona" not in reply and "{" not in reply, f"se filtró JSON de herramienta: {reply!r}"


def test_sin_texto_utilizable_hay_un_valor_EXPLICITO():
    """Ni `None`, ni lista, ni cadena vacía silenciosa: el mismo centinela que ya usaba la
    función cuando no encontraba respuesta. `verificar_prosa` lo audita sin hallazgos y el
    carril de respuesta tiene algo que mostrar."""
    contenido = [{"type": "tool_use", "name": "buscar", "input": {}}]

    reply = _ultima_respuesta([AIMessage(content=contenido)])

    assert reply == "Sin respuesta del agente."
    assert verificar_prosa(reply, _cards()) == []


def test_sin_ningun_AIMessage_se_conserva_el_centinela():
    assert _ultima_respuesta([HumanMessage(content="hola")]) == "Sin respuesta del agente."


# ══ 5 · las siete verificaciones vuelven a ser alcanzables ══════════════════════════


def test_el_chequeo_que_REVENTABA_vuelve_a_producir_hallazgos():
    """`_cifra_sin_procedencia` es donde moría el turno: `_montos_en` → `_MONTO.finditer`.

    Que no levante ya no basta como prueba —un chequeo saltado tampoco levanta—. Hay que
    verlo emitir SU hallazgo con contenido en bloques.
    """
    prosa = "Hay opciones desde $450 al mes en la zona."

    reply = _ultima_respuesta([AIMessage(content=_bloques(prosa))])
    codigos = {v["codigo"] for v in verificar_prosa(reply, _cards())}

    assert "cifra_sin_procedencia" in codigos, codigos


def test_el_fallo_del_TERCER_chequeo_ya_no_apaga_al_SEXTO():
    """La propiedad estructural de TR1-B, afirmada de frente.

    Los siete chequeos se suman en una sola expresión y `_cifra_sin_procedencia` (3º) corre
    ANTES de `_caminabilidad_procedencia` (6º). Con una prosa que viola los dos a la vez,
    ver ambos códigos demuestra que la cadena ya no se corta a mitad — no sólo que el primero
    sobrevivió.
    """
    prosa = ("Hay opciones desde $450 al mes en la zona (caminabilidad 100, calculada "
             "sobre los comercios reales del sector).")

    reply = _ultima_respuesta([AIMessage(content=_bloques(prosa))])
    codigos = {v["codigo"] for v in verificar_prosa(reply, _cards(fuente=None))}

    assert {"cifra_sin_procedencia", "caminabilidad_procedencia_falsa"} <= codigos, codigos
