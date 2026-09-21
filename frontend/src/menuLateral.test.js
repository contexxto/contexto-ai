/**
 * La cabecera del menú lateral lleva el lockup de la marca, y no una palabra compuesta.
 *
 * Hasta el 2026-09-21 la cabecera era `sphere.svg` + «Contexto» escrito en la letra de la
 * interfaz (Geist 800 a 16,8 px). El logotipo de Contexto no es texto: es un trazado —la E de tres
 * barras— y vive en `logo.json`. Además la palabra quedaba por debajo del mínimo legible del
 * logotipo, 96 px de ancho.
 *
 * Carlos eligió entre tres variantes vistas en su teléfono: el lockup horizontal con el isotipo
 * MAESTRO («la opción 3»), pero al tamaño de las otras dos. Ese tamaño no es arbitrario: es el
 * menor en que la palabra todavía mide 96 px, y el componente generado lo exporta como
 * `ALTO_MIN_HORIZONTAL`.
 *
 * Lo que se vigila aquí no se ve roto en ninguna pantalla hasta que alguien lo nota:
 *  1. que `LogoHorizontal` sea el lockup maestro (`contexto-horizontal.svg`), no uno parecido;
 *  2. que `ALTO_MIN_HORIZONTAL` sea de verdad el MÍNIMO —ni uno menor que deje la palabra ilegible,
 *     ni uno mayor que agrande la cabecera en silencio—;
 *  3. que el menú use ese lockup a ese alto, con el color del tema, y que no vuelva la palabra
 *     compuesta a mano ni el signo pequeño emparejado con ella.
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { codigoDesnudo } from './codigoDesnudo'
import { ALTO_MIN_HORIZONTAL } from './LogoContexto'

const SRC = dirname(fileURLToPath(import.meta.url))
const MARCA = join(SRC, '..', '..', 'docs', 'branding', 'logo')
const geo = JSON.parse(readFileSync(join(MARCA, 'logo.json'), 'utf8'))
const maestroHorizontal = readFileSync(join(MARCA, 'contexto-horizontal.svg'), 'utf8')
const componente = readFileSync(join(SRC, 'LogoContexto.jsx'), 'utf8')
const menu = codigoDesnudo(readFileSync(join(SRC, 'Sidebar.jsx'), 'utf8'), 'Sidebar.jsx')

const MIN_PALABRA_PX = 96   // README de la marca: mínimo legible del logotipo

/** Ancho de la PALABRA, en px, para un lockup horizontal de `alto` px (el alto del isotipo). */
function anchoPalabra(alto) {
  const { m, respiro } = geo.isotipo
  return (alto * geo.ancho * geo.horizontal.esc) / (m + 2 * respiro)
}

describe('LogoHorizontal es el lockup maestro, no uno parecido', () => {
  it('usa el mismo lienzo que contexto-horizontal.svg', () => {
    const vb = maestroHorizontal.match(/viewBox="([^"]+)"/)[1]
    expect(componente).toContain(`viewBox="${vb}"`)
  })

  it('coloca la palabra donde la coloca el maestro (caja alta de 4 módulos, 4 de separación)', () => {
    const tr = maestroHorizontal.match(/<g fill="currentColor" transform="([^"]+)"/)[1]
    expect(componente).toContain(`transform="${tr}"`)
  })
})

describe('ALTO_MIN_HORIZONTAL es el mínimo, ni más ni menos', () => {
  it('a ese alto la palabra llega a los 96 px', () => {
    expect(anchoPalabra(ALTO_MIN_HORIZONTAL)).toBeGreaterThanOrEqual(MIN_PALABRA_PX)
  })

  it('un píxel menos y ya no llega: es el mínimo, no un número cualquiera por encima', () => {
    expect(anchoPalabra(ALTO_MIN_HORIZONTAL - 1)).toBeLessThan(MIN_PALABRA_PX)
  })
})

describe('la cabecera del menú lateral', () => {
  it('usa el lockup horizontal generado, al alto mínimo', () => {
    expect(menu).toMatch(/<LogoHorizontal\s+alto=\{ALTO_MIN_HORIZONTAL\}/)
  })

  it('le da el color del texto del tema, para que la palabra pase a blanco en oscuro', () => {
    expect(menu).toMatch(/<LogoHorizontal[^>]*style=\{\{\s*color:\s*C\.text\s*\}\}/)
  })

  it('no vuelve a escribir «Contexto» a mano en la letra de la interfaz', () => {
    expect(menu).not.toMatch(/>\s*Contexto\s*</)
  })

  it('no empareja el signo pequeño con la palabra: sphere.svg ya no entra al menú', () => {
    expect(menu).not.toContain('sphere.svg')
  })
})
