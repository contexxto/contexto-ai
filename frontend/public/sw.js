/**
 * Service Worker — Contexto AI
 * Maneja notificaciones push nativas cuando el corredor responde al lead.
 * Se registra en App.jsx al cargar la app.
 */

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
