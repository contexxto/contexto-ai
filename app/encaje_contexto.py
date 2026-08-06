"""
El ranking del motor, escrito para que el MODELO lo lea — contexto autoritativo del turno.

── Por qué existe (BATALLA_Hiinmo_vs_Contexto, 2026-07-30) ──────────────────────────────
En 3 corridas de la misma consulta el panel de tarjetas devolvió scores IDÉNTICOS (el motor
es determinístico) mientras la prosa cambió cada vez, y ninguna vez coincidió con el ranking:
prometía "te los ordeno por encaje" y entregaba el orden invertido, omitía su propia mejor
opción, y afirmaba que un inmueble de $710 estaba "dentro de tu presupuesto de $700".

La causa no era el modelo: era que el modelo NUNCA VEÍA lo que el motor había calculado. El
encaje se computaba DESPUÉS de que la respuesta estaba escrita, solo para pintar las tarjetas.
Este módulo cierra esa frontera: convierte las MISMAS tarjetas que verá la persona en un
bloque de texto que se añade al system prompt antes de que el modelo escriba.

Puro (tarjetas + preferencias → texto): sin I/O, sin LLM, determinístico y testeable. La
aritmética de presupuesto sale de `encaje.estado_presupuesto` — la misma fuente que la razón
de la tarjeta — para que el chat y la tarjeta NO puedan decir cosas distintas.
"""
from __future__ import annotations

from app.encaje import estado_presupuesto

_ARRIENDO = "arriendo"


def _es_arriendo(cards: list[dict], preferencias: dict) -> bool:
    """¿El turno habla de canon mensual? (decide si los montos llevan '/mes')."""
    op = (preferencias.get("operacion") or "").lower()
    if op:
        return op == _ARRIENDO
    ops = {(c.get("operacion") or "").lower() for c in cards}
    return ops == {_ARRIENDO}


def _monto(valor, por_mes: bool) -> str:
    if valor is None:
        return "precio no publicado"
    return f"${int(round(float(valor))):,}" + ("/mes" if por_mes else "")


def _nombre(c: dict) -> str:
    return c.get("direccion") or c.get("tipo_activo") or "Inmueble sin dirección"


# Etiquetas humanas de las necesidades declaradas, para que el modelo pueda repetirle a la
# persona QUÉ entendió el motor (y ella corregir si se leyó mal).
_ETIQUETAS = {
    "tipo_inmueble": lambda v: str(v),
    "operacion": lambda v: f"en {v}",
    "presupuesto_max": lambda v: f"tope ${int(round(float(v))):,}",
    "dormitorios": lambda v: f"{int(v)} dormitorio(s)",
    "tranquilidad": lambda _v: "tranquilidad",
    "caminable": lambda _v: "poder resolver a pie",
    "transporte": lambda _v: "transporte masivo cerca",
    "area_verde": lambda _v: "área verde cerca",
    "acepta_mascotas": lambda _v: "que acepten mascotas",
}


def _conteo_presupuesto(cards: list[dict], tope: float) -> list[str]:
    """El ENCABEZADO de conteo, ya redactado y con las cuentas hechas.

    Fallo 4 de BATALLA_Hiinmo, en su forma más terca: aun marcando bien cada ítem («⚠️ se pasa
    $10 de tu tope»), el modelo abría con «encontré 4 departamentos que encajan con tu
    presupuesto de $700» — y uno costaba $710. La frase de arriba es la que la persona lee
    primero y la que se le queda. Así que no se le pide al modelo que la componga: se la damos
    hecha, contada por el motor.
    """
    dentro = fuera = sin_precio = 0
    for c in cards:
        est = estado_presupuesto(tope, c.get("precio"))
        if est is None:
            sin_precio += 1
        elif est["dentro"]:
            dentro += 1
        else:
            fuera += 1
    n, monto = len(cards), f"${int(round(tope)):,}"
    if fuera and dentro:
        no_entran = "una no entra" if fuera == 1 else f"{fuera} no entran"
        return [
            f"CONTEO PARA TU ENCABEZADO — son {n} opciones: {dentro} dentro de tu tope de {monto} y "
            f"{fuera} que se pasa{'' if fuera == 1 else 'n'}.",
            f"Escríbelo con esa distinción. PROHIBIDO abrir con «{n} opciones que encajan con tu "
            f"presupuesto de {monto}»: {no_entran}.",
        ]
    if fuera and not dentro:
        return [f"CONTEO PARA TU ENCABEZADO — son {n} opciones y NINGUNA entra en tu tope de "
                f"{monto}. Dilo así, de frente, antes de mostrarlas."]
    if sin_precio and not dentro:
        return []  # sin precios comparables no hay conteo de presupuesto que afirmar
    return [f"CONTEO PARA TU ENCABEZADO — son {n} opciones y las {n} entran en tu tope de {monto}."]


def _necesidades(preferencias: dict) -> str:
    partes = []
    for clave, fmt in _ETIQUETAS.items():
        if clave in preferencias and preferencias[clave] not in (None, False, ""):
            try:
                partes.append(fmt(preferencias[clave]))
            except (TypeError, ValueError):  # dato raro → mejor omitirlo que romper el turno
                continue
    return " · ".join(partes)


def _sobre_cuanto(c: dict) -> list[str]:
    """SOBRE CUÁNTAS necesidades se calculó ese porcentaje — la evidencia detrás del número.

    Un 100% sobre una necesidad de seis y un 75% sobre las seis se leen igual en pantalla y
    NO son lo mismo. La tarjeta ya lo dice ("calculado sobre 3 de las 6 cosas que pediste");
    si el modelo no lo viera, escribiría "encaja perfecto contigo" al lado de una tarjeta que
    declara medio dato — exactamente la divergencia prosa↔tarjeta que este módulo existe para
    cerrar. Se calla cuando se midió todo: ahí el número no necesita asterisco.
    """
    ev, decl = c.get("encaje_evaluadas"), c.get("encaje_declaradas")
    # `bool` es subclase de `int` en Python: sin excluirlo, un True se cuela como conteo y
    # el bloque le dicta al modelo «calculado sobre True de las 6 cosas» (lo cazó el test).
    def _conteo(v) -> bool:
        return isinstance(v, int) and not isinstance(v, bool)

    if not _conteo(ev) or not _conteo(decl) or decl <= 0 or ev >= decl:
        return []
    return [f"MEDIDO SOBRE {ev} DE {decl} DE SUS NECESIDADES → di «calculado sobre {ev} de "
            f"las {decl} cosas que pediste»; PROHIBIDO «encaja perfecto/del todo contigo» y "
            f"afirmar lo que NO se midió (las razones de abajo son todo lo que se sabe)"]


def _linea_opcion(c: dict, tope, por_mes: bool) -> str:
    """Una opción del panel: nombre · monto · encaje · veredicto de presupuesto.

    Cuando se pasa del tope, la línea trae además LA FRASE QUE HAY QUE USAR y las que están
    prohibidas. Va pegada al dato a propósito: en la repro en vivo, la prohibición general
    del prompt se respetaba en la lista numerada y se rompía tres párrafos después ("$710,
    justo en tu tope"). La instrucción viaja con el número que la necesita.
    """
    trozos = [_nombre(c), _monto(c.get("precio"), por_mes)]
    enc = c.get("encaje")
    trozos.append(f"{enc}% de encaje" if enc is not None else "sin encaje puntuable")
    trozos += _sobre_cuanto(c)
    est = estado_presupuesto(tope, c.get("precio")) if tope else None
    if est:
        if est["dentro"]:
            trozos.append("DENTRO de tu tope")
        else:
            exceso = f"${int(round(est['exceso'])):,}"
            trozos.append(f"{est['etiqueta'].upper()} → di «se pasa {exceso} de tu tope» CADA vez "
                          f"que la nombres; PROHIBIDO «justo en tu tope», «casi tu tope», "
                          f"«prácticamente lo mismo» y el ✅")
    if c.get("duros_incumplidos"):
        trozos.append("NO ES EL TIPO QUE PIDIÓ")
    return " · ".join(trozos)


def bloque_autoritativo(cards: list[dict], preferencias: dict | None,
                        descartadas: list[dict] | None = None,
                        priorizado: tuple[str | None, str | None] = (None, None)) -> str:
    """Las tarjetas del turno → el bloque que el modelo recibe como verdad del turno.

    `cards` son EXACTAMENTE las que verá la persona, ya ordenadas. `descartadas` son las que
    el corte del panel dejó fuera: van nombradas para que el modelo sepa que existen y NO las
    ofrezca (si no las nombramos, puede recomendarlas de memoria y prometer algo invisible).
    Devuelve "" si no hay nada que declarar — un bloque vacío no debe ensuciar el prompt.
    """
    if not cards:
        return ""
    prefs = preferencias or {}
    por_mes = _es_arriendo(cards, prefs)
    tope = prefs.get("presupuesto_max")
    tope = float(tope) if isinstance(tope, (int, float)) and not isinstance(tope, bool) and tope > 0 else None

    out = [
        "════════ MOTOR DE ENCAJE · CONTEXTO AUTORITATIVO DE ESTE TURNO ════════",
        "Esto NO lo escribió el usuario. Son los números que el motor determinístico YA",
        "calculó y que la persona VERÁ en las tarjetas debajo de tu respuesta. Manda sobre",
        "tu criterio (regla 10 de tus instrucciones): copia sus frases, no recalcules nada.",
        "",
    ]

    necesidades = _necesidades(prefs)
    if necesidades:
        out.append(f"LO QUE EL MOTOR LEYÓ QUE BUSCA: {necesidades}")
    if tope is not None:
        unidad = " al mes" if por_mes else ""
        out += [
            f"TOPE DE PRESUPUESTO: ${int(round(tope)):,}{unidad}. Cada opción de abajo viene",
            "marcada DENTRO o SOBRE. Lo marcado SOBRE nunca lleva ✅, nunca va bajo un",
            "encabezado que diga que entra en el presupuesto, y se etiqueta con la frase",
            "exacta que trae su línea ('sobre tu tope por $X').",
        ]
    out.append("")

    plural = "opción" if len(cards) == 1 else "opciones"
    out += [
        f"EN EL PANEL — {len(cards)} {plural}. Estas son TODAS las opciones que existen para",
        "esta persona, en el ORDEN EXACTO en que las verá.",
    ]
    if tope is not None:
        out += _conteo_presupuesto(cards, tope)
    if len(cards) > 1:
        # La secuencia, escrita de corrido. En la repro en vivo el párrafo de instrucciones se
        # respetaba a medias y el modelo reordenaba por precio; una sola línea con el orden
        # literal es mucho más difícil de pasar por alto que una regla en prosa.
        secuencia = " · ".join(f"{i}) {_nombre(c)}" for i, c in enumerate(cards, 1))
        out += [
            f"ORDEN OBLIGATORIO DE TU LISTA: {secuencia}",
            "Es la posición de cada tarjeta en pantalla. Si numeras opciones, esa numeración es",
            "la tuya: mismos inmuebles, misma posición, mismo total. ¿Quieres que otra vaya",
            "primera? Llama a tool_priorizar_opcion(activo_id, motivo) — así se mueve TAMBIÉN la",
            "tarjeta. Subirla a mano deja la prosa contando una cosa y la pantalla otra.",
            "Destacar «la más barata» o «la más cercana al parque» en una frase aparte: SÍ.",
            "Reordenar o renumerar la lista por precio (ni por ningún otro criterio): NO.",
        ]
    for i, c in enumerate(cards, 1):
        out.append(f" {i}. {_linea_opcion(c, tope, por_mes)}")
        for razon in (c.get("encaje_razones") or [])[:5]:
            fuente = f" [{razon['fuente']}]" if razon.get("fuente") else ""
            out.append(f"      · {razon.get('texto', '')}{fuente}")

    if descartadas:
        n = len(descartadas)
        out += [
            "",
            f"NO SON OPCIONES ({n}) — el motor las descartó; la persona NO las verá en pantalla.",
            "PROHIBIDO listarlas, numerarlas o darles una sección propia, AUNQUE te pidan «todas»",
            "y aunque les aclares que se pasan del tope: ofrecer lo que no aparece en pantalla es",
            f"prometer lo que no hay. Y tu conteo es el del panel ({len(cards)}), no el del inventario",
            "crudo de la herramienta. Si viene al caso, reconócelas EN UNA FRASE, sin ficha ni viñeta:",
            (f"  ✅ «Hay {n} más en la zona, pero se pasa bastante de tu tope; no te la pongo.»"
             if n == 1 else
             f"  ✅ «Hay {n} más en la zona, pero se pasan bastante de tu tope; no te las pongo.»"),
            f"  ❌ Abrir una sección «Sobre tu presupuesto» y ponerla como opción {len(cards) + 1}.",
            "Sus datos, SOLO por si preguntan directo por alguna (no son material para tu lista):",
        ]
        for c in descartadas:
            out.append(f" · {_linea_opcion(c, tope, por_mes)}")

    aid, motivo = priorizado
    if aid:
        elegida = next((_nombre(c) for c in cards if c.get("id") == aid), None)
        if elegida:
            out += ["", f"PRIORIZACIÓN TUYA YA APLICADA: el panel se reordenó y {elegida} quedó",
                    f"primera. Motivo que declaraste: {motivo or '(no lo declaraste)'}.",
                    "Dile a la persona, en la respuesta, que la pones primera y POR QUÉ."]

    # Lo ÚLTIMO que el modelo lee antes de escribir. La regla del orden ya está arriba, pero
    # entre medio van las fichas de cada opción y, cuando la primera y la segunda están casi
    # empatadas, el orden se le desdibuja y termina listando por precio. Repetirla aquí es
    # aprovechar la posición: cuesta tres líneas y es lo que queda fresco.
    if len(cards) > 1:
        secuencia = " · ".join(f"{i}) {_nombre(c)}" for i, c in enumerate(cards, 1))
        out += ["", "RECORDATORIO FINAL, antes de escribir: si numeras opciones, van en ESTE orden",
                f"y ningún otro (aunque dos estén casi empatadas): {secuencia}."]

    return "\n".join(out)
