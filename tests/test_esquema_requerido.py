"""AUTH-READ-GATE.1 · HOLD-2 — el arranque se niega a servir con el esquema incompleto.

La propiedad que se prueba no es "la comprobación existe", sino **qué pasa cuando falta cada
una de las columnas**, una por una. Una comprobación que solo mirase la primera columna
pasaría un test genérico y dejaría pasar un despliegue roto por cualquiera de las otras tres.

Aquí no hace falta Postgres: `information_schema` se representa con las filas que devolvería,
y lo que se ejercita es la lógica real de `columnas_faltantes` / `exigir_esquema`. La
ejecución contra el motor real está en `tests/test_integracion_postgres.py`.
"""

import asyncio

import pytest

from app.esquema_requerido import (
    COLUMNAS_REQUERIDAS,
    EsquemaIncompleto,
    columnas_faltantes,
    exigir_esquema,
)

TODAS = [(t, c) for t, cs in COLUMNAS_REQUERIDAS.items() for c in cs]


class _Introspeccion:
    """Devuelve las filas de `information_schema.columns` que se le digan. No decide nada."""

    def __init__(self, filas):
        self.filas = filas
        self.consultas = []

    async def execute(self, stmt, params=None):
        self.consultas.append((str(stmt), dict(params or {})))
        filas = self.filas

        class _R:
            def all(self_inner):
                return filas

        return _R()


def _completo():
    return _Introspeccion(TODAS)


def _sin(columna):
    return _Introspeccion([(t, c) for t, c in TODAS if c != columna])


def test_el_esquema_completo_deja_arrancar():
    asyncio.run(exigir_esquema(db=_completo()))   # no levanta


@pytest.mark.parametrize("columna", [c for _t, c in TODAS])
def test_falta_una_columna_y_el_arranque_FALLA(columna):
    """Una por una. Es el punto: las cuatro son necesarias y ninguna es opcional."""
    with pytest.raises(EsquemaIncompleto) as e:
        asyncio.run(exigir_esquema(db=_sin(columna)))

    assert columna in str(e.value), "el error no dice QUÉ falta"
    assert "027" in str(e.value), "el error no dice CÓMO arreglarlo"


def test_la_tabla_entera_ausente_tambien_falla():
    """El caso de una base virgen: ni siquiera existe `chat_sessions`."""
    with pytest.raises(EsquemaIncompleto) as e:
        asyncio.run(exigir_esquema(db=_Introspeccion([])))
    for _t, c in TODAS:
        assert c in str(e.value)


def test_el_mensaje_no_lleva_valores_ni_conexion():
    """Un error de arranque acaba en logs de despliegue, que se comparten y se pegan en
    tickets. Nombra columnas y la migración; nada más."""
    with pytest.raises(EsquemaIncompleto) as e:
        asyncio.run(exigir_esquema(db=_Introspeccion([])))
    texto = str(e.value).lower()
    for prohibido in ("password", "postgresql://", "@", "secret", "token=", "resume_secret"):
        assert prohibido not in texto, f"el mensaje de arranque filtra {prohibido!r}"


def test_la_comprobacion_no_escribe_nada():
    """Es introspección, no una migración. Ninguna sentencia puede mutar."""
    db = _completo()
    asyncio.run(columnas_faltantes(db=db))

    assert len(db.consultas) == 1, "debería bastar una ida y vuelta"
    sql = db.consultas[0][0].upper()
    assert sql.strip().startswith("SELECT")
    for verbo in ("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP"):
        assert verbo not in sql, f"la comprobación de arranque contiene {verbo}"
    assert "INFORMATION_SCHEMA.COLUMNS" in sql


def test_el_arranque_de_main_exige_el_esquema_ANTES_de_todo():
    """Comprobar tarde no sirve: el checkpointer abre conexiones y los cron empiezan a
    barrer. La llamada tiene que ir delante, y se verifica sobre el AST — no por texto,
    porque el comentario que la explica también nombra `exigir_esquema`.
    """
    import ast
    import pathlib

    arbol = ast.parse(pathlib.Path("main.py").read_text(encoding="utf-8"))
    lifespan = next(n for n in ast.walk(arbol)
                    if isinstance(n, ast.AsyncFunctionDef) and n.name == "lifespan")

    llamadas = [ast.unparse(n.value) for n in ast.walk(lifespan)
                if isinstance(n, ast.Await)]
    assert llamadas, "el lifespan no espera nada"
    assert "exigir_esquema()" in llamadas[0], (
        f"la comprobación de esquema no es lo primero: {llamadas[0]}"
    )


def test_migrar_NO_ocurre_en_el_arranque():
    """Aplicar DDL al arrancar con varias réplicas es una carrera, y un despliegue fallido
    dejaría el esquema a medias sin que nadie lo pidiera. Migrar es explícito."""
    import ast
    import pathlib

    arbol = ast.parse(pathlib.Path("main.py").read_text(encoding="utf-8"))
    lifespan = next(n for n in ast.walk(arbol)
                    if isinstance(n, ast.AsyncFunctionDef) and n.name == "lifespan")
    cuerpo = ast.unparse(lifespan)

    assert "aplicar_migracion" not in cuerpo
    assert "ALTER TABLE" not in cuerpo and "CREATE TABLE" not in cuerpo
