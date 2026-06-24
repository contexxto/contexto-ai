"""Tests offline del motor de intención (app/intencion.py) — lógica pura."""
from app.intencion import analizar_intencion, ESTADOS


def test_anonimo_sin_mensajes():
    r = analizar_intencion(mensajes_usuario=[])
    assert r["estado"] == "anonimo"
    assert r["nivel"] == "frio"
    assert r["score"] == 0
    assert r["handoff_sugerido"] is False


def test_qr_suma_pero_sin_senales_es_frio():
    r = analizar_intencion(mensajes_usuario=[], es_qr=True)
    assert r["senales"].get("qr") is True
    assert "QR" in r["razones"][0]
    assert r["nivel"] == "frio"          # 10 puntos < 30


def test_identificado_da_perfil():
    # Necesidad DECLARADA (uso/presupuesto/mudanza) — eje objetivo, no protegido.
    r = analizar_intencion(mensajes_usuario=["Busco algo para mudarme, dentro de mi presupuesto"])
    assert r["estado"] in ("identificado", "enganchado")
    assert r["senales"].get("perfil") is True


def test_composicion_familiar_no_puntua():
    """Fair Housing: mencionar familia/hijos/esposa NO genera señal ni puntúa
    (familial status es clase protegida). Solo la necesidad declarada cuenta."""
    r = analizar_intencion(mensajes_usuario=["Tengo dos hijos y una esposa"])
    assert r["senales"].get("perfil") is not True
    assert r["score"] == 0


def test_explorando_compara_zonas():
    r = analizar_intencion(mensajes_usuario=[
        "¿Cómo es vivir en La Carolina? caminabilidad y ruido",
        "¿Y comparado con Cumbayá? cuál es mejor para servicios",
    ])
    assert r["estado"] == "explorando"
    assert r["nivel"] in ("tibio", "caliente")


def test_enganchado_profundiza_una_zona():
    r = analizar_intencion(mensajes_usuario=["¿Cómo es vivir aquí? seguridad y transporte"])
    assert r["estado"] == "enganchado"


def test_intencion_precio_y_ficha():
    r = analizar_intencion(mensajes_usuario=[
        "¿Cuánto cuesta este departamento?",
        "¿Me pasas la ficha técnica con el estado de las tuberías?",
    ], es_qr=True)
    assert r["estado"] == "intencion"
    assert r["senales"].get("precio") and r["senales"].get("ficha")
    assert any("precio" in x.lower() for x in r["razones"])


def test_pico_dispara_handoff():
    r = analizar_intencion(mensajes_usuario=[
        "Me encanta, ¿se puede agendar una visita?",
        "¿Me das el contacto del corredor?",
    ], es_qr=True)
    assert r["estado"] == "intencion"
    assert r["handoff_sugerido"] is True
    assert r["nivel"] == "caliente"
    assert "HANDOFF" in r["accion_sugerida"]


def test_inversion_por_herramienta():
    # Sin texto de inversión, pero el agente corrió el tool → señal fuerte.
    r = analizar_intencion(mensajes_usuario=["Cuéntame de este inmueble"],
                           uso_tool_inversion=True)
    assert r["senales"].get("inversion") is True
    assert r["estado"] == "intencion"


def test_score_acotado_0_100():
    r = analizar_intencion(mensajes_usuario=[
        "precio", "visita", "ficha", "rentabilidad", "contacto corredor",
    ], es_qr=True, herramientas_usadas=9, uso_tool_inversion=True, turnos=12)
    assert 0 <= r["score"] <= 100
    assert r["score"] == 100


def test_resumen_es_explicable():
    r = analizar_intencion(mensajes_usuario=["¿Cuánto vale?"], es_qr=True)
    assert r["resumen"].startswith(("🔵", "🟡", "🔥"))
    assert "—" in r["resumen"]


def test_estados_constante():
    assert "intencion" in ESTADOS and "anonimo" in ESTADOS
