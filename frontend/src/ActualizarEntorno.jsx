import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import { X, Plus, Trash2, Store, Check, Loader } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'

const C = {
  bg: '#16151E', panel: '#1E1D28', teal: '#2DBDB6', tealHi: '#5EEAD4',
  coral: '#E0685A', text: '#EDEBF2', muted: '#9C99AC', line: 'rgba(45,189,182,.22)',
}

// El "loop" del Catastro Vivo: el corredor sabe antes que el mapa.
// Marca POIs cerrados (❌) y agrega los nuevos (➕). Su voz queda verificada.
export default function ActualizarEntorno({ activo, onClose }) {
  const [base, setBase] = useState([])          // servicios del mapa (hidratados)
  const [curaciones, setCuraciones] = useState([])
  const [verificado, setVerificado] = useState({ verificado: false, fecha: null })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [nuevo, setNuevo] = useState({ nombre: '', categoria: '', distancia_m: '' })

  const cargar = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API_BASE}/api/v1/assets/${activo.id}/entorno`, { headers: apiHeaders() })
      setBase(data.servicios_base || [])
      setCuraciones(data.curaciones || [])
      setVerificado(data.verificado || { verificado: false, fecha: null })
    } catch {
      setError('No pudimos cargar el entorno. Reintenta en un momento 🔄')
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
      setError(err?.response?.data?.detail || 'No se pudo guardar. Reintenta 🔄')
    } finally { setBusy(false) }
  }

  async function deshacer(id) {
    setBusy(true); setError(null)
    try {
      const { data } = await axios.delete(`${API_BASE}/api/v1/assets/${activo.id}/entorno/${id}`, { headers: apiHeaders() })
      setCuraciones(data.curaciones || [])
      setVerificado(data.verificado || { verificado: false, fecha: null })
    } catch {
      setError('No se pudo deshacer. Reintenta 🔄')
    } finally { setBusy(false) }
  }

  function agregarLugar(e) {
    e.preventDefault()
    const nombre = nuevo.nombre.trim()
    if (nombre.length < 2) { setError('Escribe el nombre del lugar.'); return }
    const dist = nuevo.distancia_m === '' ? null : Number(nuevo.distancia_m)
    aplicar({ accion: 'agregado', nombre, categoria: nuevo.categoria.trim() || null, distancia_m: dist })
    setNuevo({ nombre: '', categoria: '', distancia_m: '' })
  }

  const inp = { width: '100%', padding: '9px 11px', borderRadius: 10, marginTop: 4, boxSizing: 'border-box',
    background: 'rgba(255,255,255,.04)', border: `1px solid ${C.line}`, color: C.text, fontSize: '.88rem', outline: 'none' }
  const lbl = { fontSize: '.74rem', color: C.muted, fontWeight: 600 }
  const sec = { fontSize: '.72rem', color: C.tealHi, letterSpacing: '.5px', fontWeight: 700, margin: '20px 0 8px' }
  const chipBtn = (color) => ({ display: 'inline-flex', alignItems: 'center', gap: 5, padding: '5px 10px',
    borderRadius: 8, border: `1px solid ${color}`, background: 'transparent', color, cursor: busy ? 'default' : 'pointer',
    fontSize: '.74rem', fontWeight: 600, opacity: busy ? 0.6 : 1 })

  return (
    <div onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}
      style={{ position: 'fixed', inset: 0, zIndex: 1100, display: 'flex', alignItems: 'center',
               justifyContent: 'center', padding: 16, background: 'rgba(10,9,16,.78)', backdropFilter: 'blur(6px)' }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 520, maxHeight: '92vh', overflowY: 'auto', position: 'relative',
                 background: `radial-gradient(120% 90% at 30% 0%, ${C.panel} 0%, ${C.bg} 70%)`,
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
          <div style={{ fontSize: '.76rem', color: C.tealHi, marginBottom: 4 }}>
            ✓ Entorno verificado por ti{verificado.fecha ? ` · ${verificado.fecha}` : ''}
          </div>
        )}

        {error && <div style={{ color: C.coral, fontSize: '.82rem', marginTop: 8 }}>⚠️ {error}</div>}

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
                                        background: cerrado ? 'rgba(224,104,90,.08)' : 'rgba(255,255,255,.03)' }}>
                    <span style={{ fontSize: '.86rem', textDecoration: cerrado ? 'line-through' : 'none',
                                   color: cerrado ? C.muted : C.text }}>
                      {s.visible}{s.distancia_m ? ` · ~${s.distancia_m} m` : ''}
                    </span>
                    {cerrado ? (
                      <span style={{ fontSize: '.72rem', color: C.coral }}>cerrado</span>
                    ) : (
                      <button disabled={busy} onClick={() => aplicar({ accion: 'cerrado', nombre: s.visible })}
                        style={chipBtn(C.coral)}>❌ Cerró</button>
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
              <div style={{ display: 'flex', gap: 8 }}>
                <div style={{ flex: 1.4 }}>
                  <label style={lbl}>Categoría (opcional)</label>
                  <input style={inp} value={nuevo.categoria} onChange={e => setNuevo(p => ({ ...p, categoria: e.target.value }))}
                    placeholder="supermercado, restaurante…" />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={lbl}>Distancia (m)</label>
                  <input type="number" min={0} style={inp} value={nuevo.distancia_m}
                    onChange={e => setNuevo(p => ({ ...p, distancia_m: e.target.value }))} placeholder="150" />
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
                                             padding: '7px 10px', borderRadius: 9, background: 'rgba(255,255,255,.03)' }}>
                      <span style={{ fontSize: '.82rem', color: C.text }}>
                        {c.accion === 'cerrado' ? '🚫' : '➕'} {c.nombre}
                        {c.distancia_m ? ` · ~${c.distancia_m} m` : ''}
                        <span style={{ color: C.muted, fontSize: '.72rem' }}>
                          {c.accion === 'cerrado' ? ' (cerrado)' : ' (agregado)'}
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
