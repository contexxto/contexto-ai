"""
Genera el par de llaves VAPID para Web Push notifications.
Úsalo UNA vez y guarda las claves generadas en .env / Render / Vercel.

Uso:
    python scripts/gen_vapid.py
"""
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import (
    Encoding, PublicFormat, PrivateFormat, NoEncryption,
)
import base64

key = ec.generate_private_key(ec.SECP256R1())

# ── Private key ─────────────────────────────────────────────────────────────
# Se guarda como base64 del PEM para que quepa en una sola línea de env var.
private_pem = key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption())
private_b64 = base64.b64encode(private_pem).decode()  # single-line, no newline issues

# ── Public key ──────────────────────────────────────────────────────────────
# Punto no comprimido (0x04 || x || y) → base64url sin padding.
# Este es el applicationServerKey que el browser usa para suscribirse.
public_raw = key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
public_b64url = base64.urlsafe_b64encode(public_raw).rstrip(b"=").decode()

out = [
    "=" * 60,
    " VAPID Keys generadas - copia en Render y Vercel",
    "=" * 60,
    "",
    "# -- Render (Backend) ------------------------------------",
    f"VAPID_PRIVATE_KEY={private_b64}",
    f"VAPID_PUBLIC_KEY={public_b64url}",
    "",
    "# -- Vercel (Frontend build env) -------------------------",
    f"VITE_VAPID_PUBLIC_KEY={public_b64url}",
    "",
    "# -- .env local (backend) --------------------------------",
    f"VAPID_PRIVATE_KEY={private_b64}",
    f"VAPID_PUBLIC_KEY={public_b64url}",
    "",
    "IMPORTANTE: no vuelvas a correr este script -- las claves",
    "deben ser las mismas en backend y frontend (una sola vez).",
]
print("\n".join(out))
