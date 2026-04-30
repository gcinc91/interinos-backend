from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    items_inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_removed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    data_version: Mapped[str] = mapped_column(String, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
