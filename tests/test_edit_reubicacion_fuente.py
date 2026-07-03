"""Regresión de honestidad (Mejora B, hallazgo top de la revisión adversaria 2026-07-03):

Al editar la dirección de un inmueble, edit_asset reubica geom pero ANTES solo actualizaba
direccion/geom, dejando el walk_score (y su procedencia) de la dirección VIEJA. Si ese
inmueble tenía walk_score_fuente='osm' y el job de fondo fallaba (Overpass caído), el anuncio
afirmaba "calculada sobre los comercios reales (OpenStreetMap)" para un score de OTRA
ubicación — la mentira exacta que Mejora B busca eliminar, pero en dirección opuesta.

El fix recomputa la capa base heurística SÍNCRONA al cambiar de dirección y marca
walk_score_fuente='heuristico', dejando score y rótulo coherentes con la nueva zona de
inmediato; el job luego lo SUBE a 'osm' si cuenta POIs reales. Este test blinda ese invariante.
"""
import asyncio
import uuid

from app.auth import CurrentUser
from app.routers import assets
from app.routers.assets import EditAssetRequest


class _FakeBackgroundTasks:
    def __init__(self):
        self.tareas: list[tuple] = []

    def add_task(self, func, *args, **kwargs):
        self.tareas.append((func, args, kwargs))


class _Mappings:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _Result:
    def __init__(self, row=None, rowcount=0):
        self._row = row
        self.rowcount = rowcount

    def mappings(self):
        return _Mappings(self._row)


class _FakeSession:
    """Despacha por el texto del SQL: ownership + estado actual devuelven filas; el
    UPDATE de activos_inmutables se captura; ALTER/DELETE son no-op. Sin DB real."""

    def __init__(self, cur_row):
        self._cur_row = cur_row
        self.updates_activo: list[tuple] = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "owner_user_id" in sql:  # _assert_owner
            return _Result(row={"u": "u1", "a": None})
        if "SELECT direccion_estandarizada" in sql:  # estado actual
            return _Result(row=self._cur_row)
        if "UPDATE activos_inmutables SET" in sql:  # el UPDATE bajo prueba
            self.updates_activo.append((sql, params or {}))
            return _Result(rowcount=1)
        return _Result(rowcount=0)  # ALTER (ensure), DELETE aura cache, etc.

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _correr_edit(monkeypatch, cur_row, nueva_dir):
    async def _fake_geocode(_d):
        return (-0.30, -78.44)  # coords nuevas (Cumbayá aprox.)

    async def _fake_wsp(*_a, **_k):
        return None

    monkeypatch.setattr(assets, "_geocode", _fake_geocode)
    monkeypatch.setattr(assets, "_guardar_wsp_corredor", _fake_wsp)
    # Forzar que el ensure ejerza su execute (idempotente sobre el fake) en cualquier orden.
    monkeypatch.setattr(assets, "_walk_score_fuente_ready", False, raising=False)

    payload = EditAssetRequest(direccion=nueva_dir)
    user = CurrentUser(user_id="u1")
    background = _FakeBackgroundTasks()
    db = _FakeSession(cur_row=cur_row)
    res = asyncio.run(assets.edit_asset(uuid.uuid4(), payload, background, user, db))
    return res, db, background


def test_reubicacion_degrada_walk_score_fuente_a_heuristico(monkeypatch):
    # Inmueble que venía de La Mariscal con score OSM; se muda a Cumbayá.
    res, db, background = _correr_edit(
        monkeypatch,
        cur_row={"dir": "Av. Colón, La Mariscal", "tipo": "Departamento",
                 "lat": -0.205, "lon": -78.492},
        nueva_dir="Av. Interoceánica y Pampite, Cumbayá",
    )
    assert res["reubicado"] is True

    # El UPDATE del activo degrada la procedencia y reescribe el score a la nueva zona.
    assert db.updates_activo, "esperaba un UPDATE de activos_inmutables al reubicar"
    sql, params = db.updates_activo[0]
    assert "walk_score_fuente = 'heuristico'" in sql  # jamás dejar 'osm' viejo pegado
    assert "walk_score = :ws" in sql
    assert isinstance(params.get("ws"), int)  # score heurístico de la NUEVA dirección
    assert params.get("ruido") in ("BAJO", "MEDIO", "ALTO")

    # Y encola el recompute que luego SUBE la caminabilidad a 'osm' con POIs reales.
    assert any(f is assets._recompute_walk_score for f, _a, _k in background.tareas)


def test_sin_cambio_de_direccion_no_toca_walk_score_fuente(monkeypatch):
    # Editar solo el precio (sin dirección) → direccion_cambio=False → NO reescribe la
    # procedencia: solo la reubicación degrada la fuente, una edición de precio no.
    async def _fake_geocode(_d):
        return (-0.30, -78.44)

    async def _fake_wsp(*_a, **_k):
        return None

    monkeypatch.setattr(assets, "_geocode", _fake_geocode)
    monkeypatch.setattr(assets, "_guardar_wsp_corredor", _fake_wsp)

    payload = EditAssetRequest(precio=123000)  # sin dirección
    user = CurrentUser(user_id="u1")
    background = _FakeBackgroundTasks()
    db = _FakeSession(cur_row={"dir": "Av. Colón, La Mariscal", "tipo": "Departamento",
                               "lat": -0.205, "lon": -78.492})
    asyncio.run(assets.edit_asset(uuid.uuid4(), payload, background, user, db))

    # No hubo reubicación → ningún UPDATE de activos_inmutables tocó walk_score_fuente.
    for sql, _p in db.updates_activo:
        assert "walk_score_fuente" not in sql
