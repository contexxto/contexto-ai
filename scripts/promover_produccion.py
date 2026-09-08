"""Promotor de producción de Vercel · VERCEL-RELEASE-CONTROL-F-R1.

QUÉ GARANTIZA (R1-R4 de la unidad F-02):
  R1  el artefacto promovido corresponde al SHA que aprobaron `pytest` y `frontend`
  R2  se promueve únicamente ese artefacto
  R3  sin reconstrucción
  R4  solo después de una aprobación humana

PRECONDICIONES DE CUTOVER · duraderas, no una foto de un día
Este programa gobierna un JOB. Que ese job gobierne además **el hecho de publicar**
depende de dos condiciones externas que NO puede comprobar por sí mismo y que deben
cumplirse antes de darle valor a su resultado:

  P-1  «Auto-Assign Custom Production Domains» del proyecto en Vercel debe estar en OFF.
       Mientras esté en ON, un merge a la rama de producción asigna los dominios por su
       cuenta y la promoción de este programa deja de ser la vía por la que se publica.
       El programa NO lee ese ajuste: vive en el panel, no en la API documentada.
  P-2  el Environment de GitHub que protege al job debe existir y llevar sus reglas
       (revisor requerido y bypass de administradores apagado). El programa tampoco
       puede verificarlo: las reglas de protección viven en la consola.

Si P-1 o P-2 no se cumplen, este programa sigue haciendo lo que dice —promueve solo el
artefacto aprobado, o falla cerrado— pero **no es la puerta de publicación**. Esa
distinción no caduca y por eso se enuncia como precondición y no como estado del día.

Tampoco cubre INV-FRESHNESS: no comprueba que el SHA siga siendo la cabeza de la rama
cuando llega la aprobación humana.

CONTRATO DEL TOKEN · alcance de PROYECTO
El token se crea limitado al proyecto que se va a promover, que es el suelo de
granularidad que ofrece Vercel: se puede bajar de cuenta a equipo y de equipo a un solo
proyecto, pero NO existe alcance por operación. Con un token así, el ámbito queda
implícito en la credencial y el programa **no exige ni envía identificador de equipo**.
Entradas requeridas:

  VERCEL_PROJECT_PROMOTION_TOKEN   secreto · nombre específico a propósito
  VERCEL_PROMOTION_PROJECT_ID      identificador del proyecto
  VERCEL_PROMOTION_ALIAS           lista de los dominios productivos, separados por comas

LOS DOMINIOS PRODUCTIVOS SON MÁS DE UNO, y esto cambia la garantía
Una promoción asigna TODOS los dominios de producción del proyecto. Reconciliar uno solo
acreditaría la mitad del hecho. Por eso este programa exige la lista completa y solo
declara `PROMOTED` cuando **todos** apuntan al mismo despliegue aprobado y al proyecto
esperado. Un estado en el que unos dominios ya sirven el artefacto y otros no es
precisamente el que hay que detectar, no el que hay que aprobar.

CONTRATO DE LA API, extraído del OpenAPI oficial de Vercel (https://openapi.vercel.sh/,
10 717 362 bytes, 297 rutas, leído el 2026-09-07 — es una foto fechada: si el contrato
cambia hay que releerla). Cada campo que este programa exige está documentado, y cada
campo que el contrato declara OPCIONAL se trata aquí como ausente-hasta-que-se-demuestre:

  GET /v7/deployments
      El 200 declara required: [deployments, pagination]. Este programa exige los dos con
      el mismo rigor: un `deployments` ausente, nulo o que no sea lista es un fallo, no
      una página vacía.
      El ITEM del listado declara required: [created, createdAt, creator, inspectorUrl,
      name, projectId, readyState, type, uid, url]. `readySubstate` NO está en esa lista
      y `gitSource` NO existe en el item. De ahí dos reglas:
        · la identidad exige SIEMPRE una segunda llamada al detalle;
        · el prefiltro por `readySubstate` solo puede EXCLUIR lo que demuestra no ser
          STAGED. Un item que omita el campo pasa al detalle. Excluirlo por ausencia
          haría invisible a un segundo candidato y desarmaría la comprobación de
          ambigüedad, que es la única defensa de R2.
      `pagination` = {count, next, prev}, las tres requeridas. `next` es un timestamp
      nullable; `null` es la última página. Que ese valor se pase como `until` NO lo dice
      el schema con esas palabras: es INFERIDO de que `until` es el único parámetro
      documentado como «Get Deployments created before this timestamp».

  GET /v13/deployments/{idOrUrl}?withGitRepoInfo=true
      El 200 es un `oneOf` de TRES variantes. `id` y `readyState` son requeridos en las
      tres. `readySubstate`, `target` y `gitSource` NO lo son en NINGUNA, y `projectId`
      solo en una. La ausencia de cualquiera descalifica al candidato.
      readyState  enum: BLOCKED BUILDING CANCELED ERROR INITIALIZING QUEUED READY
      readySubstate enum: PROMOTED ROLLING STAGED
          "STAGED: never seen production traffic". Es el estado documentado que
          corresponde al «Staged» que presupone F-02, no una palabra de la interfaz.
      target enum: production | staging | null (null = preview)
      gitSource es a su vez un `oneOf` de 19 formas. `type` es requerido en las 19;
      `sha` solo en 9.
      source: el schema advierte "Best-effort guess for metrics only — not authoritative;
          do not gate behavior on it". Por eso NO se usa.

  POST /v10/projects/{projectId}/promote/{deploymentId}
      "Allows users to promote a deployment to production. Note: This does NOT rebuild
       the deployment." — esa frase es la prueba documental de R3.
      Éxito documentado: 201 y 202, ambos SIN cuerpo declarado.
      Fallo documentado: 400 401 403 409 410 422.
      CUALQUIER OTRO CÓDIGO no está documentado, así que no se puede afirmar que el
      servidor rechazara: se trata como aceptación DESCONOCIDA y va a reconciliación.

  GET /v4/aliases/{idOrAlias}
      required: alias, created, deploymentId, projectId, uid.
      deploymentId y projectId son además nullable: un `null` es NO RECONCILIADO, jamás
      una coincidencia.

POR QUÉ SOLO BIBLIOTECA ESTÁNDAR: el job de promoción no instala requirements. urllib
basta y no añade superficie. El transporte es inyectable para que las pruebas jamás
toquen la red, y NO sigue redirecciones: un 30x arrastraría la cabecera Authorization a
otro host.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol

BASE = "https://api.vercel.com"

# ── Estados de salida ──────────────────────────────────────────────────────────
PROMOTED = "PROMOTED"
ALREADY_CURRENT_UNATTESTED = "ALREADY_CURRENT_UNATTESTED"
UNAVAILABLE = "UNAVAILABLE"
FAIL_CLOSED = "FAIL_CLOSED"
UNKNOWN_RECONCILIATION_REQUIRED = "UNKNOWN_RECONCILIATION_REQUIRED"

CODIGOS_DE_SALIDA = {
    # Éxito ATESTIGUADO: esta ejecución emitió su único POST y después comprobó que
    # TODOS los dominios productivos convergen en el artefacto aprobado. Es el ÚNICO
    # camino verde.
    PROMOTED: 0,
    UNAVAILABLE: 1,
    FAIL_CLOSED: 2,
    UNKNOWN_RECONCILIATION_REQUIRED: 3,
    # Los dominios YA servían el SHA aprobado ANTES de que esta ejecución hiciera nada.
    # Sigue siendo un no-op —no se repite la promoción— pero NO es una promoción
    # atestiguada por F: observar qué sirve Vercel no demuestra que F lo promoviera, ni
    # que la publicación esperase la aprobación humana, ni que no hubiera una promoción
    # manual fuera del workflow. Por eso sale distinto de cero.
    ALREADY_CURRENT_UNATTESTED: 4,
}

# ── Límites duros. Todos aquí, todos finitos, todos probables con reloj falso. ──
TIMEOUT_GET = 15.0
TIMEOUT_POST = 30.0
REINTENTOS_GET = 2  # solo GET, y acotados
ESPERA_ENTRE_REINTENTOS = 2.0
PAGINAS_MAXIMAS = 20
DETALLES_MAXIMOS = 50
SONDEOS_MAXIMOS = 6
ESPERA_ENTRE_SONDEOS = 5.0
VENTANA_MAXIMA_DE_SONDEO = 90.0
ALIAS_MAXIMOS = 10

# EL CONJUNTO EXACTO DE DOMINIOS PRODUCTIVOS, FIJADO EN GIT.
#
# Exigir «al menos dos» no basta: una configuración con dos dominios cualesquiera
# —uno equivocado, uno de preview, uno que ya no sirve producción— pasaría el filtro y
# el programa reconciliaría el conjunto incorrecto creyendo que cumple. Y el contenido
# de una variable del Environment se cambia desde la consola, sin revisión y sin dejar
# rastro en el repositorio.
#
# Por eso el conjunto se fija AQUÍ y la variable se valida contra él: cambiar qué
# dominios se reconcilian exige un commit, que pasa por el CI y por la revisión del PR.
# La variable no desaparece —sigue siendo la que lee el programa— pero deja de ser la
# autoridad: si discrepa del conjunto fijado, se falla cerrado.
#
# Medido en el panel de Vercel el 2026-09-07: Settings > Environments > Production
# lista estos dos, y solo estos dos, como dominios de producción del proyecto.
DOMINIOS_PRODUCTIVOS = (
    "contexxto.com",
    "contexto-ai-six.vercel.app",
)

CODIGOS_DE_EXITO_DE_PROMOCION = frozenset({201, 202})
CODIGOS_DE_RECHAZO_DOCUMENTADOS = frozenset({400, 401, 403, 409, 410, 422})

HEX40 = re.compile(r"\A[0-9a-f]{40}\Z")

# `type` es requerido en las 19 formas de gitSource. Solo se acepta la familia GitHub:
# el CI que aprueba es GitHub Actions, así que un artefacto de otro origen no puede ser
# «el que aprobó el CI».
TIPOS_GIT_ADMITIDOS = frozenset({"github", "github-limited", "github-custom-host"})

VARIABLES_REQUERIDAS = (
    "VERCEL_PROJECT_PROMOTION_TOKEN",
    "VERCEL_PROMOTION_PROJECT_ID",
    "VERCEL_PROMOTION_ALIAS",
)


class ErrorBarrera(Exception):
    """Una condición que obliga a no promover. Siempre termina en FAIL_CLOSED."""


class ErrorTransporte(Exception):
    """La petición no obtuvo respuesta concluyente del servidor."""


# ── Redacción segura ───────────────────────────────────────────────────────────


def redactar(texto: str, secretos: Iterable[str]) -> str:
    """Sustituye cualquier secreto por un marcador. Sin suelo de longitud."""
    salida = str(texto)
    for secreto in secretos:
        if secreto:
            salida = salida.replace(str(secreto), "***REDACTADO***")
    return salida


class Registro:
    """Escritor de logs que redacta siempre y no acepta objetos crudos."""

    def __init__(self, secretos: Iterable[str] = (), salida=None):
        self._secretos = tuple(s for s in secretos if s)
        self._salida = salida if salida is not None else sys.stdout
        self.lineas: list[str] = []

    def __call__(self, mensaje: str) -> None:
        linea = redactar(mensaje, self._secretos)
        self.lineas.append(linea)
        print(linea, file=self._salida)


# ── (1) Validación del contexto GitHub · la barrera redundante ─────────────────


@dataclass(frozen=True)
class ContextoGitHub:
    evento: str
    ref: str
    intento: int
    sha: str
    repositorio: str  # "owner/repo", tal como lo publica GITHUB_REPOSITORY


def validar_contexto_github(entorno: dict) -> ContextoGitHub:
    """Segunda barrera, independiente del YAML.

    La protección no puede depender solo de la condición `if:`: un PR que borre esa
    línea únicamente necesita pasar `pytest`, que no inspecciona .github/workflows/.
    Esta función vuelve a comprobar lo mismo desde dentro.
    """
    evento = entorno.get("GITHUB_EVENT_NAME", "")
    ref = entorno.get("GITHUB_REF", "")
    intento_crudo = entorno.get("GITHUB_RUN_ATTEMPT", "")
    sha = entorno.get("GITHUB_SHA", "")
    repositorio = entorno.get("GITHUB_REPOSITORY", "")

    if evento != "push":
        raise ErrorBarrera(f"evento no admitido: {evento!r}; solo 'push'")
    if ref != "refs/heads/main":
        raise ErrorBarrera(f"ref no admitida: {ref!r}; solo 'refs/heads/main'")
    try:
        intento = int(str(intento_crudo).strip())
    except (TypeError, ValueError):
        raise ErrorBarrera(
            f"GITHUB_RUN_ATTEMPT no es un entero: {intento_crudo!r}"
        ) from None
    if intento != 1:
        raise ErrorBarrera(f"intento {intento}: solo se promueve en el primero")
    if not HEX40.match(sha):
        raise ErrorBarrera(
            f"GITHUB_SHA no son 40 hex en minúscula: longitud {len(sha)}"
        )
    if repositorio.count("/") != 1 or not all(repositorio.split("/")):
        raise ErrorBarrera(
            f"GITHUB_REPOSITORY no tiene la forma owner/repo: {repositorio!r}"
        )
    return ContextoGitHub(
        evento=evento, ref=ref, intento=intento, sha=sha, repositorio=repositorio
    )


def parsear_alias(crudo: str) -> tuple[str, ...]:
    """Lista de dominios productivos, validada contra el conjunto fijado en git.

    No basta con exigir «al menos dos». Se exige el conjunto EXACTO: ni de más —un
    dominio ajeno se reconciliaría como si fuera producción— ni de menos —faltando uno,
    la convergencia parcial pasaría por completa, que es justo el fallo que esta unidad
    existe para detectar.

    Devuelve los dominios en el ORDEN FIJADO EN GIT, no en el que vengan configurados:
    el orden de la variable no debe poder alterar el comportamiento.
    """
    hosts = tuple(
        dict.fromkeys(h.strip().lower() for h in str(crudo).split(",") if h.strip())
    )
    if len(hosts) > ALIAS_MAXIMOS:
        raise ErrorBarrera(f"{len(hosts)} dominios supera el tope de {ALIAS_MAXIMOS}")
    for h in hosts:
        if "/" in h or " " in h or not h:
            raise ErrorBarrera(f"dominio con forma inesperada: {h!r}")
    esperados = set(DOMINIOS_PRODUCTIVOS)
    recibidos = set(hosts)
    if recibidos != esperados:
        sobran = sorted(recibidos - esperados)
        faltan = sorted(esperados - recibidos)
        raise ErrorBarrera(
            "la lista de dominios productivos no coincide con la fijada en git"
            + (f"; sobran {sobran}" if sobran else "")
            + (f"; faltan {faltan}" if faltan else "")
        )
    return tuple(DOMINIOS_PRODUCTIVOS)


# ── Transporte inyectable ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class Respuesta:
    estado: int
    cuerpo: object


class Transporte(Protocol):
    def __call__(
        self, metodo: str, url: str, cabeceras: dict, timeout: float
    ) -> Respuesta: ...


class _SinRedirecciones(urllib.request.HTTPRedirectHandler):
    """Convierte cualquier 30x en error.

    Seguir una redirección con el opener por defecto reenvía la cabecera Authorization
    al destino. La API de Vercel no documenta redirecciones en estas rutas.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_SinRedirecciones)


def transporte_urllib(
    metodo: str, url: str, cabeceras: dict, timeout: float
) -> Respuesta:
    peticion = urllib.request.Request(url=url, method=metodo, headers=cabeceras)
    try:
        with _OPENER.open(peticion, timeout=timeout) as respuesta:
            return Respuesta(
                estado=respuesta.status, cuerpo=_leer_json(respuesta.read())
            )
    except urllib.error.HTTPError as error:
        try:
            cuerpo = _leer_json(error.read())
        except Exception:
            cuerpo = None
        return Respuesta(estado=error.code, cuerpo=cuerpo)
    except Exception as error:  # timeout de transporte, DNS, reset, TLS
        # Solo el NOMBRE de la excepción. Su texto podría arrastrar la URL.
        raise ErrorTransporte(type(error).__name__) from None


def _leer_json(crudo: bytes) -> object:
    """Parsea si hay JSON; devuelve None si el cuerpo está vacío o no lo es.

    Los 201 y 202 de la promoción no declaran `content` en el contrato: exigir JSON ahí
    convertiría una aceptación en un fallo de transporte.
    """
    texto = (crudo or b"").decode("utf-8", errors="replace").strip()
    if not texto:
        return None
    try:
        return json.loads(texto)
    except ValueError:
        return None


# ── Cliente ────────────────────────────────────────────────────────────────────


@dataclass
class ClienteVercel:
    token: str = field(repr=False)  # fuera del repr: un traceback no debe llevarlo
    registro: Registro = field(repr=False)
    transporte: Transporte = transporte_urllib
    dormir: Callable[[float], None] = time.sleep
    reloj: Callable[[], float] = time.monotonic
    _post_emitido: bool = field(default=False, init=False, repr=False)

    def _cabeceras(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    def _url(self, ruta: str, consulta: dict | None = None) -> str:
        # No se envía identificador de equipo: el token está limitado al proyecto y el
        # ámbito queda implícito en la credencial.
        limpios = {k: v for k, v in (consulta or {}).items() if v is not None}
        sufijo = f"?{urllib.parse.urlencode(limpios)}" if limpios else ""
        return f"{BASE}{ruta}{sufijo}"

    def get(self, ruta: str, consulta: dict | None = None) -> Respuesta:
        url = self._url(ruta, consulta)
        ultimo: Exception | None = None
        for intento in range(REINTENTOS_GET + 1):
            try:
                return self.transporte("GET", url, self._cabeceras(), TIMEOUT_GET)
            except ErrorTransporte as error:
                ultimo = error
                if intento < REINTENTOS_GET:
                    self.registro(f"GET sin respuesta ({error}); reintento acotado")
                    self.dormir(ESPERA_ENTRE_REINTENTOS)
        raise ErrorTransporte(f"GET agotó {REINTENTOS_GET + 1} intentos: {ultimo}")

    def post_promocion(self, proyecto: str, despliegue: str) -> Respuesta:
        """EL único POST del programa. Sin reintentos, y estructuralmente irrepetible."""
        if self._post_emitido:
            raise ErrorBarrera(
                "intento de un SEGUNDO POST de promoción en la misma ejecución"
            )
        self._post_emitido = True
        ruta = (
            f"/v10/projects/{urllib.parse.quote(proyecto, safe='')}"
            f"/promote/{urllib.parse.quote(despliegue, safe='')}"
        )
        return self.transporte("POST", self._url(ruta), self._cabeceras(), TIMEOUT_POST)

    @property
    def post_emitido(self) -> bool:
        return self._post_emitido


# ── (2) Listado y paginación ───────────────────────────────────────────────────


def listar_despliegues_listos(cliente: ClienteVercel, proyecto: str) -> list[dict]:
    """Recorre TODAS las páginas de despliegues de producción en estado READY.

    `projectId`, `target` y `state` se usan conforme a su semántica documentada: la API
    los describe como filtros de igualdad sobre propiedades que forman parte del propio
    predicado del candidato. La garantía presupone que Vercel cumple ese contrato, y el
    cliente vuelve a validar TODOS esos campos en cada detalle.

    El filtro `sha` NO se usa porque su semántica de coincidencia exacta no está
    documentada: su schema no declara `pattern`, `minLength` ni `maxLength`, y no hay una
    sola frase sobre prefijos. Además, la comprobación de ambigüedad de R2 se hace
    contando candidatos, y un filtro que devolviera de menos ocultaría al segundo.
    """
    encontrados: list[dict] = []
    hasta: int | None = None
    for _pagina in range(PAGINAS_MAXIMAS):
        consulta = {
            "projectId": proyecto,
            "target": "production",
            "state": "READY",
            "limit": 100,
        }
        if hasta is not None:
            consulta["until"] = hasta
        respuesta = cliente.get("/v7/deployments", consulta)
        if respuesta.estado != 200:
            raise ErrorBarrera(f"listado devolvió {respuesta.estado}")
        cuerpo = respuesta.cuerpo
        if not isinstance(cuerpo, dict):
            raise ErrorBarrera("listado con cuerpo que no es un objeto")
        elementos = cuerpo.get("deployments")
        if not isinstance(elementos, list):
            raise ErrorBarrera("el listado no trae `deployments` como lista")
        for elemento in elementos:
            if not isinstance(elemento, dict):
                raise ErrorBarrera("el listado trae un elemento que no es un objeto")
            encontrados.append(elemento)
        paginacion = cuerpo.get("pagination")
        if not isinstance(paginacion, dict) or "next" not in paginacion:
            raise ErrorBarrera("el listado no trae paginación utilizable")
        siguiente = paginacion.get("next")
        if siguiente is None:
            return encontrados
        hasta = siguiente
    raise ErrorBarrera(
        f"paginación no resuelta tras {PAGINAS_MAXIMAS} páginas; no se promueve"
    )


# ── (3) Validación del candidato ───────────────────────────────────────────────


@dataclass(frozen=True)
class Esperado:
    proyecto: str
    sha: str
    repositorio: str  # "owner/repo"


def _sha_de(origen: dict) -> str | None:
    sha = origen.get("sha")
    return sha if isinstance(sha, str) else None


def _motivo_de_descarte_del_origen(origen: object, esperado: Esperado) -> str | None:
    if not isinstance(origen, dict):
        return "sin gitSource"
    tipo = origen.get("type")
    if tipo not in TIPOS_GIT_ADMITIDOS:
        return f"gitSource.type {tipo!r} no es de la familia GitHub"
    duenio, _, repositorio = esperado.repositorio.partition("/")
    org = origen.get("org")
    repo = origen.get("repo")
    # La identidad del repositorio se declara por repoId o por org+repo según la forma.
    # Cuando vienen los nombres se exigen; cuando no, la pertenencia queda sostenida por
    # projectId, que ya se comprobó. Es un límite declarado, no un descuido.
    if isinstance(org, str) and org.lower() != duenio.lower():
        return f"gitSource.org {org!r} no es {duenio!r}"
    if isinstance(repo, str) and repo.lower() != repositorio.lower():
        return f"gitSource.repo {repo!r} no es {repositorio!r}"
    sha = _sha_de(origen)
    if sha is None:
        return "sin gitSource.sha"
    if not HEX40.match(sha):
        return f"gitSource.sha no son 40 hex (longitud {len(sha)})"
    if sha != esperado.sha:
        return "gitSource.sha no coincide con el SHA aprobado"
    return None


def motivo_de_descarte(
    detalle: dict, esperado: Esperado, identificador: str | None = None
) -> str | None:
    """Devuelve None si el despliegue es promovible; si no, por qué no lo es."""
    if not isinstance(detalle, dict):
        return "el detalle no es un objeto"
    if identificador is not None and detalle.get("id") != identificador:
        return f"el detalle responde por {detalle.get('id')!r}, no por {identificador!r}"
    if detalle.get("projectId") != esperado.proyecto:
        return f"projectId {detalle.get('projectId')!r} no es el esperado"
    if detalle.get("target") != "production":
        return f"target {detalle.get('target')!r} no es production"
    if detalle.get("readyState") != "READY":
        return f"readyState {detalle.get('readyState')!r} no es READY"
    if detalle.get("readySubstate") != "STAGED":
        return f"readySubstate {detalle.get('readySubstate')!r} no es STAGED"
    return _motivo_de_descarte_del_origen(detalle.get("gitSource"), esperado)


def detalle_de(cliente: ClienteVercel, identificador: str) -> dict:
    respuesta = cliente.get(
        f"/v13/deployments/{urllib.parse.quote(identificador, safe='')}",
        {"withGitRepoInfo": "true"},
    )
    if respuesta.estado != 200:
        raise ErrorBarrera(f"detalle de despliegue devolvió {respuesta.estado}")
    if not isinstance(respuesta.cuerpo, dict):
        raise ErrorBarrera("detalle con cuerpo que no es un objeto")
    return respuesta.cuerpo


def puede_excluirse_sin_mirar_el_detalle(elemento: dict) -> bool:
    """Prefiltro que solo EXCLUYE lo que demuestra no ser promovible.

    `readySubstate` NO es un campo requerido del item del listado. Excluir por su
    AUSENCIA haría invisible a un segundo candidato y dejaría sin disparar la
    comprobación de ambigüedad, única defensa de R2: descartar aquí no cierra, abre.
    """
    substate = elemento.get("readySubstate")
    return isinstance(substate, str) and substate != "STAGED"


def seleccionar_candidato(
    cliente: ClienteVercel, esperado: Esperado, registro: Registro
) -> list[str]:
    """Selección TOTAL y determinista. Nunca 'el primero'.

    0 candidatos → UNAVAILABLE. 1 → continúa. >1 → FAIL_CLOSED.
    """
    listados = listar_despliegues_listos(cliente, esperado.proyecto)
    preseleccion = [
        d
        for d in listados
        if not puede_excluirse_sin_mirar_el_detalle(d) and isinstance(d.get("uid"), str)
    ]
    sin_uid = sum(1 for d in listados if not isinstance(d.get("uid"), str))
    if sin_uid:
        raise ErrorBarrera(f"{sin_uid} elementos del listado sin `uid`")
    if len(preseleccion) > DETALLES_MAXIMOS:
        raise ErrorBarrera(
            f"{len(preseleccion)} preseleccionados supera el tope de {DETALLES_MAXIMOS}"
        )
    registro(
        f"listado: {len(listados)} despliegues READY de producción; "
        f"{len(preseleccion)} por confirmar en el detalle"
    )
    validos: list[str] = []
    for elemento in preseleccion:
        identificador = elemento["uid"]
        motivo = motivo_de_descarte(
            detalle_de(cliente, identificador), esperado, identificador
        )
        if motivo is None:
            validos.append(identificador)
        else:
            registro(f"descartado {identificador}: {motivo}")
    if len(validos) > 1:
        raise ErrorBarrera(
            f"{len(validos)} candidatos válidos para el mismo SHA; ambigüedad"
        )
    return validos


# ── (4) Alias · ahora TODOS los dominios productivos ───────────────────────────


@dataclass(frozen=True)
class EstadoAlias:
    despliegue: str | None
    proyecto: str | None

    @property
    def reconciliado(self) -> bool:
        return bool(self.despliegue) and bool(self.proyecto)


def leer_alias(cliente: ClienteVercel, alias: str) -> EstadoAlias:
    """Lectura CANÓNICA. GET /v2/deployments/{id}/aliases no sirve para esto: no
    devuelve deploymentId ni projectId, así que solo corrobora una hipótesis ya formada.
    Aquí hace falta producir la identidad, no confirmarla."""
    respuesta = cliente.get(f"/v4/aliases/{urllib.parse.quote(alias, safe='')}")
    if respuesta.estado != 200:
        raise ErrorBarrera(f"lectura del alias devolvió {respuesta.estado}")
    cuerpo = respuesta.cuerpo
    if not isinstance(cuerpo, dict):
        raise ErrorBarrera("alias con cuerpo que no es un objeto")
    despliegue = cuerpo.get("deploymentId")
    proyecto = cuerpo.get("projectId")
    return EstadoAlias(
        despliegue=despliegue if isinstance(despliegue, str) and despliegue else None,
        proyecto=proyecto if isinstance(proyecto, str) and proyecto else None,
    )


def leer_todos_los_alias(
    cliente: ClienteVercel, hosts: Iterable[str]
) -> dict[str, EstadoAlias]:
    return {host: leer_alias(cliente, host) for host in hosts}


def alias_apunta_a(estado: EstadoAlias, despliegue: str, proyecto: str) -> bool:
    """Objetivo alcanzado solo si AMBOS identificadores coinciden y no son nulos."""
    if not despliegue or not proyecto:
        return False
    return (
        estado.reconciliado
        and estado.despliegue == despliegue
        and estado.proyecto == proyecto
    )


# ── Convergencia entre dominios ────────────────────────────────────────────────

TODOS = "TODOS"
NINGUNO = "NINGUNO"
PARCIAL = "PARCIAL"
DIVERGENTE = "DIVERGENTE"
NO_RECONCILIADO = "NO_RECONCILIADO"


def clasificar_convergencia(
    estados: dict[str, EstadoAlias], objetivo: str, proyecto: str
) -> str:
    """¿En qué estado están los dominios productivos respecto de un despliegue?

    TODOS            cada dominio apunta al objetivo y al proyecto esperado
    NINGUNO          ninguno apunta al objetivo, y todos coinciden entre sí
    PARCIAL          unos sí y otros no
    DIVERGENTE       ninguno apunta al objetivo y además NO coinciden entre sí
    NO_RECONCILIADO  algún dominio trae nulos o un proyecto ajeno

    La distinción entre PARCIAL y DIVERGENTE importa para el diagnóstico, no para la
    decisión: las dos son fallo cerrado antes del POST, y las dos son UNKNOWN después.
    """
    if not estados:
        return NO_RECONCILIADO
    for estado in estados.values():
        if not estado.reconciliado or estado.proyecto != proyecto:
            return NO_RECONCILIADO
    aciertos = sum(
        1 for e in estados.values() if alias_apunta_a(e, objetivo, proyecto)
    )
    if aciertos == len(estados):
        return TODOS
    if aciertos > 0:
        return PARCIAL
    if len({e.despliegue for e in estados.values()}) > 1:
        return DIVERGENTE
    return NINGUNO


# ── (5) Reconciliación acotada, sobre TODOS los dominios ───────────────────────


def reconciliar(
    cliente: ClienteVercel,
    hosts: tuple[str, ...],
    despliegue: str,
    proyecto: str,
    registro: Registro,
) -> str:
    """Sondeo ACOTADO de todos los dominios. Nunca infinito, nunca un segundo POST.

    Devuelve la clasificación del último sondeo concluyente. Solo `TODOS` autoriza a
    declarar la promoción: una convergencia parcial deja producción a medio camino, y
    eso no es un éxito, es un incidente que hay que reconciliar a mano.
    """
    inicio = cliente.reloj()
    ultima = NO_RECONCILIADO
    for sondeo in range(SONDEOS_MAXIMOS):
        if cliente.reloj() - inicio > VENTANA_MAXIMA_DE_SONDEO:
            registro("ventana de sondeo agotada por tiempo")
            return ultima
        try:
            estados = leer_todos_los_alias(cliente, hosts)
        except (ErrorBarrera, ErrorTransporte) as error:
            registro(f"sondeo {sondeo + 1}: sin lectura concluyente ({error})")
        else:
            ultima = clasificar_convergencia(estados, despliegue, proyecto)
            registro(f"sondeo {sondeo + 1}: convergencia {ultima}")
            if ultima == TODOS:
                return TODOS
        if sondeo < SONDEOS_MAXIMOS - 1:
            cliente.dormir(ESPERA_ENTRE_SONDEOS)
    return ultima


# ── Orquestación ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Resultado:
    estado: str
    detalle: str = ""

    @property
    def codigo(self) -> int:
        return CODIGOS_DE_SALIDA[self.estado]


def ejecutar(
    entorno: dict,
    transporte: Transporte = transporte_urllib,
    dormir: Callable[[float], None] = time.sleep,
    reloj: Callable[[], float] = time.monotonic,
    salida=None,
) -> Resultado:
    token = entorno.get("VERCEL_PROJECT_PROMOTION_TOKEN", "")
    registro = Registro(secretos=(token,), salida=salida)

    faltan = [v for v in VARIABLES_REQUERIDAS if not entorno.get(v)]
    if faltan:
        registro(f"faltan variables requeridas: {', '.join(faltan)}")
        return Resultado(FAIL_CLOSED, "entrada requerida ausente")

    try:
        contexto = validar_contexto_github(entorno)
        hosts = parsear_alias(entorno["VERCEL_PROMOTION_ALIAS"])
    except ErrorBarrera as error:
        registro(f"barrera del programa: {error}")
        return Resultado(FAIL_CLOSED, str(error))

    proyecto = entorno["VERCEL_PROMOTION_PROJECT_ID"]
    esperado = Esperado(
        proyecto=proyecto, sha=contexto.sha, repositorio=contexto.repositorio
    )
    cliente = ClienteVercel(
        token=token,
        registro=registro,
        transporte=transporte,
        dormir=dormir,
        reloj=reloj,
    )
    registro(f"SHA aprobado por el CI: {contexto.sha}")
    registro(f"dominios productivos a reconciliar: {', '.join(hosts)}")

    try:
        validos = seleccionar_candidato(cliente, esperado, registro)
    except ErrorBarrera as error:
        registro(f"selección cerrada: {error}")
        return Resultado(FAIL_CLOSED, str(error))
    except ErrorTransporte as error:
        registro(f"listado sin respuesta concluyente: {error}")
        return Resultado(FAIL_CLOSED, "listado no concluyente")

    # Los alias se leen ANTES de concluir nada sobre la disponibilidad. Si ya sirven el
    # SHA aprobado, ese despliegue estará en `PROMOTED` y por tanto NO aparecerá entre
    # los candidatos: mirar solo la lista daría UNAVAILABLE y se perdería el hecho.
    try:
        estados = leer_todos_los_alias(cliente, hosts)
    except (ErrorBarrera, ErrorTransporte) as error:
        registro(f"no se pudo leer algún dominio productivo: {error}")
        return Resultado(FAIL_CLOSED, "dominio productivo no legible")

    previo = _estado_preexistente(cliente, estados, esperado, registro)
    if previo is not None:
        return previo

    if not validos:
        registro("cero candidatos promovibles para este SHA; no se promueve nada")
        return Resultado(UNAVAILABLE, "sin artefacto promovible")

    candidato = validos[0]

    # ── el único POST ──
    try:
        respuesta = cliente.post_promocion(proyecto, candidato)
    except ErrorTransporte as error:
        # Aceptación DESCONOCIDA: la petición pudo no llegar a registrarse.
        registro(f"POST sin respuesta concluyente ({error}); se pasa a reconciliar")
        return _desenlace_incierto(cliente, hosts, candidato, proyecto, registro)
    except ErrorBarrera as error:
        registro(f"barrera del POST: {error}")
        return Resultado(FAIL_CLOSED, str(error))

    if respuesta.estado in CODIGOS_DE_EXITO_DE_PROMOCION:
        registro(f"promoción aceptada por el servidor ({respuesta.estado})")
        return _desenlace_incierto(cliente, hosts, candidato, proyecto, registro)

    if respuesta.estado in CODIGOS_DE_RECHAZO_DOCUMENTADOS:
        registro(f"promoción rechazada por el servidor ({respuesta.estado})")
        return Resultado(FAIL_CLOSED, f"POST devolvió {respuesta.estado}")

    registro(f"código no documentado tras el POST ({respuesta.estado}); se reconcilia")
    return _desenlace_incierto(cliente, hosts, candidato, proyecto, registro)


def _estado_preexistente(
    cliente: ClienteVercel,
    estados: dict[str, EstadoAlias],
    esperado: Esperado,
    registro: Registro,
) -> Resultado | None:
    """¿Qué servían los dominios ANTES de que esta ejecución hiciera nada?

    Devuelve un Resultado si hay que terminar aquí, o None si se puede seguir.
    """
    for host, estado in estados.items():
        if not estado.reconciliado:
            registro(f"{host}: alias no reconciliado (deploymentId o projectId nulos)")
            return Resultado(FAIL_CLOSED, "dominio productivo no reconciliado")
        if estado.proyecto != esperado.proyecto:
            registro(f"{host}: projectId {estado.proyecto!r} no es el esperado")
            return Resultado(FAIL_CLOSED, "dominio productivo de otro proyecto")

    servidos = {e.despliegue for e in estados.values()}
    if len(servidos) > 1:
        registro(
            "los dominios productivos apuntan a despliegues DISTINTOS entre sí: "
            + ", ".join(f"{h}->{e.despliegue}" for h, e in sorted(estados.items()))
        )
        return Resultado(FAIL_CLOSED, "dominios divergentes")

    servido = next(iter(servidos))
    try:
        detalle = detalle_de(cliente, servido)
    except (ErrorBarrera, ErrorTransporte) as error:
        registro(f"no se pudo leer lo que sirven los dominios: {error}")
        return Resultado(FAIL_CLOSED, "lo servido por los dominios no es legible")

    if el_alias_ya_sirve_el_sha_aprobado(detalle, servido, esperado):
        registro(
            "TODOS los dominios productivos YA servían el SHA aprobado antes de esta "
            "ejecución. No se emite POST. Esto NO acredita que F lo promoviera, ni que "
            "la publicación esperara la aprobación humana, ni que no hubiera una "
            "promoción manual fuera del workflow."
        )
        return Resultado(ALREADY_CURRENT_UNATTESTED, servido)
    return None


def el_alias_ya_sirve_el_sha_aprobado(
    detalle: dict, servido: str, esperado: Esperado
) -> bool:
    """¿El despliegue que sirven los dominios está construido del SHA aprobado?

    Predicado DISTINTO del de candidato promovible, y a propósito: aquí NO se mira
    `readySubstate`. Un despliegue que ya sirve producción está documentado como
    `PROMOTED`, no como `STAGED`; exigir STAGED haría que este caso nunca se detectara.
    """
    if not isinstance(detalle, dict):
        return False
    if detalle.get("id") != servido:
        return False
    if detalle.get("projectId") != esperado.proyecto:
        return False
    if detalle.get("target") != "production":
        return False
    return _motivo_de_descarte_del_origen(detalle.get("gitSource"), esperado) is None


def _desenlace_incierto(
    cliente: ClienteVercel,
    hosts: tuple[str, ...],
    candidato: str,
    proyecto: str,
    registro: Registro,
) -> Resultado:
    """Cierra la ejecución DESPUÉS de que esta corrida haya emitido su único POST.

    Solo la convergencia COMPLETA de todos los dominios productivos autoriza `PROMOTED`.
    Una convergencia parcial deja producción a medio camino y es exactamente el estado
    que no se puede declarar como éxito.
    """
    resultado = reconciliar(cliente, hosts, candidato, proyecto, registro)
    if resultado == TODOS:
        registro(
            "PROMOTED atestiguado: POST de esta ejecución + TODOS los dominios "
            "productivos comprobados en el artefacto aprobado"
        )
        return Resultado(PROMOTED, candidato)
    registro(
        f"convergencia {resultado}: UNKNOWN / NO RETRY / REQUIERE RECONCILIACIÓN"
    )
    return Resultado(UNKNOWN_RECONCILIATION_REQUIRED, candidato)


def main(argv: list[str] | None = None) -> int:
    entorno = dict(os.environ)
    token = entorno.get("VERCEL_PROJECT_PROMOTION_TOKEN", "")
    try:
        resultado = ejecutar(entorno)
    except BaseException as error:  # noqa: BLE001 - la red de seguridad del secreto
        # Una excepción inesperada imprimiría un traceback que GitHub Actions publica en
        # un log de repositorio PÚBLICO. Se corta aquí, se redacta y se sale cerrado.
        print(
            redactar(f"fallo no previsto: {type(error).__name__}: {error}", [token]),
            file=sys.stderr,
        )
        print(f"ESTADO={FAIL_CLOSED}")
        return CODIGOS_DE_SALIDA[FAIL_CLOSED]
    print(f"ESTADO={resultado.estado}")
    return resultado.codigo


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
