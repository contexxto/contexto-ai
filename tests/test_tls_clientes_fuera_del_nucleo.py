"""
#137 · clientes MUST HARDEN: todo lo que abre una conexión a Postgres FUERA del núcleo toma la
política TLS de `app/db_tls`.

El núcleo (app/database.py y el checkpointer de app/agent/graph.py) conecta con verify-full desde
el 2026-09-22 (producción = 35ab481). Los scripts que usan su `engine` heredan esa política. Pero
cuatro clientes abrían su propia conexión con la TLS por defecto del driver —`prefer` en asyncpg,
`sslmode=require` pegado a la URL en el refresco de POIs—: cifrado si el servidor quiere, sin
verificar a quién. El censo del handoff los marcó MUST HARDEN; esta prueba los fija y vigila que no
aparezca un quinto.

La regla, leída del árbol sintáctico (no por texto): cada llamada que abre conexión —create_engine,
create_async_engine, psycopg.connect, psycopg2.connect, asyncpg.connect, asyncpg.create_pool,
ConnectionPool, AsyncConnectionPool— lleva la política de db_tls (`connect_args=`, `kwargs=` o `**`)
calculada para la MISMA URL con la que conecta. Y ningún cliente fija TLS en la URL (`sslmode=`):
la política rechaza eso a propósito. Que db_tls verifica de verdad lo prueban T1/T2/T3 del núcleo
(test_db_tls_verify_full.py, contra un Postgres con TLS real); aquí se prueba que los clientes lo usan.
"""
import ast
import subprocess
from pathlib import Path

import pytest

from app import db_tls

RAIZ = Path(__file__).resolve().parents[1]
FUERA_DEL_ALCANCE = ('app/', 'tests/')           # el núcleo tiene sus guardas (G1–G5); las pruebas usan loopback
CONSTRUCTORES = {'create_engine', 'create_async_engine', 'ConnectionPool', 'AsyncConnectionPool'}
CONECTORES = {('psycopg', 'connect'), ('psycopg2', 'connect'), ('asyncpg', 'connect'), ('asyncpg', 'create_pool')}
POLITICA = {'connect_args_asyncpg', 'kwargs_psycopg'}
LOS_CUATRO = ['scripts/foso_pois_spike.py', 'scripts/asignar_corredor.py',
              'scripts/spike_commute_hora_pico.py', 'evals/adjudicador_territorial.py']


def _abre_conexion(nodo: ast.Call) -> bool:
    f = nodo.func
    if isinstance(f, ast.Name):
        return f.id in CONSTRUCTORES
    if isinstance(f, ast.Attribute):
        if f.attr in CONSTRUCTORES:
            return True
        return isinstance(f.value, ast.Name) and (f.value.id, f.attr) in CONECTORES
    return False


def _es_politica(v: ast.AST) -> bool:
    return (isinstance(v, ast.Call) and isinstance(v.func, ast.Attribute) and v.func.attr in POLITICA
            and isinstance(v.func.value, ast.Name) and v.func.value.id == 'db_tls')


def llamadas_sin_politica(fuente: str, nombre: str = '<fuente>') -> list[str]:
    """Las llamadas que abren conexión sin la política de db_tls para su misma URL."""
    faltan = []
    for nodo in ast.walk(ast.parse(fuente)):
        if not (isinstance(nodo, ast.Call) and _abre_conexion(nodo)):
            continue
        url = ast.dump(nodo.args[0]) if nodo.args else None
        politicas = [k.value for k in nodo.keywords
                     if k.arg in ('connect_args', 'kwargs', None) and _es_politica(k.value)]
        misma_url = any(p.args and url is not None and ast.dump(p.args[0]) == url for p in politicas)
        if not misma_url:
            faltan.append(f'{nombre}:{nodo.lineno}')
    return faltan


def _docstrings(arbol: ast.AST) -> set[int]:
    """Los nodos que son docstring (primera sentencia de módulo, clase o función): prosa, no URL."""
    ids = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and nodo.body:
            primero = nodo.body[0]
            if isinstance(primero, ast.Expr) and isinstance(primero.value, ast.Constant):
                ids.add(id(primero.value))
    return ids


def tls_en_la_url(fuente: str, nombre: str = '<fuente>') -> list[str]:
    """Cadenas que fijan TLS en la URL (sslmode=): la política las rechaza en una URL remota.
    Las docstrings no cuentan: explicar por qué ya no se hace no es hacerlo."""
    arbol = ast.parse(fuente)
    prosa = _docstrings(arbol)
    return [f'{nombre}:{n.lineno}' for n in ast.walk(arbol)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and 'sslmode=' in n.value
            and id(n) not in prosa]


def _clientes() -> list[str]:
    salida = subprocess.run(['git', 'ls-files', '*.py'], cwd=RAIZ, capture_output=True, text=True, check=True).stdout
    return [f for f in salida.split() if not f.startswith(FUERA_DEL_ALCANCE)]


def _leer(rel: str) -> str:
    return (RAIZ / rel).read_text(encoding='utf-8')


def test_ningun_cliente_fuera_del_nucleo_conecta_sin_la_politica():
    faltan = [x for f in _clientes() for x in llamadas_sin_politica(_leer(f), f)]
    assert faltan == [], f'conectan sin la TLS de app/db_tls: {faltan}'


@pytest.mark.parametrize('rel', LOS_CUATRO)
def test_los_cuatro_del_censo_abren_su_conexion_con_la_politica(rel):
    fuente = _leer(rel)
    conexiones = [n for n in ast.walk(ast.parse(fuente)) if isinstance(n, ast.Call) and _abre_conexion(n)]
    assert conexiones, f'{rel} ya no abre conexión propia: actualizar el censo'
    assert llamadas_sin_politica(fuente, rel) == []
    assert 'from app import db_tls' in fuente


def test_ningun_cliente_fija_tls_en_la_url():
    halladas = [x for f in _clientes() for x in tls_en_la_url(_leer(f), f)]
    assert halladas == [], f'TLS escrita en la URL: {halladas}'


def test_el_refresco_instala_el_ancla_en_su_ruta_canonica_antes_de_conectar():
    flujo = _leer('.github/workflows/refresco-pois.yml')
    instala = flujo.find(f'sudo install -D -m 0644 certs/supabase/bundle-v1.pem {db_tls.RUTA_BUNDLE}')
    comprueba = flujo.find('db_tls.validar_bundle()')
    refresca = flujo.find('python scripts/foso_pois_spike.py "${CIUDAD}" --sin-validacion')
    assert instala > -1, 'el runner no instala el ancla en la ruta que exige app/db_tls'
    assert -1 < comprueba and instala < comprueba < refresca, 'el ancla se instala y se comprueba ANTES del refresco'


# ── El canal llega al driver: lo que asyncpg y psycopg RECIBEN, no lo que el código dice ──────────

URL_REMOTA = 'u:p@db.remoto.example:5432/x'   # host que no resuelve: el driver falso corta antes de la red


class _Alto(Exception):
    pass


def test_por_connect_args_asyncpg_recibe_un_contexto_que_verifica(monkeypatch):
    import asyncio
    import ssl

    import asyncpg
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    monkeypatch.setattr(db_tls, 'RUTA_BUNDLE', str(RAIZ / 'certs/supabase/bundle-v1.pem'))
    visto = {}

    async def falso(*a, **k):
        visto.update(k)
        raise _Alto()
    monkeypatch.setattr(asyncpg, 'connect', falso)

    url = f'postgresql+asyncpg://{URL_REMOTA}'
    motor = create_async_engine(url, poolclass=NullPool, connect_args=db_tls.connect_args_asyncpg(url))

    async def abrir():
        with pytest.raises(_Alto):
            async with motor.connect():
                pass
    asyncio.run(abrir())
    contexto = visto.get('ssl')
    assert isinstance(contexto, ssl.SSLContext)
    assert contexto.verify_mode == ssl.CERT_REQUIRED and contexto.check_hostname is True


@pytest.mark.parametrize('con_politica', [False, True])
def test_por_connect_args_psycopg_recibe_verify_full_y_el_ancla(monkeypatch, con_politica):
    import psycopg
    from sqlalchemy import create_engine
    from sqlalchemy.pool import NullPool

    ancla = str(RAIZ / 'certs/supabase/bundle-v1.pem')
    monkeypatch.setattr(db_tls, 'RUTA_BUNDLE', ancla)
    visto = {}

    def falso(*a, **k):
        visto.update(k)
        raise _Alto()
    monkeypatch.setattr(psycopg, 'connect', falso)

    url = f'postgresql+psycopg://{URL_REMOTA}'
    extra = {'connect_args': db_tls.kwargs_psycopg(url)} if con_politica else {}
    with pytest.raises(_Alto):
        create_engine(url, poolclass=NullPool, **extra).connect()
    if con_politica:
        assert visto.get('sslmode') == 'verify-full' and visto.get('sslrootcert') == ancla
    else:
        # Control positivo: sin la política el driver no recibe TLS alguna (queda en su `prefer`).
        assert 'sslmode' not in visto and 'sslrootcert' not in visto


# ── Controles: el detector sí ve lo que dice ver ──────────────────────────────────────────────────

def test_control_el_detector_marca_los_cuatro_clientes_tal_como_estaban_en_main():
    """El control más fuerte: el código REAL de antes de este cambio, leído de git, sale marcado."""
    base = subprocess.run(['git', 'merge-base', 'HEAD', 'origin/main'], cwd=RAIZ, capture_output=True, text=True).stdout.strip()
    if not base:
        pytest.skip('sin historia de git para leer la versión anterior')
    marcados = []
    for rel in LOS_CUATRO:
        antes = subprocess.run(['git', 'show', f'{base}:{rel}'], cwd=RAIZ, capture_output=True, text=True, encoding='utf-8').stdout
        if antes and 'db_tls' not in antes:
            marcados.append(bool(llamadas_sin_politica(antes, rel)))
    if not marcados:
        pytest.skip('la versión base ya trae la política (este control solo muerde antes de fusionar)')
    assert all(marcados)

def test_control_detecta_un_cliente_sin_politica():
    assert llamadas_sin_politica('e = create_async_engine(URL, poolclass=NullPool)')
    assert llamadas_sin_politica('c = psycopg.connect(dsn, autocommit=True)')
    assert llamadas_sin_politica('p = asyncpg.create_pool(dsn)')


def test_control_detecta_la_politica_calculada_para_otra_url():
    # La trampa: la política de una URL de loopback es {} — pasarla con otra URL es no tener política.
    assert llamadas_sin_politica('e = create_async_engine(URL, connect_args=db_tls.connect_args_asyncpg(OTRA))')


def test_control_acepta_los_tres_canales_de_la_politica():
    assert not llamadas_sin_politica('e = create_async_engine(U, connect_args=db_tls.connect_args_asyncpg(U))')
    assert not llamadas_sin_politica('e = create_engine(U, connect_args=db_tls.kwargs_psycopg(U))')
    assert not llamadas_sin_politica('c = psycopg.connect(U, autocommit=True, **db_tls.kwargs_psycopg(U))')
    assert not llamadas_sin_politica('p = AsyncConnectionPool(U, kwargs=db_tls.kwargs_psycopg(U))')


def test_control_detecta_tls_en_la_url():
    assert tls_en_la_url('u = url + "?sslmode=require"')
    assert not tls_en_la_url('# sslmode=require en un comentario no cuenta\nu = url')
    assert not tls_en_la_url('def f(u):\n    """Antes se añadía sslmode=require."""\n    return u')
    assert tls_en_la_url('def f(u):\n    """Doc."""\n    return u + "?sslmode=require"')
