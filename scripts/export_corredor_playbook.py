#!/usr/bin/env python3
"""
export_corredor_playbook.py — Destila el LLM-wiki "Corredor-Brain" (bóveda Obsidian, fuente de verdad
local) a un JSON COMPACTO que se bundlea en el repo (`app/agent/corredor_playbook.json`) para que las
tools del CRM lo consulten EN PRODUCCIÓN (Render no ve el Obsidian local).

Qué exporta por página usable (tactics/frameworks/principles con agente != ninguno y foso != rojo):
  {titulo, tipo, mogul, agente, foso, candado, que_es, como_aplica, tags, aliases}
Y las 🔴 (anti-patterns) como lista 'evitar': {titulo, mogul, por_que}.

Es un BUILD-STEP local: se corre cuando la bóveda cambia (o tras la hidratación semanal), y el JSON
resultante se commitea. Uso:
    python scripts/export_corredor_playbook.py
    python scripts/export_corredor_playbook.py --vault "<ruta>" --out app/agent/corredor_playbook.json
"""
import argparse, json, os, re, glob

DEFAULT_VAULT = r"C:\Users\DETPC\Desktop\WHABER\2. Whaber Travel-Ops Brain\Whaber-Claude Code\Corredor-Brain"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(REPO, "app", "agent", "corredor_playbook.json")


def parse_frontmatter(txt: str) -> dict:
    fm = {}
    m = re.match(r"^---\s*\n(.*?)\n---", txt, re.DOTALL)
    if not m:
        return fm
    for line in m.group(1).splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def _list(v: str) -> list:
    v = (v or "").strip().strip("[]")
    if not v:
        return []
    return [x.strip().strip('"').strip("'") for x in v.split(",") if x.strip()]


def _clean(s: str, limit: int) -> str:
    """Aplana markdown ligero + recorta."""
    s = re.sub(r"\*\*|\*|`|>", "", s)
    s = re.sub(r"\[\[([^\]|]+)(\|[^\]]+)?\]\]", r"\1", s)  # [[link|alias]] -> link
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit].rstrip() + ("…" if len(s) > limit else "")


def _section(txt: str, header_re: str, limit: int) -> str:
    """Extrae el cuerpo de una sección '## ...' hasta el próximo '## ' o EOF."""
    m = re.search(rf"^##\s*{header_re}.*?\n(.*?)(?=\n##\s|\Z)", txt, re.DOTALL | re.M | re.I)
    return _clean(m.group(1), limit) if m else ""


def _que_es(txt: str, limit: int) -> str:
    m = re.search(r"\*\*Qu[eé] es[^:]*:\*\*\s*(.+)", txt)
    return _clean(m.group(1), limit) if m else ""


def foso_color(f: str) -> str:
    f = (f or "").lower()
    return "verde" if "verde" in f else "amarillo" if "amarillo" in f else "rojo" if "rojo" in f else f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default=DEFAULT_VAULT)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    wiki = os.path.join(args.vault, "wiki")
    # Fail-closed: si el vault/wiki no existe (ruta local mal, CI, otro entorno) ABORTA — nunca escribas
    # un JSON vacío que clobberee el bundleado bueno que ya viaja a producción. Es un build-step LOCAL.
    if not os.path.isdir(wiki):
        raise SystemExit(f"ERROR: no existe el wiki del vault: {wiki}\n"
                         f"Este export es un build-step LOCAL — pasa --vault con la ruta correcta.")
    tacticas, evitar = [], []

    for folder in ("tactics", "frameworks", "principles"):
        for p in sorted(glob.glob(os.path.join(wiki, folder, "*.md"))):
            txt = open(p, encoding="utf-8").read()
            fm = parse_frontmatter(txt)
            titulo = fm.get("title", "").strip('"') or os.path.splitext(os.path.basename(p))[0]
            agente = (fm.get("agente", "") or "").strip().strip('"')
            foso = foso_color(fm.get("foso", ""))
            if agente in ("", "ninguno") or foso not in ("verde", "amarillo"):
                continue  # no usable: sin ruteo, anti-patrón, o foso malformado → fail-CLOSED
            tacticas.append({
                "titulo": titulo,
                "tipo": (fm.get("type", folder) or folder).strip('"'),
                "mogul": ", ".join(_list(fm.get("mogul") or fm.get("moguls") or "")) or "varios",
                "agente": agente,
                "foso": foso,
                "candado": _clean(fm.get("foso_nota", ""), 320),
                "que_es": _que_es(txt, 260),
                "como_aplica": _section(txt, r"C[oó]mo se aplica", 420),
                "tags": _list(fm.get("tags")),
                "aliases": _list(fm.get("aliases")),
            })

    for p in sorted(glob.glob(os.path.join(wiki, "anti-patterns", "*.md"))):
        txt = open(p, encoding="utf-8").read()
        fm = parse_frontmatter(txt)
        titulo = fm.get("title", "").strip('"') or os.path.splitext(os.path.basename(p))[0]
        evitar.append({
            "titulo": titulo,
            "mogul": ", ".join(_list(fm.get("mogul") or fm.get("moguls") or "")) or "—",
            "por_que": _que_es(txt, 240) or _clean(fm.get("foso_nota", ""), 240),
            "tags": _list(fm.get("tags")),
        })

    if len(tacticas) < 10:
        raise SystemExit(f"ERROR: solo {len(tacticas)} tácticas usables (esperadas ~79). No sobrescribo el "
                         f"JSON bundleado con un export sospechosamente vacío. Revisa el vault/frontmatter.")
    data = {
        "_meta": "Corredor-Brain destilado — tácticas de venta HONESTA (foso + ruteo por agente). NO es "
                 "verdad Whaber: cada táctica es 'per <Mogul>' con su candado. Regenerar con "
                 "scripts/export_corredor_playbook.py tras cambiar la bóveda.",
        "n_tacticas": len(tacticas),
        "n_evitar": len(evitar),
        "tacticas": tacticas,
        "evitar": evitar,
    }
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"OK → {args.out}\n  {len(tacticas)} tácticas usables · {len(evitar)} anti-patrones (evitar)")
    porag = {}
    for t in tacticas:
        porag[t["agente"]] = porag.get(t["agente"], 0) + 1
    print("  por agente:", " ".join(f"{k}={v}" for k, v in sorted(porag.items())))


if __name__ == "__main__":
    main()
