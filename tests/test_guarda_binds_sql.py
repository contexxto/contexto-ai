"""Guarda del cepo `:nombre::tipo` en `text()` — rescatada de PR #171 (MAP-SOURCE-BOUNDARY).

EL CEPO. Dentro de `text()`, `:x::jsonb` NO es «el bind `x` con un cast»: el `::` del cast se
come el bindparam. SQLAlchemy registra un nombre truncado (`poi` en vez de `pois`) y el SQL
viaja con `:pois::jsonb` LITERAL, así que Postgres responde «syntax error at or near ":"». Si
la llamada está envuelta en un `except` best-effort, el fallo no se ve nunca: así estuvo la
caché de AURA sin escribir una sola fila desde el 2026-06-29. La forma correcta es
`CAST(:x AS tipo)`, y `app/place/providers/propia.py` ya lo documentaba.

POR QUÉ VIVE AQUÍ. PR #171 corregía ese INSERT y traía esta guarda y la prueba roja de
`save_ficha`. MAP-SOURCE-BOUNDARY retiró la caché entera (guardaba contenido de Google
Places) y por eso #171 queda superado; lo que no se pierde es lo que valía por sí mismo:

  A · la guarda sobre TODO `text()` literal de `app/`, con su lista de excepciones conocidas
      y la prueba de que ninguna excepción queda muerta;
  B · FICHA-DATE-BIND: `save_ficha` (POST /{id}/ficha) usa `:cisterna::date` y hermanos. Test
      rojo con xfail ESTRICTO: esta unidad NO arregla FICHA (el mandato lo prohíbe). Cuando
      alguien la arregle, el xfail estricto se pondrá en rojo y obligará a quitar la marca Y
      la excepción de la guarda, en el mismo cambio.

Sin `TEST_DATABASE_URL` el bloque B se SALTA: un skip aquí es «esta evidencia no se recogió».
"""
from __future__ import annotations

import ast
import os
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

import app.routers.assets as assets

RAIZ = Path(__file__).resolve().parents[1]
ACTIVO = uuid.UUID("0cb128c9-0000-4000-8000-00000000f1c4")

# Un `:nombre` que SQLAlchemy debería convertir en bind. El lookbehind replica el de
# SQLAlchemy (ni `::`, ni palabra, ni barra invertida delante); sin su lookahead `(?!:)`,
# que es justo lo que hace que `:pois::jsonb` se registre como `poi`.
_BIND_EN_FUENTE = re.compile(r"(?<![:\w\\]):([A-Za-z_]\w*)")

# Excepciones CONOCIDAS de la guarda, cada una con su motivo. Vacía = ningún `text()` de `app/`
# pierde un bind. No añadir entradas sin un test rojo que las describa.
_EXCEPCIONES_CONOCIDAS = {
    # FICHA-DATE-BIND · save_ficha (POST /{id}/ficha): `:cisterna::date` y hermanos. Test rojo
    # `test_save_ficha_persiste_las_fechas` (xfail estricto) hasta su propia unidad.
    ("app/routers/assets.py", frozenset({"cisterna", "techo", "fachada", "cableado"})),
}


def _literal(nodo) -> str | None:
    if isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
        return nodo.value
    if isinstance(nodo, ast.BinOp) and isinstance(nodo.op, ast.Add):
        a, b = _literal(nodo.left), _literal(nodo.right)
        return a + b if a is not None and b is not None else None
    return None  # f-strings y construcciones dinámicas: fuera del alcance de esta guarda


def _textos_literales(raiz: Path = RAIZ):
    for ruta in sorted((raiz / "app").rglob("*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call) or not nodo.args:
                continue
            f = nodo.func
            nombre = f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None
            if nombre != "text":
                continue
            sql = _literal(nodo.args[0])
            if sql is not None:
                yield ruta.relative_to(raiz).as_posix(), nodo.lineno, sql


def _perdidos(sql: str) -> set[str]:
    return set(_BIND_EN_FUENTE.findall(sql)) - set(text(sql)._bindparams)


# ─────────────────────────────── A · sin base ────────────────────────────────
def test_ningun_text_literal_de_app_pierde_un_bind_por_un_cast():
    """Para cada `text("…")` literal de `app/`, todo `:nombre` del fuente queda registrado
    como bind. `:x::tipo` lo rompe; `CAST(:x AS tipo)` no."""
    vistos, fallos = 0, []
    for ruta, linea, sql in _textos_literales():
        vistos += 1
        perdidos = _perdidos(sql)
        if perdidos and (ruta, frozenset(perdidos)) not in _EXCEPCIONES_CONOCIDAS:
            fallos.append(f"{ruta}:{linea} pierde {sorted(perdidos)}")
    assert vistos > 100, f"la guarda no está viendo el código ({vistos} text() literales)"
    assert fallos == [], "\n".join(fallos)


def test_las_excepciones_conocidas_siguen_existiendo():
    """Si alguien arregla el caso conocido, la excepción debe salir de la lista (no se
    acumulan permisos muertos)."""
    perdidos_por_ruta: dict[str, list[frozenset]] = {}
    for ruta, _, sql in _textos_literales():
        perdidos = _perdidos(sql)
        if perdidos:
            perdidos_por_ruta.setdefault(ruta, []).append(frozenset(perdidos))
    for ruta, conjunto in _EXCEPCIONES_CONOCIDAS:
        assert conjunto in perdidos_por_ruta.get(ruta, []), f"excepción muerta: {ruta} {sorted(conjunto)}"


def test_la_guarda_SI_PUEDE_fallar(tmp_path):
    """La mitad negativa. Se fabrica un `app/` con el INSERT roto de la caché de AURA tal como
    estaba (`:pois::jsonb`) y otro correcto; la guarda tiene que señalar el primero y solo ése."""
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "roto.py").write_text(
        "from sqlalchemy import text\n"
        "A = text(\"INSERT INTO t (a, b) VALUES (:id, :pois::jsonb)\")\n"
        "B = text(\"INSERT INTO t (a, b) VALUES (:id, CAST(:pois AS jsonb))\")\n",
        encoding="utf-8")
    hallados = [(linea, _perdidos(sql)) for _, linea, sql in _textos_literales(tmp_path)]
    assert hallados == [(2, {"pois"}), (3, set())], hallados


# ─────────────── B · FICHA-DATE-BIND (misma causa, NO se arregla aquí) ───────────────
URL = os.getenv("TEST_DATABASE_URL", "")
pg = pytest.mark.skipif(not URL, reason="sin TEST_DATABASE_URL: no hay Postgres de pruebas")


@pytest.fixture
async def base():
    """Esquema propio y efímero en el Postgres de pruebas."""
    from app.config import settings
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    if settings.database_url and URL.split("@")[-1] in settings.database_url:
        pytest.fail("TEST_DATABASE_URL apunta a la base del producto. Abortado.")
    esquema = "ficha_" + uuid.uuid4().hex[:10]
    admin = create_async_engine(URL, poolclass=NullPool)
    async with admin.begin() as cx:
        await cx.execute(text(f"CREATE SCHEMA {esquema}"))
    motor = create_async_engine(URL, poolclass=NullPool,
                                connect_args={"server_settings": {"search_path": esquema}})
    try:
        yield async_sessionmaker(motor, expire_on_commit=False)
    finally:
        await motor.dispose()
        async with admin.begin() as cx:
            await cx.execute(text(f"DROP SCHEMA {esquema} CASCADE"))
        await admin.dispose()


@pg
@pytest.mark.xfail(strict=True, reason=(
    "FICHA-DATE-BIND · save_ficha usa `:cisterna::date`, `:techo::date`, `:fachada::date`, "
    "`:cableado::date` (assets.py): el cast se come el bind y el INSERT no llega a Postgres "
    "válido. Unidad propia; MAP-SOURCE-BOUNDARY no lo arregla."))
async def test_save_ficha_persiste_las_fechas(base, monkeypatch):
    """POST /{id}/ficha tal como lo llama FichaTecnica.jsx: las fechas llegan como TEXTO."""
    async with base() as db:
        await db.execute(text(
            'CREATE TABLE ficha_tecnica_mantenimiento (id uuid PRIMARY KEY, activo_id uuid UNIQUE, '
            'tipo_tuberia varchar, "año_construccion" int, tipo_estructura varchar, '
            'calidad_acabados varchar, ultimo_mantenimiento_cisterna date, '
            'ultima_impermeabilizacion_techo date, ultima_pintura_fachada date, '
            'ultimo_cambio_cableado_electrico date, monto_invertido_mejoras numeric, '
            'descripcion_mejoras text, foto_evidencias text, estado_revision text, '
            'updated_at timestamp)'))
        await db.commit()

    async def _dueno(db, activo_id, user):
        return None
    monkeypatch.setattr(assets, "_assert_owner", _dueno)
    payload = assets.FichaRequest(
        tipo_tuberia="cobre", anio_construccion=2012, ultimo_mantenimiento_cisterna="2026-05-01",
        ultima_impermeabilizacion_techo="2025-11-15", ultima_pintura_fachada=None,
        ultimo_cambio_cableado_electrico="2024-02-29", monto_invertido_mejoras=1200.5)

    async with base() as db:
        assert (await assets.save_ficha(ACTIVO, payload, user=None, db=db))["ok"] is True
    async with base() as db:
        f = (await db.execute(text(
            "SELECT ultimo_mantenimiento_cisterna::text AS c, ultima_impermeabilizacion_techo::text AS t, "
            "ultima_pintura_fachada AS p, ultimo_cambio_cableado_electrico::text AS e "
            "FROM ficha_tecnica_mantenimiento WHERE activo_id = :id"), {"id": str(ACTIVO)})).mappings().first()
    assert dict(f) == {"c": "2026-05-01", "t": "2025-11-15", "p": None, "e": "2024-02-29"}
