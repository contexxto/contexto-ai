"""F3-SHADOW-DECISION-RUNTIME-R0G · el contrafactual de mascotas, en runtime y APAGADO.

La pregunta, exacta: **¿qué habría cambiado ÚNICAMENTE por la memoria de mascotas del
comprador?** No «¿es mejor la recomendación?» — para eso no hay patrón de verdad, y llamar
mejora a un delta sin él sería inventarse el resultado.

```
operación pets de confianza          ← evidencia estructurada, nunca texto
        +
captura comprometida (R0F1)          ← las MISMAS filas que decidieron
        +
artefacto visible (AgentState)       ← no se recalcula
        ↓
UNA corrida del núcleo puro          ← cero LLM, cero inventario, cero red
        ↓
observación efímera
```

## LO QUE NO PUEDE HACER

El resultado sombra no llega a `cards`, ni a `descartadas`, ni al panel, ni a la respuesta,
ni a la prosa, ni a las herramientas. Su único consumidor es la observación. Hay un guard
estructural con su mitad negativa.

## LAS TRES OPERACIONES, Y POR QUÉ NO SON UN `bool | None`

```
REQUERIR      el comprador exige que acepten mascotas  → escribe la clave
RETIRAR       el comprador RETIRA ese requisito        → borra la clave
SIN_SENAL     no se ha pronunciado                     → NO toca las preferencias
NO_COMPARABLE no se puede afirmar nada con certeza     → CERO corridas del núcleo
```

`None` no distingue «lo retiró» de «nunca dijo nada». Proyectarlo como retirada haría que un
comprador silencioso borrara una preferencia que la persona sí declaró en el hilo. Lo que
separa los dos casos es la **evidencia por campo**: valor `None` **con** `FieldEvidence` en la
ruta de mascotas significa retirada explícita; sin ella, silencio.

Eso es sólido porque el valor y su evidencia se escriben en la MISMA reducción y
`_fusionar_evidencia` reemplaza por ruta —cardinalidad ≤ 1—, así que no puede quedar la
evidencia de un `Set` viejo junto a un valor `None`: si la última mutación hubiera sido un
`Set`, el valor sería `True`.

## FALLA CERRADO, SIEMPRE

Captura ausente, vacía o desalineada; ambigüedad sobre mascotas en el turno o en la memoria;
o un candidato que falló por cualquier motivo que no sea silencio legítimo → `NO_COMPARABLE`,
**cero lecturas del comprador y cero corridas del núcleo**. Comparar «de todos modos» mediría
el arnés, no el campo.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import StrEnum

from app.buyer.boundary import (
    BuyerFieldV0, ClearPetsRequired, SetPetsRequired, ruta_contractual,
)
from app.buyer.candidato import DesenlaceCandidato
from app.buyer.extractor import AfirmacionAmbiguous, AfirmacionDurable
from app.config import settings
from app.decision.assembler import _decidir_desde_filas
from app.decision.runtime_capture import Correspondencia, caja_actual, cotejar

logger = logging.getLogger(__name__)

_CLAVE_LEGACY = "acepta_mascotas"
_RUTA_PETS = ruta_contractual(SetPetsRequired())
"""`property_requirements.pets_allowed_required`, derivada del contrato y no escrita a mano:
si la ruta cambiara, esto cambia con ella."""


# ── Vocabularios CERRADOS. Ninguno sale de este módulo hacia un contrato público. ──


class OperacionMascotas(StrEnum):
    REQUERIR = "requerir"
    RETIRAR = "retirar"
    SIN_SENAL = "sin_senal"
    NO_COMPARABLE = "no_comparable"


class FuenteDelEstado(StrEnum):
    TURNO_ACTUAL = "turno_actual"
    MEMORIA_PERSISTIDA = "memoria_persistida"
    NINGUNA = "ninguna"


class ClaseCaptura(StrEnum):
    COINCIDE = "coincide"
    NO_COINCIDE = "no_coincide"
    VACIA = "vacia"
    AUSENTE = "ausente"


class ClaseDelta(StrEnum):
    SIN_DELTA = "sin_delta"
    DELTA_ESPERADO = "delta_esperado"
    DELTA_INESPERADO = "delta_inesperado"
    NO_COMPARABLE = "no_comparable"


class RelacionPersistencia(StrEnum):
    ALINEADA = "alineada"
    DIVERGIDA = "divergida"
    NO_INTENTADA = "no_intentada"

    NO_OBSERVABLE = "no_observable"
    """El updater corrió pero desde aquí no se puede saber cómo terminó.

    `actualizar_en_sombra` devuelve `None` a propósito y un guard de E3.2b.4 prohíbe asignar
    su resultado, así que el llamante no tiene el desenlace. Decirlo con un valor propio es
    lo honesto: reportar `NO_INTENTADA` cuando el updater SÍ lo intentó sería falso, y
    `DIVERGIDA` sería inventarse un fallo. El mapeo completo existe y está probado
    (`relacion_de_persistencia`) para cuando el desenlace llegue.
    """


@dataclass(frozen=True)
class ObservacionSombra:
    """Lo que se puede decir del turno. **Efímera**: no se persiste ni se serializa.

    Sin `buyer_id`, sin correo, sin token, sin el texto del mensaje, sin el `BuyerContext`,
    sin el lote y sin ids de activo. Lo que queda son clases cerradas y conteos.
    """

    operacion: OperacionMascotas
    fuente: FuenteDelEstado
    captura: ClaseCaptura
    delta: ClaseDelta
    relacion_persistencia: RelacionPersistencia

    top1_cambio: bool = False
    top3_solape: int = 0
    visibles: int = 0
    sombra: int = 0
    movimientos_de_rejilla: int = 0
    movimientos_de_posicion: int = 0
    deltas_de_score: int = 0
    deltas_de_cobertura: int = 0

    lecturas_del_comprador: int = 0
    corridas_del_nucleo: int = 0
    duracion_ms: int = 0

    campo: str = "pets"


# ── Derivación de la operación · sólo evidencia estructurada ───────────────────────


def operacion_del_turno(lote) -> OperacionMascotas | None:
    """Qué dijo la persona sobre mascotas EN ESTE TURNO, o `None` si no la mencionó.

    Se lee del lote, nunca del texto y nunca reinterpretando: las afirmaciones ya vienen
    tipadas. `LoteExtraccion` garantiza una sola durable por campo —lo impone un validador,
    no una convención—, así que no hay que resolver empates aquí.

    Una ambigüedad sobre mascotas gana a cualquier memoria: si la persona está aclarando o
    contradiciendo, fingir certeza sería lo peor que podría hacer el experimento.
    """
    if lote is None:
        return None
    afirmaciones = getattr(lote, "afirmaciones", ()) or ()

    for a in afirmaciones:
        if isinstance(a, AfirmacionDurable):
            if isinstance(a.mutacion, SetPetsRequired):
                return OperacionMascotas.REQUERIR
            if isinstance(a.mutacion, ClearPetsRequired):
                return OperacionMascotas.RETIRAR

    for a in afirmaciones:
        if isinstance(a, AfirmacionAmbiguous) and a.campo is BuyerFieldV0.PETS_REQUIRED:
            return OperacionMascotas.NO_COMPARABLE

    return None


def operacion_de_la_memoria(contexto) -> OperacionMascotas:
    """Qué dice la memoria efectiva del comprador sobre mascotas.

    Una pregunta abierta sobre la ruta se comprueba PRIMERO: un valor acompañado de una
    incertidumbre declarada no es una afirmación de la que se pueda partir.
    """
    if contexto is None:
        return OperacionMascotas.SIN_SENAL

    abiertas = getattr(contexto, "unresolved_questions", ()) or ()
    if any(q.about_field == _RUTA_PETS for q in abiertas):
        return OperacionMascotas.NO_COMPARABLE

    valor = contexto.property_requirements.pets_allowed_required
    if valor is True:
        return OperacionMascotas.REQUERIR

    evidencias = getattr(contexto, "field_evidence", ()) or ()
    hay_evidencia = any(fe.field == _RUTA_PETS for fe in evidencias)
    # Valor `None` CON evidencia = retirada explícita. Sin evidencia = nunca se pronunció.
    return OperacionMascotas.RETIRAR if hay_evidencia else OperacionMascotas.SIN_SENAL


_SILENCIO_LEGITIMO = frozenset({DesenlaceCandidato.SIN_AFIRMACIONES})
"""El ÚNICO desenlace que significa «el turno no afirmó nada sobre el comprador».

`FALLO`, `SIN_MENSAJE`, `SIN_PRINCIPAL` y `FUERA_DE_COHORTE` NO son silencio: son que no
sabemos qué pasó. Usar la memoria persistida como sustituto ahí sería fingir que conocemos
el estado del turno.
"""


# ── Aplicación · UNA clave, escrita a mano ────────────────────────────────────────


def aplicar_operacion(legacy: dict, operacion: OperacionMascotas) -> dict:
    """Las preferencias del turno con el requisito de mascotas alterado. **Copia nueva.**

    Una operación por campo, no un `update(proyeccion)`: reconstruible a mano —valor legacy,
    operación, valor resultante— que es lo que permite atribuir el delta.
    """
    sombra = dict(legacy or {})
    if operacion is OperacionMascotas.REQUERIR:
        sombra[_CLAVE_LEGACY] = True
    elif operacion is OperacionMascotas.RETIRAR:
        sombra.pop(_CLAVE_LEGACY, None)
    return sombra


# ── Métricas · las de R0E, sobre el universo COMPLETO ─────────────────────────────


def _ejes(cards, descartadas):
    todas = list(cards or ()) + list(descartadas or ())
    return {
        "orden": [c["id"] for c in (cards or ())],
        "descartadas": {c["id"] for c in (descartadas or ())},
        "encaje": {c["id"]: c.get("encaje") for c in todas},
        "cobertura": {c["id"]: c.get("encaje_cobertura") for c in todas},
    }


def medir(cards_v, desc_v, cards_s, desc_s) -> dict:
    """Deterministas y sin agregados inventados. No hay «quality score»: un número único
    escondería de dónde salió la diferencia y empujaría a leerla como una mejora."""
    v, s = _ejes(cards_v, desc_v), _ejes(cards_s, desc_s)
    pos_v = {a: i for i, a in enumerate(v["orden"])}
    pos_s = {a: i for i, a in enumerate(s["orden"])}
    comunes = set(pos_v) & set(pos_s)
    universo = set(v["encaje"]) & set(s["encaje"])

    def _dif(mapa_v, mapa_s):
        return sum(1 for a in universo
                   if mapa_v[a] is not None and mapa_s[a] is not None
                   and mapa_v[a] != mapa_s[a])

    return {
        "mismo_orden": v["orden"] == s["orden"],
        "top1_cambio": (v["orden"][:1] or [None]) != (s["orden"][:1] or [None]),
        "top3_solape": len(set(v["orden"][:3]) & set(s["orden"][:3])),
        "visibles": len(v["orden"]),
        "sombra": len(s["orden"]),
        # Un activo que sale de la rejilla NO es un filtro duro nuevo: es consecuencia del
        # score y del corte que ya existía. R0E lo midió; aquí sólo se cuenta.
        "movimientos_de_rejilla": len(s["descartadas"] - v["descartadas"]),
        "movimientos_de_posicion": sum(1 for a in comunes if pos_v[a] != pos_s[a]),
        "deltas_de_score": _dif(v["encaje"], s["encaje"]),
        "deltas_de_cobertura": _dif(v["cobertura"], s["cobertura"]),
        "mismo_universo": set(v["encaje"]) == set(s["encaje"]),
    }


def clasificar_delta(legacy: dict, sombra_prefs: dict, metricas: dict) -> ClaseDelta:
    """`DELTA_ESPERADO` exige las tres condiciones: mismo universo, exactamente una
    preferencia alterada, y que la diferencia salga del propio motor."""
    cambiadas = {k for k in set(legacy or {}) | set(sombra_prefs or {})
                 if (legacy or {}).get(k, _AUSENTE) != (sombra_prefs or {}).get(k, _AUSENTE)}
    if cambiadas - {_CLAVE_LEGACY}:
        return ClaseDelta.DELTA_INESPERADO
    if not metricas["mismo_universo"]:
        return ClaseDelta.DELTA_INESPERADO
    sin_cambio = (metricas["mismo_orden"] and not metricas["deltas_de_score"]
                  and not metricas["deltas_de_cobertura"]
                  and not metricas["movimientos_de_rejilla"])
    return ClaseDelta.SIN_DELTA if sin_cambio else ClaseDelta.DELTA_ESPERADO


_AUSENTE = object()


def relacion_de_persistencia(estado, *, updater_encendido: bool) -> RelacionPersistencia:
    """Cómo terminó la escritura respecto del estado con el que se comparó.

    Nunca sustituye retrospectivamente lo observado por lo finalmente persistido: si hubo
    rebase, la comparación sigue siendo válida para la decisión del turno y lo que se
    registra es que divergieron.
    """
    from app.buyer.actualizador import EstadoActualizacion

    if not updater_encendido:
        return RelacionPersistencia.NO_INTENTADA
    if estado is None:
        return RelacionPersistencia.NO_OBSERVABLE
    if estado in (EstadoActualizacion.CREADA, EstadoActualizacion.REPLAY,
                  EstadoActualizacion.NO_OP):
        return RelacionPersistencia.ALINEADA
    if estado is EstadoActualizacion.VACIO:
        # No se intentó escribir porque no había nada que escribir. No es un fallo.
        return RelacionPersistencia.NO_INTENTADA
    return RelacionPersistencia.DIVERGIDA


# ── Orquestación ──────────────────────────────────────────────────────────────────


def _no_comparable(captura: ClaseCaptura, arranque: float, *, lecturas: int = 0,
                   operacion: OperacionMascotas = OperacionMascotas.NO_COMPARABLE,
                   fuente: FuenteDelEstado = FuenteDelEstado.NINGUNA,
                   relacion: RelacionPersistencia = RelacionPersistencia.NO_INTENTADA):
    return ObservacionSombra(
        operacion=operacion, fuente=fuente, captura=captura,
        delta=ClaseDelta.NO_COMPARABLE, relacion_persistencia=relacion,
        lecturas_del_comprador=lecturas, corridas_del_nucleo=0,
        duracion_ms=int((time.monotonic() - arranque) * 1000))


def habilitado(user) -> bool:
    """Las cuatro puertas, en orden y ANTES de gastar nada.

    Se comprueban de la más barata a la más cara para que un turno no habilitado no consuma
    ni una lectura ni una corrida. El updater NO es requisito: comparar no exige permiso de
    escritura.
    """
    from app.buyer.sombra import _habilitados

    if not getattr(settings, "buyer_shadow_decision_compare", False):
        return False
    if not settings.buyer_current_turn_candidate_shadow:
        return False
    uid = (getattr(user, "user_id", "") or "").strip() if user is not None else ""
    if not uid:
        return False
    return uid.strip().lower() in _habilitados()


async def observar_sombra_de_decision(
        user, *, desenlace_candidato, computo, cards, descartadas, preferencias,
        messages, session_id, estado_persistencia=None,
        leer_memoria=None) -> ObservacionSombra | None:
    """Calcula qué habría cambiado sólo por la memoria de mascotas. **No decide nada.**

    Devuelve `None` cuando la capacidad está apagada — que es el estado por defecto y el de
    todo despliegue hoy. El turno no paga absolutamente nada en ese caso.

    Args:
        user: el `CurrentUser` de la frontera autenticada. El objeto original, nunca uno
            reconstruido: la lectura de memoria se hace con él.
        desenlace_candidato, computo: lo que R0B/R0C ya calcularon, recibido POR PIEZAS.
            La `ObservacionCandidato` no viaja entera a propósito: R0B congeló que el
            objeto no se pasa a nadie, y esa propiedad protege de que alguien acabe
            leyéndole el desenlace o la duración para decidir con ellos.
        cards, descartadas: el artefacto VISIBLE, tal cual salió del estado. No se recalcula.
        preferencias: las legacy del turno. Base del contrafactual; se copia antes de tocar.
        estado_persistencia: el desenlace del updater si el llamante lo conoce. Hoy no lo
            conoce —ver `RelacionPersistencia.NO_OBSERVABLE`— y se pasa `None`.
        leer_memoria: inyectable para las pruebas; por defecto la lectura de 1A.
    """
    if not habilitado(user):
        return None

    arranque = time.monotonic()
    updater_on = bool(getattr(settings, "buyer_updater_shadow", False))
    relacion = relacion_de_persistencia(estado_persistencia, updater_encendido=updater_on)

    # ── PUERTA 5 · la captura tiene que corresponder al panel que se vio ──────────
    caja = caja_actual()
    correspondencia = cotejar(caja, {"cards": cards or [], "descartadas": descartadas or []})
    if correspondencia is not Correspondencia.COINCIDE:
        return _no_comparable(_CLASE_DE_CAPTURA[correspondencia], arranque,
                              relacion=relacion)

    # ── La operación · turno primero, memoria después, y nunca al revés ───────────
    desenlace = desenlace_candidato
    candidato = getattr(computo, "candidato", None) if computo is not None else None

    operacion = operacion_del_turno(getattr(candidato, "lote", None))
    fuente = FuenteDelEstado.TURNO_ACTUAL
    lecturas = 0

    if operacion is None:
        # El turno no habló de mascotas. Sólo entonces se mira la memoria — y sólo si el
        # candidato dice que el turno calló de verdad.
        if candidato is not None:
            contexto = candidato.contexto
        elif desenlace in _SILENCIO_LEGITIMO:
            contexto = await (leer_memoria or _leer_memoria)(user)
            lecturas = 1
        else:
            # `FALLO`, `SIN_MENSAJE`, … no son silencio: no sabemos qué pasó en el turno.
            return _no_comparable(ClaseCaptura.COINCIDE, arranque, relacion=relacion)

        operacion = operacion_de_la_memoria(contexto)
        fuente = (FuenteDelEstado.MEMORIA_PERSISTIDA
                  if operacion is not OperacionMascotas.SIN_SENAL
                  else FuenteDelEstado.NINGUNA)

    if operacion is OperacionMascotas.NO_COMPARABLE:
        return _no_comparable(ClaseCaptura.COINCIDE, arranque, lecturas=lecturas,
                              fuente=fuente, relacion=relacion)

    # ── UNA corrida del núcleo, sobre LAS MISMAS filas ───────────────────────────
    sombra_prefs = aplicar_operacion(preferencias or {}, operacion)
    entradas = caja.entradas
    panel_sombra = _decidir_desde_filas(
        entradas.rows, entradas.curaciones, ids=entradas.ids,
        preferencias=sombra_prefs, messages=messages, session_id=session_id)

    metricas = medir(cards, descartadas, panel_sombra["cards"], panel_sombra["descartadas"])
    return ObservacionSombra(
        operacion=operacion, fuente=fuente, captura=ClaseCaptura.COINCIDE,
        delta=clasificar_delta(preferencias or {}, sombra_prefs, metricas),
        relacion_persistencia=relacion,
        top1_cambio=metricas["top1_cambio"], top3_solape=metricas["top3_solape"],
        visibles=metricas["visibles"], sombra=metricas["sombra"],
        movimientos_de_rejilla=metricas["movimientos_de_rejilla"],
        movimientos_de_posicion=metricas["movimientos_de_posicion"],
        deltas_de_score=metricas["deltas_de_score"],
        deltas_de_cobertura=metricas["deltas_de_cobertura"],
        lecturas_del_comprador=lecturas, corridas_del_nucleo=1,
        duracion_ms=int((time.monotonic() - arranque) * 1000))


_CLASE_DE_CAPTURA = {
    Correspondencia.COINCIDE: ClaseCaptura.COINCIDE,
    Correspondencia.NO_COINCIDE: ClaseCaptura.NO_COINCIDE,
    Correspondencia.VACIA: ClaseCaptura.VACIA,
    Correspondencia.SIN_CAPTURA: ClaseCaptura.AUSENTE,
}


async def _leer_memoria(user):
    from app.buyer.lectura import leer_contexto_del_principal

    return await leer_contexto_del_principal(user)


def registrar(observacion: ObservacionSombra | None) -> None:
    """El rastro. Clases y conteos; nada del comprador ni del inventario.

    Sin preferencias crudas, sin tarjetas, sin ids de activo: lo que se quiere saber es qué
    CLASE de cosa pasó y cuánto costó, y para eso los identificadores no hacen falta.
    """
    if observacion is None:
        return
    o = observacion
    logger.info(
        "buyer decision shadow · campo=%s operacion=%s fuente=%s captura=%s delta=%s "
        "persistencia=%s top1=%s top3=%s visibles=%s sombra=%s rejilla=%s posicion=%s "
        "score=%s cobertura=%s lecturas=%s corridas=%s ms=%s",
        o.campo, o.operacion.value, o.fuente.value, o.captura.value, o.delta.value,
        o.relacion_persistencia.value, o.top1_cambio, o.top3_solape, o.visibles, o.sombra,
        o.movimientos_de_rejilla, o.movimientos_de_posicion, o.deltas_de_score,
        o.deltas_de_cobertura, o.lecturas_del_comprador, o.corridas_del_nucleo,
        o.duracion_ms)
