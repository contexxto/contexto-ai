/**
 * Service Worker — Contexto AI
 * 1) Notificaciones push nativas cuando el corredor responde al lead.
 * 2) PWA: instalabilidad (requiere un handler de fetch) + respaldo offline del shell.
 * Se registra en App.jsx al cargar la app.
 */

// ── PWA ────────────────────────────────────────────────────────────────────
const SHELL_CACHE = 'contexto-shell-v1'

self.addEventListener('install', (event) => {
  self.skipWaiting()
  // Cachea el shell (index en /) para el respaldo offline. Si falla, no bloquea la instalación.
  event.waitUntil(caches.open(SHELL_CACHE).then((c) => c.add('/')).catch(() => {}))
})

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL_CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  )
})

// Solo navegaciones (HTML): red primero (siempre fresco online), shell cacheado si no hay red.
// Assets hasheados y API NO se interceptan → los maneja el navegador, sin riesgo de servir viejo.
self.addEventListener('fetch', (event) => {
  const req = event.request
  if (req.method === 'GET' && req.mode === 'navigate') {
    event.respondWith(
      fetch(req).then((res) => {
        // Refresca el shell cacheado con la última versión de / (mantiene fresco el respaldo offline).
        if (new URL(req.url).pathname === '/') {
          const copy = res.clone()
          caches.open(SHELL_CACHE).then((c) => c.put('/', copy)).catch(() => {})
        }
        return res
      }).catch(() => caches.match('/'))
    )
  }
})

self.addEventListener('push', (event) => {
  let data = {}
  try { data = event.data?.json() ?? {} } catch { /* ignore */ }

  const title   = data.title  ?? 'Contexto AI'
  const body    = data.body   ?? 'Tienes un mensaje nuevo.'
  const icon    = data.icon   ?? '/sphere-favicon.svg'
  const badge   = '/sphere-favicon.svg'
  const destUrl = data.url    ?? '/'

  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon,
      badge,
      data: { url: destUrl },
      // Agrupa las notificaciones de la misma sesión (evita spam)
      tag: destUrl,
      renotify: true,
    })
  )
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data?.url ?? '/'

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // Si la app ya está abierta → enfocarla y navegar
      for (const client of clientList) {
        if ('focus' in client) {
          client.focus()
          if ('navigate' in client) client.navigate(url)
          return
        }
      }
      // Si no está abierta → abrir nueva ventana
      if (clients.openWindow) return clients.openWindow(url)
    })
  )
})
