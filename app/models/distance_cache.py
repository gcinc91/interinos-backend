from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DistanceCache(Base):
    __tablename__ = "distance_cache"

    origin_lat: Mapped[float] = mapped_column(Float, primary_key=True)
    origin_lon: Mapped[float] = mapped_column(Float, primary_key=True)
    dest_lat: Mapped[float] = mapped_column(Float, primary_key=True)
    dest_lon: Mapped[float] = mapped_column(Float, primary_key=True)
    road_distance_m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    road_duration_s: Mapped[int | None] = mapped_column(Integer, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
