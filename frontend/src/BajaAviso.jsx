/**
 * Plan 1.1 · TR-2 — confirmación de baja que abre el enlace de cada aviso al comprador.
 *
 * Abrir el enlace (GET) NO cambia nada: los escáneres de correo y las vistas previas abren
 * enlaces solos. Solo el clic de la persona hace el POST, y solo puede desactivar o cerrar.
 */
import { useEffect, useState } from 'react'
import axios from 'axios'
import { X } from 'lucide-react'

import { API_BASE } from './api'
import { COPY_AVISO, cuerpoBaja, tokenDeBaja, urlSinBaja } from './avisoReenganche'

export default function BajaAviso({ token, onCerrar }) {
  const [estado, setEstado] = useState('pregunta')   // pregunta | enviando | desactivado | cerrado | invalido | error

  const confirmar = async (accion) => {
    setEstado('enviando')
    try {
      await axios.post(`${API_BASE}/api/v1/chat/baja-aviso`, cuerpoBaja(token, accion))
      setEstado(accion === 'cerrar' ? 'cerrado' : 'desactivado')
    } catch (e) {
      setEstado(e?.response?.status === 400 ? 'invalido' : 'error')
    }
  }

  const boton = {
    padding: '7px 14px', borderRadius: 999, cursor: 'pointer', fontSize: '.8rem', fontWeight: 600,
    background: 'transparent', border: '1px solid var(--border, rgba(255,255,255,.2))',
    color: 'inherit',
  }
  const final = { desactivado: COPY_AVISO.desactivado, cerrado: COPY_AVISO.cerrado,
    invalido: COPY_AVISO.bajaInvalida, error: COPY_AVISO.error }[estado]

  return (
    <div role="dialog" aria-label={COPY_AVISO.bajaTitulo}
      style={{ margin: '8px auto', maxWidth: 560, padding: '12px 14px', borderRadius: 12,
               background: 'var(--surface, rgba(255,255,255,.04))',
               border: '1px solid var(--border, rgba(255,255,255,.12))', fontSize: '.85rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
        <span>{final || COPY_AVISO.bajaTitulo}</span>
        <button onClick={onCerrar} aria-label="Cerrar" style={{ ...boton, padding: 4, border: 'none' }}>
          <X size={14} />
        </button>
      </div>
      {!final && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginTop: 10 }}>
          <button style={boton} disabled={estado === 'enviando'} onClick={() => confirmar('revocar')}>
            {COPY_AVISO.dejar}
          </button>
          <button style={boton} disabled={estado === 'enviando'} onClick={() => confirmar('cerrar')}>
            {COPY_AVISO.cerrar}
          </button>
        </div>
      )}
    </div>
  )
}

/**
 * La capa que monta main.jsx junto a <App/>: lee `?baja=` UNA vez, al montar (antes de que
 * cualquier efecto de App limpie la URL), lo quita de la barra y muestra la confirmación
 * flotante sobre la vista que sea —incluida la página de anuncio /a/{id}, que es donde
 * aterriza el push—. Leer y limpiar la URL no es mutar nada en el servidor.
 */
export function CapaBajaAviso() {
  const [token, setToken] = useState(() => tokenDeBaja(window.location.search))
  useEffect(() => {
    if (new URLSearchParams(window.location.search).has('baja')) {
      window.history.replaceState(window.history.state, '', urlSinBaja(window.location.pathname, window.location.search))
    }
  }, [])
  if (!token) return null
  return (
    <div style={{ position: 'fixed', left: 16, right: 16, top: 12, zIndex: 1000,
                  background: 'var(--bg, #16151E)', borderRadius: 12, maxWidth: 560, margin: '0 auto',
                  boxShadow: '0 8px 30px rgba(0,0,0,.35)' }}>
      <BajaAviso token={token} onCerrar={() => setToken(null)} />
    </div>
  )
}
