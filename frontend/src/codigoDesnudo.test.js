/**
 * `codigoDesnudo` — que el helper cumpla lo que promete: borrar los comentarios
 * «conservando la posición de todo lo demás».
 *
 * Este fichero existe por un defecto concreto. El helper indexaba el fuente por CODE POINT
 * (`[...fuente]`) mientras que los rangos de oxc vienen en unidades UTF-16. Con un solo
 * carácter astral en el fichero — `App.jsx` lleva un emoji en una cadena — todos los rangos
 * posteriores quedaban corridos un índice: sobrevivía la primera `/` de cada comentario y se
 * borraba el carácter que lo seguía: la llave que cierra cada comentario JSX y, con CRLF, el
 * retorno de carro de fin de línea. Sobre `App.jsx` eran 262 de 471 comentarios, y la salida
 * ni siquiera volvía a parsear.
 *
 * Era benigno para las aserciones que había, y justo por eso es peligroso: un helper que
 * existe para evitar verdes falsos no puede deformar el texto sobre el que se afirma.
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { parseSync } from 'vite'
import { codigoDesnudo } from './codigoDesnudo'

const SRC = dirname(fileURLToPath(import.meta.url))

// U+1F4CD, el mismo de `App.jsx`. Escrito como escape para que se vea que es astral: ocupa
// DOS unidades UTF-16 y UN code point, que es toda la diferencia que importa aquí.
const CHINCHETA = '\u{1F4CD}'

describe('un carácter astral ANTES de un comentario no corre los rangos', () => {
  const fuente = [
    `const titulo = '${CHINCHETA} Inmueble'`,
    'const Vista = () => (',
    '  <div>',
    '    {/* x */}',
    '    <p>{titulo}</p>',
    '  </div>',
    ')',
    '',
  ].join('\n')
  const desnudo = codigoDesnudo(fuente, 'fixture.jsx')

  it('el comentario JSX desaparece entero y sus llaves quedan en su sitio', () => {
    // La línea exacta: `{`, siete espacios (lo que medía `/* x */`) y `}`. Con el corrimiento
    // salía `{/       ` — una `/` de resto y la `}` comida.
    expect(desnudo.split('\n')[3]).toBe('    {       }')
    expect(desnudo).not.toContain('x')
  })

  it('la salida mide lo mismo que el fuente y solo cambia dentro del comentario', () => {
    expect(desnudo).toHaveLength(fuente.length)
    const inicio = fuente.indexOf('/* x */')
    const fin = inicio + '/* x */'.length
    expect(desnudo.slice(0, inicio)).toBe(fuente.slice(0, inicio))
    expect(desnudo.slice(fin)).toBe(fuente.slice(fin))
  })

  it('con CRLF, el retorno de carro que sigue a un comentario de línea sobrevive', () => {
    const crlf = `const t = '${CHINCHETA}'\r\n// nota\r\nconst u = 1\r\n`
    expect(codigoDesnudo(crlf, 'fixture.js')).toBe(`const t = '${CHINCHETA}'\r\n       \r\nconst u = 1\r\n`)
  })

  it('un astral DENTRO de un comentario se borra sin descuadrar lo que viene después', () => {
    const f = `/* ${CHINCHETA} */ const a = 1 // fin\nconst b = 2\n`
    const d = codigoDesnudo(f, 'fixture.js')
    expect(d).toHaveLength(f.length)
    expect(d).toBe(`${' '.repeat(`/* ${CHINCHETA} */`.length)} const a = 1       \nconst b = 2\n`)
  })
})

describe('sobre los ficheros reales que pasan por el helper', () => {
  // Los dos fuentes sobre los que afirman `appCutover.test.js` y `leerStreamChat.test.js`.
  for (const nombre of ['App.jsx', 'leerStreamChat.js']) {
    it(`${nombre}: ningún comentario deja restos ni se come el carácter siguiente`, () => {
      const fuente = readFileSync(join(SRC, nombre), 'utf8')
      const desnudo = codigoDesnudo(fuente, nombre)
      expect(desnudo).toHaveLength(fuente.length)

      // Fuera de los rangos, idéntico al fuente; dentro, solo espacios y saltos de línea.
      // Se indexa la CADENA (unidades UTF-16), que es un camino distinto al del helper.
      const { comments } = parseSync(nombre, fuente, { sourceType: 'module' })
      expect(comments.length).toBeGreaterThan(0)
      const enComentario = new Uint8Array(fuente.length)
      for (const c of comments) enComentario.fill(1, c.start, c.end)
      const malos = []
      for (let i = 0; i < fuente.length; i++) {
        const ok = enComentario[i] ? (desnudo[i] === ' ' || desnudo[i] === '\n') : desnudo[i] === fuente[i]
        if (!ok) malos.push(i)
      }
      expect(malos).toEqual([])

      // Y la comprobación que no depende de esos rangos: lo desnudo sigue siendo un programa
      // válido y ya no trae comentarios. La salida corrida fallaba justo aquí.
      const otraVez = parseSync(nombre, desnudo, { sourceType: 'module' })
      expect(otraVez.errors).toHaveLength(0)
      expect(otraVez.comments).toHaveLength(0)
    })
  }
})
