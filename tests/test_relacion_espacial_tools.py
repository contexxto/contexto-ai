"""G20-A · la relación espacial viaja con el resultado, no en el prompt.

LA PROPIEDAD, en una frase:

    Estar cerca del punto que un geocoder asocia a "La Floresta" NO equivale a haber
    demostrado que el inmueble está dentro de La Floresta.

EL DEFECTO, caracterizado en G20.0 sobre los 10 turnos REALES de PROBE-10 (2026-08-29/30):

    tool_geocode_address("La Floresta, Quito, Ecuador")
      → {latitude: -0.20934, longitude: -78.484919}   un PUNTO de etiqueta
        y por la rama Nominatim NI SIQUIERA emite `source`
    tool_search_nearby_assets(lat, lon, 1200)
      → 5 activos; el primero a distancia_metros = 572.0
        no devuelve el punto de búsqueda, y no sabe cuál fue la consulta
    prosa → "1 departamento en arriendo EN LA FLORESTA"     10 de 10 runs
            "a unas 6 cuadras del CORAZÓN de La Floresta"

Cuatro de las cinco direcciones que devolvió el radio nombran González Suárez y una
nombra La Mariscal. Ninguna dice La Floresta. Las cuatro descartadas cayeron por
PRESUPUESTO: el motor de encaje no tiene ningún criterio territorial.

LA REGLA YA EXISTÍA en `graph.py:552` —"NUNCA llames al lugar analizado con el nombre que
pidió el usuario si NO coinciden"— y se incumplió 10/10. Mismo patrón que G18 y G19-A: lo
que no viaja con el dato como evidencia legible, el prompt no lo sostiene.

DÓNDE VIVE LA DECLARACIÓN. `pertenencia_territorial` es del RESULTADO DE BÚSQUEDA, no de
cada activo. Por activo parecería que evaluamos su geometría contra un límite y salió
"unknown"; no existe tal evaluator. A nivel de resultado dice lo único cierto: esta
operación de retrieval no estableció pertenencia.

FUERA DE ALCANCE: G20-C (una métrica del activo convertida en atributo del barrio),
G20-D (comparativo de barrios, POLICY-BLOCKED) y GEOCODER-TYPE-LOSS-01 (hoy se descartan
`types`/`location_type` de Google y `class`/`type` de Nominatim). Un punto sigue siendo un
punto aunque el proveedor lo clasifique como `suburb`.
"""
import json

import pytest

from app.agent.tools import _ancla_de, _con_procedencia_caminable, _relacion_de_busqueda

# El turno real del canary, congelado como caso de prueba.
ANCLA = {"latitude": -0.20934, "longitude": -78.484919}
DIST = 572.0
DIRECCION = "Calle Alemania E12-34 y Gonzalez Suarez, Quito"

PROHIBIDOS = ["centro", "centroide", "corazon", "corazón", "center", "centroid",
              "heart", "nucleo", "núcleo", "barrio", "parroquia", "polygon", "poligono"]


def _fila(**kw):
    base = {
        "id": "ee9ff315-5947-40bc-be09-632ace6b7991",
        "direccion_estandarizada": DIRECCION,
        "caminabilidad": 100,
        "walk_score_fuente": None,
        "distancia_metros": DIST,
    }
    base.update(kw)
    return base


# ── 1 · LA PERTENENCIA NO SE AFIRMA NI SE NIEGA ──────────────────────────────────────
def test_el_resultado_declara_pertenencia_desconocida():
    """`activos_inmutables` no tiene NINGUNA columna territorial (medido en G20.0), y el
    único MULTIPOLYGON de la base son isócronas por inmueble. Esta tool jamás tiene
    evidencia de límites, así que puede declararlo incondicionalmente y con verdad."""
    r = _relacion_de_busqueda(ancla=ANCLA, radio_pedido=1200, radio_usado=1200)
    assert r["pertenencia_territorial"] == "unknown"


def test_la_pertenencia_NO_es_un_booleano():
    """`false` sería tan inventado como `true`: tampoco sabemos que esté FUERA. Este test
    existe para que nadie 'simplifique' el campo a un booleano más adelante."""
    r = _relacion_de_busqueda(ancla=ANCLA, radio_pedido=1200, radio_usado=1200)
    assert r["pertenencia_territorial"] not in (True, False, "true", "false", "inside")


def test_la_pertenencia_vive_en_el_resultado_y_NO_por_activo():
    """A nivel de activo parecería que evaluamos su geometría contra un límite. No hay
    evaluator. La declaración pertenece a la OPERACIÓN de retrieval."""
    fila = _fila()
    assert "pertenencia_territorial" not in fila
    r = _relacion_de_busqueda(ancla=ANCLA, radio_pedido=1200, radio_usado=1200)
    assert "pertenencia_territorial" in r


# ── 2 · LA RELACIÓN QUE SÍ SE EJECUTÓ ────────────────────────────────────────────────
def test_se_declara_la_relacion_de_recuperacion_real():
    """La consulta fue `ST_DWithin(...)`. `within_radius` significa exactamente eso: el
    candidato pasó el filtro de radio. Nada más. No es una relación territorial."""
    r = _relacion_de_busqueda(ancla=ANCLA, radio_pedido=1200, radio_usado=1200)
    assert r["relacion_recuperacion"] == "within_radius"


def test_el_ancla_viaja_con_su_geometria():
    """Hoy la tool NO devuelve el punto que usó: el modelo tiene que recordarlo del
    resultado anterior."""
    r = _relacion_de_busqueda(ancla=ANCLA, radio_pedido=1200, radio_usado=1200)
    assert r["ancla_busqueda"]["latitude"] == ANCLA["latitude"]
    assert r["ancla_busqueda"]["longitude"] == ANCLA["longitude"]
    assert r["ancla_busqueda"]["geometry_type"] == "point"


# ── 3 · RADIO PEDIDO vs RADIO EFECTIVO ───────────────────────────────────────────────
def test_la_expansion_progresiva_queda_a_la_vista():
    """`radii = [radius_meters, 3000, 6000]`: si no hay nada a 1200 m, la búsqueda se
    abre en silencio. Un inmueble a 6 km puede volver como respuesta a «La Floresta».
    Con los dos campos, el modelo lo ve sin reconstruir el flujo."""
    r = _relacion_de_busqueda(ancla=ANCLA, radio_pedido=1200, radio_usado=3000)
    assert r["radius_requested_m"] == 1200
    assert r["radius_searched_m"] == 3000


def test_sin_expansion_los_dos_radios_coinciden():
    r = _relacion_de_busqueda(ancla=ANCLA, radio_pedido=1200, radio_usado=1200)
    assert r["radius_requested_m"] == r["radius_searched_m"] == 1200


# ── 4 · EL ANCLA NO SE PUEDE RENOMBRAR ───────────────────────────────────────────────
@pytest.mark.parametrize("prohibido", PROHIBIDOS)
def test_el_ancla_jamas_se_presenta_como_centro_del_barrio(prohibido):
    """Nominatim entrega UN PUNTO ASOCIADO A UNA ETIQUETA. Nada acredita que sea el
    centro geográfico, el centroide ni el 'corazón'. En el run 3 el modelo escribió «a
    unas 6 cuadras del corazón de La Floresta»: la MAGNITUD era fiel (572 m ≈ 5,7
    cuadras) y el SUSTANTIVO no lo era."""
    r = _relacion_de_busqueda(ancla=ANCLA, radio_pedido=1200, radio_usado=1200)
    assert prohibido not in json.dumps(r, ensure_ascii=False).lower()


# ── 5 · SIN ANCLA NO HAY RELACIÓN ────────────────────────────────────────────────────
def test_sin_geocode_no_se_fabrica_relacion():
    """`found: false` no puede producir una relación espacial. Sin ancla no hay
    proximidad que declarar — y la pertenencia sigue sin establecerse, no pasa a 'fuera'."""
    r = _relacion_de_busqueda(ancla=None, radio_pedido=1200, radio_usado=1200)
    assert "ancla_busqueda" not in r
    assert "relacion_recuperacion" not in r
    assert r["pertenencia_territorial"] == "unknown"


# ── 6 · EL GEOCODER DECLARA QUÉ ENTREGÓ, EN LAS DOS RAMAS ────────────────────────────
@pytest.mark.parametrize("fuente", ["google", "nominatim"])
def test_el_geocoder_declara_fuente_y_geometria(fuente):
    """DEFECTO COLATERAL REAL: hoy la rama Google emite `source: "google"` y la rama
    Nominatim NO emite `source` en absoluto. En los 10 runs del probe el modelo recibió
    el ancla sin saber qué geocoder la produjo."""
    a = _ancla_de(lat=ANCLA["latitude"], lon=ANCLA["longitude"], fuente=fuente)
    assert a["source"] == fuente
    assert a["geometry_type"] == "point"


# ── 7 · NO SE ROMPE LO QUE YA FUNCIONA ───────────────────────────────────────────────
def test_no_se_pisa_la_procedencia_de_caminabilidad_de_G19A():
    """G19-A está CLOSED/PASS con 10/10 limpio en producción. Esto es ortogonal."""
    fila = _con_procedencia_caminable(_fila())
    assert fila["caminabilidad_procedencia"] == "estimación por zona"
    assert fila["walk_score_fuente"] is None
    assert fila["caminabilidad"] == 100


def test_la_distancia_por_activo_no_se_toca():
    """`distancia_metros` sigue siendo la distancia real por candidato, intacta."""
    fila = _fila()
    _relacion_de_busqueda(ancla=ANCLA, radio_pedido=1200, radio_usado=1200)
    assert fila["distancia_metros"] == DIST


def test_los_POI_con_nombre_propio_no_se_degradan():
    """G20-E: «UPC La Floresta a ~1006 m» está ACREDITADO — hay exactamente 1 POI con
    ese nombre en `pois_vivos`, y 1006 m ÷ 80 m/min ≈ 13 min. La relación espacial del
    INMUEBLE no puede contaminar la identidad de los POI que sí traen evidencia."""
    servicios = "💊 Fybeca a ~167 m · 🛡️ UPC La Floresta a ~1006 m"
    fila = _fila(servicios_cercanos=servicios)
    _relacion_de_busqueda(ancla=ANCLA, radio_pedido=1200, radio_usado=1200)
    assert fila["servicios_cercanos"] == servicios


def test_la_metadata_espacial_no_altera_orden_ni_razones():
    """El ranking lo decide el motor de encaje; esta costura sólo describe el retrieval."""
    original = _fila(razones=["Dentro de tu presupuesto"])
    copia = dict(original)
    _relacion_de_busqueda(ancla=ANCLA, radio_pedido=1200, radio_usado=1200)
    assert copia == original


# ── 8 · LA TOOL REAL, con el fetch stubbeado ─────────────────────────────────────────
# Los tests de arriba miden el helper, y el helper no recibe filas: por si solos NO
# detectarian una mutacion que contaminara cada activo o que alterara el orden. Estos
# tres ejercitan `tool_search_nearby_assets` de verdad — el unico sitio donde se ve la
# forma que el modelo realmente recibe.

def _salida(monkeypatch, filas, radio_pedido=1200, hay_en=None):
    """Corre la tool real con `_fetch_rows` sustituido. `hay_en` = radio en el que
    aparecen resultados, para poder ejercitar la expansion progresiva."""
    import asyncio

    from app.agent import tools as T

    async def _fake(query, params):
        if hay_en is not None and params["radius"] != hay_en:
            return []
        return [dict(f) for f in filas]

    monkeypatch.setattr(T, "_fetch_rows", _fake)
    crudo = asyncio.run(T.tool_search_nearby_assets.ainvoke(
        {"latitude": ANCLA["latitude"], "longitude": ANCLA["longitude"],
         "radius_meters": radio_pedido}))
    return json.loads(crudo)


def test_la_tool_declara_la_relacion_en_el_nivel_del_resultado(monkeypatch):
    d = _salida(monkeypatch, [_fila()])
    assert d["pertenencia_territorial"] == "unknown"
    assert d["relacion_recuperacion"] == "within_radius"
    assert d["ancla_busqueda"] == {"latitude": ANCLA["latitude"],
                                   "longitude": ANCLA["longitude"],
                                   "geometry_type": "point"}
    assert d["radius_requested_m"] == d["radius_searched_m"] == 1200
    # y la distancia por candidato sigue intacta
    assert d["assets"][0]["distancia_metros"] == DIST


def test_ningun_activo_carga_la_pertenencia(monkeypatch):
    """Si viajara por activo pareceria que evaluamos su geometria contra un limite."""
    d = _salida(monkeypatch, [_fila(), _fila(id="otro", distancia_metros=900.0)])
    for a in d["assets"]:
        assert "pertenencia_territorial" not in a
        assert "relacion_recuperacion" not in a


def test_la_expansion_progresiva_se_declara_en_la_tool(monkeypatch):
    """FIXTURE PEDIDA: se piden 1200 m, no hay nada, la busqueda se abre a 3000 y
    encuentra. La salida debe decir AMBOS radios — hoy esa verdad esta casi escondida."""
    d = _salida(monkeypatch, [_fila()], radio_pedido=1200, hay_en=3000)
    assert d["radius_requested_m"] == 1200
    assert d["radius_searched_m"] == 3000


def test_sin_resultados_tambien_se_declara_la_relacion(monkeypatch):
    d = _salida(monkeypatch, [], hay_en=-1)
    assert d["assets"] == []
    assert d["pertenencia_territorial"] == "unknown"
    assert d["radius_requested_m"] == 1200


def test_el_orden_por_distancia_no_se_altera(monkeypatch):
    filas = [_fila(id="a", distancia_metros=100.0),
             _fila(id="b", distancia_metros=200.0),
             _fila(id="c", distancia_metros=300.0)]
    d = _salida(monkeypatch, filas)
    assert [a["id"] for a in d["assets"]] == ["a", "b", "c"]


# ── 9 · EL GEOCODER REAL, no solo su ayudante ────────────────────────────────────────
# M5 SOBREVIVIO a la primera pasada de mutaciones: `test_el_geocoder_declara_fuente_y_
# geometria` mide `_ancla_de` en aislamiento, asi que inlinear otra vez el dict literal en
# la rama Nominatim la dejaba verde. Mismo defecto que E3.2b.4a: el test llamaba al
# ayudante y nadie miraba si el call site lo usaba. Estos dos ejercitan la tool entera.

def _geocodifica(monkeypatch, *, con_google):
    import asyncio

    from app.agent import tools as T

    class _Loc:
        address = "La Floresta, Mariscal Sucre, Distrito Metropolitano de Quito"
        latitude, longitude = ANCLA["latitude"], ANCLA["longitude"]

    class _FakeNominatim:
        def __init__(self, *a, **k):
            pass

        def geocode(self, *a, **k):
            return _Loc()

    monkeypatch.setattr(T.settings, "google_maps_api_key",
                        "clave-de-prueba" if con_google else "")
    if con_google:
        async def _fake_google(address, key):
            return {"lat": ANCLA["latitude"], "lon": ANCLA["longitude"],
                    "formatted": "La Floresta, Quito"}
        monkeypatch.setattr(T, "_geocode_google", _fake_google)
    else:
        monkeypatch.setattr(T, "Nominatim", _FakeNominatim)
    return json.loads(asyncio.run(
        T.tool_geocode_address.ainvoke({"address": "La Floresta"})))


def test_la_rama_NOMINATIM_declara_source_y_geometry_type(monkeypatch):
    """La rama que corrio en los 10 turnos del probe. Hasta el 2026-08-30 no emitia
    `source` en absoluto."""
    d = _geocodifica(monkeypatch, con_google=False)
    assert d["found"] is True
    assert d["source"] == "nominatim"
    assert d["geometry_type"] == "point"
    assert d["latitude"] == ANCLA["latitude"]


def test_la_rama_GOOGLE_declara_source_y_geometry_type(monkeypatch):
    """Google ya traia `source`; le faltaba `geometry_type`. Una sola funcion para las dos
    ramas: tener dos formas de describir lo mismo es como se desincronizan."""
    d = _geocodifica(monkeypatch, con_google=True)
    assert d["source"] == "google"
    assert d["geometry_type"] == "point"
