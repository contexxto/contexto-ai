// Headers compartidos para todas las llamadas al backend.
// Incluye la llave del backend (X-API-Key) y, si hay sesión, el Bearer token del usuario.
export const API_BASE = import.meta.env.VITE_API_URL ?? ''
const API_KEY = import.meta.env.VITE_API_KEY ?? ''

let accessToken = null
export function setAccessToken(t) { accessToken = t || null }
export function getAccessToken() { return accessToken }

export function apiHeaders() {
  return {
    ...(API_KEY ? { 'X-API-Key': API_KEY } : {}),
    ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
  }
}
