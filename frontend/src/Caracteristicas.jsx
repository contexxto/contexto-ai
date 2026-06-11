import { useState, useEffect } from 'react'
import axios from 'axios'
import { X, Check, Upload, Loader, Trash2 } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'
import { supabase } from './supabaseClient'

const C = {
  bg: '#16151E', panel: '#1E1D28', teal: '#2DBDB6', tealHi: '#5EEAD4',
  coral: '#E0685A', text: '#EDEBF2', muted: '#9C99AC', line: 'rgba(45,189,182,.22)',
}
const NUMS = [
  ['num_dormitorios', 'Dormitorios'], ['num_banos', 'Baños'],
  ['num_medio_banos', 'Medios baños'], ['num_parqueaderos', 'Parqueaderos'],
  ['num_bodegas', 'Bodegas'],
]
const CHECKS = [
  ['amoblado', 'Amoblado'], ['sala', 'Sala'], ['comedor', 'Comedor'],
  ['estudio', 'Estudio'], ['cuarto_servicio', 'Cuarto de servicio'],
  ['balcon', 'Balcón'], ['terraza', 'Terraza'], ['acepta_mascotas', '🐾 Acepta mascotas'],
]
const AMENIDADES = ['Piscina', 'Sauna', 'Turco', 'Gimnasio', 'Seguridad 24/7', 'CCTV',
  'Ascensor', 'Áreas comunales', 'Generador', 'BBQ / Social']
const INCLUYE = ['Alícuota', 'Agua', 'Luz', 'Internet', 'Gas']

export default function Caracteristicas({ activo, onClose }) {
  const [f, setF] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)
  const [editando, setEditando] = useState(false)
  const [existe, setExiste] = useState(false)
  const set = (k, v) => setF(prev => ({ ...prev, [k]: v }))
  const toggleArr = (k, val) => setF(prev => {
    const cur = prev[k] || []
    return { ...prev, [k]: cur.includes(val) ? cur.filter(x => x !== val) : [...cur, val] }
  })
  const [uploading, setUploading] = useState(false)
  async function subirFotos(files) {
    if (!supabase) { setError('Subida no disponible (Storage no configurado).'); return }
    setError(null); setUploading(true)
    try {
      const nuevas = []
      for (const file of files) {
        const path = `inmuebles/${activo.id}/${Date.now()}-${Math.random().toString(36).slice(2, 7)}-${file.name.replace(/[^\w.\-]/g, '_')}`
        const { error: upErr } = await supabase.storage.from('evidencias').upload(path, file, { upsert: false })
        if (upErr) throw upErr
        const { data } = supabase.storage.from('evidencias').getPublicUrl(path)
        nuevas.push(data.publicUrl)
      }
      set('fotos', [...(f.fotos || []), ...nuevas])
    } catch {
      setError('No se pudieron subir las fotos. ¿Existe el bucket "evidencias" (público)?')
    } finally { setUploading(false) }
  }

  function aplicar(car, precio) {
    car = car || {}
    const tiene = Object.keys(car).length > 0
    setF({ ...car, ...(precio != null ? { precio } : {}) })
    setExiste(tiene)
    setEditando(!tiene)   // si no hay datos aún → arranca en edición
  }
  async function cargar() {
    const { data } = await axios.get(`${API_BASE}/api/v1/assets/${activo.id}/caracteristicas`, { headers: apiHeaders() })
    aplicar(data.caracteristicas, data.precio)
  }
  useEffect(() => {
    // Si "Mis publicaciones" ya trajo los datos → abre instantáneo (sin pedir nada).
    if (activo.caracteristicas !== undefined) { aplicar(activo.caracteristicas, activo.precio); setLoading(false) }
    else { (async () => { try { await cargar() } catch { setEditando(true) } finally { setLoading(false) } })() }
  }, [activo.id])

  async function guardar(e) {
    e.preventDefault(); setError(null); setSaving(true); setSaved(false)
    const num = (v) => (v === '' || v == null ? null : Number(v))
    try {
      await axios.post(`${API_BASE}/api/v1/assets/${activo.id}/caracteristicas`, {
        area_total_m2: num(f.area_total_m2), area_construida_m2: num(f.area_construida_m2),
        num_dormitorios: num(f.num_dormitorios), num_banos: num(f.num_banos),
        num_medio_banos: num(f.num_medio_banos), num_parqueaderos: num(f.num_parqueaderos),
        num_bodegas: num(f.num_bodegas), alicuota: num(f.alicuota), precio: num(f.precio),
        amoblado: !!f.amoblado, sala: !!f.sala, comedor: !!f.comedor, estudio: !!f.estudio,
        cuarto_servicio: !!f.cuarto_servicio, balcon: !!f.balcon, terraza: !!f.terraza,
        acepta_mascotas: !!f.acepta_mascotas, precio_negociable: !!f.precio_negociable,
        amenidades_edificio: f.amenidades_edificio || [], incluye: f.incluye || [],
        ideal_para: f.ideal_para || null, notas: f.notas || null,
        fotos: f.fotos || [],
      }, { headers: { 'Content-Type': 'application/json', ...apiHeaders() } })
      setSaved(true)
      try { await cargar() } catch { /* ignore */ }
      setTimeout(() => setSaved(false), 1500)
    } catch (err) {
      setError(err?.response?.data?.detail || 'No se pudieron guardar las características.')
    } finally { setSaving(false) }
  }

  const inp = { width: '100%', padding: '10px 12px', borderRadius: 10, marginTop: 5, boxSizing: 'border-box',
    background: 'rgba(255,255,255,.04)', border: `1px solid ${C.line}`, color: C.text, fontSize: '.9rem', outline: 'none' }
  const lbl = { fontSize: '.76rem', color: C.muted, fontWeight: 600 }
  const sec = { fontSize: '.72rem', color: C.tealHi, letterSpacing: '.5px', fontWeight: 700, margin: '18px 0 6px' }

  return (
    <div onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 1100, display: 'flex', alignItems: 'center',
               justifyContent: 'center', padding: 16, background: 'rgba(10,9,16,.78)', backdropFilter: 'blur(6px)' }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 540, maxHeight: '92vh', overflowY: 'auto', position: 'relative',
                 background: `radial-gradient(120% 90% at 30% 0%, ${C.panel} 0%, ${C.bg} 70%)`,
                 border: `1px solid ${C.line}`, borderRadius: 22, padding: '24px 22px', color: C.text,
                 boxShadow: '0 24px 60px rgba(0,0,0,.6)' }}>
        <button onClick={onClose} aria-label="Cerrar"
          style={{ position: 'absolute', top: 14, right: 14, background: 'none', border: 'none', color: C.muted, cursor: 'pointer' }}>
          <X size={18} />
        </button>
        <h2 style={{ margin: '0 0 2px', fontSize: '1.12rem' }}>Características del inmueble</h2>
        <div style={{ fontSize: '.8rem', color: C.muted, marginBottom: 4 }}>{activo.direccion}</div>

        {loading ? (
          <div style={{ color: C.muted, padding: '30px 0', textAlign: 'center' }}>Cargando…</div>
        ) : (
          <form onSubmit={guardar}>
            <fieldset disabled={!editando} style={{ border: 0, padding: 0, margin: 0, minWidth: 0,
              opacity: editando ? 1 : .92 }}>
            <div style={sec}>FOTOS DEL INMUEBLE</div>
            <label style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8, padding: '11px',
                            borderRadius: 12, cursor: uploading ? 'default' : 'pointer', fontSize: '.85rem',
                            background: 'rgba(45,189,182,.08)', border: `1px dashed ${C.teal}`, color: C.tealHi }}>
              {uploading ? <Loader size={16} /> : <Upload size={16} />}
              {uploading ? 'Subiendo…' : 'Subir fotos (sala, cocina, dormitorios, vista…)'}
              <input type="file" accept="image/*" multiple style={{ display: 'none' }} disabled={uploading}
                onChange={e => e.target.files?.length && subirFotos(Array.from(e.target.files))} />
            </label>
            {(f.fotos || []).length > 0 && (
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
                {f.fotos.map((url, i) => (
                  <div key={url} style={{ position: 'relative' }}>
                    {i === 0 && <span style={{ position: 'absolute', top: 3, left: 3, background: C.teal, color: '#0E0D13',
                                  fontSize: '.55rem', fontWeight: 800, padding: '1px 5px', borderRadius: 5 }}>PORTADA</span>}
                    <img src={url} alt={`foto ${i + 1}`} width={78} height={78}
                      style={{ objectFit: 'cover', borderRadius: 8, border: `1px solid ${C.line}` }} />
                    <button type="button" onClick={() => set('fotos', f.fotos.filter(u => u !== url))}
                      style={{ position: 'absolute', top: -6, right: -6, background: C.coral, border: 'none',
                               borderRadius: '50%', width: 20, height: 20, cursor: 'pointer', color: '#fff', display: 'flex',
                               alignItems: 'center', justifyContent: 'center' }}>
                      <Trash2 size={11} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <div style={sec}>DISTRIBUCIÓN</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10 }}>
              {NUMS.map(([k, label]) => (
                <div key={k}>
                  <label style={lbl}>{label}</label>
                  <input type="number" min={0} style={inp} value={f[k] ?? ''} onChange={e => set(k, e.target.value)} />
                </div>
              ))}
            </div>
            <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
              <div style={{ flex: 1 }}>
                <label style={lbl}>Área total (m²)</label>
                <input type="number" min={0} style={inp} value={f.area_total_m2 ?? ''} onChange={e => set('area_total_m2', e.target.value)} placeholder="120" />
              </div>
              <div style={{ flex: 1 }}>
                <label style={lbl}>Área construida (m²)</label>
                <input type="number" min={0} style={inp} value={f.area_construida_m2 ?? ''} onChange={e => set('area_construida_m2', e.target.value)} placeholder="95" />
              </div>
            </div>

            <div style={sec}>AMBIENTES</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {CHECKS.map(([k, label]) => (
                <button type="button" key={k} onClick={() => set(k, !f[k])}
                  style={{ padding: '7px 13px', borderRadius: 999, cursor: 'pointer', fontSize: '.8rem', fontWeight: 600,
                           background: f[k] ? 'rgba(45,189,182,.18)' : 'rgba(255,255,255,.04)',
                           border: `1px solid ${f[k] ? C.teal : C.line}`, color: f[k] ? C.tealHi : C.muted }}>
                  {f[k] ? '✓ ' : ''}{label}
                </button>
              ))}
            </div>

            <div style={sec}>AMENIDADES DEL EDIFICIO</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {AMENIDADES.map(a => {
                const on = (f.amenidades_edificio || []).includes(a)
                return (
                  <button type="button" key={a} onClick={() => toggleArr('amenidades_edificio', a)}
                    style={{ padding: '7px 13px', borderRadius: 999, cursor: 'pointer', fontSize: '.8rem', fontWeight: 600,
                             background: on ? 'rgba(45,189,182,.18)' : 'rgba(255,255,255,.04)',
                             border: `1px solid ${on ? C.teal : C.line}`, color: on ? C.tealHi : C.muted }}>
                    {on ? '✓ ' : ''}{a}
                  </button>
                )
              })}
            </div>

            <div style={sec}>¿QUÉ INCLUYE?</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
              {INCLUYE.map(a => {
                const on = (f.incluye || []).includes(a)
                return (
                  <button type="button" key={a} onClick={() => toggleArr('incluye', a)}
                    style={{ padding: '7px 13px', borderRadius: 999, cursor: 'pointer', fontSize: '.8rem', fontWeight: 600,
                             background: on ? 'rgba(45,189,182,.18)' : 'rgba(255,255,255,.04)',
                             border: `1px solid ${on ? C.teal : C.line}`, color: on ? C.tealHi : C.muted }}>
                    {on ? '✓ ' : ''}{a}
                  </button>
                )
              })}
            </div>

            <div style={{ marginTop: 14 }}>
              <label style={lbl}>Ideal para</label>
              <input style={inp} value={f.ideal_para ?? ''} onChange={e => set('ideal_para', e.target.value)}
                placeholder="Ejecutivos, diplomáticos o familia amplia" />
            </div>

            <div style={sec}>PRECIO Y GASTOS</div>
            <div style={{ display: 'flex', gap: 10, alignItems: 'flex-end' }}>
              <div style={{ flex: 1 }}>
                <label style={lbl}>Precio (USD)</label>
                <input type="number" min={0} style={inp} value={f.precio ?? ''} onChange={e => set('precio', e.target.value)} placeholder="850" />
              </div>
              <div style={{ flex: 1 }}>
                <label style={lbl}>Alícuota (USD/mes)</label>
                <input type="number" min={0} style={inp} value={f.alicuota ?? ''} onChange={e => set('alicuota', e.target.value)} placeholder="60" />
              </div>
            </div>
            <button type="button" onClick={() => set('precio_negociable', !f.precio_negociable)}
              style={{ marginTop: 10, padding: '7px 13px', borderRadius: 999, cursor: 'pointer', fontSize: '.8rem', fontWeight: 600,
                       background: f.precio_negociable ? 'rgba(45,189,182,.18)' : 'rgba(255,255,255,.04)',
                       border: `1px solid ${f.precio_negociable ? C.teal : C.line}`, color: f.precio_negociable ? C.tealHi : C.muted }}>
              {f.precio_negociable ? '✓ ' : ''}Precio negociable
            </button>

            <div style={{ marginTop: 14 }}>
              <label style={lbl}>Notas adicionales</label>
              <input style={inp} value={f.notas ?? ''} onChange={e => set('notas', e.target.value)} placeholder="Vista despejada, edificio con ascensor…" />
            </div>
            </fieldset>

            {error && <div style={{ color: C.coral, fontSize: '.82rem', marginTop: 14 }}>⚠️ {error}</div>}

            {editando ? (
              <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
                {existe && (
                  <button type="button" onClick={async () => { setError(null); await cargar() }}
                    style={{ padding: '13px 18px', borderRadius: 12, border: `1px solid ${C.line}`, cursor: 'pointer',
                             background: 'transparent', color: C.muted, fontWeight: 700, fontSize: '.9rem' }}>
                    Cancelar
                  </button>
                )}
                <button type="submit" disabled={saving || uploading}
                  style={{ flex: 1, padding: '13px', borderRadius: 12, border: 'none',
                           cursor: (saving || uploading) ? 'default' : 'pointer', fontWeight: 800, fontSize: '.92rem',
                           background: saved ? '#2E9E6B' : `linear-gradient(90deg, ${C.teal}, ${C.tealHi})`,
                           color: '#0E0D13', opacity: saving ? .7 : 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                  {saved ? <><Check size={18} /> Guardadas</> : saving ? 'Guardando…' : (existe ? 'Actualizar' : 'Grabar')}
                </button>
              </div>
            ) : (
              <button type="button" onClick={() => setEditando(true)}
                style={{ width: '100%', marginTop: 20, padding: '13px', borderRadius: 12, cursor: 'pointer',
                         border: `1px solid ${C.teal}`, background: 'rgba(45,189,182,.10)', color: C.tealHi,
                         fontWeight: 800, fontSize: '.92rem' }}>
                ✏️ Editar
              </button>
            )}
          </form>
        )}
      </div>
    </div>
  )
}
