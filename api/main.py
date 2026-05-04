from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from unisa_air_twin.api_schemas import (
    AnalyticsResponse,
    MapPayloadResponse,
    RefreshResponse,
    SensorDetailResponse,
    SummaryResponse,
    TimeseriesResponse,
    TimestampsResponse,
)
from unisa_air_twin.config import load_settings
from unisa_air_twin.live_sensors import export_operational_artifacts
from unisa_air_twin.ui_data import get_twin_service

app = FastAPI(
    title="UNISA Air Quality Digital Twin API",
    version="0.1.0",
    description="Operational API for real-only UNISA sensor snapshots, raw histories, and campus context layers.",
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


@app.get("/api/summary", response_model=SummaryResponse)
def summary() -> SummaryResponse:
    return get_twin_service().summary()


@app.post("/api/refresh", response_model=RefreshResponse)
def refresh() -> RefreshResponse:
    snapshots = export_operational_artifacts(load_settings())
    get_twin_service().refresh()
    return {"status": "refreshed", "snapshot_rows": int(len(snapshots))}


@app.get("/api/timestamps", response_model=TimestampsResponse)
def timestamps(pollutant: str = Query(...)) -> TimestampsResponse:
    return {"timestamps": get_twin_service().timestamps(pollutant)}


@app.get("/api/map", response_model=MapPayloadResponse)
def map_payload(
    pollutant: str = Query(...),
    timestamp: str = Query(...),
    resolution: Annotated[int, Query(ge=10, le=40)] = 24,
) -> MapPayloadResponse:
    return get_twin_service().map_payload(pollutant, timestamp, resolution)


@app.get("/api/timeseries", response_model=TimeseriesResponse)
def timeseries(pollutant: str = Query(...), sensor_name: str = Query(...)) -> TimeseriesResponse:
    return {"points": get_twin_service().timeseries(pollutant, sensor_name)}


@app.get("/api/sensor-detail", response_model=SensorDetailResponse)
def sensor_detail(sensor_id: str = Query(...), timestamp: str = Query(...)) -> SensorDetailResponse:
    return get_twin_service().sensor_detail(sensor_id, timestamp)


@app.get("/api/analytics", response_model=AnalyticsResponse)
def analytics(pollutant: str = Query(...), timestamp: str | None = Query(default=None)) -> AnalyticsResponse:
    return get_twin_service().analytics(pollutant, timestamp)
