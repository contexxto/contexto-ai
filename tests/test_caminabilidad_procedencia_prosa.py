"""TRUST-HOTFIX-01 — la prosa afirma una procedencia de caminabilidad que el dato no sostiene.

CASO REAL, capturado en contexxto.com el 2026-08-25 a las 14:49 (smoke test de cierre de F2,
9 min después de que `2d4291b` quedara live). Un solo turno, un solo inmueble, y las dos
superficies se contradijeron:

    ficha:  «Caminabilidad estimada por zona — todavía sin contrastar con los comercios…»
    prosa:  «Caminabilidad 84 (calculada sobre los comercios reales de la zona)»

`caminabilidad_fuente` era `heuristico`.

ES LA TERCERA SUPERFICIE DEL MISMO PROBLEMA, y las otras dos ya estaban cerradas:

    ResultCards.jsx          CERRADO (2026-08-11 — el pie sale de walk_score_fuente)
    encaje._score_caminable  CERRADO (E0.3 — _FUENTE_CAMINABLE)
    narración libre          ← esto

`app/agent/graph.py` se lo prohíbe al modelo con todas las letras —«JAMÁS afirmes
"comercios reales / OpenStreetMap" para una caminabilidad estimada»— y el modelo lo hizo
igual. Es el modo de fallo de la batalla Hiinmo: el bloque autoritativo garantiza que el
modelo RECIBA el dato, no que lo obedezca. Por eso el guardián existe en la salida.

PRIORIDAD DE ESTE CHEQUEO: **precisión sobre cobertura.** Un guardián que acusa de mentir a
una respuesta honesta se desactiva a la semana — el mismo criterio con que se escribió el
resto del módulo, donde cada caso va en pareja (la prosa que mintió y la honesta equivalente).
Cuando la tarjeta no se puede identificar sin ambigüedad, este chequeo CALLA.
"""

import pytest

from app.verificacion_prosa import ALTA, verificar_prosa

_PREFS = {"operacion": "arriendo", "tipo_inmueble": "departamento", "presupuesto_max": 700}

CODIGO = "caminabilidad_procedencia_falsa"


def _card(cid, precio, caminabilidad, fuente, direccion=None):
    return {
        "id": cid,
        "direccion": direccion or f"Calle {cid}",
        "tipo_activo": "Departamento",
        "operacion": "ARRIENDO",
        "precio": precio,
        "encaje": 60,
        "caminabilidad": caminabilidad,
        "caminabilidad_fuente": fuente,
        "caracteristicas": {"num_dormitorios": 2},
        "lat": -0.18, "lon": -78.48,
    }


# ── El caso de producción, tal cual ────────────────────────────────────────────────

CARD_REAL = _card("real", 780, 84, "heuristico",
                  direccion="Av. 6 de Diciembre y Whymper, La Floresta, Quito")

PROSA_REAL = (
    "Encontré un departamento registrado en La Floresta, pero no entra en tu tope de $700: "
    "se pasa por $80.\n"
    "Caminabilidad 84 (calculada sobre los comercios reales de la zona) — tienes lo cotidiano "
    "a pocos pasos: consultorio odontológico a ~3 min, Colegio Adventista a ~4 min, "
    "Supermaxi a ~8 min.\n"
    "La contra honesta: el precio publicado está $80 por encima de tu tope."
)


def _codigos(reply, cards, prefs=_PREFS):
    return [v["codigo"] for v in verificar_prosa(reply, cards, prefs)]


def test_el_caso_real_de_produccion_se_denuncia():
    """EL TEST QUE JUSTIFICA EL HOTFIX. Antes de este cambio, este turno salía PASSED."""
    hallazgos = verificar_prosa(PROSA_REAL, [CARD_REAL], _PREFS)
    culpables = [h for h in hallazgos if h["codigo"] == CODIGO]

    assert culpables, (
        "la contradicción observada en producción no se detecta: "
        f"solo salió {[h['codigo'] for h in hallazgos]}"
    )
    assert culpables[0]["gravedad"] == ALTA
    assert "comercios reales" in culpables[0]["evidencia"]


def test_el_turno_real_solo_mentia_en_la_procedencia():
    """El resto de la respuesta era HONESTO, y eso importa para calibrar.

    Sobre el precio la prosa dijo la verdad —«no entra en tu tope de $700: se pasa por
    $80»— y por eso los chequeos de presupuesto callan, correctamente. La única afirmación
    falsa del turno era la procedencia de la caminabilidad. Si este chequeo arrastrara
    consigo denuncias de presupuesto, estaría midiendo mal.
    """
    codigos = _codigos(PROSA_REAL, [CARD_REAL])
    assert codigos == [CODIGO], f"se esperaba exactamente una violación, salieron: {codigos}"


# ── Los ocho casos mínimos ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("fuente", ["heuristico", None, "", "  "])
@pytest.mark.parametrize("frase", [
    "Caminabilidad 84 (calculada sobre los comercios reales de la zona).",
    "Caminabilidad 84, contada sobre los comercios reales del sector.",
    "La caminabilidad de 84 sale de OpenStreetMap.",
    "Walk score 84 según OpenStreetMap.",
])
def test_1y2_estimado_afirmado_como_medido_es_alta(fuente, frase):
    """Casos 1 y 2: fuente heurística o ausente + afirmación de medición."""
    card = _card("a", 380, 84, fuente)
    hallazgos = [h for h in verificar_prosa(frase, [card], _PREFS) if h["codigo"] == CODIGO]
    assert hallazgos, f"no detectado con fuente={fuente!r}: {frase}"
    assert hallazgos[0]["gravedad"] == ALTA


@pytest.mark.parametrize("fuente", ["heuristico", None, ""])
@pytest.mark.parametrize("frase", [
    "Caminabilidad 84, estimación por zona (heurístico), todavía sin contrastar con los "
    "comercios reales del sector.",
    "Caminabilidad 84 — estimación por zona.",
    "La caminabilidad (84) es una estimación por zona, no una medición.",
])
def test_3_el_heuristico_honesto_no_dispara(frase, fuente):
    """Caso 3. LA FRASE HONESTA MENCIONA 'comercios reales' PARA NEGARLOS — un chequeo que
    solo buscara esas dos palabras acusaría justo a la respuesta correcta.

    Se parametriza también con fuente ausente porque el chequeo trata `None` y `""` igual
    que `heuristico`: no medido. Si la honestidad solo estuviera protegida para una de las
    tres, el guardián acusaría a la respuesta correcta en las otras dos.
    """
    card = _card("a", 380, 84, fuente)
    assert CODIGO not in _codigos(frase, [card])


# ── EL FALSO POSITIVO MÁS CARO: acusar a quien dijo la verdad ──────────────────────


@pytest.mark.parametrize("fuente", ["heuristico", None, ""])
@pytest.mark.parametrize("frase", [
    "La caminabilidad 84 no fue calculada sobre los comercios reales de la zona.",
    "La caminabilidad 84 no proviene de OpenStreetMap.",
    "La caminabilidad 84 no usa OpenStreetMap.",
    "La caminabilidad 84 nunca se midió sobre comercios reales.",
    "La caminabilidad 84 tampoco sale de OpenStreetMap.",
    "Ese 84 no se calculó sobre los comercios reales del sector.",
])
def test_una_negacion_verdadera_jamas_se_denuncia(frase, fuente):
    """Estas frases dicen EXACTAMENTE LA VERDAD sobre un score estimado.

    Denunciarlas sería el peor error posible de este chequeo: enseñaría al equipo a ignorar
    al guardián, y con él se perdería el caso real que motivó el hotfix. La negación
    gramatical se evalúa solo ANTES del verbo de procedencia, para que
    «calculada sobre los comercios reales, no sobre una estimación» siga siendo denunciable.
    """
    card = _card("a", 380, 84, fuente)
    assert CODIGO not in _codigos(frase, [card]), f"acusó a una negación verdadera: {frase}"


@pytest.mark.parametrize("frase", [
    "La caminabilidad es 84 y hay comercios reales alrededor.",
    "Caminabilidad 84. Alrededor hay comercios reales y un parque.",
    "Tiene caminabilidad 84; los comercios reales del sector abren hasta tarde.",
])
def test_la_mera_coexistencia_no_es_una_atribucion(frase):
    """Que "84" y "comercios reales" aparezcan en la misma frase no afirma que el uno salga
    de los otros. Hace falta un VERBO DE PROCEDENCIA que los relacione — esa es la diferencia
    entre detectar atribución y detectar mención."""
    card = _card("a", 380, 84, "heuristico")
    assert CODIGO not in _codigos(frase, [card])


def test_la_negacion_posterior_no_absuelve():
    """Contrapeso del test anterior: si la afirmación viene primero, es una afirmación.
    Sin esto, bastaría añadir un "no" al final de la frase para evadir al guardián."""
    card = _card("a", 380, 84, "heuristico")
    frase = ("Caminabilidad 84 calculada sobre los comercios reales de la zona, "
             "no sobre una estimación.")
    assert CODIGO in _codigos(frase, [card])


@pytest.mark.parametrize("frase", [
    "Caminabilidad 84 (calculada sobre los comercios reales de la zona).",
    "Caminabilidad 84, según OpenStreetMap.",
])
def test_4y5_con_fuente_osm_la_afirmacion_es_verdadera(frase):
    """Casos 4 y 5: si el dato SÍ se midió, decirlo no es una violación — es el diferenciador."""
    card = _card("a", 380, 84, "osm")
    assert CODIGO not in _codigos(frase, [card])


def test_6_varias_cards_solo_se_acusa_la_inequivoca():
    """Caso 6: dos tarjetas con fuentes distintas. Se identifica por walk score único."""
    cards = [_card("a", 380, 84, "osm"), _card("b", 420, 61, "heuristico")]
    frase = "El de caminabilidad 61 la tiene calculada sobre los comercios reales de la zona."
    hallazgos = [h for h in verificar_prosa(frase, cards, _PREFS) if h["codigo"] == CODIGO]
    assert len(hallazgos) == 1, f"esperaba una sola acusación, salieron {len(hallazgos)}"
    assert "61" in hallazgos[0]["evidencia"] or "61" in hallazgos[0]["detalle"]


def test_6b_la_card_honesta_del_mismo_turno_no_se_acusa():
    cards = [_card("a", 380, 84, "osm"), _card("b", 420, 61, "heuristico")]
    frase = "El de caminabilidad 84 se calculó sobre los comercios reales de la zona."
    assert CODIGO not in _codigos(frase, cards)


def test_7_asociacion_ambigua_no_acusa():
    """Caso 7. DOS tarjetas heurísticas con el MISMO walk score y sin dirección en la frase:
    no se puede saber de cuál habla. Callar es correcto; acusar sería adivinar."""
    cards = [_card("a", 380, 84, "heuristico"), _card("b", 420, 84, "osm")]
    frase = "Tiene buena caminabilidad, calculada sobre los comercios reales de la zona."
    assert CODIGO not in _codigos(frase, cards)


def test_7b_sin_numero_ni_direccion_con_varias_cards_no_acusa():
    cards = [_card("a", 380, 84, "heuristico"), _card("b", 420, 61, "heuristico")]
    frase = "La caminabilidad sale de OpenStreetMap."
    assert CODIGO not in _codigos(frase, cards)


def test_8_una_respuesta_que_no_habla_de_caminabilidad_sale_limpia():
    card = _card("a", 380, 84, "heuristico")
    frase = "Tiene 2 dormitorios y está dentro de tu tope de $700."
    assert CODIGO not in _codigos(frase, [card])


# ── Identificación: los tres caminos permitidos ────────────────────────────────────


def test_una_sola_card_en_el_panel_basta_para_identificar():
    """Con una sola opción no hay ambigüedad posible. Es el caso de producción."""
    card = _card("solo", 780, 84, "heuristico")
    assert CODIGO in _codigos("Su caminabilidad se midió sobre los comercios reales.", [card])


def test_la_direccion_identifica_aunque_el_numero_no_aparezca():
    cards = [_card("a", 380, 84, "heuristico", direccion="Av. 6 de Diciembre y Whymper"),
             _card("b", 420, 61, "osm", direccion="Calle Guipuzcoa y Toledo")]
    frase = "En Av. 6 de Diciembre y Whymper la caminabilidad viene de OpenStreetMap."
    hallazgos = [h for h in verificar_prosa(frase, cards, _PREFS) if h["codigo"] == CODIGO]
    assert len(hallazgos) == 1


def test_sin_tarjetas_no_se_inventa_un_juicio():
    """Sin panel no hay verdad autoritativa contra qué medir — mismo criterio que los otros
    cinco chequeos, que callan cuando `cards` viene vacío."""
    assert CODIGO not in _codigos("Caminabilidad calculada sobre los comercios reales.", [])


def test_un_hallazgo_por_tarjeta_aunque_la_mentira_se_repita():
    """EL CONTRATO, fijado explícitamente: la deduplicación es POR TARJETA, no por frase.

    Repetir la misma afirmación falsa sobre el mismo inmueble sigue siendo UNA violación —
    el mismo criterio con que `registrar` cuenta por turno y no por hit. Fijarlo ahora
    importa porque de esto va a depender el numerador cuando se mida la frecuencia
    (TRUST-OBS-01): si contara por frase, un turno verboso pesaría más que uno escueto con
    la misma mentira.
    """
    card = _card("solo", 780, 84, "heuristico")
    frase = ("Caminabilidad 84 calculada sobre los comercios reales de la zona. "
             "Ese 84 sale de OpenStreetMap.")
    hallazgos = [h for h in verificar_prosa(frase, [card], _PREFS) if h["codigo"] == CODIGO]
    assert len(hallazgos) == 1, f"la dedup es por tarjeta: salieron {len(hallazgos)}"
    assert hallazgos[0]["evidencia"]


def test_dos_tarjetas_mentidas_son_dos_hallazgos():
    """El contrapeso: la dedup es por tarjeta, así que dos inmuebles distintos con la misma
    mentira son dos violaciones. Si no, denunciar el segundo dependería del orden."""
    cards = [_card("a", 380, 84, "heuristico", direccion="Calle Uno"),
             _card("b", 420, 61, "heuristico", direccion="Calle Dos")]
    reply = ("En Calle Uno la caminabilidad 84 se calculó sobre los comercios reales.\n"
             "En Calle Dos la caminabilidad 61 sale de OpenStreetMap.")
    hallazgos = [h for h in verificar_prosa(reply, cards, _PREFS) if h["codigo"] == CODIGO]
    assert len(hallazgos) == 2


# ── La costura de E2.4 proyecta sola ───────────────────────────────────────────────


def test_el_nuevo_alta_llega_a_failed_sin_logica_especial():
    """PASO 2 del hotfix. `decision.verify` no conoce este código ni ningún otro: proyecta
    por GRAVEDAD. Si hiciera falta tocarlo, la costura de E2.4 estaría mal hecha."""
    from app.contracts.decision_v0 import VerificationStatus
    from app.decision.verify import auditar_explicacion

    explicacion, hallazgos = auditar_explicacion(PROSA_REAL, [CARD_REAL], _PREFS)
    assert any(h["codigo"] == CODIGO for h in hallazgos)
    assert explicacion.verification_status is VerificationStatus.FAILED


def test_decision_verify_no_menciona_el_codigo_nuevo():
    """La proyección es por gravedad, no por lista de códigos. Verificado por AST para que
    nadie 'ayude' añadiendo un caso especial más adelante."""
    import ast
    import inspect
    import pathlib

    from app.decision import verify

    fuente = pathlib.Path(inspect.getfile(verify)).read_text(encoding="utf-8")
    literales = {n.value for n in ast.walk(ast.parse(fuente))
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    assert not any(CODIGO in s for s in literales), (
        "decision.verify nombra el código: la proyección dejó de ser por gravedad"
    )
