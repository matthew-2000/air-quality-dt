from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Literal
from uuid import uuid4

from unisa_air_twin.config import Settings
from unisa_air_twin.external_sources import fetch_external_context
from unisa_air_twin.ingestion import (
    build_realtime_dataset,
    collect_mqtt_messages,
    export_operational_artifacts,
    write_real_sensor_geojson,
)
from unisa_air_twin.operational_store import read_job_run, read_job_runs, upsert_job_run
from unisa_air_twin.osm import download_osm
from unisa_air_twin.projections import project_pending_events, rebuild_projections_from_event_log
from unisa_air_twin.zones import ensure_twin_layers

JobStatus = Literal["queued", "running", "completed", "failed"]


def utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class JobRun:
    job_id: str
    name: str
    status: JobStatus
    started_at: str
    finished_at: str | None = None
    message: str | None = None
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class JobRegistry:
    def __init__(self) -> None:
        self._jobs: dict[str, JobRun] = {}
        self._lock = Lock()

    def create(self, name: str, message: str | None = None, settings: Settings | None = None) -> JobRun:
        job = JobRun(job_id=uuid4().hex, name=name, status="queued", started_at=utc_timestamp(), message=message)
        with self._lock:
            self._jobs[job.job_id] = job
        if settings is not None:
            upsert_job_run(settings, job.to_dict())
        return job

    def get(self, job_id: str, settings: Settings | None = None) -> JobRun | None:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is not None:
            return job
        if settings is None:
            return None
        payload = read_job_run(settings, job_id)
        return JobRun(**payload) if payload else None

    def list(self, limit: int = 20, settings: Settings | None = None) -> list[JobRun]:
        if settings is not None:
            persisted = [JobRun(**payload) for payload in read_job_runs(settings, limit=limit)]
            if persisted:
                return persisted
        with self._lock:
            jobs = list(self._jobs.values())
        return sorted(jobs, key=lambda job: job.started_at, reverse=True)[:limit]

    def run(self, job_id: str, task: Callable[[], dict[str, Any]], settings: Settings | None = None) -> JobRun:
        with self._lock:
            job = self._jobs[job_id]
            job.status = "running"
        if settings is not None:
            upsert_job_run(settings, job.to_dict())
        try:
            result = task()
        except Exception as exc:
            with self._lock:
                job.status = "failed"
                job.finished_at = utc_timestamp()
                job.error = str(exc)
            if settings is not None:
                upsert_job_run(settings, job.to_dict())
            return job
        with self._lock:
            job.status = "completed"
            job.finished_at = utc_timestamp()
            job.result = result
        if settings is not None:
            upsert_job_run(settings, job.to_dict())
        return job


job_registry = JobRegistry()
_LIVE_INGEST_LOCK = Lock()


def prepare_context_layers(settings: Settings, force: bool = False) -> dict[str, Any]:
    layers = download_osm(settings, force=force)
    sensors = write_real_sensor_geojson(settings)
    entities = ensure_twin_layers(settings)
    return {
        "layers": {name: int(len(layer)) for name, layer in layers.items()},
        "sensors": int(len(sensors)),
        "entities": int(len(entities.get("entities", []))) if isinstance(entities, dict) else 0,
    }


def rebuild_operational_dataset(settings: Settings) -> dict[str, Any]:
    snapshots = build_realtime_dataset(settings)
    return {"snapshot_rows": int(len(snapshots))}


def refresh_operational_snapshots(settings: Settings) -> dict[str, Any]:
    snapshots = export_operational_artifacts(settings)
    return {"snapshot_rows": int(len(snapshots))}


def refresh_external_sources(settings: Settings, force: bool = True) -> dict[str, Any]:
    payload = fetch_external_context(settings, force=force)
    snapshots = build_realtime_dataset(settings)
    return {
        "sources": payload["sources"],
        "snapshot_rows": int(len(snapshots)),
    }


def collect_live_and_refresh(
    settings: Settings,
    duration_seconds: int = 30,
    max_messages: int | None = None,
) -> dict[str, Any]:
    messages = collect_mqtt_messages(
        settings,
        duration_seconds=duration_seconds,
        max_messages=max_messages,
    )
    projection = project_pending_events(settings)
    return {
        "mqtt_messages": int(messages),
        "snapshot_rows": int(projection["snapshot_rows"]),
    }


def collect_live_once(
    settings: Settings,
    duration_seconds: int = 10,
    max_messages: int | None = 25,
) -> dict[str, Any]:
    if not _LIVE_INGEST_LOCK.acquire(blocking=False):
        raise RuntimeError("Una sessione live e' gia' in corso. Attendi la fine del job attivo.")
    try:
        return collect_live_and_refresh(
            settings,
            duration_seconds=max(1, int(duration_seconds)),
            max_messages=max_messages,
        )
    finally:
        _LIVE_INGEST_LOCK.release()


def replay_operational_projections(settings: Settings) -> dict[str, Any]:
    return rebuild_projections_from_event_log(settings)
