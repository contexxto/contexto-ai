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


def test_el_letrero_lleva_el_lockup_maestro_y_no_una_copia():
    """La marca del letrero se LEE de docs/branding/logo/contexto-horizontal.svg: signo y palabra
    del maestro. Hasta el 2026-09-21 ponía el signo con «Contexto» escrito en su tipografía (y antes
    una copia pegada del signo viejo, que derivó con él)."""
    import re

    lockup = gq._lockup(44)
    maestro = (_ROOT / "docs" / "branding" / "logo" / "contexto-horizontal.svg").read_text(encoding="utf-8")
    formas = re.search(r"<svg[^>]*>(.*)</svg>", maestro, re.S).group(1)
    assert formas in lockup, "el letrero ya no lleva el lockup maestro"
    card = gq._letrero_card({"id": "x", "direccion": "Calle"}, "https://app.test", uid="0")
    assert not re.search(r">\s*Contexto\s*<", card), "volvió la palabra escrita a mano"


def test_lockup_escala_y_sin_ids_colisionables():
    a = gq._lockup(44)
    assert 'height="44"' in a and 'width="189.09"' in a  # 44 × 56,9 / 13,24: la proporción del lienzo
    assert a.lstrip().startswith("<svg") and a.rstrip().endswith("</svg>")
    # Plano, sin <defs> ni gradientes: repetir el lockup en una página no choca ids.
    assert 'id="' not in a


def test_letrero_incrusta_deeplink_y_direccion():
    activo = {"id": "abc-123", "direccion": "Av. Test 100 y Quito"}
    card = gq._letrero_card(activo, "https://app.test", uid="0")
    assert "https://app.test/a/abc-123" in card  # deep-link permanente
    assert "Av. Test 100 y Quito" in card        # dirección visible
    assert card.count("<svg") == 2               # lockup + QR
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
