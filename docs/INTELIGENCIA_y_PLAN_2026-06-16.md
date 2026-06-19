# Inteligencia de Mercado y Plan de Acción — 16 jun 2026

> Documento estratégico. Recoge tres señales de mercado investigadas hoy + un
> insight propio salido de pruebas reales, y los traduce en un plan concreto
> para esta semana (16–22 jun) y la siguiente (23–29 jun).

---

## TL;DR (lee esto si no lees nada más)

1. **La capa de "app/UI" se está commoditizando** (Lovable abre su MCP). Tu foso NO es la interfaz — es la **data del lugar**. Invierte ahí.
2. **El rubro inmobiliario + IA está validado y fundable** (KW Command/Kelle, RE/MAX Max AI, y la compra **Real Brokerage → RE/MAX por $880M**). Los gigantes consolidan el **masivo global** → dejan la **profundidad local (Quito/Latam) como espacio en blanco**. Esa es tu cancha.
3. **Google formaliza que el conocimiento curado es el foso** (Open Knowledge Format). Es tu tesis ("el dato pertenece a la coordenada, no al anuncio") elevada a estándar de industria. Úsalo como **camino de interoperabilidad B2B2C a futuro**, no ahora.
4. **Insight propio (el más importante):** en prueba real detectamos *data decay* — una escuela que cerró seguía listada, y faltaban PROMART, Santa María y TUTI. **El corredor sabe antes que Google Maps.** Capturar ese ground-truth = el motor del "Catastro **Vivo**" y tu data moat real.

**Plan en una línea:** esta semana, estabilizar + blindar honestidad + difundir testing; la próxima, construir el **loop de contribución del corredor** (la mecánica del "Vivo").

---

## PARTE 1 — Inteligencia

### 1.1 Lovable abre su MCP (build apps desde tu cliente)

- **Qué es:** jugada de distribución — quieren ser la "capa de construcción" que otros clientes invocan. Abarata generar *cascarones* de app.
- **Lectura:** **ruido para el core.** Lovable optimiza justo lo que NO es tu ventaja (la UI). Cualquiera clona tu chat; nadie clona tu catastro.
- **Señal útil:** confirma que la capa UI/app se commoditiza → **doblar la apuesta en datos**, no en que el chat se vea más lindo.
- **Uso legítimo único:** landings de marketing desechables. Nada que toque la data.

### 1.2 Consolidación del rubro + Francisco Igual

**Hechos verificados (no humo):**
- **Keller Williams:** Kelle (copiloto gen-AI) + Command (CRM/OS); abrió Command a terceros (feb 2026). 180.000+ agentes.
- **RE/MAX:** suite Max AI, MaaS, ~15-20 herramientas.
- **The Real Brokerage adquiere RE/MAX (~$880M)** → "Real REMAX Group", cierra 2da mitad 2026. Mayor consolidación de brokerage en una década; 1ª vez que una plataforma AI-native compra una marca legacy a esa escala.

**Lectura estratégica:**
- El capital paga caro por **infra inmobiliaria AI-native** → tu categoría está validada y es **fundable**. Mete el dato de $880M en el pitch deck como prueba externa.
- Los gigantes consolidan el **mercado masivo global** (US/global, data en inglés) → **no atienden la profundidad local.** Quito/Latam secundaria = espacio en blanco. Tu **P7 (conocimiento tácito del territorio)** es lo que su IA gringa no tiene.

**Francisco Igual** (el del post "ÚLTIMA HORA"):
- Consultor/educador hispanohablante (~6.300 seguidores). Vende **formación + packs de prompts** para que inmobiliarias usen Claude ("segundo cerebro" de operación interna). Curso "IA Inmobiliaria RED".
- **NO es competidor ni amenaza** — vende *cómo* usar IA (prompts, vida media corta), no construye un foso de datos. Está en otra capa (ops B2B interna; tú, catastro de cara al usuario).
- **Clasificación: contacto de Radar / canal potencial.** Tiene audiencia de inmobiliarias hispanas. Movimiento (T36): dar valor primero (comentar con un dato real), no pitchear. Baja prioridad hoy.

### 1.3 Google Open Knowledge Format (OKF)

- **Qué es (v0.1, jun 2026):** especificación abierta y vendor-neutral para representar **conocimiento curado como markdown + frontmatter YAML**, consumible por agentes. "Solo archivos, solo markdown, solo YAML." Conceptos se enlazan con links → **grafo de conocimiento**. Google ya hizo que su Knowledge Catalog lo ingiera.
- **Lectura:** la industria formaliza que **la capa de conocimiento curado es el foso** (primero MCP para *tools*, ahora OKF para *conocimiento*). Es **tu tesis** aplicada a lugares: el Catastro Vivo ES un grafo de conocimiento curado.
- **¿Te sirve hoy?** NO para el motor PostGIS (queries geoespaciales en vivo; OKF son archivos estáticos). **SÍ a futuro** como **camino de interoperabilidad B2B2C**: exportar el catastro de Quito como bundle OKF → consumible por cualquier agente (corredores, fondos, ecosistema Gemini) sin lock-in.
- **Acción:** roadmap, no sprint. Higiene futura: externalizar el conocimiento de dominio del agente (hoy en el `SYSTEM_PROMPT` monolítico) a archivos versionados.

### 1.4 ⭐ INSIGHT PROPIO — El dato vivo (data decay) y el corredor como sensor

**Lo encontrado en prueba real (depto de Quitumbe):**

| Tipo de error | Ejemplo | Riesgo |
|---|---|---|
| Dato muerto (cerró, sigue listado) | Escuela Cristo del Consuelo | 🔴 El agente afirmó un falso como hecho → mata credibilidad |
| Dato faltante (abrió, no lo sabe) | PROMART (~1 mes), restaurante viral de TikTok | 🟡 Pierde "bondades" que enamoran |
| Servicio clave faltante | Supermercados Santa María, TUTI | 🟡 Bondades invisibles |

**El insight clave:** OpenStreetMap y Google Maps **también van atrasados**. PROMART abrió hace un mes — puede que ni Google lo tenga. Por eso "Actualizar zona" (re-jala de OSM) **no basta**. **El corredor sabe ANTES que Google** — camina la zona, vio cerrar la escuela, vio abrir PROMART.

→ Capturar ese ground-truth incentivado = **foso de datos que Google no puede replicar rápido** (requiere botas en el terreno). Es el **"Vivo"** de "Catastro Vivo", y el **DATA MOAT del pitch deck deja de ser teoría**.

**La mecánica (a diseñar):**
- **Loop confirmar/corregir/agregar** sobre "servicios cercanos" del anuncio: ✅ sigue · ❌ cerró · ➕ nuevo (un tap c/u).
- **Incentivo egoísta:** su anuncio mejora primero (más interesados) + insignia "Entorno verificado · jun 2026". Diferida (T5): cada confirmación enriquece el catastro de toda la zona → flywheel.
- **Honestidad por diseño:** el agente **etiqueta la frescura** — "confirmado por corredor (jun 2026)" vs "dato de mapa, sin confirmar — podría haber cambiado". El "bug" de la escuela se vuelve feature.
- **Anti-abuso (P4):** el corredor solo edita zonas donde tiene anuncios (piel en el juego); cada cambio con autor + fecha (un `log.md`, eco de OKF).

---

### 1.5 ⭐ EVIDENCIA EMPÍRICA DEL FOSO — el agente es fácil, el dato es el muro (Cynthia Wu)

*(Cynthia Wu —ex-Google, ex-fundadora— construyó un "agente cazador de casas" y publicó el resultado, jun 2026. NO valida la categoría como los competidores: prueba el FOSO desde las trincheras.)*

**Qué hizo:** un agente que filtra anuncios por geo-intención granular (casas a X min de un parque o estación, por distrito escolar) con polígonos geoJSON. Lo armó en un fin de semana.

**El muro (textual):** *"Este flujo NO es automatizable: Redfin, Zillow y MLS restringen el acceso a los anuncios. Intenté con Playwright y me bloquearon. Para tener la lista, tendría que volverme agente inmobiliario."* Su conclusión: ***"Los datos determinan el resultado."***

**La lección (P7, probado en carne propia):**
- **El agente de IA es commodity** — lo arma una ingeniera de Google en un finde.
- **El DATO es el foso.** En EE.UU. está **bloqueado** (los portales lo gatekeepean); en LatAm **no existe**. Mismo final: gana quien **controla** el dato.
- Contexto no scrapea un portal cerrado ni depende de un MLS: **construye su propio catastro** con corredores (botas en el terreno). El dato es propio — ni rentado ni robado.

**Bonus — valida el emparejamiento por intención:** el "filtro soñado" de Cynthia (a X min de parque/estación, distrito escolar) ES nuestro intent-matching (chips: familia tranquila, colegios, parque, cerca del Metro). La necesidad es real, específica y dolorosa.

**Disciplina (P5):** el foso NO es "un mejor agente cazador de casas" (el finde de Cynthia). Es el **dato propio + el loop.** Quedarse ahí.

---

## 🥊 Competidor de referencia #1 — Esri "Real Estate AI Agent"

*(Showcase de Esri —el gigante mundial del GIS/ArcGIS— publicado jun 2026 por Sajit Thomas, Application Architect. Demo, no producto lanzado. La respuesta lista cuando un inversor pregunte "¿y si Esri/Google entra?".)*

**Qué es:** un agente (por voz) que, sobre una escena 3D cinematográfica de Manhattan, analiza el entorno de un listing por factores. Datos: **NYC Open Data + synthetic listings + ArcGIS Location Services.**

**El método (debajo del eye-candy):** *proximidad a hotspot por factor* — hexbins + top 5º percentil + distancia en metros al pico, narrado por el agente:
| Factor | Narración del agente |
|---|---|
| Crimen | "296 incidentes; mayor concentración (113) a 52m del listing" |
| 311 service requests (proxy de molestia/ruido) | "1000 solicitudes en 500m: vendedores, parqueo ilegal, ruido-comercial; pico a 69m" |
| Dining | "20 lugares en 500m: lounges, postres, bubble tea; concentración a 135m" |

**Las 3 confirmaciones (todas a nuestro favor):**
1. **El concepto es el futuro** — el líder del GIS valida nuestra tesis (igual que Nadella validó el "sistema vivo").
2. **El DATO es el foso** — su demo solo funciona en NYC por el open data + listings falsos. *Pídeselo para Quito y se desarma* (no hay crime data, no hay 311, no hay listings reales).
3. **Su enfoque NO llega a Latam** — depende justo de lo que la región no tiene. Nuestro **corredor-loop resuelve el dato** donde ellos no pueden.

**Diferenciación (tabla de pitch):**
| Esri agent | Contexto |
|---|---|
| Data pública (NYC Open Data) | Dato local + **contribuido por el corredor** donde no hay data pública |
| **Synthetic listings** (inventario falso) | **Listings reales** |
| Datasets con lag | **Dato fresco verificado** (PROMART de hace 1 mes, ya capturado) |
| Plataforma B2B/enterprise (ArcGIS) | **App de consumo + handoff humano** |
| Eye-candy 3D | Honestidad + confianza + conversación |

**2 takeaways para robar (técnica, no estrategia):**
- La **narración "proximidad a concentración + distancia"** ("la mayor concentración de X está a Ym del inmueble") — adoptar cuando el grafo contribuido sea denso.
- El **corredor es nuestro "311"**: el proxy humano de molestia/ruido donde no hay datos públicos de quejas.

**Qué NO hacer (P5):** no competir en GIS multi-factor ni en render 3D — su cancha, pierdes. Nuestro foso es el dato local-contribuido, ortogonal a su fortaleza.

> **Frase de pitch:** *"Esri tiene el mapa; nosotros tenemos el territorio. Ellos, un demo bello con listings sintéticos sobre data pública de EE.UU.; nosotros, un producto real con dato fresco del corredor, donde la data pública no existe."*

---

## 🥊 Competidor de referencia #2 — Realtor.com "RealAssist™ AI"

*(Portal inmobiliario real de EE.UU. —News Corp/Move Inc.—, NO un demo. Beta desde el 2 jun 2026, sobre Google Gemini + Cloud. El competidor-concepto MÁS cercano hasta ahora.)*

**Qué es:** búsqueda de vivienda **AI-first conversacional** sobre su inventario MLS. Integra listings MLS, affordability, conexión con agentes, prompts iterativos — y **commute-time, amenities cercanas y "cómo encaja un barrio en tu rutina"** (sí toca nuestra capa de "cómo es vivir aquí"). Enmarca la IA como *"hacer al agente humano MÁS valioso, no menos"* — nuestra tesis exacta.

**Diferenciación (tabla de pitch):**
| RealAssist | Contexto |
|---|---|
| **US / MLS** (no hay MLS en Ecuador; no operan en Latam) | **Quito/Latam** — donde están ausentes |
| "Neighborhood fit" desde **data commodity de Google** | Entorno **verificado + contribuido por el corredor, más fresco** que Google |
| Sin ficha técnica verificada | Catastro vivo verificado |
| **Portal** (inventario MLS + referidos) | **Catastro vivo** — el dato pertenece a la coordenada, no al anuncio |

**El punto clave:** incluso su capa de barrio usa **data commodity de Google** — la misma que cualquiera tiene. **Nuestro dato del corredor le gana en nuestro mercado** (local, verificado, fresco). Ellos = portal más inteligente; nosotros = modelo distinto.

**El regalo escondido (PYMNTS, *"The AI House Hunter Meets a Skeptical Market"*):** el mercado está **escéptico** de los buscadores con IA. Nuestra marca entera es **honestidad ("la IA en la que confías")**. En un mercado escéptico, **la IA que NO miente gana** → el recelo del consumidor valida nuestro posicionamiento.

**Takeaway estratégico:** la ventana para "búsqueda genérica con IA" **se cierra en EE.UU.** (los incumbentes la tomarán). Espacio defendible = **Latam + capa de dato verificado/contribuido** (que ni ellos, con Google, tienen). NO derivar a "portal con IA mejor" (ahí ganan por inventario); quedarse en **"la verdad del lugar, en Latam."**

> **Frase de pitch:** *"Realtor.com hace más inteligente buscar anuncios en EE.UU. con data de Google. Nosotros decimos la verdad de dónde vivirías en Quito, con dato del corredor que Google no tiene — y en un mercado que ya no confía en la IA, somos la que no miente."*

## 🥊 Competidor de referencia #3 — Eva (Aino AI) "Site intelligence"

*(Herramienta de Alex Kamenev / Aino AI —"AI infrastructure for the built environment"—, jun 2026. Análisis de ubicación multifamiliar en EE.UU. para inversores/desarrolladores. Gratis, como vitrina de la infraestructura de Aino. La respuesta lista cuando un inversor pregunte "¿y si una herramienta de IA de ubicación entra a Quito?".)*

**Qué es:** memo de inversión **Go/No-Go en ~50s** para cualquier dirección multifamiliar de EE.UU. Genera puntuación de ubicación, caminabilidad, POIs, comps de alquiler, zonificación y demografía — con **nivel de confianza por dato** y un memo "Por qué nos gusta / Qué vigilar". Es **screening/underwriting institucional**, no para el consumidor que elige dónde vivir.

**Cómo lo hace (lo decisivo):** **AGREGA datasets de terceros** — Mapbox isochrones, Overture + Google POIs, **RentCast** (140M propiedades), **Regrid** (parcelas/zonificación), **Census ACS** (demografía).

**Diferenciación (tabla de pitch):**
| Eva / Aino | Contexto |
|---|---|
| **US, inversor/desarrollador** (underwriting B2B) | **Quito, consumidor + corredor** (recomendación + leads) |
| **AGREGA** datasets que existen en EE.UU. (RentCast, Regrid, Census…) | **CONSTRUYE** el dato donde no existe (catastro vivo + corredor) |
| Memo Go/No-Go para fondos (screening) | Empareja la intención de vivir con la verdad del lugar |
| Data commodity agregada | Dato tácito contribuido (el atajo del Terminal que ni Google supo) |

**El punto clave:** la receta de Eva **NO es replicable en Latam.** No hay un RentCast ecuatoriano, ni un Regrid de Quitumbe, ni Census micro. Sin esos datasets, su modelo se cae. **La única forma de tener inteligencia de ubicación en Latam es CREARLA** — que es justo nuestro foso (P7: nadie lo replica sin operar el territorio).

**Takeaway estratégico (disciplina, P5):** NO copiar su carril de **memo de inversión institucional** — necesita datos que Latam no tiene y nos saca de la profundidad. Quedarse en **consumidor + corredor + verdad local.**

> **Frase de pitch:** *"Esas herramientas agregan datos de Estados Unidos que para Quito no existen. Nosotros CONSTRUIMOS la verdad de los lugares de Quito, con corredores — ese dato no lo tiene nadie, y es tuyo."*

*(Confirmación, no copia: su "nivel de confianza por dato" + memo "Por qué nos gusta / Qué vigilar" ≈ nuestra tarjeta ✅/⚠️ + alertas honestas. El instinto ya iba bien.)*

---

**Síntesis de los competidores:** Esri (demo, data pública) + Realtor.com (portal real, MLS) + Eva/Aino (screening de inversión) + Nadella → **cuatro validaciones de la categoría.** Los tres son **US, sobre data commodity/agregada, ausentes en Latam.** Eva lo desnuda: su receta es **agregar datasets que en Latam NO existen** → no replicable aquí. Nuestro foso —dato local **construido**, verificado, contribuido + honestidad— es **estructuralmente ortogonal** a los tres.

---

## PARTE 2 — Plan de Acción

### Principios rectores (validados esta sesión)

1. **Honestidad > todo.** Es el único foso que un portal no puede copiar. Un dato menos, pero 100% real.
2. **Profundidad local > amplitud.** No perseguir features horizontales ni herramientas de moda.
3. **No desplegar backend con testers activos.** Cambios de backend se juntan y se empujan en ventana muerta.
4. **No scope-creep:** Lovable y OKF se archivan, no se adoptan ahora.

### 🗓️ Esta semana (16–22 jun) — estabilizar, blindar, difundir

| # | Tarea | Tipo | Por qué | Estado |
|---|---|---|---|---|
| 1 | Auditoría de auth (6 bugs) | Producto | Flujo login/rol/logout sólido | ✅ Hecho |
| 2 | Cápsula "del dato al deseo" | Producto | Despertar deseo sin mentir (feedback real) | ✅ Desplegado |
| 3 | **Fix honestidad: candado anti-invención de transporte** | Producto | El agente pudo inferir "Trolebús" no verificado → erosiona el foso | 🔜 Verificar dato + apretar prompt |
| 4 | **Etiquetado de frescura (v1 simple)** | Producto | Que el agente hedge datos sin confirmar ("dato de mapa, sin confirmar") → tapa el caso "escuela cerrada" | 🔜 Esta semana |
| 5 | Difusión controlada (WhatsApp a amigos) | GTM | Más señal de uso real; mensaje ya listo con link al anuncio | 🔜 |
| 6 | Pitch deck: folder $880M + narrativa data moat | Estrategia | Validación externa + foso defendible | 🔜 (bajo esfuerzo) |

### 🗓️ Próxima semana (23–29 jun) — construir el "Vivo"

| # | Tarea | Tipo | Por qué |
|---|---|---|---|
| 7 | **MVP loop de contribución del corredor** (confirmar/corregir/agregar sobre "Actualizar zona") | Producto ⭐ | La feature más importante: el motor del Catastro Vivo y el data moat |
| 8 | Etiquetado de frescura (v2): "verificado por corredor + fecha" vs "OSM sin confirmar" | Producto | Honestidad + gancho de contribución |
| 9 | Insignia "Entorno verificado" en el anuncio | Producto/GTM | Incentivo egoísta del corredor (más credibilidad → más leads) |
| 10 | Documentar OKF como camino de interoperabilidad B2B2C | Estrategia | Carta a futuro; no implementar |

### Lo que NO se hace (anti-distracción)

- ❌ Adoptar Lovable / migrar nada a no-code
- ❌ Implementar OKF en producción
- ❌ Pitchear a Francisco Igual / perseguir partnerships pre-tracción
- ❌ Desplegar backend mientras haya testers activos

---

## Anexo — Fuentes

- KW abre Command a terceros — Inman: https://www.inman.com/2026/02/23/keller-williams-opens-command-platform-to-3rd-party-developers/
- Real Brokerage adquiere RE/MAX $880M — Real Estate News: https://www.realestatenews.com/2026/04/27/real-remax-ceos-call-880m-deal-an-accelerator/
- RE/MAX AI — HousingWire: https://www.housingwire.com/articles/re-max-accelerates-real-estate-innovation-with-ai-and-technology/
- Francisco Igual "Claude para potenciar tu Inmobiliaria" — LinkedIn: https://es.linkedin.com/posts/francisco-igual-2b6365299_claude-para-potenciar-tu-inmobiliaria-activity-7440101218586370048-9MB8
- OKF SPEC v0.1 — GitHub: https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md
- OKF mejora el compartir datos — Google Cloud Blog: https://cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing/
- OKF, spec markdown vendor-neutral — MarkTechPost: https://www.marktechpost.com/2026/06/16/google-cloud-introduces-open-knowledge-format-okf-a-vendor-neutral-markdown-spec-for-giving-ai-agents-curated-context/
- ArcGIS for Real Estate (B2B) — Esri: https://www.esri.com/en-us/industries/real-estate/overview
- Geospatial AI en ArcGIS — Esri: https://www.esri.com/en-us/geospatial-artificial-intelligence/overview
- Sajit Thomas, Application Architect @ Esri — LinkedIn: https://www.linkedin.com/in/sajit-thomas-33a9a034/
- Realtor.com lanza RealAssist AI — Google Cloud Press: https://www.googlecloudpresscorner.com/2026-06-02-Realtor-com-R-Launches-RealAssist-TM-AI-A-Completely-Reimagined-Way-to-Find-A-Home
- RealAssist conversational search — RISMedia: https://www.rismedia.com/2026/06/08/realtor-com-launches-realassist-conversational-home-search-experience/
- "The AI House Hunter Meets a Skeptical Market" — PYMNTS: https://www.pymnts.com/artificial-intelligence-2/2026/the-ai-house-hunter-meets-a-skeptical-market/
- Eva — análisis de ubicación multifamiliar (Aino AI): https://eva.aino.world/
- Alex Kamenev (Aino AI) — LinkedIn: anuncio de Eva, jun 2026
- Cynthia Wu — "House Hunter Agent" (evidencia del foso de datos: portales gatekeepean los listados) — LinkedIn, jun 2026
- Aravind Srinivas (Perplexity) — "Context graphs / Perplexity Brain" (5ª validación, ver VISION_Sistema_Vivo): LinkedIn, jun 2026

---

*Generado el 16 jun 2026. Próxima revisión sugerida: fin de la semana 2 (29 jun), para medir avance del loop de contribución.*
