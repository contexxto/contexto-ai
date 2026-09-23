"""Valhalla como proveedor: isocronas peatonales del motor propio (PLAN04-2.2).

Valhalla es NUESTRO. Corre auto-hospedado —Docker en local, servicio privado en Render— con
los tiles de Ecuador, y por eso podemos GUARDAR sus isocronas: el TOS de Google lo prohibe,
la ODbL de OpenStreetMap no. Es el unico proveedor del Place Graph que no es de un tercero,
y aun asi se le trata igual que a los demas: detras de la frontera, sin que quien lo llama
tenga que saber donde vive.

QUE HACE ESTE MODULO, DICHO CON PRECISION. No es "I/O puro". `isocrona` hace dos cosas: pide
el poligono y TRADUCE la respuesta de Valhalla —`features[].properties.contour` y
`features[].geometry`— al vocabulario de Contexto, `{minutos, geometry}`. Traducir la forma
de un proveedor es trabajo del proveedor; calcular sobre ella no. Por eso viaja el parseo y
NO viaja nada de lo que hace `app/isocronas.py` con el resultado.

LO QUE SE QUEDO FUERA, Y NO POR OLVIDO. El upsert sobre `isocronas_inmueble` y la CUNA
—el cruce por `ST_Contains` contra el inventario fijo— siguen en `app/isocronas.py`.
Este modulo no importa SQLAlchemy, no recibe conexiones y no sabe que existe una base de
datos. Medido antes y despues: `isocrona` = 1 llamada a Valhalla y CERO operaciones de
base.

(Los nombres de esas dos funciones se omiten a proposito: una guarda del baseline busca
uno de ellos por substring en `app/` para demostrar que no tiene consumidores, y citarlo
aqui la volveria un falso positivo. Se cambia este texto, nunca la guarda.)

EL NOMBRE DEL LOGGER ES DELIBERADO Y NO ES `__name__`. Se conserva `"app.isocronas"` aunque
el codigo viva ahora aqui. `logging.getLogger(__name__)` habria cambiado la etiqueta a
`app.place.providers.valhalla` como efecto colateral del movimiento, y cualquier filtro de
logs del operador apuntando al nombre viejo habria dejado de ver las caidas de Valhalla sin
que nadie lo decidiera. Un refactor no puede cambiar en silencio lo que ve quien opera.

DEGRADACION, TAL CUAL ESTABA: cualquier fallo devuelve `None`, nunca propaga, y los fallos
de TRANSPORTE dejan un WARNING. Los de CONTENIDO —200 con features inservibles— devuelven
`None` sin registrar nada; es una asimetria real, medida en R0B1C0, congelada aqui y
reportada como deuda. Corregirla no cabe en una extraccion.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

# El nombre se escribe a mano a proposito. Ver el docstring: `__name__` cambiaria la
# etiqueta de los avisos operativos como efecto colateral de haber movido el fichero.
logger = logging.getLogger("app.isocronas")

_TIMEOUT = 20.0
_CONTORNOS_DEFECTO = (15, 30)  # minutos


async def isocrona(lat: float, lon: float, minutos=_CONTORNOS_DEFECTO) -> list[dict] | None:
    """Isócrona peatonal de un punto. Devuelve [{minutos:int, geometry:GeoJSON}] o None.

    Un solo request cubre todos los contornos. polygons=true → polígonos cerrados
    aptos para point-in-polygon; denoise limpia islas sueltas; generalize simplifica.
    """
    body = {
        "locations": [{"lat": lat, "lon": lon}],
        "costing": "pedestrian",
        "contours": [{"time": int(m)} for m in minutos],
        "polygons": True,
        "denoise": 0.5,
        "generalize": 50,
    }
    verify = settings.ssl_verify.lower() != "false"
    try:
        async with httpx.AsyncClient(verify=verify, timeout=_TIMEOUT) as c:
            r = await c.post(f"{settings.valhalla_url}/isochrone", json=body)
            r.raise_for_status()
            fc = r.json()
    except Exception as exc:  # noqa: BLE001 — Valhalla caído → el llamador degrada
        # Degradamos, pero NO en silencio: el operador debe ver que Valhalla no responde
        # (mismo criterio que routers/assets.py con Google). Distingue "caído" de "vacío".
        logger.warning("Valhalla /isochrone no respondió (%s): %s", type(exc).__name__, exc)
        return None
    out: list[dict] = []
    for feat in fc.get("features", []):
        props = feat.get("properties", {}) or {}
        geom = feat.get("geometry")
        # Con metric='time', Valhalla marca el contorno en properties.contour (minutos).
        m = props.get("contour")
        if not geom or m is None:
            continue
        try:
            minutos_val = int(round(float(m)))
        except (TypeError, ValueError):
            continue  # contorno malformado → descarta la feature, nunca revienta
        out.append({"minutos": minutos_val, "geometry": geom})
    return out or None
