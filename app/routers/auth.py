"""
Contexto AI — Endpoints de cuenta/rol sobre Supabase Auth.

  GET  /api/v1/auth/me        → datos del usuario autenticado (incluye rol).
  POST /api/v1/auth/profile   → fija rol + nombre; corredor se une a agencia con
                                invite_code; inmobiliaria crea su agencia paraguas.
  GET  /api/v1/auth/agency    → datos de la agencia del usuario (incluye invite_code
                                si es el dueño, para compartirlo con sus corredores).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import CurrentUser, get_current_user, invalidate_profile
from app.database import get_db
from app.limiter import limiter

router = APIRouter(prefix="/api/v1/auth", tags=["Auth — Cuenta y Roles"])

_ROLES = {"cliente", "corredor", "inmobiliaria"}


class ProfileUpdate(BaseModel):
    rol: str = Field(..., description="cliente | corredor | inmobiliaria")
    nombre: str | None = Field(default=None, max_length=120)
    invite_code: str | None = Field(default=None, description="Para corredor que se une a una inmobiliaria")
    agency_nombre: str | None = Field(default=None, description="Para inmobiliaria: nombre de la agencia a crear")


@router.get("/me", summary="Usuario autenticado (incluye rol)")
@limiter.limit("60/minute")
async def me(request: Request, user: CurrentUser = Depends(get_current_user)) -> dict:
    return user.model_dump()


@router.post("/profile", summary="Fijar rol y datos del perfil")
@limiter.limit("20/minute")
async def set_profile(
    request: Request,
    payload: ProfileUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rol = payload.rol.strip().lower()
    if rol not in _ROLES:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Rol inválido.")

    agency_id: str | None = None

    if rol == "inmobiliaria":
        # Crea (o reutiliza) la agencia paraguas que este usuario administra.
        existing = (
            await db.execute(
                text("SELECT id::text AS id FROM agencies WHERE owner_user = :u LIMIT 1"),
                {"u": user.user_id},
            )
        ).mappings().first()
        if existing:
            agency_id = existing["id"]
        else:
            nombre_ag = (payload.agency_nombre or payload.nombre or "Mi inmobiliaria").strip()
            new_id = str(uuid.uuid4())
            await db.execute(
                text("INSERT INTO agencies (id, nombre, owner_user) VALUES (:i, :n, :u)"),
                {"i": new_id, "n": nombre_ag, "u": user.user_id},
            )
            agency_id = new_id

    elif rol == "corredor" and payload.invite_code:
        code = payload.invite_code.strip().upper()
        ag = (
            await db.execute(
                text("SELECT id::text AS id FROM agencies WHERE invite_code = :c"),
                {"c": code},
            )
        ).mappings().first()
        if not ag:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Código de invitación no válido.")
        agency_id = ag["id"]

    await db.execute(
        text(
            "INSERT INTO profiles (user_id, rol, nombre, agency_id) "
            "VALUES (:u, :r, :n, :a) "
            "ON CONFLICT (user_id) DO UPDATE SET rol = :r, nombre = COALESCE(:n, profiles.nombre), "
            "agency_id = :a"
        ),
        {"u": user.user_id, "r": rol, "n": payload.nombre, "a": agency_id},
    )
    invalidate_profile(user.user_id)  # el rol/agencia cambió → refrescar caché

    return {"user_id": user.user_id, "rol": rol, "nombre": payload.nombre, "agency_id": agency_id}


@router.get("/agency", summary="Datos de la agencia del usuario")
@limiter.limit("60/minute")
async def my_agency(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Si es dueño de una agencia, devuelve también el invite_code para compartir.
    owned = (
        await db.execute(
            text("SELECT id::text AS id, nombre, invite_code FROM agencies WHERE owner_user = :u LIMIT 1"),
            {"u": user.user_id},
        )
    ).mappings().first()
    if owned:
        return {"es_dueño": True, **dict(owned)}

    if user.agency_id:
        ag = (
            await db.execute(
                text("SELECT id::text AS id, nombre FROM agencies WHERE id = :i"),
                {"i": user.agency_id},
            )
        ).mappings().first()
        if ag:
            return {"es_dueño": False, **dict(ag)}

    return {"es_dueño": False, "id": None, "nombre": None}
