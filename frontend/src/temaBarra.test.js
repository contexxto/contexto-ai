/**
 * La barra del sistema (theme-color) sigue el tema de la APP.
 *
 * El defecto heredado: `<meta name="theme-color" content="#1C1C1C">` estaba fijo, así que en
 * tema claro el teléfono pintaba la barra negra encima de una app blanca.
 *
 * El arreglo evidente es el equivocado. `<meta name="theme-color"
 * media="(prefers-color-scheme: light)">` obedece al SISTEMA OPERATIVO, y el tema de Contexto
 * no vive ahí: vive en `localStorage` (`theme.js`), que es lo único que lee el conmutador del
 * Sidebar. Con el teléfono en oscuro y la app en claro, la variante declarativa dejaría la
 * barra negra otra vez. Por eso el color se escribe desde JS, en los dos sitios que deciden
 * el tema: el script anti-flash de `index.html` (primer pintado) y `applyTheme` (conmutación).
 *
 * Lo que este archivo vigila es la duplicación que eso obliga: el mismo par de colores vive
 * en `index.css` (los tokens `--bg`), en `index.html` y en `theme.js`. Cambiar el token y
 * olvidar los otros dos no rompe nada a la vista — simplemente la barra deja de pegar con el
 * fondo, que es exactamente el defecto que se está arreglando.
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { COLOR_BARRA, applyTheme, getTheme, toggleTheme } from './theme'

const SRC = dirname(fileURLToPath(import.meta.url))
const css = readFileSync(join(SRC, 'index.css'), 'utf8')
const html = readFileSync(join(SRC, '..', 'index.html'), 'utf8')

/** El `--bg` que declara un bloque de index.css, en mayúsculas y sin espacios. */
function fondoDe(selector) {
  const i = css.indexOf(selector)
  expect(i, `no existe el bloque ${selector} en index.css`).toBeGreaterThan(-1)
  const bloque = css.slice(i, css.indexOf('}', i))
  const m = bloque.match(/--bg:\s*(#[0-9a-fA-F]{3,8})/)
  expect(m, `el bloque ${selector} ya no declara --bg`).not.toBeNull()
  return m[1].toUpperCase()
}

describe('el color de la barra del sistema no se separa de los tokens', () => {
  const fondoOscuro = fondoDe(':root {')
  const fondoClaro = fondoDe('html[data-theme="light"] {')

  it('los dos fondos de index.css son distintos (si no, no habría nada que vigilar)', () => {
    expect(fondoOscuro).not.toBe(fondoClaro)
  })

  it('theme.js exporta exactamente esos dos fondos', () => {
    expect(COLOR_BARRA.dark.toUpperCase()).toBe(fondoOscuro)
    expect(COLOR_BARRA.light.toUpperCase()).toBe(fondoClaro)
  })

  it('el script anti-flash de index.html usa esos mismos dos fondos', () => {
    // Sin los comentarios: nombrar un color al explicarlo no puede dar verde.
    const script = html
      .slice(html.indexOf('Tema anti-flash'), html.indexOf('Warm-up del backend'))
      .replace(/^\s*\/\/.*$/gm, '')
    expect(script.toUpperCase()).toContain(fondoOscuro)
    expect(script.toUpperCase()).toContain(fondoClaro)
  })
})

describe('el color de la barra lo decide la app, no el sistema operativo', () => {
  it('index.html declara un solo theme-color y sin media=', () => {
    // `media="(prefers-color-scheme: …)"` sería el arreglo equivocado: obedecería al SO y no
    // al conmutador del Sidebar. Se buscan las etiquetas REALES: sin los comentarios, porque
    // esa variante se menciona (a propósito) en la explicación de index.html, y los
    // <script> porque el comentario del anti-flash la nombra también.
    const soloMarcado = html
      .replace(/<!--[\s\S]*?-->/g, '')
      .replace(/<script[\s\S]*?<\/script>/g, '')
    const metas = soloMarcado.match(/<meta[^>]*name="theme-color"[^>]*>/g) || []
    expect(metas.length).toBe(1)
    expect(metas[0]).not.toContain('media=')
  })

  it('el tema no se consulta nunca al sistema operativo', () => {
    // Medido, no leído: con un espía en matchMedia, el módulo entero no lo toca. Un grep de
    // texto aquí sería peor — se pondría rojo por nombrar `prefers-color-scheme` en un
    // comentario, y verde si alguien lo consultara por una vía con otro nombre.
    const llamadas = []
    const originalMM = globalThis.matchMedia
    const originalDoc = globalThis.document
    globalThis.matchMedia = (q) => {
      llamadas.push(q)
      return { matches: true, addEventListener() {}, removeEventListener() {} }
    }
    const meta = { setAttribute() {} }
    globalThis.document = {
      documentElement: { setAttribute() {} },
      querySelector: () => meta,
    }
    try {
      getTheme()
      applyTheme('light')
      applyTheme('dark')
      toggleTheme()
    } finally {
      globalThis.matchMedia = originalMM
      globalThis.document = originalDoc
    }
    expect(llamadas).toEqual([])
  })
})

describe('applyTheme mueve el <meta>, no solo el atributo', () => {
  /** Documento mínimo: solo lo que toca applyTheme. */
  function documentoFalso(metaPresente = true) {
    const meta = { content: null, setAttribute(_, v) { this.content = v } }
    const html = { tema: null, setAttribute(_, v) { this.tema = v } }
    return {
      meta,
      html,
      documentElement: html,
      querySelector: (sel) => (metaPresente && sel === 'meta[name="theme-color"]' ? meta : null),
    }
  }

  const original = globalThis.document
  const con = (doc, fn) => {
    globalThis.document = doc
    try { return fn() } finally { globalThis.document = original }
  }

  it('en claro deja la barra con el fondo claro', () => {
    const doc = documentoFalso()
    con(doc, () => applyTheme('light'))
    expect(doc.html.tema).toBe('light')
    expect(doc.meta.content).toBe(COLOR_BARRA.light)
  })

  it('en oscuro deja la barra con el fondo oscuro', () => {
    const doc = documentoFalso()
    con(doc, () => applyTheme('dark'))
    expect(doc.html.tema).toBe('dark')
    expect(doc.meta.content).toBe(COLOR_BARRA.dark)
  })

  it('cualquier valor raro cae en oscuro, en los dos sitios', () => {
    const doc = documentoFalso()
    con(doc, () => applyTheme(undefined))
    expect(doc.html.tema).toBe('dark')
    expect(doc.meta.content).toBe(COLOR_BARRA.dark)
  })

  it('sin <meta> en el documento no revienta: el atributo igual se aplica', () => {
    const doc = documentoFalso(false)
    con(doc, () => applyTheme('light'))
    expect(doc.html.tema).toBe('light')
  })
})
