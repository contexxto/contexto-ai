"""R2B1 — readiness separado de liveness, y el checkpointer deja de degradar en silencio.

EL FALLO QUE LO ORIGINA es el mismo del 2026-08-18, pero visto desde el otro lado. Aquel día
el checkpointer no abrió su pool, el grafo quedó con `MemorySaver` y la app respondió **200 en
todo** durante 1h26m sin historial. `/health` ya delata eso en el CUERPO — pero **Render sólo
evalúa el código HTTP, nunca el cuerpo**, así que no había supervisor capaz de reaccionar.

Lo que esta unidad fija:

  * `/live`   — ¿vive el proceso? Jamás toca base, engine ni checkpointer. Es lo que mira Render.
  * `/ready`  — ¿puede servir? Base **y** memoria durable **y** pool de psycopg. 503 si no.
  * `/health` — SIN CAMBIOS OBSERVABLES. Hay consumidores; romperlos no es parte de esto.
  * `setup_checkpointer()` en PRODUCCIÓN aborta el arranque en vez de degradar, limpiando lo
    que quedó a medias. Fuera de producción conserva `MemorySaver`.

Sin base de datos: se falsean la sesión, el checkpointer y el pool. Sin `with` en `TestClient`
—igual que en `test_health_memoria.py`— porque usarlo como gestor de contexto ejecutaría el
lifespan, que monta el checkpointer REAL contra la Supabase de producción.
"""
import asyncio
import io
import pathlib
import time
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

import main

# Ancla de confianza para las URL remotas de este módulo (ver tests/ayuda_tls.py).
from tests.ayuda_tls import ancla_de_confianza  # noqa: F401


# ══ Andamiaje ═════════════════════════════════════════════════════════════════════════
class _Explota(Exception):
    """Se levanta si algo que NO debía ejecutarse se ejecuta."""


@pytest.fixture
def db_arriba(monkeypatch):
    class _Sesion:
        async def execute(self, *_a, **_k):
            return None

    @asynccontextmanager
    async def _fake():
        yield _Sesion()

    monkeypatch.setattr(main, "AsyncSessionLocal", lambda: _fake())


def _cliente():
    return TestClient(main.app)


def _todo_sano(monkeypatch):
    """Los tres caminos de `/ready` en verde."""
    monkeypatch.setattr(main, "get_checkpointer", lambda: object())

    async def _pool_ok():
        return None

    monkeypatch.setattr(main, "sondear_pool_checkpointer", _pool_ok)


# ══ /live no toca nada ════════════════════════════════════════════════════════════════
def test_live_responde_sin_invocar_ninguna_dependencia(monkeypatch):
    """LA prueba de este endpoint. Si algún día `/live` consulta algo, deja de ser un
    liveness: pasa a fallar cuando falla la base, y entonces Render —que sí lo mira—
    reinicia en bucle justo cuando escasean las conexiones. Es el fallo que `/health`
    evita devolviendo 200, entrando por la otra puerta."""
    def _prohibido(*_a, **_k):
        raise _Explota("/live tocó una dependencia")

    async def _prohibido_async(*_a, **_k):
        raise _Explota("/live tocó una dependencia")

    monkeypatch.setattr(main, "_sondear_db", _prohibido_async)
    monkeypatch.setattr(main, "sondear_pool_checkpointer", _prohibido_async)
    monkeypatch.setattr(main, "get_checkpointer", _prohibido)
    monkeypatch.setattr(main, "AsyncSessionLocal", _prohibido)

    r = _cliente().get("/live")
    assert r.status_code == 200
    assert r.json()["status"] == "alive"


# ══ /ready exige las TRES condiciones ═════════════════════════════════════════════════
def test_ready_200_con_los_dos_caminos_sanos(db_arriba, monkeypatch):
    _todo_sano(monkeypatch)
    r = _cliente().get("/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_ready_503_con_el_engine_caido(monkeypatch):
    """Camino 1: SQLAlchemy/asyncpg."""
    async def _explota():
        raise OSError("connection refused")

    monkeypatch.setattr(main, "_sondear_db", _explota)
    _todo_sano(monkeypatch)
    assert _cliente().get("/ready").status_code == 503


def test_ready_503_sin_checkpointer_durable(db_arriba, monkeypatch):
    """Camino 2, y es el corazón: en producción `MemorySaver` NO puede dar 200.

    Esto es exactamente lo que el 2026-08-18 nadie pudo ver desde fuera."""
    _todo_sano(monkeypatch)
    monkeypatch.setattr(main, "get_checkpointer", lambda: None)
    assert _cliente().get("/ready").status_code == 503


def test_ready_503_con_el_pool_psycopg_caido(db_arriba, monkeypatch):
    """Camino 3, y NO es redundante con el 1 ni con el 2.

    Con el 1: son dos stacks distintos (asyncpg en Python puro vs. psycopg/libpq en C)
    contra la misma base. Un fallo asimétrico es justo el que deja la app respondiendo 200
    sin historial.
    Con el 2: que el objeto checkpointer exista sólo dice que el montaje terminó alguna vez;
    que el pool atienda HOY es otra pregunta — y con `min_size=1` una sola conexión buena al
    arrancar dio el pool por bueno."""
    _todo_sano(monkeypatch)

    async def _pool_caido():
        raise RuntimeError("el pool no atiende")

    monkeypatch.setattr(main, "sondear_pool_checkpointer", _pool_caido)
    assert _cliente().get("/ready").status_code == 503


def test_ready_no_filtra_detalles_internos_en_el_503(db_arriba, monkeypatch):
    """El endpoint no está autenticado: el porqué del fallo va a los logs, no al cuerpo."""
    _todo_sano(monkeypatch)

    async def _pool_caido():
        raise RuntimeError("host=interno-secreto.example usuario=admin")

    monkeypatch.setattr(main, "sondear_pool_checkpointer", _pool_caido)
    r = _cliente().get("/ready")
    assert r.status_code == 503
    assert r.json() == {"status": "not_ready"}
    assert "secreto" not in r.text and "admin" not in r.text


def test_ready_acota_el_tiempo_TOTAL_no_por_sonda(monkeypatch):
    """Una base que CUELGA (no que falla) dejaría la petición esperando el timeout del pool.

    El corte es GLOBAL a propósito: tres cortes encadenados de 3 s serían 9 s de espera para
    un chequeo. 5 s en el falso —no 3600— para que quitar el corte haga FALLAR esta prueba,
    no colgarla: un test colgado en CI se ve como un timeout opaco."""
    async def _nunca_responde():
        await asyncio.sleep(5)

    monkeypatch.setattr(main, "_sondear_db", _nunca_responde)
    monkeypatch.setattr(main, "TIMEOUT_READY_S", 0.05)
    _todo_sano(monkeypatch)

    t0 = time.monotonic()
    r = _cliente().get("/ready")
    tardanza = time.monotonic() - t0

    assert r.status_code == 503
    assert tardanza < 2.0, f"el sondeo no se corto: tardo {tardanza:.1f}s"


def test_el_timeout_de_ready_es_muy_menor_que_el_del_pool():
    assert 0 < main.TIMEOUT_READY_S <= 5.0


# ══ setup_checkpointer: fail-closed en producción ═════════════════════════════════════
_CENTINELA = "postgresql://usuario:CLAVE_CENTINELA_NO_DEBE_APARECER@host-interno/base"


def _montar_con_pool_roto(monkeypatch):
    """Falsea el pool para que `open()` falle con una excepción que ARRASTRA la conninfo.

    Ese texto es el centinela: el código anterior hacía `print(f"Causa: {exc}")` y lo habría
    volcado entero a los logs de Render, que son un destino distinto del proceso."""
    import app.agent.graph as graph

    cerrados = []

    class _PoolFalso:
        def __init__(self, **_kw):
            pass

        async def open(self, **_kw):
            raise RuntimeError(_CENTINELA)

        async def close(self):
            cerrados.append(True)

    monkeypatch.setattr(graph, "AsyncConnectionPool", _PoolFalso)
    monkeypatch.setattr(
        graph, "_checkpointer_conn_str",
        lambda: "postgresql://u:p@aws-1-us-west-2.pooler.supabase.com:5432/postgres")
    return graph, cerrados


def test_en_produccion_un_fallo_de_setup_aborta_el_arranque(monkeypatch):
    """Fail-closed. El despliegue no progresa y la versión anterior sigue sirviendo — la
    misma doctrina que `exigir_esquema()` ya aplica en el lifespan."""
    monkeypatch.setenv("RENDER", "true")
    from app.config import settings
    assert settings.es_produccion, "precondicion: el test debe correr como produccion"

    graph, _ = _montar_con_pool_roto(monkeypatch)
    with pytest.raises(graph.CheckpointerStartupError):
        asyncio.run(graph.setup_checkpointer())


def test_la_excepcion_que_escapa_suprime_el_contexto_original(monkeypatch):
    """EL CONTRATO, afirmado sobre el objeto — y enunciado con precisión.

    Lo que se garantiza: mensaje CONSTANTE, `__cause__ is None` y
    `__suppress_context__ is True`, de modo que la excepción original NO APARECE en las
    superficies estándar de traceback y logging (las cuatro que verifica
    `test_el_centinela_no_escapa_por_NINGUNA_superficie_del_lifespan`).

    Lo que NO se garantiza, y conviene que esté escrito para que nadie lo descubra después
    como si fuera un bug: `from None` **no borra** la original. `__context__` sigue
    apuntando a ella —Python lo fija solo al lanzar dentro de un `except`— y lo único que
    hace `from None` es marcar que los formateadores no deben presentarla. Es un contrato
    de NO EXPOSICIÓN en las superficies verificadas, no de ausencia en memoria.

    Conseguir `__context__ is None` exigiría lanzar fuera del `except`: control de flujo
    extra por un invariante que la fuga medida no necesita. Descartado a propósito.
    """
    monkeypatch.setenv("RENDER", "true")
    graph, _ = _montar_con_pool_roto(monkeypatch)

    with pytest.raises(graph.CheckpointerStartupError) as capturada:
        asyncio.run(graph.setup_checkpointer())

    exc = capturada.value
    assert str(exc) == "checkpointer startup failed", "el mensaje debe ser CONSTANTE"
    assert _CENTINELA not in str(exc)
    assert exc.__cause__ is None, "`from exc` reintroduce la fuga — esta medido"
    assert exc.__suppress_context__ is True, "falta `from None`"


def test_el_camino_de_produccion_prohibe_raise_desnudo_y_from_exc():
    """Guarda de AST. `raise ... from exc` es una "mejora" aparentemente razonable
    —conservar el contexto para diagnosticar— que **reintroduce exactamente la
    vulnerabilidad reproducida el 2026-09-16**. Medido en las tres variantes: desnudo y
    `from exc` filtran en el mensaje ASGI y en `exc_info`; sólo `from None` queda limpio.

    Se comprueba el ÁRBOL, no el texto: un comentario que diga "no uses from exc" no
    impide nada."""
    import ast
    import app.agent.graph as graph

    arbol = ast.parse(pathlib.Path(graph.__file__).read_text(encoding="utf-8"))
    funcion = next(n for n in ast.walk(arbol)
                   if isinstance(n, ast.AsyncFunctionDef) and n.name == "setup_checkpointer")

    manejadores = [n for n in ast.walk(funcion) if isinstance(n, ast.ExceptHandler)]
    principal = manejadores[0]  # el `except Exception as exc` que envuelve todo el montaje

    raises = [n for n in ast.walk(principal) if isinstance(n, ast.Raise)]
    assert raises, "el camino de produccion debe relanzar algo"
    for r in raises:
        assert r.exc is not None, "`raise` desnudo propaga la original: filtra"
        assert r.cause is not None, "falta `from ...`: el contexto implicito filtra igual"
        assert isinstance(r.cause, ast.Constant) and r.cause.value is None, \
            "sólo se admite `from None`; `from exc` fue MEDIDO como fuga"


def test_fuera_de_produccion_el_mismo_fallo_conserva_MemorySaver(monkeypatch):
    """Levantar el backend local no debe exigir una base. Misma doctrina que
    `es_produccion` en app/config.py: la configuración ausente no abre una puerta, pero
    tampoco estorba en local."""
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    from app.config import settings
    assert not settings.es_produccion, "precondicion: el test NO debe correr como produccion"

    graph, _ = _montar_con_pool_roto(monkeypatch)
    asyncio.run(graph.setup_checkpointer())  # no lanza
    assert graph.get_checkpointer() is None


@pytest.mark.parametrize("produccion", [True, False])
def test_el_pool_parcial_se_cierra_y_los_globales_quedan_limpios(monkeypatch, produccion):
    """`open()` pudo dejar conexiones abiertas antes de vencer. Un pool huérfano consume del
    techo de 15 del Session Pooler, que es justo el recurso escaso cuando esto falla."""
    if produccion:
        monkeypatch.setenv("RENDER", "true")
    else:
        monkeypatch.delenv("RENDER", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)

    graph, cerrados = _montar_con_pool_roto(monkeypatch)
    try:
        asyncio.run(graph.setup_checkpointer())
    except Exception:  # noqa: BLE001 — en produccion aborta; aqui sólo nos interesa el estado
        pass

    assert cerrados == [True], "el pool parcial no se cerro"
    assert graph._pool is None, "_pool quedo colgando"
    assert graph.get_checkpointer() is None, "_checkpointer quedo colgando"


@pytest.mark.parametrize("produccion", [True, False])
def test_ningun_secreto_centinela_llega_a_los_logs(monkeypatch, capsys, produccion):
    """LA regresión que esta unidad cierra: el texto de la excepción puede arrastrar la
    conninfo entera —host, usuario, contraseña— y los logs de Render son otro destino.
    Se conserva la CLASE, que diagnostica igual y no lleva credenciales encima."""
    if produccion:
        monkeypatch.setenv("RENDER", "true")
    else:
        monkeypatch.delenv("RENDER", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)

    graph, _ = _montar_con_pool_roto(monkeypatch)
    try:
        asyncio.run(graph.setup_checkpointer())
    except Exception:  # noqa: BLE001
        pass

    salida = capsys.readouterr().out
    assert "CLAVE_CENTINELA_NO_DEBE_APARECER" not in salida
    assert _CENTINELA not in salida
    assert "RuntimeError" in salida, "la clase del fallo si debe quedar, para diagnosticar"


# ══ La fuga del lifespan — LA prueba que cierra el gate ═══════════════════════════════
def test_el_centinela_no_escapa_por_NINGUNA_superficie_del_lifespan(monkeypatch, capsys):
    """Recorre el LIFESPAN REAL, no la función suelta, y vigila las cuatro salidas.

    POR QUÉ NO BASTA PROBAR LA FUNCIÓN. La versión anterior de esta suite afirmaba sobre
    `capsys.readouterr().out` y daba verde — mientras el centinela escapaba por dos rutas
    que la función no controla y que el nivel siguiente NO silencia:

      · Starlette formatea `traceback.format_exc()` y lo envía como el `message` de
        `lifespan.startup.failed`  (starlette/routing.py:702,706)
      · uvicorn lo registra con `exc_info=exc`                (uvicorn/lifespan/on.py:96-97)

    Reproducido el 2026-09-16 con el `raise` desnudo: 4571 bytes en el mensaje ASGI y 6049
    en el logger, ambos con la conninfo dentro. Por eso esta prueba conduce el protocolo
    ASGI igual que uvicorn y afirma sobre las cuatro superficies a la vez.

    Y lleva una ASERCIÓN POSITIVA a propósito: la clase saneada SÍ debe aparecer. Sin ella,
    se podría "arreglar" la fuga volviendo el fallo invisible, que es peor que la fuga.
    """
    import logging

    monkeypatch.setenv("RENDER", "true")
    from app.config import settings
    assert settings.es_produccion, "precondicion: el arnes debe correr como produccion"

    # El lifespan abre la base ANTES del checkpointer; se neutraliza para no tocarla.
    import app.esquema_requerido as esq

    async def _sin_esquema():
        return None

    monkeypatch.setattr(esq, "exigir_esquema", _sin_esquema)
    _montar_con_pool_roto(monkeypatch)

    emitidos = []
    registro = io.StringIO()
    manejador = logging.StreamHandler(registro)
    logger_uvicorn = logging.getLogger("uvicorn.error")
    logger_uvicorn.addHandler(manejador)
    nivel_previo = logger_uvicorn.level
    logger_uvicorn.setLevel(logging.ERROR)

    async def _conducir_lifespan_como_uvicorn():
        cola = asyncio.Queue()
        await cola.put({"type": "lifespan.startup"})

        async def receive():
            return await cola.get()

        async def send(mensaje):
            emitidos.append(mensaje)

        try:
            await main.app({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send)
        except BaseException as exc:  # noqa: BLE001 — exactamente lo que hace uvicorn
            logger_uvicorn.error("Exception in 'lifespan' protocol\n", exc_info=exc)

    try:
        asyncio.run(_conducir_lifespan_como_uvicorn())
    finally:
        logger_uvicorn.removeHandler(manejador)
        logger_uvicorn.setLevel(nivel_previo)

    capturado = capsys.readouterr()
    mensaje_asgi = next(
        (m.get("message", "") for m in emitidos if m.get("type") == "lifespan.startup.failed"), "")
    log_uvicorn = registro.getvalue()

    assert mensaje_asgi, "el arnes no reprodujo un fallo de startup: no prueba nada"

    superficies = {
        "stdout": capturado.out,
        "stderr": capturado.err,
        "mensaje ASGI lifespan.startup.failed": mensaje_asgi,
        "logger uvicorn.error (exc_info)": log_uvicorn,
    }
    for nombre, texto in superficies.items():
        assert _CENTINELA not in texto, f"el centinela ESCAPO por {nombre}"
        assert "host-interno" not in texto, f"el host interno ESCAPO por {nombre}"

    # Positiva: el fallo tiene que seguir siendo visible y nombrable.
    assert "CheckpointerStartupError" in mensaje_asgi, \
        "arreglar la fuga volviendo el fallo invisible es peor que la fuga"
    assert "CheckpointerStartupError" in log_uvicorn


# ══ Lo que NO debe cambiar ════════════════════════════════════════════════════════════
def test_health_conserva_exactamente_su_contrato(db_arriba, monkeypatch):
    """`/health` tiene consumidores (el vigía de salud). Separar readiness no es excusa
    para romperlo en el mismo cambio."""
    monkeypatch.setattr(main, "get_checkpointer", lambda: None)
    r = _cliente().get("/health")
    assert r.status_code == 200, "degradado sigue siendo 200, a proposito"
    cuerpo = r.json()
    assert set(cuerpo) == {"status", "service", "database", "memoria"}
    assert cuerpo["status"] == "degraded"
    assert cuerpo["memoria"] == "volatil"
    assert cuerpo["database"] == "up"


def test_render_yaml_documenta_live_como_health_check_path():
    """Documental **para este servicio y con fecha**, no por una propiedad general de Render.

    VERIFICADO el 2026-09-16: la cuenta no tiene ninguna Blueprint instance y
    `contexto-ai-oregon` no está asociado a una, así que este valor no puede sincronizarse
    y el Health Check Path real —hoy vacío— se configura en el panel.

    Lo que NO se afirma, porque sería falso: que declarar `healthCheckPath` en un archivo
    de Blueprint no lo aplique. La documentación de Render dice que **sí** lo configura. Si
    algún día el servicio pasa a estar gestionado por Blueprint, este valor deja de ser
    documental — y entonces la secuencia del ADR (readiness → validar → configurar `/live`)
    quedaría corta por este archivo. Por eso el comentario del YAML lleva fecha.
    """
    raiz = pathlib.Path(__file__).resolve().parents[1]
    texto = (raiz / "render.yaml").read_text(encoding="utf-8")
    assert "healthCheckPath: /live" in texto
    assert "healthCheckPath: /health" not in texto
