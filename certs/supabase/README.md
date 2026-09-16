# Ancla de confianza de Supabase — bundle versionado

Este directorio guarda la **CA raíz** contra la que la conexión a Postgres verificará la identidad
del servidor cuando se active `verify-full`.

**Hoy `verify-full` NO está activo.** Esta unidad (`R2B2`) sólo coloca el fichero en el repositorio
y en la imagen. El comportamiento TLS de producción **no cambia**: sigue siendo el default de los
drivers. Activarlo es una unidad posterior.

## Qué hay aquí

| archivo | qué es |
|---|---|
| `bundle-v1.pem` | El bundle vigente. **Una** CA: `Supabase Root 2021 CA`. |
| `bundle-v1.manifest.json` | Procedencia y huellas **congeladas**. Es el oráculo de las pruebas. |
| `README.md` | Esto. |

**Ruta de runtime dentro de la imagen:** `/app/certs/supabase-ca-bundle.pem`
(`Dockerfile`, `COPY` propio y explícito). El bundle está **versionado** para poder rotar; la ruta
de destino es **estable** para que el código apunte siempre al mismo sitio. Una rotación cambia el
origen del `COPY`, no el consumidor.

## Esto NO es un secreto

Es una **CA pública**: material de confianza, no una credencial. Se versiona precisamente para que
un cambio pase por PR y quede auditable. No lleva clave privada, y una prueba lo comprueba.

## El fingerprint canónico es el del DER

**`SHA-256` de los bytes DER del certificado.** No el del texto PEM. Este mismo certificado lo
demuestra:

El PEM admite cambios de cabecera, orden, saltos de línea y comentarios que alteran su hash **sin
cambiar el certificado** — y al revés, reordenar un bundle daría un falso "cambió". El DER es la
codificación del certificado en sí.

Y no es teórico: **este archivo ya cambia de hash según el sistema operativo.** Git lo guarda con
`LF` y lo entrega con `CRLF` en un checkout de Windows, así que el hash del archivo depende de
dónde lo mires. El del DER no se mueve:

```
                      sha256(archivo)       sha256(DER)
checkout Linux (LF)   700723581420dd1a…     807025ad…cafa
checkout Windows      1dcaafbf6fda7f21…     807025ad…cafa      ← el mismo certificado
```

Por eso el fingerprint fijado en `tests/test_ca_bundle_supabase.py` es el del DER: uno del PEM
daría rojo en media plantilla sin que nadie hubiera tocado el certificado.

## Procedencia — única fuente autorizada

**Supabase Dashboard → proyecto `contexto-ai` → Database Settings → SSL Configuration →
Download Certificate.**

Nombre original: `prod-ca-2021.crt`. Adquirido el **2026-09-16T18:36:55Z**.

**Nunca** sustituir por: un certificado encontrado buscando en internet, una copia de otro proyecto,
el trust store del sistema, `certifi`, un certificado reconstruido desde una sesión TLS, ni un
archivo histórico sin revalidar contra el panel. Si el panel no puede entregarlo de forma
inequívoca, **parar y pedirlo**; no buscar sustituto.

## Caducidad: reverificar, no confiar en la fecha

`not_after` es **2031-04-26**. Eso es la **expiración del ancla**, no un compromiso del proveedor de
no rotarla antes. Antes de apoyarse en esa fecha, reverificar contra el panel.

---

# Runbook de rotación

## Estado normal

El bundle vigente está versionado, su manifiesto congela las huellas, y `verify-full` valida contra
él. Nada que hacer.

## Rotación — diez pasos, en orden

1. **Obtener la CA nueva únicamente de la fuente oficial** (el panel del proyecto). No de un aviso,
   un blog ni un correo.
2. **Verificar y registrar su `SHA-256` del DER.** Si no coincide con lo que el proveedor publica,
   parar.
3. **Crear la versión siguiente del bundle con `OLD + NEW`**, ambas CA. El solape es el punto: durante
   la transición el servidor puede presentar cadenas de cualquiera de las dos, y el cliente debe
   confiar en ambas. Un bundle de una sola CA convierte la rotación en una ventana de caída.
4. **Actualizar el manifiesto**: nueva versión, `certificate_count`, y una entrada por certificado.
5. **CI.**
6. **Deploy bundle-only** — sin tocar la política TLS.
7. **Verificar los DOS fingerprints dentro de la imagen** desplegada.
8. **Sólo entonces** continuar operando con `verify-full`.
9. **Retirar `OLD` únicamente cuando exista evidencia de que la transición del proveedor terminó** —
   evidencia, no calendario.
10. **Crear la versión siguiente sin `OLD`.**

## Dos prohibiciones

**Nunca retirar una CA porque "ya debe haber expirado".** Reverificar contra el proveedor y contra lo
que el servidor presenta de verdad. Una expiración supuesta que resulta falsa deja el bundle sin el
ancla que el servidor sigue usando.

**Nunca descargar certificados durante el build de Docker.** Mete una dependencia de red en el build
y convierte un fallo del proveedor en un build roto — además de abrir la puerta a que la imagen
cambie sin que cambie el repositorio.

---

# Para la unidad siguiente (no es parte de ésta)

**El bundle no tiene todavía ningún consumidor.** Nada en `app/` lo lee. Activar `verify-full`
es otra unidad, y su primer paso es desplegar **este** commit para que el archivo ya esté en la
imagen antes de que algo lo apunte.

Dos cosas medidas que conviene no re-descubrir a golpes:

**Las dos rutas fallan distinto ante un ancla mal puesta.** `AsyncConnectionPool.__init__`
guarda sus `kwargs` **sin validarlos**: una ruta de CA equivocada no da error al construir el
pool, sino en el primer checkout — ya en caliente, y por tanto en producción. asyncpg, en
cambio, falla al construir. Por eso `test_ca_bundle_supabase.py` fija el conjunto de `kwargs`
del pool por análisis estático: es la única comprobación que muerde antes de arrancar.

**Las guardas G3 y G4 deben limitarse al runtime de aplicación/checkpointer**, o trabajar con
una allowlist explícita de los clientes ya censados. Una guarda global convertiría en ilegales
los scripts `psycopg` legítimos que siguen pendientes de endurecer (`scripts/`, `evals/`) — los
rompería sin arreglar nada, que es el modo en que un control de seguridad acaba desactivado.
Y `#137` no se cierra con asyncpg + checkpointer en `verify-full`: el censo completo es parte
del cierre.
