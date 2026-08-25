"""E1.3 — PropertyContextV0.

Dos de estas pruebas anclan defectos REALES documentados en el doc 03 sobre el
inventario de hoy, no riesgos hipotéticos:

  · un JSONB de atributos con un `precio` de $200 mientras la transacción decía $180
  · cero apariciones de `provider`/`tenant`/`external_id` en `app/`, que es lo que
    bloquea cualquier integración con un tercero
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.contracts.common_v0 import Money
from app.contracts.evidence_v0 import (
    EvidenceRefV0,
    PersistencePolicy,
    SourceType,
)
from app.contracts.property_v0 import (
    CONTRACT_VERSION,
    PROVIDER_TYPE_CONTEXTO,
    Availability,
    Location,
    Media,
    Operation,
    PropertyAttribute,
    InventoryClass,
    PropertyContextV0,
    PropertyProvenanceV0,
    Quality,
    Transaction,
    json_schema,
)

AHORA = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)


def _inmueble(**cambios):
    base = dict(
        property_id="4471",
        provider_id="contexto",
        provider_type=PROVIDER_TYPE_CONTEXTO,
        location=Location(lat=-0.18, lon=-78.48, address="La Floresta"),
        provenance=PropertyProvenanceV0(received_at=AHORA, inventory_class=InventoryClass.TEST),
    )
    base.update(cambios)
    return PropertyContextV0(**base)


# ── §1: lo permanente y lo efímero no se mezclan ─────────────────────────────────


def test_un_inmueble_existe_sin_listing_activo():
    """Un departamento tiene 90 m² y está donde está, se venda o no. Que no haya
    transacción es un estado normal, no un dato incompleto."""
    b = _inmueble()
    assert b.transaction is None
    assert b.location.esta_georreferenciada is True


def test_el_activo_fisico_y_el_listing_viven_en_campos_distintos():
    b = _inmueble(
        attributes=(PropertyAttribute(key="bedrooms", value=3),),
        transaction=Transaction(
            operation=Operation.RENT,
            price=Money(amount=Decimal("180"), currency="USD"),
        ),
    )
    assert b.attributes[0].key == "bedrooms"
    assert b.transaction.price.amount == Decimal("180")


def test_el_mismo_inmueble_puede_relistarse_con_otro_precio():
    """El listing es efímero: se cierra y meses después vuelve a salir. El activo no
    cambia, así que la transacción se reemplaza sin tocar lo permanente."""
    fisico = dict(
        attributes=(PropertyAttribute(key="area_m2", value=90.0, unit="m2"),),
    )
    antes = _inmueble(
        **fisico,
        transaction=Transaction(
            operation=Operation.RENT, price=Money(amount=Decimal("180"), currency="USD")
        ),
    )
    despues = _inmueble(
        **fisico,
        transaction=Transaction(
            operation=Operation.RENT, price=Money(amount=Decimal("210"), currency="USD")
        ),
    )
    assert antes.attributes == despues.attributes
    assert antes.transaction.price != despues.transaction.price


def test_un_listing_no_se_cierra_antes_de_publicarse():
    with pytest.raises(ValidationError, match="antes de existir"):
        Transaction(
            operation=Operation.SALE,
            listed_at=AHORA,
            closed_at=AHORA - timedelta(days=1),
        )


def test_la_operacion_tiene_los_dos_valores_evidenciados():
    """`tipo_operacion` en el inventario actual es venta o arriendo."""
    assert {o.value for o in Operation} == {"sale", "rent"}


# ── §2: el precio vive en un solo sitio ──────────────────────────────────────────


@pytest.mark.parametrize(
    "llave", ["precio", "price", "Precio", "  PRICE  ", "valor", "costo", "monto", "canon"]
)
def test_el_precio_no_puede_entrar_como_atributo(llave):
    """Ancla el defecto real del doc 03: sobre un activo REAL, el JSONB traía $200
    mientras la transacción decía $180. Dos precios sin regla de precedencia."""
    with pytest.raises(ValidationError, match="transaction.price"):
        PropertyAttribute(key=llave, value=200)


def test_el_precio_si_entra_donde_le_toca():
    t = Transaction(
        operation=Operation.RENT, price=Money(amount=Decimal("180"), currency="USD")
    )
    assert t.price.amount == Decimal("180")


def test_un_precio_ausente_no_es_un_precio_de_cero():
    t = Transaction(operation=Operation.SALE, price=None)
    assert t.price is None
    with pytest.raises(ValidationError):
        Money(amount=Decimal("0"), currency="USD")


def test_un_atributo_no_puede_estar_dos_veces():
    """Dos valores para la misma llave es el problema del JSONB de hoy: nadie sabe cuál
    gana."""
    with pytest.raises(ValidationError, match="repetido"):
        _inmueble(
            attributes=(
                PropertyAttribute(key="bedrooms", value=3),
                PropertyAttribute(key="Bedrooms", value=4),
            )
        )


def test_el_atributo_ya_no_es_un_jsonb_sin_tipar():
    a = PropertyAttribute(key="area_m2", value=90.0, unit="m2")
    assert (a.key, a.value, a.unit) == ("area_m2", 90.0, "m2")


# ── §3: identidad de proveedor, sin Partner Layer ────────────────────────────────


def test_la_identidad_externa_es_el_par_proveedor_inmueble():
    """Sin esto, dos cargas del mismo listado se convierten en dos inmuebles."""
    b = _inmueble(provider_id="portal-x", property_id="4471")
    assert b.identidad_externa == ("portal-x", "4471")


def test_dos_proveedores_pueden_traer_el_mismo_numero_sin_colisionar():
    a = _inmueble(provider_id="portal-x", property_id="4471")
    z = _inmueble(provider_id="portal-y", property_id="4471")
    assert a.identidad_externa != z.identidad_externa


def test_el_inventario_propio_se_reconoce_por_su_tipo():
    assert _inmueble().es_inventario_propio is True
    assert _inmueble(provider_type="otro").es_inventario_propio is False


def test_el_proveedor_es_obligatorio():
    """El bloqueador del doc 03 era no tener dónde ponerlo."""
    for falta in ("provider_id", "provider_type"):
        datos = _inmueble().model_dump(mode="json")
        del datos[falta]
        with pytest.raises(ValidationError):
            PropertyContextV0.model_validate(datos)


def test_el_contrato_no_construye_partner_layer():
    """Tener la identidad no es integrar: no hay adaptadores, ni clientes, ni fetch."""
    for prohibido in ("fetch", "sync", "import_from", "adapter", "client", "save"):
        assert not hasattr(PropertyContextV0, prohibido)


# ── vocabularios abiertos a propósito ────────────────────────────────────────────


def test_availability_adopta_el_vocabulario_del_blueprint():
    """Blueprint 0.1: available | reserved | sold | unknown. Se adopta tal cual en vez de
    inventar uno; el inventario actual guarda texto libre y el mapeo lo hará F5."""
    assert {a.value for a in Availability} == {"available", "reserved", "sold", "unknown"}
    assert set(json_schema()["$defs"]["Availability"]["enum"]) == {
        "available", "reserved", "sold", "unknown"
    }


def test_un_estado_de_anuncio_inventado_ya_no_pasa():
    with pytest.raises(ValidationError):
        Transaction(operation=Operation.SALE, availability="disponible")


def test_no_declarado_y_declarado_desconocido_no_son_lo_mismo():
    """`None` = el listing no dice nada. `UNKNOWN` = lo dice y dice que no se sabe."""
    sin_declarar = Transaction(operation=Operation.SALE)
    declarado = Transaction(operation=Operation.SALE, availability=Availability.UNKNOWN)
    assert sin_declarar.availability is None
    assert declarado.availability is Availability.UNKNOWN
    assert sin_declarar != declarado


def test_el_estado_del_anuncio_sobrevive_el_ida_y_vuelta():
    t = Transaction(operation=Operation.SALE, availability=Availability.RESERVED)
    crudo = t.model_dump(mode="json")
    assert crudo["availability"] == "reserved"
    assert Transaction.model_validate(crudo).availability is Availability.RESERVED


def test_provider_type_queda_abierto_en_v0():
    """Solo hay un valor evidenciado; inventar una taxonomía desde un caso sería
    congelar una hipótesis sobre un mercado que aún no conocemos."""
    assert "enum" not in str(json_schema()["properties"]["provider_type"])
    assert _inmueble(provider_type="un_tipo_futuro").provider_type == "un_tipo_futuro"


# ── §4: el registro dice para qué sirve ─────────────────────────────────────────


def test_la_clasificacion_es_obligatoria_y_sin_default():
    """Un default silencioso sería el fallo mismo que este campo evita: que un registro
    de prueba pase por real porque nadie lo declaró."""
    with pytest.raises(ValidationError, match="inventory_class"):
        PropertyProvenanceV0(received_at=AHORA)


def test_los_cuatro_estados_y_ninguno_mas():
    assert {c.value for c in InventoryClass} == {"live", "demo", "test", "unknown"}


def test_el_json_schema_expone_los_cuatro_estados():
    """Un consumidor que no sea Python tiene que poder leer las opciones."""
    enum_ = json_schema()["$defs"]["InventoryClass"]["enum"]
    assert set(enum_) == {"live", "demo", "test", "unknown"}


def test_la_clasificacion_es_independiente_del_proveedor():
    """Ejes distintos: un proveedor externo puede mandar un demo y el inventario propio
    puede ser real. Cruzarlos escondería la clasificación detrás de un dato que no la
    significa."""
    propio_demo = _inmueble(
        provider_type=PROVIDER_TYPE_CONTEXTO,
        provenance=PropertyProvenanceV0(
            received_at=AHORA, inventory_class=InventoryClass.DEMO
        ),
    )
    ajeno_real = _inmueble(
        provider_type="portal_externo",
        provenance=PropertyProvenanceV0(
            received_at=AHORA, inventory_class=InventoryClass.LIVE
        ),
    )
    assert propio_demo.es_inventario_propio is True
    assert propio_demo.provenance.inventory_class is InventoryClass.DEMO
    assert ajeno_real.es_inventario_propio is False
    assert ajeno_real.provenance.inventory_class is InventoryClass.LIVE


def test_un_demo_serializa_perfectamente_y_sigue_siendo_demo():
    """El riesgo real: que al pasar por JSON la marca se caiga y el registro reaparezca
    del otro lado sin ella."""
    original = _inmueble(
        provenance=PropertyProvenanceV0(
            received_at=AHORA, inventory_class=InventoryClass.DEMO
        ),
        transaction=Transaction(
            operation=Operation.RENT, price=Money(amount=Decimal("180"), currency="USD")
        ),
    )
    crudo = original.model_dump(mode="json")
    assert crudo["provenance"]["inventory_class"] == "demo"
    assert PropertyContextV0.model_validate(crudo).provenance.inventory_class is InventoryClass.DEMO


def test_unknown_no_se_convierte_en_live_por_el_camino():
    """`unknown` es la respuesta honesta al migrar inventario del que nadie puede decir
    de dónde salió. Si se degradara a `live` en algún punto, el campo no serviría de
    nada — que es justo lo que pasa hoy sin él."""
    p = PropertyProvenanceV0(received_at=AHORA, inventory_class=InventoryClass.UNKNOWN)
    b = _inmueble(provenance=p)
    assert b.provenance.inventory_class is InventoryClass.UNKNOWN
    ida_y_vuelta = PropertyContextV0.model_validate(b.model_dump(mode="json"))
    assert ida_y_vuelta.provenance.inventory_class is InventoryClass.UNKNOWN
    assert ida_y_vuelta.provenance.inventory_class is not InventoryClass.LIVE


def test_aqui_unknown_si_es_valido_a_diferencia_de_e1_1():
    """La diferencia con E1.1 importa: allí un `source_type="unknown"` habría fabricado
    una evidencia para representar que no la hay. Aquí el registro existe y lo que se
    declara es que desconocemos una de sus propiedades."""
    from app.contracts.evidence_v0 import SourceType as ST

    assert "unknown" not in {s.value for s in ST}
    assert "unknown" in {c.value for c in InventoryClass}


def test_la_clasificacion_no_trae_politica_todavia():
    """En V0 basta con preservar la información: sin decision_eligible, sin reglas de
    benchmark, sin filtros. Esas políticas la consumirán después."""
    props = set(json_schema()["properties"])
    assert "decision_eligible" not in props
    for prohibido in ("decision_eligible", "is_eligible", "puede_decidirse"):
        assert not hasattr(PropertyContextV0, prohibido)


# ── ubicación ────────────────────────────────────────────────────────────────────


def test_media_coordenada_no_ubica_nada():
    with pytest.raises(ValidationError, match="van juntas"):
        Location(lat=-0.18)


def test_una_ubicacion_necesita_coordenadas_o_direccion():
    with pytest.raises(ValidationError, match="coordenadas o dirección"):
        Location()


def test_una_direccion_sin_coordenadas_es_valida_pero_lo_dice():
    loc = Location(address="Av. Amazonas y Naciones Unidas")
    assert loc.esta_georreferenciada is False


# ── procedencia y calidad ────────────────────────────────────────────────────────


def test_no_se_recibe_una_actualizacion_del_futuro():
    with pytest.raises(ValidationError, match="posterior a received_at"):
        PropertyProvenanceV0(received_at=AHORA, inventory_class=InventoryClass.TEST, last_updated_at=AHORA + timedelta(days=1))


def test_que_el_proveedor_no_diga_cuando_actualizo_es_un_estado_legitimo():
    """Y no se sustituye por `received_at`, que es la mentira que cerró E0.3."""
    p = PropertyProvenanceV0(received_at=AHORA, inventory_class=InventoryClass.TEST)
    assert p.last_updated_at is None


def test_la_procedencia_usa_la_primitiva_de_e1_1():
    ev = EvidenceRefV0(
        source_type=SourceType.PROVIDER_API,
        provider="un_portal",
        observed_at=None,
        retrieved_at=AHORA,
        methodology="volcado del feed del proveedor",
        persistence_policy=PersistencePolicy.PERSISTABLE,
    )
    b = _inmueble(provenance=PropertyProvenanceV0(received_at=AHORA, inventory_class=InventoryClass.LIVE, evidence=(ev,)))
    assert isinstance(b.provenance.evidence[0], EvidenceRefV0)


def test_no_hay_un_segundo_sistema_de_procedencia():
    props = set(json_schema()["properties"])
    for propio_de_evidencia in ("source_type", "confidence", "methodology"):
        assert propio_de_evidencia not in props


def test_completitud_sin_calcular_no_es_completitud_cero():
    """Misma distinción que `confidence` en E1.1: `None` se abstiene, `0.0` afirma."""
    assert Quality().completeness is None
    assert Quality(completeness=0.0).completeness == 0.0
    for fuera in (-0.1, 1.1):
        with pytest.raises(ValidationError):
            Quality(completeness=fuera)


def test_un_aviso_en_blanco_no_avisa():
    with pytest.raises(ValidationError, match="no avisa"):
        Quality(warnings=("  ",))


# ── versionado, serialización, inmutabilidad ─────────────────────────────────────


def test_el_contrato_lleva_su_version():
    assert _inmueble().contract_version == CONTRACT_VERSION == "property-context-v0"


def test_una_version_futura_no_se_cuela():
    datos = _inmueble().model_dump(mode="json")
    datos["contract_version"] = "property-context-v1"
    with pytest.raises(ValidationError):
        PropertyContextV0.model_validate(datos)


def test_serializa_y_vuelve_igual_con_todo_lleno():
    original = _inmueble(
        provider_listing_url="https://portal.example/4471",
        attributes=(
            PropertyAttribute(key="bedrooms", value=3),
            PropertyAttribute(key="area_m2", value=90.0, unit="m2"),
            PropertyAttribute(key="furnished", value=True),
        ),
        transaction=Transaction(
            operation=Operation.RENT,
            price=Money(amount=Decimal("180"), currency="USD"),
            availability=Availability.AVAILABLE,
            listed_at=AHORA - timedelta(days=30),
        ),
        media=Media(images=("https://portal.example/1.jpg",)),
        quality=Quality(completeness=0.8, warnings=("sin fotos de la cocina",)),
    )
    assert PropertyContextV0.model_validate(original.model_dump(mode="json")) == original


def test_el_inmueble_no_se_edita_despues_de_creado():
    b = _inmueble()
    with pytest.raises(ValidationError):
        b.property_id = "otro"


def test_las_colecciones_no_se_mutan_por_dentro():
    b = _inmueble(attributes=(PropertyAttribute(key="bedrooms", value=3),))
    assert isinstance(b.attributes, tuple)
    with pytest.raises(AttributeError):
        b.attributes.append(PropertyAttribute(key="colado", value=1))


def test_no_se_aceptan_campos_extra():
    with pytest.raises(ValidationError):
        _inmueble(precio=200)


def test_el_esquema_nombra_los_campos_minimos():
    props = set(json_schema()["properties"])
    for campo in (
        "property_id", "provider_id", "provider_type", "provider_listing_url",
        "location", "transaction", "attributes", "media", "provenance", "quality",
    ):
        assert campo in props, f"el contrato perdió el campo mínimo {campo}"
