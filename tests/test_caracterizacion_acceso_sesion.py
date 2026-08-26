"""AUTH-READ-GATE.0 — quién puede leer, escribir y APROPIARSE de una conversación hoy.

Caracterización. Cero cambios productivos. Ningún test espera 401/403: eso pertenece a la
implementación (`AUTH-READ-GATE.1`). Aquí solo se congela lo que el repo hace **ahora**.

El hallazgo que amplía el alcance de la unidad: la frontera abierta no es solo de LECTURA.
Conocer un `session_id` también permite **escribir** en el hilo y, si no tiene dueño,
**reclamarlo** — y en un caso, publicarlo.
"""

import ast
import pathlib
import re

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CHAT = RAIZ / "app" / "routers" / "chat.py"
ASSETS = RAIZ / "app" / "routers" / "assets.py"
APP_JSX = RAIZ / "frontend" / "src" / "App.jsx"

_AUTH = ("get_current_user", "get_optional_user", "get_optional_user_estricto",
         "require_roles", "verify_api_key")


def _fn(nombre: str, fichero: pathlib.Path = CHAT):
    arbol = ast.parse(fichero.read_text(encoding="utf-8"))
    return next(n for n in ast.walk(arbol)
                if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == nombre)


# ── El QR: qué representa y qué lleva ──────────────────────────────────────────────


def test_el_QR_codifica_el_INMUEBLE_no_una_conversacion():
    """Respuesta a "¿el QR representa un inmueble, una conversación o ambas?": el inmueble.

    La URL impresa es `{app}/a/{activo_id}?utm_source=letrero&utm_medium=qr`. No lleva
    `session_id`, no lleva token, no lleva credencial. Eso es una **restricción de diseño
    dura** para AUTH-READ-GATE.1: los letreros ya impresos no se pueden cambiar.
    """
    src = ASSETS.read_text(encoding="utf-8")
    assert 'base = f"{settings.public_app_url.rstrip(\'/\')}/a/{activo_id}"' in src
    assert 'return f"{base}?utm_source=letrero&utm_medium=qr"' in src
    assert "session_id" not in src.split("def _qr_url")[-1][:400] if "_qr_url" in src else True


def test_el_session_id_del_QR_nace_en_el_CLIENTE_y_vive_en_localstorage():
    """Cuándo existe por primera vez y quién lo genera: el navegador, al abrir el deep link.

        fresco    →  `qr-{activo}-{device}-{6 al azar}`
        reanudar  →  el guardado en `localStorage['ctx_qr_' + activo]`

    El servidor nunca lo emite en este carril: lo recibe ya hecho.
    """
    js = APP_JSX.read_text(encoding="utf-8")
    assert "const storeKey = 'ctx_qr_' + id" in js
    assert "const sid = `${qrSessionId(id)}-${Math.random().toString(36).slice(2, 8)}`" in js
    assert "localStorage.setItem(storeKey, sid)" in js


def test_la_reanudacion_del_QR_es_por_navegador_no_por_persona():
    """¿Necesita recuperar la MISMA conversación desde otro dispositivo? Hoy no puede.

    La llave de reanudación está en `localStorage`, y el `session_id` incluye el
    `device_id`. Otro navegador —aunque sea la misma persona— genera un hilo NUEVO. Es un
    dato de producto, no un defecto: acota qué tiene que preservar el gate.
    """
    js = APP_JSX.read_text(encoding="utf-8")
    assert "const qrSessionId = (id) => `qr-${id}-${getDeviceId()}`" in js
    assert "localStorage.getItem(storeKey)" in js


def test_REGRESION_el_carril_anonimo_YA_tiene_credencial():
    """`EXPECTED_POLICY_CHANGE` · antes: `test_loadFromDeepLink_no_lleva_ninguna_credencial_extra`.

    **Congelado en `.0`:** el carril de reanudación del QR no llevaba ninguna prueba de
    posesión. `apiHeaders()` solo aportaba la `X-API-Key` pública del sitio y, si existía, el
    Bearer del usuario — para un anónimo, nada que demostrara que la conversación era suya.
    Ese era el hueco que hacía del `session_id` una credencial de facto.

    **Cambio autorizado en AUTH-READ-GATE.1:** existe `apiHeadersSesion(sessionId)`, que añade
    `X-Session-Resume` cuando hay capacidad **para esa conversación**.

    Se pasa la sesión por parámetro y no se usa una "capacidad actual": el navegador puede
    tener varias conversaciones abiertas y cada una tiene la suya.
    """
    api = (RAIZ / "frontend" / "src" / "api.js").read_text(encoding="utf-8")

    assert "export function apiHeadersSesion(sessionId)" in api
    assert "resumeHeader(sessionId)" in api
    assert "bootstrapSession" in api, "y existe la única puerta de creación"

    # `apiHeaders()` sigue SIN capacidad: es para peticiones que no son sobre una
    # conversación concreta. La capacidad solo entra por la variante que recibe la sesión.
    #
    # Se acota al CUERPO de la función, no al texto entre ambas: en medio va el JSDoc de
    # `apiHeadersSesion`, que nombra la cabecera legítimamente al explicar el contrato.
    lineas = api.splitlines()
    i = next(n for n, l in enumerate(lineas) if l.startswith("export function apiHeaders()"))
    cuerpo = "\n".join(lineas[i:i + 7])
    assert "X-API-Key" in cuerpo and "Authorization" in cuerpo
    assert "resume" not in cuerpo.lower(), "la capacidad no puede colarse en la cabecera genérica"


def test_intencion_NO_participa_en_el_QR():
    """Respuesta directa: `/intencion` quedó abierto **por accidente**, no por necesidad del
    QR. Ningún componente del frontend lo llama."""
    frontend = " ".join(p.read_text(encoding="utf-8")
                        for p in (RAIZ / "frontend" / "src").rglob("*.jsx"))
    # Se busca la LLAMADA al endpoint, no la subcadena: `./intencionesEntrada` es un módulo
    # local de textos de entrada y no tiene nada que ver con `GET /{session_id}/intencion`.
    assert not re.search(r"chat/\$\{[^}]+\}/intencion", frontend)
    assert "api/v1/chat" not in frontend.split("intencionesEntrada")[0][-200:]


def test_handoff_SI_participa_en_el_QR():
    """`/handoff` sí es parte del carril anónimo: es como el visitante recupera la
    conversación con el corredor al volver a escanear."""
    js = APP_JSX.read_text(encoding="utf-8")
    assert "/handoff`, { headers: apiHeaders() })" in js


# ── Frontera 1 · LECTURA ───────────────────────────────────────────────────────────


def _rutas() -> dict[tuple[str, str], set[str]]:
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    fuera = {}
    for n in ast.walk(arbol):
        if not isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for dec in n.decorator_list:
            s = ast.unparse(dec)
            metodo = next((m for m, t in (("GET", ".get("), ("POST", ".post("),
                                          ("DELETE", ".delete("), ("PATCH", ".patch("))
                           if t in s), None)
            if metodo:
                ruta = s.split("(", 1)[1].split(",")[0].strip().strip("'\"")
                fuera[(metodo, ruta)] = {a for a in _AUTH if a in ast.unparse(n)}
                break
    return fuera


def test_conocer_el_session_id_basta_para_LEER():
    """Inventario congelado de lecturas sin autenticación."""
    r = _rutas()
    assert r[("GET", "/{session_id}/history")] == set()
    assert r[("GET", "/{session_id}/handoff")] == set()
    assert r[("GET", "/{session_id}/intencion")] == set()


def test_el_hilo_compartido_SI_exige_una_condicion():
    """El contraste que demuestra que la separación recurso↔capacidad ya existe en el repo:
    `/shared/{token}` no autentica a nadie, pero exige **token + is_public**."""
    cuerpo = ast.unparse(_fn("get_shared"))
    assert "share_token = :t" in cuerpo and "is_public = true" in cuerpo


# ── Frontera 2 · ESCRITURA Y APROPIACIÓN ───────────────────────────────────────────


def test_REGRESION_POST_chat_autoriza_ANTES_de_escribir():
    """`EXPECTED_POLICY_CHANGE` · antes: `test_POST_chat_no_comprueba_propiedad_ANTES_de_escribir`.

    **Comportamiento congelado en `.0`:** `POST /chat` llamaba a `_tag_session_owner` como
    primera instrucción, con el `session_id` que enviara el cliente y sin comprobar de quién
    era el hilo. Conocer el id permitía escribir en la conversación.

    **Cambio autorizado por la política** (`.0` §7, filas 8 y 9). Ahora la primera
    instrucción real es la autorización, y el claim vive **detrás** de ella.
    """
    fn = _fn("chat")
    cuerpo = ast.unparse(fn)
    assert "_exigir_autoridad(request, payload.session_id, user)" in cuerpo

    primera = next(s for s in fn.body if not isinstance(s, ast.Expr) or
                   not isinstance(s.value, ast.Constant))
    assert "_exigir_autoridad" in ast.unparse(primera), (
        "la autorización dejó de ser la primera instrucción: algo se escribe antes de validar"
    )
    # El claim solo puede ocurrir DESPUÉS de autorizar.
    assert cuerpo.index("_exigir_autoridad") < cuerpo.index("reclamar_sesion_anonima")


def test_REGRESION_ya_no_existe_via_de_apropiacion_por_identificador():
    """`EXPECTED_POLICY_CHANGE` · antes:
    `test_un_autenticado_puede_RECLAMAR_un_hilo_anonimo_con_solo_conocer_el_id`.

    **Comportamiento congelado en `.0`:** `_tag_session_owner` hacía
    `COALESCE(chat_sessions.user_id, :uid)`, así que el primer autenticado que enviara el
    `session_id` se quedaba con el hilo sin demostrar posesión.

    **Cambio autorizado por la política** (`.0` §7, fila 8: *auth + solo session_id → no
    claim*). La función se **eliminó**; no se conservó como auxiliar, porque mientras exista
    una vía que asigne propiedad por identificador alguien volverá a llamarla.
    """
    src = CHAT.read_text(encoding="utf-8")
    assert "async def _tag_session_owner" not in src
    # Se mira el CÓDIGO, no los comentarios: el bloque que documenta la eliminación cita la
    # sentencia vieja a propósito, y eso no es una vía de apropiación.
    literales = " ".join(n.value for n in ast.walk(ast.parse(src))
                         if isinstance(n, ast.Constant) and isinstance(n.value, str))
    assert "COALESCE(chat_sessions.user_id" not in literales, (
        "reapareció la asignación de dueño por identificador"
    )
    # Y el claim que la sustituye exige la capacidad.
    from app.sesion_autoridad import reclamar_sesion_anonima
    import inspect
    assert "resume_secret" in inspect.signature(reclamar_sesion_anonima).parameters


@pytest.mark.parametrize("fn_nombre", ["update_session", "delete_session", "share_session"])
def test_REGRESION_las_tres_mutaciones_exigen_ser_dueno(fn_nombre):
    """`EXPECTED_POLICY_CHANGE` · antes: `test_las_mutaciones_no_usan_el_mismo_criterio_entre_si`.

    **Congelado en `.0`:** asimetría entre endpoints hermanos — renombrar era estricto;
    archivar y compartir aceptaban además los hilos sin dueño (`OR user_id IS NULL`).

    **Y la caracterización se quedó corta**: `update_session` también reclamaba, con un
    `INSERT … COALESCE` como paso previo que el test de `.0` no vio porque solo miraba el
    `WHERE` de los `UPDATE`.

    **Cambio autorizado:** las tres exigen ser dueño. Ninguna crea la fila ni la adquiere.
    """
    cuerpo = ast.unparse(_fn(fn_nombre))
    assert "user_id IS NULL" not in cuerpo, "sigue aceptando hilos sin dueño"
    assert "COALESCE(chat_sessions.user_id" not in cuerpo, "sigue reclamando por identificador"
    assert "user_id = :uid" in cuerpo, "debe exigir propiedad"


def test_REGRESION_compartir_ya_no_reclama_el_hilo():
    """`EXPECTED_POLICY_CHANGE` · antes: `test_compartir_publica_y_reclama_en_la_misma_sentencia`.

    **Congelado en `.0`:** la sentencia publicaba Y reclamaba a la vez sobre un hilo sin
    dueño, así que conocer el `session_id` de una conversación anónima bastaba para quedársela
    y hacerla legible por cualquiera.

    **Cambio autorizado:** ya no inserta. Publica solo lo que ya es tuyo.
    """
    cuerpo = " ".join(ast.unparse(_fn("share_session")).split())   # SQL alineado con espacios
    assert "is_public = true" in cuerpo, "sigue siendo el endpoint de compartir"
    assert "INSERT INTO chat_sessions" not in cuerpo, "no debe crear ni adquirir la fila"
    assert "user_id = COALESCE" not in cuerpo
    assert "WHERE session_id = :sid AND user_id = :uid" in cuerpo


def test_REGRESION_ya_no_hay_etiquetado_silencioso_de_dueno():
    """`EXPECTED_POLICY_CHANGE` · antes: `test_el_etiquetado_de_dueno_es_silencioso_si_falla`.

    **Congelado en `.0`:** `_tag_session_owner` tragaba toda excepción con `pass`, así que un
    hilo podía quedar sin dueño sin que nadie se enterara.

    **Cambio autorizado:** la función se eliminó. La propiedad es ahora explícita —nace en el
    bootstrap o se reclama con capacidad— y el claim **falla ruidoso** si no toca exactamente
    una fila, en vez de callar.
    """
    import inspect

    from app.sesion_autoridad import _ejecutar_claim

    assert "async def _tag_session_owner" not in CHAT.read_text(encoding="utf-8")
    cuerpo = inspect.getsource(_ejecutar_claim)
    assert "raise AccesoDenegado" in cuerpo and "rollback" in cuerpo


# ── INVENTARIO COMPLETO · todo endpoint donde `session_id` da acceso a estado ──────


def _inventario() -> dict[tuple[str, str], set[str]]:
    """Todos los endpoints de `chat.py` en los que `session_id` participa del acceso a
    estado del hilo — por parámetro, por `payload.session_id`, por `destinatario_session`
    o por lectura del checkpointer."""
    arbol = ast.parse(CHAT.read_text(encoding="utf-8"))
    fuera = {}
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
            cuerpo = ast.unparse(n)
            params = {a.arg for a in list(n.args.args) + list(n.args.kwonlyargs)}
            usa_sesion = ("session_id" in params or "sid" in params
                          or "payload.session_id" in cuerpo
                          or "destinatario_session" in cuerpo
                          or "aget_state" in cuerpo)
            if usa_sesion:
                ruta = s.split("(", 1)[1].split(",")[0].strip().strip("'\"")
                fuera[(metodo, ruta)] = {a for a in _AUTH if a in cuerpo}
            break
    return fuera


# Clasificación exigida por la revisión. Congelada: si aparece un endpoint nuevo que use
# `session_id`, el test de exhaustividad falla y obliga a clasificarlo antes de mergear.
CLASIFICACION = {
    # ── owner-auth: exigen identidad del propietario ──────────────────────────────
    ("PATCH",  "/sessions/{session_id}"):        "owner-auth",
    ("DELETE", "/sessions/{session_id}"):        "owner-auth",
    ("POST",   "/sessions/{session_id}/share"):  "owner-auth",
    ("DELETE", "/sessions/{session_id}/share"):  "owner-auth",

    # ── public-by-design: acceso explícito por capacidad, no por identidad ────────
    ("GET",    "/shared/{token}"):               "public-by-design",

    # ── internal/irrelevant: `session_id` no es la autoridad ─────────────────────
    ("GET",    "/sessions"):                     "internal",   # filtra por usuario; [] si invitado

    # ── anonymous-capability-required: HOY basta con conocer el id ───────────────
    ("POST",   "/"):                             "capability-required",  # escribe Y reclama
    ("GET",    "/{session_id}/history"):         "capability-required",
    ("GET",    "/{session_id}/handoff"):         "capability-required",
    ("POST",   "/{session_id}/handoff"):         "capability-required",
    ("POST",   "/{session_id}/handoff/mensaje"): "capability-required",
    ("POST",   "/{session_id}/handoff/push"):    "capability-required",
    ("GET",    "/{session_id}/intencion"):       "capability-required",
    ("POST",   "/comparar"):                     "capability-required",
    ("POST",   "/lead-contacto"):                "capability-required",
    ("GET",    "/notificaciones"):               "capability-required",
    ("GET",    "/conversaciones"):               "capability-required",
    ("POST",   "/notificaciones/leidas"):        "capability-required",
}


def test_el_inventario_de_endpoints_session_scoped_esta_completo():
    """AMPLIACIÓN DEL ALCANCE, pedida en revisión.

    La primera pasada cubrió cinco endpoints. El barrido sistemático encuentra **18**. Si
    AUTH-READ-GATE.1 cerrara solo los que vimos primero, dejaría puertas equivalentes
    abiertas — la campana y la bandeja, entre otras.
    """
    encontrados = set(_inventario())
    clasificados = set(CLASIFICACION)
    assert encontrados - clasificados == set(), (
        f"endpoints session-scoped SIN clasificar: {sorted(encontrados - clasificados)}"
    )
    assert clasificados - encontrados == set(), (
        f"clasificados que ya no existen: {sorted(clasificados - encontrados)}"
    )
    assert len(encontrados) == 18


@pytest.mark.parametrize("clave", [k for k, v in CLASIFICACION.items() if v == "owner-auth"])
def test_los_owner_auth_exigen_identidad(clave):
    assert "get_current_user" in _inventario()[clave]


def test_la_campana_y_la_bandeja_usan_el_session_id_como_AUTORIDAD():
    """LA PUERTA QUE FALTABA. Los tres endpoints de avisos aceptan `session_id` y lo usan
    para decidir qué filas devolver o mutar:

        WHERE (user_id  IS NOT NULL AND destinatario_user_id = :u)
           OR (session  IS NOT NULL AND destinatario_session = :s)

    Es un **OR**, no un `else`. Así que conocer el `session_id` concede acceso a los avisos
    del hilo — y además un autenticado que pase un `session_id` ajeno también los recibe,
    porque la segunda rama no comprueba propiedad.

    Es exactamente la semántica que el gate pretende eliminar, en otro sitio.
    """
    src = CHAT.read_text(encoding="utf-8")
    assert src.count("destinatario_session = CAST(:s AS text)") >= 3
    for fn in ("notificaciones", "conversaciones", "marcar_leidas"):
        try:
            cuerpo = ast.unparse(_fn(fn))
        except StopIteration:
            continue
        assert "destinatario_session" in cuerpo


def test_hay_endpoints_sin_ninguna_auth_mas_alla_de_los_cinco_iniciales():
    """`/comparar`, `/lead-contacto` y `/handoff/push` tampoco declaran auth."""
    inv = _inventario()
    for clave in [("POST", "/comparar"), ("POST", "/lead-contacto"),
                  ("POST", "/{session_id}/handoff/push")]:
        assert inv[clave] == set(), f"{clave} ya no está desprotegido — revisar §3"


# ── BOOTSTRAP · el hueco que impide emitir la capability con seguridad ─────────────


def test_REGRESION_una_sesion_anonima_SI_deja_fila_autoritativa():
    """`EXPECTED_POLICY_CHANGE` · antes: `test_una_sesion_anonima_NO_deja_fila_en_chat_sessions`.

    **Congelado en `.0`:** los hilos anónimos nunca creaban fila, así que `chat_sessions` no
    era el catálogo de sesiones y el servidor no podía distinguir nacimiento de reanudación.

    **Cambio autorizado:** el bootstrap inserta SIEMPRE, con `creada_por_servidor = true`.
    Esa fila es la frontera que faltaba.

    Lo que NO cambia: los hilos anónimos **anteriores** al gate siguen sin fila, y por eso no
    se pueden reanudar. Es la pérdida deliberada de compatibilidad de la migración 027.
    """
    import inspect

    from app.sesion_autoridad import _ejecutar_creacion

    cuerpo = inspect.getsource(_ejecutar_creacion)
    assert "INSERT INTO chat_sessions" in cuerpo
    assert "creada_por_servidor" in cuerpo, "la frontera creación≠reanudación"
    assert "ON CONFLICT (session_id) DO NOTHING" in cuerpo
    assert "RETURNING session_id" in cuerpo


def test_el_session_id_anonimo_lo_elige_el_cliente_sin_control_del_servidor():
    """Refuerza el punto anterior: el servidor recibe un `session_id` ya hecho y no puede
    saber si es nuevo. `ChatRequest` solo lo genera cuando el cliente **no** lo manda."""
    from app.routers.chat import ChatRequest

    elegido = ChatRequest(message="hola", session_id="qr-cualquier-cosa-que-yo-invente")
    assert elegido.session_id == "qr-cualquier-cosa-que-yo-invente"


def test_no_existe_hoy_ninguna_operacion_atomica_de_creacion_de_sesion():
    """No hay endpoint ni sentencia que cree la sesión distinguiendo creación de existencia.
    El único `INSERT ... ON CONFLICT` sobre `chat_sessions` en el camino del chat es el de
    `_tag_session_owner`, que ni siquiera corre para anónimos."""
    src = CHAT.read_text(encoding="utf-8")
    assert "xmax" not in src, "no hay detección de INSERT-vs-UPDATE"
    assert "RETURNING" not in src.split("_tag_session_owner")[1][:600]


# ── El device_key sigue sin ser credencial de nada ─────────────────────────────────


def test_el_device_key_no_esta_ligado_a_chat_sessions():
    """No fue emitido como credencial, no está acotado a una conversación y no aparece en la
    tabla de sesiones. Que el cliente lo controle NO es lo que lo descalifica —todo bearer
    está en poder del cliente—: lo descalifica que nunca fue una credencial de este recurso.
    """
    for m in ("006_chat_sessions.sql", "008_auth_roles.sql"):
        assert "device" not in (RAIZ / "migrations" / m).read_text(encoding="utf-8").lower()
    chat = CHAT.read_text(encoding="utf-8")
    assert "device_key" not in chat


def test_el_device_key_ya_tiene_un_proposito_previo_y_una_obligacion():
    """Ampliarlo no es una decisión de arquitectura: la migración 024 ya lo declara dato
    personal con obligación de supresión."""
    m024 = (RAIZ / "migrations" / "024_visita.sql").read_text(encoding="utf-8")
    assert "dato personal" in m024 and "supresión debe alcanzar" in m024


# ── Lo que el session_id ES hoy ────────────────────────────────────────────────────


def test_el_session_id_funciona_como_credencial_sin_haber_sido_disenado_para_serlo():
    """Resumen ejecutable de la unidad: el mismo valor identifica el recurso Y da acceso.

    Y no cumple ninguna propiedad de credencial: no es rotable, no es revocable, viaja en
    el cuerpo de peticiones y —en el carril QR— codifica estructura legible
    (`qr-{activo}-{device}`), así que ni siquiera es opaco.
    """
    chat = CHAT.read_text(encoding="utf-8")
    assert "qr-{activo_uuid(36)}-{device_uuid}" in chat
    assert "revoke" not in chat.lower() and "rotate" not in chat.lower()
    # El único mecanismo revocable que existe hoy es el de compartir.
    assert "share_token = NULL" in chat or "is_public = false" in chat
