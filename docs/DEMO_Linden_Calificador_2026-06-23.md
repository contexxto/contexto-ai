# Demo en vivo — Calificador para Linden (Puebla)

**Para la reunión:** 23 jun 2026 · 13:30
**Cómo correrlo en vivo (desde la raíz del repo):**
```
python scripts/demo_linden.py
```
> Auto-suficiente: no necesita PYTHONPATH y fuerza UTF-8 (emojis no rompen en Windows).
> Corre con el **motor real** (`app/intencion.py`) — lo que ves es lo que el sistema produce, no una maqueta.

---

## La historia que cuenta (el arco de venta)

Tres leads de Puebla, de menos a más caliente. El punto: **el sistema reparte la atención de tus 20 asesores donde sí convierte.**

### 🔵 Caso 1 — Curioso (FRÍO · 0/100)
> 💬 *"Hola 👋 vi una casa en su Instagram que me gustó, ¿me cuentan más?"*
- **Estado:** IDENTIFICADO · **Handoff:** todavía no
- **Acción:** Ofrecer 1–3 caminos; dejar que tire del hilo.
- 🗣️ *"El asesor no gasta pólvora aquí. El sistema atiende y nutre, sin molestar al equipo."*

### 🟡 Caso 2 — Explorador que compara zonas (TIBIO · 32/100)
> 💬 *"¿Cómo es vivir en Angelópolis? me importa la caminabilidad y el ruido"*
> 💬 *"¿Y comparado con Lomas de Angelópolis? cuál es mejor para servicios y colegios"*
- **Estado:** EXPLORANDO · **Por qué:** compara opciones · explora la zona en varios mensajes
- **Acción:** Curaduría de 1–3 opciones con el porqué de cada una.
- 🗣️ *"Este es un comprador en formación. Un bot tonto lo marca 'frío' y lo pierdes. El nuestro lo sube a tibio y lo nutre hasta que esté listo."*

### 🔥 Caso 3 — Comprador caliente, sábado 11pm (CALIENTE · 92/100)
> 💬 *"Me encantó la casa en Lomas de Angelópolis, ¿cuánto cuesta?"*
> 💬 *"¿Se puede agendar una visita este fin de semana?"*
> 💬 *"¿Me pasan el contacto del asesor?"*
- **Estado:** INTENCIÓN · **Handoff:** SÍ ✅
- **Acción:** HANDOFF — notificar al asesor con el resumen de intención.
- 🗣️ *"Oficina cerrada, nadie responde. El sistema lo califica caliente y avisa al asesor al instante. **Ese lead ya no se enfría.**"*

---

## El remate (cuando termine de correr)

> *"Fíjate en tres cosas:
> 1. **Determinista** — califica sin costo de IA por lead. Escala a miles sin quemar dinero.
> 2. **Explicable** — siempre dice el *por qué*. Tus asesores confían, no es una caja negra.
> 3. **24/7** — el caliente de las 11pm se atiende a las 11pm."*

---

## ⚠️ Honestidad para la demo (NO improvisar esto)

**Esto es real para Puebla, no un truco.** El calificador detecta la *intención* en el texto en español (precio, visita, comparar zonas, pedir contacto) — **no depende de zonas codificadas de otra ciudad.** Por eso los nombres de Puebla (Angelópolis, Lomas de Angelópolis) funcionan tal cual: son lo que el lead escribe.

**Lo que SÍ se afina en el piloto** (dilo con franqueza si preguntan):
- Conexión a **WhatsApp** (hoy la demo es la lógica; el enganche al WhatsApp de Linden es alcance del piloto).
- **Datos locales de Puebla** (referencias de barrio, comparables) — el calificador ya corre; el enriquecimiento de zona se localiza.
- **Reparto entre los 20 asesores** — el handoff hoy es a un asesor; el ruteo al equipo se diseña con su flujo.

> Tu foso es la honestidad. Mostrar lo que YA corre y nombrar con claridad lo que se construye en el piloto **vende más** que aparentar que todo está listo.

---

## Plan B si no hay laptop / falla algo
Lleva una **captura de la salida** (corre el script antes y guárdala). El arco —frío → tibio → caliente— se cuenta igual de bien con la imagen.
