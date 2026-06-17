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

---

*Generado el 16 jun 2026. Próxima revisión sugerida: fin de la semana 2 (29 jun), para medir avance del loop de contribución.*
