"""F3-ADOPTION-R2 · las sondas del comprador no pueden filtrar el texto del driver.

QUÉ CONGELA, y qué NO.

    congela    que los CUATRO manejadores que aíslan las sondas del comprador en
               `app/routers/chat.py` registren **clase y sonda, y nada más**: ni el mensaje de
               la excepción, ni su `repr`, ni la traza. Y que ese contrato se mida EJECUTANDO
               el manejador real extraído del fichero, no leyendo su texto.
    NO congela  el `logger.exception` de `app/buyer/sombra.py`, que ya existía en `main` antes
               de esta cadena y se deja donde está a propósito.

## POR QUÉ EXISTE

En `#137` se midió que el texto de un driver de Postgres **arrastra la conninfo entera** —host,
usuario y contraseña—, y por eso el arranque del checkpointer sólo puede propagar `from None`.
Las sondas del comprador abren la base por el engine compartido: si una falla con TLS o con la
red, su excepción trae ese mismo texto. Registrarla con la traza adjunta reabriría, en cuatro
caminos nuevos, la fuga que aquel programa cerró en uno.

## CÓMO SE MIDE, Y POR QUÉ ASÍ

No se comprueba el texto del fichero: se **ejecuta** el cuerpo del manejador real, extraído por
AST, dentro de un `except` de verdad y con una excepción hostil que lleva un DSN completo en su
mensaje. Un guard textual diría «no aparece la palabra prohibida»; esto dice «el secreto no sale
por el log», que es la propiedad que importa.

Y trae su mitad negativa (`test_el_control_negativo_MUERDE`): el mismo comprobador, aplicado a un
manejador sintético que sí adjunta la traza, tiene que ponerse rojo. Un comprobador que no muerde
cuando se rompe lo que dice defender no prueba nada.
"""

from __future__ import annotations

import ast
import logging
import pathlib
import textwrap

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CHAT = RAIZ / "app" / "routers" / "chat.py"

# El secreto que la excepción hostil arrastra. Inventado, con la forma de una conninfo real.
USUARIO = "postgres.jzxeigzxgbglfsiiqpxv"
CLAVE = "S3cretoQueJamasDebeSalir"
ANFITRION = "aws-1-us-west-2.pooler.supabase.com"
DSN = f"postgresql://{USUARIO}:{CLAVE}@{ANFITRION}:5432/postgres"
MENSAJE_HOSTIL = f"connection failed: {DSN} sslmode=verify-full"

# Lo que un registro saneado SÍ debe contener.
SONDAS = ("candidate_commit", "decision_shadow")


class FalloDeDriverFalso(Exception):
    """Imita a un error de asyncpg: el secreto viaja en el propio mensaje."""


def _manejadores_de_sonda() -> list[str]:
    """El CUERPO, en texto, de cada `except` de chat.py que aísla una sonda del comprador.

    Se reconocen por el literal con el que empieza su registro, no por el número de línea: si
    alguien mueve el bloque, esta prueba lo sigue encontrando.
    """
    fuente = CHAT.read_text(encoding="utf-8")
    arbol = ast.parse(fuente)
    cuerpos: list[str] = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.ExceptHandler):
            continue
        texto = ast.get_source_segment(fuente, nodo) or ""
        if "buyer candidate commit" in texto or "buyer decision shadow" in texto:
            trozos = [ast.get_source_segment(fuente, s) for s in nodo.body]
            cuerpos.append("\n".join(t for t in trozos if t))
    return cuerpos


def _ejecutar(cuerpo: str, registro: logging.Logger) -> None:
    """Ejecuta el cuerpo DENTRO de un `except` real, con la excepción hostil en vuelo.

    Importa que sea un `except` de verdad: fuera de uno, un registro con traza no tendría nada
    que adjuntar y el control negativo no podría morder.
    """
    codigo = (
        "try:\n"
        "    raise _hostil\n"
        "except Exception as exc:  # noqa: BLE001\n"
        + textwrap.indent(textwrap.dedent(cuerpo), "    ")
    )
    exec(compile(codigo, "<manejador-extraido-de-chat.py>", "exec"),  # noqa: S102
         {"_hostil": FalloDeDriverFalso(MENSAJE_HOSTIL), "log": registro})


def _revisar(caplog: pytest.LogCaptureFixture) -> None:
    """El comprobador. Se aplica igual al manejador real y al sintético del control negativo."""
    assert caplog.records, "el fallo se tragó sin dejar rastro: aislado NO es invisible"

    completo = "\n".join(
        r.getMessage() + ("\n" + logging.Formatter().formatException(r.exc_info)
                          if r.exc_info else "")
        for r in caplog.records
    )

    # 1 · LO QUE NO PUEDE ESTAR, primero y pieza por pieza.
    #
    # El orden es deliberado: si alguien revierte el saneado, quiero que el fallo diga «la
    # contraseña viajó al log» y no un defecto lateral. Una prueba que muerde por la razón
    # equivocada enseña a arreglar lo que no era.
    for prohibido, nombre in ((CLAVE, "la contraseña"), (USUARIO, "el usuario"),
                              (ANFITRION, "el anfitrión"), (DSN, "el DSN completo"),
                              (MENSAJE_HOSTIL, "el mensaje de la excepción")):
        assert prohibido not in completo, f"{nombre} viajó al log"

    # 2 · la traza, que es el vehículo por el que llegan todos los anteriores.
    assert not any(r.exc_info for r in caplog.records), "se adjuntó la traza de la excepción"
    assert "Traceback" not in completo

    # 3 · y sólo entonces, lo que SÍ tiene que estar para que el rastro sirva de algo.
    assert FalloDeDriverFalso.__name__ in completo, "sin la clase no hay diagnóstico posible"
    assert any(s in completo for s in SONDAS), "sin identificar la sonda no se sabe cuál falló"


def test_hay_exactamente_cuatro_manejadores_de_sonda():
    """Si aparece un quinto camino, entra solo en esta prueba y hay que decidir sobre él."""
    assert len(_manejadores_de_sonda()) == 4


@pytest.mark.parametrize("indice", range(4))
def test_el_manejador_real_no_filtra_nada_del_driver(indice, caplog):
    """LA GARANTÍA. Se ejecuta el manejador tal como está en el fichero."""
    cuerpo = _manejadores_de_sonda()[indice]
    registro = logging.getLogger("intencion")
    with caplog.at_level(logging.ERROR, logger="intencion"):
        _ejecutar(cuerpo, registro)          # no levanta: la sonda sigue aislada
    _revisar(caplog)


def test_el_control_negativo_MUERDE(caplog):
    """La mitad que hace que esto valga algo.

    Un manejador que adjunta la traza tiene que poner ROJO al mismo comprobador. Si este test
    pasara sin `pytest.raises`, significaría que `_revisar` no distingue, y entonces el verde de
    los cuatro de arriba no querría decir nada.
    """
    sintetico = 'log.exception("buyer candidate commit falló y quedó aislado")'
    registro = logging.getLogger("intencion")
    with caplog.at_level(logging.ERROR, logger="intencion"):
        _ejecutar(sintetico, registro)
    with pytest.raises(AssertionError):
        _revisar(caplog)


def test_el_control_negativo_tambien_muerde_si_se_registra_el_mensaje(caplog):
    """Segunda mitad negativa: sin traza, pero pasando el mensaje. También debe caer."""
    sintetico = 'log.error("buyer decision shadow falló · %s", str(exc))'
    registro = logging.getLogger("intencion")
    with caplog.at_level(logging.ERROR, logger="intencion"):
        _ejecutar(sintetico, registro)
    with pytest.raises(AssertionError):
        _revisar(caplog)


def test_sombra_py_queda_fuera_de_esta_unidad():
    """Declarativo, para que nadie lo tome por un olvido.

    `app/buyer/sombra.py` registra con traza y eso ya estaba en `main` antes de esta cadena.
    Corregirlo es otra unidad; dejarlo sin decir nada sería esconderlo.
    """
    sombra = (RAIZ / "app" / "buyer" / "sombra.py").read_text(encoding="utf-8")
    assert "logger.exception(" in sombra, (
        "si sombra.py ya se saneó, esta prueba sobra y hay que retirarla junto con la nota "
        "del informe de F3-ADOPTION-R2"
    )
