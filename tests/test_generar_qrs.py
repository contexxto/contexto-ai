"""
Tests offline del generador de QRs/letreros (scripts/generar_qrs.py).

No tocan red: validan los helpers puros que arman el letrero y el QR.
"""
import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SPEC = importlib.util.spec_from_file_location(
    "generar_qrs", _ROOT / "scripts" / "generar_qrs.py"
)
gq = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gq)  # type: ignore[union-attr]


def test_qr_svg_inline_es_svg():
    svg = gq._qr_svg_inline("https://ejemplo.test/a/123")
    assert "<svg" in svg and "</svg>" in svg
    assert "<?xml" not in svg  # inline → sin declaración XML


def test_sphere_escala_y_uid_unico():
    a = gq._sphere(44, "0")
    b = gq._sphere(44, "1")
    assert 'width="44"' in a
    # ids con uid distinto evitan colisión al poner varias esferas en una página
    assert "sg0" in a and "sg1" in b
    assert "sg0" not in b


def test_letrero_incrusta_deeplink_y_direccion():
    activo = {"id": "abc-123", "direccion": "Av. Test 100 y Quito"}
    card = gq._letrero_card(activo, "https://app.test", uid="0")
    assert "https://app.test/a/abc-123" in card  # deep-link permanente
    assert "Av. Test 100 y Quito" in card        # dirección visible
    assert card.count("<svg") == 2               # esfera + QR
    assert "CADA LUGAR TIENE UN AURA" in card


def test_letrero_escapa_html_en_direccion():
    activo = {"id": "x", "direccion": "Casa <b>rara</b> & cía"}
    card = gq._letrero_card(activo, "https://app.test", uid="0")
    assert "&lt;b&gt;rara&lt;/b&gt;" in card
    assert "&amp; c" in card


def test_html_doc_envuelve_documento():
    doc = gq._html_doc("Titulo", "<p>hola</p>")
    assert doc.startswith("<!doctype html>")
    assert "<title>Titulo</title>" in doc
    assert "<p>hola</p>" in doc


@pytest.mark.parametrize("app_url", ["https://app.test", "https://app.test/"])
def test_deeplink_sin_doble_slash(app_url):
    card = gq._letrero_card({"id": "z", "direccion": "d"}, app_url, uid="0")
    assert "https://app.test/a/z" in card
    assert "//a/z" not in card
