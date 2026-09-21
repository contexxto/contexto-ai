/**
 * El texto del dictado por voz no repite frases, y el dictado no graba sin fin.
 *
 * Carlos, 2026-09-21, en su teléfono: dijo «quiero hacer una prueba» y el campo quedó «quiero hacer
 * una prueba quiero hacer una prueba una prueba quiero hacer una prueba»; y el micrófono seguía
 * abierto sin forma de pararlo. Las secuencias de abajo imitan lo que entrega Chrome en Android.
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { codigoDesnudo } from './codigoDesnudo'
import { SILENCIO_MAX_MS, textoDeSesion, textoVisible, unirSinRepetir } from './dictado'

// Una entrada de e.results como la entrega Web Speech: [{ transcript }] + isFinal.
const r = (transcript, isFinal = true) => Object.assign([{ transcript }], { isFinal })

describe('unir sin repetir', () => {
  it('une dos frases distintas con un espacio', () => {
    expect(unirSinRepetir('busco un departamento', 'cerca del metro')).toBe('busco un departamento cerca del metro')
  })

  it('un trozo que ya está entero al final no se agrega', () => {
    expect(unirSinRepetir('quiero hacer una prueba', 'una prueba')).toBe('quiero hacer una prueba')
    expect(unirSinRepetir('quiero hacer una prueba', 'Quiero hacer una prueba.')).toBe('quiero hacer una prueba')
  })

  it('si el trozo repite lo anterior y sigue, solo se agrega lo nuevo', () => {
    expect(unirSinRepetir('quiero hacer una prueba', 'quiero hacer una prueba en La Carolina'))
      .toBe('quiero hacer una prueba en La Carolina')
  })

  it('lo vacío no ensucia', () => {
    expect(unirSinRepetir('', 'hola')).toBe('hola')
    expect(unirSinRepetir('hola', '  ')).toBe('hola')
  })
})

describe('el caso de Carlos, como lo entrega Android', () => {
  it('una sola frase, partida en finales que se pisan y reentregada en cada reinicio, queda una vez', () => {
    // Sesión 1: fotos acumulativas y un final. Sesión 2: Chrome vuelve a entregar la frase y un
    // pedazo suelto. Sesión 3: otra vez la frase.
    let base = ''
    for (const sesion of [
      [r('quiero', false)],
      [r('quiero hacer una prueba')],
      [r('quiero hacer una prueba'), r('una prueba')],
      [r('Quiero hacer una prueba')],
    ]) {
      const { fin } = textoDeSesion(sesion)
      base = unirSinRepetir(base, fin)
    }
    expect(base.toLowerCase()).toBe('quiero hacer una prueba')
  })

  it('lo nuevo que se dice después sí se suma', () => {
    let base = unirSinRepetir('', textoDeSesion([r('quiero hacer una prueba')]).fin)
    base = unirSinRepetir(base, textoDeSesion([r('quiero hacer una prueba'), r('del dictado por voz')]).fin)
    expect(base).toBe('quiero hacer una prueba del dictado por voz')
  })

  it('lo que aún se oye (parcial) no duplica lo ya confirmado', () => {
    const { fin, parcial } = textoDeSesion([r('cerca del metro'), r('cerca del metro de Quito', false)])
    expect(textoVisible('busco un departamento', fin, parcial)).toBe('busco un departamento cerca del metro de Quito')
  })

  it('las fotos acumulativas de una frase se reemplazan, no se suman', () => {
    expect(textoDeSesion([r('estoy'), r('Estoy buscando'), r('Estoy buscando arriendo')]).fin).toBe('Estoy buscando arriendo')
  })
})

describe('el chat y el mapa usan estas reglas', () => {
  const SRC = dirname(fileURLToPath(import.meta.url))
  const leer = (f) => codigoDesnudo(readFileSync(join(SRC, f), 'utf8'), f)

  it.each(['App.jsx', 'MapView.jsx'])('%s arma el texto con dictado.js y se detiene tras el silencio', (f) => {
    const t = leer(f)
    expect(t).toMatch(/import \{[^}]*\btextoDeSesion\b[^}]*\} from '\.\/dictado'/)
    expect(t).toMatch(/textoDeSesion\(e\.results\)/)
    expect(t).toMatch(/textoVisible\(/)
    expect(t).toMatch(/unirSinRepetir\(/)
    // Se reinicia solo mientras haya voz, y cada resultado con texto cuenta como voz.
    expect(t).toMatch(/!\w+StopRef\.current && Date\.now\(\) - ultimaVoz < SILENCIO_MAX_MS/)
    expect(t).toMatch(/if \(fin \|\| parcial\) ultimaVoz = Date\.now\(\)/)
    // Ya no une los finales por su cuenta: ese join fue el que dejó pasar las repeticiones.
    expect(t).not.toMatch(/fins\.join\(' '\)/)
  })

  it('el tope de silencio es de segundos, no de minutos', () => {
    expect(SILENCIO_MAX_MS).toBeGreaterThanOrEqual(5000)
    expect(SILENCIO_MAX_MS).toBeLessThanOrEqual(15000)
  })
})
