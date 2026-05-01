"""Endpoints de admin protegidos por header `X-Admin-Token`."""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db
from app.services.vacancies_sync import VacanciesSync

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin_token(x_admin_token: str | None = Header(default=None)) -> None:
    settings = get_settings()
    expected = settings.ADMIN_TOKEN
    if (
        not x_admin_token
        or not expected
        or expected == "change-me"
        or not secrets.compare_digest(x_admin_token, expected)
    ):
        raise HTTPException(status_code=401, detail="unauthorized")


@router.post("/scrape", dependencies=[Depends(require_admin_token)])
async def trigger_scrape(session: AsyncSession = Depends(get_db)) -> dict:
    run = await VacanciesSync(session).run()
    return {
        "run_id": run.id,
        "status": run.status,
        "items_inserted": run.items_inserted,
        "items_updated": run.items_updated,
        "items_removed": run.items_removed,
        "data_version": run.data_version,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }
