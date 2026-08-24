"""
Motor de ENCAJE — cuánto encaja un inmueble con las NECESIDADES DECLARADAS del usuario.

El pin del Mapa Vivo codifica ENCAJE, no precio (docs/SPEC_Mapa_Vivo.md). Este es el
score 0-100 detrás de "X% de encaje contigo" (tarea #8) y el DELTA del modo COMPARAR.

DISTINTO del motor de intención (app/intencion.py), que mide qué tan CALIENTE está el
lead (preguntó precio, pidió visita → readiness de handoff). Aquí medimos PREFERENCIA:
cuánto responde ESTE inmueble a lo que el usuario dijo que busca.

── Fair Housing (innegociable, tarea #14) ──────────────────────────────────────────
El encaje se keyea a QUÉ buscas, NUNCA a QUIÉN eres. Dos garantías por CONSTRUCCIÓN:
  1. `DIMENSIONES` es una whitelist CERRADA de necesidades (tranquilidad, presupuesto,
     transporte…). El motor SOLO lee esas claves; cualquier atributo de la persona
     (familia, hijos, origen, género, religión…) que llegue en `preferencias` es
     IGNORADO — no está en la whitelist, no puede mover el score.
  2. Las `razones` son DATO + FUENTE ("no juzgamos, medimos y citamos"), nunca veredictos
     de idoneidad ("barrio familiar", "para ti"). Verificable con fair_housing.es_limpio().

Puro: sin I/O, sin DB, sin LLM. Determinístico → auditable y testeable al 100%. La
captura de `preferencias` desde la conversación (LLM → schema fijo) es una capa aparte;
este módulo solo consume el schema ya poblado.
"""
from __future__ import annotations

import math
import unicodedata

# ── Whitelist CERRADA de dimensiones de NECESIDAD declarable ────────────────────────
# Agregar una dimensión aquí es una decisión consciente. NADA fuera de esta lista puede
# influir en el encaje: es la barrera estructural de Fair Housing. Toda dimensión es una
# NECESIDAD (algo que el inmueble tiene/no tiene), jamás un rasgo de la persona.
DIMENSIONES: tuple[str, ...] = (
    "tipo_inmueble",    # texto — QUÉ pidió (departamento/casa/oficina/local comercial/quinta)
    "tranquilidad",     # bool — quiere ruido bajo
    "caminable",        # bool — quiere poder resolver a pie
    "transporte",       # bool — quiere estar cerca de transporte masivo
    "area_verde",       # bool — quiere verde/parque cerca
    "presupuesto_max",  # número — tope de precio (misma unidad que el precio del inmueble)
    "dormitorios",      # int — los dormitorios que pidió (EXACTOS, no "N o más")
    "acepta_mascotas",  # bool — necesita que acepten mascotas
)

# Peso por dimensión en el promedio ponderado. Presupuesto pesa más: estar sobre el tope
# es una necesidad dura, no un matiz. El resto, equitativo (transparencia sobre finura).
# El TIPO pesa como los demás A PROPÓSITO: no necesita peso extra porque incumplirlo TOPA
# el score (ver _REQUISITOS_DUROS), y entre las tarjetas que sí se muestran es una constante
# (todas son del tipo pedido) — subirle el peso solo diluiría a las dimensiones que de
# verdad diferencian una opción de otra, achatando el número que la persona lee.
_PESOS: dict[str, float] = {
    "presupuesto_max": 1.5,
    "tipo_inmueble": 1.0, "tranquilidad": 1.0, "caminable": 1.0, "transporte": 1.0,
    "area_verde": 1.0, "dormitorios": 1.0, "acepta_mascotas": 1.0,
}

# ── REQUISITOS DUROS (arreglo del fallo 2, BATALLA_Hiinmo 2026-07-31) ────────────────
# Hay necesidades que NO son un matiz ponderable: si el usuario pidió un DEPARTAMENTO, una
# casa no encaja "un poco menos" — no es lo que pidió. Un promedio ponderado, por más peso
# que le dé al tipo, siempre puede diluir el incumplimiento con las otras dimensiones (en
# vivo: una casa de 4 dormitorios coronada con "100% encaje contigo" ante una consulta de
# "departamento de 2 dormitorios"). Por eso el incumplimiento de un requisito duro TOPA el
# score: nunca puede parecer un buen encaje.
# El tope está DEBAJO del umbral con que chat.py recorta el panel de tarjetas
# (_ENCAJE_MIN_GRID), para que un inmueble del tipo equivocado salga del panel salvo que no
# haya nada más que mostrar — y si se muestra, se muestre con su número honesto.
_REQUISITOS_DUROS: frozenset[str] = frozenset({"tipo_inmueble"})
_TOPE_REQUISITO_DURO = 49

_RUIDO_S = {"BAJO": 1.0, "MEDIO": 0.5, "ALTO": 0.0}


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


# Coerción defensiva: la señal puede venir de un LLM o de un scraper (string, NaN, bool
# donde se esperaba número). Lo no coaccionable → None = "sin dato": el motor NUNCA
# revienta ni finge un dato; degrada honestamente. Núcleo Fair-Housing = jamás crashea.
def _num(v):
    """A float finito. Rechaza bool (True==1 no es un número declarado), NaN/inf y basura.
    Acepta int/float/Decimal/str numérica — las señales pueden venir como Decimal de PostGIS
    o como string de un scraper/LLM."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v.strip() if isinstance(v, str) else v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


_BOOL_TRUE = {"true", "si", "sí", "yes", "y", "t", "1"}
_BOOL_FALSE = {"false", "no", "n", "f", "0"}


def _bool(v):
    """A bool real. Strings ambiguas ('no', 'false') se mapean bien; lo demás → None."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in _BOOL_TRUE:
            return True
        if s in _BOOL_FALSE:
            return False
    return None


# Sinónimos que apuntan al mismo tipo de inmueble. El catastro guarda un enum corto
# ('Departamento', 'Casa', 'Local Comercial', 'Oficina', 'Quinta') y el extractor emite ese
# mismo enum, pero normalizamos por si un dato heredado o un scraper trae la variante larga.
_ALIAS_TIPO = {
    "depto": "departamento", "depa": "departamento", "apartamento": "departamento",
    "local": "local comercial", "casa de campo": "quinta",
}


def normalizar_tipo(v) -> str | None:
    """Tipo de inmueble a su forma canónica comparable (sin tildes, minúsculas, sin
    espacios de más). None si no es un texto con contenido → 'sin dato'."""
    if not isinstance(v, str):
        return None
    s = " ".join(v.strip().lower().split())
    if not s:
        return None
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return _ALIAS_TIPO.get(s, s)


def estado_presupuesto(tope, precio) -> dict | None:
    """DENTRO o SOBRE el tope, con el exceso YA calculado. Fuente ÚNICA de esa aritmética.

    La usan el scorer de presupuesto (razón de la tarjeta) y el bloque autoritativo que ve
    el modelo, para que la frase del chat y la de la tarjeta NO puedan divergir. El modelo
    tiene PROHIBIDO hacer esta resta por su cuenta (en vivo afirmó que $710 estaba "dentro
    de tu presupuesto de $700"): recibe el veredicto ya hecho.
    Devuelve {dentro, exceso, precio, tope, etiqueta} o None si falta un dato comparable.
    """
    p, t = _num(precio), _num(tope)
    if p is None or t is None or t <= 0:
        return None
    exceso = p - t
    return {
        "dentro": exceso <= 0,
        "exceso": max(0.0, exceso),
        "precio": p,
        "tope": t,
        "etiqueta": (f"dentro de tu tope de ${int(t):,}" if exceso <= 0
                     else f"sobre tu tope por ${int(round(exceso)):,}"),
    }


def _nivel(s: float) -> str:
    """Nivel cualitativo de satisfacción de una dimensión (para ícono en el frontend)."""
    return "alto" if s >= 0.8 else "parcial" if s >= 0.4 else "bajo"


def _razon(dimension, cumple, s, texto, fuente=None, aporta=True):
    """Una línea explicable del encaje: dato + fuente, nunca veredicto de idoneidad."""
    return {"dimension": dimension, "cumple": cumple, "s": s,
            "texto": texto, "fuente": fuente, "aporta": aporta}


# ── Scorers por dimensión ───────────────────────────────────────────────────────────
# Cada uno recibe (valor_declarado, inmueble) y devuelve una razón. `aporta=False` marca
# "sin dato": la dimensión se declaró pero el inmueble no tiene la señal → se explica al
# usuario pero NO entra al promedio (no castigamos ni premiamos lo que no sabemos).

# Género gramatical del tipo, para que la razón se lea en español natural ("es una casa,
# no un departamento"). Cualquier tipo desconocido cae al masculino.
_TIPO_FEMENINO = {"casa", "quinta", "oficina", "bodega"}


def _un(tipo: str) -> str:
    return "una" if tipo in _TIPO_FEMENINO else "un"


def _score_tipo_inmueble(decl, inm) -> dict:
    """REQUISITO DURO: o es el tipo que pidió, o no lo es. Sin grises (ver _REQUISITOS_DUROS)."""
    pedido, tiene = normalizar_tipo(decl), normalizar_tipo(inm.get("tipo_activo"))
    if pedido is None or tiene is None:
        return _razon("tipo_inmueble", "sin_dato", None,
                      "Pediste un tipo de inmueble · sin dato de tipo aquí", None, aporta=False)
    if pedido == tiene:
        return _razon("tipo_inmueble", "alto", 1.0,
                      f"Es {_un(pedido)} {pedido}, como pediste", "ficha del inmueble")
    return _razon("tipo_inmueble", "bajo", 0.0,
                  f"Es {_un(tiene)} {tiene}, no {_un(pedido)} {pedido}", "ficha del inmueble")


def _score_tranquilidad(_decl, inm) -> dict:
    ruido = inm.get("ruido")
    ruido = ruido.upper() if isinstance(ruido, str) else ruido  # BAJO/MEDIO/ALTO, tolerante a caja
    if ruido not in _RUIDO_S:
        return _razon("tranquilidad", "sin_dato", None,
                      "Buscabas tranquilidad · sin dato de ruido aquí", None, aporta=False)
    s = _RUIDO_S[ruido]
    return _razon("tranquilidad", _nivel(s), s,
                  f"Buscabas tranquilidad · ruido estimado {ruido.lower()}", "estimación por sector")


# Procedencia de la caminabilidad, traducida del valor que guarda
# activos_inmutables.walk_score_fuente. Hasta el 2026-08-24 este scorer afirmaba
# "OpenStreetMap" para TODOS los inmuebles, sin consultar nada: cuando Overpass no
# respondía y el score quedaba en la estimación por zona, el motor seguía reclamando
# una medición que no existía. La ficha del anuncio (routers/assets._scores_fuente) ya
# distinguía bien desde su lado, así que el mismo activo daba dos verdades distintas
# según por dónde se mirara. Es el P0 de procedencia de la auditoría.
_FUENTE_CAMINABLE = {
    "osm": "OpenStreetMap",        # contada sobre comercios reales
    "heuristico": "estimación por zona",
}
# Sin procedencia registrada no se afirma medición: se degrada a estimación, que es el
# lado seguro. Coincide con la regla que ya sigue el alta de activos
# (routers/assets.create_asset: "origen opaco del payload → el anuncio degrada a
# estimación").
_FUENTE_CAMINABLE_DESCONOCIDA = "estimación por zona"


def _score_caminable(_decl, inm) -> dict:
    ws = _num(inm.get("walk_score"))
    if ws is None:
        return _razon("caminable", "sin_dato", None,
                      "Buscabas caminable · sin caminabilidad calculada aquí", None, aporta=False)
    s = _clamp01(ws / 100)
    fuente = _FUENTE_CAMINABLE.get(
        (inm.get("walk_score_fuente") or "").strip().lower(),
        _FUENTE_CAMINABLE_DESCONOCIDA,
    )
    return _razon("caminable", _nivel(s), s,
                  f"Buscabas caminable · caminabilidad {int(ws)}/100", fuente)


def _score_transporte(_decl, inm) -> dict:
    mins = _num(inm.get("transporte_min"))  # minutos a pie al transporte masivo más cercano
    if mins is None:
        return _razon("transporte", "sin_dato", None,
                      "Buscabas transporte cerca · sin dato de transporte aquí", None, aporta=False)
    s = (1.0 if mins <= 10 else 0.75 if mins <= 15 else 0.5 if mins <= 25
         else 0.25 if mins <= 35 else 0.1)
    return _razon("transporte", _nivel(s), s,
                  f"Buscabas transporte cerca · masivo a ~{int(mins)} min a pie", "mapa")


def _score_area_verde(_decl, inm) -> dict:
    # Preferimos el parque concreto (min a pie); si no, la cobertura vegetal del sector.
    pmin = _num(inm.get("parque_min"))
    if pmin is not None:
        s = (1.0 if pmin <= 5 else 0.7 if pmin <= 10 else 0.4 if pmin <= 20 else 0.2)
        return _razon("area_verde", _nivel(s), s,
                      f"Buscabas verde · parque a ~{int(pmin)} min a pie", "mapa")
    veg = _num(inm.get("vegetacion"))
    if veg is not None:
        s = _clamp01(veg / 100)
        return _razon("area_verde", _nivel(s), s,
                      f"Buscabas verde · cobertura vegetal ~{int(veg)}%", "estimación por sector")
    return _razon("area_verde", "sin_dato", None,
                  "Buscabas verde · sin dato de áreas verdes aquí", None, aporta=False)


def _score_presupuesto(decl, inm) -> dict:
    est = estado_presupuesto(decl, inm.get("precio"))
    if est is None:
        return _razon("presupuesto_max", "sin_dato", None,
                      "Diste un presupuesto · sin precio comparable aquí", None, aporta=False)
    precio, tope = est["precio"], est["tope"]
    if est["dentro"]:
        return _razon("presupuesto_max", "alto", 1.0,
                      f"Dentro de tu presupuesto (${int(precio):,} ≤ ${int(tope):,})", "precio publicado")
    exceso = est["exceso"] / tope
    s = 0.4 if exceso <= 0.05 else 0.15 if exceso <= 0.15 else 0.0
    # El EXCESO EN DÓLARES va en el texto (antes solo iban los dos precios). Es el número que
    # el modelo tiene prohibido calcular por su cuenta y que en vivo tradujo a "justo en tu
    # tope" para un $710 contra un tope de $700 (fallo 4).
    return _razon("presupuesto_max", _nivel(s), s,
                  f"Sobre tu tope por ${int(round(est['exceso'])):,} "
                  f"(${int(precio):,} vs ${int(tope):,})", "precio publicado")


def _score_dormitorios(decl, inm) -> dict:
    """Los dormitorios que pidió, tomados LITERAL. "2 dormitorios" es 2 — no "2 o más".

    Fallo 2 de BATALLA_Hiinmo (2026-07-31): el motor leía el número como un mínimo y le
    escribía al usuario "Cumple tus 2+ dormitorios (4)" cuando nadie había dicho "2+".
    Tener de más tampoco es lo pedido (es otro inmueble, y normalmente otro precio): puntúa
    PARCIAL y lo dice, en vez de coronarlo como coincidencia perfecta.
    """
    d = _num(inm.get("num_dormitorios"))
    decl = _num(decl)
    if d is None or decl is None or decl <= 0:
        return _razon("dormitorios", "sin_dato", None,
                      "Pediste un número de dormitorios · sin dato aquí", None, aporta=False)
    d, decl = int(d), int(decl)
    if d == decl:
        s, txt = 1.0, f"Tiene los {decl} dormitorios que pediste"
    elif d > decl:
        s, txt = 0.6, f"Tiene {d} dormitorios, pediste {decl}"
    elif d == decl - 1:
        s, txt = 0.4, f"Tiene {d} dormitorio(s), pediste {decl}"
    else:
        s, txt = 0.0, f"Tiene {d} dormitorio(s), pediste {decl}"
    return _razon("dormitorios", _nivel(s), s, txt, "ficha del inmueble")


def _score_acepta_mascotas(_decl, inm) -> dict:
    am = _bool(inm.get("acepta_mascotas"))
    if am is None:
        return _razon("acepta_mascotas", "sin_dato", None,
                      "Necesitas que acepten mascotas · sin dato aquí", None, aporta=False)
    s = 1.0 if am else 0.0
    return _razon("acepta_mascotas", _nivel(s), s,
                  "Acepta mascotas" if am else "No acepta mascotas", "ficha del inmueble")


_SCORERS = {
    "tipo_inmueble": _score_tipo_inmueble,
    "tranquilidad": _score_tranquilidad,
    "caminable": _score_caminable,
    "transporte": _score_transporte,
    "area_verde": _score_area_verde,
    "presupuesto_max": _score_presupuesto,
    "dormitorios": _score_dormitorios,
    "acepta_mascotas": _score_acepta_mascotas,
}


def _dims_declaradas(preferencias: dict) -> list[str]:
    """Dimensiones DECLARADAS y activas, en el orden canónico de DIMENSIONES.

    Solo mira claves de la whitelist (Fair Housing: lo demás se ignora). Para las bool,
    'declarada' = presente y truthy (declarar False = 'no me importa' → no puntúa). Para
    las numéricas (presupuesto/dormitorios), 'declarada' = presente y no-None. Para
    tipo_inmueble, 'declarada' = un texto con contenido reconocible.
    """
    prefs = preferencias or {}
    out = []
    for dim in DIMENSIONES:
        if dim not in prefs:
            continue
        val = prefs[dim]
        if dim in ("presupuesto_max", "dormitorios"):
            n = _num(val)               # nº válido y POSITIVO: un tope de 0 (o basura) no
            if n is not None and n > 0:  # es una necesidad declarable → se ignora.
                out.append(dim)
        elif dim == "tipo_inmueble":
            if normalizar_tipo(val):         # texto con contenido; lo demás no es una necesidad
                out.append(dim)
        elif val:  # bool truthy
            out.append(dim)
    return out


def peso_de(dimensiones) -> float:
    """Peso total de un conjunto de dimensiones. Fuente ÚNICA de esa suma — la usan el
    promedio del encaje y la COBERTURA, para que no puedan divergir."""
    return sum(_PESOS[d] for d in (dimensiones or []) if d in _PESOS)


def calcular_encaje(preferencias: dict, inmueble: dict) -> dict:
    """Encaje 0-100 de `inmueble` con las necesidades DECLARADAS en `preferencias`.

    Devuelve {score, cobertura, razones, dimensiones_declaradas, dimensiones_evaluadas,
    duros_incumplidos}:
      - score: int 0-100, o None si no hay NADA que puntuar honestamente (ninguna
        preferencia declarada, o ninguna con señal disponible en el inmueble). None ≠ 0:
        "no sé" no es "no encaja" — el frontend no debe pintar un "0%" falso.
      - cobertura: 0.0-1.0 — qué FRACCIÓN DEL PESO declarado se pudo evaluar de verdad.
        Es el `n` del score: un 100% sobre una sola dimensión de seis declaradas NO es
        comparable con un 75% sobre las seis. El score solo dice qué tan bien calza lo
        que sabemos; la cobertura dice cuánto sabemos. Sin ella, el promedio ponderado
        PREMIA LA FICHA INCOMPLETA (un inmueble sin ruido/caminabilidad/parque puntúa
        sobre uno bien documentado, porque se le promedia solo lo bueno que sí tiene) —
        y con eso el sistema le enseña al corredor que hidratar mal conviene.
        Quién la usa: `app.orden.ordenar_candidatos` (para el ORDEN, no para el número).
      - razones: lista explicable (dato + fuente). Incluye las 'sin_dato' (aporta=False)
        para ser honestos sobre lo que no sabemos, sin que afecten el número.
      - duros_incumplidos: las dimensiones de _REQUISITOS_DUROS que el inmueble NO cumple
        (hoy: pediste departamento y esto es una casa). Si hay alguna, el score va TOPADO
        a _TOPE_REQUISITO_DURO: no es lo que pediste, no puede lucir como un buen encaje.

    El promedio es ponderado SOLO sobre las dimensiones con señal (aporta=True): no
    castigamos ni premiamos lo que el inmueble no reporta. El precio de esa honestidad es
    que el número sube al bajar la evidencia — por eso `cobertura` viaja SIEMPRE con él.
    """
    declaradas = _dims_declaradas(preferencias)
    razones = [_SCORERS[dim](preferencias.get(dim), inmueble or {}) for dim in declaradas]
    evaluadas = [r for r in razones if r["aporta"]]
    duros = [r["dimension"] for r in evaluadas
             if r["dimension"] in _REQUISITOS_DUROS and r["s"] <= 0]

    if not evaluadas:
        return {"score": None, "cobertura": 0.0, "razones": razones,
                "duros_incumplidos": duros,
                "dimensiones_declaradas": declaradas, "dimensiones_evaluadas": []}

    num = sum(r["s"] * _PESOS[r["dimension"]] for r in evaluadas)
    den = sum(_PESOS[r["dimension"]] for r in evaluadas)
    score = max(0, min(100, round(100 * num / den)))
    if duros:
        score = min(score, _TOPE_REQUISITO_DURO)
    peso_declarado = peso_de(declaradas)
    return {
        "score": score,
        "cobertura": _clamp01(den / peso_declarado) if peso_declarado > 0 else 0.0,
        "razones": razones,
        "duros_incumplidos": duros,
        "dimensiones_declaradas": declaradas,
        "dimensiones_evaluadas": [r["dimension"] for r in evaluadas],
    }


def delta_encaje(preferencias: dict, inmueble_a: dict, inmueble_b: dict) -> dict:
    """El DELTA del modo COMPARAR: dónde gana cada inmueble en lo que al usuario le importa.

    No un "82% vs 76%" frío (docs/SPEC_Mapa_Vivo.md): el trade-off dimensión por dimensión.
    Devuelve {a, b, dimensiones:[{dimension, gana, ...}]} — 'gana' ∈ a|b|empate|sin_dato.
    """
    ea = calcular_encaje(preferencias, inmueble_a)
    eb = calcular_encaje(preferencias, inmueble_b)
    ra = {r["dimension"]: r for r in ea["razones"]}
    rb = {r["dimension"]: r for r in eb["razones"]}

    dims = []
    for dim in _dims_declaradas(preferencias):
        a, b = ra.get(dim), rb.get(dim)
        sa = a["s"] if a and a["aporta"] else None
        sb = b["s"] if b and b["aporta"] else None
        if sa is None or sb is None:
            gana = "sin_dato"
        elif abs(sa - sb) < 1e-9:
            gana = "empate"
        else:
            gana = "a" if sa > sb else "b"
        dims.append({
            "dimension": dim, "gana": gana,
            "a_s": sa, "b_s": sb,
            "a_texto": a["texto"] if a else None,
            "b_texto": b["texto"] if b else None,
        })
    return {"a": {"score": ea["score"]}, "b": {"score": eb["score"]}, "dimensiones": dims}
