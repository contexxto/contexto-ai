/**
 * SEC-X2-R0 · ATRIBUCIÓN ≠ AUTORIDAD DE DIVULGACIÓN — el lado del comprador.
 *
 * Solo un acto EXPLÍCITO de la persona —pedir contacto con el corredor DE un inmueble
 * concreto— crea autoridad de divulgación. Este módulo NO elige por ella: calcula las
 * OPCIONES que la interfaz puede ofrecer y la etiqueta de cada control. El inmueble que
 * viaja al servidor es siempre el de la opción que la persona pulsó.
 *
 * Antes, el botón enviaba la primera tarjeta del último panel (`r[0].id`), y ese orden lo
 * puede decidir el propio LLM (`tool_priorizar_opcion`). Es decir: una salida del modelo
 * elegía a qué corredor se entregaba la conversación. Eso es lo que se retira aquí.
 *
 * Puro y sin React: se prueba por comportamiento sin jsdom (pedidoCorredor.test.js).
 */

const UUID = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
const UUID_RE = new RegExp(`^${UUID}$`, 'i')
// El servidor acuña las conversaciones del letrero como `qr-{activo}-{aleatorio}`.
// Aquí solo se LEE ese prefijo; el cliente no compone identificadores.
const SESION_LETRERO_RE = new RegExp(`^qr-(${UUID})-`, 'i')

/** UUID canónico (minúsculas) o `null`. Lo que no es un UUID no es un inmueble. */
export function canonico(id) {
  if (typeof id !== 'string') return null
  const t = id.trim()
  return UUID_RE.test(t) ? t.toLowerCase() : null
}

/** El inmueble de una conversación nacida de un letrero, leído de su prefijo, o `null`. */
export function activoDeSesionQr(sessionId) {
  const m = typeof sessionId === 'string' ? SESION_LETRERO_RE.exec(sessionId) : null
  return m ? canonico(m[1]) : null
}

/**
 * OPCIONES, nunca «el elegido»: todas las tarjetas del último panel, en su orden, sin
 * repetir y canónicas. No hay valor por defecto: el orden no es una elección.
 */
export function candidatosDelUltimoPanel(messages) {
  const lista = Array.isArray(messages) ? messages : []
  for (let i = lista.length - 1; i >= 0; i--) {
    const r = lista[i]?.results
    if (!Array.isArray(r) || !r.length) continue
    const vistos = new Set()
    const out = []
    for (const x of r) {
      const id = canonico(x?.id)
      if (!id || vistos.has(id)) continue
      vistos.add(id)
      out.push({ id, direccion: x?.direccion || x?.tipo_activo || null })
    }
    return out
  }
  return []
}

/**
 * El inmueble del letrero, SOLO si la conversación abierta nació de él.
 *
 * - Por el prefijo `qr-{activo}-` de la conversación abierta (lo acuña el servidor, y es la
 *   misma regla que aplica el backend: en una sesión del letrero solo vale ese inmueble).
 * - Por el enlace `/a/{id}`, solo si la conversación abierta es la que este aparato guardó
 *   para ese letrero (`ctx_qr_{id}`). La URL sobrevive a cambiar de conversación: sin esta
 *   atadura, un enlace viejo ofrecería su inmueble dentro de OTRA conversación.
 *
 * Si las dos fuentes se contradicen no se ofrece nada (falla cerrado).
 */
export function activoDelLetrero({ deepLinkId, sessionId, sesionDelLetrero }) {
  const delPrefijo = activoDeSesionQr(sessionId)
  const enlace = canonico(deepLinkId)
  const delEnlace = enlace && sessionId && sessionId === sesionDelLetrero ? enlace : null
  if (delPrefijo && delEnlace && delPrefijo !== delEnlace) return null
  return delPrefijo || delEnlace
}

/**
 * Qué puede ofrecer el control:
 *   'ninguno' → no se muestra (sin inmueble no hay a quién pedir: falla cerrado)
 *   'letrero' → un botón para el inmueble del letrero; en esa conversación es el ÚNICO
 *               ofrecido. `otras` = las demás tarjetas en pantalla, que NO se ofrecen pero
 *               obligan a que la etiqueta no se pueda confundir con ellas
 *   'uno'     → un botón para el único candidato en pantalla
 *   'elegir'  → la persona elige entre los candidatos; NO hay valor por defecto
 */
export function opcionesDelPedido({ letrero, direccionLetrero = null, candidatos } = {}) {
  const lista = Array.isArray(candidatos) ? candidatos : []
  const id = canonico(letrero)
  if (id) {
    const direccion = direccionLetrero || lista.find((c) => c.id === id)?.direccion || null
    return { modo: 'letrero', opciones: [{ id, direccion }], otras: lista.filter((c) => c.id !== id) }
  }
  if (!lista.length) return { modo: 'ninguno', opciones: [], otras: [] }
  return lista.length === 1
    ? { modo: 'uno', opciones: [lista[0]], otras: [] }
    : { modo: 'elegir', opciones: lista, otras: [] }
}

// ── Texto de los controles ──────────────────────────────────────────────────────────
// El agente (SEC-X3-R0) le dice a la persona que pulse «Hablar con el corredor»: todas las
// variantes del control EMPIEZAN por exactamente ese texto, para que lo encuentre.
export const PREFIJO_CONTROL = 'Hablar con el corredor'
export const ETIQUETA_ELEGIR = `${PREFIJO_CONTROL}…`
export const PREGUNTA_ELEGIR = '¿Por cuál inmueble?'

/** Primer tramo de la dirección, recortado; `null` si no hay dirección. */
export function direccionCorta(d) {
  if (!d) return null
  const base = String(d).split(',')[0].trim()
  if (!base) return null
  return base.length > 26 ? base.slice(0, 25) + '…' : base
}

export const ETIQUETA_DEL_ANUNCIO = `${PREFIJO_CONTROL} del inmueble del anuncio`

/**
 * Etiqueta del botón de UNA opción. Nombra el inmueble cuando se conoce su dirección; si no,
 * dice «este inmueble», que solo es inequívoco cuando no hay otra tarjeta en pantalla.
 *
 * En la conversación del letrero puede haber OTRAS tarjetas que no se ofrecen. Si la dirección
 * del letrero no se conoce —o una de esas tarjetas tiene la misma dirección corta—, «de este
 * inmueble» haría creer que se pide la tarjeta que la persona tiene delante, cuando lo que
 * viaja es el inmueble del letrero. Ahí la etiqueta dice «del inmueble del anuncio».
 */
export function etiquetaPedido(opcion, { modo = null, otras = [] } = {}) {
  const corta = direccionCorta(opcion?.direccion)
  if (modo === 'letrero' && Array.isArray(otras) && otras.length) {
    const choca = !corta || otras.some((o) => direccionCorta(o?.direccion) === corta)
    if (choca) return ETIQUETA_DEL_ANUNCIO
  }
  return `${PREFIJO_CONTROL} de ${corta || 'este inmueble'}`
}

/**
 * Etiquetas de los chips de «¿Por cuál inmueble?». Dos tarjetas con la misma dirección
 * corta (dos departamentos del mismo edificio) no pueden verse iguales: se les añade su
 * posición en el panel, que es la que la persona tiene delante.
 */
export function etiquetasDeOpciones(opciones) {
  const lista = Array.isArray(opciones) ? opciones : []
  const base = lista.map((o, i) => direccionCorta(o?.direccion) || `Inmueble ${i + 1}`)
  const veces = base.reduce((m, b) => m.set(b, (m.get(b) || 0) + 1), new Map())
  return base.map((b, i) => (veces.get(b) > 1 ? `${b} · ${i + 1}` : b))
}

// ── Qué hace cada clic ──────────────────────────────────────────────────────────────
/**
 * La decisión de PedirCorredor.jsx, aislada para probarla sin jsdom. Devuelve el nuevo estado
 * de la interfaz (`eligiendo`) y `pedir`: el id que se envía, o `null` si este clic no envía.
 *
 *   { tipo: 'principal' } → letrero/uno: pide su única opción. elegir: SOLO despliega.
 *   { tipo: 'chip', id }  → elegir, desplegado: pide ese id si es una de las opciones.
 *   { tipo: 'cancelar' }  → pliega el selector sin pedir nada.
 *
 * Cualquier otra combinación no pide nada (falla cerrado).
 */
export function clicEnPedido({ modo, opciones, eligiendo = false }, evento) {
  const lista = Array.isArray(opciones) ? opciones : []
  const nada = { eligiendo, pedir: null }
  switch (evento?.tipo) {
    case 'principal':
      if (modo === 'letrero' || modo === 'uno') return { eligiendo: false, pedir: canonico(lista[0]?.id) }
      if (modo === 'elegir') return { eligiendo: true, pedir: null }
      return nada
    case 'chip': {
      const id = canonico(evento.id)
      if (modo !== 'elegir' || !eligiendo || !id || !lista.some((o) => o.id === id)) return nada
      return { eligiendo: false, pedir: id }
    }
    case 'cancelar':
      return { eligiendo: false, pedir: null }
    default:
      return nada
  }
}
