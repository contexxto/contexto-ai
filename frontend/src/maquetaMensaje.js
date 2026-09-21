// Cómo se reparte el ancho de un mensaje del chat.
//
// En el teléfono la respuesta va de lado a lado. Carlos lo pidió el 2026-09-21 con Perplexity de
// referencia y eligió esta forma (la «A») mirando cuatro variantes en su teléfono: sin el signo ni
// «Tú» en cada mensaje —el logotipo ya está en la cabecera—, sin el tope del 78 % y sin los 30 px de
// relleno a la derecha. A 369 px de ancho el texto pasó de 227 px (62 %) a 332 px (90 %).
//
// En computadora sigue como estaba: con la columna de hasta 1280 px, un renglón de todo el ancho se
// lee mal, y su columna de lectura está por decidir.

export function maquetaMensaje({ isUser, enTelefono }) {
  const conSigno = !enTelefono
  return {
    // El signo del asistente y el «Tú» del usuario, cada uno en su columna.
    conSigno,
    // Sangría de tarjetas, botones y hora para alinearlos con el texto: 32 del signo + 10 de hueco.
    sangria: conSigno ? 42 : 0,
    // La burbuja del usuario se queda a la derecha; la respuesta, en el teléfono, ocupa todo el renglón.
    contenedor: isUser
      ? { maxWidth: conSigno ? '78%' : '85%' }
      : conSigno ? { maxWidth: '78%' } : { flex: '1 1 auto', minWidth: 0 },
    relleno: isUser ? '10px 14px' : conSigno ? '2px 30px 2px 2px' : '2px 0',
  }
}
