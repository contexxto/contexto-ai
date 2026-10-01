"""PLACE-EVIDENCE-WRITE-DECOUPLING · un fallo de Overpass ya no impide persistir la evidencia de lugar.

El defecto (PROD WRITE CANARY APPLY 0.1 y 0.2): `_recompute_walk_score` empezaba por `_fetch_pois` y,
si Overpass no respondía, salía en el primer paso. Con eso caía también la evidencia de servicios y
transporte, que sale ENTERA de la capa propia: dos intentos gobernados terminaron en NO-WRITE.

La matriz del mandato (A–N), con el escritor REAL:
  · sesión doble (cuenta UPDATE, catálogo, DDL y qué costuras se llamaron);
  · Postgres real (`banco` de la 041: CHECK, trigger y las otras filas), donde haya TEST_DATABASE_URL.
Cero red: Overpass y la capa propia se sustituyen por sus costuras.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid

import pytest
from sqlalchemy import text

import app.place.persistible as persistible
import app.place.providers.overpass as overpass
import app.routers.assets as assets
import app.rutas as rutas
from app.contracts.place_evidence_v0 import NearbyPlacesEvidenceV0, NearestTransitEvidenceV0
from app.contracts.place_v0 import MeasureStatus
from app.place.assembler import ensamblar_place_context
from app.place.persistible import (
    documentos_persistibles,
    formatear_conectividad,
    formatear_servicios,
    leer_contexto_persistido,
)
from tests.test_migracion_041 import _aplica, _fila_entorno, banco, pg  # noqa: F401 — `banco` es fixture
from tests.test_place_provenance_041 import COMPLETA, LAT, LON, _materia, _poi, _Sesion, _transporte

FLAG = "place_provenance_041_write_enabled"
UPDATE_PREVIO = ("UPDATE activos_inmutables SET walk_score = :w, walk_score_fuente = :f, "
                 "conectividad = :c, servicios_cercanos = :s WHERE id = :id")
UPDATE_041_COMPLETO = ("UPDATE activos_inmutables SET walk_score = :w, walk_score_fuente = :f, "
                       "conectividad = :c, servicios_cercanos = :s, "
                       "servicios_evidencia = CAST(:se AS jsonb), "
                       "conectividad_evidencia = CAST(:ce AS jsonb) WHERE id = :id")
UPDATE_SIN_OVERPASS = ("UPDATE activos_inmutables SET conectividad = :c, servicios_cercanos = :s, "
                       "servicios_evidencia = CAST(:se AS jsonb), "
                       "conectividad_evidencia = CAST(:ce AS jsonb) WHERE id = :id")
POIS_OSM = [{"lat": LAT, "lon": LON, "tags": {"amenity": "pharmacy", "name": "Farmacia OSM"}},
            {"lat": LAT + 0.004, "lon": LON, "tags": {"railway": "station", "name": "Estación OSM"}}]


@pytest.fixture(autouse=True)
def _sin_cache_de_esquema(monkeypatch):
    monkeypatch.setattr(persistible, "_esquema_041_visto", False)


class _SesionContada(_Sesion):
    """La sesión doble de la 041 que además cuenta las consultas al catálogo."""

    def __init__(self, con_041):
        super().__init__(con_041)
        self.catalogo = 0

    async def execute(self, stmt, params=None):
        if "information_schema.columns" in str(stmt):
            self.catalogo += 1
        return await super().execute(stmt, params)


def _corre(monkeypatch, *, flag=True, con_041=True, servicios=COMPLETA, overpass_ok=True, capa_caida=False):
    """El escritor REAL con Overpass y la capa propia sustituidos por sus costuras."""
    sesion = _SesionContada(con_041)
    n = {"fetch": 0, "capa_propia": 0, "zona": 0, "ddl": 0}

    async def _fetch(lat, lon, timeout=None):
        n["fetch"] += 1
        return [dict(p) for p in POIS_OSM] if overpass_ok else None

    async def _capa(lat, lon):
        n["capa_propia"] += 1
        if capa_caida:
            raise RuntimeError("capa caída")
        return _materia(servicios)

    async def _zona(lat, lon):
        n["zona"] += 1
        if capa_caida:
            raise RuntimeError("capa caída")
        return _materia(servicios)

    async def _ddl(*a, **k):
        n["ddl"] += 1
    monkeypatch.setattr(assets, "_fetch_pois", _fetch)
    monkeypatch.setattr(rutas, "_recolectar_capa_propia", _capa)
    monkeypatch.setattr(rutas, "_recolectar_zona", _zona)
    monkeypatch.setattr(assets, "AsyncSessionLocal", lambda: sesion)
    monkeypatch.setattr(assets, "ensure_walk_score_fuente_column", _ddl)
    monkeypatch.setattr(assets.settings, FLAG, flag)
    asyncio.run(assets._recompute_walk_score("activo-1", LAT, LON))
    return sesion, n


def _plano(sql: str) -> str:
    return " ".join(sql.split())


def _docs(servicios=COMPLETA):
    m = _materia(servicios)
    return documentos_persistibles(m, ensamblar_place_context(m))


def _sin_volatiles(doc_json: str | None) -> dict | None:
    """El documento sin lo que cambia de una derivación a otra (instante e ids que dependen de él)."""
    if doc_json is None:
        return None
    d = json.loads(doc_json)
    d.pop("derived_at", None)
    for e in d.get("evidence", []):
        e.pop("evidence_id")
        if e["source_type"] != "public_dataset":
            e.pop("retrieved_at")
    for el in d.get("items", []) + ([d["stop"]] if d.get("stop") else []):
        for k in ("source_evidence_id", "method_evidence_id", "verification_evidence_ids"):
            el.pop(k)
    if d.get("walk_duration"):
        d["walk_duration"].pop("evidence_id")
    d["evidence"] = sorted(d["evidence"], key=lambda e: json.dumps(e, sort_keys=True))
    return d


# ══ A–C · flag apagado o esquema ausente: el camino de antes, idéntico ═══════════════
def test_A_flag_off_y_overpass_responde_es_el_update_de_siempre(monkeypatch):
    sesion, n = _corre(monkeypatch, flag=False)
    (sql, p), = sesion.updates
    assert _plano(sql) == UPDATE_PREVIO and set(p) == {"w", "f", "c", "s", "id"}
    ctx = ensamblar_place_context(_materia(COMPLETA))
    assert p["s"] == rutas.prosa_servicios(ctx) and p["c"] == rutas.prosa_conectividad(ctx)
    assert (sesion.catalogo, n["capa_propia"]) == (0, 0), "con el flag apagado ni catálogo ni capa propia aparte"


def test_B_flag_off_y_overpass_caido_sigue_sin_escribir_nada(monkeypatch):
    """La conducta de antes del cambio, paso a paso: un fetch, ningún otro acceso, ninguna escritura."""
    sesion, n = _corre(monkeypatch, flag=False, overpass_ok=False)
    assert sesion.updates == [] and sesion.catalogo == 0
    assert n == {"fetch": 1, "capa_propia": 0, "zona": 0, "ddl": 0}


@pytest.mark.parametrize("overpass_ok", [True, False])
def test_C_flag_on_y_esquema_ausente_cae_al_camino_previo(monkeypatch, overpass_ok):
    sesion, n = _corre(monkeypatch, con_041=False, overpass_ok=overpass_ok)
    assert sesion.catalogo == 1 and n["capa_propia"] == 0
    if overpass_ok:
        (sql, p), = sesion.updates
        assert _plano(sql) == UPDATE_PREVIO and "se" not in p and "ce" not in p
    else:
        assert sesion.updates == [] and n["ddl"] == 0


# ══ D · con la 041 y Overpass respondiendo: idéntico a antes de esta unidad ══════════
def test_D_con_evidencia_y_overpass_es_el_update_de_la_041_byte_a_byte(monkeypatch):
    sesion, n = _corre(monkeypatch)
    (sql, p), = sesion.updates
    assert _plano(sql) == _plano(UPDATE_041_COMPLETO)
    s = NearbyPlacesEvidenceV0.model_validate_json(p["se"])
    c = NearestTransitEvidenceV0.model_validate_json(p["ce"])
    assert p["s"] == formatear_servicios(s) and p["c"] == formatear_conectividad(c)
    assert p["f"] == "osm" and isinstance(p["w"], int)
    assert (n["capa_propia"], n["zona"], n["fetch"], n["ddl"]) == (1, 0, 1, 1)


# ══ E · EL DEFECTO: con la 041 y Overpass caído, la evidencia propia SE PERSISTE ═════
def test_E_con_evidencia_y_sin_overpass_persiste_la_evidencia_y_no_toca_el_walk_score(monkeypatch):
    sesion, n = _corre(monkeypatch, overpass_ok=False)
    (sql, p), = sesion.updates                                       # K: exactamente UN UPDATE
    assert _plano(sql) == _plano(UPDATE_SIN_OVERPASS)
    assert "w" not in p and "f" not in p, "sin Overpass no se fabrica walk score ni su procedencia"
    s = NearbyPlacesEvidenceV0.model_validate_json(p["se"])
    c = NearestTransitEvidenceV0.model_validate_json(p["ce"])
    assert s.status is MeasureStatus.AVAILABLE and c.status is MeasureStatus.AVAILABLE
    assert p["s"] == formatear_servicios(s) and p["c"] == formatear_conectividad(c)   # N
    assert n == {"fetch": 1, "capa_propia": 1, "zona": 0, "ddl": 1}


def test_E2_la_evidencia_sin_overpass_es_la_misma_que_con_overpass(monkeypatch):
    """Overpass no entra en la evidencia: los documentos son los mismos (salvo el instante)."""
    con, _ = _corre(monkeypatch, overpass_ok=True)
    sin, _ = _corre(monkeypatch, overpass_ok=False)
    pc, ps = con.updates[0][1], sin.updates[0][1]
    assert _sin_volatiles(pc["se"]) == _sin_volatiles(ps["se"])
    assert _sin_volatiles(pc["ce"]) == _sin_volatiles(ps["ce"])
    assert (pc["s"], pc["c"]) == (ps["s"], ps["c"])


# ══ F–H · evidencia parcial, ninguna, o una categoría que el método no explica ═══════
def test_F_evidencia_parcial_sin_overpass_escribe_solo_la_dimension_respaldada(monkeypatch):
    """Sin transporte en la capa, la conectividad es `insufficient_evidence`: sin Overpass, eso NO
    sobrescribe lo que ya está. Solo se escriben los servicios."""
    sesion, _ = _corre(monkeypatch, overpass_ok=False, servicios=[_poi("parque", 254, 11)])
    (sql, p), = sesion.updates
    assert _plano(sql) == ("UPDATE activos_inmutables SET servicios_cercanos = :s, "
                           "servicios_evidencia = CAST(:se AS jsonb) WHERE id = :id")
    assert set(p) == {"s", "se", "id"}


def test_F2_solo_conectividad_respaldada_sin_overpass(monkeypatch):
    """La única categoría de servicio no la explica el método (#186): el documento de servicios es
    UNKNOWN y solo se escribe la conectividad."""
    sesion, _ = _corre(monkeypatch, overpass_ok=False,
                       servicios=[_poi("supermercado", 120, 50, dataset="overture", categoria_capa_origen="cafe"),
                                  _transporte()])
    (sql, p), = sesion.updates
    assert _plano(sql) == ("UPDATE activos_inmutables SET conectividad = :c, "
                           "conectividad_evidencia = CAST(:ce AS jsonb) WHERE id = :id")
    assert set(p) == {"c", "ce", "id"}


@pytest.mark.parametrize("caso", ["capa vacía", "capa caída", "sin procedencia y sin transporte"])
def test_G_sin_evidencia_propia_y_sin_overpass_es_NO_WRITE(monkeypatch, caso):
    """Ninguna dimensión `available`: servicios UNKNOWN (capa vacía, caída, o un POI sin identidad) y
    conectividad UNKNOWN o insuficiente. Sin Overpass no hay nada que escribir: como antes."""
    servicios = {"capa vacía": [], "capa caída": COMPLETA,
                 "sin procedencia y sin transporte": [_poi("parque", 254, None)]}[caso]
    sesion, n = _corre(monkeypatch, overpass_ok=False, servicios=servicios, capa_caida=caso == "capa caída")
    assert sesion.updates == [] and n["ddl"] == 0


def test_H_categoria_no_explicada_con_overpass_conserva_el_respaldo_de_siempre(monkeypatch):
    """Con Overpass, la dimensión sin evidencia sigue con su texto de respaldo y la evidencia en NULL,
    como antes. Nunca se promociona el respaldo a evidencia."""
    sesion, _ = _corre(monkeypatch, servicios=[
        _poi("supermercado", 120, 50, dataset="overture", categoria_capa_origen="cafe"), _transporte()])
    (sql, p), = sesion.updates
    assert _plano(sql) == _plano(UPDATE_041_COMPLETO)
    assert p["se"] is None and p["s"] is not None and p["ce"] is not None


def test_la_capa_caida_con_overpass_escribe_el_respaldo_y_ninguna_evidencia(monkeypatch):
    sesion, _ = _corre(monkeypatch, capa_caida=True)
    (sql, p), = sesion.updates
    assert p["se"] is None and p["ce"] is None and p["w"] is not None


# ══ L · sin Google ═════════════════════════════════════════════════════════════════
def test_L_sin_google_en_lo_que_se_escribe(monkeypatch):
    sesion, _ = _corre(monkeypatch, overpass_ok=False)
    _, p = sesion.updates[0]
    assert "google" not in json.dumps(p).lower()


# ══ El derivador reutilizable: SOLO la capa propia ══════════════════════════════════
def test_el_derivador_no_toca_overpass_ni_nominatim(monkeypatch):
    """Se CUENTAN las llamadas en vez de lanzar: `_recolectar_zona` usa `gather(return_exceptions=True)`
    y se tragaría una excepción (control por mutación: lanzar dejaba pasar la regresión)."""
    import app.agent.tools as tools
    externas = []

    async def _externa(*a, **k):
        externas.append(a)
        return {}

    async def _capa(lat, lon, n=6):
        return [dict(s) for s in COMPLETA]
    monkeypatch.setattr(rutas, "walk_score_para", _externa)
    monkeypatch.setattr(tools, "_reverse_geocode", _externa)
    monkeypatch.setattr(rutas, "_servicios_con_coords", _capa)
    ev = asyncio.run(rutas.evidencia_de_capa_propia(LAT, LON))
    assert externas == [], "el derivador de la capa propia llamó a Overpass o a Nominatim"
    ref = _docs(COMPLETA)
    for dim in ("servicios", "conectividad"):
        assert _sin_volatiles(ev.documentos[dim].model_dump_json()) == _sin_volatiles(ref[dim].model_dump_json())
    ctx = ensamblar_place_context(_materia(COMPLETA))
    assert (ev.servicios_texto, ev.conectividad_texto) == (rutas.prosa_servicios(ctx), rutas.prosa_conectividad(ctx))


def test_recolectar_zona_sigue_igual(monkeypatch):
    """`_recolectar_zona` (el camino sin la 041 y el del agente) no cambia: geo + walk + capa."""
    import app.agent.tools as tools

    async def _geo(lat, lon):
        return {"barrio": "Centro"}

    async def _walk(lat, lon):
        return {"walk_score": 90, "pois_analizados": 5}

    async def _capa(lat, lon, n=6):
        return [dict(s) for s in COMPLETA]
    monkeypatch.setattr(tools, "_reverse_geocode", _geo)
    monkeypatch.setattr(rutas, "walk_score_para", _walk)
    monkeypatch.setattr(rutas, "_servicios_con_coords", _capa)
    m = asyncio.run(rutas._recolectar_zona(LAT, LON))
    assert m.lugar == {"barrio": "Centro"} and m.walk["walk_score"] == 90 and len(m.servicios) == len(COMPLETA)


# ══ Observabilidad: Overpass deja rastro, sin coordenadas ni consulta ═════════════════
class _ClienteQueFalla:
    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **k):
        import httpx
        raise httpx.ConnectTimeout("timeout")


def test_overpass_registra_cada_mirror_que_falla_sin_coordenadas(monkeypatch, caplog):
    monkeypatch.setattr(overpass.httpx, "AsyncClient", _ClienteQueFalla)
    with caplog.at_level(logging.INFO, logger=overpass.__name__):
        assert asyncio.run(overpass._fetch_pois(LAT, LON, timeout=1.0)) is None
    textos = [r.getMessage() for r in caplog.records]
    assert any("mirror=overpass-api.de" in t and "exc=ConnectTimeout" in t and "outcome=fallo" in t for t in textos)
    assert any("mirror=overpass.kumi.systems" in t for t in textos)
    assert any("outcome=sin_respuesta" in t for t in textos)
    assert not any(str(LAT) in t or str(LON) in t or "around:" in t for t in textos)


def test_el_escritor_registra_su_resultado(monkeypatch, caplog):
    with caplog.at_level(logging.INFO, logger=assets.__name__):
        _corre(monkeypatch, overpass_ok=False)
    linea = next(r.getMessage() for r in caplog.records if "foso=recompute " in r.getMessage())
    assert "overpass=sin_respuesta" in linea and "escritura=update" in linea and "columnas=c,s,se,ce" in linea
    assert str(LAT) not in linea


# ══ Postgres real: el CHECK, el trigger y las otras filas ═══════════════════════════
async def _filas(banco) -> dict:
    async with banco["dueno"].connect() as cx:
        return {r["id"]: dict(r) for r in (await cx.execute(text(
            "SELECT id::text AS id, walk_score, walk_score_fuente, servicios_cercanos, conectividad, "
            "servicios_evidencia::text AS se, conectividad_evidencia::text AS ce, geom::text AS geom "
            "FROM public.activos_inmutables ORDER BY id"))).mappings().all()}


def _engancha_banco(monkeypatch, banco, *, overpass_ok):
    async def _fetch(lat, lon, timeout=None):
        return [dict(p) for p in POIS_OSM] if overpass_ok else None

    async def _capa(lat, lon):
        return _materia(COMPLETA)

    async def _nada(*a, **k):
        return None
    monkeypatch.setattr(assets, "_fetch_pois", _fetch)
    monkeypatch.setattr(rutas, "_recolectar_capa_propia", _capa)
    monkeypatch.setattr(assets, "AsyncSessionLocal", banco["Sesion"])
    monkeypatch.setattr(assets.settings, FLAG, True)
    monkeypatch.setattr(assets, "ensure_walk_score_fuente_column", _nada)


@pg
async def test_PG_E_M_N_sin_overpass_la_base_acepta_la_evidencia_y_solo_cambia_esa_fila(banco, monkeypatch):
    await _aplica(banco["dueno"])
    uid = str(uuid.UUID(int=1))
    antes = await _filas(banco)
    _engancha_banco(monkeypatch, banco, overpass_ok=False)
    await assets._recompute_walk_score(uid, LAT, LON)
    despues = await _filas(banco)
    assert [k for k in antes if antes[k] != despues[k]] == [uid], "M: cambió otra fila, o ninguna"
    a, d = antes[uid], despues[uid]
    assert (d["walk_score"], d["walk_score_fuente"], d["geom"]) == (a["walk_score"], a["walk_score_fuente"], a["geom"])
    assert d["se"] is not None and d["ce"] is not None
    fila = {"lat": LAT, "lon": LON, "servicios_evidencia": d["se"], "servicios_cercanos": d["servicios_cercanos"],
            "conectividad_evidencia": d["ce"], "conectividad": d["conectividad"]}
    for dim, col in (("servicios", "servicios_cercanos"), ("conectividad", "conectividad")):
        lectura = leer_contexto_persistido(fila, dim)
        assert lectura.estado == "estructurada" and lectura.texto == d[col], dim   # N: texto = render


@pg
async def test_PG_I_un_CHECK_que_rechaza_no_deja_nada_a_medias_aun_sin_overpass(banco, monkeypatch):
    await _aplica(banco["dueno"])
    uid = str(uuid.UUID(int=1))
    antes = await _fila_entorno(banco, uid)
    _engancha_banco(monkeypatch, banco, overpass_ok=False)
    real = assets.a_json

    def _a_json_roto(doc):
        if doc is not None and doc.dimension == "nearest_transit":
            return json.dumps({"contract_version": "place-dimension-evidence/v0", "status": "unknown"})
        return real(doc)
    monkeypatch.setattr(assets, "a_json", _a_json_roto)
    await assets._recompute_walk_score(uid, LAT, LON)        # best-effort: traga el error del CHECK
    assert await _fila_entorno(banco, uid) == antes, "el CHECK rechazó y quedó texto o evidencia a medias"


@pg
async def test_PG_D_con_overpass_el_texto_la_evidencia_y_el_walk_score_quedan_juntos(banco, monkeypatch):
    await _aplica(banco["dueno"])
    uid = str(uuid.UUID(int=1))
    _engancha_banco(monkeypatch, banco, overpass_ok=True)
    await assets._recompute_walk_score(uid, LAT, LON)
    d = (await _filas(banco))[uid]
    assert d["walk_score_fuente"] == "osm" and d["se"] is not None and d["ce"] is not None
    s = NearbyPlacesEvidenceV0.model_validate_json(d["se"])
    assert d["servicios_cercanos"] == formatear_servicios(s)
