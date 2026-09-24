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
from decimal import Decimal

from app.buyer.boundary import (
    CAMPOS_CON_CRITERIO,
    BuyerFieldV0,
    ClearAreaM2Min,
    ClearBedroomsMin,
    ClearBudgetMax,
    ClearObjective,
    ClearPetsRequired,
    RigidezV0,
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
    CriterionOrigin,
    CriterionStatus,
    DecisionCriterionV0,
    FieldEvidence,
    Objective,
    Operator,
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


_METODOLOGIA_VALOR = ("declaración explícita del comprador en la conversación, acreditada por "
                      "la guarda de evidencia exacta de E3.2b.1a")


def _evidencia(buyer_id: str, source_message_id: str, ruta: str,
               retrieved_at: datetime, methodology: str = _METODOLOGIA_VALOR
               ) -> EvidenceRefV0:
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
        methodology=methodology,
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

    E3.3 · `hard_constraints` y `soft_preferences` se derivan AL FINAL, del estado ya
    reducido y de las rigideces del lote (R8-R12, junto a `_proyectar_criterios`). Van en la
    misma revisión que el valor que describen: un criterio no puede ir por detrás de su campo.
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

    # E3.3-R2 · una rigidez sólo mueve un criterio que tiene VALOR vigente y cuyo valor no
    # quedó en duda en este mismo mensaje. *"Ahora puedo hasta mil dólares, el presupuesto es
    # innegociable"*: si "mil" no se acredita, la rigidez NO se pega al valor viejo que la
    # persona estaba abandonando. Y sin valor, la rigidez abre la pregunta de su dimensión en
    # vez de perderse en silencio.
    sin_valor = {d.campo for d in lote.rigideces
                 if _valor_y_unidad(d.campo, datos) is None} - resueltas
    abiertas |= sin_valor
    rigidez_aplicable = {d.campo: d.rigidez for d in lote.rigideces
                         if d.campo not in abiertas}
    tocados = ({campo_de_mutacion(a.mutacion) for a in durables}
               | {a.campo for a in ambiguas} | {d.campo for d in lote.rigideces})

    field_evidence = _fusionar_evidencia(contexto.field_evidence, evidencias)
    duras, blandas = _proyectar_criterios(
        contexto, datos, field_evidence, rigidez_aplicable, tocados,
        lote.source_message_id, retrieved_at)

    return contexto.model_copy(update={
        **datos,
        "field_evidence": field_evidence,
        "unresolved_questions": _fusionar_preguntas(
            contexto.unresolved_questions, abiertas, resueltas),
        "hard_constraints": duras,
        "soft_preferences": blandas,
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


# ── E3.3 · los criterios: `hard_constraints` y `soft_preferences` ───────────────────
#
# **Se DERIVAN; ninguna mutación los escribe.** Un criterio es la forma EVALUABLE de un valor
# que la persona declaró —el mismo presupuesto, como `price <= 900 USD`— más una decisión
# sobre cómo usarlo: si descalifica o si sólo ordena. El valor lo sostiene su mutación y su
# `FieldEvidence`; la rigidez, una declaración propia. Derivar de ahí, en vez de dejar que
# algo escriba criterios, es lo que mantiene los dos sitios coherentes: no hay forma de que el
# presupuesto diga 900 y su criterio 1000.
#
# ```
# R8   hard SÓLO con rigidez ESTRICTA declarada y acreditada — regla 2 del Execution Plan
# R9   sin declaración, `soft_preferences`: ordena, no excluye
# R10  la rigidez es de la DIMENSIÓN y se conserva al cambiar el valor, hasta que otra la corrija
#      — mientras el criterio sigue VIGENTE. Tras un retiro, un valor nuevo nace sin rigidez.
# R11  un Clear* no borra el criterio: lo deja RETRACTED, con su evidencia y la del retiro
# R12  todo criterio es `origin=STATED`: valor y rigidez vienen de la persona, nunca inferidos
# R13  sólo se re-proyectan las dimensiones que el lote TOCA; las demás se arrastran tal cual
# ```
#
# R13 es de E3.3-R2. Proyectar las cuatro en cada reducción rellenaba en silencio los
# criterios de las revisiones escritas antes de E3.3: el primer "gracias" dejaba de ser un
# NO_OP, y una segunda conversación que tocaba otra dimensión acababa en CONFLICTO espurio y
# perdía lo que la persona declaró. Los criterios de un comprador antiguo aparecen ahora a
# medida que cada dimensión se vuelve a tocar.
#
# R10 es la que se puede discutir. *"Máximo 900 USD, innegociable"* y después *"mejor 950"*:
# la persona corrigió el número, no la rigidez, y soltarla en silencio la cambiaría sin que
# nadie la declarase — lo contrario de lo que R8 existe para impedir. La evidencia de la
# rigidez sigue en el criterio, así que se ve de qué mensaje sale.

_CODIGO_RIGIDEZ: dict[RigidezV0, str] = {
    RigidezV0.ESTRICTA: "[rigidez:estricta]",
    RigidezV0.FLEXIBLE: "[rigidez:flexible]",
}
"""**Identificadores PERSISTIDOS.** El papel de cada evidencia dentro de un criterio —sostiene
la rigidez o el valor— se reconoce por este prefijo de `methodology`, no por la prosa que lo
sigue. E3.3 comparaba la frase entera: corregir una tilde de la redacción habría dejado a todo
comprador con un criterio duro sin rigidez reconocible, y R8 habría congelado su memoria.
Cambiar un código exige migrar las revisiones; hay test que lo recuerda."""

_METODOLOGIA_RIGIDEZ: dict[RigidezV0, str] = {
    RigidezV0.ESTRICTA: (f"{_CODIGO_RIGIDEZ[RigidezV0.ESTRICTA]} declaración explícita del "
                         "comprador de que el requisito es indispensable, acreditada por la "
                         "guarda de rigidez de E3.3"),
    RigidezV0.FLEXIBLE: (f"{_CODIGO_RIGIDEZ[RigidezV0.FLEXIBLE]} declaración explícita del "
                         "comprador de que el requisito es flexible, acreditada por la guarda "
                         "de rigidez de E3.3"),
}

_FORMA: dict[BuyerFieldV0, tuple[str, Operator]] = {
    BuyerFieldV0.BUDGET_MAX: ("price", Operator.LTE),
    BuyerFieldV0.BEDROOMS_MIN: ("bedrooms", Operator.GTE),
    BuyerFieldV0.AREA_M2_MIN: ("area_m2", Operator.GTE),
    BuyerFieldV0.PETS_REQUIRED: ("pets_allowed", Operator.EQ),
}
"""Qué se compara contra el INMUEBLE, con el vocabulario del material de PLAN04-1.6
(`bedrooms`, `area_m2`, `pets_allowed`). Total sobre la whitelist, comprobado por test.

El presupuesto se compara contra `price`, no contra `budget`: el criterio describe lo que el
inmueble tiene que cumplir, y el inmueble no tiene presupuesto."""


def _monto(amount: Decimal) -> int | float:
    """`Money.amount` es `Decimal` y `CriterionValue` no lo admite. **Sin pérdida o nada.**

    Entero si es entero —lo único que la guarda de E3.2b.1a sabe acreditar—. Si trae
    decimales, `float` sólo cuando vuelve al mismo `Decimal`; si no, se levanta: un tope que
    cambia de valor al volverse criterio es un criterio que ya no es lo que la persona dijo.
    """
    if amount == amount.to_integral_value():
        return int(amount)
    como_float = float(amount)
    if Decimal(str(como_float)) != amount:
        raise ReduccionImposible(
            f"el presupuesto {amount} no se representa como criterio sin perder exactitud")
    return como_float


def _valor_y_unidad(campo: BuyerFieldV0, datos) -> tuple | None:
    """El valor vigente de la dimensión, ya con la forma del criterio. `None` = ausente."""
    if campo is BuyerFieldV0.BUDGET_MAX:
        tope = datos["financial"].budget_max
        return None if tope is None else (_monto(tope.amount), tope.currency)
    requisitos = datos["property_requirements"]
    if campo is BuyerFieldV0.BEDROOMS_MIN:
        v = requisitos.bedrooms_min
        return None if v is None else (v, None)
    if campo is BuyerFieldV0.AREA_M2_MIN:
        v = requisitos.area_m2_min
        return None if v is None else (v, "m2")
    if campo is BuyerFieldV0.PETS_REQUIRED:
        return (True, None) if requisitos.pets_allowed_required is True else None
    raise ReduccionImposible(f"{campo} no tiene forma de criterio")  # pragma: no cover


def _criterios_previos(contexto: BuyerContextV0) -> dict[BuyerFieldV0, tuple[bool, object]]:
    """Los criterios de la base, por dimensión, con la lista en la que vivían.

    **Fail closed ante lo que este reducer no sabe mantener.** Un criterio fuera de la
    whitelist —por dimensión o por identidad— no se arrastra ni se borra: se levanta. Es la
    garantía de que ningún contexto que salga de aquí lleva un criterio sobre algo que no sea
    un requisito del inmueble, venga de donde venga la base.
    """
    previos: dict[BuyerFieldV0, tuple[bool, object]] = {}
    for duro, lista in ((True, contexto.hard_constraints), (False, contexto.soft_preferences)):
        for criterio in lista:
            campo = next((c for c in CAMPOS_CON_CRITERIO if c.value == criterio.criterion_id),
                         None)
            if campo is None or criterio.dimension != _FORMA[campo][0]:
                raise ReduccionImposible(
                    f"criterio {criterio.criterion_id!r} sobre {criterio.dimension!r} fuera "
                    f"de la whitelist de E3.3: este reducer no escribe lo que no sabe mantener")
            previos[campo] = (duro, criterio)
    return previos


def rigidez_de_evidencia(evidencia: EvidenceRefV0) -> RigidezV0 | None:
    """La rigidez que sostiene esta evidencia de un criterio, o `None` si sostiene el valor."""
    return next((r for r, codigo in _CODIGO_RIGIDEZ.items()
                 if evidencia.methodology.startswith(codigo)), None)


def es_evidencia_de_rigidez(evidencia: EvidenceRefV0) -> bool:
    """¿Esta evidencia de un criterio sostiene su RIGIDEZ, y no su valor? Lo necesita también
    el orquestador, para ver si otra conversación cambió la rigidez de una ruta."""
    return rigidez_de_evidencia(evidencia) is not None


def _proyectar_criterios(contexto, datos, field_evidence, rigidez_aplicable, tocados,
                         source_message_id, retrieved_at) -> tuple[tuple, tuple]:
    """El estado vigente de cada dimensión de la whitelist → `(duras, blandas)`.

    Se recorre en el orden de `CAMPOS_CON_CRITERIO`, así que las tuplas salen siempre en el
    mismo orden: dos reducciones del mismo lote no pueden diferir sólo en cómo se ordenaron.

    `tocados` son las dimensiones del lote (R13); las demás se arrastran como estaban.
    `rigidez_aplicable` ya viene filtrada por `reducir`: sólo dimensiones con valor vigente y
    sin duda abierta en este mensaje.
    """
    buyer_id = contexto.buyer_id
    previos = _criterios_previos(contexto)
    evidencia_de_ruta = {fe.field: fe.evidence for fe in field_evidence}

    duras, blandas = [], []
    for campo in CAMPOS_CON_CRITERIO:
        duro_previo, previo = previos.get(campo, (False, None))
        if campo not in tocados:
            if previo is not None:
                (duras if duro_previo else blandas).append(previo)
            continue

        ruta = _RUTA_DE_CAMPO[campo]
        dimension, operador = _FORMA[campo]
        vigente = previo is not None and previo.status is CriterionStatus.ACTIVE

        # ── la rigidez: declarada ahora, heredada de un criterio VIGENTE (R10), o ninguna ──
        if campo in rigidez_aplicable:
            rigidez = rigidez_aplicable[campo]
            sustento_rigidez = (_evidencia(
                buyer_id, source_message_id, f"{ruta}#rigidez", retrieved_at,
                methodology=_METODOLOGIA_RIGIDEZ[rigidez]),)
            duro = rigidez is RigidezV0.ESTRICTA
        elif vigente:
            sustento_rigidez = tuple(e for e in previo.evidence if es_evidencia_de_rigidez(e))
            duro = duro_previo
        else:
            # Nunca hubo, o el criterio estaba RETRACTED: la rigidez de un requisito que la
            # persona retiró no se hereda. Un valor nuevo nace flexible (R9) hasta que lo diga.
            sustento_rigidez, duro = (), False

        # ── el valor: vigente → ACTIVE; retirado → RETRACTED (R11); nunca hubo → nada ──
        actual = _valor_y_unidad(campo, datos)
        evidencia_valor = evidencia_de_ruta.get(ruta)
        if actual is not None:
            if evidencia_valor is None or evidencia_valor.source_type is not SourceType.USER_DECLARED:
                # Un valor sin declaración que lo sostenga no puede volverse `STATED` (R12).
                # Sólo pasa con una base escrita a mano; el reducer siempre deja evidencia.
                if previo is not None:
                    (duras if duro_previo else blandas).append(previo)
                continue
            valor, unidad = actual
            criterio = DecisionCriterionV0(
                criterion_id=campo.value, dimension=dimension, operator=operador,
                value=valor, unit=unidad, origin=CriterionOrigin.STATED,
                status=CriterionStatus.ACTIVE,
                evidence=(evidencia_valor,) + sustento_rigidez)
        elif previo is not None:
            if vigente:
                # El retiro de ESTE mensaje: el criterio conserva su valor, su lista y su
                # rigidez —documentan qué se retiró— y suma la evidencia del retiro.
                sustento = tuple(e for e in previo.evidence if not es_evidencia_de_rigidez(e))
                retiro = () if evidencia_valor is None or any(
                    e.evidence_id == evidencia_valor.evidence_id for e in sustento) \
                    else (evidencia_valor,)
                criterio = previo.model_copy(update={
                    "status": CriterionStatus.RETRACTED,
                    "evidence": sustento + retiro + tuple(
                        e for e in previo.evidence if es_evidencia_de_rigidez(e))})
                duro = duro_previo
            else:
                criterio, duro = previo, duro_previo        # ya estaba retirado: intacto
        else:
            # Tocada sin valor y sin criterio previo: una ambigüedad o una rigidez sin valor.
            # La pregunta ya la abrió `reducir`; aquí no hay criterio que crear.
            continue

        (duras if duro else blandas).append(criterio)

    _exigir_r8_y_r12(duras, blandas)
    return tuple(duras), tuple(blandas)


def _exigir_r8_y_r12(duras, blandas) -> None:
    """R8 y R12 sobre el RESULTADO completo, arrastrados incluidos.

    Comprobarlo sólo en la rama que crea criterios dejaba pasar un duro sin rigidez que
    viniera de la base: una base escrita a mano, o un cambio futuro que olvide esta regla,
    se perpetuaba revisión tras revisión.
    """
    for criterio in duras:
        if not any(rigidez_de_evidencia(e) is RigidezV0.ESTRICTA for e in criterio.evidence):
            raise ReduccionImposible(
                f"{criterio.criterion_id} está en hard_constraints sin una rigidez ESTRICTA "
                f"declarada: la inferencia no se vuelve restricción dura en silencio")
    for criterio in (*duras, *blandas):
        if criterio.origin is not CriterionOrigin.STATED:
            raise ReduccionImposible(
                f"{criterio.criterion_id} no es STATED: este reducer no produce inferencias")
