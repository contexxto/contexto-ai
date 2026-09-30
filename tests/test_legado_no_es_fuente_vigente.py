"""MAP-SOURCE-BOUNDARY · D1 — el texto legado sin procedencia NO es fuente vigente de nada.

Decisión de fundador (2026-09-30, «D1 = B · CLOSE NOW IN PR #173»). `servicios_cercanos` y
`conectividad` persistidos SIN procedencia propia demostrada no pueden:
  · alimentar `parque_min` / `transporte_min`;
  · alterar el encaje ni el orden del panel;
  · llegar a la prosa del agente como contexto vigente;
  · reaparecer indirectamente por otro consumidor.

Hasta el backfill, ausencia de procedencia = UNKNOWN (`None`) ≠ cero ≠ falso ≠ «no existe».

Qué demuestra este fichero (numerado como el mandato):
  1. el legado no altera `parque_min`;
  2. el legado no altera `transporte_min`;
  3. el agente no recibe esos textos como fuente vigente (ni para encontrar inmuebles);
  4. `None`/UNKNOWN no se convierte en 0;
  5. una fila con procedencia propia demostrada vuelve a entrar por la frontera prevista;
  6. ningún consumidor nuevo lee las columnas sin pasar por la frontera. Las siete rutas
     Google→MapLibre las vigila `tests/test_map_source_boundary.py`.

La frontera es `app/place/legado.py::con_contexto_vigente`, aplicada en la LECTURA y antes
de la curación del corredor: lo que el corredor confirmó es dato propio y sobrevive.
"""
from __future__ import annotations

import ast
import asyncio
import json
import re
from pathlib import Path

import httpx
import pytest

import app.agent.tools as tools
import app.routers.assets as assets
from app.auth import CurrentUser
from app.decision import assembler
from app.place.legado import COLUMNA_PROCEDENCIA, con_contexto_vigente
from app.routers import chat

RAIZ = Path(__file__).resolve().parents[1]
APP = RAIZ / "app"
ACTIVO = "0cb128c9-0000-4000-8000-0000000d1d1d"
# El formato REAL de las columnas (`_formatear`, y la conectividad con minutos entre paréntesis).
SERV = "🌳 Parque Legado a ~300 m · 💊 Farmacia Legada a ~120 m"
CONECT = "🚇 Estación Legada ~500 m (7 min a pie)"
PREFS = {"tipo_inmueble": "departamento", "presupuesto_max": 800,
         "transporte": True, "area_verde": True, "caminable": True}


def _fila(rid=ACTIVO, **over):
    """Una fila de catastro como la devuelve `_fetch_cards_rows`, con los textos legados."""
    fila = {"id": rid, "direccion": f"Dir {rid}", "tipo_activo": "Departamento",
            "operacion": "arriendo", "precio": 600, "imagen_url": None,
            "caminabilidad": 80, "caminabilidad_fuente": "osm", "ruido": "BAJO", "vegetacion": 40,
            "lat": -0.18, "lon": -78.48, "caracteristicas": {"num_dormitorios": 2},
            "servicios_cercanos": SERV, "conectividad": CONECT}
    fila.update(over)
    return fila


# ══ El panel real, con las señales del encaje ESPIADAS ═════════════════════════════
def _panel(monkeypatch, filas, curaciones=None):
    """`construir_panel` → `_decidir_desde_filas` con la base doblada. Devuelve el panel y
    las señales que recibió el motor de encaje, por id."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    senales: dict[str, dict] = {}
    original = assembler._senales_encaje

    def _espia(row, car):
        s = original(row, car)
        senales[row["id"]] = s
        return s

    async def _fetch(_ids):
        return (filas, curaciones or {})
    monkeypatch.setattr(assembler, "_senales_encaje", _espia)
    monkeypatch.setattr(assembler, "_fetch_cards_rows", _fetch)
    mensajes = [HumanMessage(content="depa con parque y transporte, hasta 800"),
                ToolMessage(content=json.dumps({"assets": [{"id": f["id"]} for f in filas]}),
                            name="tool_find_assets_by_text", tool_call_id="t1"),
                AIMessage(content="Encontré estas opciones.")]
    panel = asyncio.run(chat.construir_panel(mensajes, session_id="s-d1", preferencias=PREFS))
    return panel, senales


def _decision(panel):
    return {"orden": [c["id"] for c in panel["cards"]],
            "encaje": {c["id"]: c["encaje"] for c in panel["cards"]},
            "encaje_medido": {c["id"]: c["encaje_medido"] for c in panel["cards"]},
            "cobertura": {c["id"]: c["encaje_cobertura"] for c in panel["cards"]},
            "evaluadas": {c["id"]: c["encaje_evaluadas"] for c in panel["cards"]},
            "pois": {c["id"]: c["pois"] for c in panel["cards"]}}


# ── 1 y 2 · ni parque_min ni transporte_min salen del legado ─────────────────────
def test_1_el_legado_no_alimenta_parque_min(monkeypatch):
    _, s = _panel(monkeypatch, [_fila()])
    assert s[ACTIVO]["parque_min"] is None


def test_2_el_legado_no_alimenta_transporte_min(monkeypatch):
    _, s = _panel(monkeypatch, [_fila()])
    assert s[ACTIVO]["transporte_min"] is None


def test_1_2_el_legado_no_mueve_ni_el_encaje_ni_el_orden(monkeypatch):
    """Tres inmuebles, uno de ellos con textos que ANTES lo habrían subido: el panel es
    idéntico al de no tener texto alguno."""
    con_texto = [_fila("a", precio=700), _fila("b", precio=500, servicios_cercanos=None,
                                                conectividad=None), _fila("c", precio=650)]
    sin_texto = [dict(f, servicios_cercanos=None, conectividad=None) for f in con_texto]
    panel_con, _ = _panel(monkeypatch, con_texto)
    panel_sin, _ = _panel(monkeypatch, sin_texto)
    assert _decision(panel_con) == _decision(panel_sin)


def test_1_2_la_comparacion_tampoco_usa_el_legado(monkeypatch):
    """El otro consumidor de las mismas filas: el modo COMPARAR de `chat.py`."""
    import types

    senales: dict[str, dict] = {}
    original = assembler._senales_encaje

    def _espia(row, car):
        senales[row["id"]] = original(row, car)
        return senales[row["id"]]

    async def _estado(_cfg):
        return types.SimpleNamespace(values={"messages": []})

    async def _prefs(_t):
        return PREFS

    async def _fetch(_ids):
        return ([_fila("A"), _fila("B", precio=700)], {})
    monkeypatch.setattr(chat, "agent_graph",
                        types.SimpleNamespace(compiled_graph=types.SimpleNamespace(aget_state=_estado)))
    monkeypatch.setattr(assembler, "extraer_preferencias", _prefs)
    monkeypatch.setattr(assembler, "_fetch_cards_rows", _fetch)
    monkeypatch.setattr(assembler, "_senales_encaje", _espia)
    res = asyncio.run(chat.comparar_inmuebles("s", "A", "B"))
    assert res["ok"] is True
    assert {k: (v["parque_min"], v["transporte_min"]) for k, v in senales.items()} == \
        {"A": (None, None), "B": (None, None)}


# ── 3 · el agente no recibe el legado como contexto vigente ──────────────────────
def _tool(monkeypatch, herramienta, args, filas, curaciones=()):
    sqls: list[str] = []

    async def _fetch_rows(query, params=None):
        sqls.append(query)
        if "FROM entorno_curacion" in query:
            return [dict(c) for c in curaciones]
        return [dict(f) for f in filas]
    monkeypatch.setattr(tools, "_fetch_rows", _fetch_rows)
    return json.loads(asyncio.run(herramienta.ainvoke(args))), sqls


def _sin_legado(salida):
    crudo = json.dumps(salida, ensure_ascii=False)
    assert "Legad" not in crudo, crudo[:300]
    assert "entorno_note" in salida and "UNKNOWN" in salida["entorno_note"]


def test_3_busqueda_cercana_sin_legado(monkeypatch):
    out, _ = _tool(monkeypatch, tools.tool_search_nearby_assets,
                   {"latitude": -0.18, "longitude": -78.48, "radius_meters": 1500},
                   [dict(_fila(), distancia_metros=120.0, walk_score_fuente="osm")])
    _sin_legado(out)
    (activo,) = out["assets"]
    assert activo["servicios_cercanos"] is None and activo["conectividad"] is None


def test_3_busqueda_por_texto_no_encuentra_POR_el_legado_ni_lo_devuelve(monkeypatch):
    """Antes, «Quicentro» encontraba un inmueble porque SU texto legado nombraba el Quicentro:
    eso era usar el legado como fuente vigente por la puerta de atrás."""
    out, sqls = _tool(monkeypatch, tools.tool_find_assets_by_text, {"query": "Parque Legado"},
                      [dict(_fila(), walk_score_fuente="osm", _rank=0)])
    (sql,) = sqls
    assert not re.search(r"(conectividad|servicios_cercanos)\s+ILIKE", sql)
    assert ":phrase" not in sql
    _sin_legado(out)


def test_3_ficha_del_agente_sin_legado_pero_con_lo_que_confirmo_el_corredor(monkeypatch):
    """La frontera va ANTES de la curación: lo agregado por el corredor es dato propio."""
    fila = dict(_fila(), walk_score_fuente="osm", tiene_ficha_tecnica=False)
    cur = [{"accion": "agregado", "nombre": "Panadería del Corredor", "categoria": "supermercado",
            "distancia_m": 90, "creado_en": "2026-09-01"}]
    out, _ = _tool(monkeypatch, tools.tool_fetch_asset_lifecycle_specs, {"activo_id": ACTIVO},
                   [fila], cur)
    _sin_legado(out)
    assert out["specs"]["servicios_cercanos"] == "Panadería del Corredor a ~90 m (confirmado por el corredor)"
    assert out["specs"]["conectividad"] is None


def test_3_la_herramienta_de_estilo_de_vida_dice_que_null_no_es_ausencia():
    doc = tools.tool_traducir_estilo_de_vida.description
    assert "null, that is UNKNOWN" in doc and "never that it isn't there" in doc


# ── 4 · UNKNOWN no es cero ────────────────────────────────────────────────────────
def test_4_None_no_se_convierte_en_cero(monkeypatch):
    assert assembler._transporte_min(None) is None
    assert assembler._min_a_pie(None, assembler._EMOJI_PARQUE) is None
    _, s = _panel(monkeypatch, [_fila()])
    # El motor la trata como «sin dato» (no aporta), jamás como una puntuación de 0.
    from app.encaje import calcular_encaje
    enc = calcular_encaje(PREFS, s[ACTIVO])
    por_dim = {r["dimension"]: r for r in enc["razones"]}
    for dim in ("transporte", "area_verde"):
        assert por_dim[dim]["aporta"] is False and por_dim[dim]["s"] is None, por_dim[dim]
    assert "transporte" not in enc["dimensiones_evaluadas"]
    assert "area_verde" not in enc["dimensiones_evaluadas"]
    # Y la diferencia con un dato MALO de verdad: un metro a 40 min sí puntúa (bajo).
    malo = calcular_encaje(PREFS, dict(s[ACTIVO], transporte_min=40))
    assert "transporte" in malo["dimensiones_evaluadas"]
    assert malo["cobertura"] > enc["cobertura"]


def test_4_en_los_payloads_es_null_no_cero_ni_vacio(monkeypatch):
    out, _ = _tool(monkeypatch, tools.tool_search_nearby_assets,
                   {"latitude": -0.18, "longitude": -78.48, "radius_meters": 1500},
                   [dict(_fila(), distancia_metros=120.0, walk_score_fuente="osm")])
    for campo in ("servicios_cercanos", "conectividad"):
        assert out["assets"][0][campo] is None     # ni 0, ni "", ni False


# ── 5 · con procedencia propia demostrada, la fila vuelve a entrar ─────────────────
def test_5_la_frontera_deja_pasar_la_procedencia_propia(monkeypatch):
    fila = _fila(**{COLUMNA_PROCEDENCIA: "propio"})
    panel, s = _panel(monkeypatch, [fila])
    assert s[ACTIVO]["parque_min"] == 4          # 300 m / 80 m·min
    assert s[ACTIVO]["transporte_min"] == 7      # «(7 min a pie)»
    assert [p["texto"] for p in panel["cards"][0]["pois"]][:1] == ["Farmacia Legada"]
    out, _ = _tool(monkeypatch, tools.tool_search_nearby_assets,
                   {"latitude": -0.18, "longitude": -78.48, "radius_meters": 1500},
                   [dict(fila, distancia_metros=120.0, walk_score_fuente="osm")])
    assert out["assets"][0]["conectividad"] == CONECT and "entorno_note" not in out


@pytest.mark.parametrize("procedencia", [None, "", "google", "osm", "PROPIO", "heuristico"])
def test_5_cualquier_otra_procedencia_sigue_fuera(procedencia):
    f = con_contexto_vigente(_fila(**{COLUMNA_PROCEDENCIA: procedencia}))
    assert f["servicios_cercanos"] is None and f["conectividad"] is None


# ── 3 · los demás lectores del producto (corredor): /mine, /entorno, /recompute ────
class _Res:
    def __init__(self, filas):
        self.filas = filas

    def mappings(self):
        return self

    def all(self):
        return list(self.filas)

    def first(self):
        return self.filas[0] if self.filas else None


class _Sesion:
    def __init__(self, responde):
        self.responde = responde

    async def execute(self, stmt, params=None):
        return _Res(self.responde(str(stmt)))

    async def commit(self):
        pass

    async def rollback(self):
        pass


def test_3_mis_publicaciones_sin_legado():
    fila = dict(_fila(), piso_altura=3, walk_score=80, ruido="BAJO", tiene_ficha=False)
    out = asyncio.run(assets.my_assets(user=CurrentUser(user_id="u"),
                                       db=_Sesion(lambda sql: [fila])))
    (item,) = out["publicaciones"]
    assert item["servicios_cercanos"] is None and item["conectividad"] is None


def test_3_modal_de_curacion_sin_legado(monkeypatch):
    async def _nada(*a, **k):
        return None

    async def _vacio(*a, **k):
        return []
    monkeypatch.setattr(assets, "ensure_curacion_table", _nada)
    monkeypatch.setattr(assets, "_assert_owner", _nada)
    monkeypatch.setattr(assets, "fetch_curaciones", _vacio)
    monkeypatch.setattr(assets, "entorno_curable", _vacio)
    import uuid
    out = asyncio.run(assets.get_entorno(uuid.UUID(ACTIVO), user=CurrentUser(user_id="u"),
                                         db=_Sesion(lambda sql: [{"servicios_cercanos": SERV,
                                                                  "lat": -0.18, "lon": -78.48}])))
    assert out["servicios_base"] == []


def test_3_recompute_no_devuelve_el_legado(monkeypatch):
    import main
    from app.auth import get_current_user
    from app.database import get_db
    from app.limiter import limiter

    async def _nada(*a, **k):
        return None

    def _responde(sql):
        if "ST_Y(geom)" in sql:
            return [{"lat": -0.18, "lon": -78.48}]
        return [{"walk_score": 80, "conectividad": CONECT, "servicios_cercanos": SERV}]

    async def _db():
        yield _Sesion(_responde)
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setattr(assets, "_assert_owner", _nada)
    monkeypatch.setattr(assets, "_recompute_walk_score", _nada)
    main.app.dependency_overrides[get_db] = _db
    main.app.dependency_overrides[get_current_user] = lambda: CurrentUser(user_id="u")

    async def _go():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),
                                     base_url="http://test") as c:
            return await c.post(f"/api/v1/assets/{ACTIVO}/recompute")
    try:
        r = asyncio.run(_go())
    finally:
        main.app.dependency_overrides.pop(get_db, None)
        main.app.dependency_overrides.pop(get_current_user, None)
    assert r.status_code == 200, r.text
    assert r.json()["conectividad"] is None and r.json()["servicios_cercanos"] is None
    assert r.json()["walk_score"] == 80


# ── 6 · ningún consumidor NUEVO lee las columnas sin pasar por la frontera ─────────
_COLUMNA = re.compile(r"\b(servicios_cercanos|conectividad)\b")
_FRONTERA = "con_contexto_vigente"
# Lectores cuyo resultado cruza la frontera en OTRO sitio, dicho explícitamente.
_FRONTERA_DELEGADA = {
    ("app/decision/assembler.py", "_fetch_cards_rows"):
        {("app/decision/assembler.py", "_decidir_desde_filas"),
         ("app/routers/chat.py", "comparar_inmuebles")},
}


def _es_lectura(sql: str) -> bool:
    """Un SELECT que trae alguna de las dos columnas. Los UPDATE que las ESCRIBEN no cuentan."""
    s = sql.upper()
    return "SELECT" in s and bool(_COLUMNA.search(sql)) and not s.lstrip().startswith("UPDATE")


def _docstring(nodo):
    cuerpo = getattr(nodo, "body", None) or []
    if cuerpo and isinstance(cuerpo[0], ast.Expr) and isinstance(cuerpo[0].value, ast.Constant):
        return cuerpo[0].value
    return None


def _literales(nodo) -> list[str]:
    """Las cadenas del CUERPO: sin decoradores (sus `summary`/`description` nombran las
    columnas en prosa) y sin docstrings."""
    doc = _docstring(nodo)
    raices = nodo.body if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)) else [nodo]
    out = []
    for n in (m for r in raices for m in ast.walk(r)):
        if n is doc:
            continue
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.append(n.value)
        elif isinstance(n, ast.JoinedStr):
            out.append("".join(v.value for v in n.values
                               if isinstance(v, ast.Constant) and isinstance(v.value, str)))
    return out


def _lectores(raiz: Path) -> dict[tuple[str, str], bool]:
    """{(fichero, función): ¿aplica la frontera?} para cada función con un SELECT de las columnas.
    El SQL se junta por función (los SELECT se parten en varias cadenas concatenadas)."""
    out = {}
    for ruta in sorted((raiz / "app").rglob("*.py")):
        rel = ruta.relative_to(raiz).as_posix()
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for f in ast.walk(arbol):
            if not isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            sql = " ".join(_literales(f))
            if not _es_lectura(sql) or " FROM " not in sql.upper():
                continue
            if not re.search(r"\b(a\.)?(servicios_cercanos|conectividad)\b[^=]*?\bFROM\b", sql, re.S | re.I):
                continue
            usa = any(isinstance(n, ast.Name) and n.id == _FRONTERA for n in ast.walk(f))
            out[(rel, f.name)] = usa
    return out


def _funciones_que_usan_la_frontera(raiz: Path) -> set[tuple[str, str]]:
    out = set()
    for ruta in sorted((raiz / "app").rglob("*.py")):
        rel = ruta.relative_to(raiz).as_posix()
        for f in ast.walk(ast.parse(ruta.read_text(encoding="utf-8"))):
            if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                    any(isinstance(n, ast.Name) and n.id == _FRONTERA for n in ast.walk(f)):
                out.add((rel, f.name))
    return out


def test_6_todo_lector_de_las_columnas_pasa_por_la_frontera():
    lectores = _lectores(RAIZ)
    # El inventario completo, a la vista: un lector NUEVO rompe esta lista y obliga a decidir.
    assert set(lectores) == {
        ("app/routers/assets.py", "assets_geojson"),
        ("app/routers/assets.py", "assets_near"),
        ("app/routers/assets.py", "asset_anuncio"),
        ("app/routers/assets.py", "my_assets"),
        ("app/routers/assets.py", "get_entorno"),
        ("app/routers/assets.py", "recompute_asset"),
        ("app/agent/tools.py", "tool_search_nearby_assets"),
        ("app/agent/tools.py", "tool_find_assets_by_text"),
        ("app/agent/tools.py", "tool_fetch_asset_lifecycle_specs"),
        ("app/decision/assembler.py", "_fetch_cards_rows"),
    }, sorted(lectores)
    usan = _funciones_que_usan_la_frontera(RAIZ)
    for lector, aplica in lectores.items():
        if lector in _FRONTERA_DELEGADA:
            assert _FRONTERA_DELEGADA[lector] <= usan, lector
        else:
            assert aplica, f"{lector} lee las columnas legadas sin pasar por la frontera"


def test_6_nadie_busca_DENTRO_del_texto_legado():
    for ruta in sorted(APP.rglob("*.py")):
        for sql in _literales(ast.parse(ruta.read_text(encoding="utf-8"))):
            assert not re.search(r"(servicios_cercanos|conectividad)\s+(I?LIKE|~)", sql, re.I), ruta


def test_6_la_guarda_de_lectores_SI_PUEDE_fallar(tmp_path):
    """MITAD NEGATIVA: un lector fabricado que no pasa por la frontera aparece en el
    inventario marcado como tal; el mismo con la frontera, marcado como que sí la usa."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "nuevo.py").write_text(
        "from sqlalchemy import text\n"
        "async def lector_nuevo(db):\n"
        "    return (await db.execute(text('SELECT a.id, a.servicios_cercanos FROM activos_inmutables a'))).all()\n"
        "async def lector_bueno(db):\n"
        "    filas = (await db.execute(text('SELECT conectividad FROM activos_inmutables'))).all()\n"
        "    return [con_contexto_vigente(f) for f in filas]\n"
        "async def escritor(db):\n"
        "    await db.execute(text('UPDATE activos_inmutables SET conectividad = :c WHERE id = :id'))\n",
        encoding="utf-8")
    assert _lectores(tmp_path) == {("app/nuevo.py", "lector_nuevo"): False,
                                   ("app/nuevo.py", "lector_bueno"): True}
