"""PLAN04-1.6 - Fixtures del loop: 1 buyer + 10 properties + 10 places, congelados.

QUE SE PRUEBA, Y POR QUE ASI

El dataset del loop existe para que F3 pueda ejecutarse de forma reproducible sobre un
material fijo. Si se escribiera a mano, no derivaria de los productores: un cambio en
`ensamblar_place_context` o en `ensamblar_property_context` no lo romperia, y el dataset
no certificaria nada. Por eso aqui hay DOS ficheros y no uno:

    loop_1_6_material.json   ENTRADA congelada (sintetica)
              |
              v   productores REALES, solo superficie publica
    loop_1_6_dataset.json    GOLDEN congelado

y la prueba central reconstruye el golden desde el material y lo compara BYTE A BYTE.

EL RIESGO DE ESTA UNIDAD ES LA TAUTOLOGIA. Un "byte a byte" que compara un objeto consigo
mismo dentro del mismo proceso no puede fallar por ninguna de las causas que importan:
otro interprete, otra semilla de hash, otro emparejamiento, otro byte de material. Por eso
cada asercion de reproducibilidad tiene aqui su mitad NEGATIVA: se rompe algo a proposito
y se exige que la prueba lo note.

CERO RED, CERO BASE DE DATOS, CERO PII. El material es sintetico y no procede del censo
real: esa evidencia es y sigue siendo PLAN04-1.4-A1.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import uuid
from datetime import datetime
from decimal import Decimal

import pydantic
import pytest

from app.buyer.reductor import evidence_id_determinista
from app.contracts.buyer_v0 import (
    BuyerContextV0,
    CriterionOrigin,
    CriterionStatus,
    DecisionCriterionV0,
    FieldEvidence,
    Financial,
    Objective,
    Operator,
    PropertyRequirements,
)
from app.contracts.common_v0 import Money
from app.contracts.evidence_v0 import EvidenceRefV0, PersistencePolicy, SourceType
from app.contracts.place_v0 import PlaceContextV0
from app.contracts.property_v0 import PropertyContextV0
from app.decision.context import place_id_de_punto
from app.inventario import ContextoDeLectura, ensamblar_property_context
from app.rutas import MateriaDeZona, ensamblar_place_context

_AQUI = pathlib.Path(__file__).parent
MATERIAL = _AQUI / "fixtures" / "loop_1_6_material.json"
GOLDEN = _AQUI / "fixtures" / "loop_1_6_dataset.json"

CLAVES_DEL_CONTENEDOR = ("buyer", "properties", "places", "links")


# ── materializacion de los tipos que JSON no tiene ───────────────────────────


def materializar(v):
    if isinstance(v, dict):
        if "__uuid__" in v:
            return uuid.UUID(v["__uuid__"])
        if "__decimal__" in v and "currency" not in v:
            return Decimal(v["__decimal__"])
        if "__naive__" in v:
            return datetime.fromisoformat(v["__naive__"])
        return {k: materializar(x) for k, x in v.items()}
    if isinstance(v, list):
        return [materializar(x) for x in v]
    return v


def cargar_material() -> dict:
    return json.loads(MATERIAL.read_text(encoding="utf-8"))


def _instantes(material: dict) -> dict:
    inst = material["_instantes_congelados"]
    return {
        "buyer": datetime.fromisoformat(inst["buyer_updated_at"]),
        "property": datetime.fromisoformat(inst["property_snapshot_at"]),
        "place": datetime.fromisoformat(inst["place_recuperado_en"]),
        "moneda": inst["moneda"],
    }


# ── construccion del dataset, SOLO por superficie publica ────────────────────


def _evidencia_declarada(buyer_id: str, msg_id: str, ruta: str,
                         instante: datetime) -> EvidenceRefV0:
    """Evidencia del comprador, con la MISMA identidad determinista que usa el reductor.

    No se inventa un segundo esquema: `evidence_id_determinista` es publico en
    `app/buyer/reductor.py` y es `uuid5`, asi que la prueba puede rederivarlo por su cuenta.
    """
    return EvidenceRefV0(
        evidence_id=evidence_id_determinista(buyer_id, msg_id, ruta),
        source_type=SourceType.USER_DECLARED,
        source_id=msg_id,
        observed_at=None,
        retrieved_at=instante,
        methodology="declaracion del comprador en el material sintetico de PLAN04-1.6",
        persistence_policy=PersistencePolicy.PERSISTABLE,
    )


def _criterio(spec: dict, buyer_id: str, msg_id: str,
              instante: datetime) -> DecisionCriterionV0:
    return DecisionCriterionV0(
        criterion_id=spec["criterion_id"],
        dimension=spec["dimension"],
        operator=Operator(spec["operator"]),
        value=spec["value"],
        unit=spec["unit"],
        origin=CriterionOrigin(spec["origin"]),
        status=CriterionStatus.ACTIVE,
        evidence=(_evidencia_declarada(buyer_id, msg_id, spec["ruta_evidencia"], instante),),
    )


def construir_buyer(material: dict) -> BuyerContextV0:
    """El comprador, desde los contratos publicos. Sin `commute_anchors` a proposito:
    `label` y `raw_location` son donde entraria la direccion real de una persona."""
    b = material["buyer"]
    inst = _instantes(material)
    bid, msg = b["buyer_id"], b["source_message_id_sintetico"]
    return BuyerContextV0(
        buyer_id=bid,
        objective=Objective(b["objective"]),
        financial=Financial(budget_max=Money(
            amount=Decimal(b["budget_max"]["__decimal__"]),
            currency=b["budget_max"]["currency"])),
        property_requirements=PropertyRequirements(
            bedrooms_min=b["bedrooms_min"],
            pets_allowed_required=b["pets_allowed_required"]),
        hard_constraints=tuple(_criterio(s, bid, msg, inst["buyer"])
                               for s in b["hard_constraints"]),
        soft_preferences=tuple(_criterio(s, bid, msg, inst["buyer"])
                               for s in b["soft_preferences"]),
        field_evidence=tuple(
            FieldEvidence(field=ruta,
                          evidence=_evidencia_declarada(bid, msg, ruta, inst["buyer"]))
            for ruta in b["field_evidence_rutas"]),
        updated_at=inst["buyer"],
    )


def construir_properties(material: dict) -> list[PropertyContextV0]:
    """Las 10 properties, por el productor REAL de 1.4. Orden canonico: property_id."""
    inst = _instantes(material)
    contexto = ContextoDeLectura(snapshot_at=inst["property"], moneda=inst["moneda"])
    objetos = [
        ensamblar_property_context(
            {k: materializar(v) for k, v in fila.items() if k != "_caso"}, contexto)
        for fila in material["properties"]
    ]
    return sorted(objetos, key=lambda p: p.property_id)


def _materia_de(bloque: dict, instante: datetime) -> MateriaDeZona:
    """Un bloque congelado -> `MateriaDeZona`. La dataclass es PUBLICA; no se importa
    ni un privado de `app/rutas.py`."""
    servicios = [dict(s) for s in bloque["servicios"]]
    transporte = next((s for s in servicios if s.get("cat") == "transporte"), None)
    return MateriaDeZona(
        lat=bloque["lat"], lon=bloque["lon"],
        lugar=dict(bloque["lugar"]), walk=dict(bloque["walk"]),
        servicios=servicios,
        se_consultaron_servicios=bloque["se_consultaron_servicios"],
        transporte=transporte,
        transporte_distancia_m=bloque["transporte_distancia_m"],
        transporte_minutos=bloque["transporte_minutos"],
        transporte_ruta_medida=bloque["transporte_ruta_medida"],
        recuperado_en=instante,
    )


def construir_places(material: dict) -> list[PlaceContextV0]:
    """Los 10 lugares, por el productor REAL de 1.2. Orden canonico: place_id derivado.

    El `place_id` NO se escribe dentro del objeto: `ensamblar_place_context` no lo produce
    y rellenarlo aqui seria falsificar la salida del productor. Se DERIVA para ordenar y
    para enlazar, que es lo que hace el oraculo.
    """
    instante = _instantes(material)["place"]
    objetos = [_materia_de(b, instante) for b in material["places"]]
    lugares = [ensamblar_place_context(m) for m in objetos]
    return sorted(lugares, key=lambda pl: place_id_de_punto(pl.location.lat, pl.location.lon))


def construir_links(properties, places) -> list[dict]:
    """property_id -> place_id_de_punto(lat, lon) -> el place correspondiente.

    El indice es explicito para que la flecha se pueda seguir sin recalcular nada, y la
    prueba negativa pueda romperla.

    ORDEN DECLARADO: los enlaces HEREDAN el orden canonico de `properties`, que ya viene
    ordenado por `property_id`. No se vuelven a ordenar aqui: un `sorted()` sobre una lista
    que siempre llega ordenada es una guarda que nunca se ejerce —el arnes de mutacion la
    destapo naciendo INERTE— y una guarda inerte es peor que ninguna, porque aparenta
    proteger algo.
    """
    por_place_id = {
        place_id_de_punto(pl.location.lat, pl.location.lon): i
        for i, pl in enumerate(places)
    }
    enlaces = []
    for p in properties:
        pid = place_id_de_punto(p.location.lat, p.location.lon)
        enlaces.append({"property_id": p.property_id, "place_id": pid,
                        "place_index": por_place_id[pid]})
    return enlaces


def construir_contenedor(material: dict) -> dict:
    properties = construir_properties(material)
    places = construir_places(material)
    return {
        "buyer": json.loads(construir_buyer(material).model_dump_json()),
        "properties": [json.loads(p.model_dump_json()) for p in properties],
        "places": [json.loads(pl.model_dump_json()) for pl in places],
        "links": construir_links(properties, places),
    }


def serializar(contenedor: dict) -> str:
    """LA forma canonica, definida en un solo sitio.

    `model_dump_json` de pydantic fija el orden de campos (el de declaracion) y serializa
    `Decimal` como CADENA, de modo que la escala es parte del dato: "1250.5" y "1250.50"
    son datasets distintos. `json.dumps` con `sort_keys=False` respeta ese orden.
    """
    return json.dumps(contenedor, ensure_ascii=False, indent=2) + "\n"


def huella(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


# ═════════════════════════════════════════════════════════════════════════════
# (A) RECONSTRUCCION: material -> golden, byte a byte
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def material() -> dict:
    return cargar_material()


@pytest.fixture(scope="module")
def texto_reconstruido(material) -> str:
    return serializar(construir_contenedor(material))


def leer_golden_canonico() -> str:
    """El golden, leido a BYTES y normalizado en un solo aspecto: el fin de linea.

    Por que la normalizacion es necesaria y no una trampa: el repositorio tiene
    `core.autocrlf=true`, asi que git guarda LF en el objeto y entrega CRLF en el arbol de
    trabajo de Windows. Comparar los bytes crudos del fichero mediria el sistema operativo
    del que corre las pruebas, no el dataset. Lo que se congela es el TEXTO canonico —que
    no contiene ni un CR, y hay una prueba que lo exige—; el blob que git almacena coincide
    byte a byte con el.

    Se hace explicito en vez de delegarlo al modo texto de `read_text`, para que quien lea
    esto sepa exactamente que se esta comparando.
    """
    return GOLDEN.read_bytes().replace(b"\r\n", b"\n").decode("utf-8")


def test_el_material_reconstruye_el_golden_BYTE_A_BYTE(texto_reconstruido):
    """La prueba central. El golden NO se regenera nunca automaticamente: si esto falla,
    o cambio el material, o cambio un productor, y las dos cosas exigen mirarlas."""
    assert texto_reconstruido == leer_golden_canonico(), (
        "el dataset reconstruido difiere del golden. NO regeneres el golden para que pase: "
        "averigua si cambio el material o cambio un productor"
    )


def test_el_texto_canonico_no_depende_del_fin_de_linea_del_sistema(texto_reconstruido):
    """La forma canonica usa solo LF. Si algun dia trajera CR, el dataset dejaria de ser
    el mismo en Windows y en Linux y el `byte a byte` se volveria una afirmacion local."""
    assert "\r" not in texto_reconstruido
    assert texto_reconstruido.endswith("}\n")


def test_dos_reconstrucciones_en_este_proceso_coinciden(material, texto_reconstruido):
    """Necesaria pero NO suficiente: dentro de un proceso no se observa la deriva entre
    procesos. La que de verdad acredita es la de la seccion (B)."""
    assert serializar(construir_contenedor(material)) == texto_reconstruido


def test_el_contenedor_tiene_exactamente_las_cuatro_claves_canonicas(texto_reconstruido):
    assert tuple(json.loads(texto_reconstruido)) == CLAVES_DEL_CONTENEDOR


def test_el_runtime_usa_la_version_de_pydantic_fijada_por_el_proyecto():
    """El `byte a byte` se compara contra la salida de un serializador. Si el serializador
    cambia, el fallo tiene que verse AQUI y no aguas abajo."""
    pin = [l for l in (_AQUI.parent / "requirements.txt").read_text(
        encoding="utf-8").splitlines() if l.startswith("pydantic==")]
    assert pin == ["pydantic==2.10.3"], f"el pin cambio: {pin}"
    assert pydantic.VERSION == "2.10.3", (
        f"pydantic instalado {pydantic.VERSION} != pin {pin}: el golden mediria la maquina"
    )


# ═════════════════════════════════════════════════════════════════════════════
# (B) DOS PROCESOS, SEMILLAS DE HASH DISTINTAS
# ═════════════════════════════════════════════════════════════════════════════


_HIJO = (
    "import json,sys,hashlib;"
    "sys.path.insert(0, sys.argv[1]); sys.path.insert(0, sys.argv[1] + '/tests');"
    "import test_loop_fixtures_1_6 as t;"
    "m = json.loads(open(sys.argv[2], encoding='utf-8').read());"
    "print(t.huella(t.serializar(t.construir_contenedor(m))))"
)


def _huella_en_subproceso(semilla: str, ruta_material: pathlib.Path) -> str:
    raiz = str(_AQUI.parent)
    entorno = {**os.environ, "PYTHONHASHSEED": semilla, "PYTHONIOENCODING": "utf-8",
               "POSTGRES_DB": "inerte", "POSTGRES_USER": "inerte",
               "POSTGRES_PASSWORD": "inerte"}
    entorno.pop("DATABASE_URL_OVERRIDE", None)
    r = subprocess.run([sys.executable, "-c", _HIJO, raiz, str(ruta_material)],
                       capture_output=True, text=True, env=entorno, cwd=raiz, timeout=300)
    assert r.returncode == 0, f"el subproceso fallo: {r.stderr[-600:]}"
    return r.stdout.strip()


def test_dos_procesos_con_semillas_distintas_dan_el_MISMO_dataset(texto_reconstruido):
    """Lo que la autocomparacion no puede dar. `hash()` de Python va salado por proceso;
    cualquier orden que dependiera de un `set` derivaria aqui y en ningun otro sitio."""
    uno = _huella_en_subproceso("0", MATERIAL)
    otro = _huella_en_subproceso("12345", MATERIAL)
    assert uno == otro
    assert uno == huella(texto_reconstruido), "el subproceso no produce el mismo dataset"


def test_la_prueba_de_subproceso_SI_puede_detectar_divergencia(tmp_path, material):
    """La mitad negativa, y sin ella la de arriba no vale: se le da al subproceso un
    material alterado y se exige que la huella CAMBIE. Un arnes que no puede fallar no
    esta midiendo."""
    alterado = copy.deepcopy(material)
    alterado["places"][0]["walk"]["walk_score"] = 79
    ruta = tmp_path / "material_alterado.json"
    ruta.write_text(json.dumps(alterado, ensure_ascii=False), encoding="utf-8")
    assert _huella_en_subproceso("0", ruta) != _huella_en_subproceso("0", MATERIAL)


# ═════════════════════════════════════════════════════════════════════════════
# (C) EL ENLACE property <-> place, con su mitad negativa
# ═════════════════════════════════════════════════════════════════════════════


def test_cada_property_apunta_al_place_de_SUS_coordenadas(material):
    properties = construir_properties(material)
    places = construir_places(material)
    enlaces = construir_links(properties, places)

    assert len(enlaces) == 10
    for p, e in zip(properties, enlaces):
        assert e["property_id"] == p.property_id
        esperado = place_id_de_punto(p.location.lat, p.location.lon)
        assert e["place_id"] == esperado
        lugar = places[e["place_index"]]
        assert place_id_de_punto(lugar.location.lat, lugar.location.lon) == esperado
        assert (lugar.location.lat, lugar.location.lon) == (p.location.lat, p.location.lon)


def test_rotar_UN_emparejamiento_rompe_la_verificacion(material):
    """La mitad negativa del enlace. Si esto no rompiera, la comprobacion de arriba estaria
    aceptando cualquier asignacion."""
    properties = construir_properties(material)
    places = construir_places(material)
    enlaces = construir_links(properties, places)

    rotados = [dict(e) for e in enlaces]
    rotados[0]["place_index"] = (rotados[0]["place_index"] + 1) % len(places)

    with pytest.raises(AssertionError):
        for p, e in zip(properties, rotados):
            lugar = places[e["place_index"]]
            assert (lugar.location.lat, lugar.location.lon) == (p.location.lat, p.location.lon)


def test_los_places_NO_traen_place_id_fabricado(material):
    """`ensamblar_place_context` no produce `place_id`, y esta unidad no se lo inventa: el
    id vive en el enlace, derivado por el oraculo."""
    assert all(pl.place_id is None for pl in construir_places(material))


# ═════════════════════════════════════════════════════════════════════════════
# (D) IDENTIDAD DE LA EVIDENCIA, rederivada de forma independiente
# ═════════════════════════════════════════════════════════════════════════════


def _evidencias(contenedor: dict) -> list[dict]:
    """Toda `EvidenceRefV0` del dataset, mire donde mire."""
    encontradas = []

    def hurgar(nodo):
        if isinstance(nodo, dict):
            if nodo.get("contract_version") == "evidence-ref/v0":
                encontradas.append(nodo)
            for v in nodo.values():
                hurgar(v)
        elif isinstance(nodo, list):
            for v in nodo:
                hurgar(v)

    hurgar(contenedor)
    return encontradas


def test_ninguna_evidencia_del_dataset_lleva_un_id_por_defecto(material):
    """`EvidenceRefV0.evidence_id` cae en `uuid4` si nadie lo pasa. Un solo objeto con el
    default y el dataset deja de ser reproducible entre corridas."""
    evidencias = _evidencias(construir_contenedor(material))
    assert evidencias, "un dataset sin ninguna evidencia no estaria probando esto"
    assert all(uuid.UUID(e["evidence_id"]).version == 5 for e in evidencias)


def test_la_evidencia_del_buyer_se_REDERIVA_de_forma_independiente(material):
    """Reimplementacion de la regla, no llamada al helper: si el esquema cambiara a `uuid4`
    o a `hash()`, esto no cuadraria ni por casualidad."""
    b = material["buyer"]
    ns = uuid.uuid5(uuid.NAMESPACE_URL, "contexto.ai/buyer/evidence/user_declared/v0")
    buyer = construir_buyer(material)
    for fe in buyer.field_evidence:
        semilla = f"{b['buyer_id']}\x1f{b['source_message_id_sintetico']}\x1f{fe.field}"
        assert fe.evidence.evidence_id == str(uuid.uuid5(ns, semilla))


def test_la_evidencia_de_lugar_se_REDERIVA_de_forma_independiente(material):
    ns = uuid.uuid5(uuid.NAMESPACE_URL, "contexto.ai/place/evidence/v0")
    instante = _instantes(material)["place"]
    for bloque, lugar in zip(material["places"], [
            ensamblar_place_context(_materia_de(b, instante)) for b in material["places"]]):
        for dim, medida in (("walkability", lugar.walkability),
                            ("nearest_transit", lugar.nearest_transit),
                            ("nearby_places", lugar.nearby_places)):
            for ev in medida.evidence:
                semilla = "\x1f".join((
                    repr(bloque["lat"]), repr(bloque["lon"]), instante.isoformat(), dim,
                    ev.source_type.value, ev.provider or "", ev.source_id or "",
                    ev.methodology, "\x1e".join(ev.limitations)))
                assert ev.evidence_id == str(uuid.uuid5(ns, semilla))


def test_quitar_una_evidencia_cambia_el_dataset(material, texto_reconstruido):
    """La desaparicion de evidencia tiene que romper el golden."""
    contenedor = construir_contenedor(material)
    contenedor["places"][0]["walkability"]["evidence"] = []
    assert serializar(contenedor) != texto_reconstruido


# ═════════════════════════════════════════════════════════════════════════════
# (E) SENSIBILIDAD: un byte del material mueve el dataset
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("mutar,que", [
    (lambda m: m["places"][0]["walk"].__setitem__("walk_score", 79), "medida de lugar"),
    (lambda m: m["places"][1]["servicios"][0].__setitem__("fuente", "google"), "origen de un POI"),
    (lambda m: m["places"][0].__setitem__("transporte_ruta_medida", False), "ruta medida"),
    (lambda m: m["properties"][0].__setitem__("precio", {"__decimal__": "780.0"}), "escala del precio"),
    (lambda m: m["_instantes_congelados"].__setitem__(
        "place_recuperado_en", "2026-09-09T12:00:01+00:00"), "instante de lugar"),
    (lambda m: m["_instantes_congelados"].__setitem__(
        "buyer_updated_at", "2026-09-09T12:00:01+00:00"), "instante del comprador"),
])
def test_cambiar_UN_dato_material_cambia_el_dataset(material, texto_reconstruido, mutar, que):
    alterado = copy.deepcopy(material)
    mutar(alterado)
    assert serializar(construir_contenedor(alterado)) != texto_reconstruido, que


def _ids_de_evidencia_de_lugar(contenedor: dict) -> set:
    return {e["evidence_id"] for pl in contenedor["places"] for e in _evidencias(pl)}


def test_cambiar_el_instante_de_lugar_cambia_los_ids_de_evidencia_DE_LUGAR(material):
    """No basta con que cambie el JSON: el instante entra en la SEMILLA del uuid5 de lugar,
    asi que tiene que mover esos identificadores.

    Se acota a LUGAR a proposito. Los ids del comprador NO dependen del instante y eso es
    deliberado en el reductor: representan «la evidencia de este mensaje para este campo»,
    de modo que un replay del mismo mensaje conserva el id y la divergencia se ve en el
    contexto en vez de esconderse tras dos asas distintas. Exigir que TODO cambiara habria
    sido medir mal, no medir mas.
    """
    alterado = copy.deepcopy(material)
    alterado["_instantes_congelados"]["place_recuperado_en"] = "2026-09-09T12:00:01+00:00"
    antes = _ids_de_evidencia_de_lugar(construir_contenedor(material))
    despues = _ids_de_evidencia_de_lugar(construir_contenedor(alterado))
    assert antes and antes.isdisjoint(despues)


def test_los_ids_del_comprador_NO_dependen_del_instante_de_lugar(material):
    """La otra mitad de la regla anterior, escrita para que nadie la 'arregle' por error."""
    alterado = copy.deepcopy(material)
    alterado["_instantes_congelados"]["place_recuperado_en"] = "2026-09-09T12:00:01+00:00"
    ids = lambda m: {fe.evidence.evidence_id for fe in construir_buyer(m).field_evidence}  # noqa: E731
    assert ids(material) == ids(alterado)


# ═════════════════════════════════════════════════════════════════════════════
# (F) ORDEN CANONICO
# ═════════════════════════════════════════════════════════════════════════════


def test_el_orden_es_una_funcion_declarada_del_dato(texto_reconstruido):
    c = json.loads(texto_reconstruido)
    ids = [p["property_id"] for p in c["properties"]]
    assert ids == sorted(ids)
    assert [e["property_id"] for e in c["links"]] == sorted(ids)
    place_ids = [e["place_id"] for e in c["links"]]
    assert len(set(place_ids)) == 10
    indices = [c["links"][i]["place_index"] for i in range(10)]
    assert sorted(indices) == list(range(10)), "los 10 places se usan una vez cada uno"


def test_permutar_el_orden_cambia_el_dataset(material, texto_reconstruido):
    contenedor = construir_contenedor(material)
    contenedor["properties"] = list(reversed(contenedor["properties"]))
    assert serializar(contenedor) != texto_reconstruido


# ═════════════════════════════════════════════════════════════════════════════
# (G) MATERIAL NO TRIVIAL: la fixture hueca no pasa
# ═════════════════════════════════════════════════════════════════════════════


def test_el_dataset_no_es_trivial(texto_reconstruido):
    c = json.loads(texto_reconstruido)
    assert len(c["properties"]) == 10 and len(c["places"]) == 10
    assert len({p["property_id"] for p in c["properties"]}) == 10
    assert len({(pl["location"]["lat"], pl["location"]["lon"]) for pl in c["places"]}) == 10

    b = c["buyer"]
    assert b["objective"] != "unknown"
    assert b["financial"]["budget_max"] is not None
    assert len(b["hard_constraints"]) >= 2 and b["soft_preferences"]
    assert b["property_requirements"]["bedrooms_min"] is not None
    assert b["field_evidence"], "un comprador sin procedencia no acredita nada"

    con_precio = [p for p in c["properties"] if p["transaction"] and p["transaction"]["price"]]
    assert len(con_precio) >= 7
    con_atributos = [p for p in c["properties"] if p["attributes"]]
    assert len(con_atributos) == 10
    assert any(pl["walkability"]["status"] == "insufficient_evidence" for pl in c["places"])
    assert any(pl["nearest_transit"]["status"] == "available" for pl in c["places"])


def test_la_escala_del_precio_sobrevive_literal(texto_reconstruido):
    """`Decimal` se serializa como cadena: la escala es parte del dato. Si alguien lo
    pasara por `float`, "1250.5" y "780.00" dejarian de estar."""
    assert '"amount":"780.00"' in texto_reconstruido.replace(" ", "")
    assert '"amount":"1250.5"' in texto_reconstruido.replace(" ", "")


def test_un_dataset_vacio_no_pasaria_las_guardas(material):
    """La fixture hueca, hecha explicita: si el material se vaciara, la construccion no
    produce nada y las guardas de arriba caen."""
    vacio = copy.deepcopy(material)
    vacio["properties"] = []
    vacio["places"] = []
    contenedor = construir_contenedor(vacio)
    assert contenedor["properties"] == [] and contenedor["links"] == []
    with pytest.raises(AssertionError):
        c = json.loads(serializar(contenedor))
        assert len(c["properties"]) == 10


# ═════════════════════════════════════════════════════════════════════════════
# (H) ALCANCE Y DATOS SENSIBLES
# ═════════════════════════════════════════════════════════════════════════════


def test_el_material_se_declara_SINTETICO_y_no_acredita_produccion(material):
    texto = " ".join(material["_por_que_existe"])
    assert "TODO ES SINTETICO" in texto
    assert "NO acredita inventario de produccion" in texto
    assert "A1" in texto
    assert material["_instantes_congelados"]["_currency_provenance"].startswith("NOT MEASURED")


def test_el_buyer_no_arrastra_PII(material):
    """Los sitios por donde entraria un dato personal, vigilados uno a uno."""
    b = material["buyer"]
    assert "sintetico" in b["buyer_id"]
    assert not b["buyer_id"].startswith("session:")
    assert "sintetico" in b["source_message_id_sintetico"]
    buyer = construir_buyer(material)
    assert buyer.mobility.commute_anchors == (), (
        "sin anclas: `label` y `raw_location` son donde entraria una direccion real"
    )


def test_ninguna_property_reutiliza_un_id_del_censo_real(material):
    """Los ids del censo real son UUID de produccion. Los de aqui llevan un prefijo
    reconocible y declarado, para que nadie confunda un dataset sintetico con el inventario."""
    ids = [f["id"]["__uuid__"] for f in material["properties"]]
    assert len(set(ids)) == 10
    assert all(i.startswith("1a000000-0000-4000-8000-") for i in ids)


def test_esta_unidad_no_toca_las_fixtures_ajenas():
    """1.2 y 1.4 tienen sus propias guardas de alcance; 1.6 no las pisa."""
    assert (_AQUI / "fixtures" / "place_context_1_2_quito.json").exists()
    assert (_AQUI / "fixtures" / "inventario_1_4_filas.json").exists()
    propia = json.loads(MATERIAL.read_text(encoding="utf-8"))
    assert "filas" not in propia, "el material de 1.6 no imita el de 1.4"
    assert set(propia) >= {"buyer", "properties", "places"}
