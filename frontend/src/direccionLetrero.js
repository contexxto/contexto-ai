/**
 * SEC-X2-R0 · la dirección del inmueble del letrero, para la ETIQUETA del botón de corredor.
 *
 * En la conversación del letrero el botón pide SIEMPRE ese inmueble, aunque en pantalla haya
 * otras tarjetas. Para que la persona sepa cuál está pidiendo, el botón debe nombrarlo. La
 * dirección suele llegar desde la página del anuncio (`onChat(info)`), pero no cuando la
 * conversación se reabre desde la barra lateral o la campana: entonces se pide al endpoint
 * público del anuncio, el mismo que usa AnuncioView.
 *
 * Solo es una etiqueta: no decide qué inmueble se pide ni toca la conversación.
 */
import { useEffect, useState } from 'react'
import axios from 'axios'
import { API_BASE, apiHeaders } from './api'
import { canonico } from './pedidoCorredor'

/**
 * Dirección del anuncio de `id`, o `null`. Nunca lanza: si falla, el botón usa una etiqueta
 * inequívoca sin dirección (ver `etiquetaPedido`). `get` se inyecta en las pruebas.
 */
export async function leerDireccionAnuncio(id, get = (url, cfg) => axios.get(url, cfg)) {
  const activo = canonico(id)
  if (!activo) return null
  try {
    const { data } = await get(`${API_BASE}/api/v1/assets/${activo}/anuncio`, { headers: apiHeaders() })
    const d = typeof data?.direccion === 'string' ? data.direccion.trim() : ''
    return d || null
  } catch {
    return null
  }
}

/** La dirección consultada solo vale para el id con que se consultó (nunca la de otro letrero). */
export function direccionVigente(consulta, id) {
  return consulta && consulta.id && consulta.id === canonico(id) ? consulta.direccion : null
}

/**
 * Hook: si hay letrero y su dirección no se conoce (`conocida`), la consulta una vez por id.
 * Una respuesta que llega después de cambiar de letrero se ignora.
 */
export function useDireccionLetrero(id, conocida = null) {
  const [consulta, setConsulta] = useState(null)   // { id, direccion }
  const activo = canonico(id)
  useEffect(() => {
    if (!activo || conocida) return
    let vigente = true
    leerDireccionAnuncio(activo).then((direccion) => {
      if (vigente) setConsulta({ id: activo, direccion })
    })
    return () => { vigente = false }
  }, [activo, conocida])
  return direccionVigente(consulta, activo)
}

/**
 * Mensaje legible cuando el letrero no se puede abrir. El bootstrap responde 404 si el
 * inmueble no existe y 422 si el id no es un UUID: para la persona, las dos son lo mismo.
 */
export function mensajeErrorLetrero(error) {
  const codigo = error?.response?.status
  if (codigo === 404 || codigo === 422) return 'No encontramos ese inmueble.'
  return 'No pudimos abrir la conversación de este inmueble. Reintenta en un momento.'
}
