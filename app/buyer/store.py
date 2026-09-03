"""E3.1b · Buyer Store V0 — persistencia versionada del `BuyerContextV0`.

Guarda el estado del comprador y su historia. **Nada más.** No extrae preferencias, no
interpreta mensajes, no clasifica criterios, no resuelve tradeoffs y no habla con el
agente. Recibe un `BuyerContextV0` ya construido y lo persiste; quién lo construye es
E3.2.

## Las tres cosas que resuelve, y por qué no bastaba una fila mutable

**Historia.** Un estado que se sobrescribe no puede explicarse. En cuanto la siguiente
actualización pisa a la anterior, *"¿por qué el sistema cree que quiero tres dormitorios?"*
deja de tener respuesta.

**Reintentos.** El mismo mensaje puede procesarse dos veces —retry de red, replay de una
cola— y eso no puede producir dos revisiones del mismo hecho.

**Concurrencia.** Un comprador puede tener dos conversaciones abiertas. Sin una revisión
sobre la que hacer control optimista, la segunda escritura pisa a la primera **en
silencio**, que es la peor forma de perder datos.

## Dónde vive cada garantía

Las dos garantías duras están en la **base**, no en Python:

```
idempotencia   UNIQUE (buyer_id, source_message_id)
concurrencia   SELECT … FOR UPDATE sobre la fila de cabeza
```

No es una preferencia de estilo. Comprobar-en-Python-y-luego-insertar tiene una ventana
entre la comprobación y la escritura; bajo dos procesos concurrentes esa ventana se abre.
Un índice único y un bloqueo de fila no la tienen.

## Lo que este módulo NO decide

**La revisión la asigna el store**, nunca el llamante y menos el modelo. `expected_revision`
es lo que el llamante *creía* que había cuando leyó; si ya no es cierto, la escritura falla.

**No es la barrera de Fair Housing.** Acepta un `BuyerContextV0` ya construido y no mira su
contenido. La sanitización determinista de texto libre a criterios persistibles pertenece a
E3.2 y tiene que ocurrir *antes* de llegar aquí. No se abre un segundo camino de extracción
"para facilitar los tests": eso sería exactamente el atajo por el que la barrera deja de
existir.

**No guarda el texto del mensaje.** Solo `source_message_id`. La conversación tiene su
propio almacenamiento; duplicar el texto aquí sería duplicar PII sin ganar nada.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy import text

from app.contracts.buyer_v0 import BuyerContextV0
from app.contracts.evidence_v0 import SourceType
from app.database import AsyncSessionLocal


class BuyerStoreError(RuntimeError):
    """Raíz de los fallos del store. Nunca se levanta directamente."""


class BuyerRevisionConflict(BuyerStoreError):
    """Otro escritor avanzó el estado desde que este leyó. **No se escribió nada.**

    Es un `lost update` evitado, no un error de programación: dos conversaciones del mismo
    comprador pueden llegar a la vez y ambas son legítimas. Resolver el conflicto —fundir
    los dos estados, o reintentar sobre el nuevo— es E3.2; aquí solo se garantiza que
    ninguno pise al otro sin enterarse.
    """


class BuyerIdempotencyConflict(BuyerStoreError):
    """El mismo `(buyer_id, source_message_id)` ya produjo un estado **distinto**.

    Este es el error más informativo del módulo y por eso no se traga. Un reintento honesto
    del mismo mensaje tiene que producir el mismo estado; si produce otro, lo que hay
    delante es un extractor no determinista, un replay corrupto, o la misma evidencia
    interpretada de dos maneras. Si el store lo ocultara —devolviendo lo viejo o creando
    una revisión nueva— esa divergencia seguiría ahí, invisible.
    """


class BuyerContextCorrupto(BuyerStoreError):
    """Lo persistido ya no satisface `BuyerContextV0`.

    Pasa cuando el contrato evoluciona de forma incompatible con filas antiguas. Se falla
    ruidosamente en vez de devolver el `dict` crudo: un diccionario que no valida no es un
    BuyerContext, y presentarlo como tal trasladaría el fallo a quien confíe en el tipo.
    """


@dataclass(frozen=True)
class RevisionPersistida:
    """Lo que quedó guardado, y si esta llamada fue quien lo guardó.

    `creada=False` significa que el mensaje ya se había procesado y se devuelve la revisión
    que existía. El llamante necesita distinguirlo: no es lo mismo "acabo de avanzar el
    estado" que "esto ya estaba hecho".
    """

    contexto: BuyerContextV0
    revision: int
    creada: bool


def _canonico(contexto: BuyerContextV0) -> str:
    """Forma estable del contexto, para comparar dos snapshots por igualdad.

    Se compara el JSON del contrato con las claves ordenadas, no los objetos: dos
    `BuyerContextV0` equivalentes pueden diferir en el orden de serialización, y comparar
    texto sin ordenar produciría falsos `BuyerIdempotencyConflict` — un error que acusaría
    al extractor de no ser determinista cuando el no determinista sería este módulo.

    **Se excluyen `context_revision` y `updated_at`**: los dos son metadato que asigna el
    store, no estado observado del comprador. Incluir cualquiera de ellos haría que el mismo
    snapshot pareciera distinto solo por haber sido numerado o fechado — y un reintento
    honesto daría `BuyerIdempotencyConflict`, acusando de no determinista a un extractor que
    sí lo es.

    `updated_at` se excluyó en E3.2 tras decidir su semántica (§1A del reporte 15): es el
    instante de PERSISTENCIA de esa revisión, no la hora del evento. `IdentifiedUserMessage`
    no lleva timestamp contractual del evento, así que inventarle uno violaría procedencia.
    En E3.1b este campo SÍ entraba en la comparación; los tests no lo revelaban porque sus
    fixtures usaban un timestamp fijo.

    **Y se excluye la procedencia OPERACIONAL de la evidencia `USER_DECLARED`** —su
    `evidence_id` y su `retrieved_at`— por el mismo motivo y con el mismo criterio: no son
    estado observado del comprador. La regla, su alcance y su límite están junto a
    `_limpiar_procedencia_operacional`, que es donde se aplica.
    """
    datos = contexto.model_dump(mode="json")
    for metadato in ("context_revision", "updated_at"):
        datos.pop(metadato, None)
    for fe in datos.get("field_evidence") or ():
        _limpiar_procedencia_operacional(fe.get("evidence"))
    return json.dumps(datos, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# R-IDEMP-1 · qué de la procedencia es ESTADO y qué es artefacto del intento de procesarlo.
#
# Un replay del mismo mensaje construye una `EvidenceRefV0` nueva: `evidence_id` sale de
# `uuid4()` y `retrieved_at` de un reloj. Los dos cambiaban, el canónico cambiaba con ellos, y
# un reintento honesto acababa en `BuyerIdempotencyConflict` — acusando de no determinista a
# un extractor que sí lo es. Es el mismo motivo por el que ya se excluían `context_revision` y
# `updated_at`, aplicado a la evidencia.
#
# **Acotado a `USER_DECLARED`, y el límite es la parte importante.** Para un `PROVIDER_API`
# con TTL, `retrieved_at` dice si el dato sigue fresco: ahí SÍ es material y sigue
# participando. Excluirlo en general habría cambiado un defecto puntual por una pérdida
# general de procedencia.
#
# Lo que justifica la excepción es lo que significa cada campo para ESTA evidencia:
#
#     evidence_id   "un asa nuestra, no una afirmación sobre el mundo"  (su propio contrato)
#     retrieved_at  cuándo lo procesamos NOSOTROS — no cambia lo que la persona dijo
#
# Todo lo demás sigue comparándose, incluidos `source_id` —de qué mensaje salió— y
# `observed_at` —cuándo el mundo estaba así—, que sí son afirmaciones sobre el dato.
_OPERACIONAL_SI_LO_DIJO_EL_USUARIO = ("evidence_id", "retrieved_at")


def _limpiar_procedencia_operacional(evidencia) -> None:
    if not isinstance(evidencia, dict):
        return
    if evidencia.get("source_type") != SourceType.USER_DECLARED.value:
        return
    for campo in _OPERACIONAL_SI_LO_DIJO_EL_USUARIO:
        evidencia.pop(campo, None)


def _rehidratar(fila) -> BuyerContextV0:
    crudo = fila["context_json"]
    if isinstance(crudo, str):          # según el driver, JSONB llega como texto
        crudo = json.loads(crudo)
    try:
        return BuyerContextV0.model_validate({**crudo, "context_revision": fila["context_revision"]})
    except ValidationError as e:
        raise BuyerContextCorrupto(
            f"la revisión {fila['context_revision']} de {fila['buyer_id']} no satisface "
            f"BuyerContextV0: {e.error_count()} error(es)"
        ) from e


# ── Lectura ────────────────────────────────────────────────────────────────────────


async def cargar_ultima(buyer_id: str, *, db=None) -> BuyerContextV0 | None:
    """El estado vigente del comprador, o `None` si nunca se persistió."""
    async def _ejecutar(sesion):
        fila = (await sesion.execute(text(
            "SELECT r.buyer_id::text AS buyer_id, r.context_revision, r.context_json "
            "FROM buyer_context_heads h "
            "JOIN buyer_context_revisions r "
            "  ON r.buyer_id = h.buyer_id AND r.context_revision = h.current_revision "
            "WHERE h.buyer_id = CAST(:b AS uuid)"),
            {"b": buyer_id})).mappings().first()
        return _rehidratar(fila) if fila else None

    if db is not None:
        return await _ejecutar(db)
    async with AsyncSessionLocal() as propio:
        return await _ejecutar(propio)


async def cargar_revision(buyer_id: str, revision: int, *, db=None) -> BuyerContextV0 | None:
    """Una revisión concreta del historial. Es lo que hace auditable el estado."""
    async def _ejecutar(sesion):
        fila = (await sesion.execute(text(
            "SELECT buyer_id::text AS buyer_id, context_revision, context_json "
            "FROM buyer_context_revisions "
            "WHERE buyer_id = CAST(:b AS uuid) AND context_revision = :r"),
            {"b": buyer_id, "r": revision})).mappings().first()
        return _rehidratar(fila) if fila else None

    if db is not None:
        return await _ejecutar(db)
    async with AsyncSessionLocal() as propio:
        return await _ejecutar(propio)


# ── Escritura ──────────────────────────────────────────────────────────────────────


async def anexar_revision(
    buyer_id: str,
    source_message_id: str,
    contexto: BuyerContextV0,
    expected_revision: int | None,
    *,
    db=None,
) -> RevisionPersistida:
    """Añade una revisión al historial. La única forma de escribir en el store.

    `expected_revision` es lo que el llamante leyó: `None` si no había estado, o el número
    de la revisión sobre la que construyó ésta. Si el estado ya avanzó, se levanta
    `BuyerRevisionConflict` **sin escribir nada**.

    El orden de las comprobaciones no es casual:

      1. **La identidad primero.** Antes de tocar la base se exige que
         `contexto.buyer_id` sea el comprador autorizado. Persistir el estado de una
         cuenta bajo la raíz de otra es el peor fallo posible de este módulo, y no puede
         depender de que una consulta posterior lo note.
      2. **La cabeza se bloquea antes de leerla.** `FOR UPDATE` serializa a los escritores
         del mismo comprador; sin él, dos procesos leerían la misma revisión y ambos se
         creerían al día.
      3. **La idempotencia se comprueba dentro de la transacción**, ya con el bloqueo
         tomado, y aun así el `UNIQUE` de la base queda como red por si el bloqueo no
         aplicara (otra ruta de escritura, un futuro reemplazo del store).
    """
    if contexto.buyer_id != buyer_id:
        raise BuyerStoreError(
            "el contexto pertenece a otro comprador: no se persiste bajo esta raíz"
        )
    # E3.2 · 1C — defensa en profundidad. `NOT NULL` impide `NULL`, no `""`: en E3.1b la
    # cadena vacía atravesaba esta función y llegaba hasta la base. La garantía vivía solo
    # en `IdentifiedUserMessage(min_length=1)`, aguas arriba. Ahora falla aquí, y la
    # migración 029 añade el `CHECK` para que tampoco entre por otra vía.
    if not isinstance(source_message_id, str) or not source_message_id.strip():
        raise BuyerStoreError("source_message_id no puede ser vacío ni solo espacios")
    if expected_revision is not None and expected_revision < 0:
        raise BuyerStoreError("expected_revision no puede ser negativa")

    # E3.2 · 1B — LA PROPIEDAD DE LA TRANSACCIÓN SIGUE A LA PROPIEDAD DE LA SESIÓN.
    #
    #   sesión propia (db=None)  → el store hace commit/rollback
    #   sesión inyectada (db=…)  → el LLAMANTE hace commit/rollback; el store NO toca ninguno
    #
    # En E3.1b el store hacía `commit()` y `rollback()` también sobre la sesión inyectada.
    # Funcionaba porque era dueño exclusivo de la frontera, pero era una precondición no
    # escrita: en cuanto E3.2 comparta sesión con otro trabajo, un `rollback` del store
    # descartaría escrituras ajenas que nadie le pidió deshacer.
    if db is not None:
        return await _ejecutar_anexo(db, buyer_id, source_message_id, contexto,
                                     expected_revision, propietario=False)
    async with AsyncSessionLocal() as propio:
        return await _ejecutar_anexo(propio, buyer_id, source_message_id, contexto,
                                     expected_revision, propietario=True)


async def _ejecutar_anexo(db, buyer_id, source_message_id, contexto, expected_revision,
                          *, propietario: bool):
    # SAVEPOINT — lo que hace compatibles las dos garantías que E3.2 exige a la vez:
    #
    #   1. deshacer del store NO puede borrar trabajo ajeno
    #   2. un fallo del store NO puede dejar trabajo propio a medias
    #
    # Sin él solo se podía cumplir una. Con `db.rollback()` (E3.1b) se cumplía la 2 y se
    # violaba la 1. Al quitarlo (primera versión de E3.2·1B) se cumplía la 1 y se violaba
    # la 2: el `INSERT` de la cabeza ocurre ANTES de comprobar `expected_revision`, así que
    # un `BuyerRevisionConflict` dejaba una cabeza huérfana que el `commit` del llamante
    # confirmaba — contradiciendo el "no se escribió nada" documentado en la excepción.
    #
    # El savepoint acota el alcance del deshacer a lo que el store escribió. No hace falta
    # razonar sobre qué casos pueden dejar estado parcial: ninguno puede.
    punto = await db.begin_nested()

    async def _deshacer():
        """Deshace SOLO lo que escribió el store. Lo anterior del llamante no se toca."""
        if punto.is_active:
            await punto.rollback()
        if propietario:
            await db.rollback()

    async def _confirmar():
        await punto.commit()          # libera el savepoint; no confirma nada por sí solo
        if propietario:
            await db.commit()

    try:
        # 1 · La cabeza, creada si no existe, y BLOQUEADA en el mismo viaje. El
        # `ON CONFLICT DO NOTHING` seguido del `SELECT … FOR UPDATE` cubre la carrera de
        # dos primeros escritores simultáneos: uno inserta, el otro no, y ambos acaban
        # bloqueando la misma fila.
        await db.execute(text(
            "INSERT INTO buyer_context_heads (buyer_id, current_revision) "
            "VALUES (CAST(:b AS uuid), 0) ON CONFLICT (buyer_id) DO NOTHING"),
            {"b": buyer_id})

        cabeza = (await db.execute(text(
            "SELECT current_revision FROM buyer_context_heads "
            "WHERE buyer_id = CAST(:b AS uuid) FOR UPDATE"),
            {"b": buyer_id})).scalar()

        # ¿Hay ya alguna revisión, o la cabeza acaba de nacer vacía?
        hay_estado = (await db.execute(text(
            "SELECT count(*) FROM buyer_context_revisions WHERE buyer_id = CAST(:b AS uuid)"),
            {"b": buyer_id})).scalar() > 0
        actual = cabeza if hay_estado else None

        # 2 · IDEMPOTENCIA. Se mira antes que el conflicto de revisión a propósito: un
        # reintento del mismo mensaje llega con el `expected_revision` viejo y parecería
        # un conflicto de concurrencia. Sería un diagnóstico equivocado — no hay dos
        # escritores, hay uno que repite.
        previa = (await db.execute(text(
            "SELECT buyer_id::text AS buyer_id, context_revision, context_json "
            "FROM buyer_context_revisions "
            "WHERE buyer_id = CAST(:b AS uuid) AND source_message_id = :m"),
            {"b": buyer_id, "m": source_message_id})).mappings().first()

        if previa is not None:
            ya = _rehidratar(previa)
            if _canonico(ya) != _canonico(contexto):
                raise BuyerIdempotencyConflict(
                    f"el mensaje {source_message_id} ya produjo la revisión "
                    f"{previa['context_revision']} con un estado distinto"
                )
            # Nada que escribir. Con sesión propia se cierra la transacción; con sesión
            # ajena NO se toca: el llamante puede tener trabajo pendiente en ella.
            await _deshacer()
            return RevisionPersistida(ya, previa["context_revision"], creada=False)

        # 3 · CONCURRENCIA. Lo que el llamante creía ya no es lo que hay.
        if expected_revision != actual:
            raise BuyerRevisionConflict(
                f"se esperaba la revisión {expected_revision} y la vigente es {actual}"
            )

        nueva = 0 if actual is None else actual + 1

        # 4 · El historial. El store fija los DOS metadatos —la revisión y el instante de
        # persistencia— y sobrescribe lo que trajera el contexto, para que no haya dos
        # fuentes de verdad de ninguno.
        #
        # `updated_at` es el instante en que ESTA revisión se persiste (E3.2 · 1A). No es la
        # hora del mensaje: `IdentifiedUserMessage` no lleva timestamp contractual del
        # evento, y fabricarle uno sería inventar procedencia. El updater no debe generar
        # `datetime.now()` dentro del payload semántico — lo pone aquí.
        datos = contexto.model_dump(mode="json")
        datos["context_revision"] = nueva
        datos["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()

        await db.execute(text(
            "INSERT INTO buyer_context_revisions "
            "  (buyer_id, context_revision, source_message_id, context_json) "
            "VALUES (CAST(:b AS uuid), :r, :m, CAST(:j AS jsonb))"),
            {"b": buyer_id, "r": nueva, "m": source_message_id,
             "j": json.dumps(datos, ensure_ascii=False)})

        await db.execute(text(
            "UPDATE buyer_context_heads SET current_revision = :r, updated_at = now() "
            "WHERE buyer_id = CAST(:b AS uuid)"),
            {"b": buyer_id, "r": nueva})

        await _confirmar()
        return RevisionPersistida(BuyerContextV0.model_validate(datos), nueva, creada=True)

    except BuyerStoreError:
        # Los errores tipados del store también dejan el savepoint abierto si no se cierra
        # aquí. `BuyerContextCorrupto` es el caso real: sale de `_rehidratar(previa)` DENTRO
        # del savepoint cuando el `(buyer_id, source_message_id)` ya existe pero su revisión
        # dejó de validar. Antes se re-lanzaba tal cual y el store devolvía el control al
        # llamante con una transacción anidada suya todavía abierta — no se pierde nada,
        # pero rompe la frontera que E3.2 acaba de formalizar.
        #
        # UN SOLO CAMINO DE LIMPIEZA. Los `_deshacer()` que había justo antes de levantar
        # los dos conflictos se retiraron: con dos caminos, el próximo error tipado que se
        # añada vuelve a olvidarse de cerrar.
        await _deshacer()
        raise
    except Exception:
        await _deshacer()
        raise
