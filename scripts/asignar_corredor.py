"""
Asigna un corredor como owner_user_id de todas las propiedades sin dueño.

Corre:  python scripts/asignar_corredor.py
Lee DATABASE_URL_OVERRIDE del .env para conectarse a Supabase.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Cargar .env manualmente
from pathlib import Path
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

DB_URL = os.getenv("DATABASE_URL_OVERRIDE", "").strip()
if not DB_URL:
    print("❌ DATABASE_URL_OVERRIDE no está en el .env.")
    print("   Agrégala: DATABASE_URL_OVERRIDE=postgresql+asyncpg://postgres.PROJECT:PASSWORD@...supabase.com:5432/postgres")
    sys.exit(1)

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text


async def main():
    engine = create_async_engine(DB_URL, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        # 1. Buscar usuario por email
        email = "contexxto.ai@gmail.com"
        row = (await db.execute(text(
            "SELECT id FROM auth.users WHERE email = :email LIMIT 1"
        ), {"email": email})).first()

        if not row:
            print(f"❌ No encontré usuario con email {email} en auth.users")
            await engine.dispose()
            return

        user_id = str(row[0])
        print(f"✅ Usuario encontrado: {email} → {user_id}")

        # 2. Ver todas las propiedades
        activos = (await db.execute(text(
            "SELECT id, titulo, owner_user_id FROM activos_inmutables ORDER BY created_at"
        ))).fetchall()

        print(f"\n📦 Total propiedades en el catastro: {len(activos)}")
        sin_dueno = [a for a in activos if not a[2]]
        con_dueno = [a for a in activos if a[2]]

        print(f"   Sin corredor asignado: {len(sin_dueno)}")
        print(f"   Ya tienen corredor:    {len(con_dueno)}")

        if not sin_dueno:
            print("\n✅ Todas las propiedades ya tienen corredor asignado.")
            await engine.dispose()
            return

        print("\nPropiedades que se van a asignar a ti:")
        for a in sin_dueno:
            print(f"   • {a[1]} ({a[0]})")

        confirm = input(f"\n¿Asignar las {len(sin_dueno)} propiedades a {email}? (s/n): ").strip().lower()
        if confirm != "s":
            print("Cancelado.")
            await engine.dispose()
            return

        # 3. Actualizar
        result = await db.execute(text(
            "UPDATE activos_inmutables SET owner_user_id = :uid WHERE owner_user_id IS NULL"
        ), {"uid": user_id})
        await db.commit()

        print(f"\n🎉 {result.rowcount} propiedades asignadas a {email}")
        print("   Ahora el handoff te llega directo a ti cuando un lead pide contacto.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
