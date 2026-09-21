# Logotipo de Contexto

Maestro vectorial del logotipo, generado por código para que sea reproducible y nadie tenga que
retocar contornos a mano. Parte del logo que dibujó Carlos (isotipo de cuatro formas +
«CONTEXTO» en caja alta geométrica con la E de tres barras).

| Archivo | Qué es |
|---|---|
| `contexto-vertical.svg` | Versión principal: isotipo arriba, logotipo debajo (al doble de ancho). |
| `contexto-horizontal.svg` | Para cabeceras: isotipo a la izquierda, caja alta = 4 módulos. |
| `contexto-isotipo.svg` | El signo, maestro. También es el favicon (`frontend/public/favicon.svg`, copia exacta). Ver «Tamaños». |
| `contexto-logotipo.svg` | La palabra sola. Hereda `currentColor`. |
| `logo.json` | La geometría (contornos, blancos entre letras, retícula). |
| `genera_logo.py` | Construye todo lo anterior. Solo necesita Pillow (para medir los blancos). |
| `genera_componente.py` | Reescribe `frontend/src/LogoContexto.jsx` desde `logo.json`: `Isotipo`, `Logotipo`, `LogoHorizontal` (+ `ALTO_MIN_HORIZONTAL`) y `LogoVertical`. Antes de escribir comprueba que el lockup horizontal calculado sea idéntico a `contexto-horizontal.svg`. |
| `genera_iconos.py` | Escribe los PNG de `frontend/public/` desde `logo.json`. `--check` audita los que hay. |
| `genera_og_cover.py` | Pone el lockup horizontal en `og-cover.png`. `--check` audita el que hay. |

## Los iconos de mapa de bits

`genera_iconos.py` escribe `icon-192`, `icon-512`, `icon-512-maskable`, `apple-touch-icon` (180)
y `badge-96`. Hasta el 2026-09-20 estaban hechos a mano y habían derivado sin que nadie lo
notara: su segundo color era `#2DBDB6`, un teal oscurecido, en lugar de la pizarra `#3A3D44`,
y llevaban la retícula antigua de calle ancha.

Cuánto ocupa el signo depende de quién recorta, y por eso no es un solo número:

| | del lienzo | por qué |
|---|---|---|
| `any` | 0,66 | nadie lo enmascara |
| `maskable` | 0,52 | Android recorta a un círculo del 80 %: el signo entero tiene que caber |
| `apple-touch-icon` | 0,62 | iOS aplica su máscara de superelipse |
| `badge-96` | 0,70 | se pinta a 24 px en la barra de estado; silueta blanca sobre transparente |

Cada archivo se comprueba antes de escribirse —paleta de marca, esquinas, centrado, tamaño del
signo y, en el maskable, que nada se salga del círculo seguro— y `tests/test_iconos_marca.py`
repite esa comprobación en cada corrida de CI sobre los archivos que de verdad se sirven. No se
comparan bytes: local corre Pillow 12 y CI Pillow 11.

**El favicon es el isotipo maestro (decisión de Carlos, 2026-09-21).** Hasta ese día era
`sphere-favicon.svg`, de calle ancha, por la regla de tamaño óptico. Carlos la revocó para el favicon
al ver el signo viejo en los accesos directos de Chrome, junto a todo lo demás ya con el nuevo. El
costo, dicho: en una pestaña de 16 px la calle del maestro mide 1,2 px. A cambio el maestro va ceñido
al lienzo —el favicon viejo dejaba 12,5 % de margen por lado—, así que el signo ocupa 16 px y no 12.
`genera_iconos.py` lo copia byte a byte desde `contexto-isotipo.svg` y `--check` lo audita.

## La tarjeta de compartir

`og-cover.png` (1200×630) es lo que ve quien recibe un enlace de Contexto. Llevaba el signo con la
retícula antigua y «Contexto» compuesto en la tipografía de la interfaz. Su segundo color era
`#3A3A3A`, un gris neutro: cada asset hecho a mano se había inventado el suyo (los PNG usaban
`#2DBDB6`), y ninguno era la pizarra `#3A3D44`.

`genera_og_cover.py` sustituye **solo el lockup**, no la tarjeta. El titular está en Geist, que no
está en disco: rehacerlo con otra tipografía sería cambiar el diseño en vez de aplicarlo. Dos
decisiones que conviene no re-derivar:

- **El fondo se interpola, no se rellena.** Bajo el lockup el resplandor teal ya entró (el canal
  verde va de 28 a ~47 de izquierda a derecha), así que un relleno liso dejaría un rectángulo
  visible. Se reconstruye cada columna entre la fila limpia de encima y la de debajo; medido contra
  dos bandas sin tinta, el error máximo es de **1 nivel** por canal.
- **Los contornos se rasterizan aquí mismo, sin dependencias.** `logo.json` solo usa `M`, `L`, `A`
  y `Z`, y los arcos son circulares: se aplanan a segmentos y se rellena par-impar por XOR de
  subcaminos (así salen los huecos de las O sin averiguar qué contorno es exterior). Cotejado
  contra el motor SVG de Chromium a 1000 px de ancho: correlación 0,968 del perfil de tinta por
  columna, 244 de 248 columnas vacías coincidentes y **5 columnas de 754** con más de 4 px de
  diferencia — todas el mismo medio píxel de convención en los bordes verticales.

## Construcción

- **Isotipo:** retícula de 13 módulos. Lado 6, calle 1, radio 1,35. El círculo mide 6,24 (+4 %):
  a igual medida que el cuadrado se ve más pequeño.
- **Logotipo:** contornos puros, sin fuente. Caja alta 100, asta 11, barras horizontales al 93 %,
  redondas al 104 % con rebase de 1,5, diagonales al 98 %. La E son tres barras, la central un
  10 % más corta y alineada a la izquierda (es una E, no una xi).
- **Espaciado:** no es a ojo ni uniforme. Se rasteriza cada letra, se mide el blanco que deja a
  cada lado dentro de la caja alta (con tope de profundidad) y se iguala el blanco medio entre
  parejas, amortiguado al 55 %.
- **Color:** teal `#5EEAD4`, pizarra `#3A3D44`; el logotipo hereda el color del texto.
- **Mínimos:** logotipo ≥ 96 px de ancho; área de respeto = medio lado del isotipo (3 módulos).

## Tamaños

El mínimo que manda es el de la **palabra**: por debajo de 96 px de ancho, sus astas de 11/100 bajan de un píxel y deja de leerse. De ahí salen los demás:

| Uso | Signo | Desde |
|---|---|---|
| Signo solo | `Isotipo` (maestro) | 48 px |
| Favicon (pestañas, accesos directos) | `favicon.svg` = isotipo maestro | cualquier tamaño (16 px en una pestaña) |
| Signo dentro de la app y en los letreros impresos | `assets/isotipo.svg`: las formas del maestro con la retícula al 75 % del lienzo (el margen del signo viejo) | 20-44 px |
| Lockup horizontal (cabeceras) | `LogoHorizontal`, con el isotipo maestro | 32 px de alto = `ALTO_MIN_HORIZONTAL` |

`ALTO_MIN_HORIZONTAL` no se decide aparte: es el menor alto en que la palabra del lockup llega a 96 px (32 × 39,738 / 13,24 = 96,04), y `genera_componente.py` lo calcula.

**Un solo signo (decisión de Carlos, 2026-09-21).** Ese día se retiró `sphere.svg`, el signo de calle ancha que la app usaba por dentro en doce sitios (cabecera del chat, avatar del asistente, ventanas, cargador) y que el generador de letreros llevaba pegado aparte. Ahora todo es el maestro: el favicon ceñido, y el de la app con el margen de antes para que en esos doce sitios cambie la forma y no el tamaño. `genera_iconos.py` escribe `isotipo.svg` desde las formas de `contexto-isotipo.svg`, y `scripts/generar_qrs.py` lo lee en vez de guardar su copia.

**Por qué el maestro baja a 32 px dentro del lockup (decisión de Carlos, 2026-09-21).** Para la cabecera del menú lateral se probaron en su teléfono tres variantes: el signo pequeño solo, el signo pequeño con la palabra, y el lockup con el isotipo maestro. Eligió el maestro, al tamaño de las otras dos. A 32 px su calle mide 2,5 px —6-7 píxeles reales en su teléfono—, así que la regla de 48 px sigue valiendo para el signo **solo**, donde tiene que sostenerse sin la palabra al lado. Nunca se empareja `sphere.svg` con la palabra: el lockup lleva siempre el maestro.

Para cambiar algo: edita los parámetros de `genera_logo.py`, corre los dos scripts y revisa el
resultado. No edites `LogoContexto.jsx` ni los `.svg` a mano.
