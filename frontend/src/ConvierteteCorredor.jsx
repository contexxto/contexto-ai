import { useState } from 'react'
import axios from 'axios'
import { X } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'
import sphereLogo from './assets/sphere.svg'

const C = {
  bg: '#16151E', panel: '#1E1D28', teal: '#2DBDB6', tealHi: '#5EEAD4',
  coral: '#E0685A', text: '#EDEBF2', muted: '#9C99AC', line: 'rgba(45,189,182,.25)',
}

const ROLES = [
  { id: 'corredor', label: '🧑‍💼 Soy corredor', desc: 'Publicar y gestionar mis inmuebles' },
  { id: 'inmobiliaria', label: '🏢 Inmobiliaria', desc: 'Agencia con varios corredores' },
]

// Upgrade de rol cliente → corredor/inmobiliaria. El backend ya soporta el cambio
// (POST /auth/profile, ON CONFLICT DO UPDATE); esto es la UI que lo dispara.
export default function ConvierteteCorredor({ onClose, onUpgraded }) {
  const [rol, setRol] = useState('corredor')
  const [inviteCode, setInviteCode] = useState('')
  const [agencyNombre, setAgencyNombre] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const inputStyle = {
    width: '100%', padding: '11px 13px', borderRadius: 12, marginTop: 6,
    background: 'rgba(255,255,255,.04)', border: `1px solid ${C.line}`,
    color: C.text, fontSize: '.92rem', outline: 'none', boxSizing: 'border-box',
  }
  const labelStyle = { fontSize: '.78rem', color: C.muted, fontWeight: 600 }

  async function activar() {
    setError(null); setLoading(true)
    try {
      const body = {
        rol,
        invite_code: rol === 'corredor' && inviteCode ? inviteCode : null,
        agency_nombre: rol === 'inmobiliaria' ? (agencyNombre || null) : null,
      }
      const { data } = await axios.post(`${API_BASE}/api/v1/auth/profile`, body,
        { headers: { 'Content-Type': 'application/json', ...apiHeaders() } })
      onUpgraded?.(data?.rol || rol)
    } catch (err) {
      setError(err?.response?.data?.detail || 'No se pudo activar tu cuenta. Reintenta 🔄')
    } finally { setLoading(false) }
  }

  return (
    <div onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}
      style={{ position: 'fixed', inset: 0, zIndex: 1100, display: 'flex', alignItems: 'center',
               justifyContent: 'center', padding: 16, background: 'rgba(10,9,16,.78)', backdropFilter: 'blur(6px)' }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 420, maxHeight: '92vh', overflowY: 'auto', position: 'relative',
                 background: `radial-gradient(120% 90% at 30% 0%, ${C.panel} 0%, ${C.bg} 70%)`,
                 border: `1px solid ${C.line}`, borderRadius: 22, padding: '26px 24px', color: C.text }}>
        <button onClick={onClose} aria-label="Cerrar"
          style={{ position: 'absolute', top: 14, right: 14, background: 'none', border: 'none', color: C.muted, cursor: 'pointer' }}>
          <X size={18} />
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
          <img src={sphereLogo} width={30} height={30} alt="Contexto AI"
               style={{ filter: 'drop-shadow(0 0 8px rgba(45,189,182,.4))' }} />
          <div style={{ fontWeight: 800, fontSize: '1.05rem' }}>Conviértete en corredor</div>
        </div>
        <p style={{ fontSize: '.82rem', color: C.muted, margin: '0 0 16px' }}>
          Que tu próximo interesado llegue <strong style={{ color: C.tealHi }}>calificado y listo para avanzar</strong> —no un
          “alguien preguntó”, sino alguien cuyo deseo ya encaja con el lugar real y con lo que puede pagar. Convierte porque
          el dato del entorno está verificado. Publica tu inmueble, genera el QR de tu letrero y tu agente atiende 24/7.
        </p>

        <label style={labelStyle}>¿Cómo publicarás?</label>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
          {ROLES.map((r) => (
            <button type="button" key={r.id} onClick={() => setRol(r.id)}
              style={{
                textAlign: 'left', padding: '11px 13px', borderRadius: 12, cursor: 'pointer',
                background: rol === r.id ? 'rgba(45,189,182,.14)' : 'rgba(255,255,255,.03)',
                border: `1px solid ${rol === r.id ? C.teal : C.line}`, color: C.text,
              }}>
              <div style={{ fontWeight: 700, fontSize: '.9rem' }}>{r.label}</div>
              <div style={{ fontSize: '.74rem', color: C.muted }}>{r.desc}</div>
            </button>
          ))}
        </div>

        {rol === 'corredor' && (
          <div style={{ marginTop: 14 }}>
            <label style={labelStyle}>Código de invitación (opcional)</label>
            <input value={inviteCode} onChange={(e) => setInviteCode(e.target.value)}
                   placeholder="Si te unes a una inmobiliaria" style={inputStyle} />
            <div style={{ fontSize: '.72rem', color: C.muted, marginTop: 4 }}>
              Déjalo vacío si eres corredor independiente.
            </div>
          </div>
        )}
        {rol === 'inmobiliaria' && (
          <div style={{ marginTop: 14 }}>
            <label style={labelStyle}>Nombre de la inmobiliaria</label>
            <input value={agencyNombre} onChange={(e) => setAgencyNombre(e.target.value)}
                   placeholder="Ej. Inmobiliaria Andina" style={inputStyle} />
          </div>
        )}

        {error && <div style={{ color: C.coral, fontSize: '.82rem', marginTop: 14 }}>⚠️ {error}</div>}

        <button onClick={activar} disabled={loading}
          style={{
            marginTop: 18, padding: '12px', borderRadius: 12, border: 'none', width: '100%',
            cursor: loading ? 'default' : 'pointer', fontWeight: 800, fontSize: '.92rem',
            background: `linear-gradient(90deg, ${C.teal}, ${C.tealHi})`, color: '#0E0D13',
            opacity: loading ? 0.7 : 1,
          }}>
          {loading ? 'Activando…' : 'Activar mi cuenta'}
        </button>
      </div>
    </div>
  )
}
