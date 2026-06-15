"""Tests offline de la capa de inversión (app/inversion.py) — funciones puras."""
from app.inversion import _kpis, _veredicto_bruta, analizar_inversion


def test_kpis_caso_base():
    # Inmueble real de prueba: precio 50k, 85 m², renta 180/mes, sin alícuota.
    k = _kpis(50000, 85, 180, None)
    assert k["rentabilidad_bruta_pct"] == 4.3
    assert k["rentabilidad_neta_pct"] == 3.0
    assert k["precio_m2"] == 588
    assert k["renta_anual_usd"] == 2160
    assert k["inversion_total_estimada_usd"] == 53500


def test_kpis_renta_realista():
    k = _kpis(50000, 85, 350, None)        # sin alícuota
    assert k["rentabilidad_bruta_pct"] == 8.4
    assert k["rentabilidad_neta_pct"] == 6.3
    # Con alícuota de 60/mes, la neta baja (más gastos).
    assert _kpis(50000, 85, 350, 60)["rentabilidad_neta_pct"] == 5.0


def test_veredicto_umbrales():
    assert "muy buena" in _veredicto_bruta(8.4)
    assert "buena" in _veredicto_bruta(5.5)
    assert "marginal" in _veredicto_bruta(4.3)
    assert "baja" in _veredicto_bruta(2.0)


def test_faltan_inputs_no_inventa():
    r = analizar_inversion(direccion="X", tipo_activo="departamento",
                           precio=None, area=85, renta_mensual=180,
                           alicuota_mensual=None, tiene_ficha=False)
    assert r["puede_calcular"] is False
    assert "precio" in r["faltan_inputs"]


def test_analisis_completo_con_alertas():
    r = analizar_inversion(direccion="Jorge Salvador Lara", tipo_activo="Departamento",
                           precio=50000, area=85, renta_mensual=180,
                           alicuota_mensual=None, tiene_ficha=False)
    assert r["puede_calcular"] is True
    assert r["kpis"]["rentabilidad_bruta_pct"] == 4.3
    # La renta es estimación → siempre presente esa alerta.
    assert any("ESTIMACIÓN" in a for a in r["alertas_honestas"])
    # Sin ficha → alerta de estado sin verificar.
    assert any("SIN verificar" in a for a in r["alertas_honestas"])
    # Bruta baja (<3.5? no, 4.3) → no dispara la de "renta baja"; confianza marca estado.
    assert r["confianza"]["estado_estructural"] == "sin verificar"
    assert r["confianza"]["renta"] == "estimada"


def test_alerta_yield_implausible():
    # precio bajo + renta alta → bruta absurda → alerta de verificar.
    r = analizar_inversion(direccion="X", tipo_activo="departamento",
                           precio=160, area=85, renta_mensual=180,
                           alicuota_mensual=None, tiene_ficha=True)
    assert r["kpis"]["rentabilidad_bruta_pct"] > 14
    assert any("implausiblemente alta" in a for a in r["alertas_honestas"])
