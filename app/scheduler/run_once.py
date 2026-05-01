"""CLI: ejecuta UN sync de SIPRI y termina.

Uso: `python -m app.scheduler.run_once`. Pensado para Render Cron Job
(alternativa al scheduler in-process si el web service entra en sleep).
"""
from __future__ import annotations

import asyncio
import sys

from app.core.logging import configure_logging, get_logger
from app.db.session import SessionLocal
from app.services.vacancies_sync import VacanciesSync


async def _main() -> int:
    configure_logging()
    log = get_logger("run_once")
    try:
        async with SessionLocal() as session:
            run = await VacanciesSync(session).run()
        log.info(
            "run_once_ok",
            run_id=run.id,
            inserted=run.items_inserted,
            updated=run.items_updated,
            removed=run.items_removed,
            data_version=run.data_version,
        )
        return 0
    except Exception:
        log.exception("run_once_failed")
        return 1


def main() -> None:
    sys.exit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
