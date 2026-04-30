from pydantic import BaseModel, Field


class GeocodeRequest(BaseModel):
    address: str = Field(min_length=2, max_length=200)


class GeocodeResponse(BaseModel):
    lat: float
    lon: float
    address_norm: str
    cached: bool
