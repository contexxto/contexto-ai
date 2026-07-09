# HANDOFF — Estado del proyecto AuraReal + Negociación Ricardo (2026-07-09)

> **Para la próxima sesión de Claude:** este documento ES el punto de partida. Léelo completo antes de actuar. Contexto del repo: `C:\Users\DETPC\Desktop\Contexto-AI`. Reglas permanentes al final.

---

## FRENTE 1 — AuraReal (negocio nuevo: storefronts PYME Quito) 🚦 FASE 1 ACTIVA

**Decisiones del fundador (2026-07-09), TODAS aplicadas en los artefactos:**
1. **Nombre: AuraReal** ("el aura real del lugar") — pendiente registro SENADI (clases 35/36/42) y compra de `aurareal.ec` (libres en chequeo DNS preliminar). Colisión consciente: Aura Group México (relevante para expansión MX futura). Torneo + racional: `lanzamiento-pyme/naming.md`.
2. **Monetización: el 360 ES el producto** — SaaS mensual "aurareal 360" con leads calificados incluidos (cupo mensual + excedente por fee fijo). Escalera: 0·tienda $0 piloto → 1·aurareal 360 → 2·inmobiliaria. NO hay tier de fee-por-lead standalone.
3. **Luz verde a Fase 1** (piloto manual): kit completo en `lanzamiento-pyme/FASE1_PILOTO.md`. **BLOQUEANTE ÚNICO: Carlos debe dar los nombres de 1-3 inmobiliarias candidatas + fecha de kickoff.**

**El paquete completo** (`Contexto-AI/lanzamiento-pyme/`, red-teameado con 33 ataques): `recap.html` (índice) · `pitch-onepager.md` · `guion-demo.md` · `pricing-detalle.md` · `landing.html` + `landing-v2.html` (borradores) · `PROMPT_LOVABLE.md` · `naming.md` · `red-team.md` · `FASE1_PILOTO.md`.

**Diseño:** decisión de Carlos — las páginas las hace **él en Lovable** (mi diseño "se ve igual en todas"); yo entrego prompt (hecho: `PROMPT_LOVABLE.md`, ya con AuraReal + 360) + QA de claims cuando pase la URL + la tech debajo. Referencia visual: CRED (`docs/branding/LINEA_GRAFICA_CRED_Storefronts.md` + 24 screenshots en `cred-reference/screenshots/`). La landing/tiendas van en **dominio separado** — contexxto.com NO se toca.

**Integración con webs existentes** (pregunta clave de Carlos, respondida): Nivel 1 (hoy, cero código): QR + `/a/{id}` + enlace "ver entorno verificado". Nivel 2 (backlog, gate = que el piloto lo pida): widget `<script>` del agente + ficha embebida. Nivel 3: API directa. Escalón 0 tiene dos puertas: montar tienda O conectar web existente.

**Mi backlog técnico Fase 1:** plantilla de storefront manual (reusa `/a/{id}` + agente) · leads etiquetados por fuente en CRM Vivo (tarea #33, en progreso) · conectar medición de lift (tarea #12) al reporte semanal.

## FRENTE 2 — Negociación Ricardo Sánchez (Mazatlán) 🤝 MESA POR DEFINIRSE

- **Situación:** Ricardo Sánchez preparó "PROYECTO INMOBILIAR-IA" (PDF: `C:\Users\DETPC\Downloads\PROYECTO INMOBILIAR IA.pdf`) como SU apertura de negociación. Sus 5 fallas ≈ 4 ya construidas en Quito + 1 spec. Sus 3 ideas buenas a adoptar con su autoría: riesgo físico/inundación, computer vision del inmueble, Legal Parser. Sus 3 zonas rojas (canon prohíbe): datos delictivos del barrio, AVM cifra puntual, Rent-Score de personas.
- **Documento de mesa LISTO:** `docs/ENCAJE_Mazatlan_Ricardo_1pager.md` (v2, red-teameada con 3 lentes / 24 findings — la v1 regalaba leverage). Claves de la v2: convergencia entre pares, Fase 0 protegida (confidencialidad mutua + standstill + "si valida se construye entre nosotros"), motor = activo escaso licenciado no transferido, foso legal vendido como existencia no como plano, Ricardo = co-autor de producto (no proveedor de contactos), producto local se llama INMOBILIAR-IA (su marca, motor debajo — arquitectura AuraReal).
- **Reglas de mesa:** documento se presenta; cero números primero; equity solo post-piloto ("la estructura se define con los números del piloto sobre la mesa"). 3 preguntas 80/20: ¿qué desarrollador pagaría HOY por un lead calificado? · ¿qué te ha frenado para arrancar solo? · ¿cómo te ves en 2 años?
- **Pendiente:** Carlos agenda la reunión (tarea #5, in_progress). Ofrecido: guion de apertura de 2 min.

## FRENTE 3 — Contexto-AI producción (estado técnico)

- **Shippeado y verificado (2026-07-08):** design system en suite de publicación (#117) · fix crash del mapa TDZ (#118) · PWA auto-update con toast (confirmado en el teléfono de Carlos) · flechas de chips del mapa funcionales · chat al design system + light-mode · robustez del map-chat (wait_for + graceful; causa raíz: latencia Google) · chip Instalar sin glow · toast reposicionado.
- **Plan estratégico pendiente de ejecutar:** migración map-chat Google → stack propio (`docs/PLAN_Migracion_MapChat_Google_a_Stack_Propio.md`). Hallazgo crítico: **tabla `pois_propios` está VACÍA en prod** (ingesta nunca corrió). Fase 1 = poblarla + cablear propio-primero. Documentado, NO ejecutado.
- **En progreso:** CRM Vivo (tarea #33).

## RAMAS SIN MERGEAR (piden "Mergéalo" de Carlos)
- `feat/aurareal-fase1` — el paquete lanzamiento-pyme completo (con decisiones aplicadas).
- `docs/negociacion-ricardo` — el 1-pager v2 + este handoff.
*(El canon estratégico del 07-08 — modelo, análisis Habi/Sierra, línea CRED, plan migración — YA está en main.)*

## DOCS CANON CLAVE (índice rápido)
`MODELO_Shopify_Inmobiliario_PYME.md` (el modelo de negocio) · `ANALISIS_Oportunidades_Habi_Sierra_2026-07.md` (mapa competitivo: la interfaz se commoditiza, el foso es la verdad verificada) · `PLAN_Estrategico_Mazatlan_Ricardo.md` (propuesta jun-2026) · `PRODUCTO_Encaje_Financiero_Neutral.md` (anti-patrón Habi, Fair Housing duro) · `docs/branding/LINEA_GRAFICA_CRED_Storefronts.md`.

## REGLAS PERMANENTES DE TRABAJO (no negociables)
1. **Merges a main SOLO con "Mergéalo" explícito de Carlos.** PRs/ramas se preparan, no se fusionan solas.
2. **Fair Housing estructural:** perfilamos lugares e inmuebles, JAMÁS personas. Exclusividad = del inventario verificado. Sin "seguridad" social del barrio (riesgo físico sí). Sin steering. El Estratega no ve leads individuales.
3. **Honestidad de asteriscos:** estimación ≠ medición, cifras con proveniencia o rótulo "hipótesis", el "3x" NO existe hasta que la tarea #12 lo mida. Cite-don't-assert para fuentes externas.
4. **Design system:** tokens (no hardcodes), lucide (no emojis en UI), chips rectangulares, mapa siempre oscuro, chip "Voz" consistente. CRED-line solo para AuraReal/storefronts (la app mantiene ASI/teal).
5. **Datos reales del piloto son REALES** — nunca sembrar datos fabricados ni tocar prod sin consentimiento.
6. **Workflows (ultracode):** los workers van en `model:'opus'`/`'sonnet'` explícito para no quemar créditos Fable (patrón Nate: el caro orquesta, los baratos ejecutan). Red-team adversarial antes de todo entregable importante — cazó bugs/fugas reales 3 veces esta semana.
7. **Skill `modo-fable`** cargada a nivel usuario (5 pasos: scoping adversarial → evidencia → ataque → verificación → reporte calibrado). Activar en tareas complejas.
8. **A7/gates:** nada de self-serve antes de validar el piloto; nada de equity antes de resultados; scope profundo, no ancho (P5).

## PRÓXIMAS ACCIONES (en orden)
1. **Carlos:** nombres de 1-3 inmobiliarias piloto + kickoff → desbloquea TODO el Frente 1.
2. **Carlos:** agendar reunión Ricardo (llevar el 1-pager v2) · comprar `aurareal.ec` · búsqueda SENADI.
3. **Carlos (paralelo):** Lovable con `PROMPT_LOVABLE.md` + capturas CRED → pasar URL para QA.
4. **Claude (al desbloquearse 1):** plantilla storefront manual + leads por fuente + montaje del primer piloto.
5. **Claude (cuando Carlos diga):** ejecutar Fase 1 de la migración a stack propio (poblar `pois_propios`).
