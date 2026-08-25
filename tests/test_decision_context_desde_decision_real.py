"""E2.2 · primer subpaso — un `DecisionContextV0` real, sin HTTP y sin UI.

LO QUE DEMUESTRA ESTE ARCHIVO, y nada más:

    cálculo determinista legacy  →  DecisionContextV0 válido  →  salida legacy intacta

Nadie consume el objeto todavía. Invertir la autoridad del ranking es el segundo subpaso;
mezclarlo aquí haría imposible saber cuál de las dos cosas rompió la paridad si algo se
cae.

El insumo es la forma REAL del repo: una fila como la devuelve `_fetch_cards_rows` y el
resultado tal cual de `calcular_encaje`. Nada de diccionarios inventados para que encaje.
"""

import importlib
import json
import sys
from datetime import datetime, timezone

import pytest

from app.contracts.common_v0 import Objective
from app.contracts.decision_v0 import DecisionContextV0
from app.decision.context import (
    PROVIDER_ID_LOCAL,
    CoordenadasAusentes,
    EncajeSinVersion,
    assemble_decision_context_v0,
    place_id_de_punto,
)
from app.encaje import SCORE_VERSION, calcular_encaje
from app.decision.assembler import _senales_encaje

AHORA = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)

# Una fila con la forma que produce `_fetch_cards_rows` (ver el SQL del assembler).
FILA = {
    "id": "11111111-2222-3333-4444-555555555555",
    "direccion": "Av. Coruña y San Ignacio, La Floresta",
    "tipo_activo": "Departamento",
    "operacion": "ARRIENDO",
    "precio": 380,
    "imagen_url": None,
    "caminabilidad": 95,
    "caminabilidad_fuente": "osm",
    "ruido": "BAJO",
    "vegetacion": 42,
    "lat": -0.1807,
    "lon": -78.4867,
    "caracteristicas": {"num_dormitorios": 2, "acepta_mascotas": True},
    "servicios_cercanos": "🌳 Parque a ~300 m",
    "conectividad": "🚇 Metro a ~500 m (7 min a pie)",
}

PREFS = {
    "operacion": "arriendo",
    "tipo_inmueble": "departamento",
    "presupuesto_max": 700,
    "caminable": True,
    "acepta_mascotas": True,
}


def _encaje_real(row=FILA, prefs=PREFS):
    """El resultado del motor de verdad, no un stub."""
    car = row.get("caracteristicas") or {}
    return calcular_encaje(prefs, _senales_encaje(row, car))


def _construir(**cambios):
    base = dict(
        row=FILA,
        preferencias=PREFS,
        encaje=_encaje_real(),
        session_id="s-42",
        decision_id="d-1",
        created_at=AHORA,
    )
    base.update(cambios)
    return assemble_decision_context_v0(**base)


# ── el objeto se construye desde datos reales ────────────────────────────────────


def test_un_contexto_de_decision_real_se_construye():
    d = _construir()
    assert isinstance(d, DecisionContextV0)
    assert d.contract_version == "decision-context-v0"


def test_el_score_version_viene_del_motor_y_no_se_inventa():
    """Si esto cambia, dos números producidos por reglas distintas dejarían de poder
    distinguirse — que es justo lo que `score_version` existe para impedir."""
    d = _construir()
    assert d.score_version == SCORE_VERSION == "encaje-v0"


def test_la_identidad_del_inmueble_es_el_par_de_e1_3():
    d = _construir()
    assert d.property.identidad_externa == (PROVIDER_ID_LOCAL, FILA["id"])


# ── los puentes transitorios se declaran, no se disfrazan ────────────────────────


def test_el_comprador_es_la_sesion_y_lo_dice():
    """No es la identidad permanente del comprador: es la sesión. F3 lo sustituye."""
    d = _construir(session_id="abc")
    assert d.buyer.buyer_id == "session:abc"
    assert d.buyer.context_revision is None, "no hay store con historial que citar (F3)"


def test_lo_que_no_existe_todavia_se_declara_ausente():
    """Ninguno de estos se rellena para que el objeto "quede completo"."""
    d = _construir()
    assert d.trace_id is None, "no hay instrumentación (F6)"
    assert d.recommended_next_action is None, "el flujo actual no emite una acción tipada"
    assert d.explanation is None, "todavía no hay prosa que verificar (E2.4)"
    assert d.eligibility is None and d.match is None, "sin evidencia que citar (E2.3)"
    assert d.strengths == () and d.tradeoffs == () and d.uncertainties == ()
    assert d.ranking == (), "la autoridad del ranking es el segundo subpaso"
    assert d.anchor_ids == (), "no hay anclas de trayecto hasta F3"


# ── objective: solo el mapeo inequívoco ──────────────────────────────────────────


@pytest.mark.parametrize(
    "operacion,esperado",
    [
        ("arriendo", Objective.RENT),
        ("venta", Objective.BUY),
        ("ARRIENDO", Objective.RENT),
        ("  Venta  ", Objective.BUY),
        (None, Objective.UNKNOWN),
        ("", Objective.UNKNOWN),
        ("permuta", Objective.UNKNOWN),
    ],
)
def test_el_objetivo_solo_sale_de_lo_que_la_persona_declaro(operacion, esperado):
    d = _construir(preferencias={**PREFS, "operacion": operacion})
    assert d.objective is esperado


def test_sin_preferencias_el_objetivo_es_desconocido():
    assert _construir(preferencias=None, encaje=None).objective is Objective.UNKNOWN


def test_invest_no_se_infiere_nunca():
    """No tiene ninguna fuente en el flujo actual: producirlo sería inventar una intención
    que nadie declaró."""
    objetivos = {
        _construir(preferencias={**PREFS, "operacion": op}).objective
        for op in ("arriendo", "venta", "inversion", "invertir", None)
    }
    assert Objective.INVEST not in objetivos


# ── place_id: el borde que puede mentir en silencio ──────────────────────────────


def test_con_coordenadas_validas_hay_place_id_determinista():
    d = _construir()
    assert d.place.place_id.startswith("point-v0:")


def test_las_mismas_coordenadas_dan_el_mismo_id_siempre():
    """`hashlib`, no `hash()`: este último está aleatorizado por proceso y daría un id
    distinto en cada arranque."""
    assert place_id_de_punto(-0.1807, -78.4867) == place_id_de_punto(-0.1807, -78.4867)
    # Y el valor es estable entre procesos, no solo dentro de este.
    assert place_id_de_punto(-0.1807, -78.4867) == "point-v0:" + __import__("hashlib").sha256(
        b"-0.180700,-78.486700"
    ).hexdigest()[:16]


def test_coordenadas_distintas_dan_ids_distintos():
    assert place_id_de_punto(-0.1807, -78.4867) != place_id_de_punto(-0.1808, -78.4867)


def test_la_normalizacion_absorbe_ruido_por_debajo_del_decimetro():
    """Dos lecturas del mismo punto no deben producir dos lugares."""
    assert place_id_de_punto(-0.18070000001, -78.4867) == place_id_de_punto(-0.1807, -78.4867)


@pytest.mark.parametrize(
    "lat,lon",
    [
        (None, -78.4867),
        (-0.1807, None),
        (None, None),
        ("-0.18", -78.4867),
        (True, -78.4867),      # bool es subclase de int: un True daría un id válido
        (-0.1807, False),
    ],
)
def test_sin_coordenadas_validas_el_builder_se_niega_en_voz_alta(lat, lon):
    """LA PRUEBA CENTRAL DE ESTE SUBPASO. Un `place_id` fabricado VALIDARÍA contra el
    contrato: Pydantic comprueba que sea un string no vacío, no que corresponda a un lugar
    real. Una mentira semántica bien tipada pasa todos los tests.

    Por eso el builder levanta en vez de improvisar.
    """
    with pytest.raises(CoordenadasAusentes):
        _construir(row={**FILA, "lat": lat, "lon": lon})


def test_no_inventa_ni_devuelve_none_ni_excluye_en_silencio():
    """Las tres salidas cómodas, descartadas explícitamente. La tercera es la más
    peligrosa: excluir el candidato también cambia comportamiento visible."""
    row_sin_coords = {**FILA, "lat": None, "lon": None}
    try:
        resultado = _construir(row=row_sin_coords)
    except CoordenadasAusentes as exc:
        assert "no se fabrica un id" in str(exc)
        assert "no se excluye en silencio" in str(exc)
    else:
        pytest.fail(f"devolvió {resultado!r} en vez de negarse: eso es fabricar o silenciar")


def test_una_coordenada_fuera_de_rango_tampoco_pasa():
    with pytest.raises(CoordenadasAusentes):
        place_id_de_punto(91.0, 0.0)


def test_point_v0_no_pretende_ser_identidad_canonica():
    """Sin geocodificación inversa, sin proveedor y sin nombre de barrio. F4 lo
    reemplazará; que el prefijo lo diga es lo que impide que alguien lo persista como si
    fuera definitivo."""
    pid = place_id_de_punto(-0.1807, -78.4867)
    assert pid.startswith("point-v0:")
    assert "quito" not in pid.lower() and "floresta" not in pid.lower()


# ── determinismo y serialización ─────────────────────────────────────────────────


def test_mismos_insumos_mismo_objeto_serializado():
    """Sin normalizar nada: lo volátil se inyecta, así que la comparación es total."""
    uno = _construir()
    dos = _construir()
    assert uno == dos
    assert json.dumps(uno.model_dump(mode="json"), sort_keys=True) == json.dumps(
        dos.model_dump(mode="json"), sort_keys=True
    )


def test_el_ida_y_vuelta_por_json_lo_conserva():
    d = _construir()
    assert DecisionContextV0.model_validate(d.model_dump(mode="json")) == d


# ── sin HTTP, sin UI ─────────────────────────────────────────────────────────────


def test_el_objeto_se_construye_sin_fastapi_cargado():
    """El Gate F2 lo pide literal: "el primer DecisionContextV0 real puede generarse sin
    FastAPI y sin UI". Se comprueba que el módulo no arrastre fastapi al importarse en un
    intérprete donde no estaba."""
    import subprocess

    codigo = (
        "import sys\n"
        "import app.decision.context as c\n"
        "assert 'fastapi' not in sys.modules, sorted(m for m in sys.modules if 'fastapi' in m)\n"
        "assert 'app.routers' not in sys.modules\n"
        "print(c.place_id_de_punto(-0.1807, -78.4867))\n"
    )
    r = subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
        env={"POSTGRES_DB": "test", "POSTGRES_USER": "test", "POSTGRES_PASSWORD": "test",
             "PATH": __import__("os").environ.get("PATH", ""),
             "SYSTEMROOT": __import__("os").environ.get("SYSTEMROOT", "")},
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip().startswith("point-v0:")


def test_el_modulo_no_importa_fastapi_ni_routers():
    """Estructural, por AST — la lección de F1 y de E2.1: un grep da por bueno lo que no
    lo está."""
    import ast
    import pathlib

    import app.decision.context as modulo

    arbol = ast.parse(pathlib.Path(modulo.__file__).read_text(encoding="utf-8"))
    modulos = {n.module or "" for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)}
    modulos |= {a.name for n in ast.walk(arbol) if isinstance(n, ast.Import) for a in n.names}
    assert not [m for m in modulos if m.startswith(("fastapi", "app.routers"))]


# ── la salida legacy no se toca ──────────────────────────────────────────────────


def test_construir_el_contexto_no_altera_la_tarjeta_legacy():
    """El objeto se arma a partir del MISMO resultado del motor que alimenta la card, y
    ese resultado no se muta por el camino."""
    enc_antes = _encaje_real()
    copia = json.dumps(enc_antes, sort_keys=True, default=str)
    _construir(encaje=enc_antes)
    assert json.dumps(enc_antes, sort_keys=True, default=str) == copia


def test_nadie_consume_todavia_el_contexto():
    """Este subpaso NO invierte la autoridad. Si el assembler ya lo importara, la paridad
    de las 40 pruebas legacy dejaría de significar lo que significa."""
    import ast
    import pathlib

    import app.decision.assembler as assembler

    arbol = ast.parse(pathlib.Path(assembler.__file__).read_text(encoding="utf-8"))
    modulos = {n.module or "" for n in ast.walk(arbol) if isinstance(n, ast.ImportFrom)}
    assert "app.decision.context" not in modulos


# ── score_version: el motor dice bajo qué reglas puntuó, o no puntúa ─────────────


def test_sin_motor_la_version_es_la_del_motor_actual():
    """`encaje=None` es legítimo: no hubo cálculo, así que la versión que corresponde es
    la del motor vigente."""
    assert _construir(preferencias=None, encaje=None).score_version == SCORE_VERSION


def test_el_encaje_real_trae_su_version_explicita():
    assert _encaje_real()["score_version"] == SCORE_VERSION


_AUSENTE = object()


@pytest.mark.parametrize("version", [_AUSENTE, None, "", "   ", 1])
def test_un_encaje_sin_version_falla_en_voz_alta(version):
    """MISMA FAMILIA QUE `place_id`. Si el motor puntuó pero perdió su versión, caer al
    `SCORE_VERSION` actual etiquetaría el número con una procedencia que nadie declaró —
    y dos scores producidos por reglas distintas dejarían de poder distinguirse, que es
    justo lo que el campo existe para impedir."""
    roto = dict(_encaje_real())
    if version is _AUSENTE:
        del roto["score_version"]   # la clave DESAPARECE, no se sobrescribe
    else:
        roto["score_version"] = version
    with pytest.raises(EncajeSinVersion):
        _construir(encaje=roto)


def test_una_version_distinta_se_usa_tal_cual_y_no_se_normaliza():
    """Si mañana el motor devuelve `encaje-v1`, la decisión registra `encaje-v1`.
    Coercionarlo al valor esperado convertiría un cambio de reglas en un dato invisible."""
    d = _construir(encaje={**_encaje_real(), "score_version": "encaje-v1"})
    assert d.score_version == "encaje-v1"


def test_el_builder_ya_no_asume_la_version_por_defecto():
    """Regresión del atajo que tenía el subpaso 1: `(encaje or {}).get(...) or
    SCORE_VERSION` era cómodo y ocultaba un encaje mal formado."""
    import inspect

    import app.decision.context as ctx

    fuente = inspect.getsource(ctx.assemble_decision_context_v0)
    assert "or SCORE_VERSION" not in fuente
