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
```
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
