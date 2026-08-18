"""
El verificador de prosa, probado con el texto REAL que falló en contexxto.com el 2026-07-31
(docs/BATALLA_Hiinmo_vs_Contexto_2026-07-31.md).

`test_batalla_hiinmo_fallos.py` cubre la mitad de ENTRADA: que el motor calcule bien y que el
bloque autoritativo se lo diga al modelo antes de escribir. Esto cubre la mitad de SALIDA: que
si el modelo igual desobedece, quede registrado en vez de llegar intacto a la persona.

Cada caso va en pareja — la prosa que MINTIÓ y la prosa HONESTA equivalente — porque un
guardián que también castiga la respuesta correcta se desactiva a la semana.
"""
import logging

from app.verificacion_prosa import CONTADORES, registrar, resumen, verificar_prosa

_PREFS = {"operacion": "arriendo", "tipo_inmueble": "departamento", "presupuesto_max": 700}


def _card(cid, precio, encaje, direccion=None):
    return {
        "id": cid, "direccion": direccion or f"Calle {cid}", "tipo_activo": "Departamento",
        "operacion": "ARRIENDO", "precio": precio, "encaje": encaje,
        "caracteristicas": {"num_dormitorios": 2}, "lat": -0.18, "lon": -78.48,
    }


# El panel de la consulta A del informe: tres dentro del tope y el $710 que "casi entra".
_PANEL = [_card("d290", 290, 92), _card("d380", 380, 88),
          _card("d550", 550, 80), _card("d710", 710, 71)]
_DESCARTADAS = [_card("d990", 990, 40), _card("d1130", 1130, 37)]


def _codigos(reply, cards=None, prefs=_PREFS, descartadas=None):
    cards = _PANEL if cards is None else cards
    return [v["codigo"] for v in verificar_prosa(reply, cards, prefs, descartadas)]


# ══ FALLO 4a — el exceso ablandado ═════════════════════════════════════════════════════
def test_el_710_presentado_como_justo_en_tu_tope_se_denuncia():
    # La frase literal de la repro en vivo.
    assert "presupuesto_suavizado" in _codigos("El último, de $710, está justo en tu tope.")


def test_el_710_con_la_frase_obligatoria_no_dispara_nada():
    # Lo que el bloque autoritativo le exige decir. Debe pasar limpio.
    assert _codigos("El último, de $710, se pasa $10 de tu tope.") == []


def test_dos_afirmaciones_honestas_en_la_misma_linea_no_se_mezclan():
    """El falso positivo que mataría al guardián: una ventana ciega de N caracteres leería
    'dentro de tu presupuesto' pegado al $710 y gritaría. Se acota a la FRASE."""
    assert _codigos("Las tres primeras están dentro de tu presupuesto; "
                    "la de $710 se pasa $10 de tu tope.") == []


def test_el_visto_bueno_sobre_algo_que_se_pasa_se_denuncia():
    assert "presupuesto_suavizado" in _codigos("✅ $710 — la mejor ubicada del grupo.")


def test_dentro_de_tu_presupuesto_sobre_uno_que_si_entra_es_correcto():
    assert _codigos("El de $380 está dentro de tu presupuesto.") == []


# ══ FALLO 4b — el encabezado, que es lo que la persona lee primero ═════════════════════
def test_el_encabezado_que_mete_al_710_en_el_presupuesto_se_denuncia():
    v = verificar_prosa("Encontré 4 departamentos que encajan con tu presupuesto de $700.",
                        _PANEL, _PREFS)
    assert [x["codigo"] for x in v] == ["encabezado_falso"]
    assert "$710" in v[0]["detalle"]


def test_el_encabezado_que_distingue_dentro_y_fuera_pasa_limpio():
    # La redacción que el motor le entrega hecha en `_conteo_presupuesto`.
    assert _codigos("Son 4 opciones: 3 dentro de tu tope de $700 y 1 que se pasa.") == []


def test_sin_ninguna_excedida_el_colectivo_es_verdad():
    dentro = [_card("a", 290, 92), _card("b", 380, 88)]
    assert _codigos("Las 2 entran en tu tope de $700.", cards=dentro) == []


# ══ La cifra inventada ═════════════════════════════════════════════════════════════════
def test_un_precio_que_no_existe_en_el_turno_se_denuncia():
    v = verificar_prosa("También hay uno de $650 en la misma cuadra.", _PANEL, _PREFS)
    assert [x["codigo"] for x in v] == ["cifra_sin_procedencia"]


def test_las_restas_legitimas_no_son_invento():
    # El exceso ($710-$700), el margen ($700-$380) y la diferencia entre dos opciones
    # ($550-$380) son aritmética sobre datos del turno, no cifras nuevas.
    assert _codigos("La de $710 se pasa $10; con la de $380 te sobran $320, "
                    "y hay $170 entre esa y la de $550.") == []


def test_el_tope_declarado_no_se_denuncia_como_invento():
    assert _codigos("Tu tope es $700 al mes.") == []


# ══ FALLO 1 (al revés) — ofrecer lo que no está en pantalla ════════════════════════════
def test_la_descartada_como_item_numerado_se_denuncia():
    reply = ("Estas son tus opciones:\n"
             "1. Calle d290 — $290\n"
             "5. Calle d1130 — $1,130, un poco sobre tu tope.")
    assert "descartada_ofrecida" in _codigos(reply, descartadas=_DESCARTADAS)


def test_reconocerlas_en_una_frase_esta_permitido():
    # Exactamente lo que el bloque autoritativo autoriza: sin ficha, sin viñeta.
    assert _codigos("Hay 2 más en la zona, pero se pasan bastante de tu tope; no te las pongo.",
                    descartadas=_DESCARTADAS) == []


# ══ FALLO 1 — la prosa contradice el orden del panel ═══════════════════════════════════
def test_la_lista_invertida_se_denuncia():
    reply = ("Te los ordeno por encaje:\n"
             "1. Calle d710\n2. Calle d550\n3. Calle d380\n4. Calle d290")
    v = verificar_prosa(reply, _PANEL, _PREFS)
    assert [x["codigo"] for x in v] == ["orden_alterado"]
    assert v[0]["gravedad"] == "media"


def test_la_lista_en_el_orden_del_panel_pasa_limpio():
    reply = ("Te los ordeno por encaje:\n"
             "1. Calle d290\n2. Calle d380\n3. Calle d550\n4. Calle d710")
    assert _codigos(reply) == []


def test_destacar_una_en_prosa_no_es_reordenar():
    # "Destacar «la más barata» en una frase aparte: SÍ" — regla del bloque.
    assert _codigos("La de Calle d290 es la más barata de las cuatro.") == []


# ══ El GANCHO — la frase de cierre (graph.py regla 3: "1–3 opciones para seguir") ══════════
def test_el_gancho_con_veredicto_de_zona_se_denuncia():
    reply = ("Esta zona tiene mucha vida de barrio. ¿Quieres que te cuente por qué esta es "
             "la zona ideal para tu familia?")
    assert "gancho_steering" in _codigos(reply, cards=[])


def test_el_steering_en_el_cuerpo_no_se_atribuye_al_gancho():
    # Aísla el hallazgo a la frase de CIERRE: el veredicto vive en la primera oración; el
    # gancho (la última, con "?") es limpio y no debe cazarse por asociación de turno.
    reply = ("Esta es la zona ideal para tu familia. ¿Quieres que te muestre el encaje con "
             "lo que buscas?")
    assert "gancho_steering" not in _codigos(reply, cards=[])


def test_el_gancho_steering_se_caza_sin_tarjetas_tambien():
    # La razón de tocar el contrato de verificar_prosa: un turno 'explorando'/'identificado'
    # (intencion.py) no tiene panel todavía, pero el gancho puede violar Fair Housing igual.
    reply = "¿Quieres que te cuente por qué esta es la zona ideal para tu familia?"
    v = verificar_prosa(reply, [], {}, None)
    assert [x["codigo"] for x in v] == ["gancho_steering"]


def test_el_gancho_con_metafora_de_vendedor_se_denuncia():
    reply = ("El sector tiene buena conectividad. ¿Quieres que te cuente por qué el Metro "
             "es tu as bajo la manga aquí?")
    v = verificar_prosa(reply, [], {}, None)
    assert [x["codigo"] for x in v] == ["gancho_hype"]
    assert v[0]["gravedad"] == "media"


def test_el_gancho_sobrio_sin_metafora_pasa_limpio():
    reply = ("Tienes el Metro de Quito a ~8 min a pie — buena conexión al norte. ¿Quieres "
             "que te muestre el encaje con tu presupuesto?")
    assert verificar_prosa(reply, [], {}, None) == []


def test_el_gancho_que_ofrece_una_descartada_se_denuncia():
    reply = ("Estas cuatro encajan bien con lo que buscas. ¿Quieres que también te muestre "
             "la de Calle d1130, aunque se pasa de tu tope?")
    assert "gancho_descartada" in _codigos(reply, descartadas=_DESCARTADAS)


def test_mencionar_que_hay_descartadas_sin_nombrarlas_en_el_gancho_pasa():
    reply = ("Estas cuatro encajan bien. Hay 2 más que se pasan bastante de tu tope, no te "
             "las pongo. ¿Prefieres que ajuste el radio o mantenemos el tope?")
    assert _codigos(reply, descartadas=_DESCARTADAS) == []


def test_sin_signo_de_pregunta_no_hay_gancho_detectable():
    # Límite conocido y aceptado (ver docstring de `_gancho_texto`): el prompt también cierra
    # sin '?' ("...o dime qué barrio buscas."), forma que esta heurística angosta no ve.
    reply = "El Metro es tu as bajo la manga en esta zona. Cuéntame qué buscas y seguimos."
    assert verificar_prosa(reply, [], {}, None) == []


def test_el_gancho_convive_con_los_otros_chequeos_sobre_el_mismo_panel():
    reply = ("El de $710 está justo en tu tope. ¿Quieres que también te muestre la de "
             "Calle d1130, aunque se pasa de tu tope?")
    codigos = set(_codigos(reply, descartadas=_DESCARTADAS))
    assert {"presupuesto_suavizado", "gancho_descartada"} <= codigos


# ══ Observabilidad — CONTADORES + registrar (espejo de crm_guardrails.registrar_guardrail) ══
def test_registrar_cuenta_el_turno_y_el_gancho_detectado():
    antes = dict(CONTADORES)
    registrar([], "¿Quieres que te muestre el encaje con tu presupuesto?")
    assert CONTADORES["turnos"] == antes["turnos"] + 1
    assert CONTADORES["gancho_detectado"] == antes["gancho_detectado"] + 1


def test_registrar_cuenta_el_turno_sin_contar_gancho_si_no_hay_signo_de_pregunta():
    antes = dict(CONTADORES)
    registrar([], "Son 4 opciones dentro de tu tope.")
    assert CONTADORES["turnos"] == antes["turnos"] + 1
    assert CONTADORES["gancho_detectado"] == antes["gancho_detectado"]  # sin '?', no cuenta


def test_registrar_cuenta_una_vez_por_codigo_no_una_vez_por_hit():
    # Dos montos inventados en el mismo turno son DOS hits del mismo código; el contador
    # mide en cuántos TURNOS aparece la violación, no cuántas veces se repite en uno solo
    # (mismo criterio que crm_guardrails.registrar_guardrail).
    reply = "También hay uno de $650 y otro de $890 en la misma cuadra."
    v = verificar_prosa(reply, _PANEL, _PREFS)
    assert len(v) == 2 and {x["codigo"] for x in v} == {"cifra_sin_procedencia"}
    antes = dict(CONTADORES)
    registrar(v, reply)
    assert CONTADORES["cifra_sin_procedencia"] == antes["cifra_sin_procedencia"] + 1


def test_registrar_loguea_una_linea_por_codigo(caplog):
    reply = "¿Quieres que te cuente por qué esta es la zona ideal para tu familia?"
    v = verificar_prosa(reply, [], {}, None)
    with caplog.at_level(logging.WARNING, logger="prosa"):
        registrar(v, reply, session="s1")
    linea = next(r for r in caplog.records if r.name == "prosa")
    assert "gancho_steering" in linea.getMessage() and "s1" in linea.getMessage()


def test_registrar_no_loguea_nada_en_un_turno_limpio(caplog):
    with caplog.at_level(logging.WARNING, logger="prosa"):
        registrar([], "Son 4 opciones dentro de tu tope.")
    assert [r for r in caplog.records if r.name == "prosa"] == []


# ══ Contratos del módulo ═══════════════════════════════════════════════════════════════
def test_sin_tarjetas_no_hay_nada_que_verificar():
    # Una pregunta de zona no tiene panel: no hay verdad autoritativa contra qué medir y el
    # verificador no debe inventar juicios.
    assert verificar_prosa("La Floresta es un barrio con mucha vida de café.", []) == []
    assert verificar_prosa("", _PANEL, _PREFS) == []


def test_sin_tope_declarado_no_se_juzga_el_presupuesto():
    assert _codigos("El de $710 está justo en tu tope.", prefs={}) == []


def test_las_altas_van_primero_y_el_resumen_es_una_linea():
    reply = ("Encontré 4 departamentos que encajan con tu presupuesto de $700:\n"
             "1. Calle d710\n2. Calle d550\n3. Calle d380\n4. Calle d290")
    v = verificar_prosa(reply, _PANEL, _PREFS)
    assert [x["gravedad"] for x in v] == sorted(x["gravedad"] for x in v)
    assert v[0]["gravedad"] == "alta"
    linea = resumen(v)
    assert "encabezado_falso" in linea and "\n" not in linea
    assert resumen([]) == ""


def test_la_prosa_ejemplar_del_turno_completo_pasa_limpio():
    """El turno bien escrito, con todo lo que el bloque autoritativo pide: conteo distinguido,
    orden del panel, el exceso nombrado con su frase. Si esto fallara, el guardián sería ruido."""
    reply = (
        "Son 4 opciones: 3 dentro de tu tope de $700 y 1 que se pasa.\n"
        "1. Calle d290 — $290. La más barata del grupo.\n"
        "2. Calle d380 — $380, dentro de tu presupuesto.\n"
        "3. Calle d550 — $550.\n"
        "4. Calle d710 — se pasa $10 de tu tope.\n"
        "Hay 2 más en la zona, pero se pasan bastante; no te las pongo."
    )
    assert verificar_prosa(reply, _PANEL, _PREFS, _DESCARTADAS) == []
