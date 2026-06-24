"""
Demo en vivo para Linden (Puebla) — el calificador de leads 24/7 en acción.

Corre:  python scripts/demo_linden.py

Muestra cómo el motor distingue un curioso de un comprador caliente, con datos
de Puebla. Es lógica pura (app/intencion.py): sin red, sin LLM, determinista.
El mismo cerebro que consumen el agente, el panel del asesor y la API B2B.
"""
import os
import sys

# Auto-suficiente: corre con `python scripts/demo_linden.py` desde la raíz, sin
# setear PYTHONPATH, y fuerza UTF-8 para que los emojis no rompan en la consola Windows.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")  # Python 3.7+
except Exception:
    pass

from app.intencion import analizar_intencion  # noqa: E402

CASOS = [
    {
        "titulo": "1) Curioso — recién llega",
        "contexto": "Escribió por Instagram, sin señales de compra todavía.",
        "kwargs": dict(
            mensajes_usuario=[
                "Hola 👋 vi una casa en su Instagram que me gustó, ¿me cuentan más?",
            ],
        ),
        "talk": "El asesor NO debería gastar pólvora aquí todavía. El sistema lo sabe.",
    },
    {
        "titulo": "2) Explorador — compara zonas",
        "contexto": "Investiga activamente Angelópolis vs. Lomas de Angelópolis.",
        "kwargs": dict(
            mensajes_usuario=[
                "¿Cómo es vivir en Angelópolis? me importa la caminabilidad y el ruido",
                "¿Y comparado con Lomas de Angelópolis? cuál es mejor para servicios y colegios",
            ],
        ),
        "talk": "Lead REAL en formación. Marcarlo 'frío' sería perder dinero — el sistema lo sube a tibio.",
    },
    {
        "titulo": "3) Comprador caliente — precio, visita y contacto",
        "contexto": "Llegó por el QR/WhatsApp de una propiedad, un sábado a las 11pm.",
        "kwargs": dict(
            mensajes_usuario=[
                "Me encantó la casa en Lomas de Angelópolis, ¿cuánto cuesta?",
                "¿Se puede agendar una visita este fin de semana?",
                "¿Me pasan el contacto del asesor?",
            ],
            es_qr=True,
        ),
        "talk": "11pm, oficina cerrada. El sistema lo califica CALIENTE y avisa al asesor. No se enfría.",
    },
]

_NIVEL_EMOJI = {"frio": "🔵", "tibio": "🟡", "caliente": "🔥"}


def main() -> None:
    print("\n" + "=" * 66)
    print("  CONTEXTO AI · Calificador de leads 24/7 — Demo Linden (Puebla)")
    print("=" * 66)
    for c in CASOS:
        r = analizar_intencion(**c["kwargs"])
        print(f"\n{c['titulo']}")
        print(f"  Contexto: {c['contexto']}")
        for m in c["kwargs"]["mensajes_usuario"]:
            print(f'    💬 "{m}"')
        print(f"  → Estado:  {r['estado'].upper()}")
        print(f"  → Nivel:   {_NIVEL_EMOJI.get(r['nivel'], '')} {r['nivel'].upper()}"
              f"   (score {r['score']}/100)")
        print(f"  → Handoff al asesor: {'SÍ ✅' if r['handoff_sugerido'] else 'todavía no'}")
        print(f"  → Por qué: {', '.join(r['razones'][:3])}")
        print(f"  → Acción:  {r['accion_sugerida']}")
        print(f"  🗣️  {c['talk']}")
    print("\n" + "=" * 66)
    print("  Determinista → 0 costo de LLM por lead, y SIEMPRE explicable (el")
    print("  'por qué'). Por eso escala a miles de interesados sin quemar dinero.")
    print("=" * 66 + "\n")


if __name__ == "__main__":
    main()
