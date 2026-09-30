"""PlaceDimensionEvidenceV0 — la evidencia PERSISTIDA de una dimensión de lugar (PLACE-PROVENANCE-041).

QUÉ ES. El documento que se guarda en `activos_inmutables.servicios_evidencia` y
`activos_inmutables.conectividad_evidencia` (migración 041): lo que Contexto derivó sobre el
entorno de un inmueble, con la procedencia de CADA elemento. Es el origen del que se renderiza
la prosa histórica (`servicios_cercanos`, `conectividad`), no al revés.

POR QUÉ UN CONTRATO NUEVO Y NO OTRA COLUMNA DE ETIQUETA. La procedencia de esas dos columnas
iba a ser una sola palabra (`contexto_procedencia = 'propio'`, ver `app/place/legado.py`). Una
etiqueta así mezcla tres preguntas distintas y las contesta todas a la vez:

    SOURCE        de dónde sale el REGISTRO observado      → EvidenceRefV0 PUBLIC_DATASET
    METHOD        cómo se convirtió en una medida          → EvidenceRefV0 OWN_MEASUREMENT
                                                              (o HEURISTIC_ESTIMATE)
    VERIFICATION  si una persona lo comprobó en terreno    → EvidenceRefV0 OPERATOR_DECLARED

Aquí cada elemento enlaza cada eje por separado, y el tipo de la evidencia enlazada tiene que
ser el de su eje: un método no puede hacerse pasar por fuente, ni una fuente por verificación.

QUÉ SE REUTILIZA, sin modificarlo:
  · `EvidenceRefV0` / `SourceType` / `PersistencePolicy` — la procedencia;
  · `NearbyPlaceV0` / `NearestTransitV0` — el VALOR de cada elemento;
  · `MeasureStatus` — el estado (`available` / `insufficient_evidence`);
  · `GeoPoint` — el punto desde el que se midió.

QUÉ ES NUEVO, y por qué no cabía en lo existente:
  · `ValueClass` (measured / derived / estimated) — el vocabulario de Plan 1.1 §E4.5, que el
    código no tenía. No se mete en `methodology`: esa prosa ya carga dos responsabilidades y el
    canon dice que no admite una tercera.
  · `DistanceMethod` / `DurationMethod` — el método como CÓDIGO legible por máquina. Es lo que
    permite afirmar «esto no es tiempo de ruta» sin leer prosa.
  · los enlaces por elemento (`*_evidence_id(s)`) — `PlaceMeasureV0.evidence` es una tupla
    plana y no dice qué evidencia respalda a qué elemento.

LO QUE ESTE DOCUMENTO NO REPRESENTA, y por qué:
  · `unknown`. No se persiste un documento para decir «no sé»: el UNKNOWN es la columna en
    NULL. Fabricar un documento de ausencia sería inventarse una procedencia para representarla,
    el mismo error que `EvidenceRefV0` ya prohíbe.
  · la curación del corredor. Se aplica en la lectura, sobre `poi_id` (y por nombre para las
    curaciones de texto). Por eso cada elemento lleva su `poi_id`: sin él, un POI cerrado no se
    podría retirar de la evidencia guardada.
  · la licencia de cada dataset. La decisión de guardar vive en `persistence_policy`.

INVARIANTES que hace cumplir (y que la 041 repite como CHECK en la base):
  1. `available` exige elementos y evidencia; `insufficient_evidence` no admite elementos.
  2. Todo enlace apunta a una evidencia que EXISTE en el documento, y del TIPO de su eje.
  3. Todo lo que hay aquí es `persistable`: el documento se guarda, así que nada de él puede
     ser `runtime_only` ni caché temporal (Plan 1.1 §E4.6).
  4. Ningún proveedor Google: el contenido histórico de Places/Routes no vuelve a entrar.
  5. Línea recta = `derived`; minutos por paso fijo = `estimated` con evidencia heurística.
     Una estimación en línea recta NUNCA se rotula como tiempo de ruta.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.contracts.common_v0 import ContractBase as _Base
from app.contracts.evidence_v0 import EvidenceRefV0, PersistencePolicy, SourceType
from app.contracts.place_v0 import GeoPoint, MeasureStatus, NearbyPlaceV0, NearestTransitV0

CONTRACT_VERSION = "place-dimension-evidence/v0"


class ValueClass(StrEnum):
    """Qué clase de valor es. Vocabulario de Plan 1.1 §E4.5 (`measured / derived / estimated /
    insufficient_evidence`); el cuarto es un ESTADO y vive en `MeasureStatus`."""

    MEASURED = "measured"
    """Observado directamente (p. ej. un recorrido cronometrado en terreno). Hoy ningún
    productor lo emite."""

    DERIVED = "derived"
    """Calculado de forma reproducible sobre datos observados: la distancia geodésica entre
    dos coordenadas registradas, o una ruta calculada sobre la red de calles."""

    ESTIMATED = "estimated"
    """Supuesto por una heurística. Exige evidencia `heuristic_estimate` con limitaciones."""


class DistanceMethod(StrEnum):
    STRAIGHT_LINE_GEODESIC = "straight_line_geodesic"
    """`ST_Distance(geography)` entre el inmueble y el POI: línea recta sobre el elipsoide."""

    STREET_NETWORK_ROUTE = "street_network_route"
    """Recorrido por la red de calles. Ningún productor lo emite todavía."""


class DurationMethod(StrEnum):
    STRAIGHT_LINE_AT_FIXED_PACE = "straight_line_at_fixed_pace"
    """Distancia en línea recta dividida entre un paso fijo (80 m/min). Es una ESTIMACIÓN."""

    STREET_NETWORK_ROUTE = "street_network_route"
    """Duración de un recorrido real por calles. Ningún productor lo emite todavía."""


# Qué clase admite cada método. Es la regla que impide rotular una recta como ruta.
_CLASE_DE_DISTANCIA = {
    DistanceMethod.STRAIGHT_LINE_GEODESIC: {ValueClass.DERIVED},
    DistanceMethod.STREET_NETWORK_ROUTE: {ValueClass.DERIVED, ValueClass.MEASURED},
}
_CLASE_DE_DURACION = {
    DurationMethod.STRAIGHT_LINE_AT_FIXED_PACE: {ValueClass.ESTIMATED},
    DurationMethod.STREET_NETWORK_ROUTE: {ValueClass.DERIVED, ValueClass.MEASURED},
}


def _ids_utilizables(v: tuple[str, ...]) -> tuple[str, ...]:
    if any(not i.strip() for i in v):
        raise ValueError("un identificador de evidencia vacío no apunta a nada")
    if len(set(v)) != len(v):
        raise ValueError("identificadores de evidencia repetidos")
    return v


class _ProcedenciaDeElemento(_Base):
    """Los tres ejes de procedencia de un elemento, cada uno por separado."""

    source_evidence_id: str = Field(min_length=1)
    """→ `PUBLIC_DATASET`: el registro del dataset abierto del que sale el lugar."""

    method_evidence_id: str = Field(min_length=1)
    """→ `OWN_MEASUREMENT`: cómo Contexto calculó la distancia."""

    verification_evidence_ids: tuple[str, ...] = ()
    """→ `OPERATOR_DECLARED`: una persona lo comprobó en terreno. Vacío = SIN verificación, que
    no es lo mismo que verificado ni que «descartado»: nadie ha ido."""

    _v = field_validator("verification_evidence_ids")(_ids_utilizables)

    def enlaces(self) -> dict[str, tuple[str, ...]]:
        return {"source": (self.source_evidence_id,),
                "method": (self.method_evidence_id,),
                "verification": self.verification_evidence_ids}


class ServiceItemEvidenceV0(_ProcedenciaDeElemento):
    """Un servicio cercano (un POI de la capa propia) con su procedencia."""

    place: NearbyPlaceV0

    @model_validator(mode="after")
    def _identidad_obligatoria(self) -> ServiceItemEvidenceV0:
        """Sin `poi_id` el elemento no se puede curar ni invalidar después: si un corredor lo
        cierra, no habría forma de saber qué evidencia guardada lo nombra."""
        if not self.place.poi_id:
            raise ValueError("un elemento persistido exige place.poi_id (la identidad en la capa)")
        return self


class TransitItemEvidenceV0(_ProcedenciaDeElemento):
    """La parada o estación más cercana, con su procedencia."""

    stop: NearestTransitV0

    @model_validator(mode="after")
    def _identidad_obligatoria(self) -> TransitItemEvidenceV0:
        if not self.stop.stop_id:
            raise ValueError("un elemento persistido exige stop.stop_id (la identidad en la capa)")
        return self


class WalkDurationV0(_Base):
    """Minutos a pie hasta la parada, con su clase declarada. Solo existe si hay una parada."""

    minutes: float = Field(gt=0)
    value_class: ValueClass
    method: DurationMethod
    evidence_id: str = Field(min_length=1)

    @model_validator(mode="after")
    def _el_metodo_manda_sobre_la_clase(self) -> WalkDurationV0:
        permitidas = _CLASE_DE_DURACION[self.method]
        if self.value_class not in permitidas:
            raise ValueError(
                f"duración con method={self.method.value} y value_class={self.value_class.value}: "
                f"ese método solo admite {sorted(c.value for c in permitidas)}. Una estimación en "
                "línea recta no es un tiempo de ruta, y un tiempo de ruta no es una estimación"
            )
        return self


class _DocumentoDeDimension(_Base):
    """Lo común a las dos dimensiones persistidas."""

    contract_version: Literal["place-dimension-evidence/v0"] = CONTRACT_VERSION

    status: MeasureStatus
    derived_at: datetime
    """Cuándo derivó Contexto este documento. NO es `observed_at` de nada."""

    origin: GeoPoint
    """El punto desde el que se midió. Si el inmueble se mueve, el documento deja de valer."""

    radius_m: int = Field(gt=0)
    distance_method: DistanceMethod
    distance_class: ValueClass

    evidence: tuple[EvidenceRefV0, ...] = ()
    limitations: tuple[str, ...] = ()

    @field_validator("derived_at")
    @classmethod
    def _exigir_zona_horaria(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("derived_at debe traer zona horaria")
        return v

    @field_validator("limitations")
    @classmethod
    def _sin_limitaciones_vacias(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if any(not l.strip() for l in v):
            raise ValueError("una limitación vacía no limita nada")
        return v

    # ── lo que cada dimensión concreta aporta ─────────────────────────────────────
    def _elementos(self) -> tuple[_ProcedenciaDeElemento, ...]:  # pragma: no cover - abstracta
        raise NotImplementedError

    def _enlaces_extra(self) -> dict[str, tuple[tuple[str, ...], set[SourceType]]]:
        """Enlaces que no son de un elemento (la duración), con los tipos que admite cada uno."""
        return {}

    # ── invariantes comunes ───────────────────────────────────────────────────────
    @model_validator(mode="after")
    def _invariantes(self) -> _DocumentoDeDimension:
        if self.status is MeasureStatus.UNKNOWN:
            raise ValueError(
                "status=unknown no se persiste: el UNKNOWN es la columna en NULL. Guardar un "
                "documento para decir «no sé» es inventarse una procedencia para la ausencia"
            )
        elementos = self._elementos()
        if self.status is MeasureStatus.AVAILABLE:
            if not elementos:
                raise ValueError("status=available sin elementos")
            if not self.evidence:
                raise ValueError("status=available sin evidencia")
        elif elementos:
            raise ValueError(f"status={self.status.value} con elementos: la ausencia no lleva valor")

        if self.distance_class not in _CLASE_DE_DISTANCIA[self.distance_method]:
            raise ValueError(
                f"distance_method={self.distance_method.value} no admite "
                f"distance_class={self.distance_class.value}"
            )

        por_id: dict[str, EvidenceRefV0] = {}
        for e in self.evidence:
            if e.evidence_id in por_id:
                raise ValueError(f"evidence_id repetido: {e.evidence_id}")
            por_id[e.evidence_id] = e
            if e.persistence_policy is not PersistencePolicy.PERSISTABLE:
                raise ValueError(
                    f"evidencia {e.evidence_id} con persistence_policy="
                    f"{e.persistence_policy.value}: este documento SE GUARDA, así que solo admite "
                    "evidencia persistable (Plan 1.1 §E4.6)"
                )
            if (e.provider or "").lower().startswith("google"):
                raise ValueError(
                    f"evidencia {e.evidence_id} de provider={e.provider}: el contenido de Google no "
                    "se persiste ni vuelve a entrar como fuente"
                )

        tipo_por_eje = {
            "source": {SourceType.PUBLIC_DATASET},
            "method": {SourceType.OWN_MEASUREMENT},
            "verification": {SourceType.OPERATOR_DECLARED},
        }
        for el in elementos:
            for eje, ids in el.enlaces().items():
                for i in ids:
                    _exigir_enlace(por_id, i, eje, tipo_por_eje[eje])
        for eje, (ids, tipos) in self._enlaces_extra().items():
            for i in ids:
                _exigir_enlace(por_id, i, eje, tipos)
        return self


def _exigir_enlace(por_id: dict[str, EvidenceRefV0], i: str, eje: str,
                   tipos: set[SourceType]) -> None:
    ev = por_id.get(i)
    if ev is None:
        raise ValueError(f"el eje {eje} apunta a la evidencia {i}, que no está en el documento")
    if ev.source_type not in tipos:
        raise ValueError(
            f"el eje {eje} apunta a evidencia de tipo {ev.source_type.value}; ese eje solo admite "
            f"{sorted(t.value for t in tipos)}. SOURCE, METHOD y VERIFICATION no son intercambiables"
        )


class NearbyPlacesEvidenceV0(_DocumentoDeDimension):
    """`servicios_evidencia`: el servicio más cercano por categoría, en la capa propia."""

    dimension: Literal["nearby_places"] = "nearby_places"
    items: tuple[ServiceItemEvidenceV0, ...] = ()

    def _elementos(self) -> tuple[_ProcedenciaDeElemento, ...]:
        return self.items

    @model_validator(mode="after")
    def _un_elemento_por_poi(self) -> NearbyPlacesEvidenceV0:
        ids = [i.place.poi_id for i in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("el mismo poi_id aparece dos veces")
        return self


class NearestTransitEvidenceV0(_DocumentoDeDimension):
    """`conectividad_evidencia`: la parada más cercana (masiva primero), en la capa propia."""

    dimension: Literal["nearest_transit"] = "nearest_transit"
    stop: TransitItemEvidenceV0 | None = None
    walk_duration: WalkDurationV0 | None = None

    def _elementos(self) -> tuple[_ProcedenciaDeElemento, ...]:
        return (self.stop,) if self.stop is not None else ()

    def _enlaces_extra(self) -> dict[str, tuple[tuple[str, ...], set[SourceType]]]:
        if self.walk_duration is None:
            return {}
        d = self.walk_duration
        tipos = ({SourceType.HEURISTIC_ESTIMATE} if d.value_class is ValueClass.ESTIMATED
                 else {SourceType.OWN_MEASUREMENT, SourceType.PROVIDER_API})
        return {"walk_duration": ((d.evidence_id,), tipos)}

    @model_validator(mode="after")
    def _duracion_solo_con_parada(self) -> NearestTransitEvidenceV0:
        if self.walk_duration is not None and self.stop is None:
            raise ValueError("walk_duration sin parada: no hay a dónde caminar")
        return self


def json_schema() -> dict[str, Any]:
    return {"nearby_places": NearbyPlacesEvidenceV0.model_json_schema(),
            "nearest_transit": NearestTransitEvidenceV0.model_json_schema()}
