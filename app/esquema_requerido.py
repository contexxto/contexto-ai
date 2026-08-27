"""AUTH-READ-GATE.1 · HOLD-2 — el esquema que el gate necesita para poder decidir.

## El fallo que esto cierra

`_exigir_autoridad` corre en **cada** turno de `POST /chat` y en los 18 endpoints del gate.
Su consulta lee `resume_token_hash` y `resume_revoked_at`. Si la migración 027 no está
aplicada, esas columnas no existen y la consulta **falla** — no deniega, falla. El resultado
no es una degradación parcial: el chat deja de funcionar para todo el mundo, autenticados
incluidos, con un 500 que no explica nada.

Y hasta ahora nada garantizaba el orden: `render.yaml` y el `Dockerfile` **no aplican
migraciones**. El despliegue dependía de que alguien se acordara.

## Por qué una comprobación y no un `CREATE TABLE` en el arranque

Aplicar DDL al arrancar es tentador y es una mala idea aquí: con varias réplicas, cada una
correría la migración a la vez; un despliegue fallido dejaría el esquema medio migrado sin
que nadie lo pidiera; y convierte cada arranque en una operación de escritura sobre la base.

La migración es un acto **explícito** (`python -m app.esquema_requerido --aplicar`, o el
runbook del reporte 13). El arranque solo **comprueba** — y si falta algo, se niega a servir.

## Por qué fallar es mejor que arrancar

Un proceso que arranca sin las columnas atiende peticiones que fallarán todas. El health
check pasa, Render lo da por bueno, y el error aparece en la cara del usuario. Fallar en el
arranque hace que el despliegue no progrese, que la versión anterior siga sirviendo, y que
el mensaje llegue a quien puede arreglarlo.
"""

from __future__ import annotations

import pathlib

from sqlalchemy import text

from app.database import AsyncSessionLocal

# Lo que el gate necesita para poder decidir. No es "todo el esquema": es exactamente lo
# que `app/sesion_autoridad.py` lee o escribe. Si esa consulta cambia, esta lista cambia.
COLUMNAS_REQUERIDAS: dict[str, tuple[str, ...]] = {
    "chat_sessions": (
        "resume_token_hash",     # lo compara `_decidir`
        "resume_issued_at",      # lo escribe el bootstrap anónimo
        "resume_revoked_at",     # lo comprueba `_decidir` y lo sella el claim
        "creada_por_servidor",   # distingue creación de reanudación
    ),
}

MIGRACION = "migrations/027_session_resume_capability.sql"


class EsquemaIncompleto(RuntimeError):
    """Falta algo que el gate necesita. Lleva QUÉ falta y CÓMO arreglarlo — nunca datos."""


async def columnas_faltantes(db=None) -> dict[str, list[str]]:
    """Qué falta, por tabla. Diccionario vacío = el esquema está listo.

    Se consulta `information_schema` en una sola ida y vuelta. No se toca ninguna fila de
    usuario: esto es introspección, no lectura de datos.
    """
    consulta = text(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_name = ANY(:tablas)"
    )
    parametros = {"tablas": list(COLUMNAS_REQUERIDAS)}

    if db is not None:
        filas = (await db.execute(consulta, parametros)).all()
    else:
        async with AsyncSessionLocal() as propio:
            filas = (await propio.execute(consulta, parametros)).all()

    presentes: dict[str, set[str]] = {}
    for tabla, columna in filas:
        presentes.setdefault(tabla, set()).add(columna)

    faltan = {}
    for tabla, columnas in COLUMNAS_REQUERIDAS.items():
        ausentes = [c for c in columnas if c not in presentes.get(tabla, set())]
        if ausentes:
            faltan[tabla] = ausentes
    return faltan


async def exigir_esquema(db=None) -> None:
    """Levanta `EsquemaIncompleto` si el gate no puede funcionar. Se llama en el arranque.

    El mensaje nombra columnas y la migración que las crea. **Nunca** incluye valores: aquí
    no hay secretos que filtrar, y mantenerlo así evita que alguien añada uno mañana.
    """
    faltan = await columnas_faltantes(db)
    if not faltan:
        return

    detalle = "; ".join(f"{t}: {', '.join(cs)}" for t, cs in sorted(faltan.items()))
    raise EsquemaIncompleto(
        f"AUTH-READ-GATE.1 no puede arrancar — faltan columnas [{detalle}]. "
        f"Aplica {MIGRACION} antes de desplegar este código. "
        f"Sin ellas, la autorización de cada conversación falla y el chat cae por completo."
    )


async def aplicar_migracion(ruta: str = MIGRACION, db=None) -> None:
    """Aplica la migración. **Explícito, nunca automático en el arranque.**

    La 027 es idempotente (`ADD COLUMN IF NOT EXISTS`), así que repetirla es seguro.

    ## Por qué baja al driver en vez de usar `session.execute(text(...))`

    Porque **no funciona**: `asyncpg` usa el protocolo extendido (sentencias preparadas) y
    ahí una sentencia preparada es **una** sentencia. Un fichero de migración con varios
    `ALTER` y `COMMENT` revienta con `cannot insert multiple commands into a prepared
    statement`. La versión anterior de esta función lo hacía así y habría fallado el día del
    despliegue — lo descubrió el primer intento de correrla contra un Postgres real, que era
    justamente el motivo del HOLD.

    La alternativa —trocear el fichero por `;`— es la trampa de siempre: un `;` dentro de un
    literal (los `COMMENT ON … IS '…'` de la 027 son candidatos naturales) partiría la
    sentencia por la mitad. Se usa el protocolo simple del driver, que sí acepta un script.
    """
    sql = pathlib.Path(ruta).read_text(encoding="utf-8")

    async def _ejecutar(sesion) -> None:
        conexion = await sesion.connection()
        cruda = await conexion.get_raw_connection()
        # `driver_connection` es la conexión de asyncpg. Su `execute()` sin argumentos usa
        # el protocolo simple, que acepta varias sentencias en un mismo texto.
        await cruda.driver_connection.execute(sql)

    if db is not None:
        await _ejecutar(db)
        await db.commit()
        return
    async with AsyncSessionLocal() as propio:
        await _ejecutar(propio)
        await propio.commit()


async def _main() -> int:
    import sys

    aplicar = "--aplicar" in sys.argv
    if aplicar:
        await aplicar_migracion()
        print(f"aplicada: {MIGRACION}")

    faltan = await columnas_faltantes()
    if faltan:
        for tabla, columnas in sorted(faltan.items()):
            print(f"FALTA  {tabla}: {', '.join(columnas)}")
        print(f"\nAplica {MIGRACION} (o vuelve a correr con --aplicar).")
        return 1

    print("ESQUEMA COMPLETO — AUTH-READ-GATE.1 puede arrancar.")
    return 0


if __name__ == "__main__":
    import asyncio

    raise SystemExit(asyncio.run(_main()))
