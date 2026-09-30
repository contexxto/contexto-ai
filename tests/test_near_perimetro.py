"""NEAR-PERIMETER REMEDIATION 0.1 — `/near` sin sesión da solo lo espacial (opción A).

Decisión de producto (2026-09-30): `/near` sigue el MISMO criterio que `/geojson`. Sin sesión
devuelve la estructura espacial —id, dirección, tipo, piso, imagen, geometría, distancia y el
total—; los scores (walk, ruido, vegetación, tráfico), el entorno legado (conectividad,
servicios), el estado de revisión y la confianza, solo con sesión. `scores_incluidos` lo dice.

Por qué: el preflight midió que 4 consultas anónimas de 5 km bajaban el catastro enriquecido
entero, estado interno de revisión incluido, sin que ningún consumidor del producto usara esos
campos (el botón «¿Puedo vivir aquí?» se retiró el 2026-06-12 y solo leía `total`).

Qué demuestra (numerado como el mandato):
  1. anónimo: estructura espacial, ningún score;
  2. anónimo: ni `estado_revision` ni `confianza`;
  3. con sesión: la respuesta enriquecida (el conjunto de /geojson con sesión + `distancia_m`),
     y el legado sigue pasando por la frontera de D1;
  4. `scores_incluidos` refleja la realidad;
  5. `operacion` sigue funcionando;
  6. `distancia_m` sigue funcionando (y el tope de radio sigue en 5 000 m);
  7. radio vacío → FeatureCollection vacía;
  8. neutralizar la compuerta hace fallar la prueba (mutación real del código del endpoint);
  9. las guardas MAP-SOURCE-BOUNDARY y D1 viven en sus propios ficheros y corren en la misma suite.
"""
from __future__ import annotations

import asyncio
import inspect
import textwrap
from decimal import Decimal

import httpx
import pytest

import app.routers.assets as assets
from app.auth import CurrentUser

LAT, LON = -0.1807, -78.4678
ESPACIAL = {"id", "direccion", "tipo_activo", "piso_altura", "imagen_url", "distancia_m"}
SOLO_CON_SESION = {"walk_score", "ruido", "vegetacion", "trafico", "conectividad",
                   "servicios_cercanos", "estado_revision", "confianza"}
TEXTO_LEGADO = "💊 Farmacia Legada a ~120 m · 🌳 Parque Legado a ~300 m"


def _fila(i, distancia, **over):
    fila = {"id": f"0cb128c9-0000-4000-8000-00000000n{i:03d}", "direccion": f"Calle {i}",
            "tipo_activo": "Departamento", "piso_altura": 3, "walk_score": 82, "ruido": "MEDIO",
            "vegetacion": Decimal("12.50"), "trafico": 3, "conectividad": "🚇 Estación Legada ~500 m",
            "servicios_cercanos": TEXTO_LEGADO, "imagen_url": f"https://img/{i}.jpg",
            "lon": LON + i / 1000, "lat": LAT, "estado_revision": "pendiente_revision",
            "confianza_extraccion": Decimal("0.91"), "distancia_m": distancia}
    fila.update(over)
    return fila


FILAS = [_fila(1, Decimal("120")), _fila(2, Decimal("480"), estado_revision="publicado")]


class _Res:
    def __init__(self, filas):
        self.filas = filas

    def mappings(self):
        return self

    def all(self):
        return list(self.filas)


class _Sesion:
    def __init__(self, filas, registro):
        self.filas, self.registro = filas, registro

    async def execute(self, stmt, params=None):
        self.registro.append((str(stmt), dict(params or {})))
        return _Res(self.filas)


@pytest.fixture
def near(monkeypatch):
    """Llama al endpoint REAL por HTTP (ASGI) con la base doblada. Devuelve (json, sql, params)."""
    import main
    from app.auth import get_optional_user
    from app.database import get_db
    from app.limiter import limiter

    monkeypatch.setattr(limiter, "enabled", False)

    def pedir(filas=FILAS, *, sesion=False, ruta="/api/v1/assets/near", **query):
        registro: list = []

        async def _db():
            yield _Sesion(filas, registro)
        main.app.dependency_overrides[get_db] = _db
        main.app.dependency_overrides[get_optional_user] = (
            (lambda: CurrentUser(user_id="u-near")) if sesion else (lambda: None))
        params = {"lat": LAT, "lon": LON, **query}

        async def _go():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                         base_url="http://test") as c:
                return await c.get(ruta, params=params)
        try:
            r = asyncio.run(_go())
        finally:
            main.app.dependency_overrides.pop(get_db, None)
            main.app.dependency_overrides.pop(get_optional_user, None)
        assert r.status_code == 200, r.text
        sql, prm = registro[-1] if registro else ("", {})
        return r.json(), sql, prm

    return pedir


def _solo_espacial(respuesta):
    """El contrato anónimo, entero. Se usa también en la mitad negativa (8)."""
    assert respuesta["scores_incluidos"] is False
    for f in respuesta["features"]:
        assert f["type"] == "Feature" and f["geometry"]["type"] == "Point"
        assert len(f["geometry"]["coordinates"]) == 2
        props = f["properties"]
        assert set(props) == ESPACIAL, sorted(set(props) ^ ESPACIAL)
        assert not (set(props) & SOLO_CON_SESION)


# ── 1 · 2 · el contrato anónimo ──────────────────────────────────────────────────
def test_1_anonimo_recibe_la_estructura_espacial_y_ningun_score(near):
    d, _, _ = near()
    assert d["type"] == "FeatureCollection" and d["total"] == 2 and len(d["features"]) == 2
    _solo_espacial(d)
    p = d["features"][0]["properties"]
    assert p["direccion"] == "Calle 1" and p["tipo_activo"] == "Departamento" and p["distancia_m"] == 120
    for campo in ("walk_score", "ruido", "vegetacion", "trafico", "conectividad", "servicios_cercanos"):
        assert campo not in p


def test_2_anonimo_no_recibe_estado_revision_ni_confianza(near):
    d, _, _ = near()
    for f in d["features"]:
        assert "estado_revision" not in f["properties"]
        assert "confianza" not in f["properties"]


# ── 3 · con sesión, lo enriquecido (y D1 intacto) ─────────────────────────────────
def test_3_con_sesion_recibe_la_respuesta_enriquecida(near):
    d, _, _ = near(sesion=True)
    assert d["scores_incluidos"] is True
    p = d["features"][0]["properties"]
    assert set(p) == ESPACIAL | SOLO_CON_SESION
    assert (p["walk_score"], p["ruido"], p["vegetacion"], p["trafico"]) == (82, "MEDIO", 12.5, 3)
    assert p["estado_revision"] == "pendiente_revision" and p["confianza"] == 0.91
    # D1: sin procedencia propia, el legado sigue en None aunque haya sesión.
    assert p["conectividad"] is None and p["servicios_cercanos"] is None


def test_3_con_sesion_el_legado_con_procedencia_propia_vuelve_por_la_frontera(near):
    d, _, _ = near([_fila(1, Decimal("120"), contexto_procedencia="propio")], sesion=True)
    assert d["features"][0]["properties"]["servicios_cercanos"] == TEXTO_LEGADO


def test_3_con_sesion_el_conjunto_es_el_de_geojson_con_sesion_mas_la_distancia(near):
    """«No duplicar política»: la paridad con /geojson se mide contra el endpoint real."""
    g, _, _ = near(sesion=True, ruta="/api/v1/assets/geojson")
    n, _, _ = near(sesion=True)
    assert set(n["features"][0]["properties"]) == set(g["features"][0]["properties"]) | {"distancia_m"}
    g_anon, _, _ = near(ruta="/api/v1/assets/geojson")
    n_anon, _, _ = near()
    assert set(n_anon["features"][0]["properties"]) == set(g_anon["features"][0]["properties"]) | {"distancia_m"}


# ── 4 · la señal ─────────────────────────────────────────────────────────────────
def test_4_scores_incluidos_refleja_la_realidad(near):
    anon, _, _ = near()
    con, _, _ = near(sesion=True)
    assert anon["scores_incluidos"] is False
    assert not any(set(f["properties"]) & SOLO_CON_SESION for f in anon["features"])
    assert con["scores_incluidos"] is True
    assert all(SOLO_CON_SESION <= set(f["properties"]) for f in con["features"])


# ── 5 · 6 · 7 · lo que no cambia ─────────────────────────────────────────────────
@pytest.mark.parametrize("sesion", [False, True], ids=["anonimo", "con_sesion"])
def test_5_operacion_sigue_funcionando(near, sesion):
    d, sql, prm = near(sesion=sesion, operacion=" venta ")
    assert "EXISTS (SELECT 1 FROM transacciones_temporales t" in sql
    assert "t.tipo_operacion ILIKE :op" in sql and prm["op"] == "venta"
    assert d["total"] == 2
    _, sql_sin, prm_sin = near(sesion=sesion)
    assert "transacciones_temporales" not in sql_sin and "op" not in prm_sin


@pytest.mark.parametrize("sesion", [False, True], ids=["anonimo", "con_sesion"])
def test_6_distancia_m_sigue_funcionando(near, sesion):
    filas = [_fila(1, Decimal("120")), _fila(2, Decimal("480")), _fila(3, None)]
    d, sql, prm = near(filas, sesion=sesion, radius_m=800)
    assert [f["properties"]["distancia_m"] for f in d["features"]] == [120, 480, None]
    assert isinstance(d["features"][0]["properties"]["distancia_m"], int)
    assert "ORDER BY distancia_m ASC" in sql and prm["radius"] == 800
    assert d["centro"] == {"lat": LAT, "lon": LON, "radius_m": 800}


def test_6_el_tope_de_radio_sigue_en_5000(near):
    """Fuera del alcance de esta unidad: ni se baja a 2 km ni se toca el mínimo."""
    _, _, prm = near(radius_m=99999)
    assert prm["radius"] == 5000
    _, _, prm = near(radius_m=1)
    assert prm["radius"] == 50


@pytest.mark.parametrize("sesion", [False, True], ids=["anonimo", "con_sesion"])
def test_7_radio_vacio_conserva_la_featurecollection_vacia(near, sesion):
    d, _, _ = near([], sesion=sesion)
    assert d == {"type": "FeatureCollection", "centro": {"lat": LAT, "lon": LON, "radius_m": 500},
                 "total": 0, "features": [], "scores_incluidos": sesion}


# ── 8 · la compuerta, neutralizada, se detecta ────────────────────────────────────
def _endpoint_mutado(original: str, mutacion: str):
    """El cuerpo REAL de `assets_near`, sin decoradores, con una línea sustituida, compilado en
    el espacio de nombres del módulo. Sin mutación es el mismo código que sirve el endpoint."""
    fuente = inspect.getsource(assets.assets_near.__wrapped__)
    fuente = textwrap.dedent(fuente[fuente.index("async def assets_near"):])
    assert fuente.count(original) == 1, "la compuerta ya no tiene la forma esperada"
    ns = dict(vars(assets))
    exec(compile(fuente.replace(original, mutacion), "<assets_near mutado>", "exec"), ns)
    return ns["assets_near"]


def _llamar(fn, user):
    registro: list = []
    return asyncio.run(fn(request=None, lat=LAT, lon=LON, radius_m=500, operacion=None,
                          db=_Sesion(FILAS, registro), user=user))


def test_8_el_cuerpo_real_sin_mutar_cumple_el_contrato():
    """Control: la copia compilada del cuerpo, sin mutar, se comporta como el endpoint."""
    fn = _endpoint_mutado("con_scores = user is not None", "con_scores = user is not None")
    _solo_espacial(_llamar(fn, None))
    assert _llamar(fn, CurrentUser(user_id="u"))["scores_incluidos"] is True


def test_8_neutralizar_la_compuerta_hace_fallar_el_contrato_anonimo():
    fn = _endpoint_mutado("con_scores = user is not None", "con_scores = True")
    with pytest.raises(AssertionError):
        _solo_espacial(_llamar(fn, None))


def test_8_neutralizar_la_frontera_de_D1_se_detecta_con_sesion():
    fn = _endpoint_mutado("rows = [con_contexto_vigente(r) for r in rows]", "rows = [dict(r) for r in rows]")
    p = _llamar(fn, CurrentUser(user_id="u"))["features"][0]["properties"]
    assert p["servicios_cercanos"] == TEXTO_LEGADO, "sin la frontera el legado reaparece: la prueba 3 lo vería"
