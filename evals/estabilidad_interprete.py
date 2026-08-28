#!/usr/bin/env python
"""Compara varias corridas del eval semántico y decide si el intérprete es ESTABLE.

Un modelo no es determinista, así que `19/19` una vez no es `19/19` siempre. Lo que importa
aquí no es la varianza en abstracto sino una pregunta concreta:

> ¿oscila alguna decisión que podría llegar a memoria durable?

Por eso la comparación es **semántica y no textual**. Dos corridas pueden redactar motivos
distintos y ser la misma decisión; lo que no puede cambiar entre corridas es:

```
la clase de afirmación por dimensión   DURABLE / AMBIGUOUS / TURN_ONLY / REJECTED
el tipo y el valor de cada mutación    set_budget_max 120000 USD
```

Si una dimensión oscila entre DURABLE y AMBIGUOUS, el mismo mensaje escribiría memoria unas
veces sí y otras no. Eso no se arregla con un reintento: o el prompt lo estabiliza, o esa
decisión debe degradarse a AMBIGUOUS por diseño.

```bash
python evals/estabilidad_interprete.py evals/resultados/interprete_*.json
```
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path


def _huella(caso: dict) -> list[tuple]:
    """La DECISIÓN de un caso, sin la prosa.

    Se ordena porque el orden entre corridas no es la propiedad que se está midiendo aquí
    —de eso se ocupan los tests de C1-C5— y dos listas equivalentes en distinto orden no son
    una oscilación semántica.
    """
    return sorted(
        (a["clase"], a["campo"], json.dumps(a.get("mutacion"), sort_keys=True))
        for a in caso["afirmaciones"]
    )


def main() -> int:
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="Estabilidad semántica entre corridas")
    ap.add_argument("resultados", nargs="+", type=Path)
    args = ap.parse_args()

    crudos = [(p, json.loads(p.read_text(encoding="utf-8"))) for p in args.resultados]

    # Los artefactos anteriores al endurecimiento del oracle NO se tocan y NO se borran: son
    # la evidencia de que llegamos a un 19/19 falsamente convincente, lo descubrimos y
    # apretamos el sistema. Reescribir la historia cuando cambia la vara sería perder justo la
    # parte instructiva. Se catalogan como no comparables y se dejan fuera del cálculo.
    legacy = [(p, i) for p, i in crudos
              if i.get("eval_schema_version") is None or "config" not in i]
    pares = [(p, i) for p, i in crudos if (p, i) not in legacy]
    for p, i in legacy:
        print(f"\n  LEGACY / SUPERSEDED · {p.name}")
        print(f"    oracle pre-integridad · comparable: false · {i.get('ok')}/{i.get('total')}")
        print("    motivo: sin identidad de configuración (falta tool_schema/config) y con "
              "oracle que dejaba pasar la salida vacía")

    informes = [i for _, i in pares]
    rutas = [p for p, _ in pares]
    if len(informes) < 2:
        print("\nhacen falta al menos dos corridas COMPARABLES para hablar de estabilidad")
        return 2

    print(f"\n{len(informes)} corridas comparables\n")

    # 1 · sólo se compara dentro de una misma configuración, y se evalúa la VIGENTE.
    #
    # Las corridas de configuraciones anteriores no se descartan ni se borran: documentan qué
    # se probó y por qué se cambió. Se agrupan, se marcan como superadas y se dejan fuera del
    # cálculo — mismo criterio que los artefactos legacy.
    grupos: dict[str, list] = defaultdict(list)
    for p, i in zip(rutas, informes, strict=True):
        grupos[i["config"]["interpreter_config_sha256"]].append((p, i))

    vigente = max(grupos, key=lambda c: max(i["corrido"] for _, i in grupos[c]))
    for cfg, miembros in grupos.items():
        if cfg == vigente:
            continue
        c = miembros[0][1]["config"]
        print(f"  SUPERADA · config {cfg} · {len(miembros)} corridas · "
              f"system={c['system_sha256']} schema={c['tool_schema_sha256']}")

    rutas = [p for p, _ in grupos[vigente]]
    informes = [i for _, i in grupos[vigente]]
    if len(informes) < 2:
        print(f"\n  la configuración vigente {vigente} sólo tiene {len(informes)} corrida")
        return 2
    print(f"  config VIGENTE {vigente} · {len(informes)} corridas")

    # 2 · todas verdes
    fallan = [(p.name, i["fallan"]) for p, i in zip(rutas, informes, strict=True)
              if i["fallan"]]
    for nombre, n in fallan:
        print(f"  {nombre}: {n} casos fallan")
    print(f"  {'todas verdes' if not fallan else 'HAY CORRIDAS EN ROJO'}")

    # 3 · ninguna decisión oscila
    huellas: dict[str, set] = defaultdict(set)
    for informe in informes:
        for caso in informe["casos"]:
            huellas[caso["id"]].add(json.dumps(_huella(caso), sort_keys=True))

    oscilan = {cid: hs for cid, hs in huellas.items() if len(hs) > 1}

    # I3 · no toda oscilación pesa lo mismo, y meterlas en un booleano oculta lo único que de
    # verdad importa.
    #
    #   GRAVE  entra, sale o cambia una DURABLE → el MISMO mensaje escribiría memoria unas
    #          veces sí y otras no. Inaceptable.
    #   MEDIA  cambia la clase no-durable, o cambia la DIMENSIÓN de una AMBIGUOUS. No escribe
    #          nada, pero altera si el producto repregunta y sobre qué.
    #   LEVE   sólo varía el `campo` OPCIONAL de un TURN_ONLY o un REJECTED, sin tocar
    #          durables ni ambigüedades. Ahí `campo` es opcional por diseño.
    grave, media, leve = {}, {}, {}
    for cid, hs in oscilan.items():
        lecturas = [json.loads(h) for h in hs]

        def _durables(lectura):
            return frozenset((campo, mut) for c, campo, mut in lectura if c == "Durable")

        def _ambiguas(lectura):
            return frozenset(campo for c, campo, _ in lectura if c == "Ambiguous")

        def _clases(lectura):
            return tuple(sorted(c for c, _, _ in lectura))

        if len({_durables(l) for l in lecturas}) > 1:
            grave[cid] = hs
        elif len({_ambiguas(l) for l in lecturas}) > 1 or len({_clases(l) for l in lecturas}) > 1:
            media[cid] = hs
        else:
            leve[cid] = hs

    def _mostrar(titulo, grupo):
        if not grupo:
            return
        print(f"\n  {titulo} ({len(grupo)}):")
        for cid, hs in grupo.items():
            print(f"    {cid}")
            for h in sorted(hs):
                etiquetas = [f"{c.replace('Afirmacion','')}:{campo or '-'}"
                             for c, campo, _ in json.loads(h)] or ["(NADA)"]
                print(f"      · {' '.join(etiquetas)}")

    _mostrar("GRAVE · entra y sale de DURABLE — escribiría memoria de forma no determinista",
             grave)
    _mostrar("MEDIA · cambia la clase no-durable — altera si el producto repregunta", media)
    _mostrar("LEVE  · misma clase, sólo varía el `campo` opcional", leve)
    if not oscilan:
        print(f"  ninguna decisión oscila en {len(huellas)} casos")

    print(f"\n  durables estables: {'SÍ' if not grave else 'NO'}"
          f" · clasificación estable: {'SÍ' if not (grave or media) else 'NO'}")
    ok = not fallan and not grave and not media
    print(f"  {'ESTABLE' if ok else 'NO ESTABLE — HOLD'}\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
