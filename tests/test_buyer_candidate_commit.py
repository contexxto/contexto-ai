"""F3-CANDIDATE-COMMIT-R0C · persistir el candidato YA calculado, sin volver a interpretarlo.

QUÉ CONGELA, y qué NO.

    congela    que el cómputo que R0B hace antes de la decisión se puede PERSISTIR tal cual:
               una interpretación por turno, la memoria final corresponde al candidato que se
               observó, y cuando la base se movió por el camino el desenlace lo DICE en vez
               de disfrazarlo de escritura limpia
    NO congela que `BuyerContext` pueda gobernar ranking, panel ni prosa. R0C sigue siendo
               SHADOW ONLY: `CURRENT_AUTHORITY_WHITELIST` sigue vacía

## LA DEUDA QUE CIERRA

R0B dejó medido —y escrito— que con el candidato y el updater encendidos a la vez el mismo
turno se interpretaba DOS veces. `interpretar_mensaje` usa el LLM, así que dos llamadas sobre
el mismo texto pueden no coincidir: se decidía con un candidato y se guardaba otro. R0C parte
`actualizar()` en `computar_candidato()` + `persistir_computo()` y hace que la sombra reciba
el cómputo ya hecho. La interpretación del turno pasa a ser **una**, y eso se mide, no se
supone.

## LA PRECISIÓN QUE EL MANDATO EXIGE ARRASTRAR

*"Persistir exactamente el candidato"* sólo es semánticamente exacto **sin concurrencia**. Si
otra conversación movió la cabeza entre el cómputo y la escritura, lo que se persiste ya no es
el artefacto original: es el mismo lote reducido otra vez sobre una base distinta. La regla
que gobierna este fichero, literal:

> La concurrencia no invalida el candidato original; invalida la afirmación de que puede
> persistirse sin volver a reducir.

Por eso `REBASEADA` existe y por eso T6/T9 son dos tests y no uno: uno afirma que el rebase
ocurre, el otro que el artefacto original **no se transforma en silencio** en el rebasado.

## EL ARNÉS

Doble del store con el contrato COMPLETO —idempotencia por `source_message_id` antes que
conflicto de revisión, revisiones desde 0— y proponente inyectable. Deterministas a propósito:
esto no es un eval del modelo, y **no hay juez LLM** en ninguna parte.
"""

from __future__ import annotations

import ast
import asyncio
import datetime as dt
import pathlib
from decimal import Decimal

import pytest

from app.buyer import actualizador as act
from app.buyer import candidato as cand
from app.buyer import sombra as som
from app.buyer.actualizador import (
    ComputoCandidato, EstadoActualizacion, actualizar, computar_candidato, persistir_computo,
)
from app.buyer.boundary import BuyerCurrencyV0, SetAreaM2Min, SetBedroomsMin, SetBudgetMax
from app.buyer.interprete import PropuestaV0
from app.buyer.mensaje import IdentifiedUserMessage
from app.buyer.sombra import ComputoDeOtroComprador, actualizar_en_sombra
from app.buyer.store import (
    BuyerContextV0, BuyerIdempotencyConflict, BuyerRevisionConflict, RevisionPersistida,
    _canonico,
)
from app.contracts.common_v0 import Money

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CHAT = RAIZ / "app" / "routers" / "chat.py"

T0 = dt.datetime(2026, 9, 11, 12, 0, tzinfo=dt.timezone.utc)
USD = BuyerCurrencyV0.USD
A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"
MSG = "msg-33333333-3333-4333-8333-333333333333"

_BUD = PropuestaV0(disposicion="durable", motivo="tope",
                   mutacion=SetBudgetMax(amount=Decimal(120000), currency=USD))
_BED = PropuestaV0(disposicion="durable", motivo="mínimo",
                   mutacion=SetBedroomsMin(bedrooms_min=2))
_AREA = PropuestaV0(disposicion="durable", motivo="superficie",
                    mutacion=SetAreaM2Min(area_m2_min=70.0))


_TXT_BED = "al menos 2 dormitorios"
"""El texto TIENE que sostener la propuesta. G16 no acredita una afirmación sobre dormitorios
a partir de un texto que habla de presupuesto: la degrada a `AMBIGUOUS` y abre una pregunta en
vez de escribir un valor. Un arnés que ignore eso mediría el fallo de acreditación creyendo
que mide el rebase — ya pasó una vez en este fichero."""


def _msg(mid=MSG, texto="máximo 120000 USD"):
    return IdentifiedUserMessage(message_id=mid, text=texto)


def _proponente(*propuestas):
    async def proponer(_texto):
        return propuestas
    return proponer


class _StoreDoble:
    """Reimplementa el contrato del store en memoria. **No lo simplifica.**

    Copiado del doble de `test_buyer_actualizador.py` deliberadamente y no importado: un doble
    compartido entre suites se relaja para servir a la que más aprieta, y aquí lo que se mide
    es precisamente el orden interno —idempotencia ANTES que conflicto de revisión— del que
    depende que un replay no se confunda con una carrera.
    """

    def __init__(self):
        self.revisiones: dict[str, list] = {}
        self.por_mensaje: dict[tuple[str, str], int] = {}
        self.escrituras = 0
        """Intentos de anexar, no revisiones creadas. Un replay también cuenta como intento:
        es la diferencia entre «cuántas veces se llamó al store» y «cuántas filas hay»."""

    async def cargar_ultima(self, buyer_id, *, db=None):
        historial = self.revisiones.get(buyer_id) or []
        return historial[-1] if historial else None

    async def anexar_revision(self, buyer_id, source_message_id, contexto,
                              expected_revision, *, db=None):
        if contexto.buyer_id != buyer_id:
            raise AssertionError("el doble no debe recibir un contexto de otro comprador")
        self.escrituras += 1
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

        nueva = 0 if actual is None else actual + 1
        guardado = contexto.model_copy(update={"context_revision": nueva, "updated_at": T0})
        historial.append(guardado)
        self.por_mensaje[clave] = nueva
        return RevisionPersistida(guardado, nueva, creada=True)

    # ── el movimiento concurrente, explícito ────────────────────────────────────────

    def avanza_la_cabeza(self, buyer_id, **campos):
        """Otra conversación escribió mientras nosotros pensábamos.

        Se llama ENTRE el cómputo y la persistencia, que es exactamente la ventana que R0C
        abre y que `actualizar()` no tenía. No se simula con un `cargar_ultima` rancio: aquí
        la carrera es real porque las dos fases están de verdad separadas en el tiempo.
        """
        historial = self.revisiones.setdefault(buyer_id, [])
        base = historial[-1] if historial else BuyerContextV0(buyer_id=buyer_id,
                                                             updated_at=T0)
        siguiente = 0 if not historial else historial[-1].context_revision + 1

        # Se REVALIDA en vez de `model_copy(update=...)`, y no es un detalle de estilo:
        # `model_copy` no valida, así que un `{"financial": {...}}` se quedaría siendo un
        # `dict` dentro del modelo y el reductor reventaría al leerlo. Un doble que produce
        # estados que el sistema real no puede producir mide otra cosa.
        datos = base.model_dump()
        for clave, valor in campos.items():
            if isinstance(valor, dict) and isinstance(datos.get(clave), dict):
                datos[clave] = {**datos[clave], **valor}
            else:
                datos[clave] = valor
        datos["context_revision"] = siguiente
        avanzado = BuyerContextV0.model_validate(datos)
        historial.append(avanzado)
        self.por_mensaje[(buyer_id, f"m-concurrente-{siguiente}")] = siguiente
        return avanzado


@pytest.fixture
def store(monkeypatch):
    doble = _StoreDoble()
    monkeypatch.setattr(act, "cargar_ultima", doble.cargar_ultima)
    monkeypatch.setattr(act, "anexar_revision", doble.anexar_revision)
    return doble


@pytest.fixture
def contador(monkeypatch):
    """Cuenta las interpretaciones. Es EL instrumento de esta unidad.

    Casi todo lo que R0C afirma se reduce a «¿cuántas veces se llamó al LLM?», así que este
    contador tiene que ser incapaz de mentir por omisión: envuelve la función en el módulo
    `actualizador`, que es por donde pasan las dos fases.
    """
    veces = {"n": 0}
    original = act.interpretar_mensaje

    async def contado(mensaje, proponente=None):
        veces["n"] += 1
        # El carril LEGACY (`actualizar()` sin cómputo) no recibe proponente: llamaría al
        # modelo de verdad. Se le inyecta el mismo que usan los cómputos explícitos para que
        # las dos ramas de la matriz de flags sean comparables — si una fuera determinista y
        # la otra no, T13 mediría el modelo en vez de los flags.
        return await original(mensaje, proponente or _proponente(_BUD))

    monkeypatch.setattr(act, "interpretar_mensaje", contado)
    return veces


def _computar(buyer_id=A, *, mid=MSG, texto="máximo 120000 USD", propuestas=(_BUD,)):
    return asyncio.run(computar_candidato(
        buyer_id, _msg(mid, texto), retrieved_at=T0, proponente=_proponente(*propuestas)))


def _persistir(computo):
    return asyncio.run(persistir_computo(computo))


def _fila(store, buyer_id=A):
    return len(store.revisiones.get(buyer_id) or [])


# ══ T1 · NO-CONFLICT · persistir no vuelve a interpretar ════════════════════════════


def test_T1_persistir_un_computo_ya_hecho_NO_interpreta_otra_vez(store, contador):
    """La afirmación central de R0C, y la que R0B no podía hacer.

    Una interpretación para COMPUTAR, cero para PERSISTIR. Si `persistir_computo` llamara al
    intérprete, el contador subiría a 2 y lo guardado podría no ser lo observado.
    """
    computo = _computar()
    assert contador["n"] == 1, "el cómputo interpreta una vez: ésa es la línea base"

    resultado = _persistir(computo)

    assert contador["n"] == 1, "PERSIST volvió a interpretar: R0C no cierra nada"
    assert resultado.estado is EstadoActualizacion.CREADA
    assert resultado.rebasado is False
    assert resultado.revision == 0
    assert resultado.base_revision is None, "un comprador nuevo no tiene base de partida"


def test_T1b_persistir_un_computo_VACIO_no_escribe_ni_interpreta(store, contador):
    """Sin afirmaciones no hay nada que materializar, y el desenlace lo dice."""
    computo = _computar(propuestas=())
    resultado = _persistir(computo)

    assert computo.candidato is None
    assert resultado.estado is EstadoActualizacion.VACIO
    assert not resultado.persistido
    assert store.escrituras == 0
    assert contador["n"] == 1


# ══ T2 · CONVERGENCIA SEMÁNTICA ═════════════════════════════════════════════════════


def test_T2_lo_persistido_ES_el_candidato_observado(store, contador):
    """`_canonico` es el árbitro, y es el mismo que usa el store para decidir idempotencia.

    No se compara el objeto entero a propósito: `context_revision` y `updated_at` los pone la
    escritura, así que exigir igualdad literal mediría el store, no la convergencia.
    """
    computo = _computar()
    resultado = _persistir(computo)

    assert _canonico(resultado.contexto) == _canonico(computo.candidato.contexto), \
        "lo guardado no es semánticamente el candidato que se observó"
    assert resultado.contexto.financial.budget_max.amount == Decimal(120000)


# ══ T3 · REPLAY DEL MISMO ARTEFACTO ═════════════════════════════════════════════════


def test_T3_persistir_DOS_veces_el_mismo_artefacto_da_REPLAY_y_una_sola_revision(
        store, contador):
    """Idempotencia por `source_message_id`: el mismo mensaje no puede crear dos revisiones.

    Importa que sea `REPLAY` y no `CONFLICTO`: un reintento y una carrera son cosas distintas,
    y el store las distingue consultando el id ANTES que la revisión.
    """
    computo = _computar()
    primero = _persistir(computo)
    segundo = _persistir(computo)

    assert primero.estado is EstadoActualizacion.CREADA
    assert segundo.estado is EstadoActualizacion.REPLAY
    assert segundo.persistido, "un replay deja el mensaje sellado igual"
    assert segundo.revision == primero.revision
    assert _fila(store) == 1, "el mismo artefacto creó una segunda revisión"
    assert contador["n"] == 1, "reproducir no puede costar otra interpretación"


# ══ T4 · MISMO ID, CARGA DIVERGENTE ═════════════════════════════════════════════════


def test_T4_mismo_source_id_con_candidato_DISTINTO_falla_explicitamente(store, contador):
    """El caso que no puede resolverse en silencio.

    Si el mismo mensaje produce dos estados distintos, o el intérprete no es determinista o
    hay un replay corrupto. Elegir uno sería inventar; el desenlace es `FALLIDO` y no hay
    segunda revisión.
    """
    _persistir(_computar(propuestas=(_BUD,)))
    otro = _computar(texto=_TXT_BED, propuestas=(_BED,))

    resultado = _persistir(otro)

    assert resultado.estado is EstadoActualizacion.FALLIDO
    assert not resultado.persistido
    assert _fila(store) == 1, "un id divergente no puede añadir una revisión"


# ══ T5 · CONFLICTO DE REVISIÓN DETECTADO ════════════════════════════════════════════


def test_T5_si_la_cabeza_avanzo_entre_computo_y_escritura_se_DETECTA(store, contador):
    """La ventana que R0C abre: el cómputo lee la revisión R y la escritura llega con R+1 ya
    puesta. El store tiene que rechazar la escritura ciega, no aceptarla."""
    _persistir(_computar(mid="m-0", propuestas=(_BUD,)))
    computo = _computar(mid="m-1", texto=_TXT_BED, propuestas=(_BED,))
    assert computo.candidato.base_context_revision == 0

    store.avanza_la_cabeza(A, property_requirements={"area_m2_min": 70.0})
    assert store.revisiones[A][-1].context_revision == 1

    resultado = _persistir(computo)

    assert resultado.estado is not EstadoActualizacion.CREADA, \
        "escribir sobre una base movida sin decirlo es exactamente lo que no puede pasar"
    assert resultado.rebasado is True
    assert resultado.base_revision == 1, "la base efectiva es la revisión nueva, no la leída"


# ══ T6 · REBASE DISJUNTO ════════════════════════════════════════════════════════════


def test_T6_cambios_DISJUNTOS_se_rebasan_con_el_MISMO_lote(store, contador):
    """Un hecho no puede costar otro sólo por llegar a la vez.

    El rebase no reinterpreta a la persona: reduce el MISMO lote sobre la base nueva. Por eso
    el estado final conserva las dos declaraciones y el contador no se mueve.
    """
    _persistir(_computar(mid="m-0", propuestas=(_BUD,)))
    computo = _computar(mid="m-1", texto=_TXT_BED, propuestas=(_BED,))
    interpretaciones = contador["n"]

    store.avanza_la_cabeza(A, property_requirements={"area_m2_min": 70.0})
    resultado = _persistir(computo)

    assert resultado.estado is EstadoActualizacion.REBASEADA
    assert resultado.rebasado is True
    assert resultado.revision == 2
    assert contador["n"] == interpretaciones, "el rebase interpretó otra vez"

    # Las TRES declaraciones sobreviven: la propia, la anterior y la concurrente.
    assert resultado.contexto.property_requirements.bedrooms_min == 2
    assert resultado.contexto.property_requirements.area_m2_min == 70.0, \
        "el rebase perdió el cambio concurrente"
    assert resultado.contexto.financial.budget_max.amount == Decimal(120000)


def test_T6b_el_lote_del_rebase_es_LITERALMENTE_el_mismo_objeto(store, contador):
    """Más fuerte que «equivalente»: el mismo `lote`, la misma identidad.

    Si el rebase construyera un lote nuevo —aunque saliera igual— la afirmación «misma
    evidencia» dependería de que dos construcciones coincidan, y eso es justo lo que no se
    puede dar por hecho cuando hay un modelo de por medio.
    """
    _persistir(_computar(mid="m-0", propuestas=(_BUD,)))
    computo = _computar(mid="m-1", texto=_TXT_BED, propuestas=(_BED,))
    lote_original = computo.candidato.lote

    store.avanza_la_cabeza(A, property_requirements={"area_m2_min": 70.0})
    _persistir(computo)

    assert computo.candidato.lote is lote_original


# ══ T7 · EL REBASE NO INTERPRETA ════════════════════════════════════════════════════


def test_T7_ni_persist_ni_rebase_llaman_al_interprete(store, contador):
    """El caso peor: dos intentos, un conflicto, un rebase. El contador sigue en 1."""
    _persistir(_computar(mid="m-0", propuestas=(_BUD,)))
    computo = _computar(mid="m-1", texto=_TXT_BED, propuestas=(_BED,))
    contador["n"] = 0  # a partir de aquí, CUALQUIER interpretación es una de más

    store.avanza_la_cabeza(A, property_requirements={"area_m2_min": 70.0})
    resultado = _persistir(computo)

    assert resultado.estado is EstadoActualizacion.REBASEADA
    assert contador["n"] == 0, "PERSIST + REBASE interpretaron; tienen prohibido hacerlo"


def test_T7b_persistir_no_importa_el_interprete_en_su_camino(store):
    """Estructural: `persistir_computo` no puede NOMBRAR al intérprete.

    El contador mide una ejecución; esto mira el código. Hacen falta los dos, porque un
    camino de fallback poco recorrido puede llamar al LLM sin que ninguna prueba lo pise.
    """
    fuente = (RAIZ / "app" / "buyer" / "actualizador.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(fuente))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "persistir_computo")
    llamadas = {n.func.id for n in ast.walk(fn)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}

    assert "interpretar_mensaje" not in llamadas
    assert "reducir" in llamadas, \
        "si no reduce, el rebase no existe y T6 estaría pasando por otro motivo"


# ══ T8 · SOLAPE · NO se escribe ═════════════════════════════════════════════════════


def test_T8_si_las_rutas_SOLAPAN_no_se_escribe_y_el_desenlace_es_CONFLICTO(
        store, contador):
    """C1 entre mensajes: dos declaraciones sobre la MISMA dimensión no se resuelven
    adivinando. Cero last-write-wins, y el valor concurrente queda intacto."""
    _persistir(_computar(mid="m-0", propuestas=(_BUD,)))
    computo = _computar(mid="m-1", propuestas=(
        PropuestaV0(disposicion="durable", motivo="otro tope",
                    mutacion=SetBudgetMax(amount=Decimal(150000), currency=USD)),))

    store.avanza_la_cabeza(A, financial={"budget_max": Money(amount=Decimal(90000),
                                                             currency="USD")})
    filas_antes = _fila(store)
    resultado = _persistir(computo)

    assert resultado.estado is EstadoActualizacion.CONFLICTO
    assert not resultado.persistido
    assert resultado.revision is None
    assert _fila(store) == filas_antes, "un solape no puede dejar fila"
    assert store.revisiones[A][-1].financial.budget_max.amount == Decimal(90000), \
        "el valor concurrente se pisó: eso es last-write-wins"


# ══ T9 · EL ARTEFACTO ORIGINAL NO MUTA ══════════════════════════════════════════════


def test_T9_el_computo_original_NO_se_convierte_en_el_rebasado(store, contador):
    """Lo que se persistió y lo que se observó DIVERGEN cuando hubo rebase, y eso tiene que
    poder verse.

    Si `persistir_computo` mutara el artefacto de entrada, la divergencia quedaría borrada y
    con ella la única evidencia de que la base se movió. El `ComputoCandidato` es `frozen`,
    pero congelar no basta: podría reasignarse el contexto interno. Se comprueba el valor.
    """
    _persistir(_computar(mid="m-0", propuestas=(_BUD,)))
    computo = _computar(mid="m-1", texto=_TXT_BED, propuestas=(_BED,))
    contexto_observado = computo.candidato.contexto
    base_observada = computo.candidato.base_context_revision
    canonico_antes = _canonico(contexto_observado)

    store.avanza_la_cabeza(A, property_requirements={"area_m2_min": 70.0})
    resultado = _persistir(computo)

    assert computo.candidato.contexto is contexto_observado
    assert _canonico(computo.candidato.contexto) == canonico_antes
    assert computo.candidato.base_context_revision == base_observada == 0

    assert _canonico(resultado.contexto) != canonico_antes, \
        "si coincidieran, el rebase no habría incorporado nada y T6 estaría vacío"


def test_T9b_el_ComputoCandidato_es_inmutable_por_construccion():
    """La mitad estructural de T9: el dataclass está congelado."""
    computo = ComputoCandidato(estado=EstadoActualizacion.VACIO)
    with pytest.raises(Exception):
        computo.estado = EstadoActualizacion.CREADA


# ══ T10 · CARRIL LEGACY INTACTO ═════════════════════════════════════════════════════


@pytest.fixture
def sombra_encendida(monkeypatch):
    """La sombra con la base neutralizada: aquí se mide POLÍTICA, no SQL."""
    monkeypatch.setattr(som.settings, "buyer_updater_shadow", True)
    monkeypatch.setattr(som.settings, "buyer_shadow_allowlist", f"{A},{B}")

    async def _hay_esquema(_db):
        return True

    class _Sesion:
        def __init__(self):
            self.commits = 0
            self.rollbacks = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def commit(self):
            self.commits += 1

        async def rollback(self):
            self.rollbacks += 1

    sesion = _Sesion()
    monkeypatch.setattr(som, "_hay_esquema", _hay_esquema)
    monkeypatch.setattr("app.database.AsyncSessionLocal", lambda: sesion)
    return sesion


class _Usuario:
    def __init__(self, user_id=A):
        self.user_id = user_id


def _humano(texto="máximo 120000 USD", mid=MSG):
    from langchain_core.messages import HumanMessage
    return [HumanMessage(content=texto, id=mid)]


def test_T10_sin_computo_la_sombra_se_comporta_EXACTAMENTE_como_antes(
        store, contador, sombra_encendida):
    """CANDIDATE OFF · UPDATER ON. El parámetro es opcional a propósito: ningún llamador
    existente tiene que producir un candidato para seguir funcionando igual.

    Se llama SIN `computo`, que es exactamente la firma que usaba el carril legacy antes de
    R0C: si esta llamada necesitara cambiar, la compatibilidad no existiría.
    """
    asyncio.run(actualizar_en_sombra(_Usuario(), _humano()))

    assert contador["n"] == 1, "el carril legacy interpreta una vez, como siempre"
    assert _fila(store) == 1
    assert sombra_encendida.commits == 1


# ══ T11 · UNA SOLA INTERPRETACIÓN ═══════════════════════════════════════════════════


def test_T11_candidato_mas_updater_dan_UNA_interpretacion_en_total(
        store, contador, sombra_encendida):
    """CANDIDATE ON · UPDATER ON — la combinación que R0B midió en 2 y R0C deja en 1.

    Es la prueba que da sentido a toda la unidad: sin ella, «una política» seguiría siendo
    compatible con «dos llamadas al modelo».
    """
    computo = _computar()
    assert contador["n"] == 1

    asyncio.run(actualizar_en_sombra(_Usuario(), _humano(), computo=computo))

    assert contador["n"] == 1, "la sombra reinterpretó el turno: la deuda sigue abierta"
    assert _fila(store) == 1
    assert sombra_encendida.commits == 1


# ══ T12 · UN SOLO ESCRITOR ══════════════════════════════════════════════════════════


def test_T12_un_turno_normal_intenta_UNA_sola_persistencia(store, contador,
                                                            sombra_encendida):
    computo = _computar()
    asyncio.run(actualizar_en_sombra(_Usuario(), _humano(), computo=computo))

    assert store.escrituras == 1, \
        f"el turno llamó {store.escrituras} veces al store; se esperaba 1"
    assert _fila(store) == 1


def test_T12b_chat_no_puede_invocar_las_DOS_ramas_en_el_mismo_turno():
    """Estructural sobre el endpoint: las dos costuras son EXCLUYENTES.

    Una diferida (`create_task`, carril legacy) y una esperada (`await`, commit del
    candidato), gobernadas por condiciones complementarias sobre el mismo `computo`. Si
    compartieran condición, un turno escribiría dos veces.
    """
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    for nombre in ("chat", "_stream_agent"):
        fn = next(n for n in ast.walk(arbol)
                  if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                  and n.name == nombre)
        llamadas = [n for n in ast.walk(fn) if isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Name)
                    and n.func.id == "actualizar_en_sombra"]
        assert len(llamadas) == 2, f"{nombre}(): {len(llamadas)} costuras, se esperaban 2"

        condiciones = []
        for llamada in llamadas:
            envolventes = [n for n in ast.walk(fn) if isinstance(n, ast.If)
                           and any(c is llamada for c in ast.walk(n))]
            assert envolventes, f"{nombre}(): una costura corre sin condición"
            condiciones.append(
                ast.dump(min(envolventes, key=lambda n: len(list(ast.walk(n)))).test))

        assert condiciones[0] != condiciones[1], \
            f"{nombre}(): las dos costuras comparten condición"
        assert all("computo" in c for c in condiciones)
        assert ("Is()" in condiciones[0]) != ("Is()" in condiciones[1]), \
            f"{nombre}(): las condiciones no son complementarias"


# ══ T13 · MATRIZ DE FLAGS ═══════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "candidato_on, updater_on, interpretaciones, filas, comentario", [
        (False, False, 0, 0, "nada"),
        (True, False, 1, 0, "compute shadow, sin persistir"),
        (False, True, 1, 1, "updater legacy: una interpretación y persiste"),
        (True, True, 1, 1, "compute una vez y se persiste ESE compute"),
    ])
def test_T13_la_matriz_de_los_dos_flags(store, contador, monkeypatch, sombra_encendida,
                                        candidato_on, updater_on, interpretaciones, filas,
                                        comentario):
    """Los dos flags son permisos distintos: COMPUTE y WRITE. No se crea un tercero.

    La fila que R0C hace verdadera es la última: `ON + ON` deja de significar «dos
    interpretaciones» y pasa a significar «una, y se persiste ésa».
    """
    monkeypatch.setattr(cand.settings, "buyer_current_turn_candidate_shadow", candidato_on,
                        raising=False)
    monkeypatch.setattr(cand.settings, "buyer_shadow_allowlist", A, raising=False)
    monkeypatch.setattr(som.settings, "buyer_updater_shadow", updater_on)

    observacion = asyncio.run(cand.observar_candidato_del_turno(
        _Usuario(), _humano(), retrieved_at=T0, proponente=_proponente(_BUD)))

    asyncio.run(actualizar_en_sombra(_Usuario(), _humano(), computo=observacion.computo))

    assert contador["n"] == interpretaciones, comentario
    assert _fila(store) == filas, comentario


def test_T13b_el_flag_del_candidato_viene_APAGADO_de_fabrica():
    from app.config import Settings

    ajustes = Settings(postgres_db="x", postgres_user="x", postgres_password="x")
    assert ajustes.buyer_current_turn_candidate_shadow is False
    assert ajustes.buyer_updater_shadow is False


# ══ T14 · NINGÚN FALLBACK REINTERPRETA ══════════════════════════════════════════════


def test_T14_si_la_persistencia_FALLA_nadie_vuelve_a_interpretar(
        store, contador, sombra_encendida, monkeypatch):
    """El fallback prohibido: «no pude guardar, lo intento de nuevo desde el principio».

    Reinterpretar tras un fallo daría una extracción distinta de la que se observó, que es
    exactamente el defecto que R0C cierra. El fallo se registra y se queda ahí.
    """
    computo = _computar()
    contador["n"] = 0

    async def revienta(*a, **kw):
        raise RuntimeError("la base se cayó")

    monkeypatch.setattr(act, "anexar_revision", revienta)

    asyncio.run(actualizar_en_sombra(_Usuario(), _humano(), computo=computo))

    assert contador["n"] == 0, "hubo una reinterpretación después del fallo"
    assert _fila(store) == 0


# ══ T15 · ANÓNIMO ══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("anon", [None, "", "   "])
def test_T15_un_anonimo_no_persiste_aunque_traiga_computo(store, sombra_encendida, anon):
    """Un anónimo no tiene raíz. Traer un cómputo no se la da."""
    computo = _computar()
    usuario = None if anon is None else _Usuario(anon)

    asyncio.run(actualizar_en_sombra(usuario, _humano(), computo=computo))

    assert _fila(store) == 0
    assert store.escrituras == 0


# ══ T16 · BINDING COMPRADOR ↔ PRINCIPAL ═════════════════════════════════════════════


def test_T16_el_computo_del_MISMO_comprador_se_persiste(store, contador,
                                                        sombra_encendida):
    computo = _computar(A)
    asyncio.run(actualizar_en_sombra(_Usuario(A), _humano(), computo=computo))

    assert _fila(store, A) == 1


def test_T16b_el_computo_de_OTRO_comprador_se_rechaza_y_no_escribe(
        store, contador, sombra_encendida, caplog):
    """La costura nueva de R0C, y por eso necesita guardia propia.

    La procedencia del principal está congelada aguas arriba (1B/E1): no hay entrada directa
    de `buyer_id`. Pero esta costura —entregar un cómputo YA HECHO a un escritor— es nueva, y
    sin comprobación existiría un camino por el que el artefacto de A se persistiera bajo la
    raíz de B. No se degrada: se levanta, porque si ocurre es que dos nociones de «quién es
    el comprador» han divergido y eso hay que verlo.
    """
    ajeno = _computar(B)
    with caplog.at_level("ERROR"):
        asyncio.run(actualizar_en_sombra(_Usuario(A), _humano(), computo=ajeno))

    assert _fila(store, A) == 0 and _fila(store, B) == 0
    assert store.escrituras == 0, "se llegó a tocar el store con un artefacto ajeno"
    assert any("aislado" in r.message for r in caplog.records), \
        "el rechazo tiene que quedar registrado, no desaparecer"


def test_T16c_el_rechazo_LEVANTA_y_no_se_degrada_en_silencio():
    """Dónde vive la garantía, y por qué se levanta en vez de volver sin más.

    `persistir_computo` NO comprueba propiedad: recibe un artefacto que da por validado, y
    ésa es una decisión, no un descuido —la fase de persistencia no conoce al principal, sólo
    al artefacto—. La comprobación vive entera en `actualizar_en_sombra`, que es la única
    costura donde coexisten el cómputo y el sujeto que autoriza.

    Y `raise`, no `return`: si dos nociones de «quién es el comprador» divergen, eso hay que
    verlo. Un retorno silencioso lo convertiría en una no-escritura indistinguible de las
    docenas de no-escrituras legítimas que la sombra produce cada día.
    """
    assert issubclass(ComputoDeOtroComprador, RuntimeError)

    fuente_persist = (RAIZ / "app" / "buyer" / "actualizador.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(fuente_persist))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "persistir_computo")
    assert "ComputoDeOtroComprador" not in ast.dump(fn), \
        "la propiedad se comprueba dos veces en sitios distintos: una de ellas derivará"

    fuente_sombra = (RAIZ / "app" / "buyer" / "sombra.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(fuente_sombra))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "actualizar_en_sombra")
    levanta = [n for n in ast.walk(fn) if isinstance(n, ast.Raise)
               and "ComputoDeOtroComprador" in ast.dump(n)]
    assert len(levanta) == 1, "la sombra no levanta el rechazo: T16b pasaría por otro motivo"


# ══ T17 · NADA DE ESTO ENTRA EN EL GRAFO ════════════════════════════════════════════


def test_T17_el_computo_no_entra_en_state_ni_config_ni_prompt():
    """R0C sigue SHADOW ONLY: puede añadir escrituras, `await`, latencia y logs seguros, pero
    NO ranking, panel, cards, prosa, tool calls productivas, prompt ni `AGENT_TOOLS`."""
    estado = (RAIZ / "app" / "agent" / "state.py").read_text(encoding="utf-8")
    for prohibido in ("buyer", "candidato", "computo", "principal", "user_id"):
        assert prohibido not in estado

    fn = next(n for n in ast.walk(ast.parse(CHAT.read_text(encoding="utf-8")))
              if isinstance(n, ast.FunctionDef) and n.name == "_langgraph_config")
    volcado = ast.dump(fn)
    for prohibido in ("buyer", "candidato", "computo", "principal", "user_id"):
        assert prohibido not in volcado


@pytest.mark.parametrize("modulo", [
    "decision/assembler.py", "encaje.py", "orden.py", "preferencias.py",
])
def test_T17b_el_carril_que_DECIDE_no_importa_nada_del_comprador(modulo):
    """La compuerta que separa R0C de LEVEL 2, medida donde SÍ se puede medir.

    Conviene decirlo sin adornos: `CURRENT_AUTHORITY_WHITELIST` es vocabulario del mandato,
    **no un símbolo de este código**. No existe ninguna constante con ese nombre, así que un
    test que la buscara por cadena pasaría siempre y no probaría nada — sería inerte, que es
    peor que no existir.

    Lo que sí es una propiedad del repositorio es que el carril que decide —panel, encaje,
    orden, preferencias— no importa nada de `app.buyer`. Mientras eso se sostenga, ningún
    valor del comprador puede gobernar lo que la persona ve, con flags o sin ellos.
    """
    fuente = (RAIZ / "app" / modulo).read_text(encoding="utf-8")
    arbol = ast.parse(fuente)

    modulos = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.ImportFrom) and n.module:
            modulos.add(n.module)
        elif isinstance(n, ast.Import):
            modulos.update(a.name for a in n.names)

    fugas = {m for m in modulos if m.startswith("app.buyer")}
    assert not fugas, f"{modulo} importa del comprador: {sorted(fugas)}"


def test_T17c_los_consumidores_del_computo_son_TRES_y_ninguno_decide():
    """Enumerar quién puede persistir un cómputo, en vez de confiar en que nadie más lo haga.

    Si mañana apareciera un cuarto llamador —un nodo del grafo, un router, un servicio— este
    test lo obliga a pasar por aquí y a declararse.
    """
    permitidos = {"app/buyer/actualizador.py", "app/buyer/candidato.py", "app/buyer/sombra.py"}
    interesan = {"computar_candidato", "persistir_computo"}
    encontrados = set()

    for ruta in sorted((RAIZ / "app").rglob("*.py")):
        arbol = ast.parse(ruta.read_text(encoding="utf-8"))
        usa = False
        for n in ast.walk(arbol):
            # AST y no texto, por cuarta vez en este repositorio: `chat.py` NOMBRA
            # `computar_candidato` en un comentario para explicar que la política no se
            # duplica, y un `in fuente` lo contaba como consumidor. Un guard que lee
            # caracteres acaba detectando la prosa que lo explica.
            if isinstance(n, ast.ImportFrom):
                usa = usa or any(a.name in interesan for a in n.names)
            elif isinstance(n, ast.Call):
                objetivo = getattr(n.func, "id", None) or getattr(n.func, "attr", None)
                usa = usa or objetivo in interesan
        if usa:
            encontrados.add(ruta.relative_to(RAIZ).as_posix())

    assert encontrados == permitidos, \
        f"el cómputo tiene consumidores no declarados: {sorted(encontrados - permitidos)}"


def test_T17d_el_detector_de_consumidores_VE_un_consumidor_nuevo():
    """La mitad negativa de T17c: sin esto podría estar enumerando un conjunto vacío.

    Y un control adicional: un fichero que sólo MENCIONA el nombre en un comentario no cuenta
    como consumidor. Es el caso real de `chat.py`, y distinguirlo es la razón de que T17c mire
    el árbol en vez de la cadena.
    """
    interesan = {"computar_candidato", "persistir_computo"}

    def _usa(cuerpo):
        arbol = ast.parse(cuerpo)
        for n in ast.walk(arbol):
            if isinstance(n, ast.ImportFrom) and any(a.name in interesan for a in n.names):
                return True
            if isinstance(n, ast.Call):
                objetivo = getattr(n.func, "id", None) or getattr(n.func, "attr", None)
                if objetivo in interesan:
                    return True
        return False

    assert _usa("from app.buyer.actualizador import persistir_computo\n")
    assert _usa("async def f(c):\n    return await persistir_computo(c)\n")
    assert _usa("async def f(c):\n    return await act.computar_candidato(c)\n")
    assert not _usa("# `computar_candidato` es la misma que usa el updater\nx = 1\n"), \
        "una mención en un comentario no puede contar como consumidor"


# ══ T18 / T19 · ORDEN EN EL ENDPOINT ════════════════════════════════════════════════


def _lineas_clave(nombre_funcion):
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arbol)
              if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == nombre_funcion)
    return fn


def test_T18_en_SSE_el_panel_sale_ANTES_de_esperar_la_persistencia():
    """El orden cambia deliberadamente, y el mandato lo autoriza: el panel NO paga la
    escritura.

    `done` pasa a significar algo más fuerte que antes —que la TENTATIVA de persistir
    terminó—, que es la frontera útil para el turno siguiente. Sigue siendo fail-open: si la
    persistencia falla, se registra y `done` sale igual.
    """
    fn = _lineas_clave("_stream_agent")

    panel = [n for n in ast.walk(fn) if isinstance(n, ast.Yield)
             and isinstance(n.value, ast.BinOp)
             and "cuerpo_panel" in ast.dump(n.value)]
    assert len(panel) == 1, "no se localizó el yield del panel"

    espera = [n for n in ast.walk(fn) if isinstance(n, ast.Await)
              and isinstance(n.value, ast.Call)
              and isinstance(n.value.func, ast.Name)
              and n.value.func.id == "actualizar_en_sombra"]
    assert len(espera) == 1

    done = [n for n in ast.walk(fn) if isinstance(n, ast.Yield)
            and "'done'" in ast.dump(n)]
    assert len(done) == 1, "no se localizó el yield de `done`"

    assert panel[0].lineno < espera[0].lineno < done[0].lineno, (
        "el orden tiene que ser panel → persistencia → done; cualquier otro o hace esperar "
        "a la persona, o deja `done` sin significar nada")


def test_T19_en_NO_stream_la_persistencia_termina_ANTES_del_return():
    fn = _lineas_clave("chat")

    espera = [n for n in ast.walk(fn) if isinstance(n, ast.Await)
              and isinstance(n.value, ast.Call)
              and isinstance(n.value.func, ast.Name)
              and n.value.func.id == "actualizar_en_sombra"]
    assert len(espera) == 1

    respuesta = [n for n in ast.walk(fn) if isinstance(n, ast.Return)
                 and n.value is not None and "ChatResponse" in ast.dump(n.value)]
    assert len(respuesta) == 1, "no se localizó el `return ChatResponse(...)`"

    assert espera[0].lineno < respuesta[0].lineno


def test_T18b_la_persistencia_esperada_esta_AISLADA_en_las_dos_ramas():
    """Fail-open, explícito: un fallo de la sombra no puede tumbar un turno que iba bien."""
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    esperas = [n for n in ast.walk(arbol) if isinstance(n, ast.Await)
               and isinstance(n.value, ast.Call)
               and isinstance(n.value.func, ast.Name)
               and n.value.func.id == "actualizar_en_sombra"]
    assert len(esperas) == 2

    for espera in esperas:
        envolventes = [n for n in ast.walk(arbol) if isinstance(n, ast.Try)
                       and any(c is espera for c in ast.walk(n))]
        assert envolventes, "una persistencia esperada sin `try` puede tumbar el turno"
        manejador = min(envolventes, key=lambda n: len(list(ast.walk(n))))
        assert manejador.handlers, "un `try` sin `except` no aísla nada"
        for h in manejador.handlers:
            assert not any(isinstance(c, ast.Raise) for c in ast.walk(h)), \
                "el manejador repropaga: eso no es aislamiento"


# ══ T20 · FRESCURA DEL TURNO N+1 ════════════════════════════════════════════════════


@pytest.mark.parametrize("segunda_vez", [False, True])
def test_T20_tras_una_persistencia_exitosa_la_lectura_siguiente_ve_la_revision(
        store, contador, sombra_encendida, segunda_vez):
    """La propiedad es «N+1 fresco TRAS UNA PERSISTENCIA EXITOSA», nunca «N+1 siempre fresco».

    Se parametriza sobre CREADA y REPLAY porque el mandato exige la frescura para los dos y
    la prohíbe explícitamente para `FALLIDO` / `CONFLICTO` — donde no hay nada asentado que
    leer, y exigirla sería exigir que se vea algo que no se escribió.
    """
    computo = _computar()
    asyncio.run(actualizar_en_sombra(_Usuario(), _humano(), computo=computo))
    if segunda_vez:
        asyncio.run(actualizar_en_sombra(_Usuario(), _humano(), computo=computo))

    siguiente = asyncio.run(act.cargar_ultima(A))

    assert siguiente is not None
    assert siguiente.context_revision == 0
    assert siguiente.financial.budget_max.amount == Decimal(120000)
    assert _fila(store) == 1, "el replay no puede añadir revisión"


def test_T20b_tras_un_CONFLICTO_no_se_exige_frescura_porque_no_hubo_escritura(
        store, contador):
    """La otra mitad, y está aquí para que nadie «arregle» T20 haciendo que un conflicto
    también asiente algo."""
    _persistir(_computar(mid="m-0", propuestas=(_BUD,)))
    computo = _computar(mid="m-1", propuestas=(
        PropuestaV0(disposicion="durable", motivo="otro tope",
                    mutacion=SetBudgetMax(amount=Decimal(150000), currency=USD)),))
    store.avanza_la_cabeza(A, financial={"budget_max": Money(amount=Decimal(90000),
                                                             currency="USD")})

    resultado = _persistir(computo)
    siguiente = asyncio.run(act.cargar_ultima(A))

    assert resultado.estado is EstadoActualizacion.CONFLICTO
    assert siguiente.financial.budget_max.amount == Decimal(90000), \
        "lo vigente es lo concurrente, no el candidato que no se pudo aplicar"


# ══ T21–T24 · MUTACIONES · cada guard tiene que poder ponerse ROJO ══════════════════
#
# La mitad negativa de la unidad. Un guard que no se ha visto fallar nunca es indistinguible
# de un guard inerte, y en este repositorio ya han aparecido tres guards textuales que se
# detectaban a sí mismos. Aquí cada mutación se construye SÓLO en el test.


def test_T21_MUTACION_reinterpretar_en_persist_se_detecta(store, contador):
    """Si `persistir_computo` volviera a llamar al intérprete, T1/T7/T11 lo verían."""
    computo = _computar()
    contador["n"] = 0

    async def persistir_que_reinterpreta(computo, *, db=None):
        await act.interpretar_mensaje(_msg(), _proponente(_BUD))
        return await persistir_computo(computo, db=db)

    asyncio.run(persistir_que_reinterpreta(computo))

    assert contador["n"] == 1, \
        "el contador no distingue persistir de persistir-reinterpretando: sería inerte"


def test_T22_MUTACION_dos_escritores_normales_se_detecta(store, contador,
                                                         sombra_encendida):
    """Si el turno persistiera dos veces, T12 lo vería."""
    computo = _computar()
    asyncio.run(actualizar_en_sombra(_Usuario(), _humano(), computo=computo))
    escrituras_una = store.escrituras

    asyncio.run(actualizar_en_sombra(_Usuario(), _humano(), computo=computo))

    assert store.escrituras == escrituras_una + 1, \
        "el contador de escrituras no sube con un segundo escritor: sería inerte"


def test_T23_MUTACION_etiquetar_el_rebase_como_exacto_se_detecta(store, contador):
    """Si `_clasificar` ignorara `rebasado`, T5/T6 se pondrían rojos.

    Es la mutación más peligrosa de esta unidad porque no rompe NADA observable desde fuera:
    el estado final sería idéntico y sólo mentiría la etiqueta. Por eso se prueba que la
    etiqueta es la que decide, y no un adorno.
    """
    _persistir(_computar(mid="m-0", propuestas=(_BUD,)))
    computo = _computar(mid="m-1", texto=_TXT_BED, propuestas=(_BED,))
    store.avanza_la_cabeza(A, property_requirements={"area_m2_min": 70.0})
    real = _persistir(computo)

    persistida = RevisionPersistida(real.contexto, real.revision, creada=True)
    base = BuyerContextV0(buyer_id=A, updated_at=T0, context_revision=1)
    mutado = act._clasificar(persistida, base, rebasado=False)

    assert real.estado is EstadoActualizacion.REBASEADA
    assert mutado.estado is EstadoActualizacion.CREADA, \
        "`rebasado` no cambia el desenlace: la distinción sería decorativa"
    assert mutado.rebasado is False


def test_T24_MUTACION_persistir_bajo_el_comprador_equivocado_se_detecta(
        store, contador, sombra_encendida):
    """Si la sombra no comprobara la propiedad, el artefacto de B acabaría bajo B mientras
    quien autoriza es A. Se demuestra que sin el guard la escritura SÍ ocurriría — que es lo
    que hace que el guard sea la causa de que no ocurra."""
    ajeno = _computar(B)

    # Sin binding: `persistir_computo` no comprueba propiedad y escribe tan ricamente.
    resultado = _persistir(ajeno)
    assert resultado.estado is EstadoActualizacion.CREADA
    assert _fila(store, B) == 1, \
        "sin guard tampoco se escribe: entonces T16b no prueba nada sobre el guard"

    # Con binding: el mismo artefacto, por la costura real, no llega al store.
    escrituras_antes = store.escrituras
    asyncio.run(actualizar_en_sombra(_Usuario(A), _humano(), computo=ajeno))
    assert store.escrituras == escrituras_antes
