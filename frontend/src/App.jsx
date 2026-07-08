import { useState, useEffect, useRef, useMemo, useCallback, lazy, Suspense } from 'react'
import axios from 'axios'
import {
  Send, MapPin, RefreshCw, Trash2, Copy, CheckCheck, ChevronDown, PanelLeft,
  Share2, Volume2, ThumbsUp, ThumbsDown, ArrowUpToLine, Plus, ArrowUp, AudioLines
} from 'lucide-react'
import { supabase, authEnabled } from './supabaseClient'
import Auth from './Auth'
import MisPublicaciones from './MisPublicaciones'
import ConvierteteCorredor from './ConvierteteCorredor'
import ShareConversation from './ShareConversation'
import AnuncioView from './AnuncioView'
import ResultCards from './ResultCards'
import DeltaEncaje from './DeltaEncaje'
import Launcher from './Launcher'
import AttachSheet from './AttachSheet'

// Headers (backend key + Bearer del usuario) centralizados en api.js
import { API_BASE, apiHeaders, setAccessToken } from './api'
import { renderMarkdown } from './markdown'
import './App.css'
import ReviewStation from './ReviewStation'
import CRM from './CRM'
import ErrorBoundary from './ErrorBoundary'
import Sidebar from './Sidebar'
import sphereLogo from './assets/sphere.svg'

// Carga diferida: MapLibre (pesado) solo se descarga al abrir el Mapa.
const MapView = lazy(() => import('./MapView'))
// Mapa Vivo (modo ZONA): la semilla de mapa que nace inline bajo la respuesta del
// agente. Lazy → MapLibre solo se carga cuando aparece una semilla, no en el bundle base.
const MapSeed = lazy(() => import('./MapSeed'))
const CompararMap = lazy(() => import('./CompararMap'))

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

// Convierte una clave VAPID base64url a Uint8Array para pushManager.subscribe().
function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  return Uint8Array.from([...raw].map(c => c.charCodeAt(0)))
}

// ID estable por dispositivo/navegador. Hace que la sesión del QR sea PRIVADA por
// visitante (cada quien su conversación del inmueble), no compartida entre todos.
const DEVICE_KEY = 'contexto_ai_device_id'
function getDeviceId() {
  try {
    let id = localStorage.getItem(DEVICE_KEY)
    if (!id) { id = (crypto.randomUUID?.() || (Date.now() + Math.random().toString(36).slice(2))); localStorage.setItem(DEVICE_KEY, id) }
    return id
  } catch { return 'anon' }
}
// Sesión del QR: única por (inmueble × dispositivo).
const qrSessionId = (id) => `qr-${id}-${getDeviceId()}`

// renderMarkdown se movió a ./markdown.js (compartido con el CRM Vivo). Ver import arriba.

// ── Sub-components ──────────────────────────────────────────
function _plainText(md) {
  return (md || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#*_`>|-]/g, ' ')
    .replace(/\[(.*?)\]\(.*?\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim()
}

function ActBtn({ title, onClick, active, children }) {
  const [hover, setHover] = useState(false)
  return (
    <div style={{ position: 'relative', display: 'flex' }}
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <button onClick={onClick} aria-label={title}
        style={{
          background: hover ? 'rgba(255,255,255,.06)' : 'none', border: 'none', cursor: 'pointer',
          padding: 5, borderRadius: 6, color: active ? 'var(--teal)' : 'var(--text-muted)', display: 'flex',
          transition: 'background .12s',
        }}>
        {children}
      </button>
      {hover && (
        <span style={{
          position: 'absolute', bottom: 'calc(100% + 6px)', left: '50%', transform: 'translateX(-50%)',
          background: '#1E1D28', border: '1px solid rgba(255,255,255,.12)', color: 'var(--text)',
          fontSize: '.7rem', padding: '4px 9px', borderRadius: 7, whiteSpace: 'nowrap',
          pointerEvents: 'none', zIndex: 30, boxShadow: '0 4px 14px rgba(0,0,0,.45)',
        }}>
          {title}
        </span>
      )}
    </div>
  )
}

function Message({ msg, onCopy, copied, onScrollTop, onShare, onOpenAnuncio, onOpenMap, isLast, sessionId, mapBboxRef }) {
  const isUser = msg.role === 'user'
  const sustancioso = !isUser && ((msg.toolCalls?.length > 0) || (msg.content?.length > 450))
  const [speaking, setSpeaking] = useState(false)
  const [feedback, setFeedback] = useState(null)  // 'up' | 'down' | null
  // Sync lista⇄mapa (Mapa Vivo ZONA): {id, origen} del inmueble resaltado, compartido por
  // MapSeed y ResultCards → hover en un pin resalta su tarjeta (y al revés). El `origen`
  // ('map' | 'card') decide si el carrusel se desliza (solo cuando el hover viene del mapa,
  // nunca por el hover de la propia tarjeta). Grace period: al salir (id=null) esperamos
  // 120ms antes de apagar, para NO parpadear al cruzar el hueco mapa↔carrusel.
  const [pinActivo, setPinActivo] = useState(null)
  const limpiarPinRef = useRef(null)
  const activarPin = (id, origen) => {
    clearTimeout(limpiarPinRef.current)
    if (id == null) limpiarPinRef.current = setTimeout(() => setPinActivo(null), 120)
    else setPinActivo({ id, origen })
  }
  useEffect(() => () => clearTimeout(limpiarPinRef.current), [])
  // Modo COMPARAR (tarea #21): hasta 2 inmuebles del turno → delta de encaje contra lo
  // declarado. El número sale del motor DETERMINÍSTICO del backend (/comparar), no del LLM.
  const [comparar, setComparar] = useState([])       // ids elegidos (máx 2)
  const [delta, setDelta] = useState(null)           // {ok, delta, cards} | {ok:false,message} | null
  const [deltaLoading, setDeltaLoading] = useState(false)
  const toggleComparar = useCallback((id) => setComparar((prev) =>
    prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id].slice(-2)), [])
  const comparaKey = comparar.join('|')
  useEffect(() => {
    if (comparar.length !== 2) { setDelta(null); setDeltaLoading(false); return }
    let cancel = false
    setDeltaLoading(true); setDelta(null)
    axios.post(`${API_BASE}/api/v1/chat/comparar`,
      { session_id: sessionId, id_a: comparar[0], id_b: comparar[1] }, { headers: apiHeaders() })
      .then(({ data }) => { if (!cancel) setDelta(data) })
      .catch(() => { if (!cancel) setDelta({ ok: false, message: 'No pude comparar ahora mismo.' }) })
      .finally(() => { if (!cancel) setDeltaLoading(false) })
    return () => { cancel = true }
  }, [comparaKey, sessionId])  // eslint-disable-line react-hooks/exhaustive-deps
  // renderMarkdown es caro; el sync re-renderiza este Message en cada hover. Memoizamos el
  // HTML para re-parsear SOLO cuando cambia el contenido, no en cada movimiento del ratón.
  const htmlContent = useMemo(() => (isUser ? '' : renderMarkdown(msg.content)), [isUser, msg.content])

  const toggleSpeak = () => {
    const synth = window.speechSynthesis
    if (!synth) return
    if (speaking) { synth.cancel(); setSpeaking(false); return }
    const u = new SpeechSynthesisUtterance(_plainText(msg.content))
    u.lang = 'es-419'
    u.onend = () => setSpeaking(false)
    u.onerror = () => setSpeaking(false)
    setSpeaking(true); synth.speak(u)
  }

  // El icono de esfera ocupa 32px + 10px de gap = 42px de indent para alinear las tarjetas
  const AVATAR_INDENT = 42

  return (
    <div style={{
      display:'flex', flexDirection:'column',
      alignItems: isUser ? 'flex-end' : 'flex-start',
      marginBottom:16,
    }}>
      {/* ── Fila: avatar + burbuja de texto ── */}
      <div style={{ display:'flex', gap:10, alignSelf:'stretch', justifyContent: isUser ? 'flex-end' : 'flex-start' }}>
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
                dangerouslySetInnerHTML={{ __html: htmlContent }}
              />
            )}
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

      {/* ── Tarjetas: FUERA del maxWidth 78%, ancho completo del chat ──
           paddingLeft = AVATAR_INDENT para alinear con el inicio del texto */}
      {!isUser && msg.results?.length > 0 && (
        <div style={{ paddingLeft: AVATAR_INDENT, width:'100%', boxSizing:'border-box' }}>
          {/* ★ Mapa Vivo (modo ZONA): la semilla de mapa NACE en el hilo — los
              resultados del turno leídos como espacio. Invitación viva que se abre
              al mapa completo, no un botón del rail. (docs/SPEC_Mapa_Vivo.md) */}
          <Suspense fallback={null}>
            <MapSeed results={msg.results} mapSeed={msg.mapSeed} onOpen={onOpenAnuncio} onExpand={onOpenMap}
                     isLast={isLast} activeId={pinActivo?.id ?? null} onActive={activarPin} bboxRef={mapBboxRef} />
          </Suspense>
          <ResultCards results={msg.results} onOpen={onOpenAnuncio} activeId={pinActivo?.id ?? null}
                       activeOrigin={pinActivo?.origen ?? null} onActive={activarPin}
                       seleccionComparar={comparar}
                       onToggleComparar={msg.results.length >= 2 ? toggleComparar : undefined} />
          {/* Modo COMPARAR (2 inmuebles marcados con ⇄): las DOS AURAS superpuestas en el mapa
              (SPEC — se VE el trade-off) + el delta dimensión-a-dimensión debajo. */}
          {comparar.length === 2 && (
            <>
              <Suspense fallback={null}>
                <CompararMap ids={comparar} cards={delta?.cards || []} onClose={() => setComparar([])} />
              </Suspense>
              <DeltaEncaje data={delta} loading={deltaLoading} onClose={() => setComparar([])} />
            </>
          )}
        </div>
      )}

      {/* ── Botones de acción ── */}
      {!isUser && (
        <div style={{ paddingLeft: AVATAR_INDENT, display:'flex', alignItems:'center', gap:8, marginTop:6, flexWrap:'wrap' }}>
          {/* Compartir destacado */}
          <button onClick={onShare} title="Compartir esta conversación"
            style={{
              display:'flex', alignItems:'center', gap:6, padding:'6px 13px', borderRadius:999,
              background:'rgba(45,189,182,.13)', border:'1px solid rgba(45,189,182,.42)',
              color:'var(--teal-bright, #5EEAD4)', cursor:'pointer', fontSize:'.8rem', fontWeight:700,
              transition:'all .14s',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(45,189,182,.22)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(45,189,182,.13)' }}>
            <Share2 size={14}/> Compartir
          </button>
          {/* Acciones discretas */}
          <div style={{ display:'flex', alignItems:'center', gap:2 }}>
            <ActBtn title="Copiar" onClick={() => onCopy(msg.id, msg.content)} active={copied === msg.id}>
              {copied === msg.id ? <CheckCheck size={15}/> : <Copy size={15}/>}
            </ActBtn>
            <ActBtn title={speaking ? 'Detener audio' : 'Escuchar'} onClick={toggleSpeak} active={speaking}>
              <Volume2 size={15}/>
            </ActBtn>
            <ActBtn title="Me gusta" onClick={() => setFeedback(f => f === 'up' ? null : 'up')} active={feedback === 'up'}>
              <ThumbsUp size={15}/>
            </ActBtn>
            <ActBtn title="No me gusta" onClick={() => setFeedback(f => f === 'down' ? null : 'down')} active={feedback === 'down'}>
              <ThumbsDown size={15}/>
            </ActBtn>
            <ActBtn title="Ir al inicio de la conversación" onClick={onScrollTop}><ArrowUpToLine size={15}/></ActBtn>
          </div>
        </div>
      )}

      {/* ── Nudge contextual: tras análisis sustanciosos, solo en la última respuesta ── */}
      {sustancioso && isLast && (
        <div style={{
          paddingLeft: AVATAR_INDENT, width:'100%', boxSizing:'border-box', marginTop:12,
        }}>
          <div style={{
            padding:'11px 13px', borderRadius:14,
            background:'rgba(45,189,182,.06)', border:'1px solid rgba(45,189,182,.2)',
            display:'flex', alignItems:'center', gap:12, flexWrap:'wrap',
          }}>
            <span style={{ flex:1, minWidth:190, fontSize:'.8rem', lineHeight:1.45, color:'var(--text-mid, #C9C6D6)' }}>
              💬 ¿Le sirve a alguien que decide contigo? Compártelo con tu <strong style={{ color:'var(--teal-bright, #5EEAD4)' }}>pareja, corredor o cliente</strong>.
            </span>
            <button onClick={onShare}
              style={{
                display:'flex', alignItems:'center', gap:6, padding:'7px 14px', borderRadius:999,
                background:'linear-gradient(90deg, #1A7A76, #2DBDB6)', border:'none',
                color:'#0E0D13', cursor:'pointer', fontSize:'.8rem', fontWeight:800, whiteSpace:'nowrap',
              }}>
              <Share2 size={14}/> Compartir
            </button>
          </div>
        </div>
      )}

      {/* ── Timestamp ── */}
      <div style={{ paddingLeft: isUser ? 0 : AVATAR_INDENT, fontSize:'.72rem', color:'var(--text-muted)', marginTop:4,
                    textAlign: isUser ? 'right' : 'left' }}>
        {msg.time}
      </div>
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
// Los chips de INTENCIÓN viven ahora en Launcher.jsx (pantalla inicial limpia).
export default function App() {
  // Deep link de QR: /a/{uuid} → sesión determinística qr-{id}
  const deepLinkId = (window.location.pathname.match(/^\/a\/([0-9a-fA-F-]{36})$/) || [])[1] || null
  const shareToken = (window.location.pathname.match(/^\/s\/([A-Za-z0-9_-]+)$/) || [])[1] || null
  const initialQ = new URLSearchParams(window.location.search).get('q')   // pregunta que llega desde un link compartido
  // Al abrir: chat nuevo y limpio (estilo Claude). Las conversaciones previas
  // quedan accesibles en el sidebar. Excepción: deep-link por QR (carga ese activo).
  const [sessionId, setSessionId] = useState(() => deepLinkId ? qrSessionId(deepLinkId) : 'session-' + crypto.randomUUID())
  const [messages, setMessages]   = useState([])
  const [input, setInput]         = useState('')
  const [loading, setLoading]     = useState(false)
  const [error, setError]         = useState(null)
  const [copied, setCopied]       = useState(null)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  const [view, setView] = useState('chat')  // 'chat' | 'review' | 'map'
  // Mapa Vivo: ids del turno con que se abrió el mapa completo (modo ZONA). Si está set,
  // el mapa muestra SOLO esos inmuebles (la traducción de la conversación); si es null,
  // muestra el catastro completo (entrada desde el rail/barra). (docs/SPEC_Mapa_Vivo.md)
  const [mapSeed, setMapSeed] = useState(null)
  // Encaje por-id del turno con el que se abrió el mapa full-screen → colorea los puntos por
  // ENCAJE (SPEC). null = sin preferencias / entrada por el rail → el mapa cae a color por ruido.
  const [mapEncaje, setMapEncaje] = useState(null)
  // Handoff de cámara entre turnos (SPEC "arribo"): guarda el encuadre {center,zoom} del mapa
  // vivo del turno anterior → el mapa del turno nuevo VUELA desde ahí. Ref único compartido (un
  // solo mapa vivo a la vez); se resetea al cambiar de sesión (no volar desde un encuadre ajeno).
  const mapBboxRef = useRef(null)
  // QR (/a/{id}) → primero la página de anuncio (la "puerta"); el chat con el agente
  // (runtime propio) se abre solo al tocar el CTA. No arrancamos en el informe.
  const [anuncioMode, setAnuncioMode] = useState(!!deepLinkId)
  // Feedback en vivo (2026-07-02): "ampliar" el mapa del anuncio NO debe abrir un modal
  // aislado — debe llevar al mismo Mapa Vivo conversacional que ya existe en el chat
  // ("Pregúntale al mapa", "Recorre esta zona", colores de encaje). MapView es agnóstico
  // de sesión de chat (solo necesita seedIds), así que aquí no hace falta crear una
  // conversación — solo mostrar MapView sembrado con ESTE inmueble mientras estamos en el
  // flujo standalone de anuncioMode (que no pasa por el `view` state machine de abajo).
  const [anuncioMapaOpen, setAnuncioMapaOpen] = useState(false)
  // Detalle de un inmueble abierto desde una tarjeta de resultado (overlay sin
  // perder el chat). Reutiliza AnuncioView; al cerrar volvemos a la conversación.
  const [openAnuncioId, setOpenAnuncioId] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  const [geo, setGeo] = useState(null)          // {lat, lon} | null — ubicación del usuario
  const [geoLoading, setGeoLoading] = useState(false)
  const [isMobile, setIsMobile] = useState(() => window.matchMedia('(max-width: 768px)').matches)
  const [sidebarOpen, setSidebarOpen] = useState(false)   // cajón móvil
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)  // colapsar sidebar (escritorio)
  const [listening, setListening] = useState(false)       // dictado por voz
  const recognitionRef = useRef(null)
  const lastAiRef = useRef('')   // última respuesta del agente (para bloquear ecos/reenvíos)
  const [modoCorredor, setModoCorredor] = useState(false)  // handoff en vivo: el lead habla con el corredor (no el AI)
  const handoffSeenRef = useRef(0)                          // último id de mensaje de handoff visto
  const [handoffPendiente, setHandoffPendiente] = useState(false)  // handoff esperando registro del lead
  const [corredorWhatsapp, setCorredorWhatsapp] = useState(null)   // WhatsApp del corredor (si lo cargó) → botón wa.me en el handoff
  const [session, setSession] = useState(null)            // sesión de Supabase | null
  const [authOpen, setAuthOpen] = useState(false)         // modal de login/registro
  const [rol, setRol] = useState(null)                    // rol del usuario (cliente/corredor/inmobiliaria)
  const [publishOpen, setPublishOpen] = useState(false)   // modal "Mis publicaciones"
  const [upgradeOpen, setUpgradeOpen] = useState(false)   // modal "Conviértete en corredor"
  const [shareOpen, setShareOpen] = useState(false)       // modal "Compartir conversación"
  const [attachOpen, setAttachOpen] = useState(false)     // hoja "Adjuntar" (el "+" del dock → búsqueda visual)
  const [shared, setShared] = useState(null)              // datos de una conversación compartida (visor)
  const [sharedErr, setSharedErr] = useState(false)
  const [shareInput, setShareInput] = useState('')        // input "sigue preguntándole al agente" en el visor

  // Visor público de conversación compartida (/s/{token}) — solo lectura, sin login.
  // El scroll lo maneja el contenedor flex interno (como la app principal), así que
  // el overflow:hidden global del body no estorba.
  useEffect(() => {
    if (!shareToken) return
    axios.get(`${API_BASE}/api/v1/chat/shared/${shareToken}`)
      .then(({ data }) => setShared(data))
      .catch(() => setSharedErr(true))
  }, [])

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

  const logout = useCallback(() => {
    // Limpiamos el estado local PRIMERO para que la UI responda al instante.
    // Si esperáramos el await de signOut() (que hace una llamada de red para
    // revocar el token) y la red está lenta o falla, la UI quedaría congelada.
    setSession(null); setAccessToken(null); setRol(null)
    setView('chat'); setSidebarOpen(false)
    // scope:'local' borra la sesión de este dispositivo sin round-trip global.
    // Fire-and-forget: no bloquea la UI; si falla, el estado local ya se limpió.
    if (authEnabled) {
      supabase.auth.signOut({ scope: 'local' }).catch(() => {})
    }
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

  // Quita el bloque interno "[Contexto del sistema: …]" que se inyecta al agente
  // (ubicación/reglas) para que NUNCA se muestre al usuario al restaurar el historial.
  const limpiarCtx = (m) => {
    if (m.role !== 'user' || !m.content) return m.content
    // Mensaje técnico del QR → texto amigable (no exponer la instrucción interna).
    if (m.content.startsWith('El usuario escaneó el QR')) return '📍 Escaneé el QR de este inmueble. ¿Qué sabes de él?'
    const i = m.content.indexOf('[Contexto del sistema')
    return (i === -1 ? m.content : m.content.slice(0, i)).trim()
  }

  // Restore history from API on mount / session change
  useEffect(() => {
    // Nueva sesión (o vacía) → resetea el handoff de cámara ANTES de cualquier early-return,
    // para que el 1er mapa haga ease-in y NO vuele desde el encuadre de la sesión anterior.
    mapBboxRef.current = null
    if (skipFirstRestore.current) { skipFirstRestore.current = false; return }
    axios.get(`${API_BASE}/api/v1/chat/${sessionId}/history`, { headers: apiHeaders() })
      .then(({ data }) => {
        if (!data.messages?.length) return
        const restored = data.messages.map((m, i) => ({
          id: `restored-${i}`,
          role: m.role === 'user' ? 'user' : 'ai',
          content: limpiarCtx(m),
          time: '',
          toolCalls: [],
          results: Array.isArray(m.results) ? m.results : [],
          mapSeed: m.map_seed || null,  // directiva de mapa del turno restaurado (SPEC_Mapa_Vivo)
        }))
        setMessages(restored)
        const lastAi = [...restored].reverse().find(m => m.role === 'ai')
        lastAiRef.current = lastAi?.content || ''
      })
      .catch(() => {}) // silent — no history yet
  }, [sessionId])

  // Deep link de QR (letrero inteligente): /a/{id}.
  // - Si el lead ya pidió corredor en este inmueble (handoff activo) → REANUDA esa
  //   conversación para que vea la respuesta del corredor (no se pierde al volver).
  // - Si no → apertura FRESCA en cápsula (sesión nueva, sin replay del muro viejo).
  const loadFromDeepLink = useCallback(async (id) => {
    const storeKey = 'ctx_qr_' + id

    // ¿Conversación con corredor en curso para este inmueble en este dispositivo?
    const prev = localStorage.getItem(storeKey)
    if (prev) {
      try {
        const { data: h } = await axios.get(`${API_BASE}/api/v1/chat/${prev}/handoff`, { headers: apiHeaders() })
        if (h?.activo) {
          setSessionId(prev)
          const hist = await axios.get(`${API_BASE}/api/v1/chat/${prev}/history`, { headers: apiHeaders() })
            .then(r => r.data).catch(() => ({ messages: [] }))
          const base = (hist.messages || []).map((m, i) => ({
            id: `r-${i}`, role: m.role === 'user' ? 'user' : 'ai', content: limpiarCtx(m), time: '', toolCalls: [],
            results: Array.isArray(m.results) ? m.results : [] }))
          const hmsgs = (h.mensajes || []).map((m) => ({
            id: `h-${m.id}`, role: m.autor === 'corredor' ? 'ai' : 'user',
            content: m.autor === 'corredor' ? `👤 Corredor: ${m.texto}` : m.texto, time: '', toolCalls: [] }))
          for (const m of (h.mensajes || [])) handoffSeenRef.current = Math.max(handoffSeenRef.current, m.id)
          setMessages([...base, ...hmsgs])
          setModoCorredor(true)
          return
        }
      } catch { /* sin handoff: seguimos a cápsula fresca */ }
    }

    const sid = `${qrSessionId(id)}-${Math.random().toString(36).slice(2, 8)}`
    localStorage.setItem(SESSION_KEY, sid)
    localStorage.setItem(storeKey, sid)
    setSessionId(sid)

    const t = new Date().toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' })
    setMessages([{ id: crypto.randomUUID(), role:'user',
      content:'📍 Escaneé el QR de este inmueble. ¿Qué sabes de él?', time:t, toolCalls:[] }])
    setLoading(true)
    try {
      const { data } = await axios.post(`${API_BASE}/api/v1/chat/`, {
        message: `El usuario escaneó el QR del inmueble ${id} y abrió el chat. ABRE EN MODO CÁPSULA (no un informe): consulta el inmueble con tool_fetch_asset_lifecycle_specs y responde corto y cálido — un saludo, UN dato memorable y verificable del inmueble dicho con naturalidad (NO escribas etiquetas como "El pico:"), y un gancho con 2-3 caminos para profundizar. ADAPTA los caminos a la OPERACIÓN (campo "operacion"): si es ARRIENDO ofrece "cómo es vivir aquí / qué incluye el arriendo / estado del inmueble" y NUNCA "¿es buena inversión?"; si es VENTA sí puedes ofrecer "si es buena inversión". NO vuelques todos los datos; deja que el usuario elija. El informe completo solo si lo pide. Si el id no existe, dilo con honestidad.`,
        session_id: sid,
      }, { headers: apiHeaders() })
      setMessages(prev => [...prev, { id: crypto.randomUUID(), role:'ai', content: data.reply,
        time: new Date().toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' }),
        toolCalls: data.tool_calls_made > 0 ? Array(data.tool_calls_made).fill('t') : [] }])
      // Título limpio en la barra lateral (en vez del mensaje técnico).
      axios.patch(`${API_BASE}/api/v1/chat/sessions/${sid}`,
        { titulo: '📍 Inmueble escaneado (QR)' }, { headers: apiHeaders() }).catch(() => {})
    } catch {
      setError('No pudimos cargar este inmueble ahora mismo. Reintenta en un momento 🔄')
    } finally { setLoading(false) }
  }, [])

  useEffect(() => {
    // Con QR arrancamos en la página de anuncio (anuncioMode=true); el informe del
    // agente se dispara desde el CTA, no en el montaje.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (deepLinkId && !anuncioMode) loadFromDeepLink(deepLinkId)
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

  const handleCopy = useCallback(async (id, md) => {
    const text = md ?? id            // compat: si llega un solo argumento, es el texto
    const cid = md != null ? id : (text || '').slice(0, 20)
    // Inyecta bordes en línea para que las tablas conserven sus recuadros en Word/Docs.
    const body = renderMarkdown(text)
      .replaceAll('<table>', '<table cellspacing="0" style="border-collapse:collapse;border:1px solid #999;font-family:Calibri,Arial,sans-serif;">')
      .replaceAll('<th>', '<th style="border:1px solid #999;padding:6px 10px;background:#eef2f2;text-align:left;">')
      .replaceAll('<td>', '<td style="border:1px solid #999;padding:6px 10px;vertical-align:top;">')
    const html = `<div style="font-family:Calibri,Arial,sans-serif;">${body}</div>`
    try {
      if (navigator.clipboard?.write && window.ClipboardItem) {
        // Copia formato (Word/Docs conservan títulos, negritas y tablas) + texto plano.
        await navigator.clipboard.write([new window.ClipboardItem({
          'text/html': new Blob([html], { type: 'text/html' }),
          'text/plain': new Blob([text], { type: 'text/plain' }),
        })])
      } else {
        await navigator.clipboard.writeText(text)
      }
    } catch {
      try { await navigator.clipboard.writeText(text) } catch { /* ignore */ }
    }
    setCopied(cid)
    setTimeout(() => setCopied(null), 2000)
  }, [])

  const sendMessage = useCallback(async (text, geoOverride) => {
    const userText = (text ?? input).trim()
    if (!userText || loading) return
    // Guard: nunca reenviar la respuesta anterior del agente como si fuera del usuario
    // (eco por copiar/pegar o lazo de audio). Una pregunta real jamás es idéntica.
    if (lastAiRef.current && userText === lastAiRef.current.trim()) {
      setInput('')
      if (inputRef.current) inputRef.current.style.height = 'auto'
      setError('Eso es la respuesta anterior 🙂 Escribe tu pregunta.')
      return
    }
    const g = geoOverride || geo

    setInput('')
    if (inputRef.current) inputRef.current.style.height = 'auto'  // reinicia el auto-grow al enviar
    setError(null)

    const userMsg = {
      id: crypto.randomUUID(), role: 'user', content: userText,
      time: new Date().toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' }),
      toolCalls: [],
    }
    setMessages(prev => [...prev, userMsg])

    // Modo corredor: el mensaje va al corredor humano (in-platform), no al agente.
    if (modoCorredor) {
      try {
        await axios.post(`${API_BASE}/api/v1/chat/${sessionId}/handoff/mensaje`,
          { texto: userText }, { headers: apiHeaders() })
      } catch { setError('No se pudo enviar tu mensaje al corredor. Intenta de nuevo.') }
      return
    }

    setLoading(true)

    // Si la ubicación está activa, se la pasamos al agente como contexto
    // (sin ensuciar la burbuja visible). El agente usa tool_search_nearby_assets.
    const apiMessage = g
      ? `${userText}\n\n[Contexto del sistema: la ubicación GPS del usuario es lat=${g.lat}, lon=${g.lon}. REGLA: usa estas coordenadas con tool_analyze_location SOLO si el usuario pregunta por "aquí" / "mi zona" / "donde estoy" SIN nombrar otro lugar. Si el usuario nombra un sector, barrio o dirección específicos (p. ej. "La Carolina", "Cumbayá", una calle), GEOCODIFICA ESE lugar con tool_geocode_address y analiza ESE punto — NO uses estas coordenadas y NUNCA llames al lugar analizado con el nombre que pidió el usuario si no coinciden. Para inmuebles registrados, usa tool_search_nearby_assets.]`
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
        results: Array.isArray(data.results) ? data.results : [],
        // Directiva de mapa del turno (SPEC_Mapa_Vivo): el mapa la interpreta. Puede ser null.
        mapSeed: data.map_seed || null,
      }
      setMessages(prev => [...prev, aiMsg])
      lastAiRef.current = data.reply || ''
    } catch (err) {
      setError(
        err.response?.data?.detail
        ?? 'No pudimos conectar en este momento. Reintenta en unos segundos 🔄'
      )
    } finally {
      setLoading(false)
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [input, loading, sessionId, geo, modoCorredor])

  // Registra el Service Worker (notificaciones push nativas) una vez al montar.
  useEffect(() => {
    if ('serviceWorker' in navigator && 'PushManager' in window) {
      navigator.serviceWorker.register('/sw.js').catch(e => console.warn('SW:', e))
    }
  }, [])

  // Obtiene (o crea) la PushSubscription del navegador. Devuelve el JSON o null
  // si no hay soporte / el usuario denegó el permiso. Pide permiso explícitamente.
  const ensurePushSubscription = useCallback(async () => {
    const vapidKey = import.meta.env.VITE_VAPID_PUBLIC_KEY
    if (!vapidKey || !('serviceWorker' in navigator) || !('PushManager' in window)) return null
    try {
      if (Notification.permission === 'denied') return null
      if (Notification.permission === 'default') {
        const perm = await Notification.requestPermission()
        if (perm !== 'granted') return null
      }
      const reg = await navigator.serviceWorker.ready
      const existing = await reg.pushManager.getSubscription()
      const sub = existing || await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey),
      })
      return sub.toJSON()
    } catch (e) {
      console.warn('Push subscription:', e)
      return null
    }
  }, [])

  // Suscribe al LEAD a Web Push (ligada a su sesión de QR). Se llama al confirmar handoff.
  const subscribeToPush = useCallback(async (sid) => {
    const sub = await ensurePushSubscription()
    if (!sub) return
    try {
      await axios.post(`${API_BASE}/api/v1/chat/${sid}/handoff/push`, sub, { headers: apiHeaders() })
    } catch (e) { console.warn('Lead push:', e) }
  }, [ensurePushSubscription])

  // Fase 3: el COMPRADOR opta por recibir novedades verificadas del inmueble (reenganche
  // por valor). Captura su canal (push del navegador) con consentimiento explícito — así
  // el reenganche le llega a ÉL directo, no solo al corredor.
  const [reengancheOptIn, setReengancheOptIn] = useState(false)
  const subscribeLeadContacto = useCallback(async (sid) => {
    const sub = await ensurePushSubscription()   // null si deniega — igual guardamos el consentimiento
    try {
      await axios.post(`${API_BASE}/api/v1/chat/lead-contacto`,
        { session_id: sid, push_subscription: sub || null, consent: true },
        { headers: apiHeaders() })
      return true
    } catch (e) { console.warn('Lead contacto:', e); return false }
  }, [ensurePushSubscription])

  // Registra push + email del CORREDOR para avisarle de leads nuevos.
  //  - withPush=false → solo email (silencioso, sin pedir permiso). Al iniciar sesión.
  //  - withPush=true  → además pide permiso de notificación. Al abrir el CRM.
  const subscribeUserPush = useCallback(async (withPush) => {
    if (!session) return
    const sub = withPush ? await ensurePushSubscription() : null
    try {
      await axios.post(`${API_BASE}/api/v1/chat/push/subscribe`, { subscription: sub }, { headers: apiHeaders() })
    } catch (e) { console.warn('User push:', e) }
  }, [session, ensurePushSubscription])

  // Al iniciar sesión como corredor/inmobiliaria: registra el email (silencioso)
  // para poder avisarle por correo aunque no acepte notificaciones del navegador.
  useEffect(() => {
    if (session && (rol === 'corredor' || rol === 'inmobiliaria')) subscribeUserPush(false)
  }, [session, rol, subscribeUserPush])

  // Deep-link del corredor: una notificación de lead abre /?crm=1 → entra al CRM
  // en cuanto la sesión esté lista (con auth para poder cargar sus leads).
  const crmDeepLink = useRef(new URLSearchParams(window.location.search).get('crm') === '1')
  useEffect(() => {
    if (crmDeepLink.current && session && (rol === 'corredor' || rol === 'inmobiliaria')) {
      crmDeepLink.current = false
      window.history.replaceState({}, '', '/')   // limpia el ?crm=1
      setView('crm')
    }
  }, [session, rol])

  // Abre el CRM y aprovecha para pedir permiso de notificaciones nativas (contextual).
  const abrirCRM = useCallback(() => {
    setView('crm')
    setSidebarOpen(false)
    subscribeUserPush(true)
  }, [subscribeUserPush])

  // Handoff en vivo: el lead pide hablar con el corredor (dentro de Contexto).
  // Requiere registro (correo/Google) → identidad + poder avisarle. Si no hay
  // sesión, abrimos el registro y reintentamos el handoff al autenticarse.
  const iniciarHandoff = useCallback(async () => {
    if (authEnabled && !session) {
      setHandoffPendiente(true)
      setAuthOpen(true)
      return
    }
    try {
      const { data } = await axios.post(`${API_BASE}/api/v1/chat/${sessionId}/handoff`, {}, { headers: apiHeaders() })
      if (data?.corredor_whatsapp) setCorredorWhatsapp(data.corredor_whatsapp)
      setModoCorredor(true)
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(), role: 'ai',
        content: '🤝 Te conecté con el corredor. Escríbele aquí mismo — te responde en este chat, sin salir de Contexto.',
        time: new Date().toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' }), toolCalls: [],
      }])
      // Suscribe al lead a Web Push para recibir notificación nativa cuando el corredor responda.
      subscribeToPush(sessionId)
    } catch { setError('No se pudo conectar con el corredor en este momento.') }
  }, [sessionId, session, subscribeToPush])

  // Tras registrarse, continúa el handoff que quedó pendiente.
  useEffect(() => {
    if (session && handoffPendiente) { setHandoffPendiente(false); iniciarHandoff() }
  }, [session, handoffPendiente, iniciarHandoff])

  // Sondeo del handoff (solo en sesiones de QR): trae respuestas del corredor
  // y, si el corredor ya entró, activa el modo corredor aunque el lead recargue.
  useEffect(() => {
    if (!deepLinkId || anuncioMode) return
    let vivo = true
    const tick = async () => {
      try {
        const { data } = await axios.get(`${API_BASE}/api/v1/chat/${sessionId}/handoff`,
          { params: { desde: handoffSeenRef.current }, headers: apiHeaders() })
        if (!vivo || !data?.activo) return
        if (!modoCorredor) setModoCorredor(true)
        if (data?.corredor_whatsapp) setCorredorWhatsapp(data.corredor_whatsapp)
        const nuevos = (data.mensajes || []).filter(m => m.autor === 'corredor')
        for (const m of (data.mensajes || [])) handoffSeenRef.current = Math.max(handoffSeenRef.current, m.id)
        if (nuevos.length) {
          setMessages(prev => [...prev, ...nuevos.map(m => ({
            id: `h-${m.id}`, role: 'ai', content: `👤 Corredor: ${m.texto}`,
            time: new Date().toLocaleTimeString([], { hour:'2-digit', minute:'2-digit' }), toolCalls: [],
          }))])
        }
      } catch { /* silencioso */ }
    }
    const iv = setInterval(tick, 6000)
    tick()
    return () => { vivo = false; clearInterval(iv) }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deepLinkId, anuncioMode, sessionId, modoCorredor])

  // "Analiza dónde estás": pide la ubicación y dispara el análisis del lugar (global).
  const analizarMiUbicacion = useCallback(() => {
    const MSG = '¿Cómo es vivir aquí? Analiza el lugar donde estoy ahora.'
    if (geo) { sendMessage(MSG); return }
    if (!navigator.geolocation) { setError('Tu navegador no permite ubicación.'); return }
    setGeoLoading(true)
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const g = { lat: +pos.coords.latitude.toFixed(6), lon: +pos.coords.longitude.toFixed(6) }
        setGeo(g); setGeoLoading(false)
        sendMessage(MSG, g)
      },
      () => { setGeoLoading(false); setError('No pudimos obtener tu ubicación (permiso denegado).') },
      { enableHighAccuracy: true, timeout: 10000 },
    )
  }, [geo, sendMessage])

  // Enganche viral: si llega ?q= (desde un link compartido), auto-envía esa pregunta
  // en una sesión nueva → el visitante queda chateando en vivo con el agente.
  const qFired = useRef(false)
  useEffect(() => {
    if (qFired.current || !initialQ || deepLinkId || shareToken) return
    qFired.current = true
    window.history.replaceState({}, '', '/')   // limpia el ?q= de la URL
    setTimeout(() => sendMessage(initialQ), 150)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Dictado por voz (Web Speech API) — "hablarle al agente"
  const startVoice = useCallback(() => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    if (!SR) { setError('El dictado por voz no está disponible en este navegador. Prueba en Chrome.'); return }
    if (listening) { recognitionRef.current?.stop(); return }
    window.speechSynthesis?.cancel()  // corta el "Escuchar" (TTS) para que el micrófono no capte la voz del agente
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
    try { localStorage.removeItem('geoConsent'); localStorage.removeItem('ctx_lastpos'); localStorage.setItem('geoOptOut', '1') } catch { /* ignore */ }
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
        const g = { lat: +pos.coords.latitude.toFixed(6), lon: +pos.coords.longitude.toFixed(6) }
        setGeo(g)
        // Posición compartida con el Mapa (capturada una vez, sirve en todas las entradas).
        try { localStorage.setItem('geoConsent', '1'); localStorage.setItem('ctx_lastpos', JSON.stringify(g)) } catch { /* ignore */ }
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
      // Posición compartida: si el Mapa (u otra entrada) ya la capturó, úsala al instante.
      const s = JSON.parse(localStorage.getItem('ctx_lastpos') || 'null')
      if (s && typeof s.lat === 'number') setGeo(prev => prev || s)
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

  // Página de anuncio del QR (/a/{id}) — landing pública del inmueble. El CTA abre
  // el chat con el agente (runtime propio) y dispara el informe.
  if (deepLinkId && anuncioMode) {
    // "Ampliar" el mapa del anuncio → el Mapa Vivo completo, sembrado con ESTE inmueble
    // (no un modal aislado). Volver regresa al anuncio, no al chat (este flujo standalone
    // no tiene chat activo todavía — eso solo pasa al tocar el CTA "Chat").
    if (anuncioMapaOpen) {
      return (
        <div style={{ height:'100dvh', display:'flex', flexDirection:'column' }}>
          <div style={{ padding:'8px 16px' }}>
            <button onClick={() => setAnuncioMapaOpen(false)} style={{
              background:'none', border:'1px solid var(--border)', borderRadius:8,
              cursor:'pointer', color:'var(--text-muted)', padding:'6px 12px', fontSize:'.85rem',
            }}>← Volver al inmueble</button>
          </div>
          <div style={{ flex:1, minHeight:0 }}>
            <Suspense fallback={
              <div style={{ height:'100%', display:'grid', placeItems:'center', color:'var(--text-muted)' }}>
                Cargando mapa…
              </div>
            }>
              <MapView seedIds={[deepLinkId]} />
            </Suspense>
          </div>
        </div>
      )
    }
    return <AnuncioView id={deepLinkId}
      onChat={() => { setAnuncioMode(false); loadFromDeepLink(deepLinkId) }}
      onExpandMap={() => setAnuncioMapaOpen(true)} />
  }

  // Detalle abierto desde una tarjeta del chat: overlay sobre la conversación.
  // El chat (messages) sigue vivo en estado; al cerrar volvemos donde estábamos.
  if (openAnuncioId) {
    return <AnuncioView id={openAnuncioId}
      onBack={() => setOpenAnuncioId(null)}
      onChat={(info) => {
        setOpenAnuncioId(null)
        // Pequeño delay para que el overlay cierre y el chat se monte antes de enviar.
        const txt = info?.direccion
          ? `Cuéntame más sobre el inmueble en ${info.direccion}`
          : 'Cuéntame más sobre este inmueble'
        setTimeout(() => sendMessage(txt), 150)
      }}
      onExpandMap={() => {
        // Reusa el MISMO Mapa Vivo completo que ya usa el chat (view:'map' + mapSeed) —
        // sembrado solo con este inmueble, en vez del modal aislado del anuncio.
        const id = openAnuncioId
        setOpenAnuncioId(null)
        setMapSeed([id]); setMapEncaje(null)
        setView('map')
      }} />
  }

  // Visor público de conversación compartida (solo lectura)
  if (shareToken) {
    return (
      <div style={{ height:'100dvh', maxWidth:820, margin:'0 auto', padding:isMobile ? '0 16px' : '0 24px',
                    display:'flex', flexDirection:'column' }}>
        <header style={{ display:'flex', alignItems:'center', gap:10, padding:'16px 0 12px', flexShrink:0 }}>
          <img src={sphereLogo} alt="Contexto AI" width={32} height={32} />
          <div>
            <div style={{ fontWeight:800 }}>Contexto <span style={{ color:'var(--teal)' }}>AI</span></div>
            <div style={{ fontSize:'.72rem', color:'var(--text-muted)' }}>Conversación compartida · solo lectura</div>
          </div>
          <a href="/" style={{ marginLeft:'auto', fontSize:'.8rem', color:'var(--teal)',
                               textDecoration:'none', border:'1px solid rgba(45,189,182,.3)',
                               borderRadius:999, padding:'6px 14px' }}>Abrir Contexto AI</a>
        </header>
        <div style={{ flex:1, overflowY:'auto', WebkitOverflowScrolling:'touch', minHeight:0 }}>
        {sharedErr && (
          <div style={{ color:'var(--text-muted)', padding:'40px 0', textAlign:'center' }}>
            Este enlace no es válido o fue revocado.
          </div>
        )}
        {!shared && !sharedErr && (
          <div style={{ color:'var(--text-muted)', padding:'40px 0', textAlign:'center' }}>Cargando…</div>
        )}
        <div style={{ paddingBottom:24 }}>
          {shared?.messages?.map((m, i) => (
            <div key={i} style={{ display:'flex', justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
                                  marginBottom:16, gap:10 }}>
              {m.role !== 'user' && <img src={sphereLogo} alt="" width={30} height={30} style={{ flexShrink:0 }} />}
              <div style={{ maxWidth:'80%',
                            padding: m.role === 'user' ? '10px 14px' : 0,
                            borderRadius: m.role === 'user' ? '18px 18px 4px 18px' : 0,
                            background: m.role === 'user' ? 'linear-gradient(135deg, #1A7A76, #2DBDB6)' : 'transparent',
                            color: m.role === 'user' ? '#fff' : 'inherit', fontSize:'.92rem', lineHeight:1.65 }}>
                {m.role === 'user'
                  ? <span>{limpiarCtx(m)}</span>
                  : <div className="ai-content" dangerouslySetInnerHTML={{ __html: renderMarkdown(m.content) }} />}
              </div>
            </div>
          ))}
        </div>
        </div>

        {/* Superficie de conversión: el visitante sigue la conversación con el agente */}
        {shared && (
          <div style={{ flexShrink:0, paddingBottom:16, paddingTop:10, background:'#0E0D13',
                        borderTop:'1px solid #1E1D28' }}>
            <div style={{ fontSize:'.82rem', color:'var(--teal-bright)', marginBottom:8, textAlign:'center' }}>
              💬 Sigue tú la conversación con el agente
            </div>
            <form
              onSubmit={(e) => { e.preventDefault(); const t = shareInput.trim(); if (t) window.location.assign('/?q=' + encodeURIComponent(t)) }}
              style={{ display:'flex', gap:8, alignItems:'center', background:'rgba(20,44,43,.5)',
                       border:'1px solid rgba(45,189,182,.35)', borderRadius:26, padding:8,
                       boxShadow:'0 0 28px rgba(45,189,182,.2)' }}>
              <input value={shareInput} onChange={e => setShareInput(e.target.value)}
                placeholder="Pregúntale al agente sobre este inmueble o tu zona…"
                style={{ flex:1, background:'none', border:'none', outline:'none', color:'var(--text)',
                         fontSize:'.92rem', padding:'4px 10px' }} />
              <button type="submit" title="Preguntar"
                style={{ background:'var(--teal)', border:'none', borderRadius:999, width:38, height:38,
                         display:'flex', alignItems:'center', justifyContent:'center', cursor:'pointer', color:'#0E0D13' }}>
                <Send size={16}/>
              </button>
            </form>
            <div style={{ fontSize:'.72rem', color:'var(--text-muted)', textAlign:'center', marginTop:8 }}>
              Gratis · sin registro · <a href="/" style={{ color:'var(--teal)', textDecoration:'none' }}>Conoce Contexto AI</a>
            </div>
          </div>
        )}
      </div>
    )
  }

  // Vista de CRM del corredor (pantalla completa)
  if (view === 'crm') {
    return (
      <div style={{ height:'100dvh', display:'flex', flexDirection:'column' }}>
        <div style={{ padding:'8px 16px' }}>
          <button onClick={() => setView('chat')} style={{
            background:'none', border:'1px solid var(--border)', borderRadius:8,
            cursor:'pointer', color:'var(--text-muted)', padding:'6px 12px', fontSize:'.85rem',
          }}>← Volver al chat</button>
        </div>
        <div style={{ flex:1, minHeight:0 }}><ErrorBoundary label="el CRM"><CRM /></ErrorBoundary></div>
      </div>
    )
  }

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
            {/* key por seed → fuerza re-montar MapView cuando cambia el conjunto (de una
                semilla a otra, o a catastro completo): el filtro del geojson se aplica al
                montar, así que el remonte garantiza que nunca muestre un set stale. */}
            <MapView key={mapSeed ? mapSeed.join(',') : 'all'} seedIds={mapSeed} encajeById={mapEncaje} />
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
          onMap={() => { setMapSeed(null); setMapEncaje(null); setView('map') }}
          onReview={() => setView('review')}
          onCRM={abrirCRM}
          onUpgrade={() => setUpgradeOpen(true)}
          mobile={false}
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
              onMap={() => { setMapSeed(null); setMapEncaje(null); setView('map'); setSidebarOpen(false) }}
              onReview={() => { setView('review'); setSidebarOpen(false) }}
              onCRM={abrirCRM}
              onUpgrade={() => { setUpgradeOpen(true); setSidebarOpen(false) }}
              mobile={true}
              onClose={() => setSidebarOpen(false)}
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
        position:'relative', display:'flex', alignItems:'center', justifyContent:'center',
        padding:'16px 0 12px',
        flexShrink:0,
      }}>
        {/* Botón de menú/panel — anclado a la izquierda; el logo va centrado (estilo ASI:One) */}
        <div style={{ position:'absolute', left:0, top:'50%', transform:'translateY(-50%)' }}>
          {isMobile ? (
            <button onClick={() => setSidebarOpen(true)} title="Conversaciones"
              style={{ background:'none', border:'none', cursor:'pointer',
                       color:'var(--text)', padding:4, display:'flex', flexShrink:0 }}>
              <PanelLeft size={22} />
            </button>
          ) : (
            <button onClick={() => setSidebarCollapsed(c => !c)}
              title={sidebarCollapsed ? 'Mostrar barra lateral' : 'Ocultar barra lateral'}
              style={{ background:'none', border:'none', cursor:'pointer',
                       color:'var(--text-muted)', padding:4, display:'flex', flexShrink:0 }}>
              <PanelLeft size={20} />
            </button>
          )}
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:9 }}>
          <img src={sphereLogo} alt="Contexto AI" width={isMobile ? 26 : 30} height={isMobile ? 26 : 30}
               style={{ display:'block', flexShrink:0 }} />
          <div style={{ fontWeight:800, fontSize:isMobile ? '1rem' : '1.05rem', letterSpacing:'-.3px' }}>
            Contexto
          </div>
        </div>
      </header>

      {authOpen && (
        <Auth motivo={handoffPendiente ? 'Regístrate para hablar con un corredor — así puede responderte y avisarte.' : null}
          onClose={() => { setAuthOpen(false); setHandoffPendiente(false) }}
          onAuthed={(s) => { setSession(s); setAccessToken(s?.access_token) }} />
      )}
      {publishOpen && <MisPublicaciones onClose={() => setPublishOpen(false)} />}
      {upgradeOpen && (
        <ConvierteteCorredor
          onClose={() => setUpgradeOpen(false)}
          onUpgraded={(nuevoRol) => { setRol(nuevoRol); setUpgradeOpen(false); setPublishOpen(true) }}
        />
      )}
      {shareOpen && <ShareConversation sessionId={sessionId} onClose={() => setShareOpen(false)} />}
      {attachOpen && (
        <AttachSheet
          onClose={() => setAttachOpen(false)}
          onPickPhoto={(file) => {
            const r = new FileReader()
            r.onload = () => matchByImage(r.result)
            r.readAsDataURL(file)
          }}
        />
      )}

      {/* ── Messages ── */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        style={{ flex:1, overflowY:'auto', padding:'20px 0', position:'relative' }}
      >
        {isEmpty && (
          <Launcher
            onSend={sendMessage}
            onAnalyzeLocation={analizarMiUbicacion}
            onOpenMap={() => { setMapSeed(null); setMapEncaje(null); setView('map') }}
            onBroker={() => setUpgradeOpen(true)}
            geoLoading={geoLoading}
            isMobile={isMobile}
          />
        )}

        {messages.map((msg, i) => (
          <Message key={msg.id} msg={msg} onCopy={handleCopy} copied={copied}
            isLast={i === messages.length - 1} sessionId={sessionId} mapBboxRef={mapBboxRef}
            onScrollTop={() => scrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' })}
            onOpenAnuncio={setOpenAnuncioId}
            onOpenMap={(ids, encajeById) => {
              setMapSeed(Array.isArray(ids) && ids.length ? ids : null)
              setMapEncaje(encajeById && Object.keys(encajeById).length ? encajeById : null)
              setView('map')
            }}
            onShare={() => setShareOpen(true)} />
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
        {deepLinkId && (
          modoCorredor ? (
            <>
              <div style={{ display:'flex', alignItems:'center', gap:8, margin:'0 0 8px', padding:'8px 14px',
                            borderRadius:14, fontSize:'.78rem', color:'var(--teal)',
                            background:'rgba(45,189,182,.10)', border:'1px solid rgba(45,189,182,.3)' }}>
                🤝 Estás hablando con el corredor — te responde aquí mismo.
              </div>
              {/* Canal donde la gente ya está: si el corredor cargó su WhatsApp, el
                  interesado puede seguir la conversación ahí. Aditivo — el chat
                  in-platform de arriba sigue funcionando. */}
              {corredorWhatsapp && (
                <a href={`https://wa.me/${corredorWhatsapp}?text=${encodeURIComponent(
                     `Hola, vi tu inmueble en Contexto y me interesa: ${window.location.origin}/a/${deepLinkId}`)}`}
                   target="_blank" rel="noopener noreferrer"
                   style={{ display:'flex', alignItems:'center', justifyContent:'center', gap:7, margin:'0 0 8px',
                            padding:'10px 14px', borderRadius:14, textDecoration:'none', fontSize:'.82rem',
                            fontWeight:800, background:'#25D366', color:'#0B141A' }}>
                  💬 Continuar por WhatsApp
                </a>
              )}
            </>
          ) : (
            <div style={{ display:'flex', gap:8, justifyContent:'center', flexWrap:'wrap', margin:'0 0 8px' }}>
              <button onClick={iniciarHandoff}
                style={{ display:'flex', alignItems:'center', gap:7, padding:'7px 14px',
                         borderRadius:999, cursor:'pointer', fontSize:'.78rem', fontWeight:600,
                         background:'rgba(45,189,182,.10)', border:'1px solid rgba(45,189,182,.3)', color:'var(--teal)' }}>
                🤝 Hablar con el corredor
              </button>
              <button onClick={async () => { if (await subscribeLeadContacto(sessionId)) setReengancheOptIn(true) }}
                disabled={reengancheOptIn}
                title="Te avisamos solo si aparece algo verificado que te calce — sin spam."
                style={{ display:'flex', alignItems:'center', gap:7, padding:'7px 14px',
                         borderRadius:999, cursor: reengancheOptIn ? 'default' : 'pointer', fontSize:'.78rem', fontWeight:600,
                         background: reengancheOptIn ? 'rgba(232,184,75,.16)' : 'rgba(232,184,75,.10)',
                         border:'1px solid rgba(232,184,75,.35)', color:'#E8B84B' }}>
                {reengancheOptIn ? '✅ Te avisaremos' : '🔔 Avísame de novedades verificadas'}
              </button>
            </div>
          )
        )}
        <div style={{
          background:'var(--surface-1)',
          border:`1px solid ${listening ? 'var(--teal)' : 'var(--border)'}`, borderRadius:16, padding:'12px 14px',
          transition:'border-color .2s',
        }}>
          {/* Fila "Para:" — selector de destino, estilo ASI:One */}
          <div style={{ display:'flex', alignItems:'center', gap:9, marginBottom:11 }}>
            <span style={{ fontSize:'.78rem', color:'var(--text-dim)' }}>Para:</span>
            <span style={{ display:'inline-flex', alignItems:'center', gap:7, padding:'5px 11px', borderRadius:999,
                           border:'1px solid var(--border)', background:'var(--surface-2)' }}>
              <img src={sphereLogo} alt="" width={14} height={14} style={{ display:'block' }} />
              <span style={{ fontSize:'.8rem', fontWeight:600, color:'var(--text)' }}>Contexto</span>
              <span style={{ fontSize:'.74rem', color:'var(--text-dim)' }}>AI</span>
            </span>
          </div>
          <div style={{ height:1, background:'var(--border)', margin:'0 -14px 12px' }} />
          {/* Campo en su propia línea (como "Ask anything") */}
          <textarea
            ref={inputRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage() }
            }}
            placeholder="Pregúntame lo que sea…"
            disabled={loading}
            rows={1}
            style={{
              display:'block', width:'100%', background:'none', border:'none', outline:'none',
              color:'var(--text)', fontSize:'.98rem', resize:'none',
              lineHeight:1.5, maxHeight:120, overflowY:'auto',
              fontFamily:'inherit', marginBottom:12,
            }}
            onInput={e => {
              e.target.style.height = 'auto'
              e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
            }}
          />
          {/* Fila inferior: ubicación + "+" (izq) · Voz/Enviar (der) */}
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between' }}>
            <div style={{ display:'flex', alignItems:'center', gap:4 }}>
              <button
                onClick={toggleGeo}
                disabled={geoLoading}
                title={geo ? 'Ubicación activa — toca para quitar' : 'Compartir mi ubicación'}
                style={{
                  background:'none', border:'none', borderRadius:999, width:34, height:34, flexShrink:0, cursor:'pointer',
                  display:'flex', alignItems:'center', justifyContent:'center',
                  color: geo ? 'var(--teal-bright)' : 'var(--text-muted)', transition:'color .15s',
                }}
              >
                {geoLoading
                  ? <RefreshCw size={18} style={{ animation:'spin 1s linear infinite' }}/>
                  : <MapPin size={18}/>}
              </button>
              <button
                onClick={() => setAttachOpen(true)}
                title="Adjuntar — busca en el inventario por foto"
                style={{
                  background:'none', border:'none', borderRadius:999, width:34, height:34, flexShrink:0, cursor:'pointer',
                  display:'flex', alignItems:'center', justifyContent:'center', color:'var(--text-muted)',
                }}
              >
                <Plus size={20}/>
              </button>
            </div>
            {/* Voz (vacío) ↔ Enviar (con texto), como ASI:One */}
            {input.trim() ? (
              <button
                onClick={() => sendMessage()}
                disabled={loading}
                title="Enviar"
                style={{
                  background:'var(--teal-bright)', border:'none', borderRadius:999,
                  width:44, height:44, flexShrink:0, cursor: loading ? 'default' : 'pointer',
                  display:'flex', alignItems:'center', justifyContent:'center', color:'#06201C',
                }}
              >
                {loading
                  ? <RefreshCw size={18} style={{ animation:'spin 1s linear infinite' }}/>
                  : <ArrowUp size={20}/>}
              </button>
            ) : (
              <button
                onClick={startVoice}
                title={listening ? 'Escuchando… toca para detener' : 'Hablar (dictado por voz)'}
                style={{
                  display:'inline-flex', alignItems:'center', gap:8, flexShrink:0,
                  padding:'10px 16px', borderRadius:999, border:'none', cursor:'pointer',
                  background: listening ? 'var(--teal)' : 'var(--teal-bright)', color:'#06201C',
                  fontWeight:600, fontSize:'.9rem', fontFamily:'inherit',
                  animation: listening ? 'pulseGlow 1.2s ease-in-out infinite' : 'none',
                }}
              >
                <AudioLines size={17}/> Voz
              </button>
            )}
          </div>
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
          [style*="floaty"], [style*="spin 18s"] { animation: none !important; }
        }
      `}</style>
      </div>
      </div>
    </div>
  )
}
