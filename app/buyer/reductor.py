"""E3.2b.2 · Buyer Reducer V0 — el lote se convierte en memoria.

```
BuyerContextV0 base  +  LoteExtraccion ya resuelto  +  cuándo se procesó
        ↓
BuyerContextV0 nuevo
```

Es la primera capa de la fase que **escribe**. Todo lo anterior decidía qué se puede escribir
—la frontera—, qué dijo el usuario —el intérprete— y qué de eso está acreditado —la guarda—.
Aquí eso se vuelve estado.

## Puro, y la lista de lo que eso excluye es la parte útil

```
sin reloj      `retrieved_at` ENTRA COMO DATO. El reducer no llama a now().
sin random     `evidence_id` se deriva; no hay uuid4 aquí dentro.
sin base       no lee ni escribe; el store es de E3.1b y ya existe.
sin modelo     el lote ya viene interpretado y acreditado.
```

Un reducer con reloj o con azar no se puede reproducir, y un estado que no se puede
reproducir no se puede auditar — que es exactamente lo que esta fase entera existe para
sostener.

## R-IDEMP-1 · por qué `retrieved_at` entra como argumento

El contrato exige un `retrieved_at` REAL en cada `EvidenceRefV0`: es cuándo lo procesamos
nosotros, y eso siempre se sabe. Pero no es estable entre reintentos, y no tiene por qué
serlo:

```
primer procesamiento   retrieved_at = T1  →  se crea la revisión, T1 queda en historia
reintento              retrieved_at = T2  →  la igualdad canónica ignora T2 para
                                              USER_DECLARED, el store reconoce el replay
                                              y devuelve la revisión original. T1 se queda.
```

No hace falta que sea estable. Hace falta que sea **verdadero** y que no se confunda con
estado del comprador. El reloj vive en el llamante; aquí sólo llega el dato.

## Los cuatro conceptos que esto deja de mezclar

```
observed_at    cuándo el mundo estaba así      hoy None: no tenemos esa evidencia
retrieved_at   cuándo lo procesamos nosotros   verdadero, operacional, entra como dato
evidence_id    asa nuestra sobre la evidencia  determinista (uuid5)
valor + ruta   estado durable del comprador    lo único que la idempotencia compara
```

## Lo que NO hace

No decide novedad, no escribe en la base, no habla con el producto y no formula la
repregunta. Crea `unresolved_questions` para que la incertidumbre **sobreviva**; que alguien
la consuma y repregunte es wiring posterior, y hasta que eso exista el ciclo no está cerrado.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.buyer.boundary import (
    BuyerFieldV0,
    ClearAreaM2Min,
    ClearBedroomsMin,
    ClearBudgetMax,
    ClearObjective,
    ClearPetsRequired,
    SetAreaM2Min,
    SetBedroomsMin,
    SetBudgetMax,
    SetObjective,
    SetPetsRequired,
    campo_de_mutacion,
    ruta_contractual,
)
from app.buyer.extractor import AfirmacionAmbiguous, AfirmacionDurable
from app.contracts.buyer_v0 import (
    BuyerContextV0,
    FieldEvidence,
    Objective,
    UnresolvedQuestion,
)
from app.contracts.common_v0 import Money
from app.contracts.evidence_v0 import EvidenceRefV0, PersistencePolicy, SourceType


class ReduccionImposible(RuntimeError):
    """Una mutación del lote no se pudo aplicar. **No se produce contexto parcial.**

    R1: el lote es atómico. Un `skip` silencioso dejaría un estado que no corresponde ni a lo
    que el usuario dijo ni a lo que había antes, y nadie se enteraría — que es peor que
    fallar. Si esto se levanta, el defecto está aguas arriba: algo llegó como mutación válida
    y no lo era.
    """


# ── La identidad de la evidencia ───────────────────────────────────────────────────

_NAMESPACE_EVIDENCIA = uuid.uuid5(uuid.NAMESPACE_URL,
                                  "contexto.ai/buyer/evidence/user_declared/v0")
"""Namespace versionado. Va en la identidad para que un cambio futuro del esquema de
derivación no produzca colisiones con los ids ya persistidos."""


def evidence_id_determinista(buyer_id: str, source_message_id: str, ruta: str) -> str:
    """`uuid5` sobre *(comprador, mensaje, ruta)*. **Sin el valor, y es deliberado.**

    La identidad representa *"la evidencia de este mensaje para este campo"*. Si un replay del
    mismo mensaje produjera otro valor, queremos el MISMO id de evidencia y un contexto
    semánticamente distinto — así la idempotencia ve la divergencia en vez de disimularla
    detrás de dos identificadores diferentes.

    Que `evidence_id` ya no participe en la comparación canónica no lo hace irrelevante:
    seguir generándolo al azar dejaría un asa distinta en cada intento, y cualquier consumidor
    futuro que sí la mire heredaría el problema que acabamos de cerrar.
    """
    return str(uuid.uuid5(_NAMESPACE_EVIDENCIA, f"{buyer_id}\x1f{source_message_id}\x1f{ruta}"))


def _evidencia(buyer_id: str, source_message_id: str, ruta: str,
               retrieved_at: datetime) -> EvidenceRefV0:
    """La procedencia de un campo que el usuario declaró.

    `observed_at=None` es una afirmación, no un hueco por descuido: significa *"el origen no
    dice de cuándo es"*. No tenemos timestamp del evento del mensaje —el checkpointer no nos
    da uno contractual— y ponerle `retrieved_at` sería exactamente la mentira que
    `EvidenceRefV0` documenta como el error de E0.3.
    """
    return EvidenceRefV0(
        evidence_id=evidence_id_determinista(buyer_id, source_message_id, ruta),
        source_type=SourceType.USER_DECLARED,
        source_id=source_message_id,
        methodology="declaración explícita del comprador en la conversación, acreditada por "
                    "la guarda de evidencia exacta de E3.2b.1a",
        persistence_policy=PersistencePolicy.PERSISTABLE,
        observed_at=None,
        retrieved_at=retrieved_at,
    )


# ── Aplicar UNA mutación ───────────────────────────────────────────────────────────
#
# R2 · EXHAUSTIVIDAD. Las diez variantes tienen entrada explícita y hay un meta-test de
# totalidad contra la unión. Un miembro nuevo rompe ese test hasta que alguien decida qué
# hace el reducer con él — que es lo contrario de heredarlo por descuido.
#
# R3 · los `Clear*` devuelven el campo a su AUSENCIA, nunca a otro valor. `ClearObjective` va
# a `UNKNOWN` porque el contrato no admite `None` ahí, y `UNKNOWN` ES la ausencia de
# declaración; el resto va a `None`.


def _set_objective(datos, mutacion) -> None:
    datos["objective"] = mutacion.objective


def _clear_objective(datos, _mutacion) -> None:
    datos["objective"] = Objective.UNKNOWN


def _set_budget(datos, mutacion) -> None:
    datos["financial"] = datos["financial"].model_copy(
        update={"budget_max": Money(amount=mutacion.amount,
                                    currency=mutacion.currency.value)})


def _clear_budget(datos, _mutacion) -> None:
    datos["financial"] = datos["financial"].model_copy(update={"budget_max": None})


def _requisitos(datos, **cambio) -> None:
    datos["property_requirements"] = datos["property_requirements"].model_copy(update=cambio)


_APLICADORES = {
    SetObjective: _set_objective,
    ClearObjective: _clear_objective,
    SetBudgetMax: _set_budget,
    ClearBudgetMax: _clear_budget,
    SetBedroomsMin: lambda d, m: _requisitos(d, bedrooms_min=m.bedrooms_min),
    ClearBedroomsMin: lambda d, _m: _requisitos(d, bedrooms_min=None),
    SetAreaM2Min: lambda d, m: _requisitos(d, area_m2_min=m.area_m2_min),
    ClearAreaM2Min: lambda d, _m: _requisitos(d, area_m2_min=None),
    SetPetsRequired: lambda d, _m: _requisitos(d, pets_allowed_required=True),
    ClearPetsRequired: lambda d, _m: _requisitos(d, pets_allowed_required=None),
}
"""Total sobre `BuyerMutationV0`, comprobado por meta-test."""


# ── El reducer ─────────────────────────────────────────────────────────────────────


def _pregunta_de(campo: BuyerFieldV0) -> str:
    """Texto DETERMINISTA por dimensión. **No se persiste el `motivo` del modelo.**

    R6: el motivo es prosa libre de un proponente no determinista; guardarlo como el texto de
    la pregunta haría que dos procesamientos del mismo mensaje produjeran estados distintos, y
    la idempotencia lo denunciaría con razón. La pregunta es del producto, no del modelo.
    """
    return {
        BuyerFieldV0.OBJECTIVE: "¿Buscas comprar, alquilar o invertir?",
        BuyerFieldV0.BUDGET_MAX: "¿Cuál es tu presupuesto máximo, y en qué moneda?",
        BuyerFieldV0.BEDROOMS_MIN: "¿Cuántos dormitorios necesitas como mínimo?",
        BuyerFieldV0.AREA_M2_MIN: "¿Cuántos metros cuadrados necesitas como mínimo?",
        BuyerFieldV0.PETS_REQUIRED: "¿Necesitas que el inmueble admita mascotas?",
    }[campo]


def reducir(contexto: BuyerContextV0, lote, retrieved_at: datetime) -> BuyerContextV0:
    """Aplica el lote sobre el contexto base y devuelve el contexto nuevo.

    El `buyer_id` sale del contexto y el `source_message_id` del lote; ninguno se fabrica.
    `retrieved_at` llega de fuera — ver R-IDEMP-1 arriba.

    Orden de las reglas, que importa porque interactúan:

    ```
    R1  atómico: se construye todo o se levanta ReduccionImposible
    R4  TURN_ONLY y REJECTED no tocan el contexto — su sitio es el trace, no la memoria
    R5  AMBIGUOUS no aplica ni borra: abre pregunta. Nunca se vuelve un Clear encubierto
    R7  la ruta sale de `ruta_contractual`, jamás del modelo
    ```

    **R5 es la que hay que leer despacio.** Una ambigüedad sobre un campo que ya tiene valor
    NO lo borra: sólo una retractación explícita autorizó los `Clear*`, y convertir "no estoy
    seguro de lo que dijo" en "bórralo" sería perder estado declarado por una duda del
    intérprete. El valor se queda y la pregunta se abre junto a él.
    """
    datos = {
        "objective": contexto.objective,
        "financial": contexto.financial,
        "property_requirements": contexto.property_requirements,
    }

    durables = [a for a in lote.afirmaciones if isinstance(a, AfirmacionDurable)]
    ambiguas = [a for a in lote.afirmaciones if isinstance(a, AfirmacionAmbiguous)]

    evidencias: list[FieldEvidence] = []
    for afirmacion in durables:
        aplicar = _APLICADORES.get(type(afirmacion.mutacion))
        if aplicar is None:
            raise ReduccionImposible(
                f"sin aplicador para {type(afirmacion.mutacion).__name__}: el lote trae una "
                f"mutación que este reducer no sabe escribir")
        try:
            aplicar(datos, afirmacion.mutacion)
        except Exception as e:  # noqa: BLE001 — R1: se levanta, no se salta
            raise ReduccionImposible(
                f"{type(afirmacion.mutacion).__name__} no se pudo aplicar: {e}") from e
        ruta = ruta_contractual(afirmacion.mutacion)
        evidencias.append(FieldEvidence(
            field=ruta,
            evidence=_evidencia(contexto.buyer_id, lote.source_message_id, ruta,
                                retrieved_at)))

    resueltas = {campo_de_mutacion(a.mutacion) for a in durables}
    abiertas = {a.campo for a in ambiguas} - resueltas

    return contexto.model_copy(update={
        **datos,
        "field_evidence": _fusionar_evidencia(contexto.field_evidence, evidencias),
        "unresolved_questions": _fusionar_preguntas(
            contexto.unresolved_questions, abiertas, resueltas),
    })


def _fusionar_evidencia(previa, nuevas) -> tuple[FieldEvidence, ...]:
    """La evidencia VIGENTE de una ruta es la que sostiene el valor vigente.

    R7: cuando un campo se actualiza, su evidencia anterior se reemplaza — no se acumula. La
    revisión histórica ya conserva la anterior junto al valor que sostenía, y dejar las dos en
    el mismo snapshot afirmaría que una declaración vieja respalda un valor nuevo, que es
    falso.

    Varias rutas SÍ pueden citar el mismo `source_message_id`: un mensaje puede justificar
    tres campos, y el contrato lo admite porque `field_evidence` es una tupla.
    """
    reemplazadas = {fe.field for fe in nuevas}
    conservadas = [fe for fe in previa if fe.field not in reemplazadas]
    return tuple(conservadas) + tuple(nuevas)


def _fusionar_preguntas(previas, abiertas, resueltas) -> tuple[UnresolvedQuestion, ...]:
    """Abre las nuevas, cierra las que una durable resolvió, y no duplica.

    Se identifica por `about_field`, no por el texto: dos formulaciones de la misma pregunta
    son la misma pregunta, y comparar prosa las duplicaría.
    """
    rutas_resueltas = {_RUTA_DE_CAMPO[c] for c in resueltas}
    vivas = [q for q in previas if q.about_field not in rutas_resueltas]
    ya = {q.about_field for q in vivas}
    for campo in sorted(abiertas, key=lambda c: c.value):
        ruta = _RUTA_DE_CAMPO[campo]
        if ruta not in ya:
            vivas.append(UnresolvedQuestion(question=_pregunta_de(campo), about_field=ruta))
    return tuple(vivas)


_RUTA_DE_CAMPO: dict[BuyerFieldV0, str] = {
    campo_de_mutacion(m()): ruta_contractual(m())
    for m in (ClearObjective, ClearBudgetMax, ClearBedroomsMin, ClearAreaM2Min,
              ClearPetsRequired)
}
"""Dimensión → ruta del contrato, derivado de las funciones que ya son autoridad de cada una.

Escribirlo a mano sería una tercera copia del mapeo, y la que se desincronizaría primero."""


def ruta_de_campo(campo: BuyerFieldV0) -> str:
    """La ruta contractual de una dimensión, para quien tiene el campo y no la mutación.

    Lo necesita el orquestador: una `AMBIGUOUS` lleva `BuyerFieldV0` y ninguna mutación, y
    aun así reclama su ruta a efectos de concurrencia."""
    return _RUTA_DE_CAMPO[campo]
