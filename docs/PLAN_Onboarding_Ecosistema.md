# Plan — Onboarding del ecosistema (una sola puerta, y la abre el motor)

### Documento ancla · se itera EN ESTE MISMO doc con cada aprendizaje

**Creado:** 2026-08-06 · **Estado:** F0 construida · F1-F5 sin construir · **Dueño:** Carlos + Contexto

<!-- estado-verificable
codigo:
  existe: app/encaje.py::calcular_encaje
  existe: app/routers/assets.py::_leads_del_corredor
  existe: app/reenganche.py::clasificar_frescura
  existe: app/routers/chat.py::_map_seed_from_cards
  existe: app/routers/chat.py::share_session
  existe: frontend/src/ShareConversation.jsx
  existe: migrations/024_visita.sql
  existe: app/llegada.py::clasificar_canal
  existe: app/routers/visitas.py::registrar_visita
  existe: frontend/src/App.jsx::registrarLlegada
  no-existe: app/agent/crm_guardrails.py::detectar_solicitud_contacto
datos:
  2026-08-06: el correo de un interesado existe SOLO en handoff_sesion.lead_email — no hay otra puerta de identidad en todo el sistema
  2026-08-06: el chat del comprador usa get_optional_user — anónimo funciona; la unidad del lead es localStorage['contexto_ai_device_id']
-->

> **Idea en una línea.** No hay onboarding en la puerta: la puerta es la conversación. El rol
> se infiere, nunca se pregunta. Hay **una sola** puerta suave de identidad, y **la abre el
> motor, no el modelo** — solo en el callejón honesto, una vez, sin insistir.

---

## 0. Nota de honestidad — qué está verificado y qué no (léelo primero)

Todo lo marcado ✅/❌ en §3 se verificó contra el código el 2026-08-06. Lo que **no** se
verificó: el comportamiento real de la PWA instalada como canal de retorno.

**Nada de este plan está construido.** Es una decisión y un orden, no un reporte de avance.

Y el marco que ordena la prioridad: el cuello de botella declarado de Contexto es **adopción
y conversión, no funcionalidades**. Este plan no genera tráfico — hace que el tráfico que
llegue se pueda **ver** y **retener**. El crecimiento sigue viniendo de MAKLO, del canal y de
las campañas.

---

## 1. La decisión dura

El impulso natural de "un onboarding que acoja a todos" es una pantalla que pregunta
*"¿eres comprador, corredor, propietario o arrendatario?"*. **Se rechaza.**

Un selector de rol es lo contrario de la evidencia, lo contrario de la referencia que el
propio producto sigue (se entra y se escribe), y mataría el mejor activo que hay: que la
persona **empieza a hablar** y el motor deduce lo demás.

**La decisión:** no hay onboarding en la puerta. El onboarding ocurre después, es distinto
por rol, y lo dispara *lo que la persona hizo*, no lo que declaró.

**Y su consecuencia, que se acepta explícitamente:** la mayoría nunca se va a identificar.
La disciplina no es convertirlos a todos — es **medirlos a todos** y abrir **una** puerta bien
hecha en vez de siete a medias.

### La evidencia detrás

- **Duolingo** — mover el registro *detrás del primer momento de valor* fue su mayor lift
  medido (**+20% de DAU**). El registro diferido sube activación entre 10 y 30%. Preguntan
  mucho **antes** de pedir cuenta: las preguntas son la inversión, la cuenta llega en su pico.
- **Progressive profiling** — la práctica establecida es no preguntar el rol al entrar: el
  dato de registro es ruidoso e incompleto; se dispara la pregunta desde el comportamiento.
- **Portales inmobiliarios** — el prompt que mejor convierte es **la alerta**. Y su regla
  dura: *nunca cobres peaje por algo que se consigue gratis en otro lado*.

*Cite-don't-assert: son fuentes externas con cifras autorreportadas; sirven como dirección,
no como constantes.*

---

## 2. Los cinco principios

1. **La puerta es la conversación.** Cero fricción, cero preguntas, cero registro para entrar.
2. **El rol se infiere, no se pregunta.** Y el rol inferido es *contexto de conversación*:
   **jamás** entra al scoring del encaje (ver §6, línea roja).
3. **Una sola puerta suave**, en el callejón honesto.
4. **La puerta la abre el motor, no el modelo.** Una regla de conducta en un prompt no es un
   control.
5. **El core es el comprador, y no se nombra.** El sistema **ya es** el copiloto sin
   nombrarlo. Ponerle nombre crearía una mascota entre la persona y el producto.

### Convención de nombres (deuda que este doc cierra)

`Copiloto` está tomado por el agente táctico del corredor (`modo='copiloto'`). En docs y
prompts se escribe **siempre "el Copiloto del corredor"**, nunca "el Copiloto" a secas. El
agente del comprador **no tiene nombre**: se llama Contexto. Lo que sí lleva nombre es la
sección de entrada: **"Antes de decidir"** — universal, nombra el momento que Contexto posee,
y es una postura (*no decidimos por ti, te damos con qué decidir*).

---

## 3. El mapa de llegadas — auditoría 2026-08-06

✅ verificado en código · ⚠️ existe pero roto o a medias · ❌ no existe · **?** no verificado

### A. Demanda

| Entrada | Ancla | Estado | Qué se pierde |
|---|---|---|---|
| QR del letrero, **y escribe** | Inmueble | ✅ carril completo | — |
| QR del letrero, **no escribe** | Inmueble | ❌ se descarta, sin contador | La señal física más fuerte del sistema |
| Marca el teléfono del letrero | Inmueble | ❌ sale del sistema | La llamada va al corredor; Contexto no se entera |
| Home de contexto.ai | Ninguna | ⚠️ camino mayoritario, sin anclar | Etiquetado "QR", sin actividad, sin reenganche |
| Ficha pública `/a/{id}` por link | Inmueble | ✅ | El canal (se etiqueta "QR") |
| Meta → inmueble específico | Inmueble | ❌ no construido | La landing no ancla el activo |
| Meta → zona o criterio | Ninguna | ❌ ni contemplado | — |
| Motor de respuesta que te cita | Cualquiera | ❌ sin detección de referral | La tesis AEO no tiene medición |
| YouTube (canal de aura) | Ninguna | ❌ sin instrumentar | El motor de adquisición declarado |
| Reenvío por WhatsApp | Variable | ❌ sin UTM | El share más común en LATAM |
| Conversación compartida `/s/{token}` | Hereda | ⚠️ el share existe; el receptor no se cuenta | Un canal entero |
| Vuelta desde un reenganche | Inmueble | ⚠️ | Sin el link, es un lead nuevo |
| PWA instalada | — | **?** | La continuidad entre visitas |

**Hallazgo lateral:** la primitiva de retorno **ya existe** (`/?s={session_id}`) y hoy solo la
usa el aviso de respuesta del corredor. Está construida y sin explotar.

### B. Oferta

| Entrada | Estado | Qué se pierde |
|---|---|---|
| Corredor que se registra | ✅ | — |
| Inmobiliaria / agencia | ✅ `agency_id` | — |
| Constructor / promotor | ⚠️ carril MAKLO, sin producto | — |
| **Propietario particular sin corredor** | ❌ no hay puerta | Inventario que ningún corredor traerá |
| Corredor invitado por otro corredor | ❌ sin referral | El canal más barato para hidratar |
| Corredor entrando **como comprador** | ❌ indistinguible | Contamina las métricas de demanda |

### C. Terceros — el ecosistema que se quiere absorber

| Entrada | Estado | Qué aporta que nadie más tiene |
|---|---|---|
| **El arrendatario actual** | ❌ | El conocimiento tácito: ruido, agua, vecinos, sol |
| El vecino de la cuadra | ❌ | El barrio medido desde adentro |
| Comercio local / POI | ❌ `entorno_curacion` es solo de corredores | Verificación de terreno continua |
| Crawler de un motor de respuesta | ❌ sin tratamiento | Es *el* visitante de la estrategia AEO |

### Las combinaciones que rompen el modelo

- Escanea el QR en la calle (teléfono) → sigue en casa (portátil) = **2 interesados sin relación**.
- Entra anónimo → pide corredor → vuelve en tres meses = **lead nuevo**, historial perdido.
- Arrienda un año → luego quiere comprar. Mismo humano, cero continuidad.
- Un corredor busca para su cliente: llega como demanda, es oferta.
- Alguien busca algo **que no existe en el inventario** → no queda registro. Es la señal de
  producto más valiosa que hay.

---

## 4. El autoanálisis: los tres desajustes

**1. Una sola puerta de identidad, y es la más cara del embudo.** El correo existe únicamente
en `handoff_sesion.lead_email`: la única forma de dejar de ser anónimo es **pedir un
corredor**, el acto de mayor compromiso del recorrido. Todo lo anterior es anónimo, todo lo
posterior es del corredor. Puertas suaves: cero.

**2. Entradas para dos roles, ambición de siete.** Todas las superficies sirven a comprador y
corredor. Pero el foso es el Place Graph, y lo que más lo densifica viene de quien no tiene
puerta: el arrendatario que vivió ahí dos años sabe si el agua falla los martes, y **ningún
corredor lo va a decir** — tiene incentivo contrario.

**3. Los dos motores de adquisición declarados no tienen instrumentación.** Ni referrer, ni
UTM, ni forma de saber si alguien llegó porque un motor de respuesta citó a Contexto.

**Y un cuarto, que apareció al fijar que el core es el comprador:** existe un `Corredor-Brain`
(4 moguls destilados, clasificados por foso, servidos vía `tool_playbook_venta`) y **no existe
ningún corpus del lado del comprador**. El corredor tiene a Serhant, Keller y Corcoran; el
comprador no tiene a nadie. La inversión de conocimiento está al revés respecto de la
estrategia.

---

## 5. Las fases, con sus compuertas

El arco: **ver → retener → dejar de mentir → atraer → cerrar fugas → expandir.**
Si una compuerta no se cumple, no se pasa a la siguiente.

### F0 · Ver — instrumentar la llegada ✅ CONSTRUIDA (2026-08-06)

Puramente aditiva: no refactorizó nada.

- ✅ Tabla `visita` (`migrations/024_visita.sql`) — log **append-only**, una fila por
  llegada. La deduplicación se hace al consultar, no al escribir: dos escaneos del mismo
  letrero en un día **son** dos escaneos.
- ✅ `app/llegada.py` — módulo puro que clasifica el canal desde (superficie, utm,
  referrer), con lista **cerrada** de canales y superficies, igual que `DIMENSIONES`.
- ✅ `POST /api/v1/visitas` (`app/routers/visitas.py`) — best-effort: registrar una visita
  nunca puede romper la página que la persona vino a ver.
- ✅ **Registro del escaneo**: `registrarLlegada` se dispara en el MONTAJE, antes de que
  nadie escriba. Una vez por (sesión × superficie × inmueble), marcado en `sessionStorage`
  para que un re-render o el doble montaje de StrictMode no infle el conteo.
- ✅ `fuente` deja de ser `"QR"` hardcodeado: sale del canal de la **primera** llegada de
  la sesión. Sin registro previo → `"desconocido"`, que es la verdad.

**Lo que la clasificación asume, y hay que saberlo al leer el reporte:**
- `directo` significa **"no sabemos"**, no "vino solo". Es el cajón de lo no medido, y ahí
  cae el escaneo de un QR (llega sin referrer y sin utm).
- `mensajeria` va a **subestimar siempre**: una app que abre el navegador normalmente no
  manda referrer. El reenvío por WhatsApp se verá como `directo`.
- `motor_respuesta` va **antes** que `buscador` a propósito: `gemini.google.com` contiene
  `google.`, y confundirlos borraría justo la señal que se quiere medir.

**Compuerta (pendiente, necesita tráfico):** responder por semana y por canal — *¿cuántos
escaneos? ¿cuántos conversaron? ¿cuántos anclaron? ¿cuántos pidieron corredor?*

**Deuda declarada:** el QR impreso no lleva marca de canal, así que un escaneo es
indistinguible de alguien que teclea la URL. Se cierra añadiendo un parámetro al enlace que
genera `_generar_letrero_png` — los letreros ya impresos seguirán cayendo en `directo`.

**Efecto lateral que vale el doble:** las tres asimetrías del QR (dedup, actividad, `fuente`)
existen porque el canal vive en el prefijo de un string. Con `visita` pasa a ser una columna y
las tres se disuelven.

### F1 · Retener — la identidad y la primera puerta suave

La alerta necesita dónde guardar un correo, y hoy el único sitio es una tabla de handoff. Eso
fuerza la tabla `lead` — mejor que nazca motivada por una funcionalidad que por una abstracción.

- Tabla `lead`: la identidad, venga de la alerta o del handoff. Con canal, campaña,
  `activo_id` nullable.
- Tabla `demanda`: el criterio declarado + si hubo match. **Este es el activo.**
- **La alerta** (§6).
- Continuidad: el correo lleva el `?s={session_id}` **que ya existe**.

**Por qué la alerta y no otra puerta:** es el prompt de mayor conversión del sector, no toca el
consentimiento del handoff, y —lo decisivo— **funciona mejor cuanto menos inventario hay**.
Convierte *"no tengo nada que te calce"* de callejón sin salida en captura honesta.

**Compuerta:** N alertas creadas con inventario real, y el reporte de demanda no cubierta con
contenido enseñable a un promotor.

### F2 · Dejar de mentir — el CRM cuenta el universo completo

- Tabla `asignacion`: lead↔activo↔dueño, con **dueño congelado** al handoff (snapshot, no
  puntero).
- **El reparto** en `tool_stats_embudo`: atribuidos + sin anclar + qué se hizo. Como guardrail,
  no como intención.
- Proveniencia del conteo: **"dispositivos que conversaron"**, no "interesados" — son aparatos,
  no personas.
- Vista agregada para el corredor: *"3 dispositivos preguntaron por tu departamento, ninguno
  pidió corredor"*.

Esa última cierra la frontera: **agregado siempre, individuo solo cuando el individuo lo pide.**

**Compuerta:** el Estratega no puede cerrar una jugada de la semana sin nombrar el segundo
número.

### F3 · Atraer — "Antes de decidir"

Cuatro a seis entradas en la home, **procedimentales, nunca evaluativas**:

- ✅ *"¿Qué pasos tiene comprar en Quito y en qué orden?"*
- ✅ *"Es mi primer arriendo — ¿qué reviso antes de firmar?"*
- ✅ *"¿Qué gastos hay además del canon?"*
- ✅ *"¿Podrías vivir aquí un año?"* ← este no es un tip: es el producto
- ❌ *"¿Qué barrio te conviene para empezar?"* — juicio sobre la persona, y es donde vive el
  steering

**La regla que desactiva las tres minas** (consejo financiero, Fair Housing, legal): *no
aconsejamos — explicamos el procedimiento y citamos la fuente.* Es la hermana de "no juzgamos,
medimos y citamos".

**No es un agente nuevo:** es el mismo agente del comprador con intenciones de entrada. Un
segundo agente duplicaría toda la superficie de guardrails por cero beneficio.

Cada chip rinde cuatro veces: entrada, página indexable (AEO), guion del canal, y el momento de
inversión donde cae la alerta.

**Compuerta:** tasa de clic por chip. Si nadie los toca, no se escriben los otros.

### F4 · Cerrar fugas

- El teléfono del letrero → enlace de WhatsApp que abre la sesión **ya anclada**.
- El receptor de `/s/{token}` se cuenta como llegada, con su canal.
- Meta → la landing ancla el `activo_id`, como el QR.

### F5 · Expandir — una sola puerta del ecosistema

**El arrendatario actual.** Una pregunta: *"¿qué te habría gustado saber antes de mudarte
aquí?"*

Rinde doble: es materia prima del Place Graph **y es el corpus del comprador** que hoy no
existe — produce literalmente las preguntas que un primerizo no sabe hacer. El Comprador-Brain
sale de la gente, no de un gurú.

**Una, no tres.** El vecino, el comercio local y la institución esperan.

---

## 6. La puerta suave: cómo se abre y cómo NO

### El momento: el callejón honesto

La tentación es un umbral (*"a los 3 turnos, pide el correo"*). Eso es acoso con reloj. El
único momento en que pedir el dato es un **servicio y no un peaje**:

> **Criterio declarado + nada que encaje.**

Computable con lo que existe: `preferencias` no vacías + panel recortado a cero o todo bajo
umbral. El otro disparador legítimo es que **lo pida la persona** ("avísame", "cuando tengas").
Ningún otro.

### Las cinco reglas de no-presión

1. **Nunca como condición.** Jamás "déjame tu correo para ver esto".
2. **Nunca en mitad de una respuesta.** Va después de que la respuesta esté completa.
3. **Una vez.** Si dijo que no o la ignoró, no vuelve en esa sesión.
4. **El "no" se respeta y se acabó.** Sin re-preguntar, sin casillas premarcadas.
5. **La promesa es acotada y se dice:** *"Te escribo solo cuando aparezca algo que encaje.
   Nada más."*

### La arquitectura: la puerta la abre el motor

El modelo **no decide** cuándo pedir el dato. El backend emite una directiva —el mismo patrón
de `map_seed` y `chart_seed`— y el frontend renderiza la puerta. El modelo narra; el motor
autoriza.

- El modelo **no puede** ponerse insistente aunque el prompt se degrade: la puerta no es texto
  que él escribe.
- Es determinista → testeable (`una_sola_vez`, `nunca_sin_criterio_declarado`,
  `nunca_como_condicion`).
- Queda registro de cuándo se abrió y por qué.

**El control hermano:** que el modelo pida datos de contacto **en prosa** es una violación
detectable. Un detector determinista sobre la salida ("tu correo", "déjame tu email", "tu
número", "para enviarte") cuando el backend no autorizó la puerta. Misma familia que
`detectar_promesa_inflada`.

### La línea roja

El **score de intención NO dispara la puerta**. El handoff mide *quiero hablar con un humano*;
la alerta mide *quiero que me avises*. Usar el score para pedir el correo convertiría el motor
de intención en un motor de acoso.

Y la otra, del §2: **el rol inferido jamás entra al scoring del encaje.** `DIMENSIONES` es una
whitelist cerrada por una razón — si el rol se cuela como dimensión, se reintroduce por la
puerta de atrás exactamente lo que esa whitelist cierra por construcción.

---

## 7. Lo que este plan NO hace, y por qué

- **Ningún selector de rol, ni opcional.** Una pantalla entre la persona y el valor.
- **Ningún muro de registro para buscar.** Es el peaje que el propio sector reconoce como error.
- **No construye las seis puertas suaves.** Cuatro piezas se montan; seis no.
- **No escribe a la lista.** Otro sistema, otro criterio, otra puerta de aprobación. La lista
  sale de aquí limpia y con origen marcado, que es lo que ese sistema necesita para arrancar.
- **No ordena la lista todavía.** Con cuarenta correos se miran uno a uno.
- **No toca la capa financiera.** Es donde las propias barandas ya dicen que no.

---

## 8. Riesgos aceptados

**1. El rendimiento de la alerta va a CAER cuando el producto mejore.** Se dispara en el
callejón honesto, que es frecuente con inventario escaso y raro con inventario denso. No leer
la caída como fallo: **medir alertas por callejón, no alertas totales.**

**2. La inferencia de rol es la pieza con menos evidencia detrás.** Debe **ofrecer, nunca
rutear en silencio**, y corregirse en una frase ("no, busco para un cliente").

**3. Esto no genera tráfico.** Instrumenta y retiene tráfico que todavía no existe. Es el orden
correcto —instrumentar antes de gastar— pero no confundirlo con un plan de crecimiento.

**4. Es más trabajo del que cabe.** Si solo se puede hacer una cosa: **F0**. Sin ella no se
sabe si algo funcionó, y es la única que además arregla defectos ya existentes. **La decisión
es real solo si F0 y F1 se construyen; el resto es un mapa, no un compromiso.**

**5. El repo es compartido.** F1 y F2 son migraciones de esquema: hay que coordinarlas con las
otras sesiones o dos migraciones van a chocar.

---

## Changelog (iterar aquí)

- **2026-08-06 — v0.2 · F0 CONSTRUIDA** — `migrations/024_visita.sql` (log append-only),
  `app/llegada.py` (clasificador puro, listas cerradas, referrer minimizado sin query),
  `POST /api/v1/visitas` best-effort, `registrarLlegada` en el montaje del frontend, y
  `fuente` del CRM tomada del canal real en vez de la constante `"QR"`. 40 tests nuevos.
  El bloque `estado-verificable` de este doc se puso **rojo al construir** (afirmaba
  `no-existe: migrations/024_visita.sql`) — funcionó como debía y se actualizó aquí. Un
  test cazó de paso un fallo del clasificador: `utm_source` trae **nombres** (`youtube`),
  no hosts (`youtube.com`), y reusar el mapa de hosts mandaba todo el tráfico etiquetado a
  `referido`; ahora `_FUENTES` va aparte.
- **2026-08-06 — v0.1** — Doc creado desde la auditoría de llegadas (§3, verificada contra el
  código el mismo día) + la investigación de casos externos (Duolingo, progressive profiling,
  portales). **Decisión dura tomada:** no hay onboarding en la puerta; una sola puerta suave;
  la abre el motor. Se fija que el core es el comprador y que **no se nombra** (el sistema ya
  es el copiloto), la convención "el Copiloto del corredor" y el nombre de la sección **"Antes
  de decidir"**. Se incorpora el §6 completo (no-presión como control, no como intención) y las
  dos líneas rojas: el score no dispara la puerta, y el rol inferido no entra al scoring. Nada
  construido.
