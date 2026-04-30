from datetime import datetime

from geoalchemy2 import Geography
from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Vacancy(Base):
    __tablename__ = "vacancies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    source_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)

    cuerpo: Mapped[str] = mapped_column(String, nullable=False)
    especialidad: Mapped[str | None] = mapped_column(String, nullable=True)
    centro: Mapped[str] = mapped_column(String, nullable=False)
    centro_codigo: Mapped[str | None] = mapped_column(String, nullable=True)
    puesto_codigo: Mapped[str | None] = mapped_column(String, nullable=True)
    localidad: Mapped[str | None] = mapped_column(String, nullable=True)
    provincia: Mapped[str | None] = mapped_column(String, nullable=True)
    tipo: Mapped[str | None] = mapped_column(String, nullable=True)
    participacion: Mapped[str | None] = mapped_column(String, nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_cese: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    geom = mapped_column(Geography(geometry_type="POINT", srid=4326), nullable=False)

    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("vacancies_geom_gix", "geom", postgresql_using="gist"),
        Index("vacancies_active_idx", "is_active"),
        Index("vacancies_cuerpo_idx", "cuerpo", "especialidad"),
    )
