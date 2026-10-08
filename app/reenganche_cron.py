"""
Cron de Reenganche (Fase 2) — vive DENTRO de la app (tarea de fondo), no en un
servicio aparte ni en WhatsApp. Cada cierto tiempo barre los leads dormidos y,
cuando el motor (app/reenganche) dispara por VALOR, avisa por los canales que la
app YA tiene (Web Push + email/Resend) a UNA audiencia AUTORIZADA, o a ninguna:

  · al COMPRADOR, si dejó canal y un grant vivo para ese canal (Fase 3, TR-5);
  · al CORREDOR del inmueble exacto, solo si la persona le PIDIÓ contacto para ese
    inmueble (SEC-X2-EGRESS-R0) — humano en el lazo.

Sin ninguna de las dos autoridades, silencio: que el comprador no tenga grant no
autoriza a avisar al corredor, y llegar por un QR tampoco. HOY la rama del corredor no
produce efectos: el mismo hecho que la autoriza vuelve «caliente» al lead y el motor calla
(ver _escanear_reenganches y tests/test_sec_x2_egress_r0.py::test_R1).

Config por entorno (todas opcionales, con defaults sensatos):
  REENGANCHE_CRON_ENABLED   "1"/"0"     habilita el barrido (default "1"). Se consulta al arrancar
                                        el bucle Y en cada barrido: apagarla detiene todo efecto.
  REENGANCHE_CRON_INTERVAL  segundos entre barridos (default 21600 = 6 h, mínimo 300)
  REENGANCHE_CRON_LIMITE    PRESUPUESTO de resultados con consecuencia por barrido (default 200):
                            avisos autorizados al comprador + asignaciones tocado/holdout del
                            corredor. Desde SEC-X2-SCAN-FAIRNESS-R0 NO limita las filas que se leen:
                            el barrido recorre TODO el universo dormido por páginas (keyset). Antes
                            era el LIMIT de una única página: las filas descartadas (sin autoridad,
                            sin canal, no elegibles), que no reciben marca, ocupaban la cabeza del
                            orden en cada barrido y podían dejar sin leer para siempre a las demás.
  REENGANCHE_BAJA_SECRET    secreto DEDICADO del enlace de baja (≥ 32 caracteres; ver
                            app/baja_aviso.py). Sin él no sale NINGÚN aviso al comprador
                            (Plan 1.1 · TR-2, fail-closed); el aviso al corredor no depende de él.

Asume una sola instancia web (plan starter de Render, no duerme). Si algún día se escala, un
doble barrido sigue siendo inocuo por dos guardas: el consumo `once` de cada grant del comprador
(TR-5) y las marcas, que vuelven a comprobar la fila (cierre, grupo, envío) antes de confirmar
cualquier efecto.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import text

log = logging.getLogger(__name__)


def _intervalo() -> int:
    try:
        return max(300, int(os.getenv("REENGANCHE_CRON_INTERVAL", "21600")))
    except ValueError:
        return 21600


# Filas por página del recorrido. Es un detalle de la base, NO el presupuesto de efectos (`_limite`).
_PAGINA = 200


def _limite() -> int:
    """Presupuesto de resultados con CONSECUENCIA por barrido (SEC-X2-SCAN-FAIRNESS-R0): cada aviso
    autorizado al comprador, cada asignación 'tocado' y cada 'holdout' del corredor consume una unidad.
    Lo descartado (NO_GRANT, sin autoridad, sin canal, no elegible, ERROR) no consume. No limita las
    filas leídas: el trabajo de lectura puede crecer; los efectos, no.

    Cuenta consecuencias PREVISTAS (antes de las marcas): si una marca se descarta al re-comprobar la fila
    (cierre o barrido concurrente), su unidad se gasta sin efecto —nunca se excede el tope—. Es un tope
    POR BARRIDO y por proceso, no global: con una sola instancia (lo que asume este módulo) coincide con
    el tope por ciclo; con varias instancias barriendo a la vez, cada una tendría el suyo."""
    try:
        return max(1, int(os.getenv("REENGANCHE_CRON_LIMITE", "200")))
    except ValueError:
        return 200


def _holdout_pct() -> int:
    """% de dormidos elegibles que se RETIENE como control (no se les manda el touch automático),
    el contrafactual de la métrica de lift. Default 20 (aprobado para el piloto). 0 = desactivado.
    Desde SEC-X2-EGRESS-R0 se aplica SOLO a la población que el corredor está autorizado a recibir
    (el comprador no entra al experimento), y hoy esa población está vacía (test_R1): el experimento
    no suma filas nuevas. Ver docs/DISENO_Metrica_Lift_Intencion.md §3."""
    try:
        return min(100, max(0, int(os.getenv("REENGANCHE_HOLDOUT_PCT", "20"))))
    except ValueError:
        return 20


def habilitado() -> bool:
    return os.getenv("REENGANCHE_CRON_ENABLED", "1").strip().lower() not in ("0", "false", "no", "")


def auto_lead() -> bool:
    """Fase 3: si True, cuando el comprador dejó canal + consentimiento el reenganche le
    llega a ÉL directo (email/push). Si no, el comprador no recibe nada y el corredor solo
    recibe con su propia autoridad (SEC-X2-EGRESS-R0). Default True."""
    return os.getenv("REENGANCHE_AUTO_LEAD", "1").strip().lower() not in ("0", "false", "no", "")


def _horas_inactividad(ua: datetime | None) -> float | None:
    if ua is None:
        return None
    if ua.tzinfo is None:
        ua = ua.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - ua).total_seconds() / 3600.0)


_scan_lock = asyncio.Lock()


_APAGADO = {"escaneados": 0, "disparados": 0, "corredores": 0, "deshabilitado": True}


async def escanear_reenganches(db) -> dict:
    """ÚNICA entrada al barrido. Con REENGANCHE_CRON_ENABLED apagada no hace NADA: ni lee
    leads, ni escribe lead_actividad, ni calcula destinatarios, ni manda correo o push.

    La bandera se comprueba aquí y no solo en iniciar_cron (Plan 1.1 · TR-4): el control del
    arranque evita crear el bucle, pero no protege a un caller que ya existe ni a una bandera
    que cambió después del arranque. Se vuelve a mirar tras el candado porque quien esperaba
    turno pudo entrar con la bandera ya apagada.

    El candado serializa el barrido en esta instancia: dos barridos simultáneos no avisan dos
    veces (el segundo re-lee lo ya marcado). Ver _escanear_reenganches para la lógica."""
    if not habilitado():
        log.info("Reenganche: barrido omitido (REENGANCHE_CRON_ENABLED=0).")
        return dict(_APAGADO)
    async with _scan_lock:
        if not habilitado():
            return dict(_APAGADO)
        return await _escanear_reenganches(db)


async def _escanear_reenganches(db) -> dict:
    """Un barrido: detecta leads dormidos con disparo por valor y produce, como mucho, UN efecto
    por lead y solo hacia una audiencia AUTORIZADA (SEC-X2-EGRESS-R0):

      A · el COMPRADOR (PRINCIPAL_SELF), con su grant por canal (TR-5: autorizar_efecto_reenganche);
      B · el CORREDOR del inmueble EXACTO del lead, con el hecho X2 (corredor_autorizado) y una
          elegibilidad calculada SOLO con lo que tiene alcance a ese inmueble
          (intencion_de_sesion(…, activo_id=X), la frontera R0c; sin respaldo de sesión entera).

    Sin audiencia autorizada → SILENCIO: ni aviso, ni grupo, ni elegible_en, ni enviado_en. El
    NO_GRANT del comprador ya no deriva al corredor (DR-15 retirado): no es autoridad para nadie.

    El experimento tocado-vs-holdout (`reenganche_grupo`, `reenganche_elegible_en`) alimenta la
    métrica de lift que ve el corredor (`/metricas/lift`), así que es SOLO de la rama B: un efecto al
    comprador deja únicamente la marca de envío (dosis única; el CRM la lee como anti-repetición de
    su sugerencia), nunca grupo ni elegibilidad. ASIGNAR AL EXPERIMENTO ES UN CAMBIO DE ESTADO CON
    CONSECUENCIAS: exige la misma población autorizada que el aviso.

    HOY la rama B no produce población: el mismo hecho X2 que autoriza al corredor es la señal
    «pidió corredor» del motor → nivel caliente → `evaluar_reenganche` calla (tests/
    test_sec_x2_egress_r0.py::test_R1). El corredor no recibe avisos automáticos y el experimento
    no suma filas hasta que una unidad propia rediseñe esa elegibilidad.

    Idempotente vía la marca de envío y el grupo (anti-repetición). Devuelve un resumen
    {escaneados, disparados, holdout, comprador, corredores}.

    NO llamar directo: no mira la bandera. La única entrada es escanear_reenganches
    (tests/test_tr4_reenganche.py lo impone sobre todo el código de producción)."""
    from app.reenganche import evaluar_reenganche, HORAS_DORMIDO
    from app.routers.chat import intencion_de_sesion, _corredor_de_activo, ensure_lead_actividad
    from app import notifications as notificaciones
    from app.notifications import send_notification
    from app.lift import grupo_holdout
    from app import baja_aviso
    from app.autoridad_reenganche import (
        EstadoAutorizacion, autorizar_efecto_reenganche, corredor_autorizado)

    pct = _holdout_pct()
    presupuesto = _limite()
    await ensure_lead_actividad(db)
    # UNA dosis automática por lead de por vida: se escanea hasta que produce un efecto; luego queda
    # con la marca de envío (comprador o corredor tocado) o en 'holdout' (control del corredor) y no
    # vuelve a entrar. Alinea con "aportar valor sin presionar": el cron no pinguea en bucle.
    #
    # SEC-X2-SCAN-FAIRNESS-R0 · RECORRIDO JUSTO SIN MUTAR LO DESCARTADO. Una fila descartada (sin
    # autoridad, sin canal, no elegible) NO recibe ninguna marca —la ausencia de permiso no se convierte
    # en estado—, así que sigue en el universo dormido. Antes se leía UNA página (LIMIT): esas filas
    # ocupaban la cabeza del orden en cada barrido y las posteriores no se leían jamás. Ahora se recorre
    # TODO el universo por páginas keyset, con el orden y el comparador en SQL:
    #   · orden total (ultima_actividad, session_id): session_id es la PK y rompe los empates;
    #   · la página siguiente empieza estrictamente DESPUÉS de la ÚLTIMA FILA LEÍDA (nunca de la última
    #     elegible, autorizada o con efecto): lo descartado no frena el avance; sin OFFSET;
    #   · un corte temporal FIJO, tomado UNA vez de la hora de la base en la primera página: el universo
    #     no avanza mientras se recorre (una fila que vuelve a tener actividad sale sola: `now()` > corte).
    # Solo LECTURAS: todas las páginas y todas las lecturas por lead van antes de la primera reserva.
    _CANDIDATAS = (
        "SELECT session_id, activo_id::text AS activo_id, ultima_actividad, "
        "       lead_email, lead_push, {corte} AS corte "
        "FROM lead_actividad "
        "WHERE ultima_actividad < {corte} "
        "  AND reenganche_enviado_en IS NULL "   # nunca tocado
        "  AND reenganche_grupo IS NULL "        # ni asignado a un grupo (tocado/holdout)
        # Plan 1.1 · TR-2: un CIERRE explícito saca la fila del barrido COMPLETO, antes del
        # holdout, del scoring, de la marca de grupo y de cualquier aviso (comprador o corredor).
        "  AND reenganche_cerrado_en IS NULL "
        "{despues_de}"
        "ORDER BY ultima_actividad ASC, session_id ASC LIMIT :pagina"
    )
    primera = _CANDIDATAS.format(corte="(now() - make_interval(hours => :dorm))", despues_de="")
    siguiente = _CANDIDATAS.format(
        corte="CAST(:corte AS timestamptz)",
        despues_de="  AND (ultima_actividad, session_id) > (CAST(:ua AS timestamptz), CAST(:sid AS text)) ")
    filas: list = []
    vistas: set = set()
    corte = cursor = None
    paginas = 0
    try:
        while True:
            if cursor is None:
                pagina = (await db.execute(
                    text(primera), {"dorm": HORAS_DORMIDO, "pagina": _PAGINA})).mappings().all()
            else:
                pagina = (await db.execute(
                    text(siguiente),
                    {"corte": corte, "ua": cursor[0], "sid": cursor[1], "pagina": _PAGINA},
                )).mappings().all()
            paginas += 1
            if not pagina:
                break
            # Guarda de AVANCE (solo igualdad, ningún orden en Python): una página que repite una fila ya
            # leída significa que el cursor no avanzó. Se aborta antes de reservar nada: ni bucle infinito
            # ni un lead evaluado dos veces. No da falsos positivos porque el único escritor de
            # `ultima_actividad` la lleva a `now()`, por encima del corte (routers/chat.py): una fila ya leída
            # no puede reaparecer más adelante en el orden dentro del universo congelado.
            nuevas = [r["session_id"] for r in pagina]
            if len(set(nuevas)) != len(nuevas) or not vistas.isdisjoint(nuevas):
                raise RuntimeError("el cursor del recorrido no avanzó")
            vistas.update(nuevas)
            filas.extend(pagina)
            if len(pagina) < _PAGINA:
                break  # universo agotado
            if corte is None:
                corte = pagina[0].get("corte")
                if corte is None:
                    raise RuntimeError("la primera página no trajo el corte temporal")
            ultima = pagina[-1]   # la ÚLTIMA FILA LEÍDA, se evalúe como se evalúe
            cursor = (ultima["ultima_actividad"], ultima["session_id"])
    except Exception as exc:  # noqa: BLE001 — tabla aún no creada / fallo de la base / cursor
        # Fallo de SISTEMA, no no-elegibilidad: se aborta el barrido completo. Aún no hay reservas ni
        # marcas, así que el rollback no deshace ningún permiso; 0 efectos y el siguiente barrido reintenta.
        await db.rollback()
        if paginas:
            log.error("Reenganche cron: recorrido abortado tras %d página(s) leída(s) (%s) — sin efectos.",
                      paginas, type(exc).__name__)
        return {"escaneados": 0, "disparados": 0, "corredores": 0}

    if not filas:
        return {"escaneados": 0, "disparados": 0, "corredores": 0}

    # Cache por-activo: direccion, novedad verificada, corredor (email/push).
    cache: dict[str, dict] = {}

    async def _info_activo(activo_id: str) -> dict:
        if activo_id in cache:
            return cache[activo_id]
        info = {"direccion": None, "novedades": [], "email": None, "sub": None, "corredor_id": None}
        try:
            row = (await db.execute(
                text("SELECT a.direccion_estandarizada AS dir, a.walk_score_fuente AS f, "
                     "COALESCE(a.owner_user_id, ag.owner_user)::text AS corredor_id "
                     "FROM activos_inmutables a "
                     "LEFT JOIN agencies ag ON ag.id = a.owner_agency_id "
                     "WHERE a.id = :id"),
                {"id": activo_id},
            )).mappings().first()
            if row:
                info["direccion"] = row["dir"]
                info["corredor_id"] = row["corredor_id"]
                if row["f"] == "osm":
                    info["novedades"] = [{
                        "tipo": "entorno",
                        "etiqueta": "la caminabilidad del entorno medida con comercios reales (no una estimación)",
                    }]
        except Exception:  # noqa: BLE001
            await db.rollback()
        try:
            info["email"], info["sub"] = await _corredor_de_activo(db, activo_id)
        except Exception:  # noqa: BLE001
            await db.rollback()
        cache[activo_id] = info
        return info

    # §7 · PRERREQUISITOS DE ENTREGA. Un canal cuya credencial falta en el servidor no entrega:
    # `_send_email` / `_send_push` lo omiten en silencio, y para entonces el grant ya estaría consumido
    # y el lead marcado. Se decide ANTES de reservar o de enrolar, con el mismo predicado que usan los
    # envíos: sin canal entregable no hay marca, ni grant consumido, ni efecto.
    entrega = {"EMAIL": bool(notificaciones.RESEND_API_KEY), "PUSH": bool(notificaciones.VAPID_PRIVATE_KEY)}

    # 1 · LECTURAS, todas ANTES de reservar ningún grant: ficha, decisión del comprador, hecho X2 y
    # elegibilidad acotada del corredor. Después de la primera reserva solo quedan otras reservas y las
    # marcas: ninguna E/S externa sostiene los bloqueos, y ningún rollback de una lectura (ficha, hecho
    # X2) puede deshacer un permiso ya consumido.
    leads: list[dict] = []
    for f in filas:
        sid = f["session_id"]
        activo_id = f["activo_id"]
        horas = _horas_inactividad(f["ultima_actividad"])
        info = await _info_activo(activo_id)
        canales = (["EMAIL"] if f["lead_email"] else []) + (["PUSH"] if f["lead_push"] else [])
        # A · comprador: misma semántica que antes (sesión entera). Este barrido NO adjudica si la
        # personalización al PROPIO comprador debe acotarse al inmueble: no es divulgación a terceros.
        decision, sin_decision = None, False
        if auto_lead() and canales:
            try:
                intenc = await intencion_de_sesion(sid, horas_inactividad=horas)
            except Exception:  # noqa: BLE001
                # Como un ERROR de autoridad: sin saber si el comprador (que tiene prioridad) recibiría,
                # este barrido no produce nada para ese lead. Sin marca, vuelve al siguiente.
                intenc, sin_decision = {}, True
            if intenc.get("turnos"):  # solo escaneó / sin mensajes → no es un lead real
                decision = evaluar_reenganche(
                    intencion=intenc, horas_inactividad=horas,
                    direccion=info["direccion"], novedades=info["novedades"],
                )
        # B · corredor del inmueble EXACTO. Orden: hecho X2 → canal → elegibilidad acotada. La semántica
        # acotada no se calcula siquiera para quien el corredor no está autorizado a recibir.
        autorizado = await corredor_autorizado(db, session_id=sid, activo_id=activo_id)
        entregable_corredor = bool((info["email"] and entrega["EMAIL"]) or (info["sub"] and entrega["PUSH"]))
        elegible_x = False
        if autorizado and entregable_corredor:
            try:
                intenc_x = await intencion_de_sesion(sid, horas_inactividad=horas, activo_id=activo_id)
            except Exception:  # noqa: BLE001
                intenc_x = {}
            # Lo hablado de otro inmueble, o el AgentState sin procedencia, no vuelve elegible a X. Sin
            # respaldo a la sesión entera: si la semántica acotada no califica, silencio.
            elegible_x = bool(intenc_x.get("turnos") and evaluar_reenganche(
                intencion=intenc_x, horas_inactividad=horas,
                direccion=info["direccion"], novedades=info["novedades"],
            ))
        leads.append({"sid": sid, "activo_id": activo_id, "f": f, "info": info, "canales": canales,
                      "decision": decision, "sin_decision": sin_decision,
                      "corredor_autorizado": autorizado, "entregable_corredor": entregable_corredor,
                      "elegible_x": elegible_x})

    # 2 · DECISIÓN por lead: una audiencia autorizada o ninguna. Con reserva, la frontera TR-5 marca
    # `used_at` en la MISMA transacción que la marca de envío de abajo: un solo COMMIT para permiso
    # consumido + lead marcado, y sólo después el envío.
    a_comprador: list[dict] = []
    ids_comprador: list[str] = []
    tocados: list[str] = []
    holdouts: list[str] = []
    destino: dict[str, dict] = {}   # sid tocado → su inmueble y la ficha (corredor y canales)
    # SEC-X2-SCAN-FAIRNESS-R0 · PRESUPUESTO de resultados con consecuencia (`_limite()`): aviso autorizado
    # al comprador, 'tocado' y 'holdout' del corredor consumen una unidad cada uno; lo descartado, no. Se
    # recorre en el orden del cursor (de la más vieja a la más nueva). Lleno el presupuesto, NINGUNA
    # reserva, grupo ni marca más: los leads siguientes quedan intactos para el próximo barrido.
    consecuencias = 0
    for c in leads:
        if consecuencias >= presupuesto:
            break
        sid, f, info, activo_id = c["sid"], c["f"], c["info"], c["activo_id"]
        if c["sin_decision"]:
            log.error("Reenganche cron: no se pudo decidir el aviso al comprador — lead omitido.")
            continue
        if c["decision"]:
            # Plan 1.1 · TR-2: cada aviso al comprador lleva su enlace de baja. Sin
            # REENGANCHE_BAJA_SECRET no se puede emitir: entonces se consulta la frontera SIN
            # reservar (no se gasta el permiso) y, si lo había, el lead queda intacto — ni
            # comprador, ni corredor, ni marca — hasta que el secreto exista. Lo mismo si falta la
            # credencial de CUALQUIERA de sus canales (§7): no se reserva lo que no se puede entregar.
            try:
                baja = baja_aviso.emitir(sid)
            except baja_aviso.SinSecretoDeBaja:
                baja = None
            reservar = baja is not None and all(entrega[ch] for ch in c["canales"])
            veredicto = await autorizar_efecto_reenganche(
                db, session_id=sid, canales_candidatos=c["canales"], reservar=reservar)
            if veredicto.estado is EstadoAutorizacion.ERROR:
                # Sin decisión no hay efecto ni marca, para NINGUNA audiencia: un fallo de autoridad
                # no se esconde detrás del camino del corredor. Sin marca, vuelve al próximo barrido.
                # Sin rollback aquí: deshacer tiraría las reservas de otros leads de este barrido.
                log.error("Reenganche cron: autoridad en ERROR — lead omitido.")
                continue
            if veredicto.estado is EstadoAutorizacion.AUTHORIZED:
                if not reservar:
                    log.error("Reenganche cron: sin secreto de baja o sin credencial de canal — "
                              "aviso al comprador omitido.")
                    continue
                ids_comprador.append(sid)
                consecuencias += 1
                a_comprador.append({
                    "email": f["lead_email"] if "EMAIL" in veredicto.canales else None,
                    "push": f["lead_push"] if "PUSH" in veredicto.canales else None,
                    "mensaje": c["decision"]["mensaje"],
                    "activo_id": activo_id, "baja": baja,
                })
                # UNA audiencia por lead: el comprador tiene prioridad. Su efecto no avisa al corredor
                # (un grant del comprador no lo autoriza) ni entra a su experimento.
                continue
            # NO_GRANT → ningún efecto al comprador. Y NO es autoridad para el corredor: la rama B se
            # evalúa abajo por su cuenta, exactamente igual que para un lead sin canal propio.

        # B · corredor del inmueble EXACTO: hecho X2 → canal → elegibilidad acotada (fase 1) → grupo.
        # Nada de lo que sigue (ni el holdout) ocurre para un lead sin el hecho X2.
        if not c["corredor_autorizado"]:
            continue  # ni el QR, ni la atribución, ni el NO_GRANT del comprador: silencio
        if not c["entregable_corredor"]:
            continue  # sin canal ENTREGABLE no hay tratamiento posible → tampoco un control válido
        if not c["elegible_x"]:
            continue  # la semántica acotada a X no califica: silencio, sin respaldo de sesión entera
        # Holdout (contrafactual de la métrica de lift): un % de la población AUTORIZADA y elegible del
        # corredor no recibe el touch automático y queda como control desde su momento de elegibilidad.
        # Control y tratamiento son la MISMA audiencia y la misma clase de tratamiento. El corredor
        # humano igual puede retomarlos a mano desde el CRM. Ver docs/DISENO_Metrica_Lift_Intencion.md §3.
        if grupo_holdout(sid, pct) == "holdout":
            holdouts.append(sid)
            consecuencias += 1
            continue
        tocados.append(sid)
        consecuencias += 1
        destino[sid] = {"info": info, "activo_id": activo_id}

    log.info("Reenganche cron · recorrido: %d páginas, %d filas leídas, %d consecuencias previstas "
             "(presupuesto %d%s).", paginas, len(filas), consecuencias, presupuesto,
             ", lleno: los leads siguientes quedan intactos para el próximo barrido"
             if consecuencias >= presupuesto else "")
    if not ids_comprador and not tocados and not holdouts:
        return {"escaneados": len(filas), "disparados": 0, "holdout": 0, "comprador": 0, "corredores": 0}

    # 3 · MARCAS, todas en UN commit y ANTES de notificar: si un envío falla, no se reintenta en bucle
    # (mejor perder un aviso que spammear). El COMMIT confirma a la vez los permisos consumidos (TR-5);
    # si falla, se deshace todo y no sale nada.
    # TODAS las marcas vuelven a comprobar el estado de la fila (un cierre o un barrido concurrente
    # durante este) y los avisos salen SOLO para lo que de verdad quedó marcado.
    _sigue_abierta = ("AND reenganche_cerrado_en IS NULL AND reenganche_grupo IS NULL "
                      "AND reenganche_enviado_en IS NULL RETURNING session_id")
    pedidos = len(holdouts) + len(tocados)
    try:
        if ids_comprador:
            # Comprador: SOLO la marca de envío (anti-repetición). Sin grupo ni elegible_en: un efecto
            # PRINCIPAL_SELF no es una observación del experimento del corredor.
            marcados = [r["session_id"] for r in (await db.execute(
                text("UPDATE lead_actividad SET reenganche_enviado_en = now() "
                     "WHERE session_id = ANY(:ids) " + _sigue_abierta),
                {"ids": ids_comprador},
            )).mappings().all()]
            if set(marcados) != set(ids_comprador):
                # Otra escritura cambió una fila del comprador después de leerla. Sus grants ya están
                # reservados en ESTA transacción y no se puede descartar solo ese lead: se deshace TODO
                # (los grants vuelven) y no sale nada. El barrido siguiente decide con la fila actual.
                raise RuntimeError("marca del comprador desfasada")
        if holdouts:
            # Control del corredor: grupo + momento de elegibilidad, SIN envío. elegible_en se fija una
            # sola vez (COALESCE) para anclar la primera elegibilidad. No re-entra (el SELECT lo excluye).
            holdouts = [r["session_id"] for r in (await db.execute(
                text("UPDATE lead_actividad SET reenganche_grupo = 'holdout', "
                     "reenganche_elegible_en = COALESCE(reenganche_elegible_en, now()) "
                     "WHERE session_id = ANY(:ids) " + _sigue_abierta),
                {"ids": holdouts},
            )).mappings().all()]
        if tocados:
            tocados = [r["session_id"] for r in (await db.execute(
                text("UPDATE lead_actividad SET reenganche_enviado_en = now(), reenganche_grupo = 'tocado', "
                     "reenganche_elegible_en = COALESCE(reenganche_elegible_en, now()) "
                     "WHERE session_id = ANY(:ids) " + _sigue_abierta),
                {"ids": tocados},
            )).mappings().all()]
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        log.error("Reenganche cron: las marcas no se confirmaron (%s) — no sale ningún aviso.",
                  type(exc).__name__)
        return {"escaneados": len(filas), "disparados": 0, "holdout": 0, "comprador": 0, "corredores": 0}
    disparados = len(ids_comprador) + len(tocados)
    if len(holdouts) + len(tocados) < pedidos:
        log.warning("Reenganche cron: %d marcas del corredor descartadas (cierre o barrido concurrente).",
                    pedidos - len(holdouts) - len(tocados))

    # Agrupa por corredor (id del dueño; email/activo solo como respaldo) para un único aviso. N cuenta
    # SOLO leads que pasaron uno a uno la autoridad, la elegibilidad acotada y el grupo tocado, y que
    # quedaron marcados.
    por_corredor: dict[str, dict] = {}
    for sid in tocados:
        info = destino[sid]["info"]
        clave = info["corredor_id"] or info["email"] or f"activo:{destino[sid]['activo_id']}"
        grupo = por_corredor.setdefault(clave, {"email": info["email"], "sub": info["sub"], "n": 0})
        grupo["n"] += 1

    # Fase 3: al COMPRADOR directo, SÓLO por los canales que la frontera autorizó (un grant de
    # EMAIL no abre el PUSH ni al revés) → el mensaje de valor con deep-link al inmueble.
    enviados_comprador = 0
    for c in a_comprador:
        if not c["email"] and not c["push"]:
            continue
        try:
            await send_notification(
                email=c["email"], push_subscription=c["push"],
                title="Novedad sobre el inmueble que viste",
                body=c["mensaje"],
                # El toque (push) y el botón (correo) abren el inmueble con la confirmación de
                # baja a mano; el correo lleva además el enlace explícito al pie.
                url=f"/a/{c['activo_id']}?baja={c['baja']}",
                baja_url=f"/?baja={c['baja']}",
                email_subject="Contexto · una novedad verificada para ti",
            )
            enviados_comprador += 1
        except Exception as exc:  # noqa: BLE001
            log.error("Reenganche cron: fallo avisando al comprador: %s", exc)

    notificados = 0
    for grupo in por_corredor.values():
        n = grupo["n"]
        plural = "s" if n != 1 else ""
        try:
            await send_notification(
                email=grupo["email"], push_subscription=grupo["sub"],
                title="Interesados para reenganchar",
                body=(f"Tienes {n} interesado{plural} dormido{plural} con dato verificado "
                      "para retomar por valor. Míralos en tu CRM."),
                url="/?crm=1",
                email_subject="Contexto · interesados para reenganchar",
            )
            notificados += 1
        except Exception as exc:  # noqa: BLE001
            log.error("Reenganche cron: fallo notificando corredor: %s", exc)

    log.info("Reenganche cron: %d escaneados, %d disparados, %d holdout, %d a comprador, %d a corredor",
             len(filas), disparados, len(holdouts), enviados_comprador, notificados)
    return {"escaneados": len(filas), "disparados": disparados, "holdout": len(holdouts),
            "comprador": enviados_comprador, "corredores": notificados}


# ── Bucle de fondo (el "cron" dentro de la app) ─────────────────────────────
_tarea: asyncio.Task | None = None


async def _bucle() -> None:
    from app.database import AsyncSessionLocal
    intervalo = _intervalo()
    log.info("Reenganche cron activo (barrido cada %ds).", intervalo)
    while True:
        try:
            await asyncio.sleep(intervalo)
            async with AsyncSessionLocal() as db:
                await escanear_reenganches(db)
        except asyncio.CancelledError:
            break
        except Exception as exc:  # noqa: BLE001 — jamás morir por un barrido fallido
            log.error("Reenganche cron: barrido falló: %s", exc)


def iniciar_cron() -> None:
    """Arranca el bucle de fondo (desde el lifespan de la app). Idempotente."""
    global _tarea
    if not habilitado():
        log.info("Reenganche cron deshabilitado (REENGANCHE_CRON_ENABLED=0).")
        return
    if _tarea is None or _tarea.done():
        _tarea = asyncio.create_task(_bucle())


async def detener_cron() -> None:
    """Detiene el bucle de fondo (desde el shutdown del lifespan)."""
    global _tarea
    if _tarea and not _tarea.done():
        _tarea.cancel()
        try:
            await _tarea
        except asyncio.CancelledError:
            pass
    _tarea = None
