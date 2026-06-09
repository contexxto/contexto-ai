# 🛡️ Nota de Seguridad — API Key, Frontend y Abuso de Presupuesto

**Fecha:** 2026-06-09 · **Autor:** Claude (ejecución) · **Para decisión de:** Carlos

Resultado de la auditoría de la sesión de endurecimiento (tarea "API key fuera del bundle").

---

## 1. Hallazgo principal (la buena noticia)

✅ **Los secretos reales NUNCA llegan al navegador.**
Las claves de **Anthropic (Claude)** y **Voyage** viven solo en el backend
(`settings.anthropic_api_key`, `settings.voyage_api_key`) y se usan server-side.
El código del frontend solo referencia dos variables:

```
VITE_API_URL   → URL base del backend (pública por naturaleza)
VITE_API_KEY   → la llave X-API-Key de NUESTRO propio backend
```

Nada de `sk-ant-…` ni la key de Voyage aparece en el código del frontend, así que
**no puede** terminar en el bundle. El punto de la deuda técnica ("API key en el
bundle") era la `VITE_API_KEY`, que es otra cosa (ver abajo).

---

## 2. El matiz real: la `VITE_API_KEY` es pública por diseño

Cualquier variable `VITE_*` queda **incrustada y legible** en el JavaScript que Vite
publica. Es decir: el header `X-API-Key` que el frontend envía para "abrir" el backend
**es visible** para cualquiera que lea el bundle.

Conclusión honesta: ese gate por llave compartida es **seguridad por oscuridad**.
No protege de verdad los endpoints; un script podría leer la llave del bundle y llamar
a `/chat`, `/match`, `/ingest`, etc.

**El riesgo, por tanto, NO es fuga de secretos — es ABUSO DE PRESUPUESTO**
(que alguien queme tu saldo de Claude/Voyage llamando a los endpoints caros).

---

## 3. Lo que YA protege (mitigaciones existentes)

- ✅ **Rate-limiting por IP** (slowapi) en todos los endpoints caros:
  - `chat/send` 15/min · `match` 20/min · `ingest` 20/min · `ingest/batch` 5/min ·
    `similar` 30/min · `vision` 20/min.
- ✅ **Comparación en tiempo constante** de la llave (`secrets.compare_digest`) —
  añadido en esta sesión, evita timing-attacks.
- ✅ Secretos solo en variables de entorno (Render) y `.env` local (gitignored).

Para un MVP pre-ingresos, esto es **razonable**. Un atacante con IPs rotativas aún
podría abusar, pero el costo/beneficio para él es bajo y los límites acotan el daño.

---

## 4. Opciones para el fix definitivo (decisión de producto — tuya)

| Opción | Qué implica | Cuándo |
|---|---|---|
| **A. Dejarlo así (con límites)** | Aceptar el gate público + rate-limits. Cero trabajo. | Mientras sea demo/MVP sin tráfico real. |
| **B. Endurecer límites + alertas** | Bajar cuotas, límite global de respaldo, alerta de gasto en Anthropic/Voyage, CAPTCHA en el primer mensaje. | Antes de difundir la URL públicamente. |
| **C. Auth real de usuarios** | Login (Supabase Auth / JWT), la llave deja de viajar en el bundle; cada usuario tiene token propio y cuota. | Cuando haya cuentas (propietarios B2C / inmobiliarias B2B). Va de la mano con el roadmap Q4 (auth de propietarios). |

**Recomendación:** **A ahora**, planificar **C** junto con el módulo de auth de
propietarios del roadmap (Q4 2026). No vale la pena bolt-on de auth a medias.

> ⚠️ Importante: la `VITE_API_KEY` actual **no es un secreto fuerte**. Si en algún
> momento la usas para algo más sensible, trátala como pública. Y si rotas la
> `api_key` del backend, recuerda actualizar también `VITE_API_KEY` en Vercel.

---

## 5. Qué se cambió en esta sesión

- `app/routers/chat.py` → `verify_api_key` ahora compara en **tiempo constante**.
- `tests/test_auth.py` → cubre dev-sin-llave, llave correcta y 401 por llave inválida/ausente.
- Esta nota.

Sin cambios de arquitectura ni de auth (eso queda a tu decisión, opciones arriba).
