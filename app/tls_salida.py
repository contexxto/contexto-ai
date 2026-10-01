"""Verificación TLS de las llamadas HTTPS SALIENTES (Anthropic, Supabase Auth, Google, Voyage…).

Todo cliente httpx de app/ pide aquí su `verify=`. `SSL_VERIFY` admite tres valores:

  - `true` (default; producción): httpx verifica contra certifi.
  - `system`: verifica contra el almacén de certificados del SISTEMA OPERATIVO (truststore).
    Para dev local detrás de un antivirus o un proxy que re-firma el TLS — en la máquina
    de desarrollo, Avast: Windows confía en su raíz y certifi no. La verificación sigue
    ENCENDIDA; solo cambia en qué raíces se confía.
  - `false`: sin verificación. Legado: además `app/agent/graph.py` parcha httpx para TODO
    el proceso. `system` existe para que nadie tenga que volver a usarlo.

`system` entrega un contexto POR CLIENTE y nunca llama a `truststore.inject_into_ssl()`:
la inyección global reemplaza `ssl.SSLContext` y rompe `app/db_tls.py` (`get_ca_certs`).
La conexión a Postgres no pasa por aquí: la gobierna `db_tls`, que no lee esta variable.

`truststore` vive en requirements-dev.txt, no en requirements.txt: Render no lo instala,
así que `SSL_VERIFY=system` en producción falla al arrancar en vez de degradar a certifi
en silencio.
"""
from __future__ import annotations

import ssl
from functools import lru_cache

from app.config import settings


def verificacion_httpx() -> bool | ssl.SSLContext:
    """El `verify=` para httpx según `SSL_VERIFY`. Mismo criterio que antes para los
    valores que ya existían: solo `false` apaga; `system` es lo único nuevo."""
    modo = settings.ssl_verify.lower()
    if modo == "false":
        return False
    if modo == "system":
        return _contexto_del_sistema()
    return True


@lru_cache(maxsize=1)
def _contexto_del_sistema() -> ssl.SSLContext:
    try:
        import truststore
    except ImportError as exc:
        raise RuntimeError(
            "SSL_VERIFY=system necesita el paquete truststore (requirements-dev.txt). "
            "Es solo para desarrollo local: en producción no se instala a propósito."
        ) from exc
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
