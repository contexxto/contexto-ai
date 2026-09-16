"""La política TLS del núcleo, en UN solo sitio.

POR QUÉ EXISTE ESTE MÓDULO. Contra la misma base tiran dos stacks que no comparten ni una
línea de código: SQLAlchemy/asyncpg (Python puro) para los datos, y psycopg/libpq (C) para
el pool del checkpointer. Los dos leen la MISMA `DATABASE_URL_OVERRIDE`. Y está medido que
esa URL compartida **no puede** expresar modo + ancla de forma compatible con ambos a la
vez: lo que satisface a uno rompe o degrada al otro. De ahí la decisión de R2A.2 — la
política vive en el código, no en la cadena de conexión ni en el panel.

Si la política se escribiera dos veces, una en `database.py` y otra en `graph.py`, la
pregunta "¿qué verifica producción?" tendría dos respuestas que podrían divergir sin que
nadie lo note. Aquí hay una.

QUÉ GARANTIZA, para host remoto:

  * `verify-full` en los dos stacks: se valida la CADENA contra el bundle **y** el HOSTNAME.
  * Se rechaza cualquier parámetro TLS embebido en la URL compartida (G1).
  * Se valida el bundle ANTES de construir engine o pool (G2).
  * Falla cerrado, y falla temprano.

Y NO SE APAGA. No hay bandera de entorno, ni `DB_TLS_INSECURE`, ni fallback a `prefer`. La
exención de desarrollo es una propiedad de la URL —apuntar a loopback— y no un interruptor,
porque un interruptor acaba encendido en producción el día que alguien depura con prisa.

`verify-ca` no es un estado intermedio aceptable: valida la CA pero no el hostname, así que
no cierra el MITM con un certificado válido emitido para otro nombre. La distinción entre
"ancla equivocada" y "hostname equivocado" se obtiene en las pruebas (T2 vs T3), no
exponiendo producción a media verificación.
"""
from __future__ import annotations

import ipaddress
import ssl
from pathlib import Path
from urllib.parse import parse_qsl, urlparse

# Ruta ESTABLE dentro de la imagen, colocada por un `COPY` propio del Dockerfile (R2B2).
# El bundle está versionado en `certs/supabase/` para poder rotar; esta ruta no se mueve.
RUTA_BUNDLE = "/app/certs/supabase-ca-bundle.pem"


def _ruta(ruta_bundle: "str | Path | None") -> "str | Path":
    """Resuelve la ruta del bundle LEYENDO la constante en tiempo de llamada.

    Parece un rodeo y no lo es: un `ruta_bundle=RUTA_BUNDLE` como valor por defecto se
    enlaza cuando se define la función, así que cambiar `RUTA_BUNDLE` después no tendría
    ningún efecto. Las pruebas necesitan apuntar al bundle versionado del repo —el que
    viaja en todo checkout— sin que exista una vía de producción para desviar el ancla.
    """
    return RUTA_BUNDLE if ruta_bundle is None else ruta_bundle

# ── G1 · qué NO puede venir en la URL compartida ──────────────────────────────────────
# REGLA, no lista cerrada: cualquier clave que empiece por `ssl`, más las de abajo. Se
# eligió una regla porque la lista real depende de la versión del driver y crece sola —
# medido el 2026-09-16 sobre las versiones pineadas:
#
#   libpq 17.0 (la de producción, rueda manylinux de psycopg[binary]==3.2.3):
#     sslmode sslrootcert sslcert sslkey sslcrl sslcrldir sslnegotiation sslcertmode
#     sslcompression sslpassword sslsni ssl_min_protocol_version ssl_max_protocol_version
#     gssencmode gssdelegation gsslib requirepeer require_auth
#   asyncpg 0.30.0:
#     ssl sslmode sslrootcert sslcert sslkey sslcrl sslnegotiation ssl_negotiation
#     sslpassword ssl_min_protocol_version ssl_max_protocol_version
#
# `sslcertmode` y `sslnegotiation` no existen en libpq 14 —la rueda de Windows— y sí en la
# 17. Una lista literal escrita mirando el portátil habría dejado dos puertas abiertas en
# producción. El prefijo las cubre, y cubrirá las que añada libpq 18.
_EXTRA_PROHIBIDAS = frozenset({
    # Cifrado GSSAPI: puede establecer un canal cifrado EN LUGAR de TLS, con lo que toda
    # la política de verificación de certificados deja de aplicarse. No es un parámetro
    # "ssl", pero decide exactamente lo mismo que decidimos aquí.
    "gssencmode",
    # Heredada de libpq ≤ 13. Sigue aceptándose por compatibilidad en cadenas viejas.
    "requiressl",
})


class TLSPolicyError(RuntimeError):
    """La política TLS del núcleo no se puede satisfacer. MENSAJE SANEADO.

    CONTRATO: el texto puede nombrar PARÁMETROS y RUTAS de la política, nunca la cadena de
    conexión, el host, el usuario ni la contraseña. La razón es la misma fuga que se cerró
    en R2B1: esto se levanta durante el arranque, y el lifespan de Starlette mete el
    traceback en `lifespan.startup.failed` mientras uvicorn lo registra con `exc_info` —
    dos superficies que publican lo que traiga el mensaje.

    Por eso, al envolver una excepción del driver o del sistema de ficheros, se usa
    `raise ... from None` y NUNCA `from exc`: medido en R2B1, `from exc` filtra igual que
    un `raise` desnudo. `from None` marca `__suppress_context__` para que los formateadores
    estándar no presenten la original; **no** la borra — `__context__` sigue apuntando a
    ella. Es un contrato de no exposición en las superficies verificadas, no de ausencia
    en memoria.
    """


# ── Clasificación loopback vs remoto ──────────────────────────────────────────────────
def _es_host_loopback(host: str) -> bool:
    if not host:
        return False
    if host.strip().lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip()).is_loopback   # 127.0.0.0/8 y ::1
    except ValueError:
        return False                                             # es un nombre, no una IP


def hosts_declarados(url: str) -> list[str]:
    """TODOS los hosts que la URL declara, no sólo el del netloc.

    ESTO ES EL ARREGLO DE UN BYPASS COMPLETO, reproducido el 2026-09-16. Mirar sólo
    `urlparse(url).hostname` deja pasar esto:

        postgresql+asyncpg://u:p@localhost:5432/postgres?host=aws-1-…pooler.supabase.com

    El netloc dice `localhost`, así que la política lo declaraba exento y devolvía `{}` —
    ni TLS, ni G1, ni nada. Pero LOS DOS DRIVERS HONRAN EL PARÁMETRO: el dialecto asyncpg de
    SQLAlchemy lo resuelve en `create_connect_args` y libpq lo toma de la query del URI.
    Medido: ambos acababan conectando al host remoto con el modo por defecto (`prefer`),
    que es exactamente el estado del que esta unidad dice sacarnos. Y no es ningún truco:
    `?host=` es sintaxis documentada de los dos.

    `hostaddr` es la variante con más filo: libpq conserva `host` para verificar el
    certificado pero abre el TCP contra la IP de `hostaddr`. Una URL con netloc `localhost`
    y `?hostaddr=<ip remota>` parecía local por partida doble.

    libpq además admite listas separadas por comas en ambos, así que se parten.
    """
    try:
        partes = urlparse(url)
    except ValueError:
        return []
    hosts = []
    if partes.hostname:
        hosts.append(partes.hostname)
    try:
        consulta = dict(parse_qsl(partes.query, keep_blank_values=True))
    except ValueError:
        return hosts
    for clave in ("host", "hostaddr"):
        for nombre, valor in consulta.items():
            if nombre.lower() == clave and valor:
                hosts.extend(p for p in valor.split(",") if p.strip())
    return hosts


def es_loopback(url: str) -> bool:
    """¿La URL apunta inequívocamente a esta máquina, por TODAS sus vías?

    SIN RESOLVER DNS, a propósito. Si preguntáramos al resolver, quien controle el DNS
    decidiría si ciframos: un nombre que hoy resuelve a 127.0.0.1 puede resolver mañana a
    otra cosa, y la exención de desarrollo se convertiría en un agujero remoto. Aquí sólo
    cuenta lo que la URL dice literalmente.

    Exento sólo si declara al menos un host y TODOS son loopback. Basta que uno no lo sea
    —incluido el que venga por `?host=` o `?hostaddr=`— para exigir `verify-full`. Ante una
    URL ilegible o sin host: remota. El modo conservador es el que cifra y verifica.
    """
    hosts = hosts_declarados(url)
    return bool(hosts) and all(_es_host_loopback(h) for h in hosts)


# ── G1 · la URL compartida no puede traer política TLS ────────────────────────────────
def exigir_url_sin_parametros_tls(url: str) -> None:
    """Rechaza una URL remota que intente fijar TLS por su cuenta.

    El peligro no es teórico y es ASIMÉTRICO entre los dos stacks. Un `sslmode=require`
    incrustado en la URL anula `PGSSLMODE` para libpq pero deja que `PGSSLROOTCERT` aporte
    el ancla: el resultado es equivalente a `verify-ca` —cadena validada, hostname NO— justo
    donde se pidió `verify-full`, y en silencio. Del otro lado, SQLAlchemy pasaría el mismo
    parámetro como kwarg a asyncpg. Una sola cadena, dos degradaciones distintas.

    Se rechaza antes de construir nada. El mensaje puede listar NOMBRES de parámetros;
    jamás la URL.
    """
    try:
        consulta = urlparse(url).query
    except ValueError:
        raise TLSPolicyError("la URL de la base no se puede analizar") from None
    claves = [c.lower() for c, _ in parse_qsl(consulta, keep_blank_values=True)]

    # El destino no se redirige desde la query. Aunque `hosts_declarados()` ya impide que
    # un `?host=` remoto se disfrace de loopback, esto cierra el otro lado: una URL REMOTA
    # con `?host=` deja el destino ambiguo —netloc dice una cosa, la query otra— y cada
    # driver resuelve esa ambigüedad a su manera. Con `hostaddr` es peor: libpq verifica el
    # certificado contra `host` mientras abre el TCP contra otra IP.
    redirige = sorted({c for c in claves if c in ("host", "hostaddr")})
    if redirige:
        raise TLSPolicyError(
            "la URL de la base redirige el destino desde la query y eso deja ambiguo contra "
            f"quién se verifica el certificado: {redirige}"
        )

    encontrados = sorted({
        c for c in claves if c.startswith("ssl") or c in _EXTRA_PROHIBIDAS
    })
    if encontrados:
        raise TLSPolicyError(
            "la URL de la base trae parámetros TLS y la política del núcleo los fija en "
            f"código, no en la cadena de conexión: {encontrados}"
        )


# ── G2 · el bundle se valida antes de tocar ningún driver ─────────────────────────────
def validar_bundle(ruta: str | Path | None = None) -> str:
    """Comprueba que el ancla de confianza existe y es utilizable. Devuelve la ruta.

    POR QUÉ ANTES Y NO AL CONECTAR. `AsyncConnectionPool.__init__` guarda sus `kwargs` sin
    validarlos: un `sslrootcert` mal escrito no da error al construir el pool, sino en el
    primer checkout —ya con la app arriba y sirviendo—, y el síntoma llega como un timeout
    del pool, que no se parece en nada a la causa. asyncpg, en cambio, falla al construir
    el contexto. Validando aquí, las dos rutas fallan igual y fallan pronto.

    `load_verify_locations` es la validación, no un adorno: rechaza lo que OpenSSL no pueda
    usar como ancla. Y se exige que el contexto acabe con al menos un certificado cargado,
    porque un PEM sintácticamente correcto pero sin bloques de certificado pasaría el load
    sin aportar confianza alguna.
    """
    p = Path(_ruta(ruta))
    if not p.exists():
        raise TLSPolicyError(f"falta el bundle de CA en la ruta esperada: {p}")
    if not p.is_file():
        raise TLSPolicyError(f"el bundle de CA no es un archivo regular: {p}")
    try:
        tamano = p.stat().st_size
    except OSError:
        raise TLSPolicyError(f"el bundle de CA no se puede leer: {p}") from None
    if tamano == 0:
        raise TLSPolicyError(f"el bundle de CA está vacío: {p}")

    sonda = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    try:
        sonda.load_verify_locations(cafile=str(p))
    except (ssl.SSLError, OSError, ValueError):
        # `from None`: el texto de OpenSSL/errno no aporta nada accionable aquí y esto se
        # levanta en el arranque, donde el mensaje acaba publicado. Ver TLSPolicyError.
        raise TLSPolicyError(f"el bundle de CA no contiene certificados usables: {p}") from None
    if not sonda.get_ca_certs():
        raise TLSPolicyError(f"el bundle de CA no aportó ninguna ancla: {p}")
    return str(p)


# ── D · el contexto de asyncpg ────────────────────────────────────────────────────────
def contexto_ssl_asyncpg(ruta_bundle: str | Path | None = None) -> ssl.SSLContext:
    """El `SSLContext` con el que asyncpg verifica al servidor.

    `check_hostname` y `verify_mode` ya vienen así de `create_default_context`; se fijan
    igualmente de forma EXPLÍCITA porque son las dos propiedades que definen `verify-full`
    frente a `verify-ca`, y porque un default puede cambiar entre versiones de Python sin
    que ningún test nuestro se entere. Escritas aquí, la prueba las puede afirmar.
    """
    validada = validar_bundle(ruta_bundle)
    ctx = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH, cafile=validada)
    ctx.check_hostname = True                  # verify-full: el nombre también se verifica
    ctx.verify_mode = ssl.CERT_REQUIRED        # sin certificado válido no hay conexión
    return ctx


# ── Lo que consume cada stack ─────────────────────────────────────────────────────────
def connect_args_asyncpg(url: str, ruta_bundle: str | Path | None = None) -> dict:
    """Los `connect_args` TLS para el engine de SQLAlchemy. `{}` si la URL es loopback.

    Se entrega un objeto `SSLContext`, no una cadena. Consecuencia que conviene tener
    presente: a partir de aquí `sslmode` NO es el oráculo de la postura — puede no existir
    en ninguna parte y la conexión estar verificando hostname igualmente. Quien quiera
    saber qué verifica asyncpg tiene que mirar el contexto, no la URL.
    """
    if es_loopback(url):
        return {}
    exigir_url_sin_parametros_tls(url)
    return {"ssl": contexto_ssl_asyncpg(ruta_bundle)}


def kwargs_psycopg(url: str, ruta_bundle: str | Path | None = None) -> dict:
    """Los kwargs TLS para `AsyncConnectionPool`. `{}` si la URL es loopback.

    Van por `kwargs=` del pool, NUNCA concatenados a la conninfo: en psycopg los kwargs del
    pool ganan sobre la cadena, así que este es el canal que no se puede contradecir desde
    la URL compartida. Y la conninfo se deja intacta, byte a byte.
    """
    if es_loopback(url):
        return {}
    exigir_url_sin_parametros_tls(url)
    return {"sslmode": "verify-full", "sslrootcert": validar_bundle(ruta_bundle)}
