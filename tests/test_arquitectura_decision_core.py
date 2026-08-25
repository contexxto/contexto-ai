"""F2 · Gate C — la dirección de dependencias del Decision Core, congelada por AST.

POR QUÉ AST Y NO GREP. Dos veces en este proyecto un `grep` dio por bueno un cambio que
no estaba hecho: en F1 buscando la ausencia de un nombre que aparecía legítimamente en un
docstring, y en F2/E2.1 con un import partido en dos líneas que el patrón textual no
alcanzó. La pregunta "¿existe este import?" es estructural; se responde sobre el árbol.

──────────────────────────────────────────────────────────────────────────────────
EL CRITERIO C, TAL COMO QUEDÓ REDACTADO
──────────────────────────────────────────────────────────────────────────────────

El criterio original del Gate F2 decía «`agent/` no importa `routers/`». La
caracterización (commit A) demostró que eso era **más amplio que el alcance real de F2**:
había cinco imports `agent → routers` y solo uno pertenecía al carril de decisión. Los
otros cuatro son de CRM y handoff, superficies que F2 tiene prohibido tocar.

Cumplirlo literalmente habría convertido una extracción controlada en una refactorización
transversal. El criterio quedó **formalmente sustituido** —no "interpretado con
flexibilidad"— por:

    C1  app/decision no importa fastapi ni app.routers
    C2  el carril de decisión de agent no depende de app.routers
    C3  graph.py no importa decisión desde routers.chat
    C4  ningún import agent → routers nuevo respecto al baseline
    C5  los preexistentes quedan inventariados como deuda, no como resueltos

Al cerrar F2 se podrá afirmar «el Decision Core ya tiene la dirección de dependencias
correcta», y **no** «agent/ está desacoplado de routers/», porque lo segundo seguiría
siendo falso.

──────────────────────────────────────────────────────────────────────────────────
ARCH-DEBT-F2-01
──────────────────────────────────────────────────────────────────────────────────

Imports preexistentes de `app.agent` hacia `app.routers` que NO pertenecen al carril de
decisión:

    tools.py      → registrar_handoff                          (handoff)
    crm_tools.py  → _activos_del_corredor, _funnel_y_orden,
                    _leads_del_corredor, _reparto_del_corredor (CRM)
    crm_tools.py  → _leads_del_corredor                        (CRM)
    crm_tools.py  → transcript_de_sesion, ensure_handoff_tables (handoff)

Y fuera de `agent/`, misma familia de problema:

    reenganche_cron.py → routers.chat

**No los introdujo F2. No los remedia F2.** Deben desaparecer antes de poder declarar
completa la frontera de dependencias global. No se les asigna F3/F4/F5 artificialmente
solo por ponerles fecha: es deuda transversal y se resuelve cuando haya una tarea
explícita de separación CRM/handoff, o cuando uno de esos módulos entre en una fase donde
moverlo sea natural.

**Grandfathering EXACTO, no genérico.** Se toleran esos cuatro imports concretos. Si
aparece un quinto, este test falla. Esa es toda la diferencia entre una excepción
registrada y un precedente.
"""

import ast
import pathlib

import pytest

RAIZ = pathlib.Path(__file__).resolve().parent.parent


def _imports_de(ruta: pathlib.Path) -> set[tuple[str, str]]:
    """{(módulo, nombre)} de todo lo que el fichero importa. Por AST."""
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    out: set[tuple[str, str]] = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.ImportFrom) and n.module:
            for a in n.names:
                out.add((n.module, a.name))
        elif isinstance(n, ast.Import):
            for a in n.names:
                out.add((a.name, ""))
    return out


def _modulos_py(carpeta: str):
    for py in sorted((RAIZ / carpeta).rglob("*.py")):
        if "__pycache__" not in str(py):
            yield py


# El baseline exacto, por (fichero, módulo importado). Los NOMBRES importados no se
# congelan: lo que se tolera es la dependencia, no su superficie concreta.
GRANDFATHERED: set[tuple[str, str]] = {
    ("app/agent/tools.py", "app.routers.chat"),
    ("app/agent/crm_tools.py", "app.routers.assets"),
    ("app/agent/crm_tools.py", "app.routers.chat"),
}

# Deuda equivalente fuera de agent/. Se registra para que no desaparezca del radar.
DEUDA_FUERA_DE_AGENT: set[tuple[str, str]] = {
    ("app/reenganche_cron.py", "app.routers.chat"),
}


# ── C1 · el Decision Core no sabe de HTTP ────────────────────────────────────────


@pytest.mark.parametrize("py", list(_modulos_py("app/decision")), ids=lambda p: p.name)
def test_C1_el_decision_core_no_importa_fastapi_ni_routers(py):
    """Si esto falla, el core dejó de poder ejecutarse sin levantar una request — que es
    justo lo que el Gate F2 pide demostrar."""
    modulos = {m for m, _ in _imports_de(py)}
    prohibidos = {m for m in modulos if m == "fastapi" or m.startswith("fastapi.")
                  or m == "app.routers" or m.startswith("app.routers.")}
    assert not prohibidos, f"{py.name} importa {sorted(prohibidos)}"


def test_C1b_el_decision_core_se_importa_sin_fastapi_cargado():
    """No basta con no escribir el import: se comprueba que el módulo carga."""
    import importlib

    mod = importlib.import_module("app.decision.assembler")
    assert hasattr(mod, "construir_panel")


# ── C2/C3 · el carril de decisión no pasa por el router ──────────────────────────


def test_C3_graph_no_importa_decision_desde_routers():
    """`graph.py` es el consumidor del carril de decisión dentro de agent/."""
    imports = _imports_de(RAIZ / "app/agent/graph.py")
    desde_routers = {(m, n) for m, n in imports if m.startswith("app.routers")}
    assert not desde_routers, (
        f"graph.py volvió a importar de routers: {sorted(desde_routers)}. El carril de "
        "decisión va a app.decision."
    )


def test_C2_el_carril_de_decision_no_depende_de_routers():
    """Cierre transitivo del lado de decisión: graph → decision → …, sin routers."""
    pendientes = ["app/agent/graph.py"]
    vistos: set[str] = set()
    while pendientes:
        rel = pendientes.pop()
        if rel in vistos:
            continue
        vistos.add(rel)
        for modulo, _ in _imports_de(RAIZ / rel):
            if modulo.startswith("app.decision"):
                siguiente = modulo.replace(".", "/") + ".py"
                if (RAIZ / siguiente).exists():
                    pendientes.append(siguiente)
                    imports = _imports_de(RAIZ / siguiente)
                    malos = {m for m, _ in imports if m.startswith("app.routers")}
                    assert not malos, f"{siguiente} depende de {sorted(malos)}"


# ── C4/C5 · grandfathering exacto ────────────────────────────────────────────────


def test_C4_ningun_import_nuevo_de_agent_hacia_routers():
    """El corazón de la excepción: se toleran los cuatro preexistentes y ni uno más.

    Si esto falla porque añadiste un import legítimo, la respuesta NO es ampliar la lista
    sin pensarlo: es preguntarse si esa dependencia debía existir, y si la respuesta es
    sí, registrarla como deuda nueva con su motivo.
    """
    encontrados: set[tuple[str, str]] = set()
    for py in _modulos_py("app/agent"):
        rel = py.relative_to(RAIZ).as_posix()
        for modulo, _ in _imports_de(py):
            if modulo.startswith("app.routers"):
                encontrados.add((rel, modulo))

    nuevos = encontrados - GRANDFATHERED
    assert not nuevos, (
        f"import agent → routers NUEVO respecto al baseline de F2: {sorted(nuevos)}.\n"
        "Ver ARCH-DEBT-F2-01 en la cabecera de este archivo."
    )


def test_C5_los_grandfathered_siguen_ahi_y_no_se_declaran_resueltos():
    """La otra mitad, y la que evita el autoengaño: si alguno desapareciera, hay que
    ACTUALIZAR la deuda —no dejar que el test siga afirmando que existe—. Y mientras
    existan, F2 no puede decir que desacopló agent/ de routers/."""
    encontrados: set[tuple[str, str]] = set()
    for py in _modulos_py("app/agent"):
        rel = py.relative_to(RAIZ).as_posix()
        for modulo, _ in _imports_de(py):
            if modulo.startswith("app.routers"):
                encontrados.add((rel, modulo))

    assert encontrados == GRANDFATHERED, (
        "el inventario de ARCH-DEBT-F2-01 dejó de coincidir con la realidad.\n"
        f"  esperado: {sorted(GRANDFATHERED)}\n"
        f"  real:     {sorted(encontrados)}"
    )


def test_la_deuda_fuera_de_agent_tambien_esta_inventariada():
    """`reenganche_cron.py` no está en agent/, así que ningún criterio C lo cubre — y por
    eso mismo es el más fácil de olvidar."""
    for rel, modulo in DEUDA_FUERA_DE_AGENT:
        imports = {m for m, _ in _imports_de(RAIZ / rel)}
        assert modulo in imports, f"{rel} ya no importa {modulo}: actualizar ARCH-DEBT-F2-01"


def test_el_criterio_c_original_seguiria_siendo_falso():
    """La prueba incómoda, y por eso existe: deja escrito en código que la afirmación
    «agent/ no importa routers/» NO es cierta al cerrar F2. Sin esto, alguien puede leer
    los cuatro tests de arriba en verde y concluir de más."""
    hay_imports = any(
        m.startswith("app.routers")
        for py in _modulos_py("app/agent")
        for m, _ in _imports_de(py)
    )
    assert hay_imports, (
        "si esto falla, la deuda se saldó: actualiza ARCH-DEBT-F2-01 y borra este test."
    )
