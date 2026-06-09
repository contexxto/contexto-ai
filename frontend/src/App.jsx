import { useState, useEffect, useRef, useCallback } from 'react'
import axios from 'axios'
import {
  Send, MapPin, RefreshCw, Trash2, Copy, CheckCheck, ChevronDown
} from 'lucide-react'

// En desarrollo usa el proxy de Vite (/api → localhost:8000).
// En producción (Vercel) usa la variable de entorno VITE_API_URL.
const API_BASE = import.meta.env.VITE_API_URL ?? ''
// Header de autenticación — vacío en dev local (backend lo ignora si API_KEY no está configurada)
const API_KEY = import.meta.env.VITE_API_KEY ?? ''
const authHeaders = API_KEY ? { 'X-API-Key': API_KEY } : {}
import './App.css'
import ReviewStation from './ReviewStation'
import Sidebar from './Sidebar'

// ── Helpers ────────────────────────────────────────────────
const SESSION_KEY = 'contexto_ai_session_id'

function getOrCreateSession() {
  let id = localStorage.getItem(SESSION_KEY)
  if (!id) {
    id = 'session-' + crypto.randomUUID()
    localStorage.setItem(SESSION_KEY, id)
  }
  return id
}

/** Minimal markdown → HTML (headers, bold, lists, hr, code) */
function renderMarkdown(text) {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/^#{3}\s+(.+)$/gm, '<h3>$1</h3>')
    .replace(/^#{2}\s+(.+)$/gm, '<h2>$1</h2>')
    .replace(/^---$/gm, '<hr/>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/^[\*\-]\s+(.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>(\n|$))+/g, m => `<ul>${m}</ul>`)
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/^(?!<[hup]|<li|<hr)(.+)$/gm, '<p>$1</p>')
}

// ── Sub-components ──────────────────────────────────────────
function Message({ msg, onCopy, copied }) {
  const isUser = msg.role === 'user'
  return (
    <div style={{
      display:'flex', justifyContent: isUser ? 'flex-end' : 'flex-start',
      marginBottom:16, gap:10,
    }}>
      {!isUser && (
        <div style={{
          width:32, height:32, borderRadius:'50%', flexShrink:0,
          background:'linear-gradient(135deg,#1f6feb,#58a6ff)',
          display:'flex', alignItems:'center', justifyContent:'center',
          fontSize:14, fontWeight:700,
        }}>C</div>
      )}
      <div style={{ maxWidth:'78%' }}>
        {msg.toolCalls?.length > 0 && (
          <div style={{ marginBottom:6, fontSize:'.72rem', color:'var(--text-muted)',
                        display:'flex', alignItems:'center', gap:5 }}>
            🔧 Analizado con {msg.toolCalls.length} herramienta{msg.toolCalls.length > 1 ? 's' : ''} del catastro
          </div>
        )}
        <div style={{
          padding: isUser ? '10px 14px' : '2px 30px 2px 2px',
          borderRadius: isUser ? '18px 18px 4px 18px' : 0,
          background: isUser ? 'var(--user-bg)' : 'transparent',
          border: 'none',
          fontSize:'.92rem', lineHeight:1.65,
          position:'relative',
        }}>
          {isUser ? (
            <span>{msg.content}</span>
          ) : (
            <div
              className="ai-content"
              dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
            />
          )}
          {!isUser && (
            <button
              onClick={() => onCopy(msg.content)}
              title="Copiar respuesta"
              style={{
                position:'absolute', top:0, right:0,
                background:'none', border:'none', cursor:'pointer',
                color: copied === msg.id ? 'var(--success)' : 'var(--text-muted)',
                padding:4, borderRadius:4,
              }}
            >
              {copied === msg.id ? <CheckCheck size={13}/> : <Copy size={13}/>}
            </button>
          )}
        </div>
        <div style={{ fontSize:'.72rem', color:'var(--text-muted)', marginTop:4,
                      textAlign: isUser ? 'right' : 'left' }}>
          {msg.time}
        </div>
      </div>
      {isUser && (
        <div style={{
          width:32, height:32, borderRadius:'50%', flexShrink:0,
          background:'#30363d', display:'flex', alignItems:'center',
          justifyContent:'center', fontSize:13, fontWeight:600,
        }}>Tú</div>
      )}
    </div>
  )
}

function Thinking() {
  return (
    <div style={{ display:'flex', gap:10, marginBottom:16 }}>
      <div style={{
        width:32, height:32, borderRadius:'50%', flexShrink:0,
        background:'linear-gradient(135deg,#1f6feb,#58a6ff)',
        display:'flex', alignItems:'center', justifyContent:'center',
        fontSize:14, fontWeight:700,
      }}>C</div>
      <div style={{
        padding:'14px 16px', borderRadius:'4px 18px 18px 18px',
        background:'var(--ai-bg)', border:'1px solid var(--border)',
        display:'flex', gap:5, alignItems:'center',
      }}>
        {[0,1,2].map(i => (
          <span key={i} style={{
            width:7, height:7, borderRadius:'50%', background:'var(--text-muted)',
            animation:'pulse 1.2s ease-in-out infinite',
            animationDelay: `${i * 0.2}s`,
          }}/>
        ))}
      </div>
    </div>
  )
}

// ── Main App ────────────────────────────────────────────────
const QUICK_PROMPTS = [
  '¿Cuáles son las opciones más tranquilas cerca de La Carolina en Quito?',
  '¿Cómo está el mantenimiento técnico de las propiedades en Av. República del Salvador?',
  '¿Qué riesgos futuros tienen los inmuebles cerca de Av. Amazonas?',
]

export default function App() {
  const [sessionId, setSessionId] = useState(getOrCreateSession)
  const [messages, setMessages]   = useState([])
  const [input, setInput]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState(null)
  const [copied, setCopied]       = useState(null)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  const [view, setView] = useState('chat')  // 'chat' | 'review'
  const [dragOver, setDragOver] = useState(false)

  const bottomRef  = useRef(null)
  const inputRef   = useRef(null)
  const scrollRef  = useRef(null)

  // Restore history from API on mount / session change
  useEffect(() => {
    axios.get(`${API_BASE}/api/v1/chat/${sessionId}/history`, { headers: authHeaders })
      .then(({ data }) => {
        if (!data.messages?.length) return
        const restored = data.messages.map((m, i) => ({
          id: `restored-${i}`,
          role: m.role === 'user' ? 'user' : 'ai',
          content: m.content,
          time: '',
          toolCalls: [],
        }))
        setMessages(restored)
      })
      .catch(() => {}) // silent — no history yet
  }, [sessionId])

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const handleScroll = useCallback(() => {
    const el = scrollRef.current
    if (!el) return
    setShowScrollBtn(el.scrollHeight - el.scrollTop - el.clientHeight > 200)
  }, [])

  const handleCopy = useCallback((text) => {
    navigator.clipboard.writeText(text).then(() => {
      const id = text.slice(0, 20)
      setCopied(id)
      setTimeout(() => setCopied(null), 2000)
    })
  }, [])

  const sendMessage = useCallback(async (text) => {
    const userText = (text ?? input).trim()
    if (!userText || loading) return

    setInput('')
    setError(null)

    const userMsg = {
      id: crypto.randomUUID(), role: 'user', content: userText,
      time: new Date().toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' }),
      toolCalls: [],
    }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)

    const toolCallsObserved = []

    try {
      const { data } = await axios.post(`${API_BASE}/api/v1/chat/`, {
        message: userText,
        session_id: sessionId,
      }, { headers: authHeaders })

      // Capture tool calls from response (non-streaming path shows count only)
      const aiMsg = {
        id: crypto.randomUUID(), role: 'ai', content: data.reply,
        time: new Date().toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' }),
        toolCalls: data.tool_calls_made > 0
          ? Array(data.tool_calls_made).fill('tool_called')
          : [],
      }
      setMessages(prev => [...prev, aiMsg])
    } catch (err) {
      setError(
        err.response?.data?.detail
        ?? 'Error al conectar con el agente. Verifica que la API esté corriendo en :8000.'
      )
    } finally {
      setLoading(false)
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [input, loading, sessionId])

  // ── Brief Intake C0: arrastra una foto → match por similitud visual ──
  const matchByImage = useCallback(async (dataUrl) => {
    if (loading) return
    setError(null)
    setMessages(prev => [...prev, {
      id: crypto.randomUUID(), role: 'user',
      content: '🔎 Buscando inmuebles parecidos a la foto que subí…',
      time: new Date().toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' }), toolCalls: [],
    }])
    setLoading(true)
    try {
      const { data } = await axios.post(`${API_BASE}/api/v1/match`,
        { image_base64: dataUrl, top_k: 5 }, { headers: authHeaders })
      const lines = (data.resultados || []).map((r, i) =>
        `**${i + 1}. ${r.direccion}** · ${r.tipo_activo} · similitud ${(r.similitud * 100).toFixed(0)}%\n${r.por_que_encaja || ''}`
      )
      const content = lines.length
        ? `**Inmuebles más parecidos a tu foto:**\n\n${lines.join('\n\n')}`
        : 'No encontré inmuebles parecidos aún. A medida que crezca el catastro, los resultados mejorarán.'
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(), role: 'ai', content,
        time: new Date().toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' }), toolCalls: [],
      }])
    } catch (err) {
      setError(err.response?.data?.detail ?? 'Error al buscar coincidencias por imagen.')
    } finally {
      setLoading(false)
    }
  }, [loading])

  const handleDrop = useCallback((e) => {
    e.preventDefault(); setDragOver(false)
    const file = e.dataTransfer?.files?.[0]
    if (!file) return
    if (!file.type.startsWith('image/')) {
      setError('Por ahora solo fotos (C0). El soporte de Word/Excel/PPT llega en una próxima fase.')
      return
    }
    const reader = new FileReader()
    reader.onload = () => matchByImage(reader.result)
    reader.readAsDataURL(file)
  }, [matchByImage])

  const resetSession = useCallback(() => {
    // Sin confirmación: la conversación actual no se pierde — queda guardada y
    // visible en la barra lateral, a un clic. "Nuevo chat" crea uno al instante.
    const newId = 'session-' + crypto.randomUUID()
    localStorage.setItem(SESSION_KEY, newId)
    setSessionId(newId)
    setMessages([])
    setError(null)
    setTimeout(() => inputRef.current?.focus(), 100)
  }, [])

  const switchSession = useCallback((id) => {
    if (id === sessionId) return
    localStorage.setItem(SESSION_KEY, id)
    setMessages([])
    setError(null)
    setSessionId(id)            // dispara el efecto que recarga el historial
  }, [sessionId])

  const isEmpty = messages.length === 0 && !loading

  // Vista de Estación de Revisión (pantalla completa)
  if (view === 'review') {
    return (
      <div style={{ height:'100dvh', display:'flex', flexDirection:'column' }}>
        <div style={{ padding:'8px 16px', borderBottom:'1px solid var(--border)' }}>
          <button onClick={() => setView('chat')} style={{
            background:'none', border:'1px solid var(--border)', borderRadius:8,
            cursor:'pointer', color:'var(--text-muted)', padding:'6px 12px', fontSize:'.85rem',
          }}>← Volver al chat</button>
        </div>
        <div style={{ flex:1, minHeight:0 }}><ReviewStation /></div>
      </div>
    )
  }

  return (
    <div style={{ display:'flex', height:'100dvh' }}>
      <Sidebar
        sessionId={sessionId}
        onSelect={switchSession}
        onNew={resetSession}
        reloadKey={`${sessionId}:${messages.length}`}
      />
      <div
        onDragOver={e => { e.preventDefault(); if (!dragOver) setDragOver(true) }}
        onDragLeave={e => { if (e.currentTarget === e.target) setDragOver(false) }}
        onDrop={handleDrop}
        style={{ flex:1, minWidth:0, position:'relative',
                 height:'100dvh', overflow:'hidden', outline:'3px solid lime' }}>
      <div style={{ maxWidth:720, margin:'0 auto', display:'flex', flexDirection:'column',
                    height:'100dvh', minHeight:0, padding:'0 16px', outline:'3px solid red' }}>

      {dragOver && (
        <div style={{
          position:'absolute', inset:0, zIndex:50, display:'flex', flexDirection:'column',
          alignItems:'center', justifyContent:'center', gap:10,
          background:'rgba(13,17,23,.92)', border:'2px dashed #58a6ff', borderRadius:14,
          color:'#58a6ff', fontSize:'1.05rem', fontWeight:600, pointerEvents:'none',
        }}>
          <MapPin size={36} />
          Suelta tu foto para encontrar inmuebles parecidos
          <span style={{ fontSize:'.8rem', color:'#8b949e', fontWeight:400 }}>
            Shazam inmobiliario · similitud visual
          </span>
        </div>
      )}

      {/* ── Header ── */}
      <header style={{
        display:'flex', alignItems:'center', justifyContent:'space-between',
        padding:'16px 0 12px', borderBottom:'1px solid var(--border)',
        flexShrink:0,
      }}>
        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <div style={{
            width:36, height:36, borderRadius:10,
            background:'linear-gradient(135deg,#1f6feb,#388bfd)',
            display:'flex', alignItems:'center', justifyContent:'center',
          }}>
            <MapPin size={18} color="#fff" />
          </div>
          <div>
            <div style={{ fontWeight:700, fontSize:'1rem', letterSpacing:'-.3px' }}>
              Contexto AI
            </div>
            <div style={{ fontSize:'.72rem', color:'var(--text-muted)' }}>
              Catastro Vivo · La Carolina, Quito
            </div>
          </div>
        </div>
        <div style={{ display:'flex', gap:8, alignItems:'center' }}>
          <span style={{
            fontSize:'.7rem', padding:'3px 9px', borderRadius:20,
            background:'#0d2d0d', color:'var(--success)',
            border:'1px solid #1a4a1a',
          }}>● API conectada</span>
          <button
            onClick={() => setView('review')}
            title="Estación de Revisión"
            style={{
              background:'none', border:'1px solid var(--border)', borderRadius:8,
              cursor:'pointer', color:'var(--text-muted)', padding:'6px 10px',
              display:'flex', alignItems:'center', gap:5, fontSize:'.8rem',
            }}
          >
            🛡️ Revisión
          </button>
        </div>
      </header>

      {/* ── Messages ── */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        style={{ flex:1, overflowY:'auto', padding:'20px 0', position:'relative' }}
      >
        {isEmpty && (
          <div style={{ textAlign:'center', paddingTop:60 }}>
            <div style={{
              width:64, height:64, borderRadius:16, margin:'0 auto 20px',
              background:'linear-gradient(135deg,#1f6feb22,#388bfd22)',
              border:'1px solid #1f6feb44',
              display:'flex', alignItems:'center', justifyContent:'center',
            }}>
              <MapPin size={28} color='#58a6ff'/>
            </div>
            <h2 style={{ fontWeight:600, fontSize:'1.25rem', marginBottom:8 }}>
              Bienvenido a Contexto AI
            </h2>
            <p style={{ color:'var(--text-muted)', fontSize:'.9rem', marginBottom:32 }}>
              Analiza habitabilidad, mantenimiento técnico e infraestructura<br/>
              de propiedades en tiempo real con datos PostGIS verificados.
            </p>
            <div style={{ display:'flex', flexDirection:'column', gap:8, alignItems:'center' }}>
              {QUICK_PROMPTS.map((p, i) => (
                <button
                  key={i}
                  onClick={() => sendMessage(p)}
                  style={{
                    background:'var(--surface)', border:'1px solid var(--border)',
                    borderRadius:10, padding:'10px 18px', cursor:'pointer',
                    color:'var(--text)', fontSize:'.85rem', maxWidth:520,
                    textAlign:'left', transition:'border-color .15s',
                  }}
                  onMouseEnter={e => e.target.style.borderColor='#58a6ff'}
                  onMouseLeave={e => e.target.style.borderColor='var(--border)'}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map(msg => (
          <Message key={msg.id} msg={msg} onCopy={() => handleCopy(msg.content)} copied={copied} />
        ))}

        {loading && <Thinking />}

        {error && (
          <div style={{
            background:'#2d1a1a', border:'1px solid #5a2020', borderRadius:10,
            padding:'12px 16px', color:'#f85149', fontSize:'.87rem', marginBottom:12,
            display:'flex', justifyContent:'space-between', alignItems:'center',
          }}>
            <span>{error}</span>
            <button onClick={() => setError(null)}
              style={{ background:'none', border:'none', cursor:'pointer', color:'#f85149', fontSize:16 }}>
              ×
            </button>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Scroll to bottom button */}
      {showScrollBtn && (
        <button
          onClick={() => bottomRef.current?.scrollIntoView({ behavior:'smooth' })}
          style={{
            position:'fixed', bottom:90, right:24, width:36, height:36,
            borderRadius:'50%', background:'var(--surface)', border:'1px solid var(--border)',
            cursor:'pointer', color:'var(--text-muted)', display:'flex',
            alignItems:'center', justifyContent:'center', zIndex:10,
          }}
        >
          <ChevronDown size={16}/>
        </button>
      )}

      {/* ── Input ── */}
      <div style={{
        borderTop:'1px solid var(--border)', padding:'14px 0 18px', flexShrink:0,
      }}>
        <div style={{
          display:'flex', gap:10, background:'var(--surface)',
          border:'1px solid var(--border)', borderRadius:14, padding:'8px 8px 8px 16px',
          transition:'border-color .15s',
        }}
          onFocusCapture={e => e.currentTarget.style.borderColor='#58a6ff'}
          onBlurCapture={e => e.currentTarget.style.borderColor='var(--border)'}
        >
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
            }}
            placeholder="Pregunta sobre habitabilidad, mantenimiento técnico o infraestructura..."
            disabled={loading}
            rows={1}
            style={{
              flex:1, background:'none', border:'none', outline:'none',
              color:'var(--text)', fontSize:'.92rem', resize:'none',
              lineHeight:1.6, maxHeight:120, overflowY:'auto',
              fontFamily:'inherit',
            }}
            onInput={e => {
              e.target.style.height = 'auto'
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
            }}
          />
          <button
            onClick={() => sendMessage()}
            disabled={!input.trim() || loading}
            style={{
              background: !input.trim() || loading ? 'var(--border)' : '#1f6feb',
              border:'none', borderRadius:10, width:38, height:38, cursor:'pointer',
              display:'flex', alignItems:'center', justifyContent:'center',
              flexShrink:0, transition:'background .15s',
            }}
          >
            {loading
              ? <RefreshCw size={16} color="#fff" style={{ animation:'spin 1s linear infinite' }}/>
              : <Send size={16} color="#fff"/>
            }
          </button>
        </div>
        <div style={{
          display:'flex', justifyContent:'space-between', marginTop:8,
          fontSize:'.7rem', color:'var(--text-muted)', padding:'0 4px',
        }}>
          <span>Enter para enviar · Shift+Enter nueva línea</span>
          <span style={{ fontFamily:'monospace', opacity:.6 }}>
            {sessionId.slice(0, 22)}...
          </span>
        </div>
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: .3; transform: scale(.8); }
          50%       { opacity: 1;  transform: scale(1.1); }
        }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
      </div>
      </div>
    </div>
  )
}
