from datetime import datetime
from typing import Any

from pydantic import BaseModel


class VacanciesVersionResponse(BaseModel):
    data_version: str | None
    last_run_at: datetime | None
    items_active: int


class VacancySummary(BaseModel):
    id: int
    source_id: str
    cuerpo: str
    especialidad: str | None
    centro: str
    localidad: str | None
    provincia: str | None
    tipo: str | None
    participacion: str | None
    fecha_cese: datetime | None
    lat: float
    lon: float
    straight_distance_km: float | None = None


class VacancyDetail(VacancySummary):
    centro_codigo: str | None
    puesto_codigo: str | None
    observaciones: str | None
    raw_payload: dict[str, Any]
    is_active: bool
    updated_at: datetime


class FiltersResponse(BaseModel):
    cuerpos: list[str]
    especialidades: list[str]
    provincias: list[str]
    tipos: list[str]
    participaciones: list[str]
