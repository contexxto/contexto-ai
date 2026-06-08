"""
Brief Intake Multimodal — C0 (quick-win).  "Trae tu brief, recibe el match."

POST /api/v1/match
  Recibe un brief del comprador como TEXTO o IMAGEN y devuelve los inmuebles del
  catastro más parecidos (similitud semántica), cada uno con una línea de
  "por qué encaja" redactada por Claude.

Reutiliza el motor ya construido:
  - Texto  → Claude refina el brief a una frase → embedding → pgvector (ficha_texto)
  - Imagen → embedding multimodal → pgvector (imagen)   [el "Shazam inmobiliario"]

C0 es semántico puro. Los filtros duros (precio/zona) son C1 (ver diseño).
"""
import base64
import binascii
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.embeddings import EmbeddingError, embed_image_b64, embed_text, to_pgvector_literal
from app.limiter import limiter
from app.routers.chat import verify_api_key
from app.vision import ImageFetchError, _client, fetch_image_jpeg_b64

router = APIRouter(prefix="/api/v1/match", tags=["Match — Brief Intake (C0)"])


# ─────────────────────────── Schemas ───────────────────────────
class MatchRequest(BaseModel):
    input_text: str | None = Field(default=None, description="Brief en texto del comprador.")
    image_url: str | None = Field(default=None, description="URL de una foto de referencia.")
    image_base64: str | None = Field(default=None, description="Foto de referencia en base64 (JPEG/PNG).")
    top_k: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def _one_input(self) -> "MatchRequest":
        provided = [v for v in (self.input_text, self.image_url, self.image_base64) if v]
        if len(provided) != 1:
            raise ValueError("Provee EXACTAMENTE uno: input_text, image_url o image_base64.")
        return self

    model_config = {"json_schema_extra": {"example": {
        "input_text": "Busco un departamento tranquilo cerca de La Carolina, con áreas verdes, "
                       "buena caminabilidad y poco ruido. Estilo moderno, de pocos años.",
        "top_k": 5,
    }}}


class MatchItem(BaseModel):
    activo_id: str
    direccion: str
    tipo_activo: str
    imagen_url: str | None = None
    similitud: float
    por_que_encaja: str = ""


class MatchResponse(BaseModel):
    modo: str                  # "texto" | "imagen"
    consulta_interpretada: str  # frase refinada (texto) o nota (imagen)
    resultados: list[MatchItem]


# ─────────────────────────── Helpers ───────────────────────────
async def _refine_brief(texto: str) -> str:
    """Claude condensa el brief en una frase de búsqueda rica para embeber."""
    try:
        resp = await _client().messages.create(
            model=settings.llm_model,
            max_tokens=200,
            system=(
                "Eres un asistente inmobiliario en Quito. Resume el brief del usuario en UNA "
                "sola frase en español que capture los atributos DESEADOS del inmueble (tipo, "
                "ambiente, nivel de ruido, vegetación, estilo, antigüedad, ubicación). Devuelve "
                "solo la frase, sin preámbulos ni comillas."
            ),
            messages=[{"role": "user", "content": texto[:2000]}],
        )
        for b in resp.content:
            if getattr(b, "type", None) == "text" and b.text.strip():
                return b.text.strip()[:400]
    except Exception:  # noqa: BLE001
        pass
    return texto[:400]


async def _justificar(brief_desc: str, modo: str, resultados: list[dict]) -> dict[str, str]:
    """Una sola llamada a Claude: por qué cada inmueble encaja con el brief."""
    if not resultados:
        return {}
    compactos = [
        {
            "activo_id": r["activo_id"],
            "direccion": r["direccion"],
            "tipo": r["tipo_activo"],
            "walk_score": r.get("walk_score"),
            "ruido": r.get("score_ruido_predictivo"),
            "cobertura_vegetal": r.get("porcentaje_cobertura_vegetal"),
            "ficha": r.get("ficha_vision_raw"),
        }
        for r in resultados
    ]
    tool = {
        "name": "explicar_match",
        "description": "Explica brevemente por qué cada inmueble encaja con el brief del usuario.",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "activo_id": {"type": "string"},
                            "por_que_encaja": {"type": "string"},
                        },
                        "required": ["activo_id", "por_que_encaja"],
                    },
                }
            },
            "required": ["items"],
        },
    }
    contexto = (
        f"Brief del usuario ({modo}): {brief_desc}\n\n"
        f"Inmuebles candidatos (JSON):\n{json.dumps(compactos, ensure_ascii=False)}"
    )
    try:
        resp = await _client().messages.create(
            model=settings.llm_model,
            max_tokens=900,
            system=(
                "Eres un perito inmobiliario en Quito. Para CADA inmueble candidato, redacta UNA "
                "frase concreta (máx ~160 caracteres) de por qué encaja con el brief, citando datos "
                "reales del inmueble (ruido, vegetación, walk score, estructura, mantenimiento). No "
                "inventes datos que no estén en la ficha. Llama SIEMPRE a la herramienta explicar_match."
            ),
            tools=[tool],
            tool_choice={"type": "tool", "name": "explicar_match"},
            messages=[{"role": "user", "content": contexto}],
        )
        tool_input = next((b.input for b in resp.content if getattr(b, "type", None) == "tool_use"), None)
        if tool_input:
            return {it["activo_id"]: it.get("por_que_encaja", "") for it in tool_input.get("items", [])}
    except Exception:  # noqa: BLE001
        pass
    return {}


async def _similares(db: AsyncSession, kind: str, q_literal: str, top_k: int) -> list[dict]:
    rows = (
        await db.execute(
            text(
                "SELECT a.id::text AS activo_id, a.direccion_estandarizada AS direccion, "
                "       a.tipo_activo AS tipo_activo, a.walk_score, a.score_ruido_predictivo, "
                "       a.porcentaje_cobertura_vegetal, a.imagen_url, "
                "       f.ficha_vision_raw, "
                "       1 - (e.embedding <=> CAST(:q AS vector)) AS similitud "
                "FROM activo_embeddings e "
                "JOIN activos_inmutables a ON a.id = e.activo_id "
                "LEFT JOIN ficha_tecnica_mantenimiento f ON f.activo_id = a.id "
                "WHERE e.kind = :kind "
                "ORDER BY e.embedding <=> CAST(:q AS vector) "
                "LIMIT :k"
            ),
            {"q": q_literal, "kind": kind, "k": top_k},
        )
    ).mappings().all()
    return [dict(r) for r in rows]


# ─────────────────────────── Endpoint ───────────────────────────
@router.post(
    "",
    response_model=MatchResponse,
    summary="Encontrar inmuebles a partir de un brief (texto o foto)",
    description=(
        "C0 del Brief Intake. Texto → Claude refina → similitud semántica. "
        "Imagen → similitud visual ('Shazam inmobiliario'). Devuelve top-K con 'por qué encaja'."
    ),
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("20/minute")
async def match(request: Request, payload: MatchRequest, db: AsyncSession = Depends(get_db)) -> MatchResponse:
    # 1) Construir el vector de consulta + el 'kind' y la descripción del brief.
    if payload.input_text:
        modo = "texto"
        consulta = await _refine_brief(payload.input_text)
        try:
            qvec = await embed_text(consulta, input_type="query")
        except EmbeddingError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
        kind = "ficha_texto"
    else:
        modo = "imagen"
        consulta = "Foto de referencia aportada por el usuario."
        if payload.image_url:
            try:
                jpeg_b64 = await fetch_image_jpeg_b64(payload.image_url)
            except ImageFetchError as exc:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
        else:
            raw = payload.image_base64.split(",", 1)[-1]  # admite data URLs
            try:
                base64.b64decode(raw, validate=True)
            except (binascii.Error, ValueError):
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                    detail="image_base64 no es base64 válido.")
            jpeg_b64 = raw
        try:
            qvec = await embed_image_b64(jpeg_b64, input_type="query")
        except EmbeddingError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
        kind = "imagen"

    # 2) Buscar similares en pgvector.
    rows = await _similares(db, kind, to_pgvector_literal(qvec), payload.top_k)

    # 3) Justificación "por qué encaja" (no bloqueante: si falla, igual devolvemos resultados).
    justi = await _justificar(consulta, modo, rows)

    resultados = [
        MatchItem(
            activo_id=r["activo_id"],
            direccion=r["direccion"],
            tipo_activo=r["tipo_activo"],
            imagen_url=r.get("imagen_url"),
            similitud=round(float(r["similitud"]), 4),
            por_que_encaja=justi.get(r["activo_id"], ""),
        )
        for r in rows
    ]
    return MatchResponse(modo=modo, consulta_interpretada=consulta, resultados=resultados)
