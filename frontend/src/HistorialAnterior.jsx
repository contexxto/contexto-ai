import { History } from 'lucide-react'
import { NOTA_HISTORIAL, TITULO_HISTORIAL, resumenHistorial } from './historicosHandoff'

// SEC-X2-C1 · el historial anterior del handoff, aparte y de SOLO LECTURA. Presentacional: recibe
// los mensajes ya saneados (`historicosDe`) y no ofrece ninguna acción —ni responder, ni reabrir, ni
// llamar al servidor—. Para volver a hablar con un corredor hace falta una solicitud nueva y explícita
// (`PedirCorredor`). No dice a qué inmueble pertenecía la conversación ni quién era el corredor.

const CAJA = {
  margin: '0 0 16px', padding: '12px 14px', borderRadius: 14,
  background: 'var(--surface-1)', border: '1px dashed var(--border)', color: 'var(--text-muted)',
  fontSize: '.8rem',
}
const LINEA = { margin: '6px 0 0', lineHeight: 1.45, color: 'var(--text)' }

export default function HistorialAnterior({ mensajes }) {
  if (!Array.isArray(mensajes) || mensajes.length === 0) return null
  return (
    <section aria-label={TITULO_HISTORIAL} style={CAJA}>
      <div style={{ fontWeight: 700, color: 'var(--text)' }}>
        <History size={13} style={{ verticalAlign: '-2px', marginRight: 6 }} />
        {TITULO_HISTORIAL}
      </div>
      <p style={{ margin: '4px 0 8px' }}>{NOTA_HISTORIAL}</p>
      <details>
        <summary style={{ cursor: 'pointer', fontWeight: 600 }}>{resumenHistorial(mensajes.length)}</summary>
        {mensajes.map((m) => (
          <p key={m.id} style={LINEA}>
            <b>{m.etiqueta}{m.fecha ? ` · ${m.fecha}` : ''}:</b> {m.texto}
          </p>
        ))}
      </details>
    </section>
  )
}
