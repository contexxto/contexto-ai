"""Promotor de producción de Vercel · VERCEL-RELEASE-CONTROL-F-R1.

QUÉ GARANTIZA (R1-R4 de la unidad F-02):
  R1  el artefacto promovido corresponde al SHA que aprobaron `pytest` y `frontend`
  R2  se promueve únicamente ese artefacto
  R3  sin reconstrucción
  R4  solo después de una aprobación humana

QUÉ NO GARANTIZA, dicho de frente. Este programa protege un JOB, no el hecho de
publicar. Mientras «Auto-Assign Custom Production Domains» siga en ON —hoy lo está—
un merge a `main` publica por su cuenta y esto no gobierna nada. Apagar ese
interruptor es precondición de cutover, no una optimización, y está FUERA de esta
unidad. Tampoco cubre INV-FRESHNESS: no comprueba que el SHA siga siendo la cabeza
de `main` cuando la aprobación humana llega.

R4 MERECE UNA ADVERTENCIA APARTE. Este programa NO puede verificar que la aprobación
humana exista: las reglas de protección de un Environment de GitHub viven en la
consola, no en el repositorio, y ningún fichero de esta unidad puede leerlas. La
palabra `environment:` del YAML NOMBRA una puerta; no la construye. Un Environment
recién creado nace SIN required reviewers. Mientras nadie lo configure, R4 está
declarado pero no ejercido, y esta unidad no puede afirmar lo contrario.

CONTRATO DE LA API, extraído del OpenAPI oficial de Vercel (https://openapi.vercel.sh/,
10 717 362 bytes, 297 rutas, leído el 2026-09-07). Cada campo que este programa exige
está documentado; ninguno se infiere de la interfaz. Y cada campo que el contrato
declara OPCIONAL se trata aquí como ausente-hasta-que-se-demuestre:

  GET /v7/deployments
      El 200 declara required: [deployments, pagination]. Este programa exige los dos
      con el mismo rigor: un `deployments` ausente, nulo o que no sea lista es un
      fallo, no una página vacía.
      El ITEM del listado declara required: [created, createdAt, creator, inspectorUrl,
      name, projectId, readyState, type, uid, url]. `readySubstate` NO está en esa
      lista y `gitSource` NO existe en el item. De ahí dos reglas:
        · la identidad exige SIEMPRE una segunda llamada al detalle;
        · el prefiltro por `readySubstate` solo puede EXCLUIR lo que demuestra no ser
          STAGED. Un item que omita el campo pasa al detalle. Excluirlo por ausencia
          haría invisible a un segundo candidato y desarmaría la comprobación de
          ambigüedad, que es la única defensa de R2.
      `pagination` = {count, next, prev}, las tres requeridas. `next` es un timestamp
      nullable; `null` es la última página. Que ese valor se pase como `until` NO lo
      dice el schema con esas palabras: es INFERIDO de que `until` es el único
      parámetro documentado como «Get Deployments created before this timestamp».

  GET /v13/deployments/{idOrUrl}?withGitRepoInfo=true
      withGitRepoInfo: "When `true`, the response includes the `gitSource` object with
      the commit SHA, branch name, and connected repository metadata."
      El 200 es un `oneOf` de TRES variantes. `id` y `readyState` son requeridos en las
      tres. `readySubstate`, `target` y `gitSource` NO lo son en NINGUNA, y `projectId`
      solo en una. La ausencia de cualquiera descalifica al candidato.
      readyState  enum: BLOCKED BUILDING CANCELED ERROR INITIALIZING QUEUED READY
      readySubstate enum: PROMOTED ROLLING STAGED
          "STAGED: never seen production traffic". Es el estado documentado que
          corresponde al «Staged» que presupone F-02, no una palabra de la interfaz.
      target enum: production | staging | null (null = preview)
      gitSource es a su vez un `oneOf` de 19 formas. `type` es requerido en las 19;
      `sha` solo en 9. La identidad del repositorio se declara por repoId, o por
      org+repo, según la forma.
      source: el schema advierte "Best-effort guess for metrics only — not
          authoritative; do not gate behavior on it". Por eso NO se usa.

  POST /v10/projects/{projectId}/promote/{deploymentId}
      "Allows users to promote a deployment to production. Note: This does NOT rebuild
       the deployment." — esa frase es la prueba documental de R3.
      Éxito documentado: 201 y 202, ambos SIN cuerpo declarado (no traen `content`).
      Fallo documentado: 400 401 403 409 410 422.
      CUALQUIER OTRO CÓDIGO no está documentado, así que no se puede afirmar que el
      servidor rechazara: se trata como aceptación DESCONOCIDA y va a reconciliación.
      Documentación pública y schema coinciden en los dos códigos de éxito.

  GET /v4/aliases/{idOrAlias}
      required: alias, created, deploymentId, projectId, uid.
      deploymentId y projectId son además nullable: un `null` es NO RECONCILIADO,
      jamás una coincidencia.

POR QUÉ SOLO BIBLIOTECA ESTÁNDAR: el job de promoción no instala requirements. urllib
basta y no añade superficie. El transporte es inyectable para que las pruebas jamás
toquen la red, y NO sigue redirecciones: un 30x arrastraría la cabecera Authorization
a otro host.
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
    # Éxito ATESTIGUADO: esta ejecución emitió su único POST y después comprobó el
    # alias. Es el ÚNICO camino verde.
    PROMOTED: 0,
    # UNAVAILABLE sale distinto de cero A PROPÓSITO: el SHA que aprobó el CI no tiene
    # artefacto promovible. No se promovió nada —eso es lo importante— pero tampoco se
    # cumplió el encargo, y un verde silencioso lo escondería.
    UNAVAILABLE: 1,
    FAIL_CLOSED: 2,
    UNKNOWN_RECONCILIATION_REQUIRED: 3,
    # El alias YA servía el SHA aprobado ANTES de que esta ejecución hiciera nada.
    # Sigue siendo un no-op —no se repite la promoción— pero NO es una promoción
    # atestiguada por F: observar qué sirve Vercel no demuestra que F lo promoviera,
    # ni que la publicación esperase la aprobación humana, ni que no hubiera una
    # promoción manual fuera del workflow. Con «Auto-Assign Custom Production Domains»
    # en ON —hoy lo está— dejar esto en verde certificaría justo el bypass que C1
    # declara abierto. Por eso sale distinto de cero.
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

CODIGOS_DE_EXITO_DE_PROMOCION = frozenset({201, 202})
CODIGOS_DE_RECHAZO_DOCUMENTADOS = frozenset({400, 401, 403, 409, 410, 422})

HEX40 = re.compile(r"\A[0-9a-f]{40}\Z")

# `type` es requerido en las 19 formas de gitSource. Solo se acepta la familia GitHub:
# el CI que aprueba es GitHub Actions, así que un artefacto de otro origen no puede
# ser «el que aprobó el CI».
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
    """Sustituye cualquier secreto por un marcador.

    Sin suelo de longitud: un secreto corto también se redacta. Se aplica a TODO lo
    que sale del programa. No se imprime jamás el cuerpo de una respuesta ni una
    cabecera: solo campos que este programa elige explícitamente.
    """
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

    F-02 dejó dicho que la protección no puede depender solo de la condición `if:`:
    un PR que borre esa línea únicamente necesita pasar `pytest`, que no inspecciona
    .github/workflows/. Esta función vuelve a comprobar lo mismo desde dentro.
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

    Seguir una redirección con el opener por defecto reenvía la cabecera
    Authorization al destino. La API de Vercel no documenta redirecciones en estas
    rutas, así que un 30x es anómalo y aquí se trata como tal.
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
        # Un HTTPError SÍ es respuesta concluyente del servidor: hay código. Incluye
        # los 30x, que aquí llegan como error porque no se siguen.
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

    Los 201 y 202 de la promoción no declaran `content` en el contrato: exigir JSON
    ahí convertiría una aceptación en un fallo de transporte.
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
    equipo: str | None = None
    _post_emitido: bool = field(default=False, init=False, repr=False)

    def _cabeceras(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    def _url(self, ruta: str, consulta: dict | None = None) -> str:
        parametros = dict(consulta or {})
        if self.equipo:
            parametros["teamId"] = self.equipo
        limpios = {k: v for k, v in parametros.items() if v is not None}
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
        """EL único POST del programa. Sin reintentos, y estructuralmente irrepetible.

        F-02 §4.5: como máximo un POST por ejecución. No basta con no escribir el
        bucle: cualquier ruta de código que intente un segundo POST revienta aquí.
        """
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

    `projectId`, `target` y `state` se usan conforme a su semántica documentada: la
    API los describe como filtros de igualdad sobre propiedades que forman parte del
    propio predicado del candidato. La garantía presupone que Vercel cumple ese
    contrato. El cliente vuelve a validar TODOS esos campos en cada detalle.

    El filtro `sha` NO se usa porque su semántica de coincidencia exacta no está
    documentada: su schema no declara `pattern`, `minLength` ni `maxLength`, y no hay
    una sola frase sobre prefijos.

    Precisión que corrige una versión anterior de este comentario: NO es cierto que
    un filtro que estreche de más solo pueda producir UNAVAILABLE. Reducir dos
    candidatos a uno escondería una ambigüedad, que es precisamente el caso que R2
    necesita ver. Lo que justifica los tres filtros no es que «estrechen de más sin
    consecuencia», sino su semántica documentada más la revalidación en el detalle.
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
        # `deployments` es un campo REQUERIDO del contrato y se exige con el mismo
        # rigor que `pagination`. Un `or []` aquí convertiría una respuesta rota en
        # una página vacía, y una página vacía en un candidato menos.
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
    # Se agotó el tope sin llegar al final: NO se sabe si falta un candidato.
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
        # `type` es requerido en las 19 formas: si no está, o no es de la familia
        # GitHub, el artefacto no puede provenir del CI que aprobó.
        return f"gitSource.type {tipo!r} no es de la familia GitHub"
    duenio, _, repositorio = esperado.repositorio.partition("/")
    org = origen.get("org")
    repo = origen.get("repo")
    # La identidad del repositorio se declara por repoId o por org+repo según la
    # forma. Cuando vienen los nombres se exigen; cuando no, la pertenencia queda
    # sostenida por projectId, que ya se comprobó. Es un límite declarado, no un
    # descuido: el contrato no garantiza org/repo en todas las formas.
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
    """Devuelve None si el despliegue es promovible; si no, por qué no lo es.

    Todos los campos consultados salvo `id` son opcionales en el schema, así que la
    ausencia descalifica. No hay ninguna rama que acepte por omisión.
    """
    if not isinstance(detalle, dict):
        return "el detalle no es un objeto"
    if identificador is not None and detalle.get("id") != identificador:
        # `id` es requerido en las tres variantes del detalle. Comprobarlo ata la
        # identidad del listado con la del documento que se valida y con la del POST.
        return f"el detalle responde por {detalle.get('id')!r}, no por {identificador!r}"
    if detalle.get("projectId") != esperado.proyecto:
        return f"projectId {detalle.get('projectId')!r} no es el esperado"
    if detalle.get("target") != "production":
        return f"target {detalle.get('target')!r} no es production"
    if detalle.get("readyState") != "READY":
        return f"readyState {detalle.get('readyState')!r} no es READY"
    if detalle.get("readySubstate") != "STAGED":
        # PROMOTED ya vio tráfico de producción; ROLLING está en transición.
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
    comprobación de ambigüedad, que es la única defensa de R2: descartar aquí no
    cierra, abre. Por eso solo se excluye cuando el campo ESTÁ y dice otra cosa.
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
        # `uid` es requerido en el item. Si falta, el listado no cumple el contrato y
        # no se puede saber si ese elemento era un segundo candidato.
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


# ── (4) Alias canónico ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class EstadoAlias:
    despliegue: str | None
    proyecto: str | None

    @property
    def reconciliado(self) -> bool:
        return bool(self.despliegue) and bool(self.proyecto)


def leer_alias(cliente: ClienteVercel, alias: str) -> EstadoAlias:
    """Lectura CANÓNICA. GET /v2/deployments/{id}/aliases no sirve para esto:
    no devuelve deploymentId ni projectId, así que solo corrobora una hipótesis
    ya formada. Aquí hace falta producir la identidad, no confirmarla."""
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


def el_alias_ya_sirve_el_sha_aprobado(
    detalle: dict, estado: EstadoAlias, esperado: Esperado
) -> bool:
    """¿El alias canónico YA sirve un artefacto construido del SHA aprobado?

    Predicado DISTINTO del de candidato promovible, y a propósito: aquí NO se mira
    `readySubstate`. Un despliegue que ya sirve producción está documentado como
    `PROMOTED`, no como `STAGED`; exigir STAGED haría que este caso nunca se
    detectara, que es exactamente el defecto que tenía la primera versión: la
    selección devolvía cero candidatos y el programa terminaba en UNAVAILABLE sin
    llegar a mirar qué servía el alias.

    Lo que sí se exige: que el alias esté reconciliado en el proyecto esperado, que
    el documento responda por el mismo despliegue que nombra el alias, y que su
    origen sea el commit aprobado, del repositorio esperado.
    """
    if not estado.reconciliado:
        return False
    if estado.proyecto != esperado.proyecto:
        return False
    if not isinstance(detalle, dict):
        return False
    if detalle.get("id") != estado.despliegue:
        return False
    if detalle.get("projectId") != esperado.proyecto:
        return False
    if detalle.get("target") != "production":
        return False
    return _motivo_de_descarte_del_origen(detalle.get("gitSource"), esperado) is None


def alias_apunta_a(estado: EstadoAlias, despliegue: str, proyecto: str) -> bool:
    """Objetivo alcanzado solo si AMBOS identificadores coinciden y no son nulos.

    La comprobación de `reconciliado` es redundante con las dos igualdades cuando
    `despliegue` y `proyecto` son cadenas no vacías. Se conserva porque documenta la
    regla que exige F-02 —un `null` es NO reconciliado, nunca coincidencia— y porque
    protege el caso en que alguien llame a esta función con un objetivo vacío.
    """
    if not despliegue or not proyecto:
        return False
    return (
        estado.reconciliado
        and estado.despliegue == despliegue
        and estado.proyecto == proyecto
    )


# ── (5) Reconciliación acotada ─────────────────────────────────────────────────


def reconciliar(
    cliente: ClienteVercel,
    alias: str,
    despliegue: str,
    proyecto: str,
    registro: Registro,
) -> bool:
    """Sondeo ACOTADO del alias exacto. Nunca infinito, nunca un segundo POST.

    Devuelve True solo si el alias queda comprobadamente en el objetivo. Cualquier
    otro desenlace es UNKNOWN: el éxito no se concede por ausencia de evidencia.
    """
    inicio = cliente.reloj()
    for sondeo in range(SONDEOS_MAXIMOS):
        if cliente.reloj() - inicio > VENTANA_MAXIMA_DE_SONDEO:
            registro("ventana de sondeo agotada por tiempo")
            return False
        try:
            estado = leer_alias(cliente, alias)
        except (ErrorBarrera, ErrorTransporte) as error:
            registro(f"sondeo {sondeo + 1}: sin lectura concluyente ({error})")
        else:
            if alias_apunta_a(estado, despliegue, proyecto):
                registro(f"sondeo {sondeo + 1}: alias reconciliado en el objetivo")
                return True
            registro(f"sondeo {sondeo + 1}: alias aún no reconciliado")
        if sondeo < SONDEOS_MAXIMOS - 1:
            cliente.dormir(ESPERA_ENTRE_SONDEOS)
    return False


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
        # Fail-closed ante cualquier entrada requerida ausente. Se nombran las
        # variables, nunca sus valores.
        registro(f"faltan variables requeridas: {', '.join(faltan)}")
        return Resultado(FAIL_CLOSED, "entrada requerida ausente")

    try:
        contexto = validar_contexto_github(entorno)
    except ErrorBarrera as error:
        registro(f"barrera del programa: {error}")
        return Resultado(FAIL_CLOSED, str(error))

    proyecto = entorno["VERCEL_PROMOTION_PROJECT_ID"]
    alias = entorno["VERCEL_PROMOTION_ALIAS"]
    esperado = Esperado(
        proyecto=proyecto, sha=contexto.sha, repositorio=contexto.repositorio
    )
    cliente = ClienteVercel(
        token=token,
        registro=registro,
        transporte=transporte,
        dormir=dormir,
        reloj=reloj,
        equipo=entorno.get("VERCEL_PROMOTION_TEAM_ID") or None,
    )
    registro(f"SHA aprobado por el CI: {contexto.sha}")

    try:
        validos = seleccionar_candidato(cliente, esperado, registro)
    except ErrorBarrera as error:
        registro(f"selección cerrada: {error}")
        return Resultado(FAIL_CLOSED, str(error))
    except ErrorTransporte as error:
        registro(f"listado sin respuesta concluyente: {error}")
        return Resultado(FAIL_CLOSED, "listado no concluyente")

    # El alias se lee ANTES de concluir nada sobre la disponibilidad. Si ya sirve el
    # SHA aprobado, ese despliegue estará en `PROMOTED` y por tanto NO aparecerá entre
    # los candidatos: mirar solo la lista daría UNAVAILABLE y se perdería el hecho.
    try:
        estado_alias = leer_alias(cliente, alias)
    except (ErrorBarrera, ErrorTransporte) as error:
        registro(f"no se pudo leer el alias canónico: {error}")
        return Resultado(FAIL_CLOSED, "alias no legible")

    if estado_alias.reconciliado:
        try:
            servido = detalle_de(cliente, estado_alias.despliegue)
        except (ErrorBarrera, ErrorTransporte) as error:
            # Sin poder leer lo que sirve el alias no se descarta el caso no
            # atestiguado, así que no se promueve.
            registro(f"no se pudo leer lo que sirve el alias: {error}")
            return Resultado(FAIL_CLOSED, "lo servido por el alias no es legible")
        if el_alias_ya_sirve_el_sha_aprobado(servido, estado_alias, esperado):
            registro(
                "el alias YA servía el SHA aprobado antes de esta ejecución. "
                "No se emite POST. Esto NO acredita que F lo promoviera, ni que la "
                "publicación esperara la aprobación humana, ni que no hubiera una "
                "promoción manual fuera del workflow."
            )
            return Resultado(ALREADY_CURRENT_UNATTESTED, estado_alias.despliegue)

    if not validos:
        registro("cero candidatos promovibles para este SHA; no se promueve nada")
        return Resultado(UNAVAILABLE, "sin artefacto promovible")

    candidato = validos[0]

    # ── el único POST ──
    try:
        respuesta = cliente.post_promocion(proyecto, candidato)
    except ErrorTransporte as error:
        # Aceptación DESCONOCIDA. La continuidad documentada del timeout de la CLI
        # no cubre este caso: la petición pudo no llegar a registrarse.
        registro(f"POST sin respuesta concluyente ({error}); se pasa a reconciliar")
        return _desenlace_incierto(cliente, alias, candidato, proyecto, registro)
    except ErrorBarrera as error:
        registro(f"barrera del POST: {error}")
        return Resultado(FAIL_CLOSED, str(error))

    if respuesta.estado in CODIGOS_DE_EXITO_DE_PROMOCION:
        # Aceptación CONOCIDA. Aquí el reloj solo mide la espera del cliente, y la
        # promoción sigue su curso aunque venza. Se reconcilia para poder afirmarlo.
        registro(f"promoción aceptada por el servidor ({respuesta.estado})")
        return _desenlace_incierto(cliente, alias, candidato, proyecto, registro)

    if respuesta.estado in CODIGOS_DE_RECHAZO_DOCUMENTADOS:
        registro(f"promoción rechazada por el servidor ({respuesta.estado})")
        return Resultado(FAIL_CLOSED, f"POST devolvió {respuesta.estado}")

    # Código NO documentado para este endpoint: no se puede afirmar que rechazara.
    # Declararlo rechazo escondería una promoción que quizá sí ocurrió.
    registro(f"código no documentado tras el POST ({respuesta.estado}); se reconcilia")
    return _desenlace_incierto(cliente, alias, candidato, proyecto, registro)


def _desenlace_incierto(
    cliente: ClienteVercel,
    alias: str,
    candidato: str,
    proyecto: str,
    registro: Registro,
) -> Resultado:
    """Cierra la ejecución DESPUÉS de que esta corrida haya emitido su único POST.

    Solo se llega aquí con `post_emitido`. Por eso el PROMOTED que sale de aquí sí es
    atestiguado: hubo un POST de esta ejecución y luego una comprobación del alias.
    """
    if reconciliar(cliente, alias, candidato, proyecto, registro):
        # Se deja constancia de CÓMO se obtuvo el éxito: por reconciliación posterior
        # al POST, no por una respuesta concluyente del servidor.
        registro(
            "PROMOTED atestiguado: POST de esta ejecución + alias comprobado por "
            "reconciliación"
        )
        return Resultado(PROMOTED, candidato)
    registro("UNKNOWN / NO RETRY / REQUIERE RECONCILIACIÓN")
    return Resultado(UNKNOWN_RECONCILIATION_REQUIRED, candidato)


def main(argv: list[str] | None = None) -> int:
    entorno = dict(os.environ)
    token = entorno.get("VERCEL_PROJECT_PROMOTION_TOKEN", "")
    try:
        resultado = ejecutar(entorno)
    except BaseException as error:  # noqa: BLE001 - la red de seguridad del secreto
        # Una excepción inesperada imprimiría un traceback que GitHub Actions publica
        # en un log de repositorio PÚBLICO. Se corta aquí, se redacta y se sale
        # cerrado. Perder el traceback es el precio de no arriesgar el token.
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
