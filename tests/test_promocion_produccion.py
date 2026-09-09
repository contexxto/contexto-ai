"""Pruebas de COMPORTAMIENTO del promotor · VERCEL-RELEASE-CONTROL-F-R1.

No tocan la red, no usan credenciales y no llaman a la API de Vercel. El transporte es
inyectable y aquí se sustituye por un doble que responde con cuerpos sintéticos ajustados
al schema oficial. El reloj y la espera también se inyectan, para que el sondeo acotado se
pueda probar sin esperar de verdad.

EL DOBLE LEE LA QUERY y responde POR DOMINIO. Una versión anterior descartaba la query
—dejando fuera de prueba `withGitRepoInfo`, el cursor `until` y los filtros del listado— y
trataba el alias como uno solo. Ahora la página se elige por el cursor y cada dominio
productivo tiene su propio guion, porque la garantía nueva es que **todos** converjan.

HONESTIDAD SOBRE EL RED: contra el padre estas pruebas no arrancaban —el módulo no
existía— y eso es un ImportError, NO un rojo de comportamiento. Lo que demuestra que
discriminan son las mutaciones del informe.
"""

import contextlib
import importlib.util
import io
import pathlib
import sys
import urllib.parse

import pytest
import yaml

_RUTA = (
    pathlib.Path(__file__).resolve().parent.parent / "scripts" / "promover_produccion.py"
)

SHA_BUENO = "a" * 40
SHA_OTRO = "b" * 40
PROYECTO = "prj_ejemplo"
ALIAS_A = "contexxto.com"
ALIAS_B = "contexto-ai-six.vercel.app"
ALIASES = f"{ALIAS_A},{ALIAS_B}"
REPO = "contexxto/contexto-ai"
TOKEN = "tok_sintetico_no_es_un_secreto_real_0123456789"


_AUSENTE = object()


@contextlib.contextmanager
def cargar_por_ruta(nombre: str, ruta: pathlib.Path):
    """Carga un módulo por ruta y DEJA `sys.modules` exactamente como estaba.

    Registrar antes de ejecutar es obligatorio: el módulo usa
    `from __future__ import annotations`, así que las anotaciones son cadenas y
    dataclasses necesita resolverlas contra un módulo presente en `sys.modules`.

    Pero dejar ese registro puesto contamina el resto de la sesión de pytest: es estado
    global que sobrevive a este fichero y podría crear una dependencia de orden entre
    ficheros de prueba. Por eso se restaura el estado previo en `finally`, sea cual sea
    el desenlace, distinguiendo «no estaba» de «estaba con otro valor».

    Vive como función propia, y no dentro de la fixture, para que se pueda probar
    directamente: una restauración que solo se ejercita de rebote no está probada.
    """
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    modulo = importlib.util.module_from_spec(spec)
    previo = sys.modules.get(nombre, _AUSENTE)
    sys.modules[nombre] = modulo
    try:
        spec.loader.exec_module(modulo)
        yield modulo
    finally:
        if previo is _AUSENTE:
            sys.modules.pop(nombre, None)
        else:
            sys.modules[nombre] = previo


@pytest.fixture(scope="module")
def promotor():
    with cargar_por_ruta("promover_produccion", _RUTA) as modulo:
        yield modulo


# ── Dobles ─────────────────────────────────────────────────────────────────────


def entorno(**cambios) -> dict:
    base = {
        "GITHUB_EVENT_NAME": "push",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": SHA_BUENO,
        "GITHUB_REPOSITORY": REPO,
        "VERCEL_PROJECT_PROMOTION_TOKEN": TOKEN,
        "VERCEL_PROMOTION_PROJECT_ID": PROYECTO,
        "VERCEL_PROMOTION_ALIAS": ALIASES,
    }
    base.update(cambios)
    return {k: v for k, v in base.items() if v is not None}


class _Quitar:
    pass


_QUITAR = _Quitar()

# Identificadores que representan «lo que los dominios servían antes»: mismo proyecto,
# SHA distinto y ya promovido. El doble les da un detalle por defecto.
_DESPLIEGUES_VIEJOS = frozenset({"dpl_previo", "dpl_otro", "dpl_viejo", "dpl_9"})


def item_listado(uid: str, **cambios) -> dict:
    cuerpo = {
        "uid": uid,
        "projectId": PROYECTO,
        "target": "production",
        "readyState": "READY",
        "readySubstate": "STAGED",
        "created": 1,
        "createdAt": 1,
        "name": "contexto",
        "url": "x",
        "inspectorUrl": "x",
        "creator": {},
        "type": "LAMBDAS",
    }
    cuerpo.update(cambios)
    return {k: v for k, v in cuerpo.items() if v is not _QUITAR}


def detalle(uid: str, sha: str = SHA_BUENO, origen=None, **cambios) -> dict:
    cuerpo = {
        "id": uid,
        "projectId": PROYECTO,
        "target": "production",
        "readyState": "READY",
        "readySubstate": "STAGED",
        "aliasAssigned": True,
        "gitSource": origen
        if origen is not None
        else {
            "type": "github",
            "repoId": 1,
            "org": "contexxto",
            "repo": "contexto-ai",
            "sha": sha,
        },
    }
    cuerpo.update(cambios)
    return {k: v for k, v in cuerpo.items() if v is not _QUITAR}


def cuerpo_alias(host: str, uid: str = "dpl_previo", proyecto: str = PROYECTO, **cambios) -> dict:
    """Cuerpo del 200 de GET /v4/aliases/{idOrAlias}, con sus cinco campos requeridos.

    `**cambios` y `_QUITAR` siguen el mismo idioma que `detalle()` e `item_listado()`:
    sirven para construir cuerpos que INCUMPLEN el contrato sin escribirlos a mano.
    """
    cuerpo = {
        "alias": host,
        "created": "x",
        "uid": f"alias_{host}",
        "deploymentId": uid,
        "projectId": proyecto,
    }
    cuerpo.update(cambios)
    return {k: v for k, v in cuerpo.items() if v is not _QUITAR}


def ronda(uid_a, uid_b=None, proyecto=PROYECTO):
    """Una ronda de lectura de los dos dominios. `uid_b` por defecto igual que `uid_a`."""
    if uid_b is None:
        uid_b = uid_a
    return {ALIAS_A: (uid_a, proyecto), ALIAS_B: (uid_b, proyecto)}


class Transporte:
    """Doble consciente de la query y de CADA DOMINIO.

    `rondas` es una lista de dicts {host: (uid, proyecto) | respuesta cruda}. La lectura
    n-ésima de un host consume la ronda n; al agotarse se repite la última.
    """

    def __init__(
        self,
        promotor,
        paginas=None,
        detalles=None,
        rondas=None,
        post=None,
        listado=None,
    ):
        self.p = promotor
        self.paginas = paginas if paginas is not None else [([], None)]
        self.detalles = detalles or {}
        self.rondas = rondas if rondas is not None else [ronda("dpl_previo")]
        self.post = post
        self.listado = listado
        self.llamadas: list[tuple[str, str, dict]] = []
        self._por_host: dict[str, int] = {}

    @property
    def posts(self) -> int:
        return sum(1 for m, _, _ in self.llamadas if m == "POST")

    def lecturas_de(self, host: str) -> int:
        return self._por_host.get(host, 0)

    @property
    def lecturas_de_alias(self) -> int:
        return sum(self._por_host.values())

    def consultas_de(self, fragmento: str) -> list[dict]:
        return [q for _m, u, q in self.llamadas if fragmento in u]

    def __call__(self, metodo, url, cabeceras, timeout):
        partes = urllib.parse.urlsplit(url)
        consulta = dict(urllib.parse.parse_qsl(partes.query))
        self.llamadas.append((metodo, url, consulta))
        assert timeout is not None and timeout > 0, "toda llamada necesita timeout"
        assert cabeceras.get("Authorization", "").startswith("Bearer ")
        assert "teamId" not in consulta, "el token es de proyecto: no se envía teamId"
        if metodo == "POST":
            return self._responder(self.post)
        if "/v7/deployments" in partes.path:
            if self.listado is not None:
                return self._responder(self.listado)
            return self._pagina(consulta)
        if "/v13/deployments/" in partes.path:
            uid = partes.path.split("/v13/deployments/")[1]
            if uid not in self.detalles:
                if uid in _DESPLIEGUES_VIEJOS:
                    return self.p.Respuesta(
                        200, detalle(uid, sha=SHA_OTRO, readySubstate="PROMOTED")
                    )
                raise AssertionError(f"detalle no previsto para {uid}")
            return self._responder(self.detalles[uid])
        if "/v4/aliases/" in partes.path:
            host = urllib.parse.unquote(partes.path.split("/v4/aliases/")[1])
            n = self._por_host.get(host, 0)
            self._por_host[host] = n + 1
            if host not in self.rondas[0]:
                raise AssertionError(f"dominio no previsto: {host}")
            r = self.rondas[min(n, len(self.rondas) - 1)][host]
            if isinstance(r, tuple) and len(r) == 2 and isinstance(r[1], str):
                return self.p.Respuesta(200, cuerpo_alias(host, r[0], r[1]))
            return self._responder(r)
        raise AssertionError(f"URL no prevista: {url}")

    def _pagina(self, consulta):
        cursor = consulta.get("until")
        if cursor is None:
            indice = 0
        else:
            indice = None
            for i, (_elementos, siguiente) in enumerate(self.paginas):
                if siguiente is not None and str(siguiente) == str(cursor):
                    indice = i + 1
                    break
            if indice is None:
                raise AssertionError(f"cursor `until` desconocido: {cursor!r}")
        if indice >= len(self.paginas):
            raise AssertionError("se pidieron más páginas de las previstas")
        elementos, siguiente = self.paginas[indice]
        return self.p.Respuesta(
            200,
            {
                "deployments": elementos,
                "pagination": {"count": len(elementos), "next": siguiente, "prev": None},
            },
        )

    def _responder(self, valor):
        if valor is None:
            raise self.p.ErrorTransporte("sin respuesta")
        if isinstance(valor, Exception):
            raise valor
        if isinstance(valor, tuple):
            return self.p.Respuesta(valor[0], valor[1])
        return self.p.Respuesta(200, valor)


def correr(promotor, transporte, ent=None, reloj=None):
    salida = io.StringIO()
    marcas = iter(reloj or [0.0] * 400)
    resultado = promotor.ejecutar(
        ent if ent is not None else entorno(),
        transporte=transporte,
        dormir=lambda _s: None,
        reloj=lambda: next(marcas, 10_000.0),
        salida=salida,
    )
    return resultado, salida.getvalue()


def guion_nominal(promotor, **cambios):
    """Camino feliz: ambos dominios en un despliegue viejo, un candidato válido."""
    base = dict(
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1")},
        rondas=[ronda("dpl_previo"), ronda("dpl_1")],
        post=(202, None),
    )
    base.update(cambios)
    return Transporte(promotor, **base)


# ── (A) LOS DOS DOMINIOS · la garantía nueva ───────────────────────────────────


def test_promocion_verde_solo_si_convergen_los_dos_dominios(promotor):
    transporte = guion_nominal(promotor)
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.PROMOTED
    assert resultado.codigo == 0
    assert transporte.posts == 1
    assert transporte.lecturas_de(ALIAS_A) >= 2
    assert transporte.lecturas_de(ALIAS_B) >= 2, "el segundo dominio también se lee"
    assert "TODOS los dominios" in salida or "convergencia TODOS" in salida


def test_convergencia_parcial_tras_el_post_es_unknown_no_promoted(promotor):
    """El estado que esta unidad existe para detectar: producción a medio camino."""
    transporte = guion_nominal(
        promotor,
        # tras el POST, contexxto.com converge pero el .vercel.app se queda atrás
        rondas=[ronda("dpl_previo"), {ALIAS_A: ("dpl_1", PROYECTO), ALIAS_B: ("dpl_previo", PROYECTO)}],
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.UNKNOWN_RECONCILIATION_REQUIRED
    assert resultado.codigo != 0
    assert resultado.estado != promotor.PROMOTED
    assert transporte.posts == 1, "un solo POST, jamás un reintento"
    assert "convergencia PARCIAL" in salida
    assert "UNKNOWN / NO RETRY / REQUIERE RECONCILIACIÓN" in salida


def test_solo_el_segundo_dominio_converge_tambien_es_unknown(promotor):
    transporte = guion_nominal(
        promotor,
        rondas=[ronda("dpl_previo"), {ALIAS_A: ("dpl_previo", PROYECTO), ALIAS_B: ("dpl_1", PROYECTO)}],
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.UNKNOWN_RECONCILIATION_REQUIRED
    assert transporte.posts == 1


def test_los_dos_ya_actuales_antes_del_post_es_no_atestiguado(promotor):
    """Ambos dominios ya sirven el SHA aprobado: no-op, cero POST, y NO verde."""
    transporte = Transporte(
        promotor,
        paginas=[([], None)],  # ya está promovido: no aparece como STAGED
        detalles={"dpl_servido": detalle("dpl_servido", readySubstate="PROMOTED")},
        rondas=[ronda("dpl_servido")],
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.ALREADY_CURRENT_UNATTESTED
    assert resultado.codigo != 0
    assert transporte.posts == 0
    assert "NO acredita" in salida


@pytest.mark.parametrize("substate", ["PROMOTED", "STAGED", "ROLLING"])
def test_la_deteccion_de_lo_ya_servido_no_depende_del_readySubstate(promotor, substate):
    """Los TRES valores del enum deben dar el MISMO veredicto.

    Esta prueba existía y la reescritura de R2 la perdió al cambiar el doble de `alias=`
    a `rondas=`. Se restaura como paramétrica y no como bucle: un bucle se detiene en el
    primer valor que falla y solo informa de uno, así que oculta si los otros dos también
    están rotos.

    Lo que fija es que la detección de «esto ya estaba servido» NO puede colgar de
    `readySubstate`. Un despliegue que ya sirve producción está documentado como
    `PROMOTED`, no como `STAGED`; una versión anterior solo miraba candidatos `STAGED`,
    veía cero y terminaba en `UNAVAILABLE` sin llegar a leer el alias, de modo que el
    caso ni se detectaba. Por eso el listado va VACÍO aquí: si la detección dependiera
    del listado o del substate, no habría veredicto que dar.
    """
    transporte = Transporte(
        promotor,
        paginas=[([], None)],
        detalles={"dpl_servido": detalle("dpl_servido", readySubstate=substate)},
        rondas=[ronda("dpl_servido")],
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.ALREADY_CURRENT_UNATTESTED, substate
    assert resultado.codigo != 0, "no puede terminar verde"
    assert resultado.estado != promotor.PROMOTED
    assert resultado.estado != promotor.UNAVAILABLE
    assert transporte.posts == 0
    assert "NO acredita" in salida


# ── (A3) lo que sirven los dominios tiene que ser LEGIBLE ─────────────────────
# `_estado_preexistente` lee el detalle del despliegue que sirven los dominios para
# decidir si ya era el SHA aprobado. Si esa lectura no es concluyente, cierra.
#
# Esa guarda no la sostenia ninguna prueba, y es la unica que impide seguir adelante sin
# saber que hay en produccion. Sustituir su `return Resultado(FAIL_CLOSED, ...)` por
# `return None` dejaba la suite entera en verde y convertia este guion en PROMOTED con
# un POST. Por eso el candidato de abajo es VALIDO: sin candidato el mutante terminaria
# en UNAVAILABLE y la mutacion pareceria inocua.


@pytest.mark.parametrize(
    "respuesta,motivo",
    [
        ((500, {"error": "x"}), "codigo 500"),
        ((503, None), "codigo 503"),
        ((404, {"error": "x"}), "codigo 404: el despliegue servido ya no existe"),
        ((200, ["no", "es", "objeto"]), "cuerpo que es lista"),
        ((200, "una cadena"), "cuerpo que es cadena"),
        ((200, None), "cuerpo nulo"),
        # `None` en el doble significa que el transporte no responde: `_responder` lanza
        # ErrorTransporte, y `cliente.get` lo reintenta de forma acotada antes de rendirse.
        (None, "fallo de transporte"),
    ],
)
def test_lo_servido_por_los_dominios_ILEGIBLE_es_fail_closed_sin_post(
    promotor, respuesta, motivo
):
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1"), "dpl_servido": respuesta},
        rondas=[ronda("dpl_servido"), ronda("dpl_1")],
        post=(202, None),
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED, motivo
    assert resultado.estado != promotor.PROMOTED
    assert transporte.posts == 0, f"no se puede promover sin saber que hay: {motivo}"
    # El `detalle` NOMBRA la guarda. Sin esta afirmacion, la prueba solo miraria el
    # desenlace, y este proyecto ya sabe lo que cuesta eso.
    assert resultado.detalle == "lo servido por los dominios no es legible"
    assert "no se pudo leer lo que sirven los dominios" in salida


def test_el_candidato_del_caso_anterior_SI_es_promovible(promotor):
    """Contrapunto obligatorio: demuestra que el guion de arriba llega a promover cuando
    lo servido SI se puede leer, y por tanto que el cero POST lo produce la guarda y no
    la falta de candidato."""
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={
            "dpl_1": detalle("dpl_1"),
            "dpl_servido": detalle("dpl_servido", sha=SHA_OTRO, readySubstate="PROMOTED"),
        },
        rondas=[ronda("dpl_servido"), ronda("dpl_1")],
        post=(202, None),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.PROMOTED
    assert transporte.posts == 1


def test_solo_UNO_actual_antes_del_post_es_fail_closed_sin_post(promotor):
    """Convergencia parcial PREEXISTENTE: no se promueve, y no se disimula."""
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={
            "dpl_1": detalle("dpl_1"),
            "dpl_servido": detalle("dpl_servido", readySubstate="PROMOTED"),
        },
        rondas=[{ALIAS_A: ("dpl_servido", PROYECTO), ALIAS_B: ("dpl_previo", PROYECTO)}],
        post=(202, None),
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.posts == 0, "cero POST ante convergencia parcial previa"
    assert "DISTINTOS entre sí" in salida


def test_dominios_divergentes_antes_del_post_es_fail_closed_sin_post(promotor):
    """Los dos dominios apuntan a despliegues distintos, ninguno el aprobado."""
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1")},
        rondas=[{ALIAS_A: ("dpl_previo", PROYECTO), ALIAS_B: ("dpl_otro", PROYECTO)}],
        post=(202, None),
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert resultado.detalle == "dominios divergentes"
    assert transporte.posts == 0


@pytest.mark.parametrize("host_malo", [ALIAS_A, ALIAS_B])
def test_cualquier_dominio_no_reconciliado_es_fail_closed(promotor, host_malo):
    r = ronda("dpl_previo")
    r[host_malo] = {"alias": host_malo, "created": "x", "uid": "a", "deploymentId": None, "projectId": PROYECTO}
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1")},
        rondas=[r],
        post=(202, None),
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.posts == 0
    assert "no reconciliado" in salida


@pytest.mark.parametrize("host_malo", [ALIAS_A, ALIAS_B])
def test_cualquier_dominio_de_otro_proyecto_es_fail_closed(promotor, host_malo):
    r = ronda("dpl_previo")
    r[host_malo] = ("dpl_previo", "prj_ajeno")
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1")},
        rondas=[r],
        post=(202, None),
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.posts == 0
    assert "no es el esperado" in salida


@pytest.mark.parametrize("host_malo", [ALIAS_A, ALIAS_B])
@pytest.mark.parametrize(
    "cuerpo,motivo",
    [
        ((200, ["no", "es", "objeto"]), "cuerpo que no es objeto"),
        ((200, "una cadena"), "cuerpo que es cadena"),
        ((200, None), "cuerpo vacío"),
    ],
)
def test_cuerpo_de_alias_que_no_es_objeto_es_fail_closed(promotor, host_malo, cuerpo, motivo):
    """Regresión que reintrodujo la reescritura de R2 y que el arnés de 63 destapó.

    La guarda `isinstance(cuerpo, dict)` de `leer_alias` había quedado sin ninguna
    prueba que la ejercitara: su mutación nacía inerte.
    """
    r = ronda("dpl_previo")
    r[host_malo] = cuerpo
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1")},
        rondas=[r],
        post=(202, None),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED, motivo
    assert transporte.posts == 0


@pytest.mark.parametrize("host_malo", [ALIAS_A, ALIAS_B])
def test_identificadores_de_alias_que_no_son_cadena_no_reconcilian(promotor, host_malo):
    """Defensa contra confusión de tipos, vista DESDE FUERA: un 7 no promueve nada.

    Esta prueba afirma el DESENLACE, y por sí sola no verifica la guarda de tipos: el
    mismo `FAIL_CLOSED` se alcanza por otro camino —el `projectId` ajeno— si la guarda
    desaparece. Se conserva porque el desenlace también hay que fijarlo; quien verifica
    la guarda es `test_leer_alias_anula_un_deploymentId_que_no_es_cadena_util`.
    """
    r = ronda("dpl_previo")
    r[host_malo] = (200, cuerpo_alias(host_malo, uid=7, proyecto=8))
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1")},
        rondas=[r],
        post=(202, None),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.posts == 0


# ── (A1) `leer_alias` probada DIRECTAMENTE ─────────────────────────────────────
# Por qué hace falta este doble y no basta con `Transporte`: una prueba que solo afirma
# el desenlace no puede verificar una guarda cuando otra guarda produce ese MISMO
# desenlace. Medido: con la guarda de tipos el motivo es «no reconciliado» y sin ella es
# «de otro proyecto», pero los dos son FAIL_CLOSED con cero POST, así que la mutación
# sobrevivía. Para probar una guarda hay que afirmar su efecto, no el del sistema entero.


class ClienteDeAlias:
    """Cliente mínimo: `leer_alias` solo necesita `.get()`. No toca la red."""

    def __init__(self, promotor, cuerpo, estado=200):
        self.p = promotor
        self.cuerpo = cuerpo
        self.estado = estado
        self.rutas: list[str] = []

    def get(self, ruta, consulta=None):
        self.rutas.append(ruta)
        return self.p.Respuesta(self.estado, self.cuerpo)


@pytest.mark.parametrize(
    "valor",
    [7, 0, 7.5, True, False, None, ["dpl_x"], {"id": "dpl_x"}, b"dpl_x", "", ()],
)
def test_leer_alias_anula_un_deploymentId_que_no_es_cadena_util(promotor, valor):
    cliente = ClienteDeAlias(promotor, cuerpo_alias(ALIAS_A, uid=valor))
    estado = promotor.leer_alias(cliente, ALIAS_A)
    assert estado.despliegue is None, f"{valor!r} no es un identificador de despliegue"
    assert estado.reconciliado is False


@pytest.mark.parametrize(
    "valor",
    [8, 0, 8.5, True, False, None, ["prj_x"], {"id": "prj_x"}, b"prj_x", "", ()],
)
def test_leer_alias_anula_un_projectId_que_no_es_cadena_util(promotor, valor):
    cliente = ClienteDeAlias(promotor, cuerpo_alias(ALIAS_A, proyecto=valor))
    estado = promotor.leer_alias(cliente, ALIAS_A)
    assert estado.proyecto is None, f"{valor!r} no es un identificador de proyecto"
    assert estado.reconciliado is False


def test_leer_alias_CONSERVA_los_identificadores_cuando_si_son_cadena(promotor):
    """El contrapunto obligatorio: la guarda anula lo inválido, no lo válido."""
    cliente = ClienteDeAlias(promotor, cuerpo_alias(ALIAS_A, uid="dpl_x"))
    estado = promotor.leer_alias(cliente, ALIAS_A)
    assert estado.despliegue == "dpl_x"
    assert estado.proyecto == PROYECTO
    assert estado.reconciliado is True


@pytest.mark.parametrize(
    "devuelto,motivo",
    [
        (_QUITAR, "campo ausente"),
        (None, "nulo"),
        (7, "entero"),
        (["contexxto.com"], "lista"),
        ({"alias": "contexxto.com"}, "objeto"),
        (b"contexxto.com", "bytes"),
    ],
)
def test_leer_alias_rechaza_un_campo_alias_que_no_es_cadena(promotor, devuelto, motivo):
    """`alias` es REQUERIDO en el 200 documentado: sin él no hay lectura que interpretar."""
    cliente = ClienteDeAlias(promotor, cuerpo_alias(ALIAS_A, alias=devuelto))
    with pytest.raises(promotor.ErrorBarrera) as error:
        promotor.leer_alias(cliente, ALIAS_A)
    assert "alias" in str(error.value), motivo


@pytest.mark.parametrize(
    "otro",
    [ALIAS_B, "contexxto.com.ejemplo.test", "www.contexxto.com", "contexxto.co", ""],
)
def test_leer_alias_rechaza_la_respuesta_de_OTRO_dominio(promotor, otro):
    cliente = ClienteDeAlias(promotor, cuerpo_alias(ALIAS_A, alias=otro))
    with pytest.raises(promotor.ErrorBarrera) as error:
        promotor.leer_alias(cliente, ALIAS_A)
    assert ALIAS_A in str(error.value)
    assert otro.lower() in str(error.value)


@pytest.mark.parametrize("variante", ["CONTEXXTO.COM", "Contexxto.Com", "contexxto.COM"])
def test_leer_alias_acepta_el_mismo_host_en_otras_mayusculas(promotor, variante):
    """DNS no distingue mayúsculas: `CONTEXXTO.COM` ES contexxto.com, no otro host.

    Fallar cerrado aquí sería fallar por una diferencia que no existe. La tolerancia es
    exactamente esa y ninguna más: cualquier otro carácter distinto es otro dominio.

    MEDIDO, para que la tolerancia no se lea como más ancha de lo que es: bajo `.lower()`
    la única letra ASCII alcanzable desde un carácter no ASCII es `k` (U+212A), y ninguno
    de los dos dominios fijados lleva `k`, así que hoy la comparación es exacta para
    ellos. El mecanismo sí es real, y por eso se exige además que el alias devuelto sea
    ASCII: el día que se añada un dominio con `k`, la guarda ya está puesta.
    """
    cliente = ClienteDeAlias(promotor, cuerpo_alias(ALIAS_A, alias=variante))
    estado = promotor.leer_alias(cliente, ALIAS_A)
    assert estado.reconciliado is True


def test_leer_alias_normaliza_tambien_el_host_PEDIDO(promotor):
    """La tolerancia tiene DOS lados y hay que anclar los dos.

    `solicitado = alias.lower()` normaliza lo que se pregunta; `devuelto.lower()`
    normaliza lo que se responde. Las pruebas de arriba solo mueven el lado devuelto,
    porque `ALIAS_A` ya viene en minúsculas: quitar el `.lower()` del lado pedido no las
    rompía. Esta sí.
    """
    cliente = ClienteDeAlias(promotor, cuerpo_alias(ALIAS_A, "dpl_x"))
    estado = promotor.leer_alias(cliente, ALIAS_A.upper())
    assert estado.despliegue == "dpl_x"
    assert estado.reconciliado is True


@pytest.mark.parametrize(
    "devuelto,pedido,pliegue",
    [
        # U+212A KELVIN SIGN se minusculiza a `k`. Es el UNICO caracter no ASCII que
        # bajo `.lower()` alcanza una letra ASCII; esta barrido y medido.
        ("contexxto\u212Ao.test", "contexxtoko.test", "Kelvin -> k"),
        ("\u212A.test", "k.test", "Kelvin al principio"),
        # U+1E9E LATIN CAPITAL LETTER SHARP S se minusculiza a la ss alemana. El pedido
        # tampoco seria ASCII, asi que este caso no representa una configuracion real:
        # esta para fijar que la guarda mira el ALIAS DEVUELTO y no el pedido.
        ("ma\u1E9Ea.test", "ma\u00DFa.test", "sharp S -> eszett"),
    ],
)
def test_leer_alias_rechaza_un_alias_devuelto_que_no_es_ASCII(
    promotor, devuelto, pedido, pliegue
):
    """El plegado Unicode puede hacer pasar por igual a dos hosts DISTINTOS.

    Cada caso es un host devuelto que NO es el pedido y que, sin esta guarda, se volveria
    igual a el al minusculizarlo. Por eso discrimina: quitar el `isascii()` deja pasar la
    lectura en vez de cerrarla.

    MEDIDO barriendo todos los puntos de codigo: bajo `.lower()` la unica letra ASCII
    alcanzable desde un caracter no ASCII es `k`, desde U+212A. Ninguno de los dos
    dominios fijados hoy lleva `k`, asi que esto no arregla un fallo vivo. Cierra la
    CLASE: el dia que se anada un dominio con `k`, la trampa se activaria sin que nadie
    la viera.
    """
    assert devuelto.lower() == pedido, f"el caso no ejerce el pliegue: {pliegue}"
    cliente = ClienteDeAlias(promotor, cuerpo_alias(devuelto, "dpl_x"))
    with pytest.raises(promotor.ErrorBarrera) as error:
        promotor.leer_alias(cliente, pedido)
    assert "ASCII" in str(error.value)


@pytest.mark.parametrize("estado", [201, 202, 204, 301, 302, 400, 401, 403, 404, 500, 503])
def test_leer_alias_exige_un_200_aunque_el_cuerpo_sea_IMPECABLE(promotor, estado):
    """REGRESIÓN QUE INTRODUJO LA LIGADURA, y por eso esta prueba existe.

    Antes de R4, la guarda `estado != 200` la verificaba de rebote una prueba que
    respondía 403 con `{"error": "x"}`: sin la guarda, ese cuerpo no traía `deploymentId`
    ni `projectId`, el alias quedaba sin reconciliar y se fallaba igual. Al añadir la
    ligadura, ese cuerpo pasa a morir ANTES, por el campo `alias` ausente —mismo
    desenlace, guarda distinta—, y la mutación que borra la guarda de estado se volvió
    INERTE. Es el mismo patrón que dejó viva la mutación 49: una guarda nueva aguas abajo
    enmascara a la de aguas arriba, y el arnés lo dice si se reejecuta.

    El cuerpo de aquí es deliberadamente VÁLIDO: pasa la ligadura, pasa las guardas de
    tipo, y lo único que puede rechazarlo es el código de estado.
    """
    cliente = ClienteDeAlias(promotor, cuerpo_alias(ALIAS_A, "dpl_x"), estado=estado)
    with pytest.raises(promotor.ErrorBarrera) as error:
        promotor.leer_alias(cliente, ALIAS_A)
    assert str(estado) in str(error.value)


def test_leer_alias_pregunta_por_el_host_PEDIDO(promotor):
    cliente = ClienteDeAlias(promotor, cuerpo_alias(ALIAS_B))
    promotor.leer_alias(cliente, ALIAS_B)
    assert cliente.rutas == [f"/v4/aliases/{ALIAS_B}"]


def test_leer_alias_ESCAPA_el_host_en_la_ruta(promotor):
    """El nombre de la prueba anterior decia «y escapa la ruta» y no lo comprobaba: los
    dos dominios productivos no llevan ningun caracter que haya que escapar, asi que
    quitar `urllib.parse.quote` no rompia nada. Aqui si.

    El host de este caso NO puede venir de la configuracion —`parsear_alias` rechaza los
    que llevan `/` o espacios—, asi que el escapado es defensa en profundidad y no un
    requisito vivo. Se prueba igual porque una funcion que compone una URL con un dato
    ajeno tiene que escaparlo, venga de donde venga.
    """
    raro = "a/b?c=1&d.test"
    cliente = ClienteDeAlias(promotor, cuerpo_alias(raro))
    promotor.leer_alias(cliente, raro)
    assert cliente.rutas == ["/v4/aliases/a%2Fb%3Fc%3D1%26d.test"]
    assert "/" not in cliente.rutas[0].split("/v4/aliases/")[1]


# ── (A2) la ligadura respuesta ↔ dominio, vista desde fuera ────────────────────


@pytest.mark.parametrize("host_malo", [ALIAS_A, ALIAS_B])
def test_una_respuesta_de_OTRO_dominio_ANTES_del_post_es_fail_closed_sin_post(
    promotor, host_malo
):
    otro = ALIAS_B if host_malo == ALIAS_A else ALIAS_A
    r = ronda("dpl_previo")
    r[host_malo] = (200, cuerpo_alias(otro, "dpl_previo"))
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1")},
        rondas=[r],
        post=(202, None),
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.posts == 0
    assert resultado.detalle == "dominio productivo no legible"
    assert "se preguntó por" in salida


@pytest.mark.parametrize("host_malo", [ALIAS_A, ALIAS_B])
@pytest.mark.parametrize(
    "alias_devuelto,motivo",
    [(_QUITAR, "ausente"), (None, "nulo"), (7, "no cadena")],
)
def test_un_campo_alias_invalido_ANTES_del_post_es_fail_closed_sin_post(
    promotor, host_malo, alias_devuelto, motivo
):
    r = ronda("dpl_previo")
    r[host_malo] = (200, cuerpo_alias(host_malo, "dpl_previo", alias=alias_devuelto))
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1")},
        rondas=[r],
        post=(202, None),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED, motivo
    assert transporte.posts == 0


@pytest.mark.parametrize("host_malo", [ALIAS_A, ALIAS_B])
def test_una_respuesta_de_OTRO_dominio_DESPUES_del_post_es_unknown_con_un_solo_post(
    promotor, host_malo
):
    otro = ALIAS_B if host_malo == ALIAS_A else ALIAS_A
    segunda = ronda("dpl_1")
    segunda[host_malo] = (200, cuerpo_alias(otro, "dpl_1"))
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1")},
        rondas=[ronda("dpl_previo"), segunda],
        post=(202, None),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.UNKNOWN_RECONCILIATION_REQUIRED
    assert resultado.estado != promotor.PROMOTED
    assert transporte.posts == 1, "el POST ya se emitió: no se emite otro"


@pytest.mark.parametrize("host_malo", [ALIAS_A, ALIAS_B])
@pytest.mark.parametrize(
    "alias_devuelto,motivo",
    [(_QUITAR, "ausente"), (None, "nulo"), (7, "no cadena")],
)
def test_un_campo_alias_invalido_DESPUES_del_post_es_unknown_con_un_solo_post(
    promotor, host_malo, alias_devuelto, motivo
):
    segunda = ronda("dpl_1")
    segunda[host_malo] = (200, cuerpo_alias(host_malo, "dpl_1", alias=alias_devuelto))
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1")},
        rondas=[ronda("dpl_previo"), segunda],
        post=(202, None),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.UNKNOWN_RECONCILIATION_REQUIRED, motivo
    assert transporte.posts == 1


def test_los_dos_dominios_devolviendo_el_MISMO_host_no_es_convergencia(promotor):
    """EL fail-open que cierra la ligadura, reproducido.

    Los dos dominios responden con el registro de `ALIAS_A`, ya apuntando al artefacto
    aprobado. Sin ligar la respuesta a la pregunta, `clasificar_convergencia` vería dos
    estados idénticos y buenos, diría TODOS, y el programa declararía `PROMOTED`
    habiendo acreditado UN solo dominio. La convergencia de dos se cumpliría con la
    evidencia de uno, que es justo lo que R2 existe para impedir.
    """
    falsa = {
        ALIAS_A: (200, cuerpo_alias(ALIAS_A, "dpl_1")),
        ALIAS_B: (200, cuerpo_alias(ALIAS_A, "dpl_1")),
    }
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1")},
        rondas=[ronda("dpl_previo"), falsa],
        post=(202, None),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.UNKNOWN_RECONCILIATION_REQUIRED
    assert resultado.estado != promotor.PROMOTED
    assert transporte.posts == 1


@pytest.mark.parametrize("host_malo", [ALIAS_A, ALIAS_B])
def test_cualquier_dominio_ilegible_es_fail_closed(promotor, host_malo):
    r = ronda("dpl_previo")
    r[host_malo] = (403, {"error": "x"})
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1")},
        rondas=[r],
        post=(202, None),
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.posts == 0
    assert "no se pudo leer algún dominio productivo" in salida
    assert resultado.detalle == "dominio productivo no legible"


def test_se_consultan_LOS_DOS_dominios_y_ninguno_mas(promotor):
    transporte = guion_nominal(promotor)
    correr(promotor, transporte)
    hosts = set()
    for _m, u, _q in transporte.llamadas:
        if "/v4/aliases/" in u:
            hosts.add(urllib.parse.unquote(urllib.parse.urlsplit(u).path.split("/v4/aliases/")[1]))
    assert hosts == {ALIAS_A, ALIAS_B}
    for _m, u, _q in transporte.llamadas:
        assert "/v2/deployments/" not in u, "la vía secundaria no es canónica"


# ── (B) la lista de dominios · configuración ───────────────────────────────────


def test_el_conjunto_de_dominios_esta_fijado_en_git(promotor):
    """La autoridad es el repositorio, no la consola.

    Una variable del Environment se cambia sin revisión y sin dejar rastro; el conjunto
    fijado en el fuente solo cambia con un commit, que pasa por el CI y por el PR.
    """
    assert promotor.DOMINIOS_PRODUCTIVOS == (ALIAS_A, ALIAS_B)
    fuente = _RUTA.read_text(encoding="utf-8")
    assert ALIAS_A in fuente and ALIAS_B in fuente


@pytest.mark.parametrize(
    "valor,motivo",
    [
        (ALIAS_A, "falta el segundo dominio"),
        (ALIAS_B, "falta el primero"),
        (f"{ALIAS_A},", "uno solo con coma sobrante"),
        (f"{ALIAS_A},{ALIAS_A}", "el mismo repetido: sigue siendo uno"),
        (" , ", "solo separadores"),
        (f"{ALIAS_A},{ALIAS_B},otro.example.com", "un dominio DE MÁS"),
        (f"{ALIAS_A},preview.example.com", "un dominio ajeno en vez del segundo"),
        ("otro.example.com,tercero.example.com", "dos dominios, pero los equivocados"),
        (f"{ALIAS_A},{ALIAS_B.replace('six','seven')}", "un dominio casi igual"),
    ],
)
def test_solo_el_conjunto_EXACTO_se_acepta(promotor, valor, motivo):
    """Exigir «al menos dos» no bastaba: dos dominios cualesquiera pasaban el filtro."""
    transporte = Transporte(promotor)
    resultado, salida = correr(promotor, transporte, entorno(VERCEL_PROMOTION_ALIAS=valor))
    assert resultado.estado == promotor.FAIL_CLOSED, motivo
    assert transporte.llamadas == [], "no se llama a nada con la lista mal formada"
    assert "no coincide con la fijada en git" in salida or "requeridas" in salida


def test_el_mensaje_dice_QUE_sobra_y_QUE_falta(promotor):
    transporte = Transporte(promotor)
    _, salida = correr(
        promotor, transporte, entorno(VERCEL_PROMOTION_ALIAS=f"{ALIAS_A},ajeno.example.com")
    )
    assert "sobran" in salida and "ajeno.example.com" in salida
    assert "faltan" in salida and ALIAS_B in salida


def test_la_lista_se_normaliza_deduplica_y_no_depende_del_orden(promotor):
    # mayúsculas, espacios, duplicados y orden invertido: todo da el conjunto fijado,
    # y SIEMPRE en el orden de git, para que la variable no pueda alterar la conducta.
    for variante in (
        f"  {ALIAS_A.upper()} , {ALIAS_B} ,{ALIAS_A} ",
        f"{ALIAS_B},{ALIAS_A}",
        f"{ALIAS_B.upper()} , {ALIAS_A}",
    ):
        assert promotor.parsear_alias(variante) == (ALIAS_A, ALIAS_B), variante


def test_el_orden_configurado_no_cambia_el_resultado(promotor):
    transporte = guion_nominal(promotor)
    resultado, _ = correr(
        promotor, transporte, entorno(VERCEL_PROMOTION_ALIAS=f"{ALIAS_B},{ALIAS_A}")
    )
    assert resultado.estado == promotor.PROMOTED


def test_demasiados_dominios_es_fail_closed(promotor):
    muchos = ",".join(f"d{i}.example.com" for i in range(promotor.ALIAS_MAXIMOS + 1))
    with pytest.raises(promotor.ErrorBarrera):
        promotor.parsear_alias(muchos)


def test_la_carga_por_ruta_retira_el_registro_si_no_existia():
    """El registro del módulo es estado global: no debe sobrevivir al fichero.

    Prueba DIRECTA de `cargar_por_ruta`, que es lo que usa la fixture. Una versión
    anterior de esta prueba reimplementaba el mecanismo en vez de ejercitarlo, así que
    romper la fixture no la hacía fallar: la mutación nacía inerte.
    """
    nombre = "promover_produccion_prueba_de_restauracion"
    assert nombre not in sys.modules
    with cargar_por_ruta(nombre, _RUTA) as modulo:
        assert sys.modules[nombre] is modulo, "durante la carga sí debe estar registrado"
    assert nombre not in sys.modules, "al salir, el registro debe retirarse"


def test_la_carga_por_ruta_devuelve_el_valor_previo_si_lo_habia():
    nombre = "promover_produccion_prueba_con_previo"
    centinela = object()
    sys.modules[nombre] = centinela
    try:
        with cargar_por_ruta(nombre, _RUTA):
            assert sys.modules[nombre] is not centinela
        assert sys.modules[nombre] is centinela, "debe restaurarse el valor anterior"
    finally:
        sys.modules.pop(nombre, None)


def test_la_carga_por_ruta_restaura_aunque_el_modulo_reviente(tmp_path):
    """El `finally` tiene que actuar también cuando la ejecución falla."""
    roto = tmp_path / "modulo_roto.py"
    roto.write_text("raise RuntimeError('a proposito')\n", encoding="utf-8")
    nombre = "promover_produccion_prueba_rota"
    assert nombre not in sys.modules
    with pytest.raises(RuntimeError):
        with cargar_por_ruta(nombre, roto):
            pass
    assert nombre not in sys.modules, "un fallo no puede dejar el registro puesto"


def test_la_fixture_usa_la_carga_por_ruta():
    """Ata la fixture con la función probada.

    Sin este aserto, la fixture podría reimplementar la carga por su cuenta y las
    pruebas de `cargar_por_ruta` dejarían de decir nada sobre lo que de verdad se usa.
    """
    fuente = pathlib.Path(__file__).read_text(encoding="utf-8")
    bloque = fuente.split("def promotor():", 1)[1].split("\n\n\n", 1)[0]
    assert "cargar_por_ruta" in bloque, "la fixture dejó de usar la carga probada"
    assert "sys.modules" not in bloque, "la fixture no debe manipular sys.modules por su cuenta"


def test_la_clasificacion_de_convergencia_cubre_los_cinco_casos(promotor):
    E = promotor.EstadoAlias
    bueno = {ALIAS_A: E("dpl_1", PROYECTO), ALIAS_B: E("dpl_1", PROYECTO)}
    parcial = {ALIAS_A: E("dpl_1", PROYECTO), ALIAS_B: E("dpl_previo", PROYECTO)}
    ninguno = {ALIAS_A: E("dpl_previo", PROYECTO), ALIAS_B: E("dpl_previo", PROYECTO)}
    diverg = {ALIAS_A: E("dpl_previo", PROYECTO), ALIAS_B: E("dpl_otro", PROYECTO)}
    nulo = {ALIAS_A: E(None, PROYECTO), ALIAS_B: E("dpl_1", PROYECTO)}
    ajeno = {ALIAS_A: E("dpl_1", "prj_x"), ALIAS_B: E("dpl_1", PROYECTO)}
    c = promotor.clasificar_convergencia
    assert c(bueno, "dpl_1", PROYECTO) == promotor.TODOS
    assert c(parcial, "dpl_1", PROYECTO) == promotor.PARCIAL
    assert c(ninguno, "dpl_1", PROYECTO) == promotor.NINGUNO
    assert c(diverg, "dpl_1", PROYECTO) == promotor.DIVERGENTE
    assert c(nulo, "dpl_1", PROYECTO) == promotor.NO_RECONCILIADO
    assert c(ajeno, "dpl_1", PROYECTO) == promotor.NO_RECONCILIADO
    assert c({}, "dpl_1", PROYECTO) == promotor.NO_RECONCILIADO


# ── (C) el token de proyecto · sin equipo ──────────────────────────────────────


def test_no_se_exige_ni_se_envia_identificador_de_equipo(promotor):
    assert "VERCEL_PROMOTION_TEAM_ID" not in promotor.VARIABLES_REQUERIDAS
    fuente = _RUTA.read_text(encoding="utf-8")
    assert "teamId" not in fuente, "el token es de proyecto: no se envía teamId"
    assert "VERCEL_PROMOTION_TEAM_ID" not in fuente
    # y el doble lo vigila en cada llamada
    transporte = guion_nominal(promotor)
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.PROMOTED


def test_definir_un_team_id_en_el_entorno_no_cambia_nada(promotor):
    transporte = guion_nominal(promotor)
    resultado, _ = correr(promotor, transporte, entorno(VERCEL_PROMOTION_TEAM_ID="team_x"))
    assert resultado.estado == promotor.PROMOTED
    for _m, _u, q in transporte.llamadas:
        assert "teamId" not in q


def test_las_variables_requeridas_son_exactamente_tres(promotor):
    assert promotor.VARIABLES_REQUERIDAS == (
        "VERCEL_PROJECT_PROMOTION_TOKEN",
        "VERCEL_PROMOTION_PROJECT_ID",
        "VERCEL_PROMOTION_ALIAS",
    )


# ── (D) barreras de contexto ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "cambio",
    [
        {"GITHUB_EVENT_NAME": "workflow_dispatch"},
        {"GITHUB_EVENT_NAME": "pull_request"},
        {"GITHUB_EVENT_NAME": "schedule"},
        {"GITHUB_REF": "refs/heads/otra"},
        {"GITHUB_REF": "refs/tags/v1"},
        {"GITHUB_RUN_ATTEMPT": "2"},
        {"GITHUB_RUN_ATTEMPT": "10"},
        {"GITHUB_RUN_ATTEMPT": "uno"},
        {"GITHUB_REPOSITORY": "sin-barra"},
        {"GITHUB_REPOSITORY": "/vacio"},
        {"GITHUB_REPOSITORY": ""},
    ],
)
def test_la_barrera_del_programa_rechaza_aunque_el_yaml_fallara(promotor, cambio):
    transporte = Transporte(promotor)
    resultado, _ = correr(promotor, transporte, entorno(**cambio))
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.posts == 0
    assert transporte.llamadas == []


@pytest.mark.parametrize(
    "sha", ["", "a" * 39, "a" * 41, "A" * 40, "g" * 40, "abc", " " + "a" * 39]
)
def test_sha_ausente_o_malformado(promotor, sha):
    transporte = Transporte(promotor)
    resultado, _ = correr(promotor, transporte, entorno(GITHUB_SHA=sha))
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.posts == 0


# ── (E) el detalle del candidato ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "cambios,motivo",
    [
        ({"gitSource": None}, "sin gitSource"),
        ({"gitSource": _QUITAR}, "gitSource ausente"),
        ({"origen": {"type": "github", "repoId": 1}}, "sin sha"),
        ({"origen": {"type": "github", "repoId": 1, "sha": "a" * 12}}, "abreviado"),
        ({"origen": {"type": "github", "repoId": 1, "sha": "z" * 40}}, "no hex"),
        ({"origen": {"type": "github", "repoId": 1, "sha": 12345}}, "sha no es cadena"),
        ({"origen": {"type": "github", "repoId": 1, "sha": SHA_OTRO}}, "otro sha"),
        ({"readySubstate": "PROMOTED"}, "ya vio tráfico"),
        ({"readySubstate": "ROLLING"}, "en transición"),
        ({"readySubstate": None}, "substate nulo"),
        ({"readySubstate": _QUITAR}, "substate ausente"),
        ({"target": "staging"}, "target equivocado"),
        ({"target": None}, "target nulo"),
        ({"target": _QUITAR}, "target ausente"),
        ({"readyState": "BUILDING"}, "build sin terminar"),
        ({"readyState": "ERROR"}, "build fallido"),
        ({"readyState": _QUITAR}, "readyState ausente"),
        ({"projectId": "prj_otro"}, "otro proyecto"),
        ({"projectId": _QUITAR}, "projectId ausente"),
    ],
)
def test_el_detalle_que_no_prueba_identidad_descarta(promotor, cambios, motivo):
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1", **cambios)},
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.UNAVAILABLE, motivo
    assert transporte.posts == 0


@pytest.mark.parametrize(
    "origen,motivo",
    [
        ({"type": "gitlab", "projectId": "1", "sha": SHA_BUENO}, "otro proveedor"),
        ({"type": "bitbucket", "repoUuid": "1", "sha": SHA_BUENO}, "otro proveedor"),
        ({"type": "custom", "gitUrl": "x", "ref": "y", "sha": SHA_BUENO}, "custom"),
        ({"type": "vercel", "sha": SHA_BUENO}, "origen vercel"),
        ({"repoId": 1, "sha": SHA_BUENO}, "sin type"),
        ({"type": "github", "org": "otra-org", "repo": "contexto-ai", "sha": SHA_BUENO}, "otra org"),
        ({"type": "github", "org": "contexxto", "repo": "otro-repo", "sha": SHA_BUENO}, "otro repo"),
    ],
)
def test_el_origen_del_artefacto_debe_ser_el_repositorio_que_aprobo(promotor, origen, motivo):
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1", origen=origen)},
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.UNAVAILABLE, motivo
    assert transporte.posts == 0


def test_el_origen_por_repoId_sin_nombres_se_acepta_con_projectId(promotor):
    transporte = guion_nominal(
        promotor,
        detalles={"dpl_1": detalle("dpl_1", origen={"type": "github", "repoId": 7, "sha": SHA_BUENO})},
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.PROMOTED


def test_el_detalle_debe_responder_por_el_identificador_que_se_pidio(promotor):
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_OTRO")},
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.UNAVAILABLE
    assert transporte.posts == 0


def test_el_detalle_se_pide_con_withGitRepoInfo(promotor):
    transporte = guion_nominal(promotor)
    correr(promotor, transporte)
    consultas = transporte.consultas_de("/v13/deployments/")
    assert consultas
    for consulta in consultas:
        assert consulta.get("withGitRepoInfo") == "true", consulta


@pytest.mark.parametrize("codigo", [400, 401, 403, 404, 410, 429, 500])
def test_detalle_no_ok_es_fail_closed(promotor, codigo):
    # Cuerpo VÁLIDO a propósito: con None la guarda de cuerpo taparía a la de estado.
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": (codigo, detalle("dpl_1"))},
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert f"detalle de despliegue devolvió {codigo}" in salida
    assert transporte.posts == 0


def test_detalle_con_cuerpo_que_no_es_objeto_es_fail_closed(promotor):
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": (200, ["no", "es", "objeto"])},
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.posts == 0


# ── (F) selección y ambigüedad ─────────────────────────────────────────────────


def test_cero_candidatos_es_indisponibilidad_sin_post(promotor):
    transporte = Transporte(promotor, paginas=[([], None)])
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.UNAVAILABLE
    assert transporte.posts == 0
    assert resultado.codigo != 0


def test_dos_candidatos_validos_es_fail_closed(promotor):
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1"), item_listado("dpl_2")], None)],
        detalles={"dpl_1": detalle("dpl_1"), "dpl_2": detalle("dpl_2")},
        rondas=[ronda("dpl_previo")],
        post=(202, None),
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert "ambigüedad" in salida
    assert transporte.posts == 0


def test_el_segundo_candidato_sin_readySubstate_en_el_listado_sigue_contando(promotor):
    """FAIL-OPEN corregido: `readySubstate` NO es requerido en el item del listado."""
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1"), item_listado("dpl_2", readySubstate=_QUITAR)], None)],
        detalles={"dpl_1": detalle("dpl_1"), "dpl_2": detalle("dpl_2")},
        rondas=[ronda("dpl_previo")],
        post=(202, None),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.posts == 0


def test_el_prefiltro_si_excluye_lo_que_demuestra_no_ser_staged(promotor):
    transporte = guion_nominal(
        promotor,
        paginas=[([item_listado("dpl_1"), item_listado("dpl_viejo", readySubstate="PROMOTED")], None)],
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.PROMOTED
    pedidos = [u for _m, u, _q in transporte.llamadas if "/v13/deployments/" in u]
    assert not any("dpl_viejo" in u for u in pedidos)
    assert any("dpl_1" in u for u in pedidos)


def test_elemento_del_listado_sin_uid_es_fail_closed(promotor):
    sin_uid = item_listado("dpl_2")
    del sin_uid["uid"]
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1"), sin_uid], None)],
        detalles={"dpl_1": detalle("dpl_1")},
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert "sin `uid`" in salida
    assert transporte.posts == 0


def test_un_solo_candidato_valido_continua(promotor):
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1"), item_listado("dpl_2")], None)],
        detalles={"dpl_1": detalle("dpl_1"), "dpl_2": detalle("dpl_2", sha=SHA_OTRO)},
        rondas=[ronda("dpl_previo"), ronda("dpl_1")],
        post=(202, None),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.PROMOTED
    assert resultado.detalle == "dpl_1"
    assert transporte.posts == 1


# ── (G) paginación y listado ───────────────────────────────────────────────────


def test_la_paginacion_usa_el_cursor_y_encuentra_al_de_la_ultima_pagina(promotor):
    transporte = Transporte(
        promotor,
        paginas=[
            ([item_listado("dpl_viejo", readySubstate="PROMOTED")], 1000),
            ([item_listado("dpl_1")], None),
        ],
        detalles={"dpl_1": detalle("dpl_1")},
        rondas=[ronda("dpl_previo"), ronda("dpl_1")],
        post=(202, None),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.PROMOTED
    consultas = transporte.consultas_de("/v7/deployments")
    assert len(consultas) == 2
    assert "until" not in consultas[0]
    assert consultas[1].get("until") == "1000"


def test_el_listado_se_acota_por_proyecto_destino_y_estado(promotor):
    transporte = guion_nominal(promotor)
    correr(promotor, transporte)
    consulta = transporte.consultas_de("/v7/deployments")[0]
    assert consulta.get("projectId") == PROYECTO
    assert consulta.get("target") == "production"
    assert consulta.get("state") == "READY"
    assert "sha" not in consulta


def test_paginacion_no_resoluble_es_fail_closed(promotor):
    transporte = Transporte(promotor, paginas=[([], i + 1) for i in range(40)])
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert "paginación no resuelta" in salida
    assert transporte.posts == 0


@pytest.mark.parametrize(
    "cuerpo,motivo",
    [
        ((200, {"pagination": {"next": None}}), "sin deployments"),
        ((200, {"deployments": None, "pagination": {"next": None}}), "nulo"),
        ((200, {"deployments": {}, "pagination": {"next": None}}), "no es lista"),
        ((200, {"deployments": ["cadena"], "pagination": {"next": None}}), "elemento suelto"),
        ((200, {"deployments": []}), "sin paginación"),
        ((200, {"deployments": [], "pagination": {}}), "paginación sin next"),
        ((200, {"deployments": [], "pagination": None}), "paginación nula"),
        ((200, ["no", "es", "objeto"]), "cuerpo no es objeto"),
        ((200, None), "cuerpo vacío"),
    ],
)
def test_listado_malformado_es_fail_closed(promotor, cuerpo, motivo):
    transporte = Transporte(promotor, listado=cuerpo)
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED, motivo
    assert transporte.posts == 0


@pytest.mark.parametrize("codigo", [401, 403, 429, 500])
def test_listado_no_ok_es_fail_closed(promotor, codigo):
    transporte = Transporte(promotor, listado=(codigo, {"deployments": [], "pagination": {"next": None}}))
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert f"listado devolvió {codigo}" in salida
    assert transporte.posts == 0


def test_listado_sin_respuesta_concluyente_es_fail_closed(promotor):
    transporte = Transporte(promotor, listado=promotor.ErrorTransporte("caido"))
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert "listado sin respuesta concluyente" in salida
    assert salida.count("reintento acotado") == promotor.REINTENTOS_GET
    assert transporte.posts == 0


def test_demasiados_preseleccionados_es_fail_closed(promotor):
    muchos = [item_listado(f"dpl_{i}") for i in range(promotor.DETALLES_MAXIMOS + 1)]
    transporte = Transporte(promotor, paginas=[(muchos, None)])
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert "supera el tope" in salida
    assert transporte.consultas_de("/v13/deployments/") == []


# ── (H) el POST ────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("codigo", [201, 202])
def test_promocion_nominal_exactamente_un_post(promotor, codigo):
    transporte = guion_nominal(promotor, post=(codigo, None))
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.PROMOTED
    assert transporte.posts == 1
    assert resultado.codigo == 0


def test_el_post_va_al_endpoint_exacto_adjudicado(promotor):
    transporte = guion_nominal(promotor)
    correr(promotor, transporte)
    posts = [u for m, u, _q in transporte.llamadas if m == "POST"]
    assert len(posts) == 1
    assert f"/v10/projects/{PROYECTO}/promote/dpl_1" in posts[0]
    assert "latest" not in posts[0]
    assert "redeploy" not in posts[0].lower()


@pytest.mark.parametrize("codigo", [400, 401, 403, 409, 410, 422])
def test_codigos_de_rechazo_documentados_son_fail_closed(promotor, codigo):
    transporte = guion_nominal(promotor, post=(codigo, {"error": "x"}))
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.posts == 1
    assert "rechazada por el servidor" in salida
    # un rechazo documentado no necesita reconciliación: una lectura por dominio
    assert transporte.lecturas_de(ALIAS_A) == 1
    assert transporte.lecturas_de(ALIAS_B) == 1


@pytest.mark.parametrize("codigo", [200, 204, 429, 500, 502, 504])
def test_codigo_no_documentado_tras_el_post_se_reconcilia(promotor, codigo):
    transporte = guion_nominal(promotor, post=(codigo, None))
    resultado, salida = correr(promotor, transporte)
    assert "no documentado" in salida
    assert resultado.estado == promotor.PROMOTED
    assert transporte.posts == 1


def test_codigo_no_documentado_sin_convergencia_es_unknown(promotor):
    transporte = guion_nominal(promotor, rondas=[ronda("dpl_previo")], post=(503, None))
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.UNKNOWN_RECONCILIATION_REQUIRED
    assert transporte.posts == 1


def test_perdida_de_transporte_reconciliada_es_promocion(promotor):
    transporte = guion_nominal(promotor, post=None)
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.PROMOTED
    assert transporte.posts == 1, "jamás un segundo POST"


def test_perdida_sin_resolucion_es_unknown_sin_reintento(promotor):
    transporte = guion_nominal(promotor, rondas=[ronda("dpl_previo")], post=None)
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.UNKNOWN_RECONCILIATION_REQUIRED
    assert resultado.codigo != 0
    assert transporte.posts == 1
    assert "UNKNOWN / NO RETRY / REQUIERE RECONCILIACIÓN" in salida


def test_unknown_nunca_se_convierte_en_exito_por_ausencia_de_evidencia(promotor):
    transporte = guion_nominal(
        promotor, rondas=[ronda("dpl_previo"), {ALIAS_A: None, ALIAS_B: None}], post=None
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.UNKNOWN_RECONCILIATION_REQUIRED
    assert resultado.codigo != 0


# ── (I) el sondeo es finito ────────────────────────────────────────────────────


def test_el_sondeo_termina_por_numero_de_intentos(promotor):
    transporte = guion_nominal(promotor, rondas=[ronda("dpl_previo")], post=(202, None))
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.UNKNOWN_RECONCILIATION_REQUIRED
    sondeos = transporte.lecturas_de(ALIAS_A) - 1  # la primera es la lectura previa
    # Tope escrito AQUÍ como número literal: compararlo contra la constante del producto
    # sería tautológico.
    assert 1 <= sondeos <= 10, f"sondeó {sondeos} veces"
    assert transporte.lecturas_de(ALIAS_B) == transporte.lecturas_de(ALIAS_A)


def test_el_sondeo_termina_por_ventana_de_tiempo(promotor):
    transporte = guion_nominal(promotor, rondas=[ronda("dpl_previo")], post=(202, None))
    resultado, salida = correr(
        promotor, transporte, reloj=[0.0, 1.0, 10_000.0, 10_001.0, 10_002.0]
    )
    assert resultado.estado == promotor.UNKNOWN_RECONCILIATION_REQUIRED
    assert "ventana de sondeo agotada por tiempo" in salida
    assert transporte.lecturas_de(ALIAS_A) - 1 <= 3


def test_los_limites_son_finitos_y_estan_en_el_codigo(promotor):
    TECHOS = {
        "REINTENTOS_GET": 5,
        "PAGINAS_MAXIMAS": 50,
        "DETALLES_MAXIMOS": 200,
        "SONDEOS_MAXIMOS": 10,
        "VENTANA_MAXIMA_DE_SONDEO": 300,
        "TIMEOUT_GET": 60,
        "TIMEOUT_POST": 60,
        "ESPERA_ENTRE_SONDEOS": 30,
        "ESPERA_ENTRE_REINTENTOS": 30,
        "ALIAS_MAXIMOS": 20,
    }
    for nombre, techo in TECHOS.items():
        valor = getattr(promotor, nombre)
        assert isinstance(valor, (int, float)) and valor > 0, nombre
        assert valor <= techo, f"{nombre} = {valor} pasa del techo duro {techo}"
    # el conjunto fijado en git tiene los dos dominios de producción, sin duplicados
    assert len(promotor.DOMINIOS_PRODUCTIVOS) == 2
    assert len(set(promotor.DOMINIOS_PRODUCTIVOS)) == 2


def test_los_reintentos_de_get_estan_acotados(promotor):
    class GetSiempreCaido(Transporte):
        def __call__(self, metodo, url, cabeceras, timeout):
            self.llamadas.append((metodo, url, {}))
            raise self.p.ErrorTransporte("caido")

    transporte = GetSiempreCaido(promotor)
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert len(transporte.llamadas) <= 6


# ── (J) entradas requeridas y secretos ─────────────────────────────────────────


@pytest.mark.parametrize(
    "variable",
    ["VERCEL_PROJECT_PROMOTION_TOKEN", "VERCEL_PROMOTION_PROJECT_ID", "VERCEL_PROMOTION_ALIAS"],
)
def test_entrada_requerida_ausente_falla_cerrado(promotor, variable):
    transporte = Transporte(promotor)
    resultado, salida = correr(promotor, transporte, entorno(**{variable: None}))
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.llamadas == []
    assert variable in salida


def test_entrada_vacia_cuenta_como_ausente(promotor):
    transporte = Transporte(promotor)
    resultado, _ = correr(promotor, transporte, entorno(VERCEL_PROJECT_PROMOTION_TOKEN=""))
    assert resultado.estado == promotor.FAIL_CLOSED


def test_el_token_no_aparece_en_ningun_camino(promotor):
    guiones = [
        dict(),
        dict(paginas=[([], None)], detalles={}),
        dict(post=(403, {"error": "denied"})),
        dict(rondas=[ronda("dpl_previo")], post=None),
        dict(detalles={"dpl_1": detalle("dpl_1", sha=SHA_OTRO)}),
        dict(rondas=[{ALIAS_A: ("dpl_previo", PROYECTO), ALIAS_B: ("dpl_otro", PROYECTO)}]),
    ]
    for guion in guiones:
        transporte = guion_nominal(promotor, **guion)
        _, salida = correr(promotor, transporte)
        assert TOKEN not in salida
        assert "Bearer" not in salida


def test_la_redaccion_sustituye_el_secreto(promotor):
    texto = promotor.redactar(f"cabecera Bearer {TOKEN} final", [TOKEN])
    assert TOKEN not in texto
    assert "***REDACTADO***" in texto


def test_la_redaccion_no_tiene_suelo_de_longitud(promotor):
    assert "abc" not in promotor.redactar("valor abc aqui", ["abc"])
    assert "x" not in promotor.redactar("valor x aqui", ["x"])


def test_el_registro_redacta_aunque_le_pasen_el_token(promotor):
    salida = io.StringIO()
    registro = promotor.Registro(secretos=[TOKEN], salida=salida)
    registro(f"esto lleva el token {TOKEN} dentro")
    assert TOKEN not in salida.getvalue()
    assert TOKEN not in "".join(registro.lineas)


def test_el_repr_del_cliente_no_lleva_el_token(promotor):
    cliente = promotor.ClienteVercel(
        token=TOKEN, registro=promotor.Registro(salida=io.StringIO())
    )
    assert TOKEN not in repr(cliente)


def test_el_transporte_real_no_filtra_la_url_en_sus_errores(promotor, monkeypatch):
    URL = f"https://api.vercel.com/v7/deployments?projectId={PROYECTO}"

    class OpenerQueFalla:
        def open(self, peticion, timeout=None):
            raise OSError(f"conexión rechazada contra {URL}")

    monkeypatch.setattr(promotor, "_OPENER", OpenerQueFalla())
    with pytest.raises(promotor.ErrorTransporte) as capturado:
        promotor.transporte_urllib("GET", URL, {"Authorization": f"Bearer {TOKEN}"}, 1.0)
    mensaje = str(capturado.value)
    assert mensaje == "OSError"
    assert "api.vercel.com" not in mensaje
    assert TOKEN not in mensaje
    assert capturado.value.__cause__ is None


def test_el_transporte_real_no_exige_json_en_las_respuestas_sin_cuerpo(promotor, monkeypatch):
    class Respuesta202:
        status = 202

        def read(self):
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    class OpenerOK:
        def open(self, peticion, timeout=None):
            return Respuesta202()

    monkeypatch.setattr(promotor, "_OPENER", OpenerOK())
    respuesta = promotor.transporte_urllib("POST", "https://api.vercel.com/x", {}, 1.0)
    assert respuesta.estado == 202
    assert respuesta.cuerpo is None


def test_el_transporte_no_sigue_redirecciones(promotor):
    manejadores = [type(h).__name__ for h in promotor._OPENER.handlers]
    assert "_SinRedirecciones" in manejadores
    assert "HTTPRedirectHandler" not in manejadores
    manejador = promotor._SinRedirecciones()
    assert manejador.redirect_request(None, None, 302, "", {}, "https://otro.example/x") is None


# ── (K) un solo POST ───────────────────────────────────────────────────────────


def test_el_cliente_impide_estructuralmente_un_segundo_post(promotor):
    llamadas = []

    def transporte(metodo, url, cabeceras, timeout):
        llamadas.append(metodo)
        return promotor.Respuesta(202, None)

    cliente = promotor.ClienteVercel(
        token=TOKEN, registro=promotor.Registro(salida=io.StringIO()), transporte=transporte
    )
    cliente.post_promocion(PROYECTO, "dpl_1")
    with pytest.raises(promotor.ErrorBarrera):
        cliente.post_promocion(PROYECTO, "dpl_1")
    assert llamadas.count("POST") == 1


def test_ningun_guion_produce_mas_de_un_post(promotor):
    guiones = [
        dict(),
        dict(post=None),
        dict(post=(500, None)),
        dict(post=(403, None)),
        dict(rondas=[ronda("dpl_previo")], post=(202, None)),
        dict(paginas=[([], None)], detalles={}),
        dict(rondas=[{ALIAS_A: ("dpl_1", PROYECTO), ALIAS_B: ("dpl_previo", PROYECTO)}]),
    ]
    for guion in guiones:
        transporte = guion_nominal(promotor, **guion)
        correr(promotor, transporte)
        assert transporte.posts <= 1


def test_solo_hay_una_llamada_a_post_promocion_en_el_fuente():
    fuente = _RUTA.read_text(encoding="utf-8")
    assert fuente.count("post_promocion(") == 2


# ── (L) relación estructural con el YAML ───────────────────────────────────────


def test_el_yaml_invoca_el_programa_que_existe_y_le_pasa_lo_que_pide(promotor):
    raiz = pathlib.Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load(
        (raiz / ".github" / "workflows" / "pruebas.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["promocion-produccion"]
    pasos_con_run = [p for p in job["steps"] if "run" in p]
    assert pasos_con_run
    paso = pasos_con_run[-1]

    invocado = paso["run"].split()[-1]
    assert (raiz / invocado).is_file()
    assert (raiz / invocado).resolve() == _RUTA.resolve()

    puestas = set(paso.get("env", {}))
    for requerida in promotor.VARIABLES_REQUERIDAS:
        assert requerida in puestas, f"el programa exige {requerida} y el job no la pasa"
    assert "secrets.VERCEL_PROJECT_PROMOTION_TOKEN" in paso["env"]["VERCEL_PROJECT_PROMOTION_TOKEN"]
    for identificador in ("VERCEL_PROMOTION_PROJECT_ID", "VERCEL_PROMOTION_ALIAS"):
        assert "vars." in paso["env"][identificador]


def test_el_yaml_ya_no_pasa_identificador_de_equipo(promotor):
    raiz = pathlib.Path(__file__).resolve().parents[1]
    crudo = (raiz / ".github" / "workflows" / "pruebas.yml").read_text(encoding="utf-8")
    assert "VERCEL_PROMOTION_TEAM_ID" not in crudo


def test_el_secreto_solo_se_expone_al_paso_que_lo_usa(promotor):
    raiz = pathlib.Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load(
        (raiz / ".github" / "workflows" / "pruebas.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["promocion-produccion"]
    assert "env" not in job
    pasos = [p for p in job["steps"] if "VERCEL_PROJECT_PROMOTION_TOKEN" in (p.get("env") or {})]
    assert len(pasos) == 1
    assert "promover_produccion.py" in pasos[0]["run"]


# ── (M) estados de salida ──────────────────────────────────────────────────────


def test_los_estados_de_salida_son_inequivocos(promotor):
    estados = {
        promotor.PROMOTED,
        promotor.ALREADY_CURRENT_UNATTESTED,
        promotor.UNAVAILABLE,
        promotor.FAIL_CLOSED,
        promotor.UNKNOWN_RECONCILIATION_REQUIRED,
    }
    assert len(estados) == 5
    assert set(promotor.CODIGOS_DE_SALIDA) == estados
    assert len(set(promotor.CODIGOS_DE_SALIDA.values())) == 5


def test_solo_la_promocion_atestiguada_es_verde(promotor):
    verdes = [e for e, c in promotor.CODIGOS_DE_SALIDA.items() if c == 0]
    assert verdes == [promotor.PROMOTED]
    assert promotor.CODIGOS_DE_SALIDA[promotor.ALREADY_CURRENT_UNATTESTED] != 0
    assert promotor.ALREADY_CURRENT_UNATTESTED.endswith("UNATTESTED")
    assert not hasattr(promotor, "ALREADY_CURRENT")


def test_los_codigos_de_exito_y_rechazo_son_los_del_contrato(promotor):
    assert promotor.CODIGOS_DE_EXITO_DE_PROMOCION == frozenset({201, 202})
    assert promotor.CODIGOS_DE_RECHAZO_DOCUMENTADOS == frozenset({400, 401, 403, 409, 410, 422})
    assert not (
        promotor.CODIGOS_DE_EXITO_DE_PROMOCION & promotor.CODIGOS_DE_RECHAZO_DOCUMENTADOS
    )


# ── (O) `main()`, el punto de entrada de verdad ───────────────────────────────
# Todo lo demas prueba `ejecutar()`. Lo que corre en el runner es `main()`, y lo que el
# job lee para decidir si la promocion salio bien es su CODIGO DE SALIDA. Hasta ahora
# ninguna prueba lo invocaba: la traduccion de estado a codigo, la red de seguridad del
# secreto y el `ESTADO=` que se imprime estaban sin cubrir.

ESTADOS_Y_CODIGOS = [
    ("PROMOTED", 0),
    ("UNAVAILABLE", 1),
    ("FAIL_CLOSED", 2),
    ("UNKNOWN_RECONCILIATION_REQUIRED", 3),
    ("ALREADY_CURRENT_UNATTESTED", 4),
]


def test_la_tabla_de_estados_y_codigos_es_EXACTAMENTE_esta(promotor):
    """Se escriben los cinco pares a mano a proposito: comparar el diccionario consigo
    mismo no probaria nada. Esto fija los VALORES, no solo la forma."""
    assert promotor.CODIGOS_DE_SALIDA == dict(ESTADOS_Y_CODIGOS)
    assert len(promotor.CODIGOS_DE_SALIDA) == 5
    for nombre, _codigo in ESTADOS_Y_CODIGOS:
        assert getattr(promotor, nombre) == nombre, (
            f"la constante {nombre} deberia valer su propio nombre"
        )


@pytest.mark.parametrize("estado,codigo", ESTADOS_Y_CODIGOS)
def test_main_devuelve_el_codigo_de_CADA_estado_y_solo_promoted_sale_en_cero(
    promotor, monkeypatch, capsys, estado, codigo
):
    """Las dos garantias van juntas porque la segunda esta IMPLICADA por la primera.

    Separarlas daba una prueba que no puede fallar sola: si `main` devuelve el codigo de
    la tabla y la tabla solo tiene un cero, «solo PROMOTED sale verde» se cumple por
    construccion. Una prueba que no puede caer sola es decoracion; aqui la afirmacion se
    hace donde de verdad aporta, junto a la que la sostiene.

    Lo que el job lee es EL CODIGO DE SALIDA. Un cero de mas es una promocion que se da
    por buena sin estarlo.
    """
    monkeypatch.setattr(
        promotor, "ejecutar", lambda *a, **k: promotor.Resultado(estado, "detalle")
    )
    devuelto = promotor.main([])
    assert devuelto == codigo
    assert (devuelto == 0) == (estado == "PROMOTED"), (
        f"{estado} salio con {devuelto}: el unico camino verde es PROMOTED"
    )
    salida = capsys.readouterr().out
    assert f"ESTADO={estado}" in salida, salida


class _FalloDeBase(BaseException):
    """Hereda de BaseException y NO de Exception, que es lo que hay que ejercitar.

    Se define aqui en vez de usar `KeyboardInterrupt` porque pytest trata esa excepcion
    como una peticion de aborto y termina la SESION entera: la prueba no fallaria, se
    interrumpiria la corrida, y el arnes de mutacion lo contaria como cero fallos. Es
    decir: usar KeyboardInterrupt hacia inerte la mutacion que cambia `BaseException`
    por `Exception`. Medido, no supuesto.
    """


@pytest.mark.parametrize(
    "excepcion",
    [
        RuntimeError("algo se rompio"),
        ValueError("otra cosa"),
        # BaseException y no Exception: la red de seguridad del secreto tiene que cubrir
        # tambien lo que no hereda de Exception, o un traceback llegaria al log publico.
        _FalloDeBase("no hereda de Exception"),
    ],
)
def test_main_convierte_una_excepcion_INESPERADA_en_fail_closed(
    promotor, monkeypatch, capsys, excepcion
):
    def revienta(*_a, **_k):
        raise excepcion

    monkeypatch.setattr(promotor, "ejecutar", revienta)
    codigo = promotor.main([])
    assert codigo == promotor.CODIGOS_DE_SALIDA[promotor.FAIL_CLOSED]
    assert codigo != 0
    capturado = capsys.readouterr()
    assert "ESTADO=FAIL_CLOSED" in capturado.out
    assert type(excepcion).__name__ in capturado.err
    assert "Traceback" not in capturado.err, (
        "un traceback en un log de repositorio publico es exactamente lo que se evita"
    )


def test_main_REDACTA_el_token_de_una_excepcion_inesperada(promotor, monkeypatch, capsys):
    """El caso que justifica el `except BaseException`: el log de Actions es publico."""
    monkeypatch.setenv("VERCEL_PROJECT_PROMOTION_TOKEN", TOKEN)

    def revienta(*_a, **_k):
        raise RuntimeError(f"fallo pidiendo https://api.vercel.com con {TOKEN} dentro")

    monkeypatch.setattr(promotor, "ejecutar", revienta)
    codigo = promotor.main([])
    capturado = capsys.readouterr()
    assert TOKEN not in capturado.out + capturado.err, "el token se filtro al log"
    assert "***REDACTADO***" in capturado.err
    assert codigo == promotor.CODIGOS_DE_SALIDA[promotor.FAIL_CLOSED]


def test_main_no_redacta_de_menos_cuando_no_hay_token(promotor, monkeypatch, capsys):
    """Contrapunto: sin secreto en el entorno, el mensaje sale entero. Una redaccion que
    borrara de mas dejaria los fallos ilegibles."""
    monkeypatch.delenv("VERCEL_PROJECT_PROMOTION_TOKEN", raising=False)

    def revienta(*_a, **_k):
        raise RuntimeError("un mensaje sin secretos")

    monkeypatch.setattr(promotor, "ejecutar", revienta)
    promotor.main([])
    assert "un mensaje sin secretos" in capsys.readouterr().err


class _OpenerProhibido:
    """Sustituye al opener real. Si el programa intentara abrir una conexion, esto lo
    convierte en un fallo ruidoso en vez de en una peticion de verdad."""

    def __init__(self):
        self.intentos = []

    def open(self, peticion, timeout=None):
        self.intentos.append(getattr(peticion, "full_url", peticion))
        raise AssertionError(f"el programa abrio una conexion: {self.intentos}")


def test_main_SIN_ENTRADAS_falla_cerrado_antes_de_tocar_la_red(promotor, monkeypatch, capsys):
    """Ejecucion REAL: `ejecutar` de verdad, transporte por defecto de verdad.

    Es el caso del dia del cutover si alguien olvida el secreto o las variables. Tiene
    que cerrar por entrada ausente ANTES de construir el cliente, no despues de intentar
    hablar con Vercel sin credencial.
    """
    for variable in promotor.VARIABLES_REQUERIDAS:
        monkeypatch.delenv(variable, raising=False)
    opener = _OpenerProhibido()
    monkeypatch.setattr(promotor, "_OPENER", opener)

    codigo = promotor.main([])

    assert opener.intentos == [], "no puede haber ni un intento de conexion"
    assert codigo == promotor.CODIGOS_DE_SALIDA[promotor.FAIL_CLOSED]
    assert codigo != 0
    salida = capsys.readouterr().out
    assert "ESTADO=FAIL_CLOSED" in salida
    assert "faltan variables requeridas" in salida


@pytest.mark.parametrize("ausente", ["VERCEL_PROJECT_PROMOTION_TOKEN", "VERCEL_PROMOTION_PROJECT_ID", "VERCEL_PROMOTION_ALIAS"])
def test_main_con_UNA_variable_ausente_tampoco_toca_la_red(promotor, monkeypatch, capsys, ausente):
    """Que falten las tres es facil de acertar. Lo que hay que fijar es que basta con que
    falte UNA."""
    for variable, valor in entorno().items():
        monkeypatch.setenv(variable, valor)
    monkeypatch.delenv(ausente, raising=False)
    opener = _OpenerProhibido()
    monkeypatch.setattr(promotor, "_OPENER", opener)

    codigo = promotor.main([])

    # La afirmacion que da nombre a la prueba va PRIMERO: si va la ultima, cualquier
    # fallo anterior reporta otra cosa y el nombre de la prueba enganaria al leer el log.
    assert opener.intentos == [], "no puede haber ni un intento de conexion"
    assert codigo == promotor.CODIGOS_DE_SALIDA[promotor.FAIL_CLOSED]
    salida = capsys.readouterr().out
    assert ausente in salida


def test_main_es_lo_que_invoca_el_guardian_de_la_linea_de_ordenes():
    """El guardian tiene que ser EXACTAMENTE `if __name__ == "__main__":` y llamar a main.

    Tres versiones de esta prueba, y las dos primeras estaban rotas:

      textual   `sys.exit(0)  # sys.exit(main())` la satisfacia, porque el comentario
                contiene el texto que se buscaba.
      por AST   comprobaba el lado izquierdo (`__name__`) y NADA MAS. Ni el operador ni
                el comparador. Medido: con `if __name__ == "__never__":` las 348 focales
                pasaban, y el programa ejecutado de verdad salia con codigo 0 y sin
                imprimir nada, es decir, el job quedaba VERDE sin haber promovido ni
                haber fallado cerrado. Esa es la regresion que esta version cierra.

    Ahora se exige la comparacion COMPLETA: un solo operador, que sea `==`, un solo
    comparador, y que ese comparador sea la constante `"__main__"`.

    No recibe la fixture `promotor` A PROPOSITO. Lee el fuente y lo parsea, asi que sigue
    dando un veredicto util cuando el modulo ni siquiera se puede importar — que es
    justo lo que pasa si alguien escribe `!=`: el programa se ejecuta al importarlo y
    revienta la fixture. Una guarda que depende de que lo guardado funcione no sirve
    precisamente el dia que deja de funcionar.
    """
    import ast as _ast

    arbol = _ast.parse(_RUTA.read_text(encoding="utf-8"), filename=str(_RUTA))
    guardianes = [
        n for n in arbol.body
        if isinstance(n, _ast.If)
        and isinstance(n.test, _ast.Compare)
        and isinstance(n.test.left, _ast.Name)
        and n.test.left.id == "__name__"
    ]
    assert len(guardianes) == 1, f"se esperaba un unico guardian; hay {len(guardianes)}"
    prueba = guardianes[0].test

    assert len(prueba.ops) == 1 and isinstance(prueba.ops[0], _ast.Eq), (
        f"el guardian tiene que comparar con `==`; usa "
        f"{[type(o).__name__ for o in prueba.ops]}. Con `!=` el programa se ejecuta al "
        "IMPORTARLO y no se ejecuta cuando se invoca como programa."
    )
    assert len(prueba.comparators) == 1, (
        f"se esperaba un unico comparador; hay {len(prueba.comparators)}"
    )
    comparador = prueba.comparators[0]
    assert isinstance(comparador, _ast.Constant) and comparador.value == "__main__", (
        f"el guardian compara contra {_ast.dump(comparador)[:60]}. Cualquier cadena que "
        "no sea `__main__` deja el bloque muerto: el programa sale con 0 sin promover y "
        "sin fallar cerrado, y el job lo lee como exito."
    )

    llamadas = [n for n in _ast.walk(guardianes[0]) if isinstance(n, _ast.Call)]
    salidas = [
        c for c in llamadas
        if isinstance(c.func, _ast.Attribute) and c.func.attr == "exit"
    ]
    assert len(salidas) == 1, f"el guardian debe salir una vez; sale {len(salidas)}"
    argumentos = salidas[0].args
    assert len(argumentos) == 1, "sys.exit tiene que recibir el codigo de main"
    interior = argumentos[0]
    assert isinstance(interior, _ast.Call), (
        f"sys.exit recibe {_ast.dump(interior)[:80]}, no una llamada: el codigo de salida "
        "no vendria de main y el job leeria un cero fijo"
    )
    assert isinstance(interior.func, _ast.Name) and interior.func.id == "main", (
        "sys.exit tiene que llamar a `main`"
    )


class _OpenerQueRegistra:
    """Sustituye al opener real ANTES de que el modulo lo construya."""

    def __init__(self):
        self.intentos = []

    def open(self, peticion, timeout=None):
        self.intentos.append(getattr(peticion, "full_url", peticion))
        raise AssertionError(f"el programa abrio una conexion: {self.intentos}")


def test_ejecutado_COMO_PROGRAMA_sin_entradas_sale_2_y_no_toca_la_red(monkeypatch, capsys):
    """La prueba de ejecucion REAL, que es la que no se puede satisfacer leyendo el AST.

    `runpy.run_path(..., run_name="__main__")` ejecuta el fichero igual que
    `python scripts/promover_produccion.py`: el guardian se evalua de verdad. Por eso
    cae con las TRES formas de romperlo —comparador cambiado, operador negado, salida
    con cero fijo— y por un motivo distinto en cada caso, sin depender de como este
    escrito el fuente.

    Lo que se fija es el contrato que lee el runner: sin entradas, codigo 2,
    `ESTADO=FAIL_CLOSED` por stdout, y ni un intento de conexion.
    """
    import runpy
    import urllib.request

    for variable in (
        "VERCEL_PROJECT_PROMOTION_TOKEN",
        "VERCEL_PROMOTION_PROJECT_ID",
        "VERCEL_PROMOTION_ALIAS",
    ):
        monkeypatch.delenv(variable, raising=False)

    # Se intercepta la FABRICA, no el opener ya construido: el modulo se ejecuta desde
    # cero dentro de runpy y arma el suyo propio en tiempo de importacion.
    opener = _OpenerQueRegistra()
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_a, **_k: opener)

    with pytest.raises(SystemExit) as salida:
        runpy.run_path(str(_RUTA), run_name="__main__")

    assert opener.intentos == [], "no puede haber ni un intento de conexion"
    assert salida.value.code == 2, (
        f"el programa salio con {salida.value.code!r}; el runner lee ese numero y un 0 "
        "seria una promocion dada por buena sin haber ocurrido"
    )
    capturado = capsys.readouterr()
    assert "ESTADO=FAIL_CLOSED" in capturado.out, capturado.out
    assert "faltan variables requeridas" in capturado.out


def test_ejecutado_como_MODULO_no_hace_nada(monkeypatch, capsys):
    """La otra mitad del contrato del guardian, y la que atrapa el `!=`.

    Importar el fichero NO puede ejecutar nada: si lo hiciera, cualquier prueba que lo
    cargue promoveria de verdad. Con `!=` pasa exactamente eso, y ademas el programa
    deja de ejecutarse cuando se le invoca como programa.
    """
    import runpy
    import urllib.request

    opener = _OpenerQueRegistra()
    monkeypatch.setattr(urllib.request, "build_opener", lambda *_a, **_k: opener)

    espacio = runpy.run_path(str(_RUTA), run_name="promover_produccion_bajo_prueba")

    assert opener.intentos == []
    assert capsys.readouterr().out == "", "importarlo no puede imprimir nada"
    assert callable(espacio["main"]), "el modulo si define main; simplemente no lo llama"


# ── (N) precondiciones duraderas, no estados del día ───────────────────────────


def test_el_codigo_no_afirma_el_estado_de_hoy_de_auto_assign(promotor):
    """Las afirmaciones temporales caducan y envejecen mal dentro del producto.

    Lo que debe quedar es la PRECONDICIÓN —Auto-Assign tiene que estar en OFF— no una
    foto de cómo estaba el día que se escribió.
    """
    raiz = pathlib.Path(__file__).resolve().parents[1]
    for ruta in (_RUTA, raiz / ".github" / "workflows" / "pruebas.yml"):
        texto = ruta.read_text(encoding="utf-8")
        assert "hoy lo está" not in texto, f"{ruta.name} afirma el estado de hoy"
        assert "hoy lo esta" not in texto, f"{ruta.name} afirma el estado de hoy"
        assert "NO existe todavía" not in texto, f"{ruta.name} dice que algo no existe"
        assert "no existe todavia" not in texto.lower(), ruta.name
        # y sí debe enunciar la precondición
        assert "OFF" in texto, f"{ruta.name} debe enunciar la precondición de Auto-Assign"
