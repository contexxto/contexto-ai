import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import QueEs from './QueEs.jsx'
import ErrorBoundary from './ErrorBoundary.jsx'

// Web de marketing (/que-es): página standalone. Se renderiza EN LUGAR de <App/>
// (no dentro), así NO monta la maquinaria del app (sesión Supabase, carga de
// conversaciones, geo…). El launcher en / y el resto de la app quedan intactos.
const isQueEs = /^\/que-es\/?$/.test(window.location.pathname)

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <ErrorBoundary label="la aplicación">
      {isQueEs
        ? <QueEs
            onStart={() => window.location.assign('/')}
            onLogin={() => window.location.assign('/?login=1')}
            onBroker={() => window.location.assign('/?corredor=1')} />
        : <App />}
    </ErrorBoundary>
  </StrictMode>,
)
