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


def test_la_superficie_de_producto_solo_toca_la_SOMBRA():
    """E3.2b.4 · el producto ya llama a la memoria del comprador, pero **sólo por la sombra**.

    La versión anterior enumeraba nombres de módulo prohibidos y se le coló este wiring: como
    `chat.py` importa `buyer.sombra` y ese nombre no estaba en la lista, el guard pasó en
    verde el mismo commit que conectaba producción. Enumerar lo prohibido falla en cuanto
    aparece un nombre nuevo; enumerar lo PERMITIDO no.

    Ahora la regla es una lista blanca de UNO: la superficie de producto puede nombrar
    `buyer.sombra` y nada más de `app/buyer`. Cualquier atajo que salte la sombra —llamar al
    orquestador, al reducer o al store directamente— vuelve a poner esto rojo.
    """
    superficie = [p for p in [RAIZ / "app" / "routers", RAIZ / "app" / "agent",
                              RAIZ / "app" / "main.py"] if p.exists()]
    permitido = "app.buyer.sombra"
    prohibidos = ("buyer.store", "buyer.actualizador", "buyer.reductor", "buyer.interprete",
                  "buyer.extractor", "buyer.boundary", "anexar_revision", "cargar_ultima",
                  "interpretar_mensaje", "ReduccionImposible")

    atajos = []
    for raiz in superficie:
        for f in ([raiz] if raiz.is_file() else raiz.rglob("*.py")):
            if "__pycache__" in f.parts:
                continue
            texto = f.read_text(encoding="utf-8", errors="ignore").replace(permitido, "")
            if any(pr in texto for pr in prohibidos):
                atajos.append(str(f.relative_to(RAIZ)))

    assert atajos == [], f"el producto salta la sombra y llama directo: {atajos}"


def test_el_ORQUESTADOR_solo_lo_consume_la_sombra():
    """La contraparte: el único consumidor del orquestador en `app/` es `sombra.py`.

    Mantiene la propiedad que el guard anterior protegía —que nadie lo invoque por su cuenta—
    ahora que la sombra sí está autorizada a hacerlo.
    """
    llamantes = []
    for f in (RAIZ / "app").rglob("*.py"):
        if "__pycache__" in f.parts or f.name in ("actualizador.py", "sombra.py"):
            continue
        texto = f.read_text(encoding="utf-8", errors="ignore")
        if "buyer.actualizador" in texto or "ResultadoUpdater" in texto:
            llamantes.append(str(f.relative_to(RAIZ)))

    assert llamantes == [], f"el orquestador tiene un consumidor fuera de la sombra: {llamantes}"


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


# ══ R-IDEMP-1 · la procedencia OPERACIONAL no es estado del comprador ════════════════
#
# Un replay del mismo mensaje construye una `EvidenceRefV0` nueva: `evidence_id` sale de
# `uuid4()` y `retrieved_at` de un reloj. Los dos cambian, `_canonico` cambia con ellos, y un
# reintento honesto acababa en `BuyerIdempotencyConflict` — acusando de no determinista a un
# extractor que sí lo es.
#
# La excepción está ACOTADA a `USER_DECLARED`, que es la evidencia que crea este updater. Para
# un `PROVIDER_API` con TTL, `retrieved_at` sí es material —dice si el dato está fresco— y
# excluirlo en general habría cambiado un bug puntual por una pérdida general de procedencia.

from datetime import timedelta  # noqa: E402

from app.contracts.evidence_v0 import (  # noqa: E402
    EvidenceRefV0, PersistencePolicy, SourceType,
)
from app.contracts.buyer_v0 import FieldEvidence  # noqa: E402

_T0 = dt.datetime(2026, 8, 28, 12, 0, tzinfo=dt.timezone.utc)


def _ev(*, tipo=SourceType.USER_DECLARED, source_id="m-1", retrieved_at=_T0,
        observed_at=None, evidence_id=None, provider=None):
    extra = {"evidence_id": evidence_id} if evidence_id else {}
    # `HEURISTIC_ESTIMATE` exige `limitations` por contrato — "un dato no medido que no
    # declara qué no puede sostener acaba puntuando como si estuviera medido". Lo pide el
    # propio EvidenceRefV0, y este helper lo respeta en vez de esquivar el tipo.
    if tipo is SourceType.HEURISTIC_ESTIMATE:
        extra["limitations"] = ("estimado, no medido",)
    return EvidenceRefV0(
        source_type=tipo, source_id=source_id, provider=provider,
        methodology="declaración del usuario en la conversación",
        persistence_policy=PersistencePolicy.PERSISTABLE,
        retrieved_at=retrieved_at, observed_at=observed_at, **extra)


def _con_evidencia(evidencia, *, campo="objective", objetivo=Objective.BUY):
    return _ctx(objective=objetivo,
                field_evidence=(FieldEvidence(field=campo, evidence=evidencia),))


def test_IDEMP_un_replay_con_otro_evidence_id_es_el_MISMO_estado():
    """`evidence_id` es, por su propio contrato, *"un asa nuestra, no una afirmación sobre el
    mundo"*. Dos asas distintas para el mismo hecho no son dos hechos."""
    a = _con_evidencia(_ev(evidence_id="11111111-1111-5111-8111-111111111111"))
    b = _con_evidencia(_ev(evidence_id="22222222-2222-5222-8222-222222222222"))
    assert _canonico(a) == _canonico(b)


def test_IDEMP_un_replay_con_otro_retrieved_at_es_el_MISMO_estado():
    """`retrieved_at` es cuándo lo procesamos NOSOTROS. Que el reintento ocurra cinco segundos
    después no cambia lo que el comprador declaró."""
    a = _con_evidencia(_ev(retrieved_at=_T0))
    b = _con_evidencia(_ev(retrieved_at=_T0 + timedelta(seconds=5)))
    assert _canonico(a) == _canonico(b)


def test_IDEMP_otro_source_id_SI_es_otro_estado():
    """Lo que sostiene el valor es de qué mensaje salió. Cambiar eso es cambiar la
    procedencia, y tiene que verse."""
    assert _canonico(_con_evidencia(_ev(source_id="m-1"))) != \
           _canonico(_con_evidencia(_ev(source_id="m-2")))


def test_IDEMP_otro_valor_durable_SI_es_otro_estado():
    """La excepción no puede cegar el caso que la idempotencia existe para cazar: el mismo
    mensaje produciendo dos interpretaciones distintas."""
    assert _canonico(_con_evidencia(_ev(), objetivo=Objective.BUY)) != \
           _canonico(_con_evidencia(_ev(), objetivo=Objective.RENT))


def test_IDEMP_otro_observed_at_SI_es_otro_estado():
    """`observed_at` es CUÁNDO EL MUNDO ESTABA ASÍ — un hecho sobre el dato, no sobre nuestro
    intento de procesarlo. No entra en la excepción."""
    assert _canonico(_con_evidencia(_ev(observed_at=None))) != \
           _canonico(_con_evidencia(_ev(observed_at=_T0 - timedelta(days=1))))


def test_IDEMP_otra_ruta_SI_es_otro_estado():
    assert _canonico(_con_evidencia(_ev(), campo="objective")) != \
           _canonico(_con_evidencia(_ev(), campo="financial.budget_max"))


@pytest.mark.parametrize("tipo", [SourceType.PROVIDER_API, SourceType.PUBLIC_DATASET,
                                  SourceType.OWN_MEASUREMENT, SourceType.HEURISTIC_ESTIMATE])
def test_IDEMP_la_excepcion_NO_alcanza_a_la_evidencia_de_otros_origenes(tipo):
    """EL LÍMITE DE LA EXCEPCIÓN, y es lo que impide cambiar un bug puntual por una pérdida
    general de procedencia.

    Para un `PROVIDER_API` con TTL, `retrieved_at` dice si el dato sigue fresco: es material y
    tiene que seguir participando. La excepción se justifica por lo que significa
    `USER_DECLARED` —lo dijo la persona, y cuándo lo procesamos no cambia lo que dijo—, no por
    conveniencia de comparación.
    """
    a = _con_evidencia(_ev(tipo=tipo, provider="google_places", retrieved_at=_T0))
    b = _con_evidencia(_ev(tipo=tipo, provider="google_places",
                           retrieved_at=_T0 + timedelta(hours=6)))
    assert _canonico(a) != _canonico(b)


def test_IDEMP_la_excepcion_tampoco_alcanza_al_evidence_id_de_otros_origenes():
    a = _con_evidencia(_ev(tipo=SourceType.PROVIDER_API, provider="x",
                           evidence_id="11111111-1111-5111-8111-111111111111"))
    b = _con_evidencia(_ev(tipo=SourceType.PROVIDER_API, provider="x",
                           evidence_id="22222222-2222-5222-8222-222222222222"))
    assert _canonico(a) != _canonico(b)
