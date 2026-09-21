// ── Logotipo de Contexto ─────────────────────────────────────────────────────
// GENERADO por docs/branding/logo/genera_logo.py + genera_componente.py: no editar los
// contornos a mano. El logotipo son contornos puros (sin fuente): caja alta geométrica de
// trazo 11/100, barras horizontales al 93 %, redondas al 104 % con rebase de 1.5, la E de
// tres barras con la central un 10 % más corta, y el blanco entre letras calculado sobre
// el perfil de cada pareja. El isotipo vive en una retícula de 13 módulos: lado 6, calle 1,
// radio 1.35, y el círculo un 4 % mayor que el lado (a igual medida se ve más pequeño);
// por eso rebasa la retícula en 0.12 y el viewBox lleva ese respiro: sin él, sale recortado.
//
// Este isotipo es el MAESTRO, y desde el 2026-09-21 es el único signo de Contexto: el favicon
// (public/favicon.svg) y el signo de la app (assets/isotipo.svg) son sus mismas formas. Dentro del
// lockup horizontal va desde 32 px: ahí la palabra llega a su mínimo legible de 96 px.
// El logotipo hereda el color del texto (currentColor): blanco en oscuro, tinta en claro.

const LETRAS = [
  { x: 0.0, d: 'M90.95 16.9 A51.5 51.5 0 1 0 90.95 83.1 L82.19 75.75 A40.06 40.06 0 1 1 82.19 24.25 Z' },
  { x: 129.57, d: 'M0 50 A51.5 51.5 0 1 1 103 50 A51.5 51.5 0 1 1 0 50 Z M11.44 50 A40.06 40.06 0 1 0 91.56 50 A40.06 40.06 0 1 0 11.44 50 Z' },
  { x: 277.44, d: 'M0 0 L13.57 0 L79 85.61 L79 0 L90 0 L90 100 L76.43 100 L11 14.39 L11 100 L0 100 Z' },
  { x: 409.12, d: 'M0 0 L83 0 L83 10.23 L47 10.23 L47 100 L36 100 L36 10.23 L0 10.23 Z' },
  { x: 527.98, d: 'M0 0 L76 0 L76 10.23 L0 10.23 Z M0 43.88 L68.4 43.88 L68.4 54.11 L0 54.11 Z M0 89.77 L76 89.77 L76 100 L0 100 Z' },
  { x: 640.11, d: 'M0 0 L13.88 0 L47.5 41.44 L81.12 0 L95 0 L54.44 50 L95 100 L81.12 100 L47.5 58.56 L13.88 100 L0 100 L40.56 50 Z' },
  { x: 769.97, d: 'M0 0 L83 0 L83 10.23 L47 10.23 L47 100 L36 100 L36 10.23 L0 10.23 Z' },
  { x: 890.45, d: 'M0 50 A51.5 51.5 0 1 1 103 50 A51.5 51.5 0 1 1 0 50 Z M11.44 50 A40.06 40.06 0 1 0 91.56 50 A40.06 40.06 0 1 0 11.44 50 Z' },
]

export function Isotipo({ size = 76, style }) {
  return (
    <svg width={size} height={size} viewBox="-0.12 -0.12 13.24 13.24" aria-hidden="true" style={{ display: 'block', ...style }}>
      <rect x="0" y="0" width="6" height="6" rx="1.35" fill="#5EEAD4" />
      <rect x="7" y="0" width="6" height="6" rx="1.35" fill="#3A3D44" />
      <rect x="0" y="7" width="6" height="6" rx="1.35" fill="#3A3D44" />
      <circle cx="10" cy="10" r="3.12" fill="#5EEAD4" />
    </svg>
  )
}

export function Logotipo({ width = 152, style }) {
  return (
    <svg width={width} viewBox="-1 -2.5 995.45 105" role="img" aria-label="Contexto" style={{ display: 'block', height: 'auto', ...style }}>
      <g fill="currentColor">
        {LETRAS.map((l, i) => <path key={i} transform={`translate(${l.x} 0)`} d={l.d} />)}
      </g>
    </svg>
  )
}

// Versión horizontal (para cabeceras): el MISMO lienzo que docs/branding/logo/contexto-horizontal.svg
// — caja alta de 4 módulos centrada en el isotipo y 4 de separación —. `alto` es el del isotipo, y
// el ancho sale de la proporción del lienzo. Por debajo de ALTO_MIN_HORIZONTAL la palabra baja de
// 96 px y deja de leerse.
export const ALTO_MIN_HORIZONTAL = 32

export function LogoHorizontal({ alto = ALTO_MIN_HORIZONTAL, style }) {
  return (
    <svg height={alto} width={alto * 4.297583} viewBox="-0.12 -0.12 56.9 13.24" role="img" aria-label="Contexto" style={{ display: 'block', ...style }}>
      <rect x="0" y="0" width="6" height="6" rx="1.35" fill="#5EEAD4" />
      <rect x="7" y="0" width="6" height="6" rx="1.35" fill="#3A3D44" />
      <rect x="0" y="7" width="6" height="6" rx="1.35" fill="#3A3D44" />
      <circle cx="10" cy="10" r="3.12" fill="#5EEAD4" />
      <g fill="currentColor" transform="translate(17 4.5) scale(0.04000)">
        {LETRAS.map((l, i) => <path key={i} transform={`translate(${l.x} 0)`} d={l.d} />)}
      </g>
    </svg>
  )
}

// Versión vertical (la principal): isotipo de 13 módulos, 2 de separación, y el logotipo al
// doble de ancho que el isotipo.
export default function LogoVertical({ size = 76, color = 'var(--text)' }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: (size * 2) / 13, color }}>
      <Isotipo size={size} />
      <Logotipo width={size * 2} />
    </div>
  )
}
