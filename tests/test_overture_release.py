"""E0.2 del Trust Gate — el release de Overture se descubre, no se fija.

El defecto: scripts/foso_pois_spike.py tenía escrito
'release/2026-06-17.0' en la ruta de S3. Overture NO conserva los releases viejos —
el 2026-08-24 el bucket solo ofrecía 2026-07-22.0 y 2026-08-19.0—, así que ese
prefijo había dejado de existir. La tubería no estaba desactualizada: estaba rota, y
en silencio, porque leer un prefijo vacío devuelve cero filas y cero filas no es un
error para DuckDB.

Estas pruebas no tocan la red: cargan el script como módulo y sustituyen el listado
por respuestas conocidas. Lo que se prueba es la decisión —qué release se elige y qué
pasa cuando no se puede preguntar—, no la disponibilidad de S3.
"""
import importlib.util
import pathlib

import pytest

_RUTA = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "foso_pois_spike.py"


@pytest.fixture(scope="module")
def foso():
    spec = importlib.util.spec_from_file_location("foso_pois_spike", _RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(autouse=True)
def sin_release_fijado(monkeypatch):
    # OVERTURE_RELEASE en el entorno real del desarrollador no debe alterar las pruebas.
    monkeypatch.delenv("OVERTURE_RELEASE", raising=False)


def test_elige_el_release_mas_reciente(foso, monkeypatch):
    monkeypatch.setattr(foso, "_releases_disponibles",
                        lambda: ["2026-07-22.0", "2026-08-19.0"])
    assert foso.overture_release() == "2026-08-19.0"


def test_ordena_por_fecha_no_por_orden_de_llegada(foso, monkeypatch):
    """S3 devuelve los prefijos ordenados, pero no dependemos de que lo haga."""
    monkeypatch.setattr(foso, "_releases_disponibles",
                        lambda: ["2026-08-19.0", "2025-12-01.0", "2026-07-22.0"])
    assert foso.overture_release() == "2026-08-19.0"


def test_la_variable_de_entorno_manda(foso, monkeypatch):
    """Para reproducir una corrida pasada hay que poder clavar un release."""
    monkeypatch.setenv("OVERTURE_RELEASE", "2026-07-22.0")
    def _no_deberia_llamarse():
        raise AssertionError("con OVERTURE_RELEASE fijado no se debe consultar S3")
    monkeypatch.setattr(foso, "_releases_disponibles", _no_deberia_llamarse)
    assert foso.overture_release() == "2026-07-22.0"


def test_sin_red_cae_al_respaldo_y_lo_dice(foso, monkeypatch, capsys):
    """Que se caiga la red no debe tumbar la corrida sin explicar por qué."""
    def _revienta():
        raise ConnectionError("sin salida a internet")
    monkeypatch.setattr(foso, "_releases_disponibles", _revienta)
    assert foso.overture_release() == foso.OVERTURE_RELEASE_FALLBACK
    salida = capsys.readouterr().out
    assert "No se pudo listar" in salida
    assert "rotado" in salida, "el respaldo puede estar caducado y hay que advertirlo"


def test_bucket_vacio_es_error_ruidoso(foso, monkeypatch):
    """Si Overture cambia la forma del bucket, hay que enterarse en el momento —
    no seguir con una ruta inventada y cosechar cero POIs."""
    monkeypatch.setattr(foso, "_releases_disponibles", lambda: [])
    with pytest.raises(RuntimeError, match="ningún release"):
        foso.overture_release()


def test_ignora_prefijos_que_no_son_releases(foso, monkeypatch):
    """El bucket puede tener otras carpetas; solo cuentan las con forma de fecha."""
    monkeypatch.setattr(foso, "_releases_disponibles", lambda: ["2026-08-19.0"])
    assert foso.overture_release() == "2026-08-19.0"


def test_el_glob_apunta_a_places_del_release_elegido(foso):
    glob = foso.overture_glob("2026-08-19.0")
    assert glob.startswith("s3://overturemaps-us-west-2/release/2026-08-19.0/")
    assert glob.endswith("theme=places/type=place/*")
    assert "2026-06-17.0" not in glob, "el release fijado y borrado no puede reaparecer"


def test_avisar_sin_configuracion_no_falla(foso, monkeypatch, capsys):
    """Un aviso que no se puede mandar no debe convertirse en un segundo problema."""
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    monkeypatch.delenv("ALERTA_OPS_EMAIL", raising=False)
    assert foso.avisar_ops("asunto", "detalle") is False
    assert "Aviso NO enviado" in capsys.readouterr().out


def test_el_corte_por_credencial_no_ocurre_al_importar(foso, monkeypatch):
    """Regresión del PR #119: el módulo llamaba a sys.exit(1) al importarse.

    Que la fixture `foso` haya podido cargar el módulo ya es media prueba, y es la
    mitad que solo se ve en CI: allí no hay .env, y antes del arreglo eso mataba la
    recolección de este archivo entero —ocho pruebas que ni siquiera abren una
    conexión—. En el portátil del fundador nunca falló, que es justo por lo que hacía
    falta el gate.

    La otra mitad es que el corte SIGA existiendo, solo que corrido al momento de
    ejecutar. Sin esto, el arreglo podría haber sido borrar la comprobación.
    """
    monkeypatch.setattr(foso, "DB_URL", "")
    with pytest.raises(SystemExit) as salida:
        foso.exigir_credencial_de_base()
    assert salida.value.code == 1
