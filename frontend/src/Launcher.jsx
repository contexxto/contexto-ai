import { useState } from 'react'
import { ArrowDownLeft, RefreshCw } from 'lucide-react'
import { INTENCIONES, HOME } from './intencionesEntrada'
import LogoVertical from './LogoContexto'

// ── Launcher (pantalla inicial) ──────────────────────────────────────────────
// Presentational: sin estado de negocio. Recibe callbacks y dispara las MISMAS
// acciones que ya existían en App (sendMessage / analizarMiUbicacion / mapa).
//
// Dirección (2026-09-20): la referencia de esta pantalla es el inicio de Comet, NO
// ASI:One. Una sola jerarquía: la marca con aire, una leyenda, cuatro entradas a
// ancho completo que dicen qué va a pasar, y el campo de escribir (que vive en App).
// Lo que salió de aquí a propósito: el título, los ocho chips, el botón «Analiza dónde
// estás» (la zona actual es la segunda entrada) y el enlace de corredores (la home es
// del habitante; el corredor entra por el menú lateral).
//
// El aire se reparte con tres espaciadores flexibles que se encogen a cero antes que
// nada: el centrado nunca provoca scroll. Antes había 150 px fijos arriba y el bloque
// medía 642 px contra un hueco de ~440 en un teléfono de 360×720.
//
// `aviso` es el hueco para el mensaje de error de App (p. ej. permiso de ubicación
// negado): con el bloque a pantalla completa, pintarlo después del Launcher lo dejaba
// bajo el pliegue y la entrada de la zona fallaba en silencio. Va ARRIBA del todo.
// OJO al comentar: tests/test_intenciones_entrada.py lee este archivo como TEXTO, comentarios
// incluidos, y falla si aparece la palabra intent seguida de dos puntos.

// Los textos viven en ./intencionesEntrada (fuente única): cada intención rinde también
// como página indexable y como guion del canal, y repetirlos aquí los desincronizaba.
// HOME elige cuáles (cuatro ids, en orden): aquí solo se les pone forma.
const ENTRADAS = HOME.map((id) => INTENCIONES.find((i) => i.id === id)).filter(Boolean)

function Entrada({ label, busy, onClick }) {
  const [hover, setHover] = useState(false)
  return (
    <button
      onClick={onClick}
      disabled={busy}
      aria-busy={busy || undefined}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14,
        width: '100%', textAlign: 'left', padding: '10px 16px', borderRadius: 14,
        cursor: busy ? 'default' : 'pointer',
        background: hover && !busy ? 'var(--home-row-hover)' : 'var(--home-row-bg)',
        border: '1px solid var(--home-row-border)', color: 'var(--text)',
        fontSize: '.92rem', lineHeight: 1.25, fontWeight: 400, fontFamily: 'inherit',
        transition: 'background var(--dur-fast) var(--ease)',
      }}
    >
      <span>{busy ? 'Ubicándote…' : label}</span>
      {busy
        ? <RefreshCw size={18} style={{ color: 'var(--text-dim)', flexShrink: 0, animation: 'spin 1s linear infinite' }} />
        : <ArrowDownLeft size={18} style={{ color: 'var(--text-dim)', flexShrink: 0 }} />}
    </button>
  )
}

export default function Launcher({ onSend, onAnalyzeLocation, onOpenMap, onBroker, geoLoading, isMobile, aviso }) {
  const fire = (c) => {
    if (c.accion === 'geo') onAnalyzeLocation()
    else if (c.accion === 'map') onOpenMap()
    else if (c.accion === 'broker') onBroker()
    else onSend(c.intent)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'stretch', minHeight: '100%', textAlign: 'center' }}>
      {/* El fondo de aura NO vive aquí: lo pinta App detrás de toda el área principal (header y
          campo de escribir incluidos), con la misma condición que monta esta pantalla. */}
      {/* Lo primero de la pantalla: con el teclado CERRADO (que es como se toca una entrada) queda
          a la vista sin scroll, también con el aviso puesto (visto en el teléfono). Más abajo
          volvía a quedar bajo el pliegue.
          Límite conocido: Chrome de Android no encoge la página al abrir el teclado, la SUBE para
          mostrar el campo, así que con el teclado abierto se ve el FINAL del bloque (leyenda,
          entradas y campo) y este aviso queda arriba, fuera de vista, hasta cerrarlo. */}
      {aviso && <div style={{ margin: '0 auto', flexShrink: 0, width: '100%', maxWidth: 560, textAlign: 'left' }}>{aviso}</div>}

      <div style={{ flex: '1 1 0' }} />

      {/* El único encabezado de la pantalla: su nombre accesible sale del logotipo («Contexto»).
          margin 0: el margen por defecto de un h1 rompería el centrado sin scroll. */}
      <h1 style={{ margin: 0, display: 'flex', justifyContent: 'center', flexShrink: 0 }}>
        <LogoVertical size={isMobile ? 76 : 88} />
      </h1>

      <div style={{ flex: '.9 1 0' }} />

      {/* 12 px fijos arriba: los espaciadores ceden a cero, y con el aviso puesto más un borrador de
          cuatro líneas la leyenda quedaba pegada al logotipo (visto en el teléfono). */}
      <div style={{ color: 'var(--text-dim)', fontSize: '.95rem', margin: '12px 0 26px', flexShrink: 0 }}>
        Cada lugar tiene un aura.
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flexShrink: 0, width: '100%', maxWidth: 560, margin: '0 auto' }}>
        {ENTRADAS.map((c) => (
          <Entrada key={c.id} label={c.label} busy={c.accion === 'geo' && geoLoading} onClick={() => fire(c)} />
        ))}
      </div>

      <div style={{ flex: '.7 1 0' }} />
    </div>
  )
}
