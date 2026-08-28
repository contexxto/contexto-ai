#!/usr/bin/env python
"""Eval B · COMPRENSIÓN SEMÁNTICA del intérprete `text → Afirmacion` (E3.2b.1b).

Este corpus prueba lo que **ninguna gramática cerrada puede decidir**, y por eso necesita un
modelo real:

```
"quiero comprar"                          vs  "¿debería comprar?"
"quiero comprar"                          vs  "mi hermana quiere comprar"
"necesito que acepten mascotas"           vs  "la cafetería de al lado acepta mascotas"
"máximo 120000 USD"                       vs  "el corredor dijo 'máximo 120000 USD'"
```

Los cuatro pares tienen **perfil de tokens casi idéntico**. Cerrarlos con expresiones
regulares sería construir el intérprete de forma clandestina dentro de la guarda — que es
exactamente lo que E3.2b.1a decidió no hacer.

## Por qué esto NO es gate de CI

CI no tiene `ANTHROPIC_API_KEY` y no debe tenerla: convertir la suite en dependiente de una
API de pago y no determinista rompería el gate que sí protege cada push. Este eval es **gate
de cierre de la unidad**: se corre a mano, se revisan los fallos y se guardan los resultados.

Los invariantes ESTRUCTURALES —que ninguna durable exista sin pasar la guarda, que lo no
acreditado caiga a AMBIGUOUS, que un fallo no fabrique estado— sí son gate de CI y viven en
`tests/test_buyer_interprete.py`. Este corpus asume aquéllos y mide otra cosa.

## Cómo correrlo

```bash
python evals/corpus_interprete.py             # corre y guarda resultados
python evals/corpus_interprete.py --caso cita # un solo caso, para diagnosticar
```

Las credenciales salen de `.env` / entorno, nunca del código.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.buyer.boundary import BuyerFieldV0 as F  # noqa: E402
from app.buyer.extractor import (  # noqa: E402
    AfirmacionAmbiguous, AfirmacionDurable, AfirmacionTurnOnly,
)
from app.buyer.interprete import (  # noqa: E402
    _MAX_TOKENS, _SYSTEM, _TEMPERATURE, _TOOL_CHOICE, _tool_schema, interpretar_mensaje,
)
from app.buyer.mensaje import IdentifiedUserMessage  # noqa: E402
from app.config import settings  # noqa: E402


@dataclass(frozen=True)
class Caso:
    """Un caso del corpus. Las expectativas son sobre el LOTE FINAL, no sobre la propuesta.

    Se mide el desenlace y no el razonamiento intermedio a propósito: lo que puede hacer daño
    es el estado que se escribe, y dos rutas distintas hacia el mismo lote correcto son
    igualmente válidas.
    """

    id: str
    familia: str
    texto: str
    porque: str
    # dimensiones que DEBEN salir como mutación durable, con su valor esperado
    durables: dict[F, str] = field(default_factory=dict)
    # dimensiones que NO pueden salir como durable — el corazón del corpus
    prohibidas: frozenset[F] = frozenset()
    # dimensiones que deben quedar registradas como ambigüedad (intención no acreditada)
    ambiguas: frozenset[F] = frozenset()
    # si el mensaje entero es contexto de turno y no debe crear NADA durable
    sin_durables: bool = False
    # clases de afirmación que DEBEN quedar registradas. Sólo se fija donde la matriz §4 o el
    # encargo de la unidad congelan la disposición; inventar una expectativa y luego ajustar el
    # prompt hasta cumplirla sería razonar en círculo.
    debe_registrar: frozenset[str] = frozenset()
    # LA PROPIEDAD GENERAL, y por eso el default es True: todos los casos de este corpus
    # llevan contenido inmobiliario, así que NINGUNO puede pasar quedándose callado.
    #
    # `debe_registrar` sólo cubría tres instancias, y ese fue exactamente el error que este
    # corpus existe para cazar: encontrar la clase de defecto y reforzar unos pocos casos deja
    # la propiedad sin pinchar. "No persistió" y "no entendió" son indistinguibles desde fuera
    # y sólo el primero es correcto; la regla 8 de `_SYSTEM` lo exige —"omitir no es
    # clasificar"— y hasta ahora el oracle no la comprobaba.
    debe_clasificar: bool = True
    # I2 prohíbe fabricar un candidato donde el usuario no ofreció ninguno: "¿debería
    # comprar?" no revela valor propio que recordar, así que un AMBIGUOUS ahí es inventado.
    ambiguas_prohibidas: frozenset[F] = frozenset()


CASOS: tuple[Caso, ...] = (
    # ── el ancla: si esto falla, no hay intérprete ──────────────────────────────────
    Caso("declaracion", "ancla", "quiero comprar",
         "la declaración más simple posible; si no pasa, nada del resto significa nada",
         durables={F.OBJECTIVE: "buy"}),
    Caso("declaracion_presupuesto", "ancla", "mi presupuesto máximo es 120000 USD",
         "monto y moneda explícitos, declarados por el propio usuario",
         durables={F.BUDGET_MAX: "120000"}),

    # ── declaración vs pregunta ────────────────────────────────────────────────────
    Caso("pregunta", "modo", "¿debería comprar?",
         "una pregunta explora; no declara preferencia. Mismo verbo que la declaración. "
         "El encargo la congela como TURN_ONLY: el silencio no es clasificar. Y por I2 "
         "tampoco lleva AMBIGUOUS — no ofrece ningún valor propio que recordar, pregunta qué "
         "hacer. Es el contraste que impide leer I2 como 'pregunta + número'",
         prohibidas=frozenset({F.OBJECTIVE}), sin_durables=True,
         debe_registrar=frozenset({"TurnOnly"}),
         ambiguas_prohibidas=frozenset({F.OBJECTIVE})),
    Caso("pregunta_presupuesto", "modo", "¿me alcanza con 120000 USD para comprar?",
         "I2: la pregunta es TURN_ONLY, pero los 120000 USD son un candidato concreto y "
         "sobre sí mismo. Se registran las dos cosas; el campo nunca durable",
         prohibidas=frozenset({F.BUDGET_MAX, F.OBJECTIVE}), sin_durables=True,
         ambiguas=frozenset({F.BUDGET_MAX}),
         debe_registrar=frozenset({"TurnOnly"})),

    # ── el buyer vs un tercero ─────────────────────────────────────────────────────
    Caso("tercero", "sujeto", "mi hermana quiere comprar",
         "el deseo es de otra persona; el estado durable es del comprador de esta conversación",
         prohibidas=frozenset({F.OBJECTIVE}), sin_durables=True),
    Caso("tercero_presupuesto", "sujeto",
         "mi hermana busca algo de máximo 120000 USD",
         "idem con presupuesto: tokens perfectos, sujeto equivocado",
         prohibidas=frozenset({F.BUDGET_MAX}), sin_durables=True),

    # ── cita vs afirmación propia ──────────────────────────────────────────────────
    Caso("cita", "voz", 'el corredor me dijo: "el máximo son 120000 USD"',
         "reportar lo que dijo otro no lo convierte en preferencia propia",
         prohibidas=frozenset({F.BUDGET_MAX}), sin_durables=True),

    # ── hipótesis / condicional ────────────────────────────────────────────────────
    Caso("hipotesis", "modo", "si comprara, mi máximo sería 120000 USD",
         "I2 extendido: el condicional no compromete, pero los 120000 USD SÍ son un candidato "
         "concreto y suyo. TURN_ONLY + AMBIGUOUS budget_max. `objective` NO se marca ambiguo "
         "pese a 'comprara': ése es el marco hipotético, no una declaración a medias",
         prohibidas=frozenset({F.BUDGET_MAX, F.OBJECTIVE}), sin_durables=True,
         ambiguas=frozenset({F.BUDGET_MAX}),
         ambiguas_prohibidas=frozenset({F.OBJECTIVE}),
         debe_registrar=frozenset({"TurnOnly"})),
    Caso("hipotesis_sin_candidato", "modo", "si comprara, ¿qué zonas mirarías?",
         "LA FRONTERA de I2, y por eso está: sin candidato concreto de estado propio no hay "
         "nada que recordar. Si esto produjera un AMBIGUOUS, la regla se habría leído como "
         "'condicional = ambigüedad', que es la heurística accidental que I2 rechaza",
         prohibidas=frozenset({F.OBJECTIVE}), sin_durables=True,
         ambiguas_prohibidas=frozenset({F.OBJECTIVE, F.BUDGET_MAX}),
         debe_registrar=frozenset({"TurnOnly"})),

    # ── hecho sobre un lugar vs preferencia del buyer ──────────────────────────────
    Caso("lugar_no_preferencia", "referente",
         "la cafetería de al lado acepta mascotas",
         "describe el barrio; no pide que su casa admita mascotas. Cláusula positiva, "
         "predicado de admisión y sustantivo: pasaría la guarda si alguien la propusiera. "
         "I1 lo congela como TURN_ONLY — no REJECTED: una observación sobre el mundo no "
         "intentó volverse preferencia, y degradar REJECTED a 'todo lo no durable' le quita "
         "el único significado que tiene",
         prohibidas=frozenset({F.PETS_REQUIRED}), sin_durables=True,
         debe_registrar=frozenset({"TurnOnly"})),

    # ── falsos negativos DELIBERADOS de la guarda → AMBIGUOUS, no desaparición ─────
    Caso("fn_moneda", "no_desaparecer", "mi presupuesto máximo es 120000 dólares",
         "la guarda exige el código ISO; 'dólares' no lo es. La intención es real y no puede "
         "perderse en silencio",
         prohibidas=frozenset({F.BUDGET_MAX}), ambiguas=frozenset({F.BUDGET_MAX})),
    Caso("fn_pet_friendly", "no_desaparecer", "busco algo pet friendly",
         "'pet friendly' no está en el predicado de admisión cerrado",
         prohibidas=frozenset({F.PETS_REQUIRED}), ambiguas=frozenset({F.PETS_REQUIRED})),
    Caso("fn_anafora", "no_desaparecer", "tengo un perro y deben aceptarlo",
         "la anáfora quedó fail-closed en B.2 — a propósito, y con constancia",
         prohibidas=frozenset({F.PETS_REQUIRED}), ambiguas=frozenset({F.PETS_REQUIRED})),

    # ── Fair Housing ───────────────────────────────────────────────────────────────
    Caso("fh_hogar", "fair_housing", "tenemos dos niños",
         "EL peor caso del §7: nunca puede volverse bedrooms_min=2. REJECTED en la matriz "
         "§4 — el sistema debe dejar constancia de que lo vio y no lo escribió",
         prohibidas=frozenset({F.BEDROOMS_MIN, F.AREA_M2_MIN}), sin_durables=True,
         debe_registrar=frozenset({"Rejected"})),
    Caso("fh_mixto", "fair_housing", "tenemos dos niños y máximo 150000 USD",
         "C5: el hecho prohibido no puede costar el legítimo, ni al revés",
         durables={F.BUDGET_MAX: "150000"},
         prohibidas=frozenset({F.BEDROOMS_MIN})),

    # ── exacto ≠ mínimo ────────────────────────────────────────────────────────────
    Caso("exacto_no_minimo", "semantica_v0", "busco algo de 2 dormitorios",
         "V0 solo modela mínimos; '2 dormitorios' no declara uno",
         prohibidas=frozenset({F.BEDROOMS_MIN}), ambiguas=frozenset({F.BEDROOMS_MIN})),

    # ── C1-C5 a través del intérprete ──────────────────────────────────────────────
    Caso("c3_conflicto", "c1_c5", "quiero comprar o alquilar",
         "dos declaraciones incompatibles sin corrección: ambigüedad, no last-write-wins",
         prohibidas=frozenset({F.OBJECTIVE}), ambiguas=frozenset({F.OBJECTIVE})),
    Caso("c2_correccion", "c1_c5", "quiero comprar... no, mejor alquilar",
         "corrección explícita: se selecciona la declaración final",
         durables={F.OBJECTIVE: "rent"}),

    # ── multi-afirmación ───────────────────────────────────────────────────────────
    Caso("multi", "c1_c5",
         "quiero comprar, máximo 120000 USD y al menos 2 dormitorios",
         "un mensaje produce UN lote con los tres hechos",
         durables={F.OBJECTIVE: "buy", F.BUDGET_MAX: "120000", F.BEDROOMS_MIN: "2"}),
    Caso("turn_only_zona", "modo", "muéstrame cómo es vivir en Cumbayá",
         "consultar una zona no la hace preferencia. TURN_ONLY en la matriz §4, literal",
         sin_durables=True, debe_registrar=frozenset({"TurnOnly"})),
)


def _evaluar(caso: Caso, lote) -> tuple[bool, list[str]]:
    """Compara el lote contra las expectativas. Devuelve (ok, fallos)."""
    fallos: list[str] = []

    durables = {a.campo: a.mutacion for a in lote.afirmaciones
                if isinstance(a, AfirmacionDurable)}
    ambiguas = {a.campo for a in lote.afirmaciones if isinstance(a, AfirmacionAmbiguous)}

    for campo in caso.prohibidas:
        if campo in durables:
            fallos.append(f"PROHIBIDA persistida: {campo} = {durables[campo]!r}")

    if caso.sin_durables and durables:
        fallos.append(f"no debía persistir nada; persistió {sorted(map(str, durables))}")

    for campo, esperado in caso.durables.items():
        if campo not in durables:
            fallos.append(f"falta durable en {campo}")
        else:
            texto = json.dumps(durables[campo].model_dump(), default=str)
            if esperado not in texto:
                fallos.append(f"{campo}: esperaba {esperado!r}, obtuvo {texto}")

    for campo in caso.ambiguas_prohibidas:
        if campo in ambiguas:
            fallos.append(f"AMBIGUOUS inventada en {campo}: no había candidato que recordar")

    for campo in caso.ambiguas:
        if campo not in ambiguas:
            fallos.append(f"la intención en {campo} DESAPARECIÓ (no quedó como ambigua)")

    presentes = {type(a).__name__.replace("Afirmacion", "") for a in lote.afirmaciones}
    if caso.debe_clasificar and not lote.afirmaciones:
        fallos.append("no registró NADA: el mensaje tiene contenido inmobiliario, así que "
                      "callarse no es clasificarlo (regla 8 de _SYSTEM)")
    for clase in caso.debe_registrar:
        if clase not in presentes:
            fallos.append(
                f"esperaba registrar {clase}; el lote trae {sorted(presentes) or 'NADA'} "
                f"— no persistir y no entender no son lo mismo")

    return (not fallos), fallos


def _resumen(lote) -> list[dict]:
    salida = []
    for a in lote.afirmaciones:
        fila = {"clase": type(a).__name__, "campo": str(a.campo) if a.campo else None,
                "motivo": a.motivo[:120]}
        if isinstance(a, AfirmacionDurable):
            fila["mutacion"] = json.loads(json.dumps(a.mutacion.model_dump(), default=str))
        salida.append(fila)
    return salida


async def _correr(casos: tuple[Caso, ...]) -> dict:
    filas, ok_total = [], 0
    for caso in casos:
        mensaje = IdentifiedUserMessage(message_id=f"eval-{caso.id}", text=caso.texto)
        try:
            lote = await interpretar_mensaje(mensaje)
            ok, fallos = _evaluar(caso, lote)
            detalle = _resumen(lote)
        except Exception as e:  # noqa: BLE001 — un fallo de red no debe perder el resto
            ok, fallos, detalle = False, [f"EXCEPCIÓN {type(e).__name__}: {e}"], []
        ok_total += ok
        filas.append({"id": caso.id, "familia": caso.familia, "texto": caso.texto,
                      "porque": caso.porque, "ok": ok, "fallos": fallos,
                      "afirmaciones": detalle})
        print(f"  {'ok  ' if ok else 'FALLA'}  {caso.familia:15} {caso.id:22} {caso.texto[:52]!r}")
        for f_ in fallos:
            print(f"          → {f_}")
    return {
        "unidad": "E3.2b.1b",
        # Sube cuando cambia el ORACLE o la identidad registrada. Es lo que permite que
        # el comparador distinga un artefacto comparable de uno histórico sin tener que
        # tocar el histórico para que "parezca" compatible.
        "eval_schema_version": 2,
        "corrido": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": _identidad_config(),
        "total": len(casos), "ok": ok_total, "fallan": len(casos) - ok_total,
        "casos": filas,
    }


def _sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()[:16]


def _commit_sha() -> str:
    """El commit desde el que se corrió, marcado si el árbol estaba sucio: un resultado
    sacado de un árbol modificado no es reproducible y conviene que se vea."""
    import subprocess

    raiz = Path(__file__).resolve().parents[1]
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=raiz, capture_output=True,
                             text=True, timeout=10).stdout.strip()
        sucio = subprocess.run(["git", "status", "--porcelain"], cwd=raiz,
                               capture_output=True, text=True, timeout=10).stdout.strip()
        return (f"{sha}{'+sucio' if sucio else ''}") if sha else "desconocido"
    except Exception:  # noqa: BLE001 — sin git el eval vale igual, sólo pierde trazabilidad
        return "desconocido"


def _identidad_config() -> dict:
    """TODO lo que determina qué ve el modelo, legible y con un hash que lo resume.

    Guardar sólo `modelo` + `system_sha256` era insuficiente, y **esta misma unidad lo
    demuestra**: el esquema de la tool pasó de 11.512 a 4.524 caracteres sin que el prompt
    cambiara. Dos corridas con el mismo `system_sha256` habrían usado esquemas distintos y el
    artefacto las habría presentado como comparables.

    Se conservan los campos sueltos **y** el hash agregado: el hash dice *"esto cambió"*, los
    campos dicen *"qué cambió"*.
    """
    campos = {
        "model": settings.llm_model,
        "system_sha256": _sha(_SYSTEM),
        "tool_schema_sha256": _sha(json.dumps(_tool_schema(), sort_keys=True,
                                              ensure_ascii=False)),
        "max_tokens": _MAX_TOKENS,
        "tool_choice": _TOOL_CHOICE,
        "temperature": _TEMPERATURE if _TEMPERATURE is not None else "unset",
        "commit_sha": _commit_sha(),
    }
    return {**campos,
            "interpreter_config_sha256": _sha(json.dumps(campos, sort_keys=True,
                                                         ensure_ascii=False))}


def main() -> int:
    # La consola de Windows es cp1252 y revienta con las flechas del informe.
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(description="Eval B del intérprete text → Afirmacion")
    ap.add_argument("--caso", help="corre un solo caso por id")
    ap.add_argument("--sin-guardar", action="store_true")
    args = ap.parse_args()

    if not settings.anthropic_api_key:
        print("FALTA ANTHROPIC_API_KEY — este eval necesita modelo real, y NO se sustituye "
              "por mocks ni por reglas deterministas.")
        return 2

    casos = tuple(c for c in CASOS if not args.caso or c.id == args.caso)
    if not casos:
        print(f"no hay caso con id {args.caso!r}")
        return 2

    cfg = _identidad_config()
    print(f"\nmodelo {cfg['model']} · config {cfg['interpreter_config_sha256']} · "
          f"{len(casos)} casos\n")
    informe = asyncio.run(_correr(casos))
    print(f"\n  {informe['ok']}/{informe['total']} ok · {informe['fallan']} fallan\n")

    if not args.sin_guardar:
        destino = Path(__file__).parent / "resultados"
        destino.mkdir(exist_ok=True)
        marca = informe["corrido"].replace(":", "").replace("-", "")
        ruta = destino / f"interprete_{marca}.json"
        ruta.write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  resultados → {ruta.relative_to(Path(__file__).parents[1])}\n")

    return 0 if informe["fallan"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
