"""Plan 1.1 · TR-2 — enlace de baja firmado para el aviso de reenganche al comprador.

El canon exige que la revocación sea accesible «en cada mensaje». Un correo o un push no pueden
llevar el `resume_secret` (regla noLeak: capacidades fuera de la URL), y el correo se abre a
menudo en otro aparato que no tiene esa capacidad. Por eso existe esta capacidad aparte.

QUÉ ES: una capacidad UNILATERAL DE REDUCCIÓN. Quien tiene el token puede, sobre UNA sesión,
    · REVOCAR el permiso de aviso (consent_reenganche_at = NULL), o
    · CERRAR el seguimiento de ese inmueble (reenganche_cerrado_en = now()).
Y nada más: no concede, no lee la sesión ni el contacto, no cambia email ni push ni activo.

QUÉ NO ES: el sistema de autoridad nuevo. `ConsentGrantV0`, `purpose` de grant, `revoked_at`,
provenance… son TR-5. Este token no se guarda en ninguna parte ni tiene estado.

Formato (versionado):

    v1.<session_id en base64url>.<HMAC-SHA256 en base64url>

firmado sobre `REENGAGEMENT_UNSUBSCRIBE|v1|<session_id>`. El propósito va DENTRO del mensaje
firmado: un token del mismo secreto emitido para otro propósito no valida aquí. El token no
lleva email, teléfono ni push; el session_id es un identificador, no una autoridad
(ver app/sesion_autoridad.py).

SECRETO: `REENGANCHE_BAJA_SECRET`, dedicado a esto y a nada más (mínimo 32 caracteres). No se
reutiliza el de otro dominio. Sin él —o si es demasiado corto— no se puede emitir el enlace, y
el cron NO escribe al comprador (fail-closed: un aviso sin vía de baja no sale). Generar con:

    python -c "import secrets; print(secrets.token_urlsafe(48))"

NADA DE ESTE MÓDULO REGISTRA EL SECRETO NI EL TOKEN.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os

PROPOSITO = "REENGAGEMENT_UNSUBSCRIBE"
VERSION = "v1"
_ENV_SECRETO = "REENGANCHE_BAJA_SECRET"
_MIN_SECRETO = 32
_MAX_TOKEN = 400


class SinSecretoDeBaja(RuntimeError):
    """No hay un secreto de baja utilizable: no se puede emitir el enlace."""


def _secreto() -> bytes | None:
    s = (os.getenv(_ENV_SECRETO) or "").strip()
    if len(s) < _MIN_SECRETO:
        return None
    return s.encode("utf-8")


def disponible() -> bool:
    """¿Se puede emitir un enlace de baja válido ahora mismo?"""
    return _secreto() is not None


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _de_b64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _firma(secreto: bytes, proposito: str, version: str, session_id: str) -> bytes:
    msg = f"{proposito}|{version}|{session_id}".encode("utf-8")
    return hmac.new(secreto, msg, hashlib.sha256).digest()


def emitir(session_id: str, *, _proposito: str = PROPOSITO) -> str:
    """Token de baja para `session_id`. Lanza SinSecretoDeBaja si no hay secreto.

    `_proposito` existe solo para que los tests fabriquen un token de OTRO propósito y
    comprueben que aquí no valida; producción nunca lo pasa."""
    secreto = _secreto()
    if secreto is None:
        raise SinSecretoDeBaja(f"{_ENV_SECRETO} ausente o demasiado corto")
    if not session_id:
        raise ValueError("session_id vacío")
    firma = _firma(secreto, _proposito, VERSION, session_id)
    return f"{VERSION}.{_b64(session_id.encode('utf-8'))}.{_b64(firma)}"


def verificar(token: str | None) -> str | None:
    """Devuelve el session_id si el token es auténtico, de este propósito y de esta versión;
    si no, None. No toca la base ni revela por qué falló."""
    secreto = _secreto()
    if secreto is None or not token or len(token) > _MAX_TOKEN:
        return None
    partes = token.split(".")
    if len(partes) != 3 or partes[0] != VERSION:
        return None
    try:
        session_id = _de_b64(partes[1]).decode("utf-8")
        firma = _de_b64(partes[2])
    except Exception:  # noqa: BLE001 — base64 o utf-8 inválidos: token alterado
        return None
    if not session_id:
        return None
    esperada = _firma(secreto, PROPOSITO, VERSION, session_id)
    if not hmac.compare_digest(esperada, firma):
        return None
    return session_id


def ruta_de_baja(session_id: str) -> str:
    """Ruta relativa de la app que abre la CONFIRMACIÓN de baja (el GET no muta: la
    pantalla hace el POST). Lanza SinSecretoDeBaja si no hay secreto."""
    return f"/?baja={emitir(session_id)}"
