from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated, Any

import anyio
from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

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

STREAM_HEARTBEAT_SECONDS = 30.0
STREAM_RETRY_MILLISECONDS = 5000


class SnapshotEventBus:
    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    async def notify(self) -> int:
        async with self._condition:
            self._version += 1
            self._condition.notify_all()
            return self._version

    async def wait_for_change(self, version: int, timeout: float) -> int:
        async with self._condition:
            if self._version != version:
                return self._version
            try:
                await asyncio.wait_for(self._condition.wait_for(lambda: self._version != version), timeout=timeout)
            except TimeoutError:
                return version
            return self._version


snapshot_events = SnapshotEventBus()

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


def _summary_stream_fingerprint(summary: dict[str, Any]) -> str:
    coverage_rows = [
        {
            "pollutant": row.get("pollutant"),
            "active_sensors": row.get("active_sensors"),
            "capable_sensors": row.get("capable_sensors"),
            "coverage_ratio": row.get("coverage_ratio"),
        }
        for row in summary.get("coverage_by_pollutant", [])
        if isinstance(row, dict)
    ]
    fingerprint_payload = {
        "latest_timestamp": summary.get("latest_timestamp"),
        "latest_received_at": summary.get("latest_received_at"),
        "rows": summary.get("rows"),
        "snapshot_rows": summary.get("snapshot_rows"),
        "observation_rows": summary.get("observation_rows"),
        "raw_message_rows": summary.get("raw_message_rows"),
        "active_sensors": summary.get("active_sensors"),
        "capable_sensors": summary.get("capable_sensors"),
        "coverage_by_pollutant": coverage_rows,
        "generated_at": summary.get("ingestion", {}).get("generated_at") if isinstance(summary.get("ingestion"), dict) else None,
        "live_feed_status": summary.get("live_feed", {}).get("status") if isinstance(summary.get("live_feed"), dict) else None,
    }
    return json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":"))


def _summary_stream_payload(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "fingerprint": _summary_stream_fingerprint(summary),
        "latest_timestamp": summary.get("latest_timestamp"),
        "latest_received_at": summary.get("latest_received_at"),
        "snapshot_rows": int(summary.get("snapshot_rows", 0) or 0),
        "observation_rows": int(summary.get("observation_rows", 0) or 0),
        "raw_message_rows": int(summary.get("raw_message_rows", 0) or 0),
        "active_sensors": int(summary.get("active_sensors", 0) or 0),
        "live_feed_status": summary.get("live_feed", {}).get("status") if isinstance(summary.get("live_feed"), dict) else None,
        "generated_at": summary.get("ingestion", {}).get("generated_at") if isinstance(summary.get("ingestion"), dict) else None,
    }


def _sse_event(name: str, payload: dict[str, Any], retry: int | None = None) -> str:
    lines: list[str] = []
    if retry is not None:
        lines.append(f"retry: {retry}")
    lines.append(f"event: {name}")
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    for line in body.splitlines() or [body]:
        lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"


async def _summary_stream(request: Request) -> AsyncIterator[str]:
    last_fingerprint: str | None = None
    observed_version = snapshot_events.version
    service = get_twin_service()
    while True:
        if await request.is_disconnected():
            break
        try:
            payload = _summary_stream_payload(service.summary())
            if payload["fingerprint"] != last_fingerprint:
                event_name = "connected" if last_fingerprint is None else "snapshot_update"
                retry = STREAM_RETRY_MILLISECONDS if last_fingerprint is None else None
                yield _sse_event(event_name, payload, retry=retry)
                last_fingerprint = str(payload["fingerprint"])
        except Exception as exc:
            yield _sse_event("stream_error", {"message": str(exc)})
        current_version = snapshot_events.version
        observed_version = current_version
        next_version = await snapshot_events.wait_for_change(observed_version, STREAM_HEARTBEAT_SECONDS)
        if next_version == observed_version:
            yield ": heartbeat\n\n"
        observed_version = next_version


@app.get("/api/summary", response_model=SummaryResponse)
def summary() -> SummaryResponse:
    return get_twin_service().summary()


@app.post("/api/refresh", response_model=RefreshResponse)
async def refresh() -> RefreshResponse:
    snapshots = await anyio.to_thread.run_sync(export_operational_artifacts, load_settings())
    get_twin_service().refresh()
    await snapshot_events.notify()
    return {"status": "refreshed", "snapshot_rows": int(len(snapshots))}


@app.post("/api/events/snapshot")
async def notify_snapshot_event() -> dict[str, int | str]:
    get_twin_service().refresh()
    version = await snapshot_events.notify()
    return {"status": "notified", "version": version}


@app.get("/api/stream")
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
