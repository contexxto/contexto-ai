/**
 * El ancho de los mensajes del chat: en el teléfono, de lado a lado; en computadora, como estaba.
 *
 * Carlos, 2026-09-21, con capturas de Perplexity y de Contexto lado a lado: «es importante la
 * distribución del texto en la ventana, en el ejemplo aprovecha de lado a lado». Medido a 369 px:
 * la respuesta ocupaba 227 px (62 %) — la columna del signo (42), el tope del 78 % y 30 px de
 * relleno a la derecha. Eligió la variante A en su teléfono: 332 px (90 %).
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { codigoDesnudo } from './codigoDesnudo'
import { maquetaMensaje } from './maquetaMensaje'

describe('en el teléfono', () => {
  const ia = maquetaMensaje({ isUser: false, enTelefono: true })
  const tu = maquetaMensaje({ isUser: true, enTelefono: true })

  it('la respuesta no lleva signo ni sangría', () => {
    expect(ia.conSigno).toBe(false)
    expect(ia.sangria).toBe(0)
  })

  it('la respuesta ocupa todo el renglón: sin tope y sin relleno a los lados', () => {
    expect(ia.contenedor).not.toHaveProperty('maxWidth')
    expect(ia.contenedor).toMatchObject({ flex: '1 1 auto', minWidth: 0 })
    expect(ia.relleno).toBe('2px 0')
  })

  it('tu mensaje sigue en su burbuja a la derecha, sin «Tú»', () => {
    expect(tu.conSigno).toBe(false)
    expect(tu.contenedor).toEqual({ maxWidth: '85%' })
    expect(tu.relleno).toBe('10px 14px')
  })
})

describe('en computadora no cambia nada', () => {
  it('la respuesta: signo, sangría de 42, tope del 78 % y relleno a la derecha', () => {
    expect(maquetaMensaje({ isUser: false, enTelefono: false })).toEqual({
      conSigno: true, sangria: 42, contenedor: { maxWidth: '78%' }, relleno: '2px 30px 2px 2px',
    })
  })

  it('tu mensaje: «Tú» y tope del 78 %', () => {
    expect(maquetaMensaje({ isUser: true, enTelefono: false })).toEqual({
      conSigno: true, sangria: 42, contenedor: { maxWidth: '78%' }, relleno: '10px 14px',
    })
  })
})

describe('App.jsx usa la maqueta', () => {
  const SRC = dirname(fileURLToPath(import.meta.url))
  const app = codigoDesnudo(readFileSync(join(SRC, 'App.jsx'), 'utf8'), 'App.jsx')
  const inicio = app.indexOf('function Message(')
  const mensaje = app.slice(inicio, app.indexOf('\nfunction ', inicio + 1))

  it('le pasa al mensaje si está en el teléfono', () => {
    expect(mensaje).toMatch(/function Message\(\{[^}]*\bisMobile\b[^}]*\}\)/)
    expect(mensaje).toMatch(/maquetaMensaje\(\{\s*isUser,\s*enTelefono:\s*isMobile\s*\}\)/)
    // La llamada lleva funciones flecha: su «=>» corta cualquier [^>]*. Se recorta hasta el «/>».
    const i = app.indexOf('<Message ')
    expect(i, 'no encontré <Message …/>').toBeGreaterThan(-1)
    expect(app.slice(i, app.indexOf('/>', i))).toContain('isMobile={isMobile}')
  })

  it('el signo y el «Tú» solo aparecen cuando la maqueta los lleva', () => {
    expect(mensaje).toMatch(/\{!isUser && conSigno && \(\s*<img src=\{isotipo\}/)
    expect(mensaje).toMatch(/\{isUser && conSigno && \(/)
  })

  it('el ancho, el relleno y la sangría salen de la maqueta, no escritos a mano', () => {
    expect(mensaje).toContain('<div style={contenedor}>')
    expect(mensaje).toMatch(/padding:\s*relleno,/)
    expect(mensaje).not.toMatch(/maxWidth:\s*'78%'/)
    expect(mensaje).not.toMatch(/paddingLeft:\s*(isUser \? 0 : )?(42|AVATAR_INDENT)\b/)
    expect(mensaje.match(/paddingLeft:\s*(isUser \? 0 : )?sangria/g)).toHaveLength(5)
  })
})
