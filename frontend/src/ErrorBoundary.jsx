import { Component } from 'react'

// Red de seguridad de render: si CUALQUIER componente hijo lanza al dibujarse, en
// vez de tumbar toda la app (pantalla negra) mostramos un mensaje legible + el error
// para diagnóstico. Los error boundaries deben ser class components (no hay hook).
const C = {
  bg: '#16151E', panel: '#1E1D28', teal: '#2DBDB6', tealHi: '#5EEAD4',
  text: '#EDEBF2', muted: '#9C99AC', line: 'rgba(45,189,182,.20)',
}

export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null, stack: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // Deja el error a la vista para diagnóstico (consola + estado).
    console.error('ErrorBoundary capturó:', error, info?.componentStack)
    this.setState({ stack: info?.componentStack || null })
  }

  reset = () => this.setState({ error: null, stack: null })

  render() {
    if (!this.state.error) return this.props.children
    const label = this.props.label || 'esta sección'
    return (
      <div style={{ minHeight: '60vh', display: 'grid', placeItems: 'center', padding: 24,
                    color: C.text, fontFamily: 'Inter, system-ui, sans-serif' }}>
        <div style={{ maxWidth: 460, textAlign: 'center', border: `1px solid ${C.line}`, borderRadius: 18,
                      padding: '26px 24px', background: 'rgba(255,255,255,.02)' }}>
          <div style={{ fontSize: '2rem', marginBottom: 10 }}>🧭</div>
          <h2 style={{ margin: '0 0 8px', fontSize: '1.1rem' }}>Algo se cruzó en {label}</h2>
          <p style={{ color: C.muted, fontSize: '.86rem', margin: '0 0 18px', lineHeight: 1.5 }}>
            No es tu conexión — un componente falló al dibujarse. Puedes reintentar o recargar;
            el resto de la app sigue viva.
          </p>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'center', flexWrap: 'wrap' }}>
            <button onClick={this.reset}
              style={{ padding: '9px 18px', borderRadius: 10, cursor: 'pointer', fontWeight: 700, fontSize: '.85rem',
                       background: `linear-gradient(90deg,${C.teal},${C.tealHi})`, color: '#0E0D13', border: 'none' }}>
              Reintentar
            </button>
            <button onClick={() => window.location.reload()}
              style={{ padding: '9px 18px', borderRadius: 10, cursor: 'pointer', fontWeight: 700, fontSize: '.85rem',
                       background: 'rgba(255,255,255,.05)', border: `1px solid ${C.line}`, color: C.text }}>
              Recargar
            </button>
          </div>
          <details style={{ marginTop: 18, textAlign: 'left' }}>
            <summary style={{ cursor: 'pointer', fontSize: '.72rem', color: C.muted }}>Detalle técnico</summary>
            <pre style={{ marginTop: 8, fontSize: '.68rem', color: C.muted, whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word', maxHeight: 180, overflow: 'auto' }}>
              {String(this.state.error?.message || this.state.error)}
              {this.state.stack ? '\n' + this.state.stack : ''}
            </pre>
          </details>
        </div>
      </div>
    )
  }
}
