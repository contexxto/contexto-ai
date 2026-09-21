// Cómo se arma el texto del dictado por voz (Web Speech API), para el chat y para el mapa.
//
// Chrome en Android no entrega la voz como un texto limpio. En sesiones cortas (continuous=false,
// porque continuous=true ahí está roto) hace tres cosas que, sumadas sin cuidado, repiten frases:
//   · una misma frase llega como fotos acumulativas: «estoy» → «Estoy buscando…» (se reemplaza);
//   · una frase se parte en finales que se pisan: «quiero hacer una prueba», «una prueba»;
//   · al reiniciar la sesión, vuelve a entregar la frase anterior.
// Carlos lo vio en su teléfono el 2026-09-21: dijo «quiero hacer una prueba» y el campo quedó
// «quiero hacer una prueba quiero hacer una prueba una prueba quiero hacer una prueba».
//
// La regla es una sola: al unir un trozo detrás de lo que ya hay, se quita lo que se solapa —las
// últimas palabras de lo anterior que son las primeras del trozo—, y si el trozo ya está entero
// al final, no se agrega nada. El precio, aceptado: repetir a propósito una palabra justo en el
// corte de una pausa («no… no») deja una sola.

const normaliza = (p) => p.toLowerCase().replace(/[.,;:!?¡¿"«»()]/g, '')

export function unirSinRepetir(a, b) {
  const A = (a || '').trim()
  const B = (b || '').trim()
  if (!A) return B
  if (!B) return A
  const wa = A.split(/\s+/)
  const wb = B.split(/\s+/)
  const na = wa.map(normaliza)
  const nb = wb.map(normaliza)
  for (let k = Math.min(na.length, nb.length); k > 0; k--) {
    let solapa = true
    for (let i = 0; i < k; i++) {
      if (na[na.length - k + i] !== nb[i]) { solapa = false; break }
    }
    if (solapa) return [...wa, ...wb.slice(k)].join(' ')
  }
  return `${A} ${B}`
}

// Los resultados de UNA sesión (e.results) → { fin, parcial }. Se reconstruye siempre desde cero:
// una entrada que extiende a la anterior la reemplaza (foto acumulativa), y las demás se unen sin
// repetir lo que se pisa.
export function textoDeSesion(resultados) {
  const fins = []
  const parciales = []
  for (let i = 0; i < resultados.length; i++) {
    const r = resultados[i]
    const t = (r[0]?.transcript || '').trim()
    if (!t) continue
    const arr = r.isFinal ? fins : parciales
    const prev = arr[arr.length - 1]
    if (prev && (normaliza(t).startsWith(normaliza(prev)) || normaliza(prev).startsWith(normaliza(t)))) {
      arr[arr.length - 1] = t.length >= prev.length ? t : prev
    } else arr.push(t)
  }
  return { fin: fins.reduce(unirSinRepetir, ''), parcial: parciales.reduce(unirSinRepetir, '') }
}

// Lo que se ve en el campo: lo confirmado de sesiones anteriores + el final de esta + lo que aún
// se está oyendo, sin repetir lo que se solapa entre las tres.
export function textoVisible(base, fin, parcial) {
  return unirSinRepetir(unirSinRepetir(base, fin), parcial)
}

// Si pasa esto sin oír nada, el dictado se detiene solo y deja lo escrito en el campo, como ■.
// Sin tope, Android reabría el micrófono sin fin tras cada silencio: «sigue grabando sin parar».
export const SILENCIO_MAX_MS = 10000
