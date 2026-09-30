"""PLACE-PROVENANCE-041 · evidencia estructurada por dimensión, sin tocar producción.

Numerado como el mandato:

  §4 · DEFECTOS REPRODUCIDOS (caracterización explícita del código legado, que NO se corrige
       aquí: son los lectores que la reapertura sustituirá):
       A · el escritor produce «Nombre (~N m), Nombre (~N m)» y el parser espera «·» y «a ~N m»;
       B · «1.200 m» se lee como 1 m;
       C · minutos estimados en línea recta que el lector toma por tiempo de ruta;
       D · una fila con solo texto legado NO adquiere procedencia.
  §13 · DOMINIO 1–14 (el 15, regresión de la 040, vive en `tests/test_migracion_041.py`).
  §9  · el escritor (`_recompute_walk_score`) con y sin la 041 en la base.

Cero red y cero base: la materia se fabrica con la forma exacta que produce
`app/place/providers/propia.py` y el contexto sale del ensamblador REAL.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

import app.place.persistible as persistible
import app.routers.assets as assets
import app.rutas as rutas
from app.contracts.evidence_v0 import EvidenceRefV0, PersistencePolicy, SourceType
from app.contracts.place_evidence_v0 import (
    DistanceMethod,
    DurationMethod,
    NearbyPlacesEvidenceV0,
    NearestTransitEvidenceV0,
    ValueClass,
    WalkDurationV0,
)
from app.contracts.place_v0 import MeasureStatus
from app.decision.assembler import _min_a_pie, _transporte_min, _EMOJI_PARQUE
from app.entorno_curacion import parse_servicios
from app.place.assembler import MateriaDeZona, ensamblar_place_context
from app.place.legado import con_contexto_vigente
from app.place.persistible import (
    documentos_persistibles,
    evidencia_conectividad,
    evidencia_servicios,
    formatear_conectividad,
    formatear_servicios,
    leer_contexto_persistido,
)

AHORA = datetime(2026, 9, 30, 13, 0, 0, tzinfo=timezone.utc)
INGESTA = "2026-09-22T14:30:03+00:00"
LAT, LON = -0.1755, -78.4858


def _poi(cat, d, poi_id, *, dataset="osm", dataset_id=None, nombre=None, **extra):
    """Un POI con la forma EXACTA que devuelve `_servicios_propios` desde la 041."""
    base = {"nombre": nombre or f"{cat.capitalize()} Sintético {poi_id}", "cat": cat,
            "distancia_m": d, "lat": LAT, "lon": LON, "fuente": "propio", "marca": None,
            "verificado_en": None, "poi_id": poi_id, "dataset": dataset,
            "dataset_id": dataset_id or f"{dataset}/{poi_id}", "capa_actualizado_en": INGESTA,
            "verificado_en_ts": None, "verificacion_accion": None}
    base.update(extra)
    return base


def _transporte(d=640, poi_id=900, masivo=True, **extra):
    return _poi("transporte", d, poi_id, nombre="Estación Sintética", es_masivo=masivo,
                subtipo="metro" if masivo else "parada", **extra)


def _materia(servicios, *, ruta_medida=False):
    t = next((s for s in servicios if s.get("cat") == "transporte"), None)
    return MateriaDeZona(
        lat=LAT, lon=LON, lugar={}, walk={}, servicios=servicios,
        se_consultaron_servicios=bool(servicios), transporte=t,
        transporte_distancia_m=t["distancia_m"] if t else None,
        transporte_minutos=rutas._min_pie(t["distancia_m"]) if t else None,
        transporte_ruta_medida=ruta_medida, recuperado_en=AHORA)


COMPLETA = [_poi("parque", 254, 11), _poi("farmacia", 120, 12, dataset="overture"),
            _poi("supermercado", 1200, 13), _transporte()]


def _docs(servicios=COMPLETA, **kw):
    m = _materia(servicios, **kw)
    return m, documentos_persistibles(m, ensamblar_place_context(m))


@pytest.fixture(autouse=True)
def _sin_cache_de_esquema(monkeypatch):
    monkeypatch.setattr(persistible, "_esquema_041_visto", False)


# ══ §4 · DEFECTOS REPRODUCIDOS (caracterización del código legado) ═════════════════
def test_A_el_escritor_de_hoy_y_el_parser_no_hablan_el_mismo_formato():
    """CARACTERIZACIÓN: `prosa_servicios` (lo que `_recompute_walk_score` persiste hoy) une con
    «, » y pone «(~N m)»; `parse_servicios` corta por «·» y exige «~N m» AL FINAL."""
    m = _materia(COMPLETA)
    prosa = rutas.prosa_servicios(ensamblar_place_context(m))
    assert ", " in prosa and "(~254 m)" in prosa
    segmentos = parse_servicios(prosa)
    assert len(segmentos) == 1, "un solo segmento: el «·» no aparece"
    assert segmentos[0]["distancia_m"] is None, "0 distancias: «(~N m)» no está al final"
    assert _min_a_pie(prosa, _EMOJI_PARQUE) is None, "sin parque_min"
    # Con la 041, la verdad canónica es la evidencia, y la prosa renderizada sí se lee de vuelta.
    doc = evidencia_servicios(m, ensamblar_place_context(m))
    assert _min_a_pie(formatear_servicios(doc), _EMOJI_PARQUE) == 3     # 254 m / 80 m·min


def test_B_mil_doscientos_metros_no_es_un_metro():
    """CARACTERIZACIÓN: el separador de miles rompe el parser legado."""
    assert parse_servicios("🛒 Súper a ~1.200 m")[0]["distancia_m"] == 1
    # La distancia canónica viene del número, no del texto; y el formatter no emite miles.
    _, docs = _docs()
    super_ = next(i for i in docs["servicios"].items if i.place.category == "supermercado")
    assert super_.place.distance_m == 1200.0
    texto = formatear_servicios(docs["servicios"])
    assert "a ~1200 m" in texto and "1.200" not in texto
    assert 1200 in [s["distancia_m"] for s in parse_servicios(texto)]


def test_C_minutos_en_linea_recta_no_son_tiempo_de_ruta():
    """CARACTERIZACIÓN: la conectividad de hoy lleva «(N min a pie)» calculados como recta ÷ 80,
    y `_transporte_min` los toma por «el tiempo REAL de Google Routes»."""
    m = _materia(COMPLETA)
    prosa = rutas.prosa_conectividad(ensamblar_place_context(m))
    assert "(8 min a pie)" in prosa
    assert _transporte_min(prosa) == 8   # leído por la rama de «ruta real» (_MIN_PAREN_RE)
    # Con la 041: la duración se rotula como estimada, y la prosa ya no la afirma.
    doc = evidencia_conectividad(m, ensamblar_place_context(m))
    assert doc.walk_duration.value_class is ValueClass.ESTIMATED
    assert doc.walk_duration.method is DurationMethod.STRAIGHT_LINE_AT_FIXED_PACE
    assert "min" not in formatear_conectividad(doc)


def test_D_una_fila_con_solo_texto_legado_no_adquiere_procedencia():
    fila = {"id": "x", "lat": LAT, "lon": LON,
            "servicios_cercanos": "🌳 Parque Legado a ~300 m · 💊 Farmacia Legada a ~120 m",
            "conectividad": "🚇 Estación Legada a ~500 m"}
    for dim in ("servicios", "conectividad"):
        lectura = leer_contexto_persistido(fila, dim)
        assert lectura.estado == "legado_no_verificado" and not lectura.procedencia_demostrada
        assert lectura.documento is None
    # Y la frontera del producto sigue cerrada: la 041 no reabre nada.
    assert con_contexto_vigente(fila)["servicios_cercanos"] is None


# ══ §13 · DOMINIO ═════════════════════════════════════════════════════════════════
def test_1_evidencia_de_servicios_ida_y_vuelta():
    _, docs = _docs()
    doc = docs["servicios"]
    assert doc.status is MeasureStatus.AVAILABLE and len(doc.items) == 3
    assert NearbyPlacesEvidenceV0.model_validate_json(doc.model_dump_json()) == doc
    assert [i.place.poi_id for i in doc.items] == ["11", "12", "13"]


def test_2_evidencia_de_conectividad_ida_y_vuelta():
    _, docs = _docs()
    doc = docs["conectividad"]
    assert doc.stop.stop.stop_id == "900" and doc.stop.stop.mode == "masivo"
    assert NearestTransitEvidenceV0.model_validate_json(doc.model_dump_json()) == doc


def test_3_la_fila_solo_legado_sigue_sin_verificar_aunque_el_texto_tenga_el_formato_nuevo():
    """El formato correcto no convierte un texto en evidencia."""
    _, docs = _docs()
    fila = {"lat": LAT, "lon": LON, "servicios_cercanos": formatear_servicios(docs["servicios"])}
    assert leer_contexto_persistido(fila, "servicios").estado == "legado_no_verificado"


def test_4_el_formato_del_texto_ya_no_afecta_a_la_verdad_canonica():
    _, docs = _docs()
    fila = {"lat": LAT, "lon": LON, "servicios_evidencia": docs["servicios"].model_dump_json(),
            "servicios_cercanos": "texto cualquiera, con comas (~9 m), que el parser no entiende"}
    lectura = leer_contexto_persistido(fila, "servicios")
    assert lectura.estado == "estructurada" and lectura.procedencia_demostrada
    assert lectura.texto == formatear_servicios(docs["servicios"]), "la prosa sale del documento"
    assert [p["distancia_m"] for p in parse_servicios(lectura.texto)] == [120, 254, 1200]


def test_5_mil_doscientos_metros_ida_y_vuelta_exacta():
    _, docs = _docs()
    ida = {(i.place.name, int(i.place.distance_m)) for i in docs["servicios"].items}
    vuelta = {(s["visible"], s["distancia_m"]) for s in parse_servicios(formatear_servicios(docs["servicios"]))}
    assert ida == vuelta


def test_6_una_estimacion_en_linea_recta_nunca_se_rotula_como_ruta():
    with pytest.raises(ValidationError, match="no es un tiempo de ruta"):
        WalkDurationV0(minutes=8, value_class=ValueClass.DERIVED,
                       method=DurationMethod.STRAIGHT_LINE_AT_FIXED_PACE, evidence_id="e")
    with pytest.raises(ValidationError, match="no es un tiempo de ruta"):
        WalkDurationV0(minutes=8, value_class=ValueClass.ESTIMATED,
                       method=DurationMethod.STREET_NETWORK_ROUTE, evidence_id="e")
    # La evidencia de la duración estimada es heurística y declara sus límites.
    _, docs = _docs()
    c = docs["conectividad"]
    heur = next(e for e in c.evidence if e.evidence_id == c.walk_duration.evidence_id)
    assert heur.source_type is SourceType.HEURISTIC_ESTIMATE and heur.limitations
    # Y la distancia en línea recta es `derived`, nunca `measured` ni `estimated`.
    datos = json.loads(c.model_dump_json())
    datos["distance_class"] = "estimated"
    with pytest.raises(ValidationError, match="no admite"):
        NearestTransitEvidenceV0.model_validate(datos)


def test_6b_una_ruta_medida_que_no_es_persistible_no_se_guarda_como_duracion():
    _, docs = _docs(ruta_medida=True)
    assert docs["conectividad"].walk_duration is None
    assert any("no es persistible" in l for l in docs["conectividad"].limitations)


def test_7_sin_servicios_la_ausencia_es_explicita_y_no_se_inventa():
    # La capa respondió (hay transporte) pero sin servicios en el radio → insufficient_evidence.
    _, docs = _docs([_transporte()])
    s = docs["servicios"]
    assert s.status is MeasureStatus.INSUFFICIENT_EVIDENCE and s.items == ()
    assert formatear_servicios(s) is None
    assert any("hueco de capa" in l for l in s.limitations)
    # Sin nada de la capa: no se sabe → None (la columna queda en NULL), no un documento.
    _, docs = _docs([])
    assert docs == {"servicios": None, "conectividad": None}


def test_8_la_conectividad_es_independiente_de_los_servicios(monkeypatch):
    _, docs = _docs([_poi("parque", 254, 11)])
    assert docs["servicios"].status is MeasureStatus.AVAILABLE
    assert docs["conectividad"].status is MeasureStatus.INSUFFICIENT_EVIDENCE
    # Si construir una dimensión revienta, la otra sigue.

    def _revienta(*a, **k):
        raise ValueError("fallo sintético")
    monkeypatch.setattr(persistible, "evidencia_conectividad", _revienta)
    _, docs = _docs()
    assert docs["conectividad"] is None and docs["servicios"].status is MeasureStatus.AVAILABLE


def test_9_source_no_es_method():
    _, docs = _docs()
    doc = docs["servicios"]
    por_id = {e.evidence_id: e for e in doc.evidence}
    item = doc.items[0]
    fuente, metodo = por_id[item.source_evidence_id], por_id[item.method_evidence_id]
    assert fuente.source_type is SourceType.PUBLIC_DATASET and fuente.provider == "osm"
    assert fuente.source_id == "osm/11" and fuente.observed_at is None
    assert fuente.retrieved_at == datetime.fromisoformat(INGESTA), "cuándo lo ingirió la capa"
    assert metodo.source_type is SourceType.OWN_MEASUREMENT and metodo.provider == "contexto-capa-propia"
    assert fuente.methodology != metodo.methodology
    # Intercambiarlos no pasa el contrato.
    datos = json.loads(doc.model_dump_json())
    datos["items"][0]["source_evidence_id"], datos["items"][0]["method_evidence_id"] = (
        item.method_evidence_id, item.source_evidence_id)
    with pytest.raises(ValidationError, match="no son intercambiables"):
        NearbyPlacesEvidenceV0.model_validate(datos)


def test_10_sin_verificacion_no_es_verificado():
    visto = (AHORA - timedelta(days=3)).isoformat()
    servicios = [_poi("parque", 254, 11),
                 _poi("farmacia", 120, 12, verificacion_accion="confirmado", verificado_en_ts=visto),
                 _poi("supermercado", 400, 13, verificacion_accion="agregado", verificado_en_ts=visto),
                 _transporte()]
    _, docs = _docs(servicios)
    doc = docs["servicios"]
    por_id = {e.evidence_id: e for e in doc.evidence}
    por_cat = {i.place.category: i for i in doc.items}
    assert por_cat["parque"].verification_evidence_ids == (), "nadie fue: sin verificación"
    assert por_cat["supermercado"].verification_evidence_ids == (), "«agregado» no verifica ESTE lugar"
    (vid,) = por_cat["farmacia"].verification_evidence_ids
    assert por_id[vid].source_type is SourceType.OPERATOR_DECLARED
    assert por_id[vid].observed_at == datetime.fromisoformat(visto), "observed_at reparado con dato real"


def test_11_el_formatter_renderiza_desde_la_estructura():
    _, docs = _docs()
    assert formatear_servicios(docs["servicios"]) == (
        "💊 Farmacia Sintético 12 a ~120 m · 🌳 Parque Sintético 11 a ~254 m · "
        "🛒 Supermercado Sintético 13 a ~1200 m")
    assert formatear_conectividad(docs["conectividad"]) == "🚇 Estación Sintética a ~640 m"
    _, parada = _docs([_transporte(masivo=False)])
    assert formatear_conectividad(parada["conectividad"]) == (
        "🚏 Estación Sintética (parada de bus, NO es Metro) a ~640 m")


def test_12_el_formatter_no_es_fuente_inversa_de_verdad():
    """No existe camino texto → documento: ni la lectura ni el constructor leen la prosa."""
    import inspect
    fuente = inspect.getsource(persistible)
    assert "parse_servicios" not in fuente.replace("`parse_servicios`", "")
    # Un texto alterado junto a una evidencia válida no cambia lo que se lee.
    _, docs = _docs()
    fila = {"lat": LAT, "lon": LON, "conectividad_evidencia": docs["conectividad"].model_dump_json(),
            "conectividad": "🚇 Otra Estación ~5 m (1 min a pie)"}
    assert leer_contexto_persistido(fila, "conectividad").texto == "🚇 Estación Sintética a ~640 m"


def test_13_google_no_entra_como_fuente_nueva():
    # Un POI que no es de la capa propia no se persiste.
    _, docs = _docs([_poi("parque", 254, 11), _poi("salud", 300, 14, fuente="google"), _transporte()])
    assert [i.place.category for i in docs["servicios"].items] == ["parque"]
    assert any("sin procedencia completa" in l for l in docs["servicios"].limitations)
    # Y el contrato rechaza cualquier evidencia de Google, aunque alguien la construya a mano.
    datos = json.loads(docs["servicios"].model_dump_json())
    datos["evidence"][1]["provider"] = "google-places"
    with pytest.raises(ValidationError, match="Google"):
        NearbyPlacesEvidenceV0.model_validate(datos)


def test_13b_solo_evidencia_persistable():
    _, docs = _docs()
    datos = json.loads(docs["servicios"].model_dump_json())
    datos["evidence"][0]["persistence_policy"] = "runtime_only"
    with pytest.raises(ValidationError, match="persistable"):
        NearbyPlacesEvidenceV0.model_validate(datos)


def test_14_los_registros_viejos_se_siguen_leyendo_en_la_transicion():
    # Una fila de ANTES de la 041 (sin las columnas nuevas) se lee como legado, con su texto.
    fila = {"lat": LAT, "lon": LON, "servicios_cercanos": "🌳 Parque a ~300 m", "conectividad": None}
    assert leer_contexto_persistido(fila, "servicios").texto == "🌳 Parque a ~300 m"
    assert leer_contexto_persistido(fila, "conectividad").estado == "ausente"


# ══ Contrato: invariantes que la base repite como CHECK ═══════════════════════════
def test_unknown_no_se_persiste_como_documento():
    _, docs = _docs()
    datos = json.loads(docs["servicios"].model_dump_json())
    datos.update(status="unknown", items=[])
    with pytest.raises(ValidationError, match="no se persiste"):
        NearbyPlacesEvidenceV0.model_validate(datos)


def test_available_exige_elementos_y_evidencia_y_la_insuficiencia_no_admite_elementos():
    _, docs = _docs()
    datos = json.loads(docs["servicios"].model_dump_json())
    with pytest.raises(ValidationError, match="sin elementos"):
        NearbyPlacesEvidenceV0.model_validate({**datos, "items": []})
    with pytest.raises(ValidationError, match="con elementos"):
        NearbyPlacesEvidenceV0.model_validate({**datos, "status": "insufficient_evidence"})


def test_un_enlace_a_evidencia_inexistente_no_pasa():
    _, docs = _docs()
    datos = json.loads(docs["servicios"].model_dump_json())
    datos["items"][0]["source_evidence_id"] = "no-existe"
    with pytest.raises(ValidationError, match="no está en el documento"):
        NearbyPlacesEvidenceV0.model_validate(datos)


def test_un_elemento_sin_identidad_en_la_capa_no_se_persiste():
    _, docs = _docs([_poi("parque", 254, None), _transporte()])
    assert docs["servicios"] is None, "sin poi_id no hay nada que afirmar: UNKNOWN"


def test_la_misma_materia_da_el_mismo_documento_byte_a_byte():
    m = _materia(COMPLETA)
    a = documentos_persistibles(m, ensamblar_place_context(m))
    b = documentos_persistibles(m, ensamblar_place_context(m))
    assert a["servicios"].model_dump_json() == b["servicios"].model_dump_json()
    assert a["conectividad"].model_dump_json() == b["conectividad"].model_dump_json()


# ══ Lectura: la evidencia no vale si ya no describe a esta fila ════════════════════
def test_la_evidencia_medida_desde_otro_punto_no_es_canonica():
    _, docs = _docs()
    fila = {"lat": LAT + 0.01, "lon": LON, "servicios_evidencia": docs["servicios"].model_dump_json(),
            "servicios_cercanos": "🌳 Parque a ~300 m"}
    lectura = leer_contexto_persistido(fila, "servicios")
    assert lectura.estado == "legado_no_verificado" and "ya no está" in lectura.motivo
    sin_pos = {"servicios_evidencia": docs["servicios"].model_dump_json()}
    assert leer_contexto_persistido(sin_pos, "servicios").estado == "ausente"


def test_una_evidencia_corrupta_se_degrada_y_no_se_eleva():
    fila = {"lat": LAT, "lon": LON, "servicios_evidencia": '{"status": "available"}',
            "servicios_cercanos": "🌳 Parque a ~300 m"}
    lectura = leer_contexto_persistido(fila, "servicios")
    assert lectura.estado == "legado_no_verificado" and "inválida" in lectura.motivo


# ══ §11 · CURACIONES: no se resuelven aquí, pero no se pierde la posibilidad ═══════
def test_la_evidencia_conserva_lo_necesario_para_curar_despues():
    """Cada elemento guarda su `poi_id` (curación por identidad) y su nombre (las curaciones de
    texto, sin `poi_id`, que hoy se emparejan por nombre). Esta unidad no aplica ninguna."""
    _, docs = _docs()
    items = docs["servicios"].items
    assert all(i.place.poi_id and i.place.name for i in items)
    cerrado_por_id = {"accion": "cerrado", "poi_id": 12}
    assert [i.place.name for i in items if i.place.poi_id == str(cerrado_por_id["poi_id"])] == \
        ["Farmacia Sintético 12"], "un «cerrado» con poi_id localiza exactamente un elemento"
    assert docs["conectividad"].stop.stop.stop_id == "900"


def test_la_041_no_reabre_ningun_consumidor_aunque_la_fila_traiga_evidencia():
    """La frontera del producto sigue leyendo solo `contexto_procedencia` (que la 041 no crea):
    con evidencia en la fila, los textos siguen fuera de los consumidores hasta la unidad de
    reapertura, detrás de CURATION-CONSISTENCY."""
    _, docs = _docs()
    fila = {"id": "x", "lat": LAT, "lon": LON,
            "servicios_evidencia": docs["servicios"].model_dump_json(),
            "conectividad_evidencia": docs["conectividad"].model_dump_json(),
            "servicios_cercanos": formatear_servicios(docs["servicios"]),
            "conectividad": formatear_conectividad(docs["conectividad"])}
    vigente = con_contexto_vigente(fila)
    assert vigente["servicios_cercanos"] is None and vigente["conectividad"] is None


# ══ PROD-APPLY-PREFLIGHT §3 · W2 (`/publish`) solo escribe la fila que acaba de crear ══
def test_W2_publish_solo_escribe_la_conectividad_de_la_fila_que_acaba_de_crear():
    """Resultado A del preflight: `/publish` NO puede tocar una fila que ya tenga evidencia.
    El UPDATE de `conectividad` apunta a `aid`, que se genera con `uuid4()` DENTRO de la función,
    se inserta con el ORM (sin columnas de evidencia: nacen en NULL) y se escribe ANTES del
    commit: ninguna otra transacción ve la fila, y nadie pudo escribirle evidencia. Además, el
    trigger de la 041 cubre el caso por la base (`test_legacy_writer_cannot_leave_stale…`)."""
    import ast
    import inspect
    fuente = inspect.getsource(assets.publish_asset)
    arbol = ast.parse(fuente)
    lineas = {}
    for n in ast.walk(arbol):
        seg = ast.get_source_segment(fuente, n) or ""
        if isinstance(n, ast.Assign) and seg.replace(" ", "") == "aid=uuid.uuid4()":
            lineas["aid"] = n.lineno
        elif isinstance(n, ast.Call) and seg.startswith("ActivoInmutable(") and "id=aid" in seg.replace(" ", ""):
            lineas["insert"] = n.lineno
        elif isinstance(n, ast.Await) and seg.replace(" ", "") == "awaitdb.flush()":
            lineas["flush"] = n.lineno
        elif isinstance(n, ast.Await) and "conectividad = :c" in seg:
            lineas["update"] = n.lineno
            assert '"id": str(aid)' in seg, "el UPDATE de conectividad no apunta a la fila recién creada"
        elif isinstance(n, ast.Await) and seg.replace(" ", "") == "awaitdb.commit()":
            lineas.setdefault("commit", n.lineno)
    assert set(lineas) == {"aid", "insert", "flush", "update", "commit"}, lineas
    assert lineas["aid"] < lineas["insert"] < lineas["flush"] < lineas["update"] < lineas["commit"], lineas
    # El modelo ORM no mapea la evidencia: el INSERT la deja en NULL.
    from app.models import ActivoInmutable
    assert not {"servicios_evidencia", "conectividad_evidencia"} & set(ActivoInmutable.__table__.columns.keys())


# ══ §9 · EL ESCRITOR: con y sin la 041 en la base ═════════════════════════════════
class _Res:
    def __init__(self, valor=None):
        self.valor = valor

    def scalar(self):
        return self.valor


class _Sesion:
    def __init__(self, con_041, revienta_catalogo=False):
        self.con_041, self.revienta, self.updates = con_041, revienta_catalogo, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "information_schema.columns" in sql:
            if self.revienta:
                raise RuntimeError("catálogo ilegible")
            return _Res(2 if self.con_041 else 0)
        if "UPDATE activos_inmutables" in sql:
            self.updates.append((sql, dict(params)))
        return _Res()

    async def commit(self):
        pass


def _escribe(monkeypatch, sesion, servicios=COMPLETA, capa_caida=False):
    async def _fetch(lat, lon, timeout=None):
        return [{"lat": LAT, "lon": LON, "tags": {"amenity": "pharmacy", "name": "Farmacia OSM"}}]

    async def _recolecta(lat, lon):
        if capa_caida:
            raise RuntimeError("capa caída")
        return _materia(servicios)

    async def _nada(*a, **k):
        return None
    monkeypatch.setattr(assets, "_fetch_pois", _fetch)
    monkeypatch.setattr(rutas, "_recolectar_zona", _recolecta)
    monkeypatch.setattr(assets, "AsyncSessionLocal", lambda: sesion)
    monkeypatch.setattr(assets, "ensure_walk_score_fuente_column", _nada)
    asyncio.run(assets._recompute_walk_score("activo-1", LAT, LON))
    assert len(sesion.updates) == 1, sesion.updates
    return sesion.updates[0]


def test_escritor_sin_la_041_hace_el_update_de_siempre(monkeypatch):
    sql, p = _escribe(monkeypatch, _Sesion(con_041=False))
    assert "_evidencia" not in sql and set(p) == {"w", "f", "c", "s", "id"}
    m = _materia(COMPLETA)
    ctx = ensamblar_place_context(m)
    assert p["s"] == rutas.prosa_servicios(ctx) and p["c"] == rutas.prosa_conectividad(ctx), \
        "sin la 041, el texto es exactamente el de hoy"


def test_escritor_con_la_041_guarda_evidencia_y_renderiza_desde_ella(monkeypatch):
    sql, p = _escribe(monkeypatch, _Sesion(con_041=True))
    assert "servicios_evidencia = CAST(:se AS jsonb)" in sql
    assert "conectividad_evidencia = CAST(:ce AS jsonb)" in sql
    s = NearbyPlacesEvidenceV0.model_validate_json(p["se"])
    c = NearestTransitEvidenceV0.model_validate_json(p["ce"])
    assert p["s"] == formatear_servicios(s) and p["c"] == formatear_conectividad(c)
    assert s.origin.lat == LAT and c.origin.lon == LON


def test_escritor_con_la_041_y_la_capa_caida_deja_la_evidencia_en_NULL(monkeypatch):
    """El respaldo OSM escribe texto, y la evidencia NO se queda vieja junto a él."""
    _, p = _escribe(monkeypatch, _Sesion(con_041=True), capa_caida=True)
    assert p["se"] is None and p["ce"] is None
    assert p["s"] is not None or p["c"] is not None, "el texto de respaldo sigue escribiéndose"


def test_escritor_con_catalogo_ilegible_escribe_como_sin_la_041(monkeypatch):
    sql, p = _escribe(monkeypatch, _Sesion(con_041=True, revienta_catalogo=True))
    assert "_evidencia" not in sql


def test_una_dimension_insuficiente_no_borra_la_otra_en_el_escritor(monkeypatch):
    _, p = _escribe(monkeypatch, _Sesion(con_041=True), servicios=[_poi("parque", 254, 11)])
    assert NearbyPlacesEvidenceV0.model_validate_json(p["se"]).status is MeasureStatus.AVAILABLE
    assert NearestTransitEvidenceV0.model_validate_json(p["ce"]).status is \
        MeasureStatus.INSUFFICIENT_EVIDENCE


def test_la_evidencia_persistida_no_arrastra_evidencia_de_runtime():
    """El ensamblador marca su evidencia RUNTIME_ONLY; el documento crea la suya, persistable."""
    m = _materia(COMPLETA)
    ctx = ensamblar_place_context(m)
    assert all(e.persistence_policy is PersistencePolicy.RUNTIME_ONLY for e in ctx.nearby_places.evidence)
    doc = evidencia_servicios(m, ctx)
    assert all(e.persistence_policy is PersistencePolicy.PERSISTABLE for e in doc.evidence)
    assert not {e.evidence_id for e in ctx.nearby_places.evidence} & {e.evidence_id for e in doc.evidence}


def test_EvidenceRefV0_sigue_sin_valor_unknown():
    """La 041 no cambia la primitiva: la ausencia sigue sin tener una SourceType propia."""
    assert "unknown" not in {s.value for s in SourceType}
    assert set(EvidenceRefV0.model_fields) >= {"source_type", "provider", "observed_at", "methodology"}
