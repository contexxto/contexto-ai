# CONTEXTO AI · DECLARACIÓN DE FRONTERA 0.1
## De inteligencia del lugar a infraestructura contextual para decisiones del mundo físico
**Una ciudad a la vez.**  
29 de agosto de 2026 · Documento estratégico declaratorio / no normativo

> **Regla de lectura:** [VERIFICADO] = evidencia directa; [OBSERVADO] = interfaz/comportamiento; [INFERIDO] = lectura razonable; [HIPÓTESIS] = debe validarse; [DESCONOCIDO] = evidencia insuficiente. Este documento no modifica el Execution Plan 1.0.

## Declaración
**TESIS CENTRAL**
[HIPÓTESIS DECLARATORIA]
Contexto AI está intentando construir, ciudad por ciudad, una infraestructura de capacidades locales verificables para que humanos y agentes puedan comprender una situación del mundo físico, tomar una decisión de alta consecuencia y actuar dentro de límites explícitos.
Real Estate es el primer campo de prueba. Contexxto es el primer cliente del core. La visión no presupone que la infraestructura multiindustria ya exista, ni que exista todavía un mercado pagador.
La apuesta es más específica: a medida que la inteligencia de los modelos de frontera se vuelve más abundante, una parte creciente del cuello de botella se desplaza hacia contexto local, institucional, temporal y operacional que los modelos no reciben automáticamente con cada nueva versión. Ese contexto debe encontrarse, verificarse, normalizarse, versionarse, aplicarse a una decisión y mantenerse vivo.
Una ciudad a la vez. Una jurisdicción a la vez. Una clase de decisión a la vez.

## 1. La frontera que se amplía
La tesis inicial de Contexto era comprender el lugar: geografía, POIs, accesibilidad, movilidad, catastro, evidencia y razonamiento. La evolución agentic agregó BuyerContext, PropertyContext, DecisionContext y DecisionTrace. La nueva entrada revela una dimensión que estaba parcialmente fuera del encuadre: una propiedad no existe sólo en un punto del mapa; existe dentro de un sistema institucional y económico local.
[VERIFICADO — CONTEXTO] El Blueprint ya exige que el Place Harness pregunte qué información necesita una decisión específica, en lugar de recuperar “todo sobre el lugar”, y que el Buyer Agent sea un orquestador delgado. [INT-06][INT-07]
[VERIFICADO — EXTERNO] Zillow publica una arquitectura similar en espíritu: un agente central interpreta intención y coordina skills verticales de búsqueda, financiación, valoración y comprensión del hogar; la respuesta se ensambla desde datos, lógica y modelos especializados. [EXT-04][EXT-05]
[INFERIDO] La misma lógica puede expandirse desde PlaceContext hacia un Context Fabric: el agente no debe memorizar derecho, tasación, riesgo o fiscalidad dentro de un prompt gigantesco. Debe saber qué capacidad necesita, bajo qué jurisdicción y con qué evidencia.

## 2. Por qué los modelos de frontera no eliminan este problema
Los modelos de frontera pueden mejorar de forma radical en lectura, razonamiento, planificación y uso de herramientas. Eso reduce el coste de construir Contexto, pero no elimina automáticamente el trabajo local.
Un modelo puede explicar qué es una servidumbre. No garantiza cuál servidumbre afecta a esta parcela. Puede leer una ordenanza. No sabe por sí solo si esa versión sigue vigente, qué anexo espacial aplica a este predio, qué excepción municipal la modifica o qué documento oficial prevalece ante una contradicción. Puede explicar valoración. No convierte automáticamente un precio publicado, un avalúo catastral, un valor hipotecario y un valor comercial en la misma cosa.
[VERIFICADO — EXTERNO] OpenAI Frontier identifica precisamente el déficit de contexto, acceso, permisos, límites y feedback como uno de los problemas para poner agentes en producción. [EXT-02]
[VERIFICADO — LOCAL] Quito materializa este problema: el PUGS vigente asigna uso, ocupación, edificabilidad y gestión del suelo, y su geoservicio contiene capas de protección, infraestructura, vialidad, conservación y actualizaciones. [EXT-11][EXT-12] El Registro de la Propiedad emite certificados con dominio, forma de adquisición, antecedentes, gravámenes y limitaciones, y la inscripción de actos exige análisis y calificación jurídica local. [EXT-13][EXT-14]
[INFERIDO] La barrera no es “conocimiento escondido del LLM”. Es aplicabilidad: qué es verdad aquí, ahora, para este activo, objetivo, jurisdicción y operación, con qué autoridad y qué incertidumbre.

## 3. La unidad de la compañía: la decisión, no el chat
La unidad canónica que proponemos no es la conversación, el listing ni la llamada a un modelo. Es una decisión reconstruible.
PERSON × OBJECTIVE × PROPERTY × PLACE × CONTEXT RELEVANTE → DECISION → TRACE → ACTION → OUTCOME
[VERIFICADO — CONTEXTO] El diseño vigente ya separa BuyerContext, PropertyContext, PlaceContext, DecisionContext y DecisionTrace, y ordena calcular antes de narrar. [INT-06][INT-07]
[INFERIDO — REFERENCIA ENTER] El caso Enter refuerza el patrón: la unidad durable es el caso; alrededor de ella se combinan fuentes, documentos, estado estructurado, reglas/modelos, evidencia, revisión humana y outcome. [INT-13][EXT-06]
[INFERIDO — REFERENCIA STRIPE] Stripe ofrece otro patrón útil: PaymentIntent encapsula un flujo complejo con estado, autenticaciones adicionales y cambios regulatorios/regionales. Contexto no debe copiar pagos, pero sí aprender la abstracción: representar un proceso difícil mediante objetos y capacidades con lifecycle explícito. [EXT-03]
La pregunta central deja de ser “¿qué responde el agente?” y pasa a ser “¿qué decisión estamos intentando sostener y qué capacidades deben participar para sostenerla?”.

## 4. Contexto 360: las capas que una decisión puede necesitar
Una visión 360 no significa recuperar todos los datos siempre. Significa disponer de un mapa de dimensiones y seleccionar sólo las que son materialmente necesarias para la decisión.
1) Persona y objetivo: restricciones duras, preferencias blandas, anclas, horizonte, presupuesto, tolerancia al riesgo, preguntas no resueltas.
2) Identidad del activo: parcela, edificio, unidad, listing, proveedor, identidad persistente y reconciliación entre fuentes.
3) Activo físico: estructura, estado, patologías, mantenimiento, instalaciones, vida útil, accesibilidad, CAPEX probable.
4) Edificio y gobernanza: propiedad horizontal, alícuotas, expensas, fondo de reserva, morosidad, reglamento, obras extraordinarias y litigios del condominio.
5) Lugar: accesibilidad, POIs, movilidad, tiempos, caminabilidad, servicios, morfología y experiencia espacial.
6) Jurisdicción y derechos: dominio, gravámenes, servidumbres, hipotecas, restricciones, prohibiciones, antecedentes y otros derechos reales.
7) Regulación urbanística: uso de suelo, compatibilidades, edificabilidad, altura, retiros, densidad, patrimonio, licencias, afectaciones y planes futuros.
8) Valoración: comparables, metodología, ajustes, rango, confianza, liquidez y fecha de mercado.
9) Mercado: inventario, absorción, vacancia, rentas, descuentos de cierre, días en mercado y profundidad.
10) Finanzas: financiación, LTV, entrada, tasa, plazo, moneda, coste de capital y capacidad de pago cuando sea lícito y pertinente.
11) Fiscal/TCO: impuestos, tasas, registro, notaría, corretaje, seguros, mantenimiento, condominio, financiación y coste de salida.
12) Riesgo y resiliencia: sismo, deslizamiento, inundación, volcanismo, incendios, drenaje, vulnerabilidad del activo y mitigación.
13) Ambiental/habitabilidad: ruido medido, aire, sol, sombra, humedad, isla de calor, vegetación, olores y exposición.
14) Infraestructura: agua, alcantarillado, energía, telecomunicaciones, fibra, drenaje, capacidad vial y resiliencia de redes.
15) Movilidad real: frecuencia, confiabilidad, congestión, primera/última milla, pendientes, transbordos, p50/p95 por horario.
16) Transacción/procedimiento: documentos, actores, secuencia, plazos, due diligence, registro, entrega y gates.
17) Seguros: asegurabilidad, exclusiones, prima, deducibles y requisitos de financiadores.
18) Actores e incentivos: quién representa a quién, quién paga a quién, conflictos de interés, responsabilidad y autoridad de cada fuente.
19) Tiempo: vigencia, observed_at, effective_from/to, cambios, planes aprobados versus anunciados y freshness.
20) Conocimiento humano local: inspección, tasador, ingeniero, registrador, administrador, corredor, vecino o experto; evidencia estructurada, no “folklore” sin provenance.
21) Evidencia y autoridad: metacapa transversal que clasifica fuente, metodología, vigencia, confianza, conflictos, limitaciones y permiso de persistencia.
[VERIFICADO — LOCAL] La Superintendencia de Bancos mantiene un régimen de calificación para peritos valuadores; esto ilustra que “valor” puede requerir una capacidad profesional regulada, no sólo una inferencia del modelo. [EXT-15]
[DECISIÓN DE DISEÑO PROPUESTA] `unknown` e `insufficient_evidence` siguen siendo estados válidos. Ninguna dimensión debe entrar al scoring sólo porque sea interesante.

## 5. Context Fabric: de capas de datos a capacidades componibles
[HIPÓTESIS DE ARQUITECTURA]
El siguiente salto conceptual es un Context Fabric: una infraestructura que resuelve capacidades especializadas y devuelve objetos estructurados, no sólo prosa.
El agente pregunta: “¿Qué necesito saber para esta decisión?” El Context Selector construye un plan de capacidades. Un Capability Registry conoce qué servicios existen, versiones, jurisdicciones cubiertas, inputs, outputs, evidencia y límites.
Ejemplo: una compra residencial no tiene por qué invocar zoning profundo si no cambia la decisión; un desarrollo inmobiliario sí. Un banco puede necesitar valoración, derechos y riesgo; un turista no.
La reutilización nace de la composición, no de construir un producto multiindustria genérico.
CONTEXT SELECTOR → CAPABILITY PLAN → STRUCTURED RESULTS → DECISION ENGINE → TRACE
[VERIFICADO — CONTEXTO] Esta idea extiende, no contradice, E4.3 Context Selector del Execution Plan: recuperar sólo las dimensiones necesarias reduce coste, latencia y ruido. [INT-07]

## 6. Arquitectura de capacidades delegables
No proponemos extraer hoy 25 microservicios de red. Proponemos 25 servicios lógicos potenciales con contratos explícitos.
Regla: DISEÑAR COMO SERVICIOS → DESPLEGAR SIMPLE → EXTRAER SÓLO CUANDO HAYA EVIDENCIA.
Un servicio lógico debería poder evolucionar a microservicio independiente cuando exista una razón concreta: carga/latencia propia, seguridad o aislamiento regulatorio, SLA distinto, ownership separado, tecnología especializada, reutilización externa o necesidad de escalado independiente.
Esto preserva la regla actual del proyecto: modularizar el monolito, no distribuirlo prematuramente. [INT-07]
Contrato común candidato (`ContextCapabilityResult`): capability + version + subject + jurisdiction + geographic_scope + temporal_scope + result + evidence + methodology + confidence + freshness + limitations + conflicts + unknowns + requires_human_review + persistence_policy + computed_at.
[HIPÓTESIS] Si capabilities muy distintas hablan este mismo lenguaje, DecisionTrace puede consumirlas de forma homogénea y la plataforma se vuelve componible.

## 7. Una capacidad no pertenece a una transacción
El mismo servicio debe poder participar en más de un flujo. Ésa es la prueba de que estamos construyendo infraestructura y no features desechables.
Valuation: compra (¿pago demasiado?), venta (¿en qué rango salir?), crédito (¿qué LTV?), seguros (¿qué valor asegurable?), inversión (¿qué valor frente al flujo?), desarrollo (¿qué valor residual del suelo?).
Risk: compra, banco, aseguradora, desarrollador, municipio e infraestructura.
Jurisdiction/Regulatory: compraventa, arrendamiento, desarrollo, retail, construcción y planificación urbana.
Place/Mobility: vivienda, oficinas, retail, turismo, logística, salud y planificación.
[HIPÓTESIS DE REUTILIZACIÓN] El vertical no desaparece: cambia la composición. Cada industria puede requerir experiencia, datos y modelos distintos sobre una infraestructura común.

## 8. El agente como orquestador, no como experto monolítico
El agente de Contexto debería mejorar en una habilidad distinta de “saberlo todo”: saber qué necesita una decisión y delegar trabajo en capacidades con contratos.
1. Comprender el objetivo.
2. Resolver entidades e identidad.
3. Determinar contexto material.
4. Reutilizar lo ya verificado.
5. Invocar capabilities faltantes.
6. Aplicar restricciones y policies fuera del LLM cuando sea posible.
7. Detectar conflicto/no-data.
8. Solicitar revisión humana cuando el riesgo lo exija.
9. Construir DecisionContext.
10. Registrar DecisionTrace.
11. Proponer acción.
12. Pasar por Action Gateway/mandato antes de ejecutar.
13. Conectar outcome al run.
[VERIFICADO — EXTERNO] AWS ya aplica límites de pago en la capa de infraestructura; Google/Mastercard trabajan con instrucciones preautorizadas e intent verificable. [EXT-07][EXT-08][EXT-09]
[INFERIDO] El patrón general es transferible: el modelo recomienda o selecciona tools; las restricciones críticas y la autoridad no deben depender de que el modelo “recuerde” obedecerlas.

## 9. El método de expansión: una ciudad a la vez
La geografía deja de ser un simple mercado de lanzamiento. Se convierte en la unidad de construcción del contexto local.
Modelo conceptual candidato:
CONTEXT CORE + COUNTRY PACK + CITY/JURISDICTION PACK + DOMAIN PACK + DECISION PROFILE
No sabemos todavía qué porcentaje será reusable entre ciudades. Ese desconocimiento debe convertirse en una métrica, no en una promesa.
Quito puede ser el primer laboratorio porque Contexto ya concentra allí parte importante de su capa geoespacial y el Execution Plan la mantiene como mercado técnico por defecto. [INT-07]
Un Quito Pack futuro no sería “un dataset”. Sería la capacidad operacional de resolver, con fuentes y versiones: identidad predial; PUGS; derechos/registro; movilidad; riesgos; infraestructura; valoración local; mercado; procedimientos; evidencia; y expertos cuando corresponda. [EXT-11][EXT-12][EXT-13][EXT-14][EXT-15]
Regla: una ciudad está “cubierta” no cuando tenemos muchos datos, sino cuando podemos sostener una clase definida de decisiones con cobertura, evidencia, freshness y límites medibles.

## 10. Qué puede convertirse en foso — y qué no
No es foso: usar un LLM de frontera; descargar OSM/Overture; tener PDFs de leyes; vectorizar ordenanzas; llamar Google Maps; crear una API; poseer más prompts.
Puede empezar a ser foso: identidad resuelta entre sistemas; reglas normalizadas con vigencia y ámbito de aplicación; evidence graph con autoridad; metodologías locales de cálculo; historial de conflictos/correcciones; red de verificación humana; datasets de evals por decisión; DecisionTrace reproducible; outcomes conectados; actualización operationalizada; capacidad de incorporar una nueva jurisdicción cada vez con menos coste.
[INFERIDO] El activo acumulativo es know-how operacional codificado: qué fuente confiar, qué regla aplica, qué dato no se puede persistir, qué excepción invalida el cálculo, qué profesional debe revisar, qué fallo se repite y qué outcome contradijo al sistema.
Ese aprendizaje no desaparece automáticamente cuando sale un modelo mejor. Un modelo mejor puede hacerlo más barato de explotar.

## 11. Stripe, Enter y Contexto: la analogía correcta
Stripe es referencia de abstracción, no de mercado. Enter es referencia de profundidad vertical, no de arquitectura que debamos copiar.
[VERIFICADO — STRIPE] PaymentIntent sigue un lifecycle y activa autenticación adicional cuando es necesaria; Stripe presenta estos objetos como forma de gestionar flujos complejos y prepararse para nuevas regulaciones y métodos regionales. [EXT-03]
[VERIFICADO — ENTER, NIVEL PÚBLICO] Sequoia describe a Enter como una compañía que ayuda a grandes empresas a usar IA para mejorar la eficiencia jurídica mediante análisis documental exhaustivo. [EXT-06] [INFERIDO — ESTUDIO CONTEXTO] El caso estudiado muestra un patrón context-first con estado, reglas/modelos, evidencia, revisión humana y outcome. [INT-13]
[HIPÓTESIS PARA CONTEXTO] Nuestra compañía podría combinar ambos patrones: abstraer complejidad local en primitives/capabilities y, al mismo tiempo, dominar profundamente la unidad de decisión hasta el outcome.
La aspiración no es “ser el Stripe del real estate”. Es construir una compañía con disciplina de infraestructura: contratos claros, complejidad absorbida, observabilidad, reversibilidad, jurisdicción, seguridad y reliability.

## 12. Relación con HomeSelf, Zillow, Nexor y Agentic Commerce
HomeSelf empuja la representación: identidad persistente, provenance, freshness, AnswerPack y superficies machine-readable. Su límite público sigue siendo adopción/interoperabilidad y causalidad económica. [INT-14]
Zillow demuestra integración vertical: inventario vivo + contexto financiero + valoración + comprensión del hogar + usuario + safeguards + acciones. [EXT-04][EXT-05][INT-12]
Nexor aporta trace/outcome: run identity, historial, tools, evals y conversion events inspiran un `DecisionTrace` canónico y outcome attribution. [INT-09]
Agentic Commerce aporta el cambio de cliente: Build ahora; Coordinate más adelante si agentes externos necesitan consumir Contexto y existe demand/lift. [INT-10]
Visa/Mastercard/Google/AWS/Rain empujan la mitad derecha del stack: identidad, intención, autorización, límites, ejecución y pagos. [EXT-07][EXT-08][EXT-09][EXT-10][INT-15]
[HIPÓTESIS] Contexto intenta ocupar la mitad anterior: ¿qué decisión debería tomarse, con qué contexto y evidencia, antes de que otra infraestructura autorice y ejecute?

## 13. Principios declaratorios de arquitectura
1. CONTEXTO ANTES QUE GENERACIÓN. La prosa nunca reemplaza al objeto fuente.
2. APLICABILIDAD ANTES QUE ACUMULACIÓN. Importa qué regla/dato aplica, no cuántos documentos almacenamos.
3. EVIDENCIA ANTES QUE CONFIANZA. Todo claim material debe poder señalar fuente, fecha y metodología.
4. UNKNOWN ES UN RESULTADO. `insufficient_evidence` es preferible a precisión fabricada.
5. CÁLCULO ANTES QUE NARRACIÓN. Aritmética, constraints y reglas críticas fuera del LLM cuando sea posible.
6. LA DECISIÓN ES LA UNIDAD. El chat es una interfaz; la decisión debe sobrevivirla.
7. TRACE ES PARTE DEL PRODUCTO. No reconstruir el porqué retrospectivamente.
8. ACTION ≠ DECISION. Autoridad y mandato son fronteras separadas.
9. SERVICIOS LÓGICOS, DESPLIEGUE SIMPLE. No microservicios por ideología.
10. LOCAL POR DISEÑO. Jurisdicción, vigencia y ciudad son first-class.
11. HUMANO CUANDO LA RESPONSABILIDAD LO EXIJA. La revisión profesional debe ser estructural, no un disclaimer genérico.
12. OUTCOME CIERRA EL LOOP. Una decisión sin resultado observado sólo enseña parcialmente.
13. PRODUCTOS CONSUMEN EL CORE. Contexxto valida la infraestructura; no la encierra.
14. REUSO DEBE MEDIRSE. “Multiindustria” sólo existe cuando una segunda composición reutiliza capacidades sin rehacer el sistema.
15. LA ARQUITECTURA SE GANA CON EVIDENCIA. No construir la plataforma futura por anticipación.

## 14. Lo que no construiremos ahora
Este documento amplía la frontera estratégica, no el scope inmediato.
NO: reescribir el monolito en microservicios; crear una ontología universal; construir motores legales de todos los países; autodenominarnos plataforma multiindustria; construir MCP/A2A por anticipación; automatizar asesoría jurídica sin review; llamar “tasación” a una estimación no profesional; crear un único score 360 que oculte incertidumbre; expandir ciudades antes de definir cobertura mínima; inventar protocolos propios de identidad/mandato si estándares externos pueden resolverlo.
SÍ: diseñar contracts que no impidan esta evolución; preservar jurisdiction/evidence/time; identificar cada nueva feature como capability reusable o flujo vertical; incorporar la dimensión local al diseño de DecisionTrace; y medir cuándo una separación física de servicio está justificada.
[DECISIÓN DE GOBERNANZA] Execution Plan 1.0 continúa siendo la verdad de ejecución. Esta declaración es estratégica/no normativa.

## 15. Qué tendríamos que demostrar para merecer esta visión
La visión sólo gana legitimidad si supera una secuencia de pruebas.
GATE 1 — DECISION LIFT. Contexto produce mejores decisiones que el mejor baseline permitido, no sólo respuestas más bonitas.
GATE 2 — EVIDENCE INTEGRITY. Claims materiales tienen provenance/freshness suficientes y los datos faltantes degradan explícitamente.
GATE 3 — EXPERT CORRECTION. Podemos medir cuándo tasadores, abogados, ingenieros o actores locales corrigen al sistema y convertirlo en mejora.
GATE 4 — CASE REPLAY. Una decisión puede reconstruirse exactamente desde contexts, tool outputs, rules, model/policy versions y evidence refs.
GATE 5 — OUTCOME LINK. Podemos conectar decisiones con acciones/resultados sin confundir correlación comercial con calidad factual.
GATE 6 — REUSE. Una segunda clase de decisión reutiliza capacidades materiales sin reconstrucción total.
GATE 7 — CITY TRANSFER. Una segunda ciudad permite medir qué porcentaje del core se conserva, qué adapters exige y cuánto cuesta alcanzar cobertura.
GATE 8 — BUYER. Una organización paga por la mejora o integra la capacidad porque resuelve un problema material.
Si fallan, reducimos la tesis. La arquitectura no convierte automáticamente una ambición en un negocio.

## 16. Métricas de madurez de infraestructura
Proponemos medir la infraestructura con métricas que sobreviven a cambios de interfaz y de modelo:
- % de claims materiales con evidence_ref válido.
- % de features con status measured/derived/estimated/insufficient_evidence.
- Freshness SLA por capability/jurisdicción.
- Conflict rate entre fuentes y tiempo de resolución.
- Expert override/correction rate.
- Critical error rate por decisión.
- Decision lift vs baseline.
- Trace replay success rate.
- Outcome attribution coverage.
- Reuse ratio: capacidades compartidas entre dos decision profiles.
- New-jurisdiction integration time/cost.
- % de lógica crítica deterministic/policy-gated fuera del LLM.
- Human-review rate y razón.
- Runtime cost/latency por decision profile.
[HIPÓTESIS] Si estos indicadores mejoran con cada ciudad y cada decisión, podremos afirmar con más evidencia que existe una infraestructura acumulativa.

## 17. Primer experimento de la nueva frontera
No proponemos construir un Legal Harness completo. Proponemos un `Decision Case Loop` en Quito que obligue a descubrir qué contextos faltan.
Caso candidato: evaluar una propiedad residencial real para compra.
Entrada: BuyerContext real + PropertyContext real + PlaceContext actual.
Pregunta: ¿qué afirmaciones materiales para decidir no puede sostener hoy el sistema?
Luego agregar sólo las capacidades estrictamente necesarias, por ejemplo: Rights/Title snapshot; Regulatory applicability; Valuation range con metodología; Building/inspection checklist; TCO; Risk.
Para cada capability: fuente oficial/profesional → contrato → deterministic checks cuando existan → evidence refs → limitations → human review boundary → eval.
Resultado: no “un producto 360”, sino un mapa empírico de qué piezas cambian una decisión y cuáles son ruido.
[DECISIÓN PROPUESTA] Este experimento debe ocurrir después del gate actual y sin interrumpir la ejecución autorizada.

## 18. Doctrina fundadora para esta etapa
**DECLARACIÓN DE EJECUCIÓN**
La conversación de Sam Altman aporta una regla de gobierno más que una feature: una misión enorme necesita un gradiente medible. La apuesta no es creer que algo imposible será cierto; es encontrar una prueba que permita avanzar o abandonarlo. [INT-17][EXT-01]
Contexto debe conservar las dos mitades:
AMBICIÓN: construir infraestructura contextual del mundo físico que pueda convertirse en una categoría mayor.
DISCIPLINA: Real Estate primero; Quito primero; una decisión primero; evidencia antes que arquitectura; matar ideas buenas que distraen de la prueba principal.
Principio interno propuesto:
“La ambición determina qué problema vale la pena intentar. La evidencia determina si tenemos derecho a seguir intentándolo.”

## 19. Declaración final
**CIERRE**
[HIPÓTESIS CENTRAL — V0.1]
La inteligencia general puede volverse abundante. El contexto local confiable no aparece automáticamente con ella.
Contexto AI intenta convertir ese contexto —físico, institucional, económico, temporal y humano— en capacidades computables, versionadas y verificables. Un agente puede componerlas para entender una situación, evaluar alternativas, producir una decisión reconstruible y proponer una acción dentro de límites explícitos.
La compañía no será definida por un chatbot, un mapa, un portal ni un único vertical. Tampoco por una colección de microservicios. Será definida, si la evidencia lo permite, por la capacidad acumulativa de absorber complejidad local y devolver decisiones más confiables.
Contexxto es el primer cliente. Real Estate es la primera prueba. Quito es el primer territorio.
No sabemos todavía si la tesis es suficientemente valiosa, reutilizable o defendible. Lo vamos a descubrir construyendo la mínima capacidad necesaria para una decisión real, midiéndola contra alternativas fuertes y repitiendo sólo lo que produzca lift.
Una ciudad a la vez. Una decisión a la vez. Una capa de contexto a la vez.

## 20. Catálogo inicial de capabilities
| Capability | Pregunta |
|---|---|
| Identity | ¿De qué entidad física/jurídica hablamos exactamente? |
| Property | ¿Qué sabemos del activo y su estado comercial? |
| Building | ¿Qué sabemos del edificio y su gobernanza? |
| Place | ¿Qué implica estar allí? |
| Mobility | ¿Cómo se conecta realmente con destinos relevantes? |
| Infrastructure | ¿Qué redes/servicios existen y con qué capacidad? |
| Jurisdiction | ¿Qué niveles normativos aplican? |
| Rights & Title | ¿Qué derechos, gravámenes y limitaciones existen? |
| Regulatory | ¿Qué se puede hacer allí y bajo qué reglas? |
| Valuation | ¿Qué rango de valor puede defenderse y con qué incertidumbre? |
| Market | ¿Qué está ocurriendo en el mercado local? |
| Finance | ¿Cómo se financia y cuál es su coste? |
| Tax & TCO | ¿Cuál es el coste total de poseer/operar/salir? |
| Risk | ¿A qué riesgos está expuesto el activo/lugar? |
| Environmental | ¿Qué condiciones ambientales son materiales? |
| Insurance | ¿Es asegurable y bajo qué condiciones? |
| Transaction | ¿Cómo se ejecuta esta operación en esta jurisdicción? |
| Document | ¿Qué documentos existen, faltan o se contradicen? |
| Evidence | ¿De dónde sale cada claim y qué autoridad tiene? |
| Temporal | ¿Qué está vigente, qué cambió y qué quedó obsoleto? |
| Human Verification | ¿Qué requiere revisión profesional o terreno? |
| Decision | ¿Qué alternativa se sostiene bajo el objetivo? |
| Trace | ¿Cómo reconstruimos exactamente la decisión? |
| Action Gateway | ¿Qué acción está permitida y quién debe autorizarla? |
| Outcome | ¿Qué ocurrió y qué aprendemos? |

## 21. Ejemplos de composición
| Decision profile | Composición candidata |
|---|---|
| Compra residencial | Buyer + Property + Building + Place + Mobility + Valuation + Finance + Rights + Risk + TCO |
| Arrendamiento | Buyer + Property + Place + Mobility + Building + Transaction + TCO |
| Propietario: vender/arrendar/mantener | Property + Market + Valuation + Tax/TCO + Transaction + Risk |
| Desarrollo inmobiliario | Parcel/Identity + Jurisdiction + Regulatory + Infrastructure + Market + Valuation + Risk + Finance |
| Banco / crédito | Property + Rights + Valuation + Risk + Insurance + Finance + Trace |
| Aseguradora | Property + Building + Risk + Environmental + Valuation + Evidence |
| Broker / inmobiliaria | Buyer + Property + Place + Decision + Transaction + Trace |
| Retail location | Objective + Place + Mobility + Demand/Market + Competition + Regulatory + Infrastructure + Cost |
| Municipio / planificación | Place + Infrastructure + Mobility + Risk + Demography + Regulatory + Temporal + Evidence |

## 22. Registro de fuentes internas
- **INT-01 — CONTEXTO_AI_AUDITORIA.docx.** Auditoría integral del estado del producto y repositorio, 19-ago-2026; snapshot técnico, no estado eterno.
- **INT-02 — CONTEXTO_AI_ARQUITECTURA.docx.** Arquitectura real verificada; PostGIS, agentes, motores deterministas y providers.
- **INT-03 — CONTEXTO_AI_INVENTARIO.docx.** Inventario de funcionalidades y niveles de evidencia.
- **INT-04 — CONTEXTO_AI_ONE_PAGE.docx.** Síntesis de activos, riesgos y brechas verificadas.
- **INT-05 — PROJECT_AI_MASTER_STRATEGY_0.2.md.** Tesis infraestructura/persona-propiedad-lugar-decisión; baseline inventario + Maps/LLM; agentes como consumidor potencial.
- **INT-06 — Contexto_Real_Estate_Agentic_Decision_System_Product_Technical_Blueprint_0.1.** Contratos Buyer/Property/Place/Decision/Trace; context selector; agent como orquestador.
- **INT-07 — Contexto_Agentic_Decision_System_Execution_Plan_1.0.** Plan normativo de ejecución: core first, Contexxto como cliente de referencia, gates por evidencia.
- **INT-08 — 08_BUYER_HARNESS_STRATEGIC_REFERENCE.md.** Historial no es comprensión; hard constraints ≠ preferencias; conocimiento, inferencia y permiso son distintos.
- **INT-09 — 09_NEXOR_AGENTIC_INFRASTRUCTURE_REFERENCE.md + deep-research-report.md.** Trazas, run identity, evals, tool governance y conexión con outcomes.
- **INT-10 — 10_CONTEXTO_AGENTIC_COMMERCE_ESTUDIO_1.1.docx.** Build ahora; Coordinate-ready por diseño; interacción con agentes externos sólo tras evidencia.
- **INT-11 — 11_CONTEXTO_AI_TESIS_CONFIANZA_DELEGADA_0.1.docx.** Contexto verificable → decisión → trace → autoridad → acción; BuyerContext ≠ Mandate.
- **INT-12 — Zillow AI Mode y la transición de buscar vivienda a delegar decisiones inmobiliarias.docx.** Arquitectura multiagente vertical, inventario, financiación, valoración, contexto y acciones.
- **INT-13 — 10_ENTER_CONTEXT_FIRST_AGENTIC_OS_REFERENCE_EDITABLE.docx.** Caso context-first: fuentes + estado + reglas/modelos + evidencia + revisión humana + outcome.
- **INT-14 — HomeSelf AI: auditoría profunda del principio de legibilidad computacional y del protocolo VPR.** Identidad persistente, representación estructurada, provenance, freshness, AnswerPack y límites de adopción.
- **INT-15 — Verificación de pagos agénticos.txt.** Autoridad, límites y trazabilidad se están industrializando; la decisión ocurre antes del mandato/pago.
- **INT-16 — Contexto_Brand_Kit_2026_v1.docx.** Identidad visual y doctrina de procedencia: medir, declarar origen, rotular estimaciones.
- **INT-17 — Pasted text(7).txt — Sam Altman × David Senra.** Transcripción aportada por el fundador: apuestas no consensuadas, gradiente, inercia de adopción, founder fluency y matar ideas buenas.

## 23. Fuentes externas primarias / oficiales
- **EXT-01 — OpenAI — Introducing OpenAI (11-dic-2015).** El resultado era incierto y el trabajo difícil; ambición sin pretender certeza.  
  https://openai.com/index/introducing-openai/
- **EXT-02 — OpenAI — Introducing OpenAI Frontier (5-feb-2026).** Los agentes empresariales necesitan contexto, herramientas, identidad, permisos, límites y feedback; el cuello no es sólo inteligencia del modelo.  
  https://openai.com/index/introducing-openai-frontier/
- **EXT-03 — Stripe — Payment Intents API.** Patrón de abstracción: objeto con estado/lifecycle que absorbe complejidad, autenticación y cambios regulatorios/regionales.  
  https://docs.stripe.com/payments/payment-intents
- **EXT-04 — Zillow — How Zillow’s new AI mode works throughout the real estate journey (25-mar-2026).** Agente central coordina skills especializados; respuesta ensamblada con datos, lógica y modelos verticales.  
  https://www.zillow.com/news/how-zillows-new-ai-mode-works-throughout-the-real-estate-journey/
- **EXT-05 — Zillow — Zillow debuts AI mode (25-mar-2026).** Memoria, listings vivos, comparaciones, asequibilidad y acciones reales.  
  https://www.zillow.com/news/zillow-debuts-ai-mode/
- **EXT-06 — Sequoia Capital — Enter company profile.** Enter aplica IA a análisis jurídico exhaustivo para grandes empresas; referencia externa al caso de infraestructura vertical.  
  https://sequoiacap.com/companies/enter
- **EXT-07 — AWS — AgentCore Payments GA (18-ago-2026).** Límites configurables en infraestructura y observabilidad end-to-end para agentes transaccionales.  
  https://aws.amazon.com/about-aws/whats-new/2026/08/bedrock-agentcore-payments-ga/
- **EXT-08 — Google — AP2 to FIDO Alliance (28-abr-2026).** Human Not Present con instrucciones preautorizadas; accountability mediante intent verificable.  
  https://blog.google/products-and-platforms/platforms/google-pay/agent-payments-protocol-fido-alliance/
- **EXT-09 — Mastercard — Verifiable Intent (5-mar-2026).** Vincula identidad, intención y acción; la confianza se vuelve parte central del producto.  
  https://www.mastercard.com/global/en/news-and-trends/stories/2026/verifiable-intent.html
- **EXT-10 — Rain — Agentic Payments Alliance (18-ago-2026).** Coalición para autorización, fraude, rewards y estándares emergentes de agentic commerce.  
  https://www.prnewswire.com/news-releases/rain-launches-the-agentic-payments-alliance-to-guide-the-future-of-agent-driven-commerce-302853532.html
- **EXT-11 — Municipio de Quito / Hábitat — Geovisores PUGS 2024.** Normativa urbanística vigente: uso, ocupación, edificabilidad y gestión del suelo.  
  https://habitat.quito.gob.ec/geovisore
- **EXT-12 — GeoQuito — PUGS 2024 MapServer.** Capas espaciales de protección, infraestructura, vialidad, áreas de conservación y actualizaciones PUGS.  
  https://geoquito.quito.gob.ec/server/rest/services/web_reference_dmot/plan_de_uso_y_gestion_del_suelo_2024/MapServer
- **EXT-13 — Registro de la Propiedad del DMQ — certificados más solicitados.** Gravámenes, dominio, antecedentes y ventas: ejemplo de contexto jurídico local indispensable.  
  https://registrodelapropiedad.quito.gob.ec/?p=4155
- **EXT-14 — Registro de la Propiedad del DMQ — inscripción de actos y contratos.** La transferencia y constitución/cancelación de derechos requiere análisis, calificación jurídica y requisitos locales.  
  https://registrodelapropiedad.quito.gob.ec/?page_id=2095
- **EXT-15 — Superintendencia de Bancos del Ecuador — Peritos Valuadores.** La valoración regulada exige peritos calificados y experiencia/requisitos específicos.  
  https://www.superbancos.gob.ec/bancos/calificaciones-sb/
- **EXT-16 — Sequoia Capital — Services: The New Software (5-mar-2026).** Señal estratégica: cuando se vende trabajo/judgment, mejoras del modelo pueden fortalecer el servicio en lugar de sustituirlo.  
  https://sequoiacap.com/article/services-the-new-software

## 24. Límites de evidencia
Las referencias externas demuestran que actores relevantes están construyendo arquitecturas verticales, agentic, de autorización o de contexto; no demuestran que Contexto tenga product-market fit ni que su hipótesis multiindustria sea correcta. Las fuentes locales de Quito demuestran fragmentación, especificidad y vigencia jurisdiccional; no demuestran que Contexto pueda integrarlas económicamente ni sustituir revisión profesional. Las analogías con Stripe y Enter son patrones de diseño/empresa, no claims de equivalencia.