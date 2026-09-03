/**
 * `SSE-FALLBACK-REEXECUTION-R1` · una acción de la persona = como máximo una petición.
 *
 * Estos casos son los doce que la auditoría midió sobre el flujo anterior. Allí, DIEZ de los
 * doce disparaban un segundo POST a `?stream=false` — otra ejecución completa del agente.
 * Aquí se afirma lo contrario para los mismos doce: ninguno autoriza repetir el turno, y el
 * desenlace lo decide `done`, nunca la presencia de un `token`.
 *
 * SE PRUEBA LA FUNCIÓN QUE EL PRODUCTO LLAMA. Las pruebas anteriores de este flujo recortaban
 * líneas de `App.jsx` y las ejecutaban con `new Function`: eso demuestra lo que hace el
 * recorte, no lo que corre. Por eso el lector se extrajo a `leerStreamChat.js` — y por eso el
 * bloque `costura` de abajo comprueba que `App.jsx` lo importe y lo use de verdad.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { describe, expect, it, vi } from 'vitest'

import { ESTADO, leerStreamChat } from './leerStreamChat'
import { codigoDesnudo } from './codigoDesnudo'

const SRC = dirname(fileURLToPath(import.meta.url))

const sse = (...eventos) => eventos.map((e) => `data: ${JSON.stringify(e)}\n\n`).join('')

/** Una `Response` de mentira que entrega los trozos dados, y opcionalmente revienta. */
function respuesta(trozos, { ok = true, status = 200, conCuerpo = true, revienta = false } = {}) {
  let i = 0
  return {
    ok,
    status,
    body: conCuerpo
      ? {
          getReader: () => ({
            async read() {
              if (i < trozos.length) return { done: false, value: new TextEncoder().encode(trozos[i++]) }
              if (revienta) throw new TypeError('network error')
              return { done: true, value: undefined }
            },
          }),
        }
      : null,
  }
}

const PANEL = { results: [{ id: 'A1' }], map_seed: null, puerta: null }

// ── los doce escenarios auditados ─────────────────────────────────────────────

describe('los doce escenarios que antes reejecutaban el turno', () => {
  it('1 · token + panel + done → ÉXITO, texto y panel intactos', async () => {
    const r = await leerStreamChat(respuesta([sse(
      { token: 'hola ', session_id: 's' }, { token: 'mundo', session_id: 's' },
      { panel: PANEL }, { done: true, session_id: 's' })]))

    expect(r.estado).toBe(ESTADO.EXITO)
    expect(r.texto).toBe('hola mundo')
    expect(r.panel).toEqual(PANEL)
    expect(r.parcial).toBe(false)
  })

  it('2 · respuesta directa sin herramienta → ÉXITO', async () => {
    const r = await leerStreamChat(respuesta([sse(
      { token: 'respuesta directa', session_id: 's' },
      { panel: { results: [], map_seed: null, puerta: null } },
      { done: true, session_id: 's' })]))

    expect(r.estado).toBe(ESTADO.EXITO)
    expect(r.texto).toBe('respuesta directa')
  })

  it('3 · tool_call y luego excepción → ERROR, sin texto que presentar', async () => {
    const r = await leerStreamChat(
      respuesta([sse({ tool_call: 'tool_search_nearby_assets' })], { revienta: true }))

    expect(r.estado).toBe(ESTADO.ERROR)
    expect(r.texto).toBe('')
  })

  it('4 · tool_call + panel + done SIN token → ÉXITO y el panel se conserva', async () => {
    // El caso que más importa: el turno terminó BIEN. Antes se reejecutaba por no traer prosa.
    const r = await leerStreamChat(respuesta([sse(
      { tool_call: 'tool_search_nearby_assets' }, { panel: PANEL },
      { done: true, session_id: 's' })]))

    expect(r.estado).toBe(ESTADO.EXITO)
    expect(r.texto).toBe('')
    expect(r.panel).toEqual(PANEL)
    expect(r.parcial).toBe(false)
  })

  it('5 · stream sin ningún evento → INCOMPLETO', async () => {
    const r = await leerStreamChat(respuesta([]))
    expect(r.estado).toBe(ESTADO.INCOMPLETO)
  })

  it('6 · HTTP 502 → ERROR, y ni siquiera se abre el lector', async () => {
    const abrir = vi.fn()
    const r = await leerStreamChat({ ok: false, status: 502, body: { getReader: abrir } })

    expect(r.estado).toBe(ESTADO.ERROR)
    expect(r.motivo).toContain('502')
    expect(abrir).not.toHaveBeenCalled()
  })

  it('7 · resp.body === null → ERROR', async () => {
    const r = await leerStreamChat(respuesta([], { conCuerpo: false }))
    expect(r.estado).toBe(ESTADO.ERROR)
    expect(r.motivo).toBe('sin cuerpo')
  })

  it('8 · token y luego excepción → ERROR con el parcial conservado y MARCADO', async () => {
    const r = await leerStreamChat(
      respuesta([sse({ token: 'a medias ', session_id: 's' })], { revienta: true }))

    expect(r.estado).toBe(ESTADO.ERROR)
    expect(r.texto).toBe('a medias ')
    expect(r.parcial).toBe(true)      // jamás se presenta como respuesta completa
  })

  it('9 · token vacío + panel + done → ÉXITO con panel', async () => {
    const r = await leerStreamChat(respuesta([sse(
      { token: '', session_id: 's' }, { panel: PANEL }, { done: true, session_id: 's' })]))

    expect(r.estado).toBe(ESTADO.EXITO)
    expect(r.texto).toBe('')
    expect(r.panel).toEqual(PANEL)
    expect(r.eventos.token).toBe(1)   // el evento llegó; sólo no aportó texto
  })

  it('10 · bloque final sin \\n\\n → INCOMPLETO, nunca éxito silencioso', async () => {
    const r = await leerStreamChat(respuesta([
      sse({ token: 'visible ', session_id: 's' }) +
      `data: ${JSON.stringify({ done: true, session_id: 's' })}`,   // sin cierre de marco
    ]))

    expect(r.estado).toBe(ESTADO.INCOMPLETO)
    expect(r.texto).toBe('visible ')
    expect(r.parcial).toBe(true)
  })

  it('11 · JSON malformado → ERROR; un done posterior no lo rescata', async () => {
    const r = await leerStreamChat(respuesta([
      'data: {esto no es json}\n\n' + sse({ done: true, session_id: 's' })]))

    expect(r.estado).toBe(ESTADO.ERROR)
    expect(r.motivo).toBe('evento malformado')
    expect(r.eventos.done).toBe(0)
  })

  it('12 · done sin texto ni panel → VACÍO: anomalía visible, no fallo de red', async () => {
    const r = await leerStreamChat(respuesta([sse({ done: true, session_id: 's' })]))

    expect(r.estado).toBe(ESTADO.VACIO)
    expect(r.texto).toBe('')
    expect(r.panel).toBeNull()
  })
})

// ── terminación e integridad ──────────────────────────────────────────────────

describe('terminación', () => {
  it('done se cuenta una vez y nada se procesa después', async () => {
    const onToken = vi.fn()
    const r = await leerStreamChat(respuesta([sse(
      { token: 'antes ', session_id: 's' }, { done: true, session_id: 's' },
      { token: 'DESPUES', session_id: 's' }, { done: true, session_id: 's' })]), { onToken })

    expect(r.eventos.done).toBe(1)
    expect(r.eventos.ignoradosTrasDone).toBe(2)
    expect(r.texto).toBe('antes ')
    expect(onToken).toHaveBeenCalledTimes(1)
  })

  it('un cierre sin done es incompleto AUNQUE haya llegado texto', async () => {
    const r = await leerStreamChat(respuesta([sse({ token: 'texto sin cierre', session_id: 's' })]))
    expect(r.estado).toBe(ESTADO.INCOMPLETO)
    expect(r.parcial).toBe(true)
  })

  it('los callbacks pintan en vivo pero no deciden el desenlace', async () => {
    const onToken = vi.fn()
    const onPanel = vi.fn()
    const r = await leerStreamChat(respuesta([
      sse({ token: 'a', session_id: 's' }), sse({ panel: PANEL }),
    ]), { onToken, onPanel })

    expect(onToken).toHaveBeenCalledWith('a', 'a')
    expect(onPanel).toHaveBeenCalledWith(PANEL)
    expect(r.estado).toBe(ESTADO.INCOMPLETO)     // hubo pintura, no hubo done
  })

  it('el lector no puede pedir nada: no conoce fetch ni axios', () => {
    const fuente = codigoDesnudo(
      readFileSync(join(SRC, 'leerStreamChat.js'), 'utf8'), 'leerStreamChat.js')
    expect(fuente).not.toMatch(/fetch\s*\(/)
    expect(fuente).not.toMatch(/axios/)
  })
})

// ── el protocolo `contexto-sse/1` ─────────────────────────────────────────────

const META = { meta: {
  protocolo: 'contexto-sse/1', session_id: 's', execution_id: 'e-1',
  runtime_sha: '581537d4994f61d1c290c04349f6b94143879c7c', service_id: 'srv-x',
  emitido_en: '2026-09-02T21:14:07.318Z' } }

describe('identidad del turno', () => {
  it('reconoce `meta` y la conserva sin interpretarla', async () => {
    const r = await leerStreamChat(respuesta([sse(
      META, { token: 'hola' }, { panel: PANEL }, { done: true, execution_id: 'e-1' })]))

    expect(r.estado).toBe(ESTADO.EXITO)
    expect(r.meta.execution_id).toBe('e-1')
    expect(r.meta.runtime_sha).toHaveLength(40)
    expect(r.eventos.meta).toBe(1)
    expect(r.texto).toBe('hola')       // `meta` no contamina el texto
  })

  it('sin `meta` el turno sigue funcionando: el lector no la exige', async () => {
    const r = await leerStreamChat(respuesta([sse({ token: 'hola' }, { done: true })]))
    expect(r.estado).toBe(ESTADO.EXITO)
    expect(r.meta).toBeNull()          // quien adjudica decidirá que no es atribuible
  })

  it('`error` es TERMINAL: FALLIDO, no INCOMPLETO', async () => {
    const r = await leerStreamChat(respuesta([sse(
      META, { error: { code: 'execution_failed', phase: 'graph' }, execution_id: 'e-1' })]))

    expect(r.estado).toBe(ESTADO.FALLIDO)
    expect(r.motivo).toBe('execution_failed/graph')
    expect(r.eventos.error).toBe(1)
  })

  it('`error` conserva el texto y el panel ya recibidos, marcados como parciales', async () => {
    const r = await leerStreamChat(respuesta([sse(
      META, { token: 'a medias ' }, { panel: PANEL },
      { error: { code: 'checkpoint_not_found', phase: 'checkpoint' } })]))

    expect(r.estado).toBe(ESTADO.FALLIDO)
    expect(r.texto).toBe('a medias ')
    expect(r.panel).toEqual(PANEL)
    expect(r.parcial).toBe(true)
  })

  it('tras `error` no se procesa nada más, ni un `done`', async () => {
    const onToken = vi.fn()
    const r = await leerStreamChat(respuesta([sse(
      META, { error: { code: 'execution_failed', phase: 'graph' } },
      { token: 'DESPUES' }, { done: true })]), { onToken })

    expect(r.estado).toBe(ESTADO.FALLIDO)
    expect(r.texto).toBe('')
    expect(r.eventos.done).toBe(0)
    expect(onToken).not.toHaveBeenCalled()
  })
})

// ── costura: que el producto llame a esto de verdad ───────────────────────────

describe('costura con App.jsx', () => {
  const app = codigoDesnudo(readFileSync(join(SRC, 'App.jsx'), 'utf8'))

  it('App.jsx importa el lector y lo invoca', () => {
    expect(app).toMatch(/import\s*\{[^}]*leerStreamChat[^}]*\}\s*from\s*'\.\/leerStreamChat'/)
    expect(app).toMatch(/await\s+leerStreamChat\s*\(/)
  })

  it('el desenlace se decide por ESTADO, no por una bandera de tokens', () => {
    expect(app).toMatch(/ESTADO\./)
    // `escribio` era la variable que decidía el éxito y disparaba el reintento.
    expect(app).not.toMatch(/\bescribio\b/)
  })

  it('no queda ningún reintento automático del turno', () => {
    expect(app).not.toMatch(/enviarBloqueante/)
    const streams = app.match(/\/api\/v1\/chat\/\?stream=true/g) || []
    expect(streams).toHaveLength(1)
  })

  it('ninguna ruta POSTERIOR al fetch del envío pide otra vez el turno', () => {
    // Se acota al flujo de envío. `App.jsx` tiene otro POST a `/api/v1/chat/` — el turno de
    // apertura del QR (`abrirDesdeQR`), que es OTRA acción de la persona, hace una sola
    // petición y ya no tiene fallback. R1 gobierna el envío, no aquél.
    const inicio = app.indexOf('/api/v1/chat/?stream=true')
    const fin = app.indexOf('[input, loading, sessionId, session, geo, modoCorredor]')
    expect(inicio).toBeGreaterThan(0)
    expect(fin).toBeGreaterThan(inicio)

    const trasElFetch = app.slice(inicio, fin)
    expect(trasElFetch).not.toMatch(/axios\.post/)
    expect(trasElFetch).not.toMatch(/axios\.\w+/)
    expect(trasElFetch).not.toMatch(/fetch\s*\(/)
  })

  it('el mensaje del usuario se añade a la interfaz una sola vez', () => {
    const añadidos = app.match(/\[\s*\.\.\.prev\s*,\s*userMsg\s*\]/g) || []
    expect(añadidos).toHaveLength(1)
  })

  it('App.jsx trata FALLIDO con su propia copy, distinta del corte a medias', () => {
    // Dos `expect` independientes —«existe FALLIDO» y «existe la copy»— pasarían aunque
    // vivieran en ramas distintas. Se afirma sobre el TRAMO que arranca en la rama FALLIDO
    // y termina en la siguiente, que es donde la copy tiene que estar.
    const i = app.indexOf('ESTADO.FALLIDO')
    expect(i).toBeGreaterThan(0)
    const tramo = app.slice(i, app.indexOf('ESTADO.VACIO', i))
    expect(tramo.length).toBeGreaterThan(0)
    expect(tramo).toContain('No se pudo completar este turno.')
    // Y no se le llama «se cortó a medias», que es otro desenlace.
    expect(tramo).not.toContain('se cortó a medias')
  })
})
