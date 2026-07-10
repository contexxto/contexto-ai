# LÍNEA GRÁFICA — Referencia CRED para la web de la oferta + storefronts PYME

> **Contexto AI · 2026-07-08** · Extracción real de cred.club vía **Context.dev API** (styleguide + brand + markdown + images; archivos crudos en `docs/branding/cred-reference/`).
> Complemento oficial: **NeoPOP**, el design system de CRED, es **open source Apache 2.0** → [github.com/CRED-CLUB/neopop-web](https://github.com/CRED-CLUB/neopop-web) · playground: [playground.cred.club](https://playground.cred.club).
> **Ámbito:** la landing de la OFERTA "Shopify inmobiliario" + los storefronts generados para inmobiliarias PYME. La app Contexto **mantiene su design system ASI/teal actual** — esto NO lo reemplaza.

---

## 1. Por qué CRED (qué compra el "$10.000")

CRED se siente premium por **seis decisiones** (todas extraídas, no supuestas):

1. **Casi-monocromo:** paleta `#1c1c1c` (Eerie Black) · `#f7f7f7` (Lynx White) · `#7c7c7c` (gris) — theme-color `#000000`. El color es escaso → cuando aparece, manda.
2. **Tipografía editorial:** display **Gilroy** (400/600/700) + etiquetas **Overpass SemiBold en MAYÚSCULAS con letter-spacing 3.5px** (el sello: "A REFLECTION OF CLARITY"). Lujo = contraste tipográfico, no adornos.
3. **Espaciado dramático:** escala extraída `xs:10 / sm:20 / md:40 / lg:60 / xl:100px`. El lujo es aire.
4. **CTAs contundentes:** botones `min-width 238px · min-height 47px · radius 4px` (¡no pills!), padding 12/15. Pocos, grandes, seguros.
5. **Voz en minúsculas, frases cortas, marco de confianza/exclusividad:** *"not everyone gets it"*, *"crafted for the creditworthy"*, *"the proof writes itself"*, *"your data isn't our business. keeping it safe is."*
6. **NeoPOP** (la capa física): el efecto "plunk" 3D de sus botones/tarjetas — disponible legalmente (Apache 2.0).

**Cero sombras difusas** (shadows: none en todo el styleguide) — la profundidad viene del NeoPOP (aristas duras), no de blurs.

---

## 2. Tokens extraídos (crudos, de cred.club)

```
/* Paleta (brand API) */
--cred-black:  #1c1c1c;   /* Eerie Black — ¡== --bg de Contexto! */
--cred-white:  #f7f7f7;   /* Lynx White */
--cred-grey:   #7c7c7c;   /* Namara Grey */
theme-color:   #000000;

/* Tipografía (styleguide API) */
h1: Gilroy 700 · 36px/43px · ls 0
h2: Overpass-SemiBold 700 · 29px/41.6px · ls 3.5px   ← etiqueta espaciada (el sello)
h3: Gilroy 600 · 24px/29px
h4: Gilroy 600 · 20px/24px
p:  Gilroy 400 · 16px

/* Espaciado */
xs 10 · sm 20 · md 40 · lg 60 · xl 100 (px)

/* Botón primario (CSS extraído literal) */
min-width:238px; min-height:47px; background:#000; color:#fff;
border:1px solid #ffffff4d; border-radius:4px; padding:12px 15px;
font:600 16px gilroy-medium;
```

*(Gilroy es comercial — sustituto libre en nuestro stack: **Geist** (ya en Contexto) para display, o **Archivo/Inter tight**. La etiqueta espaciada: cualquier sans 600-700 en MAYÚSCULAS + `letter-spacing: .22em`.)*

---

## 3. Traducción a Contexto (adaptar, NO clonar)

**El puente ya existe:** el `--bg` de Contexto es `#1C1C1C` — **el mismo hex** que el Eerie Black de CRED. El parentesco es natural: casi-monocromo oscuro + **teal como EL único acento** (donde CRED no usa casi color, nosotros ponemos `--teal #2DBDB6` con la misma escasez deliberada).

| Elemento CRED | Versión Contexto (storefront/landing) |
|---|---|
| Etiquetas Overpass espaciadas | Rótulos de sección: `ENTORNO VERIFICADO` · `CATASTRO VIVO` · `ASÍ SE VIVE AQUÍ` (mayúsculas, ls .22em, --text-dim) |
| "not everyone gets it" (exclusividad) | **Exclusividad del inventario, no de la persona:** *"aquí no entra todo: solo lo verificado."* (Fair Housing: el club es de los INMUEBLES verificados, jamás de "gente que califica") |
| "complete security. no asterisks." | **Inversión de marca (nuestra joya):** *"la verdad del lugar. con los asteriscos donde importan."* — CRED presume no tener asteriscos; nosotros presumimos MOSTRARLOS (estimación vs medición). Es la honestidad hecha copy. |
| "the proof writes itself" | *"la prueba la puso el corredor — en terreno."* |
| CTAs 238px negros | CTAs teal-bright (#5EEAD4, texto #06201C) mismo tamaño/contundencia — como el chip Voz, agrandado |
| NeoPOP plunk (3D duro) | Opcional en botones/tarjetas del storefront (Apache 2.0, legal). Probar: borde inferior/derecho sólido teal-deep en CTAs — profundidad sin blur |
| Voz en minúsculas | Titulares en minúsculas estilo CRED: *"cada lugar tiene un aura."* (ya es tu tagline — encaja nativo) |

### Reglas duras
- **NO copiar:** logo/monograma CRED, ilustraciones, mascotas, copy literal, el nombre "club" con connotación de筛选 de personas.
- **Sí usar:** proporciones, escala de espaciado, patrón de etiqueta espaciada, contundencia de CTAs, NeoPOP (con atribución Apache 2.0 en el código).
- **Fair Housing:** el marco de "exclusividad" aplica SOLO al inventario verificado — nunca a quién puede entrar/comprar.

---

## 4. Estructura de landing extraída (esqueleto CRED, adaptable a la oferta)

1. **Hero monumental:** una frase (etiqueta espaciada arriba) + 1 CTA. *(CRED: "A REFLECTION OF CLARITY" → Contexto: "LA VERDAD DEL LUGAR" / "tu inmobiliaria, con la verdad debajo.")*
2. **Manifiesto corto** (3-4 líneas, minúsculas): la historia de confianza. *(CRED: "the story of CRED begins with trust…")*
3. **Bloques de producto** (uno por beneficio, MUCHO aire): vitrina verificada · agente que conoce el barrio · CRM Vivo · QR del letrero.
4. **Bloque de seguridad/honestidad:** *(CRED: "your data isn't our business")* → nuestro: *"tu cliente es TUYO. nosotros ponemos la verdad."* (anti-portal, anti-captura).
5. **Prueba social + números** ("the proof writes itself") → el "3x" propio cuando exista (tarea #12).
6. **Cierre de exclusividad de inventario** + CTA final.

---

## 5. Archivos de la extracción (crudos)

| Archivo | Contenido |
|---|---|
| `cred-reference/styleguide.json` | Tipografía, espaciados, sombras, CSS de botones/tarjetas |
| `cred-reference/brand.json` | Paleta con nombres, logo, slogan, descripción |
| `cred-reference/home.md.json` | Copy completo de la home (voz/estructura) + metadata OG |
| `cred-reference/images.json` | 40 assets visuales de la home (URLs) |
| `cred-reference/sitemap.json` | Mapa del sitio (mayormente SEO de calculadoras) |

**Pendiente/limitación:** el endpoint screenshot dio 403 (gated por plan) — para capturas visuales usar el playground de NeoPOP y el sitio en vivo. El styleguide capturó la variante clara de la home; la estética NeoPOP profunda (dark) sale del repo open source.

---

> **Una línea para recordar:** CRED vende exclusividad de personas; Contexto vende exclusividad de VERDAD. Mismo lenguaje de lujo — alma opuesta (y la nuestra es defendible ante Fair Housing).

---

## 6. ADDENDUM (2026-07-08 noche) — Capturas reales del sitio (24 screenshots de Carlos)

**Fuente:** `cred-reference/screenshots/` (24 PNG extraídos del PPTX de Carlos — la referencia VISUAL que el endpoint screenshot del API negó con 403). Corrigen y completan el styleguide extraído:

1. **El titular monumental es SERIF, no sans.** El hero ("crafted for the creditworthy", "feel the odds fall in your favor") usa un **serif editorial de alto contraste, gigante, en minúsculas, centrado** — el styleguide API reportó Gilroy porque midió el body/secciones, no el display del hero. **El lujo vive en ese serif.** Sustituto libre para nosotros: **Fraunces** (Google Fonts, alto contraste) o Playfair Display; el sans (Geist) queda para body/UI.
2. **El fondo no es negro plano: es 3D cinematográfico oscuro.** Monolitos de carbón con luz cálida rasante, esferas de vidrio — profundidad fotográfica, no CSS plano. Traducción sin producir 3D: **viñetas radiales + gradientes cálido-sutiles sobre carbón** (nuestro análogo natural: el AURA teal respirando sobre #1c1c1c — ya es lenguaje de Contexto).
3. **Etiqueta espaciada confirmada** en el header real ("CRED INDUSIND BANK…" caps + tracking amplio, en caja con borde fino).
4. **QR persistente** abajo-derecha en caja enmarcada ("download CRED") — patrón que mapea 1:1 a nuestro QR de letrero/tienda.
5. **Texto del hero centrado**, subtítulo corto en sans regular — jerarquía: etiqueta espaciada (arriba) → serif monumental → una línea sans → un CTA.

**Acción para la landing del paquete (`lanzamiento-pyme/landing.html`):** upgrade visual pendiente de revisión con Carlos — (a) hero a serif monumental (Fraunces), (b) fondo con profundidad (viñeta/aura teal), (c) caja de QR persistente. El resto de la línea (teal único, espaciado, CTAs 238px, minúsculas) ya está aplicado.

**Despliegue:** la landing y los storefronts viven en **dominio separado** (decisión de Carlos, 2026-07-08) — NUNCA sobre contexxto.com/la app. Candidatos naturales: subdominio (p.ej. `tiendas.contexxto.com`) o el dominio de la sub-marca ganadora del naming (los compuestos `contexto*.com` y `vitrinaviva.com` están libres — ver [`lanzamiento-pyme/naming.md`](../../lanzamiento-pyme/naming.md)). Proyecto Vercel separado; nada se publica sin su OK.
