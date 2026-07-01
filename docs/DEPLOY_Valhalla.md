# Desplegar Valhalla en producción (isócronas peatonales del foso)

El overlay 2C y la cuña "ancla + tiempo" necesitan un Valhalla que el backend de
Render pueda alcanzar. Este runbook lo levanta como **private service** dentro del
mismo Blueprint (`render.yaml`) — sin exponerlo a internet.

> **Orden:** primero Valhalla (esto), y solo cuando esté sirviendo, mergear el PR del
> overlay 2C (`feat-mapa-vivo-2c-isocronas`). Así los chips "N min a pie" funcionan en
> prod desde el día 1 en vez de mostrar "no disponible".

## Opción A — Render private service (recomendada, ya en el Blueprint)

`render.yaml` ya define el servicio `valhalla` (`type: pserv`) y le cablea al web
service el env `VALHALLA_URL=http://valhalla:8002` (URL interna de Render, no secreto).

**Pasos (dashboard de Render — los hace el fundador):**

1. Merge este PR a `main` (deja `render.yaml` + este doc en la rama principal).
2. En Render → tu Blueprint → **Manual Sync** (o auto-sync si está activo). Render
   detecta el nuevo `pserv valhalla` y lo aprovisiona con su disco `valhalla-tiles` (5 GB).
3. **Primer arranque (~5-15 min):** el contenedor baja el PBF de Ecuador (~113 MB) y
   construye los tiles. Míralo en Render → servicio `valhalla` → **Logs**: espera
   `Tile build complete` y el server escuchando en `:8002`.
4. Verifica desde el web service (Render → `contexto-ai-api` → **Shell**):
   ```bash
   curl -s -X POST http://valhalla:8002/isochrone -H 'Content-Type: application/json' \
     -d '{"locations":[{"lat":-0.1807,"lon":-78.4678}],"costing":"pedestrian","contours":[{"time":15}],"polygons":true}' | head -c 200
   ```
   Debe devolver un GeoJSON `FeatureCollection`.
5. Cuando responda: **mergea el PR del overlay 2C** → los chips quedan vivos en prod.

**Costo / RAM:** el build de tiles necesita ~2-4 GB → el `pserv` va en plan **standard**
(2 GB, ~$25/mes). Ecuador es chico y `server_threads=2` acota la RAM, así que 2 GB alcanza.
Si el primer build muriera por OOM: sube temporalmente el plan a `standard plus` (4 GB) SOLO
para ese build, y una vez que el disco tiene los tiles (`use_tiles_ignore_pbf=True`) bájalo
de nuevo a `standard` — servir consume ~512 MB-1 GB.

**Refresco de OSM (opcional, mensual):** para reconstruir con datos frescos, en el disco
borra `/custom_files/*` (o pon `force_rebuild=True` un deploy) y re-sincroniza.

## Opción B — VM barata con Docker (~$4-6/mes)

Si $25/mes es mucho para el spike, una VM (Hetzner/Fly.io/DigitalOcean) con Docker:

```bash
# En la VM:
git clone <repo> && cd contexto-ai
docker compose -f docker-compose.valhalla.yml up -d      # mismo compose que en local
```
Luego en Render → `contexto-ai-api` → Environment, pon `VALHALLA_URL=http://<IP_VM>:8002`
(y protege el puerto 8002 con firewall a solo la IP de Render, o un túnel privado —
Valhalla NO debe quedar abierto a internet). El `VALHALLA_URL` del Blueprint (interno)
solo aplica a la Opción A; en la Opción B lo sobreescribes en el dashboard.

## Notas

- El batch de isócronas por-inmueble (`scripts/valhalla_isocronas_batch.py`) ya llenó
  `isocronas_inmueble` en Supabase; esos polígonos **persisten sin Valhalla vivo**. Valhalla
  en prod se necesita para la **cuña en vivo** (isócrona del ancla del usuario) y para
  re-correr el batch cuando entren inmuebles nuevos.
- Sin `VALHALLA_URL` alcanzable, `app/isocronas.isocrona()` degrada limpio (log + None):
  el mapa no pinta isócronas, pero nada se rompe.
- Ver `docs/SPEC_Foso_Capa_de_Datos.md` §2 para el detalle del motor y la cuña.
