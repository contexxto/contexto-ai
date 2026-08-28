"""E3.2b.3 · el orquestador · gates 1-8.

Aquí se decide **qué significa procesar exactamente una vez un mensaje** cuando hay fallos,
mensajes que no cambian nada y dos conversaciones tocando al mismo comprador. Las piezas ya
estaban probadas por separado; lo que se prueba aquí es la política que las junta.

## El doble del store, y por qué no trivializa

`_StoreDoble` reimplementa el CONTRATO del store —idempotencia por `(buyer, mensaje)`,
`BuyerRevisionConflict` ante `expected_revision` rancia—, no lo simula por conveniencia. Las
garantías duras siguen viviendo en la base (`UNIQUE` y `FOR UPDATE`) y se prueban contra
Postgres en `test_buyer_actualizador_postgres.py`.

Lo que se prueba aquí es la POLÍTICA del orquestador: qué hace ante cada desenlace. Eso es
determinista y no necesita base — y separarlo es lo que permite cubrirlo entero en CI.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from decimal import Decimal

import pytest

from app.buyer import actualizador as act
from app.buyer.actualizador import (
    EstadoActualizacion, ResultadoUpdater, actualizar, rutas_divergentes, rutas_tocadas,
)
from app.buyer.boundary import (
    BuyerCurrencyV0, BuyerFieldV0, SetBedroomsMin, SetBudgetMax, SetObjective,
)
from app.buyer.extractor import (
    AfirmacionAmbiguous, AfirmacionDurable, AfirmacionRejected, AfirmacionTurnOnly,
    construir_lote,
)
from app.buyer.interprete import PropuestaV0
from app.buyer.reductor import reducir
from app.buyer.mensaje import IdentifiedUserMessage
from app.buyer.store import (
    BuyerContextV0, BuyerIdempotencyConflict, BuyerRevisionConflict, RevisionPersistida,
    _canonico,
)
from app.contracts.buyer_v0 import Objective, UnresolvedQuestion
from app.contracts.common_v0 import Money

T0 = dt.datetime(2026, 8, 28, 12, 0, tzinfo=dt.timezone.utc)
USD = BuyerCurrencyV0.USD
F = BuyerFieldV0
B1 = "11111111-1111-4111-8111-111111111111"

_BUD = SetBudgetMax(amount=Decimal(120000), currency=USD)
_BED = SetBedroomsMin(bedrooms_min=2)


def _msg(mid="m-1", texto="máximo 120000 USD"):
    return IdentifiedUserMessage(message_id=mid, text=texto)


def _proponente(*propuestas):
    async def proponer(_texto):
        return propuestas
    return proponer


def _p(disposicion, **kw):
    return PropuestaV0(disposicion=disposicion, motivo="propuesto", **kw)


class _StoreDoble:
    """Reimplementa el contrato del store en memoria. **No lo simplifica.**"""

    def __init__(self):
        self.revisiones: dict[str, list] = {}
        self.por_mensaje: dict[tuple[str, str], int] = {}

    async def cargar_ultima(self, buyer_id, *, db=None):
        historial = self.revisiones.get(buyer_id) or []
        return historial[-1] if historial else None

    async def anexar_revision(self, buyer_id, source_message_id, contexto,
                              expected_revision, *, db=None):
        if contexto.buyer_id != buyer_id:
            raise AssertionError("el doble no debe recibir un contexto de otro comprador")
        historial = self.revisiones.setdefault(buyer_id, [])

        clave = (buyer_id, source_message_id)
        if clave in self.por_mensaje:
            ya = next(r for r in historial
                      if r.context_revision == self.por_mensaje[clave])
            if _canonico(ya) != _canonico(contexto):
                raise BuyerIdempotencyConflict(
                    f"{source_message_id} ya produjo un estado distinto")
            return RevisionPersistida(ya, ya.context_revision, creada=False)

        actual = historial[-1].context_revision if historial else None
        if expected_revision != actual:
            raise BuyerRevisionConflict(
                f"esperaba {expected_revision}, la cabeza está en {actual}")

        # IDÉNTICO al store real: la primera revisión es 0, no 1. Que el doble numerara
        # desde 1 hacía que esta suite y la de Postgres afirmaran cosas distintas sobre
        # `revision`, y sólo una podía ser cierta. Hay meta-test que lo vigila.
        nueva = 0 if actual is None else actual + 1
        guardado = contexto.model_copy(update={"context_revision": nueva,
                                               "updated_at": T0})
        historial.append(guardado)
        self.por_mensaje[clave] = nueva
        return RevisionPersistida(guardado, nueva, creada=True)


@pytest.fixture
def store(monkeypatch):
    doble = _StoreDoble()
    monkeypatch.setattr(act, "cargar_ultima", doble.cargar_ultima)
    monkeypatch.setattr(act, "anexar_revision", doble.anexar_revision)
    return doble


def _correr(buyer_id, mensaje, proponente, **kw):
    return asyncio.run(actualizar(buyer_id, mensaje, retrieved_at=T0,
                                  proponente=proponente, **kw))


# ══ GATE 1 · AUTH ═══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("buyer_id", ["", "   ", None])
def test_G1_sin_comprador_autenticado_no_se_crea_estado_durable(buyer_id, store):
    """La raíz es `claims.sub` y nada más. Un `buyer_id` vacío que llegara al store ya habría
    viajado por media aplicación; se corta aquí."""
    r = _correr(buyer_id, _msg(), _proponente(
        _p("durable", mutacion=_BUD)))

    assert r.estado is EstadoActualizacion.FALLIDO
    assert not r.persistido
    assert store.revisiones == {}


# ══ GATE 2 · VACÍO · no se persiste NI se sella ═════════════════════════════════════


def test_G2_un_lote_vacio_no_persiste_y_deja_el_mensaje_sin_procesar(store):
    """`interpretar_mensaje` degrada un fallo del proponente a cero propuestas. Sellar el
    mensaje aquí lo daría por procesado para siempre por culpa de una caída del modelo."""
    r = _correr(B1, _msg(), _proponente())

    assert r.estado is EstadoActualizacion.VACIO
    assert not r.procesado
    assert store.revisiones == {}
    assert store.por_mensaje == {}


def test_G2_un_proponente_que_revienta_tambien_deja_el_mensaje_reintentable(store):
    async def revienta(_t):
        raise RuntimeError("timeout")

    r = _correr(B1, _msg(), revienta)
    assert r.estado is EstadoActualizacion.VACIO
    assert store.revisiones == {}


# ══ GATE 3 · NO-OP · se persiste para SELLAR el mensaje ═════════════════════════════


def test_G3_un_lote_solo_TURN_ONLY_persiste_una_revision_sin_cambio(store):
    """EL CASO QUE JUSTIFICA EL ESTADO `NO_OP`.

    Sin esta revisión, un mensaje interpretado hoy como `TURN_ONLY` no deja rastro. Si un
    reintento futuro lo interpretara como `DURABLE`, el store no tendría contra qué comparar y
    la divergencia entraría como estado nuevo, en silencio.
    """
    r = _correr(B1, _msg(texto="¿qué tan caminable es el barrio?"),
                _proponente(_p("turn_only")))

    assert r.estado is EstadoActualizacion.NO_OP
    assert r.persistido and r.procesado
    assert r.revision == 0, "la primera revisión del store real es 0" 


def test_G3_el_no_op_SELLA_el_mensaje_y_una_reinterpretacion_posterior_DIVERGE(store):
    """La idempotencia pasa a ser propiedad del MENSAJE PROCESADO, no sólo de los que
    casualmente mutaron algo. Es todo el argumento para persistir un no-op."""
    mensaje = _msg(mid="m-7", texto="quiero comprar")
    primero = _correr(B1, mensaje, _proponente(_p("turn_only")))
    assert primero.estado is EstadoActualizacion.NO_OP

    # el mismo mensaje, ahora interpretado como declaración durable
    segundo = _correr(B1, mensaje, _proponente(
        _p("durable", mutacion=SetObjective(objective=Objective.BUY))))

    assert segundo.estado is EstadoActualizacion.FALLIDO
    assert len(store.revisiones[B1]) == 1


def test_G3_un_REJECTED_solo_tambien_sella(store):
    r = _correr(B1, _msg(texto="tenemos dos niños"), _proponente(_p("rejected")))
    assert r.estado is EstadoActualizacion.NO_OP


# ══ GATE 4 · AMBIGUOUS ══════════════════════════════════════════════════════════════


def test_G4_una_ambiguedad_persiste_la_pregunta_y_NO_borra_el_valor(store):
    _correr(B1, _msg(mid="m-1", texto="máximo 120000 USD"),
            _proponente(_p("durable", mutacion=_BUD)))
    r = _correr(B1, _msg(mid="m-2", texto="unos 100000 más o menos"),
                _proponente(_p("ambiguous", campo=F.BUDGET_MAX)))

    assert r.estado is EstadoActualizacion.CREADA
    assert r.contexto.financial.budget_max.amount == Decimal(120000)
    assert [q.about_field for q in r.contexto.unresolved_questions] == \
           ["financial.budget_max"]


# ══ GATE 5 · IDEMPOTENCIA ═══════════════════════════════════════════════════════════


@pytest.mark.parametrize("propuestas,esperado", [
    ((("durable", {"mutacion": _BUD}),), EstadoActualizacion.CREADA),
    ((("ambiguous", {"campo": F.BUDGET_MAX}),), EstadoActualizacion.CREADA),
    ((("turn_only", {}),), EstadoActualizacion.NO_OP),
])
def test_G5_el_replay_devuelve_la_revision_existente(propuestas, esperado, store):
    """El segundo procesamiento del mismo mensaje no crea nada y se distingue del primero."""
    prop = _proponente(*[_p(d, **kw) for d, kw in propuestas])
    mensaje = _msg(mid="m-9")

    primero = _correr(B1, mensaje, prop)
    segundo = _correr(B1, mensaje, prop)

    assert primero.estado is esperado
    assert segundo.estado is EstadoActualizacion.REPLAY
    assert segundo.revision == primero.revision
    assert len(store.revisiones[B1]) == 1


def test_G5_la_misma_id_con_OTRA_interpretacion_levanta_divergencia(store):
    mensaje = _msg(mid="m-9")
    _correr(B1, mensaje, _proponente(_p("durable", mutacion=_BUD)))
    r = _correr(B1, mensaje, _proponente(_p("durable", mutacion=_BED)))

    assert r.estado is EstadoActualizacion.FALLIDO
    assert len(store.revisiones[B1]) == 1


# ══ GATE 6 · CONCURRENCIA ═══════════════════════════════════════════════════════════


def test_G6_rutas_tocadas_incluye_las_de_las_AMBIGUAS():
    """Abrir una pregunta sobre el presupuesto también reclama el presupuesto: si otra
    conversación lo cambió a la vez, no son independientes."""
    lote = construir_lote(_msg(), [
        AfirmacionDurable(mutacion=_BED, motivo="x"),
        AfirmacionAmbiguous(campo=F.BUDGET_MAX, motivo="y"),
        AfirmacionTurnOnly(campo=F.AREA_M2_MIN, motivo="z"),
        AfirmacionRejected(campo=None, motivo="w"),
    ])
    assert rutas_tocadas(lote) == {"property_requirements.bedrooms_min",
                                   "financial.budget_max"}


def test_G6_un_lote_sin_efecto_no_toca_ninguna_ruta():
    lote = construir_lote(_msg(), [AfirmacionTurnOnly(campo=None, motivo="pregunta")])
    assert rutas_tocadas(lote) == frozenset()


def test_G6_cambios_DISJUNTOS_se_rebasan_y_la_actualizacion_sobrevive(store):
    """A tocó el presupuesto, B toca los dormitorios: no compiten, así que B se rebasa sobre
    lo que A dejó y las dos actualizaciones sobreviven."""
    _correr(B1, _msg(mid="m-A", texto="máximo 120000 USD"),
            _proponente(_p("durable", mutacion=_BUD)))

    # B leyó la revisión 1 y, mientras construía, C avanzó la cabeza tocando OTRA ruta
    original = store.cargar_ultima

    async def leer_rancio(buyer_id, *, db=None):
        store.cargar_ultima = original
        ctx = await original(buyer_id, db=db)
        # simula que la cabeza avanzó por otra conversación tras esta lectura
        avanzado = ctx.model_copy(update={
            "property_requirements": ctx.property_requirements.model_copy(
                update={"area_m2_min": 70.0}),
            "context_revision": 2})
        store.revisiones[buyer_id].append(avanzado)
        store.por_mensaje[(buyer_id, "m-C")] = 2
        return ctx

    store.cargar_ultima = leer_rancio
    monkey = store.cargar_ultima
    import app.buyer.actualizador as _a
    _a.cargar_ultima = monkey

    r = _correr(B1, _msg(mid="m-B", texto="al menos 2 dormitorios"),
                _proponente(_p("durable", mutacion=_BED)))
    _a.cargar_ultima = original

    assert r.estado is EstadoActualizacion.CREADA
    assert r.contexto.property_requirements.bedrooms_min == 2
    assert r.contexto.property_requirements.area_m2_min == 70.0, \
        "el rebase perdió el cambio concurrente"
    assert r.contexto.financial.budget_max.amount == Decimal(120000)


def test_G6_un_SOLAPE_no_se_resuelve_con_last_write_wins(store):
    """C1 entre mensajes: dos declaraciones sobre la misma dimensión, sin nada que autorice
    elegir una, no se resuelven adivinando."""
    _correr(B1, _msg(mid="m-A", texto="máximo 120000 USD"),
            _proponente(_p("durable", mutacion=_BUD)))

    original = store.cargar_ultima
    import app.buyer.actualizador as _a

    async def leer_rancio(buyer_id, *, db=None):
        _a.cargar_ultima = original
        ctx = await original(buyer_id, db=db)
        avanzado = ctx.model_copy(update={
            "financial": ctx.financial.model_copy(
                update={"budget_max": Money(amount=Decimal(90000), currency="USD")}),
            "context_revision": 2})
        store.revisiones[buyer_id].append(avanzado)
        store.por_mensaje[(buyer_id, "m-C")] = 2
        return ctx

    _a.cargar_ultima = leer_rancio
    r = _correr(B1, _msg(mid="m-B", texto="máximo 150000 USD"),
                _proponente(_p("durable", mutacion=SetBudgetMax(amount=Decimal(150000),
                                                                currency=USD))))
    _a.cargar_ultima = original

    assert r.estado is EstadoActualizacion.CONFLICTO
    assert not r.persistido
    # el valor concurrente NO se pisó
    assert store.revisiones[B1][-1].financial.budget_max.amount == Decimal(90000)


def test_G6_rutas_divergentes_ve_tambien_las_preguntas_abiertas():
    """Si otra conversación abrió un `unresolved` sobre una ruta, esa ruta está en disputa
    aunque su valor no haya cambiado."""
    base = BuyerContextV0(buyer_id=B1, updated_at=T0)
    con_pregunta = base.model_copy(update={"unresolved_questions": (
        UnresolvedQuestion(question="¿cuál es tu tope?",
                           about_field="financial.budget_max"),)})
    assert "financial.budget_max" in rutas_divergentes(base, con_pregunta)


def test_G6_los_lectores_cubren_las_CINCO_rutas_del_contrato():
    """META-TEST: si aparece una sexta ruta y nadie la añade, la concurrencia dejaría de verla
    y dos escrituras sobre ella parecerían disjuntas."""
    from app.buyer.boundary import _RUTA_CONTRACTUAL

    assert set(act._LECTORES) == set(_RUTA_CONTRACTUAL.values())


# ══ GATE 7 · el PRIMER contexto ═════════════════════════════════════════════════════


def test_G7_el_primer_contexto_nace_sin_revision_y_el_store_le_pone_la_suya(store):
    r = _correr(B1, _msg(), _proponente(_p("durable", mutacion=_BUD)))

    assert r.estado is EstadoActualizacion.CREADA
    assert r.revision == 0, "la primera revisión del store real es 0"
    assert r.contexto.buyer_id == B1
    assert r.contexto.financial.budget_max.amount == Decimal(120000)


def test_G7_el_updater_no_inventa_una_cuarta_fuente_de_tiempo():
    """`updated_at` lo reescribe el store al persistir y `_canonico` lo excluye. Se pasa
    `retrieved_at` —un instante verdadero, el del procesamiento— en vez de un `now()` nuevo:
    esta fase acaba de separar tres conceptos temporales y no conviene añadir un cuarto."""
    inicial = act._contexto_inicial(B1, T0)
    assert inicial.updated_at == T0
    assert inicial.context_revision is None


# ══ GATE 8 · resultado tipado ═══════════════════════════════════════════════════════


def test_G8_los_seis_desenlaces_son_distinguibles_sin_leer_excepciones():
    """El shadow wiring no debe inferir el desenlace de un tipo de excepción o de un `None`.
    Eso sería pedirle que reconstruya una decisión que aquí ya se tomó."""
    assert {e.value for e in EstadoActualizacion} == {
        "creada", "no_op", "replay", "vacio", "conflicto", "fallido"}


@pytest.mark.parametrize("estado,persistido", [
    (EstadoActualizacion.CREADA, True), (EstadoActualizacion.NO_OP, True),
    (EstadoActualizacion.REPLAY, True), (EstadoActualizacion.VACIO, False),
    (EstadoActualizacion.CONFLICTO, False), (EstadoActualizacion.FALLIDO, False),
])
def test_G8_persistido_y_procesado_no_se_infieren_del_contexto(estado, persistido):
    assert ResultadoUpdater(estado).persistido is persistido


# ══ GATE 6b · E3.2b.3a · la divergencia se mide POR RUTA y con procedencia ══════════
#
# Dos defectos que el skip de Postgres estaba tapando, los dos en `rutas_divergentes`:
#
#   1 · con `base=None` devolvía LAS CINCO rutas, así que la primera escritura concurrente
#       sobre un comprador nuevo SIEMPRE daba conflicto — incluso entre rutas disjuntas. El
#       test `budget || bedrooms` no estaba "sin verificar": contradecía la implementación.
#
#   2 · comparaba valor y preguntas, pero NO la procedencia. Redeclarar el mismo valor desde
#       otro mensaje cambia `field_evidence` y no cambia nada más, así que la ruta parecía
#       intacta y otro escritor podía rebasarse encima. R7 acaba de congelar que la evidencia
#       vigente es parte de lo que sostiene el valor.


def _con_budget(ctx, monto=120000, mid="m-base"):
    return reducir(ctx, construir_lote(_msg(mid=mid, texto=f"máximo {monto} USD"),
                                       [AfirmacionDurable(
                                           mutacion=SetBudgetMax(amount=Decimal(monto),
                                                                 currency=USD),
                                           motivo="tope")]), T0)


def _con_bedrooms(ctx, n=2, mid="m-base"):
    return reducir(ctx, construir_lote(_msg(mid=mid, texto=f"al menos {n} dormitorios"),
                                       [AfirmacionDurable(mutacion=SetBedroomsMin(bedrooms_min=n),
                                                          motivo="mínimo")]), T0)


def _vacio():
    return BuyerContextV0(buyer_id=B1, updated_at=T0)


@pytest.mark.parametrize("construir,esperada", [
    (_con_budget, "financial.budget_max"),
    (_con_bedrooms, "property_requirements.bedrooms_min"),
])
def test_G6b_desde_VACIO_solo_diverge_la_ruta_que_se_escribio(construir, esperada):
    """EL DEFECTO QUE EL SKIP ESCONDÍA.

    `base=None` significa "cuando leí no había estado", no "todo cambió". Devolver las cinco
    rutas hacía que la primera escritura concurrente sobre un comprador nuevo diera conflicto
    aunque las dos conversaciones tocaran dimensiones distintas — que es justo el caso que la
    política congelada manda rebasar.
    """
    assert rutas_divergentes(None, construir(_vacio())) == {esperada}


def test_G6b_dos_primeras_escrituras_DISJUNTAS_se_rebasan(store):
    """`budget || bedrooms` sobre un comprador nuevo: ninguna toca lo de la otra, así que la
    que pierde la carrera se rebasa y las dos sobreviven."""
    _correr(B1, _msg(mid="m-A", texto="máximo 120000 USD"),
            _proponente(_p("durable", mutacion=_BUD)))

    original = store.cargar_ultima
    import app.buyer.actualizador as _a

    async def leer_rancio(buyer_id, *, db=None):
        _a.cargar_ultima = original
        return None          # B leyó ANTES de que A escribiera: base=None

    _a.cargar_ultima = leer_rancio
    r = _correr(B1, _msg(mid="m-B", texto="al menos 2 dormitorios"),
                _proponente(_p("durable", mutacion=_BED)))
    _a.cargar_ultima = original

    assert r.estado is EstadoActualizacion.CREADA
    assert r.contexto.property_requirements.bedrooms_min == 2
    assert r.contexto.financial.budget_max.amount == Decimal(120000), \
        "el rebase perdió la primera escritura"


def test_G6b_dos_primeras_escrituras_SOLAPADAS_dan_conflicto(store):
    """`budget || budget` sobre un comprador nuevo: sigue sin haber last-write-wins."""
    _correr(B1, _msg(mid="m-A", texto="máximo 120000 USD"),
            _proponente(_p("durable", mutacion=_BUD)))

    original = store.cargar_ultima
    import app.buyer.actualizador as _a

    async def leer_rancio(buyer_id, *, db=None):
        _a.cargar_ultima = original
        return None

    _a.cargar_ultima = leer_rancio
    r = _correr(B1, _msg(mid="m-B", texto="máximo 90000 USD"),
                _proponente(_p("durable",
                               mutacion=SetBudgetMax(amount=Decimal(90000), currency=USD))))
    _a.cargar_ultima = original

    assert r.estado is EstadoActualizacion.CONFLICTO
    assert store.revisiones[B1][-1].financial.budget_max.amount == Decimal(120000)


def test_G6b_redeclarar_el_MISMO_valor_desde_otro_mensaje_SI_es_divergencia():
    """El segundo defecto. El valor no cambia pero la procedencia sí, y R7 congela que la
    evidencia vigente es parte de lo que sostiene el valor.

    Sin esto, otro escritor sobre esa misma ruta se rebasaría encima creyéndola intacta — y
    el resultado citaría un mensaje que ya no es el que respalda el valor final.
    """
    base = _con_budget(_vacio(), mid="m-1")
    tras_A = _con_budget(base, mid="m-A")          # mismo 120000, otro mensaje

    assert base.financial.budget_max == tras_A.financial.budget_max
    assert "financial.budget_max" in rutas_divergentes(base, tras_A)


def test_G6b_la_procedencia_OPERACIONAL_no_cuenta_como_divergencia():
    """El límite del arreglo anterior: R-IDEMP-1 ya decidió que `evidence_id` y `retrieved_at`
    de una `USER_DECLARED` no son estado. Si contaran aquí, un replay parecería divergencia y
    volveríamos al problema que R-IDEMP-1 cerró, por otra puerta."""
    base = _con_budget(_vacio(), mid="m-1")
    otro_instante = reducir(_vacio(), construir_lote(
        _msg(mid="m-1", texto="máximo 120000 USD"),
        [AfirmacionDurable(mutacion=_BUD, motivo="tope")]),
        T0 + dt.timedelta(seconds=45))

    assert rutas_divergentes(base, otro_instante) == frozenset()


def test_G6b_un_TURN_ONLY_concurrente_no_bloquea_un_cambio_independiente(store):
    """`touched_paths` vacío ⇒ nunca solapa con nada."""
    _correr(B1, _msg(mid="m-A", texto="máximo 120000 USD"),
            _proponente(_p("durable", mutacion=_BUD)))

    original = store.cargar_ultima
    import app.buyer.actualizador as _a

    async def leer_rancio(buyer_id, *, db=None):
        _a.cargar_ultima = original
        return None

    _a.cargar_ultima = leer_rancio
    r = _correr(B1, _msg(mid="m-B", texto="¿qué tal el barrio?"),
                _proponente(_p("turn_only")))
    _a.cargar_ultima = original

    assert r.estado is EstadoActualizacion.NO_OP
    assert r.contexto.financial.budget_max.amount == Decimal(120000)


def test_G6b_una_AMBIGUA_concurrente_sobre_la_ruta_de_una_durable_SOLAPA(store):
    """Abrir una pregunta sobre el presupuesto reclama el presupuesto: si otra conversación lo
    declaró a la vez, no son independientes."""
    _correr(B1, _msg(mid="m-A", texto="máximo 120000 USD"),
            _proponente(_p("durable", mutacion=_BUD)))

    original = store.cargar_ultima
    import app.buyer.actualizador as _a

    async def leer_rancio(buyer_id, *, db=None):
        _a.cargar_ultima = original
        return None

    _a.cargar_ultima = leer_rancio
    r = _correr(B1, _msg(mid="m-B", texto="unos 90000 más o menos"),
                _proponente(_p("ambiguous", campo=F.BUDGET_MAX)))
    _a.cargar_ultima = original

    assert r.estado is EstadoActualizacion.CONFLICTO


def test_G6b_el_doble_numera_como_el_store_REAL():
    """META-TEST de fidelidad. El store real arranca en 0 (`0 if actual is None else actual+1`)
    y el doble arrancaba en 1. Una divergencia así hace que los asserts sobre `revision` de la
    suite offline y los de la suite Postgres afirmen cosas distintas, y sólo una sea cierta.
    """
    import inspect

    from app.buyer import store as store_real

    fuente = inspect.getsource(store_real._ejecutar_anexo)
    assert "nueva = 0 if actual is None else actual + 1" in fuente, (
        "cambió la numeración del store real: revisar `_StoreDoble`")

    doble = _StoreDoble()
    ctx = BuyerContextV0(buyer_id=B1, updated_at=T0)
    primera = asyncio.run(doble.anexar_revision(B1, "m-1", ctx, None))
    segunda = asyncio.run(doble.anexar_revision(B1, "m-2", ctx, primera.revision))
    assert (primera.revision, segunda.revision) == (0, 1)
