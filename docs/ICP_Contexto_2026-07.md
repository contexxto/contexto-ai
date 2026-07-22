# ICP de Contexto AI — El comprador-habitante de Quito

### Perfil de Cliente Ideal · investigación profunda y definición · arquitectura B2B2C

**Fecha:** 2026-07-21 · **Autor:** Contexto AI (estrategia, asistida) · **Estado:** v1.0 — borrador para red-team del fundador

> Documento de decisión. Fija el **wedge primario** del ICP (comprador-habitante de Quito) y la
> arquitectura de dos lados (usuario que se enamora / pagador que factura). Triangula el canon
> interno de Contexto con evidencia mundial fresca (2026). No es canon hasta que Carlos lo gradúe.

---

## 1. Resumen ejecutivo

La pregunta de origen fue correcta: **casi todo el proptech con IA sirve al lado oferta** (CRMs y calificadores de leads para inmobiliarias, corredores y promotores). El lado comprador —una plataforma B2C real— está vacío. Pero ese vacío **no es un mercado sin descubrir: es un cementerio.** Los intentos de plataforma pro-comprador a escala de capital de riesgo murieron por la economía del lado demanda.

De ahí la corrección de encuadre que gobierna todo este documento: **Contexto no es B2C puro, es B2B2C.** Definir "nuestro ICP" exige dos perfiles que encajan como llave y cerradura:

- **El usuario** (la superficie B2C): la persona a quien enamoramos con la asesora honesta y la verdad verificada del lugar. **Nunca paga suscripción.**
- **El comprador económico** (el negocio B2B): el "tercero que sangra" —desarrollador con inventario parado, corredor, banco— a quien facturamos por el lead calificado y la señal de demanda.

**Decisión fijada (fundador, 2026-07-21):** el **wedge primario** es el **comprador-habitante de clase media de Quito** comprando su primera o segunda vivienda de valor medio. Ancla el pagador (desarrollador MAKLO + corredor) y el énfasis de producto (verdad de habitabilidad + handoff humano). Los demás segmentos (micro-inversionista, extranjero en Mazatlán, diáspora informal) quedan como expansión, no como foco.

---

## 2. Por qué no existe "una plataforma B2C como Contexto" — la restricción

El lado comprador está vacío por una razón estructural, no por falta de intentos. El comprador transacciona ~1 vez por década, así que su costo de adquisición no se amortiza. La lista de cadáveres lo confirma:

- **Divvy** — US$2.300M de valoración a fire-sale, accionistas en cero.
- **EasyKnock** — cerrada entre 24+ demandas.
- **Reali** — US$290M quemados.
- **Flyhomes** — construyó el copiloto del comprador, **no monetizó**, terminó vendido a un brokerage; sobrevivió solo la pieza financiera.
- **Casavo** — €200M, murió con el ciclo de tasas (balance propio).
- **Modern Realty** — pivotó a CRM para agentes (se rindió al lado oferta).

El patrón: **el balance propio muere con las tasas; desafiar al gremio muere por boicot de distribución; la asesoría pura termina absorbida.** Solo sobreviven tres modelos de monetización: **success-fee contingente al cierre**, **"el tercero que sangra" paga**, o **ancla estatal**.

> Fuente: Senales-Brain, tesis "El copiloto fiduciario del comprador informal no existe en LATAM" (estado: emergente, confianza: media). Tratar como dirección estratégica atribuida, no como hecho probado.

**Consecuencia para el ICP:** no se puede definir "el ICP" como si el consumidor fuera el cliente que paga. La monetización obliga a la arquitectura de dos lados de la sección 3. Reglas innegociables que salen de aquí: **jamás balance propio; jamás suscripción al comprador; jamás scoring propio de personas; navegar (no competir con) el ancla estatal.**

---

## 3. La arquitectura de dos lados (llave y cerradura)

| Eje | El USUARIO (lado demanda, superficie B2C) | El COMPRADOR ECONÓMICO (quien paga, B2B) |
|---|---|---|
| Quién es | La persona que busca dónde vivir / rentar / invertir | El "tercero que sangra": desarrollador con inventario parado, corredor / inmobiliaria, banco con meta de colocación |
| Qué le entregamos | Asesora honesta + verdad verificada del lugar + handoff a un humano | Lead calificado en el pico de intención + señal de demanda + la verdad que hace que la IA lo recomiende |
| Qué nos da | La señal de intención (el activo defendible) | El dinero (success fee / suscripción B2B / uso de API) |
| Nunca | Le cobramos suscripción al usuario | — |

**La regla de oro:** el usuario es a quien enamoras; el comprador económico es a quien facturas. El ICP vive en la **intersección**: ganamos cuando la intención del usuario ideal cae sobre el inventario del pagador ideal.

---

## 4. El USUARIO ICP primario — "El comprador-habitante de alto riesgo emocional en mercado de dato pobre"

> **El profesional o familia joven de clase media en Quito (28–45) comprando su primera o segunda vivienda de valor medio, que vive la operación como la decisión financiera más grande de su vida y tiene pánico a equivocarse.**

### 4.1 Dimensiones del perfil

| Dimensión | Definición |
|---|---|
| Demográfica | 28–45 años; pareja o familia joven; ingreso formal o mixto; desde la banda BIESS-elegible (hogar hasta ~USD 1.528/mes para la tasa CrediCasa 2.99%) hasta clase media-alta; ticket ~USD 60k–180k. |
| Geográfica | Quito primero (beachhead del piloto del corredor + obra nueva de MAKLO). Mercado sin MLS y con catastro público pobre: donde el dato verificado es la única fuente de verdad, no un extra. |
| Psicográfica | Aversión a la pérdida aguda; quiere transferir la responsabilidad del error (a su pareja, su familia, a sí mismo). Desconfía del anuncio pero no tiene cómo verificar. Digitalmente cómodo, no necesariamente "AI-native". |
| Conductual | Entra en estado Explorando / Enganchado (compara zonas, pregunta "¿cómo es vivir aquí?"); el valor se dispara en estado Intención (pregunta precio, "¿se puede visitar?", pide ficha técnica). |
| Job-to-be-done | "Ayúdame a no arruinar la decisión más cara de mi vida: dame la verdad del lugar que el anuncio esconde y conéctame con un humano que responda." |
| Disposición a pagar | No paga suscripción. El mercado ya reveló willingness-to-pay por lo que Contexto entrega: 44% de compradores pagaría extra por verificación humana; 66% ya usa al corredor para verificar lo que la IA le dijo. Esa disposición la captura el pagador, no el usuario. |

### 4.2 Por qué este wedge y no el comprador AI-native de mercado maduro

El comprador AI-native de EE.UU./España es el **commodity**: Redfin×Sierra, Zillow-en-ChatGPT y Realtor.com ya lo poseen, y solo emparejan lo que el vendedor escribió o subió. En mercados maduros con MLS limpio, la verdad verificada **agrega** valor. En LATAM sin catastro limpio, la verdad verificada es **toda la partida**. El foso es más profundo justo donde los gigantes no pueden operar desde datos públicos —porque esos datos no existen.

### 4.3 El motor emocional (por qué este usuario se engancha por confianza, no por adicción)

La compra grande activa aversión a la pérdida y sesgo de negatividad: dolemos más por un error que lo que disfrutamos un acierto. La conducta documentada es **delegar la decisión en un experto para transferir la carga del arrepentimiento** —y los asesores humanos se perciben como más responsables que los algorítmicos. Por eso la jugada ganadora de Contexto no es "más datos": es **ficha técnica verificable (seguro psicológico contra el arrepentimiento) + conexión con el corredor humano (a quien sí se le transfiere la responsabilidad).** IA + humano = el combo que la psicología pide.

---

## 5. El COMPRADOR ECONÓMICO ICP — quién sangra y paga

El usuario define al pagador ideal: el que tiene inventario que encaja con esa intención y a quien le duele que esté parado.

| Pagador | Por qué "sangra" | Encaje con el wedge Quito |
|---|---|---|
| Desarrollador de obra nueva (MAKLO) | Inventario terminado o en preventa parado = capital inmovilizado. Paga por demanda calificada, no por otro chat. | Máximo. Pagador más limpio hoy y ya en carril. |
| Corredor / inmobiliaria (InmobIA) | Pierde 8 de cada 10 leads por mal seguimiento. Paga por lead calificado en el pico + panel CRM. | Alto. Es el loop de contribución que alimenta el foso. |
| Banco / ancla estatal (BIESS, Grupo Bolívar) | Meta de colocación de crédito sin ejecutar; subsidio sin navegador. | Estratégico / tardío, vía API (patrón Apaleo). El más grande y el más lento. |

---

## 6. Mapa completo de segmentos de demanda (wedge y expansión)

La disciplina es elegir uno y profundizar (scope mata, profundidad gana), no perseguir los cuatro.

| # | Segmento consumidor | Intención | Pagador que activa | Estado |
|---|---|---|---|---|
| A | Comprador-habitante clase media Quito (sección 4) | Vivir | Desarrollador (MAKLO) + corredor | WEDGE PRIMARIO (fijado) |
| B | Micro-inversionista LATAM (1–3 unidades, yield / renta corta) | Invertir | Desarrollador + corredor | Secundario fuerte: activa la capa de inversión (el vertical nuevo); repite, mejor CAC |
| C | Comprador extranjero en Mazatlán (jubilado / remoto US-Canadá; condo USD 150–200k vs USD 500k en Cabo) | Invertir / vivir | AuraReal / desarrollador (Ricardo) | Secundario activo hoy: ticket alto, disposición a pagar rápida, confianza en mercado ajeno (fideicomiso) |
| D | Comprador de diáspora / informal (ecuatoriano o mexicano en el exterior, ingreso informal, remesas) | Vivir | Estado (Infonavit / BIESS) + banco | Norte estratégico, no wedge: el premio más grande y más difícil (ensambla subsidio + verificación de ingreso informal + due diligence de título) |

**Nota de mercado (evidencia mundial):** el segmento inversor no es teoría —en Mazatlán, Millennials y Gen X apuntan cada vez más a mercados urbanos de alto rendimiento y renta corta, con el centro histórico UNESCO como foco. Y la remesa financia vivienda: Ecuador recibe ~US$1.600M/año (≈8% del PIB), con canales informales que hoy bloquean el acceso a hipoteca —exactamente la fricción que el segmento D convertiría en producto.

---

## 7. El ANTI-ICP (a quién NO servimos)

- El comprador AI-native de mercado maduro (EE.UU./España con MLS limpio): commodity que ya poseen los portales; ahí no tenemos foso.
- El usuario que solo quiere "chatear con las páginas": ya se commoditizó en ambos lados; no es demanda defendible.
- El pagador que quiere que Contexto tome balance propio (comprar/vender el inmueble): es el modelo del cementerio.
- Cualquier caso que exija scoring de personas, mapas de "seguridad" de barrio o AVM de cifra puntual: rojo estructural de compliance (Fair Housing) —se declina por construcción.

---

## 8. Triangulación — foso interno × evidencia mundial (2026)

| Afirmación del ICP | Evidencia interna (canon Contexto) | Evidencia mundial (2026) |
|---|---|---|
| El valor está en transferir la responsabilidad, no en más datos | Investigación de comportamiento (Berridge, Kahneman, delegación de decisión) | 44% paga por verificación humana; 66% usa corredor para verificar la IA; confianza en IA para vivienda cayó de 30% a 16% |
| El foso es la verdad verificada, no el chat | NORTHSTAR + Sistema Vivo (de ranking a recomendación) | Búsqueda conversacional se volvió commodity (Redfin, Zillow, Realtor.com); real estate = industria menos visible en AI Overviews de Google: 0,14% |
| LATAM sin MLS = foso más profundo | Estudio de adopción (informalidad estructural del suelo) | iBuying murió o pivotó en LATAM (La Haus, Loft, Casai); sobrevivientes apalancan al corredor (Habi, QuintoAndar) |
| El comprador joven es digital pero minoritario | — | Gen Z 4% + Millennials 26% de compradores; primerizos en mínimo histórico 21%; los jóvenes recurren a redes sociales + IA + pares |
| El pagador es el que sangra, nunca el consumidor | Tesis del copiloto fiduciario | Flyhomes no monetizó al comprador; Roam prueba que el comprador sí paga success-fee contingente; Esusu (unicornio) = "paga el que sangra" |

---

## 9. Señales de intención mapeadas al ICP (del Motor de Intención)

El ICP no es estático: es un recorrido de estados. Para el wedge Quito, el handoff al corredor (el momento de facturación) se dispara en el pico:

- Estados 0–2 (Anónimo, Identificado, Explorando): la IA califica y nutre; el corredor no entra.
- Estado 3 (Enganchado): profundiza en UN inmueble, pide ficha, "cómo es vivir aquí".
- Estado 4 (Intención): pregunta precio / rentabilidad, "¿se puede visitar?", usa la ficha técnica → SE DISPARA EL HANDOFF.
- Estados 5–7 (Confirmado, Completado, Returning): el corredor cierra; Contexto mide el outcome.

El score de intención es explicable (honestidad como feature): "intención alta porque preguntó precio + pidió ficha + volvió 2 veces a la página". Eso es lo que se entrega al pagador —no un "alguien preguntó".

---

## 10. Cómo validar (próximo paso verificable — no hecho en este documento)

Este documento define el ICP; **no lo valida en campo**. Para cerrar el ciclo con disciplina:

1. **Dimensionar el wedge en dólares:** cuántos compradores-habitante de valor medio compran obra nueva/usado al año en Quito, y cuánto vale un lead calificado para MAKLO y para el corredor.
2. **Prueba de disposición a pagar del pagador:** confirmar con MAKLO y con un corredor real cuánto pagarían por un lead en estado Intención con resumen + verdad verificada.
3. **Instrumentar el estado_intencion** (Fase 0 del Motor de Intención) para medir cuántos usuarios reales del piloto llegan al estado 4 —el ICP se valida cuando el embudo lo confirma, no cuando el documento lo afirma.
4. **Falsadores explícitos:** si el pagador no paga por el lead, o si el usuario del wedge no llega al pico de intención, el wedge se revisa.

---

## 11. Fuentes y nota de calibración

**Nivel de cada dato (disciplina de honestidad, coherente con la marca):**

- **Verificado (fuente sólida):** los datos externos citados abajo y el canon interno de Contexto (NORTHSTAR, Sistema Vivo, Motor de Intención, estudio de adopción con gate de verificación).
- **Atribuido a fuente (no verdad Contexto):** las tesis de Senales-Brain —el copiloto fiduciario (emergente, confianza media) y los huecos de UX LATAM (confianza baja). Dirección, no hecho probado.
- **Hipótesis a validar:** que el wedge A (Quito habitante) supera a C (Mazatlán extranjero) como primario —fijado por decisión del fundador, aún sin validación de campo.
- **Riesgo abierto:** la adopción real de IA por el comprador es minoritaria (~20%). El ICP gana por confianza y verdad, no por novedad.

**Fuentes externas (web, 2026):**

- NAR — Baby Boomers largest share; first-time buyers 21% (record low): nar.realtor/newsroom
- HousingWire — younger buyers turn to social media, AI and each other: housingwire.com
- NextGen Homebuyer Report 2026 (Gen Z / Millennial): nextgenhomebuyer.com/reports/2026
- BIESS CrediCasa 2.99% y banda de ingreso ≤ USD 1.527,94: ecuavisa.com y primicias.ec
- Tasas hipotecarias Ecuador 2026 (8,33% vs 9,1% 2025): primicias.ec
- BID — remesas a LATAM y Ecuador (~US$1.600M, 8% del PIB): iadb.org
- Mazatlán buyer guide 2026 (retiro + remoto; condos USD 150–200k; centro UNESCO): crossinghq.com/mexico y mazatlanmove.com

**Anclas del canon interno:** NORTHSTAR_Contexto_Claude_Inmobiliario.md · VISION_Sistema_Vivo.md · MOTOR_Intencion_Contexto.md · INVESTIGACION_Comportamiento_y_Enganche.md · ESTUDIO_Adopcion_IA_Real_Estate_2026-07.md · Senales-Brain/wiki/tesis/El copiloto fiduciario del comprador informal no existe en LATAM.md
