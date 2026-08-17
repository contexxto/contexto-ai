import { useState } from 'react'
import axios from 'axios'
import { BellRing, Check, X } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'

// La PUERTA SUAVE — "¿te aviso cuando aparezca algo así?".
//
// Este componente NO decide cuándo aparecer: lo decide el motor (app/puerta.py) y llega
// como directiva en el panel del turno, igual que map_seed. Aquí solo se pinta. Que la
// decisión viva en el backend es lo que hace imposible que la oferta se vuelva insistente
// por su cuenta.
//
// Las reglas de no-presión que se sostienen AQUÍ (las demás son del motor):
//   · Nunca como condición — esto va DEBAJO de la respuesta y del panel, que se ven
//     completos aunque nadie deje nada. No tapa, no bloquea, no es un modal.
//   · El "no" se respeta y se acabó — un clic, sin re-preguntar y sin "¿seguro?".
//   · La promesa se muestra literal, tal como la manda el backend: es el límite de lo
//     que se va a hacer con el correo, y no lo redacta el modelo.
const C = {
  panel: 'var(--surface-1)', teal: 'var(--teal)', tealHi: 'var(--teal-bright)',
  accent: 'var(--accent)', text: 'var(--text)', muted: 'var(--text-mid)',
  line: 'var(--border)', coral: 'var(--coral)',
}

export default function PuertaAlerta({ puerta, sessionId, activoId }) {
  const [estado, setEstado] = useState('abierta')   // abierta | enviando | lista | fuera
  const [email, setEmail] = useState('')
  const [error, setError] = useState(null)

  if (!puerta || estado === 'fuera') return null

  if (estado === 'lista') {
    return (
      <div style={{ marginTop: 10, display: 'inline-flex', alignItems: 'center', gap: 7,
                    padding: '8px 12px', borderRadius: 10, background: 'rgba(45,189,182,.10)',
                    border: `1px solid ${C.line}`, color: C.accent, fontSize: '.78rem',
                    fontWeight: 700 }}>
        <Check size={14} /> Listo. {puerta.promesa}
      </div>
    )
  }

  async function enviar(e) {
    e.preventDefault()
    if (!email.trim() || estado === 'enviando') return
    setEstado('enviando'); setError(null)
    try {
      await axios.post(`${API_BASE}/api/v1/alertas`, {
        session_id: sessionId,
        email: email.trim(),
        // El criterio y el motivo viajan tal cual los decidió el motor: la demanda queda
        // registrada con lo que la persona pidió, no con lo que el frontend interprete.
        criterio: puerta.criterio_raw || {},
        criterio_texto: puerta.detalle || null,
        hubo_match: puerta.motivo !== 'callejon_honesto',
        motivo: puerta.motivo || null,
        activo_id: activoId || null,
      }, { headers: apiHeaders() })
      setEstado('lista')
    } catch (err) {
      setEstado('abierta')
      setError(err?.response?.data?.detail
        || 'No pudimos guardar tu aviso ahora mismo. Reintenta en un momento.')
    }
  }

  return (
    <div style={{ marginTop: 12, padding: '12px 14px', borderRadius: 12,
                  background: C.panel, border: `1px solid ${C.line}` }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 9 }}>
        <BellRing size={16} color={C.teal} style={{ flexShrink: 0, marginTop: 2 }} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ color: C.text, fontSize: '.86rem', fontWeight: 700, lineHeight: 1.3 }}>
            {puerta.titulo}
          </div>
          {puerta.detalle && (
            <div style={{ color: C.muted, fontSize: '.74rem', marginTop: 3, lineHeight: 1.35 }}>
              {puerta.detalle}
            </div>
          )}
          <form onSubmit={enviar}
                style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 10 }}>
            <input
              type="email" inputMode="email" autoComplete="email" required
              value={email} onChange={(e) => setEmail(e.target.value)}
              placeholder="tu@correo.com" aria-label="Tu correo para el aviso"
              style={{ flex: '1 1 190px', minWidth: 0, padding: '8px 11px', borderRadius: 9,
                       background: 'var(--bg)', border: `1px solid ${C.line}`, color: C.text,
                       fontSize: '.8rem', outline: 'none' }} />
            <button type="submit" disabled={estado === 'enviando'}
              style={{ padding: '8px 14px', borderRadius: 9, border: 'none', cursor: 'pointer',
                       background: C.teal, color: '#0E0D13', fontSize: '.8rem', fontWeight: 800,
                       opacity: estado === 'enviando' ? .6 : 1 }}>
              {estado === 'enviando' ? 'Guardando…' : 'Avísame'}
            </button>
            {/* El "no" es un clic y se acabó: sin "¿seguro?", sin segunda redacción. */}
            <button type="button" onClick={() => setEstado('fuera')}
              aria-label="No, gracias"
              style={{ padding: '8px 10px', borderRadius: 9, cursor: 'pointer',
                       background: 'transparent', border: `1px solid ${C.line}`,
                       color: C.muted, fontSize: '.78rem', fontWeight: 600,
                       display: 'inline-flex', alignItems: 'center', gap: 5 }}>
              <X size={13} /> Ahora no
            </button>
          </form>
          {error && (
            <div role="alert" style={{ color: C.coral, fontSize: '.73rem', marginTop: 7 }}>
              {error}
            </div>
          )}
          <div style={{ color: C.muted, fontSize: '.68rem', marginTop: 8, lineHeight: 1.35 }}>
            {puerta.promesa}
          </div>
        </div>
      </div>
    </div>
  )
}
