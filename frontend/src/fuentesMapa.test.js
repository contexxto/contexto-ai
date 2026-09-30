/**
 * MAP-SOURCE-BOUNDARY — lo que los mapas dicen de sus fuentes, y lo que ya no piden.
 *
 * El contenido de Google Places/Routes/Geocoding no puede mostrarse sobre un mapa que no es
 * de Google, y los cinco montajes de mapa son MapLibre + CARTO. Esta guarda falla si:
 *   · el pie de AURA o el título de un pin vuelven a atribuir los lugares a Google;
 *   · AURA o el Mapa Vivo vuelven a pedir `/rutas` (líneas de Google Routes);
 *   · el mensaje del mapa conversacional se pinta sin escapar (trae nombres de terceros).
 *
 * Es un barrido de fuente más pruebas de las funciones puras: no monta MapLibre.
 */

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

import { LEYENDA_PINES, escaparHtml, mensajeMapaHtml, tituloPoi } from './fuentesMapa'

const SRC = path.dirname(fileURLToPath(import.meta.url))
const MAPAS = ['AuraSingleMap.jsx', 'MapView.jsx', 'MapSeed.jsx', 'CompararMap.jsx']

// Quita comentarios (`/* … */` y `// …` que no sean parte de una URL): los comentarios
// pueden NOMBRAR a Google para explicar el corte; lo que no puede es el texto que se pinta.
function sinComentarios(txt) {
  return txt
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .split(/\r?\n/)   // el checkout de Windows trae CRLF, y `.` no casa con `\r`
    .map((l) => l.replace(/(^|[^:'"`])\/\/.*$/, '$1'))
    .join('\n')
}

const fuente = (f) => sinComentarios(fs.readFileSync(path.join(SRC, f), 'utf8'))

describe('las leyendas no atribuyen a Google lo que se pinta', () => {
  it('el pie de AURA nombra la capa propia y la estimación en recta', () => {
    expect(LEYENDA_PINES).toContain('capa propia')
    expect(LEYENDA_PINES).toContain('OpenStreetMap')
    expect(LEYENDA_PINES).toContain('Overture Maps')
    expect(LEYENDA_PINES).toMatch(/línea recta/)
    expect(LEYENDA_PINES).not.toMatch(/google/i)
  })

  it('el título de un pin dice la distancia recta y no nombra a Google', () => {
    const t = tituloPoi({ nombre: 'Farmacia Ñandú', distancia_m: 240 })
    expect(t).toBe('Farmacia Ñandú · a ~240 m en línea recta')
    expect(t).not.toMatch(/google/i)
    expect(tituloPoi({ nombre: 'Sin distancia' })).toBe('Sin distancia')
    expect(tituloPoi(null)).toBe('')
  })

  it.each(MAPAS)('%s no pinta «según Google» ni «Google Routes/Maps»', (f) => {
    const txt = fuente(f)
    expect(txt).not.toMatch(/seg[uú]n Google/i)
    expect(txt).not.toMatch(/Google Routes/)
    expect(txt).not.toMatch(/Google Maps activo/)
    expect(txt).not.toMatch(/Pines según/)
  })

  it('la guarda de fuente SÍ ve el texto viejo (mitad negativa)', () => {
    const viejo = "el.title = `${p.nombre} (según Google Maps)`\n" +
      "<b>Google Routes</b> · Pines según Google Maps"
    expect(sinComentarios(viejo)).toMatch(/seg[uú]n Google/i)
    expect(sinComentarios(viejo)).toMatch(/Google Routes/)
    // …y los comentarios no cuentan:
    expect(sinComentarios('// salían de Google Routes')).not.toMatch(/Google Routes/)
  })
})

describe('nadie vuelve a pedir líneas de ruta', () => {
  it.each(['AuraSingleMap.jsx', 'MapView.jsx'])('%s no llama a /rutas', (f) => {
    expect(fuente(f)).not.toMatch(/\/rutas[`'"]/)
  })

  it('la mitad negativa ve la llamada vieja', () => {
    const viejo = "axios.get(`${API_BASE}/api/v1/assets/${activoId}/rutas`, { headers })"
    expect(sinComentarios(viejo)).toMatch(/\/rutas[`'"]/)
  })
})

describe('el mensaje del mapa se escapa antes del marcado', () => {
  it('un nombre de lugar con HTML llega inerte', () => {
    const html = mensajeMapaHtml('**Lo que tienes cerca:** 💊 <img src=x onerror=alert(1)> (95 m).')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;')
    expect(html).toContain('<b>Lo que tienes cerca:</b>')
  })

  it('negrita e itálica siguen funcionando', () => {
    expect(mensajeMapaHtml('**A** y *b*')).toBe('<b>A</b> y <i>b</i>')
  })

  it('el marcado no se puede usar para inyectar atributos', () => {
    const html = mensajeMapaHtml('**" onmouseover="alert(1)**')
    expect(html).toBe('<b>&quot; onmouseover=&quot;alert(1)</b>')
  })

  it('escaparHtml cubre los cinco caracteres', () => {
    expect(escaparHtml(`&<>"'`)).toBe('&amp;&lt;&gt;&quot;&#39;')
    expect(escaparHtml(null)).toBe('')
  })

  it('MapView pinta el mensaje SOLO a través de mensajeMapaHtml', () => {
    const txt = fuente('MapView.jsx')
    const sinks = txt.match(/dangerouslySetInnerHTML=\{\{[^}]*\}\}/g) || []
    expect(sinks.length).toBeGreaterThan(0)
    for (const s of sinks) expect(s).toMatch(/__html:\s*mensajeMapaHtml\(/)
  })
})
