import { useState, useEffect } from 'react'
import {
  MapPin, Target, ShieldCheck, Compass, Footprints, BadgeCheck, Users,
  RefreshCw, Layers, Camera, Building2, Volume2, Clock, ArrowRight, Sun, Moon,
} from 'lucide-react'
import { getTheme, toggleTheme } from './theme'
import './QueEs.css'

// Marca de Contexto (mismo mark del header de la app).
const Mark = ({ size = 21 }) => (
  <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden>
    <rect x="3" y="3" width="7" height="7" rx="1.6" fill="var(--teal-bright)" />
    <rect x="14" y="3" width="7" height="7" rx="1.6" fill="#3A3D44" />
    <rect x="3" y="14" width="7" height="7" rx="1.6" fill="#3A3D44" />
    <circle cx="17.5" cy="17.5" r="4" fill="var(--teal-bright)" />
  </svg>
)

const FOSO = [
  { Icon: Compass, t: 'Encaje relativo a intención', d: '“X% de encaje contigo”, no un puntaje absoluto igual para todos.' },
  { Icon: Footprints, t: 'Isócronas peatonales', d: 'Motor Valhalla: tiempos reales a pie, no radios en línea recta.' },
  { Icon: BadgeCheck, t: 'Verificación + frescura', d: 'Badges de qué está verificado y hace cuánto — nada rancio.' },
  { Icon: Users, t: 'CRM del corredor', d: 'Tu cartera viva: quién pide corredor, quién reenganchar, qué pasó.' },
  { Icon: RefreshCw, t: 'Reenganche', d: 'Retoma a los interesados dormidos aportando valor, no spam.' },
  { Icon: Layers, t: 'POIs propios', d: 'Overture + OSM conflados: la capa de entorno es nuestra, no alquilada.' },
]

const DOLORES = [
  { Icon: Camera, q: '“Cerca de todo”', d: '…pero ¿a cuántos minutos a pie? Nadie lo dice.' },
  { Icon: Building2, q: 'Fotos del inmueble', d: 'Cero del entorno. El barrio importa más que la cocina.' },
  { Icon: Volume2, q: 'Ruido, tráfico, colegios', d: 'Lo que decide tu día a día — nadie lo verifica.' },
  { Icon: Clock, q: 'Te enteras después', d: 'De mudarte. Cuando ya es tarde para cambiar de opinión.' },
]

export default function QueEs({ onStart, onBroker, onLogin }) {
  const [theme, setThemeState] = useState(getTheme())
  const cambiaTema = () => { toggleTheme(); setThemeState(getTheme()) }

  // El body de la app es height:100dvh; overflow:hidden (layout fijo tipo app). La web SÍ
  // scrollea → liberamos el clip mientras esta página está montada y lo restauramos al salir.
  useEffect(() => {
    const b = document.body.style
    const prevOverflow = b.overflow, prevHeight = b.height
    b.overflow = 'auto'; b.height = 'auto'
    return () => { b.overflow = prevOverflow; b.height = prevHeight }
  }, [])

  return (
    <div className="qe">
      {/* NAV */}
      <nav><div className="wrap nav-in">
        <a className="brand" href="/"><Mark /> Contexto</a>
        <div className="nav-links">
          <a href="#que-es">Qué es</a>
          <a href="#features">Características</a>
          <a href="#corredores">Corredores</a>
          <a href="/">Abrir app</a>
        </div>
        <div className="nav-cta">
          <button className="btn ghost" onClick={onLogin}>Ingresar</button>
          <button className="btn primary" onClick={onStart}>Empieza gratis</button>
          <button className="toggle" onClick={cambiaTema} aria-label="Cambiar tema">
            {theme === 'dark' ? <Sun className="lu" size={16} /> : <Moon className="lu" size={16} />}
          </button>
        </div>
      </div></nav>

      {/* HERO */}
      <header className="hero"><div className="wrap">
        <span className="eyebrow"><span className="dot" /> Inteligencia geoespacial inmobiliaria · Quito</span>
        <h1 className="big">Cada lugar<br />tiene un <em>aura</em>.</h1>
        <p className="sub">
          La IA inmobiliaria que <b>verifica el entorno</b> antes de recomendarlo. No fotos bonitas —
          caminabilidad real, colegios, ruido y a cuántos minutos a pie está todo.
        </p>
        <div className="hero-cta">
          <button className="btn primary lg" onClick={onStart}>Analiza tu zona <ArrowRight className="lu" size={18} /></button>
          <button className="btn lg" onClick={onBroker}><Users className="lu" size={18} /> Soy corredor</button>
        </div>

        <div className="story">
          <div className="pain">Fotos hermosas. Ubicación “inmejorable”. Te mudas…</div>
          <div className="fix">
            …y el colegio queda a 40 minutos, la avenida no te deja dormir y al parque “cercano” no se llega a pie.{' '}
            <b>Contexto verifica el entorno ANTES</b> — sobre los comercios y datos reales de la cuadra, no sobre la descripción del anuncio.
          </div>
        </div>
      </div></header>

      {/* QUÉ ES */}
      <section className="blk alt" id="que-es"><div className="wrap">
        <div className="kicker">¿Qué es Contexto?</div>
        <h2>El entorno, verificado.<br />El encaje, contigo.</h2>
        <p className="lead">No es otro portal de fotos. Es un agente que entiende tu intención y contrasta cada lugar contra el mundo real, con proveniencia.</p>
        <div className="pillars">
          <div className="pillar">
            <div className="ic"><MapPin className="lu" size={22} /></div>
            <h3>Verifica el entorno</h3>
            <p>Caminabilidad real, colegios, parques, ruido y tráfico — calculado sobre los comercios y datos reales de la cuadra, no sobre lo que dice el anuncio.</p>
          </div>
          <div className="pillar">
            <div className="ic"><Target className="lu" size={22} /></div>
            <h3>Encaja con tu intención</h3>
            <p>“Para mi familia”, “cerca del metro”, “según mi presupuesto” → un <b>% de encaje contigo</b>, no un ranking genérico para todos.</p>
          </div>
          <div className="pillar">
            <div className="ic"><ShieldCheck className="lu" size={22} /></div>
            <h3>Honestidad como producto</h3>
            <p>Te dice cuándo un lugar <b>no</b> encaja. Estimaciones rotuladas como estimación. Cero dato inventado.</p>
          </div>
        </div>
      </div></section>

      {/* FEATURES */}
      <section className="blk" id="features"><div className="wrap">
        <div className="kicker">Cómo funciona</div>
        <h2>Ve el aura. Habla con el lugar.</h2>
        <p className="lead" style={{ marginBottom: 50 }}>Tres piezas que ningún portal tiene.</p>

        <div className="feats">
        <div className="feat">
          <div className="copy">
            <div className="tag">Mapa Vivo</div>
            <h3>El aura del lugar, en el mapa</h3>
            <p>Isócronas peatonales reales: a cuántos minutos <b>a pie</b> está cada colegio, parque y comercio. Compara dos lugares aura contra aura.</p>
            <button className="more" onClick={onStart}>Ver el mapa <ArrowRight className="lu" size={15} /></button>
          </div>
          <div className="art">
            <div className="ring" style={{ width: 70, height: 70 }} />
            <div className="ring" style={{ width: 120, height: 120 }} />
            <div className="ring" style={{ width: 170, height: 170 }} />
            <div className="pin" />
          </div>
        </div>

        <div className="feat">
          <div className="copy">
            <div className="tag">Agente 24/7</div>
            <h3>Conversa sobre el inmueble y su entorno</h3>
            <p>Con dato verificado y <b>proveniencia</b> — de dónde sale cada cifra. Sin hype, sin “inmejorable”. Rango honesto en vez de falsa precisión.</p>
            <button className="more" onClick={onStart}>Probar el agente <ArrowRight className="lu" size={15} /></button>
          </div>
          <div className="art">
            <div className="bubble-q">¿Cómo es vivir aquí con niños?</div>
            <div className="bubble-a">Caminabilidad 94 · colegio a ~7 min a pie · parque a ~4 min ✓</div>
          </div>
        </div>

        <div className="feat" id="corredores">
          <div className="copy">
            <div className="tag">Para corredores</div>
            <h3>Recibe leads calificados, no “alguien preguntó”</h3>
            <p>Alguien cuyo deseo ya <b>encaja</b> con el lugar real y con lo que puede pagar. Publica tu inmueble, genera el QR de tu letrero y tu agente atiende 24/7.</p>
            <button className="more" onClick={onBroker}>Empezar como corredor <ArrowRight className="lu" size={15} /></button>
          </div>
          <div className="art"><div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center' }}><div className="qr">QR</div></div></div>
        </div>
        </div>
      </div></section>

      {/* FOSO */}
      <section className="blk alt"><div className="wrap">
        <div className="kicker">Más adentro</div>
        <h2>Un foso de datos propio</h2>
        <p className="lead">Cada pieza construida para que el entorno sea verificable, no decorativo.</p>
        <div className="grid">
          {FOSO.map(({ Icon, t, d }) => (
            <div className="cell" key={t}>
              <div className="ic"><Icon className="lu" size={20} /></div>
              <h4>{t}</h4><p>{d}</p>
            </div>
          ))}
        </div>
      </div></section>

      {/* DOLOR */}
      <section className="blk"><div className="wrap" style={{ textAlign: 'center' }}>
        <div className="kicker">El problema</div>
        <h2>Buscas con fotos bonitas.<br />¿Pero cómo es vivir ahí de verdad?</h2>
        <p className="lead">Lo sabes. Todos lo saben.</p>
        <div className="pains">
          {DOLORES.map(({ Icon, q, d }) => (
            <div className="paincard" key={q}>
              <div className="q"><Icon className="lu" size={17} /> {q}</div>
              <p>{d}</p>
            </div>
          ))}
        </div>
      </div></section>

      {/* CTA FINAL */}
      <section className="blk alt"><div className="wrap" style={{ textAlign: 'center' }}>
        <h2>Empieza por tu zona.</h2>
        <p className="lead">Analiza dónde estás parado ahora mismo — y descubre su aura en segundos.</p>
        <div className="hero-cta">
          <button className="btn primary lg" onClick={onStart}>Analiza dónde estás <ArrowRight className="lu" size={18} /></button>
          <button className="btn lg" onClick={onBroker}><Users className="lu" size={18} /> Soy corredor</button>
        </div>
      </div></section>

      {/* FOOTER */}
      <footer><div className="wrap foot">
        <a className="brand" href="/" style={{ fontSize: '.98rem' }}><Mark size={18} /> Contexto</a>
        <div className="cols">
          <a href="#que-es">Qué es</a>
          <a href="#features">Características</a>
          <a href="#corredores">Corredores</a>
          <a href="/">Abrir app</a>
        </div>
        <div className="cr">Cada lugar tiene un aura · Quito, Ecuador · © 2026 Contexto</div>
      </div></footer>
    </div>
  )
}
