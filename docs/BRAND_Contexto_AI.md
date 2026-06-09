# Contexto AI — Brand & Design System Brief

> Documento base para construir el sistema de diseño de Contexto AI (al nivel del de Whaber).
> Pegar por secciones en el chat del Design System.

---

## 1. Esencia de marca

- **Nombre:** Contexto AI
- **Categoría:** PropTech · Inteligencia inmobiliaria geoespacial
- **Tagline:** *El Catastro Vivo de Latinoamérica*
- **One-liner:** Inteligencia geoespacial que elimina la asimetría de información inmobiliaria.
- **Misión:** Convertir cada coordenada física en un activo de datos permanente y veraz, para que comprar, arrendar o invertir en un inmueble deje de ser un acto a ciegas.
- **Idea central (el "porqué"):** Los portales tradicionales indexan *anuncios efímeros* que desaparecen. Contexto AI indexa el **activo físico permanente** (lat, lon, piso) y acumula su historia de habitabilidad y mantenimiento en el tiempo. Los inquilinos pasan; la coordenada queda.

---

## 2. Posicionamiento y diferenciador

- **No es** un portal de anuncios. **Es** un catastro vivo e inmutable.
- Los datos pertenecen al **activo**, no al aviso.
- Diferenciador demostrable: ante la misma pregunta, los LLM grandes dan consejos genéricos; Contexto AI responde con **inmuebles concretos, métricas medidas y fichas técnicas reales** (ruido en veh/día, walk score, cobertura vegetal, historial de mantenimiento).
- Lema de producto: *fin de la asimetría de información.*

---

## 3. Audiencias

| Segmento | Quién | Qué busca |
|----------|-------|-----------|
| B2C | Compradores / arrendatarios | Saber la verdad del entorno (ruido, tráfico, riesgos) antes de decidir |
| B2B | Inmobiliarias | API de inteligencia de activos para enriquecer su portafolio |
| B2B2C | Fondos de inversión | Informes de habitabilidad y plusvalía verificables |

---

## 4. Personalidad de marca (atributos)

1. **Confiable / veraz** — nunca inventa un dato; si no lo sabe, lo dice ("Indeterminado").
2. **Riguroso pero claro** — habla con datos, no con humo; técnico y a la vez accesible.
3. **Calmado y seguro** — autoridad serena, no estridencia (refleja la paleta suave).
4. **Permanente / sólido** — la idea de "inmutable", de cimiento que no cambia.
5. **Inteligente** — comprende inmuebles por su significado, no por palabras clave.

**Tono de voz:** directo, honesto, sin exageración de marketing. Explica el *porqué*. Reconoce lo que no sabe. (Ej.: "Foto nocturna limita la inspección" en vez de inventar.)

---

## 5. Valores que guían el diseño

- **Transparencia / honestidad** → diseño limpio, sin adornos que "vendan de más". Espacio en blanco, sin recuadros ni rayas innecesarias.
- **Permanencia / inmutabilidad** → motivos sólidos, geometría estable, el pin de coordenada.
- **Geoespacialidad** → mapas, coordenadas, capas de datos sobre el territorio.
- **Datos vivos** → la sensación de que la información se acumula y respira.

---

## 6. Paleta de color (exacta — tema oscuro, calmado)

Base oscura, suave y poco saturada (recién afinada en producción):

| Token | Hex | Uso |
|-------|-----|-----|
| `bg` | `#1A1C20` | Fondo principal |
| `surface` | `#23262B` | Tarjetas / paneles |
| `border` | `#343841` | Bordes sutiles |
| `text` | `#DDE2E8` | Texto principal |
| `text-muted` | `#969CA6` | Texto secundario |
| `primary` | `#41608C` | Azul de marca (botones, burbujas) |
| `primary-soft` | `#5E80AC` | Gradiente / hover |
| `accent` | `#8FB0D4` | Acento muteado (títulos, links) |
| `success` | `#6FB083` | Estados OK / publicado |
| `warning` | `#D29922` | Revisión / dato dudoso |
| `danger` | `#F85149` | Rechazo / error |

**Gradiente de marca:** `linear-gradient(135deg, #41608C, #5E80AC)` (usado en el logo/avatar).
**Principio cromático:** azul sereno y desaturado sobre dark suave; verde/ámbar/rojo solo como señales semánticas de estado, nunca decorativas.

---

## 7. Tipografía

- **Actual:** sans-serif del sistema (`-apple-system, Segoe UI`), limpia y neutra.
- **Sugerencia para el sistema:** un sans-serif geométrico-humanista para títulos (ej. *Inter*, *Geist* o *Satoshi*) + el mismo a menor peso para cuerpo. Monoespaciada (ej. *JetBrains Mono*) para datos/coordenadas/código — refuerza el lenguaje "catastral/técnico".
- Jerarquía: títulos con peso 600–700; cuerpo 400; datos en mono.

---

## 8. Logo e iconografía

- **Símbolo núcleo:** el **pin de mapa** (📍 map-pin) — representa la coordenada física permanente. Es la metáfora literal de la marca.
- **Logo actual:** pin dentro de un cuadrado redondeado con gradiente azul de marca.
- **Avatar del agente:** monograma "C" en círculo con el gradiente.
- **Estilo de íconos:** línea, trazo medio, esquinas suaves; familia coherente (estilo *lucide*).

---

## 9. Motivos gráficos / lenguaje visual

- **Cartográfico:** líneas de cuadrícula sutiles, coordenadas, retícula de mapa muy tenue de fondo.
- **Capas de datos:** la idea de superponer capas (ruido, tráfico, vegetación, estructura) sobre un punto del mapa.
- **Punto + radio:** un activo y su radio de análisis (círculos de búsqueda espacial, ST_DWithin).
- **Limpieza radical:** mucho aire, separación por espacio (no por líneas), bordes casi invisibles.
- **Inmutabilidad:** formas estables, simétricas; nada "ruidoso".

---

## 10. Estilo de imágenes

- **Fotografía real** de fachadas de Quito (La Carolina, Cumbayá, Centro Histórico) — auténtica, no stock genérico.
- Posible overlay de datos sobre la foto (pin + métricas) para mostrar el "catastro vivo".
- Mapas oscuros y elegantes (estilo dark-map) como fondo de hero.

---

## 11. Voz y mensajes clave (copy)

- "El Catastro Vivo de Latinoamérica."
- "Los datos pertenecen al activo, no al anuncio."
- "Inteligencia geoespacial que elimina la asimetría de información."
- "Una coordenada física es permanente. Los inquilinos son transitorios."
- "Lo que no se puede ver, no se inventa."
- "Como el historial de un auto, pero para tu inmueble."

---

## 12. Piezas que el Design System debería cubrir

- Tokens (color, tipografía, espaciado, radios, sombras)
- Logo + variantes (full, símbolo, monograma) y zona de protección
- Iconografía geoespacial
- Componentes UI: chat, tarjetas de inmueble, fichas técnicas, chips de estado (BAJO/MEDIO/ALTO ruido), badges de confianza
- Plantillas: pitch deck, portada LinkedIn, one-pager de inmueble, informe de habitabilidad
- Mapas y overlays de datos
- Estados (publicado / pendiente de revisión / rechazado) con su semántica de color

---

*Contexto local: la marca nace en **Quito, Ecuador**, con vocación Latam. La identidad debe sentirse moderna y global, pero anclada en el territorio.*
