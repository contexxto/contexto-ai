# Logotipo de Contexto

Maestro vectorial del logotipo, generado por código para que sea reproducible y nadie tenga que
retocar contornos a mano. Parte del logo que dibujó Carlos (isotipo de cuatro formas +
«CONTEXTO» en caja alta geométrica con la E de tres barras).

| Archivo | Qué es |
|---|---|
| `contexto-vertical.svg` | Versión principal: isotipo arriba, logotipo debajo (al doble de ancho). |
| `contexto-horizontal.svg` | Para cabeceras: isotipo a la izquierda, caja alta = 4 módulos. |
| `contexto-isotipo.svg` | El signo solo, maestro (≥ 48 px). Por debajo: `frontend/src/assets/sphere.svg`. |
| `contexto-logotipo.svg` | La palabra sola. Hereda `currentColor`. |
| `logo.json` | La geometría (contornos, blancos entre letras, retícula). |
| `genera_logo.py` | Construye todo lo anterior. Solo necesita Pillow (para medir los blancos). |
| `genera_componente.py` | Reescribe `frontend/src/LogoContexto.jsx` desde `logo.json`. |
| `genera_iconos.py` | Escribe los PNG de `frontend/public/` desde `logo.json`. `--check` audita los que hay. |

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

El favicon NO sale de aquí. A 16-32 px la calle de un módulo del maestro se cierra y el signo se
empasta; por eso `sphere-favicon.svg` conserva la retícula de calle ancha, que es la regla de
tamaño óptico de la tabla de arriba. `og-cover.png` tampoco: lleva titular y bajada en Geist, y
eso no es geometría.

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

Para cambiar algo: edita los parámetros de `genera_logo.py`, corre los dos scripts y revisa el
resultado. No edites `LogoContexto.jsx` ni los `.svg` a mano.
