import { useState, useEffect, useCallback } from 'react'
import axios from 'axios'
import { X, Plus, QrCode, Copy, Check, Share2, MapPin, ClipboardList, ListChecks, Pencil, RefreshCw, Store, Image as ImageIcon, TrainFront, AlertTriangle } from 'lucide-react'
import { API_BASE, apiHeaders } from './api'
import PublishAsset from './PublishAsset'
import FichaTecnica from './FichaTecnica'
import Caracteristicas from './Caracteristicas'
import ActualizarEntorno from './ActualizarEntorno'

const C = {
  bg: 'var(--bg)', panel: 'var(--surface-1)', teal: 'var(--teal)', tealHi: 'var(--teal-bright)',
  coral: 'var(--coral)', text: 'var(--text)', muted: 'var(--text-mid)', line: 'var(--border)',
}

// Caché en memoria de la última lista → aperturas repetidas abren al instante.
let _cacheMine = null

export default function MisPublicaciones({ onClose }) {
  const [items, setItems] = useState(_cacheMine)   // si hay caché → sin "Cargando…"
  const [error, setError] = useState(null)
  const [crear, setCrear] = useState(false)
  const [editar, setEditar] = useState(null)
  const [copied, setCopied] = useState(null)
  const [qrId, setQrId] = useState(null)
  const [fichaAsset, setFichaAsset] = useState(null)
  const [caracAsset, setCaracAsset] = useState(null)
  const [entornoAsset, setEntornoAsset] = useState(null)
  const [recomputando, setRecomputando] = useState(null)
  const [descargandoBanner, setDescargandoBanner] = useState(null)

  // Feedback en vivo (2026-07-02): abrir el banner en pestaña nueva (window.open) dejaba
  // al usuario sin saber dónde imprimir/descargar — el navegador no siempre muestra su
  // propia barra de imagen con el ícono de descarga. Se descarga el PNG directo (blob +
  // <a download>) con un nombre útil, en vez de depender de "clic derecho > Guardar como".
  async function descargarBanner(it) {
    setDescargandoBanner(it.id)
    try {
      const { data } = await axios.get(`${API_BASE}/api/v1/assets/${it.id}/letrero.png`, {
        headers: apiHeaders(), responseType: 'blob',
      })
      const slug = (it.direccion || 'inmueble').toLowerCase()
        // sin tildes/diacriticos: normalize('NFD') separa la letra base de su marca
        // combinante (rango Unicode 0300-036F), que este regex elimina. \uXXXX (sin
        // llaves) es la sintaxis JS correcta para code points de 4 hex digitos — \x{...}
        // es PCRE/Perl, NO JavaScript (invalido, aunque el build no lo detecto).
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
      const url = URL.createObjectURL(data)
      const a = document.createElement('a')
      a.href = url
      a.download = `letrero-${slug || it.id}.png`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch {
      // Si la descarga falla (red, bloqueo del navegador), al menos abrimos la imagen
      // para que el usuario la guarde manualmente — nunca dejar el botón sin hacer nada.
      window.open(`${API_BASE}/api/v1/assets/${it.id}/letrero.png`, '_blank')
    } finally {
      setDescargandoBanner(null)
    }
  }

  async function actualizarZona(it) {
    setRecomputando(it.id)
    try {
      await axios.post(`${API_BASE}/api/v1/assets/${it.id}/recompute`, {}, { headers: apiHeaders() })
      _cacheMine = null
      await load()
    } catch { /* ignore */ } finally { setRecomputando(null) }
  }

  const load = useCallback(async () => {
    setError(null)
    try {
      const { data } = await axios.get(`${API_BASE}/api/v1/assets/mine`, { headers: apiHeaders() })
      _cacheMine = data.publicaciones || []
      setItems(_cacheMine)
    } catch (e) {
      if (!_cacheMine) {   // si ya hay datos cacheados, no los borres por un fallo de red
        setError(e?.response?.data?.detail || 'No se pudieron cargar tus publicaciones.')
        setItems([])
      }
    }
  }, [])

  useEffect(() => { load() }, [load])   // refresca siempre en segundo plano

  async function copiar(link, id) {
    try { await navigator.clipboard.writeText(link); setCopied(id); setTimeout(() => setCopied(null), 1600) } catch { /* ignore */ }
  }
  async function compartir(it) {
    const url = it.deep_link
    // Solo en móvil/táctil usamos la hoja nativa; en escritorio copiamos el enlace
    // (evita la bandeja de Windows, que tapa todo y es tosca).
    const esTactil = window.matchMedia?.('(pointer: coarse)').matches
    if (esTactil && navigator.share) {
      try { await navigator.share({ title: it.direccion, url }) } catch { /* cancelado */ }
    } else {
      copiar(url, it.id)
    }
  }

  return (
    <div onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}
      style={{ position: 'fixed', inset: 0, zIndex: 1000, display: 'flex', alignItems: 'center',
               justifyContent: 'center', padding: 16, background: 'rgba(0,0,0,.5)', backdropFilter: 'blur(6px)' }}>
      <div onClick={(e) => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 560, maxHeight: '92vh', overflowY: 'auto', position: 'relative',
                 background: C.panel,
                 border: `1px solid ${C.line}`, borderRadius: 22, padding: '24px 22px', color: C.text,
                 boxShadow: '0 24px 60px rgba(0,0,0,.55)' }}>
        <button onClick={onClose} aria-label="Cerrar"
          style={{ position: 'absolute', top: 14, right: 14, background: 'none', border: 'none', color: C.muted, cursor: 'pointer' }}>
          <X size={18} />
        </button>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 16, paddingRight: 24 }}>
          <h2 style={{ margin: 0, fontSize: '1.15rem' }}>Mis publicaciones</h2>
          <button onClick={() => setCrear(true)}
            style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '8px 14px', borderRadius: 10,
                     border: 'none', cursor: 'pointer', fontWeight: 800, fontSize: '.84rem',
                     background: `linear-gradient(90deg, ${C.teal}, ${C.tealHi})`, color: '#0E0D13' }}>
            <Plus size={16} /> Nueva publicación
          </button>
        </div>

        {error && <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: C.coral, fontSize: '.85rem', marginBottom: 10 }}><AlertTriangle size={14} /> {error}</div>}
        {items === null && <div style={{ color: C.muted, padding: '30px 0', textAlign: 'center' }}>Cargando…</div>}

        {items !== null && items.length === 0 && !error && (
          <div style={{ textAlign: 'center', padding: '30px 12px', color: C.muted }}>
            <MapPin size={28} color={C.teal} style={{ marginBottom: 8 }} />
            <div style={{ fontSize: '.9rem', marginBottom: 4, color: C.text }}>Aún no has publicado inmuebles.</div>
            <div style={{ fontSize: '.8rem' }}>Toca <strong style={{ color: C.tealHi }}>Nueva publicación</strong> para crear el primero.</div>
          </div>
        )}

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {items?.map((it) => (
            <div key={it.id}
              style={{ border: `1px solid ${C.line}`, borderRadius: 14, padding: '13px 14px',
                       background: 'var(--surface-2)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10 }}>
                {it.portada && (
                  <img src={it.portada} alt="" width={54} height={54}
                    style={{ objectFit: 'cover', borderRadius: 10, border: `1px solid ${C.line}`, flexShrink: 0 }} />
                )}
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontWeight: 700, fontSize: '.92rem', marginBottom: 2 }}>{it.direccion}</div>
                  <div style={{ fontSize: '.76rem', color: C.muted }}>
                    {it.tipo_activo} · Piso {it.piso_altura}
                    {it.operacion ? ` · ${it.operacion?.toLowerCase()}` : ''}
                    {it.precio ? ` · $${it.precio.toLocaleString('es-EC')}` : ''}
                  </div>
                </div>
                {it.walk_score != null && (
                  <div style={{ flexShrink: 0, textAlign: 'center', background: 'rgba(45,189,182,.12)',
                                border: `1px solid ${C.line}`, borderRadius: 10, padding: '4px 9px' }}>
                    <div style={{ fontWeight: 800, color: C.tealHi, fontSize: '1rem', lineHeight: 1 }}>{it.walk_score}</div>
                    <div style={{ fontSize: '.6rem', color: C.muted }}>camin.</div>
                  </div>
                )}
              </div>

              {it.conectividad && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '.74rem', color: C.muted, marginTop: 8 }}><TrainFront size={14} /> {it.conectividad}</div>
              )}

              <div style={{ display: 'flex', gap: 7, marginTop: 11, flexWrap: 'wrap' }}>
                <Btn onClick={() => setEditar(it)}><Pencil size={14} /> Editar</Btn>
                <Btn onClick={() => copiar(it.deep_link, it.id)}>
                  {copied === it.id ? <Check size={14} /> : <Copy size={14} />} {copied === it.id ? 'Copiado' : 'Copiar enlace'}
                </Btn>
                <Btn onClick={() => compartir(it)}><Share2 size={14} /> Compartir</Btn>
                <Btn onClick={() => setQrId(qrId === it.id ? null : it.id)}><QrCode size={14} /> QR</Btn>
                <Btn onClick={() => descargarBanner(it)}>
                  <ImageIcon size={14} style={descargandoBanner === it.id ? { animation: 'spin 1s linear infinite' } : undefined} />
                  {descargandoBanner === it.id ? 'Descargando…' : 'Banner'}
                </Btn>
                <Btn onClick={() => setCaracAsset(it)}><ListChecks size={14} /> Características</Btn>
                <Btn onClick={() => setFichaAsset(it)}><ClipboardList size={14} /> Ficha técnica</Btn>
                <Btn onClick={() => setEntornoAsset(it)}><Store size={14} /> Entorno</Btn>
                <Btn onClick={() => actualizarZona(it)}>
                  <RefreshCw size={14} style={recomputando === it.id ? { animation: 'spin 1s linear infinite' } : undefined} />
                  {recomputando === it.id ? 'Actualizando…' : 'Actualizar zona'}
                </Btn>
              </div>

              {qrId === it.id && (
                <div style={{ marginTop: 12, textAlign: 'center' }}>
                  <div style={{ background: '#fff', borderRadius: 14, padding: 10, display: 'inline-block' }}>
                    <img src={`${API_BASE}/api/v1/assets/${it.id}/qr.svg`} alt="QR" width={160} height={160} style={{ display: 'block' }} />
                  </div>
                  <div style={{ fontSize: '.7rem', color: C.muted, marginTop: 6 }}>
                    Imprime y pégalo en el letrero — o usa <strong style={{ color: C.tealHi }}>Banner</strong> para
                    un letrero con foto y datos listo para imprimir.
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {crear && <PublishAsset onClose={() => { setCrear(false); load() }} />}
      {editar && <PublishAsset existing={editar} onClose={() => { setEditar(null); load() }} />}
      {fichaAsset && <FichaTecnica activo={fichaAsset} onClose={() => { setFichaAsset(null); load() }} />}
      {caracAsset && <Caracteristicas activo={caracAsset} onClose={() => { setCaracAsset(null); load() }} />}
      {entornoAsset && <ActualizarEntorno activo={entornoAsset} onClose={() => { setEntornoAsset(null); load() }} />}
    </div>
  )
}

function Btn({ onClick, children }) {
  return (
    <button onClick={onClick}
      style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '6px 11px', borderRadius: 8,
               background: 'var(--surface-2)', border: '1px solid var(--border)',
               color: 'var(--teal-bright)', cursor: 'pointer', fontSize: '.76rem', fontWeight: 600 }}>
      {children}
    </button>
  )
}
