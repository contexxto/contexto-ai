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
