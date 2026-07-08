/** Markdown → HTML: headers h1-h4, tablas, listas (ol/ul), bold, italic, code, hr.
 *  Parser línea por línea (robusto ante líneas en blanco del agente).
 *  Compartido por el chat del comprador (App.jsx) y el CRM Vivo del corredor (CRMChat.jsx). */
export function renderMarkdown(text) {
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const inline = s => esc(s)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
  const cells = r => r.replace(/^\s*\|/, '').replace(/\|\s*$/, '').split('|').map(c => c.trim())

  const lines = (text || '').split('\n')
  const out = []
  let list = null  // 'ul' | 'ol'
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null } }

  let i = 0
  while (i < lines.length) {
    const t = lines[i].trim()
    let m

    // ── Tabla: fila |...| seguida (saltando blancos) de un separador |---| ──
    if (t.startsWith('|')) {
      let j = i + 1
      while (j < lines.length && lines[j].trim() === '') j++
      if (j < lines.length && /^\|?[\s:|-]+\|?$/.test(lines[j].trim()) && lines[j].includes('-')) {
        closeList()
        const header = t
        i = j + 1
        const rows = []
        while (i < lines.length) {
          const tt = lines[i].trim()
          if (tt === '') { i++; continue }
          if (tt.startsWith('|')) { rows.push(tt); i++; continue }
          break
        }
        let html = '<table><thead><tr>' +
          cells(header).map(c => `<th>${inline(c)}</th>`).join('') + '</tr></thead><tbody>'
        for (const r of rows) html += '<tr>' + cells(r).map(c => `<td>${inline(c)}</td>`).join('') + '</tr>'
        out.push(html + '</tbody></table>')
        continue
      }
    }

    if ((m = t.match(/^####\s+(.+)$/))) { closeList(); out.push(`<h4>${inline(m[1])}</h4>`); i++; continue }
    if ((m = t.match(/^###\s+(.+)$/)))  { closeList(); out.push(`<h3>${inline(m[1])}</h3>`); i++; continue }
    if ((m = t.match(/^##\s+(.+)$/)))   { closeList(); out.push(`<h2>${inline(m[1])}</h2>`); i++; continue }
    if ((m = t.match(/^#\s+(.+)$/)))    { closeList(); out.push(`<h2>${inline(m[1])}</h2>`); i++; continue }
    if (/^(---+|___+|\*\*\*+)$/.test(t)) { closeList(); out.push('<hr/>'); i++; continue }

    // ── Tarjeta de ENCAJE (intent-matching): corrida de líneas ✅ / ⚠️ ──
    if (/^[-*]?\s*(✅|⚠)️?\s*\S/.test(t)) {
      closeList()
      const rows = []
      while (i < lines.length) {
        const mm = lines[i].trim().match(/^[-*]?\s*(✅|⚠)️?\s*(.+)$/)
        if (!mm) break
        const ok = mm[1] === '✅'
        rows.push(`<div style="display:flex;gap:8px;align-items:flex-start;padding:5px 0;font-size:.9rem;line-height:1.45;"><span style="flex-shrink:0;">${ok ? '✅' : '⚠️'}</span><span class="${ok ? 'enc-ok' : 'enc-warn'}">${inline(mm[2])}</span></div>`)
        i++
      }
      out.push(`<div style="margin:12px 0;border:1px solid rgba(45,189,182,.25);border-radius:14px;padding:8px 14px;background:rgba(45,189,182,.06);">${rows.join('')}</div>`)
      continue
    }

    if ((m = t.match(/^\d+[.)]\s+(.+)$/))) {
      if (list !== 'ol') { closeList(); out.push('<ol>'); list = 'ol' }
      out.push(`<li>${inline(m[1])}</li>`); i++; continue
    }
    if ((m = t.match(/^[*\-]\s+(.+)$/))) {
      if (list !== 'ul') { closeList(); out.push('<ul>'); list = 'ul' }
      out.push(`<li>${inline(m[1])}</li>`); i++; continue
    }

    if (t === '') { closeList(); i++; continue }

    closeList()
    out.push(`<p>${inline(t)}</p>`)
    i++
  }
  closeList()
  return out.join('\n')
}
