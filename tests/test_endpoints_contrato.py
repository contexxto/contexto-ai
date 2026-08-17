"""
Contrato HTTP de los endpoints nuevos — el test que faltaba.

EL FALLO QUE LO ORIGINA (2026-08-17, primera prueba real contra el backend): `visitas.py`
y `alertas.py` empezaban con `from __future__ import annotations`. Con ese import las
anotaciones se vuelven CADENAS, FastAPI recibe un `ForwardRef('LlegadaIn')` en vez del
modelo, y degrada el cuerpo a **parámetro de query**. Resultado: los dos endpoints
respondían 422 a TODA llamada, y `/openapi.json` devolvía 500.

Ninguno de los 684 tests lo veía, porque ninguno llamaba al endpoint: probaban la lógica
pura y el esquema, no el contrato HTTP. Y en producción habría sido invisible un buen
rato — el registro de llegadas se traga sus errores a propósito (`.catch(() => {})`), así
que F0 habría estado muerta sin una sola alarma.

Estos tests no necesitan base de datos: FastAPI construye el esquema al importar la app.
"""
import pytest

from main import app


@pytest.fixture(scope="module")
def esquema():
    """El OpenAPI de la app. Generarlo YA es media prueba: con el ForwardRef sin resolver,
    esta llamada explota (que es exactamente el 500 que devolvía /openapi.json)."""
    return app.openapi()


@pytest.mark.parametrize("ruta", ["/api/v1/visitas", "/api/v1/alertas"])
def test_el_cuerpo_es_body_y_no_query(esquema, ruta):
    """El modelo va en el CUERPO. Si alguien reintroduce `from __future__ import
    annotations` en el router, esta afirmación se cae antes de llegar a producción."""
    op = esquema["paths"][ruta]["post"]
    assert op.get("requestBody"), f"{ruta} no declara cuerpo: el modelo se degradó a query"
    nombres = [p.get("name") for p in op.get("parameters", [])]
    assert "cuerpo" not in nombres, f"{ruta} expone el cuerpo como parámetro de query: {nombres}"


@pytest.mark.parametrize("ruta,campos", [
    ("/api/v1/visitas", {"session_id", "superficie", "referrer", "utm_source", "activo_id"}),
    ("/api/v1/alertas", {"session_id", "email", "criterio", "hubo_match", "motivo"}),
])
def test_el_esquema_del_cuerpo_trae_los_campos_que_manda_el_frontend(esquema, ruta, campos):
    """El contrato con el frontend, afirmado. Si un campo se renombra en el backend sin
    tocar el cliente, el dato llegaría vacío en silencio."""
    ref = (esquema["paths"][ruta]["post"]["requestBody"]["content"]["application/json"]
           ["schema"]["$ref"])
    modelo = esquema["components"]["schemas"][ref.rsplit("/", 1)[-1]]
    faltan = campos - set(modelo["properties"])
    assert not faltan, f"{ruta} perdió campos del contrato: {faltan}"


def test_ningun_router_usa_el_future_import():
    """La causa raíz, vigilada en la raíz. Los módulos PUROS sí pueden usarlo (no los ve
    FastAPI); los routers con modelos de cuerpo, no."""
    import re
    from pathlib import Path

    # Al INICIO DE LÍNEA: una sentencia real, no la mención en un comentario. La primera
    # versión buscaba la subcadena y se marcaba a sí misma con los comentarios que
    # explican por qué el import no está.
    sentencia = re.compile(r"^from __future__ import annotations", re.M)
    routers = Path(__file__).resolve().parents[1] / "app" / "routers"
    culpables = [p.name for p in routers.glob("*.py")
                 if sentencia.search(p.read_text(encoding="utf-8"))]
    assert not culpables, (
        f"estos routers usan `from __future__ import annotations`: {culpables}. "
        "FastAPI recibiría un ForwardRef y degradaría el cuerpo a query (422 en toda llamada)."
    )
