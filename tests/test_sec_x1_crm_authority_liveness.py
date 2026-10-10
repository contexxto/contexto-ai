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


def _espiar_sql(db, registro: list):
    """Anota cada sentencia que la sesión ejecuta (para afirmar que negar el acceso no emite un DELETE)."""
    real = db.execute

    async def execute(stmt, *a, **k):
        registro.append(str(stmt))
        return await real(stmt, *a, **k)
    db.execute = execute


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
    """El inmueble deja la agencia (pasa a DUENO_Y): para la colega el hilo por lead deja de ser alcanzable (GET vacío,
    POST 403); para la dueña anterior, el lead deja de estar en su CRM; para el nuevo dueño, el lead SÍ está, pero en
    su propio hilo (fresco), nunca en el de la colega."""
    Sesion, g, llm, hilo = await _t0(base, monkeypatch)
    await _sacar_de_la_agencia_el_inmueble(Sesion)
    assert await _get(Sesion, COLEGA_X, SID) == {"session_id": None, "mensajes": []}
    with pytest.raises(HTTPException) as e:
        await _chat(Sesion, COLEGA_X, "¿y él?", lead=SID)
    assert e.value.status_code == 403
    assert await _hilo(Sesion, DUENO_X, SID) is None, "la dueña anterior conserva el lead"
    nuevo = await _get(Sesion, DUENO_Y, SID)
    assert nuevo["session_id"] not in (None, hilo) and not any(NARRATIVA in m["texto"] for m in nuevo["mensajes"])


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
async def test_F3b_ni_siquiera_si_el_lead_no_canonico_esta_en_el_CRM(base, monkeypatch):
    """La canonización es una barrera propia, no un efecto de la membresía: aunque `_leads_de_activo` devolviera una
    referencia que el hilo tendría que limpiar o truncar, el modo por interesado la rechaza (caería en el hilo de
    OTRA referencia). Control: la canónica equivalente sí entra."""
    Sesion, g, llm, _ = await _t0(base, monkeypatch, quien=DUENO_X)
    raros = ["lead raro", "lead/raro", "x" * 101, "léad"]

    async def _leads(_db, _id, _dir=None):
        return [{"session_id": s} for s in raros + ["lead-canonico"]]
    monkeypatch.setattr(A, "_leads_de_activo", _leads)
    assert await _hilo(Sesion, DUENO_X, "lead-canonico") is not None, "control: la canónica entra"
    for raro in raros:
        assert await _hilo(Sesion, DUENO_X, raro) is None, raro


@pg
async def test_G_H_la_tool_retenida_y_la_narracion_no_vuelven_tras_perder_el_alcance(base, monkeypatch):
    """G · la salida de la tool (ya retenida por X1a) y H · la narración derivada de ella: ninguna llega a nada
    —ni al GET, ni al modelo, ni por el hilo por lead ni por el de cartera— tras salir de la agencia."""
    Sesion, g, llm, _ = await _t0(base, monkeypatch)
    # También el hilo de CARTERA lleva la tool retenida y la narración (control: con alcance, vuelven).
    llm.guion = [_pide_timeline("t1"), AIMessage(content=NARRATIVA)]
    await _chat(Sesion, COLEGA_X, "¿y en la cartera?", lead=None)
    control = await _get(Sesion, COLEGA_X, None)
    assert any(NARRATIVA in m["texto"] for m in control["mensajes"]), "control: la cartera tiene la narración"
    for lead in (SID, None):
        r = await _get(Sesion, FUERA, lead)
        assert not any(NARRATIVA in m["texto"] or "X actual del comprador" in m["texto"] for m in r["mensajes"])
    llm.guion = [AIMessage(content="hola")]
    await _chat(Sesion, FUERA, "¿qué me habías dicho?", lead=None)          # cartera: hilo fresco
    plano = _plano(llm.entradas[-1])
    assert NARRATIVA not in plano and "X actual del comprador" not in plano


@pg
async def test_I_otro_corredor_no_fabrica_el_hilo_original(base, monkeypatch):
    """Regresión (propiedad previa, se conserva): el hilo sale del JWT; el corredor de Y (para quien la sesión
    TAMBIÉN es lead) tiene su propio hilo."""
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
    sql: list[str] = []
    async with Sesion() as db:
        _espiar_sql(db, sql)
        with pytest.raises(HTTPException) as e:
            await A.crm_thread_reset(_peticion(), SID, "copiloto", FUERA, db)
    assert e.value.status_code == 403
    assert not any("DELETE" in s.upper() for s in sql), "negar el acceso emitió un DELETE"
    despues = (await g.aget_state({"configurable": {"thread_id": hilo}})).values["messages"]
    assert [m.content for m in despues] == [m.content for m in antes] and NARRATIVA in _plano(despues)
    # Control del espía: con alcance, «nueva conversación» SÍ emite los DELETE del hilo vigente.
    sql_ok: list[str] = []
    async with Sesion() as db:
        _espiar_sql(db, sql_ok)
        r = await A.crm_thread_reset(_peticion(), SID, "copiloto", COLEGA_X, db)
    assert r["session_id"] == hilo and any("DELETE FROM checkpoint" in s for s in sql_ok), sql_ok


@pg
async def test_K2_recuperar_EXACTAMENTE_el_mismo_alcance_vuelve_a_abrir_el_hilo(base, monkeypatch):
    """Semántica documentada de R0: el hilo pertenece a (corredor, alcance). Si la colega vuelve a la MISMA agencia
    con los MISMOS inmuebles, su hilo vuelve a ser alcanzable —es contenido producido bajo esa misma autoridad—.
    Con cualquier otro alcance (otro inmueble ganado o perdido), el hilo es otro."""
    Sesion, g, llm, hilo = await _t0(base, monkeypatch)
    assert await _get(Sesion, FUERA, SID) == {"session_id": None, "mensajes": []}
    r = await _get(Sesion, COLEGA_X, SID)
    assert r["session_id"] == hilo and any(NARRATIVA in m["texto"] for m in r["mensajes"])


@pg
async def test_K3_GANAR_un_inmueble_tambien_cambia_el_hilo(base, monkeypatch):
    """La huella cubre el conjunto de inmuebles: si la agencia GANA uno (Y pasa a la agencia), el lead sigue en
    alcance pero el hilo es otro (fresco). Residual declarado de UX: cualquier cambio de alcance reinicia los hilos."""
    Sesion, g, llm, hilo = await _t0(base, monkeypatch)
    async with Sesion() as db:
        await db.execute(text("UPDATE activos_inmutables SET owner_agency_id = CAST(:a AS uuid) "
                              "WHERE id = CAST(:y AS uuid)"), {"a": AGENCIA_X, "y": Y})
        await db.commit()
    r = await _get(Sesion, COLEGA_X, SID)
    assert r["session_id"] not in (None, hilo) and not any(NARRATIVA in m["texto"] for m in r["mensajes"])


@pg
async def test_M_si_resolver_el_alcance_falla_todo_falla_cerrado_sin_tocar_el_hilo(base, monkeypatch):
    """Sin alcance resuelto no hay contexto: GET vacío sin leer el checkpoint; POST y DELETE 503 sin invocar el
    modelo ni emitir un DELETE."""
    Sesion, g, llm, hilo = await _t0(base, monkeypatch)
    espia = _Espia(g, monkeypatch)

    async def _revienta(*_a, **_k):
        raise RuntimeError("base caída")
    monkeypatch.setattr(A, "_activos_del_corredor", _revienta)
    assert await _get(Sesion, COLEGA_X, SID) == {"session_id": None, "mensajes": []}
    with pytest.raises(HTTPException) as e:
        await _chat(Sesion, COLEGA_X, "¿y él?", lead=SID)
    assert e.value.status_code == 503
    sql: list[str] = []
    async with Sesion() as db:
        _espiar_sql(db, sql)
        with pytest.raises(HTTPException) as e:
            await A.crm_thread_reset(_peticion(), SID, "copiloto", COLEGA_X, db)
    assert e.value.status_code == 503 and not any("DELETE" in s.upper() for s in sql)
    assert espia.lecturas == [] and espia.invocaciones == []


@pg
async def test_N_la_pertenencia_del_lead_es_la_misma_que_la_del_CRM(base, monkeypatch):
    """Una sola frontera: para cada sesión, `_lead_en_activos` sobre los inmuebles del corredor dice lo mismo que
    `_leads_del_corredor` (el CRM y las tools)."""
    Sesion, g, llm, _ = await _t0(base, monkeypatch, quien=DUENO_X)
    for quien in (DUENO_X, COLEGA_X, FUERA, DUENO_Y):
        async with Sesion() as db:
            activos = await A._activos_del_corredor(db, quien.user_id, quien.agency_id)
            crm = {l.get("session_id") for l in await A._leads_del_corredor(db, quien.user_id, quien.agency_id)}
            for s in (SID, "session-ajena"):
                assert await A._lead_en_activos(db, activos, s) == (s in crm), (quien.nombre, s)


@pg
async def test_N2_la_pertenencia_recorre_TODOS_los_inmuebles_del_alcance(base, monkeypatch):
    """El lead puede estar en cualquiera de los inmuebles del corredor, no solo en el primero que devuelva la base:
    con otro inmueble (sin leads) delante de X, el lead de X sigue en alcance."""
    Sesion, g, llm, _ = await _t0(base, monkeypatch, quien=DUENO_X)
    real = A._activos_del_corredor

    async def _con_otro_delante(db, u, a=None):
        return [{"id": "00000000-0000-4000-8000-0000000000ff", "direccion": None}] + await real(db, u, a)
    monkeypatch.setattr(A, "_activos_del_corredor", _con_otro_delante)
    assert await _hilo(Sesion, DUENO_X, SID) is not None


def test_L_el_alcance_lo_decide_el_servidor_antes_que_el_grafo():
    """Estructural: GET, POST y DELETE resuelven el hilo SOLO con `_hilo_crm_vigente`, antes de tocar el grafo o el
    checkpointer; ningún puerto deriva el hilo con `_crm_thread` directamente."""
    import inspect
    for fn, primero in ((A.crm_thread, "aget_state"), (A.crm_chat, "ainvoke"), (A.crm_thread_reset, "DELETE FROM")):
        fuente = inspect.getsource(fn)
        assert "_hilo_crm_vigente(" in fuente and "_crm_thread(" not in fuente, fn.__name__
        assert fuente.index("_hilo_crm_vigente(") < fuente.index(primero), fn.__name__
