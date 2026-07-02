"""Guardarraíl: toda lectura de la transaccion VIGENTE de un activo (LEFT JOIN LATERAL a
transacciones_temporales) debe filtrar por anuncio ACTIVO — hallazgo adversarial del PR #46.

Un anuncio COMPLETADO (vendido/arrendado) o PAUSADO NO debe etiquetar el activo con una
operacion/precio que YA NO aplica; el filtro de operacion (arriendo/venta) confiaba en esa
etiqueta. Hoy no es disparable (estado_anuncio nunca deja de ser 'ACTIVO'), pero cierra el hueco.

Este test es un guardarraíl ESTRUCTURAL (no necesita DB): si alguien agrega un LATERAL de
lectura de la transaccion vigente sin el filtro de estado_anuncio, la cuenta se desbalancea
y el test falla — la defensa que la revision pidio contra "dejar una copia sin arreglar".
"""
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent


def _src(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def test_todo_lateral_de_transaccion_filtra_anuncio_activo():
    # 'FROM transacciones_temporales tt' marca el patron LATERAL de lectura de la transaccion
    # vigente (las escrituras/UPDATE usan la tabla SIN el alias tt). Cada LATERAL DEBE traer
    # el filtro de estado_anuncio: en estos modulos 'estado_anuncio' solo aparece en ese filtro.
    for rel in ("app/agent/tools.py", "app/routers/chat.py"):
        src = _src(rel)
        laterales = src.count("FROM transacciones_temporales tt")
        con_filtro = src.count("estado_anuncio")
        assert laterales > 0, f"{rel}: no se encontro el patron LATERAL esperado"
        assert laterales == con_filtro, (
            f"{rel}: {laterales} LATERAL(es) de transaccion pero {con_filtro} con filtro "
            f"estado_anuncio — hay un LATERAL de la transaccion vigente sin anclar a ACTIVO."
        )
