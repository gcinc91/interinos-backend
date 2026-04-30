"""Sincronización de vacantes desde SIPRI a la BD propia.

Estrategia:
1. Hacer fetch + parse → lista de `VacancyDTO`.
2. Leer estado actual `(source_id → content_hash, is_active)` de la BD.
3. Computar diff: nuevos / actualizados / sin cambios / desaparecidos.
4. Aplicar:
   - INSERT de los nuevos (`is_active=True`).
   - UPDATE de los actualizados (recalcular `geom`, refrescar campos, `is_active=True`).
   - UPDATE `is_active=False` de los `source_id` que ya no están en la fuente.
5. Insertar fila en `scrape_runs` con contadores y `data_version` (hash global).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import ScrapeRun, Vacancy
from app.scrapers.dto import VacancyDTO
from app.scrapers.sipri_client import SipriClient
from app.scrapers.sipri_parser import parse_feature_collection

log = get_logger(__name__)


@dataclass
class SyncDiff:
    new: list[VacancyDTO] = field(default_factory=list)
    updated: list[VacancyDTO] = field(default_factory=list)
    unchanged: list[VacancyDTO] = field(default_factory=list)
    removed_source_ids: list[str] = field(default_factory=list)


def compute_data_version(dtos: list[VacancyDTO]) -> str:
    """Hash global del set de vacantes activas. Cambia si entra/sale algo
    o si cualquier `content_hash` cambia."""
    pairs = sorted((dto.source_id, dto.content_hash) for dto in dtos)
    canonical = "|".join(f"{sid}:{ch}" for sid, ch in pairs)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def compute_diff(
    existing: dict[str, tuple[str, bool]],
    incoming: list[VacancyDTO],
) -> SyncDiff:
    """Computa qué hay que insertar / actualizar / desactivar.

    `existing` mapea `source_id` → `(content_hash, is_active)` desde la BD.
    """
    diff = SyncDiff()
    incoming_ids = {dto.source_id for dto in incoming}
    for dto in incoming:
        prev = existing.get(dto.source_id)
        if prev is None:
            diff.new.append(dto)
            continue
        stored_hash, was_active = prev
        if stored_hash == dto.content_hash and was_active:
            diff.unchanged.append(dto)
        else:
            diff.updated.append(dto)
    diff.removed_source_ids = sorted(
        sid for sid, (_, active) in existing.items() if active and sid not in incoming_ids
    )
    return diff


def _dto_to_orm_kwargs(dto: VacancyDTO) -> dict:
    return {
        "source_id": dto.source_id,
        "cuerpo": dto.cuerpo,
        "especialidad": dto.especialidad,
        "centro": dto.centro,
        "centro_codigo": dto.centro_codigo,
        "puesto_codigo": dto.puesto_codigo,
        "localidad": dto.localidad,
        "provincia": dto.provincia,
        "tipo": dto.tipo,
        "participacion": dto.participacion,
        "observaciones": dto.observaciones,
        "fecha_cese": dto.fecha_cese,
        "geom": WKTElement(f"POINT({dto.lon} {dto.lat})", srid=4326),
        "raw_payload": dto.raw_payload,
        "content_hash": dto.content_hash,
        "is_active": True,
    }


class VacanciesSync:
    def __init__(
        self,
        session: AsyncSession,
        scraper: SipriClient | None = None,
    ) -> None:
        self.session = session
        self.scraper = scraper or SipriClient()

    async def _load_existing(self) -> dict[str, tuple[str, bool]]:
        result = await self.session.execute(
            select(Vacancy.source_id, Vacancy.content_hash, Vacancy.is_active)
        )
        return {row.source_id: (row.content_hash, row.is_active) for row in result}

    async def _apply_diff(self, diff: SyncDiff) -> None:
        # Insert nuevos en bloque (ORM, hace falta para que se pueble created_at).
        for dto in diff.new:
            self.session.add(Vacancy(**_dto_to_orm_kwargs(dto)))

        # Update modificados (uno a uno: SQLAlchemy + Geography no soporta updatemany simple).
        for dto in diff.updated:
            kwargs = _dto_to_orm_kwargs(dto)
            kwargs.pop("source_id")  # no se actualiza
            kwargs["updated_at"] = func.now()
            await self.session.execute(
                update(Vacancy).where(Vacancy.source_id == dto.source_id).values(**kwargs)
            )

        # Marcar como inactivos los desaparecidos (en lote).
        if diff.removed_source_ids:
            await self.session.execute(
                update(Vacancy)
                .where(Vacancy.source_id.in_(diff.removed_source_ids))
                .values(is_active=False, updated_at=func.now())
            )

    async def run(self) -> ScrapeRun:
        started_at = datetime.now(tz=timezone.utc)
        log.info("vacancies_sync_started")

        try:
            payload = await self.scraper.fetch_geojson()
            dtos = parse_feature_collection(payload)
        except Exception as exc:
            log.exception("vacancies_sync_fetch_failed")
            run = ScrapeRun(
                started_at=started_at,
                finished_at=datetime.now(tz=timezone.utc),
                status="failed",
                data_version="",
                error_message=str(exc)[:500],
            )
            self.session.add(run)
            await self.session.commit()
            raise

        existing = await self._load_existing()
        diff = compute_diff(existing, dtos)
        log.info(
            "vacancies_sync_diff",
            new=len(diff.new),
            updated=len(diff.updated),
            unchanged=len(diff.unchanged),
            removed=len(diff.removed_source_ids),
        )

        await self._apply_diff(diff)

        data_version = compute_data_version(dtos)
        run = ScrapeRun(
            started_at=started_at,
            finished_at=datetime.now(tz=timezone.utc),
            status="success",
            items_inserted=len(diff.new),
            items_updated=len(diff.updated),
            items_removed=len(diff.removed_source_ids),
            data_version=data_version,
        )
        self.session.add(run)
        await self.session.commit()
        log.info(
            "vacancies_sync_finished",
            data_version=data_version,
            inserted=len(diff.new),
            updated=len(diff.updated),
            removed=len(diff.removed_source_ids),
        )
        return run
