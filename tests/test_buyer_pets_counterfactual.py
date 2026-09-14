"""F3-ONE-FIELD-SHADOW-COUNTERFACTUAL-R0E · el contrafactual de mascotas, sólo en pruebas.

QUÉ CONGELA, y qué NO.

    congela    que alterar ÚNICAMENTE el requisito de mascotas, sobre exactamente las mismas
               filas y el mismo motor, produce diferencias explicables y ninguna espuria
    NO congela que el comprador mejore la recomendación. No hay ground truth para eso, y
               llamar «mejora» a un delta sin patrón de verdad sería inventarse el resultado

## LA PREGUNTA, EXACTA

No es «¿sirve el BuyerContext?». Es: **¿el mecanismo es limpio?** Si el mismo valor produce
diferencias, o si una diferencia arrastra algo que no es mascotas, no habría forma de leer
ningún experimento posterior. Esto se mide antes de tener nada que medir.

## TRES OPERACIONES, NO UN `bool | None`

La tentación obvia sería proyectar `pets_allowed_required` directamente: `True` → exigir,
`None` → retirar. Está mal, y el error tiene nombre: **`None` no distingue «lo retiró» de
«nunca dijo nada»**.

```
REQUIRE_PETS            el comprador exige que acepten mascotas
CLEAR_PETS_REQUIREMENT  el comprador RETIRA ese requisito (acto explícito del turno)
NO_BUYER_SIGNAL         el comprador no se ha pronunciado — legacy manda, intacto
```

`NO_BUYER_SIGNAL` y `CLEAR_PETS_REQUIREMENT` acaban en sitios distintos: la primera **no
toca** las preferencias legacy; la segunda **borra la clave**. Confundirlas haría que un
comprador silencioso pisara una preferencia que la persona sí declaró en el hilo. T8 y M2
existen sólo para eso.

R0E **no** define cómo el runtime derivará la operación desde la evidencia real: eso es del
preflight siguiente. Aquí la operación es un dato del experimento.

## LO QUE ESTE FICHERO NO TIENE PERMITIDO SER

Es TEST ONLY. Los helpers de operación, métricas y clasificación viven aquí y sólo aquí: no
hay módulo productivo, ni flag, ni dataclass, ni enum exportado. Primero se demuestra que el
experimento produce señal; empaquetarlo antes sería construir la tubería para un caudal que
todavía no se ha visto correr.

Cero LLM, cero base, cero red. El core de R0D se llama directamente sobre filas en memoria.
"""

from __future__ import annotations

import ast
import copy
import json
import pathlib

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.decision import assembler

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FUENTE_TEST = pathlib.Path(__file__)

# ── Las tres operaciones. Vocabulario CERRADO, y sólo de este test. ────────────────

REQUIRE_PETS = "require_pets"
CLEAR_PETS_REQUIREMENT = "clear_pets_requirement"
NO_BUYER_SIGNAL = "no_buyer_signal"

_CLAVE = "acepta_mascotas"


def aplicar_contrafactual_mascotas(legacy: dict, operacion: str) -> dict:
    """Las preferencias del turno con el requisito de mascotas alterado. **Copia nueva.**

    Nunca muta la entrada: las dos ejecuciones del core tienen que partir del mismo legacy,
    y un `dict` compartido que se modifica convertiría la segunda corrida en otra cosa.

    Toca UNA clave. No es un `update(proyeccion)` ni un merge: es una operación por campo,
    reconstruible a mano —legacy efectivo, operación, valor resultante— que es lo que permite
    atribuir cualquier delta posterior.
    """
    sombra = copy.deepcopy(legacy)
    if operacion == REQUIRE_PETS:
        sombra[_CLAVE] = True
    elif operacion == CLEAR_PETS_REQUIREMENT:
        sombra.pop(_CLAVE, None)
    elif operacion == NO_BUYER_SIGNAL:
        pass  # el comprador no se pronunció: legacy manda, intacto
    else:
        raise AssertionError(f"operación desconocida: {operacion}")
    return sombra


# ── El universo experimental ───────────────────────────────────────────────────────


def _row(rid, pets, **over):
    """Activos IDÉNTICOS salvo por mascotas. Es lo que hace atribuible cualquier delta.

    `pets` es tri-estado: `True`, `False`, o `None` = la ficha no lo reporta (la clave ni
    siquiera existe, que es como llega de la base cuando nadie la hidrató).
    """
    car = {"num_dormitorios": 2}
    if pets is not None:
        car[_CLAVE] = pets
    row = {
        "id": rid,
        "direccion": f"Dir {rid}",
        "tipo_activo": "Departamento",
        "operacion": "ARRIENDO",
        "precio": 380,
        "imagen_url": None,
        "caminabilidad": 95,
        "caminabilidad_fuente": "osm",
        "ruido": "BAJO",
        "vegetacion": 42,
        "lat": -0.18,
        "lon": -78.48,
        "caracteristicas": car,
        "servicios_cercanos": "\U0001F333 Parque a ~300 m",
        "conectividad": "\U0001F687 Metro a ~500 m (7 min a pie)",
    }
    row.update(over)
    return row


IDS = ["pet-si", "pet-no", "pet-nd"]


def _universo():
    """Tres activos equivalentes salvo por la dimensión que se varía.

    `pet-nd` («no dato») no es relleno: es el que hace observable la SEGUNDA ruta causal —la
    cobertura— que un fixture con sólo true/false dejaría invisible.
    """
    return [_row("pet-si", True), _row("pet-no", False), _row("pet-nd", None)]


def _mensajes():
    return [
        HumanMessage(content="busco algo por aquí"),
        ToolMessage(content=json.dumps({"assets": [{"id": i} for i in IDS]}),
                    name="tool_search_nearby_assets", tool_call_id="t1"),
        AIMessage(content="Encontré algunas opciones."),
    ]


def _decidir(rows, prefs, *, ids=None, curaciones=None, messages=None):
    """El core cerrado por R0D, llamado directo. Sin panel, sin base, sin modelo."""
    return assembler._decidir_desde_filas(
        rows, {} if curaciones is None else curaciones,
        ids=IDS if ids is None else ids,
        preferencias=prefs,
        messages=_mensajes() if messages is None else messages,
        session_id="s-r0e")


# ── Observación: métricas y clasificación. Sólo de este test. ─────────────────────


def _ejes(panel):
    """Lo estable y comparable. NO entran `decision_id` ni `created_at`.

    R0D dejó `_nuevo_scope_id()` (uuid4) y `_ahora_utc()` dentro del core a propósito: no
    salen del panel y no tocan el orden. Compararlos mediría el reloj, no la decisión.

    Los scores se miden sobre **cards + descartadas**, es decir sobre el universo entero, y
    no sólo sobre lo visible. El motivo lo descubrió este mismo fixture: declarar mascotas
    puede empujar un activo por debajo del corte de rejilla (`_ENCAJE_MIN_GRID`) y sacarlo
    de `cards`. Si los ejes sólo miraran lo visible, ese activo desaparecería de la medición
    justo en el caso en que más dice — y el delta parecería un activo esfumado en vez de un
    score que bajó.
    """
    todas = list(panel["cards"]) + list(panel["descartadas"])
    return {
        "orden": [c["id"] for c in panel["cards"]],
        "descartadas": [c["id"] for c in panel["descartadas"]],
        "encaje": {c["id"]: c["encaje"] for c in todas},
        "cobertura": {c["id"]: c["encaje_cobertura"] for c in todas},
        "medido": {c["id"]: c["encaje_medido"] for c in todas},
        "duros": {c["id"]: list(c["duros_incumplidos"] or []) for c in todas},
        "razones": {c["id"]: [r["texto"] for r in (c["encaje_razones"] or [])]
                    for c in todas},
    }


def medir(visible: dict, sombra: dict) -> dict:
    """Las métricas del encargo. Deterministas, sin agregados inventados.

    No hay «quality score»: un número único escondería justo lo que interesa —de dónde salió
    la diferencia— y empujaría a leer un delta como una mejora.
    """
    v, s = _ejes(visible), _ejes(sombra)
    pos_v = {a: i for i, a in enumerate(v["orden"])}
    pos_s = {a: i for i, a in enumerate(s["orden"])}
    comunes = set(pos_v) & set(pos_s)          # posiciones: sólo lo VISIBLE en ambos
    universo = set(v["encaje"]) & set(s["encaje"])   # scores: todo el universo
    return {
        "same_order": v["orden"] == s["orden"],
        "top1_changed": (v["orden"][:1] or [None]) != (s["orden"][:1] or [None]),
        "top3_overlap": len(set(v["orden"][:3]) & set(s["orden"][:3])),
        "asset_count_visible": len(v["orden"]),
        "asset_count_shadow": len(s["orden"]),
        "position_deltas": {a: pos_s[a] - pos_v[a] for a in sorted(comunes)},
        "score_delta_by_asset": {a: (s["encaje"][a] - v["encaje"][a])
                                 for a in sorted(universo)
                                 if v["encaje"][a] is not None
                                 and s["encaje"][a] is not None},
        "coverage_delta_by_asset": {a: (s["cobertura"][a] - v["cobertura"][a])
                                    for a in sorted(universo)
                                    if v["cobertura"][a] is not None
                                    and s["cobertura"][a] is not None},
        "salieron_de_la_rejilla": sorted(set(s["descartadas"]) - set(v["descartadas"])),
        "descartadas_visible": v["descartadas"],
        "descartadas_shadow": s["descartadas"],
    }


NO_DELTA = "NO_DELTA"
EXPECTED_DELTA = "EXPECTED_DELTA"
UNEXPECTED_DELTA = "UNEXPECTED_DELTA"
NOT_COMPARABLE = "NOT_COMPARABLE"


def diferencia_de_preferencias(legacy: dict, sombra: dict) -> set[str]:
    """Las claves cuyo ESTADO cambió. Presencia y valor cuentan por igual.

    Se compara así —y no por valores— porque borrar una clave y ponerla a `False` son cosas
    distintas para esta guarda, aunque el motor las trate igual: si el harness empezara a
    borrar donde debería escribir, quiero verlo.
    """
    centinela = object()
    claves = set(legacy) | set(sombra)
    return {k for k in claves
            if legacy.get(k, centinela) is not sombra.get(k, centinela)
            and legacy.get(k, centinela) != sombra.get(k, centinela)}


def clasificar(legacy: dict, sombra: dict, visible: dict, sombra_panel: dict) -> str:
    """El desenlace del contrafactual. Vocabulario cerrado y sólo de este test.

    `PERSISTENCE_DIVERGED` no aparece: R0E no tiene runtime ni persistencia, y un valor que
    nunca puede producirse es ruido que invita a rellenarlo.
    """
    cambiadas = diferencia_de_preferencias(legacy, sombra)
    if cambiadas - {_CLAVE}:
        return UNEXPECTED_DELTA
    v, s = _ejes(visible), _ejes(sombra_panel)
    if set(v["orden"]) | set(v["descartadas"]) != set(s["orden"]) | set(s["descartadas"]):
        # El universo cambió: eso no lo puede hacer una dimensión de encaje.
        return UNEXPECTED_DELTA
    if not v["orden"] and not s["orden"]:
        return NOT_COMPARABLE
    return NO_DELTA if v == s else EXPECTED_DELTA


# ══ T1-T3 · LA UNIDAD EXPERIMENTAL SE MANTIENE CONSTANTE ═══════════════════════════


def test_T1_las_dos_ejecuciones_reciben_EL_MISMO_objeto_de_filas():
    """No «filas equivalentes»: el MISMO objeto, y los mismos elementos.

    Es la propiedad que R0D entregó y la que hace que este experimento signifique algo. Con
    dos copias, cualquier delta podría venir del universo en vez del campo.
    """
    filas = _universo()
    legacy = {"dormitorios": 2}
    sombra = aplicar_contrafactual_mascotas(legacy, REQUIRE_PETS)

    vistas = []
    real = assembler._decidir_desde_filas

    def espia(rows, cur, **kw):
        vistas.append(rows)
        return real(rows, cur, **kw)

    assembler._decidir_desde_filas = espia
    try:
        _decidir(filas, legacy)
        _decidir(filas, sombra)
    finally:
        assembler._decidir_desde_filas = real

    assert len(vistas) == 2
    assert vistas[0] is vistas[1] is filas
    assert all(a is b for a, b in zip(vistas[0], vistas[1]))


def test_T2_ninguna_ejecucion_MUTA_las_filas():
    """Si la primera corrida ensuciara las filas, la segunda partiría de otro universo."""
    filas = _universo()
    antes = copy.deepcopy(filas)
    legacy = {"dormitorios": 2}

    _decidir(filas, legacy)
    _decidir(filas, aplicar_contrafactual_mascotas(legacy, REQUIRE_PETS))

    assert filas == antes, "el core mutó las filas entre las dos ejecuciones"


def test_T3_el_contrafactual_no_MUTA_las_preferencias_legacy():
    """Lo visible se decide con el legacy original, y tiene que seguir siéndolo después."""
    legacy = {"dormitorios": 2, "tranquilidad": True}
    antes = copy.deepcopy(legacy)

    for operacion in (REQUIRE_PETS, CLEAR_PETS_REQUIREMENT, NO_BUYER_SIGNAL):
        sombra = aplicar_contrafactual_mascotas(legacy, operacion)
        assert legacy == antes, f"{operacion} mutó el legacy"
        assert sombra is not legacy, "la sombra tiene que ser una copia separada"


def test_T12_el_UNIVERSO_de_activos_no_cambia():
    """Mascotas es dimensión de encaje, no requisito duro: no puede quitar ni añadir activos."""
    filas = _universo()
    legacy = {"dormitorios": 2}
    visible = _decidir(filas, legacy)
    sombra = _decidir(filas, aplicar_contrafactual_mascotas(legacy, REQUIRE_PETS))

    universo = lambda p: set(c["id"] for c in p["cards"]) | set(  # noqa: E731
        c["id"] for c in p["descartadas"])
    assert universo(visible) == universo(sombra) == set(IDS)


def test_T13_el_harness_no_introduce_NINGUN_filtro_duro():
    """Mascotas NO se vuelve requisito duro — pero sí puede sacar un activo de la rejilla.

    Hay que decir las dos cosas, porque son distintas y confundirlas sería el error:

    ```
    REQUISITO DURO   `duros_incumplidos` topa el score a 49 y marca «no es lo que pediste».
                     Mascotas NO está en `_REQUISITOS_DUROS` y sigue sin estarlo: vacío en
                     las dos corridas.
    CORTE DE REJILLA `_recortar_grid` deja fuera de `cards` lo que baja de `_ENCAJE_MIN_GRID`.
                     Existía antes de R0E y no lo toca nadie: es una CONSECUENCIA del score,
                     no un filtro nuevo.
    ```

    El activo que no acepta mascotas cae a 50, por debajo del corte, y pasa a `descartadas`.
    Sigue en el universo —se le sigue midiendo el score— y no desaparece: la promesa del
    panel es que lo descartado se nombre, no que se borre.
    """
    from app.decision.assembler import _ENCAJE_MIN_GRID

    filas = _universo()
    legacy = {"dormitorios": 2}
    visible = _decidir(filas, legacy)
    sombra = _decidir(filas, aplicar_contrafactual_mascotas(legacy, REQUIRE_PETS))
    v, s = _ejes(visible), _ejes(sombra)

    # 1 · ningún requisito duro, ni antes ni después.
    assert all(not d for d in v["duros"].values())
    assert all(not d for d in s["duros"].values()), \
        "declarar mascotas convirtió la dimensión en requisito duro"

    # 2 · lo que salió de la rejilla salió por el corte que YA existía, y se puede señalar.
    salieron = set(s["descartadas"]) - set(v["descartadas"])
    for asset in salieron:
        assert s["encaje"][asset] < _ENCAJE_MIN_GRID, (
            f"{asset} salió de la rejilla sin estar por debajo del corte: "
            "eso sería un filtro que el arnés inventó")

    # 3 · y el universo no encoge: lo descartado sigue nombrado.
    assert set(v["encaje"]) == set(s["encaje"]) == set(IDS)


# ══ T4 · EXACTAMENTE UN CAMPO ══════════════════════════════════════════════════════


@pytest.mark.parametrize("legacy, operacion", [
    ({}, REQUIRE_PETS),
    ({"dormitorios": 2}, REQUIRE_PETS),
    ({"dormitorios": 2, _CLAVE: True}, CLEAR_PETS_REQUIREMENT),
    ({"dormitorios": 2, _CLAVE: True}, NO_BUYER_SIGNAL),
    ({"dormitorios": 2, "tranquilidad": True, "presupuesto_max": 700}, REQUIRE_PETS),
])
def test_T4_solo_cambia_acepta_mascotas(legacy, operacion):
    sombra = aplicar_contrafactual_mascotas(legacy, operacion)
    assert diferencia_de_preferencias(legacy, sombra) <= {_CLAVE}


def test_T4b_la_guarda_de_UN_SOLO_CAMPO_detecta_un_segundo():
    """LA MITAD NEGATIVA de T4 (y la mutación M1). Sin esto, T4 podría comparar dos dicts
    que nunca difieren y ser cierto y vacío."""
    legacy = {"dormitorios": 2}
    sombra = aplicar_contrafactual_mascotas(legacy, REQUIRE_PETS)
    sombra["presupuesto_max"] = 700          # el segundo campo, sólo aquí

    cambiadas = diferencia_de_preferencias(legacy, sombra)
    assert cambiadas == {_CLAVE, "presupuesto_max"}
    assert cambiadas - {_CLAVE}, "la guarda no ve el segundo campo"


def _claves_que_toca(fn: ast.AST) -> set[str]:
    """Las claves del `dict` de preferencias que una función ESCRIBE o BORRA.

    Se leen de la ESTRUCTURA —subíndices y `.pop(...)`— y no de los identificadores sueltos
    del cuerpo. La diferencia no es cosmética: el primer intento comparaba todos los nombres
    contra la lista de dimensiones legacy y se ponía rojo por `operacion`… que aquí es el
    PARÁMETRO de la operación, no la preferencia `operacion`. Un guard que colisiona con los
    nombres locales acaba relajándose hasta no vigilar nada.
    """
    claves = set()

    def _anotar(nodo):
        if isinstance(nodo, ast.Name):
            claves.add(nodo.id)
        elif isinstance(nodo, ast.Constant) and isinstance(nodo.value, str):
            claves.add(nodo.value)

    for n in ast.walk(fn):
        if isinstance(n, ast.Subscript):
            _anotar(n.slice)
        elif isinstance(n, ast.Call) and getattr(n.func, "attr", None) in ("pop", "get",
                                                                          "setdefault"):
            if n.args:
                _anotar(n.args[0])
    return claves


def test_T17_ningun_otro_campo_del_comprador_entra_en_la_proyeccion():
    """Estructural: la operación toca UNA clave, y está escrita a mano.

    No hay tabla de proyecciones ni bucle sobre campos del comprador — eso sería el framework
    genérico que §20 prohíbe explícitamente en esta unidad. Cuando llegue el segundo campo
    habrá que decidir su semántica una por una, no barrerlas todas con un `update`.
    """
    arbol = ast.parse(FUENTE_TEST.read_text(encoding="utf-8"))
    fn = next(n for n in ast.walk(arbol) if isinstance(n, ast.FunctionDef)
              and n.name == "aplicar_contrafactual_mascotas")

    assert _claves_que_toca(fn) == {"_CLAVE"}, (
        "la operación toca más de una clave de preferencias: "
        f"{sorted(_claves_que_toca(fn))}")
    assert _CLAVE == "acepta_mascotas"

    assert not [n for n in ast.walk(fn) if isinstance(n, (ast.For, ast.comprehension))], \
        "hay un bucle sobre campos: eso sería un framework de proyecciones"


def test_T17b_el_detector_de_CLAVES_no_es_inerte():
    """LA MITAD NEGATIVA. Ve un segundo campo tanto escrito como borrado, y NO confunde un
    parámetro que se llame igual que una preferencia."""
    dos_campos = ast.parse(
        "def f(prefs, operacion):\n"
        "    prefs[_CLAVE] = True\n"
        "    prefs['presupuesto_max'] = 700\n")
    fn = next(n for n in ast.walk(dos_campos) if isinstance(n, ast.FunctionDef))
    assert _claves_que_toca(fn) == {"_CLAVE", "presupuesto_max"}

    borra_otro = ast.parse(
        "def f(prefs, operacion):\n"
        "    prefs.pop('dormitorios', None)\n")
    fn2 = next(n for n in ast.walk(borra_otro) if isinstance(n, ast.FunctionDef))
    assert _claves_que_toca(fn2) == {"dormitorios"}

    # El control que motivó reescribir el guard: un PARÁMETRO llamado `operacion` no es una
    # clave tocada, y confundirlos fue exactamente el falso positivo original.
    solo_parametro = ast.parse(
        "def f(prefs, operacion):\n"
        "    if operacion == 'x':\n"
        "        prefs[_CLAVE] = True\n")
    fn3 = next(n for n in ast.walk(solo_parametro) if isinstance(n, ast.FunctionDef))
    assert _claves_que_toca(fn3) == {"_CLAVE"}


# ══ T5 · CONTROL A · ACUERDO → SIN DELTA ═══════════════════════════════════════════


def test_T5_acuerdo_entre_legacy_y_comprador_NO_produce_delta():
    """El control que detecta un arnés que fabrica diferencias por su cuenta.

    Legacy ya exige mascotas y el comprador exige mascotas: la sombra tiene que ser
    indistinguible de lo visible. Si esto fallara, ninguna otra medición valdría nada.
    """
    filas = _universo()
    legacy = {"dormitorios": 2, _CLAVE: True}
    sombra_prefs = aplicar_contrafactual_mascotas(legacy, REQUIRE_PETS)

    assert sombra_prefs == legacy
    visible, sombra = _decidir(filas, legacy), _decidir(filas, sombra_prefs)

    assert clasificar(legacy, sombra_prefs, visible, sombra) == NO_DELTA
    m = medir(visible, sombra)
    assert m["same_order"] and not m["top1_changed"]
    assert set(m["score_delta_by_asset"].values()) == {0}
    assert set(m["coverage_delta_by_asset"].values()) == {0.0}


# ══ T6 · CONTROL B · MEMORIA ENTRE SESIONES ════════════════════════════════════════


def test_T6_la_memoria_del_comprador_produce_un_delta_ATRIBUIBLE():
    """Hilo nuevo sin mención de mascotas, comprador que sí las exige.

    Es el caso conceptualmente central del Gate F3, reducido aquí a su parte mecánica: el
    contrafactual, sin store ni runtime. Lo que se afirma es que el delta EXISTE y que es
    reconstruible desde el campo — no que sea mejor.
    """
    filas = _universo()
    legacy = {"dormitorios": 2}                       # el hilo no habló de mascotas
    sombra_prefs = aplicar_contrafactual_mascotas(legacy, REQUIRE_PETS)

    visible, sombra = _decidir(filas, legacy), _decidir(filas, sombra_prefs)
    assert clasificar(legacy, sombra_prefs, visible, sombra) == EXPECTED_DELTA

    m = medir(visible, sombra)
    assert not m["same_order"], "el fixture no tiene varianza suficiente para ver señal"

    # El conteo VISIBLE baja de 3 a 2, y no es un activo perdido: el que no acepta mascotas
    # cayó por debajo del corte de rejilla y pasó a `descartadas`, donde se le sigue midiendo.
    assert m["asset_count_visible"] == 3 and m["asset_count_shadow"] == 2
    assert m["salieron_de_la_rejilla"] == ["pet-no"]
    assert len(m["score_delta_by_asset"]) == 3, "el universo medido sigue siendo el mismo"


# ══ T7 · CONTROL C · LA CORRECCIÓN DEL TURNO GANA ══════════════════════════════════


def test_T7_un_CLEAR_del_turno_actual_vence_a_la_memoria_vieja():
    """Estado previo: exigía mascotas. Turno actual: las retira. El legacy efectivo del
    turno ya no las trae, y la sombra tiene que coincidir con lo visible.

    Congela `CURRENT CLEAR > STALE MEMORY` **dentro del experimento**. No concede autoridad
    productiva: lo visible sigue decidiéndose con el legacy, intacto.
    """
    filas = _universo()
    legacy_del_turno = {"dormitorios": 2}             # ya sin mascotas: la persona las retiró
    sombra_prefs = aplicar_contrafactual_mascotas(legacy_del_turno, CLEAR_PETS_REQUIREMENT)

    assert _CLAVE not in sombra_prefs
    visible = _decidir(filas, legacy_del_turno)
    sombra = _decidir(filas, sombra_prefs)

    assert clasificar(legacy_del_turno, sombra_prefs, visible, sombra) == NO_DELTA
    assert medir(visible, sombra)["same_order"]


def test_T7b_el_CLEAR_retira_el_requisito_cuando_legacy_SI_lo_traia():
    """La otra mitad: si el legacy del turno todavía exige mascotas y el comprador las
    retira explícitamente, la clave desaparece y el delta es esperado."""
    filas = _universo()
    legacy = {"dormitorios": 2, _CLAVE: True}
    sombra_prefs = aplicar_contrafactual_mascotas(legacy, CLEAR_PETS_REQUIREMENT)

    assert _CLAVE not in sombra_prefs
    visible, sombra = _decidir(filas, legacy), _decidir(filas, sombra_prefs)
    assert clasificar(legacy, sombra_prefs, visible, sombra) == EXPECTED_DELTA


# ══ T8 · CONTROL D · AUSENCIA DE SEÑAL NO ES UN CLEAR ══════════════════════════════


def test_T8_sin_senal_del_comprador_NO_se_borra_la_preferencia_legacy():
    """La distinción que evita el peor fallo del diseño ingenuo.

    Un comprador que nunca se pronunció sobre mascotas **no** puede pisar una preferencia
    que la persona sí declaró en este hilo. Proyectar `None → CLEAR` haría exactamente eso,
    en silencio, y la persona vería desaparecer un requisito que acababa de pedir.
    """
    filas = _universo()
    legacy = {"dormitorios": 2, _CLAVE: True}
    sombra_prefs = aplicar_contrafactual_mascotas(legacy, NO_BUYER_SIGNAL)

    assert sombra_prefs == legacy
    assert sombra_prefs.get(_CLAVE) is True, "la ausencia de señal borró el requisito"

    visible, sombra = _decidir(filas, legacy), _decidir(filas, sombra_prefs)
    assert clasificar(legacy, sombra_prefs, visible, sombra) == NO_DELTA


def test_T8b_sin_senal_tampoco_INVENTA_una_preferencia():
    """Y al revés: si el legacy no traía mascotas, la ausencia de señal no las añade."""
    legacy = {"dormitorios": 2}
    sombra_prefs = aplicar_contrafactual_mascotas(legacy, NO_BUYER_SIGNAL)
    assert _CLAVE not in sombra_prefs and sombra_prefs == legacy


# ══ T9-T11 · LAS DOS RUTAS CAUSALES, POR SEPARADO ══════════════════════════════════


def test_T9_T10_T11_las_DOS_rutas_causales_se_miden_por_separado():
    """El hallazgo que el preflight anticipó y que aquí se mide: mascotas mueve la decisión
    por DOS caminos, y los dos son atribuibles al mismo campo.

    ```
    DIRECTA     el activo REPORTA el dato  → entra al promedio → cambia el score
    COBERTURA   el activo NO lo reporta    → no puntúa, pero sube el peso declarado
                                           → baja la cobertura → encoge el encaje ajustado
    ```

    Un arnés que sólo conociera la primera clasificaría la segunda como delta inexplicado y
    se pondría rojo sobre un comportamiento correcto.
    """
    filas = _universo()
    legacy = {"dormitorios": 2}
    sombra_prefs = aplicar_contrafactual_mascotas(legacy, REQUIRE_PETS)
    visible, sombra = _decidir(filas, legacy), _decidir(filas, sombra_prefs)

    v, s = _ejes(visible), _ejes(sombra)

    # Partida: los tres son idénticos salvo por mascotas, que nadie declaró aún.
    assert v["encaje"] == {"pet-si": 100, "pet-no": 100, "pet-nd": 100}
    assert v["cobertura"] == {"pet-si": 1.0, "pet-no": 1.0, "pet-nd": 1.0}

    # T9 · dato TRUE → el requisito se cumple: ni sube ni baja, y la razón lo dice.
    assert s["encaje"]["pet-si"] == 100
    assert "Acepta mascotas" in s["razones"]["pet-si"]

    # T10 · dato FALSE → ruta DIRECTA: la dimensión puntúa 0 y arrastra el promedio.
    assert s["encaje"]["pet-no"] == 50
    assert s["cobertura"]["pet-no"] == 1.0, "el dato existe: la cobertura no cae"
    assert "No acepta mascotas" in s["razones"]["pet-no"]

    # T11 · SIN dato → ruta COBERTURA: el score medido no se mueve, el visible sí.
    assert s["medido"]["pet-nd"] == v["medido"]["pet-nd"] == 100
    assert s["cobertura"]["pet-nd"] == 0.5, "declarar una dimensión sin señal baja la n"
    assert s["encaje"]["pet-nd"] == 75, "encaje ajustado = 100·0.5 + 50·0.5"

    m = medir(visible, sombra)
    assert m["score_delta_by_asset"] == {"pet-nd": -25, "pet-no": -50, "pet-si": 0}
    assert m["coverage_delta_by_asset"] == {"pet-nd": -0.5, "pet-no": 0.0, "pet-si": 0.0}


# ══ T14-T16 · TODO DELTA ES RECONSTRUIBLE ══════════════════════════════════════════


def test_T14_T15_T16_cada_delta_se_reconstruye_desde_el_campo():
    """La propiedad que convierte esto en evidencia y no en una anécdota: dado el legacy, la
    operación y las filas, cada número se puede volver a derivar a mano."""
    filas = _universo()
    legacy = {"dormitorios": 2}
    sombra_prefs = aplicar_contrafactual_mascotas(legacy, REQUIRE_PETS)
    m = medir(_decidir(filas, legacy), _decidir(filas, sombra_prefs))

    # T14 · score: promedio ponderado con pesos 1.0 y 1.0.
    assert m["score_delta_by_asset"]["pet-no"] == 50 - 100          # (1+0)/2 vs 1/1
    # T15 · cobertura: peso evaluado / peso declarado.
    assert m["coverage_delta_by_asset"]["pet-nd"] == 0.5 - 1.0      # 1.0/2.0 vs 1.0/1.0
    # T16 · posición: el orden se deriva del encaje visible, no de otra cosa. `pet-no` ya no
    # está en la rejilla, así que no tiene posición que comparar — sí tiene score, arriba.
    assert m["position_deltas"] == {"pet-nd": -1, "pet-si": 0}
    assert not m["top1_changed"], "el mejor sigue siendo el mismo"
    assert m["top3_overlap"] == 2


# ══ T18-T20 · SIN MODELO, SIN E/S, DETERMINISTA ════════════════════════════════════


_PROHIBIDAS = {"_fetch_cards_rows", "_fetch_curaciones_batch", "extraer_preferencias",
               "construir_panel", "build_result_cards", "execute", "commit", "rollback",
               "AsyncSessionLocal", "ainvoke", "astream", "httpx", "requests", "urlopen"}


def test_T18_T19_este_experimento_no_llama_al_MODELO_ni_a_NADA_externo():
    """Estructural sobre este fichero, por AST. Incluye `construir_panel`: usarlo en vez del
    core puro (mutación M5) reintroduciría la adquisición de filas y con ella un universo
    que ya no sería el mismo por construcción."""
    arbol = ast.parse(FUENTE_TEST.read_text(encoding="utf-8"))
    invocadas = set()
    for n in ast.walk(arbol):
        if isinstance(n, ast.Call):
            nombre = getattr(n.func, "id", None) or getattr(n.func, "attr", None)
            if nombre:
                invocadas.add(nombre)

    fugas = invocadas & _PROHIBIDAS
    assert not fugas, f"el experimento toca algo externo: {sorted(fugas)}"
    assert not [n for n in ast.walk(arbol) if isinstance(n, ast.Await)]


@pytest.mark.parametrize("operacion", [REQUIRE_PETS, CLEAR_PETS_REQUIREMENT,
                                       NO_BUYER_SIGNAL])
def test_T20_el_contrafactual_es_DETERMINISTA(operacion):
    """Dos corridas idénticas dan lo mismo. Sin esto, ningún delta sería atribuible: podría
    venir del ruido en vez del campo."""
    filas = _universo()
    legacy = {"dormitorios": 2, "tranquilidad": True}
    sombra_prefs = aplicar_contrafactual_mascotas(legacy, operacion)

    primera = medir(_decidir(filas, legacy), _decidir(filas, sombra_prefs))
    segunda = medir(_decidir(filas, legacy), _decidir(filas, sombra_prefs))
    assert primera == segunda


# ══ T21-T24 · MUTACIONES · cada guarda tiene que poder ponerse ROJA ════════════════


def test_T21_M1_MUTACION_tocar_un_segundo_campo_se_detecta():
    """M1. La clasificación tiene que pasar a `UNEXPECTED_DELTA`, no a un delta explicable."""
    filas = _universo()
    legacy = {"dormitorios": 2}
    sombra_prefs = aplicar_contrafactual_mascotas(legacy, REQUIRE_PETS)
    sombra_prefs["presupuesto_max"] = 300          # el segundo campo, sólo aquí

    veredicto = clasificar(legacy, sombra_prefs, _decidir(filas, legacy),
                           _decidir(filas, sombra_prefs))
    assert veredicto == UNEXPECTED_DELTA


def test_T22_M2_MUTACION_tratar_la_AUSENCIA_como_un_clear_se_detecta():
    """M2. Es el error de diseño que T8 previene; aquí se demuestra que se ve.

    Un `NO_BUYER_SIGNAL` que borrara la clave produciría un delta donde no debía haberlo, y
    además borraría una preferencia declarada por la persona.
    """
    filas = _universo()
    legacy = {"dormitorios": 2, _CLAVE: True}

    correcto = aplicar_contrafactual_mascotas(legacy, NO_BUYER_SIGNAL)
    mutado = copy.deepcopy(legacy)
    mutado.pop(_CLAVE)                              # la mutación: ausencia tratada como clear

    assert clasificar(legacy, correcto, _decidir(filas, legacy),
                      _decidir(filas, correcto)) == NO_DELTA
    assert clasificar(legacy, mutado, _decidir(filas, legacy),
                      _decidir(filas, mutado)) == EXPECTED_DELTA, \
        "borrar por ausencia de señal no se distingue de no hacer nada: T8 sería inerte"


def test_T23_M3_MUTACION_que_la_memoria_VIEJA_gane_al_clear_se_detecta():
    """M3. Si `CLEAR` dejara el requisito puesto, T7 se pondría rojo."""
    filas = _universo()
    legacy_del_turno = {"dormitorios": 2}

    correcto = aplicar_contrafactual_mascotas(legacy_del_turno, CLEAR_PETS_REQUIREMENT)
    mutado = {**legacy_del_turno, _CLAVE: True}     # la memoria vieja pisando al turno

    assert clasificar(legacy_del_turno, correcto, _decidir(filas, legacy_del_turno),
                      _decidir(filas, correcto)) == NO_DELTA
    assert clasificar(legacy_del_turno, mutado, _decidir(filas, legacy_del_turno),
                      _decidir(filas, mutado)) == EXPECTED_DELTA, \
        "un CLEAR que deja True no se distingue de uno que retira: T7 sería inerte"


def test_T24_M4_MUTACION_usar_filas_DISTINTAS_se_detecta():
    """M4. Dos universos distintos producirían un delta que no viene del campo.

    Se comprueba en las dos direcciones: el detector de identidad ve la copia, y el
    clasificador ve que el universo cambió.
    """
    filas = _universo()
    otras = copy.deepcopy(filas)
    assert filas is not otras and filas == otras, "una copia: igual en valor, distinta en id"

    legacy = {"dormitorios": 2}
    sombra_prefs = aplicar_contrafactual_mascotas(legacy, REQUIRE_PETS)

    # Mismo contenido pero otro objeto: el delta sigue siendo el mismo, y por eso la
    # identidad se afirma aparte (T1) — el valor solo no la detectaría.
    con_copia = medir(_decidir(filas, legacy), _decidir(otras, sombra_prefs))
    con_mismas = medir(_decidir(filas, legacy), _decidir(filas, sombra_prefs))
    assert con_copia == con_mismas
    assert not any(a is b for a, b in zip(filas, otras)) or filas is otras

    # Y un universo REALMENTE distinto sí cambia el veredicto.
    recortado = filas[:2]
    veredicto = clasificar(legacy, sombra_prefs, _decidir(filas, legacy),
                           _decidir(recortado, sombra_prefs, ids=IDS[:2]))
    assert veredicto == UNEXPECTED_DELTA


def test_M6_MUTACION_meter_ENTRADA_SALIDA_en_el_experimento_se_detecta():
    """M6. La mitad negativa del guard de T18/T19."""
    roto = ast.parse("def experimento():\n"
                     "    panel = construir_panel(mensajes)\n"
                     "    return panel\n")
    invocadas = {getattr(n.func, "id", None) or getattr(n.func, "attr", None)
                 for n in ast.walk(roto) if isinstance(n, ast.Call)}
    assert invocadas & _PROHIBIDAS, "el guard no ve una llamada al panel productivo"

    asincrono = ast.parse("async def f():\n    return await _fetch_cards_rows([1])\n")
    assert [n for n in ast.walk(asincrono) if isinstance(n, ast.Await)]


def test_NOT_COMPARABLE_existe_y_se_alcanza():
    """El cuarto desenlace no es decorativo: sin activos no hay nada que comparar, y decirlo
    es distinto de decir «no hubo diferencia»."""
    legacy = {"dormitorios": 2}
    sombra_prefs = aplicar_contrafactual_mascotas(legacy, REQUIRE_PETS)
    vacio_v = _decidir([], legacy, ids=[])
    vacio_s = _decidir([], sombra_prefs, ids=[])
    assert clasificar(legacy, sombra_prefs, vacio_v, vacio_s) == NOT_COMPARABLE
