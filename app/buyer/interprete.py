"""E3.2b.1b · `text → Afirmacion` — el intérprete, por fin.

Es la primera capa de esta fase que **comprende** en vez de comprobar. Las anteriores
—`boundary` y la guarda de `extractor`— existen para decir que no; ésta existe para proponer,
y por eso es la única que puede equivocarse en la dirección cara.

## Dos piezas, y la frontera entre ellas es lo que hace testeable esto

```
texto  →  PROPONENTE          interpreta · puede necesitar un modelo · falible
       →  POST-PROCESAMIENTO  puro · determinista · aplica la guarda y C1-C5
       →  LoteExtraccion
```

El proponente **no decide qué se persiste**. Dice qué cree que dijo el usuario; el
post-procesamiento decide qué de eso puede acreditarse. Esa separación no es estética: es lo
que permite probar offline todos los invariantes sin fingir que se ha probado la comprensión.

`app/preferencias.py` tiene la misma costura y ahí está la lección: su suite prueba
`_sanitizar` y las rutas de degradación, y **no prueba la interpretación en absoluto**. Un
seam sin tests de los dos lados solo mueve el problema de sitio.

## Qué NO puede hacer el proponente, por construcción

```
proponer un path que no existe   el esquema de la tool ES la unión cerrada
crear estado sin evidencia       autorizar_traduccion se aplica a TODA durable propuesta
hacer desaparecer una intención  lo no acreditado cae a AMBIGUOUS, nunca al vacío
fabricar durable al fallar       cualquier excepción degrada a cero propuestas
volver dura una restricción      autorizar_rigidez exige la palabra explícita (E3.3)
```

La tercera es la menos obvia y la más importante. La guarda de E3.2b.1a es deliberadamente
estricta y produce falsos negativos conocidos —`"máximo 120000 dólares"`, `"pet friendly"`,
cualquier anáfora—. Si el intérprete tratara "no pasó la guarda" como "no había nada", esos
mensajes se perderían en silencio: el usuario declaró algo, el sistema lo entendió, y no
quedó ni el estado ni la pregunta. Se convierten en `AMBIGUOUS` con su dimensión, que es lo
que permite repreguntar.

## Lo que NO hace

No aplica mutaciones, no toca el store, no crea procedencia y no decide novedad. El lote que
devuelve es el mismo contrato que E3.2b.2 consumirá.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from decimal import Decimal
from typing import Any

import anthropic
import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.buyer.boundary import (
    BuyerFieldV0,
    BuyerMutationV0,
    CampoConCriterioV0,
    DeclaracionRigidezV0,
    Disposicion,
    RigidezV0,
    campo_de_mutacion,
)
from app.buyer.extractor import (
    AfirmacionAmbiguous,
    AfirmacionDurable,
    AfirmacionRejected,
    AfirmacionTurnOnly,
    LoteExtraccion,
    RigidezNoAcreditada,
    TraduccionNoAutorizada,
    autorizar_rigidez,
    autorizar_rigidez_por_adyacencia,
    autorizar_traduccion,
    construir_lote,
)
from app.config import settings

logger = logging.getLogger(__name__)

_CERRADO = ConfigDict(frozen=True, extra="forbid")


# ── Lo que el proponente entrega ───────────────────────────────────────────────────


class PropuestaV0(BaseModel):
    """Una lectura del mensaje, **todavía no una afirmación**.

    La distinción es el punto entero del módulo: una `Afirmacion` ya pasó por la guarda y
    puede convertirse en estado; una `Propuesta` es lo que alguien —un modelo— cree haber
    entendido. Tienen forma parecida a propósito, para que la conversión sea legible, pero no
    son intercambiables.

    **No lleva validador de coherencia.** Que una `TURN_ONLY` traiga mutación es un error del
    proponente, y rechazarlo al construir convertiría un error suyo en una excepción nuestra.
    `interpretar` lo trata como dato mal formado y lo degrada; eso es más robusto que exigirle
    corrección a algo que por definición es falible.
    """

    model_config = _CERRADO

    disposicion: Disposicion
    mutacion: BuyerMutationV0 | None = None
    campo: BuyerFieldV0 | None = None
    motivo: str = Field(min_length=1)


class PropuestaRigidezV0(BaseModel):
    """E3.3 · lo que el proponente cree que la persona dijo sobre CUÁNTO manda un requisito.

    Separada de `PropuestaV0` porque no es una disposición sobre un valor: *"lo del
    presupuesto es flexible"* no declara, corrige ni retracta ningún presupuesto. Como toda
    propuesta, **no crea nada por sí misma**: pasa por `autorizar_rigidez`, y la que no se
    acredita queda como `REJECTED` con su campo.

    `campo` es la whitelist como `Literal`: el modelo no puede proponer la rigidez de algo que
    no sea requisito del inmueble, porque el esquema de la tool no tiene dónde ponerlo.
    """

    model_config = _CERRADO

    campo: CampoConCriterioV0
    rigidez: RigidezV0
    motivo: str = Field(min_length=1)


Proponente = Callable[[str], Awaitable[Sequence[PropuestaV0 | PropuestaRigidezV0]]]
"""La costura. Recibe el texto y devuelve lecturas; nada más.

Deliberadamente un `Callable` y no una clase: el intérprete no necesita ciclo de vida, ni
configuración, ni saber si al otro lado hay un modelo, una tabla o un test. Inyectarlo es lo
que permite probar el post-procesamiento sin API y sin fingir comprensión."""


# ── El post-procesamiento · puro y determinista ────────────────────────────────────


def _degradar(propuesta: PropuestaV0, campo: BuyerFieldV0 | None, motivo: str):
    """Una propuesta que no puede sostenerse **no desaparece**: baja de rango.

    Con dimensión conocida cae a `AMBIGUOUS`, que es lo que deja constancia de que hubo una
    intención sobre ese campo y permite repreguntar. Sin dimensión no hay `AMBIGUOUS` posible
    —lo exige el tipo— y cae a `REJECTED`, que sigue siendo constancia y sigue sin crear
    estado.
    """
    if campo is not None:
        return AfirmacionAmbiguous(campo=campo, motivo=motivo)
    return AfirmacionRejected(campo=None, motivo=motivo)


def _acreditar(propuesta: PropuestaV0, texto: str):
    """Convierte UNA propuesta en UNA afirmación. Aquí se aplica la guarda.

    El caso que define el módulo es el tercero: el proponente entendió una declaración
    durable y la guarda no puede acreditar la mutación exacta. Ni se persiste —sería estado
    inventado— ni se descarta —sería pérdida silenciosa—. Se convierte en `AMBIGUOUS` con su
    dimensión.
    """
    if propuesta.disposicion is not Disposicion.DURABLE:
        # Las tres sin escritura. Si el proponente adjuntó una mutación, se ignora: su tipo
        # no tiene dónde ponerla y la propuesta no manda sobre la frontera.
        campo = propuesta.campo
        if propuesta.disposicion is Disposicion.AMBIGUOUS:
            if campo is None and propuesta.mutacion is not None:
                campo = campo_de_mutacion(propuesta.mutacion)
            if campo is None:
                return AfirmacionRejected(
                    campo=None,
                    motivo=f"ambigüedad sin dimensión: {propuesta.motivo}")
            return AfirmacionAmbiguous(campo=campo, motivo=propuesta.motivo)
        clase = (AfirmacionTurnOnly if propuesta.disposicion is Disposicion.TURN_ONLY
                 else AfirmacionRejected)
        return clase(campo=campo, motivo=propuesta.motivo)

    if propuesta.mutacion is None:
        return _degradar(propuesta, propuesta.campo,
                         f"durable sin mutación: {propuesta.motivo}")

    campo = campo_de_mutacion(propuesta.mutacion)
    try:
        autorizar_traduccion(propuesta.mutacion, texto)
    except TraduccionNoAutorizada as e:
        # EL CASO QUE DEFINE EL MÓDULO. La guarda es estricta a propósito y tiene falsos
        # negativos conocidos; tratarlos como "no había nada" perdería en silencio algo que
        # el usuario sí declaró.
        return AfirmacionAmbiguous(
            campo=campo,
            motivo=f"intención durable sin evidencia acreditable ({e}): {propuesta.motivo}")
    return AfirmacionDurable(mutacion=propuesta.mutacion, motivo=propuesta.motivo)


def _acreditar_rigidez(propuesta: PropuestaRigidezV0, texto: str, valores: dict):
    """UNA propuesta de rigidez → `DeclaracionRigidezV0`, o `RigidezNoAcreditada`.

    Dos vías, y la segunda sólo si falla la primera:

    ```
    local       la cláusula nombra la dimensión y trae el marcador         autorizar_rigidez
    adyacencia  el marcador SOLO, justo después del valor que este mismo   E3.3-R2
                mensaje acreditó para esa dimensión
    ```

    `valores` son las durables ACREDITADAS de este mensaje por dimensión. La adyacencia no
    puede apoyarse en nada más: sin un valor acreditado detrás, "es indispensable" suelto no
    dice de qué.

    **No cae a `AMBIGUOUS`, y es deliberado.** Una ambigüedad sobre el presupuesto compite
    con el presupuesto en C1-C5: *"máximo 900 USD, idealmente"* con la rigidez sin acreditar
    acabaría anulando un valor que sí se acreditó. La no acreditada compite, en cambio, con
    las OTRAS rigideces de su dimensión (`resolver_rigideces`).
    """
    declaracion = DeclaracionRigidezV0(campo=propuesta.campo, rigidez=propuesta.rigidez)
    try:
        autorizar_rigidez(declaracion, texto)
        return declaracion
    except TraduccionNoAutorizada as local:
        motivo = str(local)
    for mutacion in valores.get(propuesta.campo, ()):
        try:
            autorizar_rigidez_por_adyacencia(declaracion, mutacion, texto)
            return declaracion
        except TraduccionNoAutorizada:
            pass
    return RigidezNoAcreditada(
        campo=propuesta.campo, rigidez=propuesta.rigidez,
        motivo=f"rigidez sin evidencia acreditable ({motivo}): {propuesta.motivo}")


def interpretar(mensaje, propuestas: Sequence[PropuestaV0 | PropuestaRigidezV0]
                ) -> LoteExtraccion:
    """Propuestas → lote. **Puro, determinista y sin red.**

    Es donde viven todos los invariantes estructurales, y por eso es donde se prueban. Nada
    de lo que haga el proponente puede saltarse esta función: aunque proponga diez durables
    perfectas, cada una pasa por la guarda antes de existir como tal. Las rigideces igual,
    con su propia guarda.

    Dos pasadas: primero los valores, porque el puente de adyacencia de una rigidez sólo
    puede apoyarse en un valor YA acreditado. El orden de entrada se conserva en cada lista;
    `construir_lote` aplica C1-C5 encima.
    """
    afirmaciones = [_acreditar(p, mensaje.text) for p in propuestas
                    if not isinstance(p, PropuestaRigidezV0)]
    valores: dict = {}
    for afirmacion in afirmaciones:
        if isinstance(afirmacion, AfirmacionDurable):
            valores.setdefault(afirmacion.campo, []).append(afirmacion.mutacion)
    intentos = [_acreditar_rigidez(p, mensaje.text, valores) for p in propuestas
                if isinstance(p, PropuestaRigidezV0)]
    return construir_lote(mensaje, afirmaciones, intentos)


async def interpretar_mensaje(mensaje, proponente: Proponente | None = None
                              ) -> LoteExtraccion:
    """El camino completo. `proponente=None` usa el de Anthropic.

    **Degrada a cero propuestas ante cualquier fallo** —sin credencial, timeout, respuesta
    mal formada—. Es la misma disciplina que `preferencias.py`: mejor un turno sin extracción
    que un estado inventado. Y aquí importa más, porque lo que se escribiría es memoria
    durable del comprador.
    """
    proponente = proponente or proponer_con_modelo
    try:
        propuestas = await proponente(mensaje.text)
    except Exception as e:  # noqa: BLE001 — un proponente falible no puede tumbar el turno
        logger.warning("el proponente falló, cero propuestas (%s: %s)", type(e).__name__, e)
        propuestas = ()
    return interpretar(mensaje, propuestas)


# ── El proponente por defecto ──────────────────────────────────────────────────────
#
# Cliente LOCAL y perezoso, con el patrón exacto de `preferencias.py` (singleton + control de
# SSL). No se extrae un adapter compartido: eso tocaría crm_graph, graph, vision y match, que
# están fuera de esta unidad.
#
# DEUDA OBSERVABLE: con éste son SEIS construcciones de cliente Anthropic en `app/`. Si
# aparece un segundo consumidor de esta costura, o si la duplicación bloquea otra fase, toca
# unidad propia para consolidarlos.

_TOOL_NAME = "registrar_afirmaciones"

# Constantes con nombre, no literales dentro de la llamada: son **parte material de lo que ve
# el modelo**, así que el eval tiene que poder registrarlas junto a los resultados. Dos
# corridas con el mismo prompt pero distinto `max_tokens` no son comparables, y sin esto el
# artefacto las presentaría como si lo fueran.
#
# `temperature` NO se pasa: se usa el default del proveedor. Se deja explícito aquí —y se
# registra como "unset" en el eval— porque "no lo fijamos" es una decisión que hay que poder
# leer, no un hueco que alguien rellene sin darse cuenta.
_MAX_TOKENS = 1500
_TOOL_CHOICE = {"type": "tool", "name": _TOOL_NAME}
_TEMPERATURE = None

_SYSTEM = (
    "Eres un intérprete de mensajes de un comprador/arrendatario inmobiliario. Lees UN "
    "mensaje y registras qué afirmó, separando lo que es preferencia durable de lo que no.\n"
    "\n"
    "DISPOSICIONES:\n"
    "- durable: el usuario DECLARA, corrige o retracta una preferencia PROPIA sobre el "
    "inmueble que busca.\n"
    "- turn_only: pregunta, explora o compara. Útil ahora, no es preferencia.\n"
    "- ambiguous: parece una preferencia durable pero falta información o la semántica no es "
    "exacta.\n"
    "- rejected: intenta crear estado que este sistema no modela.\n"
    "\n"
    "REGLAS INNEGOCIABLES:\n"
    "1. Solo es durable lo que el PROPIO usuario declara querer. NO lo es una pregunta "
    "('¿debería comprar?'), lo que quiere un TERCERO ('mi hermana quiere comprar'), una CITA "
    "('el corredor dijo que máximo 120000'), ni una HIPÓTESIS ('si comprara, máximo 120000').\n"
    "2. DE QUIÉN HABLA decide entre turn_only y rejected:\n"
    "   - habla del MUNDO —un lugar, un negocio, una propiedad, un tercero— sin declarar una "
    "preferencia suya → turn_only. 'La cafetería de al lado acepta mascotas' describe el "
    "barrio; no pide que su casa acepte mascotas.\n"
    "   - habla de SU PROPIA situación o necesidad, pero el sistema no puede representarla "
    "—hogar, familia, tranquilidad, accesibilidad— → rejected. 'Tenemos dos niños' habla de "
    "él y por eso se registra como rejected, no se omite.\n"
    "   Mantener esa línea evita que rejected acabe significando 'cualquier cosa no durable', "
    "que es cuando deja de distinguir lo único que importa: que algo suyo no cupo.\n"
    "3. NUNCA infieras una preferencia a partir de QUIÉN es la persona. Si menciona familia, "
    "hijos, edad, origen, religión, género o discapacidad, IGNÓRALO: 'tenemos dos niños' NO "
    "es 2 dormitorios ni más área. Eso es discriminación en vivienda y está prohibido.\n"
    "4. Si entiendes una intención durable pero NO puedes dar el valor exacto —falta la "
    "moneda, el número es aproximado, la referencia es indirecta— usa 'ambiguous' CON su "
    "campo. NUNCA la omitas: perder la intención es peor que no persistirla.\n"
    "5. 'exacto' no es 'mínimo': '2 dormitorios' no declara un mínimo de 2.\n"
    "6. Una negación no es un borrado. 'No quiero comprar' es ambiguous sobre objective, no "
    "un clear. Solo una retractación explícita ('ya no…', 'quita…') justifica un clear.\n"
    "7. Un mensaje puede contener VARIAS afirmaciones de distinto tipo. Regístralas todas, en "
    "el orden en que aparecen.\n"
    "7a. NO RESUELVAS TÚ LAS CORRECCIONES NI LOS CONFLICTOS. Si el usuario declara algo y "
    "luego lo corrige, registra LAS DOS declaraciones en orden, cada una como durable con su "
    "mutación. Hay una capa posterior, determinista y auditada, que decide cuál sobrevive; si "
    "decides tú, esa política se duplica donde nadie puede revisarla.\n"
    "   'quiero comprar... no, mejor alquilar' → DOS durables: set_objective buy, y después "
    "set_objective rent. No lo colapses a un ambiguous.\n"
    "   'quiero comprar o alquilar' → también DOS durables. Que no haya corrección explícita "
    "lo resuelve la capa de abajo, no tú.\n"
    "7b. MODALIDAD NO ASERTIVA CON CANDIDATO. Una pregunta o una hipótesis/condicional es "
    "siempre turn_only. Pero si dentro de ella el usuario introduce un valor CONCRETO y SOBRE "
    "SÍ MISMO que podría ser su preferencia, y la modalidad impide saber si lo está "
    "declarando, registra DOS cosas: el acto como turn_only Y ese campo como ambiguous. Nunca "
    "durable.\n"
    "   EL CANDIDATO ES EL VALOR CONCRETO QUE OFRECE, NO EL VERBO QUE ENMARCA LA FRASE. Marca "
    "ambiguous SÓLO el campo del que dio un valor suyo; el resto de la frase, por mucho que "
    "nombre otras dimensiones, es parte de la pregunta o de la hipótesis y va dentro del "
    "turn_only. Un ambiguous de más es una repregunta que el usuario nunca pidió.\n"
    "   '¿me alcanza con 120000 USD para comprar?' → turn_only + ambiguous SÓLO en "
    "budget_max. NO marques objective: 'comprar' es lo que está evaluando en la pregunta, no "
    "un objetivo que esté ofreciendo para recordar.\n"
    "   'si comprara, mi máximo sería 120000 USD' → turn_only + ambiguous SÓLO en budget_max. "
    "NO marques objective: 'comprara' es el marco hipotético, no una declaración a medias.\n"
    "   Hacen falta LAS DOS COSAS, modalidad y candidato. Sin candidato concreto no hay nada "
    "que recordar y va SOLO turn_only:\n"
    "   '¿debería comprar?' → solo turn_only. 'Si comprara, ¿qué zonas mirarías?' → solo "
    "turn_only. No inventes un ambiguous donde el usuario no ofreció ningún valor suyo.\n"
    "8. REGISTRA TAMBIÉN LO QUE NO ES DURABLE. Omitir no es clasificar. Una pregunta se "
    "registra como turn_only, no como lista vacía; un contenido que este sistema no modela "
    "—hogar, familia, tranquilidad, accesibilidad— se registra como rejected. Deja constancia "
    "de que lo leíste y decidiste no persistirlo: es lo que permite responderle al usuario y "
    "auditar la decisión después.\n"
    "9. RIGIDEZ, en la lista aparte `rigideces`. Regístrala SOLO si el usuario dice con "
    "palabras explícitas que un requisito suyo es indispensable, imprescindible, "
    "innegociable, obligatorio o 'sí o sí' (estricta), o que es flexible, negociable, 'lo "
    "ideal' o 'de preferencia' (flexible). Campos posibles: budget_max, bedrooms_min, "
    "area_m2_min, pets_required.\n"
    "   'máximo' y 'al menos' NO son rigidez: son el valor. 'máximo 900 USD' no lleva "
    "rigidez; 'máximo 900 USD y es innegociable' sí.\n"
    "   Puede venir sin valor, y entonces corrige la rigidez de algo ya dicho: 'lo del "
    "presupuesto es flexible' → rigidez flexible en budget_max, sin afirmación durable.\n"
    "   Si corrige la rigidez en el mismo mensaje, registra LAS DOS, en orden, igual que la "
    "regla 7a: 'el presupuesto es innegociable... no, perdón, es flexible'.\n"
    "   NUNCA la deduzcas: ni de lo importante que parezca, ni de QUIÉN es la persona ni de "
    "por qué lo necesita (regla 3). Sin palabra explícita, no hay rigidez. Una pregunta "
    "('¿es negociable?') tampoco la declara.\n"
    "\n"
    f"Llama SIEMPRE a la herramienta {_TOOL_NAME}. La lista solo va vacía si el mensaje no "
    "dice NADA sobre vivienda (un saludo, un agradecimiento)."
)


def _sin_prosa_interna(nodo):
    """Quita las `description` que Pydantic hereda de los docstrings de clase.

    **No es limpieza cosmética.** Sin esto, el esquema le entrega al modelo los docstrings de
    `boundary.py` enteros: notas de diseño internas, referencias a unidades de trabajo, y —lo
    peor— la cadena `household.children` literal, que es justo el path que esta fase existe
    para que nadie escriba. La unión sigue cerrada y el modelo no podría emitirlo; pero
    ponerlo en el prompt de un extractor con exposición a Fair Housing es gratuito y va en la
    dirección equivocada.

    El segundo motivo es de acoplamiento: con las descripciones heredadas, **editar un
    docstring cambia el prompt en silencio**. La semántica del prompt vive en `_SYSTEM`, donde
    se puede leer y revisar; la estructura vive en los tipos. Cada cosa en un sitio.
    """
    if isinstance(nodo, dict):
        return {k: _sin_prosa_interna(v) for k, v in nodo.items() if k != "description"}
    if isinstance(nodo, list):
        return [_sin_prosa_interna(v) for v in nodo]
    return nodo


class _EntradaToolV0(BaseModel):
    """El input COMPLETO de la tool, como UN solo modelo. Existe para generar su esquema.

    **Medido con el modelo real, no elegido por estética (E3.3).** Antes cada propiedad
    llevaba su propio esquema con un `$defs` anidado, y sus `$ref` —relativas a la RAÍZ del
    documento— no resolvían a nada. Con una sola propiedad el modelo lo toleraba. Al añadir
    `rigideces` dejó de hacerlo: metía el input entero como TEXTO dentro de `afirmaciones`
    —3 de 10 llamadas con dos `$defs` anidados, 16 de 16 con `rigideces` en línea—, y
    `_parsear` lo perdía todo, así que el mensaje quedaba `VACIO`. Con un único esquema y
    `$defs` en la raíz: 18 de 18 listas, y la rigidez propuesta donde se declaró.
    """

    afirmaciones: list[PropuestaV0]
    rigideces: list[PropuestaRigidezV0] = Field(default_factory=list)
    """Opcional: casi ningún mensaje declara rigidez, y exigirla empujaría al modelo a
    inventarla para rellenar el campo."""


def _tool_schema() -> dict[str, Any]:
    """El esquema de la tool **ES la unión cerrada**, generado del propio tipo.

    Escribirlo a mano lo dejaría divergir del contrato en la primera variante nueva, y esa
    divergencia no daría error: daría un modelo proponiendo algo que ya no existe. Derivarlo
    de `PropuestaV0` mantiene una sola fuente para la ESTRUCTURA; la semántica la pone
    `_SYSTEM`.

    Todas las `$ref` resuelven desde la raíz: ver `_EntradaToolV0` y el test que lo vigila.
    """
    esquema = _sin_prosa_interna(_EntradaToolV0.model_json_schema())
    esquema.pop("title", None)
    return {
        "name": _TOOL_NAME,
        "description": ("Registra las afirmaciones del mensaje. Lista vacía si no hay "
                        "ninguna."),
        "input_schema": esquema,
    }


_client_singleton: anthropic.AsyncAnthropic | None = None


def _client() -> anthropic.AsyncAnthropic:
    """Cliente reutilizado entre turnos. Mismo patrón que `preferencias._client`: crear uno
    por turno fugaría un `httpx.AsyncClient` en el camino caliente."""
    global _client_singleton
    if _client_singleton is None:
        verify = settings.ssl_verify.lower() != "false"
        _client_singleton = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            http_client=httpx.AsyncClient(verify=verify, timeout=30.0),
        )
    return _client_singleton


async def proponer_con_modelo(texto: str) -> Sequence[PropuestaV0 | PropuestaRigidezV0]:
    """El proponente por defecto. **Solo propone.**

    Lo que devuelva pasa entero por `interpretar`, así que una alucinación no crea estado:
    como mucho crea una propuesta que la guarda rechaza y que acaba en `AMBIGUOUS`.
    """
    if not settings.anthropic_api_key or not texto.strip():
        return ()
    respuesta = await _client().messages.create(
        model=settings.llm_model,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM,
        tools=[_tool_schema()],
        tool_choice=_TOOL_CHOICE,
        messages=[{"role": "user", "content": texto}],
    )
    for bloque in respuesta.content:
        if getattr(bloque, "type", "") == "tool_use" and getattr(bloque, "name", "") == _TOOL_NAME:
            return _parsear(bloque.input)
    return ()


def _tipar_monto(cruda):
    """JSON no tiene `Decimal`, y `SetBudgetMax.amount` lo exige en estricto.

    **Sin esta conversión la dimensión presupuesto es imposible de proponer.** No "difícil":
    imposible — ningún valor JSON valida, así que el modelo nunca podría declarar un tope por
    mucho que lo entendiera. Lo destapó el eval B en su primera corrida; los tests
    estructurales no podían verlo porque ahí las mutaciones se construyen en Python, donde
    `Decimal` es natural.

    Es exactamente el trabajo que `boundary` delega hacia arriba: *"la frontera recibe
    estructura ya tipada"*. Alguien tiene que tipar el wire, y es aquí.

    **Solo se convierten números.** Una cadena `"120000"` se deja intacta para que la frontera
    la rechace: interpretar texto a número es justo lo que `strict=True` existe para impedir
    —"un `amount` que llega como texto es un candidato mal formado, no un presupuesto"— y
    saltárselo aquí reabriría por arriba lo que se cerró abajo. `bool` queda fuera porque en
    Python es subclase de `int` y `True` no es un monto.
    """
    mutacion = cruda.get("mutacion") if isinstance(cruda, dict) else None
    if not isinstance(mutacion, dict):
        return cruda
    monto = mutacion.get("amount")
    if isinstance(monto, bool) or not isinstance(monto, (int, float)):
        return cruda
    return {**cruda, "mutacion": {**mutacion, "amount": Decimal(str(monto))}}


def _ubicacion(err) -> str:
    """La ruta del error, sin nombres que haya elegido el modelo: en `extra_forbidden` el último
    tramo ES la clave que el modelo inventó, y esa clave puede ser texto del mensaje."""
    loc = [str(x) for x in err["loc"]]
    if err["type"] == "extra_forbidden" and loc:
        loc[-1] = "<clave extra>"
    return ".".join(loc)


def _registrar_descarte(que: str, error: ValidationError) -> None:
    """Qué falló, **nunca con qué**. El `ValidationError` de Pydantic repite el input, y aquí el
    input es lo que el modelo leyó del mensaje de la persona —su `motivo` puede parafrasearla—.
    Se registran el número de errores y su ubicación y tipo, que es lo que sirve para depurar."""
    tipos = sorted({f"{_ubicacion(err)}:{err['type']}" for err in error.errors()})
    logger.warning("%s descartada por no validar: %d error(es) · %s",
                   que, error.error_count(), tipos)


def _parsear(bruto) -> Sequence[PropuestaV0 | PropuestaRigidezV0]:
    """Salida del modelo → propuestas. **Descarta la que no valide, conserva las demás.**

    Una propuesta mal formada no puede tumbar las otras del mismo mensaje: sería C5 perdido
    por un fallo del modelo en vez de por uno del usuario. Y no se repara nada salvo el tipado
    del wire (`_tipar_monto`) — reparar contenido sería inventar donde menos se ve.
    """
    if not isinstance(bruto, dict):
        return ()
    salida: list[PropuestaV0 | PropuestaRigidezV0] = []
    for cruda in bruto.get("afirmaciones") or ():
        try:
            salida.append(PropuestaV0.model_validate(_tipar_monto(cruda)))
        except ValidationError as e:
            _registrar_descarte("propuesta", e)
    for cruda in bruto.get("rigideces") or ():
        try:
            salida.append(PropuestaRigidezV0.model_validate(cruda))
        except ValidationError as e:
            _registrar_descarte("rigidez", e)
    return tuple(salida)
