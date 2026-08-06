"""
Motor de ORDEN — en qué orden ve la persona los inmuebles candidatos.

Es la decisión más consecuente del producto (lo primero que se ve es lo que se
considera) y hasta ahora era un `sort` inline en chat.py: sin criterio escrito, sin
test propio y sin registro. Este módulo la vuelve explícita, pura y auditable, al
mismo nivel que `app/encaje.py` (cuánto encaja UNO) y `app/intencion.py` (qué tan
caliente está el lead).

── El criterio, en orden LÉXICO (no un score único) ────────────────────────────────
Un solo número siempre se puede compensar: un inmueble puede "comprar" posición
sumando en dimensiones menores lo que pierde en una crítica. Una jerarquía no.

  1. REQUISITOS DUROS cumplidos. Lo que no es lo que la persona pidió va después de
     todo lo que sí lo es. Hoy el motor ya TOPA su score (encaje._TOPE_REQUISITO_DURO)
     y el panel lo recorta (chat._ENCAJE_MIN_GRID); ponerlo como primera llave lo hace
     explícito y lo mantiene aunque esos umbrales cambien.
  2. ENCAJE AJUSTADO POR COBERTURA (ver abajo). Descendente.
  3. ESTABILIDAD. Todo lo demás preserva el orden de entrada (espacial/similitud). Sin
     desempates ocultos: si dos candidatos empatan en el criterio, empatan de verdad.

Y explícitamente NADA MÁS. Ni antigüedad de hidratación, ni identidad del corredor,
ni precio absoluto, ni "destacados". Si algún día hay inventario promocionado, va en
un carril separado y ROTULADO — nunca mezclado en este orden. Esa frontera es lo que
separa a Contexto de un portal, y se escribe ahora que no hay a quién promocionar.

── Por qué "ajustado por cobertura" ────────────────────────────────────────────────
`calcular_encaje` promedia SOLO las dimensiones con señal ("no castigamos lo que no
sabemos" — correcto y honesto). El efecto secundario en el ORDEN no lo es:

    A: sin ruido, sin caminabilidad, sin parque; solo precio, dentro del tope → 100
    B: ficha completa; dentro del tope, ruido medio, caminable 60, parque a 12 min → 75

A gana por NO tener datos. Y como el corredor ve el encaje, el sistema le enseña que
hidratar mal conviene — la economía implícita que el producto no quiere tener.

El arreglo NO toca el número que se muestra (sigue siendo el encaje honesto de lo que
se sabe). Solo el ORDEN usa el ajustado: el score se encoge hacia el punto NEUTRO
(50) en proporción a lo que NO se pudo evaluar.

    ajustado = score · cobertura + 50 · (1 − cobertura)

Propiedades que lo hacen defendible:
  · cobertura 1.0 → ajustado == score (la ficha completa no paga nada).
  · un 100 con cobertura 0.23 cae a ~61 — deja de coronar el panel sin desaparecer.
  · es SIMÉTRICO: un 20 con poca cobertura SUBE hacia 50. "No sé" tampoco puede
    hundir a nadie — la misma regla que ya hace que `score=None` no sea `0`.
  · el punto neutro es fijo (50), así que no depende del conjunto: el orden de dos
    candidatos no cambia porque aparezca un tercero.

Puro: sin I/O, sin DB, sin LLM. Determinístico → auditable y testeable al 100%.
"""
from __future__ import annotations

# Punto neutro hacia el que se encoge un score con poca evidencia. 50 = "ni encaja ni
# desencaja": es la única constante que no afirma nada sobre el inmueble.
_NEUTRO = 50.0


def _num(v):
    """A float finito, o None. Defensivo: la tarjeta puede venir de la DB (Decimal), de
    un LLM o de un historial viejo sin el campo. Rechaza bool (True==1 no es un score)."""
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f and f not in (float("inf"), float("-inf")) else None


def encaje_ajustado(encaje, cobertura) -> float | None:
    """El encaje encogido hacia el neutro según cuánta evidencia lo respalda.

    None si no hay encaje puntuable ("sin dato" no se convierte en un número aquí
    tampoco). Cobertura ausente se trata como 1.0: una tarjeta vieja o de un camino
    que aún no la calcula NO debe ser penalizada por un campo que no existía.
    """
    s = _num(encaje)
    if s is None:
        return None
    c = _num(cobertura)
    c = 1.0 if c is None else (0.0 if c < 0 else 1.0 if c > 1 else c)
    return s * c + _NEUTRO * (1.0 - c)


def _clave(card: dict) -> tuple:
    """Llave de orden léxica. Menor = va primero.

    Ordena por `encaje` TAL CUAL viene en la tarjeta — que es el número que la persona ve.
    El ajuste por evidencia ya se aplicó al construirla (chat._ajustar_a_entero), a
    propósito: si el orden usara un valor distinto del pintado, el carrusel se leería
    desordenado (un 78% antes de un 100%) y la promesa de "ordenado por encaje" se rompería
    en pantalla. Un solo número, una sola verdad.

    Las tarjetas sin encaje puntuable (None) van al FINAL de las que sí tienen número,
    pero nunca desaparecen ni se muestran como 0% — mismo contrato que ya tenía el sort
    de chat.py ("no sé" ≠ "no encaja").
    """
    duros = card.get("duros_incumplidos") or []
    enc = _num(card.get("encaje"))
    return (
        1 if duros else 0,                  # 1) requisitos duros primero
        1 if enc is None else 0,            #    sin dato, al final del bloque
        -(enc if enc is not None else 0.0),  # 2) mayor encaje visible primero
    )


def hay_algo_que_ordenar(cards) -> bool:
    """True solo si alguna tarjeta tiene encaje real.

    Sin ninguna preferencia declarada TODAS son None: ahí no se inventa un ranking, se
    preserva el orden espacial/similitud de la búsqueda tal cual (contrato heredado del
    sort de chat.py y cubierto por tests/test_orden_encaje.py).
    """
    return any(_num((c or {}).get("encaje")) is not None for c in (cards or []))


def ordenar_candidatos(cards: list[dict]) -> list[dict]:
    """Los candidatos en el orden en que la persona debe verlos. No muta la entrada.

    No-op (copia) si no hay nada que ordenar. El sort es ESTABLE: dos candidatos que
    empatan en el criterio conservan su orden relativo de entrada.
    """
    lista = list(cards or [])
    if not hay_algo_que_ordenar(lista):
        return lista
    return sorted(lista, key=_clave)


def explicar_orden(cards: list[dict]) -> list[dict]:
    """El REGISTRO AUDITABLE del orden: una fila por candidato, ya ordenado.

    Es la base para poder medir IMPACTO DISPAR más adelante (un criterio neutro que, al
    combinarse, produce una geografía sesgada — la doctrina de Fair Housing que
    `fair_housing.detectar_steering` NO puede ver, porque no produce ninguna frase).
    Esa medición necesita tráfico e inventario; el registro tiene que existir desde
    antes o el histórico no se puede reconstruir.

    Devuelve datos puros — persistirlos/loguearlos es decisión del caller.
    """
    return [
        {
            "posicion": i,
            "id": c.get("id"),
            "encaje": c.get("encaje"),            # el número visible = el que ordenó
            "encaje_medido": c.get("encaje_medido"),  # el crudo, antes de moderar
            "cobertura": c.get("encaje_cobertura"),
            "duros_incumplidos": list(c.get("duros_incumplidos") or []),
        }
        for i, c in enumerate(ordenar_candidatos(cards))
    ]
