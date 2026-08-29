"""G19-A · la procedencia de la caminabilidad viaja con el valor hasta el modelo.

EL DEFECTO, caracterizado en G19.0 sobre el turno REAL del canary (2026-08-29):

```
tool_find_assets_by_text  →  {"caminabilidad": 100, "walk_score_fuente": null}
                                                     └── el modelo rellenó el hueco
prosa  →  "caminabilidad 100, calculada sobre los comercios reales del sector"
tarjeta →  "estimada por zona — todavía sin contrastar"
```

`walk_score_fuente` es NULL en los 40 activos de producción. La semántica que convierte ese
NULL en el lado seguro YA EXISTÍA —`encaje._FUENTE_CAMINABLE_DESCONOCIDA = "estimación por
zona"`— pero sólo se aplicaba dentro de `_score_caminable`, es decir **cuando la caminabilidad
había sido relevante para el ranking**. El bloque autoritativo del turno canary no mencionaba
caminabilidad, porque la persona no la pidió; el número llegó por la tool, en crudo.

La separación que esto restaura:

```
RELEVANCIA PARA LA DECISIÓN   ≠   PROCEDENCIA DEL DATO
(decide si puntúa)                (acompaña SIEMPRE a un dato narrable)
```

## Alcance deliberado

Se AÑADE un campo derivado, `caminabilidad_procedencia`. NO se toca `walk_score_fuente`: sigue
siendo el código crudo (`osm` | `heuristico` | `null`), porque cambiarlo por prosa rompería a
cualquier consumidor que lo compare. NO se añade todavía ninguna política de qué puede afirmar
el modelo —eso es G19-B— ni nada sobre pertenencia territorial —eso es G20—.

Y `razones[]` no cambia: la caminabilidad no se vuelve una razón de encaje por esto.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from app.agent import tools as T
from app.encaje import calcular_encaje

FILA_BASE = {
    "id": "activo-1",
    "direccion_estandarizada": "Calle Alemania E12-34 y González Suárez, Quito",
    "tipo_activo": "departamento",
    "caminabilidad": 100,
    "walk_score_fuente": None,          # NULL, como los 40 de producción
    "operacion": "arriendo",
    "precio": 630,
    "servicios_cercanos": "Fybeca; Supermercado Cordero",
    "conectividad": "Metro El Ejido 14 min",
}

# Las TRES fronteras donde el dato se hace consumible por el modelo (G19-A preflight).
FRONTERAS = [
    ("tool_find_assets_by_text", lambda: T.tool_find_assets_by_text.ainvoke(
        {"query": "La Floresta"}), "assets"),
    ("tool_search_nearby_assets", lambda: T.tool_search_nearby_assets.ainvoke(
        {"latitude": -0.2, "longitude": -78.48}), "assets"),
    ("tool_fetch_asset_lifecycle_specs", lambda: T.tool_fetch_asset_lifecycle_specs.ainvoke(
        {"activo_id": "activo-1"}), "specs"),
]


@pytest.fixture
def filas(monkeypatch):
    """Sustituye la BASE, no la lógica: lo que se mide es la SERIALIZACIÓN de la tool."""
    estado = {"fila": dict(FILA_BASE)}

    async def _fetch(_sql, _params=None):
        return [dict(estado["fila"])]

    monkeypatch.setattr(T, "_fetch_rows", _fetch)
    return estado


def _salida(invocar, clave):
    d = json.loads(asyncio.run(invocar()))
    payload = d.get(clave)
    return payload[0] if isinstance(payload, list) else payload


# ══ 1 · el turno real, en las tres fronteras ════════════════════════════════════════


@pytest.mark.parametrize("nombre,invocar,clave", FRONTERAS)
def test_el_valor_NUNCA_viaja_sin_su_procedencia(nombre, invocar, clave, filas):
    """EL DEFECTO DE PRODUCCIÓN. Con `walk_score_fuente` NULL, el modelo recibía un `null`
    y lo rellenó afirmando una medición que nadie hizo."""
    a = _salida(invocar, clave)

    assert a.get("caminabilidad") == 100
    assert a.get("caminabilidad_procedencia") == "estimación por zona", \
        f"{nombre} entregó el valor sin procedencia: {a.get('caminabilidad_procedencia')!r}"


@pytest.mark.parametrize("nombre,invocar,clave", FRONTERAS)
@pytest.mark.parametrize("fuente,esperado", [
    ("osm", "OpenStreetMap"),
    ("heuristico", "estimación por zona"),
    (None, "estimación por zona"),
])
def test_matriz_de_procedencia(nombre, invocar, clave, fuente, esperado, filas):
    filas["fila"]["walk_score_fuente"] = fuente

    a = _salida(invocar, clave)

    assert a.get("caminabilidad_procedencia") == esperado


@pytest.mark.parametrize("nombre,invocar,clave", FRONTERAS)
@pytest.mark.parametrize("fuente", ["osm", "heuristico", None])
def test_el_codigo_CRUDO_se_conserva_intacto(nombre, invocar, clave, fuente, filas):
    """`walk_score_fuente` no cambia de tipo ni de valor. Traducirlo en su sitio habría
    roto a cualquier consumidor que lo compare con `"osm"`."""
    filas["fila"]["walk_score_fuente"] = fuente

    a = _salida(invocar, clave)

    assert a.get("walk_score_fuente") == fuente


# ══ 2 · no fabricar ═════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("nombre,invocar,clave", FRONTERAS)
def test_sin_caminabilidad_NO_se_inventa_procedencia(nombre, invocar, clave, filas):
    """Un activo sin `walk_score` no tiene procedencia que declarar. Emitir «estimación por
    zona» aquí afirmaría que existe una estimación — el mismo tipo de relleno que esta
    unidad viene a cerrar, en la dirección contraria."""
    filas["fila"]["caminabilidad"] = None

    a = _salida(invocar, clave)

    assert a.get("caminabilidad_procedencia") is None, a.get("caminabilidad_procedencia")


# ══ 3 · la separación que se restaura ═══════════════════════════════════════════════


def test_la_procedencia_NO_depende_de_que_la_persona_la_pidiera(filas):
    """LA PROPIEDAD ARQUITECTÓNICA de G19-A, y la que la caracterización destapó.

    La procedencia acompaña al dato porque el dato es NARRABLE, no porque haya entrado en el
    ranking. Antes estaba atada a `_score_caminable`, que sólo corre si la dimensión fue
    declarada: quien no pedía caminabilidad recibía el número desnudo.
    """
    a = _salida(*FRONTERAS[0][1:])

    assert a.get("caminabilidad_procedencia") == "estimación por zona"


def test_la_procedencia_NO_convierte_la_caminabilidad_en_una_RAZON_de_encaje():
    """`razones[]` conserva su semántica de relevancia. Si G19-A la ensanchara, estaríamos
    diciendo que el motor puntuó algo que la persona no pidió."""
    inmueble = {"walk_score": 100, "walk_score_fuente": None, "precio": 630,
                "tipo_operacion": "arriendo"}
    prefs = {"operacion": "arriendo", "presupuesto_max": 900}

    razones = calcular_encaje(prefs, inmueble).get("razones") or []

    assert not any("caminab" in (r.get("texto") or "").lower() for r in razones), razones


@pytest.mark.parametrize("fuente,esperado", [
    ("osm", "OpenStreetMap"),
    ("heuristico", "estimación por zona"),
    (None, "estimación por zona"),
])
def test_LA_MISMA_etiqueta_en_el_carril_de_tool_y_en_el_de_decision(fuente, esperado, filas):
    """FUENTE ÚNICA. El defecto nació de dos comportamientos ante el mismo NULL: el carril de
    decisión lo degradaba al lado seguro y el de tools lo entregaba crudo. Si mañana alguien
    edita una tabla y no la otra, esto se pone rojo.
    """
    filas["fila"]["walk_score_fuente"] = fuente
    de_la_tool = _salida(*FRONTERAS[0][1:]).get("caminabilidad_procedencia")

    razones = calcular_encaje(
        {"operacion": "arriendo", "caminable": True},
        {"walk_score": 100, "walk_score_fuente": fuente, "tipo_operacion": "arriendo"},
    ).get("razones") or []
    de_la_decision = next(
        (r.get("fuente") for r in razones if "caminab" in (r.get("texto") or "").lower()), None)

    assert de_la_tool == esperado
    assert de_la_decision == esperado
    assert de_la_tool == de_la_decision, f"tool={de_la_tool!r} decision={de_la_decision!r}"
