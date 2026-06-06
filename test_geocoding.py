"""Test geocoding tool chain: address -> coords -> ST_DWithin"""
import asyncio
import json

from app.agent.tools import tool_geocode_address, tool_search_nearby_assets
from app.database import engine

TEST_ADDRESSES = [
    "Av. Gonzalez Suarez y Alemania, Quito",
    "Centro Historico Quito",
    "Cumbaya, Quito",
]

async def main():
    print("\n[TEST GEOCODING + BUSQUEDA ESPACIAL]")
    print("=" * 50)

    for addr in TEST_ADDRESSES:
        print(f"\nDireccion: {addr}")
        r1 = await tool_geocode_address.ainvoke({"address": addr})
        d1 = json.loads(r1)

        if not d1.get("found"):
            print(f"  NO ENCONTRADA: {d1.get('message')}")
            continue

        print(f"  Resolvio: {d1['address_resolved'][:60]}")
        print(f"  Coords:   lat={d1['latitude']}, lon={d1['longitude']}")

        r2 = await tool_search_nearby_assets.ainvoke({
            "latitude": d1["latitude"],
            "longitude": d1["longitude"],
            "radius_meters": 1500,
        })
        d2 = json.loads(r2)
        total = d2.get("total", 0)
        print(f"  Activos en 1.5km: {total}")
        for a in d2.get("assets", [])[:2]:
            dist = a["distancia_metros"]
            label = a["direccion_estandarizada"][:55]
            print(f"    - {label} ({dist}m)")

    print("\n[OK] Chain geocoding -> PostGIS operativa\n")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
