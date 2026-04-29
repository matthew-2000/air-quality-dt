from __future__ import annotations

from typing import Annotated

from fastapi import Body, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from unisa_air_twin.ui_data import get_twin_service


class ScenarioRequest(BaseModel):
    pollutant: str
    timestamp: str
    traffic_reduction: float = Field(default=0.2, ge=0.0, le=0.5)
    wind_multiplier: float = Field(default=1.0, ge=0.5, le=2.0)
    rain_event: bool = False
    focus_zone: str = "all"
    green_improvement: float = Field(default=0.0, ge=0.0, le=0.5)
    window_label: str = "Solo ora selezionata"
    resolution: int = Field(default=24, ge=10, le=40)


app = FastAPI(
    title="UNISA Air Quality Digital Twin API",
    version="0.1.0",
    description="Operational API for campus air quality snapshots, GIS layers, and what-if scenarios.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/summary")
def summary() -> dict:
    return get_twin_service().summary()


@app.post("/api/refresh")
def refresh() -> dict:
    return get_twin_service().refresh() and {"status": "refreshed"}


@app.get("/api/timestamps")
def timestamps(pollutant: str = Query(...)) -> dict[str, list[str]]:
    return {"timestamps": get_twin_service().timestamps(pollutant)}


@app.get("/api/map")
def map_payload(
    pollutant: str = Query(...),
    timestamp: str = Query(...),
    resolution: Annotated[int, Query(ge=10, le=40)] = 24,
) -> dict:
    return get_twin_service().map_payload(pollutant, timestamp, resolution)


@app.post("/api/scenario")
def scenario(payload: Annotated[ScenarioRequest, Body()]) -> dict:
    return get_twin_service().scenario_payload(**payload.model_dump())


@app.get("/api/timeseries")
def timeseries(pollutant: str = Query(...), sensor_name: str = Query(...)) -> dict:
    return {"points": get_twin_service().timeseries(pollutant, sensor_name)}
