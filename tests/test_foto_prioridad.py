"""Bug real (feedback en vivo, 2026-07-02): al probar el primer inmueble REAL (Jorge Salvador
Lara), el corredor subio fotos reales via caracteristicas.fotos, pero la tarjeta del chat
seguia mostrando el sofa de stock de Unsplash del backfill (imagen_url).

Causa: _card_from_row priorizaba `row["imagen_url"]` (poblado por seed_fill_all_fase1.sql con
Unsplash para activos sin foto real) SIEMPRE por encima de `caracteristicas.fotos` (las fotos
reales que sube el corredor) — y ningun endpoint de edicion limpia/actualiza imagen_url al
subir fotos nuevas, asi que el stock ganaba para siempre. La pagina publica /a/{id}
(assets.py, endpoint asset_anuncio) YA tenia la prioridad correcta (fotos primero); este fix
alinea chat.py a la misma regla.
"""
from app.routers.chat import _card_from_row


def _row(**over):
    row = {
        "id": "abc", "direccion": "Dir", "tipo_activo": "Departamento",
        "operacion": "ARRIENDO", "precio": 200, "caminabilidad": 90,
        "lat": -0.18, "lon": -78.48, "servicios_cercanos": None, "fresco": False,
        "imagen_url": None, "caracteristicas": {},
    }
    row.update(over)
    return row


def test_foto_real_del_corredor_le_gana_al_stock_de_unsplash():
    # El caso reportado en vivo: imagen_url ya tiene el Unsplash del backfill, pero el
    # corredor subio una foto real a caracteristicas.fotos — la real debe ganar.
    row = _row(
        imagen_url="https://images.unsplash.com/stock-sofa-generico.jpg",
        caracteristicas={"fotos": ["https://storage.contexxto.com/real/jorge-salvador-lara-1.jpg"]},
    )
    card = _card_from_row(row)
    assert card["imagen_url"] == "https://storage.contexxto.com/real/jorge-salvador-lara-1.jpg"


def test_imagen_url_sigue_siendo_fallback_si_no_hay_fotos_reales():
    # Si el corredor NUNCA subio fotos, el Unsplash del backfill sigue siendo mejor que nada.
    row = _row(
        imagen_url="https://images.unsplash.com/stock-sofa-generico.jpg",
        caracteristicas={},
    )
    card = _card_from_row(row)
    assert card["imagen_url"] == "https://images.unsplash.com/stock-sofa-generico.jpg"


def test_sin_ninguna_foto_la_tarjeta_no_inventa_una():
    row = _row(imagen_url=None, caracteristicas={})
    card = _card_from_row(row)
    assert card["imagen_url"] is None
