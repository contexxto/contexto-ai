"""
Contexto AI V2 — Seed Script
Hydrates PostGIS with mock assets centered on La Carolina financial district, Quito.
Run: python seed_data.py
"""
import asyncio
import uuid
from datetime import date

from geoalchemy2.elements import WKTElement
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, engine
from app.models import (
    ActivoInmutable,
    FichaTecnicaMantenimiento,
    HistorialEventoUrbano,
    TransaccionTemporal,
)


# ---------------------------------------------------------------------------
# Asset definitions — La Carolina macro-sector, Quito
# All coordinates validated against WGS84 (lat, lon)
# ---------------------------------------------------------------------------
ASSETS = [
    {
        "alias": "Building A — Torre Premium Quiet (Av. República)",
        "lat": -0.1810,
        "lon": -78.4820,
        "direccion": "Av. República del Salvador N34-183, La Carolina, Quito",
        "piso_altura": 8,
        "walk_score": 95,
        "score_ruido": "BAJO",
        "trafico": 1200,
        "densidad": 8500,
        "cobertura_vegetal": 42.3,
    },
    {
        "alias": "Building B — Alta Exposición Av. Amazonas",
        "lat": -0.1845,
        "lon": -78.4865,
        "direccion": "Av. Amazonas N35-17 y Atahualpa, La Carolina, Quito",
        "piso_altura": 12,
        "walk_score": 88,
        "score_ruido": "ALTO",
        "trafico": 18400,
        "densidad": 12000,
        "cobertura_vegetal": 14.7,
    },
    {
        "alias": "Building C — Residencial Medio Parque",
        "lat": -0.1798,
        "lon": -78.4850,
        "direccion": "Calle Los Shyris N35-61 y Portugal, Quito",
        "piso_altura": 5,
        "walk_score": 91,
        "score_ruido": "MEDIO",
        "trafico": 6300,
        "densidad": 7200,
        "cobertura_vegetal": 28.1,
    },
    {
        "alias": "Building D — Oficinas Corporativas NNUU",
        "lat": -0.1835,
        "lon": -78.4802,
        "direccion": "Av. Naciones Unidas E10-44 y Amazonas, Quito",
        "piso_altura": 15,
        "walk_score": 93,
        "score_ruido": "MEDIO",
        "trafico": 9100,
        "densidad": 11500,
        "cobertura_vegetal": 22.5,
    },
    {
        "alias": "Building E — Residencial Tranquilo Posterior",
        "lat": -0.1778,
        "lon": -78.4830,
        "direccion": "Calle Isla Fernandina N44-28 y Los Shyris, Quito",
        "piso_altura": 4,
        "walk_score": 87,
        "score_ruido": "BAJO",
        "trafico": 980,
        "densidad": 4800,
        "cobertura_vegetal": 51.0,
    },
]

FICHAS = [
    # Building A — Premium, recent maintenance
    {
        "alias": "Building A",
        "tipo_tuberia": "Termofusión",
        "año_construccion": 2021,
        "tipo_estructura": "Hormigón Armado",
        "calidad_acabados": "Porcelanato Alto Tráfico",
        "cisterna": date(2024, 11, 15),
        "techo": date(2025, 3, 10),
        "fachada": date(2024, 6, 20),
        "cableado": date(2023, 8, 5),
        "monto": 45000.00,
        "descripcion": "Soterramiento completo tuberías termofusión, impermeabilización techo bicapa, pintura fachada texturizada, actualización tablero eléctrico trifásico.",
    },
    # Building B — Outdated, critical vulnerabilities
    {
        "alias": "Building B",
        "tipo_tuberia": "Cobre/PVC",
        "año_construccion": 1998,
        "tipo_estructura": "Mampostería Confinada",
        "calidad_acabados": "Cerámica Estándar",
        "cisterna": date(2019, 4, 22),
        "techo": date(2017, 5, 14),
        "fachada": date(2020, 9, 3),
        "cableado": date(2016, 2, 11),
        "monto": 12000.00,
        "descripcion": "Reparcheo puntual de tuberías. Pintura fachada vinílica. Sin actualización eléctrica ni impermeabilización estructural.",
    },
    # Building C
    {
        "alias": "Building C",
        "tipo_tuberia": "PVC Presión",
        "año_construccion": 2015,
        "tipo_estructura": "Hormigón Armado",
        "calidad_acabados": "Porcelanato Estándar",
        "cisterna": date(2023, 7, 18),
        "techo": date(2022, 11, 30),
        "fachada": date(2023, 3, 14),
        "cableado": date(2021, 5, 20),
        "monto": 28500.00,
        "descripcion": "Impermeabilización monocapa, mantenimiento preventivo anual de cisternas, cableado actualizado norma NEC-11.",
    },
    # Building D
    {
        "alias": "Building D",
        "tipo_tuberia": "Termofusión",
        "año_construccion": 2019,
        "tipo_estructura": "Estructura Metálica",
        "calidad_acabados": "Mármol / Granito",
        "cisterna": date(2025, 1, 8),
        "techo": date(2024, 8, 22),
        "fachada": date(2024, 4, 11),
        "cableado": date(2022, 10, 15),
        "monto": 67000.00,
        "descripcion": "Fachada ventilada, sistema BMS de gestión de edificio, impermeabilización bicapa + membrana EPDM, instalaciones eléctricas certificadas.",
    },
    # Building E
    {
        "alias": "Building E",
        "tipo_tuberia": "PVC Presión",
        "año_construccion": 2010,
        "tipo_estructura": "Hormigón Armado",
        "calidad_acabados": "Porcelanato Estándar",
        "cisterna": date(2024, 2, 5),
        "techo": date(2023, 6, 17),
        "fachada": date(2022, 10, 28),
        "cableado": date(2020, 3, 9),
        "monto": 19500.00,
        "descripcion": "Mantenimiento preventivo regular. Pintura fachada 2022. Impermeabilización techo 2023.",
    },
]

EVENTOS_URBANOS = [
    {
        "lat": -0.1830,
        "lon": -78.4870,
        "tipo": "Obra Pública — Metro de Quito",
        "descripcion": "Extensión Línea 1 Metro de Quito: Estación La Carolina. Adjudicación SERCOP 2024. Obras civiles activas hasta 2026. Impacto: cierre parcial Av. Amazonas en horas nocturnas.",
        "restriccion_altura": None,
        "fecha_inicio": date(2024, 3, 1),
        "fecha_fin": date(2026, 6, 30),
        "impacto_plusvalia": 12.50,
    },
    {
        "lat": -0.1860,
        "lon": -78.4840,
        "tipo": "Pavimentación SERCOP — Av. Eloy Alfaro",
        "descripcion": "Repavimentación completa Av. Eloy Alfaro tramo La Carolina-González Suárez. Contrato SERCOP #2025-EPMMOP-014. Ruido de maquinaria en horario 06:00-18:00.",
        "restriccion_altura": None,
        "fecha_inicio": date(2025, 2, 15),
        "fecha_fin": date(2025, 9, 30),
        "impacto_plusvalia": 4.20,
    },
    {
        "lat": -0.1800,
        "lon": -78.4810,
        "tipo": "Zonificación Municipal — Restricción Altura",
        "descripcion": "Ordenanza Metropolitana DMQ: Lote esquinero Shyris/Portugal. Zonificación A18 permite construcción hasta 12 pisos. Riesgo de obstrucción luz natural para inmuebles de baja altura colindantes.",
        "restriccion_altura": 12,
        "fecha_inicio": date(2023, 1, 1),
        "fecha_fin": None,
        "impacto_plusvalia": -3.80,
    },
]


def _point(lon: float, lat: float) -> WKTElement:
    return WKTElement(f"POINT({lon} {lat})", srid=4326)


async def seed(session: AsyncSession) -> None:
    print("\n[SEED] Iniciando seed - Catastro La Carolina, Quito")
    print("=" * 55)

    # --- activos_inmutables ---
    asset_ids: dict[str, uuid.UUID] = {}
    for a in ASSETS:
        asset_id = uuid.uuid4()
        asset_ids[a["alias"]] = asset_id
        asset = ActivoInmutable(
            id=asset_id,
            geom=_point(a["lon"], a["lat"]),
            direccion_estandarizada=a["direccion"],
            piso_altura=a["piso_altura"],
            walk_score=a["walk_score"],
            score_ruido_predictivo=a["score_ruido"],
            volumen_trafico_historico=a["trafico"],
            densidad_poblacional_pico=a["densidad"],
            porcentaje_cobertura_vegetal=a["cobertura_vegetal"],
        )
        session.add(asset)
        print(f"  [OK] Activo: {a['alias'][:45]}")

    await session.flush()

    # --- ficha_tecnica_mantenimiento ---
    alias_to_key = {
        "Building A": "Building A — Torre Premium Quiet (Av. República)",
        "Building B": "Building B — Alta Exposición Av. Amazonas",
        "Building C": "Building C — Residencial Medio Parque",
        "Building D": "Building D — Oficinas Corporativas NNUU",
        "Building E": "Building E — Residencial Tranquilo Posterior",
    }
    for f in FICHAS:
        full_key = alias_to_key[f["alias"]]
        ficha = FichaTecnicaMantenimiento(
            id=uuid.uuid4(),
            activo_id=asset_ids[full_key],
            tipo_tuberia=f["tipo_tuberia"],
            año_construccion=f["año_construccion"],
            tipo_estructura=f["tipo_estructura"],
            calidad_acabados=f["calidad_acabados"],
            ultimo_mantenimiento_cisterna=f["cisterna"],
            ultima_impermeabilizacion_techo=f["techo"],
            ultima_pintura_fachada=f["fachada"],
            ultimo_cambio_cableado_electrico=f["cableado"],
            monto_invertido_mejoras=f["monto"],
            descripcion_mejoras=f["descripcion"],
        )
        session.add(ficha)
        print(f"  [OK] Ficha tecnica: {f['alias']} ({f['año_construccion']}, {f['tipo_tuberia']})")

    # --- transacciones_temporales ---
    transacciones = [
        {
            "activo_key": "Building A — Torre Premium Quiet (Av. República)",
            "tipo": "VENTA",
            "precio": 285000.00,
            "estado": "ACTIVO",
        },
        {
            "activo_key": "Building B — Alta Exposición Av. Amazonas",
            "tipo": "ARRIENDO",
            "precio": 1850.00,
            "estado": "ACTIVO",
        },
        {
            "activo_key": "Building C — Residencial Medio Parque",
            "tipo": "ARRIENDO",
            "precio": 1200.00,
            "estado": "ACTIVO",
        },
        {
            "activo_key": "Building E — Residencial Tranquilo Posterior",
            "tipo": "VENTA",
            "precio": 165000.00,
            "estado": "ACTIVO",
        },
    ]
    for t in transacciones:
        tx = TransaccionTemporal(
            id=uuid.uuid4(),
            activo_id=asset_ids[t["activo_key"]],
            tipo_operacion=t["tipo"],
            precio=t["precio"],
            estado_anuncio=t["estado"],
        )
        session.add(tx)
        print(f"  [OK] Transaccion: {t['tipo']} ${t['precio']:,.0f} — {t['activo_key'][:35]}")

    # --- historial_eventos_urbanos ---
    for e in EVENTOS_URBANOS:
        evento = HistorialEventoUrbano(
            id=uuid.uuid4(),
            geom_evento=_point(e["lon"], e["lat"]),
            tipo_evento=e["tipo"],
            descripcion=e["descripcion"],
            restriccion_altura_pisos=e["restriccion_altura"],
            fecha_inicio=e["fecha_inicio"],
            fecha_fin=e["fecha_fin"],
            impacto_plusvalia_estimado=e["impacto_plusvalia"],
        )
        session.add(evento)
        print(f"  [OK] Evento urbano: {e['tipo'][:50]}")

    await session.commit()
    print("\n✅ Seed completado exitosamente.")
    print(f"   {len(ASSETS)} activos inmutables")
    print(f"   {len(FICHAS)} fichas técnicas")
    print(f"   {len(transacciones)} transacciones activas")
    print(f"   {len(EVENTOS_URBANOS)} eventos urbanos\n")

    # Quick spatial verification
    result = await session.execute(
        text("SELECT COUNT(*) FROM activos_inmutables")
    )
    count = result.scalar()
    print(f"[DB] Verificacion PostGIS: {count} activos en tabla activos_inmutables")


async def main() -> None:
    async with AsyncSessionLocal() as session:
        await seed(session)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
