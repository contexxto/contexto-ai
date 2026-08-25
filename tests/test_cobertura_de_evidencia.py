"""E2.3a · GATE — ninguna razón que movió la decisión queda muda.

El gate, en una frase: **una razón que afectó la decisión no puede quedar a la vez sin
evidencia resoluble y sin incertidumbre que lo diga.** Ese estado —participar en el
resultado y no aparecer en el contrato ni como afirmación ni como hueco— es exactamente
lo que hace inauditable a un sistema de decisión.

Fíjese en que el gate admite DOS formas de cumplirse, no una:

    evidencia resoluble  → afirmación material + evidence_refs
    sin evidencia        → UncertaintyV0 que registra el hueco

Hoy todas las razones pasan por el segundo camino, porque la tabla de procedencia
demostró que no hay ninguna referencia resoluble de punta a punta. Pero el test está
escrito sobre la disyunción y no sobre el estado de hoy: cuando F4 haga resoluble la
caminabilidad, esa dimensión migrará al primer camino y el gate seguirá pasando sin
tocarlo. Un test que solo dijera "todas son incertidumbres" habría que reescribirlo
—o peor, se volvería un incentivo para no migrar ninguna—.
"""

from datetime import datetime, timezone

import pytest

from app.contracts.decision_v0 import DecisionContextV0, Impact
from app.decision.assembler import _senales_encaje
from app.decision.context import assemble_decision_context_v0
from app.decision.evidencia import (
    DimensionSinProcedencia,
    derivar_incertidumbres,
    dimension_de,
)
from app.encaje import DIMENSIONES, calcular_encaje

AHORA = datetime(2026, 8, 25, 12, 0, 0, tzinfo=timezone.utc)

# La forma REAL que produce `_fetch_cards_rows` (misma fila que usa el archivo de E2.2).
ROW_REAL = {
    "id": "11111111-2222-3333-4444-555555555555",
    "direccion": "Av. Coruña y San Ignacio, La Floresta",
    "tipo_activo": "Departamento",
    "operacion": "ARRIENDO",
    "precio": 380,
    "imagen_url": None,
    "caminabilidad": 95,
    "caminabilidad_fuente": "osm",
    "ruido": "BAJO",
    "vegetacion": 42,
    "lat": -0.1807,
    "lon": -78.4867,
    "caracteristicas": {"num_dormitorios": 2, "acepta_mascotas": True},
    "servicios_cercanos": "🌳 Parque a ~300 m",
    "conectividad": "🚇 Metro a ~500 m (7 min a pie)",
}


def _fila(over: dict) -> dict:
    return {**ROW_REAL, **over}


def encaje_de(prefs: dict, over: dict) -> dict:
    """El motor de verdad sobre la fila de verdad. Nada de stubs."""
    row = _fila(over)
    return calcular_encaje(prefs, _senales_encaje(row, row.get("caracteristicas") or {}))


def decision_de(prefs: dict, over: dict) -> DecisionContextV0:
    row = _fila(over)
    return assemble_decision_context_v0(
        row=row,
        preferencias=prefs,
        encaje=encaje_de(prefs, over),
        session_id="s-e23",
        decision_id=f"scope:{row['id']}",
        created_at=AHORA,
    )


# ── El gate ────────────────────────────────────────────────────────────────────────


def _refs_materiales_de(decision: DecisionContextV0, dimension: str) -> list[str]:
    """Referencias de evidencia que una AFIRMACIÓN MATERIAL hace sobre esa dimensión.

    Hoy devuelve siempre vacío —no se emite ninguna afirmación material— y esa es la
    mitad del hallazgo. La función existe completa igual, para que el día que F4/F5
    empiecen a emitirlas el gate las cuente sin que haya que reescribirlo.
    """
    refs: list[str] = []
    materiales = [
        *decision.strengths,
        *decision.tradeoffs,
        *((decision.eligibility.violations) if decision.eligibility else ()),
        *((decision.match.dimensions) if decision.match else ()),
    ]
    for claim in materiales:
        texto = getattr(claim, "statement", "") or getattr(claim, "dimension", "") or ""
        if dimension in texto or dimension_de_texto(texto) == dimension:
            refs.extend(claim.evidence_refs)
    return refs


def dimension_de_texto(texto: str) -> str | None:
    from app.decision.evidencia import _ETIQUETA

    for dim in DIMENSIONES:
        if texto.startswith(_ETIQUETA[dim]):
            return dim
    return None


ESCENARIOS = {
    "todo_declarado_con_señal": (
        {"tipo_inmueble": "departamento", "presupuesto_max": 700, "caminable": True,
         "transporte": True, "area_verde": True, "acepta_mascotas": True,
         "tranquilidad": True, "dormitorios": 2},
        {},
    ),
    "ficha_vacía": (
        {"tipo_inmueble": "departamento", "presupuesto_max": 700, "caminable": True,
         "transporte": True, "area_verde": True, "acepta_mascotas": True,
         "tranquilidad": True, "dormitorios": 2},
        {"caminabilidad": None, "ruido": None, "servicios_cercanos": None,
         "conectividad": None, "caracteristicas": {}},
    ),
    "requisito_duro_incumplido": (
        {"tipo_inmueble": "departamento", "presupuesto_max": 700},
        {"tipo_activo": "Casa"},
    ),
    "sobre_presupuesto": (
        {"tipo_inmueble": "departamento", "presupuesto_max": 300},
        {"precio": 990},
    ),
    # `ruido` SÍ trae nivel ("BAJO" en la fila real) → el motor devuelve
    # `insufficient_evidence`, no `sin_dato`: el valor existe y se decidió, desde E0.4, no
    # dejarlo puntuar porque detrás no hay medición. Poner aquí un valor inválido daría
    # `sin_dato` y el test compararía el caso equivocado consigo mismo.
    "ruido_con_valor_sin_medición": (
        {"tranquilidad": True, "tipo_inmueble": "departamento"},
        {},
    ),
    "solo_una_dimensión": ({"dormitorios": 2}, {}),
    "sin_preferencias": ({}, {}),
}


@pytest.mark.parametrize("caso", sorted(ESCENARIOS))
def test_gate_ninguna_razon_queda_sin_evidencia_y_sin_incertidumbre(caso):
    """EL GATE DE E2.3. Cada razón del motor cae en uno de los dos caminos válidos."""
    prefs, over = ESCENARIOS[caso]
    encaje = encaje_de(prefs, over)
    decision = decision_de(prefs, over)

    mudas = []
    for razon in encaje["razones"]:
        dim = razon["dimension"]
        tiene_refs = bool(_refs_materiales_de(decision, dim))
        tiene_incertidumbre = any(
            dimension_de(u) == dim for u in decision.uncertainties
        )
        if not tiene_refs and not tiene_incertidumbre:
            mudas.append(dim)

    assert not mudas, (
        f"[{caso}] estas razones movieron la decisión y no aparecen en el contrato "
        f"ni como afirmación con evidencia ni como incertidumbre: {mudas}"
    )


def test_hoy_el_resultado_es_cero_afirmaciones_materiales_y_n_incertidumbres():
    """El estado que la tabla de procedencia predijo, medido y no supuesto.

    No es un fracaso de E2.3: es la primera vez que el sistema registra de forma
    estructurada qué parte de su propia decisión todavía no puede demostrar.
    """
    prefs, over = ESCENARIOS["todo_declarado_con_señal"]
    decision = decision_de(prefs, over)

    materiales = sum(len(_refs_materiales_de(decision, d)) for d in DIMENSIONES)
    assert materiales == 0, "apareció una evidence_ref material: revisar si resuelve de verdad"
    assert len(decision.uncertainties) == len(encaje_de(prefs, over)["razones"]) > 0


# ── Ninguna afirmación material se emite a medias ──────────────────────────────────


def test_no_se_emiten_afirmaciones_que_exigirian_refs_inventadas():
    """`ViolationV0` exige `evidence_refs` no vacía (congelado en E1.5). Emitir una hoy
    obligaría a fabricar la referencia — que es lo único que E2.3 no puede hacer."""
    decision = decision_de(*ESCENARIOS["requisito_duro_incumplido"])
    assert decision.strengths == ()
    assert decision.tradeoffs == ()
    assert decision.eligibility is None
    assert decision.match is None


def test_el_incumplimiento_duro_no_desaparece_solo_porque_no_pueda_ser_violation():
    """Si `eligibility.violations` no se puede emitir, el hecho tiene que salir igual por
    el otro camino. Si no, el gate se cumpliría callando el caso más grave."""
    prefs, over = ESCENARIOS["requisito_duro_incumplido"]
    encaje = encaje_de(prefs, over)
    assert encaje["duros_incumplidos"] == ["tipo_inmueble"]

    decision = decision_de(prefs, over)
    tipo = [u for u in decision.uncertainties if dimension_de(u) == "tipo_inmueble"]
    assert len(tipo) == 1
    assert tipo[0].impact is Impact.HIGH


# ── `impact` se deriva del motor, no se fija a ojo ─────────────────────────────────


@pytest.mark.parametrize("dim,esperado", [
    ("tipo_inmueble", Impact.HIGH),      # requisito duro → topa el score → sale del panel
    ("presupuesto_max", Impact.HIGH),    # gobierna el corte que saca tarjetas de la vista
    ("caminable", Impact.MEDIUM),        # mueve score y ranking, no elegibilidad
    ("dormitorios", Impact.MEDIUM),
    ("acepta_mascotas", Impact.MEDIUM),
])
def test_impacto_alto_solo_donde_el_hueco_cambia_lo_visible(dim, esperado):
    prefs, over = ESCENARIOS["todo_declarado_con_señal"]
    decision = decision_de(prefs, over)
    u = next(u for u in decision.uncertainties if dimension_de(u) == dim)
    assert u.impact is esperado


def test_una_dimension_que_no_pudo_evaluarse_pesa_bajo():
    """No alteró la decisión: decirlo con `impact` alto sería ruido que tapa lo que sí pesa."""
    decision = decision_de(*ESCENARIOS["ficha_vacía"])
    caminable = next(u for u in decision.uncertainties if dimension_de(u) == "caminable")
    assert caminable.impact is Impact.LOW


def test_el_impacto_duro_se_deriva_de_encaje_y_no_de_una_lista_paralela():
    """Si mañana alguien agrega un requisito duro en `encaje.py`, su impacto tiene que
    subir solo. Una lista copiada aquí divergiría en silencio."""
    from app.decision import evidencia
    from app.encaje import _REQUISITOS_DUROS

    assert _REQUISITOS_DUROS <= evidencia._CAMBIAN_LO_VISIBLE


# ── Los tres huecos son distintos y se dicen distinto ──────────────────────────────


def test_valor_sin_fuente_no_se_confunde_con_ausencia_de_valor():
    """`insufficient_evidence` (el número existe, nada lo sostiene) y `sin_dato` (no hay
    número) son huecos distintos. Colapsarlos perdería justo la distinción que E0.4
    introdujo para poder decir "no lo sabemos" en vez de inventar precisión."""
    sin_fuente = decision_de(*ESCENARIOS["ruido_con_valor_sin_medición"])
    sin_dato = decision_de(*ESCENARIOS["ficha_vacía"])

    a = next(u for u in sin_fuente.uncertainties if dimension_de(u) == "tranquilidad")
    b = next(u for u in sin_dato.uncertainties if dimension_de(u) == "tranquilidad")
    assert a.statement != b.statement
    assert "el valor existe" in a.statement
    assert "no reporta la señal" in b.statement


def test_la_incertidumbre_no_afirma_que_se_desconozca_el_valor():
    """Lo que se registra es que no se puede DEMOSTRAR la procedencia, no que el dato sea
    desconocido: el sistema sí lo conoce y lo usó para decidir."""
    prefs, over = ESCENARIOS["todo_declarado_con_señal"]
    decision = decision_de(prefs, over)
    presupuesto = next(
        u for u in decision.uncertainties if dimension_de(u) == "presupuesto_max"
    )
    assert "afectó el ranking" in presupuesto.statement
    assert "sin declaración trazable" in presupuesto.statement


def test_cada_incertidumbre_declara_que_fase_cierra_la_deuda():
    """La deuda va con destino. Sin eso, "falta evidencia" es un lamento y no un plan."""
    prefs, over = ESCENARIOS["todo_declarado_con_señal"]
    for u in decision_de(prefs, over).uncertainties:
        assert any(f in u.statement for f in ("→ F3", "→ F4", "→ F5")), u.statement


# ── Fronteras ──────────────────────────────────────────────────────────────────────


def test_las_incertidumbres_nunca_llevan_evidencia_fabricada():
    prefs, over = ESCENARIOS["todo_declarado_con_señal"]
    for u in decision_de(prefs, over).uncertainties:
        assert u.evidence_refs == ()


def test_vegetacion_y_trafico_no_producen_ninguna_afirmacion():
    """E0.4 los retiró del scoring. NO_CLAIM: ni razón, ni incertidumbre, ni fuerza."""
    prefs, over = ESCENARIOS["todo_declarado_con_señal"]
    decision = decision_de(prefs, over)
    texto = " ".join(u.statement for u in decision.uncertainties).lower()
    assert "vegetaci" not in texto and "tráfico" not in texto and "trafico" not in texto


def test_sin_preferencias_declaradas_no_hay_nada_que_registrar():
    """Cero razones → cero incertidumbres. Un hueco inventado sería tan falso como una
    evidencia inventada."""
    decision = decision_de({}, {})
    assert decision.uncertainties == ()


def test_sin_encaje_no_se_inventan_huecos():
    assert derivar_incertidumbres(None) == ()
    assert derivar_incertidumbres({}) == ()


def test_toda_dimension_del_motor_tiene_fila_de_procedencia():
    """Agregar una dimensión a `encaje.py` sin fila aquí la dejaría moviendo la decisión
    en silencio. Este test la caza antes que producción."""
    from app.decision import evidencia

    for tabla in (evidencia._ETIQUETA, evidencia._HUECO, evidencia._DESTINO):
        assert set(DIMENSIONES) <= set(tabla)


def test_una_dimension_desconocida_falla_ruidosamente():
    """No se omite la razón: se exige la fila. Omitirla produciría exactamente el estado
    que el gate prohíbe."""
    with pytest.raises(DimensionSinProcedencia, match="ascensor"):
        derivar_incertidumbres(
            {"razones": [{"dimension": "ascensor", "cumple": "alto", "aporta": True}]}
        )


def test_las_etiquetas_no_se_solapan_entre_si():
    """El emparejamiento razón↔incertidumbre va por prefijo. Si una etiqueta fuera prefijo
    de otra, el gate podría dar por cubierta la dimensión equivocada."""
    from app.decision.evidencia import _ETIQUETA

    for a in DIMENSIONES:
        for b in DIMENSIONES:
            if a != b:
                assert not _ETIQUETA[a].startswith(_ETIQUETA[b])


def test_mismo_encaje_produce_las_mismas_incertidumbres():
    prefs, over = ESCENARIOS["todo_declarado_con_señal"]
    encaje = encaje_de(prefs, over)
    assert derivar_incertidumbres(encaje) == derivar_incertidumbres(encaje)


def test_el_orden_sigue_al_de_las_razones_del_motor():
    """No se reordena por impacto: el contrato refleja la decisión, no la edita."""
    prefs, over = ESCENARIOS["todo_declarado_con_señal"]
    encaje = encaje_de(prefs, over)
    esperado = [r["dimension"] for r in encaje["razones"]]
    assert [dimension_de(u) for u in derivar_incertidumbres(encaje)] == esperado


# ── Que esto no haya cambiado nada de lo ya cerrado ────────────────────────────────


def test_el_ranking_y_la_identidad_siguen_intactos():
    """E2.3 agrega una lectura del contrato; no toca la autoridad que cerró E2.2."""
    prefs, over = ESCENARIOS["todo_declarado_con_señal"]
    decision = decision_de(prefs, over)
    assert decision.score_version == calcular_encaje(prefs, {})["score_version"]
    assert decision.property.property_id == str(ROW_REAL["id"])
