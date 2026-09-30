/**
 * MAPLIBRE-COLOR-BOUNDARY — ningún `var(--…)` llega al motor de estilos de MapLibre.
 *
 * MapLibre tiene su propio parser de color y no resuelve variables CSS. Un `var(--teal)` en
 * `paint` hace que `addLayer` rechace la capa: emite un error y no la crea, sin que falle
 * nada más. Así el Mapa Vivo dijo «Catastro · 41 activos» sin dibujar un solo punto desde
 * `aed9015` (2026-08-23).
 *
 * La guarda NO busca texto. Aquella migración ya buscó `var(` dentro de `paint:`; se le
 * escaparon los que llegaban por una constante, un parámetro o un objeto desestructurado.
 * Esta sigue el valor hasta su origen (`flujoMapLibre.js`), en los cuatro montajes de mapa.
 * El DOM (marcadores, JSX, HTML) no entra: ahí `var(--…)` es correcto y se queda.
 */
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { crearAnalizador, leerDe } from './flujoMapLibre'

const SRC = path.dirname(fileURLToPath(import.meta.url))
const MAPAS = ['MapView.jsx', 'AuraSingleMap.jsx', 'CompararMap.jsx', 'MapSeed.jsx']

const { capas, hallazgos } = crearAnalizador(leerDe(SRC)).analizar(MAPAS)

describe('los cuatro mapas no entregan var(--…) a MapLibre', () => {
  it('inventario: la guarda ve cada capa y cada cambio de pintura (no pasa en vacío)', () => {
    // Si se añade o quita una capa, este inventario se actualiza a mano: así nadie agrega una
    // capa sin que la guarda la haya mirado. MapSeed solo usa marcadores DOM.
    expect(capas.map((c) => `${c.archivo} ${c.via} ${c.id}`)).toEqual([
      'MapView.jsx addLayer `${id}-glow`',              // agregarRutaAnimada
      'MapView.jsx addLayer id',
      'MapView.jsx addLayer `${id}-flow`',
      'MapView.jsx setPaintProperty `${id}-glow`',
      'MapView.jsx setPaintProperty `${id}-glow`',
      'MapView.jsx setPaintProperty `${id}-flow`',
      'MapView.jsx addLayer `${id}-fill`',              // isócronas de ejecutarAcciones
      'MapView.jsx addLayer `${id}-line`',
      "MapView.jsx addLayer 'activos-glow'",
      "MapView.jsx addLayer 'activos-dot'",
      'AuraSingleMap.jsx addLayer `${id}-fill`',
      'AuraSingleMap.jsx addLayer `${id}-line`',
      'CompararMap.jsx addLayer `${id}-fill`',
      'CompararMap.jsx addLayer `${id}-line`',
    ])
  })

  it('ningún valor de paint/layout puede recibir var(--…), ni un color de origen no demostrable', () => {
    expect(hallazgos).toEqual([])
  })
})

// ── mitad negativa: la guarda muerde por cada camino por el que el defecto llegó ──────────

const analizar = (fuentes, archivo = 'M.jsx') =>
  crearAnalizador((n) => fuentes[n] ?? null).analizar([archivo]).hallazgos

const capa = (paint) => `map.addLayer({ id: 'x', type: 'circle', source: 's', paint: ${paint} })`

describe('la guarda ve var(--…) por cada camino', () => {
  it('literal dentro de paint', () => {
    const h = analizar({ 'M.jsx': `export function f(map) { ${capa("{ 'circle-color': 'var(--teal)' }")} }` })
    expect(h.join('\n')).toMatch(/paint\.circle-color ← «var\(--teal\)»/)
  })

  it('constante de módulo elegida por un ternario (RUIDO_COLOR / ENCAJE_COLOR)', () => {
    const h = analizar({ 'M.jsx': `
      const RUIDO = ['match', ['get', 'r'], 'BAJO', 'var(--teal)', '#969CA6']
      const ENCAJE = ['interpolate', ['linear'], ['get', 'e'], 0, '#3A8F89', 100, '#5EEAD4']
      export function f(map, modo) { const COLOR = modo ? ENCAJE : RUIDO; ${capa("{ 'circle-color': COLOR }")} }` })
    expect(h).toHaveLength(1)
    expect(h[0]).toMatch(/«var\(--teal\)» \(en M\.jsx:2 /)
  })

  it('parámetro de una función con nombre, por el respaldo de la llamada (agregarRutaAnimada)', () => {
    const h = analizar({ 'M.jsx': `
      function ruta(map, id, color) { map.addLayer({ id, type: 'line', source: id, paint: { 'line-color': color } }) }
      export function g(map) { ruta(map, 'r', 'var(--teal-bright)') }` })
    expect(h.join('\n')).toMatch(/paint\.line-color ← «var\(--teal-bright\)»/)
  })

  it('valor por defecto de un parámetro', () => {
    const h = analizar({ 'M.jsx': `
      function ruta(map, color = 'var(--teal)') { map.addLayer({ id: 'r', type: 'line', source: 'r', paint: { 'line-color': color } }) }
      export function g(map) { ruta(map) }` })
    expect(h.join('\n')).toMatch(/«var\(--teal\)»/)
  })

  it('constante local dentro de un callback (isócronas)', () => {
    const h = analizar({ 'M.jsx': `
      export function h(map, contornos) {
        contornos.forEach((c) => {
          const col = c.minutos <= 15 ? 'var(--teal-bright)' : '#2DBDB6'
          map.addLayer({ id: 'i', type: 'fill', source: 'i', paint: { 'fill-color': col } })
        })
      }` })
    expect(h.join('\n')).toMatch(/fill-color ← «var\(--teal-bright\)»/)
  })

  it('elemento desestructurado de un forEach (CompararMap: hue.accent)', () => {
    const h = analizar({ 'M.jsx': `
      const HUE_A = { accent: 'var(--teal-bright)' }
      const HUE_B = { accent: '#E8B84B' }
      export function k(map) {
        const capas = [{ hue: HUE_A, key: 'a' }, { hue: HUE_B, key: 'b' }]
        capas.forEach(({ hue, key }) => {
          map.addLayer({ id: key, type: 'line', source: key, paint: { 'line-color': hue.accent } })
        })
      }` })
    expect(h).toHaveLength(1)
    expect(h[0]).toMatch(/«var\(--teal-bright\)» \(en M\.jsx:2 /)
  })

  it('constante importada de otro módulo', () => {
    const h = analizar({
      'paleta.js': "export const P = { teal: 'var(--teal)' }",
      'M.jsx': `import { P } from './paleta'
        export function f(map) { ${capa("{ 'circle-color': P.teal }")} }`,
    })
    expect(h.join('\n')).toMatch(/«var\(--teal\)» \(en paleta\.js:1 /)
  })

  it('lo que devuelve una función importada, pasado como parámetro (intentHue → pintarAura)', () => {
    const h = analizar({
      'hue.js': `const CALIDO = { accent: 'var(--warm)' }
        export function tono(t) { if (t) return CALIDO; return { accent: '#ffffff' } }`,
      'M.jsx': `import { tono } from './hue'
        function pintar(map, hue) { ${capa("{ 'circle-color': hue.accent }")} }
        export function z(map, t) { const hue = tono(t); pintar(map, hue) }`,
    })
    expect(h).toHaveLength(1)
    expect(h[0]).toMatch(/«var\(--warm\)» \(en hue\.js:1 /)
  })

  it('let reasignado', () => {
    const h = analizar({ 'M.jsx': `export function f(map, x) {
      let col = '#2DBDB6'
      if (x) col = 'var(--teal)'
      ${capa("{ 'circle-color': col }")} }` })
    expect(h.join('\n')).toMatch(/«var\(--teal\)»/)
  })

  it('plantilla que arma el var(', () => {
    const h = analizar({ 'M.jsx': `export function f(map, t) { ${capa("{ 'circle-color': `var(--${t})` }")} }` })
    expect(h.join('\n')).toMatch(/plantilla con var\(/)
  })

  it('setPaintProperty', () => {
    const h = analizar({ 'M.jsx': "export function f(map) { map.setPaintProperty('a', 'line-color', 'var(--teal)') }" })
    expect(h.join('\n')).toMatch(/\['a'\] 'line-color' ← «var\(--teal\)»/)
  })

  it('un color que viene de datos sin pasar por la frontera: origen no demostrable', () => {
    const h = analizar({ 'M.jsx': `
      function ruta(map, color) { map.addLayer({ id: 'r', type: 'line', source: 'r', paint: { 'line-color': color } }) }
      export function d(map, acciones) { acciones.forEach((a) => ruta(map, a.color)) }` })
    expect(h.join('\n')).toMatch(/line-color ← origen no demostrable/)
  })

  it('la frontera colorMapa se audita por su respaldo', () => {
    const conRespaldoVar = analizar({ 'M.jsx': `import { colorMapa } from './mapaColores'
      function ruta(map, color) { map.addLayer({ id: 'r', type: 'line', source: 'r', paint: { 'line-color': color } }) }
      export function d(map, acciones) { acciones.forEach((a) => ruta(map, colorMapa(a.color, 'var(--teal-bright)'))) }` })
    expect(conRespaldoVar.join('\n')).toMatch(/«var\(--teal-bright\)»/)
  })

  it('una función local que se llama colorMapa NO es la frontera', () => {
    const h = analizar({ 'M.jsx': `
      function colorMapa(v, r) { return v || r }
      function ruta(map, color) { map.addLayer({ id: 'r', type: 'line', source: 'r', paint: { 'line-color': color } }) }
      export function d(map, acciones) { acciones.forEach((a) => ruta(map, colorMapa(a.color, '#5EEAD4'))) }` })
    expect(h.join('\n')).toMatch(/origen no demostrable/)
  })

  it('un paint que no es un objeto demostrable', () => {
    const h = analizar({ 'M.jsx': `export function f(map) { ${capa('construir()')} }` })
    expect(h.join('\n')).toMatch(/paint no es un objeto demostrable/)
  })

  it('un fichero que no parsea rompe la guarda en vez de dejarla en verde', () => {
    expect(() => analizar({ 'M.jsx': 'export function f( {' })).toThrow(/no parsea/)
  })
})

describe('…y no inventa hallazgos (mitad positiva)', () => {
  it('las mismas formas con literales y con la frontera quedan limpias', () => {
    const h = analizar({
      'mapaColores.js': `export const MAP_COLOR = { teal: '#2DBDB6', tealBright: '#5EEAD4' }
        export function colorMapa(valor, respaldo) { return respaldo }`,
      'hue.js': "export function tono() { return { accent: '#E8B84B' } }",
      'M.jsx': `import { MAP_COLOR, colorMapa } from './mapaColores'
        import { tono } from './hue'
        const RUIDO = ['match', ['get', 'r'], 'BAJO', MAP_COLOR.teal, '#969CA6']
        const HUE_A = { accent: 'var(--teal-bright)', mapa: MAP_COLOR.tealBright }
        function ruta(map, id, color) {
          map.addLayer({ id, type: 'line', source: id, paint: { 'line-color': color, 'line-opacity': 0.9 } })
          map.setPaintProperty(id, 'line-opacity', 0.16 + Math.sin(Date.now()) * 0.18)
        }
        function pintar(map, hue) { map.addLayer({ id: 'p', type: 'fill', source: 'p', paint: { 'fill-color': hue.accent } }) }
        export function todo(map, acciones, modo) {
          const COLOR = modo ? RUIDO : '#6B6878'
          map.addLayer({ id: 'a', type: 'circle', source: 'a', paint: { 'circle-color': COLOR, 'circle-radius': modo ? 8 : 7 } })
          acciones.forEach((a) => ruta(map, 'r', colorMapa(a.color, MAP_COLOR.tealBright)))
          ;[{ hue: HUE_A, key: 'a' }].forEach(({ hue, key }) =>
            map.addLayer({ id: key, type: 'line', source: key, paint: { 'line-color': hue.mapa } }))
          pintar(map, tono())
        }`,
    })
    expect(h).toEqual([])
  })
})
