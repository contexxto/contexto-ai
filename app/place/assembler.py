"""El ensamblaje PURO de Place: material recolectado → `PlaceContextV0` (PLAN04-2.2).

Este modulo no habla con nadie. No abre sockets, no consulta la base, no mira el reloj y
no llama a ningun proveedor: recibe una `MateriaDeZona` ya recolectada y devuelve el
objeto. Esa es toda su responsabilidad, y es lo que permite probarlo en un interprete
donde `httpx` y `app.database` no se han importado siquiera.

DE DONDE VIENE. El bloque se escribio en `app/rutas.py` durante PLAN04-1.2 y aqui se
MUEVE, no se copia: en `rutas.py` no queda una segunda implementacion, solo una fachada
que liga el mismo objeto, de modo que `rutas.X is assembler.X`. Los consumidores
historicos siguen funcionando sin tocar ni un import.

QUE SE MOVIO Y POR QUE. El conjunto no se eligio por contiguidad sino por el cierre
transitivo de dependencias de `ensamblar_place_context`, comprobado con el AST: quince
simbolos, todos puros. Dos exclusiones que la contiguidad habria arrastrado y la
dependencia rechaza:

  · `_recolectar_zona` — es EL fetch. Async, toca red y base, y lee el reloj. Se queda.
  · `place_context_de` — es `async` y espera al fetch. Se queda.

Y una inclusion que la contiguidad no habria visto: `_nombre_limpio`, que vive lejos en el
fichero pero lo llaman `_medir_transporte` y `_medir_servicios`. Es puro, asi que viene; y
`rutas.py` lo recupera por la fachada porque su prosa tambien lo usa.

LO QUE ESTE MODULO NO ES. No es un paquete de proveedores: `app/place/providers/` no
existe todavia y esta unidad no lo abre. Tampoco decide que dimensiones pedir —eso es el
selector de 2.3—. Aqui solo se ensambla lo que ya se trajo.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.contracts.evidence_v0 import EvidenceRefV0, PersistencePolicy, SourceType
from app.contracts.place_v0 import (
    GeoPoint,
    MeasureStatus,
    NamedMeasureV0,
    NearbyPlaceV0,
    NearestTransitV0,
    PlaceContextV0,
    PlaceMeasureV0,
)


def _nombre_limpio(n: str | None, max_len: int = 42) -> str:
    """Recorta nombres kilométricos de Google (corta en separadores y por longitud)."""
    if not n:
        return "este lugar"
    # Google a veces devuelve "Nombre | keyword SEO | keyword | …": nos quedamos con lo 1ro.
    for sep in (" | ", " - ", " — ", " · ", ", "):
        if sep in n:
            n = n.split(sep)[0].strip()
            break
    n = n.strip()
    if len(n) > max_len:
        n = n[:max_len].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return n or "este lugar"


@dataclass(frozen=True)
class MateriaDeZona:
    """Lo que devolvió el ÚNICO fetch, sin interpretar.

    Existe para separar «lo que se recuperó» de «lo que se afirma». Mientras esto era
    variables locales dentro de `analizar_zona`, la única forma de probar el ensamblaje
    era hacer red.
    """

    lat: float
    lon: float
    lugar: dict
    walk: dict
    """`{}` cuando `walk_score_para` devolvió None — Overpass no respondió. Distinto de
    un dict con `pois_analizados=0`, que es Overpass respondiendo que no hay nada."""
    servicios: list[dict]
    se_consultaron_servicios: bool
    """Hubo llave de Google y se preguntó. Sin esto, «cero servicios» y «no se preguntó»
    serían indistinguibles, que es justo la confusión que el contrato prohíbe."""
    transporte: dict | None
    transporte_distancia_m: int | float | None
    transporte_minutos: int | float | None
    transporte_ruta_medida: bool
    """True = caminata real por calles (Google Routes). False = estimación recta ÷ 80."""
    recuperado_en: datetime


# ── La identidad de la evidencia ─────────────────────────────────────────────
#
# `EvidenceRefV0.evidence_id` cae por defecto en un `uuid4`, y ese default es correcto
# para quien crea evidencia suelta. Aquí no sirve: dos ensamblajes del MISMO material
# producían dos objetos que solo se diferenciaban en las asas, así que «el objeto es el
# mismo» dejaba de ser comprobable —no se podía comparar el JSON— y cualquier consumidor
# que cachee o compare por serialización veía cambios donde no los hay.
#
# Tampoco vale `hash()`: `PYTHONHASHSEED` sala el hash de las cadenas en cada proceso, de
# modo que dos corridas darían asas distintas para el mismo contenido. Se usa `uuid5`, que
# es la misma solución que `app/buyer/reductor.py` ya tomó para la evidencia declarada.
#
# QUÉ ENTRA EN LA IDENTIDAD, y por qué cada pieza:
#
#   · el PUNTO — sin él, dos lugares distintos con la misma metodología compartirían
#     `evidence_id`, y `DecisionContextV0` resuelve sus referencias por ese id: la
#     colisión no sería cosmética, sería citar la evidencia de otro lugar.
#   · el INSTANTE de recuperación — dos lecturas distintas son dos evidencias distintas
#     aunque digan lo mismo; el id no debe fingir que son una sola.
#   · la DIMENSIÓN que respalda — la misma consulta acredita cosas distintas.
#   · el ORIGEN y el CONTENIDO — proveedor, metodología y limitaciones.
#
# NO entra el valor medido, por la misma razón que en el reductor de Buyer: si dos
# lecturas iguales produjeran valores distintos, queremos el mismo id y dos objetos
# distintos, para que la divergencia se vea en vez de esconderse tras dos asas.
_NAMESPACE_EVIDENCIA_LUGAR = uuid.uuid5(
    uuid.NAMESPACE_URL, "contexto.ai/place/evidence/v0"
)


def _identidad_evidencia(materia: MateriaDeZona, dimension: str, campos: dict) -> str:
    """`uuid5` sobre *(punto, instante, dimensión, origen, contenido)*. Determinista."""
    tipo = campos["source_type"]
    semilla = "\x1f".join((
        repr(materia.lat),
        repr(materia.lon),
        materia.recuperado_en.isoformat(),
        dimension,
        tipo.value if isinstance(tipo, SourceType) else str(tipo),
        campos.get("provider") or "",
        campos.get("source_id") or "",
        campos.get("methodology") or "",
        "\x1e".join(campos.get("limitations") or ()),
    ))
    return str(uuid.uuid5(_NAMESPACE_EVIDENCIA_LUGAR, semilla))


def _evidencia(materia: MateriaDeZona, *, dimension: str, **campos) -> EvidenceRefV0:
    """Toda evidencia de esta unidad es de una lectura en vivo: se usa y se tira."""
    campos.setdefault("persistence_policy", PersistencePolicy.RUNTIME_ONLY)
    campos.setdefault("observed_at", None)
    return EvidenceRefV0(
        evidence_id=_identidad_evidencia(materia, dimension, campos),
        retrieved_at=materia.recuperado_en,
        **campos,
    )


# ── De dónde salió cada POI, LEÍDO del dato ──────────────────────────────────
#
# `_servicios_con_coords` mezcla DOS orígenes en una sola lista y lo marca uno por uno en
# `fuente`: `"propio"` es nuestra capa (`pois_propios`, PostGIS) y `"google"` es el relleno
# de Google Places para las categorías que la capa no cubre en ese punto.
#
# Hasta PLAN04-1.2-R1 la lista entera se acreditaba a Google Places. Es decir: un
# supermercado de nuestra propia capa —el foso— se atribuía a un tercero, y con la llave
# de Google ausente se seguía afirmando lo mismo. Es el defecto de E0.3 otra vez, con otra
# ropa: la procedencia viajaba como convención (el nombre de la función) en vez de leerse
# del dato, que es quien la sabe.
_ORIGEN_DE_LA_CAPA_DE_POIS: dict[str, tuple[SourceType, str]] = {
    "propio": (SourceType.OWN_MEASUREMENT, "contexto-capa-propia"),
    "google": (SourceType.PROVIDER_API, "google-places"),
}

_METODO_SERVICIO = {
    "propio": ("servicio más cercano por categoría en la capa propia de POIs, con la "
               "distancia calculada en PostGIS desde el punto consultado"),
    "google": ("servicio más cercano por categoría según Google Places, usado solo para "
               "las categorías que la capa propia no cubre en este punto"),
}

_METODO_PARADA = {
    "propio": ("parada más cercana en la capa propia de POIs, priorizando el hub masivo "
               "aunque otra parada esté más cerca"),
    "google": "parada de transporte más cercana según Google Places",
}

_SIN_ORIGEN_DECLARADO = (
    "la capa de POIs devolvió el dato sin declarar su origen: su procedencia no se puede "
    "acreditar, y un valor sin procedencia no se presenta como disponible"
)


def _evidencia_de_poi(materia: MateriaDeZona, *, dimension: str, fuente,
                      metodos: dict[str, str]) -> EvidenceRefV0 | None:
    """La procedencia de un POI, derivada de su campo `fuente`.

    Devuelve `None` cuando `fuente` no es una de las que la capa produce. NO se inventa un
    origen por defecto: eso es exactamente lo que se vino a cerrar. Quien llama decide qué
    hacer si eso deja la medida sin ninguna evidencia — y el contrato ya dice qué: sin
    procedencia no hay valor disponible.
    """
    origen = _ORIGEN_DE_LA_CAPA_DE_POIS.get(fuente or "")
    if origen is None:
        return None
    tipo, proveedor = origen
    return _evidencia(materia, dimension=dimension, source_type=tipo, provider=proveedor,
                      methodology=metodos[fuente])


def _medir_caminabilidad(materia: MateriaDeZona) -> PlaceMeasureV0[float]:
    """La procedencia de E0.3, hecha estructura. TRES casos, y ninguno se confunde.

      1. el proveedor no respondió       → insufficient_evidence, sin valor
      2. respondió y no había ni un POI  → available, valor 0, con evidencia y con la
                                           limitación de cobertura
      3. respondió con POIs              → available, con el valor calculado

    EL CASO 2 ES EL QUE COSTÓ UNA ADJUDICACIÓN. La tentación es tratarlo como ausencia
    de dato, y es lo contrario: la consulta se hizo, la respuesta llegó, y el cálculo
    sobre esa respuesta da 0. Eso ES una medición —«miramos OSM alrededor de este punto
    y la consulta no devolvió POIs relevantes»— y borrarla perdería información real.
    Decir «no hay nada caminable» sería otra cosa: una afirmación sobre el barrio que
    este dato no sostiene.

    Lo que sí exige es declarar QUÉ no puede sostener: un 0 por cobertura nula no
    distingue «zona sin comercios» de «zona que OSM no tiene mapeada», y confundirlas
    penalizaría a los barrios peor cartografiados, que suelen ser los más pobres. Esa
    limitación viaja en la medida, no en un comentario.

    El caso 1 es `insufficient_evidence` y no `unknown` porque la dimensión SÍ se evaluó:
    se preguntó y no hubo respuesta. `unknown` diría que ni se intentó.

    DOS EVIDENCIAS, NO UNA (PLAN04-1.2-R1). El puntaje no lo publica OSM: lo calcula
    Contexto sobre insumos de OSM. Fundirlo en una sola referencia con
    `provider="overpass"` atribuía nuestro método al proveedor de los datos —y borraba
    de paso que el método es nuestro—. Van separadas: el cálculo es `own_measurement` de
    Contexto, los insumos son el dataset público consultado por Overpass.
    """
    if not materia.walk:
        return PlaceMeasureV0[float](
            status=MeasureStatus.INSUFFICIENT_EVIDENCE,
            limitations=(
                "la capa de POIs no respondió: se consultó y no hubo lectura sobre la "
                "que calcular nada",
            ),
        )

    valor = materia.walk.get("walk_score")
    if valor is None:
        return PlaceMeasureV0[float](
            status=MeasureStatus.INSUFFICIENT_EVIDENCE,
            limitations=("la respuesta llegó sin puntaje de caminabilidad",),
        )

    pois = materia.walk.get("pois_analizados", 0) or 0
    return PlaceMeasureV0[float](
        status=MeasureStatus.AVAILABLE,
        value=float(valor),
        evidence=(
            _evidencia(
                materia,
                dimension="walkability",
                source_type=SourceType.OWN_MEASUREMENT,
                provider="contexto",
                methodology=(
                    f"walk score calculado por Contexto sobre {pois} POIs, con "
                    "decaimiento por distancia y pesos por categoría"
                ),
            ),
            _evidencia(
                materia,
                dimension="walkability",
                source_type=SourceType.PUBLIC_DATASET,
                provider="overpass",
                methodology=(
                    f"{pois} POIs de OpenStreetMap consultados en vivo por Overpass "
                    "alrededor del punto: son los INSUMOS del cálculo, no el puntaje"
                ),
            ),
        ),
        limitations=() if pois else (
            "cobertura nula: la consulta no devolvió ni un POI, así que este 0 no "
            "distingue una zona sin comercios de una zona que OSM no tiene mapeada",
        ),
    )


def _medir_transporte(materia: MateriaDeZona) -> PlaceMeasureV0[NearestTransitV0]:
    """La parada más cercana, con las DOS procedencias que la producen (PLAN04-1.2-R1).

    Descubrir la parada y medir la caminata hasta ella son dos actos distintos, de dos
    orígenes distintos, y hasta R1 compartían una sola referencia cuyo `provider` iba
    cambiando: cuando Google Routes medía la ruta, la evidencia decía `google-routes` y
    de dónde había salido la parada —a menudo nuestra propia capa— desaparecía. Se
    perdía justo la mitad que acredita el foso.

    Ahora el descubrimiento siempre está, leído de `fuente`, y la de Routes se añade
    SOLO cuando midió de verdad. Que la de Routes exista o no es, además, la única señal
    estructural de si `distance_m` es una caminata por calles o una línea recta.
    """
    t = materia.transporte
    if not t:
        if not materia.se_consultaron_servicios:
            return PlaceMeasureV0[NearestTransitV0](
                status=MeasureStatus.UNKNOWN,
                limitations=("no se consultó el proveedor de servicios",),
            )
        return PlaceMeasureV0[NearestTransitV0](
            status=MeasureStatus.INSUFFICIENT_EVIDENCE,
            limitations=("se consultó y no apareció ninguna parada de transporte",),
        )

    descubrimiento = _evidencia_de_poi(
        materia, dimension="nearest_transit", fuente=t.get("fuente"),
        metodos=_METODO_PARADA,
    )
    ruta = _evidencia(
        materia,
        dimension="nearest_transit",
        source_type=SourceType.PROVIDER_API,
        provider="google-routes",
        methodology=(
            "caminata real por calles hasta la parada, medida con Google Routes; de "
            "aquí salen la distancia y la duración cuando la medición existe"
        ),
    ) if materia.transporte_ruta_medida else None

    evidencia = tuple(e for e in (descubrimiento, ruta) if e is not None)
    if not evidencia:
        return PlaceMeasureV0[NearestTransitV0](
            status=MeasureStatus.INSUFFICIENT_EVIDENCE,
            limitations=(_SIN_ORIGEN_DECLARADO,),
        )

    # `mode` recoge la ÚNICA distinción que la capa de POIs expone en esta costura:
    # masivo (metro, estación, terminal) frente a parada. Escribir "metro" aquí sería
    # inventar precisión: una terminal terrestre no es un metro.
    masivo = bool(t.get("es_masivo", False))
    return PlaceMeasureV0[NearestTransitV0](
        status=MeasureStatus.AVAILABLE,
        value=NearestTransitV0(
            distance_m=float(materia.transporte_distancia_m),
            mode="masivo" if masivo else "parada",
            name=_nombre_limpio(t["nombre"]),
        ),
        evidence=evidencia,
    )


def _medir_minutos_a_pie(materia: MateriaDeZona) -> NamedMeasureV0 | None:
    """Los minutos a pie hasta la parada.

    Van en `environment` y NO en `travel_to_anchors`: ese campo declara, por contrato,
    el trayecto hasta un ancla DEL COMPRADOR, correlacionado por `anchor_id`. Una parada
    de bus no es un ancla de nadie, y meterla ahí colonizaría con Place una costura que
    el contrato reserva para Buyer.

    Aquí la procedencia sí distingue lo medido de lo estimado, que en la prosa de hoy es
    invisible: «19 min a pie» se lee igual venga de Google Routes o de dividir la recta
    entre 80.
    """
    if materia.transporte_minutos is None:
        return None
    medida = materia.transporte_ruta_medida
    return NamedMeasureV0(
        dimension="transporte_minutos_a_pie",
        measure=PlaceMeasureV0[float](
            status=MeasureStatus.AVAILABLE,
            value=float(materia.transporte_minutos),
            evidence=(
                _evidencia(
                    materia,
                    dimension="transporte_minutos_a_pie",
                    source_type=(SourceType.PROVIDER_API if medida
                                 else SourceType.HEURISTIC_ESTIMATE),
                    provider="google-routes" if medida else None,
                    methodology=("duración peatonal por calles según Google Routes"
                                 if medida else "distancia en línea recta dividida entre 80 m/min"),
                    limitations=() if medida else (
                        "estimación en línea recta: ignora manzanas, desniveles y "
                        "cruces, y en Quito subestima de forma sistemática",
                    ),
                ),
            ),
        ),
    )


def _medir_servicios(materia: MateriaDeZona) -> PlaceMeasureV0[tuple]:
    """Los servicios cercanos, con UNA evidencia POR ORIGEN presente (PLAN04-1.2-R1).

    No una por servicio —serían seis referencias diciendo lo mismo— y desde luego no una
    sola para toda la lista, que era lo que atribuía a Google Places los POIs de nuestra
    capa. El origen se lee de `fuente`, servicio por servicio, y se agrupa.
    """
    otros = [s for s in materia.servicios if s.get("cat") != "transporte"]
    if not otros:
        if not materia.se_consultaron_servicios:
            return PlaceMeasureV0[tuple](
                status=MeasureStatus.UNKNOWN,
                limitations=("no se consultó el proveedor de servicios",),
            )
        return PlaceMeasureV0[tuple](
            status=MeasureStatus.INSUFFICIENT_EVIDENCE,
            limitations=("se consultó y no apareció ningún servicio cercano",),
        )

    # `sorted` sobre el conjunto: dos ensamblajes del mismo material tienen que producir
    # la misma tupla en el mismo orden, o el objeto deja de ser comparable.
    presentes = sorted({(s.get("fuente") or "") for s in otros})
    evidencia = tuple(
        e for e in (
            _evidencia_de_poi(materia, dimension="nearby_places", fuente=f,
                              metodos=_METODO_SERVICIO)
            for f in presentes
        ) if e is not None
    )
    if not evidencia:
        return PlaceMeasureV0[tuple](
            status=MeasureStatus.INSUFFICIENT_EVIDENCE,
            limitations=(_SIN_ORIGEN_DECLARADO,),
        )

    # Los servicios sin origen reconocible SÍ van en el valor —su distancia se midió—
    # pero la medida declara cuántos son. Callarlo dejaría que se leyeran como
    # acreditados por los orígenes que sí están.
    sin_origen = sum(1 for s in otros
                     if (s.get("fuente") or "") not in _ORIGEN_DE_LA_CAPA_DE_POIS)
    return PlaceMeasureV0[tuple](
        status=MeasureStatus.AVAILABLE,
        value=tuple(
            NearbyPlaceV0(
                category=s.get("cat") or "otros",
                distance_m=float(s["distancia_m"]),
                name=_nombre_limpio(s["nombre"]),
            )
            for s in otros
        ),
        evidence=evidencia,
        limitations=() if not sin_origen else (
            f"{sin_origen} de los {len(otros)} servicios llegaron sin origen declarado: "
            "van en el valor porque su distancia sí se midió, pero su procedencia no "
            "está acreditada",
        ),
    )


def ensamblar_place_context(materia: MateriaDeZona) -> PlaceContextV0:
    """La materia recuperada → el objeto. PURA: sin red, sin reloj propio, sin azar.

    Sin azar es literal y es un requisito: dos llamadas con la MISMA `MateriaDeZona`
    producen el mismo JSON byte a byte. Ver §"La identidad de la evidencia".
    """
    minutos = _medir_minutos_a_pie(materia)
    return PlaceContextV0(
        location=GeoPoint(lat=materia.lat, lon=materia.lon),
        assembled_at=materia.recuperado_en,
        walkability=_medir_caminabilidad(materia),
        nearest_transit=_medir_transporte(materia),
        nearby_places=_medir_servicios(materia),
        environment=(minutos,) if minutos else (),
        limitations=(
            "contexto de un punto, no de un inmueble: no incluye nada del activo",
        ),
    )
