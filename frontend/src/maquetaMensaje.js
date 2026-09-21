// Cómo se reparte el ancho del chat.
//
// Los mensajes, en el teléfono y en computadora: sin el signo ni «Tú» en cada uno —el logotipo ya está
// en la cabecera—; la respuesta ocupa todo el renglón de la columna; tu mensaje, en su burbuja a la
// derecha. Carlos lo eligió el 2026-09-21 mirando variantes, con Perplexity de referencia: la «A» en el
// teléfono (a 369 px la respuesta pasó de 227 px, el 62 %, a 335, el 91 %) y la «D» en computadora.
//
// La columna, solo en computadora: mensajes y campo de escribir en 768 px centrados, como ChatGPT y
// Perplexity. A 1536 px de ancho el renglón medía 875 px (121 caracteres); ahora 762 (81). En el
// teléfono la columna es la pantalla entera.

export const ANCHO_COLUMNA_PC = 768

// La letra de los mensajes (los tuyos y las respuestas), igual en el chat y en la conversación
// compartida: un solo sitio para cambiarla. 16 px, como ChatGPT y como la base de lectura de los
// teléfonos (Carlos, 2026-09-21, tras compararla en su teléfono con la de antes, .92rem = 14,7 px).
// Con la columna de 768 px el renglón baja de ~81 a ~75 caracteres. Títulos, tablas y filas de
// encaje van en em (index.css) y crecen con ella.
export const LETRA_MENSAJE = { fontSize: '1rem', lineHeight: 1.65 }

export function maquetaMensaje({ isUser }) {
  return {
    contenedor: isUser ? { maxWidth: '85%' } : { flex: '1 1 auto', minWidth: 0 },
    relleno: isUser ? '10px 14px' : '2px 0',
  }
}

// Relleno a cada lado que centra la columna: lo que sobra de los 768 px, nunca negativo.
export function rellenoColumna({ enTelefono }) {
  return enTelefono ? '0px' : `max(0px, calc((100% - ${ANCHO_COLUMNA_PC}px) / 2))`
}
