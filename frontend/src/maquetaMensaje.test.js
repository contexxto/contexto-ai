/**
 * El ancho del chat: mensajes sin signo ni «Tú», de lado a lado; en computadora, una columna centrada.
 *
 * Carlos, 2026-09-21, con capturas de Perplexity y de Contexto lado a lado: «es importante la
 * distribución del texto en la ventana, en el ejemplo aprovecha de lado a lado». En el teléfono la
 * respuesta ocupaba 227 de 369 px (62 %): eligió la «A». En computadora, con la captura de su pantalla,
 * el renglón llegaba a 875 px (121 caracteres): eligió la «D», columna de 768 px como ChatGPT y Perplexity.
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { codigoDesnudo } from './codigoDesnudo'
import { ANCHO_COLUMNA_PC, LETRA_MENSAJE, maquetaMensaje, rellenoColumna } from './maquetaMensaje'

describe('los mensajes', () => {
  it('la respuesta ocupa todo el renglón: sin tope y sin relleno a los lados', () => {
    const ia = maquetaMensaje({ isUser: false })
    expect(ia.contenedor).not.toHaveProperty('maxWidth')
    expect(ia.contenedor).toEqual({ flex: '1 1 auto', minWidth: 0 })
    expect(ia.relleno).toBe('2px 0')
  })

  it('tu mensaje sigue en su burbuja a la derecha', () => {
    expect(maquetaMensaje({ isUser: true })).toEqual({ contenedor: { maxWidth: '85%' }, relleno: '10px 14px' })
  })
})

describe('la columna', () => {
  it('en computadora mide 768 px y se centra con lo que sobra a cada lado', () => {
    expect(ANCHO_COLUMNA_PC).toBe(768)
    expect(rellenoColumna({ enTelefono: false })).toBe('max(0px, calc((100% - 768px) / 2))')
  })

  it('en el teléfono es la pantalla entera', () => {
    expect(rellenoColumna({ enTelefono: true })).toBe('0px')
  })
})

describe('la letra', () => {
  it('los mensajes van a 16 px, con el interlineado de siempre', () => {
    expect(LETRA_MENSAJE).toEqual({ fontSize: '1rem', lineHeight: 1.65 })
  })

  it('títulos, tablas y filas de encaje de las respuestas crecen con ella (em, no rem)', () => {
    const SRC = dirname(fileURLToPath(import.meta.url))
    const css = readFileSync(join(SRC, 'index.css'), 'utf8')
    expect(css).toMatch(/\.ai-content h2, \.ai-content h3 \{[^}]*font-size: 1\.087em;/)
    expect(css).toMatch(/\.ai-content h2 \{ font-size: 1\.141em; \}/)
    expect(css).toMatch(/\.ai-content h4 \{[^}]*font-size: 1em;/)
    expect(css).toMatch(/\.ai-content table \{[^}]*font-size: \.913em;/)
    // Fuera del chat (CRM, leads) la fila de encaje conserva su .9rem; dentro, relativa a la letra.
    expect(css).toMatch(/\.enc-fila \{ font-size: \.9rem; \}/)
    expect(css).toMatch(/\.ai-content \.enc-fila \{ font-size: \.978em; \}/)
    const md = readFileSync(join(SRC, 'markdown.js'), 'utf8')
    expect(md).toContain('<div class="enc-fila" style="')
    expect(md).not.toMatch(/enc-fila" style="[^"]*font-size/)
  })
})

describe('App.jsx usa la maqueta', () => {
  const SRC = dirname(fileURLToPath(import.meta.url))
  const app = codigoDesnudo(readFileSync(join(SRC, 'App.jsx'), 'utf8'), 'App.jsx')
  const inicio = app.indexOf('function Message(')
  const mensaje = app.slice(inicio, app.indexOf('\nfunction ', inicio + 1))

  it('el mensaje toma ancho y relleno de la maqueta, no escritos a mano', () => {
    expect(mensaje).toMatch(/maquetaMensaje\(\{\s*isUser\s*\}\)/)
    expect(mensaje).toContain('<div style={contenedor}>')
    expect(mensaje).toMatch(/padding:\s*relleno,/)
    expect(mensaje).not.toMatch(/maxWidth:\s*'78%'/)
  })

  it('ningún mensaje lleva el signo ni «Tú», ni sangría para ellos', () => {
    expect(mensaje).not.toContain('src={isotipo}')
    expect(mensaje).not.toMatch(/>\s*Tú\s*</)
    expect(mensaje).not.toMatch(/paddingLeft/)
  })

  it('la letra de los mensajes sale de la maqueta, en el chat y en la conversación compartida', () => {
    expect(mensaje).toContain('...LETRA_MENSAJE')
    expect(app).not.toMatch(/fontSize:\s*'\.92rem',\s*lineHeight:\s*1\.65/)
  })

  it('la conversación compartida usa la misma maqueta: sin signo, sin tope del 80 %, misma columna', () => {
    const inicio = app.indexOf('if (shareToken) {')
    // El fin se ancla en CÓDIGO (la barra para seguir la conversación): codigoDesnudo quita los comentarios.
    const fin = app.indexOf('paddingBottom:16, paddingTop:10', inicio)
    expect(inicio).toBeGreaterThan(-1)
    expect(fin).toBeGreaterThan(inicio)
    const visor = app.slice(inicio, fin)
    expect(visor).toMatch(/maquetaMensaje\(\{\s*isUser:\s*esTuyo\s*\}\)/)
    expect(visor).toContain('...LETRA_MENSAJE')
    expect(visor).toContain('maxWidth:ANCHO_COLUMNA_PC + 48')
    expect(visor).not.toContain("maxWidth:'80%'")
    expect(visor.match(/<img src=\{isotipo\}/g)).toBeNull()
  })

  it('la lista de mensajes y el campo de escribir comparten la columna', () => {
    expect(app).toContain("padding:`20px ${rellenoColumna({ enTelefono: isMobile })}`")
    expect(app).toContain("padding:`14px ${rellenoColumna({ enTelefono: isMobile })} 18px`")
  })
})
