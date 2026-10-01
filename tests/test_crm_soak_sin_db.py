"""
El soak del CRM (evals/crm_soak.py) promete no depender de la DB — estos tests lo exigen.

El defecto que cierran: el soak parchaba solo `_leads_del_corredor`, pero `tool_stats_embudo`
también resuelve `_activos_del_corredor` (un SELECT sobre activos_inmutables) y el reparto.
Con el .env real leía la DB de PRODUCCIÓN; sin credenciales esa tool fallaba, el LLM narraba
«no pude acceder», el guardrail de cifras no tenía nada que objetar y el soak decía «7/7
limpios» sin haber medido la narración de cifras (2026-09-30, Sonnet 4.5 y Sonnet 5).

Se corren los parches DEL PROPIO SOAK (`sin_db`), no una copia: si alguien agrega a la tool
otro acceso a la DB sin parcharlo, la sesión de `sin_db` revienta y este test se cae en el
gate — en vez de que el soak vuelva a leer la DB del .env sin avisar.

Sin DB, sin red, sin LLM.
"""
import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from evals.crm_soak import CARTERA, SoakTocoLaDB, errores_de_tools, sin_db

_CFG = {"configurable": {"owner_user_id": "soak-owner", "owner_agency_id": None}}


async def test_stats_embudo_bajo_los_parches_del_soak_no_usa_la_db():
    from app.agent.crm_tools import tool_stats_embudo

    with sin_db() as intentos:
        out = json.loads(await tool_stats_embudo.ainvoke({}, config=_CFG))

    assert intentos == []
    # Y midió la cartera canned, no un error narrable.
    assert "error" not in out
    assert out["total_interesados"] == len(CARTERA)
    assert out["reparto"]["interesados"] == len(CARTERA)
    assert out["reparto"]["hay_registro"] is False


async def test_sin_el_parche_de_activos_la_sesion_lo_atrapa():
    """Control por mutación: quitar el parche nuevo reproduce el defecto. Si la sesión de
    `sin_db` no reventara aquí, el test de arriba pasaría aunque la guarda no sirviera."""
    from app.agent.crm_tools import tool_stats_embudo
    from app.routers import assets

    real = assets._activos_del_corredor
    with sin_db() as intentos:
        assets._activos_del_corredor = real
        with pytest.raises(SoakTocoLaDB):
            await tool_stats_embudo.ainvoke({}, config=_CFG)

    assert any("activos_inmutables" in i for i in intentos)
    assert assets._activos_del_corredor is real  # sin_db restauró el original al salir


async def test_timeline_bajo_los_parches_del_soak_sigue_midiendo():
    """La otra tool de cifras. Su lectura del handoff pasa por `ensure_handoff_tables`, que
    corre DDL y backfills y hace COMMIT: con el .env real el soak escribía en esa DB. Bajo
    `sin_db` la sesión lo corta, la tool degrada a `handoff: []` como ya hacía sin tablas,
    y el prompt sigue midiéndose (no hay ToolMessage de error)."""
    from app.agent.crm_tools import tool_timeline_de_lead

    with sin_db() as intentos:
        out = json.loads(await tool_timeline_de_lead.ainvoke({"referencia": "ba0a"}, config=_CFG))

    assert "error" not in out
    assert out["lead"] == "Lead #ba0a" and out["handoff"] == []
    assert intentos, "si la tool dejó de leer el handoff, actualizar este test y el soak"


async def test_la_tool_que_falla_en_el_grafo_queda_sin_medir():
    """El camino real del soak: el ToolNode convierte la excepción en un
    ToolMessage(status='error') — no la propaga — y `errores_de_tools` lo detecta."""
    from langgraph.prebuilt import ToolNode

    from app.agent.crm_tools import tool_stats_embudo
    from app.routers import assets

    llamada = AIMessage(content="", tool_calls=[
        {"name": "tool_stats_embudo", "args": {}, "id": "t1", "type": "tool_call"}])
    real = assets._activos_del_corredor
    with sin_db():
        assets._activos_del_corredor = real
        res = await ToolNode([tool_stats_embudo]).ainvoke({"messages": [llamada]}, config=_CFG)

    msgs = [HumanMessage(content="¿Cuántos interesados tengo?"), llamada, *res["messages"]]
    errores = errores_de_tools(msgs)
    assert len(errores) == 1 and errores[0].startswith("tool_stats_embudo:")


def test_errores_de_tools_solo_mira_el_turno_actual():
    viejo = [HumanMessage(content="antes"),
             ToolMessage(content="Error: x", tool_call_id="a", name="t", status="error"),
             AIMessage(content="no pude")]
    bien = [HumanMessage(content="ahora"),
            ToolMessage(content='{"total_interesados": 3}', tool_call_id="b", name="t"),
            AIMessage(content="tienes 3")]
    assert errores_de_tools(viejo + bien) == []
    assert errores_de_tools(bien + viejo[1:]) == ["t: Error: x"]
