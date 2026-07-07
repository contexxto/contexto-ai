import { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import { Send, Sparkles } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'
import { renderMarkdown } from './markdown'

const C = {
  bg: '#16151E', panel: '#1E1D28', teal: '#2DBDB6', tealHi: '#5EEAD4',
  text: '#EDEBF2', muted: '#9C99AC', line: 'rgba(45,189,182,.20)',
}

const SUGERENCIAS = [
  '¿Cuántos interesados calientes tengo?',
  '¿A quién debería retomar?',
  '¿Cómo va mi embudo?',
]

// CRM Vivo (Fase 1): el corredor le habla a su CRM. Request/response contra el agente
// del corredor (/assets/crm/chat) — las cifras las computa el motor, el LLM narra.
export default function CRMChat() {
  const [msgs, setMsgs] = useState([])   // { autor: 'corredor'|'crm', texto }
  const [texto, setTexto] = useState('')
  const [enviando, setEnviando] = useState(false)
  const [error, setError] = useState(null)
  const [sid] = useState(() => `crm-${crypto?.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`}`)
  const finRef = useRef(null)

  useEffect(() => { finRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, enviando])

  async function enviar(t0) {
    const t = (t0 ?? texto).trim()
    if (!t || enviando) return
    setTexto(''); setError(null); setEnviando(true)
    setMsgs(prev => [...prev, { autor: 'corredor', texto: t }])
    try {
      const { data } = await axios.post(`${API_BASE}/api/v1/assets/crm/chat`,
        { message: t, session_id: sid }, { headers: apiHeaders() })
      setMsgs(prev => [...prev, { autor: 'crm', texto: data.reply || 'Sin respuesta.' }])
    } catch {
      setError('No se pudo consultar el CRM. Intenta de nuevo.')
    } finally {
      setEnviando(false)
    }
  }

  const bubble = (autor) => autor === 'corredor'
    ? { align: 'flex-end', bg: 'linear-gradient(90deg,#2DBDB6,#5EEAD4)', color: '#0E0D13', lbl: 'Tú' }
    : { align: 'flex-start', bg: 'rgba(255,255,255,.05)', color: C.text, lbl: 'Tu CRM' }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10, flexShrink: 0 }}>
        <Sparkles size={18} color={C.teal} />
        <div style={{ fontWeight: 800, fontSize: '1rem' }}>Pregúntale a tu CRM</div>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, minHeight: 0, padding: '4px 2px' }}>
        {msgs.length === 0 && (
          <div style={{ color: C.muted, fontSize: '.82rem', lineHeight: 1.5, padding: '8px 2px' }}>
            Pregúntame por tu cartera — con datos reales, sin inventar. Por ejemplo:
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 10 }}>
              {SUGERENCIAS.map(s => (
                <button key={s} onClick={() => enviar(s)}
                  style={{ fontSize: '.72rem', padding: '6px 11px', borderRadius: 999, cursor: 'pointer',
                           background: 'rgba(45,189,182,.08)', border: `1px solid ${C.line}`, color: C.tealHi }}>
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m, i) => {
          const b = bubble(m.autor)
          return (
            <div key={i} style={{ alignSelf: b.align, maxWidth: '86%' }}>
              <div style={{ fontSize: '.6rem', color: C.muted, marginBottom: 2, textAlign: b.align === 'flex-end' ? 'right' : 'left' }}>{b.lbl}</div>
              {m.autor === 'crm'
                ? <div className="crm-md" style={{ background: b.bg, color: b.color, padding: '8px 12px', borderRadius: 14, fontSize: '.84rem', lineHeight: 1.45 }}
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(m.texto) }} />
                : <div style={{ background: b.bg, color: b.color, padding: '8px 12px', borderRadius: 14, fontSize: '.84rem', lineHeight: 1.45, whiteSpace: 'pre-wrap' }}>
                    {m.texto}
                  </div>}
            </div>
          )
        })}
        {enviando && <div style={{ alignSelf: 'flex-start', color: C.muted, fontSize: '.78rem', padding: '2px 4px' }}>Pensando…</div>}
        <div ref={finRef} />
      </div>

      {error && <div style={{ color: '#E0685A', fontSize: '.76rem', textAlign: 'center', marginTop: 8, flexShrink: 0 }}>⚠️ {error}</div>}

      <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginTop: 10, flexShrink: 0,
                    background: 'rgba(20,44,43,.5)', border: `1px solid ${C.line}`, borderRadius: 20, padding: 7 }}>
        <textarea value={texto} onChange={e => setTexto(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); enviar() } }}
          placeholder="Pregúntale a tu CRM…" rows={1}
          style={{ flex: 1, background: 'none', border: 'none', outline: 'none', color: C.text, fontSize: '.88rem',
                   resize: 'none', maxHeight: 100, fontFamily: 'inherit', padding: '6px 8px' }} />
        <button onClick={() => enviar()} disabled={!texto.trim() || enviando}
          style={{ width: 38, height: 38, borderRadius: 999, flexShrink: 0, border: 'none',
                   cursor: texto.trim() ? 'pointer' : 'default', display: 'flex', alignItems: 'center', justifyContent: 'center',
                   background: texto.trim() ? `linear-gradient(90deg,${C.teal},${C.tealHi})` : 'rgba(45,189,182,.12)', color: '#0E0D13' }}>
          <Send size={16} />
        </button>
      </div>
    </div>
  )
}
