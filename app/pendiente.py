"""
LO QUE ESPERA — la primera línea del CRM, y la única que es trabajo.

Un tablero es una sala de espera: una tabla que alguien lee ANTES de decidir. La única
parte de un CRM que no lo es, es la que dice qué está esperando respuesta ahora mismo.
Por eso el CRM abre con esto y las métricas quedan debajo, como justificación.

── La regla, que es la de siempre ──────────────────────────────────────────────────
Se enuncian HECHOS, no urgencia. "3 pidieron corredor y siguen esperando" es un hecho
verificado del embudo. "¡No los pierdas!" sería presión fabricada — exactamente lo que
`detectar_promesa_inflada` prohíbe del otro lado del mostrador, y no hay motivo para
permitirlo del lado del corredor.

Y cuando no hay nada esperando, se dice. Un CRM que siempre encuentra una urgencia deja
de ser creíble a la tercera semana.

── El orden es el criterio ─────────────────────────────────────────────────────────
No es estético: es a quién se le responde primero.
  1. Pidió corredor y sigue esperando  → levantó la mano. Es lo más caro de perder.
  2. Caliente sin handoff              → señal fuerte de intención, sin pedido explícito.
  3. Por reenganchar                   → dormido CON ángulo de valor (lo decide reenganche.py).

Fair Housing: los tres criterios son señal transaccional (etapa, handoff, frescura).
Ninguno mira quién es la persona. Es la misma frontera que el Estratega.

Puro: sin I/O, sin DB, sin LLM. Determinístico → auditable y testeable al 100%.
"""
from __future__ import annotations

# Nivel que el motor de intención considera señal fuerte. Se lee de aquí y no se
# hardcodea en la frase, para que un cambio del motor no deje la línea mintiendo.
_NIVEL_FUERTE = "caliente"


def _es_dict(x) -> bool:
    return isinstance(x, dict)


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def componer_pendiente(leads) -> dict:
    """Qué está esperando respuesta, en orden de a quién atender primero.

    Devuelve {hay_pendiente, grupos[], total, frase}. `frase` viene redactada: la pantalla
    la pinta y el Estratega puede citarla sin recomponerla, así las dos superficies no
    pueden contar cosas distintas del mismo embudo.
    """
    # Defensivo hasta el tipo: si `leads` no es iterable (una respuesta parcial, un fallo
    # aguas arriba), la primera línea del CRM no puede ser una excepción.
    filas = [x for x in leads if _es_dict(x)] if isinstance(leads, (list, tuple)) else []

    piden = [x for x in filas if x.get("handoff_estado")]
    # Caliente pero sin pedido explícito: señal fuerte que todavía nadie tomó. Se excluye
    # a quien ya pidió, para no contar dos veces a la misma persona.
    calientes = [x for x in filas
                 if x.get("nivel") == _NIVEL_FUERTE and not x.get("handoff_estado")]
    # El motor de reenganche ya decidió que hay un ángulo de VALOR que ofrecer; si no lo
    # hay, el lead dormido no entra (silencio por defecto, no perseguimos).
    #
    # OJO: `nivel` (intención) y `frescura` (recencia) son ejes DISTINTOS, así que un lead
    # puede estar caliente Y dormido con reenganche listo. Sin excluir a los ya contados,
    # el total sumaría a la misma persona dos veces — y un total inflado en la primera
    # línea del CRM es justo el tipo de cifra que este proyecto no se permite.
    ya_contados = {id(x) for x in piden} | {id(x) for x in calientes}
    reenganchar = [x for x in filas
                   if x.get("reenganche") and id(x) not in ya_contados]

    grupos = []
    if piden:
        grupos.append({"clave": "piden_corredor", "n": len(piden),
                       "texto": _plural(len(piden), "pidió hablar contigo y sigue esperando",
                                        "pidieron hablar contigo y siguen esperando")})
    if calientes:
        grupos.append({"clave": "calientes", "n": len(calientes),
                       "texto": _plural(len(calientes), "está caliente y nadie lo ha tomado",
                                        "están calientes y nadie los ha tomado")})
    if reenganchar:
        grupos.append({"clave": "por_reenganchar", "n": len(reenganchar),
                       "texto": _plural(len(reenganchar), "tiene un reenganche listo",
                                        "tienen un reenganche listo")})

    if not grupos:
        # Se dice, no se inventa. Un CRM que siempre encuentra una urgencia deja de ser
        # creíble, y la ausencia de pendientes es una respuesta legítima y buena.
        return {"hay_pendiente": False, "grupos": [], "total": 0,
                "frase": ("Nada esperando respuesta ahora mismo."
                          if filas else "Tu cartera está vacía todavía.")}

    return {
        "hay_pendiente": True,
        "grupos": grupos,
        # Los tres grupos se construyen excluyendo a los ya contados, así que el total
        # cuenta PERSONAS distintas y no apariciones.
        "total": sum(g["n"] for g in grupos),
        "frase": " · ".join(g["texto"] for g in grupos).capitalize() + ".",
    }
