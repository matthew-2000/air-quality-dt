from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from unisa_air_twin.utils import project_path


class Settings(BaseModel):
    project: dict[str, Any]
    paths: dict[str, str]
    campus: dict[str, Any]
    live_sensors: dict[str, Any] = Field(default_factory=dict)
    model: dict[str, Any]

    raw_dir: Path = Field(default_factory=lambda: project_path("data/raw"))
    processed_dir: Path = Field(default_factory=lambda: project_path("data/processed"))


def load_settings(path: str | Path | None = None) -> Settings:
    settings_path = Path(path) if path else project_path("config/settings.yaml")
    data = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
    settings = Settings(**data)
    settings.raw_dir = project_path(settings.paths["raw_dir"])
    settings.processed_dir = project_path(settings.paths["processed_dir"])
    return settings
