import { useState } from 'react'
import { Handshake } from 'lucide-react'
import {
  ETIQUETA_ELEGIR, PREGUNTA_ELEGIR, clicEnPedido, etiquetaPedido, etiquetasDeOpciones, opcionesDelPedido,
} from './pedidoCorredor'

// SEC-X2-R0 · el control «Hablar con el corredor». Presentacional: NO guarda qué inmueble se
// eligió. El inmueble es el argumento de UN acto —el clic— y viaja en `onPedir(id)`.
// Qué hace cada clic lo decide `clicEnPedido` (pedidoCorredor.js), probado sin jsdom.
// Estado local solo de interfaz: si el selector está desplegado y si hay un envío en curso
// (para que un doble clic no pida dos veces).

const BOTON = {
  display: 'flex', alignItems: 'center', gap: 7, padding: '7px 14px',
  borderRadius: 999, cursor: 'pointer', fontSize: '.78rem', fontWeight: 600,
  background: 'rgba(45,189,182,.10)', border: '1px solid rgba(45,189,182,.3)', color: 'var(--teal-text)',
}
const CHIP = { ...BOTON, padding: '5px 11px', fontSize: '.74rem' }
const CANCELAR = {
  padding: '5px 11px', borderRadius: 999, cursor: 'pointer', fontSize: '.72rem', fontWeight: 600,
  background: 'transparent', border: '1px solid var(--border)', color: 'var(--text-muted)',
}

export default function PedirCorredor({ letrero, direccionLetrero, candidatos, onPedir }) {
  const [eligiendo, setEligiendo] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const { modo, opciones, otras } = opcionesDelPedido({ letrero, direccionLetrero, candidatos })

  // Sin inmueble no hay a quién pedir: no se muestra nada (falla cerrado).
  if (modo === 'ninguno') return null

  const clic = async (evento) => {
    if (enviando) return
    const r = clicEnPedido({ modo, opciones, eligiendo }, evento)
    setEligiendo(r.eligiendo)
    if (!r.pedir) return
    setEnviando(true)
    try { await onPedir(r.pedir) } finally { setEnviando(false) }
  }

  // Letrero, o un único inmueble en pantalla: una sola opción, con una etiqueta que no se
  // puede confundir con otra tarjeta (ver `etiquetaPedido`).
  if (modo === 'letrero' || modo === 'uno') {
    return (
      <button onClick={() => clic({ tipo: 'principal' })} disabled={enviando} style={BOTON}>
        <Handshake size={14} />
        {etiquetaPedido(opciones[0], { modo, otras })}
      </button>
    )
  }

  // Dos o más: la persona elige. Desplegar el selector no envía nada; solo un chip lo hace.
  if (!eligiendo) {
    return (
      <button onClick={() => clic({ tipo: 'principal' })} style={BOTON}>
        <Handshake size={14} />
        {ETIQUETA_ELEGIR}
      </button>
    )
  }
  const etiquetas = etiquetasDeOpciones(opciones)
  return (
    <div role="group" aria-label={PREGUNTA_ELEGIR}
      style={{ flexBasis: '100%', display: 'flex', gap: 6, justifyContent: 'center', flexWrap: 'wrap',
               alignItems: 'center' }}>
      <span style={{ fontSize: '.74rem', color: 'var(--text-muted)' }}>{PREGUNTA_ELEGIR}</span>
      {opciones.map((o, i) => (
        <button key={o.id} onClick={() => clic({ tipo: 'chip', id: o.id })} disabled={enviando} style={CHIP}>
          {etiquetas[i]}
        </button>
      ))}
      <button onClick={() => clic({ tipo: 'cancelar' })} style={CANCELAR}>Cancelar</button>
    </div>
  )
}
