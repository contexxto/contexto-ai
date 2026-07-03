import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class ActivoInmutable(Base):
    __tablename__ = "activos_inmutables"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    geom: Mapped[object] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    direccion_estandarizada: Mapped[str] = mapped_column(String(255), nullable=False)
    piso_altura: Mapped[int] = mapped_column(Integer, default=1)
    walk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Procedencia del walk_score (Migration 017): 'osm' (comercios reales) | 'heuristico'
    # (estimación por zona) | None (legado). Deja que el anuncio rotule cada dato con su
    # verdad en vez de afirmar OSM para todos.
    walk_score_fuente: Mapped[str | None] = mapped_column(String(20), nullable=True)
    score_ruido_predictivo: Mapped[str | None] = mapped_column(String(10), nullable=True)
    volumen_trafico_historico: Mapped[int] = mapped_column(Integer, default=0)
    densidad_poblacional_pico: Mapped[int] = mapped_column(Integer, default=0)
    porcentaje_cobertura_vegetal: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    tipo_activo: Mapped[str] = mapped_column(String(20), default="Departamento", nullable=False)
    # Caché por hash de imagen (Migration 005): dedup → cero llamadas a IA en re-subidas.
    image_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    imagen_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    transacciones: Mapped[list["TransaccionTemporal"]] = relationship(back_populates="activo")
    ficha_tecnica: Mapped["FichaTecnicaMantenimiento | None"] = relationship(back_populates="activo", uselist=False)

    __table_args__ = (
        CheckConstraint("walk_score BETWEEN 0 AND 100", name="ck_walk_score_range"),
        CheckConstraint("score_ruido_predictivo IN ('BAJO', 'MEDIO', 'ALTO')", name="ck_score_ruido"),
        CheckConstraint(
            "tipo_activo IN ('Departamento', 'Casa', 'Local Comercial', 'Oficina', 'Quinta')",
            name="ck_tipo_activo",
        ),
    )


class TransaccionTemporal(Base):
    __tablename__ = "transacciones_temporales"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    activo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activos_inmutables.id", ondelete="CASCADE"))
    tipo_operacion: Mapped[str | None] = mapped_column(String(20), nullable=True)
    precio: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    estado_anuncio: Mapped[str | None] = mapped_column(String(15), nullable=True)
    fecha_publicacion: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    activo: Mapped["ActivoInmutable"] = relationship(back_populates="transacciones")


class HistorialEventoUrbano(Base):
    __tablename__ = "historial_eventos_urbanos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    geom_evento: Mapped[object] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    tipo_evento: Mapped[str | None] = mapped_column(String(50), nullable=True)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    restriccion_altura_pisos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fecha_inicio: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fecha_fin: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    impacto_plusvalia_estimado: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)


class FichaTecnicaMantenimiento(Base):
    __tablename__ = "ficha_tecnica_mantenimiento"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    activo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activos_inmutables.id", ondelete="CASCADE"))
    tipo_tuberia: Mapped[str | None] = mapped_column(String(50), nullable=True)
    año_construccion: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tipo_estructura: Mapped[str | None] = mapped_column(String(50), nullable=True)
    calidad_acabados: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ultimo_mantenimiento_cisterna: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ultima_impermeabilizacion_techo: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ultima_pintura_fachada: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ultimo_cambio_cableado_electrico: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    monto_invertido_mejoras: Mapped[float] = mapped_column(Numeric(12, 2), default=0.00)
    descripcion_mejoras: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Gobernanza de extracción visual (Migration 004 / Fase B):
    fuente: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    confianza_extraccion: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)
    estado_revision: Mapped[str] = mapped_column(String(25), default="publicado", nullable=False)
    # Extracción visual COMPLETA (Migration 005): permite revisión/corrección y ground-truth.
    ficha_vision_raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    activo: Mapped["ActivoInmutable"] = relationship(back_populates="ficha_tecnica")

    __table_args__ = (
        CheckConstraint("fuente IN ('manual', 'vision_ia')", name="ck_ficha_fuente"),
        CheckConstraint(
            "estado_revision IN ('publicado', 'pendiente_revision', 'rechazado')",
            name="ck_ficha_estado_revision",
        ),
    )


class PoiPropio(Base):
    """Capa propia de POIs (el foso): Overture Places (6 categorías) + OSM transporte.

    La llena scripts/foso_pois_spike.py (Overture vía DuckDB/S3 anónimo + transporte vía
    Overpass, sin API keys) y la consume app/rutas.py (_servicios_propios) como FUENTE
    PRIMARIA del entorno, con Google solo de fallback por hueco. Es "catastro descargado",
    no dato del usuario: no hay FK a activos_inmutables; la relación inmueble↔POI es
    geoespacial en vivo (ST_DWithin). Ver docs/SPEC_Foso_Capa_de_Datos.md (Ladrillo #18).
    """
    __tablename__ = "pois_propios"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nombre: Mapped[str | None] = mapped_column(Text, nullable=True)
    categoria: Mapped[str] = mapped_column(Text, nullable=False)
    categoria_overture: Mapped[str | None] = mapped_column(Text, nullable=True)
    geom: Mapped[object] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    fuente: Mapped[str] = mapped_column(Text, nullable=False, default="overture")
    confianza: Mapped[float | None] = mapped_column(Float(precision=24), nullable=True)  # real (float4)
    overture_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    osm_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    marca: Mapped[str | None] = mapped_column(Text, nullable=True)
    direccion: Mapped[str | None] = mapped_column(Text, nullable=True)
    operativo: Mapped[bool] = mapped_column(Boolean, default=True)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "categoria IN ('salud','farmacia','supermercado','educacion',"
            "'parque','centro_comercial','transporte')",
            name="ck_pois_categoria",
        ),
        CheckConstraint("fuente IN ('overture','osm')", name="ck_pois_fuente"),
    )


class IsocronaInmueble(Base):
    """Isócronas peatonales pre-computadas por inmueble (Ladrillo #7 del foso).

    Motor: Valhalla auto-hospedado (/isochrone, costing=pedestrian). El inventario es
    FIJO → se pre-computa UNA isócrona por (inmueble, minutos) y se cachea en PostGIS.
    Habilita el overlay del Mapa Vivo 2C y la CUÑA de búsqueda por ancla+tiempo
    (ST_Contains). Ver docs/SPEC_Foso_Capa_de_Datos.md (Ladrillo #7).
    """
    __tablename__ = "isocronas_inmueble"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    activo_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("activos_inmutables.id", ondelete="CASCADE"), nullable=False
    )
    minutos: Mapped[int] = mapped_column(Integer, nullable=False)  # 15 | 30
    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=False
    )
    generado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("minutos > 0 AND minutos <= 60", name="ck_isocrona_minutos"),
        UniqueConstraint("activo_id", "minutos", name="uq_isocrona_activo_minutos"),
    )


class CorreccionFicha(Base):
    """Bitácora de correcciones humanas sobre la extracción de la IA (ground-truth)."""
    __tablename__ = "correcciones_ficha"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    activo_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("activos_inmutables.id", ondelete="CASCADE"))
    campo: Mapped[str] = mapped_column(Text, nullable=False)
    valor_ia: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor_humano: Mapped[str | None] = mapped_column(Text, nullable=True)
    revisor: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
