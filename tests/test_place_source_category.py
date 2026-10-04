"""SOURCE-CATEGORY · D-1 · la evidencia separa la categoría de Contexto de la de la fuente.

El defecto (CANARY SEMANTIC BLOCKER 0.1): el POI 60717 es `grocery_store` en Overture; la ingesta
lo agrupa como «supermercado», y la evidencia de la 041 guardaba `category: "supermercado"`
colgada de una SOURCE de Overture, sin conservar `grocery_store` ni decir que la categoría era
de Contexto. Estas pruebas fijan:

  P · las tablas de `app/place/clasificacion.py` son EXACTAMENTE el mapeo de la ingesta real
      (`scripts/foso_pois_spike.py`, cargado como módulo y ejecutado, sin red);
  M · la matriz de regresión del mandato (Overture, OSM, no mapeada, NULL, no abierta);
  R · el POI 60717, reconstruible de punta a punta;
  C · el contrato;
  §16 · los diez puntos del mandato.

Cero red y cero base: la materia sale de los fixtures de `test_place_provenance_041`.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import inspect
import json
import pathlib

import pytest
from pydantic import ValidationError

import app.place.clasificacion as clasificacion
import app.place.providers.propia as propia
from app.contracts.evidence_v0 import SourceType
from app.contracts.place_evidence_v0 import (
    CategoryAuthority,
    CategoryClassificationV0,
    CategoryMethod,
    NearbyPlacesEvidenceV0,
    NearestTransitEvidenceV0,
    SourceCategoryNamespace,
)
from app.place.clasificacion import MASIVO_V0, OSM_V0, OVERTURE_V0, VOCABULARIO_CONTEXTO
from app.place.legado import con_contexto_vigente
from app.place.persistible import formatear_conectividad, formatear_servicios, leer_contexto_persistido
from tests.test_place_provenance_041 import LAT, LON, _docs, _poi, _transporte

RAIZ = pathlib.Path(__file__).resolve().parent.parent
POI = SourceCategoryNamespace
V0 = CategoryMethod.CONTEXTO_POI_CATEGORY_V0
MODO_V0 = CategoryMethod.CONTEXTO_TRANSIT_MODE_V0


@pytest.fixture(scope="module")
def foso():
    """La ingesta REAL, cargada como módulo (igual que `tests/test_overture_release.py`)."""
    spec = importlib.util.spec_from_file_location("foso_pois_spike", RAIZ / "scripts" / "foso_pois_spike.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _servicio(docs, poi_id):
    return next(i for i in docs["servicios"].items if i.place.poi_id == str(poi_id))


def _fuente(doc, item):
    return next(e for e in doc.evidence if e.evidence_id == item.source_evidence_id)


# ══ P · las tablas son la ingesta real ════════════════════════════════════════════
def test_P1_overture_es_exactamente_el_leaf_to_cat_de_la_ingesta(foso):
    assert OVERTURE_V0 == foso.LEAF_TO_CAT


# Una etiqueta de clasificación por elemento: así cada subtipo que emita la ingesta tiene UNA causa.
_ETIQUETAS_OSM = [
    ("amenity", "pharmacy"), ("shop", "supermarket"), ("shop", "convenience"),
    ("amenity", "place_of_worship"), ("amenity", "police"), ("leisure", "park"), ("leisure", "garden"),
    ("railway", "subway_entrance"), ("station", "subway"), ("railway", "station"),
    ("amenity", "bus_station"), ("public_transport", "station"), ("highway", "bus_stop"),
]


def _corre_ingesta_osm(foso, monkeypatch):
    """`pull_osm_transporte` REAL sobre elementos sintéticos, con `requests.post` sustituido."""
    elementos = [{"type": "node", "id": n, "lat": -0.2, "lon": -78.5, "tags": {k: v, "name": f"Lugar {n}"}}
                 for n, (k, v) in enumerate(_ETIQUETAS_OSM, start=1)]

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            # Como toda respuesta REAL de Overpass, declara su instantánea (`osm3s`): sin ella, la OSM SNAPSHOT
            # FRESHNESS GUARD rechaza el espejo por inverificable (D-OSM-1).
            return {"osm3s": {"timestamp_osm_base": "2026-10-02T14:53:35Z", "copyright": "ODbL"},
                    "elements": copy.deepcopy(elementos)}

    monkeypatch.setattr(foso.requests, "post", lambda *a, **k: _Resp())
    filas = foso.pull_osm_transporte()
    return {f["osm_id"]: f for f in filas}, {f"node/{e['id']}": next(iter(
        (k, v) for k, v in e["tags"].items() if k != "name")) for e in elementos}


def test_P2_osm_se_decodifica_a_la_etiqueta_exacta_que_caso_la_ingesta(foso, monkeypatch):
    filas, etiqueta = _corre_ingesta_osm(foso, monkeypatch)
    assert len(filas) == len(_ETIQUETAS_OSM), "la ingesta descartó un elemento: la prueba no mediría nada"
    for osm_id, f in filas.items():
        ns, valor, categoria = OSM_V0[f["cat_leaf"]]
        assert categoria == f["categoria"], (osm_id, f)
        if ns is not None:
            assert (ns.value, valor) == (f"osm:{etiqueta[osm_id][0]}", etiqueta[osm_id][1]), (osm_id, f)


def test_P3_la_tabla_osm_cubre_exactamente_los_subtipos_que_emite_la_ingesta(foso, monkeypatch):
    filas, _ = _corre_ingesta_osm(foso, monkeypatch)
    assert set(OSM_V0) == {f["cat_leaf"] for f in filas.values()}


def test_P4_metro_es_la_unica_perdida_y_por_eso_queda_NULL(foso, monkeypatch):
    """Dos etiquetas distintas dan el mismo subtipo: la capa no puede decir cuál fue."""
    filas, etiqueta = _corre_ingesta_osm(foso, monkeypatch)
    causas = {}
    for osm_id, f in filas.items():
        causas.setdefault(f["cat_leaf"], set()).add(etiqueta[osm_id])
    ambiguos = {sub for sub, cs in causas.items() if len(cs) > 1}
    assert ambiguos == {"metro"}
    assert OSM_V0["metro"][:2] == (None, None)
    assert all(OSM_V0[s][0] is not None for s in OSM_V0 if s not in ambiguos)


def test_P5_masivo_es_el_mismo_en_la_ingesta_la_capa_y_la_clasificacion(foso):
    assert MASIVO_V0 == set(foso.TRANSPORTE_MASIVO) == set(propia._TRANSPORTE_MASIVO)


def test_P6_ningun_valor_de_la_fuente_es_vocabulario_de_contexto():
    """Si lo fuera, alguien habría traducido la categoría de Contexto y la habría pasado por la
    de la fuente: exactamente el defecto D-1."""
    valores = set(OVERTURE_V0) | {v for _, v, _ in OSM_V0.values() if v is not None}
    assert not valores & VOCABULARIO_CONTEXTO
    with pytest.raises(ValueError, match="vocabulario de Contexto"):
        clasificacion._objeto(V0, "supermercado", POI.OVERTURE_CATEGORIES_PRIMARY)


# ══ M · matriz de regresión ═══════════════════════════════════════════════════════
@pytest.mark.parametrize("dataset, en_capa, cat, fuente, ns", [
    ("overture", "supermarket", "supermercado", "supermarket", POI.OVERTURE_CATEGORIES_PRIMARY),
    ("overture", "grocery_store", "supermercado", "grocery_store", POI.OVERTURE_CATEGORIES_PRIMARY),
    ("overture", "pharmacy", "farmacia", "pharmacy", POI.OVERTURE_CATEGORIES_PRIMARY),
    ("osm", "supermercado", "supermercado", "supermarket", POI.OSM_SHOP),
    ("osm", "minimarket", "supermercado", "convenience", POI.OSM_SHOP),
    ("osm", "pharmacy", "farmacia", "pharmacy", POI.OSM_AMENITY),
    ("osm", "garden", "parque", "garden", POI.OSM_LEISURE),
], ids=["overture-supermarket", "overture-grocery_store", "overture-pharmacy", "osm-shop=supermarket",
        "osm-shop=convenience", "osm-amenity=pharmacy", "osm-leisure=garden"])
def test_M1_las_dos_autoridades_quedan_distinguibles(dataset, en_capa, cat, fuente, ns):
    _, docs = _docs([_poi(cat, 120, 50, dataset=dataset, categoria_capa_origen=en_capa), _transporte()])
    item = _servicio(docs, 50)
    c = item.classification
    assert item.place.category == cat                      # la de Contexto, por compatibilidad
    assert (c.authority, c.method) == (CategoryAuthority.CONTEXTO, V0)
    assert (c.source_category, c.source_category_namespace) == (fuente, ns)   # la de la fuente, tal cual
    assert _fuente(docs["servicios"], item).provider == ns.dataset == dataset


@pytest.mark.parametrize("dataset, en_capa, cat", [
    ("overture", "cafe", "supermercado"),          # una hoja que el método v0 no mapea
    ("overture", "pharmacy", "supermercado"),      # mapeada, pero a OTRA categoría
    ("overture", "supermercado", "supermercado"),  # vocabulario de Contexto en lugar de la fuente
    ("osm", "bakery", "supermercado"),             # un subtipo que la ingesta no emite
], ids=["no-mapeada", "incoherente", "traducida", "subtipo-desconocido"])
def test_M2_una_categoria_que_el_metodo_no_explica_no_se_persiste(dataset, en_capa, cat):
    _, docs = _docs([_poi(cat, 120, 50, dataset=dataset, categoria_capa_origen=en_capa),
                     _poi("parque", 200, 51), _transporte()])
    s = docs["servicios"]
    assert [i.place.poi_id for i in s.items] == ["51"]
    assert any("que el método de clasificación no explica" in l for l in s.limitations)


def test_M3_si_era_el_unico_servicio_el_documento_es_UNKNOWN_y_no_inventa():
    _, docs = _docs([_poi("supermercado", 120, 50, dataset="overture", categoria_capa_origen="cafe"),
                     _transporte()])
    assert docs["servicios"] is None


def test_M4_sin_categoria_de_origen_en_la_capa_queda_NULL_y_se_declara():
    _, docs = _docs([_poi("supermercado", 120, 50, dataset="overture", categoria_capa_origen=None),
                     _transporte()])
    c = _servicio(docs, 50).classification
    assert c.source_category is None and c.source_category_namespace is None
    assert c.authority is CategoryAuthority.CONTEXTO
    assert any("sin categoría de origen conservada" in l for l in docs["servicios"].limitations)


def test_M5_una_fuente_que_no_es_un_dataset_abierto_no_se_persiste():
    """La capa solo tiene `overture` y `osm` (CHECK `ck_pois_fuente`). Nada manual, nada de Google."""
    _, docs = _docs([_poi("supermercado", 120, 50, dataset="manual", categoria_capa_origen="tienda"),
                     _poi("parque", 200, 51), _transporte()])
    assert [i.place.poi_id for i in docs["servicios"].items] == ["51"]


@pytest.mark.parametrize("subtipo, masivo, fuente, ns", [
    ("parada_bus", False, "bus_stop", POI.OSM_HIGHWAY),
    ("estacion_tren", True, "station", POI.OSM_RAILWAY),
    ("estacion", True, "station", POI.OSM_PUBLIC_TRANSPORT),
    ("terminal_bus", True, "bus_station", POI.OSM_AMENITY),
    ("metro", True, None, None),
])
def test_M6_la_parada_separa_el_modo_de_contexto_de_la_etiqueta_de_osm(subtipo, masivo, fuente, ns):
    _, docs = _docs([_poi("parque", 200, 51), _transporte(masivo=masivo, categoria_capa_origen=subtipo)])
    k = docs["conectividad"]
    c = k.stop.classification
    assert k.stop.stop.mode == ("masivo" if masivo else "parada")
    assert (c.authority, c.method) == (CategoryAuthority.CONTEXTO, MODO_V0)
    assert (c.source_category, c.source_category_namespace) == (fuente, ns)
    assert any("no conserva la categoría de origen" in l for l in k.limitations) is (fuente is None)


def test_M7_un_modo_que_el_subtipo_no_explica_deja_la_conectividad_en_UNKNOWN():
    _, docs = _docs([_poi("parque", 200, 51), _transporte(masivo=True, categoria_capa_origen="parada_bus")])
    assert docs["conectividad"] is None and docs["servicios"] is not None


# ══ R · POI 60717, de punta a punta ══════════════════════════════════════════════════
# Los valores EXACTOS de producción (lectura READ ONLY del 2026-10-01, CANARY SEMANTIC BLOCKER 0.1).
P60717 = _poi("supermercado", 79, 60717, dataset="overture",
              dataset_id="c84e5e54-26ef-499c-bf66-042d2201f356",
              nombre="Bizcochos De Cayambe Biz Glaz En Quito",
              capa_actualizado_en="2026-09-22T14:30:03.808905+00:00",
              categoria_capa_origen="grocery_store")


def test_R1_el_60717_conserva_grocery_store_y_supermercado_es_de_contexto():
    _, docs = _docs([P60717, _transporte()])
    s = docs["servicios"]
    item = _servicio(docs, 60717)
    fuente = _fuente(s, item)
    assert item.place.category == "supermercado"
    assert item.classification == CategoryClassificationV0(
        authority="contexto", method="contexto_poi_category_v0",
        source_category="grocery_store", source_category_namespace="overture:categories.primary")
    # La SOURCE no cambia: el registro real, sin inventar nada.
    assert fuente.source_type is SourceType.PUBLIC_DATASET and fuente.provider == "overture"
    assert fuente.source_id == "c84e5e54-26ef-499c-bf66-042d2201f356"
    assert fuente.retrieved_at.isoformat() == "2026-09-22T14:30:03.808905+00:00"
    assert fuente.observed_at is None and fuente.confidence is None


def test_R2_supermercado_no_se_le_puede_atribuir_a_overture():
    _, docs = _docs([P60717, _transporte()])
    s = docs["servicios"]
    item = _servicio(docs, 60717)
    assert "supermercado" not in _fuente(s, item).model_dump_json()
    assert item.classification.source_category != "supermercado"
    assert item.classification.authority is CategoryAuthority.CONTEXTO
    # Y si la capa trajera «supermercado» como si fuera de Overture, no se persistiría.
    _, malo = _docs([{**P60717, "categoria_capa_origen": "supermercado"}, _transporte()])
    assert malo["servicios"] is None


def test_R3_el_60717_se_reconstruye_solo_con_el_documento_y_la_tabla_del_metodo():
    """Un revisor, con el JSON persistido y la tabla del método, reproduce las dos categorías."""
    _, docs = _docs([P60717, _transporte()])
    crudo = json.loads(docs["servicios"].model_dump_json())
    it = next(i for i in crudo["items"] if i["place"]["poi_id"] == "60717")
    assert it["classification"]["method"] == "contexto_poi_category_v0"
    assert it["classification"]["source_category_namespace"] == "overture:categories.primary"
    assert OVERTURE_V0[it["classification"]["source_category"]] == it["place"]["category"]


# ══ C · contrato ══════════════════════════════════════════════════════════════════
def _crudo_servicios():
    _, docs = _docs([P60717, _poi("parque", 200, 51), _transporte()])
    return json.loads(docs["servicios"].model_dump_json())


def _con_clasificacion(**cambios):
    d = _crudo_servicios()
    d["items"][0]["classification"].update(cambios)
    return d


def test_C1_un_documento_sin_clasificacion_no_valida():
    d = _crudo_servicios()
    del d["items"][0]["classification"]
    with pytest.raises(ValidationError):
        NearbyPlacesEvidenceV0.model_validate(d)


@pytest.mark.parametrize("cambios", [
    {"source_category_namespace": None},                       # valor sin espacio
    {"source_category": None},                                  # espacio sin valor
    {"source_category": " grocery_store"},                      # retocado
    {"authority": "overture"},                                  # la fuente no decide la de Contexto
    {"method": "contexto_transit_mode_v0"},                     # el método de otro elemento
    {"source_category_namespace": "osm:shop"},                  # espacio de otro dataset
], ids=["valor-sin-espacio", "espacio-sin-valor", "retocado", "autoridad-fuente", "metodo-ajeno",
        "dataset-ajeno"])
def test_C2_el_contrato_rechaza_una_clasificacion_incoherente(cambios):
    with pytest.raises(ValidationError):
        NearbyPlacesEvidenceV0.model_validate(_con_clasificacion(**cambios))


def test_C3_la_clave_source_category_es_obligatoria_aunque_sea_NULL():
    """Un documento que OMITE la clave no puede pasar por uno que dice «no se sabe»."""
    d = _crudo_servicios()
    del d["items"][0]["classification"]["source_category"]
    with pytest.raises(ValidationError):
        NearbyPlacesEvidenceV0.model_validate(d)


# ══ §16 · los diez puntos del mandato ═══════════════════════════════════════════════
def test_16_1_la_categoria_de_la_fuente_se_conserva_tal_cual():
    _, docs = _docs([P60717, _poi("supermercado", 300, 52, dataset="osm", categoria_capa_origen="minimarket"),
                     _transporte()])
    assert _servicio(docs, 60717).classification.source_category == "grocery_store"
    _, docs = _docs([_poi("supermercado", 300, 52, dataset="osm", categoria_capa_origen="minimarket"),
                     _transporte()])
    assert _servicio(docs, 52).classification.source_category == "convenience"


def test_16_2_la_categoria_de_contexto_esta_identificada_como_propia():
    _, docs = _docs()
    for item in (*docs["servicios"].items, docs["conectividad"].stop):
        assert item.classification.authority is CategoryAuthority.CONTEXTO
        assert item.classification.method in set(CategoryMethod)


def test_16_3_una_categoria_de_origen_desconocida_sigue_siendo_NULL():
    _, docs = _docs([_poi("parque", 200, 51, categoria_capa_origen=None), _transporte()])
    assert _servicio(docs, 51).classification.source_category is None
    assert docs["conectividad"].stop.classification.source_category is None   # metro


def test_16_4_el_formatter_no_depende_de_la_clasificacion_ni_la_toca():
    _, con = _docs([P60717, _transporte()])
    _, sin = _docs([{**P60717, "categoria_capa_origen": None}, _transporte()])
    antes = con["servicios"].model_dump_json()
    assert formatear_servicios(con["servicios"]) == formatear_servicios(sin["servicios"]) == \
        "🛒 Bizcochos De Cayambe Biz Glaz En Quito a ~79 m"
    assert con["servicios"].model_dump_json() == antes
    assert formatear_conectividad(con["conectividad"]).startswith("🚇 ")


def test_16_5_el_60717_queda_semanticamente_reconstruible():
    test_R3_el_60717_se_reconstruye_solo_con_el_documento_y_la_tabla_del_metodo()


def test_16_6_ningun_consumidor_se_abre():
    _, docs = _docs([P60717, _transporte()])
    fila = {"id": "x", "lat": LAT, "lon": LON,
            "servicios_evidencia": docs["servicios"].model_dump_json(),
            "conectividad_evidencia": docs["conectividad"].model_dump_json(),
            "servicios_cercanos": formatear_servicios(docs["servicios"]),
            "conectividad": formatear_conectividad(docs["conectividad"])}
    vigente = con_contexto_vigente(fila)
    assert vigente["servicios_cercanos"] is None and vigente["conectividad"] is None


def test_16_7_la_041_sigue_coherente_lectura_nueva_y_forma_vieja_degradada():
    _, docs = _docs([P60717, _transporte()])
    fila = {"lat": LAT, "lon": LON, "servicios_evidencia": docs["servicios"].model_dump_json(),
            "servicios_cercanos": "texto legado"}
    assert leer_contexto_persistido(fila, "servicios").estado == "estructurada"
    # La forma de ANTES de esta unidad (sin `classification`), si un runtime viejo la escribiera, no
    # es evidencia: se degrada a legado y dice por qué. Nunca asciende.
    viejo = json.loads(docs["servicios"].model_dump_json())
    for it in viejo["items"]:
        del it["classification"]
    lectura = leer_contexto_persistido({**fila, "servicios_evidencia": json.dumps(viejo)}, "servicios")
    assert lectura.estado == "legado_no_verificado" and "inválida" in lectura.motivo
    assert docs["servicios"].contract_version == "place-dimension-evidence/v0"


def _huella_lf(nombre: str) -> str:
    return hashlib.sha256((RAIZ / "migrations" / nombre).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_16_8_ni_la_041_ni_la_042_cambian_y_ninguna_migracion_posterior_toca_el_destino_de_v0():
    """SOURCE-CATEGORY es solo código: el CHECK de la 041 no mira dentro de los elementos.

    Hasta la 042 esta guarda exigía además que NO hubiera migración nueva. La primera posterior es la 043
    (POI-SOURCE-PROVENANCE: solo `pois_propios` y `poi_ingestion_run`); lo que se conserva es la intención: ninguna
    migración posterior a la 042 puede tocar el destino de la evidencia de v0 (`activos_inmutables`)."""
    assert _huella_lf("041_place_provenance_evidencia.sql") == \
        "a6520be482bfb051a91eeb4e9a8cecce67d76017c6f8eb0fea884a0c174560df"
    assert _huella_lf("042_place_evidence_target_authority.sql") == \
        "95305ee000269f202b25dfaf74c4a905fdcb44939a377ef3b6c998d2955a9ff1"
    posteriores = sorted(p for p in (RAIZ / "migrations").glob("[0-9][0-9][0-9]_*.sql") if p.name[:3] > "042")
    assert [p.name for p in posteriores][:1] == ["043_poi_source_provenance.sql"]
    for p in posteriores:
        ejecutable = "\n".join(l.split("--", 1)[0] for l in p.read_text(encoding="utf-8").splitlines())
        assert "activos_inmutables" not in ejecutable, p.name


def test_16_9_sin_google():
    assert all(ns.dataset in {"overture", "osm"} for ns in SourceCategoryNamespace)
    assert not any("google" in str(x).lower()
                   for x in (*OVERTURE_V0, *OVERTURE_V0.values(), *OSM_V0, *(v for v in OSM_V0.values())))
    _, docs = _docs([P60717, _poi("salud", 90, 53, dataset="google", categoria_capa_origen="hospital"),
                     _transporte()])
    assert all(e.provider != "google" for e in docs["servicios"].evidence)
    assert "53" not in {i.place.poi_id for i in docs["servicios"].items}


def test_16_10_sin_inferencia_historica():
    """La categoría de origen sale SOLO de la columna de la capa: ni del nombre, ni del emoji, ni
    del texto legado. Y el texto legado no adquiere clasificación."""
    _, docs = _docs([_poi("supermercado", 120, 54, dataset="overture", nombre="Supermercado Central",
                          categoria_capa_origen=None), _transporte()])
    assert _servicio(docs, 54).classification.source_category is None
    legado = leer_contexto_persistido({"lat": LAT, "lon": LON, "servicios_evidencia": None,
                                       "servicios_cercanos": "🛒 Supermercado Central a ~120 m"}, "servicios")
    assert legado.estado == "legado_no_verificado" and legado.documento is None
    fuente = inspect.getsource(clasificacion)
    assert "servicios_cercanos" not in fuente and "parse_servicios" not in fuente


def test_el_documento_de_conectividad_tambien_valida_de_ida_y_vuelta():
    _, docs = _docs([P60717, _transporte(masivo=False)])
    k = docs["conectividad"]
    assert NearestTransitEvidenceV0.model_validate_json(k.model_dump_json()) == k
    s = docs["servicios"]
    assert NearbyPlacesEvidenceV0.model_validate_json(s.model_dump_json()) == s
