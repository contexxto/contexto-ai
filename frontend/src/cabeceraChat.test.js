/**
 * La cabecera del chat lleva el lockup de la marca, y las entradas no mandan emojis.
 *
 * Carlos, 2026-09-21, con una captura de una conversación en su teléfono: «aún sigue lo viejo».
 * Dos cosas viejas a la vista, las dos del frontend:
 *
 *  1. La cabecera del chat (la que se ve en CADA conversación) componía el signo con «Contexto»
 *     escrito a mano en la letra de la interfaz. El logotipo no es texto: es la E de tres barras.
 *     Se escapó de la primera búsqueda porque la palabra va en su propia línea del JSX, y
 *     `>Contexto<` no la veía.
 *  2. La entrada «Busca cerca del Metro o de mi trabajo» mostraba su etiqueta sin emoji pero
 *     ENVIABA «🚇 Quiero vivir cerca…». La migración de marca de agosto retiró los emojis de la
 *     interfaz; este quedó escondido en el texto que se manda, no en el que se ve.
 *
 * El 🚇 no lo lee el backend: `_EMOJI_TRANSPORTE` de app/decision/assembler.py se usa sobre el
 * texto de servicios guardado, nunca sobre el mensaje de la persona.
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { codigoDesnudo } from './codigoDesnudo'
import { INTENCIONES } from './intencionesEntrada'

const SRC = dirname(fileURLToPath(import.meta.url))
const app = codigoDesnudo(readFileSync(join(SRC, 'App.jsx'), 'utf8'), 'App.jsx')

/** El bloque de la cabecera que se ve cuando la conversación ya tiene mensajes. */
function cabeceraConMensajes() {
  const i = app.indexOf('{!isEmpty && (')
  expect(i, 'no encontré la cabecera con mensajes').toBeGreaterThan(-1)
  return app.slice(i, app.indexOf(')}', i) + 2)
}

describe('la cabecera del chat', () => {
  it('usa el lockup horizontal generado, al alto mínimo, con el color del tema', () => {
    expect(cabeceraConMensajes()).toMatch(
      /<LogoHorizontal\s+alto=\{ALTO_MIN_HORIZONTAL\}\s+style=\{\{\s*color:\s*'var\(--text\)'\s*\}\}/)
  })

  it('no vuelve a escribir «Contexto» a mano, ni en su propia línea', () => {
    expect(cabeceraConMensajes()).not.toMatch(/>\s*Contexto\s*</)
  })

  it('no empareja el signo suelto con la palabra', () => {
    expect(cabeceraConMensajes()).not.toContain('src={isotipo}')
  })

  it('en computadora con el menú abierto no repite el logotipo: el menú ya lo lleva arriba', () => {
    // Carlos, 2026-09-21, al lado de ChatGPT: el logotipo salía dos veces, en el menú y en la cabecera.
    expect(app).toMatch(/\{!isEmpty && \(isMobile \|\| sidebarCollapsed\) && \(/)
  })
})

describe('las intenciones de entrada', () => {
  const pictograma = /\p{Extended_Pictographic}/u

  it('ningún texto que se envía lleva emoji', () => {
    const con = INTENCIONES.filter((i) => i.intent && pictograma.test(i.intent)).map((i) => i.id)
    expect(con).toEqual([])
  })

  it('ninguna etiqueta que se ve lleva emoji', () => {
    const con = INTENCIONES.filter((i) => i.label && pictograma.test(i.label)).map((i) => i.id)
    expect(con).toEqual([])
  })

  it('control: el detector sí reconoce el emoji que había', () => {
    expect(pictograma.test('🚇 Quiero vivir cerca del Metro o de mi trabajo')).toBe(true)
    expect(pictograma.test('Quiero vivir cerca del Metro o de mi trabajo')).toBe(false)
  })
})
