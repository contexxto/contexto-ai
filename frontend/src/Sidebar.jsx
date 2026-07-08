import { useState, useEffect, useCallback, useRef } from 'react'
import axios from 'axios'
import { Plus, Pin, PinOff, Pencil, Trash2, MoreHorizontal, MessageSquare, LogOut, Home, Map, Shield, Users, Briefcase, Sun, Moon, PanelLeft, Download } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'
import sphereLogo from './assets/sphere.svg'
import { getTheme, toggleTheme } from './theme'

// Paleta vía tokens del design system → adapta a tema oscuro/claro.
const C = {
  bg: 'var(--bg)', surface: 'var(--surface-1)', surface2: 'var(--surface-2)', border: 'var(--border)',
  text: 'var(--text)', dim: 'var(--text-mid)', faint: 'var(--text-dim)', accent: 'var(--teal-bright)', danger: 'var(--danger)',
  active: 'var(--surface-2)',
}

// Quita el bloque interno "[Contexto del sistema: …]" que pudo colarse al
// autogenerar el título desde el primer mensaje (ubicación/reglas del agente).
function tituloLimpio(t) {
  if (!t) return 'Conversación'
  const i = t.indexOf('[Contexto del sistema')
  return (i === -1 ? t : t.slice(0, i)).trim() || 'Conversación'
}

export default function Sidebar({ sessionId, onSelect, onNew, reloadKey, user, onLogin, onLogout, onPublish, onMap, onReview, onCRM, onUpgrade, mobile, onClose, puedeInstalar, onInstalar }) {
  const [sessions, setSessions] = useState([])
  const [menuId, setMenuId] = useState(null)
  const [editingId, setEditingId] = useState(null)
  const [editValue, setEditValue] = useState('')
  const [porEliminar, setPorEliminar] = useState(null)  // confirmación propia (no confirm() nativo)
  const [theme, setThemeState] = useState(getTheme())   // tema oscuro/claro (design system)
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
        onMouseEnter={e => { if (!active) e.currentTarget.style.background = C.surface2 }}
        onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}>
        <MessageSquare size={14} color={C.dim} style={{ flexShrink: 0 }} />
        {editing ? (
          <input ref={editRef} value={editValue}
            onChange={e => setEditValue(e.target.value)}
            onBlur={() => commitRename(s.session_id)}
            onKeyDown={e => { if (e.key === 'Enter') commitRename(s.session_id); if (e.key === 'Escape') setEditingId(null) }}
            onClick={e => e.stopPropagation()}
            style={{ flex: 1, background: C.surface, color: C.text, border: `1px solid ${C.accent}`, borderRadius: 5, padding: '3px 6px', fontSize: '.84rem', fontFamily: 'inherit' }} />
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
              background: C.surface2, border: `1px solid ${C.border}`, borderRadius: 8,
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
      width: mobile ? '100vw' : 300, flexShrink: 0, height: '100%', background: C.bg,
      borderRight: mobile ? 'none' : `1px solid ${C.border}`, display: 'flex', flexDirection: 'column',
    }}>
      {/* Header con logo (como ASI:One) */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 9, padding: '16px 18px 14px', borderBottom: `1px solid ${C.border}` }}>
        <img src={sphereLogo} alt="" width={22} height={22} style={{ display: 'block' }} />
        <span style={{ fontSize: '1.05rem', fontWeight: 800, color: C.text, letterSpacing: '-.02em' }}>Contexto</span>
        {mobile && onClose && (
          <button onClick={onClose} title="Cerrar menú"
            style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: C.dim, display: 'flex', padding: 4 }}>
            <PanelLeft size={20} />
          </button>
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, padding: '12px 12px 0' }}>
        {/* Nuevo chat — botón discreto (ASI no lo pone en verde; el teal se reserva para acciones) */}
        <button onClick={onNew}
          style={{
            display: 'flex', alignItems: 'center', gap: 9, width: '100%',
            padding: '11px 14px', borderRadius: 10, cursor: 'pointer', marginBottom: 8,
            background: C.surface, color: C.text, border: `1px solid ${C.border}`, fontSize: '.9rem', fontWeight: 600, fontFamily: 'inherit',
          }}
          onMouseEnter={e => e.currentTarget.style.background = C.surface2}
          onMouseLeave={e => e.currentTarget.style.background = C.surface}>
          <Plus size={17} /> Nuevo chat
        </button>

        {/* Nav aireada */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginBottom: 8 }}>
          <NavItem icon={<Home size={17} />} label="Mis inmuebles" onClick={onPublish} />
          <NavItem icon={<Map size={17} />} label="Mapa Vivo" onClick={onMap} />
          {(user?.rol === 'corredor' || user?.rol === 'inmobiliaria') && (
            <>
              <NavItem icon={<Users size={17} />} label="CRM" onClick={onCRM} />
              <NavItem icon={<Shield size={17} />} label="Revisión" onClick={onReview} />
            </>
          )}
          {user && user.rol !== 'corredor' && user.rol !== 'inmobiliaria' && onUpgrade && (
            <NavItem icon={<Briefcase size={17} />} label="Conviértete en corredor" onClick={onUpgrade} />
          )}
        </div>

        {/* Conversaciones */}
        <div style={{ flex: 1, overflowY: 'auto', minHeight: 0 }}>
          {sessions.length === 0 && (
            <div style={{ color: C.faint, fontSize: '.8rem', padding: '8px 4px' }}>Sin conversaciones aún.</div>
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
      </div>

      {/* Footer: cuenta + Modo claro + legal (como ASI) */}
      <div style={{ borderTop: `1px solid ${C.border}`, padding: '10px 12px 12px' }}>
        {user ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 8 }}>
            <div style={{
              width: 30, height: 30, borderRadius: '50%', flexShrink: 0,
              background: C.accent, color: '#06201C',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontWeight: 800, fontSize: '.85rem',
            }}>
              {(user.email || '?').trim()[0]?.toUpperCase()}
            </div>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontSize: '.8rem', color: C.text, overflow: 'hidden',
                            textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{user.email}</div>
              {user.rol && (
                <div style={{ fontSize: '.7rem', color: C.dim, textTransform: 'capitalize' }}>{user.rol}</div>
              )}
            </div>
            <button onClick={onLogout} title="Cerrar sesión"
              style={{
                background: 'none', border: 'none', borderRadius: 8, cursor: 'pointer', color: C.dim,
                display: 'flex', alignItems: 'center', padding: 7, flexShrink: 0,
              }}>
              <LogOut size={16} />
            </button>
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
            <button onClick={onLogin}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                padding: '11px 12px', borderRadius: 10, cursor: 'pointer',
                background: 'transparent', border: `1px solid ${C.border}`, color: C.text,
                fontSize: '.86rem', fontWeight: 600, fontFamily: 'inherit',
              }}>
              Ingresar
            </button>
            <button onClick={onLogin}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                padding: '11px 12px', borderRadius: 10, cursor: 'pointer',
                background: C.accent, border: 'none', color: '#06201C',
                fontSize: '.86rem', fontWeight: 700, fontFamily: 'inherit',
              }}>
              Registrarse
            </button>
          </div>
        )}

        {/* Instalar como app (PWA): Android dispara el prompt nativo; iOS muestra instrucciones */}
        {puedeInstalar && (
          <button onClick={onInstalar}
            style={{
              display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '10px 12px',
              borderRadius: 10, cursor: 'pointer', marginBottom: 4, fontFamily: 'inherit', textAlign: 'left',
              background: 'rgba(45,189,182,.12)', border: `1px solid ${C.border}`,
              color: 'var(--accent)', fontSize: '.84rem', fontWeight: 700,
            }}
            onMouseEnter={e => e.currentTarget.style.background = 'rgba(45,189,182,.20)'}
            onMouseLeave={e => e.currentTarget.style.background = 'rgba(45,189,182,.12)'}>
            <Download size={16} /> Instalar app
          </button>
        )}

        {/* Toggle de tema oscuro/claro (design system) */}
        <button onClick={() => setThemeState(toggleTheme())} title="Cambiar tema"
          style={{
            display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '9px 8px',
            borderRadius: 8, cursor: 'pointer', background: 'none', border: 'none',
            color: C.dim, fontSize: '.82rem', textAlign: 'left', fontFamily: 'inherit',
          }}
          onMouseEnter={e => e.currentTarget.style.background = C.surface2}
          onMouseLeave={e => e.currentTarget.style.background = 'none'}>
          {theme === 'light' ? <Moon size={16} /> : <Sun size={16} />}
          {theme === 'light' ? 'Modo oscuro' : 'Modo claro'}
        </button>

        {/* Footer legal / marca */}
        <div style={{ fontSize: '.68rem', color: C.faint, lineHeight: 1.6, padding: '8px 8px 0' }}>
          Cada lugar tiene un aura · <span style={{ color: C.dim }}>Términos</span> · <span style={{ color: C.dim }}>Privacidad</span>
        </div>
      </div>

      {/* Confirmación propia de borrado (en lugar del confirm() nativo del navegador) */}
      {porEliminar && (
        <div onClick={() => setPorEliminar(null)}
          style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,0,0,.55)',
                   display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
          <div onClick={e => e.stopPropagation()}
            style={{ width: 'min(360px, 100%)', background: C.surface, border: `1px solid ${C.border}`,
                     borderRadius: 14, padding: '18px', boxShadow: '0 12px 40px rgba(0,0,0,.6)',
                     fontFamily: 'inherit' }}>
            <div style={{ color: C.text, fontWeight: 700, fontSize: '.95rem', marginBottom: 6 }}>Eliminar conversación</div>
            <div style={{ color: C.dim, fontSize: '.84rem', lineHeight: 1.5, marginBottom: 16 }}>
              Se quitará <b style={{ color: C.text }}>"{tituloLimpio(porEliminar.titulo)}"</b> de tu lista.
            </div>
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button onClick={() => setPorEliminar(null)}
                style={{ padding: '8px 14px', borderRadius: 8, cursor: 'pointer', fontSize: '.84rem', fontFamily: 'inherit',
                         background: 'transparent', border: `1px solid ${C.border}`, color: C.text }}>Cancelar</button>
              <button onClick={confirmarEliminar}
                style={{ padding: '8px 14px', borderRadius: 8, cursor: 'pointer', fontSize: '.84rem', fontWeight: 600, fontFamily: 'inherit',
                         background: C.danger, border: 'none', color: '#0E0D13' }}>Eliminar</button>
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
        display: 'flex', alignItems: 'center', gap: 11, width: '100%', padding: '10px 10px',
        borderRadius: 8, cursor: 'pointer', background: 'none', border: 'none',
        color: C.dim, fontSize: '.88rem', textAlign: 'left', transition: 'all .12s', fontFamily: 'inherit',
      }}
      onMouseEnter={e => { e.currentTarget.style.background = C.surface2; e.currentTarget.style.color = C.text }}
      onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = C.dim }}>
      {icon} {label}
    </button>
  )
}

function MenuItem({ icon, label, onClick, danger }) {
  return (
    <button onClick={onClick}
      style={{
        display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '8px 12px',
        background: 'none', border: 'none', cursor: 'pointer', fontSize: '.82rem', fontFamily: 'inherit',
        color: danger ? C.danger : C.text, textAlign: 'left',
      }}
      onMouseEnter={e => e.currentTarget.style.background = C.border}
      onMouseLeave={e => e.currentTarget.style.background = 'none'}>
      {icon} {label}
    </button>
  )
}

const sectionLabel = {
  fontSize: '.68rem', textTransform: 'uppercase', letterSpacing: '.5px',
  color: C.faint, padding: '4px 6px', marginBottom: 2,
}
