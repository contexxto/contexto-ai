"""Construcción de `DecisionContextV0` desde una decisión real (E2.2, primer subpaso).

QUÉ HACE Y QUÉ NO. Toma lo que el cálculo determinista YA produce hoy —la fila del
catastro, las preferencias declaradas y el resultado de `calcular_encaje`— y arma con eso
un `DecisionContextV0` válido. **No cambia ninguna salida legacy**: en este subpaso nadie
consume el objeto. Lo único que se demuestra es que se puede construir, y que se puede
construir sin FastAPI, sin endpoint y sin frontend.

Es un builder interno, no un contrato nuevo. `DecisionContextV0` quedó congelado en F1 y
aquí no se amplía ni se reinterpreta.

──────────────────────────────────────────────────────────────────────────────────
LOS PUENTES TRANSITORIOS, Y POR QUÉ CADA UNO ES HONESTO
──────────────────────────────────────────────────────────────────────────────────

F3, F4 y F5 no existen todavía, así que tres identidades no tienen aún su forma
definitiva. Ninguna se inventa; cada una declara lo que es:

    buyer_id = "session:<session_id>"   NO es la identidad permanente del comprador.
                                        Es la sesión, y dos sesiones no son la misma
                                        persona. F3 lo sustituye.
    context_revision = None             No hay store con historial que citar (F3).
    provider_id = "contexto"            El inventario propio es su propio proveedor
                                        hasta que exista el adaptador de F5.
    trace_id = None                     No hay instrumentación (F6). Se DECLARA, no se
                                        omite.

──────────────────────────────────────────────────────────────────────────────────
`place_id`: EL ÚNICO BORDE QUE PUEDE MENTIR EN SILENCIO
──────────────────────────────────────────────────────────────────────────────────

`PlaceContextRefV0.place_id` es obligatorio —se congeló así en E1.5, porque una decisión
que no se puede rastrear hasta su lugar no se puede explicar—. Pero `lat`/`lon` vienen de
`ST_Y`/`ST_X` y **pueden ser nulos**: el propio `_card_from_row` ya los trata como
opcionales.

Ahí está el peligro, y no es teórico: un `place_id` fabricado **validaría**. Pydantic
comprueba que el campo sea un string no vacío; no puede comprobar que ese string
corresponda a un lugar real. Una mentira semántica bien tipada pasa todos los tests.

Por eso el comportamiento ante coordenadas ausentes es **negarse en voz alta**:

    hay lat y lon válidos   →  point-v0:<hash determinista de las normalizadas>
    falta cualquiera de las →  CoordenadasAusentes

Lo que este módulo NO hace, y las tres omisiones son deliberadas: no inventa un id, no
devuelve `None` para seguir adelante, y **no excluye el candidato del panel** — esa
última es la salida cómoda, y también cambiaría comportamiento visible. Quien reciba la
excepción tiene que decidir qué hacer; no es una decisión de este módulo.

`point-v0` es un identificador TRANSITORIO de punto. No es identidad canónica de lugar:
no hay geocodificación inversa, ni proveedor, ni nombre de barrio. F4 lo reemplazará.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from app.contracts.common_v0 import Objective, RankingEntryV0
from app.contracts.decision_v0 import (
    BuyerContextRefV0,
    DecisionContextV0,
    PlaceContextRefV0,
    PropertyContextRefV0,
)
from app.decision.evidencia import derivar_incertidumbres
from app.encaje import SCORE_VERSION
from app.orden import ordenar_candidatos

PROVIDER_ID_LOCAL = "contexto"
"""El inventario propio como proveedor, hasta el adaptador de F5."""

_PLACE_ID_PREFIJO = "point-v0"
_MARGEN_PRESUPUESTO = 0.10
"""El "casi entra" que sí vale la pena mostrar. Mismo valor que tenía el corte del panel
cuando esta decisión vivía en la presentación."""

_DECIMALES = 6
"""~0,1 m. Suficiente para que dos lecturas del mismo punto den el mismo id, y para que
dos inmuebles distintos no colisionen."""


class SessionIdAusente(ValueError):
    """No hay identidad de ejecución, así que no se puede nombrar a quién se le decide.

    `BuyerContextRefV0.buyer_id` es obligatorio desde F1. Rellenarlo con
    `"session:unknown"`, un UUID nuevo o cualquier otro relleno produciría un
    `DecisionContextV0` que valida y no corresponde a nadie — el mismo error que
    `place_id`, en otro campo.

    OJO CON LA DISTINCIÓN: `session_id` es la identidad de la EJECUCIÓN conversacional,
    no la del comprador. La segunda llega en F3 y sustituirá a esta. Propagarla ahora no
    adelanta F3; evita que la decisión real lleve una referencia ficticia.
    """


class EncajeSinVersion(ValueError):
    """El motor produjo un resultado pero no dijo bajo qué reglas.

    Se levanta en vez de caer al `SCORE_VERSION` actual, y la razón es la misma que
    gobierna `place_id`: un objeto válido no puede afirmar más de lo que sostiene su
    evidencia. Etiquetar como `encaje-v0` un resultado que perdió su versión sería
    inventar la procedencia del número — y dos scores producidos por reglas distintas
    dejarían de poder distinguirse, que es justo lo que `score_version` existe para
    impedir.

    `encaje=None` es otra cosa y sí es legítimo: no hubo motor, así que la versión que
    corresponde es la del motor actual.
    """


class CoordenadasAusentes(ValueError):
    """No hay `lat`/`lon` válidos, así que no se puede nombrar el lugar sin inventarlo.

    Se levanta a propósito en vez de devolver `None`: un `place_id` fabricado validaría
    contra el contrato y sería falso, y nadie lo notaría después.
    """


def _es_coordenada(v) -> bool:
    """Numérico real y no booleano. `bool` es subclase de `int` en Python, y un `True`
    colado como latitud daría un id perfectamente válido para un punto inexistente."""
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def place_id_de_punto(lat, lon) -> str:
    """`point-v0:<hash>` determinista desde coordenadas normalizadas.

    Mismas coordenadas normalizadas → mismo id, siempre y en cualquier proceso: el hash
    es de `hashlib`, no de `hash()`, que en Python está aleatorizado por proceso y daría
    un id distinto en cada arranque.
    """
    if not _es_coordenada(lat) or not _es_coordenada(lon):
        raise CoordenadasAusentes(
            f"lat={lat!r} lon={lon!r}: sin coordenadas válidas no se puede construir un "
            "place_id sin inventarlo. Decidir qué hacer con este candidato es del caller: "
            "aquí no se fabrica un id, no se devuelve None, y no se excluye en silencio."
        )
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise CoordenadasAusentes(f"lat={lat!r} lon={lon!r}: fuera del rango geográfico")

    normal = f"{round(float(lat), _DECIMALES):.{_DECIMALES}f},{round(float(lon), _DECIMALES):.{_DECIMALES}f}"
    digest = hashlib.sha256(normal.encode("utf-8")).hexdigest()[:16]
    return f"{_PLACE_ID_PREFIJO}:{digest}"


def _score_version_de(encaje: dict | None) -> str:
    """Bajo qué reglas se puntuó. Sin normalizar en silencio.

        encaje is None   →  no hubo motor; la versión es la del motor actual
        encaje existe    →  tiene que traer la suya, explícita
        falta o vacía    →  EncajeSinVersion
        difiere          →  se USA la que dice, no la que esperábamos

    Lo último importa tanto como lo anterior: si un día el motor devuelve `encaje-v1`, la
    decisión debe registrar `encaje-v1`. Coercionarlo al valor esperado convertiría un
    cambio de reglas en un dato invisible.
    """
    if encaje is None:
        return SCORE_VERSION
    version = encaje.get("score_version")
    if not isinstance(version, str) or not version.strip():
        raise EncajeSinVersion(
            f"el resultado del motor no trae score_version (recibido: {version!r}). No se "
            f"asume '{SCORE_VERSION}': etiquetar un score con una versión que no declaró "
            "es inventar su procedencia."
        )
    return version


def _objetivo_desde(preferencias: dict | None) -> Objective:
    """`preferencias.operacion` → `Objective`. Solo el mapeo inequívoco.

    El inventario usa exactamente dos valores (`arriendo`, `venta`) y su lectura desde el
    lado del comprador no admite duda. `INVEST` no tiene ninguna fuente en el flujo actual,
    así que no se produce nunca — inferirlo sería inventar una intención que nadie declaró.
    """
    op = (preferencias or {}).get("operacion")
    if isinstance(op, str):
        clave = op.strip().lower()
        if clave == "arriendo":
            return Objective.RENT
        if clave == "venta":
            return Objective.BUY
    return Objective.UNKNOWN


def assemble_decision_context_v0(
    *,
    row: dict,
    preferencias: dict | None,
    encaje: dict | None,
    session_id: str,
    decision_id: str,
    created_at: datetime,
    ranking: tuple[RankingEntryV0, ...] = (),
) -> DecisionContextV0:
    """Un `DecisionContextV0` desde el cálculo determinista que ya existe.

    Todo lo que necesita entra por parámetro: no lee globals, no toca la base de datos y
    no llama a ningún modelo. `decision_id` y `created_at` también se inyectan —son lo
    único volátil del objeto— para que `mismos insumos → mismo objeto serializado` se
    pueda probar sin normalizar media estructura después.

    Levanta `CoordenadasAusentes` si la fila no permite nombrar el lugar, y
    `EncajeSinVersion` si el motor puntuó sin declarar bajo qué reglas. Los dos son el
    mismo principio: el objeto no puede afirmar más de lo que sostiene su evidencia.
    """
    if not isinstance(session_id, str) or not session_id.strip():
        raise SessionIdAusente(
            f"session_id={session_id!r}: sin identidad de ejecución no se puede construir "
            "el buyer_id de la decisión. No se inventa un valor por defecto."
        )
    place_id = place_id_de_punto(row.get("lat"), row.get("lon"))

    return DecisionContextV0(
        decision_id=decision_id,
        created_at=created_at,
        objective=_objetivo_desde(preferencias),
        buyer=BuyerContextRefV0(
            buyer_id=f"session:{session_id}",
            context_revision=None,
        ),
        property=PropertyContextRefV0(
            provider_id=PROVIDER_ID_LOCAL,
            property_id=str(row["id"]),
        ),
        place=PlaceContextRefV0(place_id=place_id),
        score_version=_score_version_de(encaje),
        # El ranking autoritativo del turno. Lo comparten todas las decisiones de un
        # mismo panel: es el orden que se decidió una vez, no una opinión por candidato.
        ranking=ranking,
        # E2.3a — el hueco de evidencia, registrado en vez de disimulado. Hoy sale una
        # incertidumbre por CADA razón que movió la decisión, porque la tabla de
        # procedencia demostró que ninguna tiene una referencia resoluble de punta a
        # punta. Es la mitad de E2.3 que sí se puede cumplir sin inventar provenance.
        uncertainties=derivar_incertidumbres(encaje),
        # Lo de abajo sigue vacío, y ahora por una razón demostrada y no por orden de
        # trabajo: las cuatro exigen `evidence_refs` no vacías —`ViolationV0` lo tiene
        # congelado desde E1.5— y no existe todavía dónde resolverlas.
        #   · eligibility.violations / match.dimensions → F5 (propiedad) y F3 (comprador)
        #   · strengths / tradeoffs                     → F4 (lugar) y F5 (propiedad)
        #   · explanation → E2.4, y solo después de que exista prosa que verificar
        #   · anchor_ids  → F3, cuando el comprador tenga anclas de verdad
    )


# ──────────────────────────────────────────────────────────────────────────────────
# E2.2 · segundo subpaso — la autoridad
# ──────────────────────────────────────────────────────────────────────────────────
#
# Hasta aquí la presentación DECIDÍA: ordenaba las tarjetas por su cuenta y volvía a
# calcular si un precio estaba sobre el tope. Que coincidiera con el motor era una
# propiedad afortunada, no una garantía — dos sitios calculando lo mismo divergen en
# cuanto uno de los dos cambia, y el que se ve es el que gana.
#
# Estas dos funciones son ahora la única fuente de esas dos verdades. La presentación
# las CONSUME: proyecta el ranking y aplica el veredicto, sin recalcular ninguno.


def decidir_ranking(
    cards: list[dict],
    *,
    prioritario: str | None = None,
    score_version: str | None = None,
) -> tuple[RankingEntryV0, ...]:
    """El orden de la decisión, como `RankingEntryV0` con identidad estable.

    El criterio no cambia: sigue siendo `app.orden.ordenar_candidatos` —léxico por
    requisitos duros, luego encaje ajustado por cobertura, estable— más la priorización
    declarada por el modelo, que puede liderar con otra opción siempre que deje el motivo
    escrito. Lo que cambia es QUIÉN manda: esto produce el orden, y las tarjetas lo
    siguen.

    `score` es el encaje VISIBLE, que es el mismo por el que se ordena. Va acompañado de
    `score_version` porque `RankingEntryV0` no admite un número sin su regla.
    """
    ordenadas = ordenar_candidatos(list(cards))
    if prioritario and any(c.get("id") == prioritario for c in ordenadas):
        # Estable: solo sube el elegido, el resto conserva su posición relativa.
        ordenadas.sort(key=lambda c: c.get("id") != prioritario)

    version = score_version or SCORE_VERSION
    return tuple(
        RankingEntryV0(
            provider_id=PROVIDER_ID_LOCAL,
            property_id=str(c["id"]),
            rank=i,
            score=float(c["encaje"]) if c.get("encaje") is not None else None,
            score_version=version if c.get("encaje") is not None else None,
        )
        for i, c in enumerate(ordenadas, start=1)
    )


def decidir_sobre_presupuesto(
    cards: list[dict], preferencias: dict | None
) -> frozenset[str]:
    """Qué opciones quedan fuera del presupuesto declarado. Se calcula UNA vez, aquí.

    El margen es el mismo de siempre: deja pasar el "casi entra" —$710 contra $700— que
    sí vale la pena mostrar mientras se etiquete honestamente, y corta lo que ya no es
    una opción.

    Devuelve ids, no tarjetas: el veredicto viaja por identidad, así que reordenar el
    panel después no puede desalinearlo.
    """
    tope = (preferencias or {}).get("presupuesto_max")
    if not isinstance(tope, (int, float)) or isinstance(tope, bool) or tope <= 0:
        return frozenset()
    limite = float(tope) * (1 + _MARGEN_PRESUPUESTO)
    return frozenset(
        str(c["id"])
        for c in cards
        if c.get("precio") is not None and c["precio"] > limite
    )


def proyectar_cards(
    cards: list[dict], decision: DecisionContextV0
) -> list[dict]:
    """Ordena las tarjetas SEGÚN `decision.ranking`. La presentación obedece al objeto.

    Es la costura que convierte `DecisionContextV0` en el portador real de la autoridad,
    y no solo en su documentación tipada. Antes de esto había dos cores: uno tipado que
    describía la decisión y otro funcional que la tomaba — y en cuanto dos cosas
    describen lo mismo, divergen.

    Esta función **no decide nada**: no llama al criterio de orden, no mira precios y no
    conoce las preferencias. Recibe el resultado, nunca al decisor. Una tarjeta que el
    ranking no nombra no aparece; el ranking no puede nombrar una tarjeta que no existe.
    """
    por_id = {str(c["id"]): c for c in cards}
    return [por_id[e.property_id] for e in decision.ranking if e.property_id in por_id]
