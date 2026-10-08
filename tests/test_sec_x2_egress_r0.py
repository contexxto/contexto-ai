"""SEC-X2-EGRESS-R0 · el reenganche solo produce efectos hacia una audiencia AUTORIZADA.

    INTERNAL CONTEXT ≠ AUTHORIZED EGRESS
    NO_GRANT PARA LA AUDIENCIA A ≠ AUTORIDAD PARA LA B
    ATRIBUCIÓN ≠ AUTORIDAD DE DIVULGACIÓN
    ELEGIBILIDAD ≠ AUTORIDAD PARA ACTUAR
    ASIGNAR AL EXPERIMENTO ES UN CAMBIO DE ESTADO CON CONSECUENCIAS

Antes, el barrido calculaba la intención de la sesión ENTERA, repartía holdout/tocado y solo
después preguntaba por el comprador; con NO_GRANT avisaba al corredor (DR-15). Ahora cada lead
produce, como mucho, un efecto y solo hacia una audiencia autorizada:

  A · comprador (PRINCIPAL_SELF): su grant por canal (TR-5, sin cambios). Su efecto deja SOLO
      `reenganche_enviado_en`, nunca grupo ni elegible_en.
  B · corredor de X: el hecho X2 de (sesión, X) + elegibilidad con la semántica ACOTADA a X +
      canal → recién entonces holdout/tocado y, si tocado, cuenta en el aviso agregado.
  Ninguna → silencio y sin marca.

Bloques:
  B · PostgreSQL 15 real (`TEST_DATABASE_URL`): la matriz del mandato (casos A–N) con
      lead_actividad, la frontera TR-5, consent_grant (038) y el hecho X2 reales. La intención, el
      corredor, el reparto del holdout y los envíos son los dobles de TR-4, que distinguen la
      llamada de sesión entera de la acotada (activo_id): así se observa al productor con un lead
      elegible. R1 usa la semántica REAL de la intención.
  S · sin base: costuras (orden de lecturas y reservas, una sola fuente del hecho).
Sin la variable, B se SALTA: un skip es «esta evidencia no se recogió».
"""
from __future__ import annotations

import ast
import inspect
from datetime import datetime, timezone

import pytest
from langchain_core.messages import AIMessage, HumanMessage

import app.reenganche_cron as cron
import app.routers.chat as chat
from app.autoridad_reenganche import EstadoAutorizacion, corredor_autorizado
from app.reenganche import evaluar_reenganche
from tests.test_tr2_consentimiento import (  # noqa: F401 — fixtures y ayudas de TR-2
    ACTIVO,
    PUSH,
    _dormida,
    _fila,
    _pide_corredor,
    _post,
    _sesion,
    base,
    pg,
)
from tests.test_tr4_reenganche import BaseEspia, _dormido, _usos, entorno  # noqa: F401
from tests.test_tr5_consent_grant import _grants_completos, _lead_con_grant, _sql

OTRO = "44444444-4444-4444-4444-444444444444"
CORREDOR = "corredor@prueba.test"
PUSH_CORREDOR = {"endpoint": "https://push.prueba.test/k"}
SIN_MARCA = (None, None, None)
_INTENCION_REAL = chat.intencion_de_sesion


@pytest.fixture(autouse=True)
def _egress(monkeypatch):
    from app.limiter import limiter
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")


async def _barrer(Sesion) -> dict:
    # Las tablas de handoff existen en el esquema del test: «sin autoridad» se prueba por la AUSENCIA
    # del hecho, no por el fallo cerrado de una tabla que falta (eso es S1b).
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
    async with Sesion() as db:
        return await cron.escanear_reenganches(db)


_SIN_LECTURA = "no se pudo leer la autoridad del corredor"


async def _marcas(Sesion, sid) -> tuple:
    f = await _fila(Sesion, sid)
    return f["reenganche_grupo"], f["reenganche_elegible_en"], f["reenganche_enviado_en"]


def _al_corredor(entorno) -> tuple[list, list]:
    return ([e for e in entorno["email"] if e["to"] == CORREDOR],
            [p for p in entorno["push"] if p["subscription"] == PUSH_CORREDOR])


def _silencio(res: dict, entorno: dict) -> None:
    assert res.get("comprador", 0) == 0 and res.get("corredores", 0) == 0, res
    assert res.get("disparados", 0) == 0 and res.get("holdout", 0) == 0, res
    assert entorno["email"] == [] and entorno["push"] == [], "salió un aviso sin audiencia autorizada"
    assert entorno["holdout"] == [], "se repartió un grupo del experimento sin audiencia autorizada"


def _reparto(monkeypatch, entorno, holdout: set[str]):
    def grupo(sid, pct):
        entorno["holdout"].append(sid)
        return "holdout" if sid in holdout else "tocado"
    monkeypatch.setattr("app.lift.grupo_holdout", grupo)


# ══ B · PostgreSQL 15 real ══════════════════════════════════════════════════════════════

@pg
async def test_A_sin_autoridad_cero_efectos_y_cero_marcas(base, entorno, caplog):
    """Caso A. La intención de la sesión entera dispararía (el doble devuelve un lead tibio y
    dormido con señal de precio). Uno dejó canal sin grant; otro llegó por el QR de X. Ninguno
    tiene el hecho X2."""
    con_canal, por_qr = "egr-a-1", f"qr-{ACTIVO}-egra2"
    await _dormida(base, con_canal, email="a@ejemplo.invalid", push=PUSH)
    await _dormida(base, por_qr)
    res = await _barrer(base)
    assert res["escaneados"] == 2 and _SIN_LECTURA not in caplog.text
    _silencio(res, entorno)
    for sid in (con_canal, por_qr):
        assert await _marcas(base, sid) == SIN_MARCA


@pg
async def test_B_no_grant_no_es_autoridad_para_el_corredor(monkeypatch, base, entorno, caplog):
    """Caso B (reemplaza el respaldo DR-15). La frontera del comprador responde NO_GRANT —se
    comprueba, no se supone— y no hay hecho X2: silencio."""
    import app.autoridad_reenganche as AR
    veredictos = []
    real = AR.autorizar_efecto_reenganche

    async def espia(db, **kw):
        v = await real(db, **kw)
        veredictos.append(v.estado)
        return v
    monkeypatch.setattr(AR, "autorizar_efecto_reenganche", espia)
    sid, cab = await _sesion(base)
    await _dormida(base, sid)
    await _post(sid, cab, consent=True, email="b@ejemplo.invalid", push_subscription=PUSH)
    await _post(sid, cab, consent=False)                     # revoca: el canal queda, el permiso no
    res = await _barrer(base)
    assert veredictos == [EstadoAutorizacion.NO_GRANT] and _SIN_LECTURA not in caplog.text
    _silencio(res, entorno)
    assert await _marcas(base, sid) == SIN_MARCA


@pg
async def test_C_autoridad_exacta_del_corredor_entra_al_experimento(base, entorno):
    """Caso C. Hecho X2 para X, la semántica ACOTADA a X califica y el corredor tiene canal."""
    sid = f"qr-{ACTIVO}-egrc1"
    await _dormida(base, sid)
    await _pide_corredor(base, sid)
    res = await _barrer(base)
    assert entorno["intencion_activo"] == [(sid, ACTIVO)], "la elegibilidad del corredor es la acotada a X"
    assert entorno["holdout"] == [sid], "entra al reparto del experimento"
    grupo, elegible, enviado = await _marcas(base, sid)
    assert grupo == "tocado" and elegible is not None and enviado is not None
    correos, pushes = _al_corredor(entorno)
    assert len(correos) == 1 and len(pushes) == 1 and res["corredores"] == 1


@pg
async def test_D_lo_hablado_de_otro_inmueble_no_vuelve_elegible_a_X(monkeypatch, base, entorno):
    """Caso D. La sesión entera tiene intención fuerte (sobre Y); el lead apunta a X y tiene el
    hecho X2 de X, pero la semántica acotada a X no califica. Sin respaldo de sesión entera."""
    async def intencion(sid, horas_inactividad=None, activo_id=None):
        entorno["intencion"].append(sid)
        entorno["intencion_activo"].append((sid, activo_id))
        if activo_id is None:     # la sesión entera: lo hablado de Y
            return {"turnos": 6, "nivel": "tibio", "estado": "dormido", "senales": {"precio": True}}
        return {"turnos": 0, "nivel": "frio", "estado": "anonimo", "senales": {}}
    monkeypatch.setattr(chat, "intencion_de_sesion", intencion)
    sid = "egr-d-1"
    await _dormida(base, sid)
    await _pide_corredor(base, sid)
    res = await _barrer(base)
    assert entorno["intencion_activo"] == [(sid, ACTIVO)], "se consultó la sesión entera para el corredor"
    _silencio(res, entorno)
    assert await _marcas(base, sid) == SIN_MARCA


async def _intencion_solo_de_sesion_entera(entorno, sid, horas_inactividad=None, activo_id=None):
    """La sesión entera califica (lo hablado de Y); lo acotado a X, no."""
    entorno["intencion"].append(sid)
    entorno["intencion_activo"].append((sid, activo_id))
    if activo_id is None:
        return {"turnos": 6, "nivel": "tibio", "estado": "dormido", "senales": {"precio": True}}
    return {"turnos": 0, "nivel": "frio", "estado": "anonimo", "senales": {}}


@pg
async def test_D3_con_canal_y_no_grant_la_decision_del_comprador_no_sirve_al_corredor(
        monkeypatch, base, entorno):
    """La población exacta del viejo DR-15: canal del comprador, grant revocado (NO_GRANT) y hecho X2
    para X. La decisión de sesión entera del comprador SÍ existe (califica por lo hablado de Y), pero
    no puede reutilizarse para el corredor: su elegibilidad es solo la acotada a X, que no califica."""
    import app.autoridad_reenganche as AR
    veredictos = []
    real = AR.autorizar_efecto_reenganche

    async def espia(db, **kw):
        v = await real(db, **kw)
        veredictos.append(v.estado)
        return v
    monkeypatch.setattr(AR, "autorizar_efecto_reenganche", espia)
    monkeypatch.setattr(chat, "intencion_de_sesion",
                        lambda sid, **k: _intencion_solo_de_sesion_entera(entorno, sid, **k))
    sid, cab = await _sesion(base)
    await _dormida(base, sid)
    await _post(sid, cab, consent=True, email="d3@ejemplo.invalid", push_subscription=PUSH)
    await _post(sid, cab, consent=False)
    await _pide_corredor(base, sid)
    res = await _barrer(base)
    assert veredictos == [EstadoAutorizacion.NO_GRANT], "debe ejercer la rama B tras un NO_GRANT real"
    assert sorted(entorno["intencion_activo"], key=str) == sorted([(sid, None), (sid, ACTIVO)], key=str)
    _silencio(res, entorno)
    assert await _marcas(base, sid) == SIN_MARCA


@pg
async def test_D2_el_hecho_de_otro_inmueble_no_autoriza_a_X(base, entorno):
    """La persona pidió contacto para Y; el lead del barrido es de X. El hecho es del par EXACTO."""
    sid = "egr-d-2"
    await _dormida(base, sid)
    await _pide_corredor(base, sid, OTRO)
    res = await _barrer(base)
    _silencio(res, entorno)
    assert await _marcas(base, sid) == SIN_MARCA


@pg
async def test_E_solo_la_atribucion_qr_no_autoriza_nada(base, entorno, caplog):
    """Caso E. Sesión `qr-X-…`, sin solicitud: ni aviso, ni marcas del experimento. La semántica
    acotada ni siquiera se calcula: la elegibilidad va DESPUÉS de la autoridad."""
    sid = f"qr-{ACTIVO}-egre1"
    await _dormida(base, sid)
    res = await _barrer(base)
    assert _SIN_LECTURA not in caplog.text
    _silencio(res, entorno)
    assert entorno["intencion_activo"] == []
    assert await _marcas(base, sid) == SIN_MARCA


@pg
async def test_E2_una_fila_de_handoff_sin_marca_no_es_el_hecho(base, entorno):
    """Fila histórica (o fabricada por el corredor) sin `principal_requested_at`: no prueba que la
    persona lo pidiera → no autoriza."""
    sid = f"qr-{ACTIVO}-egre2"
    await _dormida(base, sid)
    await _pide_corredor(base, sid, marca=False)
    res = await _barrer(base)
    _silencio(res, entorno)
    assert await _marcas(base, sid) == SIN_MARCA


@pg
async def test_F_solo_comprador_marca_de_envio_sin_experimento(base, entorno):
    """Caso F. Grant válido del comprador y ningún hecho X2: le llega a él por los canales
    autorizados; al corredor, nada; queda `enviado_en` y NI grupo NI elegible_en."""
    sid, _ = await _lead_con_grant(base)
    res = await _barrer(base)
    assert res["comprador"] == 1 and res["corredores"] == 0 and res["holdout"] == 0
    assert [e["to"] for e in entorno["email"]] == ["c@ejemplo.invalid"]
    assert [p["subscription"] for p in entorno["push"]] == [PUSH]
    assert _al_corredor(entorno) == ([], [])
    grupo, elegible, enviado = await _marcas(base, sid)
    assert enviado is not None and grupo is None and elegible is None
    assert entorno["holdout"] == [], "el comprador no se reparte en el experimento del corredor"
    assert all(g["used_at"] is not None for g in await _grants_completos(base, sid))
    assert (await _barrer(base))["escaneados"] == 0, "la dosis única se conserva"


@pg
async def test_G_grant_del_comprador_y_hecho_del_corredor_un_solo_efecto(base, entorno):
    """Caso G. Las dos autoridades: el comprador tiene prioridad, como hoy. Un solo efecto, sin
    aviso duplicado al corredor y sin asignación al experimento."""
    sid, _ = await _lead_con_grant(base)
    await _pide_corredor(base, sid)
    res = await _barrer(base)
    assert res["comprador"] == 1 and res["corredores"] == 0 and res["disparados"] == 1
    assert _al_corredor(entorno) == ([], [])
    grupo, elegible, enviado = await _marcas(base, sid)
    assert enviado is not None and grupo is None and elegible is None
    assert sid not in entorno["holdout"]


@pg
async def test_H_holdout_del_corredor(monkeypatch, base, entorno):
    """Caso H. Autoridad + elegibilidad acotada + reparto holdout: control sin aviso."""
    sid = "egr-h-1"
    _reparto(monkeypatch, entorno, {sid})
    await _dormida(base, sid)
    await _pide_corredor(base, sid)
    res = await _barrer(base)
    assert res["holdout"] == 1 and res["corredores"] == 0 and res["disparados"] == 0
    grupo, elegible, enviado = await _marcas(base, sid)
    assert grupo == "holdout" and elegible is not None and enviado is None
    assert entorno["email"] == [] and entorno["push"] == []
    assert (await _barrer(base))["escaneados"] == 0, "el control no re-entra"


@pg
async def test_I_tocado_del_corredor_un_aviso_agregado(monkeypatch, base, entorno):
    """Caso I. Autoridad + elegibilidad acotada + reparto tocado: marcas y UN aviso agregado."""
    sid = "egr-i-1"
    _reparto(monkeypatch, entorno, set())
    await _dormida(base, sid)
    await _pide_corredor(base, sid)
    res = await _barrer(base)
    assert res["corredores"] == 1 and res["disparados"] == 1 and res["holdout"] == 0
    grupo, elegible, enviado = await _marcas(base, sid)
    assert grupo == "tocado" and elegible is not None and enviado is not None
    correos, pushes = _al_corredor(entorno)
    assert len(correos) == 1 and len(pushes) == 1
    assert correos[0]["url"] == "/?crm=1" and "baja_url" not in correos[0]


@pg
async def test_J_sin_canal_del_corredor_no_entra_al_experimento(monkeypatch, base, entorno):
    """Caso J. Hay autoridad, pero el corredor no tiene canal: sin tratamiento posible no hay
    control válido → ni holdout ni tocado."""
    async def sin_canal(db, activo_id):
        entorno["corredor"].append(activo_id)
        return None, []
    monkeypatch.setattr(chat, "_corredor_de_activo", sin_canal)
    sid = "egr-j-1"
    await _dormida(base, sid)
    await _pide_corredor(base, sid)
    res = await _barrer(base)
    _silencio(res, entorno)
    assert await _marcas(base, sid) == SIN_MARCA


@pg
@pytest.mark.parametrize("con_hecho_del_corredor", [False, True], ids=["sin_hecho", "con_hecho"])
async def test_K_error_de_autoridad_cero_efectos_y_cero_marcas(base, entorno, con_hecho_del_corredor):
    """Caso K. La frontera del comprador responde ERROR (038 sin aplicar, simulado). Sin otra
    autoridad: cero. CON el hecho del corredor, también cero —decisión declarada, la de TR-5: un
    fallo de autoridad no se esconde detrás del camino del corredor—; sin marca, el lead vuelve
    al barrido siguiente."""
    sid, _ = await _lead_con_grant(base)
    if con_hecho_del_corredor:
        await _pide_corredor(base, sid)
    await _sql(base, "ALTER TABLE public.consent_grant RENAME TO consent_grant_apartada")
    try:
        res = await _barrer(base)
    finally:
        await _sql(base, "ALTER TABLE public.consent_grant_apartada RENAME TO consent_grant")
    _silencio(res, entorno)
    assert await _marcas(base, sid) == SIN_MARCA
    assert all(g["used_at"] is None for g in await _grants_completos(base, sid))


@pg
async def test_L_bandera_apagada_ni_lecturas_ni_escrituras_ni_efectos(monkeypatch, base, entorno):
    """Caso L (TR-4 se conserva): con las dos autoridades listas, la bandera apagada no deja nada."""
    comprador, _ = await _lead_con_grant(base)
    await _pide_corredor(base, comprador)
    corredor = "egr-l-2"
    await _dormida(base, corredor)
    await _pide_corredor(base, corredor)
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "0")
    res = await _barrer(base)
    assert res.get("deshabilitado") is True
    assert entorno["email"] == [] and entorno["push"] == []
    assert entorno["intencion"] == [] and entorno["corredor"] == [] and entorno["holdout"] == []
    for sid in (comprador, corredor):
        assert await _marcas(base, sid) == SIN_MARCA
    assert all(g["used_at"] is None for g in await _grants_completos(base, comprador))


async def _lift_reenganche(Sesion) -> dict:
    """La misma función pura que sirve `/metricas/lift`, sobre las filas reales y con su contrato: la
    observación se indexa por el PAR exacto (session_id, activo_id) (SEC-X2-LIFT-SCOPE-R0)."""
    from sqlalchemy import text
    from app.lift import par_observacion, resumen_lift
    async with Sesion() as db:
        filas = (await db.execute(text(
            "SELECT session_id, activo_id::text AS activo_id, primera_actividad, ultima_actividad, "
            "reenganche_grupo, reenganche_elegible_en FROM lead_actividad"))).mappings().all()
    act = {par: dict(f) for f in filas
           if (par := par_observacion(f["session_id"], f["activo_id"])) is not None}
    leads = [{"session_id": s, "activo_id": a, "estado": "dormido", "handoff": False} for s, a in act]
    r = resumen_lift(leads, act, datetime.now(timezone.utc))["reenganche"]
    return {g: r[g]["n"] for g in ("tocado", "holdout")}


@pg
async def test_M_la_metrica_solo_cuenta_el_experimento_del_corredor(monkeypatch, base, entorno):
    """Caso M. Un efecto directo al comprador no mueve los conteos tocado/holdout del lift; las
    filas del experimento del corredor, sí."""
    _reparto(monkeypatch, entorno, {"egr-m-hold"})
    await _lead_con_grant(base)
    res = await _barrer(base)
    assert res["comprador"] == 1
    assert await _lift_reenganche(base) == {"tocado": 0, "holdout": 0}
    for sid in ("egr-m-toc", "egr-m-hold"):
        await _dormida(base, sid)
        await _pide_corredor(base, sid)
    res = await _barrer(base)
    assert res["corredores"] == 1 and res["holdout"] == 1
    assert await _lift_reenganche(base) == {"tocado": 1, "holdout": 1}


@pg
async def test_N_el_agregado_solo_cuenta_leads_autorizados(base, entorno):
    """Caso N. El mismo corredor, dos leads internamente elegibles: uno con el hecho X2 y otro
    sin él. El aviso dice N=1, nunca 2: con N pequeño la mera cifra divulga estado privado."""
    autorizado, ajeno = f"qr-{ACTIVO}-egrn1", f"qr-{ACTIVO}-egrn2"
    await _dormida(base, autorizado)
    await _dormida(base, ajeno)
    await _pide_corredor(base, autorizado)
    res = await _barrer(base)
    correos, pushes = _al_corredor(entorno)
    assert len(correos) == 1 and len(pushes) == 1 and res["corredores"] == 1
    for aviso in (correos[0], pushes[0]):
        assert aviso["body"].startswith("Tienes 1 interesado dormido "), aviso["body"]
    assert await _marcas(base, ajeno) == SIN_MARCA
    assert ajeno not in entorno["holdout"]


@pg
async def test_O_un_cierre_durante_el_barrido_no_marca_ni_cuenta_para_el_corredor(monkeypatch, base, entorno):
    """La persona cierra («no quiero más seguimiento») MIENTRAS el barrido evalúa. El cierre es la
    única reducción de autoridad de la audiencia B (la marca X2 no se borra): las marcas del corredor
    vuelven a comprobar la fila y el aviso agregado cuenta solo lo que de verdad quedó marcado."""
    from sqlalchemy import text
    cerrado, otro = "egr-o-1", "egr-o-2"
    for sid in (cerrado, otro):
        await _dormida(base, sid)
        await _pide_corredor(base, sid)
    doble = chat.intencion_de_sesion

    async def cierra_a_mitad(sid, horas_inactividad=None, activo_id=None):
        if sid == cerrado and activo_id is not None:
            async with base() as db2:
                await db2.execute(text("UPDATE lead_actividad SET reenganche_cerrado_en = now() "
                                       "WHERE session_id = :s"), {"s": sid})
                await db2.commit()
        return await doble(sid, horas_inactividad=horas_inactividad, activo_id=activo_id)
    monkeypatch.setattr(chat, "intencion_de_sesion", cierra_a_mitad)
    res = await _barrer(base)
    correos, pushes = _al_corredor(entorno)
    assert res["corredores"] == 1 and res["disparados"] == 1 and len(correos) == 1 and len(pushes) == 1
    assert correos[0]["body"].startswith("Tienes 1 interesado dormido "), correos[0]["body"]
    grupo, elegible, enviado = await _marcas(base, cerrado)
    assert (grupo, elegible, enviado) == SIN_MARCA, "se marcó un lead cerrado durante el barrido"
    assert (await _marcas(base, otro))[0] == "tocado"


def _escribe_a_mitad(monkeypatch, base, sid, sentencia, *, acotada):
    """Otra sesión escribe `sentencia` sobre la fila de `sid` MIENTRAS el barrido evalúa ese lead (en la
    llamada a la intención acotada, o en la de sesión entera si `acotada` es False)."""
    from sqlalchemy import text
    doble = chat.intencion_de_sesion

    async def a_mitad(s, horas_inactividad=None, activo_id=None):
        if s == sid and (activo_id is not None) is acotada:
            async with base() as db2:
                await db2.execute(text(sentencia), {"s": sid})
                await db2.commit()
        return await doble(s, horas_inactividad=horas_inactividad, activo_id=activo_id)
    monkeypatch.setattr(chat, "intencion_de_sesion", a_mitad)


@pg
async def test_O2_un_efecto_concurrente_sobre_la_fila_no_deja_un_segundo_efecto_al_corredor(
        monkeypatch, base, entorno):
    """Un barrido concurrente ya dio a este lead su dosis (enviado_en) después de que este lo leyó:
    la marca tocado vuelve a comprobar la fila, así que el corredor ni lo marca ni lo cuenta."""
    sid = "egr-o2"
    await _dormida(base, sid)
    await _pide_corredor(base, sid)
    _escribe_a_mitad(monkeypatch, base, sid,
                     "UPDATE lead_actividad SET reenganche_enviado_en = now() WHERE session_id = :s",
                     acotada=True)
    res = await _barrer(base)
    assert res["corredores"] == 0 and res["disparados"] == 0
    assert _al_corredor(entorno) == ([], [])
    grupo, elegible, _ = await _marcas(base, sid)
    assert grupo is None and elegible is None, "el experimento marcó una fila que ya tenía su efecto"


@pg
async def test_O3_un_cierre_durante_el_barrido_tampoco_deja_un_holdout(monkeypatch, base, entorno):
    """La guarda vale también para el control: un holdout no se asigna a una fila cerrada a mitad."""
    sid = "egr-o3"
    _reparto(monkeypatch, entorno, {sid})
    await _dormida(base, sid)
    await _pide_corredor(base, sid)
    _escribe_a_mitad(monkeypatch, base, sid,
                     "UPDATE lead_actividad SET reenganche_cerrado_en = now() WHERE session_id = :s",
                     acotada=True)
    res = await _barrer(base)
    assert res["holdout"] == 0 and entorno["email"] == [] and entorno["push"] == []
    grupo, elegible, enviado = await _marcas(base, sid)
    assert (grupo, elegible, enviado) == SIN_MARCA


@pg
async def test_P_si_la_fila_del_comprador_cambia_a_mitad_se_deshace_todo(monkeypatch, base, entorno):
    """Otro barrido asignó la fila del comprador al experimento después de leerla. Su grant ya está
    reservado en esta transacción: se deshace TODO (el grant vuelve), no sale nada y la fila queda
    como la dejó el otro. Un efecto del comprador no se suma a una observación del experimento."""
    sid, _ = await _lead_con_grant(base)
    _escribe_a_mitad(monkeypatch, base, sid,
                     "UPDATE lead_actividad SET reenganche_grupo = 'holdout', "
                     "reenganche_elegible_en = now() WHERE session_id = :s", acotada=False)
    res = await _barrer(base)
    assert res["comprador"] == 0 and res["disparados"] == 0
    assert entorno["email"] == [] and entorno["push"] == []
    grupo, elegible, enviado = await _marcas(base, sid)
    assert grupo == "holdout" and enviado is None
    assert all(g["used_at"] is None for g in await _grants_completos(base, sid)), "el grant se consumió"


# ── R · la semántica REAL ───────────────────────────────────────────────────────────────

class _GrafoConIntencion:
    """La persona habló con el agente de OTRO inmueble, con señales que el motor puntúa como
    «tibio» (precio y barrio, sin pedir visita ni contacto): con la sesión entera y sin ninguna
    fila de handoff, ese lead SÍ dispararía el reenganche (el control de R1 lo comprueba)."""

    class compiled_graph:
        @staticmethod
        async def aget_state(_config):
            class _E:
                values = {"messages": [
                    HumanMessage(content="¿Cuál es el precio final del departamento de la Av. Y?"),
                    AIMessage(content="Te paso los datos."),
                    HumanMessage(content="¿Es negociable? ¿Qué tal los servicios del barrio?"),
                ]}
            return _E()


@pg
async def test_R1_con_la_semantica_real_el_hecho_X2_vuelve_caliente_al_lead_y_no_hay_aviso(
        monkeypatch, base, entorno):
    """FIJA UN HALLAZGO, no una regla nueva. Con la intención REAL acotada a X, el mismo hecho que
    autoriza al corredor —la persona pidió contacto para X— es la señal «pidió corredor» del
    motor: nivel caliente → `evaluar_reenganche` calla (regla 1: los calientes / en handoff no se
    reenganchan). Hoy la población autorizada Y elegible de la rama B es VACÍA: el corredor no
    recibe avisos automáticos y el experimento no acumula filas nuevas. Si un rediseño de la
    elegibilidad la abre, este test debe caer y revisarse con su propio mandato."""
    llamadas = []

    async def real(sid, horas_inactividad=None, activo_id=None):
        llamadas.append((sid, activo_id))
        return await _INTENCION_REAL(sid, horas_inactividad=horas_inactividad, activo_id=activo_id)
    monkeypatch.setattr(chat, "intencion_de_sesion", real)
    monkeypatch.setattr(chat, "agent_graph", _GrafoConIntencion)
    from sqlalchemy import text
    sid = f"qr-{ACTIVO}-egrr1"
    await _dormida(base, sid)
    await _pide_corredor(base, sid)
    async with base() as db:     # lo que escribió en el hilo de X DESPUÉS de pedir contacto
        await db.execute(text(
            "INSERT INTO handoff_mensaje (session_id, activo_id, autor, texto, creado_en) "
            "VALUES (:s, CAST(:a AS uuid), 'lead', '¿Cuál es el precio final?', now())"),
            {"s": sid, "a": ACTIVO})
        await db.commit()
    res = await _barrer(base)
    assert llamadas == [(sid, ACTIVO)], "la rama del corredor usa la semántica acotada, y solo esa"
    _silencio(res, entorno)
    assert await _marcas(base, sid) == SIN_MARCA
    intenc = await _INTENCION_REAL(sid, horas_inactividad=120.0, activo_id=ACTIVO)
    assert intenc["senales"].get("corredor") and intenc["nivel"] == "caliente"
    assert evaluar_reenganche(intencion=intenc, horas_inactividad=120.0) is None
    # La causa es ESA y solo esa: el mismo hilo (solo tibio: precio) con «pidió corredor» apagado sí
    # sería elegible. Si un rediseño desacopla X2 → caliente, este test cae.
    from app.intencion import analizar_intencion
    for pidio, elegible in ((True, False), (False, True)):
        a = analizar_intencion(mensajes_usuario=["¿Cuál es el precio final?"], es_qr=True,
                               pidio_corredor=pidio, horas_inactividad=120.0)
        assert bool(evaluar_reenganche(intencion=a, horas_inactividad=120.0)) is elegible, pidio

    # Corolario histórico. La rama de sesión ENTERA del barrido viejo hacía «pidió corredor» = haber
    # CUALQUIER fila de handoff (con marca o sin ella) y callaba igual. Control: la misma
    # conversación, sin ninguna fila, sí dispara. Luego el aviso automático viejo al corredor solo
    # pudo salir para sesiones sin ninguna fila de handoff: nunca con el hecho X2.
    limpio, viejo = f"qr-{ACTIVO}-egrr2", f"qr-{ACTIVO}-egrr3"
    await _pide_corredor(base, viejo, marca=False)
    sin_fila = await _INTENCION_REAL(limpio, horas_inactividad=120.0)
    assert not sin_fila["senales"].get("corredor") and sin_fila["nivel"] == "tibio"
    assert evaluar_reenganche(intencion=sin_fila, horas_inactividad=120.0), "el control debe disparar"
    for con_fila in (sid, viejo):
        entera = await _INTENCION_REAL(con_fila, horas_inactividad=120.0)
        assert entera["senales"].get("corredor"), con_fila
        assert evaluar_reenganche(intencion=entera, horas_inactividad=120.0) is None, con_fila


# ══ S · sin base ════════════════════════════════════════════════════════════════════════

async def test_S1_toda_la_lectura_va_antes_de_reservar_ningun_grant(monkeypatch, entorno):
    """`corredor_autorizado` deshace la transacción si falla la lectura, y la intención abre otra
    conexión y lee el checkpointer: por eso TODAS esas lecturas van antes de la primera reserva TR-5
    del barrido (ni un rollback que tire un permiso consumido, ni E/S externa sosteniendo bloqueos)."""
    db = BaseEspia([_dormido("s1-comprador", consentido=True, pidio_corredor=True),
                    _dormido("s1-corredor", pidio_corredor=True)])
    doble, posiciones = chat.intencion_de_sesion, []

    async def espia(sid, **k):
        posiciones.append(len(db.sentencias))
        return await doble(sid, **k)
    monkeypatch.setattr(chat, "intencion_de_sesion", espia)
    res = await cron.escanear_reenganches(db)
    assert res["comprador"] == 1 and res["corredores"] == 1
    sql = [s for s, _ in db.sentencias]
    i_reserva = next(i for i, s in enumerate(sql) if "UPDATE consent_grant" in s)
    hechos = [i for i, s in enumerate(sql) if "FROM handoff_sesion" in s]
    assert len(hechos) == 2 and max(hechos) < i_reserva
    assert len(posiciones) == 3 and max(posiciones) <= i_reserva, posiciones


async def test_S1b_un_fallo_al_leer_el_hecho_falla_cerrado(entorno):
    class _Rota(BaseEspia):
        async def execute(self, stmt, params=None):
            if "FROM handoff_sesion" in str(stmt):
                raise RuntimeError("handoff_sesion no disponible")
            return await super().execute(stmt, params)
    db = _Rota([_dormido("s1b", pidio_corredor=True)])
    res = await cron.escanear_reenganches(db)
    assert res["corredores"] == 0 and db.updates_lead_actividad() == [] and db.rollbacks >= 1
    assert entorno["email"] == [] and entorno["push"] == [] and entorno["holdout"] == []


def test_S2_una_sola_fuente_del_hecho_del_corredor():
    """El hecho es el de X2 y nada más: ni el prefijo, ni el grant, ni la propiedad del inmueble."""
    funcion = ast.parse(inspect.getsource(corredor_autorizado)).body[0]
    codigo = "\n".join(ast.unparse(n) for n in funcion.body[1:])         # sin el docstring
    for exigido in ("FROM handoff_sesion", "session_id = :s", "activo_id = CAST(:a AS uuid)",
                    "principal_requested_at IS NOT NULL"):
        assert exigido in codigo, exigido
    for prohibido in ("qr-", "startswith", "consent_grant", "owner", "lead_actividad", "intencion"):
        assert prohibido not in codigo, prohibido
    assert _usos("corredor_autorizado") == [("app/reenganche_cron.py", "_escanear_reenganches")]


async def test_S3b_sin_elegibilidad_acotada_no_hay_reparto_aunque_el_hash_diga_holdout(monkeypatch, entorno):
    """Con el hecho X2 y canal, pero la semántica acotada no califica: el reparto ni se consulta."""
    _reparto(monkeypatch, entorno, {"s3b"})
    monkeypatch.setattr(chat, "intencion_de_sesion",
                        lambda sid, **k: _intencion_solo_de_sesion_entera(entorno, sid, **k))
    db = BaseEspia([_dormido("s3b", pidio_corredor=True)])
    res = await cron.escanear_reenganches(db)
    assert entorno["holdout"] == [] and res["holdout"] == 0 and db.updates_lead_actividad() == []


async def test_S4_con_canal_y_no_grant_la_decision_del_comprador_no_sirve_al_corredor(monkeypatch, entorno):
    """La variante sin base de D3: la decisión de sesión entera existe, el comprador da NO_GRANT, el
    corredor tiene el hecho, y aun así la rama B solo usa la elegibilidad acotada a X."""
    monkeypatch.setattr(chat, "intencion_de_sesion",
                        lambda sid, **k: _intencion_solo_de_sesion_entera(entorno, sid, **k))
    lead = _dormido("s4", consentido=True, pidio_corredor=True)
    lead["_grants"] = []                                           # canal del comprador, sin permiso
    db = BaseEspia([lead])
    res = await cron.escanear_reenganches(db)
    assert ("s4", None) in entorno["intencion_activo"], "la decisión del comprador sí se calculó"
    _silencio(res, entorno)
    assert db.updates_lead_actividad() == []


async def test_S5_si_el_commit_falla_no_sale_ningun_aviso(entorno):
    """TR-5: reserva + marcas van en UN commit antes de enviar; si ese commit falla, se deshace todo
    y no sale nada (ni al comprador ni al corredor)."""
    class _CommitRoto(BaseEspia):
        async def commit(self):
            if any("UPDATE consent_grant" in s for s, _ in self.sentencias):
                raise RuntimeError("commit roto")
            await super().commit()
    db = _CommitRoto([_dormido("s5-c", consentido=True), _dormido("s5-k", pidio_corredor=True)])
    res = await cron.escanear_reenganches(db)
    assert entorno["email"] == [] and entorno["push"] == []
    assert res["comprador"] == 0 and res["corredores"] == 0 and db.rollbacks >= 1
    assert res["disparados"] == 0 and res["holdout"] == 0, "el resumen no informa disparos que no ocurrieron"


async def test_S6_las_marcas_van_en_un_solo_commit(entorno):
    """Si falla la marca del corredor, tampoco queda confirmada la del comprador ni su grant: un
    commit partido le quitaría al comprador su única dosis sin avisarle."""
    commits_tras_reserva = []

    class _MarcaRota(BaseEspia):
        async def execute(self, stmt, params=None):
            if "reenganche_grupo = 'tocado'" in str(stmt):
                raise RuntimeError("marca rota")
            return await super().execute(stmt, params)

        async def commit(self):
            if any("UPDATE consent_grant" in s for s, _ in self.sentencias):
                commits_tras_reserva.append(len(self.sentencias))
            await super().commit()
    db = _MarcaRota([_dormido("s6-c", consentido=True), _dormido("s6-k", pidio_corredor=True)])
    res = await cron.escanear_reenganches(db)
    assert commits_tras_reserva == [], "se confirmó algo entre la reserva y la marca rota"
    assert entorno["email"] == [] and entorno["push"] == [] and res["comprador"] == 0


async def test_S7_sin_secreto_el_comprador_autorizado_no_cae_al_corredor(monkeypatch, entorno):
    """AUTHORIZED sin REENGANCHE_BAJA_SECRET: el lead queda intacto —ni comprador, ni corredor
    (aunque tenga el hecho X2), ni marca— y el grant no se consume."""
    monkeypatch.delenv("REENGANCHE_BAJA_SECRET")
    db = BaseEspia([_dormido("s7", consentido=True, pidio_corredor=True)])
    res = await cron.escanear_reenganches(db)
    _silencio(res, entorno)
    assert db.updates_lead_actividad() == []
    assert not [s for s, _ in db.sentencias if "UPDATE consent_grant" in s]


async def test_S8_si_falla_la_decision_del_comprador_no_cae_al_corredor(monkeypatch, entorno):
    """Si no se puede calcular la decisión del comprador (que tiene prioridad), el lead no produce
    nada en este barrido, como un ERROR de autoridad: un fallo transitorio no regala su dosis única
    al corredor."""
    async def intencion(sid, horas_inactividad=None, activo_id=None):
        entorno["intencion_activo"].append((sid, activo_id))
        if activo_id is None:
            raise RuntimeError("checkpointer caído")
        return {"turnos": 4, "nivel": "tibio", "estado": "dormido", "senales": {"precio": True}}
    monkeypatch.setattr(chat, "intencion_de_sesion", intencion)
    db = BaseEspia([_dormido("s8", consentido=True, pidio_corredor=True)])
    res = await cron.escanear_reenganches(db)
    _silencio(res, entorno)
    assert db.updates_lead_actividad() == []
    assert not [s for s, _ in db.sentencias if "UPDATE consent_grant" in s]


class _BaseTx(BaseEspia):
    """Modela la transacción: lo reservado queda PENDIENTE hasta el commit; un error la aborta (toda
    sentencia siguiente falla) y el rollback descarta lo pendiente."""

    def __init__(self, dormidos, falla_en):
        super().__init__(dormidos)
        self.pendiente, self.confirmado, self.abortada, self.falla_en = set(), set(), False, falla_en

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if self.abortada:
            raise RuntimeError("current transaction is aborted")
        if "UPDATE consent_grant" in sql and (params or {}).get("sid") == self.falla_en:
            self.abortada = True
            raise RuntimeError("lock timeout")
        r = await super().execute(stmt, params)
        if "UPDATE consent_grant" in sql:
            self.pendiente.update((params["sid"], f["channel"]) for f in r.all())
        return r

    async def commit(self):
        if self.abortada:
            raise RuntimeError("current transaction is aborted")
        self.confirmado |= self.pendiente
        self.pendiente = set()
        await super().commit()

    async def rollback(self):
        self.pendiente, self.abortada = set(), False
        await super().rollback()


async def test_S9_ningun_aviso_al_comprador_sin_su_grant_consumido_en_el_mismo_commit(entorno):
    """TR-5 ante un ERROR por excepción A MITAD del barrido: L1 ya reservó; la reserva de L2 rompe la
    transacción. Nada puede salir hacia un comprador cuyo consumo no quedó confirmado (un rollback
    «para seguir» tiraría la reserva de L1 y, aun así, se le avisaría)."""
    import app.baja_aviso as baja
    db = _BaseTx([_dormido("s9-1", consentido=True), _dormido("s9-2", consentido=True),
                  _dormido("s9-3", pidio_corredor=True)], falla_en="s9-2")
    await cron.escanear_reenganches(db)
    for e in entorno["email"]:
        if e["to"] == "comprador@prueba.test":
            sid = baja.verificar(e["baja_url"].split("?baja=", 1)[1])
            assert (sid, "EMAIL") in db.confirmado, f"aviso a {sid} sin su grant consumido"
    for p in entorno["push"]:
        if "?baja=" in p["url"]:
            sid = baja.verificar(p["url"].split("?baja=", 1)[1])
            assert (sid, "PUSH") in db.confirmado, f"push a {sid} sin su grant consumido"


@pytest.mark.parametrize("acotada", ["lanza", "caliente"])
async def test_S12_si_la_acotada_falla_o_no_califica_no_hay_respaldo_de_sesion_entera(
        monkeypatch, entorno, acotada):
    """§4: «If the scoped semantics do not produce an eligible reengagement: silence. Do not fall
    back to session-wide intent». Ni cuando la llamada acotada lanza, ni cuando trae turnos pero
    no califica (caliente); la de sesión entera, que sí calificaría, no se usa para el corredor."""
    async def intencion(sid, horas_inactividad=None, activo_id=None):
        entorno["intencion_activo"].append((sid, activo_id))
        if activo_id is None:
            return {"turnos": 6, "nivel": "tibio", "estado": "dormido", "senales": {"precio": True}}
        if acotada == "lanza":
            raise RuntimeError("checkpointer caído")
        return {"turnos": 3, "nivel": "caliente", "estado": "intencion", "handoff_sugerido": True,
                "senales": {"corredor": True, "precio": True}}
    monkeypatch.setattr(chat, "intencion_de_sesion", intencion)
    db = BaseEspia([_dormido("s12", pidio_corredor=True)])
    res = await cron.escanear_reenganches(db)
    assert entorno["intencion_activo"] == [("s12", "11111111-1111-1111-1111-111111111111")]
    _silencio(res, entorno)
    assert db.updates_lead_actividad() == []


@pytest.mark.parametrize("falta", ["RESEND_API_KEY", "VAPID_PRIVATE_KEY"])
async def test_S10_sin_credencial_de_un_canal_del_comprador_no_se_reserva_ni_se_marca(monkeypatch, entorno, falta):
    """§7: «si faltan los prerrequisitos de entrega: sin marca, sin consumo del grant, sin efecto».
    Al comprador (con grant en sus dos canales) le falta la credencial de UNO en el servidor: la
    frontera se consulta sin reservar, el lead queda intacto y tampoco cae al corredor."""
    import app.notifications as notif
    monkeypatch.setattr(notif, falta, None)
    db = BaseEspia([_dormido("s10", consentido=True, pidio_corredor=True)])
    res = await cron.escanear_reenganches(db)
    _silencio(res, entorno)
    assert db.updates_lead_actividad() == []
    assert not [s for s, _ in db.sentencias if "UPDATE consent_grant" in s], "se consumió un grant"


async def test_S11_sin_credencial_del_canal_del_corredor_no_hay_experimento(monkeypatch, entorno):
    """El corredor solo tiene correo y el servidor no tiene RESEND_API_KEY: no hay canal entregable,
    así que no hay tratamiento posible ni control válido. Control: con la credencial, sí entra."""
    import app.notifications as notif

    async def solo_correo(db, activo_id):
        return "corredor@prueba.test", []
    monkeypatch.setattr(chat, "_corredor_de_activo", solo_correo)
    monkeypatch.setattr(notif, "RESEND_API_KEY", None)
    db = BaseEspia([_dormido("s11", pidio_corredor=True)])
    res = await cron.escanear_reenganches(db)
    _silencio(res, entorno)
    assert entorno["intencion_activo"] == [] and db.updates_lead_actividad() == []
    monkeypatch.setattr(notif, "RESEND_API_KEY", "re_prueba")
    res = await cron.escanear_reenganches(BaseEspia([_dormido("s11", pidio_corredor=True)]))
    assert res["corredores"] == 1 and entorno["holdout"] == ["s11"]


async def test_S3_el_lead_sin_hecho_no_se_reparte_aunque_el_hash_diga_holdout(monkeypatch, entorno):
    """ELEGIBILIDAD ≠ AUTORIDAD PARA ACTUAR: el reparto del experimento no se consulta para quien
    el corredor no está autorizado a recibir, aunque el hash lo mandara al control."""
    _reparto(monkeypatch, entorno, {"s3-sin-hecho", "s3-con-hecho"})
    db = BaseEspia([_dormido("s3-sin-hecho"), _dormido("s3-con-hecho", pidio_corredor=True)])
    res = await cron.escanear_reenganches(db)
    assert entorno["holdout"] == ["s3-con-hecho"] and res["holdout"] == 1
    (marca,) = db.updates_lead_actividad()
    assert marca[1]["ids"] == ["s3-con-hecho"] and "reenganche_grupo = 'holdout'" in marca[0]
