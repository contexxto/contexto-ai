import { useState, useEffect, useRef, useCallback, lazy, Suspense } from 'react'
import axios from 'axios'
import {
  Send, MapPin, RefreshCw, Trash2, Copy, CheckCheck, ChevronDown, Menu, Mic, PanelLeft
} from 'lucide-react'
import { supabase, authEnabled } from './supabaseClient'
import Auth from './Auth'
import PublishAsset from './PublishAsset'

// Headers (backend key + Bearer del usuario) centralizados en api.js
import { API_BASE, apiHeaders, setAccessToken } from './api'
import './App.css'
import ReviewStation from './ReviewStation'
import Sidebar from './Sidebar'
import sphereLogo from './assets/sphere.svg'

// Carga diferida: MapLibre (pesado) solo se descarga al abrir el Mapa.
const MapView = lazy(() => import('./MapView'))

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

/** Markdown → HTML: headers h1-h4, tablas, listas (ol/ul), bold, italic, code, hr.
 *  Parser línea por línea (robusto ante líneas en blanco del agente). */
function renderMarkdown(text) {
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const inline = s => esc(s)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
  const cells = r => r.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map(c => c.trim())

  const lines = (text || '').split('\n')
  const out = []
  let list = null  // 'ul' | 'ol'
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null } }

  let i = 0
  while (i < lines.length) {
    const t = lines[i].trim()
    let m

    // ── Tabla: fila |...| seguida (saltando blancos) de un separador |---| ──
    if (t.startsWith('|')) {
      let j = i + 1
      while (j < lines.length && lines[j].trim() === '') j++
      if (j < lines.length && /^\|?[\s:|-]+\|?$/.test(lines[j].trim()) && lines[j].includes('-')) {
        closeList()
        const header = t
        i = j + 1
        const rows = []
        while (i < lines.length) {
          const tt = lines[i].trim()
          if (tt === '') { i++; continue }
          if (tt.startsWith('|')) { rows.push(tt); i++; continue }
          break
        }
        let html = '<table><thead><tr>' +
          cells(header).map(c => `<th>${inline(c)}</th>`).join('') + '</tr></thead><tbody>'
        for (const r of rows) html += '<tr>' + cells(r).map(c => `<td>${inline(c)}</td>`).join('') + '</tr>'
        out.push(html + '</tbody></table>')
        continue
      }
    }

    if ((m = t.match(/^####\s+(.+)$/))) { closeList(); out.push(`<h4>${inline(m[1])}</h4>`); i++; continue }
    if ((m = t.match(/^###\s+(.+)$/)))  { closeList(); out.push(`<h3>${inline(m[1])}</h3>`); i++; continue }
    if ((m = t.match(/^##\s+(.+)$/)))   { closeList(); out.push(`<h2>${inline(m[1])}</h2>`); i++; continue }
    if ((m = t.match(/^#\s+(.+)$/)))    { closeList(); out.push(`<h2>${inline(m[1])}</h2>`); i++; continue }
    if (/^(---+|___+|\*\*\*+)$/.test(t)) { closeList(); out.push('<hr/>'); i++; continue }

    if ((m = t.match(/^\d+[.)]\s+(.+)$/))) {
      if (list !== 'ol') { closeList(); out.push('<ol>'); list = 'ol' }
      out.push(`<li>${inline(m[1])}</li>`); i++; continue
    }
    if ((m = t.match(/^[*\-]\s+(.+)$/))) {
      if (list !== 'ul') { closeList(); out.push('<ul>'); list = 'ul' }
      out.push(`<li>${inline(m[1])}</li>`); i++; continue
    }

    if (t === '') { closeList(); i++; continue }

    closeList()
    out.push(`<p>${inline(t)}</p>`)
    i++
  }
  closeList()
  return out.join('\n')
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
        <img src={sphereLogo} alt="Contexto AI" width={32} height={32}
             style={{ flexShrink:0, display:'block' }} />
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
          background: isUser ? 'linear-gradient(135deg, #1A7A76, #2DBDB6)' : 'transparent',
          border: 'none',
          boxShadow: isUser ? '0 4px 18px rgba(45,189,182,.22)' : 'none',
          color: isUser ? '#fff' : 'inherit',
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
      <img src={sphereLogo} alt="Contexto AI" width={32} height={32}
           style={{ flexShrink:0, display:'block', filter:'drop-shadow(0 0 8px rgba(45,189,182,.45))' }} />
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
  // Deep link de QR: /a/{uuid} → sesión determinística qr-{id}
  const deepLinkId = (window.location.pathname.match(/^\/a\/([0-9a-fA-F-]{36})$/) || [])[1] || null
  const [sessionId, setSessionId] = useState(() => deepLinkId ? 'qr-' + deepLinkId : getOrCreateSession())
  const [messages, setMessages]   = useState([])
  const [input, setInput]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState(null)
  const [copied, setCopied]       = useState(null)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  const [view, setView] = useState('chat')  // 'chat' | 'review' | 'map'
  const [dragOver, setDragOver] = useState(false)
  const [geo, setGeo] = useState(null)          // {lat, lon} | null — ubicación del usuario
  const [geoLoading, setGeoLoading] = useState(false)
  const [isMobile, setIsMobile] = useState(() => window.matchMedia('(max-width: 768px)').matches)
  const [sidebarOpen, setSidebarOpen] = useState(false)   // cajón móvil
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)  // colapsar sidebar (escritorio)
  const [listening, setListening] = useState(false)       // dictado por voz
  const recognitionRef = useRef(null)
  const [session, setSession] = useState(null)            // sesión de Supabase | null
  const [authOpen, setAuthOpen] = useState(false)         // modal de login/registro
  const [rol, setRol] = useState(null)                    // rol del usuario (cliente/corredor/inmobiliaria)
  const [publishOpen, setPublishOpen] = useState(false)   // modal "Publicar mi inmueble"

  // Sesión: cargar la actual y escuchar cambios (login/logout). Mantiene el token
  // que apiHeaders() adjunta a cada llamada al backend.
  useEffect(() => {
    if (!authEnabled) return
    // Si quedó un rol pendiente del registro (cuando hay confirmación por correo),
    // lo aplicamos en cuanto haya sesión válida.
    const applyPendingProfile = async (token) => {
      const raw = localStorage.getItem('pendingProfile')
      if (!raw || !token) return
      try {
        await axios.post(`${API_BASE}/api/v1/auth/profile`, JSON.parse(raw),
          { headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` } })
        localStorage.removeItem('pendingProfile')
      } catch { /* reintentará en el próximo inicio de sesión */ }
    }
    const loadRol = async (token) => {
      if (!token) { setRol(null); return }
      try {
        const { data } = await axios.get(`${API_BASE}/api/v1/auth/me`,
          { headers: { Authorization: `Bearer ${token}` } })
        setRol(data?.rol ?? null)
      } catch { setRol(null) }
    }
    const onSession = async (s) => {
      setSession(s)
      setAccessToken(s?.access_token)
      await applyPendingProfile(s?.access_token)
      await loadRol(s?.access_token)
    }
    supabase.auth.getSession().then(({ data }) => onSession(data.session))
    const { data: sub } = supabase.auth.onAuthStateChange((_e, s) => onSession(s))
    return () => sub?.subscription?.unsubscribe?.()
  }, [])

  const logout = useCallback(async () => {
    if (authEnabled) await supabase.auth.signOut()
    setSession(null); setAccessToken(null); setRol(null)
  }, [])

  const bottomRef  = useRef(null)
  const inputRef   = useRef(null)
  const scrollRef  = useRef(null)
  // Salta la restauración SOLO en la primera carga si vino por QR
  // (loadFromDeepLink maneja esa sesión). Los cambios de conversación restauran normal.
  const skipFirstRestore = useRef(!!deepLinkId)

  // Responsive: detecta móvil/tablet para mostrar la barra lateral como cajón
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 768px)')
    const h = (e) => setIsMobile(e.matches)
    mq.addEventListener('change', h)
    return () => mq.removeEventListener('change', h)
  }, [])

  // Restore history from API on mount / session change
  useEffect(() => {
    if (skipFirstRestore.current) { skipFirstRestore.current = false; return }
    axios.get(`${API_BASE}/api/v1/chat/${sessionId}/history`, { headers: apiHeaders() })
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

  // Deep link de QR (letrero inteligente): /a/{id} → el agente entrega el informe.
  // Sesión determinística por inmueble: re-escanear reutiliza la conversación.
  const loadFromDeepLink = useCallback(async (id) => {
    const sid = 'qr-' + id
    localStorage.setItem(SESSION_KEY, sid)
    setSessionId(sid)
    // Si ya fue escaneado antes, restauramos (rápido, sin volver a llamar al agente).
    try {
      const { data } = await axios.get(`${API_BASE}/api/v1/chat/${sid}/history`, { headers: apiHeaders() })
      if (data.messages?.length) {
        setMessages(data.messages.map((m, i) => ({
          id: `r-${i}`, role: m.role === 'user' ? 'user' : 'ai', content: m.content, time: '', toolCalls: [],
        })))
        return
      }
    } catch { /* sin historial: seguimos al brief */ }

    const t = new Date().toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' })
    setMessages([{ id: crypto.randomUUID(), role:'user',
      content:'📍 Escaneé el QR de este inmueble. ¿Qué sabes de él?', time:t, toolCalls:[] }])
    setLoading(true)
    try {
      const { data } = await axios.post(`${API_BASE}/api/v1/chat/`, {
        message: `El usuario escaneó el QR de un inmueble. Entrégale el informe completo en lenguaje natural, usando el identificador del activo ${id}. Incluye: dirección, tipo de activo, walk score, nivel de ruido, tráfico, cobertura vegetal y el estado de mantenimiento (tuberías, año de construcción, estructura, acabados, impermeabilización de techo, cableado eléctrico, cisterna, fachada e inversión en mejoras). Si no existen datos para ese identificador, dilo con honestidad.`,
        session_id: sid,
      }, { headers: apiHeaders() })
      setMessages(prev => [...prev, { id: crypto.randomUUID(), role:'ai', content: data.reply,
        time: new Date().toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' }),
        toolCalls: data.tool_calls_made > 0 ? Array(data.tool_calls_made).fill('t') : [] }])
      // Título limpio en la barra lateral (en vez del mensaje técnico).
      axios.patch(`${API_BASE}/api/v1/chat/sessions/${sid}`,
        { titulo: '📍 Inmueble escaneado (QR)' }, { headers: apiHeaders() }).catch(() => {})
    } catch {
      setError('No se pudo cargar el informe del inmueble escaneado.')
    } finally { setLoading(false) }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (deepLinkId) loadFromDeepLink(deepLinkId)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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

    // Si la ubicación está activa, se la pasamos al agente como contexto
    // (sin ensuciar la burbuja visible). El agente usa tool_search_nearby_assets.
    const apiMessage = geo
      ? `${userText}\n\n[Contexto del sistema: el usuario está físicamente en estas coordenadas → lat=${geo.lat}, lon=${geo.lon}. Si su pregunta es sobre cercanía ("cerca de mí", "aquí", "este sector", "a X metros/km"), usa tool_search_nearby_assets con estas coordenadas y el radio que indique (por defecto 1000 m). Si no menciona distancia, usa 1000 m.]`
      : userText

    try {
      const { data } = await axios.post(`${API_BASE}/api/v1/chat/`, {
        message: apiMessage,
        session_id: sessionId,
      }, { headers: apiHeaders() })

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
  }, [input, loading, sessionId, geo])

  // Dictado por voz (Web Speech API) — "hablarle al agente"
  const startVoice = useCallback(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) { setError('El dictado por voz no está disponible en este navegador. Prueba en Chrome.'); return }
    if (listening) { recognitionRef.current?.stop(); return }
    const rec = new SR()
    rec.lang = 'es-419'      // español de Latinoamérica
    rec.interimResults = true
    rec.continuous = false
    rec.onresult = (e) => {
      let txt = ''
      for (let i = 0; i < e.results.length; i++) txt += e.results[i][0].transcript
      setInput(txt)
    }
    rec.onerror = () => setListening(false)
    rec.onend = () => { setListening(false); setTimeout(() => inputRef.current?.focus(), 50) }
    recognitionRef.current = rec
    setListening(true)
    rec.start()
  }, [listening])

  // Ubicación del usuario, estilo Uber: se autoriza UNA vez y queda activa en tiempo
  // real (watchPosition). Si el navegador ya tiene el permiso concedido, al abrir la
  // app se reactiva sola — sin volver a pedirla.
  const watchIdRef = useRef(null)

  const stopGeo = useCallback(() => {
    if (watchIdRef.current != null && navigator.geolocation) {
      navigator.geolocation.clearWatch(watchIdRef.current)
    }
    watchIdRef.current = null
    setGeo(null)
    // El usuario apagó la ubicación a propósito → recordar para NO reactivar al reabrir.
    try { localStorage.removeItem('geoConsent'); localStorage.setItem('geoOptOut', '1') } catch { /* ignore */ }
  }, [])

  const startGeo = useCallback((silent = false) => {
    if (!navigator.geolocation) {
      if (!silent) setError('Tu navegador no permite geolocalización.')
      return
    }
    try { localStorage.removeItem('geoOptOut') } catch { /* ignore */ }
    if (watchIdRef.current != null) return   // ya activa
    if (!silent) setGeoLoading(true)
    let first = true
    watchIdRef.current = navigator.geolocation.watchPosition(
      (pos) => {
        setGeo({ lat: +pos.coords.latitude.toFixed(6), lon: +pos.coords.longitude.toFixed(6) })
        try { localStorage.setItem('geoConsent', '1') } catch { /* ignore */ }
        if (first) {
          first = false
          setGeoLoading(false)
          if (!silent) setTimeout(() => inputRef.current?.focus(), 100)
        }
      },
      () => {
        setGeoLoading(false)
        watchIdRef.current = null
        try { localStorage.removeItem('geoConsent') } catch { /* ignore */ }
        if (!silent) setError('No pudimos obtener tu ubicación (permiso denegado).')
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 },
    )
  }, [])

  const toggleGeo = useCallback(() => {
    if (geo || watchIdRef.current != null) { stopGeo(); return }   // activa → apagar
    startGeo(false)                                                // primera vez → pedir
  }, [geo, startGeo, stopGeo])

  // Al abrir la app: si el navegador YA tiene el permiso concedido (o lo activó antes),
  // reactivamos la ubicación automáticamente — sin volver a molestar con el permiso.
  useEffect(() => {
    let optOut = false, consented = false
    try {
      optOut = localStorage.getItem('geoOptOut') === '1'
      consented = localStorage.getItem('geoConsent') === '1'
    } catch { /* ignore */ }
    if (optOut) return   // el usuario la apagó a propósito → no reactivar en segundo plano
    if (navigator.permissions?.query) {
      navigator.permissions.query({ name: 'geolocation' })
        .then((status) => { if (status.state === 'granted') startGeo(true) })
        .catch(() => { if (consented) startGeo(true) })
    } else if (consented) {
      startGeo(true)
    }
    return () => {
      if (watchIdRef.current != null && navigator.geolocation) {
        navigator.geolocation.clearWatch(watchIdRef.current)
      }
    }
  }, [startGeo])

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
        { image_base64: dataUrl, top_k: 5 }, { headers: apiHeaders() })
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
        <div style={{ padding:'8px 16px' }}>
          <button onClick={() => setView('chat')} style={{
            background:'none', border:'1px solid var(--border)', borderRadius:8,
            cursor:'pointer', color:'var(--text-muted)', padding:'6px 12px', fontSize:'.85rem',
          }}>← Volver al chat</button>
        </div>
        <div style={{ flex:1, minHeight:0 }}><ReviewStation /></div>
      </div>
    )
  }

  // Vista de Mapa Vivo (pantalla completa)
  if (view === 'map') {
    return (
      <div style={{ height:'100dvh', display:'flex', flexDirection:'column' }}>
        <div style={{ padding:'8px 16px' }}>
          <button onClick={() => setView('chat')} style={{
            background:'none', border:'1px solid var(--border)', borderRadius:8,
            cursor:'pointer', color:'var(--text-muted)', padding:'6px 12px', fontSize:'.85rem',
          }}>← Volver al chat</button>
        </div>
        <div style={{ flex:1, minHeight:0 }}>
          <Suspense fallback={
            <div style={{ height:'100%', display:'grid', placeItems:'center', color:'var(--text-muted)' }}>
              Cargando mapa…
            </div>
          }>
            <MapView />
          </Suspense>
        </div>
      </div>
    )
  }

  return (
    <div style={{ display:'flex', height:'100dvh' }}>
      {/* Desktop: barra lateral fija (colapsable). Móvil: cajón con backdrop. */}
      {!isMobile && !sidebarCollapsed && (
        <Sidebar
          sessionId={sessionId}
          onSelect={switchSession}
          onNew={resetSession}
          reloadKey={`${sessionId}:${messages.length}:${session?.user?.id ?? 'guest'}`}
          user={authEnabled && session ? { email: session.user?.email, rol } : null}
          onLogin={() => setAuthOpen(true)}
          onLogout={logout}
          onPublish={() => (authEnabled && session) ? setPublishOpen(true) : setAuthOpen(true)}
          onMap={() => setView('map')}
          onReview={() => setView('review')}
        />
      )}
      {isMobile && sidebarOpen && (
        <>
          <div onClick={() => setSidebarOpen(false)}
            style={{ position:'fixed', inset:0, background:'rgba(0,0,0,.55)', zIndex:40 }} />
          <div style={{ position:'fixed', top:0, left:0, bottom:0, zIndex:50 }}>
            <Sidebar
              sessionId={sessionId}
              onSelect={(id) => { switchSession(id); setSidebarOpen(false) }}
              onNew={() => { resetSession(); setSidebarOpen(false) }}
              reloadKey={`${sessionId}:${messages.length}:${session?.user?.id ?? 'guest'}`}
              user={authEnabled && session ? { email: session.user?.email, rol } : null}
              onLogin={() => { setAuthOpen(true); setSidebarOpen(false) }}
              onLogout={logout}
              onPublish={() => { (authEnabled && session) ? setPublishOpen(true) : setAuthOpen(true); setSidebarOpen(false) }}
              onMap={() => { setView('map'); setSidebarOpen(false) }}
              onReview={() => { setView('review'); setSidebarOpen(false) }}
            />
          </div>
        </>
      )}
      <div
        onDragOver={e => { e.preventDefault(); if (!dragOver) setDragOver(true) }}
        onDragLeave={e => { if (e.currentTarget === e.target) setDragOver(false) }}
        onDrop={handleDrop}
        style={{ flex:1, minWidth:0, position:'relative',
                 height:'100dvh', overflow:'hidden' }}>
      <div style={{ width:'100%', maxWidth:1280, margin:'0 auto', display:'flex', flexDirection:'column',
                    height:'100dvh', minHeight:0, padding:isMobile ? '0 14px' : '0 32px' }}>

      {dragOver && (
        <div style={{
          position:'absolute', inset:0, zIndex:50, display:'flex', flexDirection:'column',
          alignItems:'center', justifyContent:'center', gap:10,
          background:'rgba(14,13,19,.92)', border:'2px dashed var(--teal)', borderRadius:14,
          color:'var(--teal)', fontSize:'1.05rem', fontWeight:600, pointerEvents:'none',
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
        padding:'16px 0 12px',
        flexShrink:0,
      }}>
        <div style={{ display:'flex', alignItems:'center', gap:10, minWidth:0 }}>
          {isMobile ? (
            <button onClick={() => setSidebarOpen(true)} title="Conversaciones"
              style={{ background:'none', border:'none', cursor:'pointer',
                       color:'var(--text)', padding:4, display:'flex', flexShrink:0 }}>
              <Menu size={22} />
            </button>
          ) : (
            <button onClick={() => setSidebarCollapsed(c => !c)}
              title={sidebarCollapsed ? 'Mostrar barra lateral' : 'Ocultar barra lateral'}
              style={{ background:'none', border:'none', cursor:'pointer',
                       color:'var(--text-muted)', padding:4, display:'flex', flexShrink:0 }}>
              <PanelLeft size={20} />
            </button>
          )}
          <img src={sphereLogo} alt="Contexto AI" width={isMobile ? 30 : 36} height={isMobile ? 30 : 36}
               style={{ display:'block', flexShrink:0 }} />
          <div style={{ minWidth:0 }}>
            <div style={{ fontWeight:800, fontSize:isMobile ? '.95rem' : '1rem', letterSpacing:'-.3px' }}>
              Contexto <span style={{ color:'var(--teal)' }}>AI</span>
            </div>
            {!isMobile && (
              <div style={{ fontSize:'.72rem', color:'var(--text-muted)' }}>
                Cada lugar tiene un aura · Quito
              </div>
            )}
          </div>
        </div>
      </header>

      {authOpen && (
        <Auth onClose={() => setAuthOpen(false)} onAuthed={(s) => { setSession(s); setAccessToken(s?.access_token) }} />
      )}
      {publishOpen && <PublishAsset onClose={() => setPublishOpen(false)} />}

      {/* ── Messages ── */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        style={{ flex:1, overflowY:'auto', padding:'20px 0', position:'relative' }}
      >
        {isEmpty && (
          <div style={{ textAlign:'center', paddingTop:isMobile ? 28 : 48 }}>
            <img src={sphereLogo} alt="Contexto AI" width={isMobile ? 100 : 128} height={isMobile ? 100 : 128}
                 style={{ display:'block', margin:'0 auto 24px',
                          filter:'drop-shadow(0 0 34px rgba(45,189,182,.55))',
                          animation:'floaty 4.5s ease-in-out infinite' }} />
            <h1 style={{ fontFamily:'var(--font-display)', fontWeight:800,
                         fontSize:isMobile ? '2rem' : '2.6rem', letterSpacing:'-1px', marginBottom:14, lineHeight:1.05 }}>
              Contexto <span style={{
                background:'linear-gradient(135deg, #5EEAD4, #2DBDB6 55%, #E0685A)',
                WebkitBackgroundClip:'text', backgroundClip:'text', WebkitTextFillColor:'transparent',
              }}>AI</span>
            </h1>
            <div style={{ fontFamily:'var(--font-mono)', fontSize:'.72rem', letterSpacing:'3px',
                          color:'var(--teal)', textTransform:'uppercase', marginBottom:18 }}>
              Cada lugar tiene un aura
            </div>
            <p style={{ color:'var(--text-mid)', fontSize:isMobile ? '.92rem' : '1rem', lineHeight:1.7,
                        maxWidth:560, margin:'0 auto 34px' }}>
              Tu agente inteligente que absorbe capas de contexto — ruido, seguridad, vida,
              historia — y te las traduce para que encuentres el lugar perfecto.
            </p>
            <div style={{ display:'flex', flexDirection:'column', gap:8, alignItems:'center' }}>
              {QUICK_PROMPTS.map((p, i) => (
                <button
                  key={i}
                  className="qp"
                  onClick={() => sendMessage(p)}
                  style={{
                    borderRadius:14, padding:'11px 18px', cursor:'pointer',
                    color:'var(--text)', fontSize:'.85rem', maxWidth:520, textAlign:'left',
                  }}
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
          title="Bajar al final"
          style={{
            position:'fixed', bottom:90, right:24, width:36, height:36,
            borderRadius:'50%', background:'var(--surface-2)', border:'none',
            boxShadow:'var(--shadow-md)',
            cursor:'pointer', color:'var(--teal)', display:'flex',
            alignItems:'center', justifyContent:'center', zIndex:10,
          }}
        >
          <ChevronDown size={16}/>
        </button>
      )}

      {/* ── Input ── */}
      <div style={{
        padding:'14px 0 18px', flexShrink:0,
      }}>
        <div style={{
          display:'flex', gap:8, alignItems:'flex-end',
          background: listening ? 'rgba(45,189,182,.16)' : 'rgba(20,44,43,.5)',
          backdropFilter:'blur(16px)', WebkitBackdropFilter:'blur(16px)',
          border:`1px solid ${listening ? 'var(--teal)' : 'rgba(45,189,182,.35)'}`, borderRadius:26, padding:'8px',
          transition:'border-color .2s, box-shadow .2s, background .2s',
          boxShadow: listening
            ? '0 0 0 1px var(--teal), 0 0 42px rgba(45,189,182,.5), 0 0 90px rgba(45,189,182,.22)'
            : '0 0 28px rgba(45,189,182,.20), 0 0 64px rgba(45,189,182,.09)',
        }}
          onFocusCapture={e => { e.currentTarget.style.borderColor='var(--teal)'; e.currentTarget.style.boxShadow='0 0 0 1px var(--teal), 0 0 34px rgba(45,189,182,.34), 0 0 72px rgba(45,189,182,.14)' }}
          onBlurCapture={e => { e.currentTarget.style.borderColor=listening ? 'var(--teal)' : 'rgba(45,189,182,.35)'; e.currentTarget.style.boxShadow=listening ? '0 0 0 1px var(--teal), 0 0 42px rgba(45,189,182,.5), 0 0 90px rgba(45,189,182,.22)' : '0 0 28px rgba(45,189,182,.20), 0 0 64px rgba(45,189,182,.09)' }}
        >
          <button
            onClick={toggleGeo}
            disabled={geoLoading}
            title={geo ? 'Ubicación activa' : 'Compartir mi ubicación'}
            style={{
              background: 'rgba(45,189,182,.12)',
              border: '1px solid rgba(45,189,182,.3)',
              borderRadius:999, width:38, height:38, flexShrink:0, cursor:'pointer',
              display:'flex', alignItems:'center', justifyContent:'center',
              color: 'var(--teal)', transition:'all .15s',
              boxShadow: geo ? '0 0 12px rgba(45,189,182,.4)' : 'none',
            }}
          >
            {geoLoading
              ? <RefreshCw size={16} style={{ animation:'spin 1s linear infinite' }}/>
              : <MapPin size={16}/>}
          </button>
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
            onClick={startVoice}
            title={listening ? 'Escuchando… toca para detener' : 'Hablar (dictado por voz)'}
            style={{
              background: listening ? 'var(--teal)' : 'rgba(45,189,182,.12)',
              border: `1px solid ${listening ? 'var(--teal)' : 'rgba(45,189,182,.3)'}`,
              borderRadius:999, width:38, height:38, flexShrink:0, cursor:'pointer',
              display:'flex', alignItems:'center', justifyContent:'center',
              color: listening ? '#0E0D13' : 'var(--teal)', transition:'all .15s',
              animation: listening ? 'pulseGlow 1.2s ease-in-out infinite' : 'none',
            }}
          >
            <Mic size={16}/>
          </button>
          <button
            onClick={() => sendMessage()}
            disabled={!input.trim() || loading}
            title="Enviar"
            style={{
              background: input.trim() && !loading ? 'var(--teal)' : 'rgba(45,189,182,.12)',
              border:'1px solid rgba(45,189,182,.3)', borderRadius:999, width:38, height:38,
              cursor: input.trim() && !loading ? 'pointer' : 'default', flexShrink:0,
              display:'flex', alignItems:'center', justifyContent:'center',
              color: input.trim() && !loading ? '#0E0D13' : 'var(--teal)',
              transition:'background .15s, box-shadow .15s',
              boxShadow: input.trim() && !loading ? '0 0 16px rgba(45,189,182,.4)' : 'none',
            }}
          >
            {loading
              ? <RefreshCw size={16} style={{ animation:'spin 1s linear infinite' }}/>
              : <Send size={16}/>
            }
          </button>
        </div>
        {listening && (
          <div style={{ marginTop:8, fontSize:'.72rem', color:'var(--teal)',
                        padding:'0 4px', textAlign:'center' }}>
            🎤 Escuchando… habla ahora
          </div>
        )}
      </div>

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: .3; transform: scale(.8); }
          50%       { opacity: 1;  transform: scale(1.1); }
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulseGlow {
          0%, 100% { box-shadow: 0 0 0 0 rgba(45,189,182,.5); }
          50%       { box-shadow: 0 0 0 6px rgba(45,189,182,0); }
        }
        @keyframes floaty {
          0%, 100% { transform: translateY(0); }
          50%       { transform: translateY(-7px); }
        }
        @media (prefers-reduced-motion: reduce) {
          [style*="floaty"] { animation: none !important; }
        }
      `}</style>
      </div>
      </div>
    </div>
  )
}
