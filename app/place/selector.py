"""El selector de Place: qué categorías de POI pide ESTA decisión (PLAN04-2.3-R0A).

Puro. Recibe un `BuyerContextV0` y devuelve una tupla ordenada de categorías de POI. No
toca red, ni base, ni reloj, ni configuración, y no sabe qué proveedor las va a resolver:
«qué pedir» y «a quién pedírselo» son dos preguntas distintas, y esta unidad solo posee la
primera.

LO QUE ESTA UNIDAD **NO** HACE, Y NO ES UN DESCUIDO

  · No selecciona todavía. Devuelve SIEMPRE el conjunto de hoy, venga el comprador vacío o
    venga con `place_preferences` y `commute_anchors`. La FASE 2 es extracción **sin
    cambiar comportamiento**, así que una regla como «quiere verde → solo parque» sería
    comportamiento nuevo por mucho sentido que tenga.
  · No la llama nadie en producción: `PRODUCTION_SELECTOR_CALLERS = 0`. Eso es una
    limitación DECLARADA de R0A, no una virtud ni un criterio de cierre de 2.3. Mientras
    siga así, Contexto **no** selecciona contexto dinámicamente en producción.
  · No decide proveedor, ni radio, ni tope de resultados. Nada de eso es «qué pedir».

PLAN04-2.3-NAMING-01 · «dimensions» en el canon es deriva terminológica

El inventario de tools bautizó la pieza `select_place_dimensions` y el árbol de fronteras
la describe como «qué dimensiones pide ESTA decisión». Pero el mismo canon ancla el HOY a
un símbolo concreto que es una lista de CATEGORÍAS DE POI —«`_CATS_ENTORNO` fijo (6
categorías)»—, y en el Execution Plan la palabra «dimensión» significa `encaje.DIMENSIONES`
en tres de sus cuatro apariciones. R0A devuelve categorías y se nombra en consecuencia:
llamar `select_place_dimensions` a una función que devuelve categorías fabricaría un cuarto
vocabulario de «dimensión» solo para acomodar un documento. El documento no se toca.

POR QUÉ FALTA `transporte`, Y POR QUÉ NO ES LA MISMA AUSENCIA QUE LAS OTRAS DOS

Hoy no se pide por esta vía. `_servicios_con_coords` pide `_CATS_ENTORNO` por un lado y
resuelve el transporte por una rama propia —otro radio, otra consulta, prioridad de hub
masivo—. Meterlo aquí cambiaría el conjunto pedido, que es justo lo que esta unidad no
puede hacer.

POR QUÉ FALTAN `iglesia` Y `seguridad`

Decisión `D-2.3-b`, explícita y de producto: no son seleccionables desde el
`BuyerContextV0` en esta fase. Existen en la capa propia —el CHECK `ck_pois_categoria` de
la migración 021 admite nueve valores— y el camino Place no las pide nunca. La razón está
escrita en `app/estilo_vida.py`: «cerca de mi iglesia como comunidad» se declina como clase
protegida (religión), y `seguridad` de zona como «juicio subjetivo, no una medición —
decisión ya tomada en este producto».

LA PROTECCIÓN DE R0A ES DE FORMA, NO DE SEMÁNTICA — y conviene decirlo para que nadie la
confunda con una compuerta de Fair Housing. Aquí no hay un segundo motor que lea texto y
juzgue: la salida es una constante que pertenece a una allowlist cerrada de seis, así que
mientras no se derive de texto libre **no hay nada que un texto pueda ampliar**. El día que
el selector empiece a leer al comprador, esa propiedad se pierde y hará falta una compuerta
de verdad. Ese día no es hoy.

PLACE-SELECTOR-DUAL-DEFAULT-01 · TEMPORARY UNTIL RUNTIME WIRING

La tupla de abajo repite el contenido de `_CATS_ENTORNO`, que vive en
`app/place/providers/propia.py`. Es duplicación DECLARADA, no descuido: importar el
provider desde aquí rompería la pureza de este módulo —arrastra `app.config` y
`sqlalchemy`—, y mover la constante está fuera del radio de R0A. Mientras dure, una guarda
lee las dos por AST, sin cargar ninguno de los dos módulos, y se pone roja si divergen en
contenido o en orden. La deuda se paga cuando exista cableado; no se «arregla» creando una
dependencia `selector ↔ provider`, que es peor que la duplicación que vendría a quitar.
"""
from __future__ import annotations

from app.contracts.buyer_v0 import BuyerContextV0

# El conjunto de hoy, en el orden de `_CATS_ENTORNO`. Es una TUPLA y no un `set` ni un
# `frozenset` a propósito: el orden de iteración de un conjunto de cadenas cambia con
# `PYTHONHASHSEED` —medido: cinco semillas, cinco órdenes—, y en un régimen que descansa
# en goldens byte a byte eso es no-determinismo silencioso.
CATEGORIAS_POR_DEFECTO: tuple[str, ...] = (
    "salud",
    "farmacia",
    "supermercado",
    "educacion",
    "parque",
    "centro_comercial",
)


def select_place_categories(buyer: BuyerContextV0) -> tuple[str, ...]:
    """Las categorías de POI que pide esta decisión.

    Hoy, siempre `CATEGORIAS_POR_DEFECTO`, sea cual sea el comprador.

    El parámetro no sobra ni es decorativo: es la firma que fija la fila 2.3 del plan
    —«Dado `BuyerContext`, decide qué dimensiones pedir»— y es la costura por la que
    entrará la decisión cuando esté autorizada. Que R0A no lo lea es la propiedad que las
    pruebas exigen: mientras la FASE 2 prohíba comportamiento nuevo, **cambiar el
    comprador no puede cambiar la salida**.
    """
    return CATEGORIAS_POR_DEFECTO
