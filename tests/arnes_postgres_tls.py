"""Un PostgreSQL EFÍMERO con TLS, para que T1/T2/T3 sean handshakes de verdad.

POR QUÉ ESTO NO PUEDE SER UN DOBLE. La propiedad que R2C1 introduce es criptográfica: que
una CA equivocada falle y que un hostname equivocado falle. Un mock que devuelva "sí
verifiqué" prueba que el mock devuelve eso. Sólo un servidor TLS real, presentando un
certificado real, obliga a OpenSSL —el de libpq— y al módulo `ssl` —el de asyncpg— a
recorrer el código que aquí se afirma. Por eso el arnés levanta Postgres de verdad.

QUÉ LEVANTA. Dos contenedores, cada uno con su certificado:

  * `ok`        — certificado emitido por la CA buena, SAN `DNS:localhost`.
  * `hostmalo`  — certificado emitido por la MISMA CA buena, SAN `DNS:otro-host.invalid`.

Con eso, los tres casos salen de combinar servidor y ancla, sin tocar `/etc/hosts`:

  T1  servidor `ok`        + ancla buena  → conecta
  T2  servidor `ok`        + ancla MALA   → falla por cadena
  T3  servidor `hostmalo`  + ancla buena  → falla por hostname

T2 y T3 son los controles negativos, y son los que dan sentido a T1: sin ellos, un verde en
T1 no distingue "verifica" de "no verifica nada y conecta igual", que es exactamente el
estado del que venimos.

LOS CERTIFICADOS VAN DENTRO DE LA IMAGEN, no bind-mounted. PostgreSQL se niega a arrancar si
la clave del servidor no es suya y no está en 0600, y un bind-mount trae el uid del runner.
Copiarlos en un `docker build` de tres líneas evita esa clase entera de problemas y se
comporta igual en Windows y en el runner de CI.

SE ROMPE, NO SE SALTA, EN CI. Un `skip` silencioso en CI convertiría T1/T2/T3 en decoración:
el gate seguiría verde sin haber verificado nada, que es el modo en que un control de
seguridad se apaga sin que nadie lo decida. Fuera de CI sí se salta, con el motivo escrito.
"""
from __future__ import annotations

import datetime as dt
import os
import shutil
import socket
import subprocess
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


def _hay_docker() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(
            ["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=60,
        ).returncode == 0
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
        "sin Docker: no se puede levantar el PostgreSQL TLS efímero. En CI esto sería un "
        "fallo, no un salto."
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


def escribir_pem_ca(destino: Path, cert) -> Path:
    from cryptography.hazmat.primitives import serialization
    destino.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return destino


def _escribir_par_servidor(carpeta: Path, k, cert) -> None:
    from cryptography.hazmat.primitives import serialization
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "server.crt").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (carpeta / "server.key").write_bytes(k.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))


# ── Contenedores ──────────────────────────────────────────────────────────────────────
def _puerto_libre() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _arrancar(etiqueta: str, carpeta: Path, puerto: int) -> None:
    (carpeta / "Dockerfile").write_text(
        "FROM postgres:15\n"
        "COPY server.crt /pgtls/server.crt\n"
        "COPY server.key /pgtls/server.key\n"
        "RUN chown postgres:postgres /pgtls/server.crt /pgtls/server.key"
        " && chmod 600 /pgtls/server.key\n",
        encoding="utf-8",
    )
    subprocess.run(["docker", "build", "-q", "-t", etiqueta, str(carpeta)],
                   check=True, stdout=subprocess.DEVNULL, timeout=600)
    subprocess.run(["docker", "rm", "-f", etiqueta],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([
        "docker", "run", "-d", "--name", etiqueta, "-p", f"127.0.0.1:{puerto}:5432",
        "-e", f"POSTGRES_PASSWORD={CLAVE}", "-e", f"POSTGRES_USER={USUARIO}",
        "-e", f"POSTGRES_DB={BASE}", etiqueta,
        "-c", "ssl=on",
        "-c", "ssl_cert_file=/pgtls/server.crt",
        "-c", "ssl_key_file=/pgtls/server.key",
    ], check=True, stdout=subprocess.DEVNULL, timeout=180)

    for _ in range(90):
        listo = subprocess.run(["docker", "exec", etiqueta, "pg_isready", "-U", USUARIO],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if listo.returncode == 0:
            return
        time.sleep(1)
    logs = subprocess.run(["docker", "logs", "--tail", "30", etiqueta],
                          capture_output=True, text=True)
    raise RuntimeError(f"el Postgres TLS '{etiqueta}' no llegó a estar listo:\n{logs.stderr}")


@dataclass
class ArnesTLS:
    puerto_ok: int
    puerto_host_malo: int
    ca_buena: Path
    ca_mala: Path


def levantar_arnes(tmp: Path) -> ArnesTLS:
    ca_k, ca_cert = crear_ca("CA de pruebas R2C1")
    _, cert_malo = crear_ca("CA de pruebas R2C1 - ANCLA EQUIVOCADA")

    arnes = ArnesTLS(
        puerto_ok=_puerto_libre(),
        puerto_host_malo=_puerto_libre(),
        ca_buena=escribir_pem_ca(tmp / "ca_buena.pem", ca_cert),
        ca_mala=escribir_pem_ca(tmp / "ca_mala.pem", cert_malo),
    )
    _escribir_par_servidor(tmp / "srv_ok", *_cert_de_servidor(ca_k, ca_cert, "localhost"))
    _escribir_par_servidor(tmp / "srv_malo",
                           *_cert_de_servidor(ca_k, ca_cert, HOST_DEL_CERT_MALO))
    _arrancar("r2c1-pgtls-ok", tmp / "srv_ok", arnes.puerto_ok)
    _arrancar("r2c1-pgtls-hostmalo", tmp / "srv_malo", arnes.puerto_host_malo)
    return arnes


def derribar_arnes() -> None:
    for etiqueta in ("r2c1-pgtls-ok", "r2c1-pgtls-hostmalo"):
        subprocess.run(["docker", "rm", "-f", etiqueta],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
