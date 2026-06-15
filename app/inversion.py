"""
Capa de inversión — lógica financiera PURA (sin red, sin DB).

Fuente ÚNICA de verdad del análisis de inversión: la consumen tanto el agente
(tool_analyze_investment) como el endpoint REST (GET /assets/{id}/investment).
Es el principio API-first (patrón Apaleo): una sola lógica, varios clientes.
"""
from __future__ import annotations

# Parámetros por mercado (defaults Ecuador/LATAM; configurables a futuro por jurisdicción).
_INV = {
    "costo_adquisicion_pct": 0.07,    # notaría, registro, alcabala, etc.
    "vacancia_meses": 1.0,            # ~1 mes/año sin arrendar
    "mantenimiento_pct_renta": 0.05,  # 5% de la renta anual
    "predial_pct_precio": 0.005,      # impuesto predial anual aprox.
}


def _veredicto_bruta(b: float) -> str:
    if b >= 7:
        return "muy buena (renta atractiva)"
    if b >= 5:
        return "buena (sobre el umbral de inversión)"
    if b >= 3.5:
        return "marginal (apenas; revisa los gastos)"
    return "baja como renta — solo tendría sentido por revalorización/ubicación, no por flujo"


def _kpis(precio: float, area: float | None, renta_mensual: float,
          alicuota_mensual: float | None) -> dict:
    """Cálculo PURO de los KPIs de inversión."""
    renta_anual = renta_mensual * 12
    bruta = renta_anual / precio * 100
    inversion_total = precio * (1 + _INV["costo_adquisicion_pct"])
    gastos = ((alicuota_mensual or 0) * 12
              + renta_mensual * _INV["vacancia_meses"]
              + renta_anual * _INV["mantenimiento_pct_renta"]
              + precio * _INV["predial_pct_precio"])
    neta = (renta_anual - gastos) / inversion_total * 100
    return {
        "rentabilidad_bruta_pct": round(bruta, 1),
        "rentabilidad_neta_pct": round(neta, 1),
        "precio_m2": round(precio / area) if area else None,
        "renta_anual_usd": round(renta_anual),
        "inversion_total_estimada_usd": round(inversion_total),
        "veredicto": _veredicto_bruta(bruta),
    }


def analizar_inversion(*, direccion: str | None, tipo_activo: str | None,
                       precio: float | None, area: float | None,
                       renta_mensual: float | None, alicuota_mensual: float | None,
                       tiene_ficha: bool) -> dict:
    """
    Resultado completo del análisis de inversión a partir de inputs ya leídos.
    Si faltan inputs, lo dice con honestidad (no inventa). Devuelve siempre un dict
    serializable, idéntico para el agente y para el API REST.
    """
    faltan = [n for n, v in (("precio", precio), ("área (m²)", area),
                             ("renta mensual estimada", renta_mensual)) if not v]
    if faltan:
        return {
            "direccion": direccion, "puede_calcular": False, "faltan_inputs": faltan,
            "mensaje": "Para analizar la inversión faltan: " + ", ".join(faltan)
                       + ". El dueño puede agregarlos en la ficha del inmueble.",
        }

    kpis = _kpis(float(precio), float(area), float(renta_mensual), alicuota_mensual)

    # Chequeo HONESTO de la calidad del input (el diferenciador vs. los scrapers).
    alertas = ["La renta es una ESTIMACIÓN del corredor, no un contrato verificado."]
    b = kpis["rentabilidad_bruta_pct"]
    if b > 14:
        alertas.append("Rentabilidad implausiblemente alta — verifica que el precio y la renta sean correctos.")
    elif b < 3.5:
        alertas.append("La renta estimada parece baja para el precio — vale la pena verificarla; podría cambiar el veredicto.")
    if not tiene_ficha:
        alertas.append("Estado estructural SIN verificar (ficha técnica pendiente) — riesgo de reparaciones no cuantificado.")

    return {
        "direccion": direccion, "tipo_activo": tipo_activo, "puede_calcular": True,
        "inputs": {"precio_usd": precio, "area_m2": area,
                   "renta_mensual_estimada_usd": renta_mensual, "alicuota_mensual_usd": alicuota_mensual},
        "kpis": kpis,
        "supuestos": "Adquisición 7% · vacancia 1 mes/año · mantenimiento 5% de renta · predial 0.5%/año (configurables por mercado)",
        "alertas_honestas": alertas,
        "umbral_referencia": "Bruta >5% se considera buena inversión de renta en LATAM (sobre el costo de oportunidad).",
        "confianza": {"precio": "declarado", "area": "declarada", "renta": "estimada",
                      "estado_estructural": "verificado" if tiene_ficha else "sin verificar"},
    }
