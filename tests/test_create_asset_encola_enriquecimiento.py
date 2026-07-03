"""Test del bug real (feedback en vivo, 2026-07-01): POST /api/v1/assets/ creaba el
activo con SOLO los scores heurísticos y nunca encolaba el enriquecimiento real
(_recompute_walk_score: Overpass + Google Routes/Places) — a diferencia de /publish,
que sí lo hacía. Resultado: 39/40 activos en producción (los cargados por
scripts/hidratar_activos.py, que usa este endpoint) nacían sin servicios_cercanos/
conectividad hasta correr un backfill manual. El fix encola la misma background task
que ya usa /publish justo después de crear el activo.
"""
import asyncio
import uuid
from datetime import datetime, timezone

from app.routers import assets
from app.schemas import ActivoCreateRequest


class _FakeBackgroundTasks:
    def __init__(self):
        self.tareas: list[tuple] = []

    def add_task(self, func, *args, **kwargs):
        self.tareas.append((func, args, kwargs))


class _FakeResult:
    def __init__(self, asset):
        self._asset = asset


class _FakeSession:
    """Suficiente para satisfacer add/flush/refresh + el auto-sanado de la columna
    de procedencia (ensure_walk_score_fuente_column: execute/commit no-op) sin DB real."""

    async def execute(self, *a, **k):
        return _FakeResult(None)

    async def commit(self):
        pass

    def add(self, obj):
        pass

    async def flush(self):
        pass

    async def refresh(self, obj):
        if obj.id is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime(2026, 7, 1, tzinfo=timezone.utc)


def test_create_asset_encola_recompute_walk_score(monkeypatch):
    payload = ActivoCreateRequest(
        latitude=-0.1795,
        longitude=-78.4825,
        direccion_estandarizada="Av. 6 de Diciembre N36-109 y Bosmediano, La Carolina",
    )
    background = _FakeBackgroundTasks()
    db = _FakeSession()

    resultado = asyncio.run(assets.create_asset(payload, background, db))

    # El activo se sigue creando con los scores heurísticos como antes (no rompe nada).
    assert resultado.direccion_estandarizada == payload.direccion_estandarizada

    # El punto central del fix: se encoló _recompute_walk_score con el id recién creado
    # y las MISMAS coordenadas del payload — antes de este fix esta lista quedaba vacía.
    assert len(background.tareas) == 1
    func, args, _kwargs = background.tareas[0]
    assert func is assets._recompute_walk_score
    assert args == (str(resultado.id), payload.latitude, payload.longitude)
