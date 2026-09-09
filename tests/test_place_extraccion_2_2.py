"""PLAN04-2.2-R0A - el ensamblaje de Place sale de `rutas.py` y es PURO de verdad.

QUE SE PRUEBA, Y POR QUE ASI

Una extraccion se puede fingir de cuatro maneras, y las cuatro dejan la suite en verde si
solo se mira la salida:

  1. mover el NOMBRE y dejar la responsabilidad donde estaba;
  2. mover el bloque pero arrastrar los proveedores con el;
  3. dejar una SEGUNDA implementacion en el modulo viejo;
  4. reexportar en vez de mover, y llamarlo extraccion.

Ninguna prueba de comportamiento las distingue: el objeto producido es el mismo en todos
los casos. Por eso aqui no se pregunta QUE devuelve el ensamblador —de eso ya responden las
54 pruebas de 1.2 y las 31 de 1.6, que esta unidad tiene PROHIBIDO tocar— sino DONDE vive,
QUE puede alcanzar y CON QUE se enlaza.

Las tres unicas preguntas que distinguen: el sitio de definicion leido del AST del FICHERO
(no del objeto, que `inspect` sigue a donde este), el `__module__` del objeto vivo, y el
grafo de modulos observado en un interprete limpio.
"""

from __future__ import annotations

import ast
import inspect
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

import pytest

from app import rutas
from app.place import assembler

_RAIZ = pathlib.Path(__file__).resolve().parent.parent

# Los quince simbolos del cierre transitivo de `ensamblar_place_context`, comprobado con
# el AST. No es una lista de deseos: es lo que la dependencia obliga a mover.
MOVIDOS = (
    "MateriaDeZona",
    "_NAMESPACE_EVIDENCIA_LUGAR",
    "_ORIGEN_DE_LA_CAPA_DE_POIS",
    "_METODO_PARADA",
    "_METODO_SERVICIO",
    "_SIN_ORIGEN_DECLARADO",
    "_evidencia",
    "_evidencia_de_poi",
    "_identidad_evidencia",
    "_medir_caminabilidad",
    "_medir_minutos_a_pie",
    "_medir_servicios",
    "_medir_transporte",
    "_nombre_limpio",
    "ensamblar_place_context",
)

# Lo que la CONTIGUIDAD habria arrastrado y la dependencia rechaza. Se quedan en rutas.py
# porque no son puros: `_recolectar_zona` ES el fetch y `place_context_de` lo espera.
NO_MOVIDOS = ("_recolectar_zona", "place_context_de", "_num", "analizar_zona")

FUNCIONES_PURAS = (
    "_identidad_evidencia", "_evidencia", "_evidencia_de_poi", "_nombre_limpio",
    "_medir_caminabilidad", "_medir_transporte", "_medir_minutos_a_pie",
    "_medir_servicios", "ensamblar_place_context",
)

PROHIBIDOS_EN_EL_ASSEMBLER = (
    "httpx", "engine", "AsyncSessionLocal", "text", "settings",
    "now", "utcnow", "connect", "execute",
)


def _arbol(ruta: pathlib.Path) -> ast.Module:
    return ast.parse(ruta.read_text(encoding="utf-8"))


def _definidos_en(ruta: pathlib.Path) -> set[str]:
    """Los nombres definidos EN ESE FICHERO. Del AST del fichero, no del objeto: un
    `inspect.getsource` sigue al objeto y leeria el modulo viejo si nada se movio."""
    nombres = set()
    for n in _arbol(ruta).body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nombres.add(n.name)
        elif isinstance(n, ast.Assign):
            nombres |= {t.id for t in n.targets if isinstance(t, ast.Name)}
        elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
            nombres.add(n.target.id)
    return nombres


# ═════════════════════════════════════════════════════════════════════════════
# (A) AISLAMIENTO REAL: importar Y EJECUTAR en un interprete limpio
# ═════════════════════════════════════════════════════════════════════════════

_HIJO = r"""
import sys
from datetime import datetime, timezone

from app.place.assembler import MateriaDeZona, ensamblar_place_context

materia = MateriaDeZona(
    lat=-0.1807, lon=-78.4867, lugar={}, walk={"walk_score": 70, "pois_analizados": 12},
    servicios=[{"nombre": "X", "cat": "parque", "distancia_m": 100, "fuente": "propio"}],
    se_consultaron_servicios=True, transporte=None,
    transporte_distancia_m=None, transporte_minutos=None, transporte_ruta_medida=False,
    recuperado_en=datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc),
)
objeto = ensamblar_place_context(materia)
assert objeto.walkability.value == 70.0

cargados = sorted(m for m in sys.modules
                  if m == "httpx" or m.startswith("httpx.")
                  or m == "app.database" or m.startswith("app.database.")
                  or m == "app.routers" or m.startswith("app.routers.")
                  or m == "app.agent" or m.startswith("app.agent.")
                  or m == "app.rutas")
print("CARGADOS:" + ",".join(cargados))
"""


def _correr_hijo() -> str:
    entorno = {k: v for k, v in os.environ.items()
               if k in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "PATHEXT")}
    entorno.update(POSTGRES_DB="inerte", POSTGRES_USER="inerte",
                   POSTGRES_PASSWORD="inerte", PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-c", _HIJO], capture_output=True, text=True,
                       cwd=str(_RAIZ), env=entorno, timeout=300)
    assert r.returncode == 0, f"el subproceso fallo:\n{r.stderr[-1500:]}"
    return r.stdout.strip()


def test_A_el_assembler_se_importa_y_EJECUTA_sin_red_ni_base_ni_router():
    """La unica prueba que una reexportacion no puede pasar.

    No basta con importar: se ENSAMBLA de verdad y despues se mira `sys.modules`. Un
    import diferido dentro del cuerpo —el truco que la version de solo-import no ve— se
    delata aqui, porque para entonces ya se ejecuto.
    """
    salida = _correr_hijo()
    assert salida.startswith("CARGADOS:"), salida
    cargados = [m for m in salida[len("CARGADOS:"):].split(",") if m]
    assert cargados == [], (
        f"el ensamblador arrastro modulos que no deberia: {cargados}. "
        "Si son de red o de base, la extraccion no separo nada"
    )


def test_A2_el_arnes_de_aislamiento_SI_puede_fallar():
    """La mitad negativa. Un arnes que no puede ponerse rojo no esta midiendo: se le pide
    al mismo interprete limpio que importe `app.rutas` y se exige que ENTONCES si aparezcan
    los modulos que el ensamblador no arrastra."""
    hijo = _HIJO.replace(
        "from app.place.assembler import MateriaDeZona, ensamblar_place_context",
        "import app.rutas\nfrom app.place.assembler import MateriaDeZona, ensamblar_place_context",
    )
    entorno = {k: v for k, v in os.environ.items()
               if k in ("PATH", "SYSTEMROOT", "TEMP", "TMP", "PATHEXT")}
    entorno.update(POSTGRES_DB="inerte", POSTGRES_USER="inerte",
                   POSTGRES_PASSWORD="inerte", PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, "-c", hijo], capture_output=True, text=True,
                       cwd=str(_RAIZ), env=entorno, timeout=300)
    assert r.returncode == 0, r.stderr[-800:]
    cargados = r.stdout.strip()[len("CARGADOS:"):]
    assert "httpx" in cargados and "app.rutas" in cargados, (
        "importar app.rutas TENIA que ensuciar sys.modules; si no lo hace, la prueba (A) "
        "esta pasando por vacio"
    )


# ═════════════════════════════════════════════════════════════════════════════
# (B) PUREZA POR AST, con su guarda de no-ceguera
# ═════════════════════════════════════════════════════════════════════════════


def test_B_las_funciones_del_assembler_son_PURAS_en_el_codigo():
    """Sin `await`, sin red, sin base, sin reloj. Y `vistas == esperadas` para que la
    guarda no pueda quedarse mirando un conjunto vacio si alguien renombra algo."""
    vistas = set()
    arbol = _arbol(_RAIZ / "app" / "place" / "assembler.py")
    for n in ast.walk(arbol):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in FUNCIONES_PURAS:
            vistas.add(n.name)
            assert not isinstance(n, ast.AsyncFunctionDef), f"{n.name} es async"
            for hijo in ast.walk(n):
                assert not isinstance(hijo, (ast.Await, ast.AsyncWith, ast.AsyncFor)), n.name
                if isinstance(hijo, ast.Name):
                    assert hijo.id not in PROHIBIDOS_EN_EL_ASSEMBLER, f"{n.name} toca {hijo.id}"
                if isinstance(hijo, ast.Attribute):
                    assert hijo.attr not in PROHIBIDOS_EN_EL_ASSEMBLER, f"{n.name} toca {hijo.attr}"
    assert vistas == set(FUNCIONES_PURAS), f"no se revisaron todas: faltan {set(FUNCIONES_PURAS) - vistas}"


def test_B2_el_modulo_entero_no_importa_infraestructura():
    """No solo las funciones: el MODULO. Un import de nivel de modulo bastaria para que
    `httpx` apareciera en `sys.modules` aunque nadie lo llamara."""
    modulos = set()
    for n in ast.walk(_arbol(_RAIZ / "app" / "place" / "assembler.py")):
        if isinstance(n, ast.Import):
            modulos |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            modulos.add(n.module)
    prohibidos = {m for m in modulos
                  if m.split(".")[0] in ("httpx", "sqlalchemy", "asyncio")
                  or m in ("app.database", "app.rutas", "app.config")
                  or m.startswith(("app.routers", "app.agent", "app.rutas."))}
    assert not prohibidos, f"el assembler importa infraestructura: {sorted(prohibidos)}"


def test_B3_el_reloj_solo_lo_lee_el_recolector_que_se_quedo():
    """El determinismo de 1.2 depende de que el instante venga en la materia. Si el
    ensamblador leyera el reloj, dos ensamblajes del mismo material dejarian de coincidir
    —y eso lo caza 1.2— pero conviene cazarlo tambien aqui, en el sitio."""
    fuente = (_RAIZ / "app" / "place" / "assembler.py").read_text(encoding="utf-8")
    assert "datetime.now" not in fuente and "utcnow" not in fuente
    rutas_src = (_RAIZ / "app" / "rutas.py").read_text(encoding="utf-8")
    assert rutas_src.count("datetime.now") == 1, (
        "el reloj debe leerse en un solo sitio: `_recolectar_zona`"
    )


# ═════════════════════════════════════════════════════════════════════════════
# (C) SITIO DE DEFINICION
# ═════════════════════════════════════════════════════════════════════════════


def test_C_los_simbolos_movidos_se_DEFINEN_en_el_modulo_nuevo():
    definidos = _definidos_en(_RAIZ / "app" / "place" / "assembler.py")
    faltan = [s for s in MOVIDOS if s not in definidos]
    assert not faltan, f"no se definen en app/place/assembler.py: {faltan}"
    assert len(MOVIDOS) == 15, "la lista de movidos se toco sin actualizar la guarda"


def test_C2_rutas_NO_conserva_una_segunda_implementacion():
    """El modo de fraude mas comodo: mover el bloque y dejar el original. Las dos
    implementaciones divergirian con el tiempo y nadie se enteraria."""
    definidos = _definidos_en(_RAIZ / "app" / "rutas.py")
    duplicados = sorted(set(MOVIDOS) & definidos)
    assert not duplicados, f"rutas.py sigue DEFINIENDO simbolos movidos: {duplicados}"


def test_C3_el_module_del_objeto_vivo_apunta_al_modulo_nuevo():
    """El AST dice donde esta el texto; `__module__` dice de donde salio el objeto. Hacen
    falta los dos: una fachada que REDEFINA pasaria el segundo y no el primero."""
    for nombre in MOVIDOS:
        obj = getattr(assembler, nombre)
        if inspect.isfunction(obj) or inspect.isclass(obj):
            assert obj.__module__ == "app.place.assembler", f"{nombre}: {obj.__module__}"
            assert "app" + os.sep + "place" in inspect.getsourcefile(obj)


def test_C4_lo_que_NO_es_puro_se_quedo_en_rutas():
    """La contiguidad habria arrastrado estos cuatro. La dependencia los rechaza."""
    definidos_rutas = _definidos_en(_RAIZ / "app" / "rutas.py")
    definidos_ass = _definidos_en(_RAIZ / "app" / "place" / "assembler.py")
    for nombre in NO_MOVIDOS:
        assert nombre in definidos_rutas, f"{nombre} debia quedarse en rutas.py"
        assert nombre not in definidos_ass, f"{nombre} no es puro y no debia moverse"


# ═════════════════════════════════════════════════════════════════════════════
# (D) FACHADA: los consumidores historicos resuelven al MISMO objeto
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("nombre", MOVIDOS)
def test_D_la_fachada_liga_el_mismo_objeto_no_una_copia(nombre):
    """`rutas.X is assembler.X`. Una copia pasaria una igualdad y fallaria esto: dos
    objetos distintos divergen en cuanto alguien parchea uno."""
    assert hasattr(rutas, nombre), f"la fachada perdio {nombre}"
    assert getattr(rutas, nombre) is getattr(assembler, nombre)


def test_D2_los_consumidores_historicos_siguen_importando_de_app_rutas():
    """Los dos oraculos importan de `app.rutas`. Esta unidad no cambia sus imports, asi
    que la fachada tiene que sostenerlos tal cual."""
    for fichero in ("test_place_context_v0.py", "test_loop_fixtures_1_6.py"):
        texto = (_RAIZ / "tests" / fichero).read_text(encoding="utf-8")
        assert "from app.rutas import" in texto
    from app.rutas import MateriaDeZona, ensamblar_place_context  # noqa: F401
    assert MateriaDeZona is assembler.MateriaDeZona


# ═════════════════════════════════════════════════════════════════════════════
# (E) EL GOLDEN DE 1.6 NO SE MUEVE
# ═════════════════════════════════════════════════════════════════════════════


def test_E_el_dataset_del_loop_sigue_siendo_byte_a_byte_el_mismo():
    """El oraculo mas fuerte que hay: 21 objetos congelados, reconstruidos por los
    productores reales. Si la extraccion hubiera tocado una coma del `PlaceContextV0`,
    esto cae. El golden NO se regenera: si falla, la extraccion cambio comportamiento."""
    sys.path.insert(0, str(_RAIZ / "tests"))
    import test_loop_fixtures_1_6 as loop

    reconstruido = loop.serializar(loop.construir_contenedor(loop.cargar_material()))
    assert loop.huella(reconstruido) == loop.huella(loop.leer_golden_canonico())
