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
