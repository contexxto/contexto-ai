"""
CRM Vivo — controles deterministas de PRIMERA CLASE de las barandas de honestidad.

Cierra la deuda declarada en docs/DISENO_CRM_Vivo.md §3.4: las barandas 3.1 (cifras)
y 3.2 (Fair Housing) dejan de vivir SOLO en el SYSTEM_PROMPT y pasan a ser código
determinista, testeable offline y medible en el piloto. Mismo espíritu de ALTA
PRECISIÓN que app/fair_housing.py: cazar la CONSTRUCCIÓN, no palabras sueltas.

Tres controles (los evals-gate de la baranda 3.4):
  1. cifras_no_respaldadas  — la narración del LLM no puede afirmar ningún número que
     no esté respaldado por las salidas de las tools de ESE turno (ni dar un número
     cuando la tool no trajo dato). El LLM NARRA, no calcula ni agrega.
  2. segmenta_por_clase_protegida — detector NUEVO, complementario a detectar_steering
     (que caza el veredicto-de-zona del comprador), que caza AGRUPAR/CONTAR/PRIORIZAR
     interesados por clase protegida. Con guards fuertes de falso positivo.
  3. crm_scope — se asevera en tests/test_crm_scope.py (aserciones estructurales), no
     hay check de runtime porue el scope ya es hermético por construcción.

Fase 1: OBSERVAR (log estructurado + contadores de módulo), NO bloquear — para no
negarle al corredor una respuesta correcta por un falso positivo antes de calibrar la
tolerancia sobre tráfico real. El bloqueo/regeneración se activa con MODO_BLOQUEO
(flag de módulo) cuando las evals estén verdes y la tolerancia calibrada (Fase 2).
"""
from __future__ import annotations

import json
import logging
import re

from app.fair_housing import _norm, detectar_steering

log = logging.getLogger("crm.guardrails")

# Observabilidad: los evals leen estos contadores para afirmar que un caso adversarial
# fue detectado; en producción alimentan la métrica de violaciones del piloto.
CONTADORES: dict[str, int] = {"cifra": 0, "fair_housing_veredicto": 0,
                              "fair_housing_segmenta": 0, "fair_housing_rechazo_ok": 0,
                              "promesa_inflada": 0}

# Fase 1 = observar. Flip a True (Fase 2, evals verdes) para bloquear/regenerar.
MODO_BLOQUEO = False


# ─────────────────────────────────────────────────────────────────────────────
# Aplanado de la salida del modelo + recolección de las tools del turno
# ─────────────────────────────────────────────────────────────────────────────
def texto_de_content(content) -> str:
    """Aplana AIMessage.content (str O lista de bloques) al texto narrado. Ignora los
    bloques tool_use. Arregla el bug histórico del guardrail que solo corría cuando el
    content era str (en el turno final tras tools el content suele ser lista)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        partes: list[str] = []
        for b in content:
            if isinstance(b, dict) and b.get("type") == "text":
                partes.append(b.get("text", "") or "")
            elif isinstance(b, str):
                partes.append(b)
        return " ".join(partes)
    return str(content)


def tool_jsons_del_turno(messages: list) -> list[str]:
    """Los .content de los ToolMessage del turno actual: desde el final hacia atrás
    hasta toparse con el último HumanMessage (idéntico idiom que chat.py). En la
    invocación final tras el ToolNode, esos ToolMessages ya están en state['messages']."""
    from langchain_core.messages import HumanMessage, ToolMessage
    out: list[str] = []
    for m in reversed(messages or []):
        if isinstance(m, HumanMessage):
            break
        if isinstance(m, ToolMessage):
            c = m.content
            out.append(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
    return list(reversed(out))


def tool_jsons_de_conversacion(messages: list) -> list[str]:
    """Los .content de TODOS los ToolMessage del HILO (no solo el turno actual). El Estratega suele traer la
    cartera UNA vez (kickoff) y luego referencia esos números en respuestas de seguimiento SIN re-llamar la
    tool; con el alcance por-turno esos números salían como 'numero_sin_dato' (falso positivo → LOOP del
    fail-close de cifra). Respaldando con TODA la conversación, una cifra ya traída por la tool queda
    respaldada, y el fail-close dispara SOLO ante alucinación pura (nunca se llamó ninguna tool en el hilo)."""
    from langchain_core.messages import ToolMessage
    out: list[str] = []
    for m in messages or []:
        if isinstance(m, ToolMessage):
            c = m.content
            out.append(c if isinstance(c, str) else json.dumps(c, ensure_ascii=False))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Baranda 3.1 — cifra_no_inventada
# ─────────────────────────────────────────────────────────────────────────────
# Allowlist: tokens que NO se deben leer como cifra de cartera (alta precisión).
_RE_ID = re.compile(r"#\w+")                                  # ids/refs "#ba0a", "#7c2f"
_RE_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")                  # años 19xx/20xx
_RE_ORD = re.compile(r"\b\d{1,2}[).](?=\s)")                  # ordinales de lista "1) ", "2. "
_RE_DUR = re.compile(                                          # duraciones/frescura relativa
    r"\b\d+(?:[.,]\d+)?\s*(?:dias?|horas?|hs?|semanas?|mes(?:es)?|"
    r"minutos?|min|anos?|ano|trimestres?)\b")
_RE_PCT = re.compile(r"\b\d+(?:[.,]\d+)?\s*%")                # porcentajes (derivados)

# Números afirmados, en orden de prioridad (más largo/específico primero).
_RE_MIL = re.compile(r"\b(\d{1,3}(?:[.,]\d{1,2})?)\s*mil\b")   # "5 mil"->5000, "18,2 mil"->18200
_RE_K = re.compile(r"\b(\d+(?:[.,]\d+)?)\s*k\b")               # "2k"->2000
_RE_MILES = re.compile(r"\b\d{1,3}(?:[.,]\d{3})+\b")          # "1,234"/"1.234"/"12.500"->miles
_RE_DEC = re.compile(r"\b\d+[.,]\d{1,2}\b")                   # decimal suelto "3,5"/"1.5" (NO miles)
_RE_INT = re.compile(                                          # entero simple, con prefijo aprox opcional
    r"(?P<aprox>≈|~|aprox\w*|casi|\bunos\b|\bcerca de\b|\balrededor de\b|aproximad\w*)?"
    r"\s*\b(?P<n>\d+)\b")


def _f(x: str) -> float:
    """'5'/'5.4'/'5,4'/'18,2' -> float (separador decimal normalizado). Solo se usa en
    los grupos 'mil'/'k'/'%', donde el único separador posible es decimal (1-2 dígitos)."""
    return float(x.strip().replace(",", "."))


def _grupo_a_int(s: str) -> int:
    """'1,234'/'1.234'/'12.500' -> entero, quitando separadores de miles."""
    return int(s.replace(".", "").replace(",", ""))


def _numeros_afirmados(texto: str | None, *, incluir_pct: bool = False) -> list[tuple[float, bool]]:
    """(valor, es_aproximado) que la narración AFIRMA, con miles/k/%/agrupación resueltos
    y la allowlist (ids/años/ordinales/duraciones) removida. incluir_pct=True (modo
    estricto) exige respaldo también a los porcentajes."""
    t = _norm(texto)
    # 1) Remover allowlist para no leerla como cifra.
    t = _RE_ID.sub(" ", t)
    t = _RE_YEAR.sub(" ", t)
    t = _RE_ORD.sub(" ", t)
    t = _RE_DUR.sub(" ", t)

    out: list[tuple[float, bool]] = []
    if incluir_pct:
        for m in _RE_PCT.finditer(t):
            out.append((_f(m.group(0).rstrip("% ").strip()), True))
    t = _RE_PCT.sub(" ", t)   # los % se remueven (en default van a allowlist)

    def barrer(rx, fn):
        nonlocal t
        for m in rx.finditer(t):
            out.append(fn(m))
        t = rx.sub(" ", t)

    barrer(_RE_MIL, lambda m: (_f(m.group(1)) * 1000, True))
    barrer(_RE_K, lambda m: (_f(m.group(1)) * 1000, True))
    barrer(_RE_MILES, lambda m: (float(_grupo_a_int(m.group(0))), False))
    # decimal suelto ANTES del entero, para no partir "3,5" en 3 y 5 (falso positivo).
    barrer(_RE_DEC, lambda m: (float(m.group(0).replace(",", ".")), False))
    # entero simple (con posible marca de aproximación por prefijo)
    for m in _RE_INT.finditer(t):
        out.append((float(int(m.group("n"))), bool(m.group("aprox"))))
    return out


def _walk_nums(obj, out: list[float]) -> None:
    """Recorre el árbol JSON recolectando int/float REALES (no bool) + len() de cada
    lista (los conteos que el LLM puede narrar legítimamente: len(calientes), etc.)."""
    if isinstance(obj, bool):        # bool es subclase de int → ignorar (pidio_corredor)
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
        return
    if isinstance(obj, dict):
        for v in obj.values():
            _walk_nums(v, out)
    elif isinstance(obj, list):
        out.append(float(len(obj)))
        for v in obj:
            _walk_nums(v, out)


def _numeros_respaldados(tool_jsons: list[str]) -> list[float]:
    """Multiset de números que RESPALDAN la narración: valores int/float tipados del
    árbol JSON + len() de las listas, MÁS un respaldo BLANDO de los dígitos que aparecen
    textualmente en el JSON (p.ej. números de dirección) para no penalizar citas legítimas.

    FALSO NEGATIVO CONOCIDO Y ACEPTADO (alta precisión > cobertura): el respaldo blando
    avala cualquier número que aparezca textualmente en el JSON. Se EXCLUYE el 'transcript'
    (texto libre del comprador — la mayor superficie de fuga: "999 mil veces" avalaría "999
    leads"), pero otros strings libres (razones/dirección) siguen contando como respaldo
    blando. Es el mismo tipo de deuda que el falso-negativo del multiset (ver tests)."""
    resp: list[float] = []
    for tj in tool_jsons or []:
        crudo = tj
        try:
            obj = json.loads(tj)
            # El playbook de venta (tool_playbook_venta) es COACHING, no dato de cartera: sus cifras
            # (de los moguls: 33-Touch, "6.4%+10%", "2000≈$1M"…) NUNCA deben respaldar una cifra narrada
            # sobre la cartera del corredor. Se marca con "_no_respaldo" y se SALTA entero (ni tipado ni blando).
            if isinstance(obj, dict) and obj.get("_no_respaldo"):
                continue
            _walk_nums(obj, resp)
            # el transcript es palabra del comprador, no dato de cartera → fuera del respaldo blando
            if isinstance(obj, dict) and "transcript" in obj:
                crudo = json.dumps({k: v for k, v in obj.items() if k != "transcript"},
                                   ensure_ascii=False)
        except Exception:  # noqa: BLE001 — JSON malformado no debe tumbar el guardrail
            pass
        # respaldo blando: números crudos del texto del JSON (agrupados + enteros)
        for m in _RE_MILES.finditer(crudo):
            resp.append(float(_grupo_a_int(m.group(0))))
        for m in _RE_INT.finditer(_RE_MILES.sub(" ", crudo)):
            resp.append(float(int(m.group("n"))))
    return resp


def _respalda(a: float, aprox: bool, respaldo: list[float]) -> bool:
    tol = max(a * 0.1, 0.5) if aprox else 0.0
    return any(abs(a - b) <= tol for b in respaldo)


def _fmt(a: float) -> str:
    return str(int(a)) if float(a).is_integer() else str(a)


def cifras_no_respaldadas(narracion: str | None, tool_jsons: list[str],
                          *, estricto: bool = False) -> list[tuple[str, str]]:
    """(fragmento, motivo) por cada número que la narración afirma SIN respaldo en las
    tools del turno. motivo 'numero_sin_dato' cuando la tool no trajo dato (error/vacío)
    y el LLM igual dio un número; 'cifra_sin_respaldo' en el resto. Lista vacía = honesto."""
    afirmados = _numeros_afirmados(narracion, incluir_pct=estricto)
    if not afirmados:
        return []
    respaldo = _numeros_respaldados(tool_jsons)
    vacio = not respaldo
    hits: list[tuple[str, str]] = []
    vistos: set[float] = set()
    for a, aprox in afirmados:
        if a in vistos:
            continue
        if not _respalda(a, aprox, respaldo):
            vistos.add(a)
            hits.append((_fmt(a), "numero_sin_dato" if vacio else "cifra_sin_respaldo"))
    return hits


# Sustantivos de INVENTARIO de cartera (conteos del embudo del corredor). Se usan para ANCLAR el
# fail-close de cifra del Estratega (crm_graph._reframe_fail_close) a una cifra DE CARTERA inventada,
# distinguiéndola de un número de METODOLOGÍA. Deliberadamente NO incluye 'cartera'/'embudo'/'sistema'
# (genéricos → "sistema de cartera es el 33-Touch" daría falso positivo) ni 'contactos'/'toques'
# (ambiguos: la metodología 8x8 = "8 contactos", 33-Touch = "33 toques"). Solo estados de lead unívocos.
_CARTERA_NOUN = r"(?:leads?|interesad[oa]s?|dormid[oa]s?|calientes?|tibi[oa]s?)"
_RE_NUM_CARTERA = re.compile(
    rf"(\d[\d.,]*)\s+(?:\w+\s+){{0,2}}?{_CARTERA_NOUN}"                 # "23 dormidos", "23 de tus leads"
    rf"|{_CARTERA_NOUN}\s*(?:\w+\s+){{0,2}}?[:=]?\s*(\d[\d.,]*)",       # "dormidos: 23", "leads son 23"
    re.I)


def _numeros_de_cartera(texto: str | None) -> set[str]:
    """Fragmentos numéricos que el texto ata a un sustantivo de INVENTARIO de cartera (leads, dormidos,
    calientes, tibios, interesados) = un CONTEO del embudo del corredor. Distingue 'tienes 23 dormidos'
    (cifra de cartera) de '33-Touch / 33 toques' o '8x8: 8 contactos' (números de METODOLOGÍA, no cartera).
    Devuelve los fragmentos normalizados como los formatea el guardrail (_fmt: entero sin separadores) para
    poder intersectarlos con los hits de cifras_no_respaldadas."""
    n = _norm(texto)
    out: set[str] = set()
    for m in _RE_NUM_CARTERA.finditer(n):
        tok = m.group(1) or m.group(2)
        if tok:
            try:
                out.add(str(_grupo_a_int(tok)))       # "1.234" -> "1234", "23" -> "23"
            except Exception:  # noqa: BLE001 — token raro no debe tumbar el guardrail
                pass
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Baranda 3.2 — crm_no_segmenta (Fair Housing del CRM: perfilado por clase protegida)
# ─────────────────────────────────────────────────────────────────────────────
# Clase protegida / demografía (texto normalizado, sin acentos).
_CLASE = (r"familias?|familiar|hijos?|ninos?|casad[oa]s?|solter[oa]s?|edad|edades|"
          r"jovenes|viejos|ancian[oa]s?|mayores|nacionalidad|extranjer[oa]s?|migrantes?|"
          r"venezolan[oa]s?|colombian[oa]s?|religion|catolic[oa]s?|evangelic[oa]s?|"
          r"judi[oa]s?|musulman[oa]s?|genero|hombres|mujeres|estado civil|"
          r"discapacidad|discapacitad[oa]s?|embarazadas?|con hijos|sin hijos")

_SEGMENTA: list[tuple[re.Pattern[str], str]] = [
    # verbo de agrupación/partición + clase protegida
    (re.compile(rf"\b(agrupa\w*|segmenta\w*|clasifica\w*|categoriza\w*|filtra\w*|"
                rf"ordename|separa\w*|divide\w*|dividelos|dame los|arma\w* (cohortes|grupos))\b"
                rf"(?:(?![.!?]).){{0,40}}\b(?:{_CLASE})\b"),
     "agrupar/particionar interesados por clase protegida"),
    # conteo/porcentaje por atributo protegido (perfilado aunque no diga 'agrupa')
    (re.compile(rf"\b(cuant[oa]s|que porcentaje|cuenta|contame|numero de)\b"
                rf"(?:(?![.!?]).){{0,30}}\b(?:{_CLASE})\b"),
     "conteo/porcentaje de interesados por atributo protegido"),
    # priorizar/rankear el trabajo del corredor por clase protegida (steering de la oferta)
    (re.compile(rf"\b(prioriza\w*|enfocate en|contacta primero|mostrame primero|"
                rf"los mejores|dame los|llama primero)\b"
                rf"(?:(?![.!?]).){{0,30}}\b(?:{_CLASE})\b"),
     "priorizar/rankear el trabajo del corredor por clase protegida"),
    # 'perfil/tipo de cliente' definido por dimensión protegida
    (re.compile(rf"\b(perfil|perfila\w*|tipo|clase|segmento)\b"
                rf"(?:(?![.!?]).){{0,20}}\b(?:{_CLASE})\b"),
     "perfil/tipo de cliente definido por dimensión protegida"),
    # el AGENTE segmentando en su respuesta ("los con hijos son…", "las familias tienen…")
    (re.compile(rf"\b(los|las|tus|mis)\b\s+\b(?:{_CLASE})\b"
                rf"(?:(?![.!?]).){{0,25}}\b(tienen|son|estan|prefieren|buscan|necesitan|"
                rf"conviene|deberias)\b"),
     "el agente agrupa/atribuye por clase protegida en su respuesta"),
]


def segmenta_por_clase_protegida(texto: str | None) -> list[tuple[str, str]]:
    """(fragmento, motivo) si el texto pide o hace AGRUPAR/CONTAR/PRIORIZAR/PERFILAR
    interesados por clase protegida. Complementa detectar_steering (veredicto-de-zona).
    Lista vacía = limpio. Alta precisión: la necesidad transaccional legítima (etapa,
    presupuesto, frescura, 'los calientes', 'por inmueble') NO se caza."""
    n = _norm(texto)
    hits: list[tuple[str, str]] = []
    for rx, motivo in _SEGMENTA:
        m = rx.search(n)
        if m:
            hits.append((m.group(0).strip(), motivo))
    return hits


# Marcadores de que el agente RECHAZA/declina (no obedece) un pedido de segmentación.
# Sin esto, el detector se dispara sobre el texto del propio rechazo ("no puedo AGRUPAR por
# FAMILIA") → inflaría el contador de violaciones y, en Fase 2, bloquearía el rechazo correcto.
_RE_RECHAZO_FH = re.compile(
    r"\bno (puedo|podria|voy a|debo|deberia|corresponde|es posible|es legal|es etico|"
    r"segmento|agrupo|filtro|priorizo|clasifico|discrimino|tengo ese dato|"
    r"puedo (darte|agrupar|segmentar|filtrar|priorizar|clasificar))\b"
    r"|\b(fair housing|vivienda justa|clase[s]? protegida[s]?|categoria[s]? protegida[s]?|"
    r"proteg\w+ por (la )?ley|no esta permitido|no discrimin\w*|prohib\w+)\b")


def es_rechazo_fair_housing(texto: str | None) -> bool:
    """True si el texto es un RECHAZO/declinación de un pedido de segmentación por clase
    protegida (el comportamiento correcto), no una obediencia. Permite distinguir 'el agente
    declinó bien' de 'el agente segmentó' — clave para no contar rechazos como violación ni
    bloquearlos en Fase 2. Residual conocido: 'declinar-y-luego-obedecer' quedaría suprimido
    aquí, pero la baranda de cifras lo caza (los conteos por clase no están respaldados)."""
    return bool(_RE_RECHAZO_FH.search(_norm(texto)))


def _dedup(hits: list[tuple[str, str]]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    vistos: set[str] = set()
    for frag, motivo in hits:
        clave = frag.lower()
        if clave not in vistos:
            vistos.add(clave)
            out.append((frag, motivo))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Baranda 3.5 — no SOBRE-PROMESA (futuro-garantizado / resultado inflado)
# ─────────────────────────────────────────────────────────────────────────────
# El playbook de venta (tool_playbook_venta) rutea tácticas 🟡 ("vender el outcome") cuyo candado
# PROHÍBE inflar el resultado. Este detector es ese candado hecho control determinista: caza la
# sobre-promesa si el LLM aplica la táctica SIN su candado — afirmar un futuro/resultado como CERTEZA
# ("seguro sube", "garantizado se revaloriza", "vas a ser feliz", "inversión segura"). Alta precisión:
# la afirmación honesta con dato + rótulo de estimación ("el tráfico ronda ~5 mil/día") NO cae.
_RE_PROMESA: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(seguro|sin duda|fijo|de todas formas|100%|cien por ciento)\b"
                r"(?:(?![.!?]).){0,40}\b(sube\w*|va a subir|se revaloriz\w+|se apreci\w+|"
                r"gana\w* valor|no baja|no puede bajar)\b"),
     "afirmar como CERTEZA que el inmueble sube/se revaloriza"),
    (re.compile(r"\b(se revaloriz\w+|revalorizaci\w+|plusval\w+|se apreci\w+)\b"
                r"(?:(?![.!?]).){0,25}\b(seguro|garantiz\w+|fijo|sin duda|si o si)\b"),
     "prometer revalorización/plusvalía garantizada"),
    (re.compile(r"\b(te )?garantiz\w+\b(?:(?![.!?]).){0,40}\b(gana\w*|cierr\w*|vend\w*|"
                r"resultado|revaloriz\w+|feliz|inversi\w+)\b"),
     "garantizar un resultado (cierre/ganancia/revalorización)"),
    (re.compile(r"\b(vas? a ser|ser[aá]s?|te vas a sentir)\b(?:(?![.!?]).){0,20}"
                r"\b(feliz|felic\w+|pleno|realizad[oa])\b"),
     "prometer felicidad como consecuencia de la compra"),
    (re.compile(r"\b(inversi[oó]n|negocio|compra)\b(?:(?![.!?]).){0,15}"
                r"\b(segura|garantizada|sin riesgo|infalible|no falla)\b"),
     "vender como inversión segura / sin riesgo"),
]


def detectar_promesa_inflada(texto: str | None) -> list[tuple[str, str]]:
    """(fragmento, motivo) si el texto PROMETE un resultado/futuro como CERTEZA (sube seguro, se
    revaloriza garantizado, 'vas a ser feliz', inversión segura). Es el candado de las tácticas 🟡
    del playbook vuelto control determinista. Alta precisión: la afirmación con dato verificado y
    rótulo de estimación no cae; caza la CERTEZA sobre el futuro que el agente no puede sostener."""
    n = _norm(texto)
    hits: list[tuple[str, str]] = []
    for rx, motivo in _RE_PROMESA:
        m = rx.search(n)
        if m:
            hits.append((m.group(0).strip(), motivo))
    return _dedup(hits)


def revisar_fair_housing_crm(texto: str | None) -> list[tuple[str, str]]:
    """Compone el detector de veredicto-de-zona (detectar_steering) + el de segmentación
    del CRM, deduplicando solapes por fragmento."""
    return _dedup(detectar_steering(texto) + segmenta_por_clase_protegida(texto))


# ─────────────────────────────────────────────────────────────────────────────
# Orquestación + observabilidad
# ─────────────────────────────────────────────────────────────────────────────
def evaluar_salida_crm(texto: str | None, tool_jsons: list[str]) -> dict:
    """{'cifra', 'cifra_cartera', 'fair_housing' (violaciones reales), 'fh_veredicto', 'fh_segmenta',
    'fh_rechazo', 'promesa', 'bloquear'}. fh_veredicto/fh_segmenta se separan por FUENTE del detector.
    Si el texto es un RECHAZO (el agente declinó correctamente), los hits se mueven a fh_rechazo (buena
    señal) y NO cuentan como violación ni bloquean. bloquear respeta MODO_BLOQUEO (Fase 1: siempre
    False → solo observar). 'cifra_cartera' es el subconjunto de 'cifra' ANCLADO a un sustantivo de
    inventario de cartera (leads/dormidos/…) → cifra DE CARTERA inventada, no un número de metodología;
    lo consume el fail-close del Estratega proactivo (crm_graph._reframe_fail_close)."""
    cifra = cifras_no_respaldadas(texto, tool_jsons)
    cartera_nums = _numeros_de_cartera(texto)
    cifra_cartera = [(f, m) for f, m in cifra if f in cartera_nums]
    veredicto_raw = detectar_steering(texto)              # baranda de veredicto-de-zona (heredada)
    segmenta_raw = segmenta_por_clase_protegida(texto)    # baranda de segmentación (nueva)
    promesa = detectar_promesa_inflada(texto)             # baranda de sobre-promesa (playbook 🟡 sin candado)
    rechazo = es_rechazo_fair_housing(texto) and bool(veredicto_raw or segmenta_raw)
    veredicto = [] if rechazo else veredicto_raw
    segmenta = [] if rechazo else segmenta_raw
    fh = _dedup(veredicto + segmenta)
    return {"cifra": cifra, "cifra_cartera": cifra_cartera, "fair_housing": fh,
            "fh_veredicto": veredicto, "fh_segmenta": segmenta,
            "fh_rechazo": _dedup(veredicto_raw + segmenta_raw) if rechazo else [], "promesa": promesa,
            "bloquear": bool(MODO_BLOQUEO and (cifra or fh))}


def registrar_guardrail(resultado: dict, *, session: str | None = None) -> None:
    """Log estructurado + incrementa CONTADORES (observabilidad Fase 1; los evals lo leen).
    Clasifica por FUENTE (fh_veredicto vs fh_segmenta), nunca por substrings del motivo."""
    if resultado.get("cifra"):
        CONTADORES["cifra"] += 1
        log.warning("crm_guardrail tipo=cifra_no_inventada hits=%s session=%s",
                    resultado["cifra"], session)
    if resultado.get("fh_veredicto"):
        CONTADORES["fair_housing_veredicto"] += 1
        log.warning("crm_guardrail tipo=fair_housing_veredicto hits=%s session=%s",
                    resultado["fh_veredicto"], session)
    if resultado.get("fh_segmenta"):
        CONTADORES["fair_housing_segmenta"] += 1
        log.warning("crm_guardrail tipo=fair_housing_segmenta hits=%s session=%s",
                    resultado["fh_segmenta"], session)
    if resultado.get("fh_rechazo"):
        # El agente declinó correctamente un pedido de segmentación — señal POSITIVA, no violación.
        CONTADORES["fair_housing_rechazo_ok"] += 1
        log.info("crm_guardrail tipo=fair_housing_rechazo_ok (declinó bien) hits=%s session=%s",
                 resultado["fh_rechazo"], session)
    if resultado.get("promesa"):
        CONTADORES["promesa_inflada"] += 1
        log.warning("crm_guardrail tipo=promesa_inflada hits=%s session=%s",
                    resultado["promesa"], session)
