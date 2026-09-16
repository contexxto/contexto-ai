"""Un PostgreSQL con TLS de verdad, para que T1/T2/T3 sean handshakes reales.

POR QUÉ ESTO NO PUEDE SER UN DOBLE. La propiedad que R2C1 introduce es criptográfica: que
una CA equivocada falle y que un hostname equivocado falle. Un mock que devuelva "sí
verifiqué" prueba que el mock devuelve eso. Sólo un servidor TLS real, presentando un
certificado real, obliga a OpenSSL —el de libpq— y al módulo `ssl` —el de asyncpg— a
recorrer el código que aquí se afirma.

QUÉ LEVANTA. Dos contenedores, cada uno con su certificado:

  * `ok`        — emitido por la CA buena, SAN `DNS:localhost`.
  * `hostmalo`  — emitido por la MISMA CA buena, SAN `DNS:otro-host.invalid`.

Los tres casos salen de combinar servidor y ancla, sin tocar `/etc/hosts`:

  T1  servidor `ok`        + ancla buena  → conecta
  T2  servidor `ok`        + ancla MALA   → falla por CADENA
  T3  servidor `hostmalo`  + ancla buena  → falla por HOSTNAME

T2 y T3 son los controles negativos y son los que dan sentido a T1: sin ellos, un verde en
T1 no distingue "verifica" de "no verifica nada y conecta igual", que es el estado del que
venimos.

LOS CERTIFICADOS VAN DENTRO DE LA IMAGEN, no bind-mounted. PostgreSQL se niega a arrancar si
la clave del servidor no es suya y no está en 0600, y un bind-mount trae el uid del runner.
Copiarlos en un `docker build` de tres líneas evita esa clase entera de problemas.

SE REUTILIZA, NO SE RECREA — y esto es una lección medida, no una optimización. Recrear los
contenedores en cada corrida (`docker rm -f` seguido de `docker run` con el mismo nombre)
producía fallos INTERMITENTES: `pg_isready` respondía dentro del contenedor mientras el
reenvío de puerto seguía rechazando desde el host (`WinError 10061`,
`Socket is not connected (10057)`). La liberación del puerto es asíncrona y la creación
siguiente pisaba a la anterior. Reintentar sólo lo empeoró: más ciclos, más carrera.

El síntoma era el peor posible — una prueba de TLS en rojo por algo que no tiene nada que
ver con TLS. Un arnés intermitente convierte un gate de seguridad en ruido, y un gate que
hace ruido acaba ignorado. Por eso los contenedores tienen nombre y puerto FIJOS y se
reutilizan mientras sirvan, y el material criptográfico vive junto a ellos para que
reutilizar sea coherente: si la CA se regenerara en cada corrida, dejaría de corresponder al
certificado del servidor reutilizado. En CI el runner es nuevo, así que se crean una vez.

SE ROMPE, NO SE SALTA, EN CI. Un `skip` silencioso en CI convertiría T1/T2/T3 en decoración:
el gate seguiría verde sin haber verificado nada. Fuera de CI sí se salta, con el motivo.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

_EPOCA = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
_FIN = dt.datetime(2036, 1, 1, tzinfo=dt.timezone.utc)

USUARIO = "arnes"
CLAVE = "arnes"
BASE = "arnes"
HOST_DEL_CERT_MALO = "otro-host.invalid"

# Nombres y puertos FIJOS: son la condición para poder reutilizar. Se evita el rango 55432+,
# que en la máquina del fundador cae en un intervalo TCP excluido por Windows.
_CONTENEDOR_OK = "r2c1-pgtls-ok"
_CONTENEDOR_HOSTMALO = "r2c1-pgtls-hostmalo"
_PUERTO_OK = 15433
_PUERTO_HOSTMALO = 15434

_TALLER = Path(tempfile.gettempdir()) / "r2c1-arnes-tls"

# SSLRequest de Postgres: longitud 8 + código 80877103.
_SSL_REQUEST = b"\x00\x00\x00\x08\x04\xd2\x16\x2f"


def _hay_docker() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=60).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def exigir_arnes_disponible() -> None:
    """En CI, la ausencia de Docker es un FALLO. Fuera de CI, un salto con motivo."""
    if _hay_docker():
        return
    if os.getenv("CI"):
        pytest.fail(
            "T1/T2/T3 exigen un PostgreSQL TLS real y Docker no responde en CI. "
            "NO se degradan a mocks: sin handshake real, 'verify-full' no está probado."
        )
    pytest.skip(
        "sin Docker: no se puede levantar el PostgreSQL TLS. En CI esto sería un fallo, "
        "no un salto."
    )


# ── Certificados ──────────────────────────────────────────────────────────────────────
def _clave_rsa():
    from cryptography.hazmat.primitives.asymmetric import rsa
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def crear_ca(nombre_comun: str):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509.oid import NameOID

    k = _clave_rsa()
    n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, nombre_comun)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(n).issuer_name(n).public_key(k.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_EPOCA).not_valid_after(_FIN)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(k, hashes.SHA256())
    )
    return k, cert


def _cert_de_servidor(ca_k, ca_cert, dns: str):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509.oid import NameOID

    k = _clave_rsa()
    cert = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, dns)]))
        .issuer_name(ca_cert.subject).public_key(k.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_EPOCA).not_valid_after(_FIN)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(dns)]), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(ca_k, hashes.SHA256())
    )
    return k, cert


def _escribir_ca(destino: Path, cert) -> None:
    from cryptography.hazmat.primitives import serialization
    destino.write_bytes(cert.public_bytes(serialization.Encoding.PEM))


def _escribir_par_servidor(carpeta: Path, k, cert) -> None:
    from cryptography.hazmat.primitives import serialization
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "server.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (carpeta / "server.key").write_bytes(k.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))


def _generar_material() -> None:
    """Emite CA buena, CA equivocada y los dos certificados de servidor. Idempotente: si ya
    existen se conservan, porque los contenedores reutilizados sirven ESOS certificados."""
    if (_TALLER / "ca_buena.pem").is_file() and (_TALLER / "ca_mala.pem").is_file():
        return
    _TALLER.mkdir(parents=True, exist_ok=True)
    ca_k, ca_cert = crear_ca("CA de pruebas R2C1")
    _, cert_malo = crear_ca("CA de pruebas R2C1 - ANCLA EQUIVOCADA")
    _escribir_ca(_TALLER / "ca_buena.pem", ca_cert)
    _escribir_ca(_TALLER / "ca_mala.pem", cert_malo)
    _escribir_par_servidor(_TALLER / "srv_ok", *_cert_de_servidor(ca_k, ca_cert, "localhost"))
    _escribir_par_servidor(_TALLER / "srv_malo",
                           *_cert_de_servidor(ca_k, ca_cert, HOST_DEL_CERT_MALO))


# ── Contenedores ──────────────────────────────────────────────────────────────────────
def _sirve(puerto: int, intentos: int = 1) -> bool:
    """¿Contesta un Postgres en ese puerto, visto DESDE EL HOST?

    Se manda un SSLRequest y se exige respuesta. Un `connect` a secas no bastaría: el proxy
    de Docker acepta el TCP antes de tener a quién reenviarlo — que es justo el fallo que
    esta comprobación existe para atrapar.
    """
    for intento in range(intentos):
        try:
            with socket.create_connection(("127.0.0.1", puerto), timeout=3) as s:
                s.sendall(_SSL_REQUEST)
                if s.recv(1) in (b"S", b"N"):
                    return True
        except OSError:
            pass
        if intento + 1 < intentos:
            time.sleep(1)
    return False


def _diagnostico(etiqueta: str) -> str:
    estado = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Status}} exit={{.State.ExitCode}}", etiqueta],
        capture_output=True, text=True)
    logs = subprocess.run(["docker", "logs", "--tail", "25", etiqueta],
                          capture_output=True, text=True)
    return (f"estado={(estado.stdout.strip() or estado.stderr.strip())!r} "
            f"logs={(logs.stdout + logs.stderr)[-500:]!r}")


def _crear(etiqueta: str, carpeta: Path, puerto: int) -> None:
    (carpeta / "Dockerfile").write_text(
        "FROM postgres:15\n"
        "COPY server.crt /pgtls/server.crt\n"
        "COPY server.key /pgtls/server.key\n"
        "RUN chown postgres:postgres /pgtls/server.crt /pgtls/server.key"
        " && chmod 600 /pgtls/server.key\n",
        encoding="utf-8",
    )
    subprocess.run(["docker", "build", "-q", "-t", etiqueta, str(carpeta)],
                   check=True, stdout=subprocess.DEVNULL, timeout=900)
    subprocess.run(["docker", "rm", "-f", etiqueta],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)                      # la liberación del puerto es asíncrona
    subprocess.run([
        "docker", "run", "-d", "--name", etiqueta, "-p", f"127.0.0.1:{puerto}:5432",
        "-e", f"POSTGRES_PASSWORD={CLAVE}", "-e", f"POSTGRES_USER={USUARIO}",
        "-e", f"POSTGRES_DB={BASE}", etiqueta,
        "-c", "ssl=on",
        "-c", "ssl_cert_file=/pgtls/server.crt",
        "-c", "ssl_key_file=/pgtls/server.key",
    ], check=True, stdout=subprocess.DEVNULL, timeout=300)

    if not _sirve(puerto, intentos=120):
        raise RuntimeError(
            f"el Postgres TLS {etiqueta!r} no llegó a servir en el puerto {puerto}. "
            f"NO es un fallo de TLS: es el arnés. {_diagnostico(etiqueta)}"
        )


def _esta_corriendo(etiqueta: str) -> bool:
    r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", etiqueta],
                       capture_output=True, text=True)
    return r.stdout.strip() == "true"


def _asegurar(etiqueta: str, carpeta: Path, puerto: int) -> None:
    """Reutiliza si ya sirve; crea sólo si de verdad no hay nada vivo.

    EL MATIZ QUE COSTÓ ENCONTRAR. Dar por muerto el contenedor tras UN intento fallido de
    conexión creaba un bucle que se alimentaba solo: un hipo del reenvío de puerto →
    "está muerto" → recrear → más churn → más hipos. Las corridas alternaban verde y rojo
    sin que nada del código bajo prueba cambiara.

    Así que si Docker dice que el contenedor está corriendo, se insiste antes de destruirlo.
    Sólo se recrea cuando no hay contenedor vivo, o cuando lo hay y aun así no responde tras
    varios segundos — que ya es un síntoma de que está roto de verdad.
    """
    if _esta_corriendo(etiqueta):
        if _sirve(puerto, intentos=20):
            return
    elif _sirve(puerto):                 # algo sirve ahí sin ser nuestro contenedor
        return
    _crear(etiqueta, carpeta, puerto)


@dataclass
class ArnesTLS:
    puerto_ok: int
    puerto_host_malo: int
    ca_buena: Path
    ca_mala: Path


def levantar_arnes(_tmp: Path | None = None) -> ArnesTLS:
    _generar_material()
    _asegurar(_CONTENEDOR_OK, _TALLER / "srv_ok", _PUERTO_OK)
    _asegurar(_CONTENEDOR_HOSTMALO, _TALLER / "srv_malo", _PUERTO_HOSTMALO)
    return ArnesTLS(
        puerto_ok=_PUERTO_OK,
        puerto_host_malo=_PUERTO_HOSTMALO,
        ca_buena=_TALLER / "ca_buena.pem",
        ca_mala=_TALLER / "ca_mala.pem",
    )


def derribar_arnes() -> None:
    """Sólo en CI, donde el runner muere igualmente y conviene no dejar nada colgando.

    En local se dejan vivos A PROPÓSITO: reutilizarlos es precisamente lo que quita la
    intermitencia, y recrearlos en cada corrida es lo que la producía. Para forzar material
    nuevo: `docker rm -f r2c1-pgtls-ok r2c1-pgtls-hostmalo` y borrar la carpeta
    `r2c1-arnes-tls` del temporal.
    """
    if not os.getenv("CI"):
        return
    for etiqueta in (_CONTENEDOR_OK, _CONTENEDOR_HOSTMALO):
        subprocess.run(["docker", "rm", "-f", etiqueta],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
