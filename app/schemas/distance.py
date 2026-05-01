from typing import Literal

from pydantic import BaseModel, Field


class Coord(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class DistanceDestination(Coord):
    id: int | str


class DistanceRequest(BaseModel):
    origin: Coord
    destinations: list[DistanceDestination] = Field(min_length=1, max_length=200)


class DistanceResult(BaseModel):
    id: int | str
    road_distance_m: int | None
    road_duration_s: int | None
    source: Literal["osrm", "cache", "haversine"]
    straight_distance_km: float


class DistanceResponse(BaseModel):
    results: list[DistanceResult]
