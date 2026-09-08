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
# PyYAML NO está en requirements-dev.txt, pero SÍ está garantizado en CI: requirements.txt
# fija `uvicorn[standard]==0.32.1`, y los metadatos de uvicorn declaran
# `pyyaml>=5.1; extra == 'standard'`. Verificado con importlib.metadata sobre el venv del
# repositorio, no supuesto. Si algún día se quita el extra `standard`, estas pruebas se
# caen en recolección y hay que declarar PyYAML explícitamente.

from pathlib import Path

import pytest

yaml = pytest.importorskip(
    "yaml",
    reason=(
        "PyYAML llega por uvicorn[standard]; si falta, el entorno no reproduce el de CI "
        "y estas pruebas no dirían la verdad sobre el gate."
    ),
)

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
