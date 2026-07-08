# Contexto · Design System

Fundación visual para el rediseño total (app + web) en el lenguaje de **ASI:One**,
con la **marca teal** de Contexto. Los valores oscuros salen de inspeccionar
`asi1.ai` con DevTools; los claros están inspirados en los promos blancos de ASI.

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
| `--text-dim` | `#8C8C8C` | `#A1A1AA` | Texto terciario / placeholder |
| `--accent` | `#2DBDB6` | `#14A79F` | Links / títulos de acento |

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
- **Chip:** `background: var(--surface-2)`, `border: 1px var(--border)`, texto `var(--text)`, ícono `var(--text-mid)`, radio 10, hover → `var(--surface-3)`.
- **Card:** `background: var(--surface-1/2)`, `border: 1px var(--border)`, radio 13–16.
- **Input/dock:** `background: var(--surface-1)`, `border: 1px var(--border)`, radio 16, placeholder `var(--text-dim)`.
- **Nav item:** texto `var(--text-mid)`, hover bg `var(--surface-2)` + texto `var(--text)`, radio 8.
- **Bottom sheet:** `background: var(--surface-1)`, `border-top: 1px var(--border)`, radio superior 18, scrim `rgba(5,5,7,.62)`.

## 5. Estado de migración a tokens

| Pantalla / componente | Estado |
|---|---|
| Launcher (`Launcher.jsx`) | ✅ tokens (dark+light) |
| Dock / header (`App.jsx`) | ✅ tokens |
| Hoja Adjuntar (`AttachSheet.jsx`) | ✅ tokens |
| Menú (`Sidebar.jsx`) | ✅ tokens |
| Chat / mensajes (bubbles · ResultCards · DeltaEncaje) | ✅ tokens (dark+light) |
| CRM / Análisis | ⏳ migrar |
| Mapa Vivo | ⏳ migrar |
| Anuncio `/a/{id}` · Auth · Publicar | ⏳ migrar |

> El **shell** (launcher, dock, menú, hoja) ya responde al tema. El modo claro
> se completa a medida que cada pantalla migra a tokens (siguientes PRs).
