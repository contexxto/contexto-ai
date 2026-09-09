"""El adaptador local: una fila del inventario propio → `PropertyContextV0` (PLAN04-1.4).

Antes de esta unidad `PropertyContextV0` existía y NADIE lo producía. La única traducción
escrita vivía dentro de una prueba de compatibilidad de contratos —`_inmueble_desde_el_repo`,
bajo `tests/`— sobre un diccionario a mano, y ese fichero declara de sí mismo: *«No son
adaptadores. No viven en `app/`, no se reutilizan y nadie los importa.»* Aquí se convierte
en código.

    (Ese fichero no se nombra entero a propósito: tiene una guarda que busca su propio
    nombre dentro de `app/` para comprobar que nadie lo importa, y una cita en prosa le
    resulta indistinguible de un import. Queda anotado como deuda: la guarda sería más
    precisa mirando los imports del AST. No se toca desde aquí.)

    frontera de lectura  ─→  fila cruda  ─→  ensamblador PURO  ─→  PropertyContextV0

`leer_activos_locales` es lo ÚNICO que habla con la base. `ensamblar_property_context` no
abre sockets, no mira el reloj y no consulta configuración: dado el mismo par
*(fila, contexto)* devuelve el mismo objeto, byte a byte. Separarlos es lo que hace la
unidad probable sin base de datos, y es también lo que impide que la política se cuele
dentro de la traducción.

──────────────────────────────────────────────────────────────────────────────────
LO QUE ESTE ADAPTADOR SE NIEGA A INVENTAR, Y POR QUÉ CADA COSA
──────────────────────────────────────────────────────────────────────────────────

**1. La zona horaria.** `activos_inmutables.created_at`, `transacciones_temporales.
fecha_publicacion` y `fecha_cierre` son `TIMESTAMP` **sin zona** (`init_db.sql`, y ninguna
migración las convierte). El contrato exige instantes con zona. Hay dos salidas: suponerles
UTC, o no usarlos. Suponer es afirmar algo que el dato no dice —y este repositorio ya pagó
un bug de fechas por exactamente eso—, así que **se omiten y se declara la omisión**. El
contrato lo permite: `listed_at` y `closed_at` son opcionales.

`provenance.received_at` NO es opcional, y por eso no sale de la fila: lo trae
`ContextoDeLectura.snapshot_at`, que el llamador construye con zona. Es honesto porque
`received_at` significa *«cuándo lo trajimos nosotros»* — y eso lo sabe quien lee, no la
fila leída.

**2. La moneda.** `Money.currency` es obligatoria y el inventario NO tiene columna de
moneda: cero apariciones en `models.py`, `init_db.sql` y `migrations/`. Tampoco hay una
configuración autoritativa que reutilizar. `settings.buyer_market_currency` existe, pero su
propia definición la acota a otra cosa —*«el mercado monetario que ESTE DESPLIEGUE del
Buyer Harness puede usar como contexto determinista para acreditar expresiones monetarias
que por sí solas serían ambiguas»*—: es política del Buyer para interpretar lo que dice una
persona, no la moneda en la que está denominado el inventario. Usarla aquí acoplaría el
precio de un inmueble a un ajuste del comprador y heredaría su sucesor previsto.

Así que la moneda llega por parámetro, obligatoria y sin default. El ensamblador no la
elige: la recibe.

**3. Los valores fuera de vocabulario.** `tipo_operacion` y `estado_anuncio` tienen CHECK en
mayúsculas (`'ARRIENDO' | 'VENTA' | 'MONITOREO_PASIVO'`, `'ACTIVO' | 'COMPLETADO' |
'PAUSADO'`) y el runtime compara contra `'ACTIVO'` en cinco sitios. El mapeo es EXACTO: lo
que no está en la tabla no se aproxima, se declara. `'MONITOREO_PASIVO'` no tiene destino
—`Operation` solo admite venta y arriendo— y produce `transaction=None` con aviso, que es
distinto de no tener listing.

Y hay una asimetría que obliga a mirar las dos columnas a la vez: el inventario cierra un
anuncio con una sola palabra, `'COMPLETADO'`, para los dos finales posibles, mientras que el
contrato solo modela uno. `VENTA + COMPLETADO` es `sold`; `ARRIENDO + COMPLETADO` NO lo es
—diría que se vendió un inmueble que se arrendó— y sale como `unknown` con aviso. Ver
`_disponibilidad_de`.

    OJO, DEUDA DECLARADA: los docstrings de `Operation` y `Availability` afirman que el
    inventario guarda minúsculas (`venta`, `disponible`). El DDL dice lo contrario y manda
    el DDL. Corregir esos docstrings toca `app/contracts/`, que esta unidad tiene prohibido
    tocar; queda anotado.

**4. La clasificación del registro.** `inventory_class` es obligatorio y sin default, y la
respuesta honesta hoy es `unknown`: la propia auditoría del repositorio admite que de ocho
artefactos de siembra solapados *«Ninguno indica cuál generó los 40 activos vivos»*. Cuando
la fuente demuestre otra clasificación, se cambia; mientras tanto, `unknown` es una decisión
declarada, no una omisión.

**5. La evidencia.** `provenance.evidence` queda VACÍA, y es deliberado. `EvidenceRefV0` no
tiene —por diseño— un `source_type="unknown"`: su propio módulo dice que fabricar una
referencia para representar la ausencia de procedencia *«es inventarse una procedencia»*, el
error de E0.3 con otra ropa. Y aquí la ausencia es real: si no sabemos qué proceso cargó el
registro (por eso `inventory_class=unknown`), tampoco podemos decir quién declaró su precio
ni sus atributos. Elegir `operator_declared` sería afirmar que detrás hay un corredor con
interés comercial; sobre una ficha posiblemente hidratada, eso es exactamente la
sobreafirmación que el contrato existe para impedir.

Consecuencia práctica: esta unidad NO genera `evidence_id`, así que no hay identidad de
evidencia que hacer determinista. Cuando el inventario sepa decir de dónde viene cada
registro, la evidencia entrará con `uuid5` y namespace propio de Property — sin importar
nada de `app/rutas.py`, que es Place y está tipado sobre su propia materia.

──────────────────────────────────────────────────────────────────────────────────
DETERMINISMO
──────────────────────────────────────────────────────────────────────────────────

Dos ensamblajes de la misma fila con el mismo contexto producen el MISMO JSON. Lo único que
podía romperlo era el orden de `attributes`, que nace de un JSONB: un dict parseado desde
texto y un dict entregado por el driver no tienen por qué iterar igual. Por eso los
atributos se ordenan por llave. No es cosmética — sin eso, «el objeto es el mismo» deja de
ser comprobable.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from pydantic import ValidationError
from sqlalchemy import text

from app.contracts.common_v0 import Money
from app.contracts.property_v0 import (
    PROVIDER_TYPE_CONTEXTO,
    Availability,
    InventoryClass,
    Location,
    Media,
    Operation,
    PropertyAttribute,
    PropertyContextV0,
    PropertyProvenanceV0,
    Quality,
    Transaction,
)
from app.database import AsyncSessionLocal

# El inventario propio es su propio proveedor. No es una identidad externa de verdad —no
# existe todavía— pero tampoco se inventa una: se declara cuál es el proveedor de estos
# registros. `app/decision/context.py` ya tomó la misma decisión para el ref de la decisión.
PROVIDER_ID_LOCAL = "contexto"

# Vocabulario REAL del inventario, el del CHECK del DDL. Exacto y en mayúsculas: aceptar
# minúsculas sería admitir filas que la base no puede contener, y callar la deriva el día
# que alguien relaje el constraint.
_OPERACION: dict[str, Operation] = {
    "VENTA": Operation.SALE,
    "ARRIENDO": Operation.RENT,
}

_SIN_DESTINO_EN_OPERACION = frozenset({"MONITOREO_PASIVO"})
"""Existe en el inventario y NO tiene valor en `Operation`. No es un dato corrupto: es una
operación que el contrato no modela. Se declara, no se aproxima a arriendo."""

_DISPONIBILIDAD_DIRECTA: dict[str, Availability] = {
    "ACTIVO": Availability.AVAILABLE,
}
"""Estados cuya traducción NO depende de la operación. `'COMPLETADO'` no está aquí a
propósito — ver `_disponibilidad_de`."""

_ESTADO_COMPLETADO = "COMPLETADO"
"""El inventario cierra con una sola palabra los dos finales posibles, y el contrato solo
modela uno. Ver `_disponibilidad_de`: es la razón de que la disponibilidad necesite saber
qué operación se estaba ofreciendo."""

_SIN_DESTINO_EN_DISPONIBILIDAD = frozenset({"PAUSADO"})
"""`Availability` no tiene «pausado». `unknown` es lo más cerca que se puede estar sin
mentir, pero se dice por qué: si no, un anuncio pausado sería indistinguible de uno cuyo
estado nadie conoce."""

_LLAVES_QUE_NO_SON_ATRIBUTOS = frozenset({"fotos"})
"""`fotos` no es un atributo del inmueble: es media, y tiene su sitio en el contrato."""

_COLUMNAS_PROPIAS_COMO_ATRIBUTOS = ("tipo_activo", "piso_altura")
"""Columnas de primera clase que describen el activo físico. Van a `attributes` porque el
contrato no les da campo propio, y GANAN sobre el JSONB si ambos traen la misma llave: una
columna con CHECK es mejor dato que una llave sin tipar."""


# ── La frontera de lectura ────────────────────────────────────────────────────────
#
# UN solo sitio habla con la base. Las columnas que el ensamblador lee tienen que estar
# TODAS aquí, y hay una prueba que lo verifica leyendo el AST en vez del texto.

_SELECT_ACTIVOS = """
    SELECT
        a.id,
        ST_Y(a.geom) AS lat,
        ST_X(a.geom) AS lon,
        a.direccion_estandarizada,
        a.tipo_activo,
        a.piso_altura,
        a.imagen_url,
        a.caracteristicas,
        t.tipo_operacion,
        t.precio,
        t.estado_anuncio,
        t.fecha_publicacion,
        t.fecha_cierre
    FROM activos_inmutables a
    LEFT JOIN LATERAL (
        SELECT tipo_operacion, precio, estado_anuncio, fecha_publicacion, fecha_cierre
        FROM transacciones_temporales tt
        WHERE tt.activo_id = a.id
        ORDER BY tt.fecha_publicacion DESC
        LIMIT 1
    ) t ON true
"""
"""El listing MÁS RECIENTE, sea cual sea su estado — a diferencia de las consultas de
tarjetas, que filtran a `'ACTIVO'`. Aquí el estado no se filtra: se traduce. Un anuncio
completado sigue siendo un hecho sobre el inmueble, y esconderlo convertiría
`availability` en un campo que solo puede valer `available`."""

_FILTRO_POR_IDS = " WHERE a.id::text = ANY(:ids)"


async def leer_activos_locales(ids: list[str] | None = None) -> list[dict]:
    """LA ÚNICA FRONTERA CON LA BASE. Recupera filas crudas; no interpreta nada.

    Sin `ids`, el inventario entero. No devuelve contratos a propósito: quien lee no decide
    la moneda ni el instante de recepción, y mezclarlo obligaría a esta función a conocer
    política que no le toca.
    """
    consulta = _SELECT_ACTIVOS + (_FILTRO_POR_IDS if ids is not None else "")
    parametros = {"ids": ids} if ids is not None else {}
    async with AsyncSessionLocal() as db:
        filas = (await db.execute(text(consulta), parametros)).mappings().all()
    return [dict(f) for f in filas]


# ── El contexto que el ensamblador NO puede deducir ───────────────────────────────


@dataclass(frozen=True)
class ContextoDeLectura:
    """Lo que la fila no dice y el contrato exige. Se declara fuera, no se adivina dentro.

    Falla al construirse y no al ensamblar: un contexto mal formado es un error del
    llamador, y descubrirlo cuarenta filas después esconde de quién es la culpa.
    """

    snapshot_at: datetime
    """Cuándo leímos nosotros. Va a `provenance.received_at`, que es obligatorio. Con zona:
    un instante sin zona significa una cosa en Quito y otra en el runner."""

    moneda: str
    """ISO-4217. Obligatoria y sin default — ver §2 de la cabecera del módulo."""

    def __post_init__(self) -> None:
        if self.snapshot_at.tzinfo is None:
            raise ValueError(
                "snapshot_at debe traer zona horaria: es el único instante que este "
                "adaptador afirma, y afirmarlo sin zona sería el mismo error que se evita "
                "al omitir los timestamps naive de la fila"
            )
        if not re.fullmatch(r"[A-Z]{3}", self.moneda):
            raise ValueError(
                f"moneda debe ser un código ISO-4217 de tres letras en mayúsculas; "
                f"llegó {self.moneda!r}. El inventario no tiene columna de moneda y este "
                "adaptador no la inventa: la declara quien lee"
            )


# ── El ensamblador. PURO ──────────────────────────────────────────────────────────


def _caracteristicas_de(fila: Mapping[str, Any], avisos: list[str]) -> dict:
    """El JSONB, degradado con ruido si no es un objeto. Nunca revienta.

    `caracteristicas` llega como dict o como texto según el driver, y un JSON válido que no
    sea objeto (`5`, `[1,2]`, `true`, `"5"`) es un caso REAL del que el repositorio ya se
    guarda en tres sitios. Degradar en silencio dejaría un inmueble sin atributos
    indistinguible de uno que no los tiene.
    """
    crudo = fila.get("caracteristicas")
    if crudo is None:
        return {}
    if isinstance(crudo, (str, bytes)):
        try:
            crudo = json.loads(crudo)
        except (ValueError, TypeError):
            avisos.append(
                "`caracteristicas` traía texto que no es JSON válido: se descartó entero "
                "y este inmueble va sin los atributos del JSONB"
            )
            return {}
    if not isinstance(crudo, dict):
        avisos.append(
            f"`caracteristicas` no es un objeto JSON (llegó {type(crudo).__name__}): se "
            "descartó entero y este inmueble va sin los atributos del JSONB"
        )
        return {}
    return crudo


def _atributos_de(fila: Mapping[str, Any], caracteristicas: dict,
                  avisos: list[str]) -> tuple[PropertyAttribute, ...]:
    """Columnas propias + JSONB, sin precios y ordenados.

    Quién decide que una llave es un precio: EL CONTRATO. No se duplica su lista aquí —una
    segunda copia se desincronizaría y la regla dejaría de ser una—. Se le ofrece la llave
    sola; si la rechaza, es un precio.
    """
    candidatos: dict[str, Any] = {}
    for columna in _COLUMNAS_PROPIAS_COMO_ATRIBUTOS:
        if fila.get(columna) is not None:
            candidatos[columna] = fila[columna]

    for llave, valor in caracteristicas.items():
        llave = str(llave)
        if llave in _LLAVES_QUE_NO_SON_ATRIBUTOS:
            continue
        if llave in candidatos:
            avisos.append(
                f"`caracteristicas.{llave}` repite una columna del activo: se conservó la "
                "columna, que es el dato con restricción"
            )
            continue
        candidatos[llave] = valor

    atributos: list[PropertyAttribute] = []
    for llave in sorted(candidatos):          # orden = función del dato, no del driver
        try:
            PropertyAttribute(key=llave)
        except ValidationError:
            avisos.append(
                f"la llave {llave!r} es un campo de precio y no puede ser atributo: el "
                "precio vive solo en transaction.price"
            )
            continue
        try:
            atributos.append(PropertyAttribute(key=llave, value=candidatos[llave]))
        except ValidationError:
            avisos.append(
                f"el atributo {llave!r} llegó con un valor no representable "
                f"({type(candidatos[llave]).__name__}) y se descartó"
            )
    return tuple(atributos)


def _media_de(fila: Mapping[str, Any], caracteristicas: dict, avisos: list[str]) -> Media:
    urls: list[str] = []
    portada = fila.get("imagen_url")
    if isinstance(portada, str):
        urls.append(portada)

    fotos = caracteristicas.get("fotos")
    if isinstance(fotos, list):
        urls.extend(f for f in fotos if isinstance(f, str))
    elif fotos is not None:
        avisos.append(
            f"`caracteristicas.fotos` no es una lista (llegó {type(fotos).__name__}): se "
            "descartó"
        )

    # `dict.fromkeys` deduplica CONSERVANDO el orden — un `set` lo haría no determinista.
    limpias = tuple(dict.fromkeys(u.strip() for u in urls if u.strip()))
    return Media(images=limpias)


def _instante(valor: Any, columna: str, avisos: list[str]) -> datetime | None:
    """Un instante de la fila, o nada. Nunca se le pone zona a lo que no la trae."""
    if valor is None:
        return None
    if getattr(valor, "tzinfo", None) is None:
        avisos.append(
            f"`{columna}` llegó sin zona horaria y se omite: la columna es TIMESTAMP sin "
            "zona, y suponerle UTC sería afirmar un dato que nadie declaró"
        )
        return None
    return valor


def _disponibilidad_de(estado_crudo: Any, operacion: Operation,
                       avisos: list[str]) -> Availability:
    """El estado del anuncio. Depende de la OPERACIÓN, y esa asimetría no es un detalle.

    El inventario cierra un anuncio con una sola palabra —`'COMPLETADO'`— para los dos
    finales posibles, y el contrato solo modela uno: `Availability.SOLD` significa vendido.
    Traducir `COMPLETADO → sold` sin mirar la operación afirma que se vendió un inmueble
    que en realidad se **arrendó**, y ese es exactamente el tipo de mentira bien tipada que
    pasa todas las validaciones: el objeto es válido, el dato es falso.

        VENTA + COMPLETADO      → sold      (la venta se cerró: eso SÍ es lo que dice)
        ARRIENDO + COMPLETADO   → unknown   + aviso

    Por qué `unknown` y no otra cosa en el segundo caso: `sold` mentiría; `reserved`
    inventaría un estado que nadie declaró; y ampliar `Availability` con un `rented` sería
    cambiar un contrato congelado desde una unidad de adaptador. `unknown` es lo único que
    no afirma de más — pero **no entra callado**, porque un arriendo cerrado y un anuncio
    del que no se sabe nada no son lo mismo, y el aviso es lo único que los distingue.
    """
    if estado_crudo is None:
        avisos.append(
            "`estado_anuncio` es NULL: el listing no declara estado. Se registra unknown "
            "en vez de asumir que está activo"
        )
        return Availability.UNKNOWN

    if estado_crudo == _ESTADO_COMPLETADO:
        if operacion is Operation.SALE:
            return Availability.SOLD
        avisos.append(
            f"`estado_anuncio` = {_ESTADO_COMPLETADO!r} sobre una operación de "
            f"{operacion.value}: el inventario solo declara «completado» y el contrato no "
            "tiene un estado equivalente a «arrendado». Se registra unknown, porque `sold` "
            "afirmaría una venta que no ocurrió y `reserved` inventaría un estado que "
            "nadie declaró"
        )
        return Availability.UNKNOWN

    if estado_crudo in _SIN_DESTINO_EN_DISPONIBILIDAD:
        avisos.append(
            f"`estado_anuncio` = {estado_crudo!r} existe en el inventario pero el contrato "
            "no tiene ese valor: unknown es lo más cerca sin mentir"
        )
        return Availability.UNKNOWN

    directa = _DISPONIBILIDAD_DIRECTA.get(estado_crudo)
    if directa is None:
        avisos.append(
            f"`estado_anuncio` = {estado_crudo!r} no está en el vocabulario del "
            "inventario: unknown en vez de aproximar"
        )
        return Availability.UNKNOWN
    return directa


def _transaccion_de(fila: Mapping[str, Any], contexto: ContextoDeLectura,
                    avisos: list[str]) -> Transaction | None:
    """El listing, o `None` — que es un estado normal, no un dato incompleto."""
    operacion_cruda = fila.get("tipo_operacion")
    if operacion_cruda is None:
        return None                      # sin listing: no hay nada que declarar

    operacion = _OPERACION.get(operacion_cruda)
    if operacion is None:
        if operacion_cruda in _SIN_DESTINO_EN_OPERACION:
            avisos.append(
                f"`tipo_operacion` = {operacion_cruda!r} existe en el inventario pero no "
                "tiene valor en el contrato (Operation solo admite venta y arriendo): la "
                "transacción se omite entera en vez de aproximarla"
            )
        else:
            avisos.append(
                f"`tipo_operacion` = {operacion_cruda!r} no está en el vocabulario del "
                "inventario ('VENTA', 'ARRIENDO', 'MONITOREO_PASIVO'): la transacción se "
                "omite en vez de adivinar la operación"
            )
        return None

    precio = fila.get("precio")
    importe: Money | None = None
    if precio is None:
        avisos.append("el listing no declara precio")
    else:
        try:
            importe = Money(amount=Decimal(str(precio)), currency=contexto.moneda)
        except (ValidationError, InvalidOperation, ValueError):
            avisos.append(
                f"el precio {precio!r} no es un importe representable (el contrato exige "
                "un decimal positivo): se omite el precio, no la transacción"
            )

    return Transaction(
        operation=operacion,
        price=importe,
        availability=_disponibilidad_de(fila.get("estado_anuncio"), operacion, avisos),
        listed_at=_instante(fila.get("fecha_publicacion"), "fecha_publicacion", avisos),
        closed_at=_instante(fila.get("fecha_cierre"), "fecha_cierre", avisos),
    )


def ensamblar_property_context(fila: Mapping[str, Any],
                               contexto: ContextoDeLectura) -> PropertyContextV0:
    """Una fila del inventario propio → `PropertyContextV0`. PURA y determinista.

    Sin red, sin reloj, sin configuración: dado el mismo par *(fila, contexto)*, el mismo
    objeto y el mismo JSON. Lo que la fila no puede sostener no se rellena — se omite y se
    declara en `quality.warnings`.
    """
    avisos: list[str] = []
    caracteristicas = _caracteristicas_de(fila, avisos)

    return PropertyContextV0(
        property_id=str(fila["id"]),
        # Identidad externa del inventario propio. Constantes, no datos de la fila: no hay
        # columna de proveedor, y esta unidad tiene prohibido crearla.
        provider_id=PROVIDER_ID_LOCAL,
        provider_type=PROVIDER_TYPE_CONTEXTO,
        provider_listing_url=None,      # no existe la columna
        location=Location(
            lat=fila.get("lat"),
            lon=fila.get("lon"),
            address=fila.get("direccion_estandarizada"),
        ),
        attributes=_atributos_de(fila, caracteristicas, avisos),
        transaction=_transaccion_de(fila, contexto, avisos),
        media=_media_de(fila, caracteristicas, avisos),
        provenance=PropertyProvenanceV0(
            # `unknown` mientras la fuente no demuestre otra cosa. Ver §4 de la cabecera.
            inventory_class=InventoryClass.UNKNOWN,
            received_at=contexto.snapshot_at,
            last_updated_at=None,       # el inventario no declara cuándo se actualizó
            evidence=(),                # ver §5: no se fabrica procedencia
        ),
        quality=Quality(
            completeness=None,          # nadie la calcula hoy: None, no 0.0
            warnings=tuple(avisos),
        ),
    )
