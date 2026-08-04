"""
El verificador de prosa, probado con el texto REAL que falló en contexxto.com el 2026-07-31
(docs/BATALLA_Hiinmo_vs_Contexto_2026-07-31.md).

`test_batalla_hiinmo_fallos.py` cubre la mitad de ENTRADA: que el motor calcule bien y que el
bloque autoritativo se lo diga al modelo antes de escribir. Esto cubre la mitad de SALIDA: que
si el modelo igual desobedece, quede registrado en vez de llegar intacto a la persona.

Cada caso va en pareja — la prosa que MINTIÓ y la prosa HONESTA equivalente — porque un
guardián que también castiga la respuesta correcta se desactiva a la semana.
"""
from app.verificacion_prosa import resumen, verificar_prosa

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
