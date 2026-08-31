"""G20-B1-R1 · TYPE NORMALIZATION HOTFIX — el borde donde nace la relación territorial.

QUÉ ROMPIÓ, Y POR QUÉ NINGUNA DE LAS 2397 PRUEBAS LO VIO.

`8322e25` pasó RED/GREEN 23/23, 8/8 mutaciones rojas y CI 2397/0/0 — y abortó el primer
turno real que tocó. El canary del 2026-08-30T20:40:22Z murió con la excepción que quedó
persistida en `checkpoint_writes.__error__` del hilo `session-xrYdnRd5CYUc3u_R`:

    ValueError("Unknown format code 'g' for object of type 'str'")

La cadena, entera:

    tools.py:259   ROUND(ST_Distance(...)::numeric, 1)   →  Decimal("572.0")
    tools.py:303   json.dumps(..., default=str)          →  "572.0"   ← STRING
    assembler.py   fuera["distancia_metros"] = ...       →  copia literal, sin coerción
    encaje_contexto.py:193   f"{dist:g}"                 →  ValueError
    graph.py:776   bloque_autoritativo() vive FUERA del try  →  el grafo aborta

EL DEFECTO DE MÉTODO, que importa más que el bug. El fixture de
`test_contrato_territorial.py` dice «El turno REAL del canary de producción, congelado» y
fija `DIST = 572.0`, un **float**. No estaba congelado: estaba **transcrito** desde el
informe en prosa del canary de G20-A, donde la línea se imprimía `distancia_metros 572.0`.
En el cable era la cadena `"572.0"`. Un float y un str que lo contiene **se imprimen
idénticos** en un informe; sólo difieren en `type()`. Ese carácter de comilla es toda la
distancia entre 23/23 verde y el 100% de los turnos rotos.

    evidencia ≠ autorización de afirmación

Es la misma tesis de G20-B1, aplicada al arnés en vez de al modelo: «el informe dice 572.0»
no autoriza «el payload trae un float». Por eso este módulo NO fabrica su entrada: la carga
del artefacto causal, copiado del checkpointer sin reescribir, en
`tests/fixtures/g20_b1_canary_void_20260830T204022Z.json`.

QUÉ CUBRE ESTE MÓDULO
  1. que el artefacto siga siendo el artefacto (guard de procedencia — el primer test)
  2. la costura completa ToolMessages → construir_panel → bloque_autoritativo
  3. equivalencia de tipos: str, int y float dicen lo mismo
  4. qué NO es evidencia: ausente, no numérico, NaN, ±infinito, negativo
  5. y el guard que hace que 4 no sea una puerta trasera: rechazar la DISTANCIA nunca
     desactiva la PROHIBICIÓN territorial

FUERA DE ALCANCE, deliberadamente: `G20-B1-CONTAINMENT-01` (dónde vive el `try` de
`encaje_node`) queda SEPARADO y en HOLD por decisión de gatekeeper — mover
`bloque_autoritativo` dentro del `try` convertiría un fallo del contrato de autoridad en
degradación fail-open, y eso exige decidir la política de abstención antes que el código.
"""
import asyncio
import json
import math
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.decision import assembler
from app.decision.assembler import _relacion_territorial_del_turno, construir_panel
from app.encaje_contexto import bloque_autoritativo

ARTEFACTO = (Path(__file__).parent / "fixtures"
             / "g20_b1_canary_void_20260830T204022Z.json")

# El turno REAL, sin retocar. Las preferencias son las que el turno declara en su texto
# («Busco arriendo en La Floresta, con un presupuesto máximo de 900 dólares»); se pasan
# explícitas para que `construir_panel` no llame al LLM ni a Postgres.
PREFS = {"operacion": "arriendo", "presupuesto_max": 900}
CONSULTA = "La Floresta, Quito, Ecuador"


def _artefacto() -> dict:
    with open(ARTEFACTO, encoding="utf-8") as f:
        return json.load(f)


def _mensajes() -> list:
    """Los mensajes del turno roto, reconstruidos con los `content` EXACTOS del cable."""
    fuera = []
    for m in _artefacto()["messages"]:
        if m["type"] == "human":
            fuera.append(HumanMessage(content=m["content"]))
        elif m["type"] == "ai":
            fuera.append(AIMessage(content=m["content"] or "",
                                   tool_calls=m.get("tool_calls") or []))
        elif m["type"] == "tool":
            fuera.append(ToolMessage(content=m["content"], name=m["name"],
                                     tool_call_id=m["tool_call_id"]))
    return fuera


def _assets() -> list[dict]:
    for m in _artefacto()["messages"]:
        if m.get("name") == "tool_search_nearby_assets":
            return json.loads(m["content"])["assets"]
    raise AssertionError("el artefacto perdió el ToolMessage de búsqueda")


def _rows() -> list[dict]:
    """Filas de base para los 5 activos REALES del turno.

    La base no participa (`_fetch_cards_rows` va monkeypatcheado): lo que importa es que
    los `id` sean los del artefacto, porque son los que `_collect_asset_ids` recolecta.
    """
    filas = []
    for a in _assets():
        filas.append({
            "id": a["id"], "direccion": a["direccion_estandarizada"],
            "tipo_activo": a["tipo_activo"], "operacion": a["operacion"],
            "precio": float(a["precio"]), "imagen_url": None,
            "caminabilidad": 90, "caminabilidad_fuente": "osm", "ruido": "BAJO",
            "vegetacion": 40, "lat": -0.2093, "lon": -78.4849,
            "caracteristicas": {"num_dormitorios": 2},
            "servicios_cercanos": "🌳 Parque a ~300 m",
            "conectividad": "🚇 Metro a ~500 m (7 min a pie)",
        })
    return filas


def _panel(monkeypatch, mensajes=None, prefs=PREFS):
    async def fake_fetch(_ids):
        return (_rows(), {})

    monkeypatch.setattr(assembler, "_fetch_cards_rows", fake_fetch)
    return asyncio.run(construir_panel(mensajes or _mensajes(),
                                       session_id="s-g20b1r1", preferencias=prefs))


def _bloque(monkeypatch, **kw) -> str:
    """LA COSTURA ENTERA, igual que `encaje_node`: panel → bloque autoritativo."""
    panel = _panel(monkeypatch, **kw)
    return bloque_autoritativo(panel["cards"], PREFS, panel["descartadas"],
                               panel["priorizado"],
                               relacion_territorial=panel.get("relacion_territorial"))


# ══ 0 · GUARD DE PROCEDENCIA · que el artefacto siga siendo el artefacto ═════════════
#
# Este test existe para que el arreglo obvio y equivocado —«pon 572.0 y ya»— no pueda
# aplicarse en silencio. Si alguien "normaliza" el fixture, esto se cae aquí y no en
# producción tres semanas después.

def test_el_artefacto_conserva_el_tipo_del_CABLE_no_el_del_informe():
    for a in _assets():
        d = a["distancia_metros"]
        assert isinstance(d, str), (
            f"distancia_metros llegó como {type(d).__name__}. En el cable es str: "
            "`json.dumps(default=str)` sobre el Decimal de Postgres. Si este fixture "
            "trae un float, ya no es el turno de producción — es el informe otra vez.")
    assert _assets()[0]["distancia_metros"] == "572.0"


def test_el_artefacto_declara_su_procedencia():
    p = _artefacto()["_procedencia"]
    assert p["thread_id"] == "session-xrYdnRd5CYUc3u_R"
    assert p["commit"].startswith("8322e25")
    assert "Unknown format code 'g'" in p["error_persistido"]


# ══ 1 · EL RED · la costura completa, con el artefacto real ═════════════════════════
#
# Sobre 8322e25 sin reparar, este test levanta la MISMA ValueError que quedó persistida
# en el checkpoint. Es la regresión, reproducida sin red, sin Render y sin Postgres.

def test_la_costura_completa_no_revienta_con_el_payload_real(monkeypatch):
    """(1) AUSENCIA DE EXCEPCIÓN. El RED de esta unidad."""
    bloque = _bloque(monkeypatch)
    assert isinstance(bloque, str) and bloque


def test_la_relacion_territorial_se_conserva(monkeypatch):
    """(2) RELACIÓN CONSERVADA — normalizar un tipo no puede perder la evidencia."""
    rel = _panel(monkeypatch)["relacion_territorial"]
    assert rel is not None
    assert rel["relacion_recuperacion"] == "within_radius"
    assert rel["ancla_busqueda"] == {"latitude": -0.20934, "longitude": -78.484919,
                                     "geometry_type": "point"}
    assert rel["radius_requested_m"] == 1200
    assert rel["radius_searched_m"] == 1200
    assert rel["consulta"] == CONSULTA


def test_la_distancia_queda_normalizada_a_numero(monkeypatch):
    """(3) DISTANCIA NORMALIZADA — y con el MISMO valor, no uno redondeado por el camino."""
    rel = _panel(monkeypatch)["relacion_territorial"]
    d = _dist(rel)
    assert isinstance(d, float), f"sigue siendo {type(d).__name__}"
    assert d == 572.0


def test_el_contrato_autoritativo_se_emite_completo(monkeypatch):
    """(4) CONTRATO EMITIDO — las tres partes, no sólo la ausencia de excepción."""
    bloque = _bloque(monkeypatch)
    assert "RELACIÓN TERRITORIAL · QUÉ PUEDES AFIRMAR" in bloque
    assert "LA EVIDENCIA DE ESTE TURNO:" in bloque
    assert "PUEDES AFIRMAR:" in bloque
    assert "NO AFIRMES — esta evidencia no lo autoriza:" in bloque
    # el topónimo se ligó por igualdad EXACTA de coordenadas geocode↔ancla
    assert f"se geocodificó «{CONSULTA}»" in bloque
    assert "radio pedido 1200 m, efectivo 1200 m" in bloque
    # `:g` sobre 572.0 da «572», no «572.0»: la aserción fija el formato, no lo adivina
    assert "— 572 m" in bloque          # G20-B1-R2: la cifra va pegada a SU inmueble
    assert "572.0 m" not in bloque


def test_la_pertenencia_sigue_siendo_unknown(monkeypatch):
    """(5) `unknown` PRESERVADO — ni se vuelve booleana ni se pierde por el camino."""
    rel = _panel(monkeypatch)["relacion_territorial"]
    assert rel["pertenencia_territorial"] == "unknown"
    assert rel["pertenencia_territorial"] not in (True, False, "true", "false", "inside")
    assert "pertenencia territorial: NO ESTÁ ESTABLECIDA" in _bloque(monkeypatch)


def test_ninguna_autorizacion_accidental_de_pertenencia(monkeypatch):
    """(6) SIN MEMBERSHIP ACCIDENTAL.

    El riesgo del hotfix no es que falle: es que al arreglar el formato se cuele una
    afirmación de pertenencia por la lista de lo PERMITIDO. Se leen las líneas ✅ una por
    una y se exige que ninguna nombre el lugar como ubicación del inmueble.
    """
    bloque = _bloque(monkeypatch)
    permitidas = [l for l in bloque.splitlines() if l.strip().startswith("✅")]
    assert permitidas, "el bloque perdió la sección de lo afirmable"
    for linea in permitidas:
        for verbo in ("está en", "ubicado en", "dentro de", "pertenece", "se encuentra en"):
            assert verbo not in linea, f"línea ✅ autoriza pertenencia: {linea!r}"

    prohibidas = "\n".join(l for l in bloque.splitlines() if l.strip().startswith("❌"))
    assert f"que el inmueble esté «en {CONSULTA}»" in prohibidas
    assert "el centro, el centroide o el corazón" in prohibidas
    # UNKNOWN NO ES NEGACIÓN: tampoco se autoriza el contrario.
    assert "no digas que está fuera ni que no pertenece" in prohibidas


# ══ 2 · EQUIVALENCIA DE TIPOS · str, int y float dicen lo mismo ═════════════════════

_AUSENTE = object()


def _mensajes_con(distancia) -> list:
    """El turno real, con `distancia_metros` del primer activo forzado a un valor."""
    msgs = _mensajes()
    for i, m in enumerate(msgs):
        if getattr(m, "name", None) != "tool_search_nearby_assets":
            continue
        cuerpo = json.loads(m.content)
        if distancia is _AUSENTE:
            cuerpo["assets"][0].pop("distancia_metros", None)
        else:
            cuerpo["assets"][0]["distancia_metros"] = distancia
        # `default=str` NO es un detalle del arnés: es exactamente lo que hace
        # `tools.py:303`, y es el mecanismo que convirtió el Decimal en "572.0".
        # Serializar de otra forma volvería a probar contra un payload irreal.
        msgs[i] = ToolMessage(content=json.dumps(cuerpo, default=str), name=m.name,
                              tool_call_id=m.tool_call_id)
    return msgs


def _rel_con(monkeypatch, distancia):
    """La relación del turno, con `distancia_metros` del activo forzado a un valor.

    G20-B1-R2 cambió el contrato: la relación liga cada distancia a una tarjeta VISIBLE por
    id, así que ya no basta con los mensajes — hay que cruzar el panel. Con `PREFS`
    (arriendo, tope 900) el panel deja UNA tarjeta, y es justamente el activo que
    `_mensajes_con` muta. La equivalencia de tipos se sigue probando sobre la costura real,
    que es lo que esta unidad exigía.
    """
    return _panel(monkeypatch, mensajes=_mensajes_con(distancia))["relacion_territorial"]


def _dist(rel):
    """La distancia LIGADA a la única tarjeta visible del turno.

    Ya no existe `rel["distancia_metros"]`: era la cifra suelta que R2 eliminó porque
    permitía atribuir al «candidato mostrado» la distancia de un activo que el filtro había
    ocultado. Ver tests/test_g20_b1_r2_binding_entidad_visible.py.
    """
    return rel["distancias"][0]["distancia_metros"]


@pytest.mark.parametrize("entrada, esperado", [
    ("572.0", 572.0),       # el caso REAL de producción
    ("572", 572.0),
    (572, 572.0),           # int
    (572.0, 572.0),         # float — lo que el fixture viejo suponía
    ("0", 0.0),             # cero es una distancia válida, no un vacío
    (0, 0.0),
    ("1014.4", 1014.4),
])
def test_str_int_y_float_convergen_al_mismo_numero(monkeypatch, entrada, esperado):
    rel = _rel_con(monkeypatch, entrada)
    assert _dist(rel) == esperado
    assert isinstance(_dist(rel), float)


def test_el_formato_no_depende_del_tipo_de_entrada(monkeypatch):
    """La prueba de que la equivalencia es REAL: mismo texto emitido, vengan como vengan.

    Cruza el PANEL completo a propósito. Compararlo sobre `cards=[]` habría pasado
    vacuamente: sin tarjetas `bloque_autoritativo` devuelve "" para los cuatro tipos y el
    conjunto tendría un solo elemento sin haber probado nada (ver
    `G20-B1-NOCARDS-01`).
    """
    textos = {_bloque(monkeypatch, mensajes=_mensajes_con(v))
              for v in ("572.0", "572", 572, 572.0)}
    assert len(textos) == 1, "el tipo de entrada cambió el texto autoritativo"
    assert "— 572 m" in textos.pop()


# ══ 3 · QUÉ NO ES EVIDENCIA ════════════════════════════════════════════════════════
#
# Un número que no puede ser una distancia NO se degrada a «0 m» ni se propaga: se cae a
# None, que es el estado que `_seccion_territorial` ya sabe decir («la proximidad al punto
# usado para la búsqueda», sin cifra). Fail-closed sobre la AFIRMACIÓN, nunca sobre el
# contrato.

@pytest.mark.parametrize("basura", [
    _AUSENTE,                       # la llave no vino
    None,
    "",
    "   ",
    "abc",
    "572 m",                        # con unidad pegada: no es un número
    "NaN", "nan", float("nan"),     # NaN no es una distancia
    "inf", "-inf", float("inf"), float("-inf"),
    -1, -0.5, "-572.0",             # una distancia negativa no existe
    True, False,                    # bool es int en Python: `float(True)` daría 1.0
    [572.0], {"m": 572}, object(),
])
def test_lo_que_no_es_una_distancia_no_se_vuelve_evidencia(monkeypatch, basura):
    rel = _rel_con(monkeypatch, basura)
    assert rel is not None, "rechazar la distancia no puede matar la relación entera"
    assert _dist(rel) is None, f"{basura!r} se coló como distancia"


def test_ni_NaN_ni_infinito_sobreviven_como_numero(monkeypatch):
    """Explícito porque `float('nan')` es un float y pasaría cualquier isinstance()."""
    for v in ("NaN", float("nan"), float("inf"), float("-inf")):
        d = _dist(_rel_con(monkeypatch, v))
        assert d is None or math.isfinite(d)


def test_rechazar_la_distancia_NO_desactiva_la_prohibicion(monkeypatch):
    """EL GUARD QUE HACE QUE EL FAIL-CLOSED NO SEA UNA PUERTA TRASERA.

    Si una distancia mala apagara la sección territorial entera, bastaría un dato sucio
    para que el modelo quedara sin restricción — el mismo fail-open que el gatekeeper
    rechazó en CONTAINMENT-01, entrando por la puerta de los datos. La cifra se cae; la
    prohibición se queda.
    """
    bloque = _bloque(monkeypatch, mensajes=_mensajes_con("abc"))
    assert "RELACIÓN TERRITORIAL · QUÉ PUEDES AFIRMAR" in bloque
    assert "pertenencia territorial: NO ESTÁ ESTABLECIDA" in bloque
    assert f"que el inmueble esté «en {CONSULTA}»" in bloque
    assert "no digas que está fuera ni que no pertenece" in bloque
    # sin cifra, pero con la proximidad dicha en palabras
    assert "se recuperaron por proximidad a ese punto" in bloque
    assert "NINGUNA distancia quedó ligada" in bloque


def test_la_relacion_sigue_completa_aunque_la_distancia_se_caiga(monkeypatch):
    rel = _rel_con(monkeypatch, "abc")
    assert rel["pertenencia_territorial"] == "unknown"
    assert rel["relacion_recuperacion"] == "within_radius"
    assert rel["consulta"] == CONSULTA
    assert rel["radius_searched_m"] == 1200
