"""R2C1 — `verify-full` para los dos clientes del núcleo, probado contra TLS real.

QUÉ CAMBIA ESTA UNIDAD. Hasta aquí el cliente resolvía `prefer`: ciframos si el servidor
quiere, y no verificamos ni la cadena ni el hostname. Eso protege del fisgón pasivo y de
nada más — un intermediario que presente cualquier certificado se acepta sin pestañear.
Desde aquí, para cualquier host que no sea loopback, ambos stacks exigen `verify-full`.

LA PARTE REAL Y LA PARTE DE CONFIGURACIÓN, que no son lo mismo:

  * T1/T2/T3 abren conexiones TLS **de verdad** contra un PostgreSQL efímero. Son las
    únicas que pueden demostrar la propiedad criptográfica, y por eso no se degradan a
    dobles bajo ninguna circunstancia (ver `tests/arnes_postgres_tls.py`).
  * T4..T17 son de configuración y fallo cerrado: no necesitan servidor porque afirman que
    NO se llega a conectar.

POR QUÉ HACEN FALTA LAS DOS FAMILIAS. Las de configuración prueban que la política se
construye bien; las reales prueban que la política construida efectivamente verifica. Se ha
visto más de una vez un `sslmode=verify-full` bien puesto que no verificaba nada porque el
ancla no estaba donde se creía.
"""
from __future__ import annotations

import asyncio
import ssl
import tempfile
from pathlib import Path

import pytest

from app import db_tls
from tests import arnes_postgres_tls as arnes

URL_REMOTA = "postgresql+asyncpg://u:p@aws-1-us-west-2.pooler.supabase.com:5432/postgres"
URL_LOOPBACK = "postgresql+asyncpg://u:p@localhost:5432/postgres"
BUNDLE_DEL_REPO = Path(__file__).resolve().parents[1] / "certs" / "supabase" / "bundle-v1.pem"


# ══ Arnés real ════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope="module")
def tls_real():
    """Dos PostgreSQL con TLS, uno por escenario. Se levantan una vez por módulo."""
    arnes.exigir_arnes_disponible()
    tmp = Path(tempfile.mkdtemp(prefix="r2c1_tls_"))
    try:
        yield arnes.levantar_arnes(tmp)
    finally:
        arnes.derribar_arnes()


async def _conectar_asyncpg(puerto: int, ca: Path, host: str = "localhost"):
    import asyncpg
    # El contexto lo construye LA POLÍTICA, no el test: lo que se prueba es lo que
    # producción usará, no una reconstrucción parecida hecha aquí al lado.
    ctx = db_tls.contexto_ssl_asyncpg(ruta_bundle=ca)
    conexion = await asyncpg.connect(
        host=host, port=puerto, user=arnes.USUARIO, password=arnes.CLAVE,
        database=arnes.BASE, ssl=ctx, timeout=20,
    )
    try:
        return await conexion.fetchval("SELECT 1")
    finally:
        await conexion.close()


def _conectar_psycopg(puerto: int, ca: Path, host: str = "localhost"):
    import psycopg
    # Igual que arriba: los kwargs salen de la política. Se le pasa una URL REMOTA porque
    # eso es lo que gobierna la decisión (loopback estaría exento); el puerto al que de
    # hecho se conecta es el del arnés.
    kwargs = db_tls.kwargs_psycopg(URL_REMOTA, ruta_bundle=ca)
    assert kwargs["sslmode"] == "verify-full"
    with psycopg.connect(
        host=host, port=puerto, user=arnes.USUARIO, password=arnes.CLAVE,
        dbname=arnes.BASE, connect_timeout=20, **kwargs,
    ) as conexion:
        return conexion.execute("SELECT 1").fetchone()[0]


# ── T1 · CA y hostname correctos → conecta ────────────────────────────────────────────
def test_T1_asyncpg_conecta_con_ca_y_hostname_correctos(tls_real):
    assert asyncio.run(_conectar_asyncpg(tls_real.puerto_ok, tls_real.ca_buena)) == 1


def test_T1_psycopg_conecta_con_ca_y_hostname_correctos(tls_real):
    assert _conectar_psycopg(tls_real.puerto_ok, tls_real.ca_buena) == 1


# ── T2 · CA equivocada → falla por CADENA ─────────────────────────────────────────────
def test_T2_asyncpg_rechaza_una_ca_equivocada(tls_real):
    """El servidor es el mismo que en T1 y su certificado es perfectamente válido: lo único
    que cambia es el ancla del cliente. Si esto pasara, no estaríamos verificando nada."""
    with pytest.raises(ssl.SSLCertVerificationError) as e:
        asyncio.run(_conectar_asyncpg(tls_real.puerto_ok, tls_real.ca_mala))
    assert "CERTIFICATE_VERIFY_FAILED" in str(e.value)


def test_T2_psycopg_rechaza_una_ca_equivocada(tls_real):
    import psycopg
    with pytest.raises(psycopg.OperationalError) as e:
        _conectar_psycopg(tls_real.puerto_ok, tls_real.ca_mala)
    assert "certificate verify failed" in str(e.value).lower()


# ── T3 · hostname incorrecto → falla por NOMBRE ───────────────────────────────────────
def test_T3_asyncpg_rechaza_un_hostname_que_no_coincide(tls_real):
    """Aquí el ancla es la CORRECTA y la cadena valida. Lo único que falla es el nombre —
    que es precisamente la diferencia entre `verify-ca` y `verify-full`, y el motivo por el
    que R2A.2 descartó `verify-ca` como estado de producción."""
    with pytest.raises(ssl.SSLCertVerificationError) as e:
        asyncio.run(_conectar_asyncpg(tls_real.puerto_host_malo, tls_real.ca_buena))
    texto = str(e.value)
    assert "Hostname mismatch" in texto or "hostname" in texto.lower()


def test_T3_psycopg_rechaza_un_hostname_que_no_coincide(tls_real):
    import psycopg
    with pytest.raises(psycopg.OperationalError) as e:
        _conectar_psycopg(tls_real.puerto_host_malo, tls_real.ca_buena)
    assert arnes.HOST_DEL_CERT_MALO in str(e.value)


def test_T3b_los_dos_fallos_no_son_el_mismo_fallo(tls_real):
    """Control del control. Si T2 y T3 fallaran por la misma causa, uno de los dos no
    estaría probando lo que dice — y la distinción cadena/nombre, que es la razón de ser de
    `verify-full`, quedaría sin evidencia."""
    with pytest.raises(ssl.SSLCertVerificationError) as ca_mala:
        asyncio.run(_conectar_asyncpg(tls_real.puerto_ok, tls_real.ca_mala))
    with pytest.raises(ssl.SSLCertVerificationError) as host_malo:
        asyncio.run(_conectar_asyncpg(tls_real.puerto_host_malo, tls_real.ca_buena))
    assert "unable to get local issuer" in str(ca_mala.value).lower()
    assert "hostname mismatch" in str(host_malo.value).lower()


# ══ T4..T6 · el bundle, y qué pasa cuando no sirve ════════════════════════════════════
@pytest.mark.parametrize("caso", ["ausente", "vacio", "basura", "directorio"])
def test_T4_T5_T6_un_bundle_inutilizable_cierra_antes_de_conectar(tmp_path, caso):
    """Falla CERRADO y falla PRONTO — antes de que exista pool o engine.

    El orden importa más de lo que parece. `AsyncConnectionPool.__init__` guarda sus kwargs
    sin validarlos, así que un `sslrootcert` mal escrito no se nota al construir el pool
    sino en el primer checkout, ya con la app arriba, y llega disfrazado de timeout.
    """
    if caso == "ausente":
        ruta = tmp_path / "no-existe.pem"
    elif caso == "vacio":
        ruta = tmp_path / "vacio.pem"; ruta.write_bytes(b"")
    elif caso == "basura":
        ruta = tmp_path / "basura.pem"; ruta.write_text("esto no es un certificado\n")
    else:
        ruta = tmp_path / "soy_un_directorio.pem"; ruta.mkdir()

    for construir in (db_tls.validar_bundle,
                      lambda r: db_tls.contexto_ssl_asyncpg(ruta_bundle=r),
                      lambda r: db_tls.connect_args_asyncpg(URL_REMOTA, ruta_bundle=r),
                      lambda r: db_tls.kwargs_psycopg(URL_REMOTA, ruta_bundle=r)):
        with pytest.raises(db_tls.TLSPolicyError):
            construir(ruta)


def test_T4b_el_bundle_del_repo_si_sirve():
    """Control positivo: sin él, los cuatro casos de arriba estarían verdes aunque la
    validación rechazara TODO, incluido el ancla buena."""
    assert db_tls.validar_bundle(BUNDLE_DEL_REPO) == str(BUNDLE_DEL_REPO)
    ctx = db_tls.contexto_ssl_asyncpg(ruta_bundle=BUNDLE_DEL_REPO)
    assert ctx.get_ca_certs()


# ══ T7 · G1 — la URL compartida no fija TLS ═══════════════════════════════════════════
@pytest.mark.parametrize("parametro", [
    "sslmode=require", "sslmode=verify-ca", "sslrootcert=/otra/ca.pem", "ssl=true",
    "sslcert=/x.crt", "sslkey=/x.key", "sslcrl=/x.crl", "sslcrldir=/x",
    "sslnegotiation=direct", "sslcertmode=disable", "sslcompression=1", "sslsni=0",
    "ssl_min_protocol_version=TLSv1", "sslpassword=x",
    "gssencmode=require", "requiressl=1",
    "SSLMODE=require",                      # mayúsculas: la comparación es insensible
])
def test_T7_una_url_remota_con_parametros_tls_se_rechaza(parametro):
    """`sslcertmode` y `sslnegotiation` no existen en libpq 14 (la rueda de Windows) y sí en
    la 17, que es la de producción — medido. Por eso la guarda es una REGLA de prefijo y no
    una lista escrita a mano mirando el portátil."""
    url = f"{URL_REMOTA}?{parametro}"
    with pytest.raises(db_tls.TLSPolicyError) as e:
        db_tls.connect_args_asyncpg(url, ruta_bundle=BUNDLE_DEL_REPO)
    assert parametro.split("=")[0].lower() in str(e.value).lower()
    with pytest.raises(db_tls.TLSPolicyError):
        db_tls.kwargs_psycopg(url, ruta_bundle=BUNDLE_DEL_REPO)


def test_T7b_un_parametro_inocente_no_se_rechaza():
    """Control negativo de la guarda: si rechazara cualquier query string, la prueba de
    arriba pasaría por el motivo equivocado."""
    url = f"{URL_REMOTA}?application_name=contexto"
    assert "ssl" in db_tls.connect_args_asyncpg(url, ruta_bundle=BUNDLE_DEL_REPO)


# ══ T8/T9 · lo que el entorno y la URL NO pueden hacer ════════════════════════════════
def test_T8_PGSSLMODE_del_entorno_no_apaga_el_contexto_de_asyncpg(monkeypatch):
    """`PGSSLMODE` es una variable de libpq; asyncpg no la lee, y con un `SSLContext`
    explícito no habría forma de que la obedeciera aunque quisiera. Se afirma para que
    nadie "arregle" un incidente futuro poniéndola en Render y crea que hizo algo."""
    monkeypatch.setenv("PGSSLMODE", "disable")
    ctx = db_tls.connect_args_asyncpg(URL_REMOTA, ruta_bundle=BUNDLE_DEL_REPO)["ssl"]
    assert ctx.check_hostname is True
    assert ctx.verify_mode is ssl.CERT_REQUIRED


def test_T9_un_sslmode_require_inline_no_puede_degradar_el_pool():
    """La degradación silenciosa que motivó G1: `sslmode=require` inline habría dado
    `verify-ca` —cadena sí, hostname no— donde se pidió `verify-full`. Se corta antes: la
    URL se rechaza, así que la degradación no llega a existir."""
    with pytest.raises(db_tls.TLSPolicyError):
        db_tls.kwargs_psycopg(f"{URL_REMOTA}?sslmode=require", ruta_bundle=BUNDLE_DEL_REPO)


# ══ T10/T11 · la forma exacta de lo que recibe psycopg ════════════════════════════════
def test_T10_los_kwargs_de_psycopg_son_verify_full_y_la_ruta_exacta():
    kwargs = db_tls.kwargs_psycopg(URL_REMOTA, ruta_bundle=BUNDLE_DEL_REPO)
    assert kwargs == {"sslmode": "verify-full", "sslrootcert": str(BUNDLE_DEL_REPO)}


def test_T11_la_conninfo_no_se_muta():
    """La política va por `kwargs=` del pool. Si alguien la concatenara a la conninfo, la
    URL compartida podría contradecirla — y en psycopg ganaría el kwarg, dejando dos
    verdades en el mismo sitio."""
    original = "postgresql://u:p@aws-1-us-west-2.pooler.supabase.com:5432/postgres"
    copia = str(original)
    db_tls.kwargs_psycopg(original, ruta_bundle=BUNDLE_DEL_REPO)
    assert original == copia


# ══ T12 · loopback ════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("host,esperado", [
    ("localhost", True), ("LOCALHOST", True),
    ("127.0.0.1", True), ("127.9.9.9", True), ("[::1]", True),
    ("aws-1-us-west-2.pooler.supabase.com", False),
    ("localhost.attacker.example", False),     # sufijo, no loopback
    ("127.0.0.1.attacker.example", False),     # parece una IP y no lo es
    ("10.0.0.5", False),
])
def test_T12_clasificacion_loopback(host, esperado):
    assert db_tls.es_loopback(f"postgresql+asyncpg://u:p@{host}:5432/db") is esperado


def test_T12b_una_url_ilegible_se_trata_como_remota():
    """El modo conservador es el que cifra y verifica. Ante la duda, `verify-full`."""
    for rara in ("", "esto no es una url ::::", "postgresql+asyncpg:///sinhost"):
        assert db_tls.es_loopback(rara) is False


def test_T12c_loopback_no_pide_ancla_ni_toca_nada(tmp_path):
    """Con el ancla apuntando a un archivo inexistente, loopback sigue funcionando: la
    exención es de la URL y no depende del bundle."""
    inexistente = tmp_path / "no-existe.pem"
    assert db_tls.connect_args_asyncpg(URL_LOOPBACK, ruta_bundle=inexistente) == {}
    assert db_tls.kwargs_psycopg(URL_LOOPBACK, ruta_bundle=inexistente) == {}


def test_T12d_no_se_resuelve_dns_para_decidir(monkeypatch):
    """Si preguntáramos al resolver, quien controle el DNS decidiría si ciframos. Se afirma
    haciendo explotar la resolución: la clasificación no debe notarlo."""
    import socket as socket_mod

    def _prohibido(*_a, **_k):
        raise AssertionError("la clasificación loopback resolvió DNS")

    monkeypatch.setattr(socket_mod, "getaddrinfo", _prohibido)
    monkeypatch.setattr(socket_mod, "gethostbyname", _prohibido)
    assert db_tls.es_loopback(URL_LOOPBACK) is True
    assert db_tls.es_loopback(URL_REMOTA) is False


# ══ T13/T14 · saneamiento del error ═══════════════════════════════════════════════════
_CENTINELA = "clave-secreta-que-no-debe-salir-9f2c"


def test_T13_el_error_no_arrastra_la_cadena_de_conexion(tmp_path):
    """El mensaje se publica: esto se levanta en el arranque, Starlette lo mete en
    `lifespan.startup.failed` y uvicorn lo registra con `exc_info`. Lo que traiga el texto,
    se publica — la misma fuga que se cerró en R2B1."""
    url = f"postgresql://usuario:{_CENTINELA}@aws-1-us-west-2.pooler.supabase.com:5432/db"
    for construir in (lambda: db_tls.connect_args_asyncpg(url, ruta_bundle=tmp_path / "no.pem"),
                      lambda: db_tls.kwargs_psycopg(url, ruta_bundle=tmp_path / "no.pem"),
                      lambda: db_tls.connect_args_asyncpg(f"{url}?sslmode=require")):
        with pytest.raises(db_tls.TLSPolicyError) as e:
            construir()
        texto = f"{e.value}{getattr(e.value, 'args', '')}"
        assert _CENTINELA not in texto
        assert "usuario" not in texto
        assert "pooler.supabase.com" not in texto


def test_T14_la_excepcion_saneada_usa_la_semantica_ya_congelada(tmp_path):
    """Con la precisión que costó una errata en R2B1: `from None` fija
    `__suppress_context__` para que los formateadores estándar no presenten la original.
    NO la borra — `__context__` puede seguir apuntando a ella. Lo que se garantiza es la no
    exposición en las superficies verificadas, no la ausencia en memoria. La prueba afirma
    exactamente eso y ni una palabra más."""
    basura = tmp_path / "basura.pem"
    basura.write_text("no soy un certificado")
    with pytest.raises(db_tls.TLSPolicyError) as e:
        db_tls.validar_bundle(basura)
    assert e.value.__cause__ is None
    assert e.value.__suppress_context__ is True


# ══ T15/T16/T17 · guardas estáticas ═══════════════════════════════════════════════════
_RAIZ = Path(__file__).resolve().parents[1]
# Runtime de APLICACIÓN/checkpointer. `scripts/` y `evals/` quedan FUERA a propósito: están
# censados y pendientes de endurecer en su propia unidad, y una guarda global los declararía
# ilegales sin arreglarlos — que es como un control de seguridad acaba desactivado.
_RUNTIME_APP = ("app", "main.py")


def _fuentes_del_runtime():
    for raiz in _RUNTIME_APP:
        p = _RAIZ / raiz
        yield from ([p] if p.is_file() else sorted(p.rglob("*.py")))


def test_T15_G3_nadie_esquiva_el_pool_canonico_en_el_runtime():
    """`AsyncPostgresSaver.from_conn_string` abre su propia conexión a partir de la cadena,
    sin pasar por los `kwargs` del pool — es decir, sin política TLS. Es el bypass más fácil
    de escribir sin darse cuenta, porque es justo lo que sugiere la documentación."""
    from ast import parse, walk
    ofensas = []
    for f in _fuentes_del_runtime():
        for n in walk(parse(f.read_text(encoding="utf-8"))):
            if n.__class__.__name__ == "Call" and getattr(n.func, "attr", None) in (
                "from_conn_string", "connect", "AsyncConnectionPool", "ConnectionPool",
            ):
                duenyo = getattr(getattr(n.func, "value", None), "id", None)
                if duenyo in ("AsyncPostgresSaver", "PostgresSaver", "psycopg"):
                    ofensas.append(f"{f.relative_to(_RAIZ)}:{n.lineno} {duenyo}.{n.func.attr}")
    assert not ofensas, f"conexión psycopg fuera de la política del núcleo: {ofensas}"


def test_T16_G4_el_runtime_no_concatena_tls_a_la_url():
    """Concatenar `?sslmode=...` a la cadena compartida es la otra forma de tener dos
    políticas. Se prohíbe en el runtime de app; los scripts censados van en su unidad."""
    ofensas = []
    for f in _fuentes_del_runtime():
        if f.name == "db_tls.py":
            continue                       # es el único sitio donde TLS es tema
        texto = f.read_text(encoding="utf-8")
        for aguja in ("sslmode=", "sslrootcert=", "?ssl", "&ssl"):
            if aguja in texto:
                ofensas.append(f"{f.relative_to(_RAIZ)} contiene {aguja!r}")
    assert not ofensas, ofensas


def test_T17_G5_sslmode_no_es_el_oraculo_de_la_postura_de_asyncpg():
    """Con `SSLContext` explícito, `sslmode` puede no aparecer en ningún sitio y la conexión
    estar verificando hostname igualmente. Quien audite la postura de asyncpg tiene que
    mirar el contexto; buscar la palabra da una respuesta falsa y tranquilizadora."""
    args = db_tls.connect_args_asyncpg(URL_REMOTA, ruta_bundle=BUNDLE_DEL_REPO)
    assert "sslmode" not in args and "sslmode" not in repr(args).lower().replace("sslmodule", "")
    ctx = args["ssl"]
    assert isinstance(ctx, ssl.SSLContext)
    assert (ctx.check_hostname, ctx.verify_mode) == (True, ssl.CERT_REQUIRED)
