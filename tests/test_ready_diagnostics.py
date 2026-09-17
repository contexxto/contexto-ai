"""R2C1a — un 503 de `/ready` tiene que decir QUÉ sonda falló, sin filtrar nada.

DE DÓNDE SALE ESTA UNIDAD. El 2026-09-16 hubo un `/ready` = 503 en producción. Se localizó
el evento —uno solo en cuatro horas, emitido por nuestro propio handler, con la petición
siguiente del mismo cliente en 200— pero **no se pudo averiguar la causa**: el handler
capturaba todo en un `except` opaco y no registraba nada, mientras su docstring prometía que
"el detalle vive en los logs". No vivía.

Eso bloqueó la promoción de `verify-full` a producción, y con razón: si ese 503 reapareciera
durante el despliegue de TLS, se le atribuiría a TLS, y se haría rollback de una mejora de
seguridad por una causa que no tiene nada que ver.

EL PRECEDENTE, que vale más que el parche: un readiness sin atribución de fallo es
suficiente para automatización —un supervisor sólo necesita el booleano— pero insuficiente
para operar un cambio de infraestructura sensible, donde hace falta causalidad mínima.

LAS DOS FAMILIAS DE PRUEBA:

  * CONTRATO — que el 503 y el 200 sigan siendo exactamente lo que eran. Esta unidad no
    puede cambiar lo que ve un cliente; si lo cambiara, sería otra unidad.
  * FUGA — que el diagnóstico nuevo no se convierta en el vehículo de la fuga que R2B1
    cerró. Las sondas fallan con excepciones que llevan DSN y contraseña dentro, y se
    comprueba con centinelas que nada de eso sale.

Sin base de datos: se falsean las tres sondas. Y sin `with` en `TestClient` —igual que en
`test_health_memoria.py`— porque usarlo como gestor de contexto ejecutaría el lifespan, que
montaría el checkpointer REAL contra la Supabase de producción.
"""
import asyncio
import re

import pytest
from fastapi.testclient import TestClient

import main


# Un secreto verosímil dentro del mensaje de las excepciones internas. Si aparece en la
# salida, la fuga es real y no una hipótesis.
_CENTINELA = "P4ssw0rd-n0-debe-salir-9f2c"
_DSN_FALSO = (
    f"postgresql://usuario:{_CENTINELA}@aws-1-us-west-2.pooler.supabase.com:5432/postgres"
)


def _mensaje_venenoso(prefijo: str) -> str:
    """El texto que un driver de Postgres produce de verdad: la conninfo entera dentro."""
    return f"{prefijo}: connection to server failed for {_DSN_FALSO}"


@pytest.fixture
def cliente():
    return TestClient(main.app)


@pytest.fixture
def sondas_sanas(monkeypatch):
    """Las tres sondas en verde. Punto de partida de todos los casos."""
    async def _db_ok():
        return None

    async def _pool_ok():
        return None

    monkeypatch.setattr(main, "_sondear_db", _db_ok)
    monkeypatch.setattr(main, "get_checkpointer", lambda: object())
    monkeypatch.setattr(main, "sondear_pool_checkpointer", _pool_ok)


def _romper(monkeypatch, sonda: str, excepcion: BaseException):
    """Rompe UNA sonda dejando las otras dos sanas."""
    if sonda == "asyncpg":
        async def _falla():
            raise excepcion
        monkeypatch.setattr(main, "_sondear_db", _falla)
    elif sonda == "checkpointer":
        monkeypatch.setattr(main, "get_checkpointer", lambda: None)
    elif sonda == "psycopg_pool":
        async def _falla():
            raise excepcion
        monkeypatch.setattr(main, "sondear_pool_checkpointer", _falla)
    else:                                     # pragma: no cover - error del propio test
        raise AssertionError(f"sonda desconocida: {sonda}")


def _lineas_de_diagnostico(capsys) -> list[str]:
    salida = capsys.readouterr()
    return [l for l in (salida.out + salida.err).splitlines() if "ready_probe_failed" in l]


# ══ A · Contrato: las tres sondas en verde ════════════════════════════════════════════
def test_A_con_las_tres_sondas_sanas_sigue_siendo_200_ready(cliente, sondas_sanas, capsys):
    r = cliente.get("/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}
    assert not _lineas_de_diagnostico(capsys), "el camino feliz no debe registrar nada"


# ══ B/C/D · Atribución por sonda ══════════════════════════════════════════════════════
@pytest.mark.parametrize(
    "sonda,excepcion,clase_esperada",
    [
        ("asyncpg", RuntimeError(_mensaje_venenoso("asyncpg")), "RuntimeError"),
        ("asyncpg", OSError(_mensaje_venenoso("socket")), "OSError"),
        ("checkpointer", None, "RuntimeError"),
        ("psycopg_pool", TimeoutError(_mensaje_venenoso("pool")), "TimeoutError"),
        ("psycopg_pool", RuntimeError(_mensaje_venenoso("pool")), "RuntimeError"),
    ],
)
def test_BCD_un_fallo_de_sonda_queda_atribuido(
    cliente, sondas_sanas, monkeypatch, capsys, sonda, excepcion, clase_esperada
):
    """La respuesta no cambia; lo que cambia es que ahora se sabe QUÉ falló."""
    _romper(monkeypatch, sonda, excepcion)
    r = cliente.get("/ready")

    assert r.status_code == 503
    assert r.json() == {"status": "not_ready"}

    lineas = _lineas_de_diagnostico(capsys)
    assert len(lineas) == 1, f"se esperaba UNA línea de diagnóstico, hay {len(lineas)}"
    assert lineas[0].strip() == f"ready_probe_failed probe={sonda} error_class={clase_esperada}"


def test_BCD_la_primera_sonda_que_falla_es_la_que_se_reporta(
    cliente, sondas_sanas, monkeypatch, capsys
):
    """Con DOS sondas rotas gana la primera del orden, que es el orden que no cambió.

    Importa: si reportara la última, un fallo del engine quedaría etiquetado como fallo del
    pool y el diagnóstico apuntaría al sitio equivocado.
    """
    _romper(monkeypatch, "asyncpg", RuntimeError(_mensaje_venenoso("engine")))
    _romper(monkeypatch, "psycopg_pool", RuntimeError(_mensaje_venenoso("pool")))
    assert cliente.get("/ready").status_code == 503
    (linea,) = _lineas_de_diagnostico(capsys)
    assert "probe=asyncpg" in linea


# ══ E · Timeout global ════════════════════════════════════════════════════════════════
def test_E_el_timeout_global_se_registra_como_tal(cliente, sondas_sanas, monkeypatch, capsys):
    """Una sonda que se cuelga más allá del presupuesto no se atribuye a esa sonda.

    Y no es un matiz: cuando el corte llega por tiempo NO se sabe cuál habría fallado —sólo
    que el conjunto no cupo—, así que decir `probe=asyncpg` sería inventarse una atribución.
    """
    monkeypatch.setattr(main, "TIMEOUT_READY_S", 0.05)

    async def _se_cuelga():
        await asyncio.sleep(5)

    monkeypatch.setattr(main, "_sondear_db", _se_cuelga)

    r = cliente.get("/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "not_ready"}
    (linea,) = _lineas_de_diagnostico(capsys)
    assert "probe=global_timeout" in linea
    assert "error_class=TimeoutError" in linea


def test_E_el_timeout_sigue_siendo_de_3_segundos():
    """El mandato prohíbe tocarlo, y un cambio accidental aquí no se vería de otro modo."""
    assert main.TIMEOUT_READY_S == 3.0


# ══ SANEAMIENTO · el diagnóstico no puede ser el vehículo de la fuga ══════════════════
@pytest.mark.parametrize("sonda", ["asyncpg", "psycopg_pool"])
def test_el_diagnostico_no_filtra_NADA_de_la_excepcion_interna(
    cliente, sondas_sanas, monkeypatch, capsys, sonda
):
    """El mismo contrato de R2B1, aplicado al canal nuevo.

    La excepción interna lleva dentro un DSN completo con contraseña — que es exactamente lo
    que produce un driver de Postgres de verdad. Se comprueba sobre TODA la salida, no sólo
    sobre la línea de diagnóstico: si el texto escapara por otra vía, seguiría siendo fuga.
    """
    _romper(monkeypatch, sonda, RuntimeError(_mensaje_venenoso("driver")))
    respuesta = cliente.get("/ready")

    salida = capsys.readouterr()
    todo = salida.out + salida.err + respuesta.text
    for prohibido, etiqueta in (
        (_CENTINELA, "la contraseña"),
        (_DSN_FALSO, "el DSN completo"),
        ("pooler.supabase.com", "el host"),
        ("usuario", "el usuario"),
        ("connection to server failed", "el mensaje del driver"),
        ("Traceback", "el traceback"),
    ):
        assert prohibido not in todo, f"FUGA: salió {etiqueta}"


def test_la_linea_de_diagnostico_tiene_exactamente_dos_campos(
    cliente, sondas_sanas, monkeypatch, capsys
):
    """Formato cerrado. Un campo de más mañana es por donde entraría el mensaje del driver."""
    _romper(monkeypatch, "asyncpg", RuntimeError(_mensaje_venenoso("driver")))
    cliente.get("/ready")
    (linea,) = _lineas_de_diagnostico(capsys)
    assert re.fullmatch(r"ready_probe_failed probe=\w+ error_class=\w+", linea.strip()), linea


def test_la_excepcion_de_atribucion_no_encadena_la_original():
    """`from None`: `__cause__` a None y `__suppress_context__` a True.

    Enunciado con la precisión que costó una errata en R2B1: `from None` NO borra la
    original — `__context__` puede seguir apuntando a ella. Lo que se garantiza es la NO
    EXPOSICIÓN en las superficies verificadas, no su ausencia en memoria.
    """
    try:
        try:
            raise RuntimeError(_mensaje_venenoso("driver"))
        except Exception as exc:
            raise main._FalloDeSonda("asyncpg", type(exc).__name__) from None
    except main._FalloDeSonda as fallo:
        assert fallo.__cause__ is None
        assert fallo.__suppress_context__ is True
        assert str(fallo) == "asyncpg"
        assert _CENTINELA not in f"{fallo}{fallo.args}"


# ══ F/G · lo que NO puede haber cambiado ══════════════════════════════════════════════
def test_F_live_no_cambia(cliente):
    r = cliente.get("/live")
    assert r.status_code == 200
    assert r.json() == {"status": "alive"}


def test_F_live_no_toca_las_sondas(cliente, monkeypatch):
    """`/live` no puede haberse contagiado de la instrumentación: si consultara algo, sería
    otro `/ready` con el nombre cambiado, y con el bucle de reinicios de regalo."""
    def _explota():
        raise AssertionError("/live tocó una sonda")

    monkeypatch.setattr(main, "_sondear_db", _explota)
    monkeypatch.setattr(main, "get_checkpointer", _explota)
    monkeypatch.setattr(main, "sondear_pool_checkpointer", _explota)
    assert cliente.get("/live").status_code == 200


def test_G_health_no_cambia_de_forma_observable(cliente, sondas_sanas):
    """Hay consumidores de `/health`; romperlos no es parte de esto."""
    r = cliente.get("/health")
    assert r.status_code == 200
    assert set(r.json()) >= {"status", "database", "memoria"}


# ══ Que la política TLS no se rozó ════════════════════════════════════════════════════
def test_esta_unidad_no_toca_la_politica_TLS():
    """Control explícito: `main.py` sigue sin contener política TLS, que vive en `db_tls`."""
    import pathlib

    texto = (pathlib.Path(main.__file__)).read_text(encoding="utf-8")
    for token in ("sslmode", "sslrootcert", "SSLContext", "verify-full", "check_hostname"):
        assert token not in texto, f"main.py ganó {token!r}: la política TLS se copió aquí"
