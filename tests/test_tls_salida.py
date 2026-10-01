"""
`SSL_VERIFY=system` — verificar TLS contra el almacén del sistema operativo (app/tls_salida.py).

El problema que cierra: en la máquina de desarrollo Avast re-firma el TLS. Windows confía en
su raíz y certifi no, así que el único arreglo disponible era `SSL_VERIFY=false`. Y eso no
apaga solo la llamada a Anthropic: `graph.py` parcha httpx para TODO el proceso, de modo que
Supabase Auth, Google, Voyage y la visión también corrían sin verificar.

`system` verifica con las raíces del sistema, cliente por cliente. Lo que más se prueba aquí:
  - que los valores que ya existían devuelven EXACTAMENTE lo mismo que antes;
  - que `system` no hace inyección global (rompería `db_tls`, que conecta a Postgres);
  - que ningún cliente saliente de app/ se salta el helper, porque en `system` no hay
    parche global que lo rescate: el que no pase `verify=` usaría certifi.

Sin red. La prueba contra el TLS real de Avast no cabe en CI: va en el PR.
"""
import ast
import pathlib
import ssl
import sys

import pytest

from app.config import settings
from app.tls_salida import _contexto_del_sistema, verificacion_httpx

APP = pathlib.Path(__file__).resolve().parent.parent / "app"


@pytest.fixture(autouse=True)
def _sin_cache():
    _contexto_del_sistema.cache_clear()
    yield
    _contexto_del_sistema.cache_clear()


# ── Paridad: lo que ya existía no cambia ────────────────────────────────────────────

@pytest.mark.parametrize("valor", ["true", "True", "TRUE", "1", "yes", "cualquier-cosa"])
def test_todo_lo_que_no_es_false_ni_system_sigue_verificando_con_certifi(monkeypatch, valor):
    monkeypatch.setattr(settings, "ssl_verify", valor)
    assert verificacion_httpx() is True


@pytest.mark.parametrize("valor", ["false", "False", "FALSE"])
def test_false_sigue_apagando(monkeypatch, valor):
    monkeypatch.setattr(settings, "ssl_verify", valor)
    assert verificacion_httpx() is False


def test_el_default_de_settings_verifica():
    from app.config import Settings
    assert Settings.model_fields["ssl_verify"].default == "true"


# ── system: el almacén del sistema, con la verificación encendida ───────────────────

@pytest.mark.parametrize("valor", ["system", "SYSTEM", "System"])
def test_system_entrega_un_contexto_de_truststore_que_verifica(monkeypatch, valor):
    import truststore

    monkeypatch.setattr(settings, "ssl_verify", valor)
    ctx = verificacion_httpx()
    assert isinstance(ctx, truststore.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


def test_system_no_inyecta_nada_global(monkeypatch):
    """`truststore.inject_into_ssl()` reemplaza `ssl.SSLContext` para todo el proceso, y
    `db_tls.validar_bundle` revienta (`get_ca_certs` → NotImplementedError) antes de
    conectar a Postgres. El contexto tiene que ser por cliente."""
    import truststore

    antes = ssl.SSLContext
    monkeypatch.setattr(settings, "ssl_verify", "system")
    verificacion_httpx()
    assert ssl.SSLContext is antes
    assert ssl.SSLContext is not truststore.SSLContext


def test_system_sin_truststore_falla_con_el_motivo(monkeypatch):
    """En producción el paquete no está (requirements-dev.txt): `system` ahí tiene que
    reventar al arrancar, no degradar a certifi ni a `false` en silencio."""
    monkeypatch.setitem(sys.modules, "truststore", None)  # import → ImportError
    monkeypatch.setattr(settings, "ssl_verify", "system")
    with pytest.raises(RuntimeError, match="truststore"):
        verificacion_httpx()


def test_truststore_no_va_en_las_dependencias_de_produccion():
    raiz = APP.parent
    prod = (raiz / "requirements.txt").read_text(encoding="utf-8").lower()
    dev = (raiz / "requirements-dev.txt").read_text(encoding="utf-8").lower()
    assert "truststore" not in prod
    assert "truststore==" in dev


# ── Guardas estructurales: ningún cliente saliente se salta el helper ───────────────

def _modulos():
    for p in sorted(APP.rglob("*.py")):
        yield p.relative_to(APP.parent).as_posix(), ast.parse(p.read_text(encoding="utf-8"))


def test_solo_tls_salida_lee_ssl_verify():
    """Si otro módulo vuelve a leer `settings.ssl_verify` por su cuenta, `system` le llega
    como `True` (certifi) y ese cliente falla detrás de Avast mientras el resto funciona."""
    lectores = set()
    for rel, arbol in _modulos():
        for n in ast.walk(arbol):
            if isinstance(n, ast.Attribute) and n.attr == "ssl_verify":
                lectores.add(rel)
            if isinstance(n, ast.Constant) and n.value == "SSL_VERIFY":  # os.getenv("SSL_VERIFY")
                lectores.add(rel)
    assert lectores == {"app/tls_salida.py"}


def _nombre(func: ast.expr) -> str:
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def test_todo_cliente_saliente_de_app_lleva_su_verify():
    """Con `false`, `graph.py` parchaba httpx para todo el proceso y un cliente sin
    `verify=` quedaba cubierto igual. Con `system` no hay parche global: el que no lo pase
    usa certifi. Lo mismo para el SDK de Anthropic sin `http_client=`, que trae el suyo."""
    sin_verify, sin_http_client = [], []
    for rel, arbol in _modulos():
        for n in ast.walk(arbol):
            if not isinstance(n, ast.Call):
                continue
            nombre, kws = _nombre(n.func), {k.arg for k in n.keywords}
            if nombre in ("AsyncClient", "Client") and isinstance(n.func, ast.Attribute) \
                    and getattr(n.func.value, "id", "") == "httpx":
                if "verify" not in kws:
                    sin_verify.append(f"{rel}:{n.lineno}")
                else:
                    v = next(k.value for k in n.keywords if k.arg == "verify")
                    if isinstance(v, ast.Constant):
                        sin_verify.append(f"{rel}:{n.lineno} (verify literal)")
            if nombre in ("AsyncAnthropic", "Anthropic") and "http_client" not in kws:
                sin_http_client.append(f"{rel}:{n.lineno}")
    assert sin_verify == []
    assert sin_http_client == []


def test_los_parches_globales_de_graph_solo_aplican_con_false():
    """`system` llega a graph.py como un SSLContext, que es truthy: con el `if not
    _ssl_verify` de antes no se parcheaba, pero por accidente. Ahora la condición lo dice."""
    import inspect

    from app.agent import graph

    src = inspect.getsource(graph)
    assert "_ssl_verify = verificacion_httpx()" in src
    assert "if _ssl_verify is False:" in src
    assert "if not _ssl_verify" not in src
