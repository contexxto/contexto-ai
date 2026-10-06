/**
 * SEC-X2-R0 · ATRIBUCIÓN ≠ AUTORIDAD DE DIVULGACIÓN — contrato de fuente.
 *
 * `pedidoCorredor.test.js` prueba las piezas por comportamiento. Esto prueba que `App.jsx`,
 * `PedirCorredor.jsx` y el CRM las USAN: que el inmueble que viaja en el pedido de corredor
 * sale del clic de la persona y no de la primera tarjeta, y que el CRM no ofrece la
 * conversación de quien aún no la pidió.
 *
 * Como en `appCutover.test.js`, se afirma sobre `codigoDesnudo(...)`: sin comentarios. Un
 * `grep` crudo daría verde (o rojo) por lo que dice un comentario, no por lo que hace el código.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { codigoDesnudo } from './codigoDesnudo'
import { ETIQUETA_SIN_SOLICITUD, conversacionVisible, frasePrivada, pidioCorredor, puntaje } from './divulgacionLead'
import { direccionVigente, leerDireccionAnuncio, mensajeErrorLetrero } from './direccionLetrero'

const SRC = dirname(fileURLToPath(import.meta.url))
const leer = (f) => codigoDesnudo(readFileSync(join(SRC, f), 'utf8'), f)
const app = leer('App.jsx')
const pedir = leer('PedirCorredor.jsx')
const leadsPanel = leer('LeadsPanel.jsx')
const crm = leer('CRM.jsx')
const analisis = leer('AnalisisPanel.jsx')

/** El cuerpo de `iniciarHandoff`, desde su declaración hasta el cierre del useCallback. */
const cuerpoIniciar = (() => {
  const i = app.indexOf('const iniciarHandoff = useCallback(')
  const f = app.indexOf('}, [sessionId, session, subscribeToPush])', i)
  return i >= 0 && f > i ? app.slice(i, f) : ''
})()

describe('App.jsx: ninguna heurística elige el inmueble', () => {
  it('no queda `activoCandidato` ni la primera tarjeta del panel', () => {
    expect(app).not.toContain('activoCandidato')
    expect(app).not.toMatch(/r\[0\]\??\.id/)
  })

  it('iniciarHandoff recibe el inmueble del acto y falla cerrado sin él', () => {
    expect(cuerpoIniciar).not.toBe('')
    expect(cuerpoIniciar).toContain('async (activoId) =>')
    expect(cuerpoIniciar).toContain('const elegido = canonico(activoId)')
    const corte = cuerpoIniciar.indexOf('if (!elegido) return')
    expect(corte).toBeGreaterThan(-1)
    expect(corte).toBeLessThan(cuerpoIniciar.indexOf('axios.post('))
  })

  it('nadie llama a iniciarHandoff sin inmueble ni le pasa el evento del clic', () => {
    expect(app).not.toMatch(/iniciarHandoff\(\s*\)/)
    expect(app).not.toContain('onClick={iniciarHandoff}')
    // El único que la recibe como callback es el control, que la llama con un id.
    expect(app).toContain('onPedir={iniciarHandoff}')
    expect(pedir).not.toMatch(/onPedir\(\s*\)/)
    expect(pedir).not.toContain('onClick={onPedir}')
    // Una sola llamada, con el id que decide `clicEnPedido` y solo si lo hay.
    expect(pedir.match(/onPedir\(/g)).toHaveLength(1)
    expect(pedir).toContain('const r = clicEnPedido({ modo, opciones, eligiendo }, evento)')
    expect(pedir).toContain('if (!r.pedir) return')
    expect(pedir).toContain('await onPedir(r.pedir)')
  })

  it('el POST a /handoff lleva el inmueble en el CUERPO (y el mismo en el query)', () => {
    // Uno solo, sea cual sea su cuerpo: un segundo POST a /handoff no puede colarse sin pasar
    // por esta aserción (ni con un cuerpo vacío ni con una variable).
    expect(app.match(/axios\.post\(\s*`[^`]*\/handoff`/g)).toHaveLength(1)
    const posts = [...app.matchAll(/axios\.post\(\s*`[^`]*\/handoff`\s*,\s*(\{[^}]*\})\s*,\s*\{([^\n]*)\}\)/g)]
    expect(posts).toHaveLength(1)
    const [, cuerpo, opciones] = posts[0]
    expect(cuerpo).toBe('{ activo_id: elegido }')
    expect(opciones).toContain('params: { activo_id: elegido }')
    expect(opciones).toContain('headers: apiHeadersSesion(sessionId)')
  })

  it('no anuncia «Te conecté» si el servidor registró otro inmueble', () => {
    const chequeo = cuerpoIniciar.indexOf('canonico(data?.activo_id) !== elegido')
    expect(chequeo).toBeGreaterThan(-1)
    expect(chequeo).toBeLessThan(cuerpoIniciar.indexOf('Te conecté con el corredor'))
  })

  it('el pendiente del login guarda EL inmueble elegido, no un booleano', () => {
    expect(app).not.toContain('setHandoffPendiente(true)')
    expect(app).not.toContain('setHandoffPendiente(false)')
    expect(app).toContain('const [handoffPendiente, setHandoffPendiente] = useState(null)')
    expect(app).toContain('setHandoffPendiente(elegido)')
    expect(app).toMatch(/const elegido = handoffPendiente\s+setHandoffPendiente\(null\)\s+iniciarHandoff\(elegido\)/)
  })

  it('el control aparece por el letrero vigente o por opciones en pantalla, no por la URL a secas', () => {
    expect(app).toContain('(letrero || candidatosCorredor.length > 0 || modoCorredor || hilosCorredor.length > 0) &&')
    expect(app).not.toContain('(deepLinkId || activoCandidato')
    expect(app).toContain('activoDelLetrero({ deepLinkId, sessionId, sesionDelLetrero })')
  })
})

describe('el texto del control empieza por «Hablar con el corredor»', () => {
  it('PedirCorredor usa las etiquetas del módulo puro, con las otras tarjetas a la vista', () => {
    // `otras` es lo que impide que el botón del letrero diga «este inmueble» con otra tarjeta delante.
    expect(pedir).toContain('{etiquetaPedido(opciones[0], { modo, otras })}')
    expect(pedir).toContain('{ETIQUETA_ELEGIR}')
    expect(pedir).toContain('{PREGUNTA_ELEGIR}')
  })

  it('App consulta la dirección del letrero sin otra llamada con apiHeaders() en App.jsx', () => {
    expect(app).toContain('useDireccionLetrero(letrero, direccionCapturada)')
    expect(app).toContain('direccionLetrero={direccionLetrero}')
    expect(app).not.toContain('/anuncio`')
  })

  it('nadie escribe «Hablar con un corredor»', () => {
    for (const f of [app, pedir]) expect(f).not.toMatch(/[Hh]ablar con un corredor/)
  })
})

describe('CRM: sin solicitud, la conversación no se ofrece', () => {
  const leadChat = leadsPanel.slice(leadsPanel.indexOf('export function LeadChat'))
  const tramo = (desde, hasta) => {
    const i = leadChat.indexOf(desde)
    return i >= 0 ? leadChat.slice(i, leadChat.indexOf(hasta, i)) : ''
  }

  it('LeadChat comprueba la solicitud ANTES de pedir /conversacion y de /responder', () => {
    const cargar = tramo('async function cargar()', '/conversacion`')
    const responder = tramo('async function responder()', '/responder`')
    expect(cargar).toContain('if (!conversacionVisible(lead)) return')
    expect(responder).toContain('if (!conversacionVisible(lead)) return')
    expect(leadChat).toContain('if (!visible) return <LeadPrivado')
  })

  it('el listado solo ofrece «Entrar a la conversación» a quien la pidió', () => {
    expect(leadsPanel).toMatch(/\{visible && \(\s*<button onClick=\{\(\) => setConvo\(l\)\}/)
  })

  it('el Copiloto solo se enfoca en un interesado que pidió corredor', () => {
    expect(crm).toContain("lead={asistente === 'copiloto' && conversacionVisible(sel) ? sel : null}")
  })

  it('«Piden corredor» cuenta el acto, no la inferencia', () => {
    expect(crm).toContain('const pide = (l) => pidioCorredor(l)')
    expect(crm).not.toContain('l.handoff_estado || l.handoff_sugerido')
  })

  it('ningún campo que puede llegar en null se pinta crudo', () => {
    for (const f of [leadsPanel, crm]) {
      expect(f).not.toMatch(/\{\s*(l|lead)\.score\s*\}/)
      expect(f).not.toContain('{l.mensajes ?? 0}')
      expect(f).not.toContain('{lead.score}/100')
    }
  })
})

describe('divulgacionLead: la regla, por comportamiento', () => {
  const privado = {
    session_id: 'qr-x', pidio_corredor: false, lead: 'Lead #ab12', fuente: 'qr',
    estado: null, nivel: null, score: null, razones: null, reenganche: null, mensajes: null,
    handoff_estado: null, handoff_sugerido: null, email: null,
  }

  it('pidio_corredor=false: ni conversación ni «pidió corredor»', () => {
    expect(conversacionVisible(privado)).toBe(false)
    expect(pidioCorredor(privado)).toBe(false)
    expect(puntaje(privado)).toBeNull()
  })

  it('pidio_corredor=true: se ofrece', () => {
    const l = { ...privado, pidio_corredor: true, handoff_estado: 'solicitado', score: 72 }
    expect(conversacionVisible(l)).toBe(true)
    expect(pidioCorredor(l)).toBe(true)
    expect(puntaje(l)).toBe(72)
  })

  it('backend anterior (sin el campo): se conserva su comportamiento', () => {
    expect(conversacionVisible({ session_id: 's' })).toBe(true)
    expect(pidioCorredor({ handoff_estado: 'activo' })).toBe(true)
    expect(pidioCorredor({ handoff_estado: null })).toBe(false)
    expect(conversacionVisible(null)).toBe(false)
  })

  it('puntaje nunca devuelve NaN ni texto', () => {
    expect(puntaje({ score: Number.NaN })).toBeNull()
    expect(puntaje({ score: '80' })).toBeNull()
    expect(puntaje({})).toBeNull()
  })

  it('la línea neutral no afirma de más: «no hay solicitud registrada», no «aún no lo pidió»', () => {
    expect(ETIQUETA_SIN_SOLICITUD).toBe('Sin solicitud registrada')
    expect(frasePrivada(privado)).toBe(
      'Llegó por el letrero (QR). No hay una solicitud de contacto registrada: '
      + 'su conversación es privada hasta que la persona la pida.')
    expect(frasePrivada({ ...privado, fuente: 'buscador' })).toMatch(/^Llegó por un buscador\. /)
    expect(frasePrivada({ ...privado, fuente: 'directo' })).toMatch(/^Llegó por un canal sin identificar\. /)
    // Sin registro de llegada no se afirma ningún canal.
    for (const fuente of [null, undefined, 'desconocido']) {
      const t = frasePrivada({ ...privado, fuente })
      expect(t).toBe('No hay una solicitud de contacto registrada: su conversación es privada hasta que la persona la pida.')
      expect(t).not.toMatch(/null|undefined|NaN/)
    }
    for (const t of [ETIQUETA_SIN_SOLICITUD, frasePrivada(privado)]) expect(t).not.toMatch(/[Aa]ún no/)
  })
})

describe('el comprador: errores que se explican', () => {
  const tramoEnvioCorredor = (() => {
    const i = app.indexOf('/handoff/mensaje`')
    return i >= 0 ? app.slice(i, app.indexOf('return', app.indexOf('} catch (e) {', i))) : ''
  })()

  it('409 al escribir al corredor: sale del modo corredor y pide una solicitud nueva', () => {
    // El hilo se declara FUERA del try: el catch lo usa para quitarlo de la lista.
    expect(app).toMatch(/if \(modoCorredor\) \{\s+const hilo = hiloActivo \|\| hiloSeleccionado\s+try \{/)
    expect(tramoEnvioCorredor).toContain('if (e?.response?.status === 409) {')
    expect(tramoEnvioCorredor).toContain('setHilosCorredor((prev) => prev.filter((h) => h.activo_id !== hilo))')
    expect(tramoEnvioCorredor).toContain('setModoCorredor(false)')
    expect(tramoEnvioCorredor).toContain(
      "setError('Tu conversación con el corredor necesita una nueva solicitud. Pulsa «Hablar con el corredor» para retomarla.')")
    // Los demás errores siguen con el mensaje de siempre.
    expect(tramoEnvioCorredor).toContain("setError('No se pudo enviar tu mensaje al corredor. Intenta de nuevo.')")
  })

  it('el letrero se abre con manejo de error: nadie llama a loadFromDeepLink sin catch', () => {
    const llamadas = app.split('\n').filter((l) => /loadFromDeepLink\(/.test(l) && !/const loadFromDeepLink/.test(l))
    expect(llamadas).toHaveLength(1)
    expect(llamadas[0]).toContain('loadFromDeepLink(id).catch((e) => setError(mensajeErrorLetrero(e)))')
  })

  it('404 o 422 del bootstrap se dicen «No encontramos ese inmueble.»', () => {
    expect(mensajeErrorLetrero({ response: { status: 404 } })).toBe('No encontramos ese inmueble.')
    expect(mensajeErrorLetrero({ response: { status: 422 } })).toBe('No encontramos ese inmueble.')
    expect(mensajeErrorLetrero(new Error('red'))).toMatch(/^No pudimos abrir la conversación/)
    expect(mensajeErrorLetrero(undefined)).toMatch(/^No pudimos abrir la conversación/)
  })
})

describe('direccionLetrero: la etiqueta del letrero sin inventar ni lanzar', () => {
  const X = '33333333-3333-4333-8333-333333333333'

  it('pide el anuncio público del inmueble y devuelve su dirección', async () => {
    const vistas = []
    const get = async (url, cfg) => { vistas.push({ url, cfg }); return { data: { direccion: ' Av. Amazonas N24, Quito ' } } }
    expect(await leerDireccionAnuncio(X.toUpperCase(), get)).toBe('Av. Amazonas N24, Quito')
    expect(vistas).toHaveLength(1)
    expect(vistas[0].url).toMatch(new RegExp(`/api/v1/assets/${X}/anuncio$`))
    expect(vistas[0].cfg).toHaveProperty('headers')
  })

  it('si falla o no trae dirección, devuelve null (nunca lanza)', async () => {
    expect(await leerDireccionAnuncio(X, async () => { throw new Error('404') })).toBeNull()
    expect(await leerDireccionAnuncio(X, async () => ({ data: {} }))).toBeNull()
    expect(await leerDireccionAnuncio(X, async () => ({ data: { direccion: '   ' } }))).toBeNull()
  })

  it('un id que no es UUID no hace ninguna petición', async () => {
    let llamadas = 0
    expect(await leerDireccionAnuncio('abc-123', async () => { llamadas++; return { data: {} } })).toBeNull()
    expect(llamadas).toBe(0)
  })

  it('la respuesta de un letrero anterior no se usa para otro', () => {
    const consulta = { id: X, direccion: 'Av. Amazonas N24' }
    expect(direccionVigente(consulta, X)).toBe('Av. Amazonas N24')
    expect(direccionVigente(consulta, '11111111-1111-4111-8111-111111111111')).toBeNull()
    expect(direccionVigente(null, X)).toBeNull()
  })
})

describe('AnalisisPanel: el cubo «atribuido» es una fila aparte, no una etapa', () => {
  it('no entra en ORDEN ni en EN_CURSO (no puede ser el cuello ni recibir la pregunta por etapa)', () => {
    const orden = analisis.slice(analisis.indexOf('const ORDEN'), analisis.indexOf('const card'))
    expect(orden).not.toContain('atribuido')
  })

  it('se dibuja con su propia fila, sin onClick, y cuenta en la escala de las barras', () => {
    expect(analisis).toContain('funnel.atribuido')
    expect(analisis).toContain('Math.max(1, ...filas.map(e => funnel[e]), atribuidos)')
    const i = analisis.indexOf('{atribuidos > 0 && (')
    const fila = analisis.slice(i, analisis.indexOf('{onPreguntar && filas.length > 0', i))
    expect(i).toBeGreaterThan(-1)
    expect(fila).not.toContain('onClick')
    expect(fila).not.toContain('onPreguntar')
    expect(fila).toContain('{ETIQUETA_SIN_SOLICITUD}')
  })
})
