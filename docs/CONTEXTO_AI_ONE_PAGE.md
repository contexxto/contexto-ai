# CONTEXTO AI — Una página
### Lo que hay que saber si mañana hay que explicárselo a un CTO, un inversor o un socio
**Fecha:** 2026-08-19 · **Commit:** `782e57ba` · Todo lo de abajo está verificado contra producción, la base de datos o el código.

---

## QUÉ ES

Una capa de **verificación de entorno** para decisiones inmobiliarias. Dado un punto en el mapa, mide qué hay alcanzable a pie —servicios, transporte, caminabilidad—, **cita la fuente de cada dato**, y conversa sobre ello con un agente que tiene prohibido afirmar lo que no consultó. Cuando la persona muestra intención real de transacción, la transfiere a un corredor humano dentro del mismo chat.

No es un portal. No compite por inventario. Compite por **la verdad del lugar**.

---

## QUÉ FUNCIONA (verificado hoy en producción)

- **API viva y sana**: `contexto-ai-oregon.onrender.com/health` → `healthy`, base `up`, memoria `postgres`. **60 rutas**.
- **Web en dominio propio**: `contexxto.com`, PWA completa con notificaciones push.
- **Entorno real por inmueble**: la ficha pública devuelve servicios con nombre y distancia, más *"🚇 Quitumbe a ~1496 m (20 min a pie)"* — **tiempo real caminando por calles**, no línea recta.
- **Verificación humana propagada**: cuando un corredor confirma o cierra un local con foto y coordenada, **el cambio aplica a todos los inmuebles del barrio**, no solo a esa ficha.
- **Motor de encaje determinista** con lista blanca cerrada anti-discriminación, ejecutado y comprobado en esta auditoría.
- **Memoria conversacional persistente**: 2.119 puntos de control, 246 hilos.
- **771 pruebas automáticas en verde**, en 95 segundos.
- Handoff con avisos, QR y letreros imprimibles, análisis de inversión, extracción de fichas por visión, CRM del corredor con su propio agente.

**784 commits en 11 semanas.**

---

## QUÉ DATOS TIENE

| Dato | Cantidad | Naturaleza |
|---|---|---|
| **Puntos de interés propios** | **8.512** (Quito) | Overture Places + OpenStreetMap, con procedencia y confianza, **almacenados** (Google prohíbe hacerlo) |
| **Isócronas peatonales propias** | 78 | Valhalla auto-hospedado, 15 y 30 min |
| **Inmuebles** | 40 | ⚠️ **39 son de demostración** (fotos de banco de imágenes, datos sembrados a mano) |
| **Inmuebles reales** | **1** | Fotos del corredor, entorno verificado en terreno el 2026-06-18 |
| **Verificaciones en terreno** | 4 | Con foto y coordenada. Todas del mismo día |
| **Conversaciones reales** | 148 sesiones · 246 hilos | 104 en junio, 35 en julio, **9 en agosto** |
| **Handoffs a corredor** | 10 | En toda la historia |

**Lo honesto de decir en voz alta:** *ruido, tráfico y cobertura vegetal no tienen fuente.* Son una tabla fija de siete sectores de Quito. El producto los rotula como estimación, pero no están medidos.

---

## QUÉ IA UTILIZA

- **Claude Sonnet 4.5** (Anthropic) para el agente del comprador, el agente del CRM, la extracción de preferencias y la lectura de fotos.
- **Voyage AI** (`voyage-multimodal-3`) para embeddings de imagen y ficha.
- **LangGraph** con una topología poco común y bien pensada: `llm → herramientas → **encaje** → llm`. El nodo intermedio calcula el ranking de forma determinista **y se lo entrega al modelo antes de que escriba**, con las mismas tarjetas que verá la persona. Existe porque el fallo contrario está documentado: el modelo afirmaba que $710 estaba "dentro de un presupuesto de $700".
- **Cuatro capas de barandas**: esquema cerrado en la entrada, lista blanca en el motor, detector de sesgo territorial en la salida, y un verificador que contrasta la prosa contra los números.
- El modelo **no calcula**: las restas de presupuesto y las antigüedades le llegan resueltas.

---

## QUÉ VENTAJA TIENE

**Una, y es real:** el dato de entorno **con procedencia, con fecha y con alguien que estuvo ahí**. Google prohíbe contractualmente almacenar sus POIs; un scraper no puede pisar la calle. La curación del corredor propaga a todo el barrio, así que cada verificación mejora el sistema entero.

**Una segunda, subestimada:** la doctrina de honestidad está *instrumentada*, no prometida. 568 líneas de prompt con contraejemplos de fallos reales, un motor de encaje auditable al 100%, y un verificador que mide si el modelo obedeció. Copiar el código es fácil; llegar a saber por qué cada regla está ahí cuesta meses de fallos.

**Lo que NO es ventaja:** los POIs de Overture/OSM (públicos, cualquiera los baja) ni la caminabilidad (metodología pública). Eso es el suelo, no el foso.

---

## QUÉ FALTA

1. **Inventario real.** 1 de 40. Sin inventario, ningún flujo tiene valor comercial.
2. **Validar el bucle del corredor.** Es la hipótesis central del negocio y tiene 4 observaciones a favor, todas de un solo día de junio.
3. **Reparar la tubería del foso.** Rota desde el 2026-08-18 (referencia fija a un lanzamiento de Overture que ya no existe). Y corre en el portátil del fundador.
4. **Cerrar `POST /api/v1/assets/`** — hoy cualquiera en internet puede escribir en el catastro de producción. Verificado.
5. **Integración continua.** 771 pruebas que no bloquean ningún despliegue.
6. **Fuente real de ruido.** La vía coherente: que el corredor mida decibelios con el móvil durante la visita.
7. **Observabilidad.** Un incidente de 1h26m se descubrió *"por casualidad, mirando otra cosa"*.

---

## QUÉ ESTAMOS INTENTANDO DEMOSTRAR

> **Que el dato de entorno verificado en terreno es escaso, valioso y acumulable — y que un corredor lo aportará porque le devuelve leads que llegan sabiendo lo que quieren.**

La primera mitad **ya es cierta y está construida**. La segunda mitad **no está demostrada**, y es de lo que depende todo lo demás.

La pregunta no es técnica. Es: *¿por qué un corredor ocupado dedicaría veinte minutos a curar el entorno de un inmueble?* Hoy la respuesta del producto es *"porque el dato queda para siempre"*. Esa es una respuesta de fundador. La que funcionaría es *"porque el lead que llega cierra más rápido"* — y todavía no se ha demostrado ni una vez.

---

## PRÓXIMO PASO

**Uno solo, y no es código:**

> **Diez inmuebles reales, cargados por un corredor que no sea Carlos, con letrero y QR en la calle, medidos durante dos semanas.**

Antes hay cuatro arreglos de higiene que caben en una semana y media: cerrar el endpoint abierto, reparar la tubería de datos, corregir la etiqueta de procedencia de la caminabilidad, y conectar las pruebas al despliegue.

**La métrica que decide todo a 30 días: número de inmuebles reales publicados por alguien que no sea el fundador. Hoy es 0.**

---

### En una frase, si solo hay tiempo para una

> *Contexto AI es un producto técnicamente sólido y desplegado —API sana, 8.512 puntos de interés propios, agente con memoria y barandas reales, 771 pruebas en verde— construido en once semanas por una persona, que todavía no ha demostrado que alguien fuera de su círculo quiera usarlo: un inmueble real, cuatro verificaciones en terreno y nueve conversaciones en el último mes.*
