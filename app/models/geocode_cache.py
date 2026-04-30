from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GeocodeCache(Base):
    __tablename__ = "geocode_cache"

    address_norm: Mapped[str] = mapped_column(String, primary_key=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False, default="nominatim")
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
