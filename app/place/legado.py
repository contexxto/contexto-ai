"""Los textos de contexto PERSISTIDOS frente a las superficies de mapa (MAP-SOURCE-BOUNDARY).

`activos_inmutables.servicios_cercanos` y `activos_inmutables.conectividad` son texto libre
que se escribió en su día con Google primero (Places op. B para los servicios; Routes para
los minutos de algunas conectividades) y OSM de respaldo. La columna NO guarda de dónde
salió cada texto, así que hoy ninguno tiene procedencia propia DEMOSTRADA.

Mientras sea así, esos textos no vuelven a una superficie que se pinta sobre MapLibre o
junto a él: el popup del Mapa Vivo, el badge del pin de MapSeed, los chips de la tarjeta
del chat y el anuncio que lleva el mini-mapa AURA. Tampoco se trata de adivinar: un nombre
que no aparece en `pois_vivos` NO se declara de Google por eso — simplemente no se sabe.

La salida es la unidad de datos PLACE-LEGACY-CONTEXT-BACKFILL: re-derivar los textos desde
la capa propia y guardar su procedencia. Cuando exista esa marca, quien lea la columna la
pasa en `procedencia` y el texto vuelve a mostrarse; hasta entonces, todas las llamadas
llegan sin ella y la respuesta es `None` (la clave se conserva: el contrato no cambia).
"""
from __future__ import annotations

PROCEDENCIA_PROPIA = "propio"


def texto_legado_para_mapa(texto: str | None, procedencia: str | None = None) -> str | None:
    """El texto persistido, SOLO si su procedencia propia está demostrada; si no, `None`."""
    if procedencia == PROCEDENCIA_PROPIA and texto:
        return texto
    return None
