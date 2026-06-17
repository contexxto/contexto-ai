"""
Contexto AI — Curación del entorno por el corredor (el "loop" del Catastro Vivo).

El campo `servicios_cercanos` del catastro se genera por hidratación (OpenStreetMap)
y puede quedar desactualizado: negocios cierran, abren otros. El corredor, que
camina la zona, sabe ANTES que el mapa. Aquí guardamos su curación como un OVERLAY
que se aplica al servir el entorno al agente y al anuncio:

  - acción 'cerrado'  → el servicio se QUITA del texto (ya no existe).
  - acción 'agregado' → se AÑADE un servicio nuevo, marcado "confirmado por el corredor".

Cada curación queda con autor (corredor) + fecha → auditable y base de la insignia
"Entorno verificado por el corredor". El catastro base (texto hidratado) NO se toca:
la curación es una capa encima, reversible.
"""
import re
import unicodedata
from typing import Any

from sqlalchemy import text

# ── Esquema (idempotente, patrón de las tablas de handoff) ───────────────────
_CURACION_DDL = [
    "CREATE TABLE IF NOT EXISTS entorno_curacion ("
    "  id bigserial PRIMARY KEY,"
    "  activo_id uuid NOT NULL,"
    "  accion text NOT NULL,"           # 'cerrado' | 'agregado'
    "  nombre text NOT NULL,"
    "  categoria text,"
    "  distancia_m integer,"
    "  lat double precision,"           # coord. del lugar (capturada por GPS del corredor)
    "  lon double precision,"           # → semilla del grafo de habitabilidad (escalón 2)
    "  foto text,"                       # URL de la foto del lugar (captura ahora, display luego)
    "  corredor_id uuid,"
    "  creado_en timestamptz DEFAULT now())",
    # Para tablas ya creadas en un deploy anterior (idempotente):
    "ALTER TABLE entorno_curacion ADD COLUMN IF NOT EXISTS lat double precision",
    "ALTER TABLE entorno_curacion ADD COLUMN IF NOT EXISTS lon double precision",
    "ALTER TABLE entorno_curacion ADD COLUMN IF NOT EXISTS foto text",
    "CREATE INDEX IF NOT EXISTS ix_entorno_cur_activo ON entorno_curacion (activo_id)",
]
_curacion_ready = False


async def ensure_curacion_table(db) -> None:
    """Crea la tabla de curación si no existe (idempotente, una vez por proceso)."""
    global _curacion_ready
    if _curacion_ready:
        return
    for ddl in _CURACION_DDL:
        await db.execute(text(ddl))
    await db.commit()
    _curacion_ready = True


# ── Parsing / normalización del texto de servicios ──────────────────────────
_SUFIJO_DIST = re.compile(r"\s*a\s*~?\s*[\d.,]+\s*m\.?\s*$", re.I)
_PREFIJO_SIMB = re.compile(r"^[^0-9A-Za-zÁÉÍÓÚÑÜáéíóúñü]+")  # emojis/símbolos iniciales


def _norm(s: str | None) -> str:
    """Normaliza para comparar: sin emoji inicial, sin sufijo de distancia, sin acentos, minúsculas."""
    s = _SUFIJO_DIST.sub("", s or "")
    s = _PREFIJO_SIMB.sub("", s).strip().lower()
    s = "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    return s.strip()


def parse_servicios(texto: str | None) -> list[dict[str, Any]]:
    """Parte el texto '·'-separado en segmentos {visible, distancia_m, raw} para el formulario."""
    out: list[dict[str, Any]] = []
    for seg in [s.strip() for s in (texto or "").split("·") if s.strip()]:
        m = re.search(r"~?\s*([\d.,]+)\s*m\.?\s*$", seg, re.I)
        dist = None
        if m:
            try:
                dist = int(float(m.group(1).replace(",", ".")))
            except ValueError:
                dist = None
        visible = _PREFIJO_SIMB.sub("", _SUFIJO_DIST.sub("", seg)).strip()
        out.append({"visible": visible, "distancia_m": dist, "raw": seg})
    return out


def aplicar_curacion(texto: str | None, curaciones: list[dict[str, Any]]) -> str | None:
    """Aplica el overlay del corredor al texto de servicios_cercanos."""
    if not curaciones:
        return texto
    cerrados = {_norm(c["nombre"]) for c in curaciones if c.get("accion") == "cerrado" and c.get("nombre")}
    agregados = [c for c in curaciones if c.get("accion") == "agregado"]

    segmentos = [s.strip() for s in (texto or "").split("·") if s.strip()]
    vivos: list[str] = []
    for seg in segmentos:
        n = _norm(seg)
        # Quita el segmento si el corredor lo marcó cerrado (igualdad o contención de nombre).
        if any(c and (c == n or c in n or n in c) for c in cerrados):
            continue
        vivos.append(seg)

    for a in agregados:
        nombre = (a.get("nombre") or "").strip()
        if not nombre:
            continue
        dist = a.get("distancia_m")
        dist_txt = f" a ~{int(dist)} m" if dist else ""
        vivos.append(f"{nombre}{dist_txt} (confirmado por el corredor)")

    return " · ".join(vivos) if vivos else None


def info_verificacion(curaciones: list[dict[str, Any]]) -> dict[str, Any]:
    """Para la insignia 'Entorno verificado por el corredor · fecha'."""
    if not curaciones:
        return {"verificado": False, "fecha": None}
    # La más reciente (la lista viene ordenada DESC por creado_en).
    fecha = curaciones[0].get("creado_en")
    return {"verificado": True, "fecha": (fecha or "")[:10] or None}


async def fetch_curaciones(db, activo_id) -> list[dict[str, Any]]:
    """Lee la curación de un activo. Defensiva: si la tabla aún no existe, devuelve []."""
    try:
        rows = (
            await db.execute(
                text("SELECT id, accion, nombre, categoria, distancia_m, foto, "
                     "creado_en::text AS creado_en FROM entorno_curacion "
                     "WHERE activo_id = :a ORDER BY creado_en DESC"),
                {"a": str(activo_id)},
            )
        ).mappings().all()
        return [dict(r) for r in rows]
    except Exception:  # noqa: BLE001 — tabla inexistente todavía / error transitorio
        return []
