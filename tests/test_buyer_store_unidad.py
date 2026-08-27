"""E3.1b · Buyer Store — lo que se puede probar sin motor.

Las garantías duras (idempotencia por `UNIQUE`, concurrencia por `FOR UPDATE`) viven en la
base y se prueban en `test_buyer_store_postgres.py`. Aquí quedan las propiedades que son
del módulo y no del motor: comparación canónica, validación de entrada, y **que esta unidad
no haya conectado nada al producto**.
"""

from __future__ import annotations

import ast
import asyncio
import datetime as dt
import pathlib
import uuid

import pytest

from app.buyer import store
from app.buyer.store import BuyerStoreError, _canonico
from app.contracts.buyer_v0 import BuyerContextV0, Objective

RAIZ = pathlib.Path(__file__).resolve().parent.parent
B1 = str(uuid.uuid4())


def _sql_sin_comentarios(nombre: str) -> str:
    """El SQL sin las líneas `--`. Estos ficheros están densamente comentados y los
    comentarios nombran justo lo que los tests buscan (`source_message_id`, `session_id`),
    así que afirmar sobre el fuente crudo daría verdes y rojos falsos por igual."""
    sql = (RAIZ / "migrations" / nombre).read_text(encoding="utf-8")
    return "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))


def _ctx(buyer_id=B1, revision=None, **extra) -> BuyerContextV0:
    return BuyerContextV0(
        buyer_id=buyer_id, context_revision=revision,
        updated_at=dt.datetime(2026, 8, 27, 12, 0, tzinfo=dt.timezone.utc), **extra)


# ── La comparación canónica ────────────────────────────────────────────────────────


def test_la_revision_NO_entra_en_la_comparacion():
    """`context_revision` es metadato que asigna el store, no estado del comprador.

    Si entrara en la comparación, el mismo snapshot parecería distinto solo por haber sido
    numerado — y un reintento honesto daría `BuyerIdempotencyConflict`, acusando de no
    determinista a un extractor que sí lo es.
    """
    assert _canonico(_ctx(revision=None)) == _canonico(_ctx(revision=7))


def test_dos_contextos_equivalentes_dan_la_MISMA_forma():
    assert _canonico(_ctx(objective=Objective.RENT)) == _canonico(_ctx(objective=Objective.RENT))


def test_un_cambio_real_de_estado_SÍ_cambia_la_forma():
    assert _canonico(_ctx(objective=Objective.RENT)) != _canonico(_ctx(objective=Objective.BUY))


def test_la_forma_canonica_es_estable_entre_llamadas():
    """Sin orden estable de claves, la comparación sería un generador de conflictos falsos."""
    ctx = _ctx(objective=Objective.BUY, stage="explorando")
    assert len({_canonico(ctx) for _ in range(5)}) == 1


# ── Validación de entrada, antes de tocar la base ──────────────────────────────────


def test_un_contexto_de_otro_comprador_se_rechaza_sin_base():
    """Se comprueba ANTES de abrir conexión: persistir el estado de una cuenta bajo la raíz
    de otra no puede depender de que una consulta posterior lo note."""
    with pytest.raises(BuyerStoreError):
        asyncio.run(store.anexar_revision(
            B1, "m-1", _ctx(buyer_id=str(uuid.uuid4())), None, db=None))


def test_una_revision_esperada_negativa_se_rechaza():
    with pytest.raises(BuyerStoreError):
        asyncio.run(store.anexar_revision(B1, "m-1", _ctx(), -1, db=None))


def test_el_contrato_ya_prohibe_revisiones_negativas():
    """El store no reimplementa la regla: la hereda de `BuyerContextV0` (`ge=0`)."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        _ctx(revision=-1)


# ── El store no guarda texto de mensajes ───────────────────────────────────────────


def test_el_esquema_NO_tiene_columna_para_el_texto_del_mensaje():
    """Solo `source_message_id`. La conversación tiene su propio almacenamiento; duplicar
    el texto aquí duplicaría PII sin ganar nada."""
    # Se quitan los comentarios ANTES de acotar. La primera versión de este test recortaba
    # por `);` sobre el fuente crudo y el corte caía dentro de un comentario — el mismo
    # fallo de "texto en vez de estructura" que persigue a esta rama desde AUTH-READ-GATE.
    sql = _sql_sin_comentarios("028_buyer_context_store.sql")
    cuerpo = sql[sql.index("CREATE TABLE IF NOT EXISTS buyer_context_revisions"):]
    cuerpo = cuerpo[:cuerpo.index(");")]
    assert "source_message_id" in cuerpo
    for prohibida in ("message_text", "mensaje_texto", "texto", "content", "contenido"):
        assert prohibida not in cuerpo, f"el esquema guarda {prohibida}"


def test_el_store_nunca_escribe_el_texto_del_mensaje():
    """Se mira el CÓDIGO, no el fuente crudo: los comentarios del módulo hablan del texto
    del mensaje precisamente para explicar que no se guarda."""
    codigo = ast.unparse(ast.parse((RAIZ / "app" / "buyer" / "store.py").read_text(encoding="utf-8")))
    firma = [a.arg for a in ast.parse(
        (RAIZ / "app" / "buyer" / "store.py").read_text(encoding="utf-8")).body
        if isinstance(a, ast.AsyncFunctionDef) and a.name == "anexar_revision"
        for a in a.args.args]
    assert "source_message_id" in firma
    assert "message_text" not in codigo and "texto_mensaje" not in codigo


# ── Ninguna identidad que no sea el sujeto autenticado ─────────────────────────────


def test_ni_session_id_ni_device_key_aparecen_en_el_store():
    """E3.1a y AUTH-READ-GATE.1 lo dejaron decidido: su conocimiento otorga acceso, así que
    no identifican a nadie. No pueden ser raíz de comprador."""
    codigo = ast.unparse(ast.parse((RAIZ / "app" / "buyer" / "store.py").read_text(encoding="utf-8")))
    sql = (RAIZ / "migrations" / "028_buyer_context_store.sql").read_text(encoding="utf-8")
    cuerpo_sql = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))

    for prohibido in ("session_id", "device_key", "thread_id", "anonymous_buyer", "guest_id"):
        assert prohibido not in codigo, f"el store usa {prohibido}"
        assert prohibido not in cuerpo_sql, f"el esquema usa {prohibido}"


def test_la_raiz_es_auth_users():
    sql = (RAIZ / "migrations" / "028_buyer_context_store.sql").read_text(encoding="utf-8")
    cuerpo = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    assert "REFERENCES auth.users (id) ON DELETE CASCADE" in cuerpo
    assert "profiles" not in cuerpo, "profiles es una proyección, no la raíz de identidad"


# ── CERO wiring productivo ─────────────────────────────────────────────────────────


def test_NADIE_en_produccion_llama_todavia_al_store():
    """E3.1b es infraestructura interna: al terminar, el store existe y nadie lo usa.

    Conectarlo es E3.2. Este test es lo que impide que el wiring se cuele "de paso" y
    cambie el comportamiento del producto en una unidad que no lo autorizaba.
    """
    consumidores = []
    for f in RAIZ.rglob("*.py"):
        partes = set(f.parts)
        if partes & {"tests", ".venv", "node_modules", "__pycache__"}:
            continue
        if f.name == "store.py" and "buyer" in partes:
            continue
        texto = f.read_text(encoding="utf-8", errors="ignore")
        if "buyer.store" in texto or "anexar_revision" in texto or "cargar_ultima" in texto:
            consumidores.append(str(f.relative_to(RAIZ)))

    assert consumidores == [], f"el store ya está conectado a producción: {consumidores}"


def test_el_store_no_expone_endpoints():
    codigo = (RAIZ / "app" / "buyer" / "store.py").read_text(encoding="utf-8")
    for prohibido in ("@router", "APIRouter", "FastAPI", "Depends("):
        assert prohibido not in codigo, f"el store expone HTTP ({prohibido})"


def test_el_store_no_extrae_ni_interpreta():
    """No es la barrera de Fair Housing y no puede convertirse en un segundo camino de
    extracción. Acepta un `BuyerContextV0` ya construido."""
    codigo = (RAIZ / "app" / "buyer" / "store.py").read_text(encoding="utf-8")
    for prohibido in ("anthropic", "llm", "extraer_preferencias", "HumanMessage", "prompt"):
        assert prohibido.lower() not in codigo.lower(), f"el store {prohibido}"
