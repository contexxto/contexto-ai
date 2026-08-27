"""E3.2b.0 · la frontera de estado del Buyer, atacada.

El criterio de esta suite **no es que los tests estén verdes**. Es:

> ¿el sistema de tipos hace imposible construir lo que declaramos inválido?

Por eso la mayoría de los tests no comprueban que algo "se rechace" sino que **no se pueda
expresar**. Un saneador que descarta `household.children` puede olvidarse de un caso; una
unión donde ese campo no existe, no.

Pura y offline: sin Postgres, sin LLM, sin store.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from app.buyer import boundary as B
from app.contracts.buyer_v0 import Objective

USD = B.BuyerCurrencyV0.USD


def _mutaciones_validas():
    return [
        B.SetObjective(objective=Objective.BUY),
        B.ClearObjective(),
        B.SetBudgetMax(amount=Decimal("900"), currency=USD),
        B.ClearBudgetMax(),
        B.SetBedroomsMin(bedrooms_min=2),
        B.ClearBedroomsMin(),
        B.SetAreaM2Min(area_m2_min=50.0),
        B.ClearAreaM2Min(),
        B.SetPetsRequired(),
        B.ClearPetsRequired(),
    ]


# ── A · lo que no se puede EXPRESAR ────────────────────────────────────────────────


PROTEGIDOS = [
    "household", "children", "familial_status", "race", "ethnicity", "national_origin",
    "religion", "sex", "gender_identity", "sexual_orientation", "disability",
]
DIFERIDOS = [
    "stage", "tradeoffs", "hard_constraints", "soft_preferences", "place_preferences",
    "accessibility_requirements", "mobility", "commute_anchors", "unresolved_questions",
]


@pytest.mark.parametrize("nombre", PROTEGIDOS + DIFERIDOS)
def test_ningun_path_prohibido_es_representable(nombre):
    """No hay clase de mutación que lo nombre, ni campo donde ponerlo.

    Se mira el conjunto de campos declarados de TODAS las variantes: si un atributo
    protegido pudiera escribirse, tendría que existir un campo capaz de recibirlo.
    """
    for clase in B._RUTA_CONTRACTUAL:
        assert nombre not in clase.model_fields, f"{clase.__name__} expone {nombre}"
        assert nombre not in clase.__name__.lower()


@pytest.mark.parametrize("nombre", PROTEGIDOS + DIFERIDOS)
def test_ningun_path_prohibido_llega_a_una_ruta_contractual(nombre):
    """El mapeo de rutas es cerrado: las cinco de V0 y ninguna más."""
    for ruta in B._RUTA_CONTRACTUAL.values():
        assert nombre not in ruta


def test_las_rutas_contractuales_son_exactamente_las_cinco_de_V0():
    assert set(B._RUTA_CONTRACTUAL.values()) == {
        "objective",
        "financial.budget_max",
        "property_requirements.bedrooms_min",
        "property_requirements.area_m2_min",
        "property_requirements.pets_allowed_required",
    }


def test_una_mutacion_ajena_a_la_union_se_rechaza():
    """`autorizar` no acepta cualquier objeto que se le parezca."""
    class Impostora(BaseModel):
        path: str = "household.children"

    r = B.autorizar(Impostora())
    assert r.disposicion is B.Disposicion.REJECTED
    assert r.mutacion is None and r.persiste is False



def test_la_UNION_y_el_MAPEO_DE_RUTAS_no_pueden_divergir():
    """HUECO ENCONTRADO POR LA MUTACIÓN M1.

    Añadir una variante a la unión sin añadirla al mapeo no rompía ningún test. En el
    comportamiento actual sería inocuo —`autorizar` rechaza lo que no está en el mapeo— pero
    deja dos listas que describen lo mismo y pueden separarse. La siguiente persona que
    añada una mutación legítima solo tocaría una de las dos, y el fallo aparecería como un
    `REJECTED` inexplicable en vez de como un test rojo.

    Se exige que sean el MISMO conjunto, en las dos direcciones.
    """
    import typing

    args = typing.get_args(B.BuyerMutationV0)
    en_union = set(typing.get_args(args[0]))
    en_mapeo = set(B._RUTA_CONTRACTUAL)

    assert en_union == en_mapeo, (
        f"solo en la unión: {[c.__name__ for c in en_union - en_mapeo]} · "
        f"solo en el mapeo: {[c.__name__ for c in en_mapeo - en_union]}"
    )
    assert len(en_union) == 10, f"la unión V0 tiene 10 variantes, no {len(en_union)}"


def test_ninguna_variante_de_la_union_expone_un_path_como_dato():
    """La ruta se DERIVA de la clase. Si una variante trajera `path` o `field`, el candidato
    podría elegir dónde escribe — que es la superficie que la unión existe para cerrar."""
    import typing

    for clase in typing.get_args(typing.get_args(B.BuyerMutationV0)[0]):
        assert not ({"path", "field", "value"} & set(clase.model_fields)),             f"{clase.__name__} deja elegir destino o valor genérico"

# ── B · dominios ───────────────────────────────────────────────────────────────────


def test_objective_UNKNOWN_no_es_un_SET():
    """`UNKNOWN` es la ausencia de declaración, no algo que se declare. Afirmarlo sería
    distinto de no saberlo, y para lo segundo ya está `ClearObjective`."""
    with pytest.raises(ValidationError):
        B.SetObjective(objective=Objective.UNKNOWN)


@pytest.mark.parametrize("valor", ["comprar", "BUY", None, 1, True])
def test_objective_solo_acepta_el_enum(valor):
    with pytest.raises(ValidationError):
        B.SetObjective(objective=valor)


@pytest.mark.parametrize("moneda", ["EUR", "ZZZ", "usd", "US", "DOLAR", "", None, 1])
def test_la_moneda_fuera_de_USD_MXN_se_rechaza(moneda):
    """`Money.currency` valida `^[A-Z]{3}$`: forma, no dominio. `ZZZ` y `EUR` pasan ese
    patrón. El updater exige el enum cerrado."""
    with pytest.raises(ValidationError):
        B.SetBudgetMax(amount=Decimal("1"), currency=moneda)


@pytest.mark.parametrize("monto", [Decimal("0"), Decimal("-1"), True, "900", None])
def test_un_presupuesto_no_positivo_o_mal_tipado_se_rechaza(monto):
    with pytest.raises(ValidationError):
        B.SetBudgetMax(amount=monto, currency=USD)


@pytest.mark.parametrize("n", [0, -1, True, False, 2.5, "2", None])
def test_los_dormitorios_exigen_entero_estricto_mayor_que_cero(n):
    """`bool` es subclase de `int`: sin `StrictInt`, `True` entraría como un dormitorio.
    Y `ge=1` porque "cero como mínimo" no restringe nada — es ruido, no requisito."""
    with pytest.raises(ValidationError):
        B.SetBedroomsMin(bedrooms_min=n)


@pytest.mark.parametrize("a", [0.0, -1.0, True, False, float("nan"), float("inf"),
                               float("-inf"), "50", None])
def test_el_area_exige_float_finito_positivo(a):
    """`allow_inf_nan=False` vive en el campo, no en un validador aparte: así la garantía
    aparece en el schema y no se puede retirar sin que se note."""
    with pytest.raises(ValidationError):
        B.SetAreaM2Min(area_m2_min=a)


def test_un_area_entera_SI_se_acepta_y_bool_no():
    """Matiz verificado, no supuesto: en modo estricto Pydantic admite `int` para `float`
    —50 es un float exacto, no hay pérdida— pero **excluye `bool`**, que en Python es
    subclase de `int`. Es justo la línea que queremos: un entero es un área legítima; un
    booleano es un candidato mal formado."""
    assert B.SetAreaM2Min(area_m2_min=50).area_m2_min == 50.0
    with pytest.raises(ValidationError):
        B.SetAreaM2Min(area_m2_min=True)


# ── C · la regla estructural ───────────────────────────────────────────────────────


SIN_PAYLOAD = [
    B.SetPetsRequired, B.ClearPetsRequired, B.ClearObjective,
    B.ClearBudgetMax, B.ClearBedroomsMin, B.ClearAreaM2Min,
]


@pytest.mark.parametrize("clase", SIN_PAYLOAD)
def test_las_operaciones_sin_payload_no_exponen_value(clase):
    """META-TEST de la regla congelada.

    *Una mutación cerrada no debe aceptar parámetros que puedan representar estados
    inválidos para esa operación.* Si una de estas clases adquiere un `value`, la forma
    volvió a abrirse — y este test es lo que lo detecta.

    `SetPetsRequired` es el caso que da nombre a la regla: con `value: bool` podría
    construirse con `False`, que no es "ya no lo necesito" sino un requisito distinto que V0
    no modela, y habría que validarlo DESPUÉS de construirla.
    """
    campos = set(clase.model_fields) - {"tipo"}
    assert campos == set(), f"{clase.__name__} expone payload: {campos}"


@pytest.mark.parametrize("clase", SIN_PAYLOAD)
@pytest.mark.parametrize("payload", [{"value": True}, {"value": False}, {"value": 1},
                                     {"objective": Objective.BUY}])
def test_pasarle_un_valor_a_una_operacion_sin_payload_falla(clase, payload):
    with pytest.raises(ValidationError):
        clase(**payload)


@pytest.mark.parametrize("clase", list(B._RUTA_CONTRACTUAL))
def test_todas_las_variantes_son_cerradas_e_inmutables(clase):
    """`extra='forbid'` es lo que impide colar un campo nuevo; `frozen` impide reescribir
    la mutación después de autorizarla."""
    assert clase.model_config.get("extra") == "forbid"
    assert clase.model_config.get("frozen") is True


@pytest.mark.parametrize("mutacion", _mutaciones_validas())
def test_una_mutacion_autorizada_no_se_puede_modificar_despues(mutacion):
    with pytest.raises(ValidationError):
        mutacion.tipo = "otro"


# ── D · disposición: solo DURABLE muta ─────────────────────────────────────────────


def test_DURABLE_exige_mutacion():
    with pytest.raises(ValidationError):
        B.ResultadoFrontera(disposicion=B.Disposicion.DURABLE)


@pytest.mark.parametrize("disposicion", [B.Disposicion.TURN_ONLY, B.Disposicion.AMBIGUOUS,
                                         B.Disposicion.REJECTED])
def test_lo_que_no_es_DURABLE_no_puede_llevar_mutacion(disposicion):
    """NO MATCH → NO PERSIST, garantizado al construir.

    Si dependiera de que el llamante lo respete, la garantía viviría en la disciplina de
    quien escriba E3.2b.1 en vez de en el tipo.
    """
    with pytest.raises(ValidationError):
        B.ResultadoFrontera(disposicion=disposicion, mutacion=B.SetPetsRequired())


@pytest.mark.parametrize("disposicion", [B.Disposicion.TURN_ONLY, B.Disposicion.AMBIGUOUS,
                                         B.Disposicion.REJECTED])
def test_los_tres_desenlaces_sin_escritura_son_construibles(disposicion):
    """TURN_ONLY y AMBIGUOUS **no son errores**: son decisiones de no persistencia."""
    r = B.no_persistir(disposicion, "motivo")
    assert r.mutacion is None and r.persiste is False


def test_no_persistir_no_puede_fabricar_un_DURABLE():
    with pytest.raises(ValueError):
        B.no_persistir(B.Disposicion.DURABLE, "motivo")


@pytest.mark.parametrize("mutacion", _mutaciones_validas())
def test_autorizar_devuelve_DURABLE_con_la_mutacion_intacta(mutacion):
    r = B.autorizar(mutacion)
    assert r.disposicion is B.Disposicion.DURABLE
    assert r.mutacion == mutacion and r.persiste is True


# ── E · la ruta se DERIVA, no se recibe ────────────────────────────────────────────


@pytest.mark.parametrize("mutacion", _mutaciones_validas())
def test_la_ruta_sale_de_la_clase_y_no_de_un_campo(mutacion):
    """`FieldEvidence.field` es un `str` libre en el contrato. Aceptarlo del candidato
    reabriría la superficie que la unión cierra: bastaría pedir procedencia de
    `household.children`."""
    assert "field" not in mutacion.model_fields
    assert "path" not in mutacion.model_fields
    assert B.ruta_contractual(mutacion) in B._RUTA_CONTRACTUAL.values()


def test_set_y_clear_del_mismo_campo_apuntan_a_la_misma_ruta():
    for s, c in ((B.SetObjective(objective=Objective.BUY), B.ClearObjective()),
                 (B.SetBudgetMax(amount=Decimal("1"), currency=USD), B.ClearBudgetMax()),
                 (B.SetBedroomsMin(bedrooms_min=1), B.ClearBedroomsMin()),
                 (B.SetAreaM2Min(area_m2_min=1.0), B.ClearAreaM2Min()),
                 (B.SetPetsRequired(), B.ClearPetsRequired())):
        assert B.ruta_contractual(s) == B.ruta_contractual(c)



def test_ruta_contractual_no_admite_que_le_pasen_la_ruta():
    """CIERRE DE LA MUTACIÓN M6.

    La primera versión de M6 añadía un parámetro `ruta` opcional a esta función y **ningún
    test caía** — con razón: un parámetro que nadie usa no rompe ninguna propiedad. Pero
    dejaba la puerta entornada, porque el siguiente llamante sí podría usarlo.

    La garantía real es que la firma no ofrezca por dónde pasar un destino. Se fija aquí:
    un solo parámetro, la mutación.
    """
    import inspect

    parametros = list(inspect.signature(B.ruta_contractual).parameters)
    assert parametros == ["mutacion"], (
        f"la firma abre una vía para elegir destino: {parametros}"
    )


# ── G · BuyerFieldV0 · la dimensión, para lo que no lleva mutación ─────────────────


def test_el_mapeo_mutacion_a_campo_cubre_TODA_la_union():
    """META-TEST de totalidad.

    Si mañana se añade una variante a `BuyerMutationV0` y se olvida el mapeo, una afirmación
    de esa dimensión no podría identificarse — y volvería el defecto que `BuyerFieldV0`
    existe para cerrar: una ambigüedad sin dimensión no compite con la durable que viene a
    invalidar. Esto lo convierte en test rojo en vez de en pérdida silenciosa.
    """
    import typing

    en_union = set(typing.get_args(typing.get_args(B.BuyerMutationV0)[0]))
    assert en_union == set(B._CAMPO_DE), (
        f"sin campo: {[c.__name__ for c in en_union - set(B._CAMPO_DE)]} · "
        f"sobran: {[c.__name__ for c in set(B._CAMPO_DE) - en_union]}"
    )


@pytest.mark.parametrize("set_, clear_", [
    (B.SetObjective(objective=Objective.BUY), B.ClearObjective()),
    (B.SetBudgetMax(amount=Decimal("1"), currency=USD), B.ClearBudgetMax()),
    (B.SetBedroomsMin(bedrooms_min=1), B.ClearBedroomsMin()),
    (B.SetAreaM2Min(area_m2_min=1.0), B.ClearAreaM2Min()),
    (B.SetPetsRequired(), B.ClearPetsRequired()),
])
def test_set_y_clear_COMPITEN_por_la_misma_dimension(set_, clear_):
    """Son las dos declaraciones que se disputan un campo. Agruparlas es lo que permite
    resolver el conflicto intramensaje antes de que llegue al reducer."""
    assert B.campo_de_mutacion(set_) is B.campo_de_mutacion(clear_)


def test_hay_exactamente_cinco_dimensiones():
    assert len(set(B._CAMPO_DE.values())) == 5
    assert set(B.BuyerFieldV0) == set(B._CAMPO_DE.values())


def test_el_campo_es_un_enum_y_no_una_cadena_libre():
    """Un `field: str` dejaría que una ambigüedad declarara `household.children` y confiara
    en un filtro posterior — la misma superficie que la unión de mutaciones cerró."""
    for prohibido in ("household", "children", "race", "familial_status", "stage",
                      "accessibility", "place_preferences"):
        assert prohibido not in {c.value for c in B.BuyerFieldV0}


def test_una_mutacion_ajena_no_tiene_campo():
    from pydantic import BaseModel as _BM

    class Impostora(_BM):
        pass

    with pytest.raises(TypeError):
        B.campo_de_mutacion(Impostora())

# ── F · la frontera es PURA ────────────────────────────────────────────────────────


def test_la_frontera_no_toca_nada_de_fuera():
    """Sin LLM, sin base, sin store, sin reloj, sin identidad. Si algún día necesita
    cualquiera de esas cosas, dejó de ser una frontera y pasó a ser el updater."""
    import ast
    import pathlib

    arbol = ast.parse(pathlib.Path(B.__file__).read_text(encoding="utf-8"))

    # Los DOCSTRINGS sobreviven a `unparse` —son código, no comentarios— y este módulo se
    # explica nombrando justo lo que no usa ("no conoce el buyer_id, ni la hora"). Sin
    # quitarlos, el test se acusaría a sí mismo. Es la misma trampa de texto-vs-estructura
    # que persigue a esta rama; aquí se cierra podando los docstrings del AST.
    for nodo in ast.walk(arbol):
        cuerpo = getattr(nodo, "body", None)
        if isinstance(cuerpo, list) and cuerpo:
            primero = cuerpo[0]
            if (isinstance(primero, ast.Expr) and isinstance(primero.value, ast.Constant)
                    and isinstance(primero.value.value, str)):
                cuerpo.pop(0)
    codigo = ast.unparse(arbol)

    for prohibido in ("anthropic", "AsyncSessionLocal", "sqlalchemy", "datetime",
                      "buyer_id", "EvidenceRef", "cargar_ultima", "anexar_revision",
                      "HumanMessage", "prompt"):
        assert prohibido not in codigo, f"la frontera usa {prohibido}"


def test_la_frontera_no_conoce_el_contrato_completo():
    """Solo importa `Objective`. Traerse `BuyerContextV0` invitaría a aplicar la mutación
    aquí — y aplicarla es E3.2b.2."""
    import ast
    import pathlib

    arbol = ast.parse(pathlib.Path(B.__file__).read_text(encoding="utf-8"))
    importado = {n.name for x in ast.walk(arbol) if isinstance(x, ast.ImportFrom)
                 for n in x.names}
    assert "BuyerContextV0" not in importado
    assert importado & {"Objective"}
