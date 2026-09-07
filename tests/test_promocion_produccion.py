"""Pruebas de COMPORTAMIENTO del promotor · VERCEL-RELEASE-CONTROL-F-R1.

No tocan la red, no usan credenciales y no llaman a la API de Vercel. El transporte
es inyectable y aquí se sustituye por un doble que responde con cuerpos sintéticos
ajustados al schema oficial. El reloj y la espera también se inyectan, para que el
sondeo acotado se pueda probar sin esperar de verdad.

EL DOBLE LEE LA QUERY. Una versión anterior la descartaba, y eso dejaba fuera de
prueba todos los parámetros de consulta: `withGitRepoInfo` —del que depende R1
entera—, el cursor `until` de la paginación y los tres filtros del listado. Se podían
borrar del producto y la suite seguía verde. Ahora la página se elige POR EL CURSOR,
no contando llamadas, y hay asertos explícitos sobre los parámetros.

HONESTIDAD SOBRE EL RED: contra el padre 4275655 este fichero no arrancaba —el módulo
no existía— y eso es un ImportError, NO una prueba de comportamiento en rojo. Lo que
demuestra que estas pruebas discriminan son las mutaciones del §6 del informe.
"""

import importlib.util
import io
import pathlib
import sys
import urllib.parse

import pytest

_RUTA = (
    pathlib.Path(__file__).resolve().parent.parent / "scripts" / "promover_produccion.py"
)

SHA_BUENO = "a" * 40
SHA_OTRO = "b" * 40
PROYECTO = "prj_ejemplo"
ALIAS = "contexxto.com"
REPO = "contexxto/contexto-ai"
TOKEN = "tok_sintetico_no_es_un_secreto_real_0123456789"


@pytest.fixture(scope="module")
def promotor():
    spec = importlib.util.spec_from_file_location("promover_produccion", _RUTA)
    modulo = importlib.util.module_from_spec(spec)
    # Registrar ANTES de ejecutar: el módulo usa `from __future__ import annotations`,
    # así que las anotaciones son cadenas y dataclasses necesita resolverlas contra un
    # módulo presente en sys.modules.
    sys.modules[spec.name] = modulo
    try:
        spec.loader.exec_module(modulo)
    except Exception:
        del sys.modules[spec.name]
        raise
    return modulo


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
        "VERCEL_PROMOTION_ALIAS": ALIAS,
    }
    base.update(cambios)
    return {k: v for k, v in base.items() if v is not None}


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


class _Quitar:
    pass


_QUITAR = _Quitar()


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


# Identificadores que representan «lo que el alias servía antes»: mismo proyecto, SHA
# distinto y ya promovido. El doble les da un detalle por defecto para que cada guion
# no tenga que repetirlo; cualquier otro identificador inesperado sigue siendo error.
_DESPLIEGUES_VIEJOS = frozenset({"dpl_previo", "dpl_otro", "dpl_viejo", "dpl_9"})


def alias_a(uid: str, proyecto: str = PROYECTO) -> dict:
    return {
        "alias": ALIAS,
        "created": "x",
        "uid": "alias_1",
        "deploymentId": uid,
        "projectId": proyecto,
    }


class Transporte:
    """Doble de transporte CONSCIENTE DE LA QUERY.

    `paginas` es una lista de (elementos, siguiente_cursor). La página se elige por el
    valor de `until` recibido, no por el número de llamada: así el cursor queda bajo
    prueba de verdad.
    """

    def __init__(
        self,
        promotor,
        paginas=None,
        detalles=None,
        alias=None,
        alias_secuencia=None,
        post=None,
        listado=None,
    ):
        self.p = promotor
        self.paginas = paginas if paginas is not None else [([], None)]
        self.detalles = detalles or {}
        self.alias = alias
        self.alias_secuencia = list(alias_secuencia or [])
        self.post = post
        self.listado = listado  # anula por completo la respuesta del listado
        self.llamadas: list[tuple[str, str, dict]] = []

    @property
    def posts(self) -> int:
        return sum(1 for m, _, _ in self.llamadas if m == "POST")

    @property
    def lecturas_de_alias(self) -> int:
        return sum(
            1 for m, u, _ in self.llamadas if m == "GET" and "/v4/aliases/" in u
        )

    def consultas_de(self, fragmento: str) -> list[dict]:
        return [q for _m, u, q in self.llamadas if fragmento in u]

    def __call__(self, metodo, url, cabeceras, timeout):
        partes = urllib.parse.urlsplit(url)
        consulta = dict(urllib.parse.parse_qsl(partes.query))
        self.llamadas.append((metodo, url, consulta))
        assert timeout is not None and timeout > 0, "toda llamada necesita timeout"
        assert cabeceras.get("Authorization", "").startswith("Bearer ")
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
                    # Lo que servía el alias ANTES: mismo proyecto, SHA distinto, ya
                    # promovido. Se sirve por defecto para no repetirlo en cada guion,
                    # pero cualquier otro identificador sigue siendo un error: el
                    # doble no debe tapar una llamada inesperada.
                    return self.p.Respuesta(
                        200, detalle(uid, sha=SHA_OTRO, readySubstate="PROMOTED")
                    )
                raise AssertionError(f"detalle no previsto para {uid}")
            return self._responder(self.detalles[uid])
        if "/v4/aliases/" in partes.path:
            if self.alias_secuencia:
                return self._responder(self.alias_secuencia.pop(0))
            if self.alias is None:
                # Por defecto el alias sirve algo ANTERIOR y distinto. Es el estado
                # normal de producción antes de una promoción, y evita que cada guion
                # tenga que declararlo. Para probar un alias ilegible se pasa un
                # código explícito o una excepción.
                return self.p.Respuesta(200, alias_a("dpl_previo"))
            return self._responder(self.alias)
        raise AssertionError(f"URL no prevista: {url}")

    def _pagina(self, consulta):
        # La primera página es la que NO trae cursor; las siguientes se localizan por
        # el cursor recibido. Si el producto dejara de enviar `until`, pediría
        # eternamente la primera y la prueba de paginación se caería.
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
    marcas = iter(reloj or [0.0] * 200)
    resultado = promotor.ejecutar(
        ent if ent is not None else entorno(),
        transporte=transporte,
        dormir=lambda _s: None,
        reloj=lambda: next(marcas, 10_000.0),
        salida=salida,
    )
    return resultado, salida.getvalue()


def guion_nominal(promotor, **cambios):
    base = dict(
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1")},
        alias_secuencia=[alias_a("dpl_previo"), alias_a("dpl_1")],
        post=(202, None),
    )
    base.update(cambios)
    return Transporte(promotor, **base)


# ── (6) barrera redundante dentro del programa ─────────────────────────────────


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
    # Si un PR borrase la línea `if:` del YAML, `pytest` no lo vería: no inspecciona
    # .github/workflows/. Esta barrera es la que queda.
    transporte = Transporte(promotor)
    resultado, _ = correr(promotor, transporte, entorno(**cambio))
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.posts == 0
    assert transporte.llamadas == [], "no debe hacerse ni una llamada"


# ── (7) SHA ausente o malformado ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "sha", ["", "a" * 39, "a" * 41, "A" * 40, "g" * 40, "abc", " " + "a" * 39]
)
def test_sha_ausente_o_malformado(promotor, sha):
    transporte = Transporte(promotor)
    resultado, _ = correr(promotor, transporte, entorno(GITHUB_SHA=sha))
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.posts == 0


# ── (8) el detalle que no prueba identidad ─────────────────────────────────────


@pytest.mark.parametrize(
    "cambios,motivo",
    [
        ({"gitSource": None}, "sin gitSource"),
        ({"gitSource": _QUITAR}, "gitSource ausente del documento"),
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
        (
            {"type": "github", "org": "otra-org", "repo": "contexto-ai", "sha": SHA_BUENO},
            "otra organización",
        ),
        (
            {"type": "github", "org": "contexxto", "repo": "otro-repo", "sha": SHA_BUENO},
            "otro repositorio",
        ),
    ],
)
def test_el_origen_del_artefacto_debe_ser_el_repositorio_que_aprobo(
    promotor, origen, motivo
):
    # R1 dice «el artefacto corresponde al SHA aprobado». Un SHA es un hash de
    # contenido: sin atar el origen, otro repositorio con el mismo hash pasaría.
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1", origen=origen)},
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.UNAVAILABLE, motivo
    assert transporte.posts == 0


def test_el_origen_por_repoId_sin_nombres_se_acepta_con_projectId(promotor):
    # Límite declarado: hay formas de gitSource que solo traen repoId. La pertenencia
    # queda sostenida por projectId, que ya se comprobó.
    transporte = guion_nominal(
        promotor,
        detalles={
            "dpl_1": detalle(
                "dpl_1", origen={"type": "github", "repoId": 7, "sha": SHA_BUENO}
            )
        },
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.PROMOTED


def test_el_detalle_debe_responder_por_el_identificador_que_se_pidio(promotor):
    # `id` es requerido en las tres variantes del detalle. Sin este aserto, la
    # identidad del listado y la del documento validado no están atadas entre sí.
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_OTRO")},
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.UNAVAILABLE
    assert transporte.posts == 0


def test_el_detalle_se_pide_con_withGitRepoInfo(promotor):
    # Sin ese parámetro la respuesta no trae gitSource y R1 se quedaría sin campo.
    transporte = guion_nominal(promotor)
    correr(promotor, transporte)
    consultas = transporte.consultas_de("/v13/deployments/")
    assert consultas, "no se pidió el detalle"
    for consulta in consultas:
        assert consulta.get("withGitRepoInfo") == "true", consulta


@pytest.mark.parametrize("codigo", [400, 401, 403, 404, 410, 429, 500])
def test_detalle_no_ok_es_fail_closed(promotor, codigo):
    # El cuerpo es un OBJETO VÁLIDO a propósito: con `None` la guarda de cuerpo
    # taparía a la de estado y esta prueba no distinguiría cuál actúa. Es el caso que
    # dejó inerte a la mutación «quitar la guarda de estado del detalle».
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
        detalles={"dpl_1": (200, ["no", "es", "un", "objeto"])},
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.posts == 0


# ── (9) cero candidatos ────────────────────────────────────────────────────────


def test_cero_candidatos_es_indisponibilidad_sin_post(promotor):
    transporte = Transporte(promotor, paginas=[([], None)])
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.UNAVAILABLE
    assert transporte.posts == 0
    assert resultado.codigo != 0


# ── (10) más de un candidato ───────────────────────────────────────────────────


def test_dos_candidatos_validos_es_fail_closed(promotor):
    # Con alias legible, para que el FAIL_CLOSED sea el de la ambigüedad y no el de
    # un alias que no se pudo leer. Una versión anterior pasaba por el motivo
    # equivocado y no habría detectado que la guarda se aflojara.
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1"), item_listado("dpl_2")], None)],
        detalles={"dpl_1": detalle("dpl_1"), "dpl_2": detalle("dpl_2")},
        alias=alias_a("dpl_previo"),
        post=(202, None),
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert "ambigüedad" in salida
    assert transporte.posts == 0


def test_el_segundo_candidato_sin_readySubstate_en_el_listado_sigue_contando(promotor):
    """FAIL-OPEN corregido, y el más grave que tuvo esta unidad.

    `readySubstate` NO es un campo requerido del item del listado. Una versión
    anterior prefiltraba por él, de modo que un segundo candidato cuyo item omitiera
    el campo desaparecía antes del detalle: la comprobación de ambigüedad —única
    defensa de R2— no llegaba a dispararse y el programa promovía.
    """
    transporte = Transporte(
        promotor,
        paginas=[
            ([item_listado("dpl_1"), item_listado("dpl_2", readySubstate=_QUITAR)], None)
        ],
        detalles={"dpl_1": detalle("dpl_1"), "dpl_2": detalle("dpl_2")},
        alias=alias_a("dpl_previo"),
        post=(202, None),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.posts == 0


def test_el_prefiltro_si_excluye_lo_que_demuestra_no_ser_staged(promotor):
    # La optimización sigue viva: un item que DICE PROMOTED no gasta una llamada.
    transporte = guion_nominal(
        promotor,
        paginas=[
            ([item_listado("dpl_1"), item_listado("dpl_viejo", readySubstate="PROMOTED")], None)
        ],
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.PROMOTED
    pedidos = [u for _m, u, _q in transporte.llamadas if "/v13/deployments/" in u]
    # Se pide el detalle del candidato y el de lo que servía el alias. NO el del que
    # ya declara PROMOTED en el listado: ése es el ahorro que da el prefiltro.
    assert not any("dpl_viejo" in u for u in pedidos), (
        "se pidió el detalle de un despliegue que ya decía PROMOTED en el listado"
    )
    assert any("dpl_1" in u for u in pedidos)


def test_elemento_del_listado_sin_uid_es_fail_closed(promotor):
    # `uid` es requerido en el item. Si falta, no se puede saber si ese elemento era
    # un segundo candidato: descartarlo en silencio abriría la misma vía.
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


# ── (11) paginación ────────────────────────────────────────────────────────────


def test_la_paginacion_usa_el_cursor_y_encuentra_al_de_la_ultima_pagina(promotor):
    transporte = Transporte(
        promotor,
        paginas=[
            ([item_listado("dpl_viejo", readySubstate="PROMOTED")], 1000),
            ([item_listado("dpl_1")], None),
        ],
        detalles={"dpl_1": detalle("dpl_1")},
        alias_secuencia=[alias_a("dpl_previo"), alias_a("dpl_1")],
        post=(202, None),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.PROMOTED
    consultas = transporte.consultas_de("/v7/deployments")
    assert len(consultas) == 2, "no se agotó la paginación"
    assert "until" not in consultas[0], "la primera página no lleva cursor"
    assert consultas[1].get("until") == "1000", "la segunda debe llevar el cursor"


def test_el_listado_se_acota_por_proyecto_destino_y_estado(promotor):
    transporte = guion_nominal(promotor)
    correr(promotor, transporte)
    consulta = transporte.consultas_de("/v7/deployments")[0]
    assert consulta.get("projectId") == PROYECTO
    assert consulta.get("target") == "production"
    assert consulta.get("state") == "READY"
    # El filtro `sha` NO se envía: ocultaría a un segundo candidato.
    assert "sha" not in consulta


def test_el_equipo_viaja_cuando_esta_definido(promotor):
    transporte = guion_nominal(promotor)
    correr(promotor, transporte, entorno(VERCEL_PROMOTION_TEAM_ID="team_x"))
    for consulta in transporte.consultas_de("api.vercel.com"):
        assert consulta.get("teamId") == "team_x"


def test_paginacion_no_resoluble_es_fail_closed(promotor):
    # `next` no nulo indefinidamente: nunca se sabe si falta un candidato.
    transporte = Transporte(promotor, paginas=[([], i + 1) for i in range(40)])
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert "paginación no resuelta" in salida
    assert transporte.posts == 0


@pytest.mark.parametrize(
    "cuerpo,motivo",
    [
        ((200, {"pagination": {"next": None}}), "sin `deployments`"),
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
    # `deployments` y `pagination` son AMBOS requeridos en el contrato. Tratar la
    # ausencia del primero como «página vacía» perdería candidatos en silencio.
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
    # Se pasa la excepción como guion para que el doble la lance: `listado=None`
    # significaría «sin anulación» y caería en la paginación normal.
    transporte = Transporte(promotor, listado=promotor.ErrorTransporte("caido"))
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert "listado sin respuesta concluyente" in salida
    # Y los reintentos del GET quedaron acotados: no hubo bucle.
    assert salida.count("reintento acotado") == promotor.REINTENTOS_GET
    assert transporte.posts == 0


def test_demasiados_preseleccionados_es_fail_closed(promotor):
    muchos = [item_listado(f"dpl_{i}") for i in range(promotor.DETALLES_MAXIMOS + 1)]
    transporte = Transporte(promotor, paginas=[(muchos, None)])
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert "supera el tope" in salida
    assert transporte.posts == 0
    assert transporte.consultas_de("/v13/deployments/") == [], "ni un detalle"


# ── (12) exactamente un candidato válido ───────────────────────────────────────


def test_un_solo_candidato_valido_continua(promotor):
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1"), item_listado("dpl_2")], None)],
        detalles={"dpl_1": detalle("dpl_1"), "dpl_2": detalle("dpl_2", sha=SHA_OTRO)},
        alias_secuencia=[alias_a("dpl_previo"), alias_a("dpl_1")],
        post=(202, None),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.PROMOTED
    assert resultado.detalle == "dpl_1"
    assert transporte.posts == 1


# ── (13) alias ya en el objetivo ───────────────────────────────────────────────


def test_el_estado_preexistente_es_no_atestiguado_y_no_verde(promotor):
    """CASO OBLIGATORIO fijado por el adjudicador.

    El alias ya sirve el SHA aprobado ANTES de que esta ejecución haga nada. Ese
    despliegue está en `PROMOTED` —el contrato documenta ese valor precisamente para
    lo que ya vio tráfico de producción— y por tanto NO figura entre los candidatos
    STAGED: hay CERO. Una versión anterior terminaba aquí en UNAVAILABLE sin llegar a
    mirar el alias, de modo que el caso ni se detectaba.

    Observar qué sirve Vercel no demuestra que F lo promoviera, ni que la publicación
    esperara la aprobación, ni que `Auto-Assign` estuviera apagado, ni que no hubiera
    una promoción manual. Con `Auto-Assign` en ON, dejarlo verde certificaría el
    bypass que C1 declara abierto.
    """
    servido = detalle("dpl_servido", readySubstate="PROMOTED")
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_servido", readySubstate="PROMOTED")], None)],
        detalles={"dpl_servido": servido},
        alias=alias_a("dpl_servido"),
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.ALREADY_CURRENT_UNATTESTED
    assert resultado.codigo != 0, "no puede terminar verde"
    assert transporte.posts == 0
    assert resultado.estado != promotor.PROMOTED
    assert "NO acredita" in salida


def test_la_deteccion_no_depende_de_que_siga_apareciendo_como_staged(promotor):
    # El mismo caso con substate STAGED y con PROMOTED debe dar el mismo veredicto:
    # la detección no puede colgar de ese campo.
    for substate in ("PROMOTED", "STAGED", "ROLLING"):
        transporte = Transporte(
            promotor,
            paginas=[([], None)],  # ni siquiera aparece en el listado
            detalles={"dpl_servido": detalle("dpl_servido", readySubstate=substate)},
            alias=alias_a("dpl_servido"),
        )
        resultado, _ = correr(promotor, transporte)
        assert resultado.estado == promotor.ALREADY_CURRENT_UNATTESTED, substate
        assert resultado.codigo != 0
        assert transporte.posts == 0


def test_un_alias_que_sirve_OTRO_sha_no_es_estado_preexistente(promotor):
    # Camino normal: lo servido no es el SHA aprobado, así que sí hay que promover.
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={
            "dpl_1": detalle("dpl_1"),
            "dpl_viejo": detalle("dpl_viejo", sha=SHA_OTRO, readySubstate="PROMOTED"),
        },
        alias_secuencia=[alias_a("dpl_viejo"), alias_a("dpl_1")],
        post=(202, None),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.PROMOTED
    assert transporte.posts == 1


def test_un_alias_que_sirve_otro_proyecto_no_es_estado_preexistente(promotor):
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={
            "dpl_1": detalle("dpl_1"),
            "dpl_ajeno": detalle("dpl_ajeno", projectId="prj_ajeno"),
        },
        alias_secuencia=[alias_a("dpl_ajeno", proyecto="prj_ajeno"), alias_a("dpl_1")],
        post=(202, None),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.PROMOTED
    assert transporte.posts == 1


def test_si_no_se_puede_leer_lo_que_sirve_el_alias_no_se_promueve(promotor):
    # Sin poder descartar el caso no atestiguado, no se promueve.
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1"), "dpl_servido": (500, {"error": "x"})},
        alias=alias_a("dpl_servido"),
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert "no se pudo leer lo que sirve el alias" in salida
    assert resultado.detalle == "lo servido por el alias no es legible"
    assert transporte.posts == 0


# ── (14) alias con campos nulos o ilegible ─────────────────────────────────────


@pytest.mark.parametrize(
    "cuerpo",
    [
        {"alias": ALIAS, "created": "x", "uid": "a", "deploymentId": None, "projectId": PROYECTO},
        {"alias": ALIAS, "created": "x", "uid": "a", "deploymentId": "dpl_1", "projectId": None},
        {"alias": ALIAS, "created": "x", "uid": "a", "deploymentId": None, "projectId": None},
        {"alias": ALIAS, "created": "x", "uid": "a"},
        {"alias": ALIAS, "created": "x", "uid": "a", "deploymentId": "", "projectId": ""},
        {"alias": ALIAS, "created": "x", "uid": "a", "deploymentId": 7, "projectId": 8},
    ],
)
def test_alias_con_nulos_no_cuenta_como_reconciliado(promotor, cuerpo):
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1")},
        alias=cuerpo,
        post=(202, None),
    )
    resultado, _ = correr(promotor, transporte)
    # Nunca ALREADY_CURRENT: un null no es coincidencia. Y como el sondeo posterior
    # sigue viendo nulos, tampoco se puede afirmar la promoción.
    assert resultado.estado == promotor.UNKNOWN_RECONCILIATION_REQUIRED
    assert transporte.posts == 1


@pytest.mark.parametrize(
    "despliegue,proyecto,esperado",
    [
        ("dpl_1", PROYECTO, True),
        (None, PROYECTO, False),
        ("dpl_1", None, False),
        (None, None, False),
        ("", PROYECTO, False),
        ("dpl_1", "", False),
    ],
)
def test_un_null_nunca_cuenta_como_reconciliado(promotor, despliegue, proyecto, esperado):
    estado = promotor.EstadoAlias(despliegue=despliegue, proyecto=proyecto)
    assert estado.reconciliado is esperado


def test_alias_apunta_a_rechaza_un_objetivo_vacio(promotor):
    # Aserto que SÍ separa la conjunción: con objetivo vacío, las igualdades podrían
    # cumplirse contra un estado igualmente vacío y aun así no es el objetivo.
    vacio = promotor.EstadoAlias(despliegue=None, proyecto=None)
    assert promotor.alias_apunta_a(vacio, "", "") is False
    assert promotor.alias_apunta_a(vacio, "dpl_1", PROYECTO) is False
    bueno = promotor.EstadoAlias(despliegue="dpl_1", proyecto=PROYECTO)
    assert promotor.alias_apunta_a(bueno, "dpl_1", PROYECTO) is True
    assert promotor.alias_apunta_a(bueno, "dpl_otro", PROYECTO) is False
    assert promotor.alias_apunta_a(bueno, "dpl_1", "prj_otro") is False
    assert promotor.alias_apunta_a(bueno, "", PROYECTO) is False


@pytest.mark.parametrize("codigo", [400, 401, 403, 404, 429, 500])
def test_alias_no_legible_es_fail_closed_y_no_promueve(promotor, codigo):
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1")},
        alias=(codigo, {"error": "x"}),
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert f"lectura del alias devolvió {codigo}" in salida
    assert transporte.posts == 0


def test_alias_con_cuerpo_que_no_es_objeto_es_fail_closed(promotor):
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1")},
        alias=(200, ["no", "es", "objeto"]),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.posts == 0


def test_se_consulta_el_alias_exacto_y_no_la_via_secundaria(promotor):
    transporte = Transporte(
        promotor,
        paginas=[([item_listado("dpl_1")], None)],
        detalles={"dpl_1": detalle("dpl_1")},
        alias=alias_a("dpl_1"),
    )
    correr(promotor, transporte)
    lecturas = [u for _m, u, _q in transporte.llamadas if "/v4/aliases/" in u]
    assert lecturas, "no se leyó el alias canónico"
    for url in lecturas:
        assert f"/v4/aliases/{ALIAS}" in url
        assert "/v2/deployments/" not in url


# ── (15) promoción nominal ─────────────────────────────────────────────────────


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


@pytest.mark.parametrize("codigo", list(sorted({400, 401, 403, 409, 410, 422})))
def test_codigos_de_rechazo_documentados_son_fail_closed(promotor, codigo):
    transporte = guion_nominal(
        promotor, alias=alias_a("dpl_previo"), alias_secuencia=None, post=(codigo, {"error": "x"})
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.posts == 1
    assert "rechazada por el servidor" in salida
    # Un rechazo documentado no necesita reconciliación: no hubo aceptación.
    assert transporte.lecturas_de_alias == 1


@pytest.mark.parametrize("codigo", [200, 204, 429, 500, 502, 504])
def test_codigo_no_documentado_tras_el_post_se_reconcilia(promotor, codigo):
    """No se puede afirmar que el servidor rechazara con un código que su contrato no
    documenta. Declararlo rechazo escondería una promoción que quizá sí ocurrió."""
    transporte = guion_nominal(promotor, post=(codigo, None))
    resultado, salida = correr(promotor, transporte)
    assert "no documentado" in salida
    assert resultado.estado == promotor.PROMOTED  # el sondeo lo confirma
    assert transporte.posts == 1


def test_codigo_no_documentado_sin_reconciliacion_es_unknown(promotor):
    transporte = guion_nominal(
        promotor,
        alias_secuencia=[alias_a("dpl_previo")] + [alias_a("dpl_otro")] * 40,
        post=(503, None),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.UNKNOWN_RECONCILIATION_REQUIRED
    assert transporte.posts == 1


# ── (16) y (17) pérdida de transporte ──────────────────────────────────────────


def test_perdida_de_transporte_reconciliada_es_promocion(promotor):
    transporte = guion_nominal(promotor, post=None)
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.PROMOTED
    assert transporte.posts == 1, "jamás un segundo POST"


def test_perdida_sin_resolucion_es_unknown_sin_reintento(promotor):
    transporte = guion_nominal(
        promotor,
        alias_secuencia=[alias_a("dpl_previo")] + [alias_a("dpl_otro")] * 40,
        post=None,
    )
    resultado, salida = correr(promotor, transporte)
    assert resultado.estado == promotor.UNKNOWN_RECONCILIATION_REQUIRED
    assert resultado.codigo != 0, "UNKNOWN debe salir con código no exitoso"
    assert transporte.posts == 1
    assert "UNKNOWN / NO RETRY / REQUIERE RECONCILIACIÓN" in salida


def test_unknown_nunca_se_convierte_en_exito_por_ausencia_de_evidencia(promotor):
    transporte = guion_nominal(
        promotor, alias_secuencia=[alias_a("dpl_previo")] + [None] * 40, post=None
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.UNKNOWN_RECONCILIATION_REQUIRED
    assert resultado.codigo != 0


def test_el_alias_de_otro_proyecto_no_reconcilia(promotor):
    transporte = guion_nominal(
        promotor,
        alias_secuencia=[alias_a("dpl_previo")] + [alias_a("dpl_1", proyecto="prj_ajeno")] * 40,
        post=(202, None),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.UNKNOWN_RECONCILIATION_REQUIRED


# ── (19) el sondeo es finito ───────────────────────────────────────────────────


def test_el_sondeo_termina_por_numero_de_intentos(promotor):
    transporte = guion_nominal(
        promotor,
        alias_secuencia=[alias_a("dpl_previo")] + [alias_a("dpl_otro")] * 100,
        post=(202, None),
    )
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.UNKNOWN_RECONCILIATION_REQUIRED
    sondeos = transporte.lecturas_de_alias - 1  # la primera es la lectura previa
    # El tope se escribe AQUÍ, como número literal. Compararlo contra
    # promotor.SONDEOS_MAXIMOS sería tautológico: subir la constante haría pasar la
    # prueba sola.
    assert 1 <= sondeos <= 10, f"sondeó {sondeos} veces"


def test_el_sondeo_termina_por_ventana_de_tiempo(promotor):
    transporte = guion_nominal(
        promotor,
        alias_secuencia=[alias_a("dpl_previo")] + [alias_a("dpl_otro")] * 100,
        post=(202, None),
    )
    resultado, salida = correr(
        promotor, transporte, reloj=[0.0, 1.0, 10_000.0, 10_001.0, 10_002.0]
    )
    assert resultado.estado == promotor.UNKNOWN_RECONCILIATION_REQUIRED
    assert "ventana de sondeo agotada por tiempo" in salida
    assert transporte.lecturas_de_alias - 1 <= 3, "la ventana debía cortar antes"


def test_los_limites_son_finitos_y_estan_en_el_codigo(promotor):
    # Cada techo es un número literal escrito aquí, no una lectura de la constante que
    # se quiere vigilar. Si alguien afloja un tope en el producto, esto se cae.
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
    }
    for nombre, techo in TECHOS.items():
        valor = getattr(promotor, nombre)
        assert isinstance(valor, (int, float)) and valor > 0, nombre
        assert valor <= techo, f"{nombre} = {valor} pasa del techo duro {techo}"


def test_los_reintentos_de_get_estan_acotados(promotor):
    class GetSiempreCaido(Transporte):
        def __call__(self, metodo, url, cabeceras, timeout):
            self.llamadas.append((metodo, url, {}))
            raise self.p.ErrorTransporte("caido")

    transporte = GetSiempreCaido(promotor)
    resultado, _ = correr(promotor, transporte)
    assert resultado.estado == promotor.FAIL_CLOSED
    assert len(transporte.llamadas) <= 6, "los reintentos de GET no están acotados"


# ── (21) secreto o entrada requerida ausente ───────────────────────────────────


@pytest.mark.parametrize("variable", list(("VERCEL_PROJECT_PROMOTION_TOKEN", "VERCEL_PROMOTION_PROJECT_ID", "VERCEL_PROMOTION_ALIAS")))
def test_entrada_requerida_ausente_falla_cerrado(promotor, variable):
    transporte = Transporte(promotor)
    resultado, salida = correr(promotor, transporte, entorno(**{variable: None}))
    assert resultado.estado == promotor.FAIL_CLOSED
    assert transporte.llamadas == [], "no se llama a nada sin las entradas"
    assert variable in salida, "se debe nombrar la variable que falta"


def test_entrada_vacia_cuenta_como_ausente(promotor):
    transporte = Transporte(promotor)
    resultado, _ = correr(promotor, transporte, entorno(VERCEL_PROJECT_PROMOTION_TOKEN=""))
    assert resultado.estado == promotor.FAIL_CLOSED


# ── (22) el token no aparece en logs ───────────────────────────────────────────


def test_el_token_no_aparece_en_ningun_camino(promotor):
    guiones = [
        dict(),  # nominal
        dict(paginas=[([], None)], detalles={}, alias_secuencia=None, alias=None),
        dict(post=(403, {"error": "denied"}), alias=alias_a("dpl_previo"), alias_secuencia=None),
        dict(alias_secuencia=[alias_a("dpl_previo")] + [None] * 40, post=None),
        dict(detalles={"dpl_1": detalle("dpl_1", sha=SHA_OTRO)}, alias=None, alias_secuencia=None),
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
    # Un secreto corto también es un secreto.
    assert "abc" not in promotor.redactar("valor abc aqui", ["abc"])
    assert "x" not in promotor.redactar("valor x aqui", ["x"])


def test_el_registro_redacta_aunque_le_pasen_el_token(promotor):
    salida = io.StringIO()
    registro = promotor.Registro(secretos=[TOKEN], salida=salida)
    registro(f"esto lleva el token {TOKEN} dentro")
    assert TOKEN not in salida.getvalue()
    assert TOKEN not in "".join(registro.lineas)


def test_el_repr_del_cliente_no_lleva_el_token(promotor):
    # Un traceback de pytest o de Actions imprime repr() de los locales.
    cliente = promotor.ClienteVercel(
        token=TOKEN, registro=promotor.Registro(salida=io.StringIO())
    )
    assert TOKEN not in repr(cliente)


def test_el_transporte_real_no_filtra_la_url_en_sus_errores(promotor, monkeypatch):
    """Prueba del transporte DE VERDAD, no de una excepción construida a mano.

    El resto de la suite inyecta un doble, así que `transporte_urllib` nunca se
    ejercita: sus fallos quedaban fuera de prueba. Aquí se sustituye solo el opener.
    """
    URL = f"https://api.vercel.com/v7/deployments?projectId={PROYECTO}&token_en_query=x"

    class OpenerQueFalla:
        def open(self, peticion, timeout=None):
            raise OSError(f"conexión rechazada contra {URL}")

    monkeypatch.setattr(promotor, "_OPENER", OpenerQueFalla())
    with pytest.raises(promotor.ErrorTransporte) as capturado:
        promotor.transporte_urllib("GET", URL, {"Authorization": f"Bearer {TOKEN}"}, 1.0)
    mensaje = str(capturado.value)
    assert mensaje == "OSError", f"el error arrastra contexto: {mensaje!r}"
    assert "api.vercel.com" not in mensaje
    assert TOKEN not in mensaje
    # `from None`: la excepción original no viaja como causa encadenada.
    assert capturado.value.__cause__ is None


def test_el_transporte_real_no_exige_json_en_las_respuestas_sin_cuerpo(promotor, monkeypatch):
    # Los 201 y 202 de la promoción no declaran `content` en el contrato. Exigir JSON
    # convertiría una aceptación en un fallo de transporte.
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


# ── (23) ninguna ruta puede emitir un segundo POST ─────────────────────────────


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
        dict(post=(403, None), alias=alias_a("dpl_previo"), alias_secuencia=None),
        dict(alias=alias_a("dpl_1"), alias_secuencia=None),
        dict(paginas=[([], None)], detalles={}),
    ]
    for guion in guiones:
        transporte = guion_nominal(promotor, **guion)
        correr(promotor, transporte)
        assert transporte.posts <= 1


def test_solo_hay_una_llamada_a_post_promocion_en_el_fuente():
    # Guarda estructural: si alguien añadiera una segunda invocación, la garantía
    # dejaría de descansar solo en el flag y habría que volver a razonarla.
    fuente = _RUTA.read_text(encoding="utf-8")
    assert fuente.count("post_promocion(") == 2, (
        "se esperan exactamente dos apariciones: la definición y su única llamada"
    )


# ── (24) relación estructural completa ─────────────────────────────────────────


def test_el_yaml_invoca_el_programa_que_existe_y_le_pasa_lo_que_pide(promotor):
    """No basta con probar el YAML por un lado y el programa por otro."""
    yaml = pytest.importorskip("yaml")
    raiz = pathlib.Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load(
        (raiz / ".github" / "workflows" / "pruebas.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["promocion-produccion"]
    pasos_con_run = [p for p in job["steps"] if "run" in p]
    assert pasos_con_run, "el job no ejecuta nada"
    paso = pasos_con_run[-1]

    invocado = paso["run"].split()[-1]
    assert (raiz / invocado).is_file(), f"el job invoca {invocado}, que no existe"
    assert (raiz / invocado).resolve() == _RUTA.resolve()

    puestas = set(paso.get("env", {}))
    for requerida in promotor.VARIABLES_REQUERIDAS:
        assert requerida in puestas, (
            f"el programa exige {requerida} y el job no la pasa; el gate fallaría "
            "cerrado en producción por una desconexión entre las dos mitades"
        )
    assert "secrets.VERCEL_PROJECT_PROMOTION_TOKEN" in paso["env"][
        "VERCEL_PROJECT_PROMOTION_TOKEN"
    ]
    for identificador in ("VERCEL_PROMOTION_PROJECT_ID", "VERCEL_PROMOTION_ALIAS"):
        assert "vars." in paso["env"][identificador]


def test_el_secreto_solo_se_expone_al_paso_que_lo_usa(promotor):
    yaml = pytest.importorskip("yaml")
    raiz = pathlib.Path(__file__).resolve().parents[1]
    workflow = yaml.safe_load(
        (raiz / ".github" / "workflows" / "pruebas.yml").read_text(encoding="utf-8")
    )
    job = workflow["jobs"]["promocion-produccion"]
    assert "env" not in job, "el secreto no debe vivir en el env del JOB"
    pasos_con_secreto = [
        p for p in job["steps"] if "VERCEL_PROJECT_PROMOTION_TOKEN" in (p.get("env") or {})
    ]
    assert len(pasos_con_secreto) == 1, "el secreto se expone a más de un paso"
    assert "promover_produccion.py" in pasos_con_secreto[0]["run"]


def test_los_estados_de_salida_son_inequivocos(promotor):
    estados = {
        promotor.PROMOTED,
        promotor.ALREADY_CURRENT_UNATTESTED,
        promotor.UNAVAILABLE,
        promotor.FAIL_CLOSED,
        promotor.UNKNOWN_RECONCILIATION_REQUIRED,
    }
    assert len(estados) == 5, "dos estados colisionan"
    assert set(promotor.CODIGOS_DE_SALIDA) == estados
    assert len(set(promotor.CODIGOS_DE_SALIDA.values())) == 5, "dos códigos colisionan"


def test_solo_la_promocion_atestiguada_es_verde(promotor):
    """`PROMOTED` es el ÚNICO estado con salida cero.

    Todo lo demás —incluido el estado preexistente— sale distinto de cero. Un alias
    que ya servía el SHA no acredita que F lo promoviera.
    """
    verdes = [
        estado
        for estado, codigo in promotor.CODIGOS_DE_SALIDA.items()
        if codigo == 0
    ]
    assert verdes == [promotor.PROMOTED], f"hay más estados verdes: {verdes}"
    assert promotor.CODIGOS_DE_SALIDA[promotor.ALREADY_CURRENT_UNATTESTED] != 0
    # Y el nombre lleva la reserva dentro: quien lo cite suelto ve que no está atestiguado.
    assert promotor.ALREADY_CURRENT_UNATTESTED.endswith("UNATTESTED")
    assert not hasattr(promotor, "ALREADY_CURRENT"), (
        "el estado antiguo, que era verde, no debe seguir existiendo"
    )


def test_los_codigos_de_exito_y_rechazo_son_los_del_contrato(promotor):
    # Documentados en el OpenAPI de Vercel para POST /v10/.../promote/...
    assert promotor.CODIGOS_DE_EXITO_DE_PROMOCION == frozenset({201, 202})
    assert promotor.CODIGOS_DE_RECHAZO_DOCUMENTADOS == frozenset(
        {400, 401, 403, 409, 410, 422}
    )
    assert not (
        promotor.CODIGOS_DE_EXITO_DE_PROMOCION & promotor.CODIGOS_DE_RECHAZO_DOCUMENTADOS
    )


def test_el_transporte_no_sigue_redirecciones(promotor):
    """Seguir un 30x reenviaría la cabecera Authorization a otro host.

    No basta con comprobar que la clase existe: hay que comprobar que el opener QUE
    SE USA la lleva instalada. Comprobar solo la clase dejó inerte a la mutación que
    devolvía el opener por defecto.
    """
    manejadores = [type(h).__name__ for h in promotor._OPENER.handlers]
    assert "_SinRedirecciones" in manejadores, (
        f"el opener no lleva el manejador que corta redirecciones: {manejadores}"
    )
    assert "HTTPRedirectHandler" not in manejadores, (
        "el manejador por defecto sigue instalado y seguiría los 30x"
    )
    manejador = promotor._SinRedirecciones()
    assert (
        manejador.redirect_request(None, None, 302, "", {}, "https://otro.example/x")
        is None
    )
