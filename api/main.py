from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated, Any

import anyio
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse

from api.autostart import auto_ingest_loop
from api.events import snapshot_events
from api.streaming import summary_stream
from unisa_air_twin.api_schemas import (
    AnalyticsResponse,
    JobListResponse,
    JobRunResponse,
    MapPayloadResponse,
    OperationalHealthResponse,
    RefreshResponse,
    SensorDetailResponse,
    SummaryResponse,
    TimeseriesResponse,
    TimestampsResponse,
)
from unisa_air_twin.config import load_settings
from unisa_air_twin.decision_engine import health_payload
from unisa_air_twin.external_sources import read_source_statuses
from unisa_air_twin.operational_store import read_observations, read_raw_messages, read_sensors
from unisa_air_twin.product_jobs import (
    collect_live_once,
    job_registry,
    prepare_context_layers,
    rebuild_operational_dataset,
    refresh_external_sources,
    refresh_operational_snapshots,
)
from unisa_air_twin.ui_data import get_twin_service
from unisa_air_twin.utils import project_path


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    ingest_task = asyncio.create_task(auto_ingest_loop(settings, get_twin_service, snapshot_events))
    try:
        yield
    finally:
        ingest_task.cancel()
        with suppress(asyncio.CancelledError):
            await ingest_task


app = FastAPI(
    title="UNISA Air Quality Digital Twin API",
    version="0.1.0",
    description="Operational API for real-only UNISA sensor snapshots, raw histories, and campus context layers.",
    lifespan=lifespan,
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


async def _summary_stream(request: Request) -> AsyncIterator[str]:
    async for event in summary_stream(request, snapshot_events, get_twin_service):
        yield event


@app.get("/api/summary", response_model=SummaryResponse)
def summary() -> SummaryResponse:
    return get_twin_service().summary()


@app.post("/api/refresh", response_model=RefreshResponse)
async def refresh() -> RefreshResponse:
    result = await anyio.to_thread.run_sync(refresh_operational_snapshots, load_settings())
    get_twin_service().refresh()
    await snapshot_events.notify()
    return {"status": "refreshed", "snapshot_rows": int(result["snapshot_rows"])}


async def _run_job_and_notify(job_id: str, task: Any, refresh_view: bool = True) -> None:
    settings = load_settings()
    await anyio.to_thread.run_sync(job_registry.run, job_id, task, settings)
    if refresh_view:
        get_twin_service().refresh()
        await snapshot_events.notify()


def _job_response(job_id: str) -> dict[str, Any]:
    job = job_registry.get(job_id, settings=load_settings())
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@app.get("/api/jobs", response_model=JobListResponse)
def jobs(limit: Annotated[int, Query(ge=1, le=50)] = 20) -> JobListResponse:
    return {"jobs": [job.to_dict() for job in job_registry.list(limit=limit, settings=load_settings())]}


@app.get("/api/jobs/{job_id}", response_model=JobRunResponse)
def job_detail(job_id: str) -> JobRunResponse:
    return _job_response(job_id)


@app.post("/api/jobs/refresh", response_model=JobRunResponse, status_code=202)
async def start_refresh_job(background_tasks: BackgroundTasks) -> JobRunResponse:
    settings = load_settings()
    job = job_registry.create("refresh_snapshots", "Ricostruzione snapshot dallo store operativo.", settings=settings)
    background_tasks.add_task(_run_job_and_notify, job.job_id, lambda: refresh_operational_snapshots(load_settings()))
    return job.to_dict()


@app.post("/api/jobs/snapshots", response_model=JobRunResponse, status_code=202)
async def start_snapshot_rebuild_job(background_tasks: BackgroundTasks) -> JobRunResponse:
    settings = load_settings()
    job = job_registry.create("rebuild_dataset", "Normalizzazione MQTT raw e ricostruzione dataset operativo.", settings=settings)
    background_tasks.add_task(_run_job_and_notify, job.job_id, lambda: rebuild_operational_dataset(load_settings()))
    return job.to_dict()


@app.post("/api/jobs/context", response_model=JobRunResponse, status_code=202)
async def start_context_job(
    background_tasks: BackgroundTasks,
    force: bool = Query(default=False),
) -> JobRunResponse:
    settings = load_settings()
    job = job_registry.create("prepare_context", "Aggiornamento sensori, zone e layer campus.", settings=settings)
    background_tasks.add_task(
        _run_job_and_notify,
        job.job_id,
        lambda: prepare_context_layers(load_settings(), force=force),
        False,
    )
    return job.to_dict()


@app.post("/api/jobs/enrich", response_model=JobRunResponse, status_code=202)
async def start_enrichment_job(
    background_tasks: BackgroundTasks,
    force: bool = Query(default=True),
) -> JobRunResponse:
    settings = load_settings()
    job = job_registry.create("refresh_external_sources", "Aggiornamento fonti gratuite e arricchimento dataset operativo.", settings=settings)
    background_tasks.add_task(_run_job_and_notify, job.job_id, lambda: refresh_external_sources(load_settings(), force=force))
    return job.to_dict()


@app.post("/api/jobs/live-ingest", response_model=JobRunResponse, status_code=202)
async def start_live_ingest_job(
    background_tasks: BackgroundTasks,
    duration_seconds: Annotated[int, Query(ge=1, le=60)] = 10,
    max_messages: Annotated[int | None, Query(ge=1, le=200)] = 25,
) -> JobRunResponse:
    settings = load_settings()
    job = job_registry.create(
        "live_ingest_once",
        f"Ascolto MQTT manuale per {duration_seconds}s e refresh snapshot operativo.",
        settings=settings,
    )
    background_tasks.add_task(
        _run_job_and_notify,
        job.job_id,
        lambda: collect_live_once(
            load_settings(),
            duration_seconds=duration_seconds,
            max_messages=max_messages,
        ),
    )
    return job.to_dict()


@app.get("/api/sources")
def sources() -> dict[str, Any]:
    return {"sources": read_source_statuses(load_settings())}


@app.get("/api/export/{dataset}")
def export_dataset(
    dataset: str,
    format: str = Query(default="csv", pattern="^(csv|json)$"),
) -> Response:
    settings = load_settings()
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


@app.get("/api/ops/health", response_model=OperationalHealthResponse)
def ops_health() -> OperationalHealthResponse:
    settings = load_settings()
    return health_payload(get_twin_service().summary(), [job.to_dict() for job in job_registry.list(limit=50, settings=settings)])


def frontend_dist_dir() -> Path:
    return project_path("web", "dist")


def frontend_index_path() -> Path:
    return frontend_dist_dir() / "index.html"


def _frontend_file(full_path: str) -> Path | None:
    root = frontend_dist_dir().resolve()
    candidate = (root / full_path).resolve()
    if candidate == root:
        return None
    if root not in candidate.parents:
        return None
    if candidate.is_file():
        return candidate
    return None


@app.get("/", include_in_schema=False)
def frontend_index() -> Response:
    index_path = frontend_index_path()
    if not index_path.exists():
        raise HTTPException(status_code=503, detail="Frontend assets not available")
    return FileResponse(index_path)


@app.get("/{full_path:path}", include_in_schema=False)
def frontend_routes(full_path: str) -> Response:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    index_path = frontend_index_path()
    if not index_path.exists():
        raise HTTPException(status_code=503, detail="Frontend assets not available")
    asset = _frontend_file(full_path)
    if asset is not None:
        return FileResponse(asset)
    return FileResponse(index_path)
