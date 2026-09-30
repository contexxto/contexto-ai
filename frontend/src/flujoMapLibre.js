/**
 * ¿Qué valores PUEDEN llegar al motor de estilos de MapLibre? Analizador de flujo de la guarda
 * MAPLIBRE-COLOR-BOUNDARY. Lo usa `fronteraMapLibre.test.js`; la app no lo importa.
 *
 * El 2026-08-23 (`aed9015`) los hex del mapa pasaron a `var(--token)`. MapLibre tiene su propio
 * parser de color y no resuelve variables CSS, así que `addLayer` rechazó las capas: emite un
 * error y no las crea. El Mapa Vivo dejó de dibujar sus puntos, sin que fallara nada más.
 * Aquella migración SÍ buscó `var(` dentro de `paint:` y revirtió tres casos; los que se
 * escaparon llegaban por una CONSTANTE, un PARÁMETRO o un objeto DESESTRUCTURADO. Por eso esto
 * no busca texto: sigue cada valor desde `addLayer` / `setPaintProperty` hasta su origen.
 *
 * Sigue:
 *   · constantes y `let`/`var`, con sus reasignaciones;
 *   · parámetros de funciones con nombre, hasta cada llamada, con su valor por defecto;
 *   · el elemento de un `forEach`/`map`/…, con desestructuración;
 *   · miembros de objetos y arreglos literales;
 *   · el `return` de funciones locales o importadas de './…';
 *   · ternarios y `||`/`??`.
 *
 * Reporta:
 *   · `var(` en cualquier cadena alcanzable desde un `paint`/`layout`, sea cual sea la clave;
 *   · un origen DESCONOCIDO (dato del servidor, llamada opaca, callback…) en una clave de
 *     COLOR: si no se puede demostrar que es literal, no pasa.
 *
 * Para colores que vienen de datos está la frontera `colorMapa(valor, respaldo)` de
 * `mapaColores.js`. El analizador la trata como «puede devolver el respaldo»; que nunca deja
 * pasar un `var(` lo fijan sus propias pruebas.
 */
import fs from 'node:fs'
import path from 'node:path'
import { parseSync } from 'vite'

const LLAVE_COLOR = /color|gradient/          // fill-color, line-color, circle-stroke-color, line-gradient…
const ITERADORES = new Set(['forEach', 'map', 'filter', 'some', 'every', 'find', 'findLast', 'flatMap'])
const MISMOS_ELEMENTOS = new Set(['sort', 'filter', 'slice', 'reverse', 'toSorted', 'toReversed'])
const FRONTERA = { modulos: ['./mapaColores', './mapaColores.js'], nombre: 'colorMapa' }

const esFuncion = (n) =>
  n?.type === 'FunctionDeclaration' || n?.type === 'FunctionExpression' || n?.type === 'ArrowFunctionExpression'

function hijos(n) {
  const out = []
  for (const k of Object.keys(n)) {
    if (k === 'type' || k === 'start' || k === 'end') continue
    const v = n[k]
    if (Array.isArray(v)) { for (const x of v) if (x && typeof x.type === 'string') out.push(x) }
    else if (v && typeof v.type === 'string') out.push(v)
  }
  return out
}

function recorrer(n, fn, padre = null) {
  fn(n, padre)
  for (const h of hijos(n)) recorrer(h, fn, n)
}

function sinEnvoltura(n) {
  while (n && (n.type === 'ChainExpression' || n.type === 'ParenthesizedExpression')) n = n.expression
  return n
}

function miembroNombre(callee) {
  const c = sinEnvoltura(callee)
  if (c?.type !== 'MemberExpression') return null
  if (!c.computed) return c.property.name
  return c.property.type === 'Literal' ? c.property.value : null
}

const nombreDeClave = (p) =>
  p.computed ? (p.key.type === 'Literal' ? p.key.value : undefined) : (p.key.name ?? p.key.value)

/** Lector de fuentes de un directorio: `leer('intentHue.js')` o `null` si no existe. */
export function leerDe(dir) {
  return (nombre) => {
    const ruta = path.join(dir, nombre)
    return fs.existsSync(ruta) && fs.statSync(ruta).isFile() ? fs.readFileSync(ruta, 'utf8') : null
  }
}

/** `leer(nombre)` devuelve el fuente o `null`. Los imports './x' se resuelven con el mismo lector. */
export function crearAnalizador(leer) {
  const modulos = new Map()

  function modulo(nombre) {
    if (modulos.has(nombre)) return modulos.get(nombre)
    const fuente = leer(nombre)
    if (fuente == null) { modulos.set(nombre, null); return null }
    const { program, errors } = parseSync(nombre, fuente, { sourceType: 'module' })
    // Un fichero que no parsea dejaría la guarda en verde sin haber mirado nada.
    if (errors?.length) throw new Error(`${nombre} no parsea: ${errors[0]?.message ?? ''}`)
    const padres = new Map()
    recorrer(program, (n, p) => padres.set(n, p))
    const m = { nombre, fuente, program, padres }
    modulos.set(nombre, m)
    return m
  }

  function resolverModulo(fuente) {
    if (!fuente.startsWith('./')) return null
    const base = fuente.slice(2)
    for (const c of [base, `${base}.js`, `${base}.jsx`]) {
      const m = modulo(c)
      if (m) return m
    }
    return null
  }

  const linea = (m, n) => m.fuente.slice(0, n.start).split('\n').length
  const texto = (m, n) => m.fuente.slice(n.start, n.end).replace(/\s+/g, ' ').trim()
  const DESC = (m, n, motivo) => ({ m, n, desconocido: motivo })

  // Visitados por CAMINO (se quitan al volver): un nodo que aparece dos veces en contextos
  // distintos —`c ? X.a : X.b`— se explora las dos. Solo se corta la recursión real.
  function conCiclo(clave, vistos, f) {
    if (vistos.has(clave)) return []
    vistos.add(clave)
    try { return f() } finally { vistos.delete(clave) }
  }

  // ── ligaduras ────────────────────────────────────────────────────────────────────────────

  // Dónde, dentro de un patrón (`x`, `{ hue }`, `{ a: { b = 1 } }`, `[x]`), queda `nombre`.
  function rutaEnPatron(p, nombre) {
    if (!p) return null
    if (p.type === 'Identifier') return p.name === nombre ? { claves: [], defecto: null } : null
    if (p.type === 'AssignmentPattern') {
      const r = rutaEnPatron(p.left, nombre)
      return r && p.left.type === 'Identifier' ? { ...r, defecto: p.right } : r
    }
    if (p.type === 'RestElement') {
      const r = rutaEnPatron(p.argument, nombre)
      return r ? { claves: ['*'], defecto: null } : null
    }
    if (p.type === 'ObjectPattern') {
      for (const prop of p.properties) {
        if (prop.type === 'RestElement') {
          if (rutaEnPatron(prop.argument, nombre)) return { claves: ['*'], defecto: null }
          continue
        }
        const r = rutaEnPatron(prop.value, nombre)
        if (r) return { claves: [nombreDeClave(prop) ?? null, ...r.claves], defecto: r.defecto }
      }
      return null
    }
    if (p.type === 'ArrayPattern') {
      for (let i = 0; i < p.elements.length; i++) {
        const r = rutaEnPatron(p.elements[i], nombre)
        if (r) return { claves: [i, ...r.claves], defecto: r.defecto }
      }
      return null
    }
    return null
  }

  function buscarEnCuerpo(m, bloque, cuerpo, nombre) {
    for (const s of cuerpo) {
      const d = s.type === 'ExportNamedDeclaration' && s.declaration ? s.declaration : s
      if (d.type === 'VariableDeclaration') {
        for (const decl of d.declarations) {
          const ruta = rutaEnPatron(decl.id, nombre)
          if (ruta) return { tipo: 'var', m, nodo: decl, ruta, ambito: bloque, kind: d.kind, nombre }
        }
      } else if (d.type === 'FunctionDeclaration' && d.id?.name === nombre) {
        return { tipo: 'funcion', m, nodo: d, nombre }
      } else if (d.type === 'ImportDeclaration') {
        for (const sp of d.specifiers) {
          if (sp.local.name !== nombre) continue
          const importado = sp.type === 'ImportSpecifier' ? (sp.imported.name ?? sp.imported.value) : 'default'
          return { tipo: 'import', m, nodo: sp, fuente: d.source.value, importado, nombre }
        }
      }
    }
    return null
  }

  function ligadura(m, ident) {
    const nombre = ident.name
    for (let a = m.padres.get(ident); a; a = m.padres.get(a)) {
      if (esFuncion(a)) {
        for (let i = 0; i < a.params.length; i++) {
          const ruta = rutaEnPatron(a.params[i], nombre)
          if (ruta) return { tipo: 'param', m, nodo: a, indice: i, ruta, nombre }
        }
      }
      if (a.type === 'Program' || a.type === 'BlockStatement' || a.type === 'StaticBlock') {
        const b = buscarEnCuerpo(m, a, a.body, nombre)
        if (b) return b
      }
    }
    return null
  }

  function exportado(mod, nombre) {
    for (const s of mod.program.body) {
      if (s.type !== 'ExportNamedDeclaration') continue
      if (s.declaration) {
        const b = buscarEnCuerpo(mod, mod.program, [s.declaration], nombre)
        if (b) return b
      }
      for (const sp of s.specifiers || []) {
        const fuera = sp.exported.name ?? sp.exported.value
        const dentro = sp.local.name ?? sp.local.value
        if (fuera === nombre && !s.source) return buscarEnCuerpo(mod, mod.program, mod.program.body, dentro)
      }
    }
    return null
  }

  const esFrontera = (b) => b.tipo === 'import' && FRONTERA.modulos.includes(b.fuente) && b.importado === FRONTERA.nombre

  // ── valores ──────────────────────────────────────────────────────────────────────────────

  function candidatos(m, n, vistos) {
    if (!n) return []
    switch (n.type) {
      case 'Literal': case 'TemplateLiteral': case 'ArrayExpression': case 'ObjectExpression':
      case 'BinaryExpression': case 'UnaryExpression':
      case 'FunctionDeclaration': case 'FunctionExpression': case 'ArrowFunctionExpression':
        return [{ m, n }]
      case 'ParenthesizedExpression': case 'ChainExpression':
        return candidatos(m, n.expression, vistos)
      case 'ConditionalExpression':
        return [...candidatos(m, n.consequent, vistos), ...candidatos(m, n.alternate, vistos)]
      case 'LogicalExpression':
        return [...candidatos(m, n.left, vistos), ...candidatos(m, n.right, vistos)]
      case 'SequenceExpression':
        return candidatos(m, n.expressions[n.expressions.length - 1], vistos)
      case 'AssignmentExpression':
        return candidatos(m, n.right, vistos)
      case 'Identifier':
        return deIdentificador(m, n, vistos)
      case 'MemberExpression':
        return deMiembro(m, n, vistos)
      case 'CallExpression':
        return deLlamada(m, n, vistos)
      default:
        return [DESC(m, n, n.type)]
    }
  }

  function deIdentificador(m, n, vistos) {
    if (n.name === 'undefined') return []
    const b = ligadura(m, n)
    if (!b) return [DESC(m, n, `global «${n.name}»`)]
    return conCiclo(`${b.m.nombre}:${b.nodo.start}:${b.nombre}`, vistos, () => deLigadura(b, vistos))
  }

  function deLigadura(b, vistos) {
    const { m } = b
    if (b.tipo === 'funcion') return [{ m, n: b.nodo }]
    if (b.tipo === 'import') {
      const mod = resolverModulo(b.fuente)
      if (!mod) return [DESC(m, b.nodo, `import de «${b.fuente}»`)]
      const e = exportado(mod, b.importado)
      if (!e) return [DESC(m, b.nodo, `«${b.importado}» no se exporta desde ${mod.nombre}`)]
      return conCiclo(`${mod.nombre}:${e.nodo.start}:${e.nombre}`, vistos, () => deLigadura(e, vistos))
    }
    if (b.tipo === 'param') return deParametro(b, vistos)
    // var / let / const
    const base = b.nodo.init ? candidatos(m, b.nodo.init, vistos) : []
    if (b.kind !== 'const') {
      recorrer(b.ambito, (n) => {
        if (n.type === 'AssignmentExpression' && n.left.type === 'Identifier' && n.left.name === b.nombre) {
          base.push(...candidatos(m, n.right, vistos))
        }
      })
    }
    const r = extraer(base, b.ruta.claves, vistos)
    return b.ruta.defecto ? [...r, ...candidatos(m, b.ruta.defecto, vistos)] : r
  }

  function extraer(cands, claves, vistos) {
    let actual = cands
    for (const k of claves) actual = actual.flatMap((c) => miembroDe(c, k, vistos))
    return actual
  }

  // `k` es una clave concreta, o '*' («cualquier elemento/propiedad»: índice no literal, resto).
  function miembroDe(c, k, vistos) {
    if (c.desconocido) return [DESC(c.m, c.n, `${c.desconocido} → .${k}`)]
    if (k === null) return [DESC(c.m, c.n, 'clave computada')]
    const { m, n } = c
    if (n.type === 'ObjectExpression') {
      const out = []
      for (const p of n.properties) {
        if (p.type === 'SpreadElement') { out.push(...extraer(candidatos(m, p.argument, vistos), [k], vistos)); continue }
        const clave = nombreDeClave(p)
        if (clave === undefined) { out.push(DESC(m, p, 'propiedad con clave computada')); continue }
        if (k === '*' || String(clave) === String(k)) out.push(...candidatos(m, p.value, vistos))
      }
      return out
    }
    if (n.type === 'ArrayExpression') {
      if (k === 'length') return []
      const hayResto = n.elements.some((e) => e?.type === 'SpreadElement')
      if (k === '*' || hayResto) return elementos(c, vistos)
      if (typeof k === 'number') {
        const e = n.elements[k]
        return e ? candidatos(m, e, vistos) : []
      }
      return [DESC(m, n, `arreglo.${k}`)]
    }
    return [DESC(m, n, `.${k} de ${n.type}`)]
  }

  function deMiembro(m, n, vistos) {
    const k = !n.computed ? n.property.name : n.property.type === 'Literal' ? n.property.value : '*'
    return candidatos(m, n.object, vistos).flatMap((c) => miembroDe(c, k, vistos))
  }

  function elementos(c, vistos) {
    if (c.desconocido) return [DESC(c.m, c.n, `elemento de ${c.desconocido}`)]
    if (c.n.type !== 'ArrayExpression') return [DESC(c.m, c.n, `elementos de ${c.n.type}`)]
    return c.n.elements.filter(Boolean).flatMap((e) =>
      e.type === 'SpreadElement' ? elementosDeExpr(c.m, e.argument, vistos) : candidatos(c.m, e, vistos))
  }

  // Elementos de una expresión que produce un arreglo; `.sort()`, `.filter()`… no los cambian.
  function elementosDeExpr(m, e, vistos) {
    const x = sinEnvoltura(e)
    if (x.type === 'CallExpression' && MISMOS_ELEMENTOS.has(miembroNombre(x.callee))) {
      return elementosDeExpr(m, sinEnvoltura(x.callee).object, vistos)
    }
    return candidatos(m, x, vistos).flatMap((c) => elementos(c, vistos))
  }

  function nombreDeFuncion(m, fn) {
    if (fn.type === 'FunctionDeclaration') return fn.id?.name ?? null
    const p = m.padres.get(fn)
    return p?.type === 'VariableDeclarator' && p.init === fn && p.id.type === 'Identifier' ? p.id.name : null
  }

  function esExportada(m, fn, nombre) {
    const p = m.padres.get(fn)
    if (p?.type === 'ExportNamedDeclaration' || p?.type === 'ExportDefaultDeclaration') return true
    if (p?.type === 'VariableDeclarator' && m.padres.get(m.padres.get(p))?.type === 'ExportNamedDeclaration') return true
    return m.program.body.some((s) => s.type === 'ExportNamedDeclaration' &&
      (s.specifiers || []).some((sp) => (sp.local.name ?? sp.local.value) === nombre))
  }

  // Una aparición de `nombre` que NO es usarlo como valor: su propia declaración, una clave
  // de objeto, `obj.nombre`, un import/export.
  function esDeclaracion(n, p) {
    if (!p) return false
    if ((p.type === 'VariableDeclarator' || p.type === 'FunctionDeclaration') && p.id === n) return true
    if (p.type === 'Property' && p.key === n && !p.computed && !p.shorthand) return true
    if (p.type === 'MemberExpression' && p.property === n && !p.computed) return true
    return /Specifier$/.test(p.type)
  }

  function deParametro(b, vistos) {
    const { m, nodo: fn, indice, ruta } = b
    const padre = m.padres.get(fn)
    const fuentes = []
    if (padre?.type === 'CallExpression' && padre.arguments.includes(fn) && ITERADORES.has(miembroNombre(padre.callee))) {
      // Callback de un iterador: el primer parámetro es cada elemento del arreglo.
      if (indice === 0) fuentes.push(...elementosDeExpr(m, sinEnvoltura(padre.callee).object, vistos))
      else fuentes.push(DESC(m, fn, `parámetro ${indice} de un ${miembroNombre(padre.callee)}`))
    } else {
      const nombre = nombreDeFuncion(m, fn)
      if (!nombre) return [DESC(m, fn, 'parámetro de un callback: quien lo llama no se ve')]
      recorrer(m.program, (n, p) => {
        if (n.type !== 'Identifier' || n.name !== nombre || esDeclaracion(n, p)) return
        if (p?.type === 'CallExpression' && p.callee === n) {
          const arg = p.arguments[indice]
          if (!arg) return    // sin argumento → undefined (el defecto se suma abajo)
          fuentes.push(...(arg.type === 'SpreadElement' ? [DESC(m, arg, 'argumento con spread')] : candidatos(m, arg, vistos)))
        } else {
          fuentes.push(DESC(m, n, `«${nombre}» se pasa como valor: sus llamadas no se ven`))
        }
      })
      if (esExportada(m, fn, nombre)) fuentes.push(DESC(m, fn, `«${nombre}» se exporta: se puede llamar desde fuera`))
    }
    const r = extraer(fuentes, ruta.claves, vistos)
    return ruta.defecto ? [...r, ...candidatos(m, ruta.defecto, vistos)] : r
  }

  function retornos(m, fn, vistos) {
    if (fn.body.type !== 'BlockStatement') return candidatos(m, fn.body, vistos)
    const out = []
    const visitar = (n) => {
      if (n !== fn && esFuncion(n)) return
      if (n.type === 'ReturnStatement') { if (n.argument) out.push(...candidatos(m, n.argument, vistos)); return }
      hijos(n).forEach(visitar)
    }
    visitar(fn.body)
    return out
  }

  function deLlamada(m, n, vistos) {
    const callee = sinEnvoltura(n.callee)
    if (callee.type === 'Identifier') {
      const b = ligadura(m, callee)
      if (b && esFrontera(b)) {
        // colorMapa(valor, respaldo): `valor` solo pasa si es un color literal que MapLibre
        // entiende. Lo que no se sabe de antemano es el dato; lo que se puede auditar es el respaldo.
        return n.arguments[1] ? candidatos(m, n.arguments[1], vistos) : [DESC(m, n, 'colorMapa sin respaldo')]
      }
    }
    return candidatos(m, callee, vistos).flatMap((c) => {
      if (c.desconocido) return [DESC(m, n, `llamada opaca «${texto(m, callee)}»`)]
      if (!esFuncion(c.n)) return [DESC(m, n, `llamada a un ${c.n.type}`)]
      return conCiclo(`${c.m.nombre}:${c.n.start}:return`, vistos, () => retornos(c.m, c.n, vistos))
    })
  }

  // ── revisión ─────────────────────────────────────────────────────────────────────────────

  function revisar(cands, ctx, vistos) {
    for (const c of cands) {
      const { m, n } = c
      if (c.desconocido) {
        if (ctx.color) reportar(ctx, `origen no demostrable: ${c.desconocido}`, c)
        continue
      }
      switch (n.type) {
        case 'Literal':
          if (typeof n.value === 'string' && n.value.includes('var(')) reportar(ctx, `«${n.value}»`, c)
          break
        case 'TemplateLiteral':
          if (n.quasis.some((q) => (q.value.cooked ?? q.value.raw).includes('var('))) reportar(ctx, 'plantilla con var(', c)
          for (const e of n.expressions) revisar(candidatos(m, e, vistos), ctx, vistos)
          break
        case 'ArrayExpression':
          for (const e of n.elements) {
            if (e) revisar(e.type === 'SpreadElement' ? elementosDeExpr(m, e.argument, vistos) : candidatos(m, e, vistos), ctx, vistos)
          }
          break
        case 'ObjectExpression':
          for (const p of n.properties) revisar(candidatos(m, p.type === 'SpreadElement' ? p.argument : p.value, vistos), ctx, vistos)
          break
        case 'BinaryExpression':
          revisar(candidatos(m, n.left, vistos), ctx, vistos)
          revisar(candidatos(m, n.right, vistos), ctx, vistos)
          break
        case 'UnaryExpression':
          revisar(candidatos(m, n.argument, vistos), ctx, vistos)
          break
        default:
          if (ctx.color) reportar(ctx, `valor ${n.type}`, c)
      }
    }
  }

  function reportar(ctx, motivo, c) {
    ctx.hallazgos.add(`${ctx.capa.archivo}:${ctx.capa.linea} [${ctx.capa.id}] ${ctx.llave} ← ${motivo}` +
      ` (en ${c.m.nombre}:${linea(c.m, c.n)} «${texto(c.m, c.n).slice(0, 70)}»)`)
  }

  function revisarCapa(m, llamada, capas, hallazgos) {
    const donde = { archivo: m.nombre, linea: linea(m, llamada) }
    for (const s of candidatos(m, llamada.arguments[0], new Set())) {
      if (s.desconocido || s.n.type !== 'ObjectExpression') {
        const capa = { ...donde, id: '(capa no literal)', via: 'addLayer' }
        capas.push(capa)
        reportar({ capa, llave: 'capa', hallazgos }, 'la especificación no es un objeto demostrable', s)
        continue
      }
      const idProp = s.n.properties.find((p) => p.type === 'Property' && nombreDeClave(p) === 'id')
      const capa = { ...donde, id: idProp ? texto(s.m, idProp.value) : '(sin id)', via: 'addLayer' }
      capas.push(capa)
      for (const seccion of ['paint', 'layout']) {
        const sec = s.n.properties.find((p) => p.type === 'Property' && nombreDeClave(p) === seccion)
        if (!sec) continue
        for (const obj of candidatos(s.m, sec.value, new Set())) {
          if (obj.desconocido || obj.n.type !== 'ObjectExpression') {
            reportar({ capa, llave: seccion, hallazgos }, `${seccion} no es un objeto demostrable`, obj)
            continue
          }
          for (const q of obj.n.properties) {
            if (q.type === 'SpreadElement') {
              revisar(candidatos(obj.m, q.argument, new Set()), { capa, llave: `${seccion}.…`, color: true, hallazgos }, new Set())
              continue
            }
            const llave = nombreDeClave(q)
            const ctx = { capa, llave: `${seccion}.${llave ?? '[computada]'}`, color: llave == null || LLAVE_COLOR.test(llave), hallazgos }
            revisar(candidatos(obj.m, q.value, new Set()), ctx, new Set())
          }
        }
      }
    }
  }

  function revisarPropiedad(m, llamada, metodo, capas, hallazgos) {
    const [idArg, llaveArg, valorArg] = llamada.arguments
    const capa = { archivo: m.nombre, linea: linea(m, llamada), id: idArg ? texto(m, idArg) : '(sin id)', via: metodo }
    capas.push(capa)
    const llaves = candidatos(m, llaveArg, new Set())
    const color = !llaves.length || llaves.some((c) =>
      c.desconocido || c.n.type !== 'Literal' || typeof c.n.value !== 'string' || LLAVE_COLOR.test(c.n.value))
    const llave = llaveArg ? texto(m, llaveArg) : '(sin propiedad)'
    revisar(candidatos(m, valorArg, new Set()), { capa, llave, color, hallazgos }, new Set())
  }

  /** Recorre los ficheros y devuelve el inventario de capas y los hallazgos (vacío = limpio). */
  function analizar(nombres) {
    const capas = []
    const hallazgos = new Set()
    for (const nombre of nombres) {
      const m = modulo(nombre)
      if (!m) throw new Error(`no existe ${nombre}`)
      recorrer(m.program, (n) => {
        if (n.type !== 'CallExpression') return
        const metodo = miembroNombre(n.callee)
        if (metodo === 'addLayer') revisarCapa(m, n, capas, hallazgos)
        else if (metodo === 'setPaintProperty' || metodo === 'setLayoutProperty') revisarPropiedad(m, n, metodo, capas, hallazgos)
      })
    }
    return { capas, hallazgos: [...hallazgos] }
  }

  return { analizar }
}
