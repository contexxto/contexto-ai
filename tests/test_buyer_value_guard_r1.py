"""F3-E3.2-VALUE-GUARD-R1 · cada número ligado a SU dimensión y a SU operador.

La guarda de valor de E3.2 pedía la dimensión y el número en la misma cláusula, y por eso podía
elegir CUALQUIER número presente: los hijos como dormitorios, las personas como metros, un
piso como un tope. Ahora el número tiene que estar LIGADO a su operador y a su ancla.

```
A  los casos obligatorios de la adjudicación
B  floor ≠ ceiling
C  sin ancla local, no liga
D  contexto protegido: nunca evidencia, en ninguna dirección
E  varios candidatos → fail closed → AMBIGUOUS
F  de punta a punta: interpretar + reducir, con un proponente hostil
G  lo que SÍ tiene que seguir acreditando
H  una cláusula negada no liga
I  R1b · lo que encontró la revisión adversarial: el contexto de la ligadura
J  R1c · lo que encontró la segunda ronda: tasas, sujetos, líneas, tiempo, colas
```

La sección I tiene UNA prueba aislante por defensa: cada una la caza sólo esa defensa, y el
arnés de mutación (`arneses/mutaciones_value_guard_r1.py`) comprueba que al quitarla se pone
roja.
"""

from __future__ import annotations

import datetime as dt
import itertools
from decimal import Decimal

import pytest

from app.buyer.boundary import (
    BuyerCurrencyV0, BuyerFieldV0, Disposicion, SetAreaM2Min, SetBedroomsMin, SetBudgetMax,
)
from app.buyer.extractor import AfirmacionAmbiguous, TraduccionNoAutorizada, autorizar_traduccion
from app.buyer.interprete import PropuestaV0, interpretar
from app.buyer.mensaje import IdentifiedUserMessage
from app.buyer.reductor import reducir
from app.contracts.buyer_v0 import BuyerContextV0

USD = BuyerCurrencyV0.USD
F = BuyerFieldV0
T0 = dt.datetime(2026, 9, 24, 12, 0, tzinfo=dt.timezone.utc)


def _bed(n):
    return SetBedroomsMin(bedrooms_min=n)


def _area(n):
    return SetAreaM2Min(area_m2_min=float(n))


def _bud(n):
    return SetBudgetMax(amount=Decimal(n), currency=USD)


def _ok(mutacion, texto):
    try:
        autorizar_traduccion(mutacion, texto)
        return True
    except TraduccionNoAutorizada:
        return False


# ══ A · los casos obligatorios ══════════════════════════════════════════════════════


def test_A1_dos_dormitorios_para_tres_hijos_liga_el_2_y_jamas_el_3():
    texto = "al menos 2 dormitorios para mis 3 hijos"
    assert _ok(_bed(2), texto)
    assert not _ok(_bed(3), texto)


def test_A2_ochenta_m2_para_cuatro_personas_liga_el_80_y_jamas_el_4():
    texto = "mínimo 80 m2 para 4 personas"
    assert _ok(_area(80), texto)
    assert not _ok(_area(4), texto)


def test_A3_hasta_900_USD_acredita_el_tope():
    assert _ok(_bud(900), "hasta 900 USD")


def test_A4_presupuesto_desde_900_USD_NO_acredita_un_tope():
    assert not _ok(_bud(900), "presupuesto desde 900 USD")


def test_A5_cada_numero_queda_ligado_a_su_dimension():
    texto = "2 dormitorios y máximo 900 USD"
    assert _ok(_bud(900), texto)
    assert not _ok(_bud(2), texto)
    assert not _ok(_bed(2), texto), "«2 dormitorios» es exacto, no un mínimo"
    assert not _ok(_bed(900), texto)


def test_A6_los_perros_no_contaminan_los_dormitorios():
    texto = "tengo 2 perros y quiero mínimo 3 dormitorios"
    assert _ok(_bed(3), texto)
    assert not _ok(_bed(2), texto)


@pytest.mark.parametrize("texto", [
    "máximo 900 USD con al menos 2 dormitorios",
    "con al menos 2 dormitorios hasta 900 USD",
    "mínimo 80 m2 y al menos 3 dormitorios con tope de 1200 USD",
])
def test_A7_en_UNA_cláusula_los_números_no_se_intercambian(texto):
    """Sin separador entre las dimensiones: la ligadura es lo único que las distingue."""
    numeros = [2, 3, 80, 900, 1200]
    for n in numeros:
        assert _ok(_bed(n), texto) is (f"{n} dormitorios" in texto and n in (2, 3)), n
    assert not any(_ok(_bud(n), texto) for n in numeros if f"{n} USD" not in texto)
    assert not any(_ok(_area(n), texto) for n in numeros if f"{n} m2" not in texto)


# ══ B · floor ≠ ceiling ═════════════════════════════════════════════════════════════


@pytest.mark.parametrize("texto", [
    "presupuesto desde 900 USD",
    "a partir de 900 USD",
    "mínimo 900 USD",
    "al menos 900 USD",
    "más de 900 USD",
    "presupuesto mínimo de 900 USD",
])
def test_B_un_piso_nunca_es_un_tope(texto):
    assert not _ok(_bud(900), texto)


@pytest.mark.parametrize("texto", [
    "máximo 900 USD", "hasta 900 USD", "no más de 900 USD", "tope de 900 USD",
    "mi presupuesto es de 900 USD", "presupuesto de 900 USD", "presupuesto máximo 900 USD",
    "900 USD como máximo", "900 USD máximo", "máximo USD 900", "900 USD de presupuesto",
])
def test_B_las_formas_de_tope_SI_acreditan(texto):
    assert _ok(_bud(900), texto)


# ══ C · sin ancla local, no liga ════════════════════════════════════════════════════


@pytest.mark.parametrize("mutacion, texto", [
    (_area(4), "mínimo 4 personas en 80 m2"),
    (_bed(3), "mínimo 3 para los dormitorios"),
    (_bed(3), "al menos 3, dormitorios"),
    (_area(80), "mínimo 80, en m2"),
    (_bud(900), "máximo 900 y en USD"),
    (_bud(900), "máximo 900"),
])
def test_C_un_numero_sin_su_ancla_pegada_no_liga(mutacion, texto):
    assert not _ok(mutacion, texto)


def test_C_un_decimal_ambiguo_no_liga():
    """«120.5» puede ser decimal o miles según la plaza: no se elige."""
    assert not _ok(_bud(120), "máximo 120.5 USD")
    assert not _ok(_bud(5), "máximo 120.5 USD")


# ══ D · contexto protegido ══════════════════════════════════════════════════════════


@pytest.mark.parametrize("texto, n", [
    ("tenemos 3 hijos", 3), ("somos 4 personas", 4), ("vivimos 5 en la familia", 5),
    ("3 hijos o más", 3), ("4 personas como mínimo", 4), ("al menos 3 niños", 3),
    ("mínimo 2 adultos y 3 niños", 3), ("mi familia de 4", 4),
])
def test_D_un_conteo_de_personas_no_es_ni_dormitorios_ni_metros(texto, n):
    assert not _ok(_bed(n), texto)
    assert not _ok(_area(n), texto)


def test_D_el_contexto_protegido_tampoco_RESUELVE_el_numero_correcto():
    """La guarda no usa «hijos» para descartar el 3: lo descarta porque no está ligado. Sin el
    sustantivo protegido, el resultado es el mismo."""
    for protegido, neutro in (("para mis 3 hijos", "para mis 3 bicicletas"),
                              ("para 4 personas", "para 4 cajas")):
        for mutacion in (_bed(2), _bed(3), _area(80), _area(4)):
            a = _ok(mutacion, f"al menos 2 dormitorios y mínimo 80 m2 {protegido}")
            b = _ok(mutacion, f"al menos 2 dormitorios y mínimo 80 m2 {neutro}")
            assert a == b, (mutacion, protegido)


# ══ E · varios candidatos → fail closed ═════════════════════════════════════════════


@pytest.mark.parametrize("mutacion, texto", [
    (_bed(2), "al menos 2 dormitorios o al menos 3 dormitorios"),
    (_bed(3), "al menos 2 dormitorios o al menos 3 dormitorios"),
    (_area(80), "mínimo 80 m2 o mínimo 100 m2"),
    (_bud(900), "máximo 900 USD o máximo 1000 USD"),
])
def test_E_dos_numeros_ligados_a_la_misma_dimension_no_se_desempatan(mutacion, texto):
    assert not _ok(mutacion, texto)


def test_E_el_fail_closed_llega_como_AMBIGUOUS_con_su_dimension():
    lote = interpretar(IdentifiedUserMessage(message_id="m", text="mínimo 80 m2 o mínimo 100 m2"),
                       [PropuestaV0(disposicion=Disposicion.DURABLE, mutacion=_area(80),
                                    motivo="x")])
    assert lote.mutaciones == ()
    assert [(type(a), a.campo) for a in lote.afirmaciones] == [
        (AfirmacionAmbiguous, F.AREA_M2_MIN)]


# ══ F · de punta a punta, proponente hostil ═════════════════════════════════════════


@pytest.mark.parametrize("texto, dimension, legitimo, contaminante, crear", [
    ("al menos 2 dormitorios para mis 3 hijos", F.BEDROOMS_MIN, 2, 3, _bed),
    ("Realmente busco al menos 2 dormitorios para mis 3 hijos", F.BEDROOMS_MIN, 2, 3, _bed),
    ("mínimo 80 m2 para 4 personas", F.AREA_M2_MIN, 80, 4, _area),
    ("tengo 2 perros y quiero mínimo 3 dormitorios", F.BEDROOMS_MIN, 3, 2, _bed),
])
def test_F_ningun_orden_de_propuestas_hostiles_escribe_el_numero_contaminante(
        texto, dimension, legitimo, contaminante, crear):
    """El proponente propone el valor legítimo Y el contaminante, en los dos órdenes, con y sin
    marca de autocorrección. Nunca queda el contaminante; como mucho, el legítimo o nada."""
    lectura = {F.BEDROOMS_MIN: lambda c: c.property_requirements.bedrooms_min,
               F.AREA_M2_MIN: lambda c: c.property_requirements.area_m2_min}[dimension]
    for orden in itertools.permutations([crear(legitimo), crear(contaminante)]):
        propuestas = [PropuestaV0(disposicion=Disposicion.DURABLE, mutacion=m, motivo="x")
                      for m in orden]
        lote = interpretar(IdentifiedUserMessage(message_id="m", text=texto), propuestas)
        c = reducir(BuyerContextV0(buyer_id="b", updated_at=T0), lote, T0)
        assert lectura(c) in (None, legitimo), (texto, orden, lectura(c))
        assert lectura(c) != contaminante
        assert "household" not in c.model_dump() and "children" not in c.model_dump_json()


# ══ G · lo que SÍ sigue acreditando ═════════════════════════════════════════════════


@pytest.mark.parametrize("mutacion, texto", [
    (_bed(3), "al menos 3 dormitorios"), (_bed(3), "mínimo de 3 dormitorios"),
    (_bed(3), "3 dormitorios o más"), (_bed(3), "3 dormitorios como mínimo"),
    (_bed(2), "desde 2 recámaras"), (_bed(2), "necesito como mínimo 2 habitaciones"),
    (_area(80), "al menos 80 metros cuadrados"), (_area(80), "mínimo 80m2"),
    (_area(80), "80 m2 o más"),
    (_bud(120000), "mi presupuesto máximo es 120000 USD"),
    (_bud(120000), "máximo 120.000 USD"), (_bud(1200000), "tope de 1,200,000 USD"),
])
def test_G_las_formas_naturales_siguen_acreditando(mutacion, texto):
    assert _ok(mutacion, texto)



@pytest.mark.parametrize("mutacion, texto", [
    (_bed(3), "no necesito al menos 3 dormitorios"),
    (_area(80), "ya no quiero mínimo 80 m2"),
    (_bud(900), "no tengo un tope de 900 USD"),
])
def test_H_una_clausula_negada_no_liga(mutacion, texto):
    assert not _ok(mutacion, texto)


# ══ I · R1b · el contexto de la ligadura ════════════════════════════════════════════
#
# La revisión adversarial de R1 (26 agentes, 0 refutados) mostró que ligar el número a su
# operador y su ancla no bastaba: lo que rodea a la ligadura podía contradecirla. Cada bloque
# es una familia; cada caso, una frase real de los atacantes.


@pytest.mark.parametrize("texto", [
    "presupuesto de 900 USD o más", "mi presupuesto es de 900 USD como mínimo",
    "presupuesto de 900 USD en adelante", "perdón, mi presupuesto es de 900 USD para arriba",
    "900 USD de presupuesto como mínimo", "presupuesto de 900 USD como piso",
    "budget 900 USD or more", "900 USD mensuales como mínimo", "mi presupuesto es 900 USD o más",
])
def test_I1_un_piso_POSPUESTO_nunca_es_un_tope(texto):
    assert not _ok(_bud(900), texto)


@pytest.mark.parametrize("texto", [
    "mínimo presupuesto de 900 USD", "más de 900 USD de presupuesto",
    "al menos 900 USD de presupuesto", "a partir de un presupuesto de 900 USD",
    "busco desde un presupuesto de 900 USD", "minimum budget 900 USD",
])
def test_I2_un_piso_ANTEPUESTO_a_la_forma_de_tope_tampoco(texto):
    assert not _ok(_bud(900), texto)


@pytest.mark.parametrize("mutacion, texto", [
    (_bud(700), "presupuesto de 700 USD a 1200"), (_bud(500), "presupuesto de 500 USD - 900"),
    (_bud(700), "tengo un presupuesto de 700 USD a 1200 USD"),
])
def test_I3_un_extremo_de_rango_no_es_un_tope(mutacion, texto):
    assert not _ok(mutacion, texto)


@pytest.mark.parametrize("mutacion, texto", [
    (_bed(3), "2 o 3 dormitorios o más"), (_bed(2), "2 o 3 dormitorios o más"),
    (_bed(3), "de 2 a 3 dormitorios o más"), (_bed(3), "2 o 3 recámaras en adelante"),
    (_area(80), "70 u 80 m2 o más"),
])
def test_I3b_una_opcion_de_una_disyuncion_de_pisos_no_es_el_minimo(mutacion, texto):
    """La guarda antigua acreditaba los dos extremos; la de R1, sólo el EQUIVOCADO."""
    assert not _ok(mutacion, texto)


@pytest.mark.parametrize("mutacion, texto", [
    (_bud(900), "hasta 900 USD a 10 minutos del centro"),
    (_bed(2), "con al menos 2 dormitorios hasta 900 USD"),
    (_bud(900), "desde 700 hasta 900 USD"),
])
def test_I3c_un_rango_se_forma_con_la_MISMA_dimension(mutacion, texto):
    assert _ok(mutacion, texto)


@pytest.mark.parametrize("mutacion, texto", [
    (_bed(2), "necesito al menos 2 cuartos de baño"), (_bed(1), "mínimo 1 cuarto de servicio"),
    (_bed(1), "al menos 1 habitación de servicio"), (_bed(3), "al menos 3 cuartos de hora del trabajo"),
    (_bed(2), "mínimo 2 habitaciones de hotel cerca"),
    (_bed(2), "mínimo 2 cuartos de baño con al menos 3 dormitorios"),
])
def test_I4_otra_pieza_no_ancla_dormitorios(mutacion, texto):
    assert not _ok(mutacion, texto)


def test_I4b_el_TAMANO_de_los_dormitorios_si_ancla_y_no_es_area():
    texto = "al menos 3 dormitorios de al menos 12 m2"
    assert _ok(_bed(3), texto)
    assert not _ok(_area(12), texto)
    assert _ok(_bed(3), "mínimo 2 cuartos de baño con al menos 3 dormitorios")


@pytest.mark.parametrize("mutacion, texto", [
    (_bud(900), "hasta 900 USD el m2"), (_bud(1200), "busco comprar a no más de 1200 USD el m2"),
    (_bud(50), "hasta 50 USD la noche"),
])
def test_I5_un_precio_por_unidad_no_es_el_del_inmueble(mutacion, texto):
    assert not _ok(mutacion, texto)


@pytest.mark.parametrize("mutacion, texto", [
    (_bed(1), "mínimo 1 dormitorio por hijo"), (_bed(1), "al menos 1 habitación para cada niño"),
    (_area(20), "mínimo 20 m2 por persona"), (_area(12), "mínimo 12 m2 cada uno"),
])
def test_I6_una_tasa_no_es_el_requisito_minimo(mutacion, texto):
    assert not _ok(mutacion, texto)


@pytest.mark.parametrize("texto", ["máximo 300 USD por persona", "máximo 300 USD cada uno"])
def test_I6b_una_tasa_no_es_el_tope(texto):
    assert not _ok(_bud(300), texto)


def test_I6c_la_tasa_se_reconoce_por_la_FORMA_no_por_el_sustantivo():
    """Fair Housing: la guarda no mira QUÉ se reparte. Lo protegido y lo neutro dan lo mismo."""
    for x in ("hijo", "niño", "persona", "bicicleta", "caja"):
        assert not _ok(_bed(1), f"mínimo 1 dormitorio por {x}"), x


@pytest.mark.parametrize("mutacion, texto", [
    (_bed(3), "al menos 3 dormitorios por favor"), (_bud(900), "hasta 900 USD por mes"),
    (_bud(120000), "hasta 120000 USD por una casa"), (_bud(900), "máximo 900 USD por la zona norte"),
])
def test_I6d_un_por_que_no_reparte_si_liga(mutacion, texto):
    assert _ok(mutacion, texto)


@pytest.mark.parametrize("mutacion, texto", [
    (_bud(50), "el parqueadero cuesta hasta 50 USD"), (_area(50), "un jardín de al menos 50 m2"),
    (_area(20), "terraza de mínimo 20 m2"), (_area(200), "lote de al menos 200 m2"),
    (_area(12), "habitaciones de al menos 12 m2"),
])
def test_I7_con_otro_SUJETO_la_ligadura_habla_de_el(mutacion, texto):
    assert not _ok(mutacion, texto)


@pytest.mark.parametrize("mutacion, texto", [
    (_bud(50), "parqueadero máximo 50 USD"), (_bud(80), "la alícuota máximo 80 USD"),
    (_area(20), "terraza mínimo 20 m2"), (_area(80), "casa con jardín mínimo 80 m2"),
])
def test_I7b_un_objeto_ajeno_pegado_al_operador_tampoco(mutacion, texto):
    """En un área, ni como amenidad: «casa con jardín mínimo 80 m2» puede ser el jardín."""
    assert not _ok(mutacion, texto)


@pytest.mark.parametrize("mutacion, texto", [
    (_area(120), "casa de al menos 120 m2"), (_area(60), "busco alquilar algo de mínimo 60 m2"),
    (_bud(900), "busco algo que cueste máximo 900 USD"), (_bud(900), "un depa de máximo 900 USD"),
    (_bud(900), "depa con parqueadero hasta 900 USD"), (_bud(900), "barrio seguro hasta 900 USD"),
])
def test_I7c_cuando_el_sujeto_es_el_inmueble_si_liga(mutacion, texto):
    assert _ok(mutacion, texto)


@pytest.mark.parametrize("mutacion, texto", [
    (_bud(900), "hasta 900 USD de parqueadero"), (_bud(100), "máximo 100 USD de alícuota"),
    (_bud(20000), "tengo hasta 20000 USD de entrada"), (_area(80), "mínimo 80 m2 de jardín"),
    (_area(15), "mínimo 15 m2 de terraza"),
])
def test_I8_de_OTRA_cosa_detras_del_numero_no_liga(mutacion, texto):
    assert not _ok(mutacion, texto)


@pytest.mark.parametrize("mutacion, texto", [
    (_area(80), "mínimo 80 m2 de construcción"), (_bud(900), "hasta 900 USD de presupuesto"),
])
def test_I8b_de_lo_mismo_si(mutacion, texto):
    assert _ok(mutacion, texto)


@pytest.mark.parametrize("mutacion, texto", [
    (_bud(80), "hasta 80 USD para la alícuota"), (_bud(1500), "gano hasta 1500 USD mensuales"),
    (_bud(5000), "presupuesto de 5000 USD para remodelar"),
])
def test_I9_un_costo_o_un_ingreso_en_la_clausula_no_deja_elegir(mutacion, texto):
    assert not _ok(mutacion, texto)


@pytest.mark.parametrize("mutacion, texto", [
    (_bud(900), "máximo 900 USD o 1000 USD"), (_bed(2), "al menos 2 dormitorios o 3 dormitorios"),
    (_area(80), "mínimo 80 m2 o 100 m2"), (_area(80), "mínimo 80 m2 con 100 m2 de jardín"),
])
def test_I10_dos_CANDIDATOS_con_la_misma_ancla_fallan_cerrado(mutacion, texto):
    """Aunque sólo uno lleve el operador: no se elige entre dos números de la misma unidad."""
    assert not _ok(mutacion, texto)


@pytest.mark.parametrize("mutacion, texto", [
    (_bed(2), "al menos 2 dormitorios, o al menos 3 dormitorios"),
    (_bed(3), "al menos 2 dormitorios, o al menos 3 dormitorios"),
    (_bud(1000), "máximo 900 USD, o máximo 1000 USD"),
])
def test_I10b_una_coma_no_parte_una_disyuncion(mutacion, texto):
    assert not _ok(mutacion, texto)


def test_I11_con_mercado_USD_otro_dolar_no_es_USD(monkeypatch):
    from app.buyer import extractor as E
    monkeypatch.setattr(E.settings, "buyer_market_currency", "USD", raising=False)
    assert _ok(_bud(900), "hasta 900 dólares")
    assert not _ok(_bud(900), "hasta 900 dólares canadienses")
    assert not _ok(_bud(900), "máximo 900 dólares australianos")


@pytest.mark.parametrize("mutacion, texto", [
    (_bed(3), "no más de 3 dormitorios o más"), (_bed(3), "al menos 3 dormitorios como máximo"),
])
def test_I12_un_techo_pegado_a_un_minimo_lo_invalida(mutacion, texto):
    assert not _ok(mutacion, texto)


def test_I13_un_marcador_pospuesto_que_abre_OTRO_valor_no_califica_al_primero():
    texto = "máximo 900 USD al menos 2 dormitorios"
    assert _ok(_bud(900), texto)
    assert _ok(_bed(2), texto)
    assert not _ok(_bed(2), "2 dormitorios mínimo 2 baños")
    assert not _ok(_bed(3), "dormitorios mínimo 3 baños")


@pytest.mark.parametrize("mutacion, texto", [
    (_bud(900), "mi presupuesto son 900 USD"), (_bud(900), "mi tope son 900 USD"),
    (_bud(900), "900 USD es mi tope"), (_bud(900), "900 USD es mi máximo"),
    (_bud(900), "máximo puedo pagar 900 USD"), (_bud(900), "lo máximo que puedo pagar son 900 USD"),
    (_bud(900), "mi presupuesto llega a 900 USD"), (_bud(900), "mi presupuesto está en 900 USD"),
    (_bud(900), "tengo como máximo unos 900 USD"), (_bud(900), "hasta unos 900 USD"),
    (_bud(900), "máximo $900 USD"), (_bud(900), "USD 900 máximo"), (_bud(900), "900 USD como tope"),
    (_bud(900), "900 USD al mes máximo"), (_bud(900), "mi límite es 900 USD"),
    (_bed(3), "como mínimo necesito 3 dormitorios"), (_bed(3), "por lo menos 3 dormitorios"),
    (_bed(3), "3 o más dormitorios"), (_bed(3), "3 dormitorios al menos"),
    (_bed(3), "mínimo unos 3 dormitorios"), (_bed(3), "Dormitorios mínimo 3"),
    (_bed(3), "Zona Cumbayá, recámaras mínimo 3, presupuesto máx 900 USD"),
    (_bed(3), "de 3 dormitorios para arriba"), (_area(80), "mínimo unos 80 m2"),
    (_area(80), "área mínima de 80 m2"), (_area(80), "m2 mínimo 80"), (_area(80), "mínimo 80 m²"),
])
def test_I14_las_formas_naturales_que_R1_perdia_vuelven_a_acreditar(mutacion, texto):
    assert _ok(mutacion, texto)


def _rigidez_estricta(campo):
    from app.buyer.boundary import RigidezV0
    from app.buyer.interprete import PropuestaRigidezV0
    return PropuestaRigidezV0(campo=campo, rigidez=RigidezV0.ESTRICTA, motivo="x")


@pytest.mark.parametrize("texto, dimension, propuestas, prohibido", [
    ("perdón, mi presupuesto es de 900 USD para arriba", F.BUDGET_MAX, [_bud(900)], 900),
    ("Mi presupuesto es de 900 USD en adelante. El presupuesto es innegociable", F.BUDGET_MAX,
     [_bud(900)], 900),
    ("Busco depa en Cumbayá, alícuota máximo 100 USD", F.BUDGET_MAX, [_bud(100)], 100),
    ("mínimo 2 cuartos de baño con al menos 3 dormitorios", F.BEDROOMS_MIN, [_bed(3), _bed(2)], 2),
    ("Tengo 3 hijos, necesito mínimo 1 dormitorio por hijo", F.BEDROOMS_MIN,
     [_bed(1), _bed(3)], 1),
    ("busco algo con mínimo 20 m2 de jardín", F.AREA_M2_MIN, [_area(20)], 20),
])
def test_I15_de_punta_a_punta_ni_el_valor_ni_su_rigidez_llegan(texto, dimension, propuestas,
                                                              prohibido):
    """Proponente hostil, en los dos órdenes y con la rigidez ESTRICTA al lado: el número
    contaminante no se escribe, y por tanto tampoco puede endurecerse."""
    lectura = {F.BUDGET_MAX: lambda c: c.financial.budget_max and c.financial.budget_max.amount,
               F.BEDROOMS_MIN: lambda c: c.property_requirements.bedrooms_min,
               F.AREA_M2_MIN: lambda c: c.property_requirements.area_m2_min}[dimension]
    for orden in itertools.permutations(propuestas):
        lote = interpretar(
            IdentifiedUserMessage(message_id="m", text=texto),
            [PropuestaV0(disposicion=Disposicion.DURABLE, mutacion=m, motivo="x") for m in orden]
            + [_rigidez_estricta(dimension)])
        c = reducir(BuyerContextV0(buyer_id="b", updated_at=T0), lote, T0)
        assert lectura(c) != prohibido, (texto, orden)
        assert all(k.value != prohibido for k in c.hard_constraints), (texto, orden)


# ══ J · R1c · la segunda ronda adversarial ══════════════════════════════════════════
#
# Sobre R1b: la tasa escrita ANTES del valor, el objeto ajeno separado del operador por un
# adjetivo o un relativo, las fichas de WhatsApp (líneas, números seguidos sin puntuación), los
# marcadores que hablan del valor anterior o del tiempo, y colas frecuentes que R1b rechazaba.


@pytest.mark.parametrize("texto", ["por persona máximo 300 USD", "por cabeza hasta 300 USD",
                                   "Somos 3 amigos. Por persona máximo 300 USD"])
def test_J1_una_tasa_ANTEPUESTA_no_es_el_tope(texto):
    assert not _ok(_bud(300), texto)


@pytest.mark.parametrize("texto", [
    "Somos 3 amigos, cada uno puede pagar hasta 300 USD", "cada quien paga hasta 300 USD",
    "hasta 300 USD a cada uno", "hasta 300 USD entre cada uno", "hasta 300 USD per cápita",
])
def test_J1b_un_reparto_en_la_clausula_no_deja_ligar(texto):
    assert not _ok(_bud(300), texto)


def test_J1c_una_tasa_al_FINAL_de_la_clausula_tampoco():
    assert not _ok(_bud(300), "300 USD es lo máximo que puedo pagar por persona")


@pytest.mark.parametrize("mutacion, texto", [
    (_bud(300), "Por persona, máximo 300 USD"), (_bed(1), "Por hijo, al menos 1 dormitorio"),
])
def test_J1d_un_ENCABEZADO_distributivo_anula_el_mensaje(mutacion, texto):
    assert not _ok(mutacion, texto)


def test_J1e_el_encabezado_se_reconoce_por_la_FORMA_no_por_el_sustantivo():
    for x in ("hijo", "niño", "persona", "pareja", "bicicleta", "caja"):
        assert not _ok(_bed(1), f"Por {x}, al menos 1 dormitorio"), x
    assert _ok(_bud(900), "Por favor, máximo 900 USD")


@pytest.mark.parametrize("mutacion, texto", [
    (_bud(50), "hasta 50 USD diarios"), (_bud(400), "hasta 400 USD semanales"),
    (_bud(400), "hasta 400 USD a la semana"), (_bud(120), "máximo USD 120 mil"),
    (_bud(120), "hasta USD 120k"),
])
def test_J1f_otra_periodicidad_u_otra_escala_no_es_el_tope(mutacion, texto):
    assert not _ok(mutacion, texto)


@pytest.mark.parametrize("texto", ["el m2 hasta 1200 USD", "el metro cuadrado máximo 1200 USD",
                                   "precio por m2 hasta 1200 USD"])
def test_J1g_un_precio_por_metro_ANTEPUESTO_tampoco(texto):
    assert not _ok(_bud(1200), texto)


@pytest.mark.parametrize("mutacion, texto", [
    (_bud(50), "parqueadero adicional hasta 50 USD"), (_bud(80), "gastos comunes hasta 80 USD"),
    (_bud(80), "que la administración cobre máximo 80 USD"),
    (_area(12), "la recámara principal mínimo 12 m2"),
    (_area(12), "3 dormitorios mínimo, que cada habitación tenga al menos 12 m2"),
    (_area(50), "casa con jardín que mida mínimo 50 m2"),
    (_area(200), "un terreno que tenga mínimo 200 m2"), (_area(12), "habitaciones con al menos 12 m2"),
])
def test_J2_un_objeto_ajeno_no_se_esconde_tras_un_adjetivo_o_un_relativo(mutacion, texto):
    assert not _ok(mutacion, texto)


def test_J2b_un_verbo_de_precio_le_asigna_el_precio_a_su_sujeto():
    assert not _ok(_bud(300), "el colegio cuesta hasta 300 USD")
    assert _ok(_bud(900), "busco algo que cueste máximo 900 USD")


@pytest.mark.parametrize("mutacion, texto", [
    (_bed(3), "que sea de mínimo 3 dormitorios"), (_bed(3), "tiene que ser de al menos 3 dormitorios"),
    (_bed(3), "busco una casa grande de mínimo 3 dormitorios"),
    (_bed(3), "depa con balcón de mínimo 3 dormitorios"), (_area(80), "que el depa sea de al menos 80 m2"),
    (_area(80), "busco departamento en Quito de mínimo 80 m2"),
    (_bud(900), "mi presupuesto es de máximo 900 USD"), (_bud(900), "que el arriendo sea de máximo 900 USD"),
    (_bud(900), "busco un depto en Cumbayá de hasta 900 USD"), (_bud(900), "busco arriendos de hasta 900 USD"),
    (_bud(900), "busco un depa amueblado de hasta 900 USD"),
    (_bud(900), "depa con parqueadero techado hasta 900 USD"),
])
def test_J2c_una_copula_un_adjetivo_o_un_lugar_con_de_no_son_otro_sujeto(mutacion, texto):
    assert _ok(mutacion, texto)


def test_J3_el_numero_de_OTRA_dimension_tras_la_moneda_no_es_candidato():
    texto = "busco depa en cumbaya hasta 900 USD 2 dormitorios minimo"
    assert _ok(_bud(900), texto)
    assert _ok(_bed(2), texto)
    assert _ok(_bud(900), "hasta 900 USD 2 dormitorios")
    assert not _ok(_bed(2), "hasta 900 USD 2 dormitorios"), "exacto, no un mínimo"
    assert not _ok(_bud(900), "máximo 900 USD o USD 1000")


@pytest.mark.parametrize("mutacion, texto", [
    (_bud(900), "Máximo 900 USD\nAlícuota hasta 100 USD"),
    (_bud(900), "Busco depa en Cumbayá\n3 dormitorios mínimo\nHasta 900 USD"),
    (_bed(3), "Busco depa en Cumbayá\n3 dormitorios mínimo\nHasta 900 USD"),
    (_bed(3), "Presupuesto 900 USD máximo\n3 dormitorios mínimo"),
])
def test_J4_un_salto_de_linea_separa_como_en_una_ficha(mutacion, texto):
    assert _ok(mutacion, texto)
    assert not _ok(_bud(100), "Máximo 900 USD\nAlícuota hasta 100 USD")


@pytest.mark.parametrize("mutacion, texto", [
    (_bud(900), "3 dormitorios mínimo hasta 900 USD"), (_bed(3), "3 dormitorios mínimo hasta 900 USD"),
    (_bud(900), "2 dormitorios mínimo máximo 900 USD"),
])
def test_J4b_el_marcador_pospuesto_del_valor_ANTERIOR_no_invierte_el_siguiente(mutacion, texto):
    assert _ok(mutacion, texto)
    assert not _ok(_bud(900), "mínimo presupuesto de 900 USD")
    assert not _ok(_bud(900), "presupuesto de 900 USD mínimo")


@pytest.mark.parametrize("mutacion, texto", [
    (_bud(900), "hasta 900 USD desde octubre"), (_bud(900), "hasta 900 USD a partir de noviembre"),
    (_bud(900), "máximo 900 USD al menos por un año"), (_bud(900), "hasta 900 USD desde el lunes"),
    (_bed(3), "mínimo 3 dormitorios hasta diciembre"),
])
def test_J4c_un_marcador_que_habla_de_TIEMPO_no_invierte_el_valor(mutacion, texto):
    assert _ok(mutacion, texto)
    assert not _ok(_bud(900), "hasta 900 USD como mínimo")


def test_J4d_el_numero_pegado_a_su_unidad_no_abre_una_alternativa():
    assert _ok(_bed(3), "Cumbayá - 80 m2 - 3 dormitorios mínimo")


@pytest.mark.parametrize("mutacion, texto", [
    (_bud(900), "hasta 900 USD de preferencia"), (_bud(900), "hasta 900 USD de ser posible"),
    (_bud(900), "hasta 900 USD de arrendamiento"), (_bed(3), "al menos 3 dormitorios de preferencia"),
    (_bed(3), "mínimo 3 dormitorios de buen tamaño"), (_area(80), "mínimo 80 m2 de espacio"),
    (_bed(3), "mínimo 3 dormitorios por fa"), (_bud(900), "hasta 900 USD por el momento"),
    (_bed(3), "mínimo 3 dormitorios cada uno con baño"),
    (_bed(3), "3 recámaras o más cada una con clóset"),
])
def test_J5_las_colas_frecuentes_no_rompen_la_ligadura(mutacion, texto):
    assert _ok(mutacion, texto)


@pytest.mark.parametrize("texto", [
    "hasta 900 USD alícuota incluida", "máximo 900 USD más alícuota",
    "hasta 900 USD con mantenimiento",
])
def test_J5b_un_costo_AÑADIDO_al_tope_no_lo_anula(texto):
    assert _ok(_bud(900), texto)


def test_J5c_un_costo_como_DESTINO_del_numero_si():
    assert not _ok(_bud(80), "hasta 80 USD para la alícuota")
    assert not _ok(_bud(1500), "gano hasta 1500 USD mensuales")
    assert _ok(_bud(120000), "hasta 120000 USD en cuotas")


@pytest.mark.parametrize("texto, dimension, propuestas, prohibido", [
    ("Somos 3 amigos, cada uno puede pagar hasta 300 USD", F.BUDGET_MAX,
     [_bud(300), _bud(900)], 300),
    ("Por persona, máximo 300 USD", F.BUDGET_MAX, [_bud(300), _bud(900)], 300),
    ("3 dormitorios mínimo, que cada habitación tenga al menos 12 m2", F.AREA_M2_MIN,
     [_area(12)], 12),
    ("parqueadero adicional hasta 50 USD", F.BUDGET_MAX, [_bud(50)], 50),
])
def test_J6_de_punta_a_punta_ni_la_tasa_ni_el_objeto_ajeno_se_escriben(texto, dimension,
                                                                       propuestas, prohibido):
    lectura = {F.BUDGET_MAX: lambda c: c.financial.budget_max and c.financial.budget_max.amount,
               F.AREA_M2_MIN: lambda c: c.property_requirements.area_m2_min}[dimension]
    for orden in itertools.permutations(propuestas):
        lote = interpretar(
            IdentifiedUserMessage(message_id="m", text=texto),
            [PropuestaV0(disposicion=Disposicion.DURABLE, mutacion=m, motivo="x") for m in orden]
            + [_rigidez_estricta(dimension)])
        c = reducir(BuyerContextV0(buyer_id="b", updated_at=T0), lote, T0)
        assert lectura(c) != prohibido, (texto, orden)
        assert lectura(c) is None or lectura(c) != 900, "la tasa multiplicada tampoco"
