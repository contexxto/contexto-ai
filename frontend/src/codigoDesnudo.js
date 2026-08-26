/**
 * Devuelve el fuente con los COMENTARIOS borrados, conservando la posición de todo lo demás.
 *
 * Existe porque en esta unidad tres tests míos afirmaron sobre TEXTO donde debían afirmar
 * sobre ESTRUCTURA, y los tres dieron un verde falso: SQL con espacios de alineación, un
 * `COALESCE` que vivía dentro de un comentario, y un JSDoc entre dos funciones. Un `grep`
 * sobre el fuente crudo no distingue "el código hace X" de "un comentario menciona X" — y
 * en un gate de seguridad esa diferencia es justamente la que importa. Este fichero está
 * densamente comentado; sin esto, cualquier aserción sobre él sería teatro.
 *
 * Los rangos los da **oxc**, el parser que Vite ya usa para compilar este mismo fichero.
 * No es un tokenizador propio: la primera versión de este helper sí lo era, y se comía el
 * 92 % del fuente en cuanto encontraba una plantilla anidada. Un parser de verdad estaba a
 * un import de distancia — y la lección es la misma que motiva el helper.
 *
 * Se sustituye por espacios en vez de recortar, para que los desplazamientos, los números
 * de línea y las líneas de código sigan siendo los del fichero real.
 */
import { parseSync } from 'vite'

export function codigoDesnudo(fuente, nombre = 'App.jsx') {
  const { comments, errors } = parseSync(nombre, fuente, { sourceType: 'module' })

  // Si el fichero no parsea, cualquier aserción posterior sería sobre un fuente a medias:
  // el verde no significaría nada. Mejor romper aquí y decir por qué.
  if (errors?.length) {
    throw new Error(`${nombre} no parsea (${errors.length}): ${errors[0]?.message ?? ''}`)
  }

  const caracteres = [...fuente]
  for (const c of comments) {
    for (let i = c.start; i < c.end; i++) {
      if (caracteres[i] !== '\n') caracteres[i] = ' '
    }
  }
  return caracteres.join('')
}
