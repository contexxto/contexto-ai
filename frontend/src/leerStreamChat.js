/**
 * Lee el stream SSE de un turno de chat y dice **cómo terminó**. Nada más.
 *
 * POR QUÉ EXISTE (`SSE-FALLBACK-REEXECUTION-01`). Este bucle vivía dentro de `App.jsx` y
 * decidía el éxito del turno con una sola variable: `escribio`, verdadera sólo si había
 * llegado algún `token`. Si no llegaba ninguno, lanzaba y el `catch` reintentaba **por el POST
 * bloqueante** — una SEGUNDA EJECUCIÓN COMPLETA del agente. La auditoría midió 10 de 12
 * condiciones que la disparaban, y la peor no era un fallo: un turno que terminaba bien
 * —`tool_call`, `panel` y `done`, sin excepción— se reejecutaba entero por no tener prosa,
 * duplicando los cinco efectos que la primera ejecución ya había consumado (herramienta,
 * panel, auditoría de prosa, sombra del comprador, registro de intención). El hilo acababa
 * con dos `HumanMessage` para una sola intención de la persona.
 *
 * EL ERROR DE FONDO era una equivalencia falsa: «no escribí nada al cliente» ⇒ «el servidor no
 * hizo nada». Una caída de transporte después de despachar es AMBIGUA — el cliente no puede
 * saber si el servidor no ejecutó, ejecutó a medias, o terminó sin poder entregar. Se buscó
 * alguna condición observable que probara que la petición no llegó a empezar: no existe
 * ninguna. `fetch` lanza el mismo `TypeError` para un DNS que no resolvió y para una conexión
 * cortada tras enviar.
 *
 * LA REGLA NUEVA: **`done` decide el éxito, no `token`.** Un turno sin prosa pero con panel es
 * un éxito con panel; un turno sin `done` es incompleto aunque haya llegado texto. Y pase lo
 * que pase, quien llama NUNCA vuelve a pedir el turno: el reintento lo decide la persona.
 *
 * QUÉ NO SABE ESTE MÓDULO, a propósito: nada de contrato territorial, Buyer Harness, tarjetas
 * ni negocio. Transporte, parseo y desenlace. Se extrajo para poder probarlo de verdad — las
 * pruebas anteriores ejecutaban un fragmento recortado de `App.jsx`, que demuestra lo que
 * decía el recorte, no lo que corre en producción.
 */

/** Cómo terminó el turno. Sólo `EXITO` autoriza tratar la respuesta como completa. */
export const ESTADO = {
  /** Llegó `done` y hay algo que mostrar (texto, panel, o ambos). */
  EXITO: 'exito',
  /** El servidor dijo explícitamente que el turno no pudo completarse (evento `error`). */
  FALLIDO: 'fallido',
  /** Llegó `done` pero el turno no trajo ni prosa ni panel: anomalía, no fallo de red. */
  VACIO: 'vacio',
  /** El stream se cerró sin `done`. Puede haber texto parcial; NO es un éxito. */
  INCOMPLETO: 'incompleto',
  /** No se pudo leer: respuesta no válida, corte con excepción, o marco corrupto. */
  ERROR: 'error',
}

const PREFIJO = 'data: '

/**
 * Consume `resp` (una `Response` de `fetch`) y devuelve el desenlace del turno.
 *
 * @param {Response} resp
 * @param {{onToken?: (textoAcumulado: string, trozo: string) => void,
 *          onPanel?: (panel: object) => void}} callbacks
 *        Se invocan mientras llega el stream, para que la interfaz pinte en vivo. No
 *        deciden nada: el desenlace lo devuelve esta función.
 * @returns {Promise<{estado: string, texto: string, panel: object|null, parcial: boolean,
 *                    motivo: string|null, eventos: object}>}
 *
 * `parcial` es verdadero cuando llegó texto pero el turno no terminó bien: quien llama debe
 * conservar lo escrito y decir que se cortó, nunca presentarlo como respuesta completa.
 */
export async function leerStreamChat(resp, { onToken, onPanel } = {}) {
  const eventos = { meta: 0, token: 0, panel: 0, done: 0, error: 0, ignoradosTrasDone: 0 }
  let texto = ''
  let panel = null
  let meta = null

  const desenlace = (estado, motivo) => ({
    estado,
    texto,
    panel,
    // La identidad del turno (`contexto-sse/1`): execution_id, runtime_sha, service_id.
    // Se conserva tal cual llegó, sin interpretarla: quien adjudica es otro.
    meta,
    parcial: estado !== ESTADO.EXITO && (texto.length > 0 || panel !== null),
    motivo: motivo ?? null,
    eventos,
  })

  // Una respuesta que no se puede leer no es un turno fallido: es un turno del que no
  // sabemos nada. Y de no saber nada no se deduce permiso para repetirlo.
  if (!resp || resp.ok === false) {
    return desenlace(ESTADO.ERROR, `http ${resp ? resp.status : 'sin respuesta'}`)
  }
  if (!resp.body) return desenlace(ESTADO.ERROR, 'sin cuerpo')

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let terminado = false

  try {
    for (;;) {
      const { done: fin, value } = await reader.read()
      if (fin) break
      buffer += decoder.decode(value, { stream: true })

      // SSE: los eventos se separan por línea en blanco. El último fragmento se queda en el
      // buffer porque un chunk de red puede partir un evento por la mitad — y si el stream
      // acaba ahí, ese bloque está INCOMPLETO y se descarta. Antes daba igual; ahora importa,
      // porque un `done` a medio marco no puede declarar un turno terminado.
      const partes = buffer.split('\n\n')
      buffer = partes.pop() ?? ''

      for (const parte of partes) {
        if (terminado) { eventos.ignoradosTrasDone += 1; continue }

        const linea = parte.split('\n').find((l) => l.startsWith(PREFIJO))
        if (!linea) continue

        let ev
        try {
          ev = JSON.parse(linea.slice(PREFIJO.length))
        } catch {
          // Un marco corrupto rompe la integridad del transcript: a partir de aquí no se
          // sabe qué se perdió. Se corta y se dice. Antes se hacía `continue` en silencio y
          // el turno acababa "sin tokens", que era justo el disparador del reintento.
          return desenlace(ESTADO.ERROR, 'evento malformado')
        }

        if (ev.meta) {
          eventos.meta += 1
          meta = ev.meta
          continue
        }
        if (ev.error) {
          // Terminal ALTERNATIVO. El servidor dice que no pudo completar el turno; antes
          // este caso llegaba como un cierre sin `done` y se leía «se cortó a medias», que
          // es distinto y menos honesto. Nunca se reintenta: el turno pudo ejecutarse entero.
          eventos.error += 1
          terminado = true
          return desenlace(ESTADO.FALLIDO, `${ev.error.code ?? 'error'}/${ev.error.phase ?? '?'}`)
        }
        if (ev.done) {
          eventos.done += 1
          terminado = true
          continue
        }
        if (typeof ev.token === 'string') {
          eventos.token += 1
          // Un token vacío es un evento legítimo del protocolo: cuenta como recibido y no
          // añade texto. Lo que NO puede es decidir el desenlace, ni por su presencia ni por
          // su ausencia.
          if (ev.token) {
            texto += ev.token
            onToken?.(texto, ev.token)
          }
          continue
        }
        if (ev.panel) {
          eventos.panel += 1
          panel = ev.panel
          onPanel?.(ev.panel)
        }
      }
    }
  } catch (e) {
    // El corte deja lo ya escrito como PARCIAL. No se reintenta: el servidor pudo haber
    // ejecutado el turno entero.
    return desenlace(ESTADO.ERROR, `corte: ${e?.message ?? 'desconocido'}`)
  }

  if (!terminado) return desenlace(ESTADO.INCOMPLETO, 'el stream cerró sin done')
  if (!texto && panel === null) return desenlace(ESTADO.VACIO, 'done sin texto ni panel')
  return desenlace(ESTADO.EXITO)
}
