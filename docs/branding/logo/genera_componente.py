# -*- coding: utf-8 -*-
"""Escribe frontend/src/LogoContexto.jsx a partir de logo.json (junto a este script).
Los contornos no se copian a mano; frontend/src/homeLauncher.test.js vigila que sigan en sincronía."""
import json, sys
from pathlib import Path
B = Path(__file__).resolve().parent
d = json.loads((B / 'logo.json').read_text(encoding='utf-8'))
i = d['isotipo']
letras = ",\n".join(f"  {{ x: {l['x']}, d: '{l['d']}' }}" for l in d['letras'])
vb = d['vb_logotipo']
p = i['lado'] + i['gap']; c = p + i['lado'] / 2
src = f"""// ── Logotipo de Contexto ─────────────────────────────────────────────────────
// GENERADO por docs/branding/logo/genera_logo.py + genera_componente.py: no editar los
// contornos a mano. El logotipo son contornos puros (sin fuente): caja alta geométrica de
// trazo {d['S']:g}/100, barras horizontales al 93 %, redondas al 104 % con rebase de {d['OV']:g}, la E de
// tres barras con la central un 10 % más corta, y el blanco entre letras calculado sobre
// el perfil de cada pareja. El isotipo vive en una retícula de 13 módulos: lado 6, calle 1,
// radio {i['radio']:g}, y el círculo un 4 % mayor que el lado (a igual medida se ve más pequeño);
// por eso rebasa la retícula en {i['respiro']:g} y el viewBox lleva ese respiro: sin él, sale recortado.
//
// Este isotipo es el MAESTRO, para 48 px o más. Por debajo se sigue usando
// assets/sphere.svg, que es su versión de tamaño pequeño (calle más ancha, 24 px).
// El logotipo hereda el color del texto (currentColor): blanco en oscuro, tinta en claro.

const LETRAS = [
{letras},
]

export function Isotipo({{ size = 76, style }}) {{
  return (
    <svg width={{size}} height={{size}} viewBox="{d['vb_isotipo']}" aria-hidden="true" style={{{{ display: 'block', ...style }}}}>
      <rect x="0" y="0" width="{i['lado']:g}" height="{i['lado']:g}" rx="{i['radio']:g}" fill="{i['teal']}" />
      <rect x="{p:g}" y="0" width="{i['lado']:g}" height="{i['lado']:g}" rx="{i['radio']:g}" fill="{i['pizarra']}" />
      <rect x="0" y="{p:g}" width="{i['lado']:g}" height="{i['lado']:g}" rx="{i['radio']:g}" fill="{i['pizarra']}" />
      <circle cx="{c:g}" cy="{c:g}" r="{i['circulo'] / 2:g}" fill="{i['teal']}" />
    </svg>
  )
}}

export function Logotipo({{ width = 152, style }}) {{
  return (
    <svg width={{width}} viewBox="{vb}" role="img" aria-label="Contexto" style={{{{ display: 'block', height: 'auto', ...style }}}}>
      <g fill="currentColor">
        {{LETRAS.map((l, i) => <path key={{i}} transform={{`translate(${{l.x}} 0)`}} d={{l.d}} />)}}
      </g>
    </svg>
  )
}}

// Versión vertical (la principal): isotipo de 13 módulos, 2 de separación, y el logotipo al
// doble de ancho que el isotipo.
export default function LogoVertical({{ size = 76, color = 'var(--text)' }}) {{
  return (
    <div style={{{{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: (size * 2) / 13, color }}}}>
      <Isotipo size={{size}} />
      <Logotipo width={{size * 2}} />
    </div>
  )
}}
"""
dst = Path(sys.argv[1]) if len(sys.argv) > 1 else B.parents[2] / 'frontend' / 'src' / 'LogoContexto.jsx'
dst.write_bytes(src.encode('utf-8'))          # bytes: LF siempre, también en Windows
print('escrito', dst, len(src.encode('utf-8')), 'bytes')
