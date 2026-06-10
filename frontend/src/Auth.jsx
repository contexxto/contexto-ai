import { useState } from 'react'
import { X } from 'lucide-react'
import { supabase } from './supabaseClient'
import sphereLogo from './assets/sphere.svg'

const API_BASE = import.meta.env.VITE_API_URL ?? ''

const ROLES = [
  { id: 'cliente',      label: '👤 Busco inmueble', desc: 'Cliente — buscar y consultar' },
  { id: 'corredor',     label: '🧑‍💼 Soy corredor',   desc: 'Publicar y gestionar mis inmuebles' },
  { id: 'inmobiliaria', label: '🏢 Inmobiliaria',     desc: 'Agencia con varios corredores' },
]

const C = {
  bg: '#16151E', panel: '#1E1D28', teal: '#2DBDB6', tealHi: '#5EEAD4',
  coral: '#E0685A', text: '#EDEBF2', muted: '#9C99AC', line: 'rgba(45,189,182,.25)',
}

export default function Auth({ onClose, onAuthed }) {
  const [mode, setMode] = useState('login')      // 'login' | 'signup'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [nombre, setNombre] = useState('')
  const [rol, setRol] = useState('cliente')
  const [inviteCode, setInviteCode] = useState('')
  const [agencyNombre, setAgencyNombre] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [info, setInfo] = useState(null)

  const inputStyle = {
    width: '100%', padding: '11px 13px', borderRadius: 12, marginTop: 6,
    background: 'rgba(255,255,255,.04)', border: `1px solid ${C.line}`,
    color: C.text, fontSize: '.92rem', outline: 'none', boxSizing: 'border-box',
  }
  const labelStyle = { fontSize: '.78rem', color: C.muted, fontWeight: 600 }

  async function setProfile(token) {
    // Registra rol/nombre en nuestro backend (corredor se une por invite_code;
    // inmobiliaria crea su agencia).
    await fetch(`${API_BASE}/api/v1/auth/profile`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        rol,
        nombre: nombre || null,
        invite_code: rol === 'corredor' && inviteCode ? inviteCode : null,
        agency_nombre: rol === 'inmobiliaria' ? (agencyNombre || nombre || null) : null,
      }),
    })
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null); setInfo(null)
    if (!supabase) { setError('Autenticación no disponible (configuración pendiente).'); return }
    setLoading(true)
    try {
      if (mode === 'login') {
        const { data, error } = await supabase.auth.signInWithPassword({ email, password })
        if (error) throw error
        onAuthed?.(data.session)
        onClose?.()
      } else {
        const { data, error } = await supabase.auth.signUp({ email, password })
        if (error) throw error
        const token = data.session?.access_token
        if (token) {
          await setProfile(token)
          onAuthed?.(data.session)
          onClose?.()
        } else {
          // Email confirmation activada → no hay sesión inmediata.
          setInfo('Cuenta creada. Revisa tu correo para confirmar y luego inicia sesión.')
          setMode('login')
        }
      }
    } catch (err) {
      setError(err?.message || 'No se pudo completar la acción.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000, display: 'flex',
        alignItems: 'center', justifyContent: 'center', padding: 16,
        background: 'rgba(10,9,16,.72)', backdropFilter: 'blur(6px)',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '100%', maxWidth: 420,
          background: `radial-gradient(120% 90% at 30% 0%, ${C.panel} 0%, ${C.bg} 70%)`,
          border: `1px solid ${C.line}`, borderRadius: 22, padding: '26px 24px',
          boxShadow: '0 24px 60px rgba(0,0,0,.55), 0 0 40px rgba(45,189,182,.12)',
          color: C.text, position: 'relative', maxHeight: '92vh', overflowY: 'auto',
        }}
      >
        <button onClick={onClose} aria-label="Cerrar"
          style={{ position: 'absolute', top: 14, right: 14, background: 'none',
                   border: 'none', color: C.muted, cursor: 'pointer' }}>
          <X size={18} />
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
          <img src={sphereLogo} width={34} height={34} alt="Contexto AI"
               style={{ filter: 'drop-shadow(0 0 8px rgba(45,189,182,.4))' }} />
          <div style={{ fontWeight: 800, fontSize: '1.1rem' }}>
            Contexto <span style={{ color: C.teal }}>AI</span>
          </div>
        </div>
        <p style={{ fontSize: '.82rem', color: C.muted, margin: '0 0 18px' }}>
          {mode === 'login' ? 'Inicia sesión para guardar tus conversaciones.' : 'Crea tu cuenta en segundos.'}
        </p>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: 6, marginBottom: 18, background: 'rgba(255,255,255,.04)',
                      borderRadius: 12, padding: 4 }}>
          {['login', 'signup'].map((m) => (
            <button key={m} onClick={() => { setMode(m); setError(null); setInfo(null) }}
              style={{
                flex: 1, padding: '8px 0', borderRadius: 9, border: 'none', cursor: 'pointer',
                fontSize: '.85rem', fontWeight: 700,
                background: mode === m ? C.teal : 'transparent',
                color: mode === m ? '#0E0D13' : C.muted,
              }}>
              {m === 'login' ? 'Entrar' : 'Crear cuenta'}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {mode === 'signup' && (
            <div>
              <label style={labelStyle}>Nombre</label>
              <input value={nombre} onChange={(e) => setNombre(e.target.value)}
                     placeholder="Tu nombre" style={inputStyle} />
            </div>
          )}
          <div>
            <label style={labelStyle}>Correo</label>
            <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                   placeholder="tucorreo@ejemplo.com" style={inputStyle} />
          </div>
          <div>
            <label style={labelStyle}>Contraseña</label>
            <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)}
                   placeholder="••••••••" minLength={6} style={inputStyle} />
          </div>

          {mode === 'signup' && (
            <div>
              <label style={labelStyle}>¿Cómo usarás Contexto?</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
                {ROLES.map((r) => (
                  <button type="button" key={r.id} onClick={() => setRol(r.id)}
                    style={{
                      textAlign: 'left', padding: '10px 12px', borderRadius: 12, cursor: 'pointer',
                      background: rol === r.id ? 'rgba(45,189,182,.14)' : 'rgba(255,255,255,.03)',
                      border: `1px solid ${rol === r.id ? C.teal : C.line}`, color: C.text,
                    }}>
                    <div style={{ fontWeight: 700, fontSize: '.9rem' }}>{r.label}</div>
                    <div style={{ fontSize: '.74rem', color: C.muted }}>{r.desc}</div>
                  </button>
                ))}
              </div>

              {rol === 'corredor' && (
                <div style={{ marginTop: 12 }}>
                  <label style={labelStyle}>Código de invitación (opcional)</label>
                  <input value={inviteCode} onChange={(e) => setInviteCode(e.target.value)}
                         placeholder="Si te unes a una inmobiliaria" style={inputStyle} />
                  <div style={{ fontSize: '.72rem', color: C.muted, marginTop: 4 }}>
                    Déjalo vacío si eres corredor independiente.
                  </div>
                </div>
              )}
              {rol === 'inmobiliaria' && (
                <div style={{ marginTop: 12 }}>
                  <label style={labelStyle}>Nombre de la inmobiliaria</label>
                  <input value={agencyNombre} onChange={(e) => setAgencyNombre(e.target.value)}
                         placeholder="Ej. Inmobiliaria Andina" style={inputStyle} />
                </div>
              )}
            </div>
          )}

          {error && <div style={{ color: C.coral, fontSize: '.82rem' }}>⚠️ {error}</div>}
          {info && <div style={{ color: C.tealHi, fontSize: '.82rem' }}>✅ {info}</div>}

          <button type="submit" disabled={loading}
            style={{
              marginTop: 4, padding: '12px', borderRadius: 12, border: 'none',
              cursor: loading ? 'default' : 'pointer', fontWeight: 800, fontSize: '.92rem',
              background: `linear-gradient(90deg, ${C.teal}, ${C.tealHi})`, color: '#0E0D13',
              opacity: loading ? 0.7 : 1,
            }}>
            {loading ? 'Procesando…' : mode === 'login' ? 'Entrar' : 'Crear cuenta'}
          </button>
        </form>
      </div>
    </div>
  )
}
