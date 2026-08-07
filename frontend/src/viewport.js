/**
 * Respaldo medido para --app-h (ver el porqué completo en index.css).
 *
 * El CSS ya calcula `100dvh - env(safe-area-inset-bottom)`. Eso es lo correcto en teoría,
 * pero si el navegador NO expone el inset de la barra de navegación (Chrome de Android
 * reporta 0 arriba incluso en la PWA instalada, así que abajo tampoco está garantizado),
 * el cálculo se queda en 100dvh y vuelve a medir de más. `innerHeight` sí da la altura
 * visible real: en el Android de Carlos, 750 frente a los 806 de 100dvh.
 *
 * Deliberadamente simple, porque la versión anterior se rompió por hacer de más:
 *  - NO usa visualViewport ni intenta detectar el teclado. Ese heurístico confundía un
 *    viewport legítimamente pequeño con el teclado abierto y dejaba la altura congelada.
 *    `innerHeight` ya se encoge con el teclado en Android, que es el comportamiento que
 *    queremos (la barra de escribir sigue a la vista).
 *  - Nunca escribe un 0: sin medida fiable no toca nada y manda el cálculo del CSS.
 *    Un 0 dejaba el shell sin altura y la app en blanco.
 */
export function instalarAlturaVisible() {
  const raiz = document.documentElement
  let anterior = null      // lectura previa, para exigir confirmación
  let aplicado = null      // lo último que llegamos a escribir
  const aplicar = () => {
    const alto = Math.round(window.innerHeight)
    // Un 0 deja el shell sin altura y la app en blanco: sin medida fiable, no tocamos
    // nada y manda el cálculo del CSS.
    if (!(alto > 0)) return
    // Dos lecturas seguidas iguales antes de escribir. innerHeight da valores pasajeros
    // malos (medido: alternaba 812 y 650 en el mismo viewport), y escribirlos encogía el
    // shell de golpe. En un teléfono eso sería un salto visible al rotar o al abrir el
    // teclado. Una lectura solitaria no cambia nada; una sostenida, sí.
    const confirmada = alto === anterior
    anterior = alto
    if (!confirmada || alto === aplicado) return
    aplicado = alto
    raiz.style.setProperty('--app-h', `${alto}px`)
  }
  aplicar()
  requestAnimationFrame(aplicar)          // por si aún no había medida en el primer intento
  window.addEventListener('load', aplicar)
  window.addEventListener('resize', aplicar)
  window.addEventListener('orientationchange', aplicar)
  // Repaso periódico: no todos los entornos emiten 'resize' al cambiar el viewport (el
  // panel de pruebas de Claude Code no lo hace, ni tampoco ResizeObserver), y una altura
  // obsoleta en el atributo style PISA al cálculo del CSS. Dos segundos no cuestan nada
  // y garantizan que converja aunque no llegue ningún evento.
  setInterval(aplicar, 2000)
}
