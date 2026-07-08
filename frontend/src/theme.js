// ── Tema (oscuro / claro) ────────────────────────────────────────────────────
// El tema vive en <html data-theme="dark|light">; los tokens de index.css
// cambian solos. Se persiste en localStorage. La inicialización anti-flash está
// en index.html (script inline en el <head>), así que la app arranca sin parpadeo.

const KEY = 'contexto_theme'

export function getTheme() {
  try { return localStorage.getItem(KEY) === 'light' ? 'light' : 'dark' } catch { return 'dark' }
}

export function applyTheme(t) {
  try { document.documentElement.setAttribute('data-theme', t === 'light' ? 'light' : 'dark') } catch { /* noop */ }
}

export function setTheme(t) {
  const theme = t === 'light' ? 'light' : 'dark'
  try { localStorage.setItem(KEY, theme) } catch { /* noop */ }
  applyTheme(theme)
  return theme
}

export function toggleTheme() {
  return setTheme(getTheme() === 'light' ? 'dark' : 'light')
}
