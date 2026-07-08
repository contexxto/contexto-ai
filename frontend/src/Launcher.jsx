import { useState } from 'react'
import { MapPin, Map, Home, Train, Wallet, Building2, Sparkles } from 'lucide-react'

// ── Launcher (pantalla inicial limpia, estilo ASI:One) ──────────────────────
// Presentational: sin estado de negocio. Recibe callbacks y dispara las MISMAS
// acciones que ya existían en App (sendMessage / analizarMiUbicacion / mapa /
// upgrade). Reemplaza el hero del estado vacío. Superficies planas, cero glow.

// Chips de intención → cada uno mapea a una acción real del app.
const CHIPS = [
  { icon: MapPin,    label: 'Analiza mi zona',     action: 'geo' },
  { icon: Map,       label: 'Explorar el mapa',    action: 'map' },
  { icon: Home,      label: 'Para mi familia',     action: 'send',
    intent: '🏡 Busco para mi familia: tranquilo, con colegios y parque cerca' },
  { icon: Train,     label: 'Cerca del Metro',     action: 'send',
    intent: '🚇 Quiero vivir cerca del Metro o de mi trabajo' },
  { icon: Wallet,    label: 'Mi presupuesto',      action: 'send',
    intent: '💰 Dime qué me conviene para mi presupuesto' },
  { icon: Building2, label: 'Soy corredor',        action: 'broker' },
  { icon: Sparkles,  label: 'El aura de un lugar', action: 'send',
    intent: '¿Qué es el aura de un lugar y cómo la lees en Contexto?' },
]

// Filas escalonadas 2-2-2-1 (como ASI:One).
const ROWS = [[0, 1], [2, 3], [4, 5], [6]]

function Chip({ icon: Icon, label, onClick }) {
  const [hover, setHover] = useState(false)
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 9, whiteSpace: 'nowrap',
        padding: '11px 16px', borderRadius: 10, cursor: 'pointer',
        background: hover ? 'var(--surface-3)' : 'var(--surface-2)',
        border: '1px solid var(--border)', color: 'var(--text)',
        fontSize: '.9rem', fontWeight: 500, fontFamily: 'inherit',
        transition: 'background .15s',
      }}
    >
      <Icon size={17} style={{ color: 'var(--text-mid)', flexShrink: 0 }} />
      {label}
    </button>
  )
}

export default function Launcher({ onSend, onAnalyzeLocation, onOpenMap, onBroker, geoLoading, isMobile }) {
  const fire = (c) => {
    if (c.action === 'geo') onAnalyzeLocation()
    else if (c.action === 'map') onOpenMap()
    else if (c.action === 'broker') onBroker()
    else onSend(c.intent)
  }

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', alignItems: 'center',
      paddingTop: isMobile ? 34 : 70, textAlign: 'center',
    }}>
      <h1 style={{
        fontFamily: 'var(--font-display)', fontWeight: 800,
        fontSize: isMobile ? '1.85rem' : '2.4rem', letterSpacing: '-.03em',
        color: 'var(--text)', lineHeight: 1.12, margin: '0 0 26px',
      }}>
        ¿Con qué te ayudo hoy?
      </h1>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 11, alignItems: 'center', maxWidth: 500 }}>
        {ROWS.map((row, ri) => (
          <div key={ri} style={{ display: 'flex', justifyContent: 'center', gap: 11, flexWrap: 'wrap' }}>
            {row.map((idx) => {
              const c = CHIPS[idx]
              return <Chip key={idx} icon={c.icon} label={c.label} onClick={() => fire(c)} />
            })}
          </div>
        ))}
      </div>

      <div style={{ color: 'var(--text-mid)', fontSize: '1rem', margin: '38px 0 20px' }}>
        Cada lugar tiene un aura.
      </div>

      <button
        onClick={onAnalyzeLocation}
        disabled={geoLoading}
        style={{
          display: 'inline-flex', alignItems: 'center', gap: 10,
          padding: '14px 26px', borderRadius: 12, border: 'none',
          cursor: geoLoading ? 'default' : 'pointer',
          background: 'var(--teal-bright)', color: '#06201C',
          fontWeight: 700, fontSize: '1rem', fontFamily: 'inherit',
        }}
      >
        <MapPin size={18} /> {geoLoading ? 'Ubicándote…' : 'Analiza dónde estás'}
      </button>

      <button
        onClick={onBroker}
        style={{
          marginTop: 26, background: 'none', border: 'none', cursor: 'pointer',
          color: 'var(--text-muted)', fontSize: '.82rem', fontFamily: 'inherit',
        }}
      >
        ¿Eres corredor o inmobiliaria?{' '}
        <span style={{ color: 'var(--teal-bright)', fontWeight: 700 }}>
          Que tu próximo lead llegue calificado →
        </span>
      </button>
    </div>
  )
}
