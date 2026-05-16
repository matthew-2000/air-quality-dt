from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from api.events import SnapshotEventBus, snapshot_events
from unisa_air_twin.application.twin_query_service import TwinDataService
from unisa_air_twin.application.twin_query_service import (
    get_twin_service as default_twin_service,
)
from unisa_air_twin.config import Settings, load_settings
from unisa_air_twin.product_jobs import JobRegistry, job_registry
from unisa_air_twin.utils import project_path


class ApiRuntime:
    def __init__(
        self,
        settings_loader: Callable[[], Settings] | None = None,
        twin_service_factory: Callable[[], TwinDataService] | None = None,
        events: SnapshotEventBus | None = None,
        jobs: JobRegistry | None = None,
        frontend_root_factory: Callable[[], Path] | None = None,
    ) -> None:
        self.settings_loader = settings_loader or load_settings
        self.twin_service_factory = twin_service_factory or default_twin_service
        self.events = events or snapshot_events
        self.jobs = jobs or job_registry
        self.frontend_root_factory = frontend_root_factory or (lambda: project_path("web", "dist"))

    def settings(self) -> Settings:
        return self.settings_loader()

    def twin_service(self) -> TwinDataService:
        return self.twin_service_factory()

    def frontend_dist_dir(self) -> Path:
        return self.frontend_root_factory()


runtime = ApiRuntime()


def get_settings() -> Settings:
    return runtime.settings()


def get_twin_service() -> TwinDataService:
    return runtime.twin_service()


def get_snapshot_events() -> SnapshotEventBus:
    return runtime.events


def get_job_registry() -> JobRegistry:
    return runtime.jobs


def frontend_dist_dir() -> Path:
    return runtime.frontend_dist_dir()


def frontend_index_path() -> Path:
    return frontend_dist_dir() / "index.html"


def frontend_file(full_path: str) -> Path | None:
    root = frontend_dist_dir().resolve()
    candidate = (root / full_path).resolve()
    if candidate == root:
        return None
    if root not in candidate.parents:
        return None
    if candidate.is_file():
        return candidate
    return None
