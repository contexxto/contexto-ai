"""
Estilo de vida difuso → dato de entorno verificado (tarea #13, foso conversacional).

Cuando alguien dice "quiero algo con buena vida nocturna" o "un lugar tranquilo y
familiar", el agente necesita traducir esa frase difusa a UNO de CUATRO destinos, nunca
improvisado por el LLM: (1) una dimensión objetiva que YA calculamos y podemos citar con
fuente, (2) un servicio real del catastro que puede estar o no estar ahí, (3) un concepto
legítimo pero que hoy NO tenemos verificado —y decirlo con honestidad en vez de
inventar—, o (4) un rasgo de identidad/clase protegida que JAMÁS se traduce a un dato de
zona, sea cual sea el dato disponible. Ver docs/BATALLA_Redfin_vs_Contexto_2026-06-23.md fila #3: "el ángulo de
estilo de vida SOLO es vendible si está INSTRUMENTADO (guardrail + eval), no como prosa
en el prompt" — este módulo es esa instrumentación: puro, determinístico, testeable
offline, la MISMA disciplina de app/encaje.py y app/fair_housing.py.

── Relación con el resto del guardrail Fair Housing (defensa en capas, no la única) ──
Este módulo es un AYUDANTE estructurado para los casos más comunes — NO reemplaza el
principio general "ATRIBUCIÓN, NO JUICIO" del prompt (app/agent/graph.py) ni el detector
de steering en la SALIDA del agente (app/fair_housing.py::detectar_steering). Una frase
que este diccionario no reconozca sigue gobernada por esos dos. Las tres capas juntas:
  1. Este módulo (ENTRADA): decide si el concepto que dijo el usuario se puede traducir a
     dato objetivo, a un servicio verificable, o si debe rechazarse — ANTES de que el
     agente responda.
  2. El prompt (ATRIBUCIÓN NO JUICIO): principio general para lo que este módulo no cubre.
  3. fair_housing.detectar_steering (SALIDA): red de seguridad final sobre lo que el
     agente efectivamente dijo, sea cual sea el camino que tomó para llegar ahí.

── Qué NUNCA se mapea a un dato de zona (clase protegida — precedente de este proyecto) ──
Mismo listado exacto que ya usa app/preferencias.py para IGNORAR atributos de identidad
("familia, hijos, edad, nacionalidad, origen, religión, género, discapacidad") — no es
una lista nueva inventada aquí, es la MISMA barrera aplicada también en la entrada
conversacional difusa. Se suma "seguridad": decisión ya tomada en este proyecto (no por
falta de dato — SÍ hay POIs de UPC/policía — sino porque un veredicto de "zona segura" es
subjetivo, no verificable, y es exactamente la clase de juicio que históricamente se ha
usado para redlining. Ruido se queda (medible); seguridad se va (juicio, no medición).

Nota de alcance (para no sobre-prometer): "accesibilidad física" (rampa/ascensor) es
DISTINTO de "discapacidad" como rasgo de identidad — es una necesidad legítima sobre el
EDIFICIO, no un veredicto de zona. Hoy preferencias.py la ignora junto con el resto de la
lista; este módulo mantiene esa misma línea por consistencia, pero es una posible mejora
futura separada (fuera del alcance de esta tarea) tratarla como necesidad legítima, igual
que `acepta_mascotas`.
"""
from __future__ import annotations

import re
import unicodedata


def _norm(texto: str | None) -> str:
    """minúsculas + sin acentos (NFD) → matching robusto en español."""
    t = unicodedata.normalize("NFD", texto or "")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return t.lower()


# ── (1) YA LO CALCULAMOS: dimensiones de encaje.DIMENSIONES, con plantilla ATRIBUCIÓN ──
# Frases MÁS AMPLIAS/difusas que las declaraciones literales que ya capta preferencias.py
# (que exige que el usuario "lo pida"); aquí cubrimos paráfrasis de estilo de vida que
# apuntan a la MISMA necesidad objetiva ya instrumentada.
_MAPEABLES_EXISTENTES: list[tuple[str, re.Pattern[str], str]] = [
    ("tranquilidad", re.compile(
        r"\btranquil\w*|\bsilenci\w*|poco ruido|sin ruido|para desconectar|"
        r"vivir en paz|un lugar en paz\b"),
     "Ruido (estimación por sector, no medición) y caminabilidad del inmueble."),
    ("caminable", re.compile(
        # "resolver" DIPTONGA (o→ue) en las formas más habladas: resuelvo/resuelve/
        # resuelva NO comparten raíz con el infinitivo "resolv-". res(olv|uelv) cubre
        # ambas — el mismo tipo de hueco de conjugación que fair_housing.py documenta
        # haber tenido que cerrar en varias rondas (ahí con "conviene/convengo"); acá lo
        # cerramos desde el principio en vez de descubrirlo después en producción.
        # La negación de "depender del auto" también varía de construcción ("sin
        # depender de auto" vs. "no quiero depender del auto"): una ventana corta
        # (hasta 20 caracteres, sin cruzar puntuación) entre sin/no y "depender" cubre
        # ambas sin exigir la frase exacta.
        r"\bcaminable|a pie\b|caminar(lo)? todo|vida peatonal|"
        r"sin (necesitar )?(el )?auto\b|"
        r"(sin|no)[^.!?]{0,20}?depend\w*\s+de(l)?\s*(el\s+|un\s+)?(auto|carro)\b|"
        r"res(?:olv|uelv)\w* caminando"),
     "Caminabilidad calculada sobre los comercios reales de la zona (OpenStreetMap)."),
    ("transporte", re.compile(
        r"transporte (publico|masivo)|cerca del metro|cerca de una parada|"
        r"\bbuseta|no (tengo|uso|manejo) (auto|carro)\b|sin (auto|carro)\b"),
     "Distancia real a pie al transporte masivo más cercano (Metro/parada)."),
    ("area_verde", re.compile(
        r"area verde|\bnaturaleza\b|\bverde\b|\bparques?\b|aire libre|"
        r"salir a correr|hacer ejercicio afuera|espacios? verdes?"),
     "Parque más cercano y/o cobertura vegetal del sector (estimación)."),
]

# ── (2) SERVICIO OBJETIVO: existe (o no) en servicios_cercanos del inmueble ─────────
# Dato de presencia, no de zona: "hay/no hay ese servicio a X distancia", nunca un
# veredicto de si la ZONA es apta para nadie. Reutiliza las categorías de
# app.entorno._CATEGORIAS (mismo vocabulario, una sola fuente de verdad).
_SERVICIOS_OBJETIVOS: list[tuple[str, re.Pattern[str], str]] = [
    ("centro_comercial", re.compile(r"\bcompras\b|centro comercial|ir de compras|\bmall\b"),
     "centro comercial"),
    ("supermercado", re.compile(r"supermercado|hacer (el )?mercado|\bsuper\b"),
     "supermercado"),
    ("salud", re.compile(r"\bclinica\b|\bhospital\b|centro de salud|atencion medica"),
     "salud (clínica/hospital)"),
    ("farmacia", re.compile(r"\bfarmacia\b"),
     "farmacia"),
    ("educacion", re.compile(r"\bcolegio\b|\bescuela\b|\buniversidad\b|centro educativo"),
     "educación (colegio/escuela/universidad)"),
]

# ── (3) CLASE PROTEGIDA: JAMÁS se traduce a dato de zona (mismo listado de preferencias.py) ──
_PROTEGIDOS: list[tuple[str, re.Pattern[str], str]] = [
    ("familia_o_ninos", re.compile(
        r"\bfamiliar\b|para mi familia|para (mis |sus )?hijos|para criar|"
        r"zona de familias|gente con ninos"),
     "composición familiar/hijos (familial status)"),
    ("edad", re.compile(
        r"para jovenes|gente joven|zona de jubilados|solo (para )?estudiantes|"
        r"ambiente universitario|para adultos mayores"),
     "edad/generación"),
    ("nacionalidad_u_origen", re.compile(
        r"gente de mi pais|comunidad extranjera|zona de expatriados|"
        r"barrio de migrantes|gente de mi (region|ciudad) de origen"),
     "nacionalidad/origen"),
    ("religion", re.compile(
        r"comunidad religiosa|ambiente religioso|cerca de mi (iglesia|templo|mezquita|"
        r"sinagoga) como comunidad"),
     "religión"),
    ("genero_u_orientacion", re.compile(
        r"gente de mi genero|solo (para )?(hombres|mujeres)|ambiente (gay|lgbt)\w*"),
     "género/orientación"),
    ("discapacidad", re.compile(
        r"zona (buena|ideal|inclusiva) para discapacitados|comunidad (para|de) discapacitados"),
     "discapacidad (como identidad de zona — distinto de accesibilidad física del edificio)"),
    ("seguridad", re.compile(
        # OJO: "seguro/segura" en español es AMBIGUO — también significa "certeza"
        # ("estoy seguro de que me gusta"), sin relación con seguridad de zona. Por eso
        # el adjetivo exige contexto de lugar/vivienda pegado (antes o después); solo el
        # SUSTANTIVO "seguridad" y las frases ya inequívocamente de zona quedan sueltos.
        r"\b(zona|barrio|sector|lugar|entorno)\s+segur[ao]s?\b|"
        r"\bsegur[ao]s?\s+(para vivir|para mi|para nosotros|para la familia)\b|"
        r"\bseguridad\b|zona segura|sin delincuencia|bajo en criminalidad|libre de robos"),
     "seguridad de la zona (juicio subjetivo, no una medición — decisión ya tomada en este producto)"),
    ("gente_como_yo", re.compile(
        r"gente como (yo|tu)|comunidad como la (mia|tuya)|gente de bien\b"),
     "juicio sobre 'la gente' del barrio"),
]

# ── (4) LEGÍTIMO, SIN DATO VERIFICADO HOY: honestidad, no invención ─────────────────
_SIN_DATO_HOY: list[tuple[str, re.Pattern[str], str]] = [
    ("vida_nocturna", re.compile(
        r"vida nocturna|\bbares?\b|discotecas?|salir de fiesta|ambiente nocturno"),
     "vida nocturna/bares"),
    ("gastronomia", re.compile(
        r"gastronomi\w*|restaurantes variados|buena comida cerca|escena culinaria"),
     "variedad gastronómica"),
    ("cultura", re.compile(
        r"vida cultural|\bmuseos?\b|\bteatros?\b|escena (artistica|cultural)|\barte\b"),
     "oferta cultural (museos/teatros)"),
    ("deporte", re.compile(
        # Sin excepciones cuando aparece "afuera": "hacer deporte afuera" SIGUE sin dato
        # de gimnasios (lo que sí tenemos, área verde, ya lo captura _MAPEABLES_EXISTENTES
        # por separado con "hacer ejercicio afuera"/"salir a correr" — que ambas listas
        # se disparen a la vez es correcto, no un conflicto: son dos necesidades reales.
        r"\bgimnasios?\b|vida deportiva|hacer deporte\b|actividad fisica"),
     "instalaciones deportivas/gimnasios"),
    ("cafe_trabajo", re.compile(
        r"cafe(s)? para trabajar|coworking|trabajar desde (un )?cafe"),
     "cafés/coworking para trabajo remoto"),
]


def _buscar(texto_norm: str, tabla: list[tuple[str, re.Pattern[str], str]]) -> list[dict]:
    out = []
    for clave, rx, detalle in tabla:
        m = rx.search(texto_norm)
        if m:
            out.append({"clave": clave, "frase_detectada": m.group(0).strip(), "detalle": detalle})
    return out


def evaluar_concepto_estilo_vida(texto: str | None) -> dict:
    """
    Traduce lo que el usuario dijo a sus tres destinos posibles. Una frase compuesta
    ("tranquilo y familiar") puede caer en más de una lista a la vez — se reportan TODAS,
    para que el agente atienda cada parte por separado en vez de promediarlas.

    Devuelve:
      {
        "existentes": [{clave, frase_detectada, detalle}],   # ya calculado, cita con fuente
        "servicios":  [{clave, frase_detectada, detalle}],   # presencia real, cita si está
        "protegidos": [{clave, frase_detectada, detalle}],   # JAMÁS traducir a dato de zona
        "sin_dato":   [{clave, frase_detectada, detalle}],   # honesto "no lo tengo aún"
      }
    Todas las listas vacías = no se detectó ningún concepto de estilo de vida reconocido;
    el agente sigue el principio general de ATRIBUCIÓN NO JUICIO del prompt.
    """
    n = _norm(texto)
    return {
        "existentes": _buscar(n, _MAPEABLES_EXISTENTES),
        "servicios": _buscar(n, _SERVICIOS_OBJETIVOS),
        "protegidos": _buscar(n, _PROTEGIDOS),
        "sin_dato": _buscar(n, _SIN_DATO_HOY),
    }


def hay_algo_reconocido(resultado: dict) -> bool:
    """True si evaluar_concepto_estilo_vida encontró AL MENOS un concepto en cualquier lista."""
    return any(resultado.get(k) for k in ("existentes", "servicios", "protegidos", "sin_dato"))
