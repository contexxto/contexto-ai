"""SEC-X1-CRM-AUTHORITY-LIVENESS-R0 · la autoridad ACTUAL gobierna el contexto persistido del CRM.

    AUTORIDAD PASADA ≠ AUTORIDAD ACTUAL · ALMACENAMIENTO ≠ AUTORIDAD DE DIVULGACIÓN

Un hilo persistido del Copiloto o del Estratega (narraciones del asistente, mensajes del corredor, salidas de tools)
se produjo con el alcance que el corredor tenía ENTONCES. Antes, `/crm/thread` y `/crm/chat` derivaban el hilo solo
de `user_id + lead` y comprobaban únicamente el ROL: un corredor que salía de su agencia, o perdía un inmueble,
seguía leyendo esas narraciones y se las reinyectaba al modelo (F-1, reproducido sobre `edf7a91`). Ahora:

  · la huella del alcance VIGENTE (`_alcance_crm`: los inmuebles que hoy le da su dueño o su agencia) entra en el id
    del hilo → con otro alcance, el hilo es otro (fresco); el viejo queda ALMACENADO e inaccesible;
  · en el modo por interesado, el lead tiene que estar HOY en `_leads_del_corredor`, comprobado ANTES de leer el
    checkpoint o de invocar el grafo; fuera de él: GET vacío (no revela), POST/DELETE 403 sin cargar ni borrar nada.

PostgreSQL 15 real (`TEST_DATABASE_URL`) con el andamiaje de tests/test_sec_x2_r0_disclosure_authority.py: X es de
DUENO_X dentro de AGENCIA_X; COLEGA_X es miembro de la agencia; el lead es una sesión real con solicitud para X. El
grafo del CRM es el REAL con el LLM falseado y un checkpointer en memoria. Sin la variable, todo se SALTA.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlalchemy import text

import app.routers.assets as A
import app.routers.chat as chat
from app.auth import CurrentUser
from tests.test_sec_x2_r0_disclosure_authority import (  # noqa: F401
    AGENCIA_X, COLEGA_X, DUENO_X, DUENO_Y, X, Y, _grafo_crm, _peticion, _plano, _sesion_mixta, base, pg)

@pytest.fixture(autouse=True)
def _sin_rate_limit(monkeypatch):
    from app.limiter import limiter
    monkeypatch.setattr(limiter, "enabled", False)


SID = "session-liveness-1"
NARRATIVA = "NARRATIVA-LIVENESS: el comprador escribió X actual del comprador y quiere visitar el sábado"
FUERA = CurrentUser(user_id=COLEGA_X.user_id, rol="corredor", agency_id=None, nombre="Ex colega")


def _pide_timeline(cid):
    return AIMessage(content="", tool_calls=[{"name": "tool_timeline_de_lead",
                                              "args": {"referencia": "Lead #sess"}, "id": cid}])


async def _chat(Sesion, quien, texto, lead=None, modo="copiloto"):
    async with Sesion() as db:
        return await A.crm_chat(_peticion(), A.CRMChatReq(message=texto, lead=lead, modo=modo), quien, db)


async def _get(Sesion, quien, lead=None, modo="copiloto"):
    async with Sesion() as db:
        return await A.crm_thread(_peticion(), lead, modo, quien, db)


async def _hilo(Sesion, quien, lead=None, modo="copiloto"):
    async with Sesion() as db:
        return await A._hilo_crm_vigente(db, quien, lead, modo)


async def _t0(base, monkeypatch, quien=COLEGA_X, lead=SID):
    """T0: el lead real de X con solicitud; el corredor con alcance usa el Copiloto; el hilo persiste Human + tool
    (con el hilo de X) + narración."""
    Sesion, _ = base
    await _sesion_mixta(Sesion, SID)
    g, llm = _grafo_crm(monkeypatch)
    llm.guion = [_pide_timeline("t0"), AIMessage(content=NARRATIVA)]
    r = await _chat(Sesion, quien, "resúmeme a este interesado", lead=lead)
    tool = [m for m in llm.entradas[1] if isinstance(m, ToolMessage)]
    assert tool and "X actual del comprador" in tool[0].content, "T0: con alcance, el Copiloto SÍ trae el hilo de X"
    return Sesion, g, llm, r["session_id"]


class _Espia:
    """Cuenta las lecturas e invocaciones del grafo: negar el acceso NO puede pasar por leer el checkpoint."""
    def __init__(self, g, monkeypatch):
        import app.agent.crm_graph as CG
        self.lecturas, self.invocaciones = [], []
        real_get, real_inv = g.aget_state, g.ainvoke

        async def aget_state(config, *a, **k):
            self.lecturas.append(config["configurable"]["thread_id"])
            return await real_get(config, *a, **k)

        async def ainvoke(entrada, config=None, *a, **k):
            self.invocaciones.append(config["configurable"]["thread_id"])
            return await real_inv(entrada, config, *a, **k)
        envoltura = type("G", (), {"aget_state": staticmethod(aget_state), "ainvoke": staticmethod(ainvoke)})
        monkeypatch.setattr(CG, "compiled_crm_graph", envoltura)


async def _sacar_de_la_agencia_el_inmueble(Sesion):
    async with Sesion() as db:
        await db.execute(text("UPDATE activos_inmutables SET owner_user_id = CAST(:u AS uuid), owner_agency_id = NULL "
                              "WHERE id = CAST(:x AS uuid)"), {"u": DUENO_Y.user_id, "x": X})
        await db.commit()


# ══ A–B · con alcance vigente, todo funciona ═══════════════════════════════════════════════

@pg
async def test_A_dueno_actual_y_lead_actual(base, monkeypatch):
    Sesion, g, llm, hilo = await _t0(base, monkeypatch, quien=DUENO_X)
    r = await _get(Sesion, DUENO_X, SID)
    assert r["session_id"] == hilo and any(NARRATIVA in m["texto"] for m in r["mensajes"])
    llm.guion = [AIMessage(content="sigo")]
    await _chat(Sesion, DUENO_X, "¿y ahora?", lead=SID)
    assert NARRATIVA in _plano(llm.entradas[-1]), "con alcance, su propio hilo sí vuelve al modelo"


@pg
async def test_B_miembro_actual_de_la_agencia_y_lead_de_la_agencia(base, monkeypatch):
    Sesion, g, llm, hilo = await _t0(base, monkeypatch, quien=COLEGA_X)
    r = await _get(Sesion, COLEGA_X, SID)
    assert r["session_id"] == hilo and any(NARRATIVA in m["texto"] for m in r["mensajes"])


# ══ C–E · perder el alcance cierra el hilo (sin borrarlo) ═══════════════════════════════════

@pg
async def test_C_sale_de_la_agencia_GET_no_revela_y_ni_lee_el_checkpoint(base, monkeypatch):
    Sesion, g, llm, hilo = await _t0(base, monkeypatch)
    espia = _Espia(g, monkeypatch)
    r = await _get(Sesion, FUERA, SID)
    assert r == {"session_id": None, "mensajes": []}, r
    assert espia.lecturas == [], "el checkpoint se leyó ANTES de comprobar el alcance"


@pg
async def test_D_sale_de_la_agencia_POST_no_carga_el_hilo_en_el_modelo(base, monkeypatch):
    Sesion, g, llm, hilo = await _t0(base, monkeypatch)
    espia = _Espia(g, monkeypatch)
    n = len(llm.entradas)
    with pytest.raises(HTTPException) as e:
        await _chat(Sesion, FUERA, "¿qué me habías dicho de él?", lead=SID)
    assert e.value.status_code == 403
    assert espia.invocaciones == [] and len(llm.entradas) == n, "el modelo se invocó con un lead fuera de alcance"


@pg
async def test_E_el_inmueble_cambia_de_dueno(base, monkeypatch):
    """El inmueble deja la agencia: para la colega (y para la dueña anterior) el hilo por lead y el de cartera dejan
    de ser alcanzables; ninguno revela la narración."""
    Sesion, g, llm, hilo = await _t0(base, monkeypatch)
    await _sacar_de_la_agencia_el_inmueble(Sesion)
    assert await _get(Sesion, COLEGA_X, SID) == {"session_id": None, "mensajes": []}
    with pytest.raises(HTTPException) as e:
        await _chat(Sesion, COLEGA_X, "¿y él?", lead=SID)
    assert e.value.status_code == 403
    cartera = await _get(Sesion, COLEGA_X, None)
    assert not any(NARRATIVA in m["texto"] for m in cartera["mensajes"])


# ══ F–I · ni el checkpoint ni conocer el `lead` dan acceso ══════════════════════════════════

@pg
async def test_F_un_lead_con_checkpoint_pero_fuera_del_alcance_es_inaccesible(base, monkeypatch):
    """Existe un hilo con ESE id exacto (alcance vigente) para un `lead` que no es un interesado del corredor."""
    Sesion, g, llm, _ = await _t0(base, monkeypatch, quien=DUENO_X)
    async with Sesion() as db:
        huella = await A._alcance_crm(db, DUENO_X)
    falso = A._crm_thread(DUENO_X.user_id, "session-ajena", "copiloto", huella)
    await g.aupdate_state({"configurable": {"thread_id": falso}},
                          {"messages": [HumanMessage(content="hola"), AIMessage(content=NARRATIVA)]}, as_node="llm")
    assert await _get(Sesion, DUENO_X, "session-ajena") == {"session_id": None, "mensajes": []}
    with pytest.raises(HTTPException):
        await _chat(Sesion, DUENO_X, "¿y este?", lead="session-ajena")


@pg
async def test_F2_un_lead_real_de_OTRO_inmueble_tampoco(base, monkeypatch):
    """No basta con que el corredor tenga ALGÚN inmueble: el lead tiene que ser de uno suyo. Una sesión que es
    interesada solo de Y no entra en el CRM de la dueña de X."""
    Sesion, g, llm, _ = await _t0(base, monkeypatch, quien=DUENO_X)
    solo_y = "session-liveness-solo-y"
    assert (await chat.registrar_handoff(solo_y, activo_id=Y))["ok"]
    async with Sesion() as db:
        await db.execute(text("INSERT INTO handoff_mensaje (session_id, autor, texto, activo_id, creado_en) "
                              "VALUES (:s, 'lead', 'hola Y', CAST(:y AS uuid), clock_timestamp())"),
                         {"s": solo_y, "y": Y})
        await db.commit()
    assert await _hilo(Sesion, DUENO_Y, solo_y) is not None, "control: es un lead real de Y"
    assert await _hilo(Sesion, DUENO_X, solo_y) is None


@pg
async def test_F3_solo_el_id_canonico(base, monkeypatch):
    """Una referencia que el hilo tendría que limpiar (y que caería en otro hilo) no se acepta."""
    Sesion, g, llm, _ = await _t0(base, monkeypatch, quien=DUENO_X)
    for raro in (SID + "!", " " + SID, "", SID + "/x"):
        assert await _hilo(Sesion, DUENO_X, raro) is None, raro


@pg
async def test_G_H_la_tool_retenida_y_la_narracion_no_vuelven_tras_perder_el_alcance(base, monkeypatch):
    """G · la salida de la tool (ya retenida por X1a) y H · la narración derivada de ella: ninguna llega a nada
    —ni al GET, ni al modelo, ni por el hilo por lead ni por el de cartera— tras salir de la agencia."""
    Sesion, g, llm, _ = await _t0(base, monkeypatch)
    for lead in (SID, None):
        r = await _get(Sesion, FUERA, lead)
        assert not any(NARRATIVA in m["texto"] or "X actual del comprador" in m["texto"] for m in r["mensajes"])
    llm.guion = [AIMessage(content="hola")]
    await _chat(Sesion, FUERA, "¿qué me habías dicho?", lead=None)          # cartera: hilo fresco
    plano = _plano(llm.entradas[-1])
    assert NARRATIVA not in plano and "X actual del comprador" not in plano


@pg
async def test_I_otro_corredor_no_fabrica_el_hilo_original(base, monkeypatch):
    """El hilo sale del JWT: el corredor de Y (para quien la sesión TAMBIÉN es lead) tiene su propio hilo."""
    Sesion, g, llm, hilo = await _t0(base, monkeypatch)
    r = await _get(Sesion, DUENO_Y, SID)
    assert r["session_id"] not in (None, hilo) and not any(NARRATIVA in m["texto"] for m in r["mensajes"])


# ══ J · cartera y Estratega ═══════════════════════════════════════════════════════════════

@pg
async def test_J_cartera_y_estratega_siguen_funcionando_y_no_ganan_acceso_por_lead(base, monkeypatch):
    Sesion, g, llm, hilo_lead = await _t0(base, monkeypatch, quien=DUENO_X)
    for modo in ("copiloto", "estratega"):
        llm.guion = [AIMessage(content=f"respuesta {modo}")]
        r = await _chat(Sesion, DUENO_X, "¿cómo va mi cartera?", lead=None, modo=modo)
        assert r["reply"] == f"respuesta {modo}" and r["session_id"] != hilo_lead
        assert NARRATIVA not in _plano(llm.entradas[-1]), "la cartera recibió el hilo por lead"
    # El Estratega ignora `lead` (es de cartera): un lead fuera de alcance no lo vuelve 403 ni le da su hilo.
    llm.guion = [AIMessage(content="estrategia")]
    r = await _chat(Sesion, DUENO_X, "jugada", lead="session-ajena", modo="estratega")
    assert r["reply"] == "estrategia" and "lead" not in r["session_id"]


@pg
async def test_J2_F1b_la_cartera_de_quien_sale_de_la_agencia_es_un_hilo_fresco(base, monkeypatch):
    """F-1b: la narración producida en el hilo de CARTERA del Copiloto tampoco sobrevive a perder el alcance."""
    Sesion, g, llm, hilo = await _t0(base, monkeypatch, lead=None)
    assert "lead" not in hilo
    r = await _get(Sesion, FUERA, None)
    assert r["session_id"] != hilo and not any(NARRATIVA in m["texto"] for m in r["mensajes"])
    llm.guion = [AIMessage(content="ok")]
    await _chat(Sesion, FUERA, "¿qué me habías dicho?", lead=None)
    assert NARRATIVA not in _plano(llm.entradas[-1])


# ══ K · negar el acceso no borra ni reescribe nada ═══════════════════════════════════════════

@pg
async def test_K_el_hilo_sigue_almacenado_intacto_y_DELETE_fuera_de_alcance_no_borra(base, monkeypatch):
    Sesion, g, llm, hilo = await _t0(base, monkeypatch)
    antes = (await g.aget_state({"configurable": {"thread_id": hilo}})).values["messages"]
    assert await _get(Sesion, FUERA, SID) == {"session_id": None, "mensajes": []}
    async with Sesion() as db:
        with pytest.raises(HTTPException) as e:
            await A.crm_thread_reset(_peticion(), SID, "copiloto", FUERA, db)
    assert e.value.status_code == 403
    despues = (await g.aget_state({"configurable": {"thread_id": hilo}})).values["messages"]
    assert [m.content for m in despues] == [m.content for m in antes] and NARRATIVA in _plano(despues)


@pg
async def test_K2_recuperar_EXACTAMENTE_el_mismo_alcance_vuelve_a_abrir_el_hilo(base, monkeypatch):
    """Semántica documentada de R0: el hilo pertenece a (corredor, alcance). Si la colega vuelve a la MISMA agencia
    con los MISMOS inmuebles, su hilo vuelve a ser alcanzable —es contenido producido bajo esa misma autoridad—.
    Con cualquier otro alcance (otro inmueble ganado o perdido), el hilo es otro."""
    Sesion, g, llm, hilo = await _t0(base, monkeypatch)
    assert await _get(Sesion, FUERA, SID) == {"session_id": None, "mensajes": []}
    r = await _get(Sesion, COLEGA_X, SID)
    assert r["session_id"] == hilo and any(NARRATIVA in m["texto"] for m in r["mensajes"])


def test_L_el_alcance_lo_decide_el_servidor_antes_que_el_grafo():
    """Estructural: GET, POST y DELETE resuelven el hilo SOLO con `_hilo_crm_vigente`, antes de tocar el grafo o el
    checkpointer; ningún puerto deriva el hilo con `_crm_thread` directamente."""
    import inspect
    for fn, primero in ((A.crm_thread, "aget_state"), (A.crm_chat, "ainvoke"), (A.crm_thread_reset, "DELETE FROM")):
        fuente = inspect.getsource(fn)
        assert "_hilo_crm_vigente(" in fuente and "_crm_thread(" not in fuente, fn.__name__
        assert fuente.index("_hilo_crm_vigente(") < fuente.index(primero), fn.__name__
