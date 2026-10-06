"""Plan 1.1 · TR-1 · la puerta de alerta sin consumidor queda RETIRADA (OFD-02 = A).

La puerta suave ofrecía «avisar cuando apareciera algo que encajara» y pedía un correo para
eso. Ningún código lee `contacto` ni `demanda`, ni envía aviso alguno: la promesa era falsa por
construcción. OFD-02 = A: se retira hasta que exista el consumidor, y las filas ya recogidas se
rigen por la política de retención de E3.1-R — no se reinterpretan para otro propósito.

Este fichero fija que la retirada no se deshace sin que alguien lo decida:
  1. `/api/v1/alertas` no existe;
  2. ningún código productivo escribe `contacto` ni `demanda`;
  3. ninguno las lee;
  4. el contrato conserva `puerta` (siempre None) — el comportamiento de los dos caminos del
     chat, con endpoint y grafo reales, está en `tests/test_puerta_persistencia.py`;
  5. el frontend no importa ni pinta la puerta, ni aunque un backend viejo la mande;
  6. ningún texto visible —ni `aria-label`, ni `placeholder`— conserva la promesa;
  7. el prompt prohíbe prometer un aviso futuro y un detector MEDIA lo mide en la prosa;
  8. el opt-in de reenganche (P5), que SÍ tiene consumidor, queda intacto: es TR-2/TR-5.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
APP_JSX = RAIZ / "frontend" / "src" / "App.jsx"


def _norm(t: str) -> str:
    s = unicodedata.normalize("NFD", t or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def _fuentes_backend():
    yield from (RAIZ / "app").rglob("*.py")
    yield from (RAIZ / "scripts").rglob("*.py")
    yield from (RAIZ / "evals").rglob("*.py")
    yield RAIZ / "main.py"


def _fuentes_frontend():
    for p in (RAIZ / "frontend" / "src").rglob("*.js*"):
        if ".test." not in p.name:
            yield p


# ── 1 · la ruta no existe ──────────────────────────────────────────────────────────────

def test_1_alertas_no_esta_en_el_inventario_de_rutas():
    import main
    rutas = {getattr(r, "path", "") for r in main.app.routes}
    assert not [p for p in rutas if "alerta" in p], "reapareció una ruta de alertas"
    assert not (RAIZ / "app" / "routers" / "alertas.py").exists()


@pytest.mark.parametrize("rol", [None, "cliente", "corredor"])
def test_1b_post_a_alertas_no_llega_a_ningun_endpoint(rol):
    from fastapi.testclient import TestClient

    import main
    from app.auth import CurrentUser, get_current_user, get_optional_user
    app = main.app
    if rol:
        u = CurrentUser(user_id="00000000-0000-0000-0000-0000000000a1", email="x@p.test", rol=rol)
        app.dependency_overrides[get_current_user] = lambda: u
        app.dependency_overrides[get_optional_user] = lambda: u
    try:
        r = TestClient(app).post("/api/v1/alertas",   # sin `with`: no corre el lifespan
                                 json={"session_id": "qr-x-y", "email": "a@b.co"})
    finally:
        app.dependency_overrides.clear()
    assert r.status_code in (404, 405), r.status_code


# ── 2 y 3 · ningún código productivo escribe NI lee `contacto` / `demanda` ────────────

_ESCRIBE = re.compile(r"\b(insert\s+into|update|delete\s+from|truncate(\s+table)?)\s+(public\.)?"
                      r"(contacto|demanda)\b", re.I)
_LEE = re.compile(r"\b(from|join)\s+(public\.)?(contacto|demanda)\b", re.I)
_DDL = re.compile(r"\bcreate\s+(table|unique\s+index|index)\b[^;\"]*\b(contacto|demanda)\b", re.I)


def _hits(rx):
    out = []
    for f in _fuentes_backend():
        for i, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if rx.search(linea):
                out.append(f"{f.relative_to(RAIZ).as_posix()}:{i}: {linea.strip()[:90]}")
    return out


def test_2_ningun_codigo_productivo_escribe_contacto_ni_demanda():
    assert _hits(_ESCRIBE) == [], "STOP_NEW_COLLECTION: apareció un escritor de contacto/demanda"


def test_2b_ningun_codigo_productivo_crea_esas_tablas_al_vuelo():
    """`ensure_alertas` las creaba en el primer POST. Sin ese DDL en runtime, en un entorno donde
    no existían no vuelven a nacer por la puerta de atrás. La migración 025 sigue intacta."""
    assert _hits(_DDL) == []
    assert (RAIZ / "migrations" / "025_contacto_demanda.sql").exists()


def test_3_ningun_codigo_productivo_lee_contacto_ni_demanda():
    """KEEP_UNTIL_RETENTION_POLICY sin reinterpretar: las filas históricas no alimentan
    reenganche, ventas, métricas ni comunicación. Un lector nuevo es una finalidad nueva."""
    assert _hits(_LEE) == [], "apareció un lector de contacto/demanda: finalidad no autorizada"


def test_3b_el_frontend_no_llama_a_alertas():
    for f in _fuentes_frontend():
        assert "api/v1/alertas" not in f.read_text(encoding="utf-8"), f.name


# ── 4 y 5 · el contrato conserva `puerta`, y el backend no la calcula ─────────────────

def test_4_la_clave_puerta_sigue_en_el_contrato_y_vale_none_por_defecto():
    from app.routers.chat import ChatResponse
    assert "puerta" in ChatResponse.model_fields
    assert ChatResponse.model_fields["puerta"].default is None


def test_4b_el_chat_no_calcula_ni_marca_la_puerta():
    import app.puerta as puerta
    import app.routers.chat as chat
    for nombre in ("_puerta_del_turno", "_marcar_puerta_ofrecida", "_pidio_corredor"):
        assert not hasattr(chat, nombre), f"reapareció {nombre}"
    for nombre in ("PROMESA", "evaluar_puerta", "pidio_aviso", "_hay_algo_que_sirva",
                   "_criterio_legible", "criterio_whitelist", "ENCAJE_SUFICIENTE"):
        assert not hasattr(puerta, nombre), f"reapareció app.puerta.{nombre}"
    fuente = (RAIZ / "app" / "routers" / "chat.py").read_text(encoding="utf-8")
    assert "evaluar_puerta" not in fuente and '"puerta_ofrecida": True' not in fuente


def test_4c_puerta_ofrecida_sigue_declarada_pero_inerte():
    """Declarada por compatibilidad con los checkpoints que ya la llevan (LangGraph descarta en
    silencio las claves no declaradas); nadie la escribe ni la lee."""
    from app.agent.state import AgentState
    assert "puerta_ofrecida" in AgentState.__annotations__
    # El uso real era siempre como CLAVE de estado: `{"puerta_ofrecida": True}` para escribir y
    # `.get("puerta_ofrecida")` para leer. Los comentarios que cuentan la retirada no cuentan.
    uso = re.compile(r"[\"']puerta_ofrecida[\"']")
    for f in _fuentes_backend():
        assert not uso.search(f.read_text(encoding="utf-8")), f"{f.name} vuelve a usar la marca"


# ── 6, 7 y 8 · frontend y textos visibles ─────────────────────────────────────────────

def test_6_el_frontend_no_importa_ni_pinta_la_puerta():
    assert not (RAIZ / "frontend" / "src" / "PuertaAlerta.jsx").exists()
    js = APP_JSX.read_text(encoding="utf-8")
    assert "PuertaAlerta" not in js
    assert "msg.puerta" not in js, "el mensaje vuelve a leer la puerta"


def test_7_un_backend_viejo_que_mande_puerta_no_la_hace_reaparecer():
    """El frontend nuevo IGNORA `panel.puerta`: el mapeo del panel ya no la copia al mensaje,
    así que aunque llegue un objeto no hay ningún campo que pintar."""
    js = APP_JSX.read_text(encoding="utf-8")
    on_panel = js[js.index("onPanel: (panel) =>"):]
    on_panel = on_panel[:on_panel.index("})")]
    codigo = "\n".join(l for l in on_panel.splitlines() if not l.strip().startswith("//"))
    assert "puerta" not in codigo, "onPanel vuelve a copiar panel.puerta al mensaje"


# Barrido de promesas de aviso futuro sobre TODO texto productivo (backend y frontend), con una
# lista blanca CERRADA y exacta: el test exige igualdad, así que falla tanto si aparece una
# promesa nueva como si una entrada de la lista deja de existir sin que nadie lo revise.
_PROMESA = [
    re.compile(r"\bte (escribo|aviso|avisamos|avisaremos|avisare|notific\w+|escribire|escribiremos)\b"
               r"[^.\n]{0,40}\b(cuando|si) (aparezca|aparece|haya|salga|sale)\b"),
    re.compile(r"te escribo solo cuando"),
    re.compile(r"tu correo para el aviso"),
    re.compile(r"\bavisame\b"),
]
_LISTA_BLANCA = {
    # P5 · opt-in de reenganche. Plan 1.1 · TR-2 (actualización esperada): sus dos entradas
    # —«te avisamos solo si aparece algo verificado que te calce» y «avísame de novedades
    # verificadas»— SALEN de la lista porque el texto se corrigió (D-4) y ya no promete: el
    # copy nuevo vive en frontend/src/avisoReenganche.js y este barrido no encuentra promesa en él.
    # La PROHIBICIÓN en el prompt cita la frase para prohibirla.
    ("app/agent/graph.py", "\"te escribo si sale\"): no hay nada que lo vaya a hacer"),
    # El detector documenta lo que caza y lo que no.
    ("app/verificacion_prosa.py", "«te aviso cuando aparezca», «te escribo si sale algo»"),
    ("app/verificacion_prosa.py", "(«avisame de novedades verificadas»), que es un imperativo"),
}


def _promesas():
    hallados = set()
    for f in [*_fuentes_backend(), *_fuentes_frontend()]:
        rel = f.relative_to(RAIZ).as_posix()
        for linea in f.read_text(encoding="utf-8").splitlines():
            n = _norm(linea)
            if any(rx.search(n) for rx in _PROMESA):
                marca = next((m for (r, m) in _LISTA_BLANCA if r == rel and m in n), None)
                hallados.add((rel, marca or n.strip()[:120]))
    return hallados


def test_8_ninguna_promesa_de_aviso_sobrevive_fuera_de_la_lista_blanca():
    assert _promesas() == _LISTA_BLANCA


def test_8b_accesibilidad_y_placeholders_no_conservan_la_puerta():
    prohibidos = ("tu correo para el aviso", "¿te aviso cuando aparezca", "tu@correo.com",
                  "no pudimos guardar tu aviso")
    for f in _fuentes_frontend():
        n = _norm(f.read_text(encoding="utf-8"))
        for p in prohibidos:
            assert _norm(p) not in n, f"{f.name} conserva «{p}»"


# ── 9 · B2 sigue vivo, ahora en todo turno ────────────────────────────────────────────

def test_9_b2_detecta_el_contacto_pedido_en_prosa_sin_necesidad_de_puerta():
    from app.verificacion_prosa import MEDIA, verificar_prosa
    h = [x for x in verificar_prosa("Déjame tu correo y te aviso.", cards=None)
         if x["codigo"] == "contacto_pedido_en_prosa"]
    assert h and h[0]["gravedad"] == MEDIA


# ── 10 y 11 · la promesa improvisada del modelo ───────────────────────────────────────

def test_10_el_prompt_prohibe_prometer_un_aviso_futuro():
    from app.agent.graph import SYSTEM_PROMPT
    texto = SYSTEM_PROMPT.content
    assert "NUNCA prometas avisar, escribir, contactar ni notificar al usuario más adelante" in texto
    # SEC-X3-R0: la excepción ya no es «un handoff que la tool confirmó» —la tool no tiene
    # efecto—, sino el contacto que la PERSONA pidió con el control explícito.
    assert "después de que la persona lo pidió con «Hablar con el" in texto, (
        "la excepción del handoff real desapareció")
    assert "tool_connect_with_broker confirmó" not in texto, (
        "el prompt volvió a afirmar que la tool confirma un handoff")


@pytest.mark.parametrize("frase", [
    "Te aviso cuando aparezca algo así.",
    "Te escribo si sale algo en Cumbayá.",
    "Te notificaremos cuando haya opciones.",
    "¿Te aviso cuando aparezca algo así?",
    "Le avisaré en cuanto salga un depa.",
    "Contexto te avisará apenas aparezca.",
    "Te mantendré al tanto.",
    "Te mando un correo cuando haya novedades.",
    "Te escribo por correo si aparece algo.",
])
def test_11_el_detector_caza_la_promesa_propia(frase):
    from app.verificacion_prosa import MEDIA, verificar_prosa
    h = [x for x in verificar_prosa(frase, cards=None) if x["codigo"] == "aviso_prometido_en_prosa"]
    assert h, f"no se detectó: {frase!r}"
    assert h[0]["gravedad"] == MEDIA and h[0]["evidencia"]


@pytest.mark.parametrize("frase", [
    "El corredor te escribirá hoy mismo.",                     # handoff real: tercera persona
    "Un corredor lo contactará pronto.",
    "Tu solicitud quedó registrada; el corredor te escribirá a tu correo.",
    "Te aviso que este inmueble no acepta mascotas.",          # informa ahora, no promete
    "Te contacto con el corredor que maneja este inmueble.",   # conecta, no escribe después
    "Puedes activar «Avísame de novedades verificadas» debajo.",  # P5: nombre del botón
    "¿Quieres que el corredor te contacte?",
    "Si aparece algo, lo verás aquí cuando vuelvas.",
    "",
])
def test_11b_el_detector_no_marca_lo_legitimo(frase):
    from app.verificacion_prosa import verificar_prosa
    assert [x for x in verificar_prosa(frase, cards=None)
            if x["codigo"] == "aviso_prometido_en_prosa"] == [], f"falso positivo: {frase!r}"


def test_11c_el_detector_mide_y_no_bloquea():
    """MEDIA → el turno queda en WARNING, no en FAILED. Y la función es pura: devuelve hallazgos,
    no toca la respuesta."""
    from app.contracts.decision_v0 import VerificationStatus
    from app.decision.verify import auditar_explicacion
    texto = "Hoy no tengo nada que te calce. Te aviso cuando aparezca algo."
    explicacion, hallazgos = auditar_explicacion(texto, cards=None)
    assert any(h["codigo"] == "aviso_prometido_en_prosa" for h in hallazgos)
    assert explicacion.verification_status is VerificationStatus.WARNING


def test_11d_el_detector_tambien_corre_con_panel():
    from app.verificacion_prosa import verificar_prosa
    cards = [{"id": "a1", "precio": 700, "direccion_estandarizada": "Calle 1"}]
    assert any(x["codigo"] == "aviso_prometido_en_prosa"
               for x in verificar_prosa("Esta es la opción. Te aviso si sale otra.", cards=cards))


# ── 12 · P5 (reenganche) intacto: no es TR-1 ──────────────────────────────────────────

def test_12_el_opt_in_de_reenganche_sigue_en_pie():
    """P5 no se retiró en TR-1 y sigue en pie. Plan 1.1 · TR-2 (actualización esperada): su
    texto cambió (D-4) —ya no promete— y ahora se puede desactivar y cerrar; el texto exacto
    lo fija tests/test_tr2_consentimiento.py."""
    import main
    js = APP_JSX.read_text(encoding="utf-8")
    assert "COPY_AVISO.boton" in js and "COPY_AVISO.dejar" in js
    assert "/api/v1/chat/lead-contacto" in js
    rutas = {getattr(r, "path", "") for r in main.app.routes}
    assert "/api/v1/chat/lead-contacto" in rutas
