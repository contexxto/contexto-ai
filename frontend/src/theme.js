// ── Tema (oscuro / claro) ────────────────────────────────────────────────────
// El tema vive en <html data-theme="dark|light">; los tokens de index.css
// cambian solos. Se persiste en localStorage. La inicialización anti-flash está
// en index.html (script inline en el <head>), así que la app arranca sin parpadeo.

const KEY = 'contexto_theme'

export function getTheme() {
  try { return localStorage.getItem(KEY) === 'light' ? 'light' : 'dark' } catch { return 'dark' }
}

// Color de la barra del sistema por tema. Son los `--bg` de index.css, repetidos aquí
// porque el <meta> se escribe desde JS: el tema de Contexto vive en localStorage, NO en
// `prefers-color-scheme`, así que la variante declarativa
// (<meta name="theme-color" media="(prefers-color-scheme: light)">) daría el color del
// SISTEMA y no el de la app — teléfono en oscuro + app en claro = barra negra sobre blanco.
// El mismo par está en el script anti-flash de index.html, para que la barra ya salga bien
// en el primer pintado. `temaBarra.test.js` vigila que los tres sitios no se separen.
export const COLOR_BARRA = { dark: '#1C1C1C', light: '#FFFFFF' }

export function applyTheme(t) {
  const theme = t === 'light' ? 'light' : 'dark'
  try { document.documentElement.setAttribute('data-theme', theme) } catch { /* noop */ }
  try {
    const meta = document.querySelector('meta[name="theme-color"]')
    if (meta) meta.setAttribute('content', COLOR_BARRA[theme])
  } catch { /* noop */ }
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
