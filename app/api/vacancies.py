from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import ScrapeRun, Vacancy
from app.schemas.vacancy import VacanciesVersionResponse

router = APIRouter(tags=["vacancies"])


@router.get("/vacancies/version", response_model=VacanciesVersionResponse)
async def vacancies_version(
    session: AsyncSession = Depends(get_db),
) -> VacanciesVersionResponse:
    last_run_q = await session.execute(
        select(ScrapeRun)
        .where(ScrapeRun.status == "success")
        .order_by(ScrapeRun.started_at.desc())
        .limit(1)
    )
    last = last_run_q.scalar_one_or_none()

    count_q = await session.execute(
        select(func.count()).select_from(Vacancy).where(Vacancy.is_active.is_(True))
    )
    items_active = int(count_q.scalar() or 0)

    return VacanciesVersionResponse(
        data_version=last.data_version if last else None,
        last_run_at=(last.finished_at or last.started_at) if last else None,
        items_active=items_active,
    )
