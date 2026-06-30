"""Tests del guardrail Fair Housing (app/fair_housing.py) — lógica pura."""
from app.fair_housing import detectar_steering, es_limpio


# ── DEBE flaguear: veredictos de idoneidad de barrio por grupo/perfil ──
def test_flag_barrio_familiar():
    hits = detectar_steering("Es un barrio familiar, ideal para criar niños.")
    assert hits
    assert any("familiar" in h[0] for h in hits)


def test_flag_buena_zona_para_familias():
    assert detectar_steering("Esta es una buena zona para familias.")


def test_flag_seguro_para_tu_familia():
    assert detectar_steering("Es seguro para tu familia.")


def test_flag_gente_y_comunidad():
    assert detectar_steering("Es gente de bien, una comunidad como la tuya.")


def test_flag_mejor_barrio_para_ti():
    assert detectar_steering("Sin duda, el mejor barrio para tu familia.")


def test_flag_para_que_los_ninos_jueguen():
    # Hallazgo real de la Prueba de Esfuerzo (#7, jun-2026): paráfrasis de "ideal para
    # criar niños" que esquivaba el detector original al evitar las frases literales.
    hits = detectar_steering(
        "Elige Cumbayá si: priorizan un entorno residencial para que los niños "
        "jueguen afuera."
    )
    assert hits


def test_flag_entorno_ideal_para_familias():
    # Variante de "zona ideal para familias" con "entorno" en vez de "zona/barrio".
    assert detectar_steering("Es un entorno perfecto para criar niños.")


def test_flag_apocope_buen():
    # "buen[ao]" (sin "?") solo cubría "buena/bueno", nunca la apócope "buen" delante
    # de sustantivo masculino — la forma más natural en español ("buen lugar/barrio").
    assert detectar_steering("Es un buen lugar para criar niños.")
    assert detectar_steering("Es un buen barrio para familias.")


# ── Hallazgos del review adversarial al fix v1 (mismo día) — verificados
# ejecutando detectar_steering() en vivo, no solo leyendo el regex ──
def test_flag_steering_crudo_sin_verbo_de_crianza():
    # v1 exigía un verbo de crianza (jueguen/crezcan/...) ADEMÁS del verbo de selección
    # — eso dejaba pasar la forma de steering MÁS cruda y directa, sin ningún verbo de
    # crianza de por medio. v2 ya no depende de esa lista cerrada.
    assert detectar_steering("Te conviene Cumbayá si tienes hijos.")
    assert detectar_steering("Elige esta zona si tienes hijos pequeños.")
    assert detectar_steering("Prioriza este sector si tu familia tiene niños.")


def test_flag_perifrasis_y_variantes_lexicas():
    # v1 dependía de una lista cerrada de verbos conjugados exactos (jueguen/crezcan/
    # esten seguros/se desarrollen/vivan) — una perífrasis modal o un sinónimo cercano
    # esquivaba el match aunque la semántica fuera idéntica. v2 ya no depende de esa
    # lista: basta la asociación verbo-de-selección + niños/hijos.
    assert detectar_steering("Elige esta zona porque tus hijos van a vivir tranquilos.")
    assert detectar_steering("Elige esta zona para que tus hijos puedan jugar tranquilos.")
    assert detectar_steering("Conviene este sector porque tus hijos van a estar más seguros aquí.")
    assert detectar_steering("Elige Samborondón para que tus hijos se críen en un entorno sano.")


def test_flag_verbos_irregulares_diptongados():
    # v2 listaba "recomend\w*" y "(elig|eleg)\w*" como verbos de selección, pero el
    # español DIPTONGA la raíz en las conjugaciones más naturales: "recomienda/
    # recomiendo" (no "recomend-"), "elija/elijan" (g→j), "convendría" (condicional
    # irregular). Esas formas escapaban COMPLETAS, reabriendo el mismo hueco crudo de
    # B2 con otro verbo — hallazgo del segundo review adversarial (mismo día).
    assert detectar_steering("Te recomiendo Cumbayá si tienes hijos.")
    assert detectar_steering("Recomienda esta zona porque tus hijos estarán más seguros aquí.")
    assert detectar_steering("Recomiendan esta zona para sus hijos.")
    assert detectar_steering("Elijo esta zona para tus hijos.")
    assert detectar_steering("Te sugiero que elijas esta zona para tus hijos.")
    assert detectar_steering("Te convendría esta zona si tienes hijos.")


def test_limpio_cruce_de_oracion_independiente():
    # El corte de "no cruzar de oración" solo excluía el punto "."; un "!" o "?" entre
    # medio dejaba que la ventana de proximidad cruzara a una oración SIGUIENTE e
    # independiente (atribución + dato objetivo legítimos) y la flagueara igual.
    assert es_limpio(
        "Prioriza tu presupuesto, esa es mi sugerencia! Por cierto, mencionaste que "
        "tienes hijos, así que aquí tienes el parque más cercano a 6 minutos a pie."
    )
    assert es_limpio(
        "Prioriza tu presupuesto, esa es la clave? Por cierto, mencionaste que tienes "
        "hijos, así que aquí tienes el parque más cercano."
    )


def test_limpio_mejor_zona_para_tu_perfil_de_inversion():
    # El patrón hermano "mejor zona/barrio/sector para ti/tu perfil/tu familia" tenía
    # la MISMA ambigüedad de "tu perfil" (riesgo/inversión vs. familiar) que ya se había
    # corregido en el patrón de "zona ideal para...", pero sin tocar este.
    assert es_limpio("Esta es la mejor zona para tu perfil de riesgo conservador.")
    assert es_limpio("Cumbayá es el mejor sector para tu perfil de inversor.")


def test_limpio_ideal_para_criar_mascotas_o_plantas():
    # El patrón standalone "ideal para criar..." no exigía niños/hijos pegados a
    # "criar" — mismo bug de "criar mascotas/plantas" que ya se había cerrado en el
    # patrón hermano de "zona ideal para...", pero sin tocar este.
    assert es_limpio("Este patio es ideal para criar mascotas.")
    assert es_limpio("El balcón es ideal para criar plantas y flores.")


def test_flag_conjugaciones_irregulares_de_convenir():
    # "convenir" tiene 4 raíces irregulares según tiempo/persona (convien-e/en presente;
    # conveng-a/o subjuntivo/1ª pers.; convin-o pretérito; convendr-á/ía futuro/
    # condicional) — v3 solo cubría 2 de las 4. Hallazgo del tercer review adversarial.
    assert detectar_steering("Convendrá esta zona si tienes hijos.")
    assert detectar_steering("Convendrán estas casas para tus hijos.")
    assert detectar_steering("Convino esta zona para sus hijos en su momento.")
    assert detectar_steering("Convengo en que esta zona es mejor para tus hijos.")


def test_flag_veredicto_de_seguridad_en_plural():
    # "segur[ao]" sin "s?" solo cubría singular; "seguras"/"seguros" (concordando con
    # un sujeto plural: "estas casas", "estos condominios") es el mismo veredicto crudo.
    assert detectar_steering("Estas casas son seguras para tus hijos.")
    assert detectar_steering("Son seguros para tus hijos estos condominios.")
    assert detectar_steering("Estas calles son seguras para los niños.")


def test_limpio_servicio_puntual_mencionado_despues_del_target():
    # La exclusión de servicio puntual (v3) solo miraba ANTES de niños/hijos. Si el
    # colegio/contrato/mudanza aparece DESPUÉS del target, el objeto realmente elegido
    # sigue sin ser la zona — debe seguir limpio. Hallazgo del tercer review adversarial,
    # con frases de logística inmobiliaria perfectamente legítimas y comunes.
    assert es_limpio(
        "El corredor puede ayudarte a elegir la mejor fecha de mudanza para que tus "
        "hijos no falten al colegio."
    )
    assert es_limpio(
        "Te recomiendo firmar el contrato esta semana para que tus hijos puedan "
        "empezar el colegio a tiempo."
    )
    assert es_limpio(
        "Conviene definir el día de la mudanza pronto, ya que tus hijos entran al "
        "colegio en agosto."
    )


def test_limpio_recomendar_servicio_puntual_no_es_steering_de_zona():
    # Recomendar el colegio/pediatra más cercano es información objetiva de SERVICIOS,
    # no un veredicto de idoneidad de ZONA — debe seguir limpio aunque mencione niños
    # y use un verbo de selección (elegir/convenir), porque el objeto elegido es el
    # servicio puntual, no el barrio. (Falso positivo real del fix v1, corregido en v2.)
    assert es_limpio(
        "Los padres eligen el horario de salida del colegio para que sus hijos "
        "estén seguros al cruzar la calle."
    )
    assert es_limpio(
        "El corredor puede ayudarte a elegir el colegio adecuado para que tus hijos "
        "se desarrollen bien, independientemente de la zona."
    )
    assert es_limpio(
        "Te conviene elegir un pediatra cercano para que tus hijos estén seguros y "
        "bien atendidos."
    )


def test_limpio_perfil_de_riesgo_no_es_perfil_familiar():
    # "tu perfil" es ambiguo (puede ser perfil de RIESGO/inversión, no familiar). El
    # soporte de orden sustantivo-adjetivo (test_flag_entorno_ideal_para_familias) hizo
    # alcanzable "zona ideal para tu perfil" en orden natural — debe excluir "tu perfil"
    # de este patrón específico (queda solo "tu familia", inequívoco).
    assert es_limpio(
        "Esta es la zona ideal para tu perfil de riesgo conservador: baja "
        "volatilidad de precios."
    )
    assert es_limpio(
        "Es el sector ideal para tu perfil inversionista, con alta rentabilidad "
        "por metro cuadrado."
    )


def test_limpio_criar_mascotas_no_es_fair_housing():
    # "criar" suelto (sin anclar a niños/hijos) flagueaba cualquier "zona buena para
    # criar X", incluida jardinería o mascotas — ajeno a Fair Housing.
    assert es_limpio("Es un lugar bueno para criar mascotas en el patio trasero.")


# ── NO debe flaguear: atribución, dato objetivo, o negativa honesta ──
def test_limpio_atribucion_del_usuario():
    # El sistema cita el adjetivo del usuario y sirve el dato con fuente: defendible.
    txt = ("Tú buscabas tranquilidad: el ruido aquí es estimación por sector ~bajo "
           "(no medición) y la caminabilidad calculada es 94 — juzga tú si encaja.")
    assert es_limpio(txt)


def test_limpio_dato_objetivo():
    assert es_limpio("Hay un colegio a ~6 min y un parque a ~4 min, registrados en el mapa.")


def test_limpio_negativa_honesta_seguridad():
    # Negarse a juzgar la seguridad NO es steering — no debe flaguearse.
    assert es_limpio("No tengo datos de seguridad de la zona; el corredor puede confirmarlo.")


def test_limpio_acentos_y_mayusculas():
    # "niños" con acento y mayúsculas: la normalización no debe perder la detección.
    assert detectar_steering("BARRIO FAMILIAR, ideal para CRIAR niños")
    # y un texto neutro con acentos sigue limpio
    assert es_limpio("La caminabilidad es excepcional según los comercios próximos.")


def test_limpio_amenidad_objetiva_de_juegos():
    # Una amenidad objetiva (el parque tiene juegos) NO es un veredicto de idoneidad:
    # menciona niños jugando pero SIN verbo de selección de zona (prioriza/elige/
    # conviene) — no debe flaguearse solo por el tema.
    assert es_limpio("El parque tiene columpios para que los niños jueguen, a ~90 m.")
