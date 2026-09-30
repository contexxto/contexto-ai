"""La evidencia PERSISTIBLE del entorno de un inmueble (PLACE-PROVENANCE-041).

TRES PIEZAS, en el orden en que viaja el dato:

    MateriaDeZona + PlaceContextV0
        └─ documentos_persistibles()  →  NearbyPlacesEvidenceV0 / NearestTransitEvidenceV0
               └─ formatear_*()       →  la prosa histórica (`servicios_cercanos`, `conectividad`)
    fila de activos_inmutables
        └─ leer_contexto_persistido() →  estructurada | legado_no_verificado | ausente

LA DIRECCIÓN ES LA DEL CANON (Plan 1.1 §E4.1): la evidencia estructurada es la fuente y la prosa
se DERIVA de ella. Nada aquí convierte texto en evidencia: `parse_servicios` sigue existiendo
para compatibilidad, pero ni otorga procedencia ni es el origen de ninguna `EvidenceRefV0`.

LO QUE ESTE MÓDULO NO HACE, a propósito:
  · no consulta la base (salvo `esquema_041_presente`, que solo mira el catálogo);
  · no escribe: el UPDATE vive en el escritor (`app/routers/assets.py::_recompute_walk_score`);
  · no abre ningún consumidor. La frontera de lectura del producto sigue siendo
    `app/place/legado.py::con_contexto_vigente`, que con la 041 sigue cerrada. Reabrir pasa por
    `leer_contexto_persistido` en una unidad posterior, detrás de la compuerta
    CURATION-CONSISTENCY (la curación del corredor todavía solo se aplica en 4 de 10 lectores).
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import ValidationError

from app.contracts.evidence_v0 import EvidenceRefV0, PersistencePolicy, SourceType
from app.contracts.place_evidence_v0 import (
    DistanceMethod,
    DurationMethod,
    NearbyPlacesEvidenceV0,
    NearestTransitEvidenceV0,
    ServiceItemEvidenceV0,
    TransitItemEvidenceV0,
    ValueClass,
    WalkDurationV0,
)
from app.contracts.place_v0 import (
    GeoPoint,
    MeasureStatus,
    NearbyPlaceV0,
    NearestTransitV0,
    PlaceContextV0,
)
from app.place.assembler import MateriaDeZona, _nombre_limpio

log = logging.getLogger("foso")

# El mismo `provider` que ya usa el ensamblador para la capa propia (`assembler.py`). Nombra la
# TUBERÍA que calcula; los datasets de los que salen los lugares van en su propia evidencia.
PROVEEDOR_CAPA = "contexto-capa-propia"
PROVEEDOR_CORREDOR = "contexto-corredor"
DATASETS_ABIERTOS = frozenset({"overture", "osm"})

# Los radios EXACTOS de la derivación (`app/place/providers/propia.py`). Se repiten aquí como
# dato del documento: quien lea la evidencia dentro de un año tiene que saber qué se buscó.
RADIO_SERVICIOS_M = 1500
RADIO_TRANSPORTE_M = 3000
PASO_PEATONAL_M_POR_MIN = 80

COLUMNAS_041 = ("servicios_evidencia", "conectividad_evidencia")

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "contexto.ai/place/persisted-evidence/v0")


# ══ 1 · CONSTRUCCIÓN: materia + contexto → documentos ═════════════════════════════
def _instante(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(v)
    except ValueError:
        return None
    return d if d.tzinfo is not None else None  # un instante sin zona no se usa: no se adivina


def _id(materia: MateriaDeZona, *partes: object) -> str:
    """`uuid5` determinista: el mismo material produce el mismo documento, byte a byte. Es lo
    que permitirá al backfill saber que no tiene nada que escribir (idempotencia)."""
    semilla = "\x1f".join((repr(materia.lat), repr(materia.lon), materia.recuperado_en.isoformat(),
                           *(str(p) for p in partes)))
    return str(uuid.uuid5(_NAMESPACE, semilla))


def _metodo_distancia(materia: MateriaDeZona, dimension: str, radio_m: int) -> EvidenceRefV0:
    return EvidenceRefV0(
        evidence_id=_id(materia, dimension, "method"),
        source_type=SourceType.OWN_MEASUREMENT,
        provider=PROVEEDOR_CAPA,
        observed_at=None,
        retrieved_at=materia.recuperado_en,
        methodology=(f"el más cercano en la capa propia de POIs dentro de {radio_m} m, con la "
                     "distancia geodésica en línea recta calculada en PostGIS desde el inmueble"),
        persistence_policy=PersistencePolicy.PERSISTABLE,
        limitations=("la distancia es en línea recta, no por calles",),
    )


def _procedencia(materia: MateriaDeZona, dimension: str, s: dict, metodo: EvidenceRefV0
                 ) -> tuple[dict, list[EvidenceRefV0]] | None:
    """SOURCE + METHOD + VERIFICATION de un elemento, o `None` si su procedencia está incompleta.

    Incompleta significa: no es de la capa propia, le falta la identidad en la capa, el dataset
    no es uno abierto conocido, o no se sabe cuándo lo ingirió la capa. En cualquiera de esos
    casos NO se rellena nada: el elemento no se persiste.
    """
    if s.get("fuente") != "propio" or s.get("poi_id") is None:
        return None
    dataset = s.get("dataset")
    ingerido = _instante(s.get("capa_actualizado_en"))
    if dataset not in DATASETS_ABIERTOS or ingerido is None or ingerido > materia.recuperado_en:
        return None
    poi = str(s["poi_id"])
    fuente = EvidenceRefV0(
        evidence_id=_id(materia, dimension, "source", poi),
        source_type=SourceType.PUBLIC_DATASET,
        provider=dataset,
        source_id=s.get("dataset_id") or None,
        observed_at=None,
        retrieved_at=ingerido,
        methodology=("registro del dataset abierto, ingerido por el refresco semanal de la capa "
                     "propia de POIs"),
        persistence_policy=PersistencePolicy.PERSISTABLE,
        limitations=("el dataset no declara cuándo se observó el lugar",),
    )
    evidencias = [fuente]
    verificaciones: list[str] = []
    visto = _instante(s.get("verificado_en_ts"))
    # Solo un «confirmado» es verificación. `cerrado` ya lo quitó la vista `pois_vivos`, y un
    # nombre añadido a mano (`agregado`, sin `poi_id`) no es la verificación de ESTE lugar.
    if s.get("verificacion_accion") == "confirmado" and visto is not None \
            and visto <= materia.recuperado_en:
        v = EvidenceRefV0(
            evidence_id=_id(materia, dimension, "verification", poi),
            source_type=SourceType.OPERATOR_DECLARED,
            provider=PROVEEDOR_CORREDOR,
            observed_at=visto,
            retrieved_at=materia.recuperado_en,
            methodology="un corredor confirmó en terreno que el lugar existe y está operando",
            persistence_policy=PersistencePolicy.PERSISTABLE,
            limitations=("declarado por un corredor, con interés comercial en el resultado",),
        )
        evidencias.append(v)
        verificaciones.append(v.evidence_id)
    enlaces = {"source_evidence_id": fuente.evidence_id, "method_evidence_id": metodo.evidence_id,
               "verification_evidence_ids": tuple(verificaciones)}
    return enlaces, evidencias


def evidencia_servicios(materia: MateriaDeZona, contexto: PlaceContextV0
                        ) -> NearbyPlacesEvidenceV0 | None:
    """`None` = UNKNOWN (la columna queda en NULL). Nunca se fabrica un documento de ausencia."""
    medida = contexto.nearby_places
    if medida is None or medida.status is MeasureStatus.UNKNOWN:
        return None
    metodo = _metodo_distancia(materia, "nearby_places", RADIO_SERVICIOS_M)
    base = dict(derived_at=materia.recuperado_en, origin=GeoPoint(lat=materia.lat, lon=materia.lon),
                radius_m=RADIO_SERVICIOS_M, distance_method=DistanceMethod.STRAIGHT_LINE_GEODESIC,
                distance_class=ValueClass.DERIVED)
    if medida.status is MeasureStatus.INSUFFICIENT_EVIDENCE:
        return NearbyPlacesEvidenceV0(
            status=MeasureStatus.INSUFFICIENT_EVIDENCE, evidence=(metodo,),
            limitations=(*medida.limitations,
                         "sin nada en el radio de NUESTRA capa: un hueco de capa no es ausencia real"),
            **base)

    items: list[ServiceItemEvidenceV0] = []
    evidencias: list[EvidenceRefV0] = [metodo]
    incompletos = 0
    for s in materia.servicios:
        if s.get("cat") == "transporte":
            continue
        proc = _procedencia(materia, "nearby_places", s, metodo)
        if proc is None or s.get("distancia_m") is None or not s.get("cat"):
            incompletos += 1
            continue
        enlaces, evs = proc
        items.append(ServiceItemEvidenceV0(
            place=NearbyPlaceV0(category=s["cat"], distance_m=float(s["distancia_m"]),
                                name=_nombre_limpio(s.get("nombre")), poi_id=str(s["poi_id"])),
            **enlaces))
        evidencias.extend(evs)
    if not items:
        # El contexto dice que había servicios, pero ninguno tiene procedencia completa: no hay
        # nada que se pueda AFIRMAR con evidencia. Eso es UNKNOWN, no «no hay servicios».
        return None
    return NearbyPlacesEvidenceV0(
        status=MeasureStatus.AVAILABLE, items=tuple(items), evidence=tuple(evidencias),
        limitations=() if not incompletos else (
            f"{incompletos} servicio(s) sin procedencia completa no se persistieron",),
        **base)


def evidencia_conectividad(materia: MateriaDeZona, contexto: PlaceContextV0
                           ) -> NearestTransitEvidenceV0 | None:
    """Independiente de los servicios: si esto falla, los servicios no se inventan, ni al revés."""
    medida = contexto.nearest_transit
    if medida is None or medida.status is MeasureStatus.UNKNOWN:
        return None
    metodo = _metodo_distancia(materia, "nearest_transit", RADIO_TRANSPORTE_M)
    base = dict(derived_at=materia.recuperado_en, origin=GeoPoint(lat=materia.lat, lon=materia.lon),
                radius_m=RADIO_TRANSPORTE_M, distance_method=DistanceMethod.STRAIGHT_LINE_GEODESIC,
                distance_class=ValueClass.DERIVED)
    if medida.status is MeasureStatus.INSUFFICIENT_EVIDENCE:
        return NearestTransitEvidenceV0(
            status=MeasureStatus.INSUFFICIENT_EVIDENCE, evidence=(metodo,),
            limitations=(*medida.limitations,
                         "sin parada en el radio de NUESTRA capa: un hueco de capa no es ausencia real"),
            **base)

    t = materia.transporte or {}
    proc = _procedencia(materia, "nearest_transit", t, metodo)
    if proc is None or materia.transporte_distancia_m is None:
        return None
    enlaces, evidencias = proc
    stop = TransitItemEvidenceV0(
        stop=NearestTransitV0(distance_m=float(materia.transporte_distancia_m),
                              mode="masivo" if t.get("es_masivo") else "parada",
                              name=_nombre_limpio(t.get("nombre")), stop_id=str(t["poi_id"])),
        **enlaces)
    todas = [metodo, *evidencias]
    duracion = None
    limitaciones: list[str] = []
    if materia.transporte_minutos is not None:
        if materia.transporte_ruta_medida:
            # Hoy nadie lo produce: la única ruta medida que existió fue de Google Routes, que no
            # se persiste. Si vuelve (Valhalla), entra con su propia evidencia, no por aquí.
            limitaciones.append("hubo duración por ruta pero su proveedor no es persistible: no se guardó")
        else:
            heur = EvidenceRefV0(
                evidence_id=_id(materia, "nearest_transit", "walk_duration"),
                source_type=SourceType.HEURISTIC_ESTIMATE,
                provider=PROVEEDOR_CAPA,
                observed_at=None,
                retrieved_at=materia.recuperado_en,
                methodology=(f"distancia en línea recta dividida entre "
                             f"{PASO_PEATONAL_M_POR_MIN} m/min"),
                persistence_policy=PersistencePolicy.PERSISTABLE,
                limitations=("estimación en línea recta: ignora manzanas, desniveles y cruces, y en "
                             "Quito subestima de forma sistemática",),
            )
            todas.append(heur)
            duracion = WalkDurationV0(minutes=float(materia.transporte_minutos),
                                      value_class=ValueClass.ESTIMATED,
                                      method=DurationMethod.STRAIGHT_LINE_AT_FIXED_PACE,
                                      evidence_id=heur.evidence_id)
    return NearestTransitEvidenceV0(
        status=MeasureStatus.AVAILABLE, stop=stop, walk_duration=duracion,
        evidence=tuple(todas), limitations=tuple(limitaciones), **base)


def documentos_persistibles(materia: MateriaDeZona, contexto: PlaceContextV0) -> dict:
    """Las dos dimensiones, cada una por su lado. Si construir una falla, esa queda en `None`
    (UNKNOWN) y la otra sigue: un fallo de una dimensión no borra ni inventa la otra."""
    out = {}
    for clave, fn in (("servicios", evidencia_servicios), ("conectividad", evidencia_conectividad)):
        try:
            out[clave] = fn(materia, contexto)
        except (ValidationError, ValueError, KeyError, TypeError) as exc:
            log.warning("foso=evidencia_no_construida dimension=%s causa=%s: %s",
                        clave, type(exc).__name__, str(exc)[:300])
            out[clave] = None
    return out


# ══ 2 · FORMATTER: documento → prosa histórica ════════════════════════════════════
def _nombre_para_prosa(n: str | None) -> str:
    """El separador de la prosa es «·»: un nombre que lo contuviera partiría el segmento."""
    return (n or "este lugar").replace("·", "-").strip()


def formatear_servicios(doc: NearbyPlacesEvidenceV0 | None) -> str | None:
    """«🌳 Parque X a ~254 m · 💊 Farmacia Y a ~120 m», ordenado por distancia.

    Es el formato que ya entienden los lectores (`parse_servicios`, los chips y `parque_min`):
    separador «·» y «a ~N m» AL FINAL del segmento, con la distancia en metros ENTEROS y sin
    separador de miles («1200», nunca «1.200», que el parser leería como 1 m).
    """
    if doc is None or doc.status is not MeasureStatus.AVAILABLE:
        return None
    from app.rutas import _CAT_EMOJI  # lazy: `rutas` carga la base; este módulo no la necesita
    items = sorted(doc.items, key=lambda i: (i.place.distance_m, i.place.category))
    return " · ".join(
        f"{_CAT_EMOJI.get(i.place.category, '📍')} {_nombre_para_prosa(i.place.name)} "
        f"a ~{int(round(i.place.distance_m))} m"
        for i in items
    ) or None


def formatear_conectividad(doc: NearestTransitEvidenceV0 | None) -> str | None:
    """«🚇 Estación X a ~640 m». SIN minutos: en la prosa, «(N min» se lee como tiempo real de
    ruta (`_transporte_min`), y aquí solo hay una estimación en línea recta. Los minutos viven
    en la evidencia, rotulados como `estimated`."""
    if doc is None or doc.status is not MeasureStatus.AVAILABLE or doc.stop is None:
        return None
    s = doc.stop.stop
    masivo = s.mode == "masivo"
    icono = "🚇" if masivo else "🚏"
    tipo = "" if masivo else " (parada de bus, NO es Metro)"
    return f"{icono} {_nombre_para_prosa(s.name)}{tipo} a ~{int(round(s.distance_m))} m"


# ══ 3 · LECTURA COMPATIBLE: fila → estructurada | legado_no_verificado | ausente ═══
Estado = Literal["estructurada", "legado_no_verificado", "ausente"]

_DIMENSIONES = {
    "servicios": ("servicios_evidencia", "servicios_cercanos", NearbyPlacesEvidenceV0,
                  formatear_servicios),
    "conectividad": ("conectividad_evidencia", "conectividad", NearestTransitEvidenceV0,
                     formatear_conectividad),
}

# Tolerancia al comparar el origen de la evidencia con la posición actual de la fila: ~1 cm.
# Si el inmueble se movió (dirección editada), la evidencia describe OTRO punto.
_TOLERANCIA_GRADOS = 1e-7


@dataclass(frozen=True)
class LecturaContexto:
    estado: Estado
    documento: NearbyPlacesEvidenceV0 | NearestTransitEvidenceV0 | None
    texto: str | None
    """`estructurada` → la prosa RENDERIZADA desde el documento, nunca la columna de texto.
    `legado_no_verificado` → el texto guardado, tal cual, marcado como sin procedencia."""
    motivo: str | None = None

    @property
    def procedencia_demostrada(self) -> bool:
        return (self.estado == "estructurada" and self.documento is not None
                and self.documento.status is MeasureStatus.AVAILABLE)


def leer_contexto_persistido(fila: Mapping, dimension: str) -> LecturaContexto:
    """La lectura de transición. Con evidencia válida, la evidencia MANDA; sin ella, el texto es
    legado sin verificar, que ningún consumidor debe tratar como procedencia.

    Una evidencia que no valida, o que se midió desde otro punto, NO es canónica: se degrada a
    legado y dice por qué. Nunca al revés: el texto no asciende a evidencia por parecer válido.
    """
    col_ev, col_txt, modelo, formatear = _DIMENSIONES[dimension]
    crudo, texto = fila.get(col_ev), fila.get(col_txt)
    motivo = None
    if crudo is not None:
        try:
            doc = modelo.model_validate(json.loads(crudo) if isinstance(crudo, (str, bytes)) else crudo)
        except (ValidationError, ValueError, TypeError) as exc:
            motivo = f"evidencia persistida inválida: {type(exc).__name__}"
        else:
            lat, lon = fila.get("lat"), fila.get("lon")
            if lat is None or lon is None:
                motivo = "sin la posición de la fila no se puede comprobar el origen de la evidencia"
            elif (abs(float(lat) - doc.origin.lat) > _TOLERANCIA_GRADOS
                  or abs(float(lon) - doc.origin.lon) > _TOLERANCIA_GRADOS):
                motivo = "el inmueble ya no está donde se midió la evidencia"
            else:
                return LecturaContexto("estructurada", doc, formatear(doc))
    if texto:
        return LecturaContexto("legado_no_verificado", None, texto, motivo)
    return LecturaContexto("ausente", None, None, motivo)


# ══ 4 · ESQUEMA: ¿existe la 041 en esta base? ═════════════════════════════════════
_esquema_041_visto = False


async def esquema_041_presente(session) -> bool:
    """Las dos columnas de la 041 existen en `public.activos_inmutables`.

    Se consulta el catálogo, no se asume: el mismo código tiene que funcionar contra una base
    SIN la 041 (escribe solo el texto, como hoy) y contra una CON ella. El «sí» se recuerda por
    proceso; el «no» se vuelve a mirar, para que aplicar la 041 no exija reiniciar.
    """
    global _esquema_041_visto
    if _esquema_041_visto:
        return True
    from sqlalchemy import text
    try:
        n = (await session.execute(text(
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'activos_inmutables' "
            "AND column_name IN ('servicios_evidencia', 'conectividad_evidencia')"))).scalar()
    except Exception as exc:  # noqa: BLE001 — no saber ≠ «sí está»: se escribe como sin la 041
        log.warning("foso=esquema_041_ilegible causa=%s: %s", type(exc).__name__, str(exc)[:200])
        return False
    _esquema_041_visto = n == len(COLUMNAS_041)
    return _esquema_041_visto


def a_json(doc: NearbyPlacesEvidenceV0 | NearestTransitEvidenceV0 | None) -> str | None:
    return None if doc is None else doc.model_dump_json()
