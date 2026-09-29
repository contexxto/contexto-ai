/**
 * Plan 1.1 · TR-1 — la PUERTA SUAVE está retirada (OFD-02 = A).
 *
 * Ofrecía avisar por correo «cuando apareciera algo que encajara», y ningún código envía ese
 * aviso. Se retiró hasta que exista el consumidor. Este barrido de fuente fija, del lado del
 * frontend, lo que el backend ya prueba en `tests/test_tr1_retiro_alerta.py`:
 *
 *     el componente no existe y nadie lo importa
 *     el mensaje no lee `puerta`
 *     `onPanel` ignora `panel.puerta` — un backend viejo que la mande no la hace reaparecer
 *     ningún texto, aria-label ni placeholder conserva la oferta
 *     el opt-in de reenganche (P5), que SÍ tiene consumidor, sigue igual: es TR-2/TR-5
 *
 * Es un barrido de fuente, igual que `noLeak.test.js`: caza el patrón antes de que llegue a un
 * navegador.
 */

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'

const SRC = path.dirname(fileURLToPath(import.meta.url))
const APP = fs.readFileSync(path.join(SRC, 'App.jsx'), 'utf8')

const sinTildes = (t) => t.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

function fuentesDeProduccion(dir = SRC) {
  const out = []
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name)
    if (e.isDirectory()) out.push(...fuentesDeProduccion(p))
    else if (/\.(js|jsx)$/.test(e.name) && !/\.test\./.test(e.name)) out.push(p)
  }
  return out
}

describe('TR-1 · puerta suave retirada', () => {
  it('el componente PuertaAlerta no existe y nadie lo importa', () => {
    expect(fs.existsSync(path.join(SRC, 'PuertaAlerta.jsx'))).toBe(false)
    for (const f of fuentesDeProduccion()) {
      expect(fs.readFileSync(f, 'utf8'), path.basename(f)).not.toMatch(/PuertaAlerta/)
    }
  })

  it('el mensaje no lee `puerta`', () => {
    expect(APP).not.toMatch(/msg\.puerta/)
  })

  it('onPanel ignora panel.puerta: un backend viejo no la hace reaparecer', () => {
    const ini = APP.indexOf('onPanel: (panel) =>')
    expect(ini).toBeGreaterThan(-1)
    const bloque = APP.slice(ini, APP.indexOf('})', ini))
    const codigo = bloque.split('\n').filter((l) => !l.trim().startsWith('//')).join('\n')
    expect(codigo).not.toMatch(/puerta/)
  })

  it('ningún texto, aria-label ni placeholder conserva la oferta retirada', () => {
    const prohibidos = ['tu correo para el aviso', '¿te aviso cuando aparezca',
      'te escribo solo cuando aparezca', 'tu@correo.com', 'no pudimos guardar tu aviso',
      '/api/v1/alertas']
    for (const f of fuentesDeProduccion()) {
      const t = sinTildes(fs.readFileSync(f, 'utf8'))
      for (const p of prohibidos) expect(t, `${path.basename(f)} · ${p}`).not.toContain(sinTildes(p))
    }
  })

  it('el opt-in de reenganche (P5) sigue en pie — no es TR-1', () => {
    // Plan 1.1 · TR-2 (actualización esperada): el texto se corrigió (D-4) y vive en
    // avisoReenganche.js; lo fija avisoReenganche.test.js.
    expect(APP).toContain('COPY_AVISO.boton')
    expect(APP).toContain('/api/v1/chat/lead-contacto')
  })
})
