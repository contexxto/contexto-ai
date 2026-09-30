"""La frontera de los textos de contexto PERSISTIDOS (MAP-SOURCE-BOUNDARY).

`activos_inmutables.servicios_cercanos` y `activos_inmutables.conectividad` son texto libre
que se escribió en su día con Google primero (Places op. B para los servicios; Routes para
los minutos de algunas conectividades) y OSM de respaldo. La columna NO guarda de dónde
salió cada texto, así que hoy ninguno tiene procedencia propia DEMOSTRADA.

Mientras sea así, esos textos no son fuente vigente de NADA:
  · no se pintan sobre MapLibre ni junto a él (popup del Mapa Vivo, badge de MapSeed, chips,
    anuncio con el mini-mapa AURA);
  · no alimentan `parque_min` / `transporte_min` ni, por tanto, el encaje y el orden;
  · no llegan al agente como contexto del inmueble, ni sirven para encontrarlo por texto;
  · no reaparecen por otro consumidor: todo lector de la columna pasa por aquí.

Ausencia de procedencia = UNKNOWN (`None`). No es cero, ni falso, ni «no existe». Y no se
adivina: un nombre que no aparece en `pois_vivos` NO se declara de Google por eso.

LA FRONTERA SE APLICA EN LA LECTURA, antes de cualquier otra cosa (en particular, antes de
la curación del corredor). Así lo que el corredor confirmó —que es dato propio— sobrevive, y
nada de lo que viene después tiene que volver a preguntar.

La salida es la unidad de datos PLACE-LEGACY-CONTEXT-BACKFILL: re-derivar los textos desde la
capa propia y guardar su procedencia en `contexto_procedencia`. Cuando exista esa columna, los
lectores la seleccionan y la fila vuelve a entrar sola, por esta misma puerta.
"""
from __future__ import annotations

from collections.abc import Mapping

PROCEDENCIA_PROPIA = "propio"
COLUMNA_PROCEDENCIA = "contexto_procedencia"  # la crea PLACE-LEGACY-CONTEXT-BACKFILL (040)
CAMPOS_LEGADOS = ("servicios_cercanos", "conectividad")


def contexto_legado_vigente(texto: str | None, procedencia: str | None = None) -> str | None:
    """El texto persistido, SOLO si su procedencia propia está demostrada; si no, `None`."""
    if procedencia == PROCEDENCIA_PROPIA and texto:
        return texto
    return None


def con_contexto_vigente(fila: Mapping) -> dict:
    """Copia de la fila con los dos textos pasados por la frontera. El resto, intacto.

    La procedencia se lee DE LA FILA (`contexto_procedencia`): hoy ningún SELECT la trae, así
    que todo queda en `None`; el día que el backfill la escriba y los SELECT la incluyan, las
    filas con procedencia propia vuelven a entrar sin tocar a ningún consumidor.
    """
    out = dict(fila)
    procedencia = out.get(COLUMNA_PROCEDENCIA)
    for campo in CAMPOS_LEGADOS:
        if campo in out:
            out[campo] = contexto_legado_vigente(out[campo], procedencia)
    return out
