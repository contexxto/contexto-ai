"""
El REPARTO del embudo — el CRM deja de contar solo a los sobrevivientes.

`tool_stats_embudo` le decía al corredor "tienes 12 interesados" y eran 12 **de los que
el sistema pudo atribuir**: los que conversaron y quedaron ligados a uno de sus
inmuebles. Quien llegó a su ficha y se fue sin escribir no estaba en ninguna parte — ni
como lead, ni como número, ni como nota al pie.

Y lo incómodo es que ese número **pasaba todos los guardrails**. `cifras_no_respaldadas`
verifica que una cifra narrada tenga respaldo en la tool: lo tenía. `_reframe_fail_close`
caza cifras de cartera inventadas: no estaba inventada. Era una cifra **verdadera sobre
un universo silenciosamente truncado** — una clase que ningún detector de texto puede
cazar, porque no hay nada mal escrito.

El arreglo no es pedir cuidado: es que el sistema deje de reportar UN número y reporte el
reparto. Mismo movimiento que hizo el encaje al viajar con su cobertura.

── La ventana, que es la parte honesta ─────────────────────────────────────────────
El registro de llegadas (`visita`) nació con F0. Para todo lo anterior **no hay dato**, y
"0 se fueron sin escribir" sería mentira, no un cero. Por eso el reparto declara SIEMPRE
desde cuándo mide, y cuando no hay registro no muestra ceros: dice que no hay registro.
Es la misma regla que `encaje.score = None` — "no sé" no es "no pasó".

Puro: sin I/O, sin DB, sin LLM. Determinístico → auditable y testeable al 100%.
"""
from __future__ import annotations

# Lo que el corredor DEBE leer junto a cualquier cifra de cartera. Se entrega redactado,
# no se le pide al modelo que lo componga — mismo criterio que el conteo de presupuesto
# de `encaje_contexto._conteo_presupuesto`, que se escribió así justo porque pedirlo en
# el prompt no bastaba.
_SIN_REGISTRO = ("Todavía no hay registro de llegadas a tus fichas, así que no se puede "
                 "decir cuántas personas entraron y se fueron sin escribir.")


def _n(v) -> int:
    """Entero no negativo. Defensivo: los conteos vienen de SQL y pueden llegar None."""
    if isinstance(v, bool) or v is None:
        return 0
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 0
    return max(0, n)


def componer_reparto(*, llegadas=0, sesiones_que_llegaron=0, interesados=0,
                     piden_corredor=0, desde: str | None = None) -> dict:
    """El embudo completo de UN corredor, con su ventana declarada.

    `interesados` son los que el CRM ya contaba (dispositivos que conversaron y quedaron
    atribuidos a sus inmuebles). Lo nuevo son los dos escalones de arriba.

    `se_fueron_sin_escribir` se calcula solo si hay registro Y no queda negativo: las dos
    fuentes se cuentan distinto (`visita` cuenta sesiones, el embudo dedupe por
    dispositivo), y un negativo significaría que la resta no aplica — se omite en vez de
    inventar una explicación.
    """
    lleg, ses = _n(llegadas), _n(sesiones_que_llegaron)
    inter, hand = _n(interesados), _n(piden_corredor)

    if lleg == 0 and ses == 0:
        return {
            "hay_registro": False,
            "interesados": inter,
            "piden_corredor": hand,
            "desde": desde,
            "_frase_obligatoria": _SIN_REGISTRO,
            "_proveniencia": ("'interesados' son DISPOSITIVOS que conversaron, no personas: "
                              "el mismo humano en el teléfono y en el portátil cuenta dos veces."),
        }

    perdidos = ses - inter
    reparto = {
        "hay_registro": True,
        "llegadas": lleg,
        "sesiones_que_llegaron": ses,
        "interesados": inter,
        "piden_corredor": hand,
        "desde": desde,
        "_proveniencia": ("'llegadas' son visitas a tus fichas (incluye el escaneo de un QR "
                          "aunque no escriban). 'interesados' son DISPOSITIVOS que conversaron, "
                          "no personas. Ambos se cuentan distinto, así que no se restan a ciegas."),
    }
    if perdidos >= 0:
        reparto["se_fueron_sin_escribir"] = perdidos
    reparto["_frase_obligatoria"] = frase_del_reparto(reparto)
    return reparto


def frase_del_reparto(reparto: dict) -> str:
    """La frase que el corredor tiene que leer, ya redactada.

    No se le pide al modelo que la componga: se le entrega. Es la lección de todo el
    proyecto — una instrucción en el prompt no es un control.
    """
    if not (reparto or {}).get("hay_registro"):
        return _SIN_REGISTRO

    ses = _n(reparto.get("sesiones_que_llegaron"))
    inter = _n(reparto.get("interesados"))
    hand = _n(reparto.get("piden_corredor"))
    desde = reparto.get("desde")
    ventana = f" (desde el {desde})" if desde else ""

    partes = [f"{ses} llegaron a tus fichas{ventana}", f"{inter} conversaron"]
    if hand:
        partes.append(f"{hand} pidieron corredor")

    frase = "DE CADA CIFRA DE CARTERA, DI TAMBIÉN EL REPARTO: " + " · ".join(partes) + "."
    perdidos = reparto.get("se_fueron_sin_escribir")
    if isinstance(perdidos, int) and perdidos > 0:
        frase += (f" {perdidos} entraron y se fueron sin escribir: eso NO se omite, es la "
                  f"mitad del embudo que antes no se veía.")
    return frase
