"""Los proveedores de Place: cada capacidad detras de su propio modulo (PLAN04-2.2).

Aqui vive SOLO lo que los dos proveedores comparten de verdad, y no se importa ningun
submodulo desde este `__init__`: si lo hiciera, `propia` y `google` no podrian importar de
su propio paquete sin cerrar un ciclo.

QUE COMPARTEN, Y POR QUE NO ES CASUALIDAD. La heuristica de MARCA ANCLA —una marca
reconocible gana si esta a no mas del margen— la aplican los dos, cada uno sobre SUS
candidatos. Describe como elige una persona, no como responde un proveedor. Dejarla en
`rutas.py` habria obligado a los providers a importar del modulo del que estan saliendo;
duplicarla habria dejado dos reglas divergiendo sin que nadie se entere. Vive aqui, en el
unico sitio que los dos pueden ver.

LO QUE ESTE PAQUETE NO ES. No hay interfaz comun ni selector: eso es otra unidad, y esta
no lo abre. Nominatim y Overpass siguen fuera; su extraccion no esta autorizada todavia.
"""

from __future__ import annotations

# Marcas reconocibles (LATAM): se prefieren como destino aunque un genérico esté un poco más cerca.
_MARCAS_ANCLA = (
    "tuti", "supermaxi", "megamaxi", "santa maría", "santa maria", "mi comisariato",
    "akí", "aki", "gran akí", "tía", "tia", "coral",                       # supermercados
    "fybeca", "sana sana", "pharmacys", "medicity", "cruz azul", "difare",  # farmacias
    "quicentro", "el recreo", "scala", "san luis", "el condado", "granados",
    "el bosque", "paseo san francisco", "ventura", "el jardín", "el jardin",  # centros comerciales
)

_MARGEN_MARCA_M = 350  # una marca gana si está a ≤ (más cercano + este margen)


def _es_marca(nombre: str | None) -> bool:
    n = (nombre or "").lower()
    return any(m in n for m in _MARCAS_ANCLA)
