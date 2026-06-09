"""
Router de Ingesta + Similitud (Fase B3 + B4).

POST /api/v1/assets/ingest        → orquesta: geocode + visión + persistencia + embeddings
POST /api/v1/assets/ingest/batch  → lote (máx 10) para poblar el catálogo
POST /api/v1/assets/similar       → búsqueda por similitud (uso interno)

Principios (validados con Gemini):
  - La visión SOLO llena campos observables; lo no visible queda NULL. Nunca se inventa.
  - confianza_global < 0.6 → estado_revision='pendiente_revision' (cola de revisión).
  - Generar embeddings NO bloquea la ingesta: si Voyage falla, el activo igual se crea.
"""
import hashlib
import json
import uuid
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, status
from geoalchemy2.elements import WKTElement
from pydantic import BaseModel, Field, HttpUrl, model_validator
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import tool_geocode_address
from app.config import settings
from app.database import get_db
from app.embeddings import (
    EmbeddingError,
    embed_image_b64,
    embed_text,
    embed_text_cached,
    to_pgvector_literal,
)
from app.limiter import limiter
from app.models import ActivoInmutable, FichaTecnicaMantenimiento
from app.routers.chat import verify_api_key
from app.vision import (
    ExtractionInvalidError,
    FichaVision,
    ImageFetchError,
    extract_ficha_from_b64,
    fetch_image_jpeg_b64,
    ficha_to_text,
)

router = APIRouter(prefix="/api/v1/assets", tags=["Ingesta visual + Similitud"])

_UMBRAL_CONFIANZA = 0.6
_VALID_TIPOS = {"Departamento", "Casa", "Local Comercial", "Oficina", "Quinta"}


# ─────────────────────────── Schemas ───────────────────────────
class IngestRequest(BaseModel):
    image_url: HttpUrl
    direccion: str = Field(..., min_length=5, max_length=255)
    piso_altura: int = Field(default=1, ge=1, le=200)

    model_config = {"json_schema_extra": {"example": {
        "image_url": "https://images.unsplash.com/photo-1568605114967-8130f3a36994?w=800",
        "direccion": "Av. de los Shyris y Naciones Unidas, La Carolina, Quito",
        "piso_altura": 1,
    }}}


class IngestResult(BaseModel):
    activo_id: uuid.UUID | None = None
    direccion_input: str
    direccion_resuelta: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    tipo_activo: str | None = None
    confianza_global: float | None = None
    estado_revision: str | None = None
    requiere_revision: bool | None = None
    embeddings: dict[str, bool] = Field(default_factory=dict)
    ficha: FichaVision | None = None
    cache_hit: bool = False  # True si la imagen ya existía (cero llamadas a IA)
    ok: bool = True
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None


class BatchIngestRequest(BaseModel):
    items: list[IngestRequest] = Field(..., min_length=1, max_length=10)


class BatchIngestResponse(BaseModel):
    procesados: int
    exitosos: int
    resultados: list[IngestResult]


class SimilarRequest(BaseModel):
    image_url: HttpUrl | None = None
    activo_id: uuid.UUID | None = None
    texto: str | None = None
    top_k: int = Field(default=5, ge=1, le=20)

    @model_validator(mode="after")
    def _exactly_one_input(self) -> "SimilarRequest":
        provided = [v for v in (self.image_url, self.activo_id, self.texto) if v]
        if len(provided) != 1:
            raise ValueError("Provee EXACTAMENTE uno de: image_url, activo_id, texto.")
        return self

    model_config = {"json_schema_extra": {"example": {
        "texto": "Casa de hormigón, dos pisos, acabados de alta calidad, fachada en buen estado",
        "top_k": 5,
    }}}


class SimilarItem(BaseModel):
    activo_id: uuid.UUID
    direccion: str
    tipo_activo: str
    similitud: float


class SimilarResponse(BaseModel):
    kind: str
    resultados: list[SimilarItem]


# ─────────────────────────── Helpers ───────────────────────────
def _validate_host(image_url: str) -> None:
    """Anti-SSRF: si hay allowlist configurada, el host debe estar en ella."""
    allow = [h.strip().lower() for h in settings.ingest_allowed_image_hosts.split(",") if h.strip()]
    if not allow:
        return  # modo pruebas: cualquier host
    host = (urlparse(image_url).hostname or "").lower()
    if host not in allow:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Host de imagen no permitido: {host!r}. Permitidos: {allow}",
        )


async def _geocode(direccion: str) -> dict:
    raw = await tool_geocode_address.ainvoke({"address": direccion})
    return json.loads(raw)


async def _generate_and_store_embeddings(
    db: AsyncSession,
    activo_id: uuid.UUID,
    jpeg_b64: str,
    ficha_texto: str,
    source_url: str,
) -> tuple[dict[str, bool], list[str]]:
    """
    Genera y guarda los embeddings (imagen + ficha_texto). NO bloqueante:
    cualquier fallo de Voyage se captura y se reporta como warning; el activo
    permanece intacto gracias a un SAVEPOINT (begin_nested).
    """
    status_map = {"imagen": False, "ficha_texto": False}
    warnings: list[str] = []

    targets = [
        ("imagen", lambda: embed_image_b64(jpeg_b64, input_type="document")),
        ("ficha_texto", lambda: embed_text(ficha_texto, input_type="document")),
    ]
    for kind, embed_fn in targets:
        try:
            vec = await embed_fn()
            async with db.begin_nested():  # SAVEPOINT: aísla el insert del embedding
                await db.execute(
                    text(
                        "INSERT INTO activo_embeddings "
                        "(activo_id, kind, embedding, source_url, model) "
                        "VALUES (:aid, :kind, CAST(:emb AS vector), :url, :model)"
                    ),
                    {
                        "aid": str(activo_id),
                        "kind": kind,
                        "emb": to_pgvector_literal(vec),
                        "url": source_url if kind == "imagen" else None,
                        "model": settings.voyage_model,
                    },
                )
            status_map[kind] = True
        except EmbeddingError as exc:
            warnings.append(f"Embedding '{kind}' pendiente (Voyage): {exc}")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Embedding '{kind}' falló al guardar: {exc}")

    return status_map, warnings


async def _ingest_one(db: AsyncSession, item: IngestRequest) -> IngestResult:
    """Orquesta la ingesta de un activo. No lanza: devuelve IngestResult(ok=False) en error."""
    result = IngestResult(direccion_input=item.direccion)
    url = str(item.image_url)

    # 1) Anti-SSRF
    try:
        _validate_host(url)
    except HTTPException as exc:
        result.ok = False
        result.error = exc.detail
        return result

    # 2) Descargar imagen UNA sola vez (reutilizada en visión y embedding)
    try:
        jpeg_b64 = await fetch_image_jpeg_b64(url)
    except ImageFetchError as exc:
        result.ok = False
        result.error = f"Imagen: {exc}"
        return result

    # 2b) CACHÉ POR HASH: si esta imagen ya fue procesada, reusamos el activo
    #     existente → CERO llamadas a Sonnet/Voyage (protección de presupuesto).
    img_hash = hashlib.sha256(jpeg_b64.encode("ascii")).hexdigest()
    existing = (
        await db.execute(
            select(ActivoInmutable).where(ActivoInmutable.image_sha256 == img_hash).limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        estado = (
            await db.execute(
                select(FichaTecnicaMantenimiento.estado_revision).where(
                    FichaTecnicaMantenimiento.activo_id == existing.id
                )
            )
        ).scalar_one_or_none()
        result.cache_hit = True
        result.activo_id = existing.id
        result.tipo_activo = existing.tipo_activo
        result.estado_revision = estado
        result.requiere_revision = estado == "pendiente_revision"
        result.warnings.append(
            "Imagen ya procesada previamente (cache hit). Se reutiliza el activo "
            "existente sin llamar a la IA."
        )
        return result

    # 3) Visión → ficha observable
    try:
        ficha = await extract_ficha_from_b64(jpeg_b64)
    except ExtractionInvalidError as exc:
        result.ok = False
        result.error = f"Visión: {exc}"
        return result
    result.ficha = ficha
    result.confianza_global = ficha.confianza_global

    # 4) Geocodificar (no inventamos coordenadas: si falla, no se crea el activo)
    geo = await _geocode(item.direccion)
    if not geo.get("found"):
        result.ok = False
        result.error = f"Dirección no geocodificable: {geo.get('message', 'sin detalle')}"
        return result
    lat, lon = float(geo["latitude"]), float(geo["longitude"])
    result.direccion_resuelta = geo.get("address_resolved")
    result.latitude, result.longitude = lat, lon

    # 5) Persistir activo + ficha
    tipo = ficha.tipo_activo if ficha.tipo_activo in _VALID_TIPOS else "Departamento"
    if ficha.tipo_activo not in _VALID_TIPOS:
        result.warnings.append(
            f"tipo_activo visual '{ficha.tipo_activo}' no es categoría válida → "
            "se guarda como 'Departamento' y se marca para revisión."
        )

    pendiente = (ficha.confianza_global < _UMBRAL_CONFIANZA) or (ficha.tipo_activo not in _VALID_TIPOS)
    estado = "pendiente_revision" if pendiente else "publicado"

    activo_id = uuid.uuid4()
    activo = ActivoInmutable(
        id=activo_id,
        geom=WKTElement(f"POINT({lon} {lat})", srid=4326),
        direccion_estandarizada=item.direccion,
        piso_altura=item.piso_altura,
        porcentaje_cobertura_vegetal=ficha.cobertura_vegetal_visible_pct,
        tipo_activo=tipo,
        image_sha256=img_hash,   # clave de caché para futuras re-subidas
        imagen_url=url,          # foto canónica (Supabase Storage)
    )
    db.add(activo)

    ficha_db = FichaTecnicaMantenimiento(
        id=uuid.uuid4(),
        activo_id=activo_id,
        # SOLO campos observables; el resto queda NULL (no se inventa):
        tipo_estructura=(
            None if ficha.tipo_estructura_aparente == "Indeterminado"
            else ficha.tipo_estructura_aparente
        ),
        calidad_acabados=(
            None if ficha.calidad_acabados_aparente == "Indeterminado"
            else ficha.calidad_acabados_aparente
        ),
        fuente="vision_ia",
        confianza_extraccion=ficha.confianza_global,
        estado_revision=estado,
        ficha_vision_raw=ficha.model_dump(),  # extracción IA completa para revisión/ground-truth
    )
    db.add(ficha_db)
    await db.flush()  # asegura que el activo existe antes de insertar embeddings (FK)

    result.activo_id = activo_id
    result.tipo_activo = tipo
    result.estado_revision = estado
    result.requiere_revision = pendiente

    # 6) Embeddings (no bloqueante)
    ficha_txt = ficha_to_text(ficha, item.direccion)
    emb_status, emb_warnings = await _generate_and_store_embeddings(
        db, activo_id, jpeg_b64, ficha_txt, url
    )
    result.embeddings = emb_status
    result.warnings.extend(emb_warnings)

    return result


# ─────────────────────────── Endpoints ───────────────────────────
@router.post(
    "/ingest",
    response_model=IngestResult,
    summary="Ingesta visual de un activo (geocode + visión + embeddings)",
    description=(
        "Descarga la foto, extrae la ficha observable con visión, geocodifica la "
        "dirección, crea el activo + ficha y genera embeddings (imagen y texto). "
        "Si la confianza < 0.6, el activo queda en 'pendiente_revision'."
    ),
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("20/minute")
async def ingest(
    request: Request, payload: IngestRequest, db: AsyncSession = Depends(get_db)
) -> IngestResult:
    result = await _ingest_one(db, payload)
    if not result.ok:
        # Imagen/visión/geocode: error de entrada del usuario → 422
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=result.error)
    return result


@router.post(
    "/ingest/batch",
    response_model=BatchIngestResponse,
    summary="Ingesta visual por lote (máx 10) para poblar el catálogo",
    description=(
        "Procesa una lista de inmuebles secuencialmente. Cada ítem reporta su propio "
        "estado: un fallo individual NO detiene el lote (ok=false + error en ese ítem)."
    ),
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("5/minute")
async def ingest_batch(
    request: Request, payload: BatchIngestRequest, db: AsyncSession = Depends(get_db)
) -> BatchIngestResponse:
    resultados: list[IngestResult] = []
    for item in payload.items:
        try:
            resultados.append(await _ingest_one(db, item))
        except Exception as exc:  # noqa: BLE001 — un ítem nunca tumba el lote
            resultados.append(
                IngestResult(direccion_input=item.direccion, ok=False, error=f"Inesperado: {exc}")
            )
    exitosos = sum(1 for r in resultados if r.ok)
    return BatchIngestResponse(
        procesados=len(resultados), exitosos=exitosos, resultados=resultados
    )


@router.post(
    "/similar",
    response_model=SimilarResponse,
    summary="Buscar activos similares por imagen, texto o activo existente",
    description=(
        "Embebe la consulta (foto/texto) o usa el vector de un activo existente y "
        "devuelve los más parecidos por distancia coseno. Uso interno: apoyar la "
        "categorización y detectar anomalías al ingresar activos nuevos."
    ),
    dependencies=[Depends(verify_api_key)],
)
@limiter.limit("30/minute")
async def similar(
    request: Request, payload: SimilarRequest, db: AsyncSession = Depends(get_db)
) -> SimilarResponse:
    self_id: str | None = None

    # Determinar el vector de consulta y el 'kind' contra el que se compara.
    if payload.texto:
        kind = "ficha_texto"
        try:
            qvec = await embed_text_cached(db, payload.texto, input_type="query")
        except EmbeddingError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
        q_literal = to_pgvector_literal(qvec)

    elif payload.image_url:
        kind = "imagen"
        try:
            jpeg_b64 = await fetch_image_jpeg_b64(str(payload.image_url))
        except ImageFetchError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
        try:
            qvec = await embed_image_b64(jpeg_b64, input_type="query")
        except EmbeddingError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
        q_literal = to_pgvector_literal(qvec)

    else:  # activo_id → usar su vector de imagen ya guardado
        kind = "imagen"
        self_id = str(payload.activo_id)
        row = (
            await db.execute(
                text(
                    "SELECT embedding::text AS emb FROM activo_embeddings "
                    "WHERE activo_id = CAST(:aid AS uuid) AND kind = :kind LIMIT 1"
                ),
                {"aid": self_id, "kind": kind},
            )
        ).mappings().first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"El activo {self_id} no tiene embedding de imagen. Ingéstalo primero.",
            )
        q_literal = row["emb"]

    # WHERE condicional: NUNCA pasamos un parámetro NULL ambiguo a asyncpg
    # (un :self_id NULL usado en CAST/IS NULL impide inferir su tipo → error).
    params: dict = {"q": q_literal, "kind": kind, "k": payload.top_k}
    self_filter = ""
    if self_id is not None:
        self_filter = "AND e.activo_id <> CAST(:self_id AS uuid) "
        params["self_id"] = self_id

    rows = (
        await db.execute(
            text(
                "SELECT a.id::text AS activo_id, a.direccion_estandarizada AS direccion, "
                "       a.tipo_activo AS tipo_activo, "
                "       1 - (e.embedding <=> CAST(:q AS vector)) AS similitud "
                "FROM activo_embeddings e "
                "JOIN activos_inmutables a ON a.id = e.activo_id "
                "WHERE e.kind = :kind " + self_filter +
                "ORDER BY e.embedding <=> CAST(:q AS vector) "
                "LIMIT :k"
            ),
            params,
        )
    ).mappings().all()

    return SimilarResponse(
        kind=kind,
        resultados=[
            SimilarItem(
                activo_id=uuid.UUID(r["activo_id"]),
                direccion=r["direccion"],
                tipo_activo=r["tipo_activo"],
                similitud=round(float(r["similitud"]), 4),
            )
            for r in rows
        ],
    )
