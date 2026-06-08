#!/usr/bin/env python3
"""
Contexto AI — Subida masiva de fotos a Supabase Storage + generación de payloads
para POST /api/v1/assets/ingest/batch (Fase: escalado a 500 activos).

QUÉ HACE
  1. Lee un manifest CSV: archivo,direccion,pisos
  2. Sube cada foto local (carpeta --fotos-dir) al bucket de Supabase Storage
  3. Construye la URL pública permanente de cada foto
  4. Genera un JSON con los payloads de /ingest/batch, troceados de a --chunk (≤10)

SEGURIDAD
  - Lee SUPABASE_URL y SUPABASE_SERVICE_KEY de tu .env LOCAL (python-dotenv).
  - La service key NUNCA se imprime, ni se sube al repo, ni se pega en ningún chat.
  - El .env está gitignored. Este script no escribe secretos en su salida.

USO
  # 1) En tu .env local agrega (sin comillas):
  #    SUPABASE_URL=https://<tu-ref>.supabase.co
  #    SUPABASE_SERVICE_KEY=<service_role key de Supabase, solo local>
  #
  # 2) Pon tus fotos en ./fotos_quito/ y describe el lote en un CSV:
  #    archivo,direccion,pisos
  #    casa1.jpg,"Av. República del Salvador y Suecia, La Carolina, Quito",8
  #
  # 3) Corre:
  #    python scripts/subir_y_generar_payload.py --manifest scripts/fotos_manifest.csv
  #
  # 4) Revisa scripts/batch_payloads.json y úsalo en /ingest/batch (tanda por tanda).

  Flags útiles:
    --dry-run     Solo valida y genera URLs/payloads SIN subir nada.
    --fotos-dir   Carpeta de imágenes locales (default: ./fotos_quito)
    --bucket      Bucket destino (default: activos-fotos)
    --chunk       Tamaño de cada lote para /ingest/batch (default: 10, máx 10)
    --out         Archivo JSON de salida (default: scripts/batch_payloads.json)
"""
import argparse
import csv
import json
import mimetypes
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
ENV = dotenv_values(ROOT / ".env")

SUPABASE_URL = (ENV.get("SUPABASE_URL") or "").rstrip("/")
SERVICE_KEY = ENV.get("SUPABASE_SERVICE_KEY") or ""

_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def _fail(msg: str) -> None:
    print(f"❌ {msg}", file=sys.stderr)
    sys.exit(1)


def _public_url(bucket: str, path: str) -> str:
    return f"{SUPABASE_URL}/storage/v1/object/public/{bucket}/{path}"


def _upload(client: httpx.Client, bucket: str, path: str, data: bytes, ctype: str) -> None:
    """Sube (con upsert) un objeto al Storage de Supabase vía REST."""
    url = f"{SUPABASE_URL}/storage/v1/object/{bucket}/{path}"
    headers = {
        "Authorization": f"Bearer {SERVICE_KEY}",
        "apikey": SERVICE_KEY,
        "Content-Type": ctype,
        "x-upsert": "true",  # re-subir reemplaza, idempotente
    }
    resp = client.post(url, content=data, headers=headers)
    if resp.status_code not in (200, 201):
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Sube fotos a Supabase y genera payloads de ingesta.")
    ap.add_argument("--manifest", default="scripts/fotos_manifest.csv")
    ap.add_argument("--fotos-dir", default="fotos_quito")
    ap.add_argument("--bucket", default="activos-fotos")
    ap.add_argument("--out", default="scripts/batch_payloads.json")
    ap.add_argument("--chunk", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    chunk = max(1, min(args.chunk, 10))

    if not args.dry_run:
        if not SUPABASE_URL:
            _fail("Falta SUPABASE_URL en tu .env local.")
        if not SERVICE_KEY:
            _fail("Falta SUPABASE_SERVICE_KEY en tu .env local (solo local, nunca al repo/chat).")
    elif not SUPABASE_URL:
        _fail("Aun en --dry-run necesito SUPABASE_URL para construir las URLs públicas.")

    manifest_path = (ROOT / args.manifest).resolve()
    fotos_dir = (ROOT / args.fotos_dir).resolve()
    if not manifest_path.exists():
        _fail(f"No encuentro el manifest: {manifest_path}")

    rows: list[dict] = []
    with open(manifest_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"archivo", "direccion", "pisos"}
        if not required.issubset({(h or "").strip() for h in (reader.fieldnames or [])}):
            _fail(f"El CSV debe tener cabeceras: {sorted(required)}. Encontré: {reader.fieldnames}")
        for i, raw in enumerate(reader, start=2):  # línea 2 = primera fila de datos
            archivo = (raw.get("archivo") or "").strip()
            direccion = (raw.get("direccion") or "").strip()
            pisos_s = (raw.get("pisos") or "").strip()
            if not archivo or not direccion:
                print(f"⚠️  Línea {i}: fila incompleta, se omite.")
                continue
            try:
                pisos = int(pisos_s) if pisos_s else 1
            except ValueError:
                print(f"⚠️  Línea {i}: pisos '{pisos_s}' no es entero, uso 1.")
                pisos = 1
            rows.append({"archivo": archivo, "direccion": direccion, "pisos": pisos, "linea": i})

    if not rows:
        _fail("El manifest no tiene filas válidas.")

    items: list[dict] = []
    subidas = 0
    with httpx.Client(timeout=60.0) as client:
        for r in rows:
            local = fotos_dir / r["archivo"]
            ext = local.suffix.lower()
            if ext not in _ALLOWED_EXT:
                print(f"⚠️  {r['archivo']}: extensión {ext!r} no soportada, se omite.")
                continue
            if not local.exists():
                print(f"⚠️  {r['archivo']}: no existe en {fotos_dir}, se omite.")
                continue

            ctype = mimetypes.guess_type(str(local))[0] or "image/jpeg"
            if not args.dry_run:
                try:
                    _upload(client, args.bucket, r["archivo"], local.read_bytes(), ctype)
                    subidas += 1
                    print(f"✅ subida: {r['archivo']}")
                except Exception as exc:  # noqa: BLE001
                    print(f"❌ {r['archivo']}: error al subir → {exc}")
                    continue
            else:
                print(f"· (dry-run) {r['archivo']} → {_public_url(args.bucket, r['archivo'])}")

            items.append({
                "image_url": _public_url(args.bucket, r["archivo"]),
                "direccion": r["direccion"],
                "piso_altura": r["pisos"],
            })

    # Trocear en lotes de <= chunk para /ingest/batch
    lotes = [items[i:i + chunk] for i in range(0, len(items), chunk)]
    payloads = [{"items": lote} for lote in lotes]

    out_path = (ROOT / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payloads, f, ensure_ascii=False, indent=2)

    print("\n──────── RESUMEN ────────")
    print(f"Filas válidas en manifest : {len(rows)}")
    print(f"Fotos {'(dry-run, NO) ' if args.dry_run else ''}subidas   : {subidas}")
    print(f"Activos listos a ingestar : {len(items)}")
    print(f"Lotes (de a {chunk})           : {len(payloads)}")
    print(f"Payloads escritos en      : {out_path}")
    print("\nSiguiente paso: usa cada objeto de batch_payloads.json en POST /api/v1/assets/ingest/batch")


if __name__ == "__main__":
    main()
