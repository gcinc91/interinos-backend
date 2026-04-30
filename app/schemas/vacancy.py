from datetime import datetime

from pydantic import BaseModel


class VacanciesVersionResponse(BaseModel):
    data_version: str | None
    last_run_at: datetime | None
    items_active: int
