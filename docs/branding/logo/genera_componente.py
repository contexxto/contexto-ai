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

def f(v):                                      # el mismo redondeo que genera_logo.py
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s

# Lockup horizontal: la misma cuenta que genera_logo.py usa para contexto-horizontal.svg.
hz, r, m = d['horizontal'], i['respiro'], i['m']
vb_h = f"{f(-r)} {f(-r)} {f(hz['vb'][0] + r + hz['esc'])} {f(m + 2 * r)}"
tr_h = f"translate({f(m + hz['sep'])} {f((m - 4.0) / 2)}) scale({hz['esc']:.5f})"
maestro = (B / 'contexto-horizontal.svg').read_text(encoding='utf-8')
if f'viewBox="{vb_h}"' not in maestro or f'transform="{tr_h}"' not in maestro:
    sys.exit('el lockup horizontal calculado NO coincide con contexto-horizontal.svg: no se escribe nada')
ancho_por_alto = float(vb_h.split()[2]) / float(vb_h.split()[3])
# Mínimo legible del logotipo (README de la marca): 96 px de ancho de PALABRA. El alto mínimo del
# lockup sale de ahí, no se decide aparte.
MIN_PALABRA_PX = 96
palabra_por_alto = d['ancho'] * hz['esc'] / (m + 2 * r)
alto_min_h = -(-MIN_PALABRA_PX // palabra_por_alto)          # techo
src = f"""// ── Logotipo de Contexto ─────────────────────────────────────────────────────
// GENERADO por docs/branding/logo/genera_logo.py + genera_componente.py: no editar los
// contornos a mano. El logotipo son contornos puros (sin fuente): caja alta geométrica de
// trazo {d['S']:g}/100, barras horizontales al 93 %, redondas al 104 % con rebase de {d['OV']:g}, la E de
// tres barras con la central un 10 % más corta, y el blanco entre letras calculado sobre
// el perfil de cada pareja. El isotipo vive en una retícula de 13 módulos: lado 6, calle 1,
// radio {i['radio']:g}, y el círculo un 4 % mayor que el lado (a igual medida se ve más pequeño);
// por eso rebasa la retícula en {i['respiro']:g} y el viewBox lleva ese respiro: sin él, sale recortado.
//
// Este isotipo es el MAESTRO. Solo, va desde 48 px; por debajo se sigue usando assets/sphere.svg,
// su versión de tamaño pequeño (calle más ancha, 24 px). Dentro del lockup horizontal va desde
// {alto_min_h:g} px: ahí la palabra llega a su mínimo legible de {MIN_PALABRA_PX} px (decisión de Carlos, 2026-09-21).
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

// Versión horizontal (para cabeceras): el MISMO lienzo que docs/branding/logo/contexto-horizontal.svg
// — caja alta de 4 módulos centrada en el isotipo y 4 de separación —. `alto` es el del isotipo, y
// el ancho sale de la proporción del lienzo. Por debajo de ALTO_MIN_HORIZONTAL la palabra baja de
// {MIN_PALABRA_PX} px y deja de leerse.
export const ALTO_MIN_HORIZONTAL = {alto_min_h:g}

export function LogoHorizontal({{ alto = ALTO_MIN_HORIZONTAL, style }}) {{
  return (
    <svg height={{alto}} width={{alto * {ancho_por_alto:.6f}}} viewBox="{vb_h}" role="img" aria-label="Contexto" style={{{{ display: 'block', ...style }}}}>
      <rect x="0" y="0" width="{i['lado']:g}" height="{i['lado']:g}" rx="{i['radio']:g}" fill="{i['teal']}" />
      <rect x="{p:g}" y="0" width="{i['lado']:g}" height="{i['lado']:g}" rx="{i['radio']:g}" fill="{i['pizarra']}" />
      <rect x="0" y="{p:g}" width="{i['lado']:g}" height="{i['lado']:g}" rx="{i['radio']:g}" fill="{i['pizarra']}" />
      <circle cx="{c:g}" cy="{c:g}" r="{i['circulo'] / 2:g}" fill="{i['teal']}" />
      <g fill="currentColor" transform="{tr_h}">
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
