from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

import api.dependencies as deps
from api.streaming import summary_stream
from unisa_air_twin.api_schemas import (
    AnalyticsResponse,
    MapPayloadResponse,
    SensorDetailResponse,
    SummaryResponse,
    TimeseriesResponse,
    TimestampsResponse,
)
from unisa_air_twin.external_sources import read_source_statuses
from unisa_air_twin.operational_store import read_observations, read_raw_messages, read_sensors

router = APIRouter()


async def _summary_stream(request: Request) -> AsyncIterator[str]:
    async for event in summary_stream(request, deps.get_snapshot_events(), deps.get_twin_service):
        yield event


@router.get("/api/summary", response_model=SummaryResponse)
def summary() -> SummaryResponse:
    return deps.get_twin_service().summary()


@router.get("/api/sources")
def sources() -> dict[str, Any]:
    return {"sources": read_source_statuses(deps.get_settings())}


@router.get("/api/export/{dataset}")
def export_dataset(
    dataset: str,
    format: str = Query(default="csv", pattern="^(csv|json)$"),
) -> Response:
    settings = deps.get_settings()
    if dataset == "observations":
        frame = read_observations(settings)
    elif dataset == "raw-messages":
        frame = read_raw_messages(settings)
    elif dataset == "sensors":
        frame = read_sensors(settings)
    else:
        raise HTTPException(status_code=404, detail="Unknown export dataset")

    if format == "json":
        content = frame.where(frame.notna(), None).to_json(orient="records", date_format="iso")
        return Response(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{dataset}.json"'},
        )

    content = frame.to_csv(index=False)
    return Response(
        content=content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{dataset}.csv"'},
    )


@router.get("/api/stream")
async def stream(request: Request) -> StreamingResponse:
    return StreamingResponse(
        _summary_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/timestamps", response_model=TimestampsResponse)
def timestamps(pollutant: str = Query(...)) -> TimestampsResponse:
    return {"timestamps": deps.get_twin_service().timestamps(pollutant)}


@router.get("/api/map", response_model=MapPayloadResponse)
def map_payload(
    pollutant: str = Query(...),
    timestamp: str = Query(...),
    resolution: Annotated[int, Query(ge=10, le=40)] = 24,
) -> MapPayloadResponse:
    return deps.get_twin_service().map_payload(pollutant, timestamp, resolution)


@router.get("/api/timeseries", response_model=TimeseriesResponse)
def timeseries(pollutant: str = Query(...), sensor_name: str = Query(...)) -> TimeseriesResponse:
    return {"points": deps.get_twin_service().timeseries(pollutant, sensor_name)}


@router.get("/api/sensor-detail", response_model=SensorDetailResponse)
def sensor_detail(sensor_id: str = Query(...), timestamp: str = Query(...)) -> SensorDetailResponse:
    return deps.get_twin_service().sensor_detail(sensor_id, timestamp)


@router.get("/api/analytics", response_model=AnalyticsResponse)
def analytics(pollutant: str = Query(...), timestamp: str | None = Query(default=None)) -> AnalyticsResponse:
    return deps.get_twin_service().analytics(pollutant, timestamp)
