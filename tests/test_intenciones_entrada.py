"""
"Antes de decidir" — las intenciones de entrada, vigiladas.

EL DEFECTO QUE CIERRAN (hallado el 2026-08-17 mirando la home renderizada): el chip
"Para mi familia" no era una etiqueta — INYECTABA en boca del usuario
«Busco para mi familia: tranquilo, con colegios y parque cerca». Tres proxies de Fair
Housing en una línea: estado familiar, colegios como filtro, y "tranquilo" como eufemismo.

Lo fino es POR QUÉ era peor de lo que parece. `fair_housing.detectar_steering` está
calibrado a propósito para NO marcar la cita del usuario (su docstring lo dice: "NI la
cita del usuario"). Al poner la frase en su boca, el sistema lavaba su propio encuadre por
la única puerta que el guardrail deja abierta. La garantía estructural aguantaba —
`encaje.DIMENSIONES` no puede puntuar por "familia"— pero la conversación quedaba
encuadrada ahí.

El arreglo NO es dejar de servir a quien tiene hijos: es dejar de nombrarla. La necesidad
(área verde, espacio) se declara igual y sí puntúa; la persona no se menciona.

Estos tests leen el archivo: no hay runtime JS que ejecutar, y la garantía está en el
texto que se le entrega al agente.
"""
import re
from pathlib import Path

import pytest

_FRONT = Path(__file__).resolve().parents[1] / "frontend" / "src"
_INTENCIONES = (_FRONT / "intencionesEntrada.js").read_text(encoding="utf-8")
_LAUNCHER = (_FRONT / "Launcher.jsx").read_text(encoding="utf-8")
_QUEES = (_FRONT / "QueEs.jsx").read_text(encoding="utf-8")

# Solo la parte EJECUTABLE: los comentarios explican el defecto y deben poder nombrarlo.
_CODIGO = re.sub(r"//[^\n]*|/\*.*?\*/", "", _INTENCIONES, flags=re.S)

# Clase protegida y sus proxies clásicos en vivienda. Lo que el SISTEMA no puede poner en
# boca de nadie; que el usuario lo diga por su cuenta es otra cosa y se respeta.
_PROHIBIDO = [
    (r"\bmi familia\b|\bpara familias?\b", "estado familiar (clase protegida)"),
    (r"\bcolegios?\b|\bescuelas?\b", "colegios como filtro: el proxy de manual"),
    (r"\bni[nñ]os?\b|\bhijos?\b", "presencia de menores (estado familiar)"),
    (r"\bbarrio tranquilo\b|\bzona tranquila\b", "'tranquilo' como eufemismo de zona"),
    (r"\bgente como (tu|usted)\b", "composición del vecindario"),
    (r"\bsoltero|\bpareja\b|\bjubilad", "estado civil / edad"),
]


@pytest.mark.parametrize("patron,motivo", _PROHIBIDO)
def test_ninguna_intencion_pone_clase_protegida_en_boca_del_usuario(patron, motivo):
    hits = re.findall(patron, _CODIGO, re.I)
    assert not hits, (
        f"una intención de entrada contiene {motivo}: {hits}. El sistema no puede sembrar "
        f"ese encuadre — al llegar como 'cita del usuario', detectar_steering NO lo marca.")


def test_las_intenciones_no_piden_un_veredicto():
    """Procedimental o necesidad declarada; nunca «dime qué me conviene». La diferencia
    entre informar una decisión y tomarla por la persona."""
    veredictos = re.findall(r"qu[eé] me conviene|cu[aá]l me conviene|qu[eé] barrio me|"
                            r"d[oó]nde deber[ií]a vivir|es bueno para m[ií]", _CODIGO, re.I)
    assert not veredictos, f"una intención pide un veredicto sobre la persona: {veredictos}"


def test_el_producto_tiene_su_propia_entrada():
    """"¿Podría vivir aquí un año?" no es un tip: es la pregunta que el Place Graph
    responde y que ningún portal puede contestar. Si desaparece, la home deja de ofrecer
    lo único que diferencia a Contexto."""
    assert "vivir-un-ano" in _INTENCIONES
    assert re.search(r"vivir un a[nñ]o", _INTENCIONES, re.I)


def test_las_necesidades_sembradas_existen_en_la_whitelist_del_encaje():
    """Sembrar una necesidad que el motor no puntúa promete algo que el encaje no puede
    cumplir. Las que se siembran tienen que estar en `encaje.DIMENSIONES`."""
    from app.encaje import DIMENSIONES

    # Lo que las intenciones prometen hoy, y su dimensión en el motor.
    promesas = {"área verde": "area_verde", "presupuesto": "presupuesto_max",
                "Metro": "transporte"}
    for texto, dim in promesas.items():
        assert texto.lower() in _INTENCIONES.lower(), f"desapareció la intención de {texto}"
        assert dim in DIMENSIONES, f"{dim} no está en la whitelist: no se puede prometer"


def test_el_launcher_no_tiene_textos_propios():
    """Fuente única: cada intención rinde como chip, como página indexable (AEO) y como
    guion del canal. Textos duplicados en el Launcher se desincronizan."""
    assert "from './intencionesEntrada'" in _LAUNCHER
    assert "intent:" not in _LAUNCHER, "el Launcher volvió a definir textos propios"


def test_la_pagina_de_venta_no_promete_lo_que_el_motor_tiene_prohibido():
    """QueEs.jsx usaba “Para mi familia” como EJEMPLO de encaje: prometía en la página de
    venta exactamente lo que el motor no puede puntuar."""
    cuerpo = re.sub(r"\{/\*.*?\*/\}", "", _QUEES, flags=re.S)   # sin comentarios JSX
    assert "Para mi familia" not in cuerpo
