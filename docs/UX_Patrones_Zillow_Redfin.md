# Patrones de UX — Zillow y Redfin destilados para Contexto

**Fecha:** 19 jun 2026
**Origen:** *teardowns* de zillow.com y redfin.com hechos con Claude en Chrome (inspección de
estructura/UX, NO extracción de anuncios — ambos bloquean el scraping). Insumo para el trabajo
de UX, sobre todo el **Mapa Vivo (escalón 2A)** de `UX_Vision_Intent_Matching.md`.

> **Síntesis en una frase:** roba su disciplina —*una intención, una caja, un número de marca,
> URL semántica, telemetría*— e ignora su foso (inventario/MLS), su mapa de pines de precio y su
> dibujo a mano. Tu ventaja es el **dato local verificado y contribuido**, no el catálogo.

---

## 🟢 ROBAR (con su traducción a Contexto)

| Patrón observado | Traducción a Contexto |
|---|---|
| Caja única de intención + "AI Search" en beta (Redfin) | Declarar la vida en lenguaje natural ("a 10 min a pie del Metro, parque y colegio cerca"). Extiende los chips actuales. **Su beta valida el rumbo — y aún no lo resuelven.** |
| Estado geográfico en la URL (`viewport=N:S:E:O`, `poly=…`) | URL **como intención**: `walk=10min;anchor=metro;parque=true` → compartible, indexable, SEO local que un portal cerrado no tiene |
| Lienzo de terceros + **capa propia** de pines (Redfin pone overlay sobre Google) | Google/OSM dan tiles/zoom; **tú dibujas tus pines verificados** por categoría. Mapa mundial sin construir motor, sin atarte a sus widgets |
| Sincronía total mapa↔lista, un solo estado de verdad | El pin sabe qué tarjeta es; cero disonancia |
| Autocompletado multi-entidad (ciudad, dirección, colegio, agente) | Buscar **barrio, estación de Metro, parque, colegio** como entidades |
| Control deslizante de umbral para calidad (no binario) | "Buen colegio" / "tranquilo" son un continuo, no un sí/no |
| Telemetría geográfica/​de intención de 1ª clase | Saber **qué intenciones busca la gente** = activo de demanda defendible, desde el día 1 |
| Marcadores de carga (placeholders) sobre spinners | El dato local (que tarda en agregarse) no se siente lento; cero salto de layout |
| Personalización **opt-in honesta** + corredor como destino de 1ª clase | Decir para qué sirve registrarse; "habla con quien conoce el barrio de verdad" |

---

## ⭐ LA JUGADA MAESTRA — isócronas peatonales reales (tu foso)

El dibujo a mano de Redfin tiene 3 defectos que se vuelven tu ventaja:
1. **Es geometría, no semántica** — un recinto no entiende "cerca del Metro", solo "dentro de la línea".
2. **Distancia en línea recta** — pierde casas a 200 m en recta pero a un puente de distancia caminando.
3. **Efecto borde** — descarta inmuebles idénticos por estar un metro fuera del trazo.

**Contexto lo invierte:** el usuario **declara** la intención; tú calculas una **superficie de aptitud**
con **rutas reales a pie** (Google Routes — ya activo, los "19 min al Metro" de hoy) intersectando los
**imanes de vida verificados** (Metro, parque, colegio). Resultado: **puntaje continuo + explicación**
("a 8 min del Metro, parque a 4"), **sin dentro/fuera**. *Donde Redfin filtra, tú recomiendas y explicas.*
→ **Este es el blueprint del Mapa Vivo (escalón 2A).** El cimiento (caminata real) ya existe.

---

## 🔴 IGNORAR (disciplina anti-portal)

- **La carrera por inventario/MLS** — su foso, no el tuyo.
- **El mapa-céntrico de pines de precio como pantalla principal** — si tu home es "muchos pines con $", perdiste contra Zillow/Plusvalía. Tu home es la **zona y su verdad vivida**.
- **El embudo financiero** (hipotecas/Home Loans) — negocio de Zillow, te desvía.
- **El gancho "early access" / urgencia** — tu retención viene de la **frescura del dato**, no de inventario anticipado.
- **El dibujo a mano alzada** — es justo el patrón que tu producto **vuelve obsoleto**; ofrecerlo "porque Redfin lo tiene" diluiría tu propuesta.
- **Micro-frontends, Apollo, Module Federation, design system multi-equipo** (Zillow) — ingeniería para cientos de personas. Roba la **filosofía** (design system, URL-como-estado, telemetría declarativa), NO la complejidad. Empieza monolito simple.

---

## ⚠️ LA TRAMPA DEL PUNTAJE

Tentación: un "puntaje de habitabilidad" de marca (tipo "BuyAbility" de Zillow). **Bien, pero con cuidado:**
un puntaje **absoluto de zona** ("esta zona: 87/100") **es RANKING** — lo que estás dejando atrás
(*de ranking a recomendación*) y es **gameable**. Si haces un número, que sea **relativo a la intención**
("**87% de encaje con lo que TÚ buscas**"), igual que BuyAbility es relativo a **tu** presupuesto. La
caminabilidad (0-100) es **un dato de entrada**, no el titular.

---

## Conexión con docs
- `UX_Vision_Intent_Matching.md` — el Mapa Vivo (E / escalón 2A) es donde aterriza la jugada de isócronas.
- `VISION_Sistema_Vivo.md` — el foso (dato contribuido) que ninguno de los dos portales tiene.
- `INTELIGENCIA_y_PLAN_2026-06-16.md` — Cynthia Wu (1.5): el dato es el muro; el agente es commodity.
