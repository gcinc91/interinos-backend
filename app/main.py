from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, distance, geocode, health, vacancies
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.scheduler.jobs import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    log = get_logger("startup")
    if settings.ENABLE_SCHEDULER:
        start_scheduler()
    log.info("app_started", scheduler_enabled=settings.ENABLE_SCHEDULER)
    try:
        yield
    finally:
        if settings.ENABLE_SCHEDULER:
            stop_scheduler()
        log.info("app_stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="interinos-backend", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(geocode.router)
    app.include_router(vacancies.router)
    app.include_router(distance.router)
    app.include_router(admin.router)
    return app


app = create_app()
