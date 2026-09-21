"""
El nombre de la marca en lo que el backend le muestra a las personas: «Contexto», no «Contexto AI».

La marca con «AI» se retiró el 2026-08-19 en la app, pero el backend la seguía usando donde la
gente la ve: el agente se presentaba como «Contexto AI», los asuntos de los correos de reenganche
la llevaban y el letrero imprimible la escribía en su franja (Carlos, 2026-09-21, con la foto de un
letrero). Y main.py, en la raíz, la ponía en el título de la documentación de la API y en /health.
Esta prueba lee cada cadena de app/ y de main.py con `ast` —lo que puede llegar a una persona— y
deja fuera los comentarios y las docstrings de módulo, que no salen de ahí.
"""
import ast
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
APP = RAIZ / "app"
# Lo que sirve el backend: el paquete app/ y el punto de entrada. Los scripts sueltos de la raíz
# (semillas, importadores) no llegan a nadie.
FUENTES = sorted(APP.rglob("*.py")) + [RAIZ / "main.py"]
MARCA_ANTERIOR = re.compile(r"contexto\s+ai\b", re.IGNORECASE)


def _cadenas_visibles(fuente: str):
    """Cada cadena literal del módulo salvo su docstring (la primera expresión, si es texto)."""
    arbol = ast.parse(fuente)
    doc = arbol.body[0].value if arbol.body and isinstance(arbol.body[0], ast.Expr) else None
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str) and nodo is not doc:
            yield nodo.lineno, nodo.value


def test_ninguna_cadena_del_backend_dice_contexto_ai():
    halladas = [f"{p.relative_to(RAIZ)}:{n}: {v[:60]!r}"
                for p in FUENTES
                for n, v in _cadenas_visibles(p.read_text(encoding="utf-8"))
                if MARCA_ANTERIOR.search(v)]
    assert halladas == []


def test_control_el_detector_ve_las_cadenas_y_perdona_la_docstring_de_modulo():
    fuente = '"""Contexto AI — módulo."""\n# Contexto AI en un comentario\nASUNTO = "Contexto AI · una novedad"\n'
    assert [v for _, v in _cadenas_visibles(fuente) if MARCA_ANTERIOR.search(v)] == ["Contexto AI · una novedad"]
    assert not MARCA_ANTERIOR.search("Mozilla/5.0 (compatible; ContextoAI/2.0)")  # identificador técnico
