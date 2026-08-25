"""PlaceContextV0 — lo que sabemos de un punto (E1.4 de FASE 1, Contracts).

Contrato puro. No se refactoriza `rutas.py`, no se construye Place Harness, no hay
scoring. Nadie lo consume todavía.

El doc 03 resume por qué esta unidad es la más grande de F1: *"~40 % del contrato,
~75 % del dato — el dato está, el contrato no"*. Casi todo lo que hace falta ya se
calcula; lo que falta es un objeto que diga **con qué respaldo** se calculó cada cosa.

──────────────────────────────────────────────────────────────────────────────────
LA REGLA CENTRAL: "NO SABEMOS" NO SE PUEDE CONFUNDIR CON "TENEMOS UN VALOR"
──────────────────────────────────────────────────────────────────────────────────

Toda dimensión respaldada por evidencia se envuelve en `PlaceMeasureV0`, y su estado
tiene cuatro lecturas — tres explícitas y una por ausencia:

    dimensión AUSENTE del objeto
      → no evaluada, no solicitada, o no ensamblada en ESTE contexto.
        No dice nada sobre el lugar; dice algo sobre esta consulta.

    status = available
      → hay un valor defendible Y la evidencia que lo sostiene.

    status = unknown
      → la dimensión forma parte del contexto, pero su valor se desconoce.

    status = insufficient_evidence
      → la dimensión SÍ se evaluó, y la evidencia no alcanza para declarar un valor.
        Es el estado que E0.4 dejó visible al usuario: "no tenemos medición de ruido
        aquí" es información, no un hueco.

`unknown` e `insufficient_evidence` **prohíben** `value`. Nunca se rellena la ausencia
con un número o una categoría sintética: ese relleno es exactamente lo que en E0.4
hacía que el ruido moviera el ranking ±50 puntos sin una sola medición detrás.

Y al revés: `available` **exige** evidencia. Un valor sin procedencia no puede
construirse, aunque el valor sea correcto. Esto es E0.3 y E0.4 convertidos en
invariante en vez de en disciplina.

`evidence[]` puede estar vacío o, en `insufficient_evidence`, contener la evidencia que
EXPLICA la insuficiencia. Lo que no puede hacer es convertirse en un valor por
inferencia: que exista una referencia no significa que haya un número.

──────────────────────────────────────────────────────────────────────────────────
LO QUE **NO** ENTRA
──────────────────────────────────────────────────────────────────────────────────

No hay `score`, ni `weight`, ni `rank`, ni `decision_eligible`. Decidir qué dimensión
pesa y si algo es elegible para puntuar es del Decision Harness, y meterlo aquí haría
que el contrato tomara partido sobre una decisión que todavía no se ha diseñado.

Tampoco hay strings humanos como representación primaria. La prosa —"a 5 minutos
caminando del parque"— se DERIVA de este objeto; si la prosa fuera el dato, volveríamos
a tener que reparsearla para comprobar cualquier cosa.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Generic, Literal, TypeVar

from pydantic import Field, field_validator, model_validator

from app.contracts.common_v0 import ContractBase as _Base
from app.contracts.common_v0 import TravelMode
from app.contracts.evidence_v0 import EvidenceRefV0

CONTRACT_VERSION = "place-context-v0"

T = TypeVar("T")


class MeasureStatus(StrEnum):
    """Qué respaldo tiene el valor de una dimensión. Ver la cabecera del módulo."""

    AVAILABLE = "available"
    UNKNOWN = "unknown"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class PlaceMeasureV0(_Base, Generic[T]):
    """Una dimensión del lugar con su respaldo. Genérica: el tipo del valor lo pone
    quien la usa (`PlaceMeasureV0[float]`, `PlaceMeasureV0[NearestTransitV0]`…).

    Genérica y no una clase por dimensión porque la REGLA es la misma para todas: si no
    hay evidencia, no hay valor. Repetirla por dimensión sería repetirla mal en alguna.
    """

    status: MeasureStatus
    value: T | None = None
    evidence: tuple[EvidenceRefV0, ...] = ()

    observed_at: datetime | None = None
    """Cuándo el mundo estaba así — la frescura de esta dimensión. `None` = no se sabe;
    no se sustituye por "ahora", que es la mentira que cerró E0.3."""

    limitations: tuple[str, ...] = ()
    """Qué NO puede sostener este valor, a nivel de la dimensión. Es distinto de las
    `limitations` de una `EvidenceRefV0`, que hablan de UNA fuente: aquí se declara el
    límite de la medida completa."""

    @field_validator("observed_at")
    @classmethod
    def _exigir_zona_horaria(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("los instantes deben traer zona horaria")
        return v

    @field_validator("limitations")
    @classmethod
    def _sin_limitaciones_vacias(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if any(not l.strip() for l in v):
            raise ValueError("una limitación vacía no limita nada")
        return v

    @model_validator(mode="after")
    def _el_estado_manda_sobre_el_valor(self) -> PlaceMeasureV0[T]:
        """El corazón del contrato. Ver la cabecera."""
        if self.status is MeasureStatus.AVAILABLE:
            if self.value is None:
                raise ValueError(
                    "status=available sin value: si no hay valor, el estado es unknown "
                    "o insufficient_evidence, no 'disponible'"
                )
            if not self.evidence:
                raise ValueError(
                    "status=available sin evidence: un valor sin procedencia es "
                    "exactamente lo que en E0.4 movía el ranking sin una sola medición "
                    "detrás. Si el valor es defendible, la evidencia existe; si no la "
                    "hay, el estado es insufficient_evidence"
                )
            return self

        if self.value is not None:
            raise ValueError(
                f"status={self.status.value} con value={self.value!r}: la ausencia de "
                "un valor defendible no se rellena con un número ni una categoría "
                "sintética. value tiene que ser None"
            )
        return self

    @property
    def hay_valor(self) -> bool:
        """Lectura. Qué hacer con eso es del Decision Harness, no de aquí."""
        return self.status is MeasureStatus.AVAILABLE


class GeoPoint(_Base):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class NearestTransitV0(_Base):
    """La parada de transporte más cercana. Estructurado, no "a dos cuadras"."""

    distance_m: float = Field(ge=0)
    mode: str | None = Field(default=None, min_length=1)
    """`"bus"`, `"metro"`, `"trolebus"`… Texto abierto: el inventario de POIs ya
    distingue metro, estación de tren y terminal de bus, y el catálogo cambia por
    ciudad. Un enum congelaría el de Quito."""

    name: str | None = Field(default=None, min_length=1)
    stop_id: str | None = Field(default=None, min_length=1)


class NearbyPlaceV0(_Base):
    """Un servicio cercano. La categoría es texto por la misma razón que `dimension` en
    E1.2: el catálogo del dominio no entra en la primitiva."""

    category: str = Field(min_length=1)
    distance_m: float = Field(ge=0)
    name: str | None = Field(default=None, min_length=1)
    poi_id: str | None = Field(default=None, min_length=1)


class TravelToAnchorV0(_Base):
    """El trayecto hasta un ancla del comprador.

    REPRESENTABLE, NO CALCULADO. F1 no implementa `compute_travel_to_anchor` — ni aquí
    ni en E1.2. Este objeto solo tiene que poder guardar el resultado cuando exista, y
    poder decir que todavía no existe: para eso está el `PlaceMeasureV0` que lo envuelve,
    con `status=unknown` mientras nadie lo haya calculado.

    LA COSTURA CON EL COMPRADOR ES `anchor_id`, Y NO EL LABEL. Este módulo **no importa**
    `CommuteAnchorV0`: no hay clave foránea ni dependencia Place → Buyer, porque un
    lugar existe sin que haya nadie buscándolo. `anchor_id` es un identificador opaco de
    correlación; quien valide que corresponde a un ancla real del comprador que
    participa en la decisión es `DecisionContextV0` (E1.5), que es donde los dos
    contextos se encuentran.
    """

    anchor_id: str = Field(min_length=1)
    """Referencia ESTRUCTURAL al ancla del comprador. Opaca: no se parsea ni se deriva."""

    anchor_label: str | None = Field(default=None, min_length=1)
    """Solo presentación. **Nunca se usa para correlacionar.** Correlacionar por texto es
    cómo un trayecto queda huérfano en silencio porque alguien escribió "oficina" donde
    la persona había dicho "la oficina"."""

    mode: TravelMode = TravelMode.UNKNOWN
    duration_minutes: float | None = Field(default=None, ge=0)
    distance_m: float | None = Field(default=None, ge=0)


class IsochroneV0(_Base):
    """Un contorno de alcance. Se incluye porque el dato existe de verdad: `isocronas.py`
    pide a Valhalla contornos peatonales con `polygons=true` y el repo ya los guarda
    serializados con `json.dumps(geometry)`.
    """

    mode: TravelMode
    minutes: int = Field(gt=0)
    geometry_geojson: str = Field(min_length=1)
    """La geometría en GeoJSON, tal como la devuelve Valhalla y como el repo ya la
    persiste. Se valida que sea JSON con un `type` de polígono — así no es texto opaco,
    aunque viaje serializada."""

    @field_validator("geometry_geojson")
    @classmethod
    def _tiene_que_ser_un_poligono(cls, v: str) -> str:
        try:
            geom = json.loads(v)
        except json.JSONDecodeError as exc:
            raise ValueError(f"geometry_geojson no es JSON válido: {exc}") from exc
        if not isinstance(geom, dict) or geom.get("type") not in {"Polygon", "MultiPolygon"}:
            raise ValueError(
                "geometry_geojson tiene que ser un Polygon o MultiPolygon; un contorno "
                "que no cierra no sirve para preguntar si un punto cae dentro"
            )
        return v


class NamedMeasureV0(_Base):
    """Una dimensión escalar del entorno, con nombre: ruido, tráfico, vegetación…

    Existe para que esas dimensiones puedan estar presentes SIN valor. En E0.4 el ruido
    y la vegetación movían el score ±50 y ±80 puntos sin fuente medida; se sacaron del
    ranking pero se conservó su explicación al usuario. Esto es esa decisión hecha
    estructura: la dimensión aparece, su estado dice que no hay medición, y `value` es
    `None` porque el validador de `PlaceMeasureV0` no admite otra cosa.
    """

    dimension: str = Field(min_length=1)
    measure: PlaceMeasureV0[float]


class PlaceContextV0(_Base):
    """Lo que sabemos de un punto, con el respaldo de cada cosa."""

    contract_version: Literal["place-context-v0"] = CONTRACT_VERSION

    place_id: str | None = Field(default=None, min_length=1)
    """Identificador propio, si lo hay. Un punto no necesita id para tener contexto."""

    location: GeoPoint
    assembled_at: datetime
    """Cuándo se ensambló ESTE contexto. Distinto del `observed_at` de cada medida: se
    puede ensamblar hoy un contexto con dimensiones observadas hace meses, y confundir
    las dos fechas haría parecer fresco lo que no lo es."""

    walkability: PlaceMeasureV0[float] | None = None
    """Caminabilidad. La procedencia —medida sobre red OSM o estimada por zona— vive en
    `evidence[].source_type` y `methodology`. Ese es el arreglo de E0.3 hecho
    estructura: antes el motor decía "OpenStreetMap" sobre un número estimado porque la
    fuente viajaba en una columna que nadie miraba."""

    nearest_transit: PlaceMeasureV0[NearestTransitV0] | None = None
    nearby_places: PlaceMeasureV0[tuple[NearbyPlaceV0, ...]] | None = None
    travel_to_anchors: tuple[PlaceMeasureV0[TravelToAnchorV0], ...] = ()
    isochrones: tuple[PlaceMeasureV0[IsochroneV0], ...] = ()

    environment: tuple[NamedMeasureV0, ...] = ()
    """Dimensiones escalares del entorno: ruido, tráfico, vegetación. Ver
    `NamedMeasureV0`."""

    limitations: tuple[str, ...] = ()
    """Límites del contexto entero, no de una dimensión."""

    @field_validator("assembled_at")
    @classmethod
    def _exigir_zona_horaria(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("assembled_at debe traer zona horaria")
        return v

    @field_validator("limitations")
    @classmethod
    def _sin_limitaciones_vacias(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if any(not l.strip() for l in v):
            raise ValueError("una limitación vacía no limita nada")
        return v

    @model_validator(mode="after")
    def _cada_dimension_una_sola_vez(self) -> PlaceContextV0:
        nombres = [d.dimension.strip().lower() for d in self.environment]
        repetidas = {n for n in nombres if nombres.count(n) > 1}
        if repetidas:
            raise ValueError(
                f"dimensión repetida en environment: {sorted(repetidas)}. Dos medidas "
                "para la misma dimensión y nadie sabe cuál gana"
            )
        return self

    @model_validator(mode="after")
    def _un_ancla_una_sola_vez(self) -> PlaceContextV0:
        """Por `anchor_id`, no por label: dos anclas pueden llamarse igual y ser
        distintas, y la misma puede cambiar de nombre."""
        ids = [m.value.anchor_id for m in self.travel_to_anchors if m.value is not None]
        repetidos = {i for i in ids if ids.count(i) > 1}
        if repetidos:
            raise ValueError(f"anchor_id repetido: {sorted(repetidos)}")
        return self


def json_schema() -> dict[str, Any]:
    """JSON Schema del contrato. Función y no constante, para que no se congele en el
    import y quede desincronizado del modelo."""
    return PlaceContextV0.model_json_schema()
