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
    async with Sesion() as db:
        return await cron.escanear_reenganches(db)


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
async def test_A_sin_autoridad_cero_efectos_y_cero_marcas(base, entorno):
    """Caso A. La intención de la sesión entera dispararía (el doble devuelve un lead tibio y
    dormido con señal de precio). Uno dejó canal sin grant; otro llegó por el QR de X. Ninguno
    tiene el hecho X2."""
    con_canal, por_qr = "egr-a-1", f"qr-{ACTIVO}-egra2"
    await _dormida(base, con_canal, email="a@ejemplo.invalid", push=PUSH)
    await _dormida(base, por_qr)
    res = await _barrer(base)
    assert res["escaneados"] == 2
    _silencio(res, entorno)
    for sid in (con_canal, por_qr):
        assert await _marcas(base, sid) == SIN_MARCA


@pg
async def test_B_no_grant_no_es_autoridad_para_el_corredor(monkeypatch, base, entorno):
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
    assert veredictos == [EstadoAutorizacion.NO_GRANT]
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
async def test_E_solo_la_atribucion_qr_no_autoriza_nada(base, entorno):
    """Caso E. Sesión `qr-X-…`, sin solicitud: ni aviso, ni marcas del experimento. La semántica
    acotada ni siquiera se calcula: la elegibilidad va DESPUÉS de la autoridad."""
    sid = f"qr-{ACTIVO}-egre1"
    await _dormida(base, sid)
    res = await _barrer(base)
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
    """La misma función pura que sirve `/metricas/lift`, sobre las filas reales."""
    from sqlalchemy import text
    from app.lift import resumen_lift
    async with Sesion() as db:
        filas = (await db.execute(text(
            "SELECT session_id, primera_actividad, ultima_actividad, reenganche_grupo, "
            "reenganche_elegible_en FROM lead_actividad"))).mappings().all()
    act = {f["session_id"]: dict(f) for f in filas}
    leads = [{"session_id": s, "estado": "dormido", "handoff": False} for s in act]
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
            "VALUES (:s, CAST(:a AS uuid), 'lead', '¿Cuál es el precio? Quiero visitarlo', now())"),
            {"s": sid, "a": ACTIVO})
        await db.commit()
    res = await _barrer(base)
    assert llamadas == [(sid, ACTIVO)], "la rama del corredor usa la semántica acotada, y solo esa"
    _silencio(res, entorno)
    assert await _marcas(base, sid) == SIN_MARCA
    intenc = await _INTENCION_REAL(sid, horas_inactividad=120.0, activo_id=ACTIVO)
    assert intenc["senales"].get("corredor") and intenc["nivel"] == "caliente"
    assert evaluar_reenganche(intencion=intenc, horas_inactividad=120.0) is None

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

async def test_S1_el_hecho_X2_se_lee_antes_de_reservar_ningun_grant(entorno):
    """`corredor_autorizado` deshace la transacción si falla la lectura: por eso TODAS sus
    lecturas van antes de la primera reserva TR-5 del barrido."""
    db = BaseEspia([_dormido("s1-comprador", consentido=True, pidio_corredor=True),
                    _dormido("s1-corredor", pidio_corredor=True)])
    res = await cron.escanear_reenganches(db)
    assert res["comprador"] == 1 and res["corredores"] == 1
    sql = [s for s, _ in db.sentencias]
    i_reserva = next(i for i, s in enumerate(sql) if "UPDATE consent_grant" in s)
    hechos = [i for i, s in enumerate(sql) if "FROM handoff_sesion" in s]
    assert len(hechos) == 2 and max(hechos) < i_reserva


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


async def test_S3_el_lead_sin_hecho_no_se_reparte_aunque_el_hash_diga_holdout(monkeypatch, entorno):
    """ELEGIBILIDAD ≠ AUTORIDAD PARA ACTUAR: el reparto del experimento no se consulta para quien
    el corredor no está autorizado a recibir, aunque el hash lo mandara al control."""
    _reparto(monkeypatch, entorno, {"s3-sin-hecho", "s3-con-hecho"})
    db = BaseEspia([_dormido("s3-sin-hecho"), _dormido("s3-con-hecho", pidio_corredor=True)])
    res = await cron.escanear_reenganches(db)
    assert entorno["holdout"] == ["s3-con-hecho"] and res["holdout"] == 1
    (marca,) = db.updates_lead_actividad()
    assert marca[1]["ids"] == ["s3-con-hecho"] and "reenganche_grupo = 'holdout'" in marca[0]
