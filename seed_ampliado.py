"""
Contexto AI V2 -- Seed Ampliado: 30 activos en 6 sectores de Quito
Sectores: La Carolina, Gonzalez Suarez, Cumbaya, Norte (Condado),
          Centro Historico, Quito Sur (El Camal)

Run: python seed_ampliado.py
"""
import asyncio
import uuid

from geoalchemy2.elements import WKTElement
from sqlalchemy import text

from app.database import AsyncSessionLocal, engine
from app.models import ActivoInmutable, FichaTecnicaMantenimiento, TransaccionTemporal
from datetime import date

# ---------------------------------------------------------------------------
# Dataset: 30 activos ultra-realistas distribuidos por Quito
# Coordenadas validadas contra WGS84 (lat, lon)
# ---------------------------------------------------------------------------
ASSETS = [
    # ── SECTOR 1: La Carolina (5) ──────────────────────────────────────────
    {
        "sector": "La Carolina",
        "direccion": "Av. 6 de Diciembre N36-109 y Bosmediano, La Carolina, Quito",
        "lat": -0.1795, "lon": -78.4825, "piso": 10,
        "walk": 92, "ruido": "MEDIO", "trafico": 7800, "densidad": 9200, "vegetal": 31.5,
    },
    {
        "sector": "La Carolina",
        "direccion": "Calle Portugal E12-76 y 6 de Diciembre, Quito",
        "lat": -0.1815, "lon": -78.4835, "piso": 6,
        "walk": 89, "ruido": "MEDIO", "trafico": 5400, "densidad": 7800, "vegetal": 26.8,
    },
    {
        "sector": "La Carolina",
        "direccion": "Av. Eloy Alfaro N34-451 y Portugal, Quito",
        "lat": -0.1855, "lon": -78.4855, "piso": 14,
        "walk": 90, "ruido": "ALTO", "trafico": 14200, "densidad": 10500, "vegetal": 18.2,
    },
    {
        "sector": "La Carolina",
        "direccion": "Calle Catalina Aldaz N34-208 y Portugal, Quito",
        "lat": -0.1800, "lon": -78.4860, "piso": 4,
        "walk": 86, "ruido": "BAJO", "trafico": 1450, "densidad": 5600, "vegetal": 39.4,
    },
    {
        "sector": "La Carolina",
        "direccion": "Av. De Los Shyris N35-174 y Suecia, Quito",
        "lat": -0.1822, "lon": -78.4872, "piso": 8,
        "walk": 94, "ruido": "MEDIO", "trafico": 9100, "densidad": 11200, "vegetal": 24.7,
    },
    # ── SECTOR 2: Gonzalez Suarez / La Paz (5) ────────────────────────────
    {
        "sector": "Gonzalez Suarez",
        "direccion": "Av. Gonzalez Suarez N27-160 y Alemania, Quito",
        "lat": -0.2045, "lon": -78.4892, "piso": 18,
        "walk": 78, "ruido": "ALTO", "trafico": 22000, "densidad": 13000, "vegetal": 8.5,
    },
    {
        "sector": "Gonzalez Suarez",
        "direccion": "Calle Alemania E12-34 y Gonzalez Suarez, Quito",
        "lat": -0.2052, "lon": -78.4880, "piso": 12,
        "walk": 75, "ruido": "MEDIO", "trafico": 6800, "densidad": 9800, "vegetal": 15.3,
    },
    {
        "sector": "Gonzalez Suarez",
        "direccion": "Av. Colon E4-50 y 12 de Octubre, La Mariscal, Quito",
        "lat": -0.2101, "lon": -78.4940, "piso": 7,
        "walk": 96, "ruido": "ALTO", "trafico": 19500, "densidad": 14500, "vegetal": 12.0,
    },
    {
        "sector": "Gonzalez Suarez",
        "direccion": "Calle Juan Pablo Sainz y Gonzalez Suarez, Quito",
        "lat": -0.2038, "lon": -78.4905, "piso": 5,
        "walk": 72, "ruido": "BAJO", "trafico": 1100, "densidad": 5200, "vegetal": 44.0,
    },
    {
        "sector": "Gonzalez Suarez",
        "direccion": "Av. 12 de Octubre N24-593 y Cordero, Quito",
        "lat": -0.2115, "lon": -78.4920, "piso": 9,
        "walk": 88, "ruido": "MEDIO", "trafico": 8300, "densidad": 10200, "vegetal": 20.5,
    },
    # ── SECTOR 3: Cumbaya / Urbanizaciones (5) ────────────────────────────
    {
        "sector": "Cumbaya",
        "direccion": "Av. Interoceánica Km 13.5, Urbanizacion El Pilar, Cumbaya",
        "lat": -0.1980, "lon": -78.4320, "piso": 2,
        "walk": 45, "ruido": "BAJO", "trafico": 3200, "densidad": 2800, "vegetal": 65.0,
    },
    {
        "sector": "Cumbaya",
        "direccion": "Calle Francisco de Orellana y Av. Pampite, Cumbaya, Quito",
        "lat": -0.1975, "lon": -78.4340, "piso": 3,
        "walk": 52, "ruido": "BAJO", "trafico": 2400, "densidad": 3200, "vegetal": 58.5,
    },
    {
        "sector": "Cumbaya",
        "direccion": "Av. Pampite N°5-23 y De Los Conquistadores, Cumbaya",
        "lat": -0.1965, "lon": -78.4355, "piso": 4,
        "walk": 58, "ruido": "MEDIO", "trafico": 5600, "densidad": 4500, "vegetal": 47.2,
    },
    {
        "sector": "Cumbaya",
        "direccion": "Calle Chimborazo y Av. Simon Bolivar, Cumbaya, Quito",
        "lat": -0.2010, "lon": -78.4280, "piso": 2,
        "walk": 38, "ruido": "BAJO", "trafico": 1800, "densidad": 2100, "vegetal": 72.0,
    },
    {
        "sector": "Cumbaya",
        "direccion": "Av. Robles y Francisco de Orellana, El Batán, Cumbaya",
        "lat": -0.1990, "lon": -78.4300, "piso": 6,
        "walk": 61, "ruido": "MEDIO", "trafico": 4900, "densidad": 5800, "vegetal": 39.8,
    },
    # ── SECTOR 4: Norte / El Condado (5) ──────────────────────────────────
    {
        "sector": "Norte - El Condado",
        "direccion": "Av. Diego de Vasquez y Condado Shopping, Norte, Quito",
        "lat": -0.1022, "lon": -78.5010, "piso": 5,
        "walk": 70, "ruido": "MEDIO", "trafico": 8900, "densidad": 6800, "vegetal": 22.3,
    },
    {
        "sector": "Norte - El Condado",
        "direccion": "Calle Antonio Jose de Sucre N78-24, El Condado, Quito",
        "lat": -0.1035, "lon": -78.5025, "piso": 3,
        "walk": 65, "ruido": "BAJO", "trafico": 2100, "densidad": 4200, "vegetal": 35.6,
    },
    {
        "sector": "Norte - El Condado",
        "direccion": "Av. Occidental y De La Prensa, Cotocollao, Quito",
        "lat": -0.1105, "lon": -78.5080, "piso": 4,
        "walk": 68, "ruido": "ALTO", "trafico": 15600, "densidad": 8900, "vegetal": 16.4,
    },
    {
        "sector": "Norte - El Condado",
        "direccion": "Calle Nicolas Arteta y Marchena, Cotocollao, Quito",
        "lat": -0.1092, "lon": -78.5055, "piso": 2,
        "walk": 62, "ruido": "BAJO", "trafico": 1350, "densidad": 3600, "vegetal": 41.2,
    },
    {
        "sector": "Norte - El Condado",
        "direccion": "Av. Diego de Vasquez y Mariana de Jesus, Norte, Quito",
        "lat": -0.1045, "lon": -78.5040, "piso": 8,
        "walk": 74, "ruido": "MEDIO", "trafico": 7200, "densidad": 7100, "vegetal": 28.9,
    },
    # ── SECTOR 5: Centro Historico (5) ────────────────────────────────────
    {
        "sector": "Centro Historico",
        "direccion": "Calle Garcia Moreno N2-60 y Sucre, Centro Historico, Quito",
        "lat": -0.2201, "lon": -78.5120, "piso": 3,
        "walk": 98, "ruido": "ALTO", "trafico": 21000, "densidad": 18000, "vegetal": 5.2,
    },
    {
        "sector": "Centro Historico",
        "direccion": "Calle Venezuela y Chile, Centro Historico, Quito",
        "lat": -0.2215, "lon": -78.5135, "piso": 4,
        "walk": 97, "ruido": "ALTO", "trafico": 19500, "densidad": 17200, "vegetal": 6.8,
    },
    {
        "sector": "Centro Historico",
        "direccion": "Av. 24 de Mayo y Cuenca, La Loma, Quito",
        "lat": -0.2240, "lon": -78.5150, "piso": 2,
        "walk": 92, "ruido": "MEDIO", "trafico": 9800, "densidad": 14500, "vegetal": 11.0,
    },
    {
        "sector": "Centro Historico",
        "direccion": "Calle Mejia N4-30 y Guayaquil, Centro Historico, Quito",
        "lat": -0.2195, "lon": -78.5108, "piso": 5,
        "walk": 96, "ruido": "ALTO", "trafico": 18200, "densidad": 16800, "vegetal": 4.5,
    },
    {
        "sector": "Centro Historico",
        "direccion": "Calle Benalcazar N2-12 y Bolivar, Quito",
        "lat": -0.2208, "lon": -78.5125, "piso": 3,
        "walk": 95, "ruido": "MEDIO", "trafico": 11000, "densidad": 15200, "vegetal": 7.3,
    },
    # ── SECTOR 6: Sur / El Camal / Solanda (5) ────────────────────────────
    {
        "sector": "Sur - El Camal",
        "direccion": "Av. Morona N°34-28 y El Camal, Sur, Quito",
        "lat": -0.2650, "lon": -78.5205, "piso": 3,
        "walk": 72, "ruido": "MEDIO", "trafico": 7400, "densidad": 9800, "vegetal": 14.2,
    },
    {
        "sector": "Sur - El Camal",
        "direccion": "Calle Manglar Alto y Av. Cardenal de la Torre, Solanda, Quito",
        "lat": -0.2720, "lon": -78.5280, "piso": 2,
        "walk": 68, "ruido": "BAJO", "trafico": 2800, "densidad": 7500, "vegetal": 19.6,
    },
    {
        "sector": "Sur - El Camal",
        "direccion": "Av. Maldonado S25-80 y Cusubamba, Sur, Quito",
        "lat": -0.2690, "lon": -78.5245, "piso": 4,
        "walk": 75, "ruido": "ALTO", "trafico": 16800, "densidad": 12200, "vegetal": 9.8,
    },
    {
        "sector": "Sur - El Camal",
        "direccion": "Calle Gral Enriquez y Napo, Chimbacalle, Quito",
        "lat": -0.2445, "lon": -78.5185, "piso": 3,
        "walk": 80, "ruido": "MEDIO", "trafico": 6200, "densidad": 10400, "vegetal": 16.8,
    },
    {
        "sector": "Sur - El Camal",
        "direccion": "Av. Pedro Vicente Maldonado y Cusubamba, Villa Flora, Quito",
        "lat": -0.2608, "lon": -78.5220, "piso": 5,
        "walk": 78, "ruido": "MEDIO", "trafico": 8100, "densidad": 11000, "vegetal": 13.5,
    },
]

# Fichas tecnicas generadas automaticamente segun año y sector
def _ficha(asset_idx: int, asset: dict) -> dict:
    sector = asset["sector"]
    if "Cumbaya" in sector:
        return {
            "tuberia": "Termofusion",
            "año": 2018, "estructura": "Hormigon Armado", "acabados": "Porcelanato Alto Trafico",
            "cisterna": date(2024, 5, 20), "techo": date(2024, 2, 14),
            "fachada": date(2023, 8, 10), "cableado": date(2022, 4, 5),
            "monto": 38000.00, "desc": "Impermeabilizacion bicapa, tuberias termofusion, pintura texturizada.",
        }
    elif "Gonzalez" in sector:
        return {
            "tuberia": "PVC Presion",
            "año": 2008, "estructura": "Hormigon Armado", "acabados": "Porcelanato Estandar",
            "cisterna": date(2022, 9, 18), "techo": date(2020, 11, 22),
            "fachada": date(2021, 6, 15), "cableado": date(2019, 3, 8),
            "monto": 22000.00, "desc": "Mantenimiento periodico. Techo requiere revision en 2026.",
        }
    elif "Centro" in sector:
        return {
            "tuberia": "Cobre/PVC",
            "año": 1985, "estructura": "Mamposteria Confinada", "acabados": "Ceramica Estandar",
            "cisterna": date(2021, 4, 12), "techo": date(2018, 7, 30),
            "fachada": date(2022, 2, 20), "cableado": date(2015, 10, 5),
            "monto": 9500.00, "desc": "Edificio patrimonial. Restauracion parcial 2022. Riesgo sismico moderado.",
        }
    elif "Norte" in sector or "Condado" in sector:
        return {
            "tuberia": "PVC Presion",
            "año": 2012, "estructura": "Hormigon Armado", "acabados": "Ceramica Estandar",
            "cisterna": date(2023, 1, 25), "techo": date(2022, 8, 5),
            "fachada": date(2023, 3, 18), "cableado": date(2021, 7, 14),
            "monto": 16500.00, "desc": "Mantenimiento regular. Cisterna revisada anualmente.",
        }
    elif "Sur" in sector or "Camal" in sector:
        return {
            "tuberia": "Cobre/PVC",
            "año": 1999, "estructura": "Mamposteria Confinada", "acabados": "Ceramica Estandar",
            "cisterna": date(2021, 6, 8), "techo": date(2019, 3, 14),
            "fachada": date(2020, 11, 22), "cableado": date(2017, 9, 3),
            "monto": 8200.00, "desc": "Mantenimiento basico. Impermeabilizacion pendiente desde 2019.",
        }
    else:  # La Carolina
        return {
            "tuberia": "Termofusion" if asset_idx % 2 == 0 else "PVC Presion",
            "año": 2014 + (asset_idx % 8), "estructura": "Hormigon Armado",
            "acabados": "Porcelanato Estandar",
            "cisterna": date(2024, 3, 10), "techo": date(2023, 7, 5),
            "fachada": date(2023, 11, 18), "cableado": date(2022, 5, 20),
            "monto": 24000.00 + (asset_idx * 1200),
            "desc": "Mantenimiento preventivo regular. Buenas condiciones generales.",
        }


def _point(lon: float, lat: float):
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


async def seed_ampliado() -> None:
    print("\n[SEED AMPLIADO] 30 activos en 6 sectores de Quito")
    print("=" * 55)

    async with AsyncSessionLocal() as session:
        # Verificar duplicados por direccion
        result = await session.execute(
            text("SELECT direccion_estandarizada FROM activos_inmutables")
        )
        existing = {r[0] for r in result.fetchall()}

        inserted = 0
        skipped = 0

        for i, a in enumerate(ASSETS):
            if a["direccion"] in existing:
                skipped += 1
                continue

            asset_id = uuid.uuid4()
            asset = ActivoInmutable(
                id=asset_id,
                geom=_point(a["lon"], a["lat"]),
                direccion_estandarizada=a["direccion"],
                piso_altura=a["piso"],
                walk_score=a["walk"],
                walk_score_fuente="heuristico",  # score sembrado por sector → estimación, no OSM
                score_ruido_predictivo=a["ruido"],
                volumen_trafico_historico=a["trafico"],
                densidad_poblacional_pico=a["densidad"],
                porcentaje_cobertura_vegetal=a["vegetal"],
            )
            session.add(asset)
            await session.flush()

            f = _ficha(i, a)
            ficha = FichaTecnicaMantenimiento(
                id=uuid.uuid4(),
                activo_id=asset_id,
                tipo_tuberia=f["tuberia"],
                año_construccion=f["año"],
                tipo_estructura=f["estructura"],
                calidad_acabados=f["acabados"],
                ultimo_mantenimiento_cisterna=f["cisterna"],
                ultima_impermeabilizacion_techo=f["techo"],
                ultima_pintura_fachada=f["fachada"],
                ultimo_cambio_cableado_electrico=f["cableado"],
                monto_invertido_mejoras=f["monto"],
                descripcion_mejoras=f["desc"],
            )
            session.add(ficha)

            # Transaccion para activos seleccionados
            if i % 3 == 0:
                precio = 185000 + (i * 8500) if a["sector"] != "Sur - El Camal" else 89000 + (i * 3200)
                tx = TransaccionTemporal(
                    id=uuid.uuid4(), activo_id=asset_id,
                    tipo_operacion="VENTA" if i % 2 == 0 else "ARRIENDO",
                    precio=precio, estado_anuncio="ACTIVO",
                )
                session.add(tx)

            print(f"  [OK] [{a['sector']}] {a['direccion'][:55]}")
            inserted += 1

        await session.commit()

        total = await session.execute(text("SELECT COUNT(*) FROM activos_inmutables"))
        print(f"\n[DB] Insertados: {inserted} | Omitidos (ya existian): {skipped}")
        print(f"[DB] Total activos en catastro: {total.scalar()}")
        print("\n[OK] Seed ampliado completado.\n")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_ampliado())
