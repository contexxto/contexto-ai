"""
Tests del motor de LLEGADA (app/llegada.py) — de qué canal viene una visita.

Lo que hace valioso a este módulo es una sola cosa: hasta ahora `fuente` era la
constante 'QR' para todo el mundo y no había captura de utm ni de referrer en ningún
punto del repo. Los dos motores de adquisición declarados (el canal y la estrategia AEO)
no tenían forma de medirse.

Dos contratos se prueban con más dureza que el resto:
  · `motor_respuesta` — es la tesis AEO hecha medible; si este bucket falla, la
    inversión en respuestas de IA sigue siendo invisible.
  · `directo` significa "no sabemos", nunca "vino solo". Es el cajón honesto, hermano
    de `encaje.score = None`.

Puros: sin DB, sin red, sin LLM.
"""
import pytest

from app.llegada import (
    CANALES,
    SUPERFICIES,
    clasificar_canal,
    limpiar_referrer,
    normalizar_llegada,
    normalizar_superficie,
)


# ── La tesis AEO, por fin medible ───────────────────────────────────────────────────

@pytest.mark.parametrize("ref", [
    "https://chatgpt.com/c/abc-123",
    "https://www.perplexity.ai/search/algo",
    "https://claude.ai/chat/xyz",
    "https://gemini.google.com/app",
    "https://copilot.microsoft.com/",
])
def test_motor_de_respuesta_se_reconoce(ref):
    assert clasificar_canal(referrer=ref) == "motor_respuesta"


def test_gemini_no_se_confunde_con_buscador():
    # gemini.google.com contiene 'google.' — el orden de la tabla decide, y motor_respuesta
    # va PRIMERO a propósito: confundirlos borraría justo la señal que se quiere medir.
    assert clasificar_canal(referrer="https://gemini.google.com/app") == "motor_respuesta"
    assert clasificar_canal(referrer="https://www.google.com/search") == "buscador"


# ── Precedencia: la utm manda sobre el referrer ─────────────────────────────────────

@pytest.mark.parametrize("medium", ["cpc", "paid", "ads", "ad", "ppc", "display", "retargeting"])
def test_utm_de_pago_es_campana(medium):
    assert clasificar_canal(utm_medium=medium, utm_source="meta") == "campana"


def test_la_utm_gana_al_referrer():
    # Alguien escribió la utm a propósito; el referrer lo pone el navegador. La evidencia
    # deliberada manda sobre la automática.
    assert clasificar_canal(utm_medium="cpc", utm_source="meta",
                            referrer="https://www.google.com/search") == "campana"


def test_utm_organica_no_es_campana():
    # utm sin medio de pago (la firma de un correo, el enlace del canal) NO es tráfico
    # comprado. Marcarla como campaña inflaría el costo por lead de una campaña real.
    assert clasificar_canal(utm_source="youtube", utm_medium="descripcion") == "social"
    assert clasificar_canal(utm_source="boletin", utm_medium="email") == "referido"


# ── El resto del mapa ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ref,esperado", [
    ("https://www.google.com/search?q=x", "buscador"),
    ("https://duckduckgo.com/", "buscador"),
    ("https://www.instagram.com/p/abc", "social"),
    ("https://www.youtube.com/watch", "social"),
    ("https://www.linkedin.com/feed", "social"),
    ("https://api.whatsapp.com/send", "mensajeria"),
    ("https://t.me/algo", "mensajeria"),
    ("https://elcomercio.com/nota", "referido"),
])
def test_mapa_de_hosts(ref, esperado):
    assert clasificar_canal(referrer=ref) == esperado


def test_navegacion_propia_no_es_una_llegada_nueva():
    # Moverse dentro de contexto no es entrar: contarlo como 'referido' inflaría el
    # embudo con tráfico propio.
    assert clasificar_canal(referrer="https://contexto.ai/a/123",
                            host_propio="contexto.ai") == "propio"
    assert clasificar_canal(referrer="https://www.contexto.ai/",
                            host_propio="contexto.ai") == "propio"
    # Y un host que solo TERMINA parecido no es propio.
    assert clasificar_canal(referrer="https://nocontexto.ai/",
                            host_propio="contexto.ai") == "referido"


def test_sin_ninguna_senal_es_directo_y_eso_significa_no_sabemos():
    assert clasificar_canal() == "directo"
    assert clasificar_canal(referrer="", utm_source="", utm_medium="") == "directo"
    # Un letrero YA IMPRESO (anterior a la marca) llega así, y sigue cayendo en 'directo'.
    # No es un error del conteo: de esos escaneos, honestamente, no sabemos.
    assert clasificar_canal(superficie="anuncio") == "directo"


# ── El letrero físico: la señal más fuerte, y la última que se podía medir (F4) ─────

def test_el_qr_del_letrero_se_distingue_de_directo():
    """La deuda que F0 dejó declarada. Alguien parado frente al inmueble, con el letrero
    delante, es la señal más fuerte del sistema — y era la única indistinguible de teclear
    la URL."""
    assert clasificar_canal(superficie="anuncio", utm_source="letrero",
                            utm_medium="qr") == "qr"


@pytest.mark.parametrize("medio", ["qr", "letrero", "lona", "pendon", "cartel"])
def test_los_marcadores_fisicos_de_lonas_y_pendones(medio):
    """LINDEN lista 'lonas y pendones' entre sus seis fuentes de leads y su CRM las
    colapsa todas en 'WEB'. Aquí se distinguen."""
    assert clasificar_canal(utm_medium=medio) == "qr"


def test_lo_fisico_gana_al_medio_de_pago():
    """Si un letrero se usa dentro de una campaña impresa, sigue siendo el letrero lo que
    la persona tuvo delante. El orden de precedencia lo afirma."""
    assert clasificar_canal(utm_source="letrero", utm_medium="cpc") == "qr"


def test_la_url_impresa_lleva_la_marca():
    """Contrato con el generador del letrero: si alguien quita el parámetro, el QR vuelve
    a ser indistinguible de una URL tecleada y el canal 'qr' deja de existir en los datos."""
    from app.routers.assets import _url_del_qr

    url = _url_del_qr("11111111-2222-3333-4444-555555555555")
    assert "/a/11111111-2222-3333-4444-555555555555" in url
    assert "utm_source=letrero" in url and "utm_medium=qr" in url
    # Y el pathname sigue siendo el que el frontend usa para anclar el inmueble: el
    # `deepLinkId` matchea solo el path, así que la query no rompe el anclaje.
    assert url.split("?")[0].endswith("/a/11111111-2222-3333-4444-555555555555")


def test_el_canal_siempre_sale_de_la_lista_cerrada():
    entradas = [None, "", "  ", "basura", "https://", "javascript:alert(1)", 42, {"a": 1}]
    for e in entradas:
        assert clasificar_canal(referrer=e, utm_source=e, utm_medium=e) in CANALES


# ── Privacidad: el referrer entra minimizado ────────────────────────────────────────

def test_el_referrer_pierde_la_query_donde_viajan_los_datos():
    # Términos de búsqueda, tokens de sesión y correos viajan en la query. Para
    # clasificar el canal basta el host; guardar la query sería recolectar de más.
    assert limpiar_referrer("https://www.google.com/search?q=divorcio+mudanza+quito") \
        == "www.google.com/search"
    assert limpiar_referrer("https://x.com/i/status/1?token=abc123#frag") == "x.com/i/status/1"


@pytest.mark.parametrize("basura", [None, "", "   ", 42, [], {}, "://///", "no-es-una-url"])
def test_referrer_basura_no_revienta(basura):
    r = limpiar_referrer(basura)
    assert r is None or isinstance(r, str)


def test_referrer_se_acota():
    largo = "https://ejemplo.com/" + ("a" * 5000)
    assert len(limpiar_referrer(largo)) <= 500


# ── Superficie ──────────────────────────────────────────────────────────────────────

def test_superficie_lista_cerrada():
    assert normalizar_superficie("anuncio") == "anuncio"
    assert normalizar_superficie("conversacion_compartida") == "conversacion_compartida"
    # Lo desconocido cae a 'home', no se inventa una superficie nueva.
    for basura in (None, "", "inventada", 42, "ANUNCIO "):
        assert normalizar_superficie(basura) in SUPERFICIES


# ── La puerta única de entrada del dato ─────────────────────────────────────────────

def test_normalizar_llegada_devuelve_la_fila_completa():
    fila = normalizar_llegada({
        "superficie": "anuncio",
        "utm_source": "meta", "utm_medium": "cpc", "utm_campaign": "quito-ago",
        "utm_content": "video-1",
        "referrer": "https://l.facebook.com/l.php?u=algo&token=secreto",
    })
    assert fila["superficie"] == "anuncio"
    assert fila["canal"] == "campana"
    assert fila["utm_campaign"] == "quito-ago"
    assert "token" not in (fila["referrer"] or "")   # la query no sobrevive


def test_normalizar_llegada_con_payload_vacio_o_basura():
    for entrada in ({}, None, {"superficie": 9, "referrer": [], "utm_source": {}}):
        fila = normalizar_llegada(entrada)
        assert fila["canal"] in CANALES
        assert fila["superficie"] in SUPERFICIES


def test_los_campos_utm_se_acotan():
    fila = normalizar_llegada({"utm_campaign": "x" * 5000, "utm_source": "y" * 5000})
    assert len(fila["utm_campaign"]) <= 200 and len(fila["utm_source"]) <= 200


# ── El contrato con el frontend (las claves exactas que manda registrarLlegada) ─────

@pytest.mark.parametrize("payload,canal", [
    # El escaneo de un letrero: sin referrer, sin utm. Cae en 'directo' = no medido.
    ({"superficie": "anuncio", "utm_source": None, "utm_medium": None,
      "utm_campaign": None, "utm_content": None, "referrer": ""}, "directo"),
    # Campaña de Meta a un inmueble concreto.
    ({"superficie": "anuncio", "utm_source": "meta", "utm_medium": "cpc",
      "utm_campaign": "quito-ago", "utm_content": "v1", "referrer": ""}, "campana"),
    # Alguien llegó porque un motor de respuesta citó a Contexto. LA tesis AEO.
    ({"superficie": "home", "utm_source": None, "utm_medium": None, "utm_campaign": None,
      "utm_content": None, "referrer": "https://www.perplexity.ai/search/vivir-en-quito"},
     "motor_respuesta"),
    # La conversación de otro, abierta desde un enlace compartido.
    ({"superficie": "conversacion_compartida", "utm_source": None, "utm_medium": None,
      "utm_campaign": None, "utm_content": None,
      "referrer": "https://web.whatsapp.com/"}, "mensajeria"),
])
def test_payload_real_del_frontend(payload, canal):
    """El frontend manda SIEMPRE todas las claves, con None donde no hay dato (es lo que
    devuelve URLSearchParams.get). Si el contrato se rompe, se rompe aquí y no en prod."""
    fila = normalizar_llegada(payload)
    assert fila["canal"] == canal
    assert fila["superficie"] == payload["superficie"]
