/**
 * MAPA-VIVO-COLORES — nada de lo que se le entrega a MapLibre lleva `var(--…)`.
 *
 * MapLibre GL valida el estilo con su propio parser: `var(--teal)` no es un color para él, y
 * addLayer RECHAZA LA CAPA ENTERA (un error en consola, nada en el mapa). aed9015 cambió hex por
 * tokens en constantes que llegaban a `circle-color` por referencia, y en producción el Mapa Vivo
 * decía «41 activos» sin dibujar un solo punto. El barrido de entonces buscó `var(` DENTRO de
 * `paint:` y se le escaparon los caminos donde el color viaja por una constante, un parámetro o
 * un objeto `hue`.
 *
 * Por eso esta prueba no lee el texto: MONTA los componentes de mapa, con MapLibre simulado, y
 * captura lo que reciben addLayer / setPaintProperty / setLayoutProperty / setFilter. Recorre
 * cada camino que hoy pinta capas:
 *   · el Mapa Vivo coloreado por ruido (lo que ve quien lo abre) y por encaje;
 *   · las isócronas de los chips «15 / 30 min a pie»;
 *   · las rutas animadas del comando y del recorrido, sin color del backend (el color por defecto);
 *   · las isócronas de AURA-SINGLE y de COMPARAR.
 * Y lleva inventario: todo fichero que importe maplibre-gl tiene que estar montado aquí o declarar
 * que solo usa marcadores DOM. Un mapa nuevo rompe la prueba hasta que alguien lo añada.
 *
 * No hay jsdom en este repo. Los componentes se ejecutan como funciones con un React mínimo
 * (useState / useEffect / useRef / useMemo) que vuelve a renderizar cuando cambia el estado y
 * conecta los `ref`. No pinta nada: solo deja correr los efectos, que es donde viven las llamadas
 * a MapLibre.
 *
 * Los literales viven en coloresMapa.js. La última parte comprueba que siguen valiendo lo mismo
 * que los tokens de index.css.
 */

import { readFileSync, readdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

import { validateStyleMin } from '@maplibre/maplibre-gl-style-spec'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import AuraSingleMap from './AuraSingleMap'
import CompararMap from './CompararMap'
import MapView from './MapView'
import { codigoDesnudo } from './codigoDesnudo'
import { MAPA_CORAL, MAPA_TEAL, MAPA_TEAL_BRIGHT, colorMapa } from './coloresMapa'

// ── MapLibre simulado: registra todo lo que toca el estilo ─────────────────────────────────
const sim = vi.hoisted(() => {
  const llamadas = []   // { api, id, valor } — lo que MapLibre validaría
  const mapas = []
  class Mapa {
    constructor(opciones) {
      this.opciones = opciones
      this.oyentes = {}
      this.capas = new Set()
      this.fuentes = new Map()
      mapas.push(this)
    }
    on(tipo, capaOFn, fn) { (this.oyentes[tipo] ||= []).push(fn || capaOFn); return this }
    once(tipo, fn) { return this.on(tipo, fn) }
    async disparar(tipo) { for (const fn of this.oyentes[tipo] || []) await fn({}) }
    addSource(id, fuente) { this.fuentes.set(id, { ...fuente, setData() {} }) }
    getSource(id) { return this.fuentes.get(id) }
    removeSource(id) { this.fuentes.delete(id) }
    addLayer(capa) {
      llamadas.push({ api: 'addLayer', id: capa.id, tipo: capa.type, valor: { paint: capa.paint, layout: capa.layout, filter: capa.filter } })
      this.capas.add(capa.id)
    }
    getLayer(id) { return this.capas.has(id) ? { id } : undefined }
    removeLayer(id) { this.capas.delete(id) }
    setPaintProperty(id, prop, valor) { llamadas.push({ api: 'setPaintProperty', id, valor: { [prop]: valor } }) }
    setLayoutProperty(id, prop, valor) { llamadas.push({ api: 'setLayoutProperty', id, valor: { [prop]: valor } }) }
    setFilter(id, valor) { llamadas.push({ api: 'setFilter', id, valor }) }
    isStyleLoaded() { return true }
    getCenter() { return { lat: -0.1807, lng: -78.4825 } }
    getCanvas() { return { style: {} } }
    resize() {}
    remove() {}
    fitBounds() {}
    flyTo() {}
    jumpTo() {}
  }
  class Encadenable {
    setLngLat() { return this }
    setHTML() { return this }
    addTo() { return this }
    remove() { return this }
  }
  class LngLatBounds {
    constructor() { this.n = 0 }
    extend() { this.n++; return this }
    isEmpty() { return this.n === 0 }
  }
  return { llamadas, mapas, maplibre: { Map: Mapa, Popup: Encadenable, Marker: Encadenable, LngLatBounds } }
})
vi.mock('maplibre-gl', () => ({ default: sim.maplibre }))

// ── React mínimo: suficiente para que corran los efectos de un componente ──────────────────
const mini = vi.hoisted(() => {
  let actual = null
  const cambian = (antes, ahora) =>
    !antes || !ahora || antes.length !== ahora.length || ahora.some((d, i) => !Object.is(d, antes[i]))
  const ranura = () => actual.i++
  const useRef = (inicial) => (actual.ranuras[ranura()] ??= { current: inicial })
  function useState(inicial) {
    const inst = actual
    const h = (inst.ranuras[ranura()] ??= { v: typeof inicial === 'function' ? inicial() : inicial })
    const fijar = (nuevo) => {
      const v = typeof nuevo === 'function' ? nuevo(h.v) : nuevo
      if (!Object.is(v, h.v)) { h.v = v; inst.agendar() }
    }
    return [h.v, fijar]
  }
  function useMemo(fn, deps) {
    const h = (actual.ranuras[ranura()] ??= {})
    if (!('v' in h) || cambian(h.deps, deps)) { h.v = fn(); h.deps = deps }
    return h.v
  }
  function useCallback(fn, deps) {
    const h = (actual.ranuras[ranura()] ??= {})
    if (!('v' in h) || cambian(h.deps, deps)) { h.v = fn; h.deps = deps }
    return h.v
  }
  function useEffect(fn, deps) {
    const h = (actual.ranuras[ranura()] ??= {})
    if (!cambian(h.deps, deps)) return
    h.deps = deps
    actual.efectos.push(() => { h.limpiar?.(); const r = fn(); h.limpiar = typeof r === 'function' ? r : null })
  }
  // React conecta los `ref` antes de correr los efectos; los componentes miran `ref.current`.
  function conectarRefs(nodo) {
    if (Array.isArray(nodo)) { nodo.forEach(conectarRefs); return }
    if (!nodo || typeof nodo !== 'object' || !nodo.props) return
    const { ref, children } = nodo.props
    if (ref && typeof ref === 'object' && 'current' in ref && ref.current == null) ref.current = { style: {} }
    conectarRefs(children)
  }
  function montar(Componente, props = {}) {
    const inst = { ranuras: [], i: 0, efectos: [], arbol: null, vivo: true, pendiente: false }
    inst.render = () => {
      if (!inst.vivo) return
      inst.i = 0
      inst.efectos = []
      actual = inst
      try { inst.arbol = Componente(props) } finally { actual = null }
      conectarRefs(inst.arbol)
      for (const fx of inst.efectos) fx()
    }
    inst.agendar = () => {
      if (inst.pendiente) return
      inst.pendiente = true
      queueMicrotask(() => { inst.pendiente = false; inst.render() })
    }
    inst.desmontar = () => { inst.vivo = false; inst.ranuras.forEach((h) => h?.limpiar?.()) }
    inst.render()
    return inst
  }
  return { montar, hooks: { useRef, useState, useMemo, useCallback, useEffect } }
})
vi.mock('react', async (importOriginal) => ({ ...(await importOriginal()), ...mini.hooks }))

// ── El backend, simulado ───────────────────────────────────────────────────────────────────
vi.mock('./api', () => ({ API_BASE: '', apiHeaders: () => ({}) }))
const axiosGet = vi.hoisted(() => ({ fn: null }))
vi.mock('axios', () => ({ default: { get: (...a) => axiosGet.fn(...a) } }))

const CUADRO = (lon, lat, d = 0.004) => ({
  type: 'Polygon',
  coordinates: [[[lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d], [lon - d, lat + d], [lon - d, lat - d]]],
})
// Un activo por nivel de ruido: cada rama del `match` tiene quien la use.
const GEOJSON = {
  type: 'FeatureCollection',
  features: ['BAJO', 'MEDIO', 'ALTO'].map((ruido, i) => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [-78.48 + i * 0.01, -0.18] },
    properties: { id: 101 + i, direccion: `Activo ${i}`, ruido },
  })),
}
const ISOCRONAS = [{ minutos: 15, geometry: CUADRO(-78.48, -0.18) }, { minutos: 30, geometry: CUADRO(-78.48, -0.18, 0.008) }]
const AURA = { lat: -0.18, lon: -78.48, pois: [], isocronas: ISOCRONAS }

let respuestaComando = null
const rafs = []

beforeEach(() => {
  sim.llamadas.length = 0
  sim.mapas.length = 0
  rafs.length = 0
  respuestaComando = null
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  vi.stubGlobal('fetch', vi.fn(async (url) => {
    const cuerpo = String(url).endsWith('/api/v1/assets/geojson') ? GEOJSON
      : String(url).endsWith('/api/v1/assets/mapa/comando') ? respuestaComando
        : null
    return { ok: cuerpo != null, status: cuerpo != null ? 200 : 404, json: async () => cuerpo }
  }))
  axiosGet.fn = async () => ({ data: AURA })
  const almacen = new Map()
  vi.stubGlobal('localStorage', {
    getItem: (k) => almacen.get(k) ?? null, setItem: (k, v) => almacen.set(k, String(v)), removeItem: (k) => almacen.delete(k),
  })
  vi.stubGlobal('document', { createElement: () => ({ style: {}, animate() {} }) })
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} })
  vi.stubGlobal('requestAnimationFrame', (cb) => rafs.push(cb))
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

// ── Utilidades ─────────────────────────────────────────────────────────────────────────────
const drenar = async () => { for (let i = 0; i < 25; i++) await Promise.resolve() }
const avanzar = async (ms) => { await drenar(); vi.advanceTimersByTime(ms); await drenar() }

/** CSS que solo resuelve el navegador. MapLibre no entiende ninguna de estas formas. */
const SOLO_NAVEGADOR = /var\(|color-mix\(|calc\(|env\(|currentcolor/i

function cadenas(v, ruta = '') {
  if (typeof v === 'string') return [[ruta, v]]
  if (Array.isArray(v)) return v.flatMap((x, i) => cadenas(x, `${ruta}[${i}]`))
  if (v && typeof v === 'object') return Object.entries(v).flatMap(([k, x]) => cadenas(x, ruta ? `${ruta}.${k}` : k))
  return []
}
/** Cada valor con CSS de navegador que llegó a MapLibre, con su capa y su ruta dentro del estilo. */
const infracciones = () => sim.llamadas.flatMap(({ api, id, valor }) =>
  cadenas(valor).filter(([, s]) => SOLO_NAVEGADOR.test(s)).map(([ruta, s]) => `${api}(${id}).${ruta} = '${s}'`))
/**
 * Lo que diría el validador del PROPIO MapLibre (@maplibre/maplibre-gl-style-spec: el que en
 * producción rechazó las capas con «Could not parse color from value 'var(--teal)'») sobre todo
 * lo capturado: cada addLayer, y cada setPaintProperty/setLayoutProperty como capa de su tipo.
 */
function erroresMapLibre() {
  const tipos = new Map(sim.llamadas.filter((l) => l.api === 'addLayer').map((l) => [l.id, l.tipo]))
  const layers = sim.llamadas.flatMap((l, i) => {
    const base = { id: `${i}:${l.id}`, source: 's' }
    if (l.api === 'addLayer') {
      const { paint, layout, filter } = l.valor
      return [{ ...base, type: l.tipo, ...(paint && { paint }), ...(layout && { layout }), ...(filter && { filter }) }]
    }
    if (l.api === 'setPaintProperty' && tipos.has(l.id)) return [{ ...base, type: tipos.get(l.id), paint: l.valor }]
    if (l.api === 'setLayoutProperty' && tipos.has(l.id)) return [{ ...base, type: tipos.get(l.id), layout: l.valor }]
    return []
  })
  const s = { type: 'geojson', data: { type: 'FeatureCollection', features: [] } }
  return validateStyleMin({ version: 8, sources: { s }, layers }).map((e) => e.message)
}
const capasAnadidas = () => sim.llamadas.filter((l) => l.api === 'addLayer').map((l) => l.id)

const texto = (n) => (typeof n === 'string' ? n
  : Array.isArray(n) ? n.map(texto).join('')
    : n && n.props ? texto(n.props.children) : '')
function buscar(n, cumple) {
  if (Array.isArray(n)) { for (const x of n) { const r = buscar(x, cumple); if (r) return r } return null }
  if (!n || typeof n !== 'object' || !n.props) return null
  return cumple(n) ? n : buscar(n.props.children, cumple)
}
const boton = (inst, etiqueta) => {
  const b = buscar(inst.arbol, (n) => n.type === 'button' && texto(n).includes(etiqueta))
  if (!b) throw new Error(`no encuentro el botón «${etiqueta}» en el Mapa Vivo`)
  return b
}

async function abrirMapaVivo(props = {}) {
  const inst = mini.montar(MapView, props)
  await sim.mapas.at(-1).disparar('load')
  await drenar()
  return inst
}

// ── El Mapa Vivo ───────────────────────────────────────────────────────────────────────────
describe('Mapa Vivo (MapView): lo que llega a MapLibre', () => {
  it('al abrirlo (color por ruido): las capas de los activos llevan colores que MapLibre entiende', async () => {
    await abrirMapaVivo()
    expect(capasAnadidas()).toEqual(expect.arrayContaining(['activos-glow', 'activos-dot']))
    expect(infracciones()).toEqual([])
    expect(erroresMapLibre()).toEqual([])
  })

  it('coloreado por encaje: ídem', async () => {
    await abrirMapaVivo({ encajeById: { 101: 12, 102: 55, 103: 97 } })
    const glow = sim.llamadas.find((l) => l.id === 'activos-glow')
    expect(glow?.valor.paint['circle-color'][0]).toBe('interpolate')   // de verdad es el modo encaje
    expect(infracciones()).toEqual([])
    expect(erroresMapLibre()).toEqual([])
  })

  it('chip «15 min a pie»: las isócronas de 15 y 30 min', async () => {
    const inst = await abrirMapaVivo()
    sim.llamadas.length = 0
    respuestaComando = { texto: 'Te ilumino…', acciones: [{ tipo: 'isocrona', contornos: ISOCRONAS, centro: [-78.48, -0.18] }] }
    await boton(inst, '15 min a pie').props.onClick()
    await drenar()
    expect(capasAnadidas()).toEqual(['cmd-iso-0-30-fill', 'cmd-iso-0-30-line', 'cmd-iso-0-15-fill', 'cmd-iso-0-15-line'])
    expect(infracciones()).toEqual([])
    expect(erroresMapLibre()).toEqual([])
  })

  it('una ruta del comando SIN color del backend: el color por defecto, y la animación', async () => {
    const inst = await abrirMapaVivo()
    sim.llamadas.length = 0
    respuestaComando = { texto: 'Ruta', acciones: [{ tipo: 'ruta', coords: [[-78.48, -0.18], [-78.47, -0.17]], destino: [-78.47, -0.17] }] }
    await boton(inst, 'Transporte').props.onClick()
    await drenar()
    expect(capasAnadidas()).toEqual(['cmd-ruta-0-glow', 'cmd-ruta-0', 'cmd-ruta-0-flow'])
    rafs.shift()?.(performance.now() + 400)   // un fotograma: respira el glow, corre la estela
    expect(sim.llamadas.some((l) => l.api === 'setPaintProperty')).toBe(true)
    expect(infracciones()).toEqual([])
    expect(erroresMapLibre()).toEqual([])
  })

  it('un recorrido con ruta SIN color: el color por defecto de la escena', async () => {
    const inst = await abrirMapaVivo()
    sim.llamadas.length = 0
    respuestaComando = {
      texto: 'Tour',
      acciones: [{ tipo: 'tour', escenas: [{ centro: [-78.48, -0.18], ruta: { coords: [[-78.48, -0.18], [-78.47, -0.17]] } }] }],
    }
    await boton(inst, 'Recorre esta zona').props.onClick()
    await avanzar(700)   // la escena se ilumina a los 650 ms
    expect(capasAnadidas()).toEqual(['tour-ruta-0-glow', 'tour-ruta-0', 'tour-ruta-0-flow'])
    expect(infracciones()).toEqual([])
    expect(erroresMapLibre()).toEqual([])
  })
})

// ── Los otros mapas que pintan capas ───────────────────────────────────────────────────────
describe('isócronas de AURA-SINGLE y de COMPARAR', () => {
  it('AURA-SINGLE (hue del propósito del inmueble)', async () => {
    mini.montar(AuraSingleMap, { activoId: 'x1', tipoActivo: 'Departamento' })
    await avanzar(80)
    expect(capasAnadidas()).toEqual(['aura-iso-30-fill', 'aura-iso-30-line', 'aura-iso-15-fill', 'aura-iso-15-line'])
    expect(infracciones()).toEqual([])
    expect(erroresMapLibre()).toEqual([])
  })

  it('COMPARAR (A teal, B ámbar)', async () => {
    mini.montar(CompararMap, { ids: ['a1', 'b2'], cards: [] })
    await avanzar(80)
    expect(capasAnadidas()).toEqual([
      'cmp-a-iso-30-fill', 'cmp-a-iso-30-line', 'cmp-a-iso-15-fill', 'cmp-a-iso-15-line',
      'cmp-b-iso-30-fill', 'cmp-b-iso-30-line', 'cmp-b-iso-15-fill', 'cmp-b-iso-15-line',
    ])
    expect(infracciones()).toEqual([])
    expect(erroresMapLibre()).toEqual([])
  })
})

// ── Colores que vienen del backend: la frontera colorMapa ─────────────────────────────────
describe('colores del backend: solo pasan si MapLibre los entiende (colorMapa)', () => {
  const RUTA = [[-78.48, -0.18], [-78.47, -0.17]]
  const lineaDe = (id) => sim.llamadas.find((l) => l.api === 'addLayer' && l.id === id)?.valor.paint['line-color']

  it.each([
    ['#5E9BE0', '#5E9BE0'],            // un hex del backend pasa tal cual
    ['var(--teal)', MAPA_TEAL_BRIGHT],  // un token → respaldo literal
    ['', MAPA_TEAL_BRIGHT],
    [null, MAPA_TEAL_BRIGHT],
  ])('ruta del comando con color del backend %j → %s', async (delBackend, esperado) => {
    const inst = await abrirMapaVivo()
    sim.llamadas.length = 0
    respuestaComando = { texto: 'Ruta', acciones: [{ tipo: 'ruta', coords: RUTA, color: delBackend }] }
    await boton(inst, 'Transporte').props.onClick()
    await drenar()
    expect(lineaDe('cmd-ruta-0-glow')).toBe(esperado)
    expect(lineaDe('cmd-ruta-0')).toBe(esperado)
    expect(infracciones()).toEqual([])
    expect(erroresMapLibre()).toEqual([])
  })

  it.each([['#5E9BE0', '#5E9BE0'], ['var(--teal)', MAPA_TEAL_BRIGHT]])(
    'ruta de un recorrido con color del backend %j → %s', async (delBackend, esperado) => {
      const inst = await abrirMapaVivo()
      sim.llamadas.length = 0
      respuestaComando = { texto: 'Tour', acciones: [{ tipo: 'tour', escenas: [{ centro: [-78.48, -0.18], ruta: { coords: RUTA, color: delBackend } }] }] }
      await boton(inst, 'Recorre esta zona').props.onClick()
      await avanzar(700)
      expect(lineaDe('tour-ruta-0')).toBe(esperado)
      expect(infracciones()).toEqual([])
      expect(erroresMapLibre()).toEqual([])
    })

  it('colorMapa: qué deja pasar y qué cae al respaldo', () => {
    for (const c of ['#5E9BE0', '#abc', '#AABBCCDD', 'rgba(94,234,212,.5)', 'hsl(120deg, 50%, 50%)']) {
      expect(colorMapa(c, MAPA_TEAL)).toBe(c)
    }
    expect(colorMapa('  #2DBDB6 ', MAPA_CORAL)).toBe('#2DBDB6')
    for (const v of ['var(--teal)', ' var(--teal-bright) ', 'rgb(var(--x))', 'teal', 'currentColor', '#12345', '', null, undefined, 42, {}]) {
      expect(colorMapa(v, MAPA_TEAL)).toBe(MAPA_TEAL)
    }
  })
})

// ── El popup de un activo es DOM: sus colores viven en index.css, con tokens ──────────────
describe('popup de un activo (ctx-popup): legible sobre el mapa oscuro', () => {
  const SRC = dirname(fileURLToPath(import.meta.url))
  const css = readFileSync(join(SRC, 'index.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')
  // Cuerpos de las reglas cuyo selector (o uno de su grupo) es exactamente `sel`.
  const reglas = (sel) => [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)]
    .filter(([, sels]) => sels.split(',').some((x) => x.trim().replace(/\s+/g, ' ') === sel))
    .map(([, , cuerpo]) => cuerpo)
  const declara = (sel, prop) => reglas(sel).some((c) => new RegExp(`(^|[;\\s])${prop}\\s*:`).test(c))

  it('MapView sigue creando el popup con la clase ctx-popup', () => {
    expect(codigoDesnudo(readFileSync(join(SRC, 'MapView.jsx'), 'utf8'), 'MapView.jsx')).toMatch(/className:\s*'ctx-popup'/)
  })

  it('fondo y texto propios: sin ellos MapLibre pone fondo blanco y el contenido, claro, no se lee', () => {
    expect(declara('.ctx-popup .maplibregl-popup-content', 'background')).toBe(true)
    expect(declara('.ctx-popup .maplibregl-popup-content', 'color')).toBe(true)
  })

  it.each(['top', 'bottom', 'left', 'right'])('el pico toma el fondo del popup con el ancla %s', (ancla) => {
    const lado = { top: 'bottom', bottom: 'top', left: 'right', right: 'left' }[ancla]
    expect(declara(`.ctx-popup.maplibregl-popup-anchor-${ancla} .maplibregl-popup-tip`, `border-${lado}-color`)).toBe(true)
  })

  it('el botón cerrar tiene color propio', () => {
    expect(declara('.ctx-popup .maplibregl-popup-close-button', 'color')).toBe(true)
  })
})

// ── Inventario: ningún mapa queda fuera ────────────────────────────────────────────────────
describe('inventario de montajes de MapLibre', () => {
  const SRC = dirname(fileURLToPath(import.meta.url))
  const MONTADOS_AQUI = ['AuraSingleMap.jsx', 'CompararMap.jsx', 'MapView.jsx']
  const SOLO_MARCADORES_DOM = ['MapSeed.jsx']

  it('todo fichero que importa maplibre-gl está montado arriba o declarado como solo-DOM', () => {
    const importan = readdirSync(SRC, { recursive: true })
      .map(String)
      .filter((f) => /\.jsx?$/.test(f) && !/\.test\.jsx?$/.test(f))
      .filter((f) => /from\s+['"]maplibre-gl['"]/.test(codigoDesnudo(readFileSync(join(SRC, f), 'utf8'), f)))
      .map((f) => f.replace(/\\/g, '/'))
      .sort()
    expect(importan).toEqual([...MONTADOS_AQUI, ...SOLO_MARCADORES_DOM].sort())
  })

  it.each(SOLO_MARCADORES_DOM)('%s no toca el estilo del mapa (solo marcadores DOM)', (f) => {
    const codigo = codigoDesnudo(readFileSync(join(SRC, f), 'utf8'), f)
    expect(codigo).not.toMatch(/\.(addLayer|setPaintProperty|setLayoutProperty|setFilter|setStyle)\s*\(/)
  })
})

// ── Los literales siguen siendo los tokens ─────────────────────────────────────────────────
describe('los colores literales del mapa valen lo mismo que los tokens de index.css', () => {
  const SRC = dirname(fileURLToPath(import.meta.url))
  // Sin comentarios: el del tema claro dice «El relleno sigue siendo --teal: ahi no hay…».
  const css = readFileSync(join(SRC, 'index.css'), 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')

  // Una sola definición (en :root). Si un tema la redefine, esta prueba falla a propósito: el
  // mapa es oscuro en los dos temas y alguien tiene que decidir qué valor le corresponde.
  it.each([['--teal', MAPA_TEAL], ['--teal-bright', MAPA_TEAL_BRIGHT], ['--coral', MAPA_CORAL]])('%s', (token, literal) => {
    const definiciones = [...css.matchAll(new RegExp(`${token}\\s*:\\s*([^;]+);`, 'g'))].map((m) => m[1].trim().toLowerCase())
    expect(definiciones).toEqual([literal.toLowerCase()])
  })
})
