"""
Contexto AI — Autenticación con Supabase Auth (JWT vía JWKS, ECC P-256 / ES256).

El frontend (supabase-js) entrega un access_token (JWT) firmado por Supabase con
llaves asimétricas. Aquí validamos ese token contra las llaves PÚBLICAS que Supabase
publica en su endpoint JWKS — sin manejar ningún secreto.

Provee:
  - get_current_user  → exige token válido; devuelve CurrentUser (con rol del perfil).
  - get_optional_user → si hay token lo valida; si no, devuelve None (modo invitado).
  - El perfil se auto-provisiona como 'cliente' la primera vez que se ve al usuario.
"""
import json
import logging
import time

import httpx
import jwt
from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

logger = logging.getLogger(__name__)

_ROLES_VALIDOS = {"cliente", "corredor", "inmobiliaria"}


class CurrentUser(BaseModel):
    user_id: str
    email: str | None = None
    rol: str = "cliente"
    nombre: str | None = None
    agency_id: str | None = None


# ── Caché de las llaves públicas (JWKS) ──────────────────────────────────────
_jwks_cache: dict = {"keys": None, "exp": 0.0}


def _jwks_url() -> str:
    return f"{settings.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"


def _ssl_verify() -> bool:
    return settings.ssl_verify.lower() != "false"


async def _get_jwks(force: bool = False) -> list[dict]:
    now = time.time()
    if not force and _jwks_cache["keys"] and now < _jwks_cache["exp"]:
        return _jwks_cache["keys"]
    async with httpx.AsyncClient(verify=_ssl_verify(), timeout=10.0) as c:
        resp = await c.get(_jwks_url())
        resp.raise_for_status()
        keys = resp.json().get("keys", [])
    _jwks_cache.update(keys=keys, exp=now + 3600)  # refresca cada hora
    return keys


def _key_for(token: str, keys: list[dict]):
    kid = jwt.get_unverified_header(token).get("kid")
    jwk = next((k for k in keys if k.get("kid") == kid), None)
    if jwk is None:
        return None
    return jwt.algorithms.ECAlgorithm.from_jwk(json.dumps(jwk))


async def _decode(token: str) -> dict:
    """Valida el JWT contra las llaves públicas. Reintenta si rotaron las llaves."""
    if not settings.supabase_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Autenticación no configurada (falta SUPABASE_URL).",
        )
    keys = await _get_jwks()
    key = _key_for(token, keys)
    if key is None:  # posible rotación → refrescar una vez
        keys = await _get_jwks(force=True)
        key = _key_for(token, keys)
    if key is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Llave del token no reconocida.")
    try:
        return jwt.decode(
            token,
            key,
            algorithms=["ES256"],
            audience="authenticated",
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token inválido o expirado.") from exc


async def _load_or_provision_profile(db: AsyncSession, user_id: str, email: str | None) -> dict:
    """Lee el perfil; si no existe, lo crea como 'cliente' (auto-provisión)."""
    row = (
        await db.execute(
            text("SELECT rol, nombre, agency_id::text AS agency_id FROM profiles WHERE user_id = :u"),
            {"u": user_id},
        )
    ).mappings().first()
    if row:
        return dict(row)
    await db.execute(
        text(
            "INSERT INTO profiles (user_id, rol, nombre) VALUES (:u, 'cliente', :n) "
            "ON CONFLICT (user_id) DO NOTHING"
        ),
        {"u": user_id, "n": (email or "").split("@")[0] or None},
    )
    return {"rol": "cliente", "nombre": (email or "").split("@")[0] or None, "agency_id": None}


def _extract_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer" and parts[1].strip():
        return parts[1].strip()
    return None


async def get_current_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Exige un JWT válido. Lanza 401 si falta o es inválido."""
    token = _extract_token(authorization)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Falta el token de autenticación.")
    claims = await _decode(token)
    user_id = claims["sub"]
    email = claims.get("email")
    prof = await _load_or_provision_profile(db, user_id, email)
    return CurrentUser(
        user_id=user_id, email=email,
        rol=prof.get("rol") or "cliente",
        nombre=prof.get("nombre"),
        agency_id=prof.get("agency_id"),
    )


async def get_optional_user(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> CurrentUser | None:
    """Como get_current_user pero NO falla si no hay token (modo invitado)."""
    if not _extract_token(authorization):
        return None
    try:
        return await get_current_user(authorization, db)
    except HTTPException:
        return None


def require_roles(*roles: str):
    """Dependencia que exige que el usuario tenga uno de los roles dados."""
    async def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.rol not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Tu rol no tiene permiso para esta acción.")
        return user
    return _dep
