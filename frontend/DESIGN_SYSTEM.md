# Contexto · Design System

Fundación visual para el rediseño total (app + web) en el lenguaje de **ASI:One**,
con la **marca teal** de Contexto. Los valores oscuros salen de inspeccionar
`asi1.ai` con DevTools; los claros están inspirados en los promos blancos de ASI.

> **Dos referencias, no una (2026-09-20).** ASI:One sigue siendo la referencia del *shell*
> (tokens, dock, menú, chat). La **pantalla inicial vacía** sigue otra: el inicio de
> **Comet** — marca con aire, cuatro entradas a ancho completo que dicen qué va a pasar, y
> el campo de escribir. Se llegó ahí tras dos vueltas aplicando ASI:One a la home por leer
> solo este documento: antes de rediseñar la home, mira `Launcher.jsx`, no asi1.ai.

> **Regla de oro:** ningún componente hardcodea colores. Todo usa **tokens**
> (`var(--…)`) para que el tema oscuro/claro cambie solo.

---

## 1. Temas (tokens)

Definidos en `src/index.css`. El tema vive en `<html data-theme="dark|light">`;
el default es **dark**. Init anti-flash en `index.html`; toggle en `src/theme.js`
(`getTheme` / `setTheme` / `toggleTheme`), cableado en el menú ("Modo claro").

| Token | Oscuro (ASI real) | Claro | Uso |
|---|---|---|---|
| `--bg` | `#1C1C1C` | `#FFFFFF` | Fondo de página |
| `--surface-1` / `--surface` | `#282828` | `#F4F4F5` | Dock, tarjetas, botón discreto |
| `--surface-2` | `#2E2E2E` | `#EFEFF1` | Chips |
| `--surface-3` | `#3A3A3A` | `#E7E7EA` | Hover |
| `--border` | `#404040` | `#E4E4E7` | Bordes/divisores |
| `--text` | `#FFFFFF` | `#09090B` | Texto principal |
| `--text-mid` / `--text-muted` | `#C9C9C9` | `#52525B` | Texto secundario |
| `--text-dim` | `#959595` | `#676772` | Texto terciario / placeholder (AA: 5.69:1 / 5.59:1 sobre `--bg`) |
| `--accent` | `#2DBDB6` | `#1C746F` | Links / títulos de acento (claro 5.56:1) |
| `--home-row-bg` / `-border` / `-hover` | blanco al 7 % / 8,5 % / 11 % | tinta al 4 % / 8 % / 7 % | Solo la home vacía: filas del Launcher y botones redondos del header |

**Constantes (ambos temas):** marca teal (`--teal #2DBDB6`, `--teal-bright #5EEAD4`,
`--teal-deep #1A7A76`), coral (`--coral #E0685A`), semánticos
(`--success`, `--warning`, `--danger`, `--info`).

> El **teal es la marca** — reemplaza el verde `#85F47C` de ASI. Se reserva
> para **acciones** (CTA, Voz, Enviar, "Registrarse"), no se dispersa.

---

## 2. Tipografía

- Familia: **Geist** (la de ASI/Vercel) vía Google Fonts → `--font-display` / `--font-body`.
- Mono: IBM Plex Mono → `--font-mono`.
- Escala de referencia (móvil): título `1.55rem/700`, subtítulo `1rem`, cuerpo `.92–.95rem`,
  chip `.83rem/500`, label `.68rem` uppercase.
- Letter-spacing en titulares: `-.02em`.

## 3. Radios · Espaciado · Motion

- Radios: `--radius-sm 8` · `--radius-md 12` · `--radius-lg 16` · `--radius-xl 22` · `--radius-pill 999`.
  Ventanas (chips/cards) **rectangulares**: 10–14px. Pills (Voz/Enviar): 999.
- Sombras: `--shadow-sm/md/lg` (suaves en claro, marcadas en oscuro).
- Motion: `--ease` + `--dur-fast 150` / `--dur 250` / `--dur-slow 400`.

## 4. Componentes base (recetas)

- **Botón primario (acción):** `background: var(--teal-bright)`, texto `#06201C`, `700`, radio 12, pill si es circular.
- **Botón secundario/discreto:** `background: var(--surface-1)`, `border: 1px var(--border)`, texto `var(--text)`.
- **Botón contorno:** `background: transparent`, `border: 1px var(--border)`, texto `var(--text)`.
- **Fila de la home:** `background: var(--home-row-bg)`, `border: 1px var(--home-row-border)`, radio 14, padding `10 16`, texto `var(--text)` `.92rem/400` línea 1.25, flecha `arrow-down-left` 18 en `var(--text-dim)`, hover → `var(--home-row-hover)`. 40 px una línea, 58 dos. La línea es decorativa (≈1.3:1): el control se identifica por su texto (≥ 12:1) y por la flecha (≥ 4.1:1 en hover oscuro; es un gráfico, umbral 3:1). No poner texto en `--text-dim` dentro de la fila. No reutiliza `--map-*` (esa familia no tiene tema claro).
- **Botón redondo de la home:** 44 × 44, radio 50 %, mismos `--home-row-bg` / `--home-row-border`. Solo con el chat vacío.
- **Chip:** `background: var(--surface-2)`, `border: 1px var(--border)`, texto `var(--text)`, ícono `var(--text-mid)`, radio 10, hover → `var(--surface-3)`.
- **Card:** `background: var(--surface-1/2)`, `border: 1px var(--border)`, radio 13–16.
- **Input/dock:** `background: var(--surface-1)`, `border: 1px var(--border)`, radio 16, placeholder `var(--text-dim)`.
- **Nav item:** texto `var(--text-mid)`, hover bg `var(--surface-2)` + texto `var(--text)`, radio 8.
- **Bottom sheet:** `background: var(--surface-1)`, `border-top: 1px var(--border)`, radio superior 18, scrim `rgba(5,5,7,.62)`.

## 5. Estado de migración a tokens

| Pantalla / componente | Estado |
|---|---|
| Launcher (`Launcher.jsx`) | ✅ tokens (dark+light) · 2026-09-20: dirección Comet, logotipo vertical, cuatro entradas por id (`HOME`), centrado que nunca provoca scroll |
| Dock / header (`App.jsx`) | ✅ tokens |
| Hoja Adjuntar (`AttachSheet.jsx`) | ✅ tokens |
| Menú (`Sidebar.jsx`) | ✅ tokens |
| Chat / mensajes (bubbles · ResultCards · DeltaEncaje) | ✅ tokens (dark+light) |
| CRM / Análisis | ⏳ migrar |
| Mapa Vivo | ⏳ migrar |
| Anuncio `/a/{id}` · Auth · Publicar | ⏳ migrar |

> El **shell** (launcher, dock, menú, hoja) ya responde al tema. El modo claro
> se completa a medida que cada pantalla migra a tokens (siguientes PRs).

## 6. Logotipo

- **Maestro:** `src/LogoContexto.jsx` (generado desde `docs/branding/logo/`). Contornos puros, sin
  fuente. Isotipo en retícula de 13 módulos (lado 6, calle 1, radio 1,35, círculo +4 %);
  «CONTEXTO» en caja alta geométrica con la E de tres barras; hereda `currentColor`.
- **Versión vertical** (la principal): logotipo al doble de ancho que el isotipo, 2 módulos de
  separación. Es la de la pantalla inicial (isotipo 76 px en móvil, 88 en escritorio).
- **Tamaño pequeño:** por debajo de 48 px se usa `assets/sphere.svg` (calle más ancha, 24 px).
  Es el mismo signo con corrección de tamaño, no otro logo.
- **Mínimos:** logotipo ≥ 96 px de ancho (asta ≈ 1 px); área de respeto = medio lado del isotipo.
  La versión horizontal exige isotipo ≥ 48 px (palabra ≥ 147 px): el header de la app, a 26–30 px,
  sigue con `sphere.svg` y el nombre en texto.
- **Deuda heredada:** en cada tema, dos de las cuatro formas quedan a ≈1.5:1 del fondo (la pizarra
  en oscuro, el teal en claro). Son los mismos colores que `sphere.svg` ya tenía en producción; a
  76–88 px se nota más. Si se corrige, que sea con tokens por tema desde el generador.

