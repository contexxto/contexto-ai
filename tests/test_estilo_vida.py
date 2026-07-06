"""Tests del diccionario difuso→dato (app/estilo_vida.py) — tarea #13.

Cubre las cuatro rutas (existentes/servicios/protegidos/sin_dato), frases compuestas
(donde una sola oración cae en más de una lista), y los DOS bugs reales que la propia
revisión adversaria encontró EJECUTANDO el módulo antes de escribir estos tests (no solo
leyéndolo) — quedan aquí como regresión permanente, mismo espíritu que las rondas v2/v3/v4
documentadas en test_fair_housing.py / app/fair_housing.py.
"""
from app.estilo_vida import evaluar_concepto_estilo_vida, hay_algo_reconocido


def _claves(resultado: dict, bucket: str) -> set[str]:
    return {item["clave"] for item in resultado[bucket]}


# ── (1) YA LO CALCULAMOS: dimensiones existentes de encaje.py ──────────────────────
def test_tranquilidad_variantes():
    for frase in ("busco algo tranquilo", "necesito silencio para trabajar",
                  "quiero poco ruido", "un lugar para desconectar"):
        assert "tranquilidad" in _claves(evaluar_concepto_estilo_vida(frase), "existentes"), frase


def test_caminable_variantes():
    for frase in ("quiero que todo se resuelva caminando", "vida peatonal",
                  "no quiero depender del auto", "que pueda caminar todo"):
        assert "caminable" in _claves(evaluar_concepto_estilo_vida(frase), "existentes"), frase


def test_transporte_variantes():
    for frase in ("cerca del metro", "necesito transporte publico", "no tengo auto"):
        assert "transporte" in _claves(evaluar_concepto_estilo_vida(frase), "existentes"), frase


def test_area_verde_variantes():
    for frase in ("me gusta la naturaleza", "quiero un parque cerca",
                  "salir a correr", "hacer ejercicio afuera"):
        assert "area_verde" in _claves(evaluar_concepto_estilo_vida(frase), "existentes"), frase


# ── (2) SERVICIO OBJETIVO: presencia real, no veredicto de zona ────────────────────
def test_servicios_objetivos():
    casos = {
        "quiero ir de compras fácil": "centro_comercial",
        "necesito hacer el mercado cerca": "supermercado",
        "que haya una clínica cerca": "salud",
        "necesito una farmacia cerca": "farmacia",
        "quiero un colegio cerca": "educacion",
    }
    for frase, esperado in casos.items():
        assert esperado in _claves(evaluar_concepto_estilo_vida(frase), "servicios"), frase


# ── (3) CLASE PROTEGIDA: jamás traducir a dato de zona ─────────────────────────────
def test_familia_o_ninos():
    for frase in ("es para mi familia", "busco algo familiar", "para criar a mis hijos"):
        assert "familia_o_ninos" in _claves(evaluar_concepto_estilo_vida(frase), "protegidos"), frase


def test_edad():
    for frase in ("zona de jubilados", "ambiente universitario", "gente joven"):
        assert "edad" in _claves(evaluar_concepto_estilo_vida(frase), "protegidos"), frase


def test_nacionalidad_religion_genero_discapacidad():
    assert "nacionalidad_u_origen" in _claves(
        evaluar_concepto_estilo_vida("zona de expatriados"), "protegidos")
    assert "religion" in _claves(
        evaluar_concepto_estilo_vida("un ambiente religioso"), "protegidos")
    assert "genero_u_orientacion" in _claves(
        evaluar_concepto_estilo_vida("solo para mujeres"), "protegidos")
    assert "discapacidad" in _claves(
        evaluar_concepto_estilo_vida("zona inclusiva para discapacitados"), "protegidos")


def test_gente_como_yo():
    assert "gente_como_yo" in _claves(
        evaluar_concepto_estilo_vida("busco gente como yo"), "protegidos")


# ── Seguridad: caso especial, precedente ya decidido en este proyecto ──────────────
def test_seguridad_se_detecta_con_contexto_de_zona():
    for frase in ("quiero una zona segura", "necesito seguridad", "sin delincuencia por favor"):
        assert "seguridad" in _claves(evaluar_concepto_estilo_vida(frase), "protegidos"), frase


def test_seguro_NO_se_confunde_con_certeza_BUG_REAL_ENCONTRADO_ADVERSARIALMENTE():
    # Hallazgo real de esta misma sesión (ejecutando el módulo, no solo leyéndolo):
    # "seguro/segura" en español es AMBIGUO — también significa CERTEZA, no seguridad
    # de zona. Sin este fix, "estoy seguro de que me gusta" disparaba un falso positivo
    # de "seguridad", exactamente el tipo de ruido que fair_housing.py evita a propósito
    # ("alta precisión, pocos falsos positivos").
    r = evaluar_concepto_estilo_vida("Estoy seguro de que esta zona me gusta mucho")
    assert r["protegidos"] == []
    # Variante: "seguro que sí" (coloquial, sin relación a vivienda) tampoco debe marcar.
    r2 = evaluar_concepto_estilo_vida("seguro que sí, me interesa ese inmueble")
    assert not any(p["clave"] == "seguridad" for p in r2["protegidos"])


def test_seguro_CON_contexto_de_zona_SI_se_detecta():
    # El fix no debe sobre-corregir: "seguro" pegado a una necesidad de vivienda SÍ es
    # el caso real que hay que atrapar.
    for frase in ("busco algo seguro para vivir", "necesito un lugar seguro para mi familia"):
        assert "seguridad" in _claves(evaluar_concepto_estilo_vida(frase), "protegidos"), frase


# ── (4) LEGÍTIMO, SIN DATO VERIFICADO HOY: honestidad, no invención ────────────────
def test_sin_dato_hoy_variantes():
    casos = {
        "quiero buena vida nocturna": "vida_nocturna",
        "me gusta la gastronomía variada": "gastronomia",
        "quiero vida cultural, museos y teatros": "cultura",
        "necesito un gimnasio cerca": "deporte",
        "quiero un café para trabajar": "cafe_trabajo",
    }
    for frase, esperado in casos.items():
        assert esperado in _claves(evaluar_concepto_estilo_vida(frase), "sin_dato"), frase


def test_hacer_deporte_afuera_ya_no_queda_en_hueco_silencioso_BUG_REAL():
    # Hallazgo real de esta sesión: una exclusión (?!\ afuera) en el regex de "deporte"
    # dejaba "hacer deporte afuera" sin NINGÚN match en ninguna de las 4 listas — el
    # tipo de hueco silencioso más peligroso (ni honesto "sin_dato" ni dato real).
    r = evaluar_concepto_estilo_vida("me gusta hacer deporte afuera")
    assert hay_algo_reconocido(r)
    assert "deporte" in _claves(r, "sin_dato")


# ── Frases compuestas: cada parte se reporta en SU lista, ninguna se pisa ──────────
def test_frase_compuesta_tranquilo_y_familiar():
    r = evaluar_concepto_estilo_vida("busco un lugar tranquilo y familiar")
    assert "tranquilidad" in _claves(r, "existentes")
    assert "familia_o_ninos" in _claves(r, "protegidos")


def test_frase_compuesta_colegio_para_hijos():
    # El servicio (colegio) SÍ se puede citar como dato objetivo de distancia; lo que
    # nunca debe pasar es que el sistema emita un veredicto de idoneidad familiar de la
    # zona — por eso ambas listas se disparan a la vez, cada una gobernando su propia mitad.
    r = evaluar_concepto_estilo_vida("quiero un colegio cerca para mis hijos")
    assert "educacion" in _claves(r, "servicios")
    assert "familia_o_ninos" in _claves(r, "protegidos")


def test_frase_compuesta_sin_dato_y_protegido():
    r = evaluar_concepto_estilo_vida("quiero vida nocturna y que sea un lugar familiar")
    assert "vida_nocturna" in _claves(r, "sin_dato")
    assert "familia_o_ninos" in _claves(r, "protegidos")


def test_ninguna_clave_se_repite_entre_las_cuatro_tablas():
    # Guardia estructural: si una clave apareciera en dos tablas a la vez, un mismo
    # concepto podría reportarse con dos tratamientos distintos (p. ej. mapeable Y
    # protegido) según cuál tabla se recorra primero — ambigüedad que hay que impedir
    # por construcción, no confiar en que nadie la introduzca por accidente.
    from app.estilo_vida import _MAPEABLES_EXISTENTES, _PROTEGIDOS, _SERVICIOS_OBJETIVOS, _SIN_DATO_HOY
    todas = [c for tabla in (_MAPEABLES_EXISTENTES, _SERVICIOS_OBJETIVOS, _PROTEGIDOS, _SIN_DATO_HOY)
             for c, _, _ in tabla]
    assert len(todas) == len(set(todas))


# ── Degradación honesta: nada reconocido, nada inventado ───────────────────────────
def test_frase_sin_concepto_reconocido():
    r = evaluar_concepto_estilo_vida("quiero 3 dormitorios y 2 baños")
    assert not hay_algo_reconocido(r)
    assert r == {"existentes": [], "servicios": [], "protegidos": [], "sin_dato": []}


def test_entrada_vacia_o_none_no_revienta():
    assert not hay_algo_reconocido(evaluar_concepto_estilo_vida(""))
    assert not hay_algo_reconocido(evaluar_concepto_estilo_vida(None))


def test_insensible_a_acentos_y_mayusculas():
    r = evaluar_concepto_estilo_vida("QUIERO ALGO TRANQUILO Y CAMINABLE")
    assert "tranquilidad" in _claves(r, "existentes")
    assert "caminable" in _claves(r, "existentes")


# ── La tool del agente expone exactamente el mismo resultado (sin lógica propia) ───
def test_tool_traducir_estilo_de_vida_expone_el_mismo_resultado():
    import asyncio
    import json

    from app.agent.tools import AGENT_TOOLS, tool_traducir_estilo_de_vida

    assert tool_traducir_estilo_de_vida in AGENT_TOOLS

    directo = evaluar_concepto_estilo_vida("busco algo tranquilo y familiar")
    via_tool = asyncio.run(tool_traducir_estilo_de_vida.ainvoke(
        {"concepto": "busco algo tranquilo y familiar"}))
    assert json.loads(via_tool) == directo
