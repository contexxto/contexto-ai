"""
Notificaciones — email (Resend) + Web Push (pywebpush). Genéricas y reutilizables.

Se disparan en AMBAS direcciones del handoff in-platform:
  • corredor → lead : cuando el corredor responde      (app/routers/assets.py)
  • lead → corredor : cuando el lead pide hablar o      (app/routers/chat.py)
                      le escribe un mensaje

Patrón: fire-and-forget desde asyncio.create_task (no bloquea la respuesta HTTP).

Variables de entorno necesarias:
  RESEND_API_KEY      → API key de resend.com (gratis hasta 3 000 emails/mes)
  NOTIFY_FROM_EMAIL   → Remitente, ej.: "Contexto AI <notifs@tudominio.com>"
                        Sin dominio propio usa "Contexto AI <onboarding@resend.dev>"
  APP_URL             → https://contexto-ai-six.vercel.app
  VAPID_PRIVATE_KEY   → base64(PEM) generado con scripts/gen_vapid.py
  VAPID_PUBLIC_KEY    → base64url del punto público (gen_vapid.py)
  VAPID_EMAIL         → mailto:contexxto.ai@gmail.com
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os

log = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FROM_EMAIL     = os.getenv("NOTIFY_FROM_EMAIL", "Contexto AI <onboarding@resend.dev>")
APP_URL        = os.getenv("APP_URL", "https://contexxto.com").rstrip("/")

def _normalizar_vapid(bruto: str) -> str | None:
    """Devuelve el PEM de la clave privada, venga como venga de la variable de entorno.

    Nace de un fallo real: el push llevaba dias sin salir con "ASN.1 parsing error:
    invalid length" — la clave estaba puesta pero era ilegible. Pegar un PEM en una
    variable de entorno lo estropea de formas conocidas: los saltos de linea se convierten
    en la secuencia \\n literal, el panel añade comillas alrededor, o se cuela un espacio.
    Se contemplan las tres, mas el base64 del PEM que produce scripts/gen_vapid.py.
    """
    if not bruto:
        return None
    v = bruto.strip().strip('"').strip("'")
    if not v:
        return None
    if "-----" not in v:                      # base64 del PEM (formato de gen_vapid.py)
        try:
            v = base64.b64decode(v).decode()
        except Exception:
            log.warning("VAPID_PRIVATE_KEY no es base64 ni PEM — push deshabilitado")
            return None
    if "\\n" in v and "\n" not in v:          # PEM con los saltos escapados
        v = v.replace("\\n", "\n")
    return v


def _vapid_utilizable(pem: str | None) -> tuple[bool, str]:
    """¿La clave se puede CARGAR de verdad? Comprobar que la variable existe no basta —
    el diagnostico decia "configurada" mientras cada envio fallaba."""
    if not pem:
        return False, "no configurada"
    try:
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        load_pem_private_key(pem.encode(), password=None)
        return True, "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"ilegible ({type(exc).__name__})"


VAPID_PRIVATE_KEY: str | None = _normalizar_vapid(os.getenv("VAPID_PRIVATE_KEY", ""))
VAPID_VALIDA, VAPID_DETALLE = _vapid_utilizable(VAPID_PRIVATE_KEY)
if not VAPID_VALIDA:
    log.warning("VAPID_PRIVATE_KEY %s — el push NO va a funcionar", VAPID_DETALLE)

VAPID_EMAIL = os.getenv("VAPID_EMAIL", "mailto:contexxto.ai@gmail.com")

_credencial = None


def credencial_vapid():
    """El objeto Vapid que espera pywebpush, construido desde nuestro PEM.

    AQUI estaba el fallo que tuvo el push muerto desde el principio. pywebpush documenta
    `vapid_private_key: Vapid instance or path to vapid private key PEM`: una CADENA la
    interpreta como una RUTA DE ARCHIVO, no como el contenido. Al no ser un fichero,
    terminaba en Vapid.from_string(), que espera la clave en crudo — y reventaba con
    "Could not deserialize key data … ASN.1 parsing error: invalid length".

    O sea: la clave siempre fue valida (cryptography la carga sin problema), y el error
    apuntaba a ella. Reproducido en local: from_string(PEM) falla con ese mismo mensaje,
    from_pem(PEM) funciona.
    """
    global _credencial
    if _credencial is None and VAPID_PRIVATE_KEY:
        try:
            from py_vapid import Vapid01
            _credencial = Vapid01.from_pem(VAPID_PRIVATE_KEY.encode())
        except Exception as exc:  # noqa: BLE001
            log.error("No se pudo construir la credencial VAPID: %s", exc)
    return _credencial


# ── API pública ──────────────────────────────────────────────────────────────
# asyncio solo guarda una referencia DÉBIL a las tareas: una lanzada con create_task y
# sin guardar puede ser recolectada a mitad de ejecución, y el aviso se pierde sin dejar
# rastro (lo advierte la propia doc de asyncio). Todos los avisos son fire-and-forget, así
# que se guarda la referencia hasta que termina.
_tareas_vivas: set = set()


def disparar(coro) -> None:
    """Lanza una corrutina de aviso sin bloquear la respuesta HTTP, conservando la
    referencia para que no la recolecte el GC a medias."""
    tarea = asyncio.ensure_future(coro)
    _tareas_vivas.add(tarea)
    tarea.add_done_callback(_tareas_vivas.discard)


async def send_notification(
    *,
    email: str | None,
    push_subscription: dict | list | None,
    title: str,
    body: str,
    url: str,
    email_subject: str | None = None,
    tag: str | None = None,
    email_clave: str | None = None,
    email_minutos: int = 30,
) -> None:
    """Notifica a un destinatario por email Y push de forma concurrente.

    Args:
        email: destino del correo (o None para omitir email).
        push_subscription: PushSubscription JSON, o una LISTA de ellas para avisar a
             todos los dispositivos del destinatario (teléfono y web a la vez). Se
             acepta el dict suelto porque el lead sigue teniendo un solo dispositivo
             por sesión; el corredor manda lista.
        title: título corto (encabezado del email / título de la notificación).
        body: cuerpo del mensaje.
        url: ruta destino al tocar (ej. "/a/<uuid>" o "/?crm=1"). En el email se
             antepone APP_URL; en push se usa relativa (el Service Worker resuelve).
        email_subject: asunto del correo (por defecto = title).
        tag: identificador de AGRUPACIÓN del push. Los avisos con el mismo tag se
             reemplazan entre sí en el aparato en vez de apilarse — el comportamiento de
             cualquier app de mensajería. Debe ser por conversación. Si no se pasa, el
             Service Worker agrupa por url.
        email_clave: si se indica, el correo se manda como MUCHO una vez cada
             `email_minutos` para esa clave. El push es instantáneo y gratis para el
             usuario; el correo no: una conversación de seis turnos generaba seis correos.
             El correo pasa a ser el aviso de "tienes algo pendiente", no una copia de
             cada mensaje. Sin clave, se envía siempre (avisos puntuales, no de hilo).
        email_minutos: ventana del freno anterior.
    """
    tasks = []
    if email and (email_clave is None or await _email_permitido(email_clave, email_minutos)):
        tasks.append(_send_email(
            to=email, subject=email_subject or title, title=title, body=body, url=url,
        ))
    subs = push_subscription if isinstance(push_subscription, list) else [push_subscription]
    for sub in subs:
        if sub:
            tasks.append(_send_push(subscription=sub, title=title, body=body, url=url, tag=tag))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _email_permitido(clave: str, minutos: int) -> bool:
    """¿Toca mandar correo para esta clave, o ya se mandó hace poco?

    Marca el envío en la MISMA sentencia que lo consulta: el INSERT … ON CONFLICT DO
    UPDATE … WHERE devuelve fila solo si insertó o si el anterior ya caducó. Dos avisos
    simultáneos no pueden colarse los dos, que es justo lo que pasaría comprobando y
    escribiendo por separado.

    Ante cualquier fallo devuelve True: perder un aviso es peor que mandar uno de más.
    """
    try:
        from sqlalchemy import text
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await db.execute(text(
                "CREATE TABLE IF NOT EXISTS aviso_email ("
                "clave text PRIMARY KEY, enviado_en timestamptz NOT NULL DEFAULT now())"))
            fila = (await db.execute(text(
                "INSERT INTO aviso_email (clave, enviado_en) VALUES (:c, now()) "
                "ON CONFLICT (clave) DO UPDATE SET enviado_en = now() "
                "  WHERE aviso_email.enviado_en < now() - make_interval(mins => :m) "
                "RETURNING 1"), {"c": clave, "m": minutos})).scalar()
            await db.commit()
            return fila is not None
    except Exception as exc:  # noqa: BLE001
        log.warning("Freno de correo no disponible (%s) — se envía igual", exc)
        return True


# ── Email vía Resend ─────────────────────────────────────────────────────────
async def _send_email(*, to: str, subject: str, title: str, body: str, url: str) -> None:
    if not RESEND_API_KEY:
        log.warning("RESEND_API_KEY no configurada — email omitido")
        return
    link = url if url.startswith("http") else f"{APP_URL}{url}"
    html = f"""
    <div style="font-family:sans-serif;max-width:540px;margin:auto;padding:28px 24px;
                background:#16151E;color:#EDEBF2;border-radius:16px">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:18px">
        <div style="width:36px;height:36px;border-radius:50%;background:#2DBDB6;
                    display:flex;align-items:center;justify-content:center;
                    font-size:18px">🏠</div>
        <span style="font-weight:800;font-size:1.1rem">
          Contexto <span style="color:#2DBDB6">AI</span>
        </span>
      </div>
      <h2 style="margin:0 0 8px;font-size:1.15rem">{title}</h2>
      <p style="color:#9C99AC;margin:0 0 20px;font-size:.9rem">{body}</p>
      <a href="{link}"
         style="display:inline-block;padding:12px 28px;border-radius:10px;
                background:#2DBDB6;color:#0E0D13;font-weight:800;
                text-decoration:none;font-size:.95rem">
        Abrir Contexto AI →
      </a>
      <p style="margin-top:28px;font-size:.75rem;color:#9C99AC">
        Contexto AI · Inteligencia inmobiliaria en Quito
      </p>
    </div>
    """
    try:
        import resend as _resend  # lazy — solo si RESEND_API_KEY está configurada
        _resend.api_key = RESEND_API_KEY
        await asyncio.to_thread(
            _resend.Emails.send,
            {"from": FROM_EMAIL, "to": to, "subject": subject, "html": html},
        )
        log.info("Email enviado → %s", to)
    except Exception as exc:
        log.error("Error enviando email a %s: %s", to, exc)


# ── Web Push vía pywebpush ───────────────────────────────────────────────────
async def _send_push(*, subscription: dict, title: str, body: str, url: str, tag: str | None = None) -> None:
    if not VAPID_PRIVATE_KEY:
        log.warning("VAPID_PRIVATE_KEY no configurada — push omitido")
        return
    # subscription puede venir como str (jsonb) o dict, según el driver.
    if isinstance(subscription, str):
        try:
            subscription = json.loads(subscription)
        except Exception:
            log.error("Suscripción push inválida (no es JSON)")
            return
    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "icon": "/icon-192.png",   # logo actual de la marca
        # Agrupa por conversación en el aparato (ver sw.js): un hilo, un aviso.
        **({"tag": tag} if tag else {}),
    })
    try:
        from pywebpush import webpush  # lazy import

        def _push() -> None:
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=credencial_vapid(),
                vapid_claims={"sub": VAPID_EMAIL},
                ttl=86400,
            )

        await asyncio.to_thread(_push)
        log.info("Push enviado")
    except Exception as exc:
        # 404/410 = el navegador se desuscribió (desinstaló la PWA, limpió datos…). Ese
        # endpoint no revive: sin borrarlo, push_dispositivo acumula basura y cada aviso
        # gasta un intento en un destino muerto.
        estado = getattr(getattr(exc, "response", None), "status_code", None)
        if estado in (404, 410):
            await _olvidar_dispositivo(subscription.get("endpoint"))
            log.info("Push: endpoint caducado (%s), dispositivo olvidado", estado)
            return
        log.error("Error enviando push: %s", exc)


async def _olvidar_dispositivo(endpoint: str | None) -> None:
    """Borra un dispositivo cuyo endpoint ya no existe. Silencioso a propósito: esto
    corre dentro de un fire-and-forget y no debe tumbar el aviso a los demás."""
    if not endpoint:
        return
    try:
        from sqlalchemy import text
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db:
            await db.execute(
                text("DELETE FROM push_dispositivo WHERE endpoint = :e"), {"e": endpoint})
            await db.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("No se pudo olvidar el dispositivo: %s", exc)


async def probar_push(subscription: dict) -> tuple[bool, str]:
    """Intenta un push y DEVUELVE el resultado en vez de tragárselo en un log.

    Existe porque diagnosticar "no me llega el push" desde fuera era imposible: el envío
    falla en el servidor, deja un log.error que solo se ve entrando a Render, y el usuario
    solo percibe silencio. Esto pone el error en la pantalla de quien prueba.
    """
    if not VAPID_PRIVATE_KEY:
        return False, "VAPID_PRIVATE_KEY no configurada en el servidor"
    if isinstance(subscription, str):
        try:
            subscription = json.loads(subscription)
        except Exception:
            return False, "La suscripción guardada no es JSON válido"
    payload = json.dumps({
        "title": "🔔 Prueba de notificación",
        "body": "Si ves esto, el push funciona en este aparato.",
        "url": "/?crm=1",
        "icon": "/icon-192.png",   # logo actual de la marca
        "tag": "prueba-push",
    })
    try:
        from pywebpush import webpush

        def _push() -> None:
            webpush(
                subscription_info=subscription,
                data=payload,
                vapid_private_key=credencial_vapid(),
                vapid_claims={"sub": VAPID_EMAIL},
                ttl=60,
            )

        await asyncio.to_thread(_push)
        return True, "enviado"
    except Exception as exc:  # noqa: BLE001
        estado = getattr(getattr(exc, "response", None), "status_code", None)
        detalle = f"{type(exc).__name__}: {exc}"
        if estado:
            detalle = f"HTTP {estado} — {detalle}"
        return False, detalle[:300]


def forma_vapid() -> dict:
    """Radiografía de la clave privada SIN revelarla: longitudes y cabeceras, nada de
    material criptográfico. Existe porque "la clave no se puede leer" no dice DÓNDE se
    rompe: si llega truncada, si no es base64, si decodifica a algo que no es un PEM, o
    si es un PEM de un tipo que no sirve.
    """
    bruto = os.getenv("VAPID_PRIVATE_KEY", "") or ""
    info = {
        "largo_crudo": len(bruto),
        "tiene_espacios_o_saltos": any(c in bruto for c in " \n\r\t"),
        "empieza_con_pem": bruto.strip().startswith("-----"),
        "decodifica_base64": None,
        "largo_decodificado": None,
        "cabecera_pem": None,
        "carga": VAPID_DETALLE,
    }
    v = bruto.strip().strip('"').strip("'")
    if v and not v.startswith("-----"):
        try:
            d = base64.b64decode(v).decode()
            info["decodifica_base64"] = True
            info["largo_decodificado"] = len(d)
            primera = d.strip().splitlines()[0] if d.strip() else ""
            info["cabecera_pem"] = primera[:40]      # "-----BEGIN EC PRIVATE KEY-----": no es secreto
        except Exception as exc:  # noqa: BLE001
            info["decodifica_base64"] = False
            info["cabecera_pem"] = f"no decodifica ({type(exc).__name__})"
    elif v:
        primera = v.splitlines()[0]
        info["cabecera_pem"] = primera[:40]
    return info
