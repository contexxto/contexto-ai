"""PropertyContextV0 — un inmueble tal como lo conocemos por un proveedor (E1.3).

Contrato puro: no hay adaptadores, ni migraciones, ni persistencia nueva, ni Partner
Layer. Nadie lo consume todavía y nada de aquí cambia el comportamiento del producto.

──────────────────────────────────────────────────────────────────────────────────
1. LO PERMANENTE Y LO EFÍMERO NO SE MEZCLAN
──────────────────────────────────────────────────────────────────────────────────

El repo ya acertó con esta separación —`ActivoInmutable` + `TransaccionTemporal`— y el
contrato la conserva:

  · `location` y `attributes` describen el ACTIVO FÍSICO. Un departamento tiene 90 m²
    y está donde está, se venda o no.
  · `transaction` describe el LISTING, que es efímero: aparece, cambia de precio,
    se cierra, y meses después el mismo inmueble vuelve a salir con otro precio.

Por eso `transaction` es opcional: un inmueble que existe sin listing activo es un
estado normal, no un dato incompleto.

──────────────────────────────────────────────────────────────────────────────────
2. EL PRECIO VIVE EN UN SOLO SITIO, Y ESTO NO ES TEÓRICO
──────────────────────────────────────────────────────────────────────────────────

El inventario de hoy guarda los atributos en un JSONB (`caracteristicas`) con 25 llaves
sin tipar, y el doc 03 documenta el resultado sobre un activo REAL: ese JSONB traía un
`precio` de $200 mientras la transacción decía $180. Dos precios, ninguna regla sobre
cuál gana, y quien lea uno u otro dará una cifra distinta al mismo comprador.

El contrato lo cierra estructuralmente: **el precio solo existe en `transaction.price`**
y `attributes` rechaza cualquier llave que parezca un precio. No es una convención que
haya que recordar; es un error al construir.

──────────────────────────────────────────────────────────────────────────────────
3. IDENTIDAD DE PROVEEDOR, SIN PARTNER LAYER
──────────────────────────────────────────────────────────────────────────────────

`(provider_id, property_id)` es la identidad externa estable. Hoy no existe en el
inventario —cero apariciones de `provider`/`tenant`/`external_id` en `app/`, verificado
en doc 03— y esa ausencia es lo que bloquea cualquier integración con un tercero: sin
un sitio donde poner "este inmueble es el 4471 de tal proveedor", dos cargas del mismo
listado se convierten en dos inmuebles.

Que el contrato lo tenga NO construye Partner Layer. Solo deja de hacerla imposible.

──────────────────────────────────────────────────────────────────────────────────
LO QUE QUEDA ABIERTO A PROPÓSITO
──────────────────────────────────────────────────────────────────────────────────

`provider_type` también es texto. Solo hay un valor evidenciado —`"contexto"` para el
inventario propio, según el Plan §1.4—; inventar una taxonomía de tipos de proveedor a
partir de un solo caso sería congelar una hipótesis sobre un mercado que aún no
conocemos.

──────────────────────────────────────────────────────────────────────────────────
4. UN REGISTRO DICE PARA QUÉ SIRVE, Y LO DICE AQUÍ
──────────────────────────────────────────────────────────────────────────────────

`provenance.inventory_class` declara si el registro es inventario utilizable (`live`),
material de demostración (`demo`), un fixture de pruebas (`test`), o si no se sabe
(`unknown`). Es OBLIGATORIO y no tiene default.

Por qué vive en el contrato y no se difiere a `DecisionContext` o `DecisionTrace`: esas
capas tienen que poder CONFIAR en que esto ya viene declarado. Si la clasificación
naciera aguas abajo, cada consumidor tendría que inferirla, y la inferencia por omisión
siempre acaba en "asumamos que es real".

El caso concreto que esto evita: las fichas de Quito del inventario actual están
hidratadas para pruebas. Sin este campo, un registro hidratado y uno real son
indistinguibles para cualquier capa de arriba, y basta un descuido para que material de
prueba se presente como inventario comercial.

**`provider_type` NO es señal de esto.** Son ejes independientes: un proveedor externo
puede mandar un `demo` y el inventario propio puede ser `live`. Cruzarlos volvería a
esconder la clasificación detrás de un dato que no la significa.

Lo que este campo **todavía no hace**: no hay `decision_eligible`, ni reglas de
benchmark, ni filtros del agente. Esas políticas lo consumirán después. En V0 basta con
preservar la información.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.contracts.common_v0 import ContractBase as _Base
from app.contracts.common_v0 import Money
from app.contracts.evidence_v0 import EvidenceRefV0

CONTRACT_VERSION = "property-context-v0"

PROVIDER_TYPE_CONTEXTO = "contexto"
"""El `provider_type` del inventario propio (Plan §1.4). Es una constante, no un enum:
ver la cabecera del módulo."""

_LLAVES_DE_PRECIO = frozenset(
    {"precio", "price", "valor", "value", "costo", "cost", "monto", "amount", "canon"}
)
"""Llaves prohibidas en `attributes`. Ver §2 de la cabecera: sobre un activo real, un
`precio` en el JSONB contradecía el de la transacción."""


class Operation(StrEnum):
    """Qué se ofrece. Los dos valores están evidenciados en el inventario actual
    (`tipo_operacion` ∈ {`venta`, `arriendo`}); el contrato usa etiquetas en inglés por
    consistencia con el resto de `contracts/`, y el mapeo lo hará el adaptador local
    cuando exista: `venta → sale`, `arriendo → rent`."""

    SALE = "sale"
    RENT = "rent"


class Availability(StrEnum):
    """Estado del anuncio. **Vocabulario del Blueprint 0.1**, adoptado tal cual.

    El inventario actual guarda esto en `estado_anuncio` como texto libre y solo se ha
    observado `"disponible"`; el mapeo lo hará el adaptador de F5:
    `disponible → available`, `reservado → reserved`, `vendido/arrendado → sold`.

    `unknown` forma parte del vocabulario del Blueprint y es el valor honesto para un
    registro cuyo estado no se conoce — distinto de que el campo sea `None`, que
    significa que el listing no lo declara en absoluto.
    """

    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"
    UNKNOWN = "unknown"


class Location(_Base):
    """Dónde está. Del activo físico, no del listing."""

    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    address: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _las_coordenadas_van_de_a_dos(self) -> Location:
        if (self.lat is None) != (self.lon is None):
            raise ValueError(
                "lat y lon van juntas: media coordenada no ubica nada y se propaga "
                "como si ubicara"
            )
        return self

    @model_validator(mode="after")
    def _ubicar_en_algun_sitio(self) -> Location:
        if self.lat is None and self.address is None:
            raise ValueError(
                "una ubicación necesita coordenadas o dirección; sin ninguna de las dos "
                "el inmueble no se puede situar ni comparar contra un lugar"
            )
        return self

    @property
    def esta_georreferenciada(self) -> bool:
        return self.lat is not None


class PropertyAttribute(_Base):
    """Un atributo del activo físico: `("bedrooms", 3)`, `("floor", 4)`.

    Par tipado en vez del JSONB de hoy. Sigue siendo texto libre en la llave —igual que
    `dimension` en E1.2, para no meter el catálogo del dominio en la primitiva— pero el
    valor ya no puede ser cualquier cosa, y el precio no puede entrar.
    """

    key: str = Field(min_length=1)
    value: str | int | float | bool | None = None
    unit: str | None = Field(default=None, min_length=1)

    @field_validator("key")
    @classmethod
    def _el_precio_no_es_un_atributo(cls, v: str) -> str:
        if v.strip().lower() in _LLAVES_DE_PRECIO:
            raise ValueError(
                f"'{v}' no puede ser un atributo: el precio vive solo en "
                "transaction.price. Dos precios sin regla de precedencia es cómo un "
                "activo real acabó ofreciendo $200 y $180 a la vez"
            )
        return v


class Transaction(_Base):
    """El listing. Efímero por naturaleza — ver §1 de la cabecera."""

    operation: Operation
    price: Money | None = None
    """`None` = no publicado. Distinto de cero, que sería un precio."""

    availability: Availability | None = None
    """Vocabulario cerrado del Blueprint 0.1. `None` = el listing no lo declara, que es
    distinto de `UNKNOWN` = lo declara y dice que no se sabe."""

    listed_at: datetime | None = None
    closed_at: datetime | None = None

    @field_validator("listed_at", "closed_at")
    @classmethod
    def _exigir_zona_horaria(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("los instantes deben traer zona horaria")
        return v

    @model_validator(mode="after")
    def _no_se_cierra_antes_de_publicarse(self) -> Transaction:
        if self.listed_at and self.closed_at and self.closed_at < self.listed_at:
            raise ValueError(
                "closed_at es anterior a listed_at: el listing no pudo cerrarse antes "
                "de existir"
            )
        return self


class Media(_Base):
    images: tuple[str, ...] = ()

    @field_validator("images")
    @classmethod
    def _sin_urls_vacias(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if any(not u.strip() for u in v):
            raise ValueError("una URL de imagen vacía no muestra nada")
        return v


class InventoryClass(StrEnum):
    """Para qué sirve este registro. Ver §4 de la cabecera.

    Eje INDEPENDIENTE del proveedor: un proveedor externo puede mandar un demo y el
    inventario propio puede ser real. `provider_type` no es señal de esto.
    """

    LIVE = "live"
    """Destinado a representar inventario real utilizable."""

    DEMO = "demo"
    """Destinado a demostración o producto. **No debe asumirse inventario comercial
    real.**"""

    TEST = "test"
    """Fixture o registro creado para pruebas."""

    UNKNOWN = "unknown"
    """No hay evidencia suficiente para clasificarlo.

    Aquí `unknown` SÍ es válido, y la diferencia con E1.1 importa: allí se prohibió un
    `source_type="unknown"` porque habría fabricado una evidencia para representar que
    no la hay. Aquí no se fabrica nada — el registro existe, y lo que se declara es que
    desconocemos una de sus propiedades. Es la respuesta honesta al migrar inventario
    del que nadie puede decir con certeza de dónde salió."""


class PropertyProvenanceV0(_Base):
    """De dónde vino este registro, cuándo, y para qué sirve.

    Misma disciplina que `EvidenceRefV0`: `received_at` siempre se sabe;
    `last_updated_at` es lo que el proveedor dice, y puede no saberse.
    """

    inventory_class: InventoryClass
    """Obligatorio y sin default. Un default silencioso sería exactamente el fallo que
    este campo existe para evitar: que un registro de prueba pase por real porque nadie
    lo declaró. Si no se puede determinar, `UNKNOWN` — que es una decisión, no una
    omisión."""

    received_at: datetime
    """Cuándo lo recibimos nosotros."""

    last_updated_at: datetime | None = None
    """Cuándo lo actualizó el proveedor, según él. `None` = no lo dice — y no se
    sustituye por `received_at`, que es la mentira que cerró E0.3."""

    evidence: tuple[EvidenceRefV0, ...] = ()

    @field_validator("received_at", "last_updated_at")
    @classmethod
    def _exigir_zona_horaria(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("los instantes deben traer zona horaria")
        return v

    @model_validator(mode="after")
    def _no_actualizado_despues_de_recibido(self) -> PropertyProvenanceV0:
        if self.last_updated_at and self.last_updated_at > self.received_at:
            raise ValueError(
                "last_updated_at es posterior a received_at: no se puede recibir una "
                "actualización que todavía no había ocurrido"
            )
        return self


class Quality(_Base):
    """Qué tan completo llegó y qué le falla. No es una nota al proveedor: es lo que
    permite que un inmueble a medias no se presente igual que uno completo."""

    completeness: float | None = Field(default=None, ge=0.0, le=1.0)
    """`None` = no se calculó. Distinto de `0.0`, que afirma que no llegó nada — la
    misma distinción que `confidence` en E1.1."""

    warnings: tuple[str, ...] = ()

    @field_validator("warnings")
    @classmethod
    def _sin_avisos_vacios(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        if any(not w.strip() for w in v):
            raise ValueError("un aviso en blanco no avisa de nada")
        return v


class PropertyContextV0(_Base):
    """Un inmueble tal como lo conocemos a través de un proveedor."""

    contract_version: Literal["property-context-v0"] = CONTRACT_VERSION

    property_id: str = Field(min_length=1)
    """Identificador del inmueble DENTRO del proveedor."""

    provider_id: str = Field(min_length=1)
    provider_type: str = Field(min_length=1)
    """Texto, no enum — ver la cabecera. El inventario propio es
    `PROVIDER_TYPE_CONTEXTO`."""

    provider_listing_url: str | None = Field(default=None, min_length=1)

    location: Location
    attributes: tuple[PropertyAttribute, ...] = ()
    transaction: Transaction | None = None
    """`None` = sin listing activo. Es un estado normal, no un dato incompleto."""

    media: Media = Field(default_factory=Media)
    provenance: PropertyProvenanceV0
    quality: Quality = Field(default_factory=Quality)

    @model_validator(mode="after")
    def _cada_atributo_una_sola_vez(self) -> PropertyContextV0:
        claves = [a.key.strip().lower() for a in self.attributes]
        repetidas = {k for k in claves if claves.count(k) > 1}
        if repetidas:
            raise ValueError(
                f"atributo repetido: {sorted(repetidas)}. Dos valores para la misma "
                "llave es el problema del JSONB de hoy: nadie sabe cuál gana"
            )
        return self

    @property
    def identidad_externa(self) -> tuple[str, str]:
        """`(provider_id, property_id)` — la identidad estable de §3.

        Sin esto, dos cargas del mismo listado se convierten en dos inmuebles.
        """
        return (self.provider_id, self.property_id)

    @property
    def es_inventario_propio(self) -> bool:
        """Si viene de nuestro propio inventario. **No dice si es real**: para eso está
        `provenance.inventory_class`, que es un eje distinto — ver §4."""
        return self.provider_type == PROVIDER_TYPE_CONTEXTO


def json_schema() -> dict[str, Any]:
    """JSON Schema del contrato. Función y no constante, para que no se congele en el
    import y quede desincronizado del modelo."""
    return PropertyContextV0.model_json_schema()
