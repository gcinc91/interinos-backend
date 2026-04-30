from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.geocode import GeocodeRequest, GeocodeResponse
from app.services.geocode_service import GeocodeService

router = APIRouter(tags=["geocode"])


@router.post("/geocode", response_model=GeocodeResponse)
async def geocode_address(
    payload: GeocodeRequest,
    session: AsyncSession = Depends(get_db),
) -> GeocodeResponse:
    service = GeocodeService(session=session)
    result = await service.geocode(payload.address)
    if result is None:
        raise HTTPException(status_code=404, detail="address_not_found")
    lat, lon, address_norm, cached = result
    return GeocodeResponse(lat=lat, lon=lon, address_norm=address_norm, cached=cached)
