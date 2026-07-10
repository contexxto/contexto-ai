# Tarjeta de combate: Redfin × Sierra vs. Contexto

**Fecha:** 2026-06-23 · Basado en el teardown en vivo de Redfin AI Search + 10 agentes que cruzaron cada hueco con el código real de Contexto.
**Acompaña a:** [`COMPLIANCE_FairHousing_AgentSpec_2026-06-23.md`](COMPLIANCE_FairHousing_AgentSpec_2026-06-23.md) (las barandas y la spec técnica) e [`INTELIGENCIA_Sierra_Redfin_2026-06-23.md`](INTELIGENCIA_Sierra_Redfin_2026-06-23.md).

> Regla de oro de esta tarjeta: solo se listan jugadas **defendibles** tras las barandas de Fair Housing. El ángulo de "estilo de vida" SOLO es vendible si está instrumentado (guardrail + eval), no como prosa en el prompt.

---

## La tabla

| # | Hueco | Redfin hace | Contexto YA puede (anclado al código) | Estado código | Defensa |
|---|---|---|---|---|---|
| 1 | Entrevistar antes de ejecutar | Asume ciudad y tira 20 listings a ciegas (asumió SF solo) | Prompt ya ordena entrevistar (`graph.py:113`) + ejemplo de 1 pregunta (`:126`); motor mapea `anonimo`→"pregunta" (`intencion.py:28`) | Pieza existe pero el motor **no está en el lazo** del agente (`graph.py:385` nunca llama `analizar_intencion`). Cerrar el lazo = construcción | Media |
| 2 | Verdad de barrio | Cita un Walk Score opaco; para ruido dice "no tengo info" | Walk Score **calculado** sobre POIs reales de OSM por coordenada; caminata **real** calle-por-calle con Google Routes (corrige "640m recta=8min vs 1.5km caminando=19min"); Metro vs bus; overlay del corredor verificado | **REPLICABLE YA.** Walk score por inmueble se sobrescribe con OSM real al publicar (`assets.py:1116`). **Excepción dura:** ruido/tráfico/vegetación son heurísticos de tabla de 7 sectores — nunca presentar como medición | **Fuerte** |
| 3 | Estilo de vida difuso | Lo abandona por Fair Housing (juzga o calla → calla) | Tiene la materia prima (caminabilidad/servicios) para la versión **atribuida** | Materia prima ~80%. **Fuga real:** el prompt hace que el SISTEMA emita el adjetivo (`graph.py:110`). Falta diccionario + guardrail + eval | Fuerte (solo atribuida) |
| 4 | Cierre que convierte | No agenda, no califica, no handoff; "usa el botón de la ficha" | Handoff in-chat **completo**: endpoint, 3 tablas, email+push al corredor dueño, transcript, captura de lead. Motor califica frío/tibio/caliente | Infra **~80%** vs Redfin ~10%. Falta el 20% que convierte: **ninguna de las 6 tools dispara handoff** (lo hace un botón). Construcción | **Fuerte** |
| 5 | Multilingüe | Se cuelga 45s+ con "responde en español" | Español **es el sustrato**: prompt 100% español, anti-anglicismos duro, datos forzados a `es`. Sin capa de traducción que romper | **REPLICABLE YA**, ventaja estructural. Falta mini-regla de política de idioma | Media |
| 6 | Narrar el cambio (0/demasiados) | "No había bajo $X, subí a $Y, añadí ciudades" → control percibido | Mecanismo de expansión de radio existe (`tools.py:88` devuelve `radius_searched_m`) | Mecanismo existe pero **no hay regla que obligue a narrarlo** (retoque barato). Filtro precio/ciudad NO existe — replicar 1:1 es trabajo de producto (#6/#8) | Débil |

---

## Munición para el pitch a Linden (refinada con evidencia)

De más a menos defendible. Cada frase usa el lenguaje que el código respalda — sin inflar lo no construido.

**1. Verdad de barrio que se camina, no se scrapea** (foso más fuerte, código confirmado)
> *"Redfin te cita un Walk Score y se lava las manos con el ruido. Contexto calcula la caminabilidad sobre los comercios reales de tu cuadra —por coordenada, no por código postal— y te dice que el Metro está a 12 min caminando POR LA CALLE, no a 8 en línea recta que es mentira. Y te marca qué confirmó el corredor que pisó la zona, con fecha. Eso no se scrapea: se camina."*

**2. Servimos la verdad, no la opinión — hablamos de lifestyle donde el #2 de EE.UU. se rindió** (solo con atribución + guardrail)
> *"Redfin tuvo que tirar 'zona tranquila para tu familia' porque solo podía juzgar o callar. Nosotros no juzgamos: tomamos tu 'busco algo tranquilo' y respondemos con el ruido y la caminabilidad verificada de la cuadra, con la fuente al lado, y TÚ decides. El adjetivo es tuyo, el dato es nuestro, la conclusión es tuya."*

**3. El cierre ocurre en la conversación, no se pierde en una ficha** (infra confirmada, falta cablear la tool)
> *"Redfin te devuelve a la ficha y nunca sabe quién eres. Contexto detecta cuándo estás caliente, te conecta con TU corredor dentro del mismo chat y te lo entrega calificado con la intención completa."*

**4. LATAM no es mercado secundario, es el producto** (ventaja estructural confirmada)
> *"Redfin se cuelga 45s con 'responde en español'. Contexto no traduce el español: lo piensa en español, incluso los datos del mapa. LATAM es el sustrato, no un mercado a medias."*

**5. Un corredor bueno entrevista antes de mostrar** (solo con ejes objetivos)
> *"Redfin asume tu ciudad. Contexto te hace UNA pregunta primero —¿zona, presupuesto, cercanía al Metro?— porque la entrevista pregunta QUÉ buscas, nunca QUIÉN eres."*

**6. Cuando no hay nada en la cuadra, te lo decimos en una frase** (el más flojo)
> *"Contexto no te miente: te dice 'amplié a 3 km' y te muestra lo real."* (El filtro precio/ciudad que Redfin relaja no existe aún — roadmap, no demo.)

---

## Las 3 acciones replicables YA (por leverage)

**1. Exponer el foso de entorno con proveniencia en el chat** (leverage máximo, código ya existe)
- "Walk Score 78 calculado sobre N POIs reales (OSM)" usando `pois_analizados`/`desglose` que `analizar_zona` ya retorna.
- "El Metro está a 12 min caminando por la calle, no 8 en línea recta" (`conect_txt`) — el golpe directo al Walk Score opaco.
- Marcar la capa de corredor con `info_verificacion()`.
- **Baranda:** ruido/tráfico/vegetación → "estimación por sector, no medición" o callar. Nunca vestir heurístico de medición.

**2. Cerrar el lazo del cierre: tool de handoff para el agente** (leverage alto, convierte)
- La infra está 100% (`chat.py:527`). Falta que el AGENTE dispare el handoff, no un botón.
- Extraer `solicitar_handoff` a helper, añadir `tool_connect_with_broker` a `AGENT_TOOLS`, instruir en el prompt.
- **Baranda:** consentimiento de transferencia + resumen estructurado, no el hilo crudo (LOPDP/LFPDPPP).

**3. Blindar honestidad + política de idioma** (dos retoques de prompt, baratos)
- **Regla de atribución** (cierra la fuga `graph.py:110`): "Tranquilo y caminable (94), como buscabas" → "tú buscabas tranquilidad; caminabilidad 94 medida sobre N POIs OSM, ruido estimación ~X — juzga tú".
- **Narrar la expansión de radio** usando `radius_searched_m`.
- **Política de idioma** sin degradar servicio.

**Diferido (correctamente):** filtro precio/ciudad (trabajo de producto, #6/#8); diccionario difuso→dato completo y **guardrail Fair Housing** (construcción nueva imprescindible ANTES de vender el ángulo lifestyle a inversores).
