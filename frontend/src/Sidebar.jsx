import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'
import { Plus, Pin, PinOff, Pencil, Trash2, MoreHorizontal, MessageSquare, LogIn, LogOut, Home, Map, Shield } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'

const C = {
  bg: '#0B0A10', border: '#2E2D3A', text: '#F0ECE6', dim: '#A8A3B3', accent: '#2DBDB6', active: '#1E1D28',
}

// Quita el bloque interno "[Contexto del sistema: …]" que pudo colarse al
// autogenerar el título desde el primer mensaje (ubicación/reglas del agente).
function tituloLimpio(t) {
  if (!t) return 'Conversación'
  const i = t.indexOf('[Contexto del sistema')
  return (i === -1 ? t : t.slice(0, i)).trim() || 'Conversación'
}

export default function Sidebar({ sessionId, onSelect, onNew, reloadKey, user, onLogin, onLogout, onPublish, onMap, onReview }) {
  const [sessions, setSessions] = useState([])
  const [menuId, setMenuId] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [editValue, setEditValue] = useState('')
  const [porEliminar, setPorEliminar] = useState(null)  // confirmación propia (no confirm() nativo)
  const editRef = useRef(null)

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/api/v1/chat/sessions?limit=50`, { headers: apiHeaders() })
      setSessions(data.sessions || [])
    } catch (e) { console.error('No se pudo cargar la lista de conversaciones:', e); setSessions([]) }
  }, [])

  // Recarga al montar y cuando cambia reloadKey (sesión activa / nuevos mensajes)
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { load() }, [load, reloadKey])

  // Cerrar menú al hacer click fuera
  useEffect(() => {
    const close = () => setMenuId(null)
    if (menuId) { window.addEventListener('click', close); return () => window.removeEventListener('click', close) }
  }, [menuId])

  useEffect(() => { if (editingId && editRef.current) editRef.current.focus() }, [editingId])

  async function commitRename(id) {
    const titulo = editValue.trim()
    setEditingId(null)
    if (!titulo) return
    try {
      await axios.patch(`${API_BASE}/api/v1/chat/sessions/${id}`, { titulo }, { headers: apiHeaders() })
      await load()
    } catch (e) { console.error('No se pudo renombrar la conversación:', e); alert('No se pudo renombrar la conversación.') }
  }

  async function togglePin(s) {
    setMenuId(null)
    try {
      await axios.patch(`${API_BASE}/api/v1/chat/sessions/${s.session_id}`, { pinned: !s.pinned }, { headers: apiHeaders() })
      await load()
    } catch (e) { console.error('No se pudo fijar/desfijar:', e); alert('No se pudo fijar/desfijar la conversación.') }
  }

  function remove(s) { setMenuId(null); setPorEliminar(s) }

  async function confirmarEliminar() {
    const s = porEliminar
    setPorEliminar(null)
    if (!s) return
    try {
      await axios.delete(`${API_BASE}/api/v1/chat/sessions/${s.session_id}`, { headers: apiHeaders() })
      await load()
      if (s.session_id === sessionId) onNew()
    } catch (e) { console.error('No se pudo eliminar la conversación:', e) }
  }

  const pinned = sessions.filter(s => s.pinned)
  const recientes = sessions.filter(s => !s.pinned)

  const Row = (s) => {
    const active = s.session_id === sessionId
    const editing = s.session_id === editingId
    return (
      <div key={s.session_id}
        onClick={() => !editing && onSelect(s.session_id)}
        style={{
          position: 'relative', display: 'flex', alignItems: 'center', gap: 8,
          padding: '8px 10px', borderRadius: 8, cursor: 'pointer', marginBottom: 2,
          background: active ? C.active : 'transparent',
        }}
        onMouseEnter={e => { if (!active) e.currentTarget.style.background = '#1E1D28' }}
        onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}>
        <MessageSquare size={14} color={C.dim} style={{ flexShrink: 0 }} />
        {editing ? (
          <input ref={editRef} value={editValue}
            onChange={e => setEditValue(e.target.value)}
            onBlur={() => commitRename(s.session_id)}
            onKeyDown={e => { if (e.key === 'Enter') commitRename(s.session_id); if (e.key === 'Escape') setEditingId(null) }}
            onClick={e => e.stopPropagation()}
            style={{ flex: 1, background: '#16151E', color: C.text, border: `1px solid ${C.accent}`, borderRadius: 5, padding: '3px 6px', fontSize: '.84rem' }} />
        ) : (
          <span style={{ flex: 1, fontSize: '.84rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', color: C.text }}>
            {s.pinned && <Pin size={11} color={C.accent} style={{ marginRight: 4, verticalAlign: 'middle' }} />}
            {tituloLimpio(s.titulo)}
          </span>
        )}
        {!editing && (
          <button title="Opciones"
            onClick={e => { e.stopPropagation(); setMenuId(menuId === s.session_id ? null : s.session_id) }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: C.dim, padding: 2, display: 'flex' }}>
            <MoreHorizontal size={16} />
          </button>
        )}
        {menuId === s.session_id && (
          <div onClick={e => e.stopPropagation()}
            style={{
              position: 'absolute', right: 6, top: '100%', zIndex: 30, width: 160,
              background: '#1E1D28', border: `1px solid ${C.border}`, borderRadius: 8,
              boxShadow: '0 8px 24px rgba(0,0,0,.5)', overflow: 'hidden',
            }}>
            <MenuItem icon={<Pencil size={14} />} label="Renombrar"
              onClick={() => { setEditingId(s.session_id); setEditValue(tituloLimpio(s.titulo)); setMenuId(null) }} />
            <MenuItem icon={s.pinned ? <PinOff size={14} /> : <Pin size={14} />}
              label={s.pinned ? 'Desfijar' : 'Fijar'} onClick={() => togglePin(s)} />
            <MenuItem icon={<Trash2 size={14} />} label="Eliminar" danger onClick={() => remove(s)} />
          </div>
        )}
      </div>
    )
  }

  return (
    <div style={{
      width: 264, flexShrink: 0, height: '100%', background: C.bg,
      borderRight: `1px solid ${C.border}`, display: 'flex', flexDirection: 'column', padding: 10,
    }}>
      <button onClick={onNew}
        style={{
          display: 'flex', alignItems: 'center', gap: 8, width: '100%', justifyContent: 'center',
          padding: '9px 12px', borderRadius: 8, cursor: 'pointer', marginBottom: 12,
          background: C.accent, color: '#fff', border: 'none', fontSize: '.85rem', fontWeight: 600,
        }}>
        <Plus size={16} /> Nuevo chat
      </button>

      {/* Acciones (estilo Claude: arriba a la izquierda) */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginBottom: 10 }}>
        <NavItem icon={<Home size={16} />} label="Mis publicaciones" onClick={onPublish} />
        <NavItem icon={<Map size={16} />} label="Mapa" onClick={onMap} />
        {(user?.rol === 'corredor' || user?.rol === 'inmobiliaria') && (
          <NavItem icon={<Shield size={16} />} label="Revisión" onClick={onReview} />
        )}
      </div>

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {sessions.length === 0 && (
          <div style={{ color: C.dim, fontSize: '.8rem', padding: '8px 4px' }}>Sin conversaciones aún.</div>
        )}
        {pinned.length > 0 && (
          <>
            <div style={sectionLabel}>Fijadas</div>
            {pinned.map(Row)}
            <div style={{ height: 10 }} />
          </>
        )}
        {recientes.length > 0 && <div style={sectionLabel}>Recientes</div>}
        {recientes.map(Row)}
      </div>

      {/* Cuenta (al fondo, estilo Claude) */}
      <div style={{ borderTop: `1px solid ${C.border}`, paddingTop: 10, marginTop: 6 }}>
        {user ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <div style={{
              width: 30, height: 30, borderRadius: '50%', flexShrink: 0,
              background: 'linear-gradient(135deg,#2DBDB6,#E0685A)', color: '#0B0A10',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontWeight: 800, fontSize: '.85rem',
            }}>
              {(user.email || '?').trim()[0]?.toUpperCase()}
            </div>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontSize: '.78rem', color: C.text, overflow: 'hidden',
                            textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user.email}</div>
              {user.rol && (
                <div style={{ fontSize: '.68rem', color: C.dim, textTransform: 'capitalize' }}>{user.rol}</div>
              )}
            </div>
            <button onClick={onLogout} title="Cerrar sesión"
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: C.dim, display: 'flex', padding: 4 }}>
              <LogOut size={16} />
            </button>
          </div>
        ) : (
          <button onClick={onLogin}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, width: '100%',
              padding: '9px 12px', borderRadius: 8, cursor: 'pointer',
              background: 'transparent', border: `1px solid ${C.accent}`, color: C.accent,
              fontSize: '.85rem', fontWeight: 600,
            }}>
            <LogIn size={15} /> Entrar
          </button>
        )}
      </div>

      {/* Confirmación propia de borrado (en lugar del confirm() nativo del navegador) */}
      {porEliminar && (
        <div onClick={() => setPorEliminar(null)}
          style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,.55)',
                   display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
          <div onClick={e => e.stopPropagation()}
            style={{ width: 'min(360px, 100%)', background: '#16151E', border: `1px solid ${C.border}`,
                     borderRadius: 14, padding: '18px', boxShadow: '0 12px 40px rgba(0,0,0,.6)',
                     fontFamily: "'Plus Jakarta Sans',sans-serif" }}>
            <div style={{ color: C.text, fontWeight: 700, fontSize: '.95rem', marginBottom: 6 }}>Eliminar conversación</div>
            <div style={{ color: C.dim, fontSize: '.84rem', lineHeight: 1.5, marginBottom: 16 }}>
              Se quitará <b style={{ color: C.text }}>"{tituloLimpio(porEliminar.titulo)}"</b> de tu lista.
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button onClick={() => setPorEliminar(null)}
                style={{ padding: '8px 14px', borderRadius: 8, cursor: 'pointer', fontSize: '.84rem',
                         background: 'transparent', border: `1px solid ${C.border}`, color: C.text }}>Cancelar</button>
              <button onClick={confirmarEliminar}
                style={{ padding: '8px 14px', borderRadius: 8, cursor: 'pointer', fontSize: '.84rem', fontWeight: 600,
                         background: '#E0685A', border: 'none', color: '#0E0D13' }}>Eliminar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function NavItem({ icon, label, onClick }) {
  return (
    <button onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '9px 10px',
        borderRadius: 8, cursor: 'pointer', background: 'none', border: 'none',
        color: '#A8A3B3', fontSize: '.85rem', textAlign: 'left', transition: 'all .12s',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = '#1E1D28'; e.currentTarget.style.color = '#F0ECE6' }}
      onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = '#A8A3B3' }}>
      {icon} {label}
    </button>
  )
}

function MenuItem({ icon, label, onClick, danger }) {
  return (
    <button onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '8px 12px',
        background: 'none', border: 'none', cursor: 'pointer', fontSize: '.82rem',
        color: danger ? '#E0685A' : '#F0ECE6', textAlign: 'left',
      }}
      onMouseEnter={e => e.currentTarget.style.background = '#262533'}
      onMouseLeave={e => e.currentTarget.style.background = 'none'}>
      {icon} {label}
    </button>
  )
}

const sectionLabel = {
  fontSize: '.68rem', textTransform: 'uppercase', letterSpacing: '.5px',
  color: '#6B6778', padding: '4px 6px', marginBottom: 2,
}
