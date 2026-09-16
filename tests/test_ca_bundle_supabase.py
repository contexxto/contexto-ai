"""R2B2 — el bundle de CA de Supabase entra al repositorio y a la imagen, SIN activar TLS.

QUÉ PRUEBA ESTO Y QUÉ NO. Esta unidad coloca un archivo y una instrucción `COPY`. No cambia
el comportamiento TLS de nada: hoy el cliente resuelve `prefer` —cifra si puede, no verifica
ni CA ni hostname— y al terminar esta unidad sigue resolviendo `prefer`. Por eso la mitad de
las pruebas de abajo (T-B8..T-B11) son NEGATIVAS: afirman que NO se activó nada. Sin ellas,
"el bundle está en el repo" y "la política TLS cambió" quedarían indistinguibles en el diff.

EL FINGERPRINT CANÓNICO ES EL DEL DER, no el del texto PEM. El PEM admite variaciones de
cabecera, orden, saltos de línea y comentarios que cambian su hash sin cambiar el certificado
— y al revés, reordenar un bundle daría un falso "cambió". Este mismo certificado lo enseña:

    sha256(DER)  = 807025ad…cafa     ← lo que se congela
    sha256(PEM)  = 70072358…f3b7     ← distinto, y no significa nada

Y EL ORÁCULO NO PUEDE SER EL ARCHIVO BAJO PRUEBA. El fingerprint esperado está escrito como
literal aquí abajo, tomado del certificado que entregó el panel de Supabase el 2026-09-16. Si
se leyera del propio bundle —o sólo del manifest, que vive en el mismo commit— la prueba sería
una tautología: cualquier sustitución del certificado pasaría, que es exactamente el ataque
que un fingerprint fijado existe para detectar. La comprobación es a TRES bandas:
bundle → DER → sha256  ==  literal de este archivo  ==  valor del manifest.

NO SE ABRE NINGUNA CONEXIÓN. Todo es lectura de archivos y parseo local; T-B11 lo impone
prohibiendo el socket, incluso durante los imports de `app.*`.
"""
import hashlib
import json
import re
import socket
from ast import Dict as AstDict, literal_eval, parse, walk
from contextlib import contextmanager
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding


_RAIZ = Path(__file__).resolve().parents[1]
_BUNDLE = _RAIZ / "certs" / "supabase" / "bundle-v1.pem"
_MANIFEST = _RAIZ / "certs" / "supabase" / "bundle-v1.manifest.json"
_DOCKERFILE = _RAIZ / "Dockerfile"

# Ruta ESTABLE dentro de la imagen. El bundle está versionado (v1, v2…) para poder rotar;
# el destino no se mueve, para que el futuro consumidor apunte siempre al mismo sitio.
RUTA_RUNTIME = "/app/certs/supabase-ca-bundle.pem"

# ══ Oráculo congelado ═════════════════════════════════════════════════════════════════
# Supabase Dashboard → proyecto contexto-ai → Database Settings → SSL Configuration →
# Download Certificate, el 2026-09-16T18:36:55Z. Archivo `prod-ca-2021.crt`, UNA CA.
# NO se deriva de nada del repositorio: ese es el punto.
FINGERPRINTS_DER_ESPERADOS = (
    "807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa",
)
SUJETO_ESPERADO = "Supabase Root 2021 CA"


# ══ T-B11 · prohibición de red, activa también durante los imports ════════════════════
@contextmanager
def _sin_red():
    """Cualquier intento de abrir un socket dentro del bloque revienta con un nombre legible.

    Se restaura siempre: si se dejara puesto, envenenaría al resto de la suite en la misma
    sesión de pytest. Se prohíbe CONECTAR, no resolver: resolver un nombre no es tráfico
    contra la base, y patchear `getaddrinfo` rompe cosas ajenas a lo que aquí se afirma.
    """
    def _prohibido(*_a, **_k):
        raise AssertionError(
            "T-B11: esta suite no puede abrir conexiones. Algo intentó salir a la red."
        )

    originales = {
        (socket.socket, "connect"): socket.socket.connect,
        (socket.socket, "connect_ex"): socket.socket.connect_ex,
        (socket, "create_connection"): socket.create_connection,
    }
    for (obj, nombre) in originales:
        setattr(obj, nombre, _prohibido)
    try:
        yield
    finally:
        for (obj, nombre), original in originales.items():
            setattr(obj, nombre, original)


# Los imports de `app.*` ocurren AQUÍ DENTRO a propósito. Importar `app.database` construye
# el engine y importar `app.agent.graph` compila el grafo; si alguno de esos efectos de
# import abriera una conexión, T-B11 sería falso y una fixture por-test no lo vería.
with _sin_red():
    from app.agent.graph import _checkpointer_conn_str
    from app.config import Settings
    from app.database import opciones_de_engine


@pytest.fixture(autouse=True)
def red_prohibida():
    with _sin_red():
        yield


# ══ Ayudas ════════════════════════════════════════════════════════════════════════════
def _bloques_pem(texto: str) -> list[str]:
    return re.findall(
        r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", texto, re.DOTALL
    )


def _manifest() -> dict:
    return json.loads(_MANIFEST.read_text(encoding="utf-8"))


def _copys_del_dockerfile() -> list[tuple[str, str]]:
    """Los `COPY origen destino` del Dockerfile, con continuaciones de línea resueltas."""
    texto = _DOCKERFILE.read_text(encoding="utf-8")
    texto = re.sub(r"\\\r?\n", " ", texto)          # une líneas partidas con `\`
    pares = []
    for linea in texto.splitlines():
        limpia = linea.strip()
        if not limpia.upper().startswith("COPY "):
            continue
        partes = [p for p in limpia.split()[1:] if not p.startswith("--")]
        if len(partes) >= 2:
            pares.append((partes[-2], partes[-1]))
    return pares


# ══ T-B1 ══════════════════════════════════════════════════════════════════════════════
def test_TB1_el_bundle_existe_en_el_repo():
    assert _BUNDLE.is_file(), f"falta {_BUNDLE.relative_to(_RAIZ)}"
    assert _MANIFEST.is_file(), f"falta {_MANIFEST.relative_to(_RAIZ)}"
    assert _BUNDLE.stat().st_size > 0


# ══ T-B2 ══════════════════════════════════════════════════════════════════════════════
def test_TB2_contiene_al_menos_un_bloque_certificate():
    bloques = _bloques_pem(_BUNDLE.read_text(encoding="utf-8"))
    assert len(bloques) >= 1, "el bundle no trae ni un bloque CERTIFICATE"


# ══ T-B3 ══════════════════════════════════════════════════════════════════════════════
def test_TB3_no_contiene_clave_privada():
    """Una CA es material PÚBLICO de confianza. Una clave privada aquí sería una credencial
    versionada en un repositorio — otra clase de objeto, con otra clase de consecuencia."""
    texto = _BUNDLE.read_text(encoding="utf-8")
    encontrados = re.findall(r"-----BEGIN ([A-Z ]*PRIVATE KEY)-----", texto)
    assert not encontrados, f"el bundle trae clave privada: {encontrados}"


# ══ T-B4 ══════════════════════════════════════════════════════════════════════════════
def test_TB4_cada_bloque_parsea_como_certificado_x509():
    """Que el base64 se decodifique no basta: `ssl.PEM_cert_to_DER_cert` traga cualquier
    payload. Aquí se exige que el ASN.1 sea un certificado de verdad."""
    bloques = _bloques_pem(_BUNDLE.read_text(encoding="utf-8"))
    for i, bloque in enumerate(bloques):
        cert = x509.load_pem_x509_certificate(bloque.encode())
        assert cert.subject.rfc4514_string(), f"bloque {i} sin subject"
        assert cert.not_valid_after_utc > cert.not_valid_before_utc


# ══ T-B5 ══════════════════════════════════════════════════════════════════════════════
def test_TB5_el_sha256_del_der_coincide_con_el_fingerprint_congelado():
    """A TRES bandas. El literal de este archivo es el único oráculo externo: el bundle y el
    manifest viajan en el mismo commit, así que compararlos entre sí no prueba nada."""
    bloques = _bloques_pem(_BUNDLE.read_text(encoding="utf-8"))
    reales = [
        hashlib.sha256(
            x509.load_pem_x509_certificate(b.encode()).public_bytes(Encoding.DER)
        ).hexdigest()
        for b in bloques
    ]
    assert reales == list(FINGERPRINTS_DER_ESPERADOS), "el certificado del repo NO es el fijado"

    del_manifest = [c["sha256_der"] for c in _manifest()["certificates"]]
    assert del_manifest == list(FINGERPRINTS_DER_ESPERADOS), "el manifest no describe ese certificado"


def test_TB5b_el_fingerprint_del_texto_pem_NO_sirve_como_sustituto():
    """Control negativo del criterio. Si esta prueba fallara —si ambos hashes coincidieran—
    la distinción DER/PEM que gobierna el runbook sería letra muerta."""
    texto = _BUNDLE.read_bytes()
    assert hashlib.sha256(texto).hexdigest() not in FINGERPRINTS_DER_ESPERADOS


# ══ T-B6 ══════════════════════════════════════════════════════════════════════════════
def test_TB6_certificate_count_coincide_con_el_contenido_real():
    manifest = _manifest()
    reales = len(_bloques_pem(_BUNDLE.read_text(encoding="utf-8")))
    assert manifest["certificate_count"] == reales
    assert len(manifest["certificates"]) == reales


def test_TB6b_el_manifest_describe_el_certificado_que_hay():
    """El manifest no es decorativo: es lo que leerá quien rote. Si su metadata se despega
    del archivo, la rotación se decide sobre datos falsos."""
    cert = x509.load_pem_x509_certificate(
        _bloques_pem(_BUNDLE.read_text(encoding="utf-8"))[0].encode()
    )
    entrada = _manifest()["certificates"][0]
    assert SUJETO_ESPERADO in entrada["subject"]
    assert SUJETO_ESPERADO in cert.subject.rfc4514_string()
    assert entrada["serial"].lower() == f"{cert.serial_number:x}".lower()
    # Raíz autofirmada: el emisor es ella misma. Si dejara de serlo, el bundle ya no es un
    # ancla de confianza sino un intermedio, y eso cambia qué significa confiar en él.
    assert cert.issuer == cert.subject
    assert entrada["issuer"] == entrada["subject"]


def test_TB6c_el_manifest_no_lleva_secretos():
    crudo = _MANIFEST.read_text(encoding="utf-8").lower()
    for prohibido in ("password", "database_url", "postgresql://", "postgres://", "@aws-", "pooler.supabase.com"):
        assert prohibido not in crudo, f"el manifest menciona {prohibido!r}"


# ══ T-B7 ══════════════════════════════════════════════════════════════════════════════
def test_TB7_el_dockerfile_copia_el_bundle_a_la_ruta_runtime_estable():
    """Un COPY PROPIO, no el arrastre del `COPY . .`.

    Hoy no existe `.dockerignore`, así que el `COPY . .` metería el bundle igual. Ese es un
    hecho de hoy que nadie vigila: el día que alguien añada un `.dockerignore` con `certs/`,
    el archivo desaparecería de la imagen EN SILENCIO y el fallo aparecería en caliente. Con
    la instrucción explícita, ese mismo día rompe el build.
    """
    destinos = {
        origen: destino
        for origen, destino in _copys_del_dockerfile()
        if destino == RUTA_RUNTIME
    }
    assert destinos, f"ningún COPY del Dockerfile deja nada en {RUTA_RUNTIME}"
    assert len(destinos) == 1, f"varios COPY pelean por {RUTA_RUNTIME}: {destinos}"

    (origen,) = destinos
    esperado = _BUNDLE.relative_to(_RAIZ).as_posix()
    assert origen == esperado, (
        f"el Dockerfile copia {origen!r}, pero el bundle versionado y verificado "
        f"por estas pruebas es {esperado!r} — se probaría un archivo y se enviaría otro"
    )
    assert (_RAIZ / origen).is_file()


def test_TB7b_el_dockerfile_no_descarga_certificados_durante_el_build():
    """Prohibición del runbook. Una descarga en build mete una dependencia de red en el
    build y deja que la imagen cambie sin que cambie el repositorio."""
    texto = _DOCKERFILE.read_text(encoding="utf-8")
    for linea in texto.splitlines():
        limpia = linea.strip()
        if limpia.startswith("#") or not limpia.upper().startswith("RUN "):
            continue
        bajo = limpia.lower()
        if any(h in bajo for h in ("curl", "wget", "openssl s_client")):
            assert not any(c in bajo for c in ("cert", ".crt", ".pem", "ca-bundle")), (
                f"el build parece descargar un certificado: {limpia}"
            )


# ══ T-B8 ══════════════════════════════════════════════════════════════════════════════
# Los archivos que forman los CAMINOS DE CONEXIÓN a Postgres. `scripts/` y `evals/` quedan
# fuera adrede: están censados y pendientes de endurecer en su propia unidad, y una guarda
# global que los declarase ilegales bloquearía trabajo legítimo sin arreglar nada.
_CAMINOS_DE_CONEXION = ("app/database.py", "app/agent/graph.py", "app/config.py", "main.py")

# Tokens de TLS de POSTGRES. `SSL_VERIFY`/`ssl_verify` NO está aquí: gobierna el cliente
# httpx de Anthropic, no la base — medido, y fuera del alcance de #137.
_TOKENS_TLS_POSTGRES = (
    "sslmode", "sslrootcert", "sslcert", "sslkey", "sslcrl", "ssl_min_protocol_version",
    "PGSSLMODE", "PGSSLROOTCERT", "PGSSLCERT", "PGSSLKEY", "PGREQUIRESSL",
    "SSLContext", "create_default_context", "CERT_REQUIRED", "CERT_NONE",
)


@pytest.mark.parametrize("ruta", _CAMINOS_DE_CONEXION)
def test_TB8_no_se_anadio_configuracion_tls_a_los_caminos_de_conexion(ruta):
    texto = (_RAIZ / ruta).read_text(encoding="utf-8")
    encontrados = [t for t in _TOKENS_TLS_POSTGRES if t in texto]
    assert not encontrados, (
        f"{ruta} menciona {encontrados} — esta unidad NO activa TLS. "
        "Si esto falla porque llegó la unidad de verify-full, la prueba debe MOVERSE "
        "a afirmar la nueva política, no borrarse."
    )


def test_TB8b_no_se_anadio_ninguna_variable_de_configuracion_tls():
    """El único campo de Settings relacionado con TLS sigue siendo `ssl_verify`, que es de
    httpx. Congelado como conjunto exacto: un campo nuevo tiene que aparecer aquí."""
    sospechosos = {
        nombre for nombre in Settings.model_fields
        if any(p in nombre.lower() for p in ("ssl", "tls", "cert", "ca_"))
    }
    assert sospechosos == {"ssl_verify"}, f"campos TLS inesperados en Settings: {sospechosos}"


# ══ T-B9 ══════════════════════════════════════════════════════════════════════════════
_URL_SESION = "postgresql+asyncpg://u:p@db.example.com:5432/postgres"
_URL_TRANSACCION = "postgresql+asyncpg://u:p@db.example.com:6543/postgres"


def test_TB9_el_engine_no_cambia_su_postura_tls():
    """Conjunto de claves CONGELADO para la rama de producción (5432).

    Deliberadamente más estrecho que `tests/test_database_pooler.py`, que afirma la ausencia
    de `connect_args` entera: aquel assert es más ancho que la política que dice defender, y
    estrecharlo pertenece a la unidad que active verify-full, en su propio commit.
    """
    opciones = opciones_de_engine(_URL_SESION)
    assert set(opciones) == {"echo", "pool_pre_ping", "pool_size", "max_overflow", "pool_recycle"}

    # La rama 6543 sí lleva connect_args — y sólo por prepared statements.
    assert set(opciones_de_engine(_URL_TRANSACCION)["connect_args"]) == {
        "prepared_statement_cache_size",
        "statement_cache_size",
        "prepared_statement_name_func",
    }


def test_TB9b_ninguna_rama_del_engine_pasa_parametros_tls():
    for url in (_URL_SESION, _URL_TRANSACCION):
        crudo = repr(opciones_de_engine(url))
        for token in ("ssl", "sslmode", "sslrootcert"):
            assert token not in crudo.lower(), f"{url} produce opciones con {token!r}"


# ══ T-B10 ═════════════════════════════════════════════════════════════════════════════
def test_TB10_la_conninfo_del_checkpointer_no_gana_parametros_tls(monkeypatch):
    """Se le da una URL SINTÉTICA. Ni se lee ni se imprime la real."""
    monkeypatch.setattr(
        "app.agent.graph.settings.database_url_override", _URL_SESION, raising=False
    )
    conn = _checkpointer_conn_str()
    assert conn == "postgresql://u:p@db.example.com:5432/postgres"
    for token in ("sslmode", "sslrootcert", "ssl="):
        assert token not in conn


def test_TB10b_el_pool_del_checkpointer_no_recibe_kwargs_tls():
    """Por AST, no por texto: sobrevive a un reformateo y muerde ante un `kwargs` nuevo.

    Y hace falta que muerda AQUÍ. `AsyncConnectionPool.__init__` guarda sus `kwargs` sin
    validarlos (psycopg_pool/base.py) — un parámetro mal puesto no se nota al construir el
    pool, sino en el primer checkout, ya en caliente. asyncpg, en cambio, falla al construir.
    Esa asimetría es la razón de fijar el conjunto de claves por análisis estático.
    """
    arbol = parse((_RAIZ / "app" / "agent" / "graph.py").read_text(encoding="utf-8"))
    llamadas = [
        n for n in walk(arbol)
        if n.__class__.__name__ == "Call"
        and getattr(n.func, "id", None) == "AsyncConnectionPool"
    ]
    assert len(llamadas) == 1, f"se esperaba UN AsyncConnectionPool, hay {len(llamadas)}"

    (kwargs_nodo,) = [k.value for k in llamadas[0].keywords if k.arg == "kwargs"]
    assert isinstance(kwargs_nodo, AstDict)
    claves = {literal_eval(k) for k in kwargs_nodo.keys}
    assert claves == {"autocommit", "prepare_threshold", "row_factory"}, (
        f"el pool del checkpointer recibe kwargs nuevos: {claves}"
    )

    # Y la conninfo se le pasa como `conninfo=`, no concatenada con parámetros TLS.
    conninfo = [k.value for k in llamadas[0].keywords if k.arg == "conninfo"]
    assert conninfo and conninfo[0].__class__.__name__ == "Name", (
        "la conninfo del pool dejó de ser una variable — revisar que nadie le concatene TLS"
    )


# ══ T-B11 ═════════════════════════════════════════════════════════════════════════════
def test_TB11_la_prohibicion_de_red_esta_realmente_activa():
    """Control positivo de la propia guarda. Sin esto, T-B11 sería la afirmación vacía
    "no hubo conexiones" sostenida por un mecanismo que nadie comprobó que funcione."""
    with pytest.raises(AssertionError, match="T-B11"):
        socket.create_connection(("192.0.2.1", 5432), timeout=0.01)
    with pytest.raises(AssertionError, match="T-B11"):
        socket.socket().connect(("192.0.2.1", 5432))
