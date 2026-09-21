/**
 * La marca se dibuja con el logotipo, nunca con «Contexto» escrito en la letra de la interfaz.
 *
 * Carlos, 2026-09-21: «Poner el logotipo en los lugares donde "Contexto" todavía aparece escrito en
 * letra normal». Tras la cabecera del menú (#148) y la del chat (#152) quedaban siete: la
 * conversación compartida, el letrero inteligente, la hoja del «+», el ingreso y /que-es (cabecera y
 * pie), más el letrero impreso (tests/test_generar_qrs.py). Todos llevan ahora el lockup horizontal
 * generado desde logo.json, a su alto mínimo legible.
 */

import { readdirSync, readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { codigoDesnudo } from './codigoDesnudo'

const SRC = dirname(fileURLToPath(import.meta.url))
const leer = (f) => codigoDesnudo(readFileSync(join(SRC, f), 'utf8'), f)
const TODOS = readdirSync(SRC).filter((f) => f.endsWith('.jsx'))

// «Contexto» como texto suelto de JSX pegado a una etiqueta: >Contexto<, también con saltos de
// línea (la cabecera del chat se escapó así de una búsqueda de una sola línea) y detrás de un signo.
const PALABRA_A_MANO = />\s*Contexto\s*</

const SITIOS = ['App.jsx', 'AnuncioView.jsx', 'AttachSheet.jsx', 'Auth.jsx', 'QueEs.jsx']

describe('la palabra de la marca', () => {
  it('ningún componente la escribe a mano', () => {
    const con = TODOS.filter((f) => PALABRA_A_MANO.test(leer(f)))
    expect(con).toEqual([])
  })

  it('control: el detector reconoce las tres formas que había', () => {
    expect(PALABRA_A_MANO.test(`<span style={{ fontWeight: 800 }}>Contexto</span>`)).toBe(true)
    expect(PALABRA_A_MANO.test(`<div style={{ fontWeight:800 }}>\n  Contexto\n</div>`)).toBe(true)
    expect(PALABRA_A_MANO.test(`<a className="brand" href="/"><img src={isotipo} alt="" /> Contexto</a>`)).toBe(true)
    expect(PALABRA_A_MANO.test(`<a href="/">Abrir Contexto</a>`)).toBe(false)
  })
})

describe('el logotipo en su lugar', () => {
  it.each(SITIOS)('%s usa el lockup horizontal generado', (f) => {
    const t = leer(f)
    expect(t).toContain("import { LogoHorizontal, ALTO_MIN_HORIZONTAL } from './LogoContexto'")
    expect(t).toMatch(/<LogoHorizontal\s+alto=\{ALTO_MIN_HORIZONTAL\}/)
  })

  it('nadie lo dibuja por debajo del alto en que la palabra se lee', () => {
    const usos = TODOS.flatMap((f) => [...leer(f).matchAll(/<LogoHorizontal\b[^/]*\/>/g)].map((m) => `${f}: ${m[0]}`))
    expect(usos.length).toBeGreaterThanOrEqual(SITIOS.length + 2)  // + el menú y la cabecera del chat
    expect(usos.filter((u) => !/alto=\{ALTO_MIN_HORIZONTAL\}/.test(u))).toEqual([])
  })
})
