import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import { X, Plus, Trash2, Store, Check, Loader, MapPin, Camera, Ban, AlertTriangle } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'
import { supabase } from './supabaseClient'

const C = {
  bg: 'var(--bg)', panel: 'var(--surface-1)', teal: 'var(--teal)', tealHi: 'var(--teal-bright)',
  coral: 'var(--coral)', text: 'var(--text)', muted: 'var(--text-mid)', line: 'var(--border)',
}

// Taxonomía CURADA de habitabilidad — el corredor elige de aquí (no texto libre,
// para no fragmentar ni "alucinar"). El emoji sirve también de ícono en el mapa.
const CATEGORIAS = [
  '🛒 Supermercado / Mercado',
  '💊 Farmacia',
  '🏥 Salud (clínica, consultorio, hospital)',
  '🎓 Educación (colegio, escuela, guardería)',
  '🚌 Transporte (parada, estación, terminal)',
  '🛡️ Seguridad (UPC, policía)',
  '🌳 Parque / Áreas verdes',
  '🍽️ Restaurante / Café',
  '🏦 Banco / Cajero',
  '⛪ Iglesia / Culto',
  '🏋️ Gimnasio / Deporte',
  '🏬 Centro comercial',
  '🔧 Hogar / Ferretería',
  '🐾 Veterinaria / Mascotas',
]

// El "loop" del Catastro Vivo: el corredor sabe antes que el mapa.
// Marca POIs cerrados (❌) y agrega los nuevos (➕). Su voz queda verificada.
export default function ActualizarEntorno({ activo, onClose }) {
  const [base, setBase] = useState([])          // servicios del mapa (hidratados)
  const [curaciones, setCuraciones] = useState([])
  const [verificado, setVerificado] = useState({ verificado: false, fecha: null })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [nuevo, setNuevo] = useState({ nombre: '', categoria: '', lat: null, lon: null, foto: null })
  const [geo, setGeo] = useState('idle')   // idle | capturando | ok | error
  const [uploading, setUploading] = useState(false)

  const cargar = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/api/v1/assets/${activo.id}/entorno`, { headers: apiHeaders() })
      setBase(data.servicios_base || [])
      setCuraciones(data.curaciones || [])
      setVerificado(data.verificado || { verificado: false, fecha: null })
    } catch {
      setError('No pudimos cargar el entorno. Reintenta en un momento')
    } finally { setLoading(false) }
  }, [activo.id])

  useEffect(() => { cargar() }, [cargar])

  const norm = (s) => (s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').trim().toLowerCase()
  const cerrados = new Set(curaciones.filter(c => c.accion === 'cerrado').map(c => norm(c.nombre)))
  const estaCerrado = (visible) => {
    const n = norm(visible)
    return [...cerrados].some(c => c && (c === n || c.includes(n) || n.includes(c)))
  }
  const agregados = curaciones.filter(c => c.accion === 'agregado')

  async function aplicar(payload) {
    setBusy(true); setError(null)
    try {
      const { data } = await axios.post(`${API_BASE}/api/v1/assets/${activo.id}/entorno`, payload,
        { headers: { 'Content-Type': 'application/json', ...apiHeaders() } })
      setCuraciones(data.curaciones || [])
      setVerificado(data.verificado || { verificado: false, fecha: null })
    } catch (err) {
      setError(err?.response?.data?.detail || 'No se pudo guardar. Reintenta')
    } finally { setBusy(false) }
  }

  async function deshacer(id) {
    setBusy(true); setError(null)
    try {
      const { data } = await axios.delete(`${API_BASE}/api/v1/assets/${activo.id}/entorno/${id}`, { headers: apiHeaders() })
      setCuraciones(data.curaciones || [])
      setVerificado(data.verificado || { verificado: false, fecha: null })
    } catch {
      setError('No se pudo deshacer. Reintenta')
    } finally { setBusy(false) }
  }

  // HEIC (iPhone/Samsung) → JPEG en el navegador antes de subir (carga diferida).
  async function aJpegSiHeic(file) {
    const esHeic = /\.(heic|heif)$/i.test(file.name) || /image\/hei[cf]/i.test(file.type || '')
    if (!esHeic) return file
    const { default: heic2any } = await import('heic2any')
    const blob = await heic2any({ blob: file, toType: 'image/jpeg', quality: 0.85 })
    const out = Array.isArray(blob) ? blob[0] : blob
    return new File([out], file.name.replace(/\.(heic|heif)$/i, '.jpg'), { type: 'image/jpeg' })
  }

  async function subirFoto(file) {
    if (!file) return
    if (!supabase) { setError('Subida no disponible (Storage no configurado).'); return }
    setError(null); setUploading(true)
    try {
      let f = file
      try { f = await aJpegSiHeic(file) } catch { setError('No se pudo convertir la foto HEIC. Súbela en JPG/PNG.'); return }
      const path = `entorno/${activo.id}/${Date.now()}-${Math.random().toString(36).slice(2, 7)}-${f.name.replace(/[^\w.\-]/g, '_')}`
      const { error: upErr } = await supabase.storage.from('evidencias').upload(path, f, { upsert: false })
      if (upErr) throw upErr
      const { data } = supabase.storage.from('evidencias').getPublicUrl(path)
      setNuevo(p => ({ ...p, foto: data.publicUrl }))
    } catch {
      setError('No se pudo subir la foto. Reintenta')
    } finally { setUploading(false) }
  }

  function capturarUbicacion() {
    if (!navigator.geolocation) { setGeo('error'); return }
    setGeo('capturando'); setError(null)
    navigator.geolocation.getCurrentPosition(
      (pos) => { setNuevo(p => ({ ...p, lat: pos.coords.latitude, lon: pos.coords.longitude })); setGeo('ok') },
      () => setGeo('error'),
      { enableHighAccuracy: true, timeout: 10000 },
    )
  }

  function agregarLugar(e) {
    e.preventDefault()
    const nombre = nuevo.nombre.trim()
    if (nombre.length < 2) { setError('Escribe el nombre del lugar.'); return }
    if (!nuevo.categoria) { setError('Elige una categoría (es obligatoria).'); return }
    // El corredor aporta el GPS (estoy aquí); el backend calcula la distancia real.
    aplicar({ accion: 'agregado', nombre, categoria: nuevo.categoria,
              lat: nuevo.lat, lon: nuevo.lon, foto: nuevo.foto })
    setNuevo({ nombre: '', categoria: '', lat: null, lon: null, foto: null }); setGeo('idle')
  }

  const inp = { width: '100%', padding: '9px 11px', borderRadius: 10, marginTop: 4, boxSizing: 'border-box',
    background: 'var(--surface-2)', border: `1px solid ${C.line}`, color: C.text, fontSize: '.88rem', outline: 'none' }
  const lbl = { fontSize: '.74rem', color: C.muted, fontWeight: 600 }
  const sec = { fontSize: '.72rem', color: C.tealHi, letterSpacing: '.5px', fontWeight: 700, margin: '20px 0 8px' }
  const chipBtn = (color) => ({ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '5px 10px',
    borderRadius: 8, border: `1px solid ${color}`, background: 'transparent', color, cursor: busy ? 'default' : 'pointer',
    fontSize: '.74rem', fontWeight: 600, opacity: busy ? 0.6 : 1 })

  return (
    <div onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}
      style={{ position: 'fixed', inset: 0, zIndex: 1100, display: 'flex', alignItems: 'center',
               justifyContent: 'center', padding: 16, background: 'rgba(0,0,0,.5)', backdropFilter: 'blur(6px)' }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 520, maxHeight: '92vh', overflowY: 'auto', position: 'relative',
                 background: C.panel,
                 border: `1px solid ${C.line}`, borderRadius: 22, padding: '24px 22px', color: C.text }}>
        <button onClick={onClose} aria-label="Cerrar"
          style={{ position: 'absolute', top: 14, right: 14, background: 'none', border: 'none', color: C.muted, cursor: 'pointer' }}>
          <X size={18} />
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 4 }}>
          <Store size={20} color={C.tealHi} />
          <div style={{ fontWeight: 800, fontSize: '1.05rem' }}>Actualizar entorno</div>
        </div>
        <p style={{ fontSize: '.8rem', color: C.muted, margin: '0 0 6px' }}>
          Tú conoces la zona mejor que el mapa. Marca lo que cerró y agrega lo nuevo —
          tu inmueble queda <strong style={{ color: C.tealHi }}>verificado</strong> y el agente responde con datos frescos.
        </p>
        {verificado.verificado && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 5, fontSize: '.76rem', color: C.tealHi, marginBottom: 4 }}>
            <Check size={14} /> Entorno verificado por ti{verificado.fecha ? ` · ${verificado.fecha}` : ''}
          </div>
        )}

        {error && <div style={{ display: 'flex', alignItems: 'center', gap: 5, color: C.coral, fontSize: '.82rem', marginTop: 8 }}><AlertTriangle size={14} /> {error}</div>}

        {loading ? (
          <div style={{ display: 'flex', justifyContent: 'center', padding: 30 }}>
            <Loader size={22} color={C.teal} style={{ animation: 'spin 1s linear infinite' }} />
          </div>
        ) : (
          <>
            {/* Servicios del mapa */}
            <div style={sec}>SERVICIOS DEL MAPA (toca lo que ya cerró)</div>
            {base.length === 0 && (
              <div style={{ fontSize: '.82rem', color: C.muted }}>No hay servicios cargados del mapa para este inmueble.</div>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
              {base.map((s, i) => {
                const cerrado = estaCerrado(s.visible)
                return (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
                                        padding: '8px 11px', borderRadius: 10, border: `1px solid ${C.line}`,
                                        background: cerrado ? 'rgba(224,104,90,.08)' : 'var(--surface-2)' }}>
                    <span style={{ fontSize: '.86rem', textDecoration: cerrado ? 'line-through' : 'none',
                                   color: cerrado ? C.muted : C.text }}>
                      {s.visible}{s.distancia_m ? ` · ~${s.distancia_m} m` : ''}
                    </span>
                    {cerrado ? (
                      <span style={{ fontSize: '.72rem', color: C.coral }}>cerrado</span>
                    ) : (
                      <button disabled={busy} onClick={() => aplicar({ accion: 'cerrado', nombre: s.visible })}
                        style={chipBtn(C.coral)}><Ban size={13} /> Cerró</button>
                    )}
                  </div>
                )
              })}
            </div>

            {/* Agregar un lugar nuevo */}
            <div style={sec}>AGREGAR UN LUGAR NUEVO</div>
            <form onSubmit={agregarLugar} style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <div>
                <label style={lbl}>Nombre del lugar</label>
                <input style={inp} value={nuevo.nombre} onChange={e => setNuevo(p => ({ ...p, nombre: e.target.value }))}
                  placeholder="Ej. Supermercado Santa María" />
              </div>
              <div>
                <label style={lbl}>Categoría</label>
                <select value={nuevo.categoria} onChange={e => setNuevo(p => ({ ...p, categoria: e.target.value }))}
                  style={{ ...inp, appearance: 'auto', cursor: 'pointer' }}>
                  <option value="">Elige una categoría…</option>
                  {CATEGORIAS.map(c => <option key={c} value={c} style={{ background: C.panel, color: C.text }}>{c}</option>)}
                </select>
              </div>
              <div>
                <label style={lbl}>Distancia</label>
                <button type="button" onClick={capturarUbicacion} disabled={busy || geo === 'capturando'}
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, width: '100%',
                           marginTop: 4, padding: '10px', borderRadius: 10, cursor: 'pointer', fontSize: '.84rem', fontWeight: 600,
                           background: geo === 'ok' ? 'rgba(45,189,182,.14)' : 'var(--surface-2)',
                           border: `1px solid ${geo === 'ok' ? C.teal : C.line}`, color: geo === 'ok' ? C.tealHi : C.text }}>
                  <MapPin size={15} />
                  {geo === 'ok' ? <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>Ubicación capturada <Check size={14} /></span> : geo === 'capturando' ? 'Capturando…' : 'Estoy aquí — usar mi ubicación'}
                </button>
                <div style={{ fontSize: '.72rem', color: geo === 'error' ? C.coral : C.muted, marginTop: 5 }}>
                  {geo === 'ok' ? 'Calcularemos la distancia exacta desde el inmueble.'
                    : geo === 'error' ? 'No se pudo obtener tu ubicación. Se agregará como “cerca”; puedes reintentar.'
                    : 'Párate junto al lugar y toca — medimos la distancia por ti, sin teclear metros.'}
                </div>
              </div>
              <div>
                <label style={lbl}>Foto del lugar (opcional)</label>
                <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, marginTop: 4,
                                padding: '10px', borderRadius: 10, cursor: uploading ? 'default' : 'pointer', fontSize: '.84rem',
                                fontWeight: 600, background: 'var(--surface-2)', border: `1px dashed ${C.line}`, color: C.text }}>
                  {uploading ? <Loader size={15} style={{ animation: 'spin 1s linear infinite' }} /> : <Camera size={15} />}
                  {uploading ? 'Subiendo…' : nuevo.foto ? 'Cambiar foto' : 'Tomar / subir foto'}
                  <input type="file" accept="image/*" capture="environment" style={{ display: 'none' }}
                    onChange={e => { if (e.target.files?.[0]) subirFoto(e.target.files[0]) }} />
                </label>
                {nuevo.foto && (
                  <img src={nuevo.foto} alt="lugar" style={{ marginTop: 8, width: '100%', maxHeight: 140, objectFit: 'cover', borderRadius: 10 }} />
                )}
                <div style={{ fontSize: '.7rem', color: C.muted, marginTop: 4 }}>
                  Se guarda ahora; se mostrará cuando tengamos el mapa propio — sin volver a fotografiar.
                </div>
              </div>
              <button type="submit" disabled={busy}
                style={{ marginTop: 4, padding: '10px', borderRadius: 10, border: 'none', cursor: busy ? 'default' : 'pointer',
                         fontWeight: 800, fontSize: '.88rem', background: `linear-gradient(90deg, ${C.teal}, ${C.tealHi})`,
                         color: '#0E0D13', opacity: busy ? 0.7 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                <Plus size={15} /> Agregar lugar
              </button>
            </form>

            {/* Lo que has curado (con deshacer) */}
            {curaciones.length > 0 && (
              <>
                <div style={sec}>TUS CAMBIOS</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {curaciones.map((c) => (
                    <div key={c.id} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
                                             padding: '7px 10px', borderRadius: 9, background: 'var(--surface-2)' }}>
                      <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '.82rem', color: C.text, minWidth: 0 }}>
                        {c.foto && <img src={c.foto} alt="" style={{ width: 34, height: 34, objectFit: 'cover', borderRadius: 6, flexShrink: 0 }} />}
                        <span style={{ minWidth: 0 }}>
                          {c.accion === 'cerrado' ? <Ban size={13} style={{ verticalAlign: 'middle' }} /> : <Plus size={13} style={{ verticalAlign: 'middle' }} />} {c.nombre}
                          {c.distancia_m ? ` · ~${c.distancia_m} m` : ''}
                          <span style={{ color: C.muted, fontSize: '.72rem' }}>
                            {c.accion === 'cerrado' ? ' (cerrado)' : ' (agregado)'}
                          </span>
                        </span>
                      </span>
                      <button disabled={busy} onClick={() => deshacer(c.id)} title="Deshacer"
                        style={{ background: 'none', border: 'none', color: C.muted, cursor: busy ? 'default' : 'pointer', padding: 4 }}>
                        <Trash2 size={15} />
                      </button>
                    </div>
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
