"""La clasificación de Contexto, separada de lo que dijo la fuente (SOURCE-CATEGORY, D-1).

EL DEFECTO QUE CIERRA. `pois_propios.categoria` ('supermercado') es una agrupación funcional que
decide la INGESTA (`scripts/foso_pois_spike.py`), no la fuente: Overture `grocery_store` y OSM
`shop=convenience` también acaban en «supermercado». La evidencia de la 041 guardaba esa
categoría colgada de una SOURCE `public_dataset` y no conservaba la de la fuente, así que un
documento afirmaba, en la práctica, «según Overture, supermercado». Aquí se reconstruye la
cadena entera para cada elemento:

    registro → categoría de la fuente → método de Contexto (versionado) → categoría de Contexto

QUÉ CONSERVA LA CAPA, POR DATASET (la columna `pois_propios.categoria_overture`, mal nombrada):
  · Overture → `categories.primary` TAL CUAL (`cat_leaf` en la ingesta). Es el valor de la fuente.
  · OSM      → un SUBTIPO que la ingesta escribe según la PRIMERA etiqueta que casa en su cadena
               (`pull_osm_transporte`): `shop=convenience` → 'minimarket', `shop=supermarket` →
               'supermercado'… NO es el valor de la fuente, pero lo CODIFICA: salvo 'metro', cada
               subtipo sale de UNA sola etiqueta, así que se decodifica sin pérdida a esa etiqueta,
               que el elemento tenía al ingerirse (y que se comprueba contra OSM por su `osm_id`).
               'metro' sale de `railway=subway_entrance` O de `station=subway`: la capa perdió
               cuál, y la categoría de origen queda NULL. No se adivina.

LAS TABLAS SON COPIA CONGELADA DE LA INGESTA, y `tests/test_place_source_category.py` las ata a
ella: carga el script real, ejecuta su clasificador de OSM y compara su `LEAF_TO_CAT`. Si la
ingesta cambia de mapeo, ese test se pone rojo y lo que toca es un MÉTODO NUEVO (v1), no editar
el v0: un documento persistido con `contexto_poi_category_v0` tiene que seguir significando lo
mismo dentro de un año.

LO QUE ESTO NO DECIDE: si «supermercado» es una buena categoría de producto para un minimarket
(D-2, TAXONOMY / PRODUCT CATEGORY QUALITY = OPEN). Solo deja de ocultar qué dijo la fuente.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.contracts.place_evidence_v0 import (
    CategoryAuthority,
    CategoryClassificationV0,
    CategoryMethod,
    SourceCategoryNamespace as NS,
)

# ── contexto_poi_category_v0 ──────────────────────────────────────────────────────
# Overture `categories.primary` → categoría de Contexto. Copia de `CAT_LEAF` /
# `LEAF_TO_CAT` de `scripts/foso_pois_spike.py` a 2026-10-01 (la ingesta del 2026-09-22).
OVERTURE_V0: dict[str, str] = {
    "hospital": "salud", "doctor": "salud", "medical_center": "salud", "urgent_care_clinic": "salud",
    "pharmacy": "farmacia", "drugstore": "farmacia",
    "supermarket": "supermercado", "grocery_store": "supermercado",
    "school": "educacion", "college_university": "educacion", "preschool": "educacion",
    "park": "parque", "playground": "parque",
    "shopping_center": "centro_comercial", "department_store": "centro_comercial",
}

# OSM: subtipo que guarda la capa → (espacio de nombres, valor de la etiqueta, categoría de Contexto).
# El espacio y el valor son la etiqueta EXACTA que casó la cadena de `pull_osm_transporte`.
# `None` = la codificación perdió la etiqueta (dos etiquetas posibles para el mismo subtipo).
OSM_V0: dict[str, tuple[NS | None, str | None, str]] = {
    "pharmacy": (NS.OSM_AMENITY, "pharmacy", "farmacia"),
    "supermercado": (NS.OSM_SHOP, "supermarket", "supermercado"),
    "minimarket": (NS.OSM_SHOP, "convenience", "supermercado"),
    "place_of_worship": (NS.OSM_AMENITY, "place_of_worship", "iglesia"),
    "police": (NS.OSM_AMENITY, "police", "seguridad"),
    "park": (NS.OSM_LEISURE, "park", "parque"),
    "garden": (NS.OSM_LEISURE, "garden", "parque"),
    "metro": (None, None, "transporte"),  # railway=subway_entrance | station=subway
    "estacion_tren": (NS.OSM_RAILWAY, "station", "transporte"),
    "terminal_bus": (NS.OSM_AMENITY, "bus_station", "transporte"),
    "estacion": (NS.OSM_PUBLIC_TRANSPORT, "station", "transporte"),
    "parada_bus": (NS.OSM_HIGHWAY, "bus_stop", "transporte"),
}

# ── contexto_transit_mode_v0 ──────────────────────────────────────────────────────
# Copia de `TRANSPORTE_MASIVO` de la ingesta y de `_TRANSPORTE_MASIVO` de `propia.py`.
MASIVO_V0: frozenset[str] = frozenset({"metro", "estacion_tren", "terminal_bus", "estacion"})

# Las categorías y modos de CONTEXTO. Ningún valor de la fuente puede ser uno de estos: si lo
# fuera, sería que alguien tradujo la categoría de Contexto y la pasó por la de la fuente.
VOCABULARIO_CONTEXTO: frozenset[str] = frozenset(
    {*OVERTURE_V0.values(), *(c for _, _, c in OSM_V0.values()), "masivo", "parada"})


@dataclass(frozen=True)
class Clasificacion:
    """Lo que el escritor necesita: el objeto del contrato, o por qué no se puede construir."""

    objeto: CategoryClassificationV0 | None
    motivo: str | None = None


def _categoria_de_la_fuente(dataset: str | None, en_capa: str | None
                            ) -> tuple[str | None, NS | None, str | None]:
    """(valor de la fuente, espacio de nombres, categoría que le da el método v0).

    La categoría `None` dice que el método v0 NO explica ese valor (no mapeado).
    """
    if dataset == "overture":
        return en_capa, NS.OVERTURE_CATEGORIES_PRIMARY, OVERTURE_V0.get(en_capa)
    if dataset == "osm" and en_capa in OSM_V0:
        ns, valor, categoria = OSM_V0[en_capa]
        return valor, ns, categoria
    return None, None, None


def _objeto(metodo: CategoryMethod, valor: str | None, ns: NS | None) -> CategoryClassificationV0:
    if valor is not None and valor in VOCABULARIO_CONTEXTO:
        # Defensa en profundidad: con las tablas de arriba no puede pasar (lo prueba el test).
        raise ValueError(f"«{valor}» es vocabulario de Contexto, no de la fuente")
    return CategoryClassificationV0(authority=CategoryAuthority.CONTEXTO, method=metodo,
                                    source_category=valor, source_category_namespace=ns)


def clasificar_servicio(s: Mapping) -> Clasificacion:
    """La clasificación de un servicio con la forma de `_servicios_propios`.

      · la capa trae la categoría de origen y el método v0 la convierte EXACTAMENTE en `cat` →
        se declara, con el valor de la fuente tal cual;
      · la capa la trae pero el método v0 no la explica (no mapeada, o mapeada a otra categoría)
        → NO se puede afirmar que la decidió este método: el elemento no se persiste;
      · la capa no la trae (NULL) → la categoría sigue siendo de Contexto, y la de la fuente se
        declara DESCONOCIDA (NULL), no se inventa.
    """
    en_capa, cat = s.get("categoria_capa_origen"), s.get("cat")
    metodo = CategoryMethod.CONTEXTO_POI_CATEGORY_V0
    if en_capa is None:
        return Clasificacion(_objeto(metodo, None, None))
    valor, ns, categoria = _categoria_de_la_fuente(s.get("dataset"), en_capa)
    if categoria is None or categoria != cat:
        return Clasificacion(None, f"«{en_capa}» de {s.get('dataset')} no da «{cat}» con {metodo.value}")
    return Clasificacion(_objeto(metodo, valor, ns))


def clasificar_parada(t: Mapping, modo: str) -> Clasificacion:
    """La clasificación de la parada: `modo` ('masivo' | 'parada') es el que va al documento."""
    en_capa = t.get("categoria_capa_origen")
    metodo = CategoryMethod.CONTEXTO_TRANSIT_MODE_V0
    esperado = "masivo" if en_capa in MASIVO_V0 else "parada"
    if esperado != modo:
        return Clasificacion(None, f"el subtipo «{en_capa}» da «{esperado}», no «{modo}», con {metodo.value}")
    if en_capa is None:
        return Clasificacion(_objeto(metodo, None, None))
    valor, ns, categoria = _categoria_de_la_fuente(t.get("dataset"), en_capa)
    if categoria != "transporte":
        return Clasificacion(None, f"«{en_capa}» de {t.get('dataset')} no es un subtipo de transporte "
                                   f"con {metodo.value}")
    return Clasificacion(_objeto(metodo, valor, ns))
