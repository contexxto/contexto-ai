# Inteligencia competitiva — Redfin × Sierra (búsqueda conversacional)

**Fecha:** 2026-06-23
**Video fuente:** https://www.youtube.com/watch?v=0TD9B1kQlTg
**Resumen en una línea:** El portal #2 de EE.UU. probó —con números— que conversar le gana a filtrar. Valida tu tesis y, a la vez, vuelve "lo conversacional" mesa de apuesta. Tu foso ya no puede ser la conversación; es el **dato verificado + el humano + el mercado sin MLS**.

---

## 1. Qué lanzó Redfin (13 nov 2025)

- **Búsqueda conversacional** en web + iOS + Android, construida con **Sierra**.
- Describes tu casa ideal en lenguaje natural ("sensación de cabaña, buena luz, ventanales") → el agente empareja sobre **millones de anuncios de su MLS**.
- Diálogo de ida y vuelta: acota y amplía ("cocina más moderna", "relaja las habitaciones", "amplía el radio").
- **Multilingüe.**

### Los números (pruebas tempranas)
| Métrica | Resultado |
|---|---|
| Anuncios vistos | **2× vs. búsqueda estándar** |
| Pedir un tour (alta intención) | **+47%** |
| (video) interacciones de alta intención | **+27%** |

> Frase de cabecera de Sierra: *"The conversation is the interface."*
> Testimonio de usuario: *"Fue como un concierge personal — me mostró barrios que no había considerado."*

---

## 2. El hueco que confirma tu foso 🎯

Lo más importante de toda la investigación: **Redfin empareja ATRIBUTOS del anuncio (cocina moderna, pisos de madera, cercanía a colegios desde el dato que YA tienen). NO verifica la realidad NO documentada del barrio** (ruido real, caminabilidad calculada, la verdad del corredor). Su comunicado no menciona verificación de entorno en ningún lado.

→ Redfin = mejor emparejamiento sobre **dato conocido**.
→ Contexto = el **dato que nadie tiene**.

Son capas distintas. No compites con Redfin; juegas debajo de él, en lo que su motor no toca.

---

## 3. Sierra — el socio (quién es, modelo, a quién vende)

- **Fundadores:** Bret Taylor (ex co-CEO Salesforce, presidente board OpenAI) + Clay Bavor (ex Google VR). Peso pesado.
- **Qué es:** plataforma horizontal de **agentes de servicio al cliente** para la Fortune 500 (reemplaza IVR/chat de soporte).
- **Modelo:** **precio por resultado** (pagas cuando el agente resuelve solo; si escala a humano, gratis). Contratos enterprise multi-año.
- **Tracción:** ~$200M ARR (may 2026), valuación **$15.8 mil M**, **~40% de la Fortune 50**.
- **Clientes:** WeightWatchers, SiriusXM, Sonos, **ADT**, Chime, Cigna, Nordstrom, **Nubank**, Ramp, Rivian, **Rocket Mortgage**, SoFi, Brex, Wayfair.
- 🔑 **ADT usa Sierra para CALIFICACIÓN DE LEADS** (lado seguridad/home services). **Tu caso de uso exacto, validado a escala Fortune 50.**

---

## 4. ¿Qué tan replicable es?

**La tecnología: SÍ, y ya tienes una versión.** Búsqueda conversacional = LLM + recuperación sobre tu catastro + bucle de intención. Tu agente (LangGraph en `graph.py`) **ya lo hace** — el demo de hoy lo probó (encontró 2 deptos en González Suárez, calificó al lead, capturó intención + día). No partes de cero; estás al ~80%.

**El foso de Sierra: NO, ni te interesa.** Su muralla es distribución enterprise + Bret Taylor + precio por resultado, no la tecnología. Eso es irrelevante para tu mercado.

**Lo que NO debes replicar:**
- Emparejar sobre millones de anuncios MLS → no tienes ese inventario y **LATAM no tiene MLS** (esa es tu ventaja, no tu carencia).
- Ser Sierra (agentes horizontales de soporte) → tú eres vertical + foso de dato.

**La ventaja estructural que te regala este lanzamiento:** el motor de Redfin/Sierra funciona *porque* el MLS gringo es rico y limpio. Quito y Puebla no lo tienen. Lo que los hace fuertes allá **los hace ausentes acá**. No pueden portar su motor a un mercado que carece del sustrato de datos que su motor asume.

---

## 5. Veredicto

1. **Cabalga su validación, no compitas con su producto.** Ellos te ahorraron la venta de la categoría.
2. **Conversación = interfaz (mesa de apuesta). Foso = dato verificado + humano + mercado sin MLS.**
3. **Refuerza la disciplina de backlog:** suelta "buscar inventario de barrios famosos" (Redfin lo posee ya); construye el foso del dato verificado.

**Fuentes:** Sierra–Redfin · Redfin blog/comunicado (13 nov 2025) · TechCrunch (Sierra $200M ARR) · Sacra · GeekWire.
