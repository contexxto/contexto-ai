"""Baseline del embudo de intención — el "ritual cero" de docs/RITUALES_DE_DATOS_CONTEXTO.md.

Mismas consultas que scripts/baseline_intencion.sql, pero SIN necesitar psql (que no está
instalado en las máquinas de trabajo) y usando la conexión que ya sabe usar la app
(app.database → Supabase vía DATABASE_URL_OVERRIDE).

    ./.venv/Scripts/python.exe scripts/baseline_intencion.py

SOLO LECTURA: ni un INSERT, ni un UPDATE, ni un DDL. Se puede correr contra producción.

DISCIPLINA (heredada de app/lift.py): con N < UMBRAL_N no se reportan ratios, solo conteos.
Un % sobre N=4 miente porque *parece* dato.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.lift import UMBRAL_N  # noqa: E402

# ── Consultas ────────────────────────────────────────────────

Q_EMBUDO = """
SELECT estado, nivel, count(*) AS sesiones,
       count(*) FILTER (WHERE handoff_sugerido) AS con_handoff,
       round(avg(turnos), 1) AS turnos_prom
FROM intencion_sesion GROUP BY estado, nivel ORDER BY sesiones DESC
"""

Q_SEMANAS = """
SELECT date_trunc('week', primer_visto)::date AS semana, count(*) AS sesiones_nuevas,
       count(*) FILTER (WHERE handoff_sugerido) AS handoffs_sugeridos
FROM intencion_sesion GROUP BY 1 ORDER BY 1 DESC LIMIT 12
"""

Q_TRANSICIONES = """
SELECT estado, count(*) AS transiciones, count(DISTINCT session_id) AS sesiones,
       min(creado_en)::date AS desde, max(creado_en)::date AS hasta
FROM intencion_evento GROUP BY estado ORDER BY transiciones DESC
"""

Q_METRICA = """
WITH primer_lead AS (
    SELECT session_id, min(creado_en) AS t_lead FROM handoff_mensaje
    WHERE autor = 'lead' GROUP BY session_id),
primer_corredor AS (
    SELECT session_id, min(creado_en) AS t_corredor FROM handoff_mensaje
    WHERE autor = 'corredor' GROUP BY session_id),
pareado AS (
    SELECT l.session_id, l.t_lead, c.t_corredor, c.t_corredor - l.t_lead AS espera
    FROM primer_lead l LEFT JOIN primer_corredor c USING (session_id))
SELECT count(*) AS leads_escribieron,
       count(t_corredor) AS atendidos_alguna_vez,
       count(*) FILTER (WHERE espera <= interval '24 hours') AS atendidos_menos_24h,
       count(*) FILTER (WHERE t_corredor IS NULL) AS nunca_atendidos,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY espera) AS espera_mediana,
       max(espera) AS espera_peor
FROM pareado
"""

Q_COLA = """
WITH primer_lead AS (
    SELECT session_id, min(creado_en) AS t_lead FROM handoff_mensaje
    WHERE autor = 'lead' GROUP BY session_id),
primer_corredor AS (
    SELECT session_id, min(creado_en) AS t_corredor FROM handoff_mensaje
    WHERE autor = 'corredor' GROUP BY session_id)
SELECT l.session_id, l.t_lead, now() - l.t_lead AS esperando_hace,
       s.estado, s.nivel, s.score
FROM primer_lead l LEFT JOIN primer_corredor c USING (session_id)
LEFT JOIN intencion_sesion s ON s.session_id = l.session_id
WHERE c.t_corredor IS NULL ORDER BY l.t_lead ASC LIMIT 25
"""

Q_SALUD = """
SELECT max(actualizado_en) AS ultima_escritura,
       now() - max(actualizado_en) AS hace,
       count(*) FILTER (WHERE actualizado_en > now() - interval '24 hours') AS escrituras_24h
FROM intencion_sesion
"""

Q_EXISTE = "SELECT to_regclass('public.handoff_mensaje') IS NOT NULL AS existe"


def tabla(filas, cols) -> str:
    if not filas:
        return "  (sin filas)"
    anchos = [max(len(str(c)), *(len(str(f[i])) for f in filas)) for i, c in enumerate(cols)]
    sep = "  " + "-+-".join("-" * a for a in anchos)
    out = ["  " + " | ".join(str(c).ljust(anchos[i]) for i, c in enumerate(cols)), sep]
    out += ["  " + " | ".join(str(f[i]).ljust(anchos[i]) for i in range(len(cols))) for f in filas]
    return "\n".join(out)


async def bloque(db, titulo: str, q: str) -> list:
    print(f"\n== {titulo} ==")
    res = await db.execute(text(q))
    filas = res.fetchall()
    print(tabla(filas, list(res.keys())))
    return filas


async def main() -> int:
    async with AsyncSessionLocal() as db:
        await bloque(db, "1. Embudo por estado (foto actual)", Q_EMBUDO)
        await bloque(db, "2. Volumen por semana", Q_SEMANAS)
        await bloque(db, "3. Transiciones del embudo (serie del lift)", Q_TRANSICIONES)

        existe = (await db.execute(text(Q_EXISTE))).scalar()
        if not existe:
            print("\n== 4. LA METRICA: intencion atendida ==")
            print("  handoff_mensaje NO existe todavia: nadie ha abierto un handoff.")
            print("  Baseline de la metrica = 0. No es un error.")
            metrica = None
        else:
            metrica = (await bloque(db, "4. LA METRICA: intencion atendida", Q_METRICA))[0]
            await bloque(db, "5. Cola viva: leads esperando AHORA", Q_COLA)

        salud = (await bloque(db, "6. Salud de la instrumentacion", Q_SALUD))[0]

    print("\n" + "=" * 70)
    print("LECTURA")
    print("=" * 70)

    if salud.escrituras_24h == 0:
        print("!! CERO escrituras de intencion en 24h.")
        print("   Si habia oferta activa, NO es poca demanda: revisa el log 'intencion'")
        print("   (docs/AUDITORIA_Fallos_Silenciosos_2026-07-31.md). Cero = roto hasta probar")
        print("   lo contrario.")
    else:
        print(f"OK instrumentacion viva: {salud.escrituras_24h} escrituras en 24h.")

    if metrica is not None:
        n = metrica.leads_escribieron
        print(f"\nLeads que escribieron: {n}")
        print(f"Atendidos <24h:        {metrica.atendidos_menos_24h}   <-- LA METRICA")
        print(f"Nunca atendidos:       {metrica.nunca_atendidos}")
        if n < UMBRAL_N:
            print(f"\nN={n} < UMBRAL_N={UMBRAL_N}: estado 'acumulando'. NO calcules un porcentaje;")
            print("un % sobre N bajo miente porque *parece* dato (regla de app/lift.py).")
        else:
            pct = round(100 * metrica.atendidos_menos_24h / n)
            print(f"\nTasa de atencion <24h: {pct}%  (N={n}, ya sobre el umbral)")

    print("\nAnota estos numeros en docs/RITUALES_DE_DATOS_CONTEXTO.md seccion 2.")
    print("La metrica queda CONGELADA hasta 2026-10-29.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
