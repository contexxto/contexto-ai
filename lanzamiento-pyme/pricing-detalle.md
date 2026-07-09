# pricing — detalle de la escalera (0 · tienda → aurareal 360 → inmobiliaria)

> ## ⚡ DECISIÓN DEL FUNDADOR (2026-07-09): **el 360 ES el producto**
> Carlos fijó el centro de gravedad de la monetización en el **SaaS mensual "aurareal 360"**
> (coherente con el canon: "ingreso principal y foso = suscripción"). Consecuencias:
> 1. El fee por lead **deja de ser un tier**: los leads calificados van **incluidos en el 360
>    con cupo mensual**; solo el excedente se cobra por lead (fee fijo, se cierre o no).
> 2. La escalera colapsa a 3: **0 · tienda ($0 piloto) → 1 · aurareal 360 (SaaS) → 2 ·
>    inmobiliaria (plan mayor del mismo SaaS)**.
> 3. Los experimentos del piloto se re-centran: la pregunta #1 es **disposición a pagar y
>    renovar el 360**; la definición auditable de "lead calificado" (§2) sigue viva para el
>    cupo/excedente.
> El detalle de abajo se escribió con la escalera de 4 — sigue siendo válido como insumo
> (función de lead calificado, anclajes, unit economics), leído bajo esta decisión.

> **Contexto AI · 2026-07-08** · Expansión del §5 de `docs/MODELO_Shopify_Inmobiliario_PYME.md` (la escalera de precios).
> **Insumos:** reglas de neutralidad y "pagar por calificar, no por dirigir" de `docs/PRODUCTO_Encaje_Financiero_Neutral.md`; principio auditable "no juzgamos, medimos y citamos" + proveniencia de `docs/COMPLIANCE_FairHousing_AgentSpec_2026-06-23.md`; benchmarks Shopify/GuruHotel del MODELO.
> **Nombre del producto:** `AuraReal` — decision del fundador (2026-07-09), pendiente registro SENADI. Torneo y racional en `naming.md`.

---

## 0. Estado y honestidad de este documento

Este es un **detalle de diseño de pricing**, no un tarifario. Su función es dejar listos para el piloto manual (MODELO §7, fase 1) cuatro entregables:

1. la **escalera de 4 escalones** expandida (qué incluye, qué dispara el cobro, qué regla lo gobierna);
2. la **definición auditable de "lead calificado"** — una función pública de criterios objetivos, **agnóstica a dónde se envía el lead**;
3. las **bandas de precio hipótesis** para la PYME de Quito, con lógica de anclaje contra lo que hoy paga al portal;
4. el **esqueleto de unit economics** (costo de servir por tienda) y los **3 experimentos de pricing** del piloto.

**Regla dura de este doc (hereda las líneas rojas del brief):**

- **Cero cifras presentadas como hechos.** Toda banda de precio va rotulada `HIPÓTESIS A VALIDAR`. Todo dato de mercado externo va rotulado `DIRECCIONAL` con su fuente y su límite (país, moneda, año). El único "$0" no rotulado es una **decisión de diseño** (barrera cero del escalón 0), no una medición de mercado.
- **La verdad del enemigo se investiga, no se inventa.** Hallazgo central del §3: **los portales de Ecuador no publican su pricing** — lo esconden detrás de "solicita tu demo". Así que todo anclaje es triangulado e indirecto, y se rotula como tal.
- **Neutralidad cableada:** el fee **jamás** depende de a qué banco/portal/corredor se envía nada. "Calificado" es una propiedad del lead **en sí**, calculada antes y con independencia de cualquier handoff.
- **Fair Housing duro:** la calificación usa solo ejes económicos/de intención declarada; la señal `perfil` (familia/hijos/etc.) **nunca** cuenta. La exclusividad del pitch es del **inventario verificado**, jamás de personas.

---

## 1. La escalera expandida (los 4 escalones)

> ⚠️ Todas las cifras de la columna "cobro" son **HIPÓTESIS A VALIDAR** en el piloto (bandas en el §4). Aquí importa el **diseño** de cada escalón: qué valor entrega, qué evento dispara el cobro, y qué regla lo protege.

| Escalón | Qué incluye | Qué **dispara** el cobro | Forma de cobro (hipótesis) | Rol estratégico |
|---|---|---|---|---|
| **0 · Tienda** | Storefront línea CRED en su dominio + N publicaciones verificadas + QR de letrero + página `/a/{id}` | Nada (adopción) | **$0** (decisión de diseño) | Barrera cero. El caballo de Troya. Corre a pérdida controlada = CAC |
| **1 · Leads** | Agente IA en SU storefront (entorno verificado) + captura de **leads calificados** | Cada lead que **pasa la función pública** del §2 | Fee **fijo por lead calificado**, idéntico sin importar destino | Cobro por lead capturado (input, **no** venta): escala con el **volumen de leads**, no con las ventas cerradas — gate: costo-por-cierre implícito (§4.3) |
| **2 · Negocio 360** | CRM Vivo + reenganche + pre-calificación neutral *(roadmap)* + **cupo de N leads/mes incluido + excedente por lead** + banner/QR ilimitados + analytics | Suscripción activa (recurrente) + excedente sobre el cupo | **SaaS mensual (incluye cupo de leads) + overage** | El foso: aquí vive la retención / NRR. El per-lead **no muere**: se absorbe como cupo + excedente (§4.1) |
| **3 · Inmobiliaria** | Multi-corredor, equipos, roles, reportes al dueño | Suscripción activa por asientos/equipo | **SaaS mayor** (post-validación) | Expansión de cuenta |

**Lógica de la escalera (por qué este orden y no otro):**

- **El valor sube antes que el precio.** El escalón 0 entrega el activo más caro de producir (el storefront con verdad verificada debajo) **gratis**, para eliminar la fricción de venderle a una PYME (upgrade de GuruHotel: entrada gratis, cobras cuando el cliente gana). El cobro solo empieza cuando la PYME ya recibe algo medible: leads (escalón 1) y luego operación (escalón 2).
- **Dos naturalezas de cobro distintas.** Escalón 1 es **transaccional** (fee por evento discreto y auditable). Escalón 2 es **recurrente** (SaaS, el ingreso que compone). El salto 1→2 es la conversión clave del negocio: de "me cobras por lead" a "no puedo operar sin esto".
- **Cómo conviven el fee-por-lead y el SaaS (definición explícita — antes estaba sin resolver).** El escalón 2 **no reemplaza ni suma a ciegas** el per-lead: lo **absorbe** como un **cupo de N leads/mes incluido en el SaaS + un excedente por lead** calibrado para cubrir el `Variable_por_lead` marginal (§4.1–4.2). Así se evitan las tres patologías del diseño anterior sin definir: (a) que el per-lead **muera** justo cuando el volumen crece (mataría el rol "crece con el volumen" y capa el LTV del tier 1); (b) que un cupo **ilimitado** ponga en margen negativo al usuario pesado (el SaaS solo absorbe Fijo+Soporte, no un Variable sin tope); (c) que se **cobre doble** (SaaS + per-lead completo encima), rompiendo el pitch de "reemplazo/consolidación del gasto de portal" del §3.4. **Gate antes de fijar la escalera:** modelar el punto de cruce de volumen (leads/mes) donde el escalón 2 domina al 1, y verificar que el salto 1→2 sea un **upgrade de valor**, no una fuga para escapar del per-lead.
- **Ningún escalón captura la transacción ni el crédito.** El cobro máximo es un SaaS + un fee por lead calificado; **nunca** un % de la venta inmobiliaria ni del crédito (anti-patrón Habi, línea roja del MODELO §8 y del doc de Encaje Financiero).

---

## 2. Definición auditable de "lead calificado" (la función pública)

> **Por qué existe esta sección.** El MODELO §9 marca el riesgo explícito: *"el fee por lead calificado puede degenerar en presión por volumen → definir 'calificado' con función pública y auditable."* El doc de Encaje Financiero fija la regla gemela: *"se paga por calificar/encajar bien (lead que avanza), no por dirigir a un prestamista."* Esta sección convierte esas dos frases en una **especificación**.

### 2.1 El principio (heredado del guardrail Fair Housing)

El principio rector del agente aplica idéntico al cobro: **separar el DATO OBJETIVO (del lead, verificable, con proveniencia) del JUICIO SUBJETIVO.** El sistema **no juzga** si un lead es "bueno para un grupo"; **mide** si un contacto real declaró intención sobre ejes objetivos y pidió avanzar. La calificación es un **instrumento que mide y registra**, no una opinión.

De ahí las tres propiedades no negociables de la función:

1. **Pública, versionada y con palanca del corredor.** `es_calificado(lead) → {sí | no, razón, versión}` es una función **publicada** (la PYME la conoce antes de firmar), **versionada** (v1, v2… con changelog), y su cambio se anuncia. Como el que cobra por unidad **no puede además fijar la unidad de forma unilateral**, el corredor tiene **palanca real sobre su factura**: (a) el umbral `N` de completitud se **co-fija por contrato** (no lo mueve el proveedor solo), y (b) el corredor elige un **cap mensual de leads facturables**. Cambiar la versión de la función a una que **amplíe lo facturable requiere su aceptación**, no solo un aviso. Es el mismo patrón que el comparador de prestamistas del doc de Encaje —*función pública, versionada y auditable*, nunca caja negra— pero aquí, además, **no la fija una sola parte**.
2. **Agnóstica al destino.** "Calificado" se computa **en el momento de la captura, en el storefront de la PYME**, antes de cualquier handoff. **No depende** de a qué banco/portal/corredor se envía nada, ni del valor del inmueble, ni de la comisión esperada. El fee es **fijo e idéntico** por lead calificado → cero incentivo a inflar hacia inventario caro o hacia un prestamista que pague.
3. **Auditable por ambas partes.** Cada decisión de calificación se **registra** (inputs objetivos → output + versión + timestamp) y es **visible para la PYME en su CRM**: *"ves exactamente por qué te cobramos por este lead."* Hay **ruta de disputa**.

### 2.2 Los criterios objetivos (esqueleto — umbrales = HIPÓTESIS a calibrar)

Un lead cuenta como **calificado** solo si cumple **todos** los ejes objetivos siguientes. Los umbrales exactos (cuántos campos, qué ventana) son **hipótesis a calibrar en el piloto** — lo que **no** es hipótesis es *qué tipo de señal* entra y cuál queda prohibida.

| Eje | Criterio objetivo (verificable) | Proveniencia |
|---|---|---|
| **A. Contacto real y alcanzable** | Un canal de contacto válido y no-bot (email/teléfono que no rebota), producto de una interacción real con el agente — no un form-fill vacío | `[medido]` (evento en el log) |
| **B. Intención declarada sobre ejes NO protegidos** | El lead declaró al menos: zona(s) de interés · rango de presupuesto · tipo de inmueble · (opcional) nº de recámaras · plazo de decisión | `[verificado por interacción]` — son los mismos ejes objetivos que el COMPLIANCE bendice |
| **C. Señal de avance DURA** | El lead **pidió avanzar explícitamente**: solicitó una **visita** o **contacto directo** con el corredor (intención dura, iniciada por el comprador). El mero *consentimiento de reenganche/follow-up* **NO** dispara cobro — queda como lead **no facturable** hasta que haya intención dura | `[medido]` (acción explícita registrada) |
| **D. Completitud mínima** | Un umbral de N de M campos objetivos presentes (N = **hipótesis a calibrar en el piloto y luego co-fijada por contrato** — no la mueve el proveedor unilateralmente; ver §2.1) | `[medido]` |
| **E. No-duplicado / no-fraude** | El mismo contacto no cuenta dos veces dentro de una ventana T; excluye spam, pruebas y bots | `[medido]` (de-dup + reglas anti-fraude) |

### 2.3 Qué NUNCA entra en la función (las prohibiciones cableadas)

- **Ningún atributo protegido ni la señal `perfil`.** Familia, hijos, edad, género, composición del hogar, nacionalidad, barrio de origen o cualquier proxy **jamás** son criterio de calificación. La señal `perfil` se **purga del input** por construcción (deuda ya saldada en el motor del agente, tarea #14). Un lead no vale ni más ni menos por quién es.
- **El destino del lead.** A quién se lo manda la PYME después (banco, BIESS, portal, otro corredor) **no altera** si contó como calificado ni cuánto se cobró. Neutralidad estructural, no cortesía.
- **El valor del inmueble o la comisión.** El fee es **plano por lead**, no un % — para no premiar el empuje a inventario caro (que sería steering financiero encubierto).
- **La subjetividad del corredor sobre "qué tan bueno se ve" el lead.** La función mide señales objetivas; la corazonada del corredor no cobra ni descuenta.

### 2.4 Cómo se audita (el foso de confianza)

- **Log versionado por lead** (inputs objetivos, output, versión de función, timestamp), visible en el CRM de la PYME.
- **Ruta de disputa:** la PYME puede marcar un lead como "no calificado de verdad"; una muestra se revisa en humano; error sistemático → ajuste **versionado** de la función (no un parche silencioso).
- **Clasificador determinista de primera clase** (no prosa en un prompt), como exige el COMPLIANCE — con **evals adversariales** de que la calificación no correlaciona con cohortes protegidas (**test de disparate impact como gate**, igual que el motor de encaje).
- **Métrica de salud del contrato de cobro:** tasa de disputa por PYME, % de leads calificados que la PYME misma hace avanzar (si la función califica bien, la PYME los trabaja; si califica basura, la disputa sube). Esa métrica es a la vez control de calidad **y** protección de la marca contra la "presión por volumen" del MODELO §9.

> **Una línea:** *el lead es calificado por lo que el comprador declaró y pidió — no por quién es, ni por a dónde lo mandes después.*

---

## 3. Anclaje de precio — ¿qué paga hoy una PYME al portal?

> **El enemigo del pitch son los portales** (Plusvalía, Properati…): la PYME paga por leads en un canal que no es suyo. Para fijar precio hay que saber contra qué se ancla. **Todo lo de abajo es `DIRECCIONAL`** y se rotula con su límite.

### 3.1 Hallazgo central: el pricing del portal es opaco (verificado 2026-07-08)

Búsqueda web sobre planes/precios de Plusvalía y Properati/Proppit para corredores en Ecuador: **ninguno de los dos publica tarifas.** Ambos las esconden detrás de *"solicita tu demo"* y "elige el plan que se adapte a tu necesidad". Consecuencia práctica:

- **La opacidad es, en sí, un ángulo de venta.** Frente a un portal que no dice qué cobra, una escalera **pública** y una función de "lead calificado" **auditable** son un diferenciador honesto (misma alma que la joya de marca de los asteriscos).
- **Cualquier número de anclaje es indirecto** — triangulado desde el modelo de cobro declarado del portal + referencias de costo-por-lead de otros mercados. No es un tarifario del competidor.

### 3.2 Lo que sí es citable del modelo del enemigo

- **`DIRECCIONAL` — Properati/Proppit cobra por contacto, no por banner.** Su propia comunicación describe la propuesta como *"entregar contactos de calidad, pagar solo por contacto recibido y no por banners o pop-ups"* (blog Properati Ecuador). **Lectura clave:** el enemigo **ya cobra por lead**. Eso valida de raíz la lógica del escalón 1 (fee por lead) y nos da el ancla natural: *lo que la PYME hoy paga por un contacto del portal es el techo contra el que competimos.*
- **`DIRECCIONAL` — Proppit es multi-portal con una suscripción** (Properati + icasas + Trovit + Mitula + Nuroa vía Lifull Connect). Es decir: hoy la PYME paga por **alcance en canal ajeno**; nosotros vendemos **canal propio** (su dominio, su QR, sus leads).

### 3.3 Referencias de orden de magnitud (todas rotuladas, ninguna es Ecuador-corredor)

| Referencia | Cifra | Límite (por qué es solo direccional) | Fuente |
|---|---|---|---|
| Costo-por-contacto vía portal | **~€6 / contacto** (€8–9 el contacto único) | **España, EUR, cartera 40–200 props.** No es Ecuador; solo da el **orden de magnitud** del canal "portal" | inmoblog.com |
| Costo-por-contacto otros canales | Google Ads ~€5 · Facebook ~€3 · display ~€25 | Misma fuente/límite; útil para saber **contra qué CPL** juega el lead | inmoblog.com |
| Portal EC gratuito, publicación anual | promo **~$100 / año** | Es publicación (visibilidad), **no** compra de leads; ancla el **piso** de "estar visible" | ecuador.buscocasita.com |
| SaaS productizado, entrada | Shopify **desde ~$24 / mes** | Otro rubro (e-commerce), pero es el **benchmark del modelo**: entrada SaaS de un dígito-dos dígitos bajos | descripción pública de Shopify (MODELO §3) |
| Pricing invertido LATAM | GuruHotel: **$0 upfront, $0/mes, 5% por reserva** | Hotelería = alta frecuencia/ticket bajo; **no** aplica el % a inmobiliaria (baja frecuencia/ticket alto) — por eso nuestro análogo es **fee por lead**, no % | prensa/vendor (MODELO §4) |

### 3.4 Bandas de precio hipótesis para la PYME de Quito

> **`HIPÓTESIS A VALIDAR` — ninguna de estas bandas es un precio fijado.** Lo que se entrega aquí es el **método de anclaje** y una banda de arranque para testear en el piloto (§5). El número final sale de la disposición a pagar medida, no de este doc.

- **Escalón 0 · Tienda — $0.** No es hipótesis: es **decisión de diseño** (barrera cero). Lo que sí es hipótesis es su **costo de servir** (§4).
- **Escalón 1 · fee por lead calificado.**
  - *Ancla (con advertencia):* el costo-por-contacto que la PYME **ya paga al portal hoy** — pero §3.1 admite que **ese precio es desconocido** (los portales no lo publican). **No se ancla a un número que se admite desconocido:** el ancla real se **mide en el piloto** (costo-por-lead efectivo de cada PYME), no se supone desde referencias de España.
  - *Lógica de la hipótesis:* nuestro lead es mejor en tres ejes (es **suyo/directo**, no alquilado; **calificado por función pública auditable**; llega con **contexto de entorno verificado**) — pero **el diferencial NO puede ser el precio.** Un entrante con capital (Pulppo/LIDZ son VC-backed) también pone el lead a $0 o negativo y **aguanta más tiempo el subsidio** (§4 escalón 0 = margen negativo controlado). Competir en "más barato que el portal" es una guerra que **gana el bolsillo más profundo**. El descuento vs el portal es **un** argumento, no **el** argumento.
  - *Cómo se fija el número (no aquí):* medir en el piloto el costo-por-lead real que cada PYME paga hoy, y **el costo-por-CIERRE implícito** (leads→cierre, §4.3), para verificar que nunca supere lo que hoy paga por el mismo resultado. Banda de arranque a testear: **un dígito bajo de USD por lead calificado** como hipótesis inicial, a mover con la evidencia. `HIPÓTESIS`.
- **Escalón 2 · SaaS mensual.**
  - *Ancla:* (a) lo que la PYME hoy gasta al mes en el/los portal(es) por alcance; (b) el benchmark de entrada SaaS (~$24/mes de Shopify como orden de magnitud, MODELO §3).
  - *Lógica:* el SaaS debe leerse como **reemplazo/consolidación** del gasto de portal + herramientas sueltas (CRM, analytics), no como un costo nuevo encima. Banda de arranque: **decenas de USD/mes**, a calibrar por disposición a pagar y por el valor demostrado del CRM Vivo. `HIPÓTESIS`.
- **Escalón 3 · SaaS mayor (multi-corredor).**
  - *Ancla:* el escalón 2 **por asiento/equipo** + reportes al dueño.
  - *Lógica:* expansión de cuenta post-validación; se fija recién cuando el escalón 2 demostró retención. `HIPÓTESIS — no calibrar aún.`

### 3.5 El competidor real y el lado de la demanda (advertencias que el pricing debe respetar)

> Corrección de encuadre competitivo: el enemigo del *mensaje* es el portal, pero el rival que **te quita el deal** no es Wix ni el portal.

- **El rival que entra a Ecuador NO es Wix ni el portal — es un CRM proptech de corredor** (Pulppo, LIDZ, VC-backed). Ese rival **ya entrega por defecto** dominio propio, marca, microsite y propiedad del lead — o sea, *"tus leads son tuyos"* es **higiene de categoría, no foso**. Y encima **integra con los portales** para traer tráfico. El precio no diferencia contra él (tiene más capital para subsidiar). El único diferencial que puede sobrevivir es el **entorno verificado propietario + agente con proveniencia**; si el piloto no demuestra que eso mueve leads que el CRM pelado no mueve, no hay wedge.
- **El foso del portal es la AGREGACIÓN DE COMPRADORES, no el canal.** La gente va a Plusvalía a *buscar*. El paquete vende herramienta de **oferta** (storefront en dominio propio) y hoy no resuelve de dónde sale el tráfico: el único influjo cierto es el **QR del letrero** (embudo diminuto de quien ya está parado frente al cartel). **Antes de basar el pitch en "reemplaza al portal"** hay que instrumentar en el piloto los **leads orgánicos NO-QR** (§5-Exp3). Sin fuente de demanda propia demostrada, el storefront es un folleto sin visitas y el wedge honesto es *"captura y verifica mejor los leads que ya tienes"*.
- **Consecuencia de pricing:** ni el fee-por-lead ni el SaaS pueden sostenerse sobre "somos más baratos". Se sostienen sobre la **verdad verificada del lugar + el agente** (valor no replicable en un trimestre) o no se sostienen. El precio se **mide**, no se ancla a un competidor opaco (§3.1) ni a una guerra de subsidio que pierde el bolsillo más chico.

---

## 4. Unit economics — esqueleto del costo de servir por tienda

> **`HIPÓTESIS A VALIDAR`.** Aquí no hay cifras en dólares inventadas: hay la **estructura** del costo (qué es fijo, qué es marginal, qué se puede medir con precisión) y **qué mide el piloto** para poblarla. La regla del brief manda: el costo se **mide en el piloto**, no se afirma.

### 4.1 La fórmula (el esqueleto)

```
Costo_de_servir(tienda, mes) =
      Fijo_por_tienda              (hosting + dominio/SSL + onboarding amortizado)
    + Variable_por_lead × N_leads  (inferencia del agente IA + verificación)
    + Soporte(nivel)               (humano; función del escalón y de si la PYME es técnica)
```

Y la lógica de margen por escalón:

```
Escalón 0:  Margen negativo controlado  → es CAC (adquisición). Se ACOTA con un disparador de conversión
            (gratis por N meses o hasta el lead #K, luego escalón 1 obligatorio) — no se deja correr infinito.
            El costo aquí NO es marginal ~0 (lleva verificación en terreno + montaje manual humano).
Escalón 1:  Fee_por_lead  debe cubrir  Variable_por_lead + margen.   (gate mínimo del cobro transaccional)
Escalón 2:  SaaS_mensual  = margen real + NRR.  Absorbe Fijo + Soporte, y el Variable_por_lead se cubre con
            un CUPO de N leads/mes incluido + EXCEDENTE por lead (NO leads ilimitados: el usuario pesado no
            puede caer en margen negativo). El per-lead no muere: se transforma en cupo + overage.
```

### 4.2 Los componentes (naturaleza + cómo se mide)

| Componente | Naturaleza | Cómo se conoce el número (piloto) | Nota |
|---|---|---|---|
| **Hosting / infra** (compute, DB, storage, bandwidth) | Fijo bajo + marginal muy bajo por tienda | Medible directo (factura cloud / tienda) | Barato; el storefront es plantilla parametrizada, no build a medida |
| **Dominio + SSL** | Fijo por tienda/año | Precio de registrador, conocido | — |
| **Agente IA (inferencia LLM)** | **Marginal, escala con nº de conversaciones/leads** | **Medible con precisión** — es una API medida por tokens; el piloto la lee exacta por conversación | Es **el** costo que el fee del escalón 1 debe cubrir. Conócelo antes de fijar el fee |
| **Verificación / hidratación de inventario** | Parte one-time por listing, parte recurrente | Medir horas/tooling por ficha verificada | Es el foso (el dato verificado); su costo es real y hay que amortizarlo |
| **Soporte + onboarding** (escalón 0 gratis) | Humano; **el costo oculto del tier gratis** (verificación en terreno + montaje manual — NO marginal ~0 como un tier gratis digital/self-serve) | Medir horas de soporte por PYME no técnica; **acotar con disparador de conversión** (N meses o lead #K) y usar los "cupos" como control de **costo real**, no como marketing de escasez | El MODELO §9 lo marca como riesgo abierto: *"costo real del escalón 0 gratis (medir)"*. Sin disparador, se subsidia para siempre a quien nunca convierte |
| **CRM / reenganche / cron** | Fijo bajo por tienda activa | Medible directo | Ya construido en gran parte (tareas #29–#33) |

### 4.3 Preguntas que el esqueleto obliga a responder en el piloto

- ¿Cuánto es **Variable_por_lead** (sobre todo inferencia)? → fija el **piso** del fee del escalón 1.
- ¿Cuál es la tasa **lead→cierre** por corredor, y por tanto el **costo-por-CIERRE implícito** del fee-por-lead? → verifica que "pagas por lead, cierre o no" no le salga al corredor **más caro por cierre** que lo que hoy paga al portal. Sin este número, "pagas cuando ganas" sería publicidad engañosa (por eso ese lenguaje se quitó del pitch/guion).
- ¿Cuánto **soporte humano** consume una PYME no técnica en el escalón 0, y **cuál es el disparador de conversión** (N meses / lead #K) que evita subsidiar para siempre a quien nunca convierte? → dice si la barrera cero es sostenible o si necesita self-serve antes de escalar (gate del MODELO §7).
- ¿Cuál es el **punto de cruce de volumen (leads/mes)** en el que el escalón 2 (SaaS + cupo) domina al escalón 1 (per-lead) y absorbe Fijo + Soporte + Variable con margen? → define a qué escalón llevar a la PYME para que la unidad sea sana, y asegura que 1→2 sea upgrade de valor, no fuga del per-lead.

---

## 5. Los 3 experimentos de pricing del piloto manual

> El MODELO §7 fase 1 fija la **pregunta que valida todo**: *"¿pagan y renuevan por la TECNOLOGÍA debajo — no por la web?"* Estos tres experimentos, uno por escalón monetizable, la responden. Cada uno: **hipótesis · qué se hace · qué se MIDE · gate de validación · señal de falla.**

### Experimento 1 — Adopción del escalón 0 (¿el caballo de Troya entra?)

- **Hipótesis:** con barrera cero, la PYME **adopta y USA** el storefront (no solo lo acepta gratis y lo abandona).
- **Qué se hace:** montar a mano el storefront para 1–3 inmobiliarias del piloto; entregar dominio + QR de letrero + `/a/{id}`.
- **Qué se mide:** % del piloto que **hidrata ≥ N publicaciones verificadas** y **activa el QR**; **tiempo a tienda viva**; horas de soporte consumidas (alimenta §4).
- **Gate de validación:** la tienda queda **viva y usada** (inventario cargado + QR en la calle), no dormida.
- **Señal de falla:** aceptan el regalo pero no cargan inventario → el valor no se percibe, o el onboarding es demasiado pesado. Sin uso real, no hay sobre qué cobrar arriba.

### Experimento 2 — Disposición a pagar por lead calificado (escalón 1)

- **Hipótesis:** una vez que los leads fluyen por **SU** storefront (agente + entorno verificado), la PYME paga un **fee fijo por lead calificado**, porque es más barato y mejor que el contacto del portal.
- **Qué se hace:** activar el agente + la captura; aplicar la **función pública del §2**; mostrar el fee **por debajo** del costo-por-contacto que hoy paga al portal (ancla del §3).
- **Qué se mide:** aceptación del fee; **tasa de disputa** de la función "calificado" (valida la definición del §2); **costo-por-lead-calificado aquí vs su costo-por-contacto en el portal**; **tasa lead→cierre y costo-por-CIERRE implícito** (el número que dice si "pagas por lead, cierre o no" es sano para el corredor); **razón declarada** del pago (¿por la tech/los leads propios, o por la web?).
- **Gate de validación:** pagan el fee por **≥ 2 ciclos** sin churn; la disputa se mantiene baja (la función califica bien); y el **costo-por-cierre implícito ≤ lo que hoy paga al portal** por el mismo resultado.
- **Señal de falla:** disputan mucho ("esto no es un lead de verdad") → recalibrar §2; o no aceptan el fee ni por debajo del portal → el lead propio no se percibe como superior al alquilado.

### Experimento 3 — Retención / NRR del SaaS (escalón 2, el foso)

- **Hipótesis:** la PYME **renueva** el SaaS mensual (CRM Vivo + reenganche + pre-calificación neutral + analytics) al mes 2–3, y lo hace **por la tecnología debajo**, no por la web.
- **Qué se hace:** activar el escalón 2 para quien pasó el experimento 2; medir renovación en los meses 2 y 3.
- **Qué se mide:** **tasa de renovación** y **NRR**; la **razón declarada de pago** (la pregunta north-star del MODELO: tech vs web); **% de inventario verificado por tienda**; **leads capturados en canal propio vs portal** (señal anti-multi-homing — la mayor amenaza al foso); y **leads orgánicos NO-QR** (los que llegan al storefront sin venir del letrero físico) — la señal de si el storefront tiene **demanda propia** o es un folleto sin visitas. Si el único influjo es el QR, el producto **no compite** con un agregador de compradores (portal), y el wedge honesto es "captura/verifica mejor lo que ya tienes", no "reemplaza al portal".
- **Gate de validación:** renuevan al mes 2–3 **citando la tecnología** (CRM/leads propios/verdad verificada), y el ratio de leads en canal propio sube.
- **Señal de falla:** renuevan "por la web bonita" o no renuevan → el foso no es la web (era el supuesto); o siguen volcando todo al portal → el candado real (entorno + CRM + agente) aún no engancha. Sin este gate verde, **no** se construye el generador self-serve (gate duro del MODELO §7).

---

## 6. Líneas rojas del pricing (innegociables)

- El fee **jamás** depende de a qué banco/portal/proveedor se envía nada. El success-fee es por **calificar**, agnóstico al destino (MODELO §5, Encaje Financiero regla 7).
- **Nunca** procesar/capturar la transacción inmobiliaria ni el crédito; **nunca** cobrar un % de la venta (anti-patrón Habi).
- **El cliente y el dato son de la inmobiliaria** (su dominio, su marca, sus leads). Si un día se va, se va **con sus leads**. La retención se gana por valor, no por secuestro.
- **Fair Housing:** la exclusividad del marketing es del **inventario verificado**, jamás de personas. La función de "lead calificado" es ciega a atributos protegidos y a la señal `perfil`; sin test de disparate impact verde, no hay cobro por lead.
- **Honestidad de precio:** la escalera es **pública** y la función de calificación es **auditable y versionada** — mostrar eso es el diferenciador frente al pricing opaco del portal, no un costo.
- **No "pagas cuando ganas" para un fee-por-lead.** El cobro es por **lead calificado capturado, cierre o no** — equiparar lead con venta es engañoso y el propio corredor lo desmiente al segundo mes. El gate es el **costo-por-cierre implícito** (§4.3, §5-Exp2).
- **No competir en precio contra capital.** El diferencial es la **verdad verificada del lugar + el agente con proveniencia**, no "más barato que el portal". *"Tus leads son tuyos"* es **higiene de categoría** (todo CRM proptech lo da), no el foso (§3.5).
- **El corredor tiene palanca sobre su factura.** El umbral `N` de "calificado" se **co-fija por contrato** y el corredor elige un **cap de leads facturables** — el que cobra por unidad no fija la unidad solo (§2.1).
- **No cifra inventada:** cualquier número que salga a UI (landing, propuesta) va rotulado `hipótesis` hasta que el piloto lo mida. Nunca una banda de este doc presentada como tarifa real.

---

## Fuentes

- **Escalera, benchmarks y reglas:** `docs/MODELO_Shopify_Inmobiliario_PYME.md` (§3 Shopify, §4 GuruHotel, §5 escalera, §7 secuencia, §8–9 líneas rojas/riesgos).
- **Neutralidad + "pagar por calificar, no por dirigir" + función pública/versionada:** `docs/PRODUCTO_Encaje_Financiero_Neutral.md` (§5 reglas Fair Housing, §7 estructura de negocio, regla 7).
- **Principio auditable "no juzgamos, medimos y citamos" + proveniencia `[medido]/[estimación]/[verificado]` + clasificador determinista + disparate impact:** `docs/COMPLIANCE_FairHousing_AgentSpec_2026-06-23.md`.
- **Nombre provisional:** `naming.md` (torneo — decision final: `AuraReal`).
- **Anclaje de mercado (todo `DIRECCIONAL`, 2026-07-08):**
  - Modelo pago-por-contacto y multi-portal, pricing gated a demo: [blog.properati.com.ec](https://blog.properati.com.ec/quieres-publicar-en-properati/) · [proppit.com (EC)](https://proppit.com/?country=ec) · [plusvalia.com](https://www.plusvalia.com/) — *ninguno publica tarifa; se rotula opaco.*
  - Costo-por-contacto direccional (España, EUR, cartera 40–200 props): [inmoblog.com](https://www.inmoblog.com/cuanto-cuesta-un-contacto-comprador-de-vivienda/).
  - Piso de "estar visible", portal EC gratuito (~$100/año promo): [ecuador.buscocasita.com](https://ecuador.buscocasita.com/).

> **Cierre:** *el portal esconde lo que cobra y te alquila un canal ajeno. Nosotros publicamos la escalera, cobramos por un lead que definimos con una función que puedes auditar — y el lead es tuyo. Todas las cifras de aquí son hipótesis hasta que el piloto las mida.*
