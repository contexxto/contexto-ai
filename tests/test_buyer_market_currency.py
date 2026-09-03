"""G16 · la guarda acredita la moneda con el contexto de mercado del despliegue.

EL FALLO QUE ESTO CIERRA lo produjo un turno REAL en producción (canary G14, 2026-08-29):

```
"Busco arriendo en La Floresta, con un presupuesto máximo de 900 dólares."
        ↓
modelo → SetBudgetMax(900, USD)          5/5 corridas, correcto
        ↓
guarda → _MONEDA_ISO[USD] = \\busd\\b     no encuentra "usd" en "900 dolares"
        ↓
AMBIGUOUS → budget_max = null  +  unresolved "¿…y en qué moneda?"
```

La guarda hacía lo que se le pidió: su docstring congelaba que `dolares` no acredita porque
*"hay ocho dólares en el mundo"*. Cierto en abstracto y **equivocado en la plaza donde el
producto opera**: Ecuador está oficialmente dolarizado y en Quito "900 dólares" no es
ambiguo. El coste de la regla abstracta era convertir la forma más común de decir un
presupuesto en una pregunta pendiente falsa.

## Lo que NO se hace aquí

No se amplía la confianza en el modelo. La disciplina se conserva entera:

```
el modelo PROPONE          →   SetBudgetMax(900, USD)
la guarda ACREDITA         →   ¿hay denominación monetaria en la cláusula?
                               ¿el mercado del despliegue declara esa moneda?
```

El contexto **confirma** una interpretación; nunca la origina. Por eso `"900"` a secas sigue
sin acreditar aunque el mercado sea USD, y `"900 euros"` no se convierte en dólares: sin
denominación en el texto no hay nada que confirmar. Y `$` sigue fuera —el símbolo es
genuinamente ambiguo y no fue el fallo observado—.

`BUYER_MARKET_CURRENCY` vacío deja el comportamiento anterior intacto: fail-closed.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from app.buyer import extractor as E
from app.buyer.boundary import BuyerCurrencyV0, SetBudgetMax, SetObjective
from app.buyer.extractor import TraduccionNoAutorizada, autorizar_traduccion
from app.buyer.interprete import Disposicion, PropuestaV0, interpretar
from app.buyer.mensaje import IdentifiedUserMessage
from app.buyer.reductor import reducir
from app.contracts.buyer_v0 import BuyerContextV0, Objective

CANARY = ("Busco arriendo en La Floresta, "
          "con un presupuesto máximo de 900 dólares.")
MSG_ID = "51ce2b89-d221-40a2-8f33-442ac980726c"
T0 = dt.datetime(2026, 8, 29, 12, 48, tzinfo=dt.timezone.utc)
USD = BuyerCurrencyV0.USD


@pytest.fixture
def mercado(monkeypatch):
    """Fija `BUYER_MARKET_CURRENCY` como lo haría el entorno del despliegue."""
    def _fijar(valor):
        monkeypatch.setattr(E.settings, "buyer_market_currency", valor, raising=False)
    return _fijar


def _propuestas_del_modelo():
    """Lo que el modelo propuso DE VERDAD en el canary, verificado 5/5 en G15."""
    return [
        PropuestaV0(disposicion=Disposicion.DURABLE, motivo="declara arriendo",
                    mutacion=SetObjective(objective=Objective.RENT)),
        PropuestaV0(disposicion=Disposicion.DURABLE, motivo="declara tope",
                    mutacion=SetBudgetMax(amount=Decimal(900), currency=USD)),
    ]


def _contexto(texto, propuestas):
    msg = IdentifiedUserMessage(message_id=MSG_ID, text=texto)
    lote = interpretar(msg, propuestas)
    base = BuyerContextV0(buyer_id="00000000-0000-4000-8000-000000000000", updated_at=T0)
    return reducir(base, lote, T0)


# ══ 1 · el turno de producción, entero ══════════════════════════════════════════════


def test_el_turno_REAL_del_canary_persiste_el_presupuesto(mercado):
    """Reproduce el fallo de producción exacto y exige el desenlace correcto.

    Si esto vuelve a ponerse rojo, la memoria del comprador volvió a perder un presupuesto
    que la persona dijo con todas sus letras.
    """
    mercado("USD")

    ctx = _contexto(CANARY, _propuestas_del_modelo())

    assert ctx.objective is Objective.RENT
    assert ctx.financial.budget_max is not None, "se perdió el presupuesto declarado"
    assert ctx.financial.budget_max.amount == Decimal(900)
    assert ctx.financial.budget_max.currency == "USD"

    campos = {q.about_field for q in ctx.unresolved_questions}
    assert "financial.budget_max" not in campos, \
        "se repregunta un dato que el usuario ya declaró"


def test_la_procedencia_del_presupuesto_apunta_al_mensaje_real(mercado):
    """La evidencia tiene que citar el `HumanMessage.id` del turno, no otro identificador:
    es lo que hace auditable de dónde salió el número."""
    mercado("USD")

    ctx = _contexto(CANARY, _propuestas_del_modelo())

    # El nombre contractual es la ruta completa, la misma que usa `about_field` en las
    # preguntas pendientes. Usar el corto pasaría inadvertido: daría cero evidencias y
    # parecería un fallo del reducer.
    ev = [e for e in ctx.field_evidence if e.field == "financial.budget_max"]
    assert len(ev) == 1, \
        f"evidencia de financial.budget_max: {[e.field for e in ctx.field_evidence]}"
    assert ev[0].evidence.source_id == MSG_ID


# ══ 2 · la matriz de acreditación ═══════════════════════════════════════════════════


@pytest.mark.parametrize("texto,config,acredita", [
    # El código ISO literal no depende del mercado: es evidencia por sí solo.
    ("Máximo USD 900.",                       "",    True),
    ("Máximo USD 900.",                       "MXN", True),
    # La denominación en habla natural SÍ depende del mercado.
    ("Mi presupuesto máximo es 900 dólares.", "USD", True),
    ("Mi presupuesto máximo es 900 dolares.", "USD", True),   # sin tilde
    ("Mi presupuesto máximo es 900 dólares.", "",    False),  # sin mercado declarado
    ("Mi presupuesto máximo es 900 dólares.", "MXN", False),  # mercado distinto
    # El símbolo queda fuera de esta unidad, a propósito.
    ("Hasta $900 al mes.",                    "USD", False),
])
def test_matriz_de_acreditacion_del_presupuesto(texto, config, acredita, mercado):
    mercado(config)
    mutacion = SetBudgetMax(amount=Decimal(900), currency=USD)

    if acredita:
        autorizar_traduccion(mutacion, texto)      # no levanta
    else:
        with pytest.raises(TraduccionNoAutorizada):
            autorizar_traduccion(mutacion, texto)


# ══ 3 · el mercado CONFIRMA, nunca ORIGINA ══════════════════════════════════════════


def test_un_numero_SIN_denominacion_no_se_acredita_por_el_mercado(mercado):
    """`"presupuesto máximo 900"` con mercado USD sigue sin autorizar.

    Es la propiedad que separa "confirmar una interpretación" de "fabricar moneda": si
    bastara el mercado, la configuración estaría escribiendo un dato que el usuario no dijo,
    y el `BuyerContext` afirmaría una moneda sin evidencia.
    """
    mercado("USD")

    with pytest.raises(TraduccionNoAutorizada):
        autorizar_traduccion(
            SetBudgetMax(amount=Decimal(900), currency=USD),
            "Mi presupuesto máximo es 900.")


def test_una_denominacion_AJENA_no_se_convierte_a_la_del_mercado(mercado):
    """`"900 euros"` con mercado USD no autoriza. El mercado no traduce ni convierte: si la
    persona nombró otra moneda, lo que hay es un desacuerdo, no una confirmación."""
    mercado("USD")

    with pytest.raises(TraduccionNoAutorizada):
        autorizar_traduccion(
            SetBudgetMax(amount=Decimal(900), currency=USD),
            "Mi presupuesto máximo es 900 euros.")


def test_el_mercado_no_acredita_una_moneda_DISTINTA_de_la_propuesta(mercado):
    """Mercado USD + texto en dólares no puede acreditar una mutación en MXN. La
    correspondencia es entre las tres: propuesta, texto y mercado."""
    mercado("USD")

    with pytest.raises(TraduccionNoAutorizada):
        autorizar_traduccion(
            SetBudgetMax(amount=Decimal(900), currency=BuyerCurrencyV0.MXN),
            "Mi presupuesto máximo es 900 dólares.")


def test_la_denominacion_y_el_numero_siguen_exigiendose_en_la_MISMA_clausula(mercado):
    """La frontera de Fair Housing de `_numero_junto_a_su_dimension` no se afloja: el
    mercado añade una forma de nombrar la moneda, no permiso para juntar evidencia suelta
    de cláusulas distintas."""
    mercado("USD")

    with pytest.raises(TraduccionNoAutorizada):
        autorizar_traduccion(
            SetBudgetMax(amount=Decimal(900), currency=USD),
            "Tengo 900 amigos, y mi presupuesto está en dólares.")


def test_una_clausula_NEGADA_no_acredita_aunque_el_mercado_calce(mercado):
    """`"no"` sigue costando la evidencia: `_afirmativas` filtra antes que nada."""
    mercado("USD")

    with pytest.raises(TraduccionNoAutorizada):
        autorizar_traduccion(
            SetBudgetMax(amount=Decimal(900), currency=USD),
            "No quiero gastar 900 dólares.")


# ══ 4 · el default es la decisión ═══════════════════════════════════════════════════


def test_el_mercado_viene_VACIO_de_fabrica():
    """Sin declararlo, el comportamiento es el anterior a G16: fail-closed. Habilitar la
    acreditación por mercado es un acto por entorno, no algo que llegue con un deploy."""
    from app.config import Settings

    assert Settings().buyer_market_currency == ""


@pytest.mark.parametrize("crudo,esperado", [
    ("USD", "USD"),
    ("usd", "USD"),      # sin sensibilidad accidental a mayúsculas
    ("  usd  ", "USD"),
    ("", ""),
])
def test_la_configuracion_normaliza_lo_que_escribe_una_persona(crudo, esperado, monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("BUYER_MARKET_CURRENCY", crudo)
    assert Settings().buyer_market_currency == esperado


@pytest.mark.parametrize("invalido", ["dolares", "US", "USDD", "12A"])
def test_una_configuracion_MALFORMADA_falla_en_el_arranque(invalido, monkeypatch):
    """Falla ruidosamente en vez de degradar en silencio. Con Render observando el health
    check, un despliegue que no arranca deja servir a la versión anterior — el mismo criterio
    que `exigir_esquema`. Un valor mal escrito que simplemente 'no acreditara' sería
    indistinguible de un canary que no funciona."""
    from app.config import Settings

    monkeypatch.setenv("BUYER_MARKET_CURRENCY", invalido)
    with pytest.raises(Exception):
        Settings()
