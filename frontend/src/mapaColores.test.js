/**
 * MAPLIBRE-COLOR-BOUNDARY — la paleta que va a MapLibre, juzgada por el parser de MapLibre.
 *
 * `@maplibre/maplibre-gl-style-spec` es el validador que trae el propio MapLibre: el mismo que
 * rechazó en producción «Could not parse color from value 'var(--teal)'». Aquí:
 *   · la paleta literal no se separa de los tokens de `index.css`;
 *   · RUIDO_COLOR y ENCAJE_COLOR dan un color REAL para cada inmueble;
 *   · la frontera `colorMapa` nunca deja pasar algo que MapLibre rechace.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { createPropertyExpression, latest, validateStyleMin } from '@maplibre/maplibre-gl-style-spec'
import { describe, expect, it } from 'vitest'

import { ENCAJE_COLOR, MAP_COLOR, RUIDO_COLOR, colorMapa } from './mapaColores'

const SRC = path.dirname(fileURLToPath(import.meta.url))

// Un estilo mínimo con UNA capa: lo que `map.addLayer` valida antes de crearla.
const errores = (tipo, paint) => validateStyleMin({
  version: 8,
  sources: { s: { type: 'geojson', data: { type: 'FeatureCollection', features: [] } } },
  layers: [{ id: 'x', type: tipo, source: 's', paint }],
}).map((e) => e.message)

// Evalúa una expresión de color para un inmueble, con el evaluador de MapLibre.
function colorPara(expr, properties) {
  const r = createPropertyExpression(expr, latest.paint_circle['circle-color'])
  if (r.result !== 'success') throw new Error(r.value.map((e) => e.message).join('; '))
  return r.value.evaluate({ zoom: 14 }, { type: 'Point', properties }).toString()
}

describe('la paleta de MapLibre es la de los tokens', () => {
  // Sin comentarios: index.css NOMBRA tokens al explicar sus variantes, y eso no es definirlos.
  const css = fs.readFileSync(path.join(SRC, 'index.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')
  const TOKEN = { teal: '--teal', tealBright: '--teal-bright', tealDeep: '--teal-deep', coral: '--coral' }

  it.each(Object.entries(TOKEN))('MAP_COLOR.%s = %s en cada bloque de tema', (clave, token) => {
    // Declaración que empieza tras `{`, `;` o espacio; y `--teal\s*:` no casa con `--teal-bright:`.
    const definiciones = [...css.matchAll(new RegExp(`(?:^|[{;\\s])${token}\\s*:\\s*([^;]+);`, 'g'))].map((m) => m[1].trim())
    expect(definiciones.length).toBeGreaterThan(0)
    for (const v of definiciones) expect(v.toUpperCase()).toBe(MAP_COLOR[clave].toUpperCase())
  })

  it('ningún valor de la paleta es un token', () => {
    for (const v of [...Object.values(MAP_COLOR), ...RUIDO_COLOR.flat(), ...ENCAJE_COLOR.flat()]) {
      expect(String(v)).not.toMatch(/var\(/)
    }
  })
})

describe('el validador de MapLibre acepta lo que ahora se le entrega', () => {
  it('activos-glow y activos-dot, en modo ruido y en modo encaje', () => {
    for (const [COLOR, modoEncaje] of [[RUIDO_COLOR, false], [ENCAJE_COLOR, true]]) {
      expect(errores('circle', {
        'circle-radius': modoEncaje ? 18 : 16, 'circle-color': COLOR,
        'circle-opacity': modoEncaje ? 0.22 : 0.12, 'circle-blur': 1,
      })).toEqual([])
      expect(errores('circle', {
        'circle-radius': modoEncaje ? 8 : 7, 'circle-color': COLOR,
        'circle-stroke-width': modoEncaje ? 1.8 : 1.5,
        'circle-stroke-color': modoEncaje ? 'rgba(240,236,230,.55)' : '#0E0D13',
        'circle-opacity': 1,
      })).toEqual([])
    }
  })

  it('isócronas y rutas: cada color de la paleta como relleno y como línea', () => {
    for (const c of Object.values(MAP_COLOR)) {
      expect(errores('fill', { 'fill-color': c, 'fill-opacity': 0.16 })).toEqual([])
      expect(errores('line', { 'line-color': c, 'line-width': 2, 'line-dasharray': [3, 2] })).toEqual([])
    }
  })

  it('mitad negativa: con un token, el validador da el MISMO error que producción', () => {
    const conToken = RUIDO_COLOR.map((v) => (v === MAP_COLOR.teal ? 'var(--teal)' : v))
    expect(errores('circle', { 'circle-color': conToken })).toEqual([
      "layers[0].paint.circle-color[2]: Could not parse color from value 'var(--teal)'",
    ])
    expect(() => colorPara(conToken, { ruido: 'BAJO' })).toThrow("Could not parse color from value 'var(--teal)'")
  })
})

describe('cada inmueble recibe un color real, sin cambiar la semántica', () => {
  // Mismas salidas que antes de aed9015 (cuando eran hex): BAJO teal, ALTO coral, resto gris.
  it('RUIDO_COLOR', () => {
    expect(colorPara(RUIDO_COLOR, { ruido: 'BAJO' })).toBe('rgba(45,189,182,1)')    // #2DBDB6
    expect(colorPara(RUIDO_COLOR, { ruido: 'MEDIO' })).toBe('rgba(229,192,106,1)')  // #E5C06A
    expect(colorPara(RUIDO_COLOR, { ruido: 'ALTO' })).toBe('rgba(224,104,90,1)')    // #E0685A
    expect(colorPara(RUIDO_COLOR, { ruido: null })).toBe('rgba(150,156,166,1)')     // #969CA6
    expect(colorPara(RUIDO_COLOR, {})).toBe('rgba(150,156,166,1)')
  })

  it('ENCAJE_COLOR', () => {
    expect(colorPara(ENCAJE_COLOR, { encaje: null })).toBe('rgba(107,104,120,1)')   // sin dato → #6B6878
    expect(colorPara(ENCAJE_COLOR, { encaje: 0 })).toBe('rgba(58,143,137,1)')       // #3A8F89
    expect(colorPara(ENCAJE_COLOR, { encaje: 50 })).toBe('rgba(45,189,182,1)')      // #2DBDB6
    expect(colorPara(ENCAJE_COLOR, { encaje: 100 })).toBe('rgba(94,234,212,1)')     // #5EEAD4
  })

  it('41 inmuebles de todas las combinaciones: ninguno se queda sin color', () => {
    const ruidos = ['BAJO', 'MEDIO', 'ALTO', null, 'OTRO']
    const encajes = [null, -1, 0, 4, 12, 25, 37, 50, 63, 75, 88, 100]
    const props = Array.from({ length: 41 }, (_, i) => ({ ruido: ruidos[i % ruidos.length], encaje: encajes[i % encajes.length] }))
    for (const p of props) {
      expect(colorPara(RUIDO_COLOR, p)).toMatch(/^rgba\(/)
      expect(colorPara(ENCAJE_COLOR, p)).toMatch(/^rgba\(/)
    }
  })
})

describe('colorMapa: frontera para colores que vienen de datos', () => {
  const RESPALDO = MAP_COLOR.tealBright

  it.each(['#5E9BE0', '#5EEAD4', '#abc', '#AABBCCDD', 'rgba(94,234,212,.5)', 'rgb(1 2 3 / 50%)', 'hsl(120deg, 50%, 50%)'])(
    'deja pasar %s… y MapLibre lo entiende', (c) => {
      expect(colorMapa(c, RESPALDO)).toBe(c)
      expect(errores('line', { 'line-color': colorMapa(c, RESPALDO) })).toEqual([])
    })

  it('recorta espacios', () => {
    expect(colorMapa('  #2DBDB6 ', RESPALDO)).toBe('#2DBDB6')
  })

  it.each([
    'var(--teal)', ' var(--teal-bright) ', 'rgb(var(--x))', 'teal', 'currentColor', 'url(x)',
    '#12345', '#GGGGGG', '', null, undefined, 42, {},
  ])('cae al respaldo con %j', (v) => {
    expect(colorMapa(v, RESPALDO)).toBe(RESPALDO)
  })

  it('los colores que hoy manda el servidor (app/rutas.py) pasan tal cual', () => {
    for (const c of ['#2DBDB6', '#5EEAD4', '#5E9BE0', '#9B8CFF', '#E0685A', '#E5C06A', '#C9C6D6', '#7FB2FF', '#9C99AC']) {
      expect(colorMapa(c, RESPALDO)).toBe(c)
    }
  })
})
