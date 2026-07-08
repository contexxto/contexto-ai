import { X, ArrowLeftRight, Check } from 'lucide-react'

// Modo COMPARAR — el DELTA de encaje entre dos inmuebles, dimensión por dimensión.
// NO un "92% vs 78%" frío: muestra QUIÉN gana en cada cosa que el usuario pidió, con el
// dato y su fuente (nunca un veredicto sobre la persona). El número sale del motor
// determinístico del backend (app/encaje.py delta_encaje), no del LLM. Paleta FRÍA de
// ZONA: el teal marca al ganador de cada dimensión; el color no infla nada (guardrail
// de honestidad / Fair Housing, tarea #14).

// Paleta vía tokens del design system → adapta a tema oscuro/claro.
const C = {
  panel: 'var(--surface-1)', teal: 'var(--teal)', tealHi: 'var(--teal-bright)',
  text: 'var(--text)', muted: 'var(--text-mid)', line: 'var(--border)',
}

// Etiquetas humanas de las 7 dimensiones-necesidad (whitelist cerrada del motor).
const DIM_LABEL = {
  tranquilidad: 'Tranquilidad', caminable: 'Caminable', transporte: 'Transporte',
  area_verde: 'Área verde', presupuesto_max: 'Presupuesto',
  min_dormitorios: 'Dormitorios', acepta_mascotas: 'Mascotas',
}

const nombreCorto = (c) => c?.direccion || c?.tipo_activo || 'Inmueble'

function ScorePill({ score }) {
  if (score == null) return <span style={{ color: C.muted, fontWeight: 700 }}>—</span>
  return <span style={{ color: C.tealHi, fontWeight: 800, fontSize: '1.05rem' }}>{score}%</span>
}

// Celda de una dimensión para un inmueble: el texto explicable del motor (dato+fuente).
// Resaltada en teal solo si ESTE inmueble gana esa dimensión.
function Celda({ texto, gana }) {
  return (
    <div style={{
      flex: 1, minWidth: 0, padding: '6px 8px', borderRadius: 8, fontSize: '.7rem', lineHeight: 1.35,
      background: gana ? 'rgba(45,189,182,.10)' : 'transparent',
      border: `1px solid ${gana ? 'rgba(45,189,182,.34)' : 'transparent'}`,
      color: gana ? C.tealHi : C.muted,
      display: 'flex', gap: 5, alignItems: 'flex-start',
    }}>
      {gana && <Check size={12} style={{ flexShrink: 0, marginTop: 2 }} />}
      <span>{texto || '—'}</span>
    </div>
  )
}

function FilaDim({ d }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontSize: '.64rem', color: C.muted, fontWeight: 700, textTransform: 'uppercase',
                    letterSpacing: .3, marginBottom: 3 }}>
        {DIM_LABEL[d.dimension] || d.dimension}
        {d.gana === 'empate' && <span style={{ fontWeight: 500, textTransform: 'none' }}> · empate</span>}
        {d.gana === 'sin_dato' && <span style={{ fontWeight: 500, textTransform: 'none' }}> · sin dato</span>}
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <Celda texto={d.a_texto} gana={d.gana === 'a'} />
        <Celda texto={d.b_texto} gana={d.gana === 'b'} />
      </div>
    </div>
  )
}

function Cuerpo({ delta, cards }) {
  const [a, b] = cards
  const dims = delta?.dimensiones || []
  return (
    <div style={{ padding: '10px 12px' }}>
      {/* Encabezados A | B: nombre + encaje global (mismo score que la tarjeta) */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
        {[{ c: a, s: delta?.a?.score }, { c: b, s: delta?.b?.score }].map((x, i) => (
          <div key={i} style={{ minWidth: 0 }}>
            <div style={{ fontSize: '.72rem', color: C.text, fontWeight: 700,
                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {nombreCorto(x.c)}
            </div>
            <ScorePill score={x.s} />
          </div>
        ))}
      </div>

      {dims.length === 0 ? (
        <div style={{ fontSize: '.76rem', color: C.muted, lineHeight: 1.5 }}>
          Aún no me dijiste qué buscas. Cuéntame tus prioridades (tranquilidad, presupuesto,
          transporte…) y comparo ambos contra eso.
        </div>
      ) : (
        dims.map((d) => <FilaDim key={d.dimension} d={d} />)
      )}

      <div style={{ fontSize: '.66rem', color: C.muted, marginTop: 8 }}>
        Comparado contra tus necesidades declaradas — no sobre quién eres. Cada dato con su fuente.
      </div>
    </div>
  )
}

// data = respuesta del endpoint /comparar: {ok, delta, cards} | {ok:false, message} | null.
export default function DeltaEncaje({ data, loading, onClose }) {
  return (
    <div style={{ marginTop: 12, borderRadius: 14, border: `1px solid ${C.line}`,
                  background: C.panel, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '9px 12px',
                    borderBottom: `1px solid ${C.line}` }}>
        <ArrowLeftRight size={15} color={C.teal} />
        <strong style={{ fontSize: '.82rem', color: C.text }}>Comparación</strong>
        <span style={{ fontSize: '.7rem', color: C.muted }}>· contra lo que pediste</span>
        <button onClick={onClose} title="Cerrar comparación"
          style={{ marginLeft: 'auto', background: 'transparent', border: 'none',
                   color: C.muted, cursor: 'pointer', display: 'flex', padding: 2 }}>
          <X size={16} />
        </button>
      </div>
      {loading && (
        <div style={{ padding: '16px 12px', color: C.muted, fontSize: '.8rem' }}>Comparando…</div>
      )}
      {!loading && data && data.ok === false && (
        <div style={{ padding: '14px 12px', color: C.muted, fontSize: '.8rem' }}>
          {data.message || 'No pude comparar ahora mismo.'}
        </div>
      )}
      {!loading && data?.ok && <Cuerpo delta={data.delta} cards={data.cards || []} />}
    </div>
  )
}
