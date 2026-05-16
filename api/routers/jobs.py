from __future__ import annotations

from typing import Annotated, Any

import anyio
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

import api.dependencies as deps
from unisa_air_twin.api_schemas import JobListResponse, JobRunResponse, RefreshResponse
from unisa_air_twin.product_jobs import (
    collect_live_once,
    prepare_context_layers,
    rebuild_operational_dataset,
    refresh_external_sources,
    refresh_operational_snapshots,
    replay_operational_projections,
)

router = APIRouter()


async def _run_job_and_notify(job_id: str, task: Any, refresh_view: bool = True) -> None:
    settings = deps.get_settings()
    await anyio.to_thread.run_sync(deps.get_job_registry().run, job_id, task, settings)
    if refresh_view:
        deps.get_twin_service().refresh()
        await deps.get_snapshot_events().notify()


def _job_response(job_id: str) -> dict[str, Any]:
    job = deps.get_job_registry().get(job_id, settings=deps.get_settings())
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dict()


@router.get("/api/jobs", response_model=JobListResponse)
def jobs(limit: Annotated[int, Query(ge=1, le=50)] = 20) -> JobListResponse:
    return {"jobs": [job.to_dict() for job in deps.get_job_registry().list(limit=limit, settings=deps.get_settings())]}


@router.get("/api/jobs/{job_id}", response_model=JobRunResponse)
def job_detail(job_id: str) -> JobRunResponse:
    return _job_response(job_id)


@router.post("/api/refresh", response_model=RefreshResponse)
async def refresh() -> RefreshResponse:
    result = await anyio.to_thread.run_sync(refresh_operational_snapshots, deps.get_settings())
    deps.get_twin_service().refresh()
    await deps.get_snapshot_events().notify()
    return {"status": "refreshed", "snapshot_rows": int(result["snapshot_rows"])}


@router.post("/api/jobs/refresh", response_model=JobRunResponse, status_code=202)
async def start_refresh_job(background_tasks: BackgroundTasks) -> JobRunResponse:
    settings = deps.get_settings()
    job = deps.get_job_registry().create("refresh_snapshots", "Ricostruzione snapshot dallo store operativo.", settings=settings)
    background_tasks.add_task(_run_job_and_notify, job.job_id, lambda: refresh_operational_snapshots(deps.get_settings()))
    return job.to_dict()


@router.post("/api/jobs/snapshots", response_model=JobRunResponse, status_code=202)
async def start_snapshot_rebuild_job(background_tasks: BackgroundTasks) -> JobRunResponse:
    settings = deps.get_settings()
    job = deps.get_job_registry().create("rebuild_dataset", "Normalizzazione MQTT raw e ricostruzione dataset operativo.", settings=settings)
    background_tasks.add_task(_run_job_and_notify, job.job_id, lambda: rebuild_operational_dataset(deps.get_settings()))
    return job.to_dict()


@router.post("/api/jobs/context", response_model=JobRunResponse, status_code=202)
async def start_context_job(
    background_tasks: BackgroundTasks,
    force: bool = Query(default=False),
) -> JobRunResponse:
    settings = deps.get_settings()
    job = deps.get_job_registry().create("prepare_context", "Aggiornamento sensori, zone e layer campus.", settings=settings)
    background_tasks.add_task(
        _run_job_and_notify,
        job.job_id,
        lambda: prepare_context_layers(deps.get_settings(), force=force),
        False,
    )
    return job.to_dict()


@router.post("/api/jobs/enrich", response_model=JobRunResponse, status_code=202)
async def start_enrichment_job(
    background_tasks: BackgroundTasks,
    force: bool = Query(default=True),
) -> JobRunResponse:
    settings = deps.get_settings()
    job = deps.get_job_registry().create("refresh_external_sources", "Aggiornamento fonti gratuite e arricchimento dataset operativo.", settings=settings)
    background_tasks.add_task(_run_job_and_notify, job.job_id, lambda: refresh_external_sources(deps.get_settings(), force=force))
    return job.to_dict()


@router.post("/api/jobs/live-ingest", response_model=JobRunResponse, status_code=202)
async def start_live_ingest_job(
    background_tasks: BackgroundTasks,
    duration_seconds: Annotated[int, Query(ge=1, le=60)] = 10,
    max_messages: Annotated[int | None, Query(ge=1, le=200)] = 25,
) -> JobRunResponse:
    settings = deps.get_settings()
    job = deps.get_job_registry().create(
        "live_ingest_once",
        f"Ascolto MQTT manuale per {duration_seconds}s e refresh snapshot operativo.",
        settings=settings,
    )
    background_tasks.add_task(
        _run_job_and_notify,
        job.job_id,
        lambda: collect_live_once(
            deps.get_settings(),
            duration_seconds=duration_seconds,
            max_messages=max_messages,
        ),
    )
    return job.to_dict()


@router.post("/api/jobs/replay-projections", response_model=JobRunResponse, status_code=202)
async def start_projection_replay_job(background_tasks: BackgroundTasks) -> JobRunResponse:
    settings = deps.get_settings()
    job = deps.get_job_registry().create(
        "replay_projections",
        "Replay append-only event log e ricostruzione proiezioni operative.",
        settings=settings,
    )
    background_tasks.add_task(
        _run_job_and_notify,
        job.job_id,
        lambda: replay_operational_projections(deps.get_settings()),
    )
    return job.to_dict()
