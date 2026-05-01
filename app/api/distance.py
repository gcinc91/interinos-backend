from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.distance import DistanceRequest, DistanceResponse
from app.services.routing_service import RoutingService

router = APIRouter(tags=["distance"])


@router.post("/distance", response_model=DistanceResponse)
async def distance(
    payload: DistanceRequest,
    session: AsyncSession = Depends(get_db),
) -> DistanceResponse:
    service = RoutingService(session=session)
    results = await service.compute_distances(
        origin_lat=payload.origin.lat,
        origin_lon=payload.origin.lon,
        destinations=payload.destinations,
    )
    return DistanceResponse(results=results)
