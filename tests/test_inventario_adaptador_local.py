"""PLAN04-1.4 — el adaptador local: inventario propio → `PropertyContextV0`.

QUE SE PRUEBA, Y POR QUE ASI

El riesgo de esta unidad no es que el objeto salga invalido. Es que salga VALIDO Y VACIO.
El criterio del plan —«40 activos → 40 objetos validos»— es casi tautologico: `geom` y
`direccion_estandarizada` son NOT NULL, `transaction` es opcional y `inventory_class=unknown`
siempre vale, asi que un adaptador que tire el precio, la operacion y los atributos pasaria
40/40 sin haber preservado nada.

Por eso aqui se prueba PRESERVACION, no validez: que el precio llegue, que la operacion
llegue, que los atributos lleguen, y que lo que NO se puede sostener salga declarado en
`warnings` en vez de rellenado.

EL OTRO RIESGO ES LA FORMA. Una prueba que fabrique la entrada a mano pasaria aunque el
adaptador no supiera leer lo que la base devuelve de verdad. La fixture congelada trae la
forma REAL de `.mappings()`: `id` como UUID, `precio` como Decimal, timestamps NAIVE,
vocabulario en MAYUSCULAS, y `caracteristicas` unas veces objeto y otras texto.

CERO RED, CERO BASE DE DATOS: la unica funcion que la toca es `leer_activos_locales`, y aqui
solo se ejercita con una sesion falsa para comprobar la costura.
"""

from __future__ import annotations

import ast
import json
import pathlib
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.contracts.property_v0 import (
    PROVIDER_TYPE_CONTEXTO,
    Availability,
    InventoryClass,
    Operation,
    PropertyContextV0,
)
from app.inventario import adaptador_local as adaptador
from app.inventario.adaptador_local import (
    ContextoDeLectura,
    ensamblar_property_context,
)

_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "inventario_1_4_filas.json"
_SNAPSHOT = datetime(2026, 9, 9, 15, 0, tzinfo=timezone.utc)


def _materializar(v):
    """Los tipos que JSON no tiene, con la forma que devuelve el driver."""
    if isinstance(v, dict):
        if "__uuid__" in v:
            return uuid.UUID(v["__uuid__"])
        if "__decimal__" in v:
            return Decimal(v["__decimal__"])
        if "__naive__" in v or "__aware__" in v:
            return datetime.fromisoformat(v.get("__naive__") or v["__aware__"])
        return {k: _materializar(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_materializar(x) for x in v]
    return v


@pytest.fixture(scope="module")
def congelado() -> dict:
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def filas(congelado) -> list[dict]:
    return [{k: _materializar(v) for k, v in f.items() if k != "_caso"}
            for f in congelado["filas"]]


@pytest.fixture(scope="module")
def casos(congelado) -> list[str]:
    return [f["_caso"] for f in congelado["filas"]]


@pytest.fixture()
def contexto() -> ContextoDeLectura:
    return ContextoDeLectura(snapshot_at=_SNAPSHOT, moneda="USD")


def fila_de(filas, indice: int) -> dict:
    return filas[indice]


# ── (A) TODA la variedad material produce un objeto valido ───────────────────


def test_todas_las_filas_congeladas_producen_un_objeto_valido(filas, casos, contexto):
    """El analogo honesto de «N activos → N objetos validos», sobre variedad SINTETICA.

    Doce filas que cubren lo que el inventario puede presentar. Que ninguna reviente es el
    piso, no el techo: lo que de verdad se prueba esta en (B).
    """
    for fila, caso in zip(filas, casos):
        objeto = ensamblar_property_context(fila, contexto)
        assert isinstance(objeto, PropertyContextV0), caso
        assert objeto.identidad_externa == ("contexto", str(fila["id"])), caso


def test_la_identidad_externa_es_del_inventario_propio(filas, contexto):
    """`provider_id`/`provider_type` son CONSTANTES, no datos de la fila: no hay columna de
    proveedor y esta unidad tiene prohibido crearla."""
    for fila in filas:
        objeto = ensamblar_property_context(fila, contexto)
        assert objeto.provider_id == "contexto"
        assert objeto.provider_type == PROVIDER_TYPE_CONTEXTO
        assert objeto.es_inventario_propio is True
        assert objeto.provider_listing_url is None


def test_la_clasificacion_es_unknown_mientras_la_fuente_no_demuestre_otra(filas, contexto):
    """`inventory_class` es obligatorio y sin default. La auditoria del repositorio admite
    que de ocho artefactos de siembra «Ninguno indica cuál generó los 40 activos vivos»:
    `unknown` es la decision honesta, y `live` seria una afirmacion sin respaldo."""
    for fila in filas:
        p = ensamblar_property_context(fila, contexto)
        assert p.provenance.inventory_class is InventoryClass.UNKNOWN


# ── (B) PRESERVACION — lo que cierra el agujero tautologico ──────────────────


def test_el_caso_nominal_preserva_ubicacion_operacion_precio_y_atributos(filas, contexto):
    p = ensamblar_property_context(fila_de(filas, 0), contexto)

    assert (p.location.lat, p.location.lon) == (-0.1807, -78.4867)
    assert p.location.address.startswith("Av. Coruña")
    assert p.location.esta_georreferenciada is True

    assert p.transaction.operation is Operation.RENT
    assert p.transaction.availability is Availability.AVAILABLE
    assert p.transaction.price.amount == Decimal("180.00")
    assert p.transaction.price.currency == "USD"

    atributos = {a.key: a.value for a in p.attributes}
    assert atributos == {
        "amoblado": True, "area_m2": 90, "dormitorios": 2,
        "piso_altura": 3, "tipo_activo": "Departamento",
    }


def test_el_precio_del_JSONB_no_llega_a_los_atributos_y_se_declara(filas, contexto):
    """El caso REAL del doc 03: $200 en `caracteristicas`, $180 en la transaccion. El
    contrato solo admite uno; el adaptador descarta el otro Y LO DICE."""
    p = ensamblar_property_context(fila_de(filas, 0), contexto)
    assert "precio" not in {a.key for a in p.attributes}
    assert p.transaction.price.amount == Decimal("180.00")
    assert any("precio" in w and "transaction.price" in w for w in p.quality.warnings)


def test_el_JSONB_como_TEXTO_produce_los_mismos_atributos_que_como_objeto(filas, contexto):
    """El driver entrega `caracteristicas` de las dos formas. Si el adaptador solo supiera
    leer una, la mitad del inventario perderia sus atributos en silencio."""
    p = ensamblar_property_context(fila_de(filas, 1), contexto)
    atributos = {a.key: a.value for a in p.attributes}
    assert atributos == {
        "area_m2": 120, "dormitorios": 0, "parqueaderos": 2,
        "piso_altura": 7, "tipo_activo": "Oficina",
    }
    assert p.transaction.operation is Operation.SALE
    assert p.transaction.availability is Availability.SOLD


def test_la_media_junta_portada_y_fotos_sin_vacias_ni_repetidas(filas, contexto):
    p = ensamblar_property_context(fila_de(filas, 0), contexto)
    assert p.media.images == ("https://cdn.example/portada.jpg", "https://cdn.example/1.jpg")


def test_sin_geometria_el_inmueble_se_ubica_por_direccion(filas, contexto):
    p = ensamblar_property_context(fila_de(filas, 11), contexto)
    assert (p.location.lat, p.location.lon) == (None, None)
    assert p.location.esta_georreferenciada is False
    assert p.location.address == "Sector Cumbaya, sin georreferenciar"


# ── (C) LO QUE NO SE PUEDE SOSTENER SE DECLARA, NO SE RELLENA ────────────────


def test_los_timestamps_NAIVE_se_omiten_y_se_declara_la_omision(filas, contexto):
    """Las columnas son TIMESTAMP sin zona y el contrato exige zona. Suponer UTC seria
    afirmar un dato que nadie declaro; el repositorio ya pago un bug de fechas por eso."""
    p = ensamblar_property_context(fila_de(filas, 1), contexto)
    assert p.transaction.listed_at is None
    assert p.transaction.closed_at is None
    assert sum("sin zona horaria" in w for w in p.quality.warnings) == 2
    assert any("suponerle UTC" in w for w in p.quality.warnings)


def test_un_timestamp_CON_zona_si_se_conserva(filas, contexto):
    """La omision es por la zona ausente, no por el campo. Sin este caso, un adaptador que
    tirara SIEMPRE los timestamps pasaria igual."""
    p = ensamblar_property_context(fila_de(filas, 11), contexto)
    assert p.transaction.listed_at == datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
    assert not any("sin zona horaria" in w for w in p.quality.warnings)


def test_MONITOREO_PASIVO_omite_la_transaccion_entera_y_lo_dice(filas, contexto):
    """Existe en el CHECK del inventario y no tiene valor en `Operation`. Aproximarlo a
    arriendo pondria un inmueble en el mercado que nadie puso."""
    p = ensamblar_property_context(fila_de(filas, 3), contexto)
    assert p.transaction is None
    assert any("MONITOREO_PASIVO" in w and "no tiene valor en el contrato" in w
               for w in p.quality.warnings)


def test_el_vocabulario_en_MINUSCULA_no_se_aproxima(filas, contexto):
    """El CHECK del DDL solo admite mayusculas. Aceptar 'arriendo' seria admitir filas que
    la base no puede contener, y callar la deriva el dia que alguien relaje el constraint."""
    p = ensamblar_property_context(fila_de(filas, 9), contexto)
    assert p.transaction is None
    assert any("'arriendo'" in w and "no está en el vocabulario" in w
               for w in p.quality.warnings)


def test_estado_NULL_es_unknown_y_no_se_asume_activo(filas, contexto):
    """El runtime de tarjetas hace `COALESCE(estado_anuncio,'ACTIVO')`, que es una comodidad
    de consulta y no una verdad. Aqui NULL significa que el listing no lo declara."""
    p = ensamblar_property_context(fila_de(filas, 4), contexto)
    assert p.transaction.availability is Availability.UNKNOWN
    assert any("no declara estado" in w for w in p.quality.warnings)


def test_una_VENTA_completada_SI_es_una_venta(filas, contexto):
    """`COMPLETADO` sobre una venta es exactamente lo que `sold` significa."""
    p = ensamblar_property_context(fila_de(filas, 1), contexto)
    assert p.transaction.operation is Operation.SALE
    assert p.transaction.availability is Availability.SOLD
    assert not any("COMPLETADO" in w for w in p.quality.warnings)


def test_un_ARRIENDO_completado_NO_se_declara_vendido(filas, contexto):
    """La mentira bien tipada que R1 vino a cerrar.

    El inventario cierra los dos finales con la MISMA palabra —`COMPLETADO`— y el contrato
    solo modela uno. Traducirlo a `sold` sin mirar la operacion afirma que se VENDIO un
    inmueble que se ARRENDO: objeto valido, dato falso, y ninguna validacion lo detecta.

    `unknown` es lo unico que no afirma de mas: `sold` mentiria y `reserved` inventaria un
    estado que nadie declaro. Pero no entra callado — un arriendo cerrado y un anuncio del
    que no se sabe nada no son lo mismo, y el aviso es lo unico que los distingue.
    """
    p = ensamblar_property_context(fila_de(filas, 10), contexto)
    assert p.transaction.operation is Operation.RENT
    assert p.transaction.availability is not Availability.SOLD
    assert p.transaction.availability is Availability.UNKNOWN
    assert any("COMPLETADO" in w and "arrendado" in w for w in p.quality.warnings)
    assert any("reserved" in w and "inventaría" in w for w in p.quality.warnings)


def test_el_MISMO_estado_se_traduce_distinto_segun_la_operacion(filas, contexto):
    """La asimetria, medida de frente: misma palabra del inventario, dos destinos. Sin este
    par, una traduccion incondicional pasaria la mitad de las pruebas igual."""
    venta = ensamblar_property_context(fila_de(filas, 1), contexto).transaction
    arriendo = ensamblar_property_context(fila_de(filas, 10), contexto).transaction
    assert venta.availability is not arriendo.availability
    assert (venta.availability, arriendo.availability) == (
        Availability.SOLD, Availability.UNKNOWN)


def test_no_se_amplia_el_vocabulario_del_contrato_ni_se_inventa_RESERVED(filas, contexto):
    """R1 corrige la traduccion, NO el contrato. `Availability` sigue teniendo sus cuatro
    valores y `reserved` no aparece nunca: el inventario no tiene con que declararlo."""
    assert [a.value for a in Availability] == ["available", "reserved", "sold", "unknown"]
    for fila in filas:
        p = ensamblar_property_context(fila, contexto)
        if p.transaction is not None:
            assert p.transaction.availability is not Availability.RESERVED


def test_PAUSADO_cae_en_unknown_pero_no_en_silencio(filas, contexto):
    """`Availability` no tiene «pausado». Sin el aviso, un anuncio pausado seria
    indistinguible de uno cuyo estado nadie conoce."""
    p = ensamblar_property_context(fila_de(filas, 8), contexto)
    assert p.transaction.availability is Availability.UNKNOWN
    assert any("PAUSADO" in w and "el contrato no tiene ese valor" in w
               for w in p.quality.warnings)


def test_un_precio_no_representable_omite_el_PRECIO_y_no_la_transaccion(filas, contexto):
    """`Money.amount` exige > 0. Un 0 no invalida que exista un listing en arriendo."""
    p = ensamblar_property_context(fila_de(filas, 8), contexto)
    assert p.transaction is not None
    assert p.transaction.operation is Operation.RENT
    assert p.transaction.price is None
    assert any("no es un importe representable" in w for w in p.quality.warnings)


def test_sin_transaccion_no_hay_listing_y_tampoco_aviso(filas, contexto):
    """La ausencia de listing es un estado normal del inmueble, no un defecto del dato."""
    p = ensamblar_property_context(fila_de(filas, 2), contexto)
    assert p.transaction is None
    assert p.quality.warnings == ()


@pytest.mark.parametrize("indice,fragmento", [(5, "no es un objeto JSON"),
                                              (6, "no es JSON válido")])
def test_un_JSONB_que_no_es_objeto_degrada_declarando_y_no_revienta(
    filas, contexto, indice, fragmento
):
    """Caso real: el repositorio ya se guarda en tres sitios de un JSONB que es `5`, `[..]`
    o `true`. Degradar en silencio dejaria un inmueble sin atributos indistinguible de uno
    que no los tiene."""
    p = ensamblar_property_context(fila_de(filas, indice), contexto)
    assert {a.key for a in p.attributes} == {"tipo_activo", "piso_altura"}
    assert any(fragmento in w for w in p.quality.warnings)


def test_fotos_que_no_es_lista_se_descarta_declarando(filas, contexto):
    p = ensamblar_property_context(fila_de(filas, 8), contexto)
    assert p.media.images == ()
    assert any("`caracteristicas.fotos` no es una lista" in w for w in p.quality.warnings)


def test_la_completitud_no_se_inventa(filas, contexto):
    """Nadie la calcula hoy. `None` dice «no se midio»; `0.0` afirmaria que no llego nada."""
    for fila in filas:
        assert ensamblar_property_context(fila, contexto).quality.completeness is None


# ── (D) EL CONTEXTO SE DECLARA FUERA: ni moneda ni instante se inventan ──────


def test_la_moneda_viene_del_PARAMETRO_y_no_esta_fijada_en_el_codigo(filas, contexto):
    """El inventario NO tiene columna de moneda y no hay configuracion autoritativa que
    reutilizar: `settings.buyer_market_currency` es politica del Buyer Harness para
    desambiguar lo que dice una persona, no la denominacion del inventario."""
    otra = ContextoDeLectura(snapshot_at=_SNAPSHOT, moneda="MXN")
    fila = fila_de(filas, 0)
    assert ensamblar_property_context(fila, contexto).transaction.price.currency == "USD"
    assert ensamblar_property_context(fila, otra).transaction.price.currency == "MXN"


def test_el_instante_de_recepcion_viene_del_CONTEXTO_y_no_de_la_fila(filas, contexto):
    """`received_at` significa «cuando lo trajimos NOSOTROS»: lo sabe quien lee, no la fila
    leida. Por eso no sale de `created_at`, que ademas es naive."""
    for fila in filas:
        p = ensamblar_property_context(fila, contexto)
        assert p.provenance.received_at == _SNAPSHOT
    otro = ContextoDeLectura(snapshot_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                             moneda="USD")
    assert ensamblar_property_context(filas[0], otro).provenance.received_at.year == 2026
    assert ensamblar_property_context(filas[0], otro).provenance.received_at.month == 1


def test_el_proveedor_no_declara_cuando_actualizo(filas, contexto):
    """`last_updated_at=None` y no se sustituye por `received_at`, que es la mentira de E0.3."""
    for fila in filas:
        assert ensamblar_property_context(fila, contexto).provenance.last_updated_at is None


@pytest.mark.parametrize("snapshot,moneda,motivo", [
    (datetime(2026, 9, 9, 15, 0), "USD", "zona horaria"),
    (_SNAPSHOT, "usd", "ISO-4217"),
    (_SNAPSHOT, "dolares", "ISO-4217"),
    (_SNAPSHOT, "", "ISO-4217"),
])
def test_un_contexto_mal_formado_falla_al_CONSTRUIRSE(snapshot, moneda, motivo):
    """Falla aqui y no cuarenta filas despues: un contexto invalido es error del llamador."""
    with pytest.raises(ValueError, match=motivo):
        ContextoDeLectura(snapshot_at=snapshot, moneda=moneda)


# ── (E) NO SE FABRICA PROCEDENCIA ────────────────────────────────────────────


def test_no_se_fabrica_evidencia_donde_no_la_hay(filas, contexto):
    """`EvidenceRefV0` no tiene —por diseno— un `source_type="unknown"`: su modulo dice que
    fabricar una referencia para representar la ausencia «es inventarse una procedencia».

    Si no sabemos que proceso cargo el registro (por eso `inventory_class=unknown`), tampoco
    sabemos quien declaro su precio. Elegir `operator_declared` afirmaria que detras hay un
    corredor con interes comercial; sobre una ficha posiblemente hidratada, eso es la
    sobreafirmacion que el contrato existe para impedir.
    """
    for fila in filas:
        assert ensamblar_property_context(fila, contexto).provenance.evidence == ()


# ── (F) DETERMINISMO ─────────────────────────────────────────────────────────


def test_dos_ensamblajes_de_la_MISMA_fila_dan_el_MISMO_JSON(filas, contexto, casos):
    """Byte a byte. Lo unico que podia romperlo era el orden de `attributes`, que nace de un
    JSONB: un dict parseado desde texto y uno entregado por el driver no tienen por que
    iterar igual."""
    for fila, caso in zip(filas, casos):
        uno = ensamblar_property_context(fila, contexto)
        otro = ensamblar_property_context(fila, contexto)
        assert uno.model_dump_json() == otro.model_dump_json(), caso
        assert uno == otro, caso


def test_los_atributos_salen_ORDENADOS_por_llave(filas, contexto):
    """El orden es una funcion del dato, no del driver. Se mide la propiedad que impide la
    deriva, porque dentro de un solo proceso la deriva no se puede observar."""
    for fila in filas:
        llaves = [a.key for a in ensamblar_property_context(fila, contexto).attributes]
        assert llaves == sorted(llaves)


def test_el_objeto_va_y_vuelve_de_JSON_sin_perder_nada(filas, contexto):
    for fila in filas:
        p = ensamblar_property_context(fila, contexto)
        assert PropertyContextV0.model_validate_json(p.model_dump_json()) == p


# ── (G) LA COSTURA CON LA BASE ───────────────────────────────────────────────


class _ResultadoFalso:
    def __init__(self, filas): self._filas = filas
    def mappings(self): return self
    def all(self): return self._filas


class _SesionFalsa:
    def __init__(self, registro, filas): self._registro, self._filas = registro, filas
    async def __aenter__(self): return self
    async def __aexit__(self, *_): return False
    async def execute(self, consulta, parametros=None):
        self._registro.append((str(consulta), parametros))
        return _ResultadoFalso(self._filas)


@pytest.mark.asyncio
async def test_la_lectura_consulta_UNA_SOLA_VEZ_y_no_ensambla(monkeypatch):
    """La frontera recupera; no interpreta. Si devolviera contratos, tendria que conocer la
    moneda y el instante de recepcion, que es politica que no le toca."""
    registro = []
    monkeypatch.setattr(adaptador, "AsyncSessionLocal",
                        lambda: _SesionFalsa(registro, [{"id": 1}]))
    salida = await adaptador.leer_activos_locales()

    assert len(registro) == 1
    assert salida == [{"id": 1}]
    assert not isinstance(salida[0], PropertyContextV0)


@pytest.mark.asyncio
async def test_el_filtro_por_ids_solo_aparece_cuando_se_piden_ids(monkeypatch):
    registro = []
    monkeypatch.setattr(adaptador, "AsyncSessionLocal",
                        lambda: _SesionFalsa(registro, []))

    # El `WHERE` del LATERAL siempre esta; lo que no puede aparecer es el filtro por ids.
    await adaptador.leer_activos_locales()
    assert "a.id::text = ANY(:ids)" not in registro[-1][0]
    assert registro[-1][1] == {}

    await adaptador.leer_activos_locales(["a", "b"])
    assert "a.id::text = ANY(:ids)" in registro[-1][0]
    assert registro[-1][1] == {"ids": ["a", "b"]}


# ── (H) GUARDAS DE FORMA: que la prueba no pase sobre un adaptador de mentira ─


def _arbol():
    import app.inventario.adaptador_local as m
    return ast.parse(pathlib.Path(m.__file__).read_text(encoding="utf-8"))


_LECTURAS_INDIRECTAS_CONOCIDAS = {"columna"}
"""Variables por las que el modulo lee la fila SIN literal. Hoy solo el bucle sobre
`_COLUMNAS_PROPIAS_COMO_ATRIBUTOS`. Se declara aqui para que la guarda no pueda quedarse
ciega en silencio: si aparece otra lectura indirecta, la prueba lo exige por su nombre."""


def _llaves_leidas_de_la_fila() -> tuple[set[str], set[str]]:
    """Toda llave que el modulo lee de la fila, sacada del AST y no del texto.

    Devuelve (literales, variables). La segunda mitad existe porque la primera version de
    esta guarda nacio MEDIO CIEGA: `piso_altura` y `tipo_activo` se leen por variable de
    bucle, asi que quitarlos de la consulta no rompia nada. Lo destapo la mutacion Z14.
    """
    literales, variables = set(), set()
    for n in ast.walk(_arbol()):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "get" and isinstance(n.func.value, ast.Name)
                and n.func.value.id == "fila" and n.args):
            if isinstance(n.args[0], ast.Constant):
                literales.add(n.args[0].value)
            elif isinstance(n.args[0], ast.Name):
                variables.add(n.args[0].id)
        if (isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name)
                and n.value.id == "fila"):
            if isinstance(n.slice, ast.Constant):
                literales.add(n.slice.value)
            elif isinstance(n.slice, ast.Name):
                variables.add(n.slice.id)
    return literales, variables


def test_toda_columna_que_el_adaptador_LEE_esta_en_la_consulta():
    """La deriva silenciosa que esto impide: mapear una columna que la consulta no trae.
    Contra la base real eso da `None` en todas las filas —un campo vacio que parece un dato
    ausente— y ninguna prueba con filas fabricadas a mano lo detectaria.

    Se mira el AST y no el texto: un `grep` se encontraria a si mismo en los comentarios.
    """
    literales, variables = _llaves_leidas_de_la_fila()

    assert variables == _LECTURAS_INDIRECTAS_CONOCIDAS, (
        f"hay lecturas indirectas de la fila que esta guarda no sabe resolver: "
        f"{variables - _LECTURAS_INDIRECTAS_CONOCIDAS}. Mientras no se resuelvan, esas "
        "columnas quedarian sin vigilar — que es como esta guarda nacio ciega."
    )
    # La unica indirecta conocida es el bucle sobre esta constante: se resuelve por valor.
    llaves = literales | set(adaptador._COLUMNAS_PROPIAS_COMO_ATRIBUTOS)

    assert len(llaves) >= 12, (
        f"solo se detectaron {len(llaves)} lecturas de la fila; la guarda esta ciega "
        "(¿se renombro `fila`?) y estaria pasando por vacio"
    )
    faltan = [k for k in llaves if k not in adaptador._SELECT_ACTIVOS]
    assert not faltan, f"el adaptador lee columnas que la consulta no selecciona: {faltan}"


def test_el_ensamblador_es_PURO_en_el_codigo_y_no_solo_de_palabra():
    """Sin `await`, sin sesion, sin reloj. Si el ensamblaje tocara la base, la unidad
    dejaria de ser probable sin ella y el determinismo seria una casualidad."""
    puras = {"ensamblar_property_context", "_atributos_de", "_media_de",
             "_transaccion_de", "_caracteristicas_de", "_instante", "_disponibilidad_de"}
    prohibidos = {"AsyncSessionLocal", "text", "now", "utcnow"}
    vistas = set()
    for n in ast.walk(_arbol()):
        if isinstance(n, ast.FunctionDef) and n.name in puras:
            vistas.add(n.name)
            for hijo in ast.walk(n):
                assert not isinstance(hijo, (ast.Await, ast.AsyncWith)), n.name
                if isinstance(hijo, ast.Name):
                    assert hijo.id not in prohibidos, f"{n.name} toca {hijo.id}"
                if isinstance(hijo, ast.Attribute):
                    assert hijo.attr not in prohibidos, f"{n.name} toca {hijo.attr}"
    assert vistas == puras, f"no se revisaron todas: faltan {puras - vistas}"


def test_no_se_importa_nada_de_Place(filas, contexto):
    """`app/rutas.py` es Place y sus ayudas de evidencia estan tipadas sobre su propia
    materia. Importarlas aqui acoplaria Property a Place por comodidad."""
    fuente = pathlib.Path(adaptador.__file__).read_text(encoding="utf-8")
    assert "app.rutas" not in fuente and "from app import rutas" not in fuente


# ── (I) EL ALCANCE DE ESTA UNIDAD, VIGILADO ──────────────────────────────────


def test_esta_fixture_NO_acredita_los_40_activos_de_produccion(congelado):
    """R0 NO mide «40 activos reales → 40 objetos validos». Estas filas son SINTETICAS y
    cubren variedad material, no el censo de produccion. Dar una cosa por la otra daria por
    acreditada una medicion que no se hizo."""
    assert len(congelado["filas"]) == 12
    texto = " ".join(congelado["_por_que_existe"])
    assert "NO ES UNA CAPTURA DE PRODUCCION" in texto
    assert "40 activos vivos" in texto
