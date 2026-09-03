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

# G20-B1-R3 · las dos marcas del bloque, exportadas para que `llm_node` pueda recortar la
# herencia sin duplicar literales. La sección territorial describe la evidencia de UNA
# operación de retrieval y NO sobrevive al turno; las reglas del panel (orden obligatorio,
# frases de presupuesto) sí, porque gobiernan el MISMO panel mientras la persona pregunta
# sobre él. Ver tests/test_g20_b1_r3_lineage_del_contrato.py.
MARCA_PANEL = "════════ MOTOR DE ENCAJE · CONTEXTO AUTORITATIVO DE ESTE TURNO ════════"
MARCA_TERRITORIAL = "──────── RELACIÓN TERRITORIAL · QUÉ PUEDES AFIRMAR ────────"

# G20-B1 · CONTRACT-SIGNATURE-01. La firma la EMITE el contrato; no se deduce de sus
# cabeceras. Un adjudicador que infiriera el formato a partir de los títulos estaría
# reconociendo su propia suposición —una firma circular— y un cambio de redacción lo dejaría
# validando algo que ya no entiende. Va exactamente UNA vez por bloque, tanto en el contrato
# enriquecido como en el fallback mínimo, y NUNCA en un turno sin relación territorial: sin
# contrato no hay nada que firmar.
#
# Si el formato cambia de forma incompatible, sube a V2 — y el arnés, que guarda su propia
# copia del literal y no importa ésta, dirá NO_ADJUDICABLE en vez de adivinar.
FIRMA_TERRITORIAL = "CONTRATO_TERRITORIAL_V1"


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


def _seccion_territorial(rel: dict | None, cards: list[dict] | None = None) -> list[str]:
    """G20-B1 · de la evidencia territorial a la AFIRMACIÓN que autoriza.

    G19-A y G20-A hicieron legible lo que SABEMOS. Para la procedencia bastó; para la
    relación territorial no. En el canary limpio del 2026-08-30 —hilo sin un solo mensaje
    previo— el modelo recibió `pertenencia_territorial: unknown` en el resultado de tool y
    escribió igual «1 departamento en arriendo EN LA FLORESTA». Enunciar el estado de la
    evidencia no gobierna la afirmación.

        evidencia  ≠  autorización de afirmación

    Por eso esta sección vive aquí y no en la tool: es el canal que el sistema ya trata
    como autoritativo y el único con obediencia demostrada —las frases obligatorias de
    presupuesto no se violaron en ninguno de los 13 turnos del corpus.

    UNKNOWN NO ES UNA NEGACIÓN. No se autoriza «está fuera» ni «no pertenece»: tampoco eso
    está demostrado. `unknown` se traduce en RESTRICCIÓN sobre lo afirmable, no en su
    contrario.

    Y la política NO es «no menciones el barrio». Las tres familias acreditadas —referencia
    a la consulta, POI con nombre propio y proximidad al punto— se nombran explícitamente
    como permitidas. Prohibir el topónimo entero degradaría el producto para arreglar un
    claim: el 24% de las coincidencias del patrón ingenuo en el corpus real eran el gancho
    de cierre («¿cómo es vivir en La Floresta?»), que es conducta deseada.
    """
    if not rel or rel.get("relacion_recuperacion") != "within_radius":
        return []
    lugar = rel.get("consulta")
    # G20-B1-R2: una distancia POR INMUEBLE VISIBLE, ligada por id. Nunca una cifra suelta.
    distancias = rel.get("distancias") or []
    nombres = {c.get("id"): _nombre(c) for c in (cards or []) if isinstance(c, dict)}
    hay_cifras = any(d.get("distancia_metros") is not None for d in distancias)

    out = ["", MARCA_TERRITORIAL,
           f"[{FIRMA_TERRITORIAL}] · esta sección es contrato, no sugerencia",
           "LA EVIDENCIA DE ESTE TURNO:"]
    if lugar:
        out.append(f"  · se geocodificó «{lugar}» y devolvió UN PUNTO — no un área, no un límite")
    else:
        out.append("  · el punto de búsqueda NO corresponde a ningún lugar nombrado en este turno")
    out.append(f"  · los candidatos se recuperaron por PROXIMIDAD a ese punto (radio pedido "
               f"{rel.get('radius_requested_m')} m, efectivo {rel.get('radius_searched_m')} m)")
    if hay_cifras:
        # Cada cifra pegada a SU inmueble, con el MISMO nombre y el MISMO número de orden que
        # la lista de opciones de arriba. Una distancia genérica «del candidato mostrado»
        # atribuía la cifra del más cercano —que el filtro pudo haber ocultado— a la tarjeta
        # que sí se ve. Ver `_distancias_ligadas` en el assembler.
        out.append("  · distancia de CADA inmueble mostrado a ese punto. La cifra es de SU "
                   "inmueble")
        out.append("    y de ningún otro, y el número es el de la lista de arriba:")
        for i, d in enumerate(distancias, 1):
            nom = nombres.get(d.get("id")) or "Inmueble sin dirección"
            metros = d.get("distancia_metros")
            if metros is None:
                out.append(f"      {i}. {nom} — SIN DISTANCIA LIGADA a este inmueble: no le "
                           f"atribuyas ninguna")
            else:
                out.append(f"      {i}. {nom} — {metros:g} m")
    else:
        out.append("  · NINGUNA distancia quedó ligada a los inmuebles mostrados: no afirmes "
                   "distancias en este turno")
    out.append("  · pertenencia territorial: NO ESTÁ ESTABLECIDA — no existe límite ni "
               "polígono que la demuestre, ni aquí ni en la base")

    out.append("PUEDES AFIRMAR:")
    if hay_cifras:
        out.append("  ✅ la distancia de cada inmueble EXACTAMENTE como está arriba, junto al "
                   "inmueble al que corresponde")
    else:
        out.append("  ✅ que los inmuebles se recuperaron por proximidad a ese punto — sin cifra")
    if lugar:
        out.append(f"  ✅ que buscaste «{lugar}» — describir la consulta es correcto")
    out.append("  ✅ los POI con nombre propio y sus tiempos, tal como vienen en los servicios "
               "cercanos: son evidencia acreditada")

    out.append("NO AFIRMES — esta evidencia no lo autoriza:")
    if lugar:
        out.append(f"  ❌ que el inmueble esté «en {lugar}», «dentro de» o «ubicado en» ese lugar")
        out.append(f"  ❌ que el punto de búsqueda sea el centro, el centroide o el corazón "
                   f"de «{lugar}»")
    else:
        out.append("  ❌ que el inmueble pertenezca a ningún barrio o sector")
        out.append("  ❌ que el punto de búsqueda sea el centro o el corazón de un lugar")
    out.append("  ❌ atribuir a un inmueble una distancia que arriba no le corresponde, ni dar "
               "una distancia «del candidato mostrado» en general: cada cifra es de un "
               "inmueble concreto y sólo de ése")
    out.append("  ❌ TAMPOCO lo contrario: no digas que está fuera ni que no pertenece. "
               "Ninguna de las dos cosas está demostrada.")
    return out


def bloque_territorial_minimo(relacion_territorial: dict | None) -> str:
    """G20-B1-R3 · el contrato territorial SOLO, sin panel, sin tarjetas y sin distancias.

    Es el fallback autoritativo mínimo, y su rasgo de diseño es de dónde NO depende: se arma
    únicamente con la relación que el ToolMessage del turno demostró. Ni base, ni ranking, ni
    `cards`. Si dependiera del panel, un fallo en `construir_panel` —que es donde vive la I/O y
    por tanto donde más se falla— arrastraría consigo al contrato, que es exactamente el modo
    de fallo que R3 cierra.

    Se usa en dos filas de la tabla de verdad:

      · hay evidencia territorial y CERO tarjetas   (G20-B1-NOCARDS-01)
      · hay evidencia territorial y el bloque enriquecido reventó  (G20-B1-CONTAINMENT-01)

    Devuelve "" cuando no hay relación que declarar: sin riesgo territorial no hay contrato
    que emitir, y eso NO es un fallo.
    """
    # SIN ENTIDADES NI DISTANCIAS, y no por economía: sin tarjetas no hay sujeto visible al
    # que ligar una cifra, y emitirla igual produciría «Inmueble sin dirección — 572 m» —
    # una distancia huérfana, que es la forma degenerada del defecto que R2 cerró. Se vacían
    # aquí y no en el llamador para que la función sea honesta venga de donde venga.
    rel = dict(relacion_territorial or {}, distancias=[]) if relacion_territorial else None
    seccion = _seccion_territorial(rel, [])
    if not seccion:
        return ""
    cabecera = [
        "════════ CONTEXTO AUTORITATIVO DE ESTE TURNO ════════",
        "Esto NO lo escribió el usuario: es la restricción del sistema sobre lo que puedes",
        "afirmar de la UBICACIÓN. Rige aunque no haya inmuebles que mostrar.",
    ]
    return "\n".join(cabecera + seccion)


def bloque_autoritativo(cards: list[dict], preferencias: dict | None,
                        descartadas: list[dict] | None = None,
                        priorizado: tuple[str | None, str | None] = (None, None),
                        relacion_territorial: dict | None = None) -> str:
    """Las tarjetas del turno → el bloque que el modelo recibe como verdad del turno.

    `cards` son EXACTAMENTE las que verá la persona, ya ordenadas. `descartadas` son las que
    el corte del panel dejó fuera: van nombradas para que el modelo sepa que existen y NO las
    ofrezca (si no las nombramos, puede recomendarlas de memoria y prometer algo invisible).
    Devuelve "" si no hay nada que declarar — un bloque vacío no debe ensuciar el prompt.
    """
    if not cards:
        # G20-B1-R3 · NOCARDS-01. Sin tarjetas no hay ranking que dictar ni presupuesto que
        # contar — pero si el turno PROBÓ una relación territorial, la prohibición se emite
        # igual. Devolver "" aquí apagaba el gobierno territorial entero: el modelo quedaba
        # libre de convertir «búsqueda radial alrededor de La Floresta» en «búsqueda dentro
        # de La Floresta» justo cuando menos evidencia había para sostenerlo.
        # Sin relación devuelve "", que es lo correcto: sin riesgo no hay contrato.
        return bloque_territorial_minimo(relacion_territorial)
    prefs = preferencias or {}
    por_mes = _es_arriendo(cards, prefs)
    tope = prefs.get("presupuesto_max")
    tope = float(tope) if isinstance(tope, (int, float)) and not isinstance(tope, bool) and tope > 0 else None

    out = [
        MARCA_PANEL,
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

    out += _seccion_territorial(relacion_territorial, cards)

    return "\n".join(out)
