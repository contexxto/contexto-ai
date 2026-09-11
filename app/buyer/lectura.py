"""F3-TOOLS-MIN-1A · leer el `BuyerContextV0` de un principal autenticado.

La capacidad que el `Execution Plan 1.0` nombra `get_buyer_context` en las «tools mínimas»
de FASE 3. Aquí se construye; **aquí NO se registra como tool**, y esa distinción es la
unidad entera —ver «lo que esta unidad no hace».

## Por qué existe, si `store.cargar_ultima` ya leía

Porque no leen lo mismo. `cargar_ultima(buyer_id: str)` es una primitiva del store: recibe
**una cadena cualquiera** y devuelve el estado de quien sea que esa cadena nombre. Es
correcta para su capa —el orquestador ya resolvió de quién es el turno antes de llamarla—
y sería un agujero si la expusiéramos tal cual: el primer llamador que pase un id de otra
fuente lee la memoria de otra persona.

Esta función **no tiene por dónde recibir un `buyer_id`**. Lo deriva del principal, y esa
ausencia de parámetro es la propiedad, no una omisión:

```
cargar_ultima(buyer_id, ...)             primitiva · la autoridad la pone quien llama
leer_contexto_del_principal(principal)   capacidad · la autoridad viaja con el sujeto
```

El aislamiento entre compradores no se comprueba: **no se puede expresar**. Una guarda
`if pedido != propio: denegar` sería más débil, porque vive mientras nadie la borre; una
firma sin el parámetro no se puede infringir sin cambiar la firma, y eso se ve en el diff.

## Lo que esta unidad NO hace, y no es un descuido

  · **No la llama nadie en producción.** `PRODUCTION_READ_CALLERS = 0`, y es una CONDICIÓN
    de 1A, no un hallazgo tardío: fabricar un llamador para que el censo diera otro número
    sería consumo productivo, que pertenece a 1B.
  · **No se registra en `AGENT_TOOLS`** ni lleva `@tool`, ni entra al prompt. Una tool
    visible al modelo puede invocarse, su resultado entra al contexto y puede cambiar la
    respuesta: eso es autoridad de runtime y la decide 1B, no esta unidad.
  · **No enciende la sombra**, no crea `buyer_id`, no reclama sesiones, no escribe
    revisiones, no toca `unresolved_questions` y no ejecuta el updater.
  · **No cierra Gate F3.** Demuestra que podemos leer; no que el producto lea.

## AUSENCIA DE PRINCIPAL vs AUSENCIA DE CONTEXTO — no son lo mismo

```
principal ausente o sin raíz  →  PrincipalNoAutenticado   (excepción tipada)
principal válido, sin estado  →  None
```

Se podría haber devuelto `None` en los dos casos, y era la opción cómoda: es lo que hace
`actualizar_en_sombra`, que ante un anónimo simplemente vuelve. Pero la sombra **escribe**,
y para quien escribe «no hay comprador» y «este comprador aún no tiene estado» llevan a la
misma acción: no hacer nada. Para quien **lee** llevan a acciones opuestas —a uno se le
pregunta qué busca, al otro se le pide iniciar sesión—, y un único `None` obligaría al
llamador a adivinar cuál de los dos ocurrió.

Es el mismo criterio que ya separa `checkpoint_not_found` de `checkpoint_read_failed` en
`routers/chat.py`: *«no son intercambiables, y confundirlos le miente al adjudicador»*.

La excepción se lanza **antes de tocar la base**: un principal sin raíz no debe consumir ni
una conexión del pool. Mismo orden que la tercera puerta de `sombra._autorizado`.
"""
from __future__ import annotations

from app.buyer.store import cargar_ultima
from app.contracts.buyer_v0 import BuyerContextV0


class PrincipalNoAutenticado(RuntimeError):
    """No hay un sujeto autenticado del que derivar la raíz del comprador.

    NO significa «este comprador no tiene contexto» —eso es `None`—. Significa que no se
    sabe de quién se estaría leyendo, y en esa duda no se lee nada.
    """


def _raiz_del_principal(principal) -> str:
    """El `buyer_id` que corresponde a este sujeto. Única fuente de identidad de la lectura.

    Se lee con `getattr` y no por tipo a propósito: el seam existente
    (`sombra.actualizar_en_sombra`) ya acepta cualquier objeto con `user_id`, y exigir aquí
    `isinstance(CurrentUser)` crearía una segunda semántica de identidad para el mismo
    concepto. La raíz es `auth.users.id`, que es lo que `buyer_context_heads.buyer_id`
    referencia por clave foránea.

    Una cadena vacía o de espacios NO es una raíz: `"   "` es exactamente el valor que
    convertiría un fallo de configuración en una lectura silenciosa de la fila equivocada.
    """
    if principal is None:
        raise PrincipalNoAutenticado("no hay principal: no se puede derivar el comprador")
    crudo = getattr(principal, "user_id", "") or ""
    raiz = crudo.strip()
    if not raiz:
        raise PrincipalNoAutenticado(
            "el principal no tiene `user_id` utilizable: sin raíz no se lee nada")
    return raiz


async def leer_contexto_del_principal(principal, *, db=None) -> BuyerContextV0 | None:
    """El `BuyerContextV0` vigente del principal, o `None` si nunca se persistió.

    **Sólo lee.** Delega en `store.cargar_ultima`, que resuelve la revisión vigente con un
    `JOIN` sobre `buyer_context_heads.current_revision` —así «la última» es una propiedad de
    la consulta y no una elección de este módulo— y rehidrata siempre por el contrato,
    inyectando el `context_revision` de la fila.

    No se captura `BuyerContextCorrupto`: una revisión que no satisface el contrato es un
    hecho que el llamador tiene que ver. Devolver `None` ahí confundiría «no hay estado» con
    «el estado guardado está roto», que es la confusión que este módulo existe para evitar.

    Args:
        principal: sujeto autenticado; cualquier objeto con `user_id` (p. ej. `CurrentUser`).
        db: sesión ya abierta, opcional. Se pasa tal cual al store para que una lectura
            pueda participar de una transacción del llamador sin abrir una segunda conexión.

    Raises:
        PrincipalNoAutenticado: no hay sujeto, o su `user_id` no es utilizable.
    """
    return await cargar_ultima(_raiz_del_principal(principal), db=db)
