"""E3.1a — qué identidad existe HOY. Caracterización, sin cambiar comportamiento.

Congela únicamente lo que el repositorio demuestra. Donde solo se puede probar una parte, el
test prueba esa parte y el reporte 11 marca el resto `[INFERIDO]` o `[DESCONOCIDO]`.

Nada aquí propone un `buyer_id`. La pregunta de esta unidad es **qué hay**, no qué querríamos.
"""

import ast
import asyncio
import pathlib
import re

import pytest
from fastapi import HTTPException

from app.auth import _extract_token, get_current_user, get_optional_user, get_optional_user_estricto

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CHAT = RAIZ / "app" / "routers" / "chat.py"
APP_JSX = RAIZ / "frontend" / "src" / "App.jsx"

_AUTH = ("get_current_user", "get_optional_user", "get_optional_user_estricto",
         "require_roles", "verify_api_key")


# ── A · usuario autenticado: la identidad es el `sub` del JWT ──────────────────────


def test_la_identidad_autenticada_sale_del_claim_sub():
    """`CurrentUser.user_id = claims["sub"]` — el UUID de cuenta de Supabase, no una
    identidad inventada por Contexto."""
    fuente = (RAIZ / "app" / "auth.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(fuente))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_current_user")
    cuerpo = ast.unparse(fn)
    assert 'user_id = claims[\'sub\']' in cuerpo or 'claims["sub"]' in cuerpo
    assert "uuid" not in cuerpo.lower(), "no se genera identidad aquí; se lee la del token"


def test_el_token_exige_exp_y_sub():
    """El decodificador rechaza un token sin `sub`: sin sujeto no hay identidad."""
    fuente = (RAIZ / "app" / "auth.py").read_text(encoding="utf-8")
    assert "'require': ['exp', 'sub']" in fuente or '"require": ["exp", "sub"]' in fuente


@pytest.mark.parametrize("cabecera,esperado", [
    ("Bearer abc123", "abc123"),
    ("bearer abc123", "abc123"),
    ("Bearer   ", None),
    ("Basic abc", None),
    ("abc123", None),
    (None, None),
])
def test_solo_se_acepta_el_esquema_bearer(cabecera, esperado):
    assert _extract_token(cabecera) == esperado


# ── B · anónimo: qué pasa sin token ────────────────────────────────────────────────


def test_sin_token_get_current_user_rechaza():
    with pytest.raises(HTTPException) as e:
        asyncio.run(get_current_user(authorization=None, db=None))
    assert e.value.status_code == 401


def test_sin_token_el_invitado_es_none_no_una_identidad_anonima():
    """LA RESPUESTA A "¿qué identifica a un anónimo en el backend?": nada.

    No devuelve un id de invitado, ni un placeholder: devuelve `None`. No existe una
    identidad de persona para el visitante sin cuenta.
    """
    assert asyncio.run(get_optional_user(authorization=None, db=None)) is None
    assert asyncio.run(get_optional_user_estricto(authorization=None, db=None)) is None


def test_el_estricto_distingue_sin_token_de_token_malo():
    """`get_optional_user` trata igual "no hay token" y "el token caducó"; el estricto no.
    La distinción existe porque una bandeja vacía era indistinguible de "no tienes nada"."""
    fuente = (RAIZ / "app" / "auth.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(fuente))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_optional_user_estricto")
    cuerpo = ast.unparse(fn)
    assert "return None" in cuerpo and "get_current_user" in cuerpo
    assert "except HTTPException" not in cuerpo, "el estricto NO traga el 401"


# ── El vínculo user ↔ thread ───────────────────────────────────────────────────────


def test_la_conversacion_se_liga_al_usuario_con_primer_dueno_gana():
    """`chat_sessions(session_id, user_id)` con `COALESCE`: una vez que un hilo tiene dueño,
    otro usuario NO se lo puede reasignar. Es lo que hace posible el caso anon→login: un hilo
    con `user_id` NULL sí puede adquirir dueño más tarde."""
    fuente = CHAT.read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(fuente))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "_tag_session_owner")
    cuerpo = ast.unparse(fn)
    assert "COALESCE(chat_sessions.user_id, :uid)" in cuerpo
    assert "ON CONFLICT (session_id) DO UPDATE" in cuerpo
    assert "if not user:" in cuerpo and "return" in cuerpo, "sin usuario no se etiqueta nada"


def test_el_etiquetado_es_best_effort_y_puede_fallar_en_silencio():
    """Consecuencia para E3.1b: el vínculo user↔thread NO está garantizado. Si la escritura
    falla, la conversación queda sin dueño y nadie se entera."""
    fuente = CHAT.read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(fuente))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "_tag_session_owner")
    manejadores = [h for t in ast.walk(fn) if isinstance(t, ast.Try) for h in t.handlers]
    assert manejadores and all(isinstance(h.body[0], ast.Pass) for h in manejadores)


def test_el_esquema_soporta_1_a_N_usuario_conversaciones():
    """`session_id` es PK y `user_id` es columna indexada NO única: un usuario puede tener
    muchas conversaciones. La relación 1:N existe y es consultable."""
    m006 = (RAIZ / "migrations" / "006_chat_sessions.sql").read_text(encoding="utf-8")
    m008 = (RAIZ / "migrations" / "008_auth_roles.sql").read_text(encoding="utf-8")
    assert "session_id  TEXT PRIMARY KEY" in m006
    assert "ADD COLUMN IF NOT EXISTS user_id UUID" in m008
    assert "CREATE INDEX IF NOT EXISTS ix_chat_sessions_user ON chat_sessions (user_id)" in m008
    assert "UNIQUE" not in m008.split("ix_chat_sessions_user")[0][-200:]


def test_el_perfil_referencia_a_auth_users():
    """`profiles.user_id` es PK con FK a `auth.users` y `ON DELETE CASCADE`: la identidad de
    cuenta no la posee Contexto, la posee Supabase."""
    m008 = (RAIZ / "migrations" / "008_auth_roles.sql").read_text(encoding="utf-8")
    assert "user_id    UUID PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE" in m008


def test_el_usuario_anonimo_no_tiene_lista_de_conversaciones():
    """`GET /sessions` devuelve `{"sessions": []}` para invitados. No hay continuidad anónima
    del lado del servidor: el hilo existe, pero nadie puede enumerarlo sin cuenta."""
    fuente = CHAT.read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(fuente))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "list_sessions")
    cuerpo = ast.unparse(fn)
    assert "if not user:" in cuerpo and "'sessions': []" in cuerpo


# ── La frontera de autorización ────────────────────────────────────────────────────


def _rutas_con_auth() -> dict[tuple[str, str], set[str]]:
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    fuera: dict[tuple[str, str], set[str]] = {}
    for n in ast.walk(arbol):
        if not isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for dec in n.decorator_list:
            s = ast.unparse(dec)
            metodo = next((m for m, t in (("GET", ".get("), ("POST", ".post("),
                                          ("DELETE", ".delete("), ("PATCH", ".patch("))
                           if t in s), None)
            if not metodo:
                continue
            ruta = s.split("(", 1)[1].split(",")[0].strip().strip("'\"")
            hits = {a for a in _AUTH if a in ast.unparse(n)}
            fuera[(metodo, ruta)] = hits
            break
    return fuera


def test_las_MUTACIONES_de_una_conversacion_exigen_dueno():
    """Lo que SÍ está protegido: renombrar, archivar y compartir exigen `get_current_user`."""
    rutas = _rutas_con_auth()
    for clave in [("PATCH", "/sessions/{session_id}"), ("DELETE", "/sessions/{session_id}"),
                  ("POST", "/sessions/{session_id}/share"), ("DELETE", "/sessions/{session_id}/share")]:
        assert "get_current_user" in rutas.get(clave, set()), clave


def test_LEER_una_conversacion_no_exige_dueno():
    """EL HALLAZGO QUE DECIDE SI `thread_id` PUEDE SER RAÍZ DEL BUYER: no puede.

    `GET /{session_id}/history` no declara ninguna dependencia de autenticación. Conocer el
    `session_id` basta para leer la conversación entera. El `session_id` es, por tanto, un
    **portador de capacidad** (como un enlace secreto), no una identidad verificada.

    Esto NO se corrige aquí —E3.1a no cambia comportamiento— pero fija el hecho: una raíz de
    identidad cuyo conocimiento otorga acceso no puede ser la raíz del Buyer.
    """
    rutas = _rutas_con_auth()
    assert rutas.get(("GET", "/{session_id}/history")) == set(), (
        "si esto cambió, revisar §9 del reporte 11: la frontera de autorización se movió"
    )


def test_el_inventario_exacto_de_lecturas_sin_auth():
    """Inventario congelado. Si aparece una ruta nueva sin auth, este test la caza."""
    rutas = _rutas_con_auth()
    sin_auth = {r for (m, r), a in rutas.items() if m == "GET" and not a}
    assert sin_auth == {
        "/shared/{token}",              # público POR DISEÑO: exige share_token + is_public
        "/{session_id}/history",
        "/{session_id}/handoff",
        "/{session_id}/intencion",
    }, f"cambió el conjunto de lecturas sin auth: {sin_auth}"


def test_el_hilo_compartido_si_exige_una_condicion_explicita():
    """`/shared/{token}` es la excepción legítima: no basta conocer el id, hace falta un
    token de compartir Y que el hilo esté marcado público."""
    fuente = CHAT.read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(fuente))
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "get_shared")
    cuerpo = ast.unparse(fn)
    assert "share_token = :t" in cuerpo and "is_public = true" in cuerpo


# ── El session_id: quién lo genera y cuánto dura ───────────────────────────────────


def test_el_backend_genera_un_session_id_si_el_cliente_no_lo_manda():
    """`ChatRequest.session_id` tiene `default_factory=uuid4`. Un turno sin session_id NO
    falla: crea una conversación de un solo turno, irrecuperable."""
    from app.routers.chat import ChatRequest

    a, b = ChatRequest(message="hola"), ChatRequest(message="hola")
    assert a.session_id != b.session_id
    assert len(a.session_id) == 36 and a.session_id.count("-") == 4


def test_el_frontend_persiste_el_session_id_en_localstorage():
    """[OBSERVADO en el fuente] `contexto_ai_session_id` sobrevive a recargas y a cierres del
    navegador: la conversación del anónimo persiste en SU navegador."""
    js = APP_JSX.read_text(encoding="utf-8")
    assert "const SESSION_KEY = 'contexto_ai_session_id'" in js
    assert re.search(r"localStorage\.getItem\(SESSION_KEY\)", js)
    assert re.search(r"localStorage\.setItem\(SESSION_KEY", js)


def test_existe_un_device_id_anonimo_previo_a_esta_fase():
    """INFRAESTRUCTURA ANÓNIMA QUE YA EXISTÍA, y hay que caracterizarla antes de reutilizarla.

    `contexto_ai_device_id` es un UUID de navegador en localStorage. Su propósito declarado es
    acotado: hacer PRIVADA la sesión del QR por visitante (`qr-{activo}-{dispositivo}`), no
    identificar a una persona.
    """
    js = APP_JSX.read_text(encoding="utf-8")
    assert "const DEVICE_KEY = 'contexto_ai_device_id'" in js
    assert "crypto.randomUUID" in js
    assert "qr-${id}-${getDeviceId()}" in js.replace("`", "`")


def test_el_device_key_SI_llega_al_backend_y_SI_se_persiste():
    """CORRECCIÓN A LA LECTURA INGENUA: el identificador de dispositivo no se queda en el
    navegador. Viaja como campo propio y se guarda.

        App.jsx  →  device_key: getDeviceId()   (registro de llegada)
                 →  visita.device_key           (migración 024)
                 →  contacto.device_key         (migración 025, vía alertas.py)

    Existe, por tanto, un identificador **durable de navegador, persistido en servidor**,
    anterior a esta fase. Eso NO lo convierte en candidato a `buyer_id` — ver el test
    siguiente, que es el que decide.
    """
    js = APP_JSX.read_text(encoding="utf-8")
    assert "device_key: getDeviceId()" in js

    alertas = (RAIZ / "app" / "routers" / "alertas.py").read_text(encoding="utf-8")
    assert "device_key: str | None" in alertas
    assert "INSERT INTO contacto" in alertas and "device_key" in alertas

    m024 = (RAIZ / "migrations" / "024_visita.sql").read_text(encoding="utf-8")
    assert "device_key   text" in m024


def test_el_repo_YA_clasifica_el_device_key_como_dato_personal():
    """EL HECHO QUE GOBIERNA CUALQUIER USO FUTURO, y no es técnico sino de política.

    La migración 024 lo dice con todas las letras: *"`device_key` es un identificador en
    línea: cuenta como dato personal aunque no traiga nombre, así que una supresión debe
    alcanzar TAMBIÉN esta tabla"*.

    Reutilizarlo como raíz del Buyer no sería una decisión de arquitectura: sería ampliar el
    alcance de un dato personal ya declarado como tal, con obligación de supresión asociada.
    E3.1a no la toma.
    """
    m024 = (RAIZ / "migrations" / "024_visita.sql").read_text(encoding="utf-8")
    assert "cuenta como" in m024 and "dato personal" in m024
    assert "supresión debe alcanzar" in m024


def test_el_device_key_no_esta_ligado_a_la_propiedad_de_la_conversacion():
    """Vive en `visita` y `contacto` —analítica y captación—, NO en `chat_sessions`. No hay
    columna, índice ni FK que lo relacione con la propiedad de un hilo."""
    m006 = (RAIZ / "migrations" / "006_chat_sessions.sql").read_text(encoding="utf-8")
    m008 = (RAIZ / "migrations" / "008_auth_roles.sql").read_text(encoding="utf-8")
    assert "device" not in m006.lower()
    assert "device" not in m008.lower()

    # `chat.py` no maneja el device como campo: su única mención es un docstring que
    # documenta que el `session_id` del QR lo lleva incrustado.
    chat = CHAT.read_text(encoding="utf-8")
    lineas = [l for l in chat.splitlines() if "device" in l.lower()]
    assert len(lineas) == 1 and lineas[0].lstrip().startswith('"""')
    assert "device_key" not in chat


def test_el_session_id_del_QR_codifica_estructura_por_posicion():
    """Consecuencia de lo anterior: el `session_id` no es opaco. `chat.py` extrae el
    `activo_id` por posición fija dentro de la cadena `qr-{activo}-{device}`.

    Importa para E3.1b: un identificador que **transporta** datos (qué inmueble, qué
    navegador) no es una llave neutral. Cambiar su formato rompería ese parseo.
    """
    chat = CHAT.read_text(encoding="utf-8")
    assert "qr-{activo_uuid(36)}-{device_uuid}" in chat
    assert "posición fija" in chat


def test_el_logout_no_borra_ni_la_sesion_ni_el_dispositivo():
    """CASO D, y tiene consecuencia de privacidad.

    `logout()` limpia la sesión de Supabase y el token en memoria, pero **no toca**
    `SESSION_KEY` ni `DEVICE_KEY`. Tras cerrar sesión, el navegador sigue apuntando al MISMO
    hilo — que ya quedó etiquetado con el `user_id` anterior en `chat_sessions`— y ese hilo se
    puede leer sin auth (ver `test_LEER_una_conversacion_no_exige_dueno`).
    """
    js = APP_JSX.read_text(encoding="utf-8")
    inicio = js.index("const logout = useCallback(")
    cuerpo = js[inicio: js.index("}, [])", inicio)]
    assert "signOut" in cuerpo and "setAccessToken(null)" in cuerpo
    assert "SESSION_KEY" not in cuerpo
    assert "DEVICE_KEY" not in cuerpo
    assert "removeItem" not in cuerpo


def test_contexto_no_guarda_el_token_por_su_cuenta():
    """Lo que SÍ se puede afirmar: el módulo propio de Contexto mantiene el access token en
    una variable de módulo y **no** lo escribe en `localStorage`.

    Esto NO significa que no haya un JWT en `localStorage` — ver el test siguiente. Afirmarlo
    sería una afirmación de seguridad falsa, y una versión anterior de este reporte la hizo.
    """
    api = (RAIZ / "frontend" / "src" / "api.js").read_text(encoding="utf-8")
    assert "let accessToken" in api or "accessToken = null" in api
    assert "localStorage" not in api.split("export function apiHeaders")[0]


def test_el_cliente_supabase_usa_la_persistencia_por_defecto():
    """CORRECCIÓN. `createClient(url, anon)` se instancia **sin opciones de auth**.

    El comportamiento por defecto de `supabase-js` es `persistSession: true`, que guarda la
    sesión de auth en `localStorage` del navegador. O sea: sí hay una sesión persistida, solo
    que **la gestiona la librería**, no Contexto.

    No confundir tres cosas distintas:

        storage de sesión de Supabase   ≠  contexto_ai_session_id  ≠  contexto_ai_device_id

    Lo que este test congela es la CONFIGURACIÓN (verificable en el repo). El comportamiento
    concreto de la librería es contrato del proveedor, y así queda marcado en el reporte.
    """
    js = (RAIZ / "frontend" / "src" / "supabaseClient.js").read_text(encoding="utf-8")
    assert "createClient(url, anon)" in js
    assert "persistSession" not in js, "si se configurara explícitamente, cambiaría §10"
    assert "storageKey" not in js


def test_el_signout_es_de_alcance_local():
    """`signOut({ scope: 'local' })` borra la sesión que la librería mantiene en ESTE
    dispositivo. Es lo que limpia el storage de Supabase — y sigue sin tocar las claves
    propias de Contexto (ver `test_el_logout_no_borra_ni_la_sesion_ni_el_dispositivo`)."""
    js = APP_JSX.read_text(encoding="utf-8")
    assert "signOut({ scope: 'local' })" in js
