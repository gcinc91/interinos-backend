from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class VacancyDTO:
    source_id: str
    cuerpo: str
    especialidad: str | None
    centro: str
    centro_codigo: str | None
    puesto_codigo: str | None
    localidad: str | None
    provincia: str | None
    tipo: str | None
    participacion: str | None
    observaciones: str | None
    fecha_cese: datetime | None
    lat: float
    lon: float
    raw_payload: dict
    content_hash: str
