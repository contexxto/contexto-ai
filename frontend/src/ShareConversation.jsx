import { useState } from 'react'
import axios from 'axios'
import { X, Lock, Globe, Check, Copy } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'

const C = {
  bg: '#16151E', panel: '#1E1D28', teal: '#2DBDB6', tealHi: '#5EEAD4',
  text: '#EDEBF2', muted: '#9C99AC', line: 'rgba(45,189,182,.22)',
}

export default function ShareConversation({ sessionId, onClose }) {
  const [access, setAccess] = useState('private')   // 'private' | 'public'
  const [loading, setLoading] = useState(false)
  const [link, setLink] = useState(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState(null)

  async function compartir() {
    setError(null)
    if (access === 'private') { onClose?.(); return }
    setLoading(true)
    try {
      const { data } = await axios.post(`${API_BASE}/api/v1/chat/sessions/${sessionId}/share`, {},
        { headers: apiHeaders() })
      const url = `${window.location.origin}/s/${data.token}`
      setLink(url)
      // Solo en móvil/táctil usamos la hoja nativa (WhatsApp, etc.).
      // En escritorio mostramos el enlace copiable inline (no la bandeja del SO).
      const esTactil = window.matchMedia?.('(pointer: coarse)').matches
      if (esTactil && navigator.share) {
        try { await navigator.share({ title: 'Contexto AI', url }) } catch { /* cancelado */ }
      }
    } catch (e) {
      setError(e?.response?.data?.detail || 'No se pudo crear el enlace. ¿Iniciaste sesión?')
    } finally { setLoading(false) }
  }

  async function copiar() {
    try { await navigator.clipboard.writeText(link); setCopied(true); setTimeout(() => setCopied(false), 1800) } catch { /* ignore */ }
  }

  const Opt = ({ id, icon, title, desc }) => (
    <button onClick={() => setAccess(id)}
      style={{
        display: 'flex', alignItems: 'center', gap: 12, width: '100%', textAlign: 'left',
        padding: '13px 14px', cursor: 'pointer', background: access === id ? 'rgba(45,189,182,.10)' : 'transparent',
        border: 'none', borderBottom: `1px solid ${C.line}`, color: access === id ? C.tealHi : C.text,
      }}>
      {icon}
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 600, fontSize: '.9rem' }}>{title}</div>
        <div style={{ fontSize: '.74rem', color: C.muted }}>{desc}</div>
      </div>
      {access === id && <Check size={18} color={C.teal} />}
    </button>
  )

  return (
    <div onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}
      style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center',
               justifyContent: 'center', padding: 16, background: 'rgba(10,9,16,.72)', backdropFilter: 'blur(6px)' }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 440, position: 'relative', color: C.text,
                 background: `radial-gradient(120% 90% at 30% 0%, ${C.panel} 0%, ${C.bg} 70%)`,
                 border: `1px solid ${C.line}`, borderRadius: 20, padding: '22px 22px 24px',
                 boxShadow: '0 24px 60px rgba(0,0,0,.55)' }}>
        <button onClick={onClose} aria-label="Cerrar"
          style={{ position: 'absolute', top: 14, right: 14, background: 'none', border: 'none', color: C.muted, cursor: 'pointer' }}>
          <X size={18} />
        </button>
        <h2 style={{ margin: '0 0 16px', fontSize: '1.1rem', textAlign: 'center' }}>Compartir conversación</h2>

        <div style={{ fontSize: '.72rem', color: C.muted, letterSpacing: '.5px', marginBottom: 8 }}>QUIÉN TIENE ACCESO</div>
        <div style={{ border: `1px solid ${C.line}`, borderRadius: 14, overflow: 'hidden', marginBottom: 18 }}>
          <Opt id="private" icon={<Lock size={18} />} title="Solo usted" desc="La conversación queda privada" />
          <div style={{ borderBottom: 'none' }}>
            <Opt id="public" icon={<Globe size={18} />} title="Cualquiera con el enlace" desc="Podrán ver la conversación (solo lectura)" />
          </div>
        </div>

        {link ? (
          <div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center',
                          background: 'rgba(255,255,255,.04)', border: `1px solid ${C.line}`,
                          borderRadius: 12, padding: '10px 12px' }}>
              <span style={{ flex: 1, fontSize: '.78rem', color: C.muted, overflow: 'hidden',
                             textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{link}</span>
              <button onClick={copiar} title="Copiar"
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: copied ? C.teal : C.tealHi, display: 'flex' }}>
                {copied ? <Check size={16} /> : <Copy size={16} />}
              </button>
            </div>
            <div style={{ fontSize: '.72rem', color: C.muted, textAlign: 'center', marginTop: 12 }}>
              Enlace creado. Puedes volver a "Solo usted" cuando quieras para revocarlo.
            </div>
          </div>
        ) : (
          <>
            {error && <div style={{ color: '#E0685A', fontSize: '.82rem', marginBottom: 10 }}>⚠️ {error}</div>}
            <button onClick={compartir} disabled={loading}
              style={{ width: '100%', padding: '12px', borderRadius: 12, border: 'none',
                       cursor: loading ? 'default' : 'pointer', fontWeight: 800, fontSize: '.92rem',
                       background: access === 'public' ? `linear-gradient(90deg, ${C.teal}, ${C.tealHi})` : 'rgba(255,255,255,.08)',
                       color: access === 'public' ? '#0E0D13' : C.muted, opacity: loading ? .7 : 1 }}>
              {loading ? 'Creando enlace…' : access === 'public' ? 'Compartir enlace' : 'Mantener privado'}
            </button>
            <div style={{ fontSize: '.72rem', color: C.muted, textAlign: 'center', marginTop: 10 }}>
              Solo se compartirán los mensajes hasta este punto.
            </div>
          </>
        )}
      </div>
    </div>
  )
}
