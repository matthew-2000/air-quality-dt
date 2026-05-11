from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any

import pandas as pd

from unisa_air_twin.config import Settings
from unisa_air_twin.utils import ensure_dir, project_path

OBSERVATION_COLUMNS = [
    "timestamp",
    "received_at",
    "sensor_id",
    "sensor_name",
    "lat",
    "lon",
    "zone",
    "pollutant",
    "base_value",
    "estimated_value",
    "temperature",
    "humidity",
    "num_devices_sniffed",
    "traffic_index",
    "green_index",
    "wind_speed_10m",
    "precipitation",
    "traffic_component",
    "green_component",
    "wind_component",
    "rain_component",
    "background_value",
    "background_source",
    "station_count",
    "nearest_station_km",
    "mean_station_distance_km",
    "uncertainty_score",
    "confidence_label",
    "source",
    "source_url",
    "downloaded_at",
    "is_real",
]


SENSOR_COLUMNS = [
    "sensor_id",
    "name",
    "type",
    "lat",
    "lon",
    "zone",
    "description",
    "coordinate_quality",
    "source",
    "source_url",
    "downloaded_at",
    "is_real",
]


RAW_MESSAGE_COLUMNS = ["received_at", "topic", "payload"]

SNAPSHOT_COLUMNS = [
    *OBSERVATION_COLUMNS,
    "measured_at",
    "reading_age_seconds",
    "snapshot_bucket_minutes",
    "snapshot_freshness_minutes",
    "capable_sensor_count",
    "coverage_ratio",
]

JOB_RUN_COLUMNS = [
    "job_id",
    "name",
    "status",
    "started_at",
    "finished_at",
    "message",
    "result",
    "error",
]

SCENARIO_RUN_COLUMNS = [
    "run_id",
    "name",
    "scenario_type",
    "pollutant",
    "intensity",
    "created_at",
    "baseline_timestamp",
    "parameters",
    "output",
]

_SCHEMA_LOCK = Lock()
_INITIALIZED_DATABASES: set[str] = set()


def database_path(settings: Settings) -> Path:
    config = settings.live_sensors.get("operational", {})
    value = config.get("db_path")
    if not value:
        return settings.processed_dir / "realtime_operational.db"
    path = Path(value)
    return path if path.is_absolute() else project_path(path)


def connect_db(settings: Settings) -> sqlite3.Connection:
    path = database_path(settings)
    ensure_dir(path.parent)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    return connection


def ensure_schema(settings: Settings) -> None:
    db_key = str(database_path(settings))
    if db_key in _INITIALIZED_DATABASES:
        return
    with _SCHEMA_LOCK:
        if db_key in _INITIALIZED_DATABASES:
            return
        with connect_db(settings) as connection:
            try:
                connection.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError:
                connection.execute("PRAGMA journal_mode=DELETE")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sensors (
                    sensor_id TEXT PRIMARY KEY,
                    name TEXT,
                    type TEXT,
                    lat REAL,
                    lon REAL,
                    zone TEXT,
                    description TEXT,
                    coordinate_quality TEXT,
                    source TEXT,
                    source_url TEXT,
                    downloaded_at TEXT,
                    is_real INTEGER
                );

                CREATE TABLE IF NOT EXISTS raw_mqtt_messages (
                    received_at TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (received_at, topic, payload)
                );

                CREATE TABLE IF NOT EXISTS observations (
                    timestamp TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    sensor_id TEXT NOT NULL,
                    sensor_name TEXT,
                    lat REAL,
                    lon REAL,
                    zone TEXT,
                    pollutant TEXT NOT NULL,
                    base_value REAL,
                    estimated_value REAL,
                    temperature REAL,
                    humidity REAL,
                    num_devices_sniffed INTEGER,
                    traffic_index REAL,
                    green_index REAL,
                    wind_speed_10m REAL,
                    precipitation REAL,
                    traffic_component REAL,
                    green_component REAL,
                    wind_component REAL,
                    rain_component REAL,
                    background_value REAL,
                    background_source TEXT,
                    station_count INTEGER,
                    nearest_station_km REAL,
                    mean_station_distance_km REAL,
                    uncertainty_score REAL,
                    confidence_label TEXT,
                    source TEXT,
                    source_url TEXT,
                    downloaded_at TEXT,
                    is_real INTEGER,
                    PRIMARY KEY (timestamp, sensor_id, pollutant, received_at)
                );

                CREATE INDEX IF NOT EXISTS idx_observations_pollutant_timestamp
                ON observations (pollutant, timestamp);

                CREATE INDEX IF NOT EXISTS idx_observations_sensor_timestamp
                ON observations (sensor_id, timestamp);

                CREATE TABLE IF NOT EXISTS operational_snapshots (
                    timestamp TEXT NOT NULL,
                    received_at TEXT NOT NULL,
                    sensor_id TEXT NOT NULL,
                    sensor_name TEXT,
                    lat REAL,
                    lon REAL,
                    zone TEXT,
                    pollutant TEXT NOT NULL,
                    base_value REAL,
                    estimated_value REAL,
                    temperature REAL,
                    humidity REAL,
                    num_devices_sniffed INTEGER,
                    traffic_index REAL,
                    green_index REAL,
                    wind_speed_10m REAL,
                    precipitation REAL,
                    traffic_component REAL,
                    green_component REAL,
                    wind_component REAL,
                    rain_component REAL,
                    background_value REAL,
                    background_source TEXT,
                    station_count INTEGER,
                    nearest_station_km REAL,
                    mean_station_distance_km REAL,
                    uncertainty_score REAL,
                    confidence_label TEXT,
                    source TEXT,
                    source_url TEXT,
                    downloaded_at TEXT,
                    is_real INTEGER,
                    measured_at TEXT,
                    reading_age_seconds INTEGER,
                    snapshot_bucket_minutes INTEGER,
                    snapshot_freshness_minutes INTEGER,
                    capable_sensor_count INTEGER,
                    coverage_ratio REAL,
                    PRIMARY KEY (timestamp, sensor_id, pollutant, received_at)
                );

                CREATE INDEX IF NOT EXISTS idx_snapshots_pollutant_timestamp
                ON operational_snapshots (pollutant, timestamp);

                CREATE INDEX IF NOT EXISTS idx_snapshots_sensor_timestamp
                ON operational_snapshots (sensor_id, timestamp);

                CREATE TABLE IF NOT EXISTS store_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ingestion_runs (
                    run_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    finished_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    raw_message_rows INTEGER NOT NULL DEFAULT 0,
                    observation_rows INTEGER NOT NULL DEFAULT 0,
                    snapshot_rows INTEGER NOT NULL DEFAULT 0,
                    sensor_rows INTEGER NOT NULL DEFAULT 0,
                    details TEXT NOT NULL DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS job_runs (
                    job_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    message TEXT,
                    result TEXT NOT NULL DEFAULT '{}',
                    error TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_job_runs_started_at
                ON job_runs (started_at DESC);

                CREATE TABLE IF NOT EXISTS scenario_runs (
                    run_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    scenario_type TEXT NOT NULL,
                    pollutant TEXT NOT NULL,
                    intensity REAL NOT NULL,
                    created_at TEXT NOT NULL,
                    baseline_timestamp TEXT,
                    parameters TEXT NOT NULL DEFAULT '{}',
                    output TEXT NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS idx_scenario_runs_created_at
                ON scenario_runs (created_at DESC);
                """
            )
            connection.execute(
                """
                INSERT INTO store_metadata (key, value) VALUES ('schema_version', '1')
                ON CONFLICT(key) DO NOTHING
                """
            )
            existing_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(observations)").fetchall()
            }
            for column_name, column_type in [
                ("wind_component", "REAL"),
                ("rain_component", "REAL"),
                ("background_value", "REAL"),
                ("background_source", "TEXT"),
            ]:
                if column_name not in existing_columns:
                    connection.execute(f"ALTER TABLE observations ADD COLUMN {column_name} {column_type}")
            snapshot_columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(operational_snapshots)").fetchall()
            }
            for column_name, column_type in [
                ("wind_component", "REAL"),
                ("rain_component", "REAL"),
                ("background_value", "REAL"),
                ("background_source", "TEXT"),
                ("measured_at", "TEXT"),
                ("reading_age_seconds", "INTEGER"),
                ("snapshot_bucket_minutes", "INTEGER"),
                ("snapshot_freshness_minutes", "INTEGER"),
                ("capable_sensor_count", "INTEGER"),
                ("coverage_ratio", "REAL"),
            ]:
                if column_name not in snapshot_columns:
                    connection.execute(f"ALTER TABLE operational_snapshots ADD COLUMN {column_name} {column_type}")
        _INITIALIZED_DATABASES.add(db_key)


def _normalize_frame(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=columns)
    copy = frame.copy()
    for column in columns:
        if column not in copy.columns:
            copy[column] = None
    copy = copy[columns]
    for column in copy.columns:
        series = copy[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            copy[column] = pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m-%dT%H:%M:%S")
        elif series.dtype == "object":
            copy[column] = series.map(
                lambda value: value.strftime("%Y-%m-%dT%H:%M:%S")
                if isinstance(value, pd.Timestamp)
                else int(value)
                if isinstance(value, bool)
                else value
            )
    copy = copy.where(pd.notna(copy), None)
    return copy


def replace_sensors(settings: Settings, sensors: pd.DataFrame) -> None:
    ensure_schema(settings)
    frame = _normalize_frame(sensors, SENSOR_COLUMNS)
    with connect_db(settings) as connection:
        connection.execute("DELETE FROM sensors")
        if not frame.empty:
            rows = [tuple(row) for row in frame.itertuples(index=False, name=None)]
            placeholders = ",".join(["?"] * len(SENSOR_COLUMNS))
            connection.executemany(
                f"INSERT INTO sensors ({','.join(SENSOR_COLUMNS)}) VALUES ({placeholders})",
                rows,
            )


def replace_observations(settings: Settings, observations: pd.DataFrame) -> None:
    ensure_schema(settings)
    frame = _normalize_frame(observations, OBSERVATION_COLUMNS)
    with connect_db(settings) as connection:
        connection.execute("DELETE FROM observations")
        if not frame.empty:
            rows = [tuple(row) for row in frame.itertuples(index=False, name=None)]
            placeholders = ",".join(["?"] * len(OBSERVATION_COLUMNS))
            connection.executemany(
                f"INSERT INTO observations ({','.join(OBSERVATION_COLUMNS)}) VALUES ({placeholders})",
                rows,
            )


def upsert_observations(settings: Settings, observations: pd.DataFrame) -> int:
    ensure_schema(settings)
    frame = _normalize_frame(observations, OBSERVATION_COLUMNS)
    if frame.empty:
        return 0
    with connect_db(settings) as connection:
        rows = [tuple(row) for row in frame.itertuples(index=False, name=None)]
        placeholders = ",".join(["?"] * len(OBSERVATION_COLUMNS))
        connection.executemany(
            f"""
            INSERT OR REPLACE INTO observations ({','.join(OBSERVATION_COLUMNS)})
            VALUES ({placeholders})
            """,
            rows,
        )
    return len(frame)


def append_raw_messages(settings: Settings, rows: list[dict[str, Any]]) -> int:
    ensure_schema(settings)
    frame = _normalize_frame(pd.DataFrame(rows), RAW_MESSAGE_COLUMNS)
    if frame.empty:
        return 0
    with connect_db(settings) as connection:
        raw_rows = [tuple(row) for row in frame.itertuples(index=False, name=None)]
        connection.executemany(
            """
            INSERT OR IGNORE INTO raw_mqtt_messages (received_at, topic, payload)
            VALUES (?, ?, ?)
            """,
            raw_rows,
        )
    return len(frame)


def replace_snapshots(settings: Settings, snapshots: pd.DataFrame) -> None:
    ensure_schema(settings)
    frame = _normalize_frame(snapshots, SNAPSHOT_COLUMNS)
    with connect_db(settings) as connection:
        connection.execute("DELETE FROM operational_snapshots")
        if not frame.empty:
            rows = [tuple(row) for row in frame.itertuples(index=False, name=None)]
            placeholders = ",".join(["?"] * len(SNAPSHOT_COLUMNS))
            connection.executemany(
                f"INSERT INTO operational_snapshots ({','.join(SNAPSHOT_COLUMNS)}) VALUES ({placeholders})",
                rows,
            )


def read_sensors(settings: Settings) -> pd.DataFrame:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        return pd.read_sql_query("SELECT * FROM sensors ORDER BY sensor_id", connection)


def read_observations(settings: Settings) -> pd.DataFrame:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        return pd.read_sql_query(
            "SELECT * FROM observations ORDER BY timestamp, pollutant, sensor_id, received_at",
            connection,
        )


def read_snapshots(settings: Settings) -> pd.DataFrame:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        return pd.read_sql_query(
            "SELECT * FROM operational_snapshots ORDER BY timestamp, pollutant, sensor_id, received_at",
            connection,
        )


def read_recent_observations(settings: Settings, since_timestamp: str | None = None) -> pd.DataFrame:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        if not since_timestamp:
            return pd.read_sql_query(
                "SELECT * FROM observations ORDER BY timestamp, pollutant, sensor_id, received_at",
                connection,
            )
        return pd.read_sql_query(
            """
            SELECT * FROM observations
            WHERE timestamp >= ?
            ORDER BY timestamp, pollutant, sensor_id, received_at
            """,
            connection,
            params=[since_timestamp],
        )


def read_raw_messages(settings: Settings) -> pd.DataFrame:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        return pd.read_sql_query(
            "SELECT * FROM raw_mqtt_messages ORDER BY received_at, topic",
            connection,
        )


def read_raw_message_count(settings: Settings) -> int:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        row = connection.execute("SELECT COUNT(*) AS count FROM raw_mqtt_messages").fetchone()
    return int(row["count"] or 0)


def upsert_job_run(settings: Settings, job: dict[str, Any]) -> None:
    ensure_schema(settings)
    payload = dict(job)
    payload["result"] = json.dumps(payload.get("result") or {}, ensure_ascii=False)
    frame = _normalize_frame(pd.DataFrame([payload]), JOB_RUN_COLUMNS)
    with connect_db(settings) as connection:
        row = tuple(frame.iloc[0].tolist())
        placeholders = ",".join(["?"] * len(JOB_RUN_COLUMNS))
        updates = ",".join(f"{column}=excluded.{column}" for column in JOB_RUN_COLUMNS if column != "job_id")
        connection.execute(
            f"""
            INSERT INTO job_runs ({','.join(JOB_RUN_COLUMNS)}) VALUES ({placeholders})
            ON CONFLICT(job_id) DO UPDATE SET {updates}
            """,
            row,
        )


def _job_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    try:
        payload["result"] = json.loads(payload.get("result") or "{}")
    except json.JSONDecodeError:
        payload["result"] = {}
    return payload


def read_job_run(settings: Settings, job_id: str) -> dict[str, Any] | None:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        row = connection.execute("SELECT * FROM job_runs WHERE job_id = ?", [job_id]).fetchone()
    return _job_row_to_dict(row) if row else None


def read_job_runs(settings: Settings, limit: int = 20) -> list[dict[str, Any]]:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        rows = connection.execute(
            "SELECT * FROM job_runs ORDER BY started_at DESC LIMIT ?",
            [limit],
        ).fetchall()
    return [_job_row_to_dict(row) for row in rows]


def write_scenario_run(settings: Settings, run: dict[str, Any]) -> None:
    ensure_schema(settings)
    payload = dict(run)
    payload["parameters"] = json.dumps(payload.get("parameters") or {}, ensure_ascii=False)
    payload["output"] = json.dumps(payload.get("output") or {}, ensure_ascii=False)
    frame = _normalize_frame(pd.DataFrame([payload]), SCENARIO_RUN_COLUMNS)
    with connect_db(settings) as connection:
        row = tuple(frame.iloc[0].tolist())
        placeholders = ",".join(["?"] * len(SCENARIO_RUN_COLUMNS))
        updates = ",".join(f"{column}=excluded.{column}" for column in SCENARIO_RUN_COLUMNS if column != "run_id")
        connection.execute(
            f"""
            INSERT INTO scenario_runs ({','.join(SCENARIO_RUN_COLUMNS)}) VALUES ({placeholders})
            ON CONFLICT(run_id) DO UPDATE SET {updates}
            """,
            row,
        )


def _scenario_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    for key in ["parameters", "output"]:
        try:
            payload[key] = json.loads(payload.get(key) or "{}")
        except json.JSONDecodeError:
            payload[key] = {}
    return payload


def read_scenario_runs(settings: Settings, limit: int = 20) -> list[dict[str, Any]]:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        rows = connection.execute(
            "SELECT * FROM scenario_runs ORDER BY created_at DESC LIMIT ?",
            [limit],
        ).fetchall()
    return [_scenario_row_to_dict(row) for row in rows]


def write_ingestion_run(settings: Settings, metadata: dict[str, Any], status: str = "completed") -> None:
    ensure_schema(settings)
    generated_at = str(metadata.get("generated_at") or "")
    run_id = generated_at or f"run-{len(json.dumps(metadata, sort_keys=True))}"
    details = json.dumps(metadata, ensure_ascii=False)
    with connect_db(settings) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO ingestion_runs (
                run_id,
                started_at,
                finished_at,
                status,
                raw_message_rows,
                observation_rows,
                snapshot_rows,
                sensor_rows,
                details
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run_id,
                generated_at,
                generated_at,
                status,
                int(metadata.get("raw_message_rows", 0) or 0),
                int(metadata.get("observation_rows", metadata.get("raw_rows", 0)) or 0),
                int(metadata.get("snapshot_rows", 0) or 0),
                int(metadata.get("sensors", 0) or 0),
                details,
            ],
        )


def write_metadata(settings: Settings, key: str, value: Any) -> None:
    ensure_schema(settings)
    serialized = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    with connect_db(settings) as connection:
        connection.execute(
            """
            INSERT INTO store_metadata (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            [key, serialized],
        )


def read_metadata(settings: Settings) -> dict[str, Any]:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        rows = connection.execute("SELECT key, value FROM store_metadata").fetchall()
    output: dict[str, Any] = {}
    for row in rows:
        value = row["value"]
        try:
            output[row["key"]] = json.loads(value)
        except json.JSONDecodeError:
            output[row["key"]] = value
    return output
