"""BUYER-UNRESOLVED-CONSUMER-R1 · la primera autoridad productiva del BuyerContext.

QUÉ CONGELA, y qué NO.

    congela    que la aclaración salga del `BuyerContextV0` PERSISTIDO y no de una segunda
               interpretación; que sea SÓLO la pregunta que este turno abrió; que su texto sea el
               determinista del producto; que no se vea antes de saber que la persistencia
               terminó; y que las cinco puertas estén, fail-closed
    NO congela  que la persona responda, ni que responder resuelva la pregunta — eso es el canary

Cada propiedad viene con su mitad negativa. Un guard que no se pone rojo al romper lo que dice
defender no prueba nada, y aquí la propiedad que más importa —«no se expone antes de persistir»—
es de ORDEN, que es justo lo que un test complaciente deja pasar sin enterarse.
"""
from __future__ import annotations

import ast
import datetime as dt
import pathlib

import pytest

from app.buyer.actualizador import ComputoCandidato, EstadoActualizacion, ResultadoUpdater
from app.buyer.clarificacion import clarificacion_del_turno, clarificacion_nueva_del_turno
from app.contracts.buyer_v0 import BuyerContextV0, UnresolvedQuestion

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CHAT = RAIZ / "app" / "routers" / "chat.py"

T0 = dt.datetime(2026, 9, 23, 12, 0, tzinfo=dt.timezone.utc)
A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"

PRESUPUESTO = "financial.budget_max"
DORMITORIOS = "property_requirements.bedrooms_min"
OBJETIVO = "objective"

Q_PRESUPUESTO = "¿Cuál es tu presupuesto máximo, y en qué moneda?"
Q_DORMITORIOS = "¿Cuántos dormitorios necesitas como mínimo?"


class _Usuario:
    def __init__(self, user_id=A):
        self.user_id = user_id


def _ctx(*rutas, revision=1):
    """Un `BuyerContextV0` con las preguntas abiertas que se le pidan, en ESE orden."""
    preguntas = tuple(
        UnresolvedQuestion(question={PRESUPUESTO: Q_PRESUPUESTO,
                                     DORMITORIOS: Q_DORMITORIOS}.get(r, f"¿{r}?"),
                           about_field=r)
        for r in rutas)
    return BuyerContextV0(buyer_id=A, context_revision=revision, updated_at=T0,
                          unresolved_questions=preguntas)


def _computo(base):
    return ComputoCandidato(estado=None, contexto_base=base, base=base)


def _resultado(contexto, estado=EstadoActualizacion.CREADA):
    return ResultadoUpdater(estado, contexto, revision=2)


@pytest.fixture
def encendida(monkeypatch):
    """Flag ON y el usuario A dentro de la cohorte. Sin esto, todo devuelve None."""
    from app.buyer import clarificacion as c
    monkeypatch.setattr(c.settings, "buyer_unresolved_product", True)
    monkeypatch.setattr(c.settings, "buyer_shadow_allowlist", A)


# ══ A-C · la pregunta correcta, y sólo una ═══════════════════════════════════════════════


def test_A_presupuesto_ambiguo_da_exactamente_la_pregunta_de_presupuesto():
    salida = clarificacion_nueva_del_turno(_computo(_ctx()), _resultado(_ctx(PRESUPUESTO)))
    assert salida == {"question": Q_PRESUPUESTO, "about_field": PRESUPUESTO}


def test_B_dormitorios_ambiguos_dan_la_suya_y_no_otra():
    salida = clarificacion_nueva_del_turno(_computo(_ctx()), _resultado(_ctx(DORMITORIOS)))
    assert salida["about_field"] == DORMITORIOS
    assert salida["question"] == Q_DORMITORIOS


def test_C_dos_ambiguedades_dan_UNA_sola_en_el_orden_del_contrato():
    """Se respeta el orden ya materializado por el reductor. No se reordena aquí."""
    salida = clarificacion_nueva_del_turno(
        _computo(_ctx()), _resultado(_ctx(DORMITORIOS, PRESUPUESTO)))
    assert salida["about_field"] == DORMITORIOS, "salió la segunda: alguien reordenó"


def test_C2_el_orden_del_contrato_es_el_que_manda_y_la_prueba_lo_sabe_ver():
    """MITAD NEGATIVA de C. Si la tupla llega al revés, sale la otra — que es lo correcto y lo
    que demuestra que C no pasaría igual con cualquier orden."""
    salida = clarificacion_nueva_del_turno(
        _computo(_ctx()), _resultado(_ctx(PRESUPUESTO, DORMITORIOS)))
    assert salida["about_field"] == PRESUPUESTO


# ══ D-E · sólo la NUEVA ══════════════════════════════════════════════════════════════════


def test_D_una_pregunta_que_ya_estaba_abierta_NO_se_repite():
    """La decisión de producto: no se insiste con lo que la persona ya ignoró."""
    base = _ctx(PRESUPUESTO)
    assert clarificacion_nueva_del_turno(_computo(base), _resultado(_ctx(PRESUPUESTO))) is None


def test_D2_pero_si_el_turno_abre_OTRA_ademas_de_la_vieja_sale_la_nueva():
    """MITAD NEGATIVA de D: el filtro no puede ser «si había alguna, calla»."""
    base = _ctx(PRESUPUESTO)
    salida = clarificacion_nueva_del_turno(
        _computo(base), _resultado(_ctx(PRESUPUESTO, DORMITORIOS)))
    assert salida["about_field"] == DORMITORIOS


def test_E_si_el_turno_RESUELVE_una_anterior_no_se_muestra_nada():
    base = _ctx(PRESUPUESTO)
    assert clarificacion_nueva_del_turno(_computo(base), _resultado(_ctx())) is None


# ══ F-G · sin cómputo o sin persistencia, no hay pregunta ════════════════════════════════


@pytest.mark.parametrize("computo,resultado", [
    (None, _resultado(_ctx(PRESUPUESTO))),                       # F · TURN_ONLY / VACIO
    (_computo(_ctx()), None),                                    # G · no se llegó a persistir
])
def test_FG_sin_las_dos_piezas_no_hay_aclaracion(computo, resultado):
    assert clarificacion_nueva_del_turno(computo, resultado) is None


@pytest.mark.parametrize("estado", [EstadoActualizacion.FALLIDO, EstadoActualizacion.CONFLICTO,
                                    EstadoActualizacion.VACIO])
def test_G2_un_resultado_que_NO_persistio_no_produce_aclaracion(estado):
    """LA PROPIEDAD QUE ORDENA EL TIEMPO. Preguntar por algo que no se guardó produciría un turno
    siguiente que vuelve a preguntar lo mismo: la persona vería a Contexto olvidando en vivo."""
    r = ResultadoUpdater(estado, _ctx(PRESUPUESTO), revision=None)
    assert not r.persistido, "el arnés se rompió: este estado debería NO persistir"
    assert clarificacion_nueva_del_turno(_computo(_ctx()), r) is None


def test_G3_el_arnes_de_persistencia_SABE_distinguir():
    """MITAD NEGATIVA de G2: con un estado que SÍ persiste, la misma entrada da pregunta."""
    r = _resultado(_ctx(PRESUPUESTO), EstadoActualizacion.CREADA)
    assert r.persistido
    assert clarificacion_nueva_del_turno(_computo(_ctx()), r) is not None


# ══ H-J · las puertas ════════════════════════════════════════════════════════════════════


def test_J_con_el_flag_APAGADO_no_sale_nada(monkeypatch):
    from app.buyer import clarificacion as c
    monkeypatch.setattr(c.settings, "buyer_unresolved_product", False)
    monkeypatch.setattr(c.settings, "buyer_shadow_allowlist", A)
    assert clarificacion_del_turno(
        _Usuario(), _computo(_ctx()), _resultado(_ctx(PRESUPUESTO))) is None


def test_J2_el_flag_viene_APAGADO_de_fabrica():
    from app.config import Settings
    assert Settings.model_fields["buyer_unresolved_product"].default is False


def test_H_un_anonimo_no_recibe_aclaracion(encendida):
    for principal in (None, _Usuario(""), _Usuario("   ")):
        assert clarificacion_del_turno(
            principal, _computo(_ctx()), _resultado(_ctx(PRESUPUESTO))) is None


def test_I_fuera_de_cohorte_no_recibe_aclaracion(encendida):
    assert clarificacion_del_turno(
        _Usuario(B), _computo(_ctx()), _resultado(_ctx(PRESUPUESTO))) is None


def test_I2_dentro_de_cohorte_SI_recibe(encendida):
    """MITAD NEGATIVA de I: si nadie recibiera nunca, I pasaría por la razón equivocada."""
    assert clarificacion_del_turno(
        _Usuario(A), _computo(_ctx()), _resultado(_ctx(PRESUPUESTO))) is not None


@pytest.mark.parametrize("comodin", ["*", "all", "1", ""])
def test_I3_no_existe_comodin_en_la_cohorte(monkeypatch, comodin):
    from app.buyer import clarificacion as c
    monkeypatch.setattr(c.settings, "buyer_unresolved_product", True)
    monkeypatch.setattr(c.settings, "buyer_shadow_allowlist", comodin)
    assert clarificacion_del_turno(
        _Usuario(A), _computo(_ctx()), _resultado(_ctx(PRESUPUESTO))) is None


def test_I4_un_id_que_es_TROZO_de_otro_no_entra(monkeypatch):
    from app.buyer import clarificacion as c
    monkeypatch.setattr(c.settings, "buyer_unresolved_product", True)
    monkeypatch.setattr(c.settings, "buyer_shadow_allowlist", A)
    assert clarificacion_del_turno(
        _Usuario(A[:8]), _computo(_ctx()), _resultado(_ctx(PRESUPUESTO))) is None


# ══ K · nada del comprador, nada del modelo ══════════════════════════════════════════════


def test_K_la_salida_tiene_DOS_claves_y_ninguna_mas():
    salida = clarificacion_nueva_del_turno(_computo(_ctx()), _resultado(_ctx(PRESUPUESTO)))
    assert set(salida) == {"question", "about_field"}


def test_K2_un_contexto_lleno_de_secretos_no_filtra_ninguno():
    """Prosa hostil en TODO lo que rodea a la pregunta. Nada de eso puede salir."""
    SECRETO = "postgresql://postgres.abc:S3cret0@aws-1.pooler.supabase.com:5432/postgres"
    contexto = BuyerContextV0(
        buyer_id=SECRETO, context_revision=2, updated_at=T0,
        unresolved_questions=(UnresolvedQuestion(question=Q_PRESUPUESTO,
                                                 about_field=PRESUPUESTO),))
    salida = clarificacion_nueva_del_turno(_computo(_ctx()), _resultado(contexto))
    entero = repr(salida)
    for prohibido in (SECRETO, "S3cret0", "supabase", "postgres", "buyer_id", "revision"):
        assert prohibido not in entero, f"{prohibido!r} viajó a la aclaración"


def test_K3_el_detector_de_fuga_SABE_ponerse_rojo():
    """MITAD NEGATIVA de K2: si la salida fuera un volcado, el mismo comprobador caería."""
    SECRETO = "S3cret0"
    volcado = {"question": Q_PRESUPUESTO, "about_field": PRESUPUESTO, "buyer_id": SECRETO}
    assert SECRETO in repr(volcado), "el comprobador no vería un volcado: no prueba nada"


def test_K4_el_texto_es_el_DETERMINISTA_del_producto_no_el_del_modelo():
    """El `motivo` del proponente es prosa libre y no determinista. La pregunta que sale tiene que
    ser la que `reductor._pregunta_de` fija por dimensión — la misma, carácter a carácter."""
    from app.buyer.boundary import BuyerFieldV0
    from app.buyer.reductor import _pregunta_de
    salida = clarificacion_nueva_del_turno(_computo(_ctx()), _resultado(_ctx(PRESUPUESTO)))
    assert salida["question"] == _pregunta_de(BuyerFieldV0.BUDGET_MAX)


def test_K4b_si_alguien_MUTA_el_texto_determinista_la_prueba_muerde(monkeypatch):
    """MITAD NEGATIVA de K4. Es el control que exige el mandato: mutar la pregunta determinista
    tiene que poner esto rojo. Si no, K4 sólo estaría comparando una constante consigo misma."""
    from app.buyer.boundary import BuyerFieldV0
    from app.buyer import reductor
    monkeypatch.setattr(reductor, "_pregunta_de", lambda c: "¿otra cosa?")
    salida = clarificacion_nueva_del_turno(_computo(_ctx()), _resultado(_ctx(PRESUPUESTO)))
    assert salida["question"] != reductor._pregunta_de(BuyerFieldV0.BUDGET_MAX), (
        "el comprobador no vería una divergencia entre el texto del producto y el ofrecido")


def test_K5_una_pregunta_SIN_about_field_no_se_ofrece():
    """Sin identidad no se puede saber si ya estaba, y tampoco sería accionable."""
    contexto = BuyerContextV0(
        buyer_id=A, context_revision=2, updated_at=T0,
        unresolved_questions=(UnresolvedQuestion(question="¿algo?"),))
    assert clarificacion_nueva_del_turno(_computo(_ctx()), _resultado(contexto)) is None


# ══ L · paridad stream / no-stream, y el ORDEN ═══════════════════════════════════════════


def _cuerpo_de(nombre: str) -> ast.AST:
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    for n in ast.walk(arbol):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nombre:
            return n
    raise AssertionError(f"no se encontró {nombre} en chat.py")


def _lineas_de(nodo, aguja: str) -> list[int]:
    fuente = CHAT.read_text(encoding="utf-8").splitlines()
    ini, fin = nodo.lineno, (nodo.end_lineno or nodo.lineno)
    return [i for i in range(ini, fin + 1) if aguja in fuente[i - 1]]


@pytest.mark.parametrize("funcion", ["_stream_agent", "chat"])
def test_L_los_dos_carriles_llaman_a_la_MISMA_decision(funcion):
    assert _lineas_de(_cuerpo_de(funcion), "clarificacion_del_turno"), \
        f"{funcion} no consulta la decisión de producto"


@pytest.mark.parametrize("funcion", ["_stream_agent", "chat"])
def test_L2_en_los_dos_carriles_la_PERSISTENCIA_va_antes_que_la_aclaracion(funcion):
    """LA PROPIEDAD DE ORDEN, comprobada sobre el fichero real y en los dos carriles.

    No basta con que ambos llamen: si la aclaración se calculara antes de persistir, se ofrecería
    una pregunta que podría no haber quedado guardada."""
    nodo = _cuerpo_de(funcion)
    persistir = _lineas_de(nodo, "await actualizar_en_sombra(")
    aclarar = _lineas_de(nodo, "clarificacion_del_turno")
    assert persistir, f"{funcion} no espera la persistencia"
    assert aclarar, f"{funcion} no calcula la aclaración"
    assert max(persistir) < min(aclarar), (
        f"en {funcion} la aclaración se calcula ANTES de persistir "
        f"(persistencia en {persistir}, aclaración en {aclarar})")


@pytest.mark.parametrize("funcion", ["_stream_agent", "chat"])
def test_L2b_la_aclaracion_recibe_EL_RESULTADO_de_la_persistencia(funcion):
    """EL ORDEN DE LÍNEAS NO BASTA, y esto lo aprendí rompiéndolo.

    Una mutación que dejaba la llamada en su sitio pero le pasaba `None, None` no movía ni una
    línea: `test_L2` seguía verde mientras la aclaración había dejado de mirar nada. Comprobar la
    posición es comprobar dónde ocurre; lo que importa es QUÉ recibe.

    Aquí se exige por AST que los argumentos sean el cómputo del turno y la variable que capturó
    el retorno de la persistencia. Si alguien desconecta el flujo, se pone rojo aunque el orden
    del fichero no cambie.
    """
    for n in ast.walk(_cuerpo_de(funcion)):
        if not (isinstance(n, ast.Call) and getattr(n.func, "id", "") == "clarificacion_del_turno"):
            continue
        args = [ast.unparse(a) for a in n.args]
        assert any("observacion_candidato.computo" == a for a in args), \
            f"{funcion}: la aclaración no recibe el cómputo del turno, recibe {args}"
        assert any("resultado_updater" == a for a in args), \
            f"{funcion}: la aclaración no recibe el resultado de la persistencia, recibe {args}"
        return
    raise AssertionError(f"{funcion} no llama a clarificacion_del_turno")


def test_L2c_la_variable_de_la_persistencia_es_la_que_captura_el_await():
    """Cierra el hueco por el otro extremo: que `resultado_updater` exista no basta si no es lo
    que devolvió `actualizar_en_sombra`. Se comprueba que la asignación es esa y no otra."""
    fuente = CHAT.read_text(encoding="utf-8")
    for funcion in ("_stream_agent", "chat"):
        nodo = _cuerpo_de(funcion)
        asignaciones = [n for n in ast.walk(nodo)
                        if isinstance(n, ast.Assign)
                        and any(getattr(t, "id", "") == "resultado_updater" for t in n.targets)
                        and "actualizar_en_sombra" in ast.unparse(n.value)]
        assert asignaciones, (
            f"{funcion}: `resultado_updater` no sale de `actualizar_en_sombra`")


def test_L3_la_sonda_de_orden_SABE_ver_el_orden_invertido():
    """MITAD NEGATIVA de L2: aplicada a un fichero sintético con el orden al revés, muerde."""
    sintetico = ast.parse(
        "async def f():\n"
        "    x = clarificacion_del_turno(u, c, r)\n"
        "    await actualizar_en_sombra(u, m)\n")
    fuente = ["async def f():",
              "    x = clarificacion_del_turno(u, c, r)",
              "    await actualizar_en_sombra(u, m)"]
    nodo = sintetico.body[0]
    lineas = lambda a: [i for i in range(nodo.lineno, (nodo.end_lineno or 1) + 1)  # noqa: E731
                        if a in fuente[i - 1]]
    assert not (max(lineas("await actualizar_en_sombra(")) < min(lineas("clarificacion_del_turno"))), \
        "la sonda no distinguiría un orden invertido"


def test_L4_el_evento_SSE_va_antes_del_done():
    """En el stream, `done` significa que la tentativa de persistencia terminó. La aclaración
    tiene que caber entre medias: después no la lee nadie."""
    nodo = _cuerpo_de("_stream_agent")
    aclarar = _lineas_de(nodo, '"clarification"')
    done = _lineas_de(nodo, '"done": True')
    assert aclarar and done
    assert max(aclarar) < min(done), "la aclaración se emite después del done"


def test_M_el_contrato_de_salida_lleva_el_campo():
    from app.routers.chat import ChatResponse
    assert "clarification" in ChatResponse.model_fields
    assert ChatResponse.model_fields["clarification"].default is None


def test_M2_unresolved_questions_NO_entra_al_prompt():
    """La aclaración es una directiva tipada, no una instrucción al modelo. Si el término
    apareciera en el grafo, el LLM podría repreguntar por su cuenta y con otro texto."""
    graph = (RAIZ / "app" / "agent" / "graph.py").read_text(encoding="utf-8")
    assert "unresolved_questions" not in graph
