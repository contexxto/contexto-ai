# Pruebas ESTRUCTURALES del job de promoción dentro de .github/workflows/pruebas.yml.
#
# Por qué existen, y por qué son estructurales y no de integración: la unidad
# VERCEL-RELEASE-CONTROL-F-R1 implementa R1-R4 de F-02 — que se promueva el artefacto
# del SHA aprobado por el CI, solo ese, sin reconstruir y solo tras aprobación humana.
# Tres de esas cuatro garantías viven en el YAML (needs, condición de evento,
# environment), no en el programa. Un fallo aquí no rompe una función: abre la puerta.
#
# ESTAS PRUEBAS SON RED HONESTO CONTRA EL PADRE 4275655: el fichero pruebas.yml existe
# y se puede leer hoy; lo que no existe todavía es el job. No es un ImportError
# disfrazado de prueba de comportamiento.
#
# PyYAML es una dependencia DIRECTA y fijada en requirements-dev.txt, y aquí se importa
# DURO a propósito.
#
# Antes llegaba solo de forma transitiva y este módulo la pedía con
# `pytest.importorskip("yaml")`. Esa forma parece prudente y es lo contrario: si PyYAML
# faltara, estas pruebas —las que vigilan que el job de promoción no pierda su `needs`,
# su `environment`, su condición de evento ni el anclaje por SHA— se SALTARÍAN, la suite
# seguiría verde y nadie vería un rojo. Un gate que se apaga solo no es un gate; es un
# gate con un interruptor que cualquier cambio de dependencias puede pulsar.
#
# El detalle de por qué dependencias la traían está en requirements-dev.txt, medido. Lo
# que NO es cierto, y este fichero lo afirmaba antes, es que viniera solo de
# `uvicorn[standard]`.
#
# Con la importación dura, la ausencia de PyYAML es un error de recolección ruidoso, que
# es exactamente lo que debe ser: el entorno no reproduce el de CI y las pruebas no
# podrían decir la verdad sobre la puerta.

import ast
from pathlib import Path

import pytest
import yaml

RAIZ = Path(__file__).resolve().parents[1]
PRUEBAS_YML = RAIZ / ".github" / "workflows" / "pruebas.yml"

JOB = "promocion-produccion"
ENVIRONMENT_EXACTO = "contexto-production-promotion"
PROGRAMA = "scripts/promover_produccion.py"


@pytest.fixture(scope="module")
def workflow() -> dict:
    assert PRUEBAS_YML.is_file(), f"no existe {PRUEBAS_YML}"
    return yaml.safe_load(PRUEBAS_YML.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def texto_crudo() -> str:
    return PRUEBAS_YML.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def job(workflow) -> dict:
    jobs = workflow["jobs"]
    assert JOB in jobs, (
        f"el job de promoción '{JOB}' no está en pruebas.yml. "
        f"Jobs presentes: {sorted(jobs)}"
    )
    return jobs[JOB]


# ── (1) el job vive DENTRO de pruebas.yml, no en otro workflow ──────────────────
# C2 de F-02: con `workflow_run` en un fichero aparte, github.sha deja de ser el SHA
# que pasó el CI ("Last commit on default branch"), y R1 se rompe en silencio.


def test_el_job_vive_en_pruebas_yml(job):
    assert job is not None


def _todos_los_workflows() -> list:
    """GitHub ejecuta .yml Y .yaml. Mirar solo uno de los dos deja media puerta sin
    vigilar: bastaría añadir `promocion.yaml` para esquivar estas guardas."""
    directorio = RAIZ / ".github" / "workflows"
    return sorted(
        list(directorio.glob("*.yml")) + list(directorio.glob("*.yaml")),
        key=lambda p: p.name,
    )


def test_no_se_creo_otro_workflow_de_promocion():
    ficheros = [p.name for p in _todos_los_workflows()]
    assert ficheros == [
        "keepalive.yml",
        "pruebas.yml",
        "refresco-pois.yml",
        "vigia-salud.yml",
    ], f"apareció o desapareció un workflow: {ficheros}"


def test_ningun_workflow_usa_workflow_run(texto_crudo):
    for fichero in _todos_los_workflows():
        contenido = yaml.safe_load(fichero.read_text(encoding="utf-8"))
        # `on` es la clave YAML 1.1 que se interpreta como booleano True.
        disparadores = contenido.get("on", contenido.get(True, {})) or {}
        if isinstance(disparadores, dict):
            assert "workflow_run" not in disparadores, (
                f"{fichero.name} usa workflow_run; C2 de F-02 lo prohíbe porque "
                "github.sha dejaría de ser el SHA que pasó el CI"
            )


def test_ningun_otro_workflow_promueve(texto_crudo):
    # Una guarda por contenido, no por nombre de fichero: el endpoint de promoción no
    # puede aparecer en ningún workflow que no sea este job.
    for fichero in _todos_los_workflows():
        contenido = fichero.read_text(encoding="utf-8")
        if fichero.name == "pruebas.yml":
            continue
        assert "promote" not in contenido, f"{fichero.name} menciona una promoción"
        assert PROGRAMA not in contenido, f"{fichero.name} invoca el promotor"


# ── (2) needs contiene pytest y frontend ───────────────────────────────────────


def test_needs_contiene_ambos_jobs(job):
    needs = job.get("needs")
    assert needs is not None, "el job no declara needs"
    if isinstance(needs, str):
        needs = [needs]
    assert set(needs) == {"pytest", "frontend"}, (
        f"needs debe ser exactamente pytest y frontend; es {needs}"
    )


def test_los_jobs_referidos_por_needs_existen(workflow, job):
    needs = job["needs"]
    if isinstance(needs, str):
        needs = [needs]
    for nombre in needs:
        assert nombre in workflow["jobs"], (
            f"needs referencia '{nombre}', que no es un job de este fichero. "
            "needs solo resuelve job_id del MISMO workflow."
        )


# ── (3) Environment exacto ─────────────────────────────────────────────────────
# C3 de F-02: Environment NUEVO y propio. No reutilizar "Production" ni "Preview",
# que ya pertenecen a la integración de Vercel y tienen protection_rules VACÍAS.


def test_environment_exacto(job):
    entorno = job.get("environment")
    assert entorno is not None, "el job no declara environment: no hay aprobación humana"
    nombre = entorno if isinstance(entorno, str) else entorno.get("name")
    assert nombre == ENVIRONMENT_EXACTO, (
        f"environment debe ser exactamente '{ENVIRONMENT_EXACTO}'; es '{nombre}'"
    )


def test_no_reutiliza_los_environments_de_vercel(job):
    entorno = job.get("environment")
    nombre = entorno if isinstance(entorno, str) else (entorno or {}).get("name")
    assert nombre not in ("Production", "Preview"), (
        "reutilizar los Environments de la integración de Vercel deja el job con "
        "protection_rules vacías: aprobación humana inexistente"
    )


# ── (4) condición conjunta de evento, ref e intento ────────────────────────────


def test_condicion_exige_las_tres_cosas(job):
    condicion = job.get("if")
    assert condicion is not None, "el job no tiene condición: sería elegible siempre"
    texto = " ".join(str(condicion).split())
    assert "github.event_name == 'push'" in texto, texto
    assert "github.ref == 'refs/heads/main'" in texto, texto
    assert "github.run_attempt == 1" in texto, texto
    assert texto.count("&&") >= 2, f"las condiciones deben conjugarse con &&: {texto}"
    assert "||" not in texto, f"un || relajaría la condición: {texto}"


def test_la_condicion_no_cae_en_el_footgun_de_las_llaves(job):
    # F-02 §2: `if: ${{ github.run_attempt }} == 1` produce la cadena "2 == 1",
    # no vacía y por tanto VERDADERA. El job correría en el intento 2.
    texto = " ".join(str(job.get("if", "")).split())
    assert "}} ==" not in texto, (
        "las llaves cierran antes del operador: la condición se evalúa como cadena "
        f"no vacía y siempre es verdadera. Condición: {texto}"
    )


def test_conserva_el_exito_obligatorio_de_los_needs(job):
    # Si la condición incluyera una función de estado como always() o failure(), el
    # success() implícito desaparecería y el job correría con los needs en rojo.
    texto = " ".join(str(job.get("if", "")).split())
    for prohibida in ("always(", "failure(", "cancelled("):
        assert prohibida not in texto, (
            f"'{prohibida}' anula el success() implícito de needs: {texto}"
        )
    assert "success()" in texto, (
        "el éxito de los needs debe estar declarado explícitamente, no confiado al "
        "success() implícito, que desaparece si alguien añade una función de estado"
    )


# ── (5) dispatch, PR, otra rama y rerun quedan rechazados ──────────────────────


@pytest.mark.parametrize(
    "evento,ref,intento",
    [
        ("workflow_dispatch", "refs/heads/main", 1),
        ("pull_request", "refs/heads/main", 1),
        ("push", "refs/heads/otra", 1),
        ("push", "refs/heads/main", 2),
        ("schedule", "refs/heads/main", 1),
        ("push", "refs/tags/v1", 1),
    ],
)
def test_la_condicion_rechaza_los_vectores_conocidos(job, evento, ref, intento):
    condicion = " ".join(str(job["if"]).split())
    assert _evaluar(condicion, evento, ref, intento) is False, (
        f"la condición acepta evento={evento} ref={ref} intento={intento}"
    )


def test_la_condicion_acepta_el_unico_caso_nominal(job):
    condicion = " ".join(str(job["if"]).split())
    assert _evaluar(condicion, "push", "refs/heads/main", 1) is True


def _evaluar(condicion: str, evento: str, ref: str, intento: int) -> bool:
    """Evaluador mínimo de la expresión de GitHub Actions usada en este job.

    No pretende implementar el lenguaje entero. Cubre exactamente la forma que este
    job puede tener —conjunción de igualdades más success()— y falla ruidosamente
    ante cualquier otra, para no dar por buena una condición que no sabe evaluar.
    """
    texto = condicion.strip()
    if texto.startswith("${{") and texto.endswith("}}"):
        texto = texto[3:-2].strip()
    partes = [p.strip() for p in texto.split("&&")]
    contexto = {
        "github.event_name": evento,
        "github.ref": ref,
        # run_attempt es `string` en el contexto de GitHub; la comparación con un
        # número funciona porque Actions coerciona. Se modela como cadena a propósito.
        "github.run_attempt": str(intento),
    }
    resultado = True
    for parte in partes:
        if parte == "success()":
            continue  # los needs se modelan como verdes en este evaluador
        if "==" not in parte:
            raise AssertionError(f"el evaluador no entiende el término: {parte!r}")
        izquierda, derecha = (t.strip() for t in parte.split("==", 1))
        if izquierda not in contexto:
            raise AssertionError(f"el evaluador no conoce el contexto: {izquierda!r}")
        esperado = derecha.strip("'\"")
        resultado = resultado and (contexto[izquierda] == esperado)
    return resultado


# ── disparadores y jobs existentes intactos ────────────────────────────────────


def test_no_se_tocaron_los_disparadores(workflow):
    disparadores = workflow.get("on", workflow.get(True))
    assert set(disparadores) == {"push", "pull_request", "workflow_dispatch"}, (
        f"los disparadores cambiaron: {disparadores}"
    )
    assert disparadores["push"] == {"branches": ["main"]}
    assert disparadores["pull_request"] == {"branches": ["main"]}
    # workflow_dispatch SIGUE EXISTIENDO a propósito: el mandato prohíbe tocar los
    # disparadores. Por eso la barrera es de nivel de JOB y no del bloque `on`.
    assert "workflow_dispatch" in disparadores


def test_los_jobs_existentes_conservan_sus_pasos(workflow):
    assert [p.get("run") for p in workflow["jobs"]["pytest"]["steps"] if "run" in p][
        -1
    ] == "python -m pytest -q"
    frontend = [p.get("run") for p in workflow["jobs"]["frontend"]["steps"] if "run" in p]
    assert frontend == ["npm ci", "npm test", "npm run build"]


def test_ningun_job_ni_paso_puede_fallar_sin_consecuencias(workflow):
    """`continue-on-error` en `pytest` o `frontend` los volvería verdes al fallar.

    `needs` seguiría satisfecho y la promoción correría con el CI roto. Mirar solo
    las cadenas `run` de esos jobs no lo vería, así que se comprueba aparte.
    """
    for nombre, definicion in workflow["jobs"].items():
        assert definicion.get("continue-on-error") in (None, False), (
            f"el job {nombre} tiene continue-on-error: su fallo dejaría de bloquear"
        )
        for paso in definicion.get("steps", []):
            assert paso.get("continue-on-error") in (None, False), (
                f"un paso de {nombre} tiene continue-on-error"
            )


def test_los_jobs_del_gate_no_ganaron_condiciones(workflow):
    # Un `if:` en pytest o frontend podría saltarlos, y un job saltado satisface
    # `needs` sin haber probado nada.
    for nombre in ("pytest", "frontend"):
        assert "if" not in workflow["jobs"][nombre], (
            f"el job {nombre} ganó una condición: saltarlo satisface needs sin probar"
        )


# ── permisos, concurrencia, checkout y llamada al programa ─────────────────────


def test_permisos_minimos(job):
    permisos = job.get("permissions")
    assert permisos is not None, "el job no declara permissions: hereda los del token"
    assert permisos == {"contents": "read"}, f"permisos no mínimos: {permisos}"


def test_concurrencia_propia_sin_cancelacion(job):
    concurrencia = job.get("concurrency")
    assert concurrencia is not None, "el job no declara concurrency propia"
    assert concurrencia.get("cancel-in-progress") is False, (
        "cancel-in-progress debe ser false: cancelar a mitad de una promoción deja "
        "el resultado indeterminado y sin reconciliar"
    )
    grupo = str(concurrencia.get("group", ""))
    assert JOB in grupo, f"el grupo de concurrencia no es propio del job: {grupo}"
    # Un grupo que varía por ejecución NO serializa nada: cada run tendría el suyo y
    # dos promociones podrían solaparse. Solo se admiten claves estables por rama.
    for variable in ("github.sha", "github.run_id", "github.run_number", "github.run_attempt"):
        assert variable not in grupo, (
            f"el grupo de concurrencia incluye {variable}: sería único por ejecución "
            f"y no serializaría nada. Grupo: {grupo}"
        )
    assert "github.ref" in grupo, (
        f"el grupo debe fijarse por rama para serializar de verdad: {grupo}"
    )


def test_checkout_del_sha_exacto_sin_credenciales(job):
    pasos = job["steps"]
    checkout = [p for p in pasos if str(p.get("uses", "")).startswith("actions/checkout")]
    assert checkout, "el job no hace checkout"
    con = checkout[0].get("with", {})
    assert con.get("ref") == "${{ github.sha }}", (
        f"el checkout debe fijar el SHA exacto que aprobó el CI; es {con.get('ref')!r}"
    )
    assert con.get("persist-credentials") is False, (
        "persist-credentials debe ser false: el job no necesita escribir en git"
    )


def test_invoca_el_programa_del_repositorio_y_no_una_cadena_de_curl(job):
    ejecuciones = [str(p.get("run", "")) for p in job["steps"] if "run" in p]
    unido = "\n".join(ejecuciones)
    assert PROGRAMA in unido, (
        f"el job debe invocar {PROGRAMA}; sus run son {ejecuciones}"
    )
    assert "curl" not in unido, "la promoción no puede ser una cadena de curl"


def test_el_token_tiene_nombre_especifico(texto_crudo, job):
    assert "VERCEL_PROJECT_PROMOTION_TOKEN" in texto_crudo
    # Un nombre genérico invitaría a reutilizar un token de cuenta ya existente.
    assert "secrets.VERCEL_TOKEN" not in texto_crudo, (
        "nombre genérico de token: C4 de F-02 exige que el secreto sea exclusivo "
        "de este Environment"
    )


def test_no_se_asignan_valores_reales_de_identificadores(texto_crudo):
    # Esta unidad no crea el Environment ni sus variables. Solo las referencia.
    import re

    for variable in ("VERCEL_PROMOTION_PROJECT_ID", "VERCEL_PROMOTION_ALIAS"):
        asignaciones = re.findall(rf"{variable}:\s*(.+)", texto_crudo)
        for valor in asignaciones:
            assert valor.strip().startswith("${{"), (
                f"{variable} tiene un valor literal en el YAML: {valor!r}. "
                "Los identificadores deben quedar como referencia a vars del Environment."
            )


# ── (7) las acciones van ANCLADAS por SHA ──────────────────────────────────────
# `actions/checkout@v4` es un tag MOVIL: quien controle ese repositorio puede
# reapuntarlo y el runner ejecutaria codigo distinto sin que cambie una linea de este
# repositorio. Para `promocion-produccion` eso es la puerta entera: un humano aprueba
# mirando un SHA de ESTE repositorio y el job corre despues con un token de promocion de
# Vercel en el entorno. Si la accion puede cambiar entre la aprobacion y la ejecucion, lo
# aprobado no es lo que corre.
#
# DOS GUARDAS DISTINTAS, y cada una cae sola:
#   FORMA     toda referencia de CUALQUIER job de pruebas.yml es un SHA de 40 hex. Cubre
#             al job que aun no existe: uno nuevo sin anclar la rompe, y la de identidad
#             no lo veria porque solo gobierna los tres jobs del gate.
#   IDENTIDAD los tres jobs del gate usan EXACTAMENTE las acciones fijadas aqui abajo.
#             Cubre lo que la forma no ve: `impostor/checkout@<40 hex>` es una referencia
#             impecable a codigo de otro. Un SHA de 40 hex acredita inmutabilidad, no
#             procedencia.
# La lista blanca vive en la prueba y no en el YAML por lo mismo que
# `DOMINIOS_PRODUCTIVOS` vive en el fuente: cambiarla exige un commit revisado.

import re

SHA_DE_40 = re.compile(r"^[0-9a-f]{40}$")
JOBS_DEL_GATE = ("pytest", "frontend", JOB)

# repo -> (sha anclado, version legible). Fijadas el 2026-09-07 resolviendo el tag movil
# con `git ls-remote --tags`, y comprobadas contra el tag de version exacto.
ACCIONES_FIJADAS = {
    "actions/checkout": ("11d5960a326750d5838078e36cf38b85af677262", "v4.4.0"),
    "actions/setup-python": ("a26af69be951a213d495a4c3e4e4022e16d87065", "v5.6.0"),
    "actions/setup-node": ("49933ea5288caeca8642d1e84afbd3f7d6820020", "v4.4.0"),
}


def _pasos_con_uses(workflow, jobs=None) -> list:
    """(job, indice, uses) de cada paso que usa una accion.

    Por defecto recorre TODOS los jobs, no una lista fija: un job nuevo que alguien
    anadiera a pruebas.yml queda cubierto sin tener que tocar esta prueba.
    """
    fuera = []
    for nombre, cuerpo in workflow["jobs"].items():
        if jobs is not None and nombre not in jobs:
            continue
        for i, paso in enumerate(cuerpo.get("steps") or []):
            if "uses" in paso:
                fuera.append((nombre, i, str(paso["uses"])))
    return fuera


def test_hay_acciones_que_anclar(workflow):
    """Guarda del propio arnes: sin esto, las pruebas de abajo pasarian con cero pasos."""
    pasos = _pasos_con_uses(workflow)
    assert len(pasos) >= 6, f"se esperaban al menos 6 pasos con `uses`, hay {len(pasos)}"
    for nombre in JOBS_DEL_GATE:
        assert nombre in workflow["jobs"], f"falta el job {nombre}"
        assert any(j == nombre for j, _, _ in pasos), f"{nombre} no usa ninguna accion"


def test_toda_accion_de_pruebas_yml_va_anclada_por_sha_de_40(workflow):
    """FORMA, sobre TODOS los jobs. Es la guarda que cubre al job que aun no existe."""
    for job_nombre, indice, uses in _pasos_con_uses(workflow):
        assert "@" in uses, f"{job_nombre}[{indice}]: `uses` sin referencia: {uses!r}"
        _repo, _, referencia = uses.partition("@")
        assert SHA_DE_40.match(referencia), (
            f"{job_nombre}[{indice}] usa {uses!r}. Una referencia que no es un SHA de 40 "
            "hex es movil: el codigo que corre puede cambiar sin cambiar este fichero."
        )


def test_los_tres_jobs_del_gate_solo_usan_las_acciones_FIJADAS(workflow):
    """IDENTIDAD. Un SHA de 40 hex acredita inmutabilidad, no procedencia.

    `impostor/checkout@11d5960a...` pasa la prueba de forma sin despeinarse. Lo unico que
    ata el codigo a quien se pretende ejecutar es fijar aqui el par (repositorio, SHA).
    """
    for job_nombre, indice, uses in _pasos_con_uses(workflow, JOBS_DEL_GATE):
        repo, _, referencia = uses.partition("@")
        assert repo in ACCIONES_FIJADAS, (
            f"{job_nombre}[{indice}] usa una accion NO fijada: {repo!r}. "
            f"Fijadas: {sorted(ACCIONES_FIJADAS)}"
        )
        esperado, version = ACCIONES_FIJADAS[repo]
        assert referencia == esperado, (
            f"{job_nombre}[{indice}]: {repo} deberia ir anclada a {esperado} ({version}) "
            f"y va a {referencia!r}"
        )


def test_se_usan_TODAS_las_acciones_fijadas_y_ninguna_de_sobra(workflow):
    """Sin esto, `ACCIONES_FIJADAS` podria acumular entradas muertas que nadie usa y la
    prueba de identidad seguiria verde: una lista blanca que crece sin que se note."""
    usadas = {u.partition("@")[0] for _j, _i, u in _pasos_con_uses(workflow, JOBS_DEL_GATE)}
    assert usadas == set(ACCIONES_FIJADAS), (
        f"usadas={sorted(usadas)} fijadas={sorted(ACCIONES_FIJADAS)}"
    )


# La forma idiomatica `- uses: x@v4` mete el `uses` en el mismo renglon que el guion del
# elemento. Una expresion anclada a `^\s*uses:` no la ve, y ese fue exactamente el
# agujero de la primera version de estas pruebas: un job nuevo escrito asi pasaba entero.
LINEA_USES = re.compile(r"^\s*-?\s*uses:\s*(\S+)")


@pytest.mark.parametrize(
    "linea,esperado",
    [
        ("        uses: actions/checkout@abc", "actions/checkout@abc"),
        ("      - uses: actions/checkout@abc", "actions/checkout@abc"),
        ("      -   uses: actions/checkout@abc", "actions/checkout@abc"),
        ("- uses: actions/checkout@abc", "actions/checkout@abc"),
    ],
)
def test_el_barrido_reconoce_las_DOS_formas_de_escribir_uses(linea, esperado):
    """Ancla la expresion regular del barrido, que si no queda sin probar.

    Hoy pruebas.yml no usa la forma `- uses:` en ningun sitio, asi que volver la regex
    ciega a ella NO rompe ninguna otra prueba: la mutacion nacia inerte. Y esa ceguera
    era real —fue el agujero de la primera version— porque el dia que alguien anada un
    job escrito en la forma idiomatica, el barrido lo pasaria por alto entero.
    """
    m = LINEA_USES.match(linea)
    assert m is not None, f"el barrido no reconoce {linea!r}"
    assert m.group(1) == esperado


@pytest.mark.parametrize(
    "linea",
    [
        "# El SHA es la unica referencia inmutable que admite `uses:`",
        "        # uses: actions/checkout@abc",
        "        with:",
        "          ref: ${{ github.sha }}",
    ],
)
def test_el_barrido_no_confunde_comentarios_ni_otras_claves(linea):
    """El contrapunto: un barrido que casa de mas convertiria el propio comentario
    explicativo del YAML en un fallo, y nadie confiaria en el."""
    assert LINEA_USES.match(linea) is None, f"el barrido casa de mas con {linea!r}"


def test_cada_ancla_conserva_la_version_legible_en_un_comentario(texto_crudo):
    """El SHA es inmutable pero ilegible. Sin la version nadie sabe que esta subiendo.

    Va sobre el texto crudo y no sobre el YAML cargado porque `yaml.safe_load` descarta
    los comentarios: la garantia solo existe en el fichero.
    """
    lineas = [
        (n, l) for n, l in enumerate(texto_crudo.splitlines(), 1)
        if LINEA_USES.match(l)
    ]
    assert lineas, "no hay ninguna linea `uses:` en pruebas.yml"
    for numero, linea in lineas:
        assert "#" in linea, (
            f"pruebas.yml:{numero} ancla sin comentario de version: {linea.strip()!r}"
        )
        comentario = linea.split("#", 1)[1].strip()
        assert re.match(r"^v\d+\.\d+\.\d+$", comentario), (
            f"pruebas.yml:{numero}: el comentario debe ser la version exacta "
            f"(por ejemplo `# v4.4.0`); es {comentario!r}"
        )


def test_el_texto_crudo_de_pruebas_yml_no_deja_NINGUNA_referencia_movil():
    """Barrido de TEXTO, complementario al del YAML cargado: atrapa un `uses` que
    `safe_load` no exponga como paso de un job.

    ALCANCE, medido y dicho de frente: cubre `pruebas.yml` y nada mas. Hoy el unico otro
    workflow del repositorio con acciones es `refresco-pois.yml`, que conserva dos tags
    moviles; `keepalive.yml` y `vigia-salud.yml` no usan ninguna. Anclar ese otro fichero
    no lo autoriza esta unidad, asi que se deja dicho en vez de sugerido.
    """
    yml = RAIZ / ".github" / "workflows" / "pruebas.yml"
    moviles = []
    for numero, linea in enumerate(yml.read_text(encoding="utf-8").splitlines(), 1):
        m = LINEA_USES.match(linea)
        if m and not SHA_DE_40.match(m.group(1).partition("@")[2]):
            moviles.append(f"pruebas.yml:{numero} {m.group(1)}")
    assert not moviles, "quedan referencias moviles: " + ", ".join(moviles)


# ── (8) el gate no se puede volver a apagar solo ───────────────────────────────
# `pytest.importorskip("yaml")` convierte la falta de una dependencia en un SALTO, no en
# un fallo. Medido en aislamiento, con `yaml` bloqueado: con importacion dura pytest da
# «ERROR ... Interrupted: 1 error during collection»; con `importorskip` da «1 skipped»,
# en verde. Aplicado a las pruebas que vigilan la puerta de produccion, eso es un gate
# con interruptor.
#
# DE DONDE VENIA PyYAML, con la medicion delante y no de oido: NO llegaba solo por el
# extra `standard` de uvicorn. `langchain-core==0.3.63`, fijado en requirements.txt,
# declara `PyYAML>=5.3` SIN extra, es decir de forma incondicional; y ademas lo declaran
# con extra fastapi[all], starlette[full], pydantic-settings[yaml] y uvicorn[standard].
# O sea que el riesgo real nunca fue «se cae el extra y desaparece PyYAML»: era que la
# suite dependiera de una dependencia que NADIE en este repositorio declara, y que
# cualquier desaparicion futura se tradujera en un SALTO MUDO en vez de en un rojo. Lo
# primero se arregla declarandola; lo segundo, importandola duro.
#
# DOS GUARDAS, y hacen cosas distintas:
#   POSITIVA  los ficheros que cargan el YAML tienen que importarlo DURO y no pueden
#             llevar ningun mecanismo de salto. Es la fuerte: no persigue deletreos,
#             exige la forma correcta.
#   NEGATIVA  ningun fichero de tests/ llama a `importorskip` para YAML, resolviendo
#             tambien los alias. Cubre el resto del arbol, donde no se puede exigir una
#             importacion que esos ficheros no necesitan.

MODULOS_QUE_NO_SE_SALTAN = ("yaml",)
REQUISITOS_DEV = RAIZ / "requirements-dev.txt"

# Los ficheros que CARGAN el YAML del workflow. Si algun dia hay mas, se anaden aqui.
FICHEROS_QUE_CARGAN_EL_YAML = (
    "test_promocion_workflow.py",
    "test_promocion_produccion.py",
)


def _ficheros_de_prueba() -> list:
    return sorted((RAIZ / "tests").rglob("*.py"))


def _nombres_de_importorskip(arbol: ast.AST) -> set:
    """Nombres locales que apuntan a `importorskip`, incluidos los alias.

    `from pytest import importorskip as saltar` deja el detector ciego si solo se busca
    el deletreo original. Esto lo resuelve.
    """
    nombres = {"importorskip"}
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom) and nodo.module == "pytest":
            for alias in nodo.names:
                if alias.name == "importorskip" and alias.asname:
                    nombres.add(alias.asname)
    return nombres


def _llamadas_a_importorskip(arbol: ast.AST) -> list:
    """(linea, primer argumento) de cada LLAMADA a importorskip del arbol.

    Mira el AST y no el texto a proposito. Un `grep` daria un falso positivo con el
    comentario de la cabecera de este mismo fichero, que nombra la forma para explicar
    por que se retiro. Reconoce la llamada con punto, sin punto, con alias, por
    `getattr`, con el argumento por nombre, y anidada en una funcion o en una clase.
    """
    nombres = _nombres_de_importorskip(arbol)
    fuera = []
    for nodo in ast.walk(arbol):
        if not isinstance(nodo, ast.Call):
            continue
        funcion = nodo.func
        if isinstance(funcion, ast.Attribute):
            nombre = funcion.attr
        elif isinstance(funcion, ast.Name):
            nombre = funcion.id
        elif isinstance(funcion, ast.Call) and isinstance(funcion.func, ast.Name) \
                and funcion.func.id == "getattr" and len(funcion.args) >= 2 \
                and isinstance(funcion.args[1], ast.Constant):
            # `getattr(pytest, "importorskip")("yaml")`
            nombre = funcion.args[1].value
        else:
            nombre = None
        if nombre not in nombres:
            continue
        argumentos = list(nodo.args) + [
            k.value for k in nodo.keywords if k.arg in (None, "modname")
        ]
        primero = argumentos[0] if argumentos else None
        valor = primero.value if isinstance(primero, ast.Constant) else None
        fuera.append((nodo.lineno, valor))
    return fuera


def ofensas_de_salto(fuente: str, etiqueta: str = "<memoria>") -> list:
    """LA REGLA que decide que es una ofensa, separada para poder MEDIRLA.

    Antes vivia embebida en el bucle de la prueba, y como hoy no queda ni una llamada en
    el arbol ese bucle corre VACIO: neutralizar la condicion o vaciar la lista negra
    dejaba la suite entera en verde. Una regla que solo se ejerce cuando alguien la
    infringe no esta probada; se prueba dandole fuentes sinteticas.
    """
    arbol = ast.parse(fuente, filename=etiqueta)
    ofensas = []
    for linea, modulo in _llamadas_a_importorskip(arbol):
        if modulo is None or str(modulo).split(".")[0] in MODULOS_QUE_NO_SE_SALTAN:
            ofensas.append(f"{etiqueta}:{linea} -> {modulo!r}")
    return ofensas


def _importa_yaml_duro_a_nivel_de_modulo(arbol: ast.Module) -> bool:
    """`import yaml` como sentencia DIRECTA del modulo.

    Directa importa: dentro de un `try/except ImportError` seria un salto disfrazado, y
    ese nodo no es hijo de `Module.body`.
    """
    return any(
        isinstance(nodo, ast.Import) and any(a.name == "yaml" for a in nodo.names)
        for nodo in arbol.body
    )


def _mecanismos_de_salto(arbol: ast.AST) -> list:
    """Saltos que NO son `importorskip` pero apagan el gate igual.

    Son las dos formas idiomaticas que escribe cualquiera que crea estar protegiendo una
    prueba de una dependencia opcional: `pytest.skip(..., allow_module_level=True)` tras
    un `find_spec`, y `skipif` sobre un `yaml` que quedo en None.
    """
    fuera = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Call):
            funcion = nodo.func
            nombre = getattr(funcion, "attr", None) or getattr(funcion, "id", None)
            if nombre == "skip" and any(
                k.arg == "allow_module_level" for k in nodo.keywords
            ):
                fuera.append(f"linea {nodo.lineno}: skip a nivel de modulo")
            if nombre == "skipif":
                fuera.append(f"linea {nodo.lineno}: marca skipif")
        if isinstance(nodo, ast.Attribute) and nodo.attr == "skipif":
            fuera.append(f"linea {nodo.lineno}: marca skipif")
    return sorted(set(fuera))


# ── (8a) la guarda POSITIVA ────────────────────────────────────────────────────


@pytest.mark.parametrize("nombre", FICHEROS_QUE_CARGAN_EL_YAML)
def test_los_ficheros_que_cargan_el_yaml_lo_importan_DURO(nombre):
    """La guarda fuerte: exige la forma correcta en vez de perseguir deletreos.

    Cubre de una vez el alias del import, el `getattr`, el `find_spec` con salto a nivel
    de modulo y el `try/except ImportError` con `skipif`: las cuatro sustituyen o
    envuelven el `import yaml`, y ninguna deja una sentencia `import yaml` directa.

    Se comprueba sobre el FUENTE y no sobre el modulo importado a proposito: si el otro
    fichero se saltara a nivel de modulo, sus propias pruebas no correrian y esta si.
    """
    fichero = RAIZ / "tests" / nombre
    assert fichero.is_file(), f"no existe {fichero}"
    arbol = ast.parse(fichero.read_text(encoding="utf-8"), filename=str(fichero))
    assert _importa_yaml_duro_a_nivel_de_modulo(arbol), (
        f"{nombre} tiene que hacer `import yaml` como sentencia directa del modulo. "
        "Envolverlo en un try/except o sustituirlo por un salto apaga el gate en silencio."
    )
    saltos = _mecanismos_de_salto(arbol)
    assert not saltos, (
        f"{nombre} lleva un mecanismo de salto: {saltos}. Las pruebas que vigilan la "
        "puerta de produccion no pueden ser condicionales."
    )
    assert not ofensas_de_salto(fichero.read_text(encoding="utf-8"), nombre)


def test_el_yaml_importado_es_el_de_verdad():
    assert yaml.safe_load("a: 1") == {"a": 1}
    assert hasattr(yaml, "__version__")


# Las dos reglas de la guarda positiva se miden igual que la negativa: con fuentes
# sinteticas. Ejercitarlas solo contra los dos ficheros REALES —que estan limpios— las
# dejaba sin medir, y borrarlas no rompia nada. Es el mismo patron que ya habia dejado
# muda la condicion de ofensa.

FUENTES_CON_IMPORT_DURO = {
    "import directo": "import yaml\n",
    "import directo con mas cosas": "import os\nimport yaml\nimport sys\n",
    "varios en la misma linea": "import os, yaml\n",
}

FUENTES_SIN_IMPORT_DURO = {
    "dentro de un try": "try:\n    import yaml\nexcept ImportError:\n    yaml = None\n",
    "dentro de una funcion": "def cargar():\n    import yaml\n    return yaml\n",
    "dentro de un if": "import sys\nif sys.version_info:\n    import yaml\n",
    "solo from yaml import": "from yaml import safe_load\n",
    "no lo importa": "import os\n",
}

FUENTES_CON_SALTO = {
    "skip a nivel de modulo": (
        "import importlib.util, pytest\n"
        'if importlib.util.find_spec("yaml") is None:\n'
        '    pytest.skip("sin yaml", allow_module_level=True)\n'
        "import yaml\n"
    ),
    "marca skipif": (
        "import pytest\ntry:\n    import yaml\nexcept ImportError:\n    yaml = None\n"
        '@pytest.mark.skipif(yaml is None, reason="sin yaml")\n'
        "def test_x():\n    assert yaml\n"
    ),
    "skipif importado suelto": (
        "import pytest\nfrom pytest.mark import skipif\nimport yaml\n"
        '@skipif(False, reason="x")\ndef test_x():\n    assert yaml\n'
    ),
}

FUENTES_SIN_SALTO = {
    "solo el import": "import yaml\n",
    "un skip normal dentro de una prueba": (
        "import pytest\nimport yaml\n"
        'def test_x():\n    pytest.skip("por otra razon")\n'
    ),
}


@pytest.mark.parametrize("etiqueta", sorted(FUENTES_CON_IMPORT_DURO))
def test_la_regla_del_import_duro_ACEPTA_lo_correcto(etiqueta):
    arbol = ast.parse(FUENTES_CON_IMPORT_DURO[etiqueta])
    assert _importa_yaml_duro_a_nivel_de_modulo(arbol), etiqueta


@pytest.mark.parametrize("etiqueta", sorted(FUENTES_SIN_IMPORT_DURO))
def test_la_regla_del_import_duro_RECHAZA_lo_que_no_lo_es(etiqueta):
    """`try/except ImportError` es la forma mas comun de disfrazar un salto, y su nodo
    `Import` NO es hijo directo de `Module.body`. De ahi que la regla mire `arbol.body` y
    no `ast.walk`: con `walk` aceptaria el import envuelto y la guarda seria decorativa."""
    arbol = ast.parse(FUENTES_SIN_IMPORT_DURO[etiqueta])
    assert not _importa_yaml_duro_a_nivel_de_modulo(arbol), etiqueta


@pytest.mark.parametrize("etiqueta", sorted(FUENTES_CON_SALTO))
def test_la_regla_de_los_saltos_los_ENCUENTRA(etiqueta):
    encontrados = _mecanismos_de_salto(ast.parse(FUENTES_CON_SALTO[etiqueta]))
    assert encontrados, f"no ve el salto de «{etiqueta}»"


@pytest.mark.parametrize("etiqueta", sorted(FUENTES_SIN_SALTO))
def test_la_regla_de_los_saltos_NO_acusa_de_mas(etiqueta):
    """Un `pytest.skip` dentro de una prueba, por una razon que no es la dependencia, es
    legitimo: lo que se prohibe es el salto a NIVEL DE MODULO y la marca condicional."""
    encontrados = _mecanismos_de_salto(ast.parse(FUENTES_SIN_SALTO[etiqueta]))
    assert not encontrados, f"acusa de mas en «{etiqueta}»: {encontrados}"


# ── (8b) la guarda NEGATIVA, y su regla MEDIDA ─────────────────────────────────

FUENTES_QUE_SON_OFENSA = {
    "con punto": 'import pytest\nyaml = pytest.importorskip("yaml")\n',
    "sin punto": 'from pytest import importorskip\nyaml = importorskip("yaml")\n',
    "con alias": 'from pytest import importorskip as saltar\nyaml = saltar("yaml")\n',
    "por getattr": 'import pytest\nyaml = getattr(pytest, "importorskip")("yaml")\n',
    "argumento por nombre": 'import pytest\nyaml = pytest.importorskip(modname="yaml")\n',
    "submodulo": 'import pytest\nc = pytest.importorskip("yaml.cyaml")\n',
    "anidada en funcion": 'import pytest\ndef f():\n    return pytest.importorskip("yaml")\n',
    "dentro de una clase": 'import pytest\nclass T:\n    y = pytest.importorskip("yaml")\n',
    "argumento no constante": 'import pytest\nm = "ya" + "ml"\ny = pytest.importorskip(m)\n',
}

FUENTES_QUE_NO_SON_OFENSA = {
    "importacion dura": "import yaml\n",
    "otro modulo": 'import pytest\nd = pytest.importorskip("duckdb")\n',
    "otro modulo por nombre": 'import pytest\nd = pytest.importorskip(modname="duckdb")\n',
    "solo una cadena": 'x = "pytest.importorskip(\'yaml\')"\n',
    "solo un comentario": '# pytest.importorskip("yaml")\nimport yaml\n',
    "una funcion que se llama parecido": 'import otro\notro.importorskip_de_mentira("yaml")\n',
}


@pytest.mark.parametrize("etiqueta", sorted(FUENTES_QUE_SON_OFENSA))
def test_la_regla_ACUSA_cada_forma_de_saltarse_yaml(etiqueta):
    """Mide la mitad que ACUSA. Sin estas fuentes sinteticas la regla nunca se ejerce,
    porque hoy no queda ni una llamada en el arbol: el bucle de la guarda negativa corre
    vacio y cualquier mutacion del filtro es indistinguible del original."""
    ofensas = ofensas_de_salto(FUENTES_QUE_SON_OFENSA[etiqueta], etiqueta)
    assert ofensas, f"la regla no acusa la forma «{etiqueta}»"


@pytest.mark.parametrize("etiqueta", sorted(FUENTES_QUE_NO_SON_OFENSA))
def test_la_regla_NO_acusa_lo_que_es_legitimo(etiqueta):
    """Contrapunto: una regla que acusa de mas se desactiva sola en cuanto estorba."""
    ofensas = ofensas_de_salto(FUENTES_QUE_NO_SON_OFENSA[etiqueta], etiqueta)
    assert not ofensas, f"la regla acusa de mas en «{etiqueta}»: {ofensas}"


def test_el_barrido_cubre_TODO_lo_que_pytest_recolectaria():
    """Ata el barrido a un calculo INDEPENDIENTE del que hace la funcion.

    Sin esto bastaba con recortar `_ficheros_de_prueba` —a una lista vacia, o a los dos
    ficheros que ya sabemos limpios— para esconder un `importorskip` en cualquier otro
    sitio de tests/ sin un solo rojo. Medido: las dos formas dejaban la suite en verde.
    """
    esperados = {p.resolve() for p in (RAIZ / "tests").rglob("*.py")}
    obtenidos = {p.resolve() for p in _ficheros_de_prueba()}
    assert obtenidos == esperados, (
        f"el barrido no cubre lo mismo que pytest recolectaria. "
        f"Le faltan: {sorted(str(p) for p in esperados - obtenidos)}"
    )
    assert len(obtenidos) >= 2, f"el barrido no encuentra ficheros: {obtenidos}"
    nombres = {p.name for p in obtenidos}
    for obligatorio in FICHEROS_QUE_CARGAN_EL_YAML:
        assert obligatorio in nombres, f"el barrido no incluye {obligatorio}"
    assert Path(__file__).name in nombres, "el barrido tiene que incluirse a si mismo"


def test_ninguna_prueba_se_salta_YAML_con_importorskip():
    """La guarda negativa sobre el arbol real.

    NO se detecta a si misma: busca LLAMADAS, y aqui `importorskip` solo aparece en
    cadenas y comentarios. Cubre `importorskip` en todos sus deletreos; los saltos que
    no son `importorskip` los cubre la guarda positiva, y solo en los dos ficheros que
    cargan el YAML.
    """
    ofensas = []
    for fichero in _ficheros_de_prueba():
        ofensas += ofensas_de_salto(
            fichero.read_text(encoding="utf-8"),
            fichero.relative_to(RAIZ).as_posix(),
        )
    assert not ofensas, (
        "vuelve a haber pruebas que se saltan YAML en vez de exigirlo. PyYAML esta "
        "fijado en requirements-dev.txt: si falta, el entorno no reproduce el de CI y "
        "estas pruebas no dirian la verdad sobre la puerta. " + "; ".join(ofensas)
    )


# ── (8c) la dependencia declarada y fijada ─────────────────────────────────────


def _normalizar_nombre(crudo: str) -> str:
    """Normalizacion de nombres de proyecto de PEP 503.

    `PyYAML`, `pyyaml` y `PYYAML` son el MISMO paquete; `Py-YAML` es OTRO, porque el
    guion es significativo. La version anterior de esta prueba borraba los guiones y
    aceptaba `Py-YAML==6.0.3`, que instalaria cualquier cosa menos PyYAML.
    """
    return re.sub(r"[-_.]+", "-", crudo).lower()


def test_pyyaml_esta_declarado_y_FIJADO_en_requirements_dev():
    """Sin esto, la declaracion se puede borrar y volveriamos a depender de que otros
    paquetes sigan arrastrando PyYAML de rebote, que es de donde venia el problema."""
    assert REQUISITOS_DEV.is_file(), f"no existe {REQUISITOS_DEV}"
    fijaciones = []
    for cruda in REQUISITOS_DEV.read_text(encoding="utf-8").splitlines():
        linea = cruda.split("#")[0].strip()
        if "==" not in linea:
            continue
        nombre, _, version = linea.partition("==")
        if _normalizar_nombre(nombre.strip()) == "pyyaml":
            fijaciones.append(version.strip())
    assert len(fijaciones) == 1, (
        f"se esperaba exactamente una fijacion de PyYAML en requirements-dev.txt; "
        f"hay {fijaciones}"
    )
    version = fijaciones[0]
    assert re.match(r"^\d+\.\d+(\.\d+)?$", version), (
        f"la version de PyYAML debe ir fijada a una version exacta; es {version!r}"
    )
    assert yaml.__version__ == version, (
        f"el entorno tiene PyYAML {yaml.__version__} y requirements-dev.txt fija "
        f"{version}: el entorno no reproduce el de CI"
    )


@pytest.mark.parametrize(
    "escrito,vale",
    [
        ("PyYAML==6.0.3", True),
        ("pyyaml==6.0.3", True),
        ("pyyaml == 6.0.3", True),
        ("PyYAML==6.0.3  # con comentario", True),
        ("Py-YAML==6.0.3", False),
        ("py_yaml==6.0.3", False),
        ("pyyaml-extra==6.0.3", False),
    ],
)
def test_la_normalizacion_del_nombre_sigue_a_PEP_503(escrito, vale):
    """La normalizacion tiene su propia prueba porque su primera version era falsa en
    los dos sentidos: aceptaba `Py-YAML==6.0.3`, que es otro paquete, y rechazaba
    `pyyaml == 6.0.3`, que es exactamente el mismo."""
    linea = escrito.split("#")[0].strip()
    nombre = linea.partition("==")[0].strip()
    assert (_normalizar_nombre(nombre) == "pyyaml") is vale, escrito
