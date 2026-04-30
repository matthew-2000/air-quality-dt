from __future__ import annotations

import os
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


def _load_dotenv_file(path: Path, protected_keys: set[str]) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if value and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key not in protected_keys:
            os.environ[key] = value


def load_dotenv(path: str | Path | None = None) -> None:
    protected_keys = set(os.environ)
    if path is not None:
        _load_dotenv_file(Path(path), protected_keys)
        return
    for candidate in [project_path(".env"), project_path(".env.local")]:
        _load_dotenv_file(candidate, protected_keys)


def load_settings(path: str | Path | None = None) -> Settings:
    load_dotenv()
    settings_path = Path(path) if path else project_path("config/settings.yaml")
    data = yaml.safe_load(settings_path.read_text(encoding="utf-8"))
    settings = Settings(**data)
    settings.raw_dir = project_path(settings.paths["raw_dir"])
    settings.processed_dir = project_path(settings.paths["processed_dir"])
    return settings
