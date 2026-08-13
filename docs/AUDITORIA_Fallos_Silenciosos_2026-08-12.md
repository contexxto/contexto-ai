# Auditoría — la cadena de avisos (2026-08-12)

Sesión de depuración sobre el handoff y las notificaciones. **Catorce defectos**, encontrados
tirando de un solo hilo: *"cuando actualizo la app, desaparece el cuadradito de arriba"*.

Continuación directa de [AUDITORIA_Fallos_Silenciosos_2026-07-31.md](AUDITORIA_Fallos_Silenciosos_2026-07-31.md).
Aquella auditó los `except: pass` del código; esta documenta lo que pasa cuando esos fallos
silenciosos llegan a producción y hay que cazarlos desde fuera.

> **Por qué importa:** doce de los catorce fallaban **en silencio**. Ni error, ni log visible,
> ni métrica movida. El handoff se perdía y el usuario leía "un corredor te contactará". El
> corredor no podía responder y veía "revisa tu conexión". El push llevaba días muerto y el
> diagnóstico decía que todo estaba bien. **Un fallo que no se anuncia no se arregla: se
> normaliza.**

---

## El patrón que se repitió

Tres formas del mismo defecto, y conviene reconocerlas antes que la lista:

**1. La guarda que asume un formato.** Cinco defectos distintos venían de la misma línea
conceptual:

```python
if not session_id.startswith("qr-"):
    return
```

El inmueble se deducía del *formato del identificador de sesión*. Toda conversación que no
naciera de un QR —el camino mayoritario hoy— caía fuera: sin corredor a quien avisar, sin
registro en el CRM, sin actividad, sin poder responder. Cada uno se manifestaba distinto, así
que se descubrieron de uno en uno.

**2. El `catch` ciego.** El error se atrapa y se sustituye por un mensaje genérico. "No se pudo
conectar con el corredor" ocultó durante días un `401` de sesión caducada y un `500` por una
columna inexistente. Un `catch` que no dice *qué* falló convierte un bug de diez minutos en uno
de tres días.

**3. El instrumento que miente.** El peor. Mi propio diagnóstico comprobaba
`bool(VAPID_PRIVATE_KEY)` —que la variable *existiera*— y decía "todo bien" mientras cada envío
fallaba. La línea de salud del CRM también desaparecía cuando el diagnóstico no respondía, de
modo que **la ausencia de alarma podía significar "todo bien" o "no pude mirar"**. Leí ese
silencio como un sí, y me costó una ronda entera.

---

## Los catorce

### El handoff se perdía en el pico de intención

| # | Defecto | Cómo se detectó | Commit |
|---|---|---|---|
| 1 | El lead que pedía corredor sin venir de QR quedaba con `activo_id` nulo: **nadie era notificado y no aparecía en ningún CRM**. El agente le decía igual que ya lo estaban atendiendo. | Leyendo `activo_de_session()` tras ver la captura donde el agente prometía algo que no había ocurrido | `3112506` |
| 2 | El corredor **no podía leer ni responder** a esos leads: dos endpoints validaban la pertenencia por el prefijo `qr-` y devolvían 403 | El panel decía "Sin mensajes todavía" con la ficha marcando 3 mensajes | `5818b37` |
| 3 | `responder_lead` consultaba `SELECT direccion`, **columna que no existe** (es `direccion_estandarizada`). El endpoint entero caía con 500 y el mensaje ni se guardaba | Mismo error me había roto un script de diagnóstico horas antes | `7c50c85` |
| 4 | El aviso al interesado apuntaba a `/a/{inmueble}`, que **crea una sesión distinta**: tocaba la notificación y aterrizaba en un chat vacío | Rastreando qué session_id reconstruye esa ruta | `c579539` |
| 5 | El sondeo de respuestas exigía `modoCorredor`, que solo se activaba… desde el propio sondeo. **Candado circular**: al recargar, el interesado no volvía a ver nunca los mensajes del corredor | Leyendo el efecto tras el defecto #4 | `c579539` |
| 6 | La conversación con el corredor **desaparecía al recargar**: `/history` solo trae lo hablado con el agente. El flujo de QR sí la restauraba; el normal, no | Reporte directo: "se borró la conversación" | `852dec8` |

### La sesión y el estado

| # | Defecto | Cómo se detectó | Commit |
|---|---|---|---|
| 7 | **El token caducaba y TODO fallaba en silencio.** La UI seguía mostrando la sesión iniciada mientras cada llamada devolvía 401 | Una tanda de 401 en los logs de Render, uno por minuto durante 12 minutos | `b551e21` |
| 8 | Las conversaciones sin QR **no registraban actividad**: el CRM marcaba "0 Activos" con una conversación en vivo, y la recencia del orden no se activaba | Auditando la prueba de punta a punta en la base | `7fd5714` |
| 9 | El `repr` de Python se colaba en la pantalla del usuario (`[{'text': '…', 'type': 'text'}]`) en el chat, en la conversación **pública** compartida y en los títulos | Captura del interesado | `d89b1c6`, revertido por error en `70c1967` y restaurado en `8af9198` — ver "Lo que costó no medir" |

### Las notificaciones

| # | Defecto | Cómo se detectó | Commit |
|---|---|---|---|
| 10 | `push_usuario` tenía `user_id` como clave primaria: **una sola suscripción por corredor**. Cada aparato nuevo pisaba al anterior | Rastreando por qué llegaba el correo y no el push | `e311abd` |
| 11 | Las tareas de aviso podían **perderse a medio ejecutar**: `asyncio` solo guarda una referencia débil de las lanzadas con `create_task` | Revisión del patrón fire-and-forget | `bbfbc38` |
| 12 | El remitente era `onboarding@resend.dev`, el **sandbox de Resend, que solo entrega al dueño de la cuenta**. Los interesados nunca recibieron un correo | Mirando la cabecera del correo que sí llegaba | `87d680c` (aviso) |
| 13 | La campana devolvía **HTTP 500**: con el parámetro en NULL, Postgres no puede deducir su tipo en `:u IS NOT NULL` | Llamando al endpoint directamente en producción | `852dec8` |
| 14 | **El push nunca funcionó.** No era la clave: era que le pasábamos el PEM como *cadena* a `pywebpush`, que documenta `Vapid instance or path to PEM` — y una cadena la interpreta como **ruta de archivo** | La radiografía de la clave devolvió `carga=ok`, lo que descartó la hipótesis en la que llevábamos dos intentos | `f077d45` |

---

## Lo que costó no medir

Tres errores míos, por si sirven de vacuna:

**Reverti código sano.** Culpé a un cambio mío de que el CRM cayera de 16 interesados a 3.
La causa real era que yo había agotado el pool de conexiones de Supabase con mis propios
scripts de diagnóstico: sin conexiones, `intencion_de_sesion` fallaba y `_leads_de_activo`
**descarta al lead que no puede leer**. Correlacioné "cambié algo" con "algo se rompió" sin
medir. El error estaba en mi propia salida, a la vista: `max clients reached`.

**Mandé a rotar una clave válida, dos veces.** El mensaje `Could not deserialize key data`
apunta a la clave, y lo leí como "la clave está mal" en vez de "algo está interpretando mal la
clave". Dos rondas de instrucciones que Carlos no tenía que ejecutar. La radiografía —cinco
números, ningún secreto— debió ser el primer paso, no el quinto.

**Di por arreglado con una medición mala.** La sonda medía el `<textarea>` y decía "ok"
mientras la fila de botones de abajo seguía cortada. Medir el elemento equivocado es peor que
no medir: da una falsa confirmación.

---

## Lo que queda instalado

No son parches, es instrumentación permanente:

- **`GET /api/v1/chat/diagnostico/notificaciones`** — qué canales están configurados, en
  booleanos, sin exponer claves. Incluye `vapid_forma`: longitudes y cabeceras, para saber
  *dónde* se rompe una clave sin verla.
- **`POST /api/v1/chat/diagnostico/push-prueba`** — envía un push real y **devuelve el error
  exacto** por dispositivo. Convierte "no me llega" en un dato, en un clic.
- **Línea de salud en el CRM** — solo aparece cuando algo está roto, y dice qué.
- **Errores con código HTTP** en el frontend, en vez de "revisa tu conexión".

---

## Regla que sale de aquí

> **Antes de proponer un remedio, mide la forma del dato.**
> Y si el instrumento no puede mirar, que lo diga — un diagnóstico que calla cuando falla
> es indistinguible de uno que aprueba, y eso es peor que no tenerlo.

Corolario para el código: comprobar que algo *existe* no es comprobar que *sirve*. La clave
VAPID estaba puesta y era ilegible; el remitente estaba configurado y no entregaba; la
variable de sesión existía y estaba caducada.
