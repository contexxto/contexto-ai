import { useState } from 'react'
import axios from 'axios'
import { X, MapPin, Check } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'
import sphereLogo from './assets/sphere.svg'

const C = {
  bg: '#16151E', panel: '#1E1D28', teal: '#2DBDB6', tealHi: '#5EEAD4',
  coral: '#E0685A', text: '#EDEBF2', muted: '#9C99AC', line: 'rgba(45,189,182,.25)',
}
const TIPOS = ['Departamento', 'Casa', 'Local Comercial', 'Oficina', 'Quinta']

export default function PublishAsset({ onClose, existing = null }) {
  const editando = !!existing
  const [f, setF] = useState({
    direccion: existing?.direccion || '',
    tipo_activo: existing?.tipo_activo || 'Departamento',
    operacion: (existing?.operacion || 'arriendo').toLowerCase(),
    precio: existing?.precio ?? '',
    piso_altura: existing?.piso_altura ?? 1,
    telefono_wsp: existing?.telefono_wsp || '',
    latitude: null, longitude: null,
  })
  const [loading, setLoading] = useState(false)
  const [geoMsg, setGeoMsg] = useState(null)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  const set = (k, v) => setF(prev => ({ ...prev, [k]: v }))

  const inputStyle = {
    width: '100%', padding: '11px 13px', borderRadius: 12, marginTop: 6, boxSizing: 'border-box',
    background: 'rgba(255,255,255,.04)', border: `1px solid ${C.line}`, color: C.text, fontSize: '.92rem', outline: 'none',
  }
  const label = { fontSize: '.78rem', color: C.muted, fontWeight: 600 }

  function usarUbicacion() {
    if (!navigator.geolocation) { setGeoMsg('Tu navegador no permite ubicación.'); return }
    setGeoMsg('Obteniendo ubicación…')
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        set('latitude', +pos.coords.latitude.toFixed(6))
        set('longitude', +pos.coords.longitude.toFixed(6))
        setGeoMsg('📍 Ubicación capturada (estás en el inmueble)')
      },
      () => setGeoMsg('No se pudo obtener la ubicación (permiso denegado).'),
      { enableHighAccuracy: true, timeout: 10000 },
    )
  }

  async function submit(e) {
    e.preventDefault()
    setError(null); setLoading(true)
    try {
      if (editando) {
        await axios.patch(`${API_BASE}/api/v1/assets/${existing.id}`, {
          direccion: f.direccion,
          tipo_activo: f.tipo_activo,
          operacion: f.operacion,
          precio: f.precio !== '' ? Number(f.precio) : null,
          piso_altura: Number(f.piso_altura) || 1,
          telefono_wsp: f.telefono_wsp || null,
        }, { headers: { 'Content-Type': 'application/json', ...apiHeaders() } })
        onClose()   // MisPublicaciones recarga la lista al cerrar
        return
      }
      const { data } = await axios.post(`${API_BASE}/api/v1/assets/publish`, {
        direccion: f.direccion,
        tipo_activo: f.tipo_activo,
        operacion: f.operacion,
        precio: f.precio ? Number(f.precio) : null,
        piso_altura: Number(f.piso_altura) || 1,
        telefono_wsp: f.telefono_wsp || null,
        latitude: f.latitude, longitude: f.longitude,
      }, { headers: { 'Content-Type': 'application/json', ...apiHeaders() } })
      setResult(data)
    } catch (err) {
      setError(err?.response?.data?.detail || (editando ? 'No se pudieron guardar los cambios.' : 'No se pudo publicar. Revisa la dirección.'))
    } finally { setLoading(false) }
  }

  return (
    <div onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}
      style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center',
               justifyContent: 'center', padding: 16, background: 'rgba(10,9,16,.72)', backdropFilter: 'blur(6px)' }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 460, maxHeight: '92vh', overflowY: 'auto', position: 'relative',
                 background: `radial-gradient(120% 90% at 30% 0%, ${C.panel} 0%, ${C.bg} 70%)`,
                 border: `1px solid ${C.line}`, borderRadius: 22, padding: '26px 24px', color: C.text,
                 boxShadow: '0 24px 60px rgba(0,0,0,.55), 0 0 40px rgba(45,189,182,.12)' }}>
        <button onClick={onClose} aria-label="Cerrar"
          style={{ position: 'absolute', top: 14, right: 14, background: 'none', border: 'none', color: C.muted, cursor: 'pointer' }}>
          <X size={18} />
        </button>

        {result ? (
          <div style={{ textAlign: 'center' }}>
            <div style={{ width: 46, height: 46, borderRadius: '50%', margin: '0 auto 12px',
                          background: 'rgba(45,189,182,.15)', border: `1px solid ${C.teal}`,
                          display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Check size={22} color={C.tealHi} />
            </div>
            <h2 style={{ margin: '0 0 6px', fontSize: '1.2rem' }}>¡Inmueble publicado! 🎉</h2>
            <p style={{ fontSize: '.85rem', color: C.muted, margin: '0 0 16px' }}>
              Ya tiene su agente 24/7. Imprime el QR y pégalo en tu letrero — quien lo escanee hablará con tu agente.
            </p>
            <div style={{ background: '#fff', borderRadius: 16, padding: 12, display: 'inline-block',
                          boxShadow: '0 0 26px rgba(45,189,182,.2)' }}>
              <img src={`${API_BASE}/api/v1/assets/${result.id}/qr.svg`} alt="QR del inmueble"
                   width={180} height={180} style={{ display: 'block' }} />
            </div>
            <div style={{ marginTop: 14, fontSize: '.74rem', color: C.muted, wordBreak: 'break-all' }}>
              {result.deep_link}
            </div>
            <div style={{ marginTop: 10, fontSize: '.78rem', color: C.tealHi }}>
              Capa base: ruido {result.scores?.score_ruido_predictivo} · walk {result.scores?.walk_score} · vegetación {result.scores?.porcentaje_cobertura_vegetal}%
            </div>
            {result.conectividad && (
              <div style={{ marginTop: 10, padding: '9px 12px', borderRadius: 12,
                            background: 'rgba(45,189,182,.08)', border: `1px solid ${C.line}`,
                            fontSize: '.78rem', color: C.text, textAlign: 'left' }}>
                <div style={{ color: C.muted, fontSize: '.68rem', letterSpacing: '.4px', marginBottom: 3 }}>
                  CONECTIVIDAD (señal de plusvalía)
                </div>
                {result.conectividad}
              </div>
            )}
            <button onClick={onClose}
              style={{ marginTop: 18, padding: '11px 22px', borderRadius: 12, border: 'none', cursor: 'pointer',
                       fontWeight: 800, background: `linear-gradient(90deg, ${C.teal}, ${C.tealHi})`, color: '#0E0D13' }}>
              Listo
            </button>
          </div>
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
              <img src={sphereLogo} width={30} height={30} alt="" style={{ filter: 'drop-shadow(0 0 8px rgba(45,189,182,.4))' }} />
              <div style={{ fontWeight: 800, fontSize: '1.05rem' }}>{editando ? 'Editar inmueble' : 'Publicar mi inmueble'}</div>
            </div>
            <p style={{ fontSize: '.82rem', color: C.muted, margin: '0 0 16px' }}>
              {editando
                ? 'Actualiza los datos de tu publicación. El QR y el enlace no cambian.'
                : 'Sin intermediarios. Tu inmueble tendrá su propio agente 24/7 y un QR para el letrero.'}
            </p>

            <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 13 }}>
              <div>
                <label style={label}>Dirección completa</label>
                <input style={inputStyle} required value={f.direccion} onChange={e => set('direccion', e.target.value)}
                       placeholder="Av. República del Salvador y Suecia, La Carolina, Quito" />
              </div>
              <div style={{ display: 'flex', gap: 10 }}>
                <div style={{ flex: 1 }}>
                  <label style={label}>Tipo</label>
                  <select style={inputStyle} value={f.tipo_activo} onChange={e => set('tipo_activo', e.target.value)}>
                    {TIPOS.map(t => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div style={{ width: 110 }}>
                  <label style={label}>Piso</label>
                  <input type="number" min={1} style={inputStyle} value={f.piso_altura} onChange={e => set('piso_altura', e.target.value)} />
                </div>
              </div>
              <div style={{ display: 'flex', gap: 10 }}>
                <div style={{ flex: 1 }}>
                  <label style={label}>Operación</label>
                  <select style={inputStyle} value={f.operacion} onChange={e => set('operacion', e.target.value)}>
                    <option value="arriendo">Arriendo</option>
                    <option value="venta">Venta</option>
                  </select>
                </div>
                <div style={{ flex: 1 }}>
                  <label style={label}>Precio (USD)</label>
                  <input type="number" min={0} style={inputStyle} value={f.precio} onChange={e => set('precio', e.target.value)} placeholder="850" />
                </div>
              </div>

              <div>
                <label style={label}>WhatsApp de contacto (opcional)</label>
                <input type="tel" style={inputStyle} value={f.telefono_wsp}
                       onChange={e => set('telefono_wsp', e.target.value)}
                       placeholder="Con código de país: 593999123456" />
                <div style={{ fontSize: '.72rem', color: C.muted, marginTop: 4 }}>
                  Habilita el botón “Continuar por WhatsApp” para los interesados. Se usa en todos tus inmuebles; déjalo vacío si ya lo configuraste.
                </div>
              </div>

              {!editando && (
                <>
                  <button type="button" onClick={usarUbicacion}
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, padding: '9px',
                             borderRadius: 12, cursor: 'pointer', fontSize: '.84rem',
                             background: f.latitude ? 'rgba(45,189,182,.16)' : 'rgba(255,255,255,.04)',
                             border: `1px solid ${f.latitude ? C.teal : C.line}`, color: f.latitude ? C.tealHi : C.text }}>
                    <MapPin size={15} /> {f.latitude ? 'Ubicación capturada ✓' : 'Estoy en el inmueble — usar mi ubicación'}
                  </button>
                  {geoMsg && <div style={{ fontSize: '.74rem', color: C.muted }}>{geoMsg}</div>}
                  <div style={{ fontSize: '.72rem', color: C.muted, marginTop: -4 }}>
                    Si no usas tu ubicación, geocodificamos la dirección automáticamente.
                  </div>
                </>
              )}
              {editando && (
                <div style={{ fontSize: '.72rem', color: C.muted, marginTop: -4 }}>
                  Si cambias la dirección, recalcularemos la capa base (caminabilidad, conectividad) automáticamente.
                </div>
              )}

              {error && <div style={{ color: C.coral, fontSize: '.82rem' }}>⚠️ {error}</div>}

              <button type="submit" disabled={loading}
                style={{ marginTop: 4, padding: '12px', borderRadius: 12, border: 'none',
                         cursor: loading ? 'default' : 'pointer', fontWeight: 800, fontSize: '.92rem',
                         background: `linear-gradient(90deg, ${C.teal}, ${C.tealHi})`, color: '#0E0D13', opacity: loading ? .7 : 1 }}>
                {loading ? (editando ? 'Guardando…' : 'Publicando…') : (editando ? 'Guardar cambios' : 'Publicar y generar mi QR')}
              </button>
              {!editando && (
                <div style={{ fontSize: '.72rem', color: C.muted, textAlign: 'center' }}>
                  Pasará por una revisión de calidad antes de difundirse.
                </div>
              )}
            </form>
          </>
        )}
      </div>
    </div>
  )
}
