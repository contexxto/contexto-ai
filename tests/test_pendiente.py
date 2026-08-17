"""
LO QUE ESPERA (app/pendiente.py) — la primera línea del CRM.

Un tablero es una sala de espera: una tabla que alguien lee ANTES de decidir. La única
parte de un CRM que es trabajo es la que dice qué está esperando respuesta AHORA. Por eso
esa línea va arriba y las métricas quedan debajo, como justificación.

Lo que más se prueba es lo que NO debe pasar: que se invente urgencia, y que la misma
persona se cuente dos veces.
"""
import pytest

from app.pendiente import componer_pendiente


def _lead(**over):
    l = {"lead": "Lead #a1", "nivel": "frio", "handoff_estado": None,
         "frescura": "activo", "reenganche": None}
    l.update(over)
    return l


# ── El orden ES el criterio: a quién se le responde primero ─────────────────────────

def test_quien_pidio_corredor_va_primero():
    """Levantó la mano: es lo más caro de perder."""
    p = componer_pendiente([
        _lead(reenganche={"mensaje": "x"}, frescura="dormido"),
        _lead(handoff_estado="abierto"),
        _lead(nivel="caliente"),
    ])
    assert p["hay_pendiente"] is True
    assert [g["clave"] for g in p["grupos"]] == ["piden_corredor", "calientes", "por_reenganchar"]
    assert "pidió hablar contigo" in p["frase"]


def test_la_frase_viene_redactada():
    """La compone el motor, no la pantalla ni el modelo: así el CRM visual y el Estratega
    no pueden contar cosas distintas del mismo embudo."""
    p = componer_pendiente([_lead(handoff_estado="abierto"), _lead(handoff_estado="abierto")])
    assert p["frase"] == "2 pidieron hablar contigo y siguen esperando."


def test_singular_y_plural():
    uno = componer_pendiente([_lead(handoff_estado="abierto")])
    assert "1 pidió hablar contigo y sigue esperando" in uno["frase"]


# ── Nada que inventar ───────────────────────────────────────────────────────────────

def test_sin_pendientes_lo_dice_y_no_fabrica_urgencia():
    """Un CRM que SIEMPRE encuentra una urgencia deja de ser creíble a la tercera semana.
    La ausencia de pendientes es una respuesta legítima y buena."""
    p = componer_pendiente([_lead(), _lead()])
    assert p["hay_pendiente"] is False and p["total"] == 0
    assert p["frase"] == "Nada esperando respuesta ahora mismo."


def test_cartera_vacia_se_distingue_de_cartera_al_dia():
    """No es lo mismo 'no tienes nada pendiente' que 'no tienes a nadie'."""
    assert componer_pendiente([])["frase"] == "Tu cartera está vacía todavía."
    assert componer_pendiente(None)["frase"] == "Tu cartera está vacía todavía."


def test_no_hay_frases_de_presion():
    """Se enuncian HECHOS del embudo. La urgencia fabricada es lo que
    `detectar_promesa_inflada` prohíbe del lado del comprador, y no hay motivo para
    permitirla del lado del corredor."""
    p = componer_pendiente([_lead(handoff_estado="abierto"), _lead(nivel="caliente")])
    prohibido = ["urgente", "no pierdas", "última", "ahora o", "corre", "rápido", "!"]
    for w in prohibido:
        assert w not in p["frase"].lower(), f"la frase fabrica urgencia con «{w}»"


# ── El total cuenta PERSONAS, no apariciones ────────────────────────────────────────

def test_un_lead_caliente_y_dormido_no_se_cuenta_dos_veces():
    """`nivel` (intención) y `frescura` (recencia) son ejes DISTINTOS: un lead puede estar
    caliente Y dormido con reenganche listo. Sin excluir a los ya contados, el total
    inflaría la primera línea del CRM — justo el tipo de cifra que aquí no se permite."""
    doble = _lead(nivel="caliente", frescura="dormido", reenganche={"mensaje": "x"})
    p = componer_pendiente([doble])
    assert p["total"] == 1
    assert [g["clave"] for g in p["grupos"]] == ["calientes"]


def test_quien_ya_pidio_corredor_no_aparece_tambien_como_caliente():
    p = componer_pendiente([_lead(handoff_estado="abierto", nivel="caliente")])
    assert p["total"] == 1
    assert [g["clave"] for g in p["grupos"]] == ["piden_corredor"]


def test_el_total_cuadra_con_la_suma_de_los_grupos():
    leads = [_lead(handoff_estado="abierto"), _lead(nivel="caliente"),
             _lead(nivel="caliente"), _lead(reenganche={"mensaje": "x"}, frescura="dormido")]
    p = componer_pendiente(leads)
    assert p["total"] == sum(g["n"] for g in p["grupos"]) == 4


# ── Fair Housing y defensivo ────────────────────────────────────────────────────────

def test_solo_mira_senal_transaccional():
    """Los tres criterios son etapa, handoff y frescura. Un atributo de la persona que
    llegue en el lead NO puede cambiar el resultado."""
    limpio = componer_pendiente([_lead(handoff_estado="abierto")])
    sucio = componer_pendiente([_lead(handoff_estado="abierto", perfil="familia con niños",
                                      origen="extranjero")])
    assert limpio["frase"] == sucio["frase"]
    assert "familia" not in sucio["frase"] and "extranjero" not in sucio["frase"]


@pytest.mark.parametrize("basura", [None, [], [None], ["x"], [{}], [{"nivel": 7}], 42])
def test_entrada_basura_no_revienta(basura):
    p = componer_pendiente(basura)
    assert isinstance(p["frase"], str) and isinstance(p["total"], int)


def test_el_endpoint_del_crm_lo_devuelve():
    """Va con el embudo, no en una llamada aparte: la pantalla debe poder abrir con esto
    sin una segunda petición que podría fallar y dejarla mostrando solo métricas."""
    import inspect

    from app.routers import assets

    src = inspect.getsource(assets.mine_leads)
    assert "componer_pendiente(leads)" in src and '"pendiente"' in src
