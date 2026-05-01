from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2.functions import (
    ST_DWithin,
    ST_Distance,
    ST_GeographyFromText,
    ST_Intersects,
    ST_X,
    ST_Y,
)
from geoalchemy2.types import Geometry
from sqlalchemy import cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import ScrapeRun, Vacancy
from app.schemas.vacancy import (
    FiltersResponse,
    VacanciesVersionResponse,
    VacancyDetail,
    VacancySummary,
)

router = APIRouter(tags=["vacancies"])


# ---- /vacancies/version (registrado primero para no chocar con /vacancies/{id})


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


# ---- /filters


@router.get("/filters", response_model=FiltersResponse)
async def get_filters(session: AsyncSession = Depends(get_db)) -> FiltersResponse:
    async def distinct(column) -> list[str]:
        result = await session.execute(
            select(column)
            .where(Vacancy.is_active.is_(True), column.isnot(None))
            .distinct()
            .order_by(column)
        )
        return [v for v in result.scalars().all() if v is not None]

    return FiltersResponse(
        cuerpos=await distinct(Vacancy.cuerpo),
        especialidades=await distinct(Vacancy.especialidad),
        provincias=await distinct(Vacancy.provincia),
        tipos=await distinct(Vacancy.tipo),
        participaciones=await distinct(Vacancy.participacion),
    )


# ---- /vacancies (list)


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    parts = bbox.split(",")
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox debe ser 'minLon,minLat,maxLon,maxLat'")
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="bbox inválido") from exc
    if min_lon >= max_lon or min_lat >= max_lat:
        raise HTTPException(status_code=400, detail="bbox: min debe ser menor que max")
    return min_lon, min_lat, max_lon, max_lat


@router.get("/vacancies", response_model=list[VacancySummary])
async def list_vacancies(
    session: AsyncSession = Depends(get_db),
    lat: float | None = Query(None, ge=-90, le=90),
    lon: float | None = Query(None, ge=-180, le=180),
    radius_km: float | None = Query(None, gt=0, le=500),
    cuerpo: Annotated[list[str] | None, Query()] = None,
    especialidad: Annotated[list[str] | None, Query()] = None,
    provincia: Annotated[list[str] | None, Query()] = None,
    tipo: Annotated[list[str] | None, Query()] = None,
    participacion: Annotated[list[str] | None, Query()] = None,
    bbox: str | None = None,
    limit: int = Query(500, ge=1, le=2000),
) -> list[VacancySummary]:
    geom_as_geom = cast(Vacancy.geom, Geometry)
    lon_expr = ST_X(geom_as_geom).label("lon")
    lat_expr = ST_Y(geom_as_geom).label("lat")

    distance_m_expr = None
    if lat is not None and lon is not None:
        origin = ST_GeographyFromText(literal(f"SRID=4326;POINT({lon} {lat})"))
        distance_m_expr = ST_Distance(Vacancy.geom, origin).label("distance_m")

    columns = [
        Vacancy.id,
        Vacancy.source_id,
        Vacancy.cuerpo,
        Vacancy.especialidad,
        Vacancy.centro,
        Vacancy.localidad,
        Vacancy.provincia,
        Vacancy.tipo,
        Vacancy.participacion,
        Vacancy.fecha_cese,
        lon_expr,
        lat_expr,
    ]
    if distance_m_expr is not None:
        columns.append(distance_m_expr)

    stmt = select(*columns).where(Vacancy.is_active.is_(True))

    if cuerpo:
        stmt = stmt.where(Vacancy.cuerpo.in_(cuerpo))
    if especialidad:
        stmt = stmt.where(Vacancy.especialidad.in_(especialidad))
    if provincia:
        stmt = stmt.where(Vacancy.provincia.in_(provincia))
    if tipo:
        stmt = stmt.where(Vacancy.tipo.in_(tipo))
    if participacion:
        stmt = stmt.where(Vacancy.participacion.in_(participacion))

    parsed_bbox = _parse_bbox(bbox)
    if parsed_bbox is not None:
        min_lon, min_lat, max_lon, max_lat = parsed_bbox
        envelope = func.ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
        stmt = stmt.where(ST_Intersects(geom_as_geom, envelope))

    if lat is not None and lon is not None and radius_km is not None:
        origin = ST_GeographyFromText(literal(f"SRID=4326;POINT({lon} {lat})"))
        stmt = stmt.where(ST_DWithin(Vacancy.geom, origin, radius_km * 1000))

    if distance_m_expr is not None:
        stmt = stmt.order_by(distance_m_expr)
    else:
        stmt = stmt.order_by(Vacancy.cuerpo, Vacancy.especialidad)

    stmt = stmt.limit(limit)

    rows = (await session.execute(stmt)).mappings().all()
    return [
        VacancySummary(
            id=row["id"],
            source_id=row["source_id"],
            cuerpo=row["cuerpo"],
            especialidad=row["especialidad"],
            centro=row["centro"],
            localidad=row["localidad"],
            provincia=row["provincia"],
            tipo=row["tipo"],
            participacion=row["participacion"],
            fecha_cese=row["fecha_cese"],
            lat=row["lat"],
            lon=row["lon"],
            straight_distance_km=(
                row["distance_m"] / 1000 if row.get("distance_m") is not None else None
            ),
        )
        for row in rows
    ]


# ---- /vacancies/{vacancy_id}


@router.get("/vacancies/{vacancy_id}", response_model=VacancyDetail)
async def get_vacancy(
    vacancy_id: int,
    session: AsyncSession = Depends(get_db),
) -> VacancyDetail:
    geom_as_geom = cast(Vacancy.geom, Geometry)
    stmt = select(
        Vacancy.id,
        Vacancy.source_id,
        Vacancy.cuerpo,
        Vacancy.especialidad,
        Vacancy.centro,
        Vacancy.centro_codigo,
        Vacancy.puesto_codigo,
        Vacancy.localidad,
        Vacancy.provincia,
        Vacancy.tipo,
        Vacancy.participacion,
        Vacancy.observaciones,
        Vacancy.fecha_cese,
        Vacancy.raw_payload,
        Vacancy.is_active,
        Vacancy.updated_at,
        ST_X(geom_as_geom).label("lon"),
        ST_Y(geom_as_geom).label("lat"),
    ).where(Vacancy.id == vacancy_id)

    row = (await session.execute(stmt)).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="vacancy_not_found")

    return VacancyDetail(
        id=row["id"],
        source_id=row["source_id"],
        cuerpo=row["cuerpo"],
        especialidad=row["especialidad"],
        centro=row["centro"],
        centro_codigo=row["centro_codigo"],
        puesto_codigo=row["puesto_codigo"],
        localidad=row["localidad"],
        provincia=row["provincia"],
        tipo=row["tipo"],
        participacion=row["participacion"],
        observaciones=row["observaciones"],
        fecha_cese=row["fecha_cese"],
        raw_payload=row["raw_payload"],
        is_active=row["is_active"],
        updated_at=row["updated_at"],
        lat=row["lat"],
        lon=row["lon"],
    )
