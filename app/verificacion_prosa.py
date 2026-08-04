"""
La prosa ya escrita, medida contra lo que el motor calculó — el gemelo de SALIDA.

── Por qué existe (BATALLA_Hiinmo_vs_Contexto, 2026-07-31) ───────────────────────────────
`encaje_contexto.bloque_autoritativo` resolvió la mitad de ENTRADA de la frontera motor↔prosa:
el modelo ya recibe el ranking, los conteos y las frases obligatorias ANTES de escribir. Pero
recibir no es obedecer, y el propio informe lo dejó anotado: la prohibición "se respetaba en la
lista numerada y se rompía tres párrafos después" ($710 descrito como "justo en tu tope"). Un
prompt es una petición; no es una garantía.

Este módulo cierra el bucle por el otro lado. Toma el texto que el modelo YA escribió y las
MISMAS tarjetas que la persona verá, y responde una sola pregunta: **¿la prosa afirma algo que
el motor no respalda?** Es el patrón del que GeoSQL (dekart-xyz, MIT) saca su mejora: el agente
no valida el SQL, valida el MAPA RENDERIZADO, porque el bucle solo-texto no ve lo que salta a la
vista. Aquí el artefacto renderizado es la respuesta en pantalla.

Hoy esto INFORMA, no bloquea (ver `routers/chat.py`): primero hay que saber con qué frecuencia
la prosa desobedece. Hacer cumplir sin esa cifra es apostar el turno de un usuario real a una
corazonada. La función es la misma para las tres bocas: instrumento en vivo, aserción
determinista del eval y test de regresión.

── Precisión por encima de cobertura ─────────────────────────────────────────────────────
Cada chequeo se ancla a un dato duro (un precio del panel, una dirección de una tarjeta, el
tope declarado) y prefiere callar antes que gritar de más: esto alimenta un eval que aspira a
ser gate de CI, y un falso positivo que rompe el build enseña a ignorar al guardián. Por eso
NO se compara el conteo crudo de la prosa contra el del panel: "3 de las 4 entran en tu tope"
es una partición legítima, y distinguirla de una invención pide criterio, no regex. Lo que sí
se denuncia es la afirmación COLECTIVA falsa ("4 opciones que encajan con tu presupuesto"
cuando una se pasa), que fue el fallo real y no tiene lectura honesta.

Puro (texto + tarjetas → violaciones): sin I/O, sin LLM, determinístico y testeable. La
aritmética de presupuesto sale de `encaje.estado_presupuesto` — la misma fuente única que usan
la tarjeta y el bloque autoritativo — para que las tres no puedan decir cosas distintas.
"""
from __future__ import annotations

import re
import unicodedata

from app.encaje import estado_presupuesto

ALTA = "alta"
MEDIA = "media"

# Montos en prosa: "$710", "$1.130", "710 dólares", "150 mil", "1,4 millones".
_MONTO = re.compile(r"\$\s?(\d[\d.,]*)|(\d[\d.,]*)\s*(?:d[óo]lares|usd)\b", re.I)
_ESCALA = re.compile(r"^\s*(mil|k\b|millones|mill[óo]n)", re.I)

# Las frases con las que el modelo ABLANDA un exceso. Salen literales del bloque autoritativo
# (que ya las prohíbe) y de la repro en vivo. Se buscan SOLO en la misma frase que un precio que
# de verdad se pasa del tope: dicha de un inmueble que sí entra, "dentro de tu presupuesto" es
# la frase correcta.
_SUAVIZANTES = re.compile(
    r"(justo (en|dentro de) (tu|el) tope|justo tu tope|casi (en )?(tu|el) tope"
    r"|pr[áa]cticamente (lo mismo|igual|tu tope)|dentro de (tu|el) (tope|presupuesto)"
    r"|entra en (tu|el) (tope|presupuesto)|encaja con tu presupuesto"
    r"|se ajusta a tu presupuesto|✅)", re.I)

# Si el modelo dijo la verdad sobre ese mismo precio en la misma frase, cumplió: el bloque le
# exige "se pasa $X de tu tope" cada vez que lo nombre. Estas marcas desactivan el chequeo.
_HONESTAS = re.compile(
    r"(se pasa|sobre (tu|el) tope|por encima|excede|se excede|supera|no entra|fuera de (tu|el) "
    r"(tope|presupuesto)|m[áa]s de tu tope)", re.I)

# La afirmación COLECTIVA de que todo el panel entra en el presupuesto.
_COLECTIVO_ENTRA = re.compile(
    r"((todas?|todos)\s+(las?|los)?\s*\w*\s*(entran|est[áa]n|caen|encajan)\s+"
    r"(en|dentro de|con)\s+(tu|el)\s+(tope|presupuesto)"
    r"|\d{1,2}\s+(opciones?|alternativas?|departamentos?|deptos?|casas?|inmuebles?|propiedades?|"
    r"suites?)\s+(que\s+)?(encajan|entran|est[áa]n|caben)\s+(en|dentro de|con)\s+(tu|el)\s+"
    r"(tope|presupuesto)"
    r"|\d{1,2}\s+(opciones?|alternativas?|departamentos?|deptos?|casas?|inmuebles?|propiedades?|"
    r"suites?)\s+dentro de (tu|el) (tope|presupuesto))", re.I)

_VINETA = re.compile(r"^\s*(?:\d{1,2}[.)]|[-*•])\s+")
_NUMERADA = re.compile(r"^\s*(\d{1,2})[.)]\s+")
_LIMITES = ".;\n•!?"


# ── Utilidades ────────────────────────────────────────────────────────────────────────────
def _sin_tildes(s: str) -> str:
    base = unicodedata.normalize("NFD", (s or "").lower())
    return re.sub(r"\s+", " ", "".join(c for c in base if not unicodedata.combining(c))).strip()


def _fragmento(texto: str, pos: int) -> str:
    """La frase que contiene `pos`. Acotar a la frase (y no a una ventana de N caracteres) es
    lo que evita el falso positivo clásico: «los otros tres están dentro de tu presupuesto; el
    de $710 se pasa $10» — dos afirmaciones honestas que una ventana ciega mezclaría."""
    ini = max((texto.rfind(ch, 0, pos) for ch in _LIMITES), default=-1)
    finales = [f for f in (texto.find(ch, pos) for ch in _LIMITES) if f != -1]
    return texto[ini + 1: min(finales) if finales else len(texto)].strip()


def _a_entero(crudo: str, cola: str) -> int | None:
    """'1.130' → 1130 · '150' + ' mil' → 150000. Los precios del catastro son enteros, así que
    los separadores se limpian sin ambigüedad de locale."""
    try:
        valor = float(re.sub(r"[.,]", "", crudo))
    except ValueError:
        return None
    escala = _ESCALA.match(cola)
    if escala:
        valor *= 1000 if escala.group(1).lower() in ("mil", "k") else 1_000_000
    return int(round(valor))


def _montos_en(texto: str) -> list[tuple[int, int]]:
    """Los montos de la prosa como (valor, posición)."""
    out = []
    for m in _MONTO.finditer(texto):
        crudo = m.group(1) or m.group(2)
        valor = _a_entero(crudo, texto[m.end():m.end() + 12])
        if valor is not None:
            out.append((valor, m.start()))
    return out


def _numeros_de(obj, profundidad: int = 0) -> set[int]:
    """Todo número que el agente PUDO ver en una tarjeta (precio, alícuota, área, distancias…).
    Sirve de coartada: solo se denuncia como inventada la cifra que no está en ninguna parte
    de los datos del turno."""
    if profundidad > 4:
        return set()
    if isinstance(obj, bool):
        return set()
    if isinstance(obj, (int, float)):
        return {int(round(obj))}
    if isinstance(obj, dict):
        return set().union(*(_numeros_de(v, profundidad + 1) for v in obj.values())) if obj else set()
    if isinstance(obj, (list, tuple)):
        return set().union(*(_numeros_de(v, profundidad + 1) for v in obj)) if obj else set()
    if isinstance(obj, str):
        return {int(n) for n in re.findall(r"\b\d{1,9}\b", obj)}
    return set()


def _tope_de(preferencias: dict | None) -> float | None:
    t = (preferencias or {}).get("presupuesto_max")
    if isinstance(t, bool) or not isinstance(t, (int, float)) or t <= 0:
        return None
    return float(t)


def _nombre(c: dict) -> str:
    return c.get("direccion") or c.get("tipo_activo") or ""


def _identifica(linea: str, cards: list[dict]) -> int | None:
    """¿De qué tarjeta habla esta línea? Por dirección, o por un precio que solo ella tiene."""
    plano = _sin_tildes(linea)
    for i, c in enumerate(cards):
        nombre = _sin_tildes(_nombre(c))
        if nombre and len(nombre) > 3 and nombre in plano:
            return i
    montos = {v for v, _ in _montos_en(linea)}
    for i, c in enumerate(cards):
        precio = c.get("precio")
        if precio is None or int(round(precio)) not in montos:
            continue
        if sum(1 for o in cards if o.get("precio") is not None
               and int(round(o["precio"])) == int(round(precio))) == 1:
            return i
    return None


def _violacion(codigo: str, gravedad: str, detalle: str, evidencia: str = "") -> dict:
    return {"codigo": codigo, "gravedad": gravedad, "detalle": detalle,
            "evidencia": (evidencia or "")[:200]}


# ── Los cinco chequeos ────────────────────────────────────────────────────────────────────
def _presupuesto_suavizado(reply: str, cards: list[dict], tope: float | None) -> list[dict]:
    """FALLO 4 en su forma literal: «$710, justo en tu tope» con tope de $700."""
    if tope is None:
        return []
    fuera = {int(round(c["precio"])): c for c in cards
             if c.get("precio") is not None
             and (estado_presupuesto(tope, c["precio"]) or {}).get("dentro") is False}
    if not fuera:
        return []
    vistos, out = set(), []
    for valor, pos in _montos_en(reply):
        if valor not in fuera or valor in vistos:
            continue
        frase = _fragmento(reply, pos)
        suave = _SUAVIZANTES.search(frase)
        if suave and not _HONESTAS.search(frase):
            vistos.add(valor)
            exceso = int(round(estado_presupuesto(tope, valor)["exceso"]))
            out.append(_violacion(
                "presupuesto_suavizado", ALTA,
                f"${valor:,} se pasa ${exceso:,} del tope de ${int(tope):,} y la prosa lo "
                f"presenta con «{suave.group(0)}»", frase))
    return out


def _encabezado_falso(reply: str, cards: list[dict], tope: float | None) -> list[dict]:
    """FALLO 4 en su forma más dañina: la frase que la persona lee PRIMERO. «4 departamentos
    que encajan con tu presupuesto de $700» — y uno costaba $710. Cada ítem podía estar bien
    marcado más abajo; el encabezado ya había mentido."""
    if tope is None:
        return []
    excedidas = [c for c in cards if c.get("precio") is not None
                 and (estado_presupuesto(tope, c["precio"]) or {}).get("dentro") is False]
    if not excedidas:
        return []
    m = _COLECTIVO_ENTRA.search(reply)
    if not m:
        return []
    precios = ", ".join(f"${int(round(c['precio'])):,}" for c in excedidas)
    return [_violacion(
        "encabezado_falso", ALTA,
        f"afirma que el conjunto entra en el tope de ${int(tope):,}, pero {len(excedidas)} "
        f"se pasa{'' if len(excedidas) == 1 else 'n'} ({precios})",
        _fragmento(reply, m.start()))]


def _cifra_sin_procedencia(reply: str, cards: list[dict], descartadas: list[dict],
                           tope: float | None) -> list[dict]:
    """El invento de dinero. Una cifra en dólares que no sale de ninguna tarjeta del turno, ni
    del tope, ni de una resta entre ellos, es una cifra que el modelo se inventó — y la
    proveniencia de las cifras ES el argumento del producto."""
    conocidos: set[int] = set()
    for c in list(cards) + list(descartadas):
        conocidos |= _numeros_de(c)
    precios = {int(round(c["precio"])) for c in list(cards) + list(descartadas)
               if c.get("precio") is not None}
    if tope is not None:
        precios.add(int(round(tope)))
        conocidos.add(int(round(tope)))
    # Restas legítimas: el exceso ("se pasa $10"), el margen ("te sobran $320"), la diferencia
    # entre dos opciones ("$170 más que la primera").
    conocidos |= {abs(a - b) for a in precios for b in precios}
    out = []
    for valor, pos in _montos_en(reply):
        if valor in conocidos or valor == 0:
            continue
        out.append(_violacion(
            "cifra_sin_procedencia", ALTA,
            f"${valor:,} no sale de ninguna tarjeta del turno, del tope ni de una resta entre ellos",
            _fragmento(reply, pos)))
    return out


def _descartada_ofrecida(reply: str, cards: list[dict], descartadas: list[dict]) -> list[dict]:
    """FALLO 1 al revés: el modelo listó como «opción 5» un inmueble que el panel había
    cortado. Ofrecer lo que no aparece en pantalla es prometer lo que no hay. Nombrarlas en UNA
    frase sí está permitido; ponerlas en una lista o viñeta, no — por eso solo miran las líneas
    con forma de ítem."""
    if not descartadas:
        return []
    out = []
    for linea in reply.splitlines():
        if not _VINETA.match(linea):
            continue
        idx = _identifica(linea, descartadas)
        if idx is None or _identifica(linea, cards) is not None:
            continue
        d = descartadas[idx]
        out.append(_violacion(
            "descartada_ofrecida", ALTA,
            f"«{_nombre(d) or 'una descartada'}» la cortó el motor y no está en pantalla, "
            f"pero la prosa la lista como ítem", linea.strip()))
    return out


def _orden_alterado(reply: str, cards: list[dict]) -> list[dict]:
    """FALLO 1: «te los ordeno por encaje» y entregó el orden exactamente invertido. Reordenar
    con criterio declarado es legítimo (para eso está tool_priorizar_opcion, que mueve TAMBIÉN
    la tarjeta); lo que rompe la confianza es que la lista numerada de la prosa no calce con la
    numeración que la persona tiene delante."""
    if len(cards) < 2:
        return []
    secuencia, etiquetas = [], []
    for linea in reply.splitlines():
        if not _NUMERADA.match(linea):
            continue
        idx = _identifica(linea, cards)
        if idx is not None:
            secuencia.append(idx)
            etiquetas.append(_nombre(cards[idx]) or f"#{idx + 1}")
    if len(secuencia) < 2 or secuencia == sorted(secuencia):
        return []
    # Sin flechas ni emoji en el `detalle`: este texto se imprime en la consola de Windows
    # (cp1252) cuando corre el eval, y un carácter fuera de esa tabla tumba el informe entero.
    return [_violacion(
        "orden_alterado", MEDIA,
        "la lista numerada de la prosa no sigue el orden del panel "
        f"(prosa: {' > '.join(etiquetas)})",
        " · ".join(f"{i}) {_nombre(c)}" for i, c in enumerate(cards, 1)))]


# ── La boca pública ───────────────────────────────────────────────────────────────────────
def verificar_prosa(reply: str, cards: list[dict] | None,
                    preferencias: dict | None = None,
                    descartadas: list[dict] | None = None) -> list[dict]:
    """¿Qué afirma la prosa que el motor no respalda?

    `cards` son EXACTAMENTE las que verá la persona, en su orden. Sin tarjetas no hay nada
    autoritativo contra qué medir (una pregunta de zona, un saludo) y se devuelve [] sin
    inventar juicios. Cada violación trae `codigo`, `gravedad`, `detalle` y la `evidencia`
    literal, para que el informe del eval señale la frase y no obligue a releer el turno.
    """
    cards = [c for c in (cards or []) if isinstance(c, dict)]
    if not reply or not cards:
        return []
    descartadas = [c for c in (descartadas or []) if isinstance(c, dict)]
    tope = _tope_de(preferencias)

    hallazgos = (
        _presupuesto_suavizado(reply, cards, tope)
        + _encabezado_falso(reply, cards, tope)
        + _cifra_sin_procedencia(reply, cards, descartadas, tope)
        + _descartada_ofrecida(reply, cards, descartadas)
        + _orden_alterado(reply, cards)
    )
    return sorted(hallazgos, key=lambda v: 0 if v["gravedad"] == ALTA else 1)


def resumen(violaciones: list[dict]) -> str:
    """Una línea para el log. Vacío si la prosa respetó al motor."""
    if not violaciones:
        return ""
    return " | ".join(f"{v['codigo']}({v['gravedad']}): {v['detalle']}" for v in violaciones)
