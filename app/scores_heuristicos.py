"""
Capa base HEURÍSTICA de scores de habitabilidad por sector de Quito (backend).

Versión compacta del script scripts/scores_heuristicos.py, para asignar scores
cuando un propietario/corredor publica un inmueble sin datos medidos. Es una
hipótesis inicial; se refina luego con la IA de visión.
"""
import hashlib
import unicodedata

_SECTORES = {
    "La Carolina":     {"ruido": "MEDIO", "walk": 91, "veg": 28, "traf": 9000},
    "La Mariscal":     {"ruido": "ALTO",  "walk": 95, "veg": 13, "traf": 18000},
    "González Suárez": {"ruido": "ALTO",  "walk": 77, "veg": 12, "traf": 20000},
    "Cumbayá":         {"ruido": "BAJO",  "walk": 52, "veg": 58, "traf": 3500},
    "El Condado":      {"ruido": "BAJO",  "walk": 66, "veg": 36, "traf": 3000},
    "Cotocollao":      {"ruido": "MEDIO", "walk": 64, "veg": 30, "traf": 9000},
    "El Batán":        {"ruido": "MEDIO", "walk": 61, "veg": 40, "traf": 5000},
}
_DEFAULT = {"ruido": "MEDIO", "walk": 70, "veg": 30, "traf": 6000}
_KEYWORDS = {
    "la carolina": "La Carolina", "carolina": "La Carolina", "republica del salvador": "La Carolina",
    "shyris": "La Carolina", "naciones unidas": "La Carolina", "amazonas": "La Carolina",
    "la mariscal": "La Mariscal", "mariscal": "La Mariscal", "12 de octubre": "La Mariscal", "colon": "La Mariscal",
    "gonzalez suarez": "González Suárez", "cumbaya": "Cumbayá", "pampite": "Cumbayá", "interoceanica": "Cumbayá",
    "el condado": "El Condado", "condado": "El Condado", "cotocollao": "Cotocollao", "la prensa": "Cotocollao",
    "el batan": "El Batán", "batan": "El Batán",
}
_RUIDO_ORDEN = ["BAJO", "MEDIO", "ALTO"]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def detectar_sector(direccion: str) -> str | None:
    n = _norm(direccion)
    for kw, sector in _KEYWORDS.items():
        if kw in n:
            return sector
    return None


def _jitter(seed: str, span: int) -> int:
    h = int(hashlib.sha256(_norm(seed).encode("utf-8")).hexdigest(), 16)
    return (h % (2 * span + 1)) - span


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def scores_para(direccion: str, tipo_activo: str = "Departamento") -> dict:
    """Scores heurísticos (capa base) para una dirección. Determinístico."""
    base = _SECTORES.get(detectar_sector(direccion), _DEFAULT)
    walk = _clamp(base["walk"] + _jitter(direccion + "w", 4), 0, 100)
    veg = _clamp(base["veg"] + _jitter(direccion + "v", 6), 0, 100)
    ruido = base["ruido"]
    if _norm(tipo_activo) in ("local", "local comercial", "comercial"):
        ruido = _RUIDO_ORDEN[min(_RUIDO_ORDEN.index(ruido) + 1, len(_RUIDO_ORDEN) - 1)]
    return {
        "score_ruido_predictivo": ruido,
        "walk_score": walk,
        "porcentaje_cobertura_vegetal": float(veg),
    }
