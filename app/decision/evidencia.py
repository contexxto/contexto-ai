"""E2.3a — cobertura de evidencia: qué parte de su propia decisión el sistema no puede demostrar.

La tabla de procedencia (`docs/agentic_decision_system/E2_3_TABLA_DE_PROCEDENCIA.md`)
encontró que hoy hay **cero** razones materiales con una referencia de evidencia resoluble
de punta a punta. Ni una. Incluso la caminabilidad —la única cuya procedencia está
registrada de verdad, gracias a `walk_score_fuente`— tendría que citarse contra un
`PlaceContextV0` que no se ensambla en runtime.

Eso deja dos salidas, y solo una es honesta:

  · fabricar `EvidenceRefV0` para que las afirmaciones materiales cierren  → NO.
    Sería un `evidence_id` que valida y no resuelve; la misma familia de `place_id`
    inventado, `score_version` normalizado y `decision_id` colisionado.

  · registrar el hueco.  `UncertaintyV0` es la ÚNICA afirmación del contrato cuya
    evidencia es opcional, y lo es exactamente por esto: una incertidumbre suele existir
    porque faltan datos. Exigirle evidencia sería exigirle que demuestre lo que no tiene.

Este módulo hace lo segundo. Para cada razón que efectivamente participó en la decisión y
NO tiene evidencia resoluble, emite una incertidumbre que dice qué se usó y por qué todavía
no se puede demostrar.

Ojo con lo que estas incertidumbres afirman, porque no es lo obvio. No dicen "no sabemos
el valor" — el sistema sí lo conoce y lo usó. Dicen algo más incómodo y más preciso:
**conocemos el valor que movió la decisión, pero todavía no podemos probar de dónde salió.**

El resultado esperado hoy es `afirmaciones materiales con evidencia = 0` y
`incertidumbres = N`. Eso no es un fracaso de E2.3: es la primera vez que el sistema sabe
de forma estructurada qué parte de su decisión no está demostrada.
"""

from __future__ import annotations

from app.contracts.decision_v0 import Impact, UncertaintyV0
from app.encaje import DIMENSIONES, INSUFICIENTE, _REQUISITOS_DUROS


class DimensionSinProcedencia(RuntimeError):
    """Una dimensión del motor sin fila en la tabla de procedencia.

    Se levanta en vez de omitirla. Omitirla produciría justo el estado que E2.3 vino a
    hacer imposible: una razón que movió la decisión, sin evidencia y sin incertidumbre
    que lo diga — invisible en el contrato y por tanto inauditable.
    """


# ── De qué depende que un hueco de evidencia sea grave ────────────────────────────
#
# `impact` es obligatorio en `UncertaintyV0` y no se decide a ojo: se deriva de cómo
# participa HOY el motor, para que no haya que reeditarlo a mano cuando el motor cambie.
#
#   HIGH    el hueco puede cambiar la elegibilidad o sacar una opción de la vista
#   MEDIUM  puede mover el score y con él el ranking, pero no la elegibilidad
#   LOW     la dimensión no altera la decisión hoy (se declaró y no pudo evaluarse)

# `presupuesto_max` es la preferencia desde la que `decidir_sobre_presupuesto` calcula el
# veredicto que `_recortar_grid` usa para SACAR tarjetas del panel. No es una ponderación
# más: decide qué se ve.
_DIMENSION_DEL_CORTE_POR_PRECIO = "presupuesto_max"

# Se deriva de `encaje._REQUISITOS_DUROS` en vez de repetir el conjunto, para que agregar
# un requisito duro allá no deje aquí un impacto desactualizado en silencio. Incumplir uno
# topa el score a 49, por debajo del `_ENCAJE_MIN_GRID` (60) con que el panel recorta: el
# efecto real es que la opción desaparece.
_CAMBIAN_LO_VISIBLE: frozenset[str] = _REQUISITOS_DUROS | {_DIMENSION_DEL_CORTE_POR_PRECIO}


# ── Tabla de procedencia, en código ───────────────────────────────────────────────
#
# Una fila por dimensión. `etiqueta` abre SIEMPRE el `statement`: es lo que permite al
# gate de E2.3 emparejar una razón con su incertidumbre, ya que `UncertaintyV0` —contrato
# congelado en F1— no tiene campo de dimensión.

_ETIQUETA: dict[str, str] = {
    "tipo_inmueble": "El tipo de inmueble",
    "tranquilidad": "La tranquilidad",
    "caminable": "La caminabilidad",
    "transporte": "La cercanía a transporte",
    "area_verde": "La cercanía a área verde",
    "presupuesto_max": "El presupuesto",
    "dormitorios": "El número de dormitorios",
    "acepta_mascotas": "La aceptación de mascotas",
}

# Cómo participó en la decisión. Solo se usa cuando la razón SÍ movió el número.
_PARTICIPACION: dict[str, str] = {
    "tipo_inmueble": "participó como restricción dura —topa el score y saca la opción del panel—",
    "presupuesto_max": "afectó el ranking y la visibilidad de la opción",
}
_PARTICIPACION_POR_DEFECTO = "participó en el encaje"

# Por qué esa participación no se puede demostrar todavía.
_HUECO: dict[str, str] = {
    "tipo_inmueble": "la declaración del inventario todavía no tiene evidencia resoluble",
    "presupuesto_max": (
        "el precio no está resuelto vía PropertyContext y el tope procede de extracción "
        "LLM sin declaración trazable"
    ),
    # Única dimensión con procedencia real registrada (`walk_score_fuente`, arreglo de
    # E0.3): el objeto se sabe construir; lo que falta es dónde resolverlo.
    "caminable": (
        "su procedencia sí está registrada, pero no existe todavía un PlaceContext contra "
        "el cual resolver la referencia"
    ),
    "transporte": "procede de texto libre parseado y su fuente real no está distinguida",
    "area_verde": "procede de texto libre parseado sin evidencia resoluble",
    "tranquilidad": "el score de ruido no tiene ninguna medición que lo sostenga",
    "dormitorios": "procede de atributos JSONB sin evidencia resoluble",
    "acepta_mascotas": "procede de atributos JSONB sin evidencia resoluble",
}

# Dónde se resuelve la deuda. No es decoración: es el contrato de qué fase la cierra.
_DESTINO: dict[str, str] = {
    "tipo_inmueble": "evidencia de propiedad → F5",
    "presupuesto_max": "evidencia de propiedad → F5; evidencia de comprador → F3",
    "caminable": "evidencia de lugar → F4",
    "transporte": "evidencia de lugar → F4",
    "area_verde": "evidencia de lugar → F4",
    "tranquilidad": "evidencia de lugar → F4",
    "dormitorios": "evidencia de propiedad → F5",
    "acepta_mascotas": "evidencia de propiedad → F5",
}


def _exigir_fila(dimension: str) -> None:
    faltan = [t for t, tabla in (("etiqueta", _ETIQUETA), ("hueco", _HUECO),
                                 ("destino", _DESTINO)) if dimension not in tabla]
    if faltan:
        raise DimensionSinProcedencia(
            f"la dimensión {dimension!r} mueve la decisión y no tiene {', '.join(faltan)} "
            "en la tabla de procedencia. Sin eso quedaría sin evidencia Y sin "
            "incertidumbre: invisible en el contrato. Agregar la fila, no omitir la razón."
        )


def _impacto(dimension: str, aporta: bool) -> Impact:
    """Derivado del comportamiento del motor, nunca fijado a mano por dimensión."""
    if not aporta:
        return Impact.LOW
    return Impact.HIGH if dimension in _CAMBIAN_LO_VISIBLE else Impact.MEDIUM


def _statement(dimension: str, razon: dict) -> str:
    etiqueta, destino = _ETIQUETA[dimension], _DESTINO[dimension]

    if razon.get("cumple") == INSUFICIENTE:
        # El valor EXISTE y se decidió no dejarlo mover el ranking. Distinto de no tenerlo.
        return (f"{etiqueta} se declaró como necesidad y el valor existe, pero ninguna "
                f"fuente lo sostiene: no movió el número ({destino}).")

    if not razon.get("aporta"):
        return (f"{etiqueta} se declaró como necesidad, pero el inmueble no reporta la "
                f"señal: no movió el número ({destino}).")

    participacion = _PARTICIPACION.get(dimension, _PARTICIPACION_POR_DEFECTO)
    return f"{etiqueta} {participacion}, pero {_HUECO[dimension]} ({destino})."


def derivar_incertidumbres(encaje: dict | None) -> tuple[UncertaintyV0, ...]:
    """Una incertidumbre por cada razón del encaje sin evidencia resoluble.

    Hoy son TODAS, y ese es el resultado correcto: la tabla de procedencia demostró que
    ninguna razón material tiene una referencia que la decisión pueda citar y resolver.
    Cuando F3/F4/F5 hagan resoluble alguna, esa dimensión deja de aparecer aquí y pasa a
    ser una afirmación material con `evidence_refs` — y el gate de E2.3 sigue exigiendo
    que esté cubierta por uno de los dos caminos.

    Las razones `sin_dato` e `insufficient_evidence` también entran, con `impact` bajo:
    se declararon como necesidad y no pudieron evaluarse. Decir eso es más honesto que
    callarlo, y es lo que ya hacía la razón legacy.
    """
    if not encaje:
        return ()

    fuera: list[UncertaintyV0] = []
    for razon in encaje.get("razones") or ():
        dimension = razon.get("dimension")
        _exigir_fila(dimension)
        fuera.append(
            UncertaintyV0(
                statement=_statement(dimension, razon),
                impact=_impacto(dimension, bool(razon.get("aporta"))),
                # Vacío A PROPÓSITO y no por olvido: si hubiera una referencia resoluble
                # que citar, esto no sería una incertidumbre sino una afirmación material.
                evidence_refs=(),
            )
        )
    return tuple(fuera)


def dimension_de(incertidumbre: UncertaintyV0) -> str | None:
    """Qué dimensión describe una incertidumbre, por su etiqueta inicial.

    El emparejamiento va por prefijo porque `UncertaintyV0` quedó congelado en F1 sin
    campo de dimensión, y no se toca un contrato para simplificarle la vida a un test.
    """
    for dimension in DIMENSIONES:
        if incertidumbre.statement.startswith(_ETIQUETA[dimension]):
            return dimension
    return None
