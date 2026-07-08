import { useRef } from 'react'
import { Camera, Image as ImageIcon, Paperclip } from 'lucide-react'
import sphereLogo from './assets/sphere.svg'

// ── Hoja "Adjuntar" (el "+" del dock) ───────────────────────────────────────
// Réplica del panel de ASI:One (Cámara / Fotos / Subir archivo), pero anclada al
// motor que YA existe: la foto que se elige alimenta /api/v1/match (embedding
// Voyage multimodal → pgvector) → "busca en el inventario algo parecido".
// Presentational: no llama al backend. Devuelve el File al padre vía onPickPhoto.

export default function AttachSheet({ onClose, onPickPhoto }) {
  const camRef = useRef(null)
  const galRef = useRef(null)

  const pick = (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''            // permite volver a elegir el mismo archivo
    if (!file) return
    if (!file.type.startsWith('image/')) return
    onClose()
    onPickPhoto(file)
  }

  const card = {
    background: 'var(--surface-3)', border: '1px solid var(--border)', borderRadius: 16,
    height: 122, display: 'flex', flexDirection: 'column', alignItems: 'center',
    justifyContent: 'center', gap: 13, cursor: 'pointer', color: 'var(--text)',
  }

  return (
    <>
      {/* scrim */}
      <div
        onClick={onClose}
        style={{ position: 'fixed', inset: 0, background: 'rgba(5,5,7,.62)', zIndex: 60 }}
      />

      {/* hidden inputs */}
      <input ref={camRef} type="file" accept="image/*" capture="environment"
             onChange={pick} style={{ display: 'none' }} />
      <input ref={galRef} type="file" accept="image/*"
             onChange={pick} style={{ display: 'none' }} />

      {/* sheet */}
      <div style={{
        position: 'fixed', left: 0, right: 0, bottom: 0, zIndex: 61,
        maxWidth: 560, margin: '0 auto',
        background: 'var(--surface-1)', borderTop: '1px solid var(--border)',
        borderRadius: '24px 24px 0 0', padding: '22px 20px 30px',
        boxShadow: '0 -22px 50px rgba(0,0,0,.55)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <img src={sphereLogo} alt="" width={20} height={20} style={{ display: 'block' }} />
            <span style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text)' }}>Contexto</span>
          </div>
          <span style={{ fontSize: '.72rem', fontWeight: 600, letterSpacing: '.12em', color: 'var(--text-dim)' }}>
            ADJUNTAR
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 8 }}>
          <button onClick={() => camRef.current?.click()} style={{ ...card, fontFamily: 'inherit' }}>
            <Camera size={30} strokeWidth={1.7} />
            <span style={{ fontSize: '1rem', fontWeight: 600 }}>Cámara</span>
          </button>
          <button onClick={() => galRef.current?.click()} style={{ ...card, fontFamily: 'inherit' }}>
            <ImageIcon size={30} strokeWidth={1.7} />
            <span style={{ fontSize: '1rem', fontWeight: 600 }}>Fotos</span>
          </button>
        </div>

        <button
          onClick={() => galRef.current?.click()}
          style={{
            display: 'flex', alignItems: 'center', gap: 14, width: '100%',
            background: 'none', border: 'none', cursor: 'pointer', padding: '16px 4px 0',
            textAlign: 'left', fontFamily: 'inherit',
          }}
        >
          <Paperclip size={24} strokeWidth={1.8} style={{ color: 'var(--text-mid)', flexShrink: 0 }} />
          <span>
            <span style={{ display: 'block', fontSize: '1.02rem', fontWeight: 700, color: 'var(--text)' }}>
              Subir archivo
            </span>
            <span style={{ display: 'block', fontSize: '.86rem', color: 'var(--text-dim)', marginTop: 3 }}>
              Busco en tu inventario algo parecido
            </span>
          </span>
        </button>
      </div>
    </>
  )
}
