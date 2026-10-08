"""SEC-X2-SCAN-FAIRNESS-R0 · el barrido del reenganche recorre TODO el universo dormido sin mutar lo descartado.

    FILA VIEJA DESCARTADA / SIN AUTORIDAD ≠ DERECHO PERMANENTE A OCUPAR LA VENTANA DEL BARRIDO

Antes el barrido leía UNA página (`ORDER BY ultima_actividad ASC LIMIT 200`). Una fila descartada (sin canal,
NO_GRANT, sin el hecho X2, no elegible) no recibe ninguna marca y conserva su `ultima_actividad`, así que volvía a
la cabeza del orden en cada barrido; con 200 así, ninguna posterior se leía jamás. Ahora:

  · recorrido KEYSET por (ultima_actividad, session_id), orden y comparador en SQL; la página siguiente empieza
    después de la ÚLTIMA FILA LEÍDA (no de la última elegible); sin OFFSET;
  · un corte temporal FIJO, tomado una vez: el universo no avanza mientras se recorre;
  · `REENGANCHE_CRON_LIMITE` = presupuesto de resultados con CONSECUENCIA (aviso al comprador, tocado, holdout);
    lo descartado no lo consume; lleno el presupuesto, ninguna reserva ni marca más;
  · lo descartado no recibe NINGUNA escritura: la justicia sale del recorrido, no de la mutación.

Bloque B: PostgreSQL 15 real (`TEST_DATABASE_URL`), esquema efímero de TR-2 (`lead_actividad` con su DDL real,
`public.consent_grant` de la 038, sesiones y grants creados por los endpoints reales). Un espía envuelve la sesión
del barrido y registra cada página (SQL, parámetros y filas). Sin la variable, B se SALTA.
Bloque A: sin base (estructura y la guarda de avance sobre el doble de TR-4).
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import logging
import textwrap

import pytest
from sqlalchemy import text

import app.reenganche_cron as cron
import app.routers.chat as chat
from tests.test_tr2_consentimiento import ACTIVO, _dormida, _fila, _pide_corredor, base, pg  # noqa: F401
from tests.test_tr4_reenganche import BaseEspia, _dormido, entorno  # noqa: F401
from tests.test_tr5_consent_grant import _grants_completos, _lead_con_grant

SIN_MARCA = (None, None, None)
CORREDOR = "corredor@prueba.test"


@pytest.fixture(autouse=True)
def _fairness(monkeypatch):
    from app.limiter import limiter
    monkeypatch.setattr(limiter, "enabled", False)
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "1")
    monkeypatch.delenv("REENGANCHE_CRON_LIMITE", raising=False)


# ── el espía de la sesión del barrido ─────────────────────────────────────────────────────

class _Filas:
    def __init__(self, filas):
        self._f = filas

    def mappings(self):
        return self

    def all(self):
        return list(self._f)


class _Espia:
    """Envuelve la sesión REAL. Registra cada página del recorrido (SQL, parámetros y session_id devueltos) y
    deja correr un gancho ANTES de cada página (índice 0, 1, …) para simular lo que pasa entre páginas."""

    def __init__(self, db, antes_de_pagina=None):
        self._db, self._gancho = db, antes_de_pagina
        self.paginas: list[tuple[str, dict, list]] = []
        self.cortes: list = []          # el `corte` que devolvió cada página (None si vino vacía)
        self.orden: list[str] = []      # 'pagina' | 'reserva' | 'otra', en el orden en que se ejecutaron
        self.sentencias = 0

    async def execute(self, stmt, params=None):
        self.sentencias += 1
        sql = str(stmt)
        if "FROM lead_actividad" in sql and "ORDER BY ultima_actividad" in sql:
            if self._gancho:
                await self._gancho(len(self.paginas), self._db)
            filas = (await self._db.execute(stmt, params)).mappings().all()
            self.paginas.append((sql, dict(params or {}), [f["session_id"] for f in filas]))
            self.cortes.append(filas[0]["corte"] if filas else None)
            self.orden.append("pagina")
            return _Filas(filas)
        self.orden.append("reserva" if "UPDATE consent_grant" in sql else "otra")
        return await self._db.execute(stmt, params)

    async def commit(self):
        await self._db.commit()

    async def rollback(self):
        await self._db.rollback()


async def _barrer(Sesion, gancho=None):
    async with Sesion() as db:
        await chat.ensure_handoff_tables(db)
    async with Sesion() as db:
        espia = _Espia(db, gancho)
        res = await asyncio.wait_for(cron.escanear_reenganches(espia), 120)   # un bucle sin fin falla, no cuelga
    return res, espia


async def _viejas(Sesion, n, prefijo, *, dias=60, email=False, mismo_instante=False):
    """`n` filas dormidas que el barrido DESCARTA: sin canal (o con correo y sin grant = NO_GRANT), sin el hecho
    X2. Más viejas que cualquier `_dormida` (5 días) y en orden: la i-ésima, i segundos más nueva."""
    async with Sesion() as db:
        await chat.ensure_lead_actividad(db)
        await db.execute(text(
            "INSERT INTO lead_actividad (session_id, activo_id, ultima_actividad, lead_email) "
            "SELECT :p || lpad(i::text, 4, '0'), CAST(:a AS uuid), "
            "       date_trunc('second', now()) - make_interval(days => :d) "
            "         + CASE WHEN :m THEN interval '0' ELSE make_interval(secs => i) END, "
            "       CASE WHEN :e THEN 'x' || i || '@ejemplo.invalid' END "
            "FROM generate_series(1, :n) i"),
            {"p": prefijo, "a": ACTIVO, "d": dias, "m": mismo_instante, "e": email, "n": n})
        await db.commit()
    return [f"{prefijo}{i:04d}" for i in range(1, n + 1)]


async def _huella(Sesion, excluir=()) -> tuple:
    """Huella de `lead_actividad`, `consent_grant` y `handoff_sesion` salvo las sesiones excluidas. Lleva el
    CONTENIDO y el `xmin` de cada fila: cualquier escritura en una fila descartada —también una que no cambie el
    valor (`SET x = x`), o una marca de «visto» en el hecho X2— la cambia."""
    async with Sesion() as db:
        la = (await db.execute(text(
            "SELECT md5(coalesce(string_agg(t::text || t.xmin::text, '|' ORDER BY session_id), '')) "
            "FROM lead_actividad t WHERE NOT (session_id = ANY(:x))"), {"x": list(excluir)})).scalar()
        cg = (await db.execute(text(
            "SELECT md5(coalesce(string_agg(g::text || g.xmin::text, '|' ORDER BY grant_id), '')) "
            "FROM consent_grant g WHERE NOT (session_id = ANY(:x))"), {"x": list(excluir)})).scalar()
        hs = None
        if (await db.execute(text("SELECT to_regclass('handoff_sesion') IS NOT NULL"))).scalar():
            hs = (await db.execute(text(
                "SELECT md5(coalesce(string_agg(h::text || h.xmin::text, '|' ORDER BY session_id, activo_id), '')) "
                "FROM handoff_sesion h WHERE NOT (session_id = ANY(:x))"), {"x": list(excluir)})).scalar()
    return la, cg, hs or md5_vacio()


def md5_vacio() -> str:
    import hashlib
    return hashlib.md5(b"").hexdigest()


async def _marcas(Sesion, sid) -> tuple:
    f = await _fila(Sesion, sid)
    return f["reenganche_grupo"], f["reenganche_elegible_en"], f["reenganche_enviado_en"]


async def _envejecer(Sesion, sid, dias):
    async with Sesion() as db:
        await db.execute(text("UPDATE lead_actividad SET ultima_actividad = now() - make_interval(days => :d) "
                              "WHERE session_id = :s"), {"d": dias, "s": sid})
        await db.commit()


def _comprador_recibio(entorno, n=1) -> None:
    correos = [e for e in entorno["email"] if e["to"] != CORREDOR]
    assert len(correos) == n, entorno["email"]


async def _sin_uso(Sesion, sid) -> bool:
    return all(g["used_at"] is None for g in await _grants_completos(Sesion, sid))


# ══ B · PostgreSQL real ════════════════════════════════════════════════════════════════════

@pg
async def test_A_siete_descartadas_viejas_y_una_autorizada_mas_nueva(monkeypatch, base, entorno):
    """Caso A (el estado de producción del C0: 7 filas sin autoridad ni canal en la cabeza). Con páginas de 3, la
    fila 8 —un comprador con grant— se alcanza en el MISMO barrido y las 7 quedan idénticas."""
    monkeypatch.setattr(cron, "_PAGINA", 3)
    viejas = await _viejas(base, 7, "a-vieja-")
    comprador, _ = await _lead_con_grant(base)
    antes = await _huella(base, excluir=[comprador])
    res, espia = await _barrer(base)
    assert res["comprador"] == 1 and res["escaneados"] == 8
    _comprador_recibio(entorno)
    assert (await _fila(base, comprador))["reenganche_enviado_en"] is not None
    assert await _huella(base, excluir=[comprador]) == antes, "una fila descartada recibió una escritura"
    assert [len(p[2]) for p in espia.paginas] == [3, 3, 2]
    for sid in viejas:
        assert await _marcas(base, sid) == SIN_MARCA


@pg
async def test_B_quinientas_descartadas_y_la_501_autorizada(base, entorno):
    """Caso B. 500 filas viejas sin autoridad y la 501 autorizada, con la página por defecto (200): tres páginas,
    la 501 recibe y las filas 1-500 no cambian ni un byte."""
    await _viejas(base, 500, "b-vieja-")
    comprador, _ = await _lead_con_grant(base)
    antes = await _huella(base, excluir=[comprador])
    res, espia = await _barrer(base)
    assert res["comprador"] == 1 and res["escaneados"] == 501
    _comprador_recibio(entorno)
    assert not await _sin_uso(base, comprador), "el grant del comprador alcanzado no se consumió"
    assert await _huella(base, excluir=[comprador]) == antes, "las filas 1-500 cambiaron"
    assert [len(p[2]) for p in espia.paginas] == [200, 200, 101]
    # TODAS las páginas se leen antes de la primera reserva TR-5: ningún grant queda bloqueado mientras se lee.
    assert "reserva" in espia.orden
    assert max(i for i, o in enumerate(espia.orden) if o == "pagina") < espia.orden.index("reserva")


@pg
async def test_C_varias_paginas_sin_canal_y_la_autorizada_despues(monkeypatch, base, entorno):
    monkeypatch.setattr(cron, "_PAGINA", 2)
    await _viejas(base, 5, "c-sin-canal-")
    comprador, _ = await _lead_con_grant(base)
    res, espia = await _barrer(base)
    # 6 filas en páginas de 2: tres llenas y una consulta vacía que confirma que el universo se agotó.
    assert res["comprador"] == 1 and [len(p[2]) for p in espia.paginas] == [2, 2, 2, 0]
    _comprador_recibio(entorno)


@pg
async def test_D_varias_paginas_de_no_grant_y_el_candidato_del_corredor_se_inspecciona(monkeypatch, base, entorno):
    """Caso D. Páginas de NO_GRANT (correo sin grant) y después un lead con el hecho X2. La rama B está vacía con
    la semántica real (EG.6, aceptado): el doble de la intención de `entorno` es el MÍNIMO para que la elegibilidad
    acotada califique y el recorrido se pueda observar. Lo que se prueba es que el candidato se ALCANZA."""
    monkeypatch.setattr(cron, "_PAGINA", 2)
    no_grant = await _viejas(base, 5, "d-nogrant-", email=True)
    corredor = "d-corredor"
    await _dormida(base, corredor)
    await _pide_corredor(base, corredor)
    antes = await _huella(base, excluir=[corredor])
    res, _ = await _barrer(base)
    assert (corredor, ACTIVO) in entorno["intencion_activo"], "el candidato del corredor no se inspeccionó"
    assert res["corredores"] == 1 and await _marcas(base, corredor) != SIN_MARCA
    assert set(no_grant) <= set(entorno["intencion"]), "una fila NO_GRANT no se evaluó"
    assert await _huella(base, excluir=[corredor]) == antes


@pg
async def test_E_lo_descartado_no_recibe_ninguna_escritura(monkeypatch, base, entorno):
    """Caso E. Sin canal, NO_GRANT, una fila con handoff SIN la marca de la persona (histórica) y una con el hecho
    X2 y canal del corredor pero NO elegible (la población real de la rama del corredor hoy, EG.6): todo se lee,
    nada se escribe. Ni lead_actividad, ni consent_grant, ni handoff_sesion cambian (contenido ni xmin)."""
    monkeypatch.setattr(cron, "_PAGINA", 2)
    await _viejas(base, 3, "e-sin-canal-")
    await _viejas(base, 3, "e-nogrant-", dias=50, email=True)
    historica, no_elegible = "e-historica", "e-x2-no-elegible"
    for sid in (historica, no_elegible):
        await _dormida(base, sid)
    await _pide_corredor(base, historica, marca=False)
    await _pide_corredor(base, no_elegible)
    doble = chat.intencion_de_sesion

    async def intencion(sid, horas_inactividad=None, activo_id=None):
        r = await doble(sid, horas_inactividad=horas_inactividad, activo_id=activo_id)   # queda registrada
        return {} if (sid == no_elegible and activo_id) else r   # la semántica acotada a X no califica
    monkeypatch.setattr(chat, "intencion_de_sesion", intencion)
    async with base() as db:
        await chat.ensure_handoff_tables(db)
    antes = await _huella(base)
    res, espia = await _barrer(base)
    assert res.get("disparados", 0) == 0 and res.get("holdout", 0) == 0 and res["escaneados"] == 8
    assert entorno["email"] == [] and entorno["push"] == [] and entorno["holdout"] == []
    assert await _huella(base) == antes, "una fila descartada recibió una escritura"
    assert [len(p[2]) for p in espia.paginas] == [2, 2, 2, 2, 0]


@pg
async def test_F_presupuesto_tres_y_cien_filas_sin_efecto_delante(monkeypatch, base, entorno):
    """Caso F. Presupuesto 3; las primeras 100 filas leídas no producen efecto: los 3 compradores autorizados de
    después SÍ reciben. El presupuesto mide consecuencias, no filas leídas."""
    monkeypatch.setenv("REENGANCHE_CRON_LIMITE", "3")
    monkeypatch.setattr(cron, "_PAGINA", 20)
    await _viejas(base, 100, "f-vieja-")
    compradores = [(await _lead_con_grant(base))[0] for _ in range(3)]
    res, _ = await _barrer(base)
    assert res["comprador"] == 3
    for sid in compradores:
        assert (await _fila(base, sid))["reenganche_enviado_en"] is not None


@pg
async def test_F2_el_presupuesto_no_lo_gastan_no_grant_ni_corredores_no_elegibles(monkeypatch, base, entorno):
    """Caso F con lo descartado que SÍ llega a las puertas: 100 NO_GRANT (correo sin grant: la frontera responde
    NO_GRANT) y 5 con el hecho X2 y canal del corredor pero no elegibles (la rama del corredor hoy, EG.6). Con
    presupuesto 3, los 3 compradores autorizados de después reciben. Si lo descartado gastara presupuesto, la
    inanición volvería —ya no en la lectura, sino en los efectos—."""
    monkeypatch.setenv("REENGANCHE_CRON_LIMITE", "3")
    monkeypatch.setattr(cron, "_PAGINA", 20)
    no_grant = await _viejas(base, 100, "f2-nogrant-", email=True)
    no_elegibles = [f"f2-x2-{i}" for i in range(5)]
    for i, sid in enumerate(no_elegibles):
        await _dormida(base, sid)
        await _pide_corredor(base, sid)
        await _envejecer(base, sid, 40 - i)
    compradores = [(await _lead_con_grant(base))[0] for _ in range(3)]
    doble = chat.intencion_de_sesion

    async def intencion(sid, horas_inactividad=None, activo_id=None):
        r = await doble(sid, horas_inactividad=horas_inactividad, activo_id=activo_id)   # queda registrada
        return {} if (sid in no_elegibles and activo_id) else r   # la semántica acotada a X no califica
    monkeypatch.setattr(chat, "intencion_de_sesion", intencion)
    res, _ = await _barrer(base)
    assert set(no_grant) <= set(entorno["intencion"]), "las NO_GRANT no llegaron a la decisión"
    assert all((sid, ACTIVO) in entorno["intencion_activo"] for sid in no_elegibles)
    assert res["comprador"] == 3 and res.get("corredores", 0) == 0
    for sid in compradores:
        assert (await _fila(base, sid))["reenganche_enviado_en"] is not None


@pg
async def test_G_presupuesto_tres_y_cuatro_autorizados(monkeypatch, base, entorno):
    """Caso G. Presupuesto 3 y 4 compradores autorizados: solo los 3 primeros (más viejos) tienen consecuencia. El
    cuarto queda INTACTO —sin grant consumido ni marca— y lo atiende el barrido siguiente."""
    monkeypatch.setenv("REENGANCHE_CRON_LIMITE", "3")
    compradores = [(await _lead_con_grant(base))[0] for _ in range(4)]
    for i, sid in enumerate(compradores):
        await _envejecer(base, sid, 10 - i)          # orden estricto: el cuarto es el más nuevo
    res, _ = await _barrer(base)
    assert res["comprador"] == 3
    cuarto = compradores[3]
    assert await _marcas(base, cuarto) == SIN_MARCA and await _sin_uso(base, cuarto), \
        "con el presupuesto lleno se reservó o se marcó el cuarto"
    res2, _ = await _barrer(base)
    assert res2["comprador"] == 1 and (await _fila(base, cuarto))["reenganche_enviado_en"] is not None


@pg
async def test_H_el_holdout_consume_presupuesto_igual_que_tocado(monkeypatch, base, entorno):
    """Caso H. Presupuesto 2 y tres leads del corredor autorizados y elegibles (doble mínimo de la intención): el
    primero cae en holdout, el segundo en tocado y el tercero queda intacto."""
    monkeypatch.setenv("REENGANCHE_CRON_LIMITE", "2")
    sids = ["h-uno", "h-dos", "h-tres"]
    for i, sid in enumerate(sids):
        await _dormida(base, sid)
        await _pide_corredor(base, sid)
        await _envejecer(base, sid, 10 - i)

    def grupo(sid, pct):
        entorno["holdout"].append(sid)
        return "holdout" if sid == "h-uno" else "tocado"
    monkeypatch.setattr("app.lift.grupo_holdout", grupo)
    res, _ = await _barrer(base)
    assert res["holdout"] == 1 and res["disparados"] == 1
    assert (await _marcas(base, "h-uno"))[0] == "holdout" and (await _marcas(base, "h-dos"))[0] == "tocado"
    assert await _marcas(base, "h-tres") == SIN_MARCA, "el holdout no consumió presupuesto"


@pg
async def test_I_empates_de_ultima_actividad_en_el_borde_de_pagina(monkeypatch, base, entorno):
    """Caso I. Siete filas con la MISMA `ultima_actividad`, páginas de 3: el desempate por session_id hace que
    cada una se lea y se evalúe exactamente una vez (ni duplicados ni omisiones)."""
    monkeypatch.setattr(cron, "_PAGINA", 3)
    sids = await _viejas(base, 7, "i-empate-", email=True, mismo_instante=True)
    res, espia = await _barrer(base)
    leidas = [s for p in espia.paginas for s in p[2]]
    assert sorted(leidas) == sorted(sids) and len(leidas) == 7
    assert sorted(entorno["intencion"]) == sorted(sids), "una fila empatada se evaluó dos veces o ninguna"


@pg
async def test_J_el_cursor_avanza_por_la_ultima_fila_leida_aunque_se_descarte(monkeypatch, base, entorno):
    """Caso J. La última fila de la página 1 es una DESCARTADA SIN CANAL, precedida por dos con correo (NO_GRANT):
    la página siguiente empieza después de ELLA —la última leída, no la última con canal ni la última elegible—,
    no vuelve a aparecer, y el comprador del final se alcanza."""
    monkeypatch.setattr(cron, "_PAGINA", 3)
    con_correo = await _viejas(base, 2, "j-a-nogrant-", dias=60, email=True)
    sin_canal = await _viejas(base, 1, "j-b-sincanal-", dias=59)
    despues = await _viejas(base, 2, "j-c-nogrant-", dias=58, email=True)
    comprador, _ = await _lead_con_grant(base)
    res, espia = await _barrer(base)
    p1, p2 = espia.paginas[0][2], espia.paginas[1][2]
    assert p1 == con_correo + sin_canal and sin_canal[0] not in p2
    assert p2[0] == despues[0]
    evaluadas = [s for s in entorno["intencion"] if s in con_correo + despues]
    assert sorted(evaluadas) == sorted(con_correo + despues), "una fila se evaluó dos veces o ninguna"
    assert res["comprador"] == 1


@pg
async def test_K_un_solo_corte_temporal_para_todas_las_paginas(monkeypatch, base, entorno):
    """Caso K. Entre la página 2 y la 3 pasa el tiempo y la transacción termina (otra conexión del pooler, un
    rollback de una lectura): `now()` cambia. Una fila que NO estaba dormida al empezar (cruza las 48 h durante el
    barrido) no entra: el universo es el del corte capturado una vez, y TODAS las páginas siguientes usan ese
    mismo corte —el que devolvió la primera—.

    Margen: la fila tardía queda 20 s por encima del corte inicial y el gancho espera 25 s. Un falso rojo exigiría
    más de 20 s entre su INSERT y la primera página; un falso verde es imposible (25 > 20)."""
    monkeypatch.setattr(cron, "_PAGINA", 2)
    await _viejas(base, 5, "k-vieja-", email=True)
    tardia = "k-tardia"
    async with base() as db:
        await db.execute(text(
            "INSERT INTO lead_actividad (session_id, activo_id, ultima_actividad, lead_email) "
            "VALUES (:s, CAST(:a AS uuid), now() - interval '48 hours' + interval '20 seconds', 'k@ejemplo.invalid')"),
            {"s": tardia, "a": ACTIVO})
        await db.commit()

    async def entre_paginas(i, db):
        if i == 2:
            await db.commit()               # fin de la transacción: el próximo now() es otro
            await asyncio.sleep(25)         # la fila tardía ya cruzó las 48 h
    res, espia = await _barrer(base, entre_paginas)
    leidas = [s for p in espia.paginas for s in p[2]]
    assert len(espia.paginas) >= 3, "el universo no llegó a la 3.ª página: la prueba no mide nada"
    assert tardia not in leidas and tardia not in entorno["intencion"], "el universo avanzó durante el recorrido"
    siguientes = espia.paginas[1:]
    assert all("now()" not in sql and ":corte" in sql for sql, _, _ in siguientes)
    assert {str(params["corte"]) for _, params, _ in siguientes} == {str(espia.cortes[0])}, \
        "una página siguiente no usó el corte que devolvió la primera"


@pg
async def test_K2_una_fila_que_sale_del_universo_entre_paginas_no_provoca_omisiones(monkeypatch, base, entorno):
    """Una fila ya leída vuelve a tener actividad mientras se recorre (sale del universo dormido). Con keyset la
    página siguiente no se desplaza: ninguna fila posterior se omite (un OFFSET se saltaría una)."""
    monkeypatch.setattr(cron, "_PAGINA", 2)
    sids = await _viejas(base, 5, "k2-vieja-", email=True)

    async def entre_paginas(i, db):
        if i == 1:
            async with base() as otra:
                await otra.execute(text("UPDATE lead_actividad SET ultima_actividad = now() WHERE session_id = :s"),
                                   {"s": sids[0]})
                await otra.commit()
    res, espia = await _barrer(base, entre_paginas)
    leidas = [s for p in espia.paginas for s in p[2]]
    assert leidas == sids, leidas


@pg
async def test_L_cerrada_entre_la_lectura_y_la_marca_no_hay_efecto(monkeypatch, base, entorno):
    """Caso L. El candidato del corredor de la página 2 cierra («no quiero más seguimiento») mientras se evalúa: la
    re-comprobación de la marca lo descarta; ni grupo, ni envío, ni aviso."""
    monkeypatch.setattr(cron, "_PAGINA", 2)
    await _viejas(base, 2, "l-vieja-")
    cand = "l-corredor"
    await _dormida(base, cand)
    await _pide_corredor(base, cand)
    doble = chat.intencion_de_sesion

    async def intencion(sid, horas_inactividad=None, activo_id=None):
        if sid == cand and activo_id:
            async with base() as otra:
                await otra.execute(text("UPDATE lead_actividad SET reenganche_cerrado_en = now() "
                                        "WHERE session_id = :s"), {"s": cand})
                await otra.commit()
        return await doble(sid, horas_inactividad=horas_inactividad, activo_id=activo_id)
    monkeypatch.setattr(chat, "intencion_de_sesion", intencion)
    res, _ = await _barrer(base)
    assert res.get("corredores", 0) == 0 and [e for e in entorno["email"] if e["to"] == CORREDOR] == []
    f = await _fila(base, cand)
    assert f["reenganche_cerrado_en"] is not None and f["reenganche_grupo"] is None
    assert f["reenganche_enviado_en"] is None


@pg
async def test_M_un_fallo_de_pagina_aborta_sin_reservas_ni_efectos(monkeypatch, base, entorno, caplog):
    """Caso M. La página 2 falla (fallo de SISTEMA): el barrido entero se aborta antes de reservar nada, aunque en
    la página 1 haya un comprador autorizado. 0 grants consumidos, 0 marcas, 0 avisos. El barrido siguiente lo
    atiende."""
    monkeypatch.setattr(cron, "_PAGINA", 2)
    comprador, _ = await _lead_con_grant(base)
    await _envejecer(base, comprador, 90)                   # el más viejo: página 1
    await _viejas(base, 3, "m-vieja-")

    async def rompe(i, db):
        if i == 1:
            raise RuntimeError("la base se cayó a mitad del recorrido")
    with caplog.at_level(logging.ERROR):
        res, _ = await _barrer(base, rompe)
    assert res == {"escaneados": 0, "disparados": 0, "corredores": 0}
    assert await _sin_uso(base, comprador) and await _marcas(base, comprador) == SIN_MARCA
    assert entorno["email"] == [] and entorno["push"] == []
    assert "recorrido abortado" in caplog.text
    res2, _ = await _barrer(base)
    assert res2["comprador"] == 1


@pg
async def test_N_una_sola_pagina_se_comporta_como_antes(base, entorno):
    """Caso N. Un universo que cabe en una página: UNA consulta de página y el mismo resultado de siempre."""
    await _viejas(base, 2, "n-vieja-")
    comprador, _ = await _lead_con_grant(base)
    res, espia = await _barrer(base)
    assert len(espia.paginas) == 1 and res["comprador"] == 1 and res["escaneados"] == 3


@pg
async def test_O_con_la_bandera_apagada_ni_una_lectura(monkeypatch, base, entorno):
    """Caso O. REENGANCHE_CRON_ENABLED=0: ni lecturas, ni escrituras, ni efectos, aunque haya varias páginas."""
    monkeypatch.setattr(cron, "_PAGINA", 1)
    await _viejas(base, 3, "o-vieja-")
    comprador, _ = await _lead_con_grant(base)
    antes = await _huella(base)
    monkeypatch.setenv("REENGANCHE_CRON_ENABLED", "0")
    res, espia = await _barrer(base)
    assert res.get("deshabilitado") is True and espia.sentencias == 0 and espia.paginas == []
    assert await _huella(base) == antes and entorno["email"] == [] and entorno["push"] == []


@pg
async def test_P_un_error_de_autoridad_no_bloquea_ni_gasta_presupuesto(monkeypatch, base, entorno):
    """Lo esperado (no elegible, ERROR de UNA decisión) no se comporta como un fallo de sistema: el lead con ERROR
    queda intacto y SIN gastar presupuesto (1), y el comprador siguiente igual recibe en el mismo barrido."""
    import app.autoridad_reenganche as autoridad
    monkeypatch.setenv("REENGANCHE_CRON_LIMITE", "1")
    con_error, _ = await _lead_con_grant(base)
    sano, _ = await _lead_con_grant(base)
    await _envejecer(base, con_error, 10)
    await _envejecer(base, sano, 9)
    real = autoridad.autorizar_efecto_reenganche

    async def decide(db, *, session_id, **k):
        if session_id == con_error:
            return autoridad.DecisionReenganche(autoridad.EstadoAutorizacion.ERROR)
        return await real(db, session_id=session_id, **k)
    monkeypatch.setattr(autoridad, "autorizar_efecto_reenganche", decide)
    res, _ = await _barrer(base)
    assert res["comprador"] == 1 and (await _fila(base, sano))["reenganche_enviado_en"] is not None
    assert await _marcas(base, con_error) == SIN_MARCA and await _sin_uso(base, con_error)


# ══ A · sin base ═══════════════════════════════════════════════════════════════════════════

async def test_A1_el_cursor_que_no_avanza_aborta_y_no_cuelga(monkeypatch, entorno, caplog):
    """Guarda de AVANCE. Un doble que ignora el cursor devuelve la MISMA página llena una y otra vez: el barrido
    aborta (sin reservas, marcas ni avisos) en lugar de girar para siempre o evaluar dos veces el mismo lead.

    El doble CEDE el control en cada sentencia (`asyncio.sleep(0)`): sin eso, un bucle sin la guarda nunca
    llegaría a un punto de cancelación y `wait_for` no podría cortarlo (la prueba colgaría en vez de fallar)."""
    monkeypatch.setattr(cron, "_PAGINA", 2)
    from datetime import datetime, timedelta, timezone
    corte = datetime.now(timezone.utc) - timedelta(hours=48)

    class _Cede(BaseEspia):
        async def execute(self, stmt, params=None):
            await asyncio.sleep(0)
            return await super().execute(stmt, params)
    db = _Cede([{**_dormido(s, consentido=True), "corte": corte} for s in ("a1-1", "a1-2")])
    with caplog.at_level(logging.ERROR):
        res = await asyncio.wait_for(cron.escanear_reenganches(db), 10)
    assert res == {"escaneados": 0, "disparados": 0, "corredores": 0}
    assert not any("UPDATE" in s.upper() for s, _ in db.sentencias)
    assert entorno["email"] == [] and entorno["push"] == []
    assert "recorrido abortado" in caplog.text


def test_A2_el_recorrido_es_keyset_en_sql_sin_offset_ni_tope_de_filas():
    fuente = inspect.getsource(cron._escanear_reenganches)
    cadenas = [n.value for n in ast.walk(ast.parse(textwrap.dedent(fuente)))
               if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    assert not any("OFFSET" in c.upper() for c in cadenas), "el recorrido volvió a paginar con OFFSET"
    assert "ORDER BY ultima_actividad ASC, session_id ASC LIMIT :pagina" in fuente
    assert "(ultima_actividad, session_id) > (CAST(:ua AS timestamptz), CAST(:sid AS text))" in fuente
    assert '"pagina": _PAGINA' in fuente
    assert "LIMIT :lim" not in fuente and '"lim": _limite()' not in fuente, \
        "el límite de consecuencias volvió a usarse como tope de lectura"


def test_A3_la_pagina_y_el_presupuesto_son_cosas_distintas(monkeypatch):
    monkeypatch.delenv("REENGANCHE_CRON_LIMITE", raising=False)
    assert cron._PAGINA == 200 and cron._limite() == 200
    monkeypatch.setenv("REENGANCHE_CRON_LIMITE", "3")
    assert cron._limite() == 3 and cron._PAGINA == 200
    assert "PRESUPUESTO" in cron.__doc__ and "consecuencia" in (cron._limite.__doc__ or "").lower()
