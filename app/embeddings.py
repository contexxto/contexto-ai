"""
Contexto AI — Cliente de embeddings multimodales (Fase B3).

Usa la REST API de Voyage AI (voyage-multimodal-3) directamente vía httpx,
por dos razones:
  1. Control del verify SSL (mismo patrón que vision.py, por el firewall corporativo).
  2. Cero dependencias nuevas → build de Render más rápido y reproducible.

Imagen y texto caen en el MISMO espacio vectorial (1024 dims), así que un
embedding de foto y uno de ficha de texto son comparables por distancia coseno.

Regla de desacople (validada con Gemini): generar embeddings NUNCA debe bloquear
la ingesta de un activo. Si Voyage falla, el activo igual se crea; el embedding
queda pendiente. Por eso estas funciones lanzan EmbeddingError y el llamador decide.
"""
from typing import Literal

import httpx

from app.config import settings

_VOYAGE_URL = "https://api.voyageai.com/v1/multimodalembeddings"
_EMBED_DIM = 1024
_TIMEOUT = 30.0

InputType = Literal["document", "query"]


class EmbeddingError(Exception):
    """Falla al generar el embedding (red, auth, rate limit, respuesta inválida)."""


class EmbeddingDimError(EmbeddingError):
    """El vector devuelto no tiene la dimensión esperada (config rota)."""


def _verify() -> bool:
    return settings.ssl_verify.lower() != "false"


async def _post_multimodal(content: list[dict], input_type: InputType) -> list[float]:
    """Envía un único 'input' multimodal a Voyage y devuelve su vector de 1024 dims."""
    if not settings.voyage_api_key:
        raise EmbeddingError("VOYAGE_API_KEY no configurada en el entorno.")

    payload = {
        "inputs": [{"content": content}],
        "model": settings.voyage_model,
        "input_type": input_type,
    }
    headers = {
        "Authorization": f"Bearer {settings.voyage_api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(verify=_verify(), timeout=_TIMEOUT) as c:
            resp = await c.post(_VOYAGE_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        body = exc.response.text[:300] if exc.response is not None else ""
        raise EmbeddingError(f"Voyage respondió {exc.response.status_code}: {body}") from exc
    except Exception as exc:  # noqa: BLE001
        raise EmbeddingError(f"Voyage no disponible: {exc}") from exc

    try:
        vec = data["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError) as exc:
        raise EmbeddingError(f"Respuesta inesperada de Voyage: {data}") from exc

    if not isinstance(vec, list) or len(vec) != _EMBED_DIM:
        raise EmbeddingDimError(
            f"Dimensión {len(vec) if isinstance(vec, list) else '?'} != {_EMBED_DIM}. "
            "Revisa voyage_model en config."
        )
    return [float(x) for x in vec]


async def embed_text(text: str, input_type: InputType = "document") -> list[float]:
    """Embebe una frase (ficha serializada o consulta de búsqueda)."""
    text = (text or "").strip()
    if not text:
        raise EmbeddingError("Texto vacío: nada que embeber.")
    return await _post_multimodal([{"type": "text", "text": text}], input_type)


async def embed_image_b64(jpeg_b64: str, input_type: InputType = "document") -> list[float]:
    """Embebe una imagen JPEG ya codificada en base64."""
    data_url = f"data:image/jpeg;base64,{jpeg_b64}"
    return await _post_multimodal(
        [{"type": "image_base64", "image_base64": data_url}], input_type
    )


def to_pgvector_literal(vec: list[float]) -> str:
    """Convierte un vector Python al literal textual que pgvector castea con ::vector."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"
