"""Plan 1.1 · TR-4 · el barrido de reenganche no tiene entrada en la API y obedece su bandera.

Antes de TR-4, `POST /api/v1/assets/reenganche/scan` lo podía llamar CUALQUIER cuenta
autenticada: un barrido GLOBAL que marcaba leads ajenos (dosis única de por vida y grupo del
experimento de lift) y mandaba correo y push a compradores y corredores de terceros. Y se
saltaba `REENGANCHE_CRON_ENABLED`, que solo se miraba al arrancar el bucle.

Lo que estos tests fijan:
  1. la ruta no existe, ni con ese path ni con otro que alcance el barrido;
  2. la ÚNICA entrada al barrido es `escanear_reenganches`, y solo la llama el bucle de fondo;
  3. con la bandera apagada no hay NINGUNA lectura, escritura, correo ni push — aunque el
     caller ya exista o la bandera se apague después del arranque;
  4. con la bandera encendida el job legítimo hace exactamente lo de antes.

La base es un DOBLE que registra cada sentencia: sin Postgres, sin red. Los envíos se
interceptan en `_send_email` / `_send_push`, detrás de `send_notification`, para que un correo
o un push que se cuele por cualquier camino se cuente.
"""
from __future__ import annotations

import ast
import asyncio
import inspect
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.notifications as notif
import app.reenganche_cron as cron
import app.routers.chat as chat

RAIZ = Path(__file__).resolve().parents[1]
RUTA_RETIRADA = "/api/v1/assets/reenganche/scan"
APAGADAS = ("0", "false", "No", "")


# ── Dobles ──────────────────────────────────────────────────────────────────────────────

class _Resultado:
    def __init__(self, filas):
        self._filas = filas

    def mappings(self):
        return self

    def all(self):
        return list(self._filas)

    def first(self):
        return self._filas[0] if self._filas else None

    def scalar(self):
        return None


class BaseEspia:
    """Registra cada sentencia. Devuelve dormidos para el SELECT de lead_actividad y la ficha
    del activo para el SELECT de activos_inmutables; todo lo demás, vacío."""

    def __init__(self, dormidos=()):
        self.dormidos = list(dormidos)
        self.sentencias: list[tuple[str, dict]] = []
        self.commits = 0
        self.rollbacks = 0

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        self.sentencias.append((sql, dict(params or {})))
        if "FROM lead_actividad" in sql and sql.lstrip().upper().startswith("SELECT"):
            return _Resultado(self.dormidos)
        if "FROM activos_inmutables" in sql:
            return _Resultado([{"dir": "Av. Prueba N1-23", "f": None, "corredor_id": "corr-1"}])
        return _Resultado([])

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    def updates_lead_actividad(self):
        return [(s, p) for s, p in self.sentencias if s.lstrip().upper().startswith("UPDATE LEAD_ACTIVIDAD")]


def _dormido(sid, *, consentido=False):
    from datetime import datetime, timedelta, timezone
    return {
        "session_id": sid, "activo_id": "11111111-1111-1111-1111-111111111111",
        "ultima_actividad": datetime.now(timezone.utc) - timedelta(days=5),
        "lead_email": "comprador@prueba.test" if consentido else None,
        "lead_push": {"endpoint": "https://push.prueba.test/c"} if consentido else None,
        "consent_reenganche_at": datetime.now(timezone.utc) if consentido else None,
    }


@pytest.fixture
def entorno(monkeypatch):
    """Intercepta TODO lo que el barrido toca fuera de la base y cuenta cada llamada."""
    registro = {"email": [], "push": [], "intencion": [], "corredor": [], "holdout": []}

    async def email(**kw):
        registro["email"].append(kw)

    async def push(**kw):
        registro["push"].append(kw)

    async def intencion(sid, horas_inactividad=None):
        registro["intencion"].append(sid)
        return {"turnos": 4, "nivel": "tibio", "estado": "dormido", "senales": {"precio": True}}

    async def corredor(db, activo_id):
        registro["corredor"].append(activo_id)
        return "corredor@prueba.test", [{"endpoint": "https://push.prueba.test/k"}]

    def holdout(sid, pct):
        registro["holdout"].append(sid)
        return "tocado"

    monkeypatch.setattr(notif, "_send_email", email)
    monkeypatch.setattr(notif, "_send_push", push)
    monkeypatch.setattr(chat, "intencion_de_sesion", intencion)
    monkeypatch.setattr(chat, "_corredor_de_activo", corredor)
    monkeypatch.setattr("app.lift.grupo_holdout", holdout)
    # Sin esto, un proceso que ya "preparó" la tabla se saltaría el DDL y un gate mal
    # colocado DESPUÉS de ensure_lead_actividad pasaría inadvertido.
    monkeypatch.setattr(chat, "_lead_actividad_ready", False)
    monkeypatch.setenv("REENGANCHE_AUTO_LEAD", "1")
    # Plan 1.1 · TR-2 (actualización esperada): el aviso al comprador exige un enlace de baja
    # firmado y, sin secreto, no sale (fail-closed). «El job legítimo» de test_7 y test_9b es
    # el de un despliegue CON secreto; la ausencia se prueba en tests/test_tr2_consentimiento.py.
    monkeypatch.setenv("REENGANCHE_BAJA_SECRET", "s" * 48)
    return registro


def _sin_efectos(db: BaseEspia, registro: dict):
    assert db.sentencias == [], f"el barrido tocó la base con la bandera apagada: {db.sentencias[:3]}"
    assert db.commits == 0 and db.rollbacks == 0
    assert db.updates_lead_actividad() == []
    assert registro["email"] == [], "salió un correo con la bandera apagada"
    assert registro["push"] == [], "salió un push con la bandera apagada"
    assert registro["intencion"] == [] and registro["corredor"] == [] and registro["holdout"] == [], \
        "se calcularon destinatarios con la bandera apagada"


# ── 1 · La ruta ya no existe ─────────────────────────────────────────────────────────────

def _app():
    import main
    return main.app


def test_1_la_ruta_no_esta_en_el_inventario():
    rutas = {getattr(r, "path", "") for r in _app().routes}
    assert RUTA_RETIRADA not in rutas
    assert not [p for p in rutas if "reenganche" in p], "reapareció una ruta de reenganche"


def test_1b_ningun_endpoint_alcanza_el_barrido():
    """Inventario por CONTENIDO, no por nombre: una ruta con otro path que llame al barrido
    es el mismo agujero con otro disfraz."""
    culpables = []
    for r in _app().routes:
        fn = getattr(r, "endpoint", None)
        if fn is None:
            continue
        try:
            fuente = inspect.getsource(fn)
        except (OSError, TypeError):
            continue
        if "escanear_reenganches" in fuente or "reenganche_cron" in fuente:
            culpables.append(getattr(r, "path", "?"))
    assert culpables == []


@pytest.mark.parametrize("rol", [None, "cliente", "corredor", "inmobiliaria"])
@pytest.mark.parametrize("metodo", ["post", "get", "put"])
def test_2_el_path_retirado_no_ejecuta_el_barrido(monkeypatch, rol, metodo):
    """Ninguna cuenta —tampoco una que se dio a sí misma el rol de corredor o inmobiliaria
    (SEC-AUTH-ROLE-01)— puede provocar el barrido por HTTP."""
    from app.auth import CurrentUser, get_current_user
    llamadas = []

    async def espia(*a, **k):
        llamadas.append(1)
        return {}

    monkeypatch.setattr(cron, "escanear_reenganches", espia)
    monkeypatch.setattr(cron, "_escanear_reenganches", espia)
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    app = _app()
    if rol:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            user_id="00000000-0000-0000-0000-0000000000a1", email="x@prueba.test", rol=rol)
    try:
        r = getattr(TestClient(app), metodo)(RUTA_RETIRADA)  # sin `with`: no corre el lifespan
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert r.status_code in (404, 405), r.status_code
    assert llamadas == []


# ── 2 · Una sola entrada, un solo caller ─────────────────────────────────────────────────

def _fuentes_de_produccion():
    for base in ("app", "scripts", "evals"):
        yield from (RAIZ / base).rglob("*.py")
    yield RAIZ / "main.py"


def _usos(nombre: str):
    """(fichero, función que lo contiene) por cada referencia a `nombre` en producción:
    llamadas, atributos e imports. Un alias no lo esconde: el import ya cuenta."""
    hallados = []
    for f in _fuentes_de_produccion():
        arbol = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        padres = {}
        for nodo in ast.walk(arbol):
            for hijo in ast.iter_child_nodes(nodo):
                padres[hijo] = nodo

        def funcion_de(n):
            while n in padres:
                n = padres[n]
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return n.name
            return "<módulo>"

        rel = f.relative_to(RAIZ).as_posix()
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Name) and nodo.id == nombre and isinstance(nodo.ctx, ast.Load):
                hallados.append((rel, funcion_de(nodo)))
            elif isinstance(nodo, ast.Attribute) and nodo.attr == nombre:
                hallados.append((rel, funcion_de(nodo)))
            elif isinstance(nodo, ast.ImportFrom) and any(a.name == nombre for a in nodo.names):
                hallados.append((rel, funcion_de(nodo)))
    return sorted(set(hallados))


def test_3_el_unico_caller_del_barrido_es_el_bucle_de_fondo():
    assert _usos("escanear_reenganches") == [("app/reenganche_cron.py", "_bucle")]


def test_3b_nadie_se_salta_la_entrada_con_la_bandera():
    """`_escanear_reenganches` no mira la bandera: llamarlo directo desde otro sitio es
    exactamente el camino que TR-4 cerró."""
    assert _usos("_escanear_reenganches") == [("app/reenganche_cron.py", "escanear_reenganches")]


# ── 3 · Bandera apagada: cero efectos ────────────────────────────────────────────────────

@pytest.mark.parametrize("valor", APAGADAS)
async def test_4_bandera_apagada_llamada_directa_sin_ningun_efecto(monkeypatch, entorno, valor):
    """Cubre los puntos 3-6 del mandato: cero consultas, cero UPDATE de lead_actividad, cero
    correo y cero push. La base TIENE dormidos listos para disparar: si el gate faltara o
    estuviera después de la primera lectura, se vería aquí."""
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", valor)
    db = BaseEspia([_dormido("qr-a-1"), _dormido("qr-a-2", consentido=True)])
    res = await cron.escanear_reenganches(db)
    assert res.get("deshabilitado") is True
    assert res["escaneados"] == 0 and res["disparados"] == 0
    _sin_efectos(db, entorno)


async def test_4b_la_bandera_se_vuelve_a_mirar_tras_el_candado(monkeypatch, entorno):
    """Quien esperaba turno detrás de otro barrido y encuentra la bandera ya apagada no
    entra: la bandera se decide al EJECUTAR, no al hacer cola."""
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    # Candado propio: el del módulo quedaría atado al bucle de este test al haber contención.
    monkeypatch.setattr(cron, "_scan_lock", asyncio.Lock())
    db = BaseEspia([_dormido("qr-b-1")])
    await cron._scan_lock.acquire()
    try:
        en_cola = asyncio.ensure_future(cron.escanear_reenganches(db))
        await asyncio.sleep(0)                      # pasa el primer control y queda en cola
        monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "0")
    finally:
        cron._scan_lock.release()
    res = await en_cola
    assert res.get("deshabilitado") is True
    _sin_efectos(db, entorno)


# ── 4 · Bandera encendida: el job legítimo no cambia ─────────────────────────────────────

async def test_7_bandera_encendida_el_barrido_hace_lo_de_siempre(monkeypatch, entorno):
    """Dos dormidos: uno sin canal propio (se avisa a su corredor) y uno con consentimiento y
    canal (le llega a él). Mismo resumen, mismas marcas y mismos envíos que antes de TR-4."""
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    db = BaseEspia([_dormido("qr-c-1"), _dormido("qr-c-2", consentido=True)])
    res = await cron.escanear_reenganches(db)

    assert res == {"escaneados": 2, "disparados": 2, "holdout": 0, "comprador": 1, "corredores": 1}
    assert any("FROM lead_actividad" in s for s, _ in db.sentencias)
    marcas = db.updates_lead_actividad()
    assert len(marcas) == 1 and "reenganche_grupo = 'tocado'" in marcas[0][0]
    assert sorted(marcas[0][1]["ids"]) == ["qr-c-1", "qr-c-2"]
    assert sorted(e["to"] for e in entorno["email"]) == ["comprador@prueba.test", "corredor@prueba.test"]
    assert len(entorno["push"]) == 2
    assert entorno["intencion"] == ["qr-c-1", "qr-c-2"]


def test_8_iniciar_cron_con_bandera_apagada_no_crea_tarea(monkeypatch):
    async def escenario():
        cron._tarea = None
        cron.iniciar_cron()
        creada = cron._tarea
        await cron.detener_cron()
        return creada
    for valor in APAGADAS:
        monkeypatch.setenv("REENGANCHE_CRON_ENABLED", valor)
        assert asyncio.run(escenario()) is None, valor


def test_8b_iniciar_cron_con_bandera_encendida_arranca_el_bucle(monkeypatch):
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")

    async def escenario():
        cron._tarea = None
        cron.iniciar_cron()
        nombre = cron._tarea.get_coro().__qualname__ if cron._tarea else None
        await cron.detener_cron()                   # antes del primer sleep: no barre nada
        return nombre
    assert asyncio.run(escenario()) == "_bucle"


# ── 5 · El bucle real: bandera apagada DESPUÉS del arranque ──────────────────────────────

def _correr_bucle(monkeypatch, db: BaseEspia, *, apagar_tras_arrancar: bool) -> None:
    """Arranca el bucle REAL con la bandera encendida y deja pasar exactamente un barrido.
    El sleep del intervalo se sustituye: la primera vuelta vuelve de inmediato (y, si se pide,
    apaga la bandera en ese momento, ya con el bucle corriendo); la segunda cancela."""
    import app.database as database
    dormir_de_verdad = asyncio.sleep
    vueltas = {"n": 0}

    async def dormir(segundos, *a, **k):
        if segundos == 0:
            return await dormir_de_verdad(0)
        vueltas["n"] += 1
        if vueltas["n"] == 1:
            if apagar_tras_arrancar:
                monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "0")
            return None
        raise asyncio.CancelledError

    class _Sesion:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _Sesion())
    monkeypatch.setattr(cron.asyncio, "sleep", dormir)

    async def escenario():
        cron._tarea = None
        cron.iniciar_cron()
        assert cron._tarea is not None, "con la bandera encendida el bucle debe arrancar"
        await cron._tarea
        cron._tarea = None

    asyncio.run(escenario())
    assert vueltas["n"] == 2, "el bucle no dio la vuelta esperada"


def test_9_bandera_apagada_despues_del_arranque_el_siguiente_barrido_no_hace_nada(monkeypatch, entorno):
    db = BaseEspia([_dormido("qr-d-1"), _dormido("qr-d-2", consentido=True)])
    _correr_bucle(monkeypatch, db, apagar_tras_arrancar=True)
    _sin_efectos(db, entorno)


def test_9b_control_el_mismo_bucle_con_la_bandera_encendida_si_barre(monkeypatch, entorno):
    """El control de test_9: sin apagar la bandera, el mismo arnés SÍ produce el barrido. Sin
    esto, test_9 pasaría también con un bucle que no barre nunca."""
    db = BaseEspia([_dormido("qr-e-1")])
    _correr_bucle(monkeypatch, db, apagar_tras_arrancar=False)
    assert db.updates_lead_actividad(), "el bucle legítimo dejó de barrer"
    assert entorno["email"] and entorno["push"]
