"""
Contexto AI — Extracción de ficha técnica por visión (Fase B2).

Recibe la URL de una foto de un inmueble y devuelve una ficha estructurada
con SOLO los campos observables. Usa Claude (visión) con tool_use forzado,
de modo que la salida es siempre un JSON validable con Pydantic.

Regla de oro: lo que no se puede ver, se devuelve "Indeterminado"/null.
NUNCA se inventa un dato.
"""
import base64
import io
from typing import Literal

import anthropic
import httpx
from PIL import Image
from pydantic import BaseModel, Field, ValidationError

from app.config import settings

# Claude recomienda lado máximo ~1568px; reescalamos para controlar tokens/costo.
_MAX_DIM = 1568
_FETCH_TIMEOUT = 15.0
_ALLOWED_CONTENT_PREFIXES = ("image/",)


# ── Errores específicos (alimentan la matriz de manejo de errores) ──
class VisionError(Exception):
    """Error base de extracción visual."""


class ImageFetchError(VisionError):
    """No se pudo descargar o decodificar la imagen."""


class ExtractionInvalidError(VisionError):
    """Claude devolvió una estructura que no valida contra el esquema."""


# ── Esquema de salida (campos OBSERVABLES únicamente) ──
Indet = "Indeterminado"


class FichaVision(BaseModel):
    """Esquema plano (sin anidación) para máxima compatibilidad con tool_use."""
    tipo_activo: Literal[
        "Casa", "Departamento", "Local Comercial", "Oficina", "Quinta", "Indeterminado"
    ] = Indet
    tipo_estructura_aparente: Literal[
        "Hormigon Armado", "Mamposteria", "Estructura Metalica", "Indeterminado"
    ] = Indet
    pisos_estimados: int | None = Field(default=None, ge=0, le=200)
    # Estado de fachada (aplanado):
    fachada_humedad_visible: bool | None = None
    fachada_grietas_visibles: bool | None = None
    fachada_estado_pintura: Literal["Bueno", "Regular", "Deteriorado", "Indeterminado"] = Indet
    fachada_nivel_riesgo: Literal["BAJO", "MEDIO", "ALTO", "Indeterminado"] = Indet
    calidad_acabados_aparente: Literal["Alta", "Media", "Basica", "Indeterminado"] = Indet
    cobertura_vegetal_visible_pct: float | None = Field(default=None, ge=0, le=100)
    # Campos añadidos por validación de negocio (Gemini) — críticos en Quito:
    estado_ventaneria: Literal["Buena", "Regular", "Deteriorada", "Indeterminado"] = Indet
    presencia_medidores: Literal["Ninguno", "Uno", "Varios", "Indeterminado"] = Indet
    observaciones: str = Field(default="", max_length=280)
    confianza_global: float = Field(ge=0.0, le=1.0)


# Esquema JSON para el tool_use de Anthropic (derivado del modelo Pydantic).
_VISION_TOOL = {
    "name": "registrar_ficha_visual",
    "description": "Registra la ficha técnica observable de un inmueble a partir de la foto.",
    "input_schema": FichaVision.model_json_schema(),
}

_SYSTEM_PROMPT = (
    "Eres un perito de inspeccion visual de inmuebles en Quito, Ecuador. "
    "Analiza UNICAMENTE lo que es visible en la foto. Esta PROHIBIDO inferir "
    "datos no observables (anio exacto, fechas de mantenimiento, montos). "
    "Si un campo no es determinable con la imagen, devuelve 'Indeterminado' o null "
    "— nunca adivines. Asigna confianza_global baja (< 0.5) si la foto esta borrosa, "
    "parcial, nocturna, o no muestra claramente el inmueble. Contexto local: en Quito "
    "predominan hormigon armado (moderno) y mamposteria (antiguo, Centro Historico). "
    "presencia_medidores: cuantos medidores de luz/agua se ven (indicio de unidades). "
    "estado_ventaneria: estado aparente de ventanas y marcos (clave por la radiacion UV "
    "y humedad de Quito). Llama SIEMPRE a la herramienta registrar_ficha_visual."
)


def _client() -> anthropic.AsyncAnthropic:
    verify = settings.ssl_verify.lower() != "false"
    return anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key,
        http_client=httpx.AsyncClient(verify=verify, timeout=60.0),
    )


async def _fetch_image_as_block(url: str) -> dict:
    """Descarga la imagen, la normaliza a JPEG <= _MAX_DIM y devuelve un bloque base64."""
    verify = settings.ssl_verify.lower() != "false"
    try:
        async with httpx.AsyncClient(verify=verify, timeout=_FETCH_TIMEOUT, follow_redirects=True) as c:
            resp = await c.get(url)
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise ImageFetchError(f"No se pudo descargar la imagen: {exc}") from exc

    ctype = resp.headers.get("content-type", "")
    if not ctype.startswith(_ALLOWED_CONTENT_PREFIXES):
        raise ImageFetchError(f"El recurso no es una imagen (content-type={ctype!r}).")

    try:
        img = Image.open(io.BytesIO(resp.content))
        img = img.convert("RGB")
        if max(img.size) > _MAX_DIM:
            img.thumbnail((_MAX_DIM, _MAX_DIM))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        data = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    except Exception as exc:  # noqa: BLE001
        raise ImageFetchError(f"Imagen corrupta o no decodificable: {exc}") from exc

    return {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": data},
    }


async def extract_ficha_from_image(image_url: str) -> FichaVision:
    """
    Extrae la ficha observable de una foto. Lanza:
      - ImageFetchError si la imagen no se puede obtener/decodificar.
      - ExtractionInvalidError si Claude no devuelve una estructura válida.
    El llamador decide qué hacer con confianza_global baja (cola de revisión).
    """
    image_block = await _fetch_image_as_block(image_url)

    resp = await _client().messages.create(
        model=settings.llm_model,
        max_tokens=1024,
        system=_SYSTEM_PROMPT,
        tools=[_VISION_TOOL],
        tool_choice={"type": "tool", "name": "registrar_ficha_visual"},
        messages=[{
            "role": "user",
            "content": [
                image_block,
                {"type": "text", "text": "Analiza este inmueble y registra su ficha visual observable."},
            ],
        }],
    )

    tool_input = next(
        (b.input for b in resp.content if getattr(b, "type", None) == "tool_use"),
        None,
    )
    if tool_input is None:
        raise ExtractionInvalidError("Claude no devolvió una llamada a la herramienta.")

    try:
        return FichaVision.model_validate(tool_input)
    except ValidationError as exc:
        raise ExtractionInvalidError(f"Estructura inválida: {exc}") from exc
