"""RELEASE-ISOLATION-041 0.1 · desplegar `main` no activa PLACE-PROVENANCE-041.

La 041 escribe evidencia en `activos_inmutables` SÓLO si se cumplen las dos condiciones:

    settings.place_provenance_041_write_enabled  (PLACE_PROVENANCE_041_WRITE_ENABLED, apagado de fábrica)
    Y  esquema_041_presente() == True

Sin el flag, el escritor toma el camino de antes de la 041 aunque las columnas existan: ni consulta
el catálogo ni toca `*_evidencia`. Es lo que pasa en Render, donde la variable no existe. El
comportamiento de la 041 ENCENDIDA lo siguen fijando los tests de `test_place_provenance_041.py` §9.
"""
from __future__ import annotations

import ast
import asyncio
import pathlib

import pytest

import app.place.persistible as persistible
import app.routers.assets as assets
import app.rutas as rutas
from app import config
from app.place.assembler import ensamblar_place_context
from tests.test_place_provenance_041 import COMPLETA, LAT, LON, _materia, _Sesion

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FLAG = "place_provenance_041_write_enabled"
VARIABLE = "PLACE_PROVENANCE_041_WRITE_ENABLED"
# El UPDATE del escritor ANTES de #178 (c4668d2), carácter por carácter.
UPDATE_PREVIO_A_LA_041 = ("UPDATE activos_inmutables SET walk_score = :w, walk_score_fuente = :f, "
                          "conectividad = :c, servicios_cercanos = :s WHERE id = :id")


@pytest.fixture(autouse=True)
def _sin_cache_de_esquema(monkeypatch):
    monkeypatch.setattr(persistible, "_esquema_041_visto", False)


class _SesionVigilada(_Sesion):
    """La sesión falsa de la 041, que además registra si alguien consultó el catálogo."""

    def __init__(self, con_041):
        super().__init__(con_041)
        self.catalogo = 0

    async def execute(self, stmt, params=None):
        if "information_schema.columns" in str(stmt):
            self.catalogo += 1
        return await super().execute(stmt, params)


def _escribir(monkeypatch, con_041: bool, flag: bool | None):
    """Corre el escritor REAL. `flag=None` = no se toca: el valor de fábrica de Settings."""
    sesion = _SesionVigilada(con_041)
    llamadas = {"con_evidencia": 0}

    async def _fetch(lat, lon, timeout=None):
        return [{"lat": LAT, "lon": LON, "tags": {"amenity": "pharmacy", "name": "Farmacia OSM"}}]

    async def _recolecta(lat, lon):
        return _materia(COMPLETA)

    original = rutas.analizar_zona_con_evidencia

    async def _con_evidencia(lat, lon):
        llamadas["con_evidencia"] += 1
        return await original(lat, lon)

    async def _nada(*a, **k):
        return None

    monkeypatch.setattr(assets, "_fetch_pois", _fetch)
    monkeypatch.setattr(rutas, "_recolectar_zona", _recolecta)
    monkeypatch.setattr(rutas, "analizar_zona_con_evidencia", _con_evidencia)
    monkeypatch.setattr(assets, "AsyncSessionLocal", lambda: sesion)
    monkeypatch.setattr(assets, "ensure_walk_score_fuente_column", _nada)
    if flag is not None:
        monkeypatch.setattr(assets.settings, FLAG, flag)
    asyncio.run(assets._recompute_walk_score("activo-1", LAT, LON))
    assert len(sesion.updates) == 1, sesion.updates
    sql, params = sesion.updates[0]
    return sql, params, sesion.catalogo, llamadas["con_evidencia"]


def _es_camino_previo(sql: str, params: dict) -> None:
    assert " ".join(sql.split()) == UPDATE_PREVIO_A_LA_041
    assert set(params) == {"w", "f", "c", "s", "id"}
    ctx = ensamblar_place_context(_materia(COMPLETA))
    assert params["s"] == rutas.prosa_servicios(ctx) and params["c"] == rutas.prosa_conectividad(ctx)


# ══ La matriz del mandato ═════════════════════════════════════════════════════════════

def test_flag_off_y_esquema_presente_es_el_camino_previo_sin_evidencia(monkeypatch):
    sql, p, catalogo, con_evidencia = _escribir(monkeypatch, con_041=True, flag=False)
    _es_camino_previo(sql, p)
    assert "_evidencia" not in sql and "se" not in p and "ce" not in p
    assert catalogo == 0, "con el flag apagado ni se mira el catálogo"
    assert con_evidencia == 0


def test_flag_off_y_esquema_ausente_es_el_camino_previo(monkeypatch):
    sql, p, catalogo, con_evidencia = _escribir(monkeypatch, con_041=False, flag=False)
    _es_camino_previo(sql, p)
    assert catalogo == 0 and con_evidencia == 0


def test_flag_on_y_esquema_presente_es_la_041_de_hoy(monkeypatch):
    sql, p, catalogo, con_evidencia = _escribir(monkeypatch, con_041=True, flag=True)
    assert "servicios_evidencia = CAST(:se AS jsonb)" in sql
    assert "conectividad_evidencia = CAST(:ce AS jsonb)" in sql
    assert p["se"] is not None and p["ce"] is not None
    assert catalogo == 1 and con_evidencia == 1


def test_flag_on_y_esquema_ausente_cae_al_camino_previo(monkeypatch):
    sql, p, catalogo, con_evidencia = _escribir(monkeypatch, con_041=False, flag=True)
    _es_camino_previo(sql, p)
    assert catalogo == 1, "con el flag encendido sí se consulta el catálogo"
    assert con_evidencia == 0


def test_sin_tocar_el_flag_el_valor_de_fabrica_no_activa_la_041(monkeypatch):
    """Lo que pasará en Render: la variable no existe y el esquema 041 SÍ está aplicado."""
    assert getattr(assets.settings, FLAG) is False
    sql, p, catalogo, con_evidencia = _escribir(monkeypatch, con_041=True, flag=None)
    _es_camino_previo(sql, p)
    assert catalogo == 0 and con_evidencia == 0


# ══ El flag: de dónde puede venir ═════════════════════════════════════════════════════

def test_el_default_es_off_por_construccion():
    campo = config.Settings.model_fields[FLAG]
    assert campo.default is False and campo.annotation is bool
    assert campo.alias is None and campo.validation_alias is None, "sólo su propio nombre lo enciende"
    assert not config.Settings.model_config.get("env_prefix")


def _settings_con(monkeypatch, entorno: dict) -> config.Settings:
    for nombre in list(__import__("os").environ):
        if nombre.upper() == VARIABLE:
            monkeypatch.delenv(nombre)
    for k, v in entorno.items():
        monkeypatch.setenv(k, v)
    return config.Settings(_env_file=None)


def test_un_entorno_como_el_de_render_no_activa_la_041(monkeypatch):
    """Las claves de `render.yaml` más las que Render inyecta y las de los flags del Buyer: ninguna
    es la del flag. La variable la introduce este cambio, así que hoy no existe en Render; y
    `.env` está en .gitignore, así que el build no trae ninguno."""
    render = {k: "x" for k in (
        "DATABASE_URL_OVERRIDE", "ANTHROPIC_API_KEY", "SSL_VERIFY", "DB_POOL_SIZE", "DB_MAX_OVERFLOW",
        "CHECKPOINTER_POOL_SIZE", "VALHALLA_URL", "POSTGRES_HOST", "POSTGRES_DB", "POSTGRES_USER",
        "POSTGRES_PASSWORD", "RENDER", "RENDER_GIT_COMMIT", "RENDER_SERVICE_ID", "REENGANCHE_BAJA_SECRET")}
    render.update({"POSTGRES_PORT": "5432", "DB_POOL_SIZE": "5", "DB_MAX_OVERFLOW": "5",
                   "CHECKPOINTER_POOL_SIZE": "4", "LLM_MODEL": "claude-sonnet-4-5-20250929",
                   "SSL_VERIFY": "true", "BUYER_UPDATER_SHADOW": "true", "BUYER_UNRESOLVED_PRODUCT": "true"})
    assert getattr(_settings_con(monkeypatch, render), FLAG) is False
    assert ".env" in (RAIZ / ".gitignore").read_text(encoding="utf-8").split()


@pytest.mark.parametrize("valor,esperado", [
    ("true", True), ("TRUE", True), ("1", True),
    ("false", False), ("False", False), ("0", False),
    ("", False),  # env_ignore_empty: vacía = ausente = apagado
])
def test_solo_el_valor_explicito_lo_enciende(monkeypatch, valor, esperado):
    assert getattr(_settings_con(monkeypatch, {VARIABLE: valor}), FLAG) is esperado


# ══ Guarda estructural ════════════════════════════════════════════════════════════════

def test_nadie_en_app_consulta_el_esquema_041_fuera_del_gate():
    """Toda llamada a `esquema_041_presente` en `app/` (fuera de su definición) va dentro de un
    `if` que lee el flag. Un escritor nuevo que la llamara sin el gate reabriría la fuga."""
    sueltas, dentro = [], 0
    for ruta in sorted((RAIZ / "app").rglob("*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        padres = {hijo: nodo for nodo in ast.walk(arbol) for hijo in ast.iter_child_nodes(nodo)}
        for n in ast.walk(arbol):
            if not (isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", None))
                    == "esquema_041_presente"):
                continue
            p, protegida = n, False
            while p in padres:
                p = padres[p]
                if isinstance(p, ast.If) and FLAG in ast.unparse(p.test):
                    protegida = True
                    break
            if protegida:
                dentro += 1
            else:
                sueltas.append(f"{ruta.relative_to(RAIZ).as_posix()}:{n.lineno}")
    assert sueltas == []
    assert dentro == 1, "el inventario cambió: mirar el escritor nuevo"
