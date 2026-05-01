"""APScheduler in-process para ejecutar el sync de SIPRI cada N horas.

Render free tier puede dormir tras 15 min idle. En ese caso, alternativa: usar
un Render Cron Job externo que ejecute `python -m app.scheduler.run_once`.
Toggle vía `ENABLE_SCHEDULER`.
"""
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.services.vacancies_sync import VacanciesSync

log = get_logger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def run_sync_job() -> None:
    """Job ejecutado por APScheduler. Crea su propia AsyncSession."""
    log.info("scheduled_sync_start")
    try:
        async with SessionLocal() as session:
            run = await VacanciesSync(session).run()
        log.info(
            "scheduled_sync_ok",
            run_id=run.id,
            inserted=run.items_inserted,
            updated=run.items_updated,
            removed=run.items_removed,
            data_version=run.data_version,
        )
    except Exception:
        log.exception("scheduled_sync_failed")


def start_scheduler() -> AsyncIOScheduler:
    """Arranca el scheduler global. Idempotente."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler

    settings = get_settings()
    _scheduler = AsyncIOScheduler(timezone=settings.SCHEDULER_TIMEZONE)
    _scheduler.add_job(
        run_sync_job,
        trigger=CronTrigger.from_crontab(settings.SCRAPE_CRON, timezone=settings.SCHEDULER_TIMEZONE),
        id="sipri_sync",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )
    _scheduler.start()
    log.info(
        "scheduler_started",
        cron=settings.SCRAPE_CRON,
        timezone=settings.SCHEDULER_TIMEZONE,
    )
    return _scheduler


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is None or not _scheduler.running:
        _scheduler = None
        return
    _scheduler.shutdown(wait=False)
    _scheduler = None
    log.info("scheduler_stopped")
