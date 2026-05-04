from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class CampusInfo(BaseModel):
    name: str
    latitude: float | None = None
    longitude: float | None = None


class CoverageRow(BaseModel):
    pollutant: str
    active_sensors: int
    capable_sensors: int
    coverage_ratio: float


class LiveFeedStatus(BaseModel):
    status: Literal["live", "stale", "unconfigured", "unknown"]
    configured: bool
    missing_env: list[str]
    latest_received_at: str | None = None
    age_minutes: int | None = None


class IngestionSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    raw_rows: int = 0
    raw_message_rows: int = 0
    observation_rows: int = 0
    snapshot_rows: int = 0
    sensors: int = 0
    source: str | None = None
    source_url: str | None = None
    generated_at: str | None = None
    pollutants: list[str] = []
    snapshot_bucket_minutes: int | None = None
    snapshot_freshness_minutes: int | None = None
    snapshot_timestamps: int | None = None


class SensorHealth(BaseModel):
    sensor_id: str
    sensor_name: str | None = None
    status: Literal["fresh", "recent", "aging", "unknown", "silent"]
    latest_received_at: str | None = None
    latest_measured_at: str | None = None
    pollutants: list[str] = []


class SummaryResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    project: str
    source: str | None = None
    campus: CampusInfo
    pollutants: list[str]
    default_pollutant: str
    latest_timestamp: str | None = None
    latest_received_at: str | None = None
    rows: int
    raw_rows: int = 0
    raw_message_rows: int = 0
    observation_rows: int = 0
    snapshot_rows: int = 0
    sensors: int
    active_sensors: int = 0
    capable_sensors: int = 0
    coverage_ratio: float = 0.0
    sensor_health: list[SensorHealth] = []
    stations: int = 0
    coverage_by_pollutant: list[CoverageRow]
    layer_counts: dict[str, int] = {}
    ingestion: IngestionSummary
    live_feed: LiveFeedStatus
    warnings: list[Any] = []
    mode: str


class RefreshResponse(BaseModel):
    status: str
    snapshot_rows: int


class TimestampsResponse(BaseModel):
    timestamps: list[str]


class MapPayloadResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    snapshot: list[dict[str, Any]]
    grid: list[dict[str, Any]]
    reliability_grid: list[dict[str, Any]]
    zones: dict[str, Any]
    zone_summary: list[dict[str, Any]] = []
    layers: dict[str, dict[str, Any]]
    stations: list[dict[str, Any]]
    meta: dict[str, Any]


class TimeseriesResponse(BaseModel):
    points: list[dict[str, Any]]


class SensorDetailResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    sensor: dict[str, Any]
    timestamp: str
    latest_values: list[dict[str, Any]]
    history: dict[str, list[dict[str, Any]]]
    environment: dict[str, Any]


class AnalyticsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    pollutant: str
    timestamp: str | None = None
    quality: dict[str, Any]
    zone_summary: list[dict[str, Any]]
    zone_geojson: dict[str, Any]
    trend: list[dict[str, Any]]
