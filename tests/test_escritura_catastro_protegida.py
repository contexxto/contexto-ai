"""E0.1 del Trust Gate — la superficie de escritura del catastro exige credencial.

Hasta el 2026-08-24, POST /api/v1/assets/ aceptaba escritura anónima: cualquiera
podía inscribir una coordenada en el Catastro Vivo y, de paso, encolar
_recompute_walk_score (Overpass + Google Routes/Places), gastando en APIs de pago
sin tope. Era uno de los cuatro P0 de la auditoría.

test_auth.py ya cubre verify_api_key como función. Lo que falta —y es lo que aquí
se prueba— es que los endpoints la APLIQUEN: una guardia que existe pero que
ninguna ruta declara no protege nada.

Se inspeccionan las dependencias reales que FastAPI resolvió al registrar cada
ruta, no el texto del archivo: un grep se engaña con un comentario, esto no.
"""
import pytest

from main import app

# Dependencias que actúan como guardia de escritura.
GUARDIAS = {"verify_api_key", "get_current_user", "require_roles"}

METODOS_ESCRITURA = {"POST", "PUT", "PATCH", "DELETE"}

# Rutas de escritura bajo /assets/ que son públicas A PROPÓSITO. La lista es
# explícita y corta por diseño: si alguien añade una, tiene que justificarla aquí.
PUBLICAS_DELIBERADAS = {
    # Mapa conversacional del visitante. No escribe en base: interpreta una
    # pregunta y devuelve acciones de mapa. Acotado con @limiter.limit("40/minute").
    ("POST", "/api/v1/assets/mapa/comando"),
}


def _guardias_de(route) -> set[str]:
    nombres = set()
    for dep in getattr(route.dependant, "dependencies", []):
        nombre = getattr(getattr(dep, "call", None), "__name__", None)
        if nombre:
            nombres.add(nombre)
    return nombres


def _rutas_de_escritura(prefijo: str):
    for r in app.routes:
        metodos = (getattr(r, "methods", set()) or set()) & METODOS_ESCRITURA
        if metodos and r.path.startswith(prefijo):
            yield sorted(metodos)[0], r.path, r


def test_create_asset_exige_api_key():
    """El endpoint de alta del catastro declara verify_api_key. Este es el P0."""
    ruta = next(
        (r for m, p, r in _rutas_de_escritura("/api/v1/assets") if p == "/api/v1/assets/" and m == "POST"),
        None,
    )
    assert ruta is not None, "POST /api/v1/assets/ desapareció del enrutador"
    assert "verify_api_key" in _guardias_de(ruta), (
        "POST /api/v1/assets/ quedó sin guardia: vuelve a aceptar escritura anónima "
        "en el catastro y a encolar llamadas a proveedores de pago."
    )


def test_ninguna_escritura_de_catastro_queda_anonima():
    """Red de regresión: toda ruta de escritura bajo /assets/ tiene guardia,
    salvo las declaradas públicas arriba con su razón."""
    sin_guardia = [
        f"{metodo} {path}"
        for metodo, path, ruta in _rutas_de_escritura("/api/v1/assets")
        if not (_guardias_de(ruta) & GUARDIAS)
        and (metodo, path) not in PUBLICAS_DELIBERADAS
    ]
    assert not sin_guardia, (
        "Estas rutas de escritura del catastro no exigen credencial. Si alguna debe "
        "ser pública, decláralo en PUBLICAS_DELIBERADAS con su motivo:\n  "
        + "\n  ".join(sorted(sin_guardia))
    )


@pytest.mark.parametrize("ruta_esperada", [
    "/api/v1/assets/ingest",
    "/api/v1/assets/ingest/batch",
])
def test_hermanos_de_ingesta_siguen_protegidos(ruta_esperada):
    """Los otros puntos de alta ya exigían la llave. Si uno se abre, se entera aquí."""
    ruta = next((r for _m, p, r in _rutas_de_escritura("/api/v1/assets") if p == ruta_esperada), None)
    assert ruta is not None, f"{ruta_esperada} desapareció del enrutador"
    assert _guardias_de(ruta) & GUARDIAS, f"{ruta_esperada} perdió su guardia"
