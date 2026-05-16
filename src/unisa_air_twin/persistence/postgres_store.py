from __future__ import annotations

import json
import os
import re
from threading import Lock
from typing import Any

import pandas as pd

from unisa_air_twin.config import Settings
from unisa_air_twin.persistence.base import OperationalStore
from unisa_air_twin.shared.constants import (
    JOB_RUN_COLUMNS,
    OBSERVATION_COLUMNS,
    RAW_MESSAGE_COLUMNS,
    SENSOR_COLUMNS,
    SNAPSHOT_COLUMNS,
)
from unisa_air_twin.utils import project_path

_SCHEMA_LOCK = Lock()
_INITIALIZED_DATABASES: set[str] = set()
_VALID_SCHEMA = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _operational_config(settings: Settings) -> dict[str, Any]:
    return settings.live_sensors.get("operational", {})


def _dsn(settings: Settings) -> str:
    config = _operational_config(settings)
    dsn = str(
        config.get("postgres_dsn")
        or os.environ.get(config.get("postgres_dsn_env", "UNISA_AQDT_POSTGRES_DSN"), "")
    ).strip()
    if not dsn:
        raise RuntimeError(
            "Postgres backend selected but DSN missing. Set UNISA_AQDT_POSTGRES_DSN or live_sensors.operational.postgres_dsn."
        )
    return dsn


def _schema(settings: Settings) -> str:
    config = _operational_config(settings)
    schema = str(
        config.get("postgres_schema")
        or os.environ.get(config.get("postgres_schema_env", "UNISA_AQDT_POSTGRES_SCHEMA"), "aqdt")
    ).strip()
    if not _VALID_SCHEMA.match(schema):
        raise RuntimeError(f"Invalid Postgres schema name: {schema}")
    return schema


def database_path(settings: Settings) -> str:
    return _dsn(settings)


def connect_db(settings: Settings) -> Any:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:
        raise RuntimeError(
            "Postgres backend requires psycopg. Install project dependencies including psycopg[binary]."
        ) from exc
    return psycopg.connect(_dsn(settings), row_factory=dict_row)


def _table(settings: Settings, name: str) -> str:
    return f'"{_schema(settings)}".{name}'


def _migration_sql(settings: Settings) -> str:
    migration_path = project_path(
        "src",
        "unisa_air_twin",
        "persistence",
        "migrations",
        "001_initial_postgres.sql",
    )
    return migration_path.read_text(encoding="utf-8").replace("__AQDT_SCHEMA__", _schema(settings))


def ensure_schema(settings: Settings) -> None:
    db_key = f"{_dsn(settings)}::{_schema(settings)}"
    if db_key in _INITIALIZED_DATABASES:
        return
    with _SCHEMA_LOCK:
        if db_key in _INITIALIZED_DATABASES:
            return
        with connect_db(settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute(_migration_sql(settings))
            connection.commit()
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


def _timestamp_value(value: str | pd.Timestamp) -> str:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        return str(value)
    return timestamp.strftime("%Y-%m-%dT%H:%M:%S")


def _placeholders(size: int) -> str:
    return ",".join(["%s"] * size)


def _job_row_to_dict(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    try:
        payload["result"] = json.loads(payload.get("result") or "{}")
    except json.JSONDecodeError:
        payload["result"] = {}
    return payload


def replace_sensors(settings: Settings, sensors: pd.DataFrame) -> None:
    ensure_schema(settings)
    frame = _normalize_frame(sensors, SENSOR_COLUMNS)
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {_table(settings, 'sensors')}")
            if not frame.empty:
                rows = [tuple(row) for row in frame.itertuples(index=False, name=None)]
                cursor.executemany(
                    f"INSERT INTO {_table(settings, 'sensors')} ({','.join(SENSOR_COLUMNS)}) VALUES ({_placeholders(len(SENSOR_COLUMNS))})",
                    rows,
                )
        connection.commit()


def replace_observations(settings: Settings, observations: pd.DataFrame) -> None:
    ensure_schema(settings)
    frame = _normalize_frame(observations, OBSERVATION_COLUMNS)
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {_table(settings, 'observations')}")
            if not frame.empty:
                rows = [tuple(row) for row in frame.itertuples(index=False, name=None)]
                cursor.executemany(
                    f"INSERT INTO {_table(settings, 'observations')} ({','.join(OBSERVATION_COLUMNS)}) VALUES ({_placeholders(len(OBSERVATION_COLUMNS))})",
                    rows,
                )
        connection.commit()


def upsert_observations(settings: Settings, observations: pd.DataFrame) -> int:
    ensure_schema(settings)
    frame = _normalize_frame(observations, OBSERVATION_COLUMNS)
    if frame.empty:
        return 0
    updates = ",".join(
        f"{column}=EXCLUDED.{column}"
        for column in OBSERVATION_COLUMNS
        if column not in {"timestamp", "sensor_id", "pollutant", "received_at"}
    )
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            rows = [tuple(row) for row in frame.itertuples(index=False, name=None)]
            cursor.executemany(
                f"""
                INSERT INTO {_table(settings, 'observations')} ({','.join(OBSERVATION_COLUMNS)})
                VALUES ({_placeholders(len(OBSERVATION_COLUMNS))})
                ON CONFLICT (timestamp, sensor_id, pollutant, received_at) DO UPDATE
                SET {updates}
                """,
                rows,
            )
        connection.commit()
    return len(frame)


def append_raw_messages(settings: Settings, rows: list[dict[str, Any]]) -> int:
    ensure_schema(settings)
    frame = _normalize_frame(pd.DataFrame(rows), RAW_MESSAGE_COLUMNS)
    if frame.empty:
        return 0
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.executemany(
                f"""
                INSERT INTO {_table(settings, 'raw_mqtt_messages')} (received_at, topic, payload)
                VALUES (%s, %s, %s)
                ON CONFLICT (received_at, topic, payload) DO NOTHING
                """,
                [tuple(row) for row in frame.itertuples(index=False, name=None)],
            )
        connection.commit()
    return len(frame)


def replace_snapshots(settings: Settings, snapshots: pd.DataFrame) -> None:
    ensure_schema(settings)
    frame = _normalize_frame(snapshots, SNAPSHOT_COLUMNS)
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"DELETE FROM {_table(settings, 'operational_snapshots')}")
            if not frame.empty:
                rows = [tuple(row) for row in frame.itertuples(index=False, name=None)]
                cursor.executemany(
                    f"INSERT INTO {_table(settings, 'operational_snapshots')} ({','.join(SNAPSHOT_COLUMNS)}) VALUES ({_placeholders(len(SNAPSHOT_COLUMNS))})",
                    rows,
                )
        connection.commit()


def read_sensors(settings: Settings) -> pd.DataFrame:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        return pd.read_sql_query(f"SELECT * FROM {_table(settings, 'sensors')} ORDER BY sensor_id", connection)


def read_observations(settings: Settings) -> pd.DataFrame:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        return pd.read_sql_query(
            f"SELECT * FROM {_table(settings, 'observations')} ORDER BY timestamp, pollutant, sensor_id, received_at",
            connection,
        )


def read_snapshots(settings: Settings) -> pd.DataFrame:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        return pd.read_sql_query(
            f"SELECT * FROM {_table(settings, 'operational_snapshots')} ORDER BY timestamp, pollutant, sensor_id, received_at",
            connection,
        )


def read_snapshot_timestamps(settings: Settings, pollutant: str) -> list[str]:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        rows = pd.read_sql_query(
            f"""
            SELECT DISTINCT timestamp
            FROM {_table(settings, 'operational_snapshots')}
            WHERE pollutant = %s AND timestamp IS NOT NULL
            ORDER BY timestamp
            """,
            connection,
            params=[pollutant],
        )
    return [str(value) for value in rows["timestamp"].tolist()] if not rows.empty else []


def read_snapshot(settings: Settings, pollutant: str, timestamp: str | pd.Timestamp) -> pd.DataFrame:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        return pd.read_sql_query(
            f"""
            SELECT *
            FROM {_table(settings, 'operational_snapshots')}
            WHERE pollutant = %s AND timestamp = %s
            ORDER BY sensor_id, received_at
            """,
            connection,
            params=[pollutant, _timestamp_value(timestamp)],
        )


def read_sensor_snapshot(settings: Settings, sensor_id: str, timestamp: str | pd.Timestamp) -> pd.DataFrame:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        return pd.read_sql_query(
            f"""
            SELECT *
            FROM {_table(settings, 'operational_snapshots')}
            WHERE sensor_id = %s AND timestamp = %s
            ORDER BY pollutant, received_at
            """,
            connection,
            params=[sensor_id, _timestamp_value(timestamp)],
        )


def read_recent_observations(settings: Settings, since_timestamp: str | None = None) -> pd.DataFrame:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        if not since_timestamp:
            return pd.read_sql_query(
                f"SELECT * FROM {_table(settings, 'observations')} ORDER BY timestamp, pollutant, sensor_id, received_at",
                connection,
            )
        return pd.read_sql_query(
            f"""
            SELECT *
            FROM {_table(settings, 'observations')}
            WHERE timestamp >= %s
            ORDER BY timestamp, pollutant, sensor_id, received_at
            """,
            connection,
            params=[since_timestamp],
        )


def read_sensor_observations(settings: Settings, sensor_id: str) -> pd.DataFrame:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        return pd.read_sql_query(
            f"""
            SELECT *
            FROM {_table(settings, 'observations')}
            WHERE sensor_id = %s
            ORDER BY timestamp, pollutant, received_at
            """,
            connection,
            params=[sensor_id],
        )


def read_sensor_timeseries(settings: Settings, pollutant: str, sensor_name: str) -> pd.DataFrame:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        return pd.read_sql_query(
            f"""
            SELECT *
            FROM {_table(settings, 'observations')}
            WHERE pollutant = %s AND sensor_name = %s
            ORDER BY timestamp, received_at
            """,
            connection,
            params=[pollutant, sensor_name],
        )


def read_raw_messages(settings: Settings) -> pd.DataFrame:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        return pd.read_sql_query(
            f"SELECT * FROM {_table(settings, 'raw_mqtt_messages')} ORDER BY received_at, topic",
            connection,
        )


def read_raw_message_count(settings: Settings) -> int:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COUNT(*) AS count FROM {_table(settings, 'raw_mqtt_messages')}")
            row = cursor.fetchone()
    return int((row or {}).get("count") or 0)


def upsert_job_run(settings: Settings, job: dict[str, Any]) -> None:
    ensure_schema(settings)
    payload = dict(job)
    payload["result"] = json.dumps(payload.get("result") or {}, ensure_ascii=False)
    frame = _normalize_frame(pd.DataFrame([payload]), JOB_RUN_COLUMNS)
    row = tuple(frame.iloc[0].tolist())
    updates = ",".join(f"{column}=EXCLUDED.{column}" for column in JOB_RUN_COLUMNS if column != "job_id")
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {_table(settings, 'job_runs')} ({','.join(JOB_RUN_COLUMNS)})
                VALUES ({_placeholders(len(JOB_RUN_COLUMNS))})
                ON CONFLICT (job_id) DO UPDATE SET {updates}
                """,
                row,
            )
        connection.commit()


def read_job_run(settings: Settings, job_id: str) -> dict[str, Any] | None:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM {_table(settings, 'job_runs')} WHERE job_id = %s", [job_id])
            return _job_row_to_dict(cursor.fetchone())


def read_job_runs(settings: Settings, limit: int = 20) -> list[dict[str, Any]]:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM {_table(settings, 'job_runs')} ORDER BY started_at DESC LIMIT %s",
                [limit],
            )
            rows = cursor.fetchall()
    return [row for row in (_job_row_to_dict(row) for row in rows) if row is not None]


def write_ingestion_run(settings: Settings, metadata: dict[str, Any], status: str = "completed") -> None:
    ensure_schema(settings)
    generated_at = str(metadata.get("generated_at") or "")
    run_id = generated_at or f"run-{len(json.dumps(metadata, sort_keys=True))}"
    details = json.dumps(metadata, ensure_ascii=False)
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {_table(settings, 'ingestion_runs')} (
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
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    started_at = EXCLUDED.started_at,
                    finished_at = EXCLUDED.finished_at,
                    status = EXCLUDED.status,
                    raw_message_rows = EXCLUDED.raw_message_rows,
                    observation_rows = EXCLUDED.observation_rows,
                    snapshot_rows = EXCLUDED.snapshot_rows,
                    sensor_rows = EXCLUDED.sensor_rows,
                    details = EXCLUDED.details
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
        connection.commit()


def write_metadata(settings: Settings, key: str, value: Any) -> None:
    ensure_schema(settings)
    serialized = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {_table(settings, 'store_metadata')} (key, value)
                VALUES (%s, %s)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                [key, serialized],
            )
        connection.commit()


def read_metadata(settings: Settings) -> dict[str, Any]:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT key, value FROM {_table(settings, 'store_metadata')}")
            rows = cursor.fetchall()
    output: dict[str, Any] = {}
    for row in rows:
        value = row["value"]
        try:
            output[row["key"]] = json.loads(value)
        except json.JSONDecodeError:
            output[row["key"]] = value
    return output


def append_operational_event(
    settings: Settings,
    event_type: str,
    payload: dict[str, Any],
    *,
    aggregate_type: str | None = None,
    aggregate_id: str | None = None,
    occurred_at: str | None = None,
) -> int:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {_table(settings, 'operational_events')} (
                    event_type,
                    aggregate_type,
                    aggregate_id,
                    occurred_at,
                    payload
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING event_id
                """,
                [
                    event_type,
                    aggregate_type,
                    aggregate_id,
                    occurred_at,
                    json.dumps(payload, ensure_ascii=False),
                ],
            )
            row = cursor.fetchone()
        connection.commit()
    return int((row or {}).get("event_id") or 0)


def read_operational_events(
    settings: Settings,
    *,
    after_event_id: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT event_id, event_type, aggregate_type, aggregate_id, occurred_at, payload
                FROM {_table(settings, 'operational_events')}
                WHERE event_id > %s
                ORDER BY event_id ASC
                LIMIT %s
                """,
                [max(after_event_id, 0), max(limit, 1)],
            )
            rows = cursor.fetchall()
    events: list[dict[str, Any]] = []
    for row in rows:
        payload = dict(row)
        try:
            payload["payload"] = json.loads(payload.get("payload") or "{}")
        except json.JSONDecodeError:
            payload["payload"] = {}
        events.append(payload)
    return events


def read_latest_event_id(settings: Settings) -> int:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT COALESCE(MAX(event_id), 0) AS event_id FROM {_table(settings, 'operational_events')}")
            row = cursor.fetchone()
    return int((row or {}).get("event_id") or 0)


def _projection_failure_row_to_dict(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    payload = dict(row)
    try:
        payload["payload"] = json.loads(payload.get("payload") or "{}")
    except json.JSONDecodeError:
        payload["payload"] = {}
    return payload


def upsert_projection_failure(settings: Settings, failure: dict[str, Any]) -> None:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO {_table(settings, 'projection_failures')} (
                    event_id,
                    event_type,
                    topic,
                    aggregate_id,
                    failed_at,
                    last_attempt_at,
                    retry_count,
                    status,
                    error,
                    payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (event_id) DO UPDATE SET
                    event_type = EXCLUDED.event_type,
                    topic = EXCLUDED.topic,
                    aggregate_id = EXCLUDED.aggregate_id,
                    failed_at = EXCLUDED.failed_at,
                    last_attempt_at = EXCLUDED.last_attempt_at,
                    retry_count = EXCLUDED.retry_count,
                    status = EXCLUDED.status,
                    error = EXCLUDED.error,
                    payload = EXCLUDED.payload
                """,
                [
                    int(failure.get("event_id") or 0),
                    str(failure.get("event_type") or ""),
                    str(failure.get("topic") or ""),
                    str(failure.get("aggregate_id") or ""),
                    str(failure.get("failed_at") or ""),
                    str(failure.get("last_attempt_at") or ""),
                    int(failure.get("retry_count") or 0),
                    str(failure.get("status") or "retrying"),
                    str(failure.get("error") or ""),
                    json.dumps(failure.get("payload") or {}, ensure_ascii=False),
                ],
            )
        connection.commit()


def read_projection_failure(settings: Settings, event_id: int) -> dict[str, Any] | None:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT * FROM {_table(settings, 'projection_failures')} WHERE event_id = %s",
                [int(event_id)],
            )
            row = cursor.fetchone()
    return _projection_failure_row_to_dict(row)


def delete_projection_failure(settings: Settings, event_id: int) -> None:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {_table(settings, 'projection_failures')} WHERE event_id = %s",
                [int(event_id)],
            )
        connection.commit()


def read_projection_failures(
    settings: Settings,
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    ensure_schema(settings)
    query = f"SELECT * FROM {_table(settings, 'projection_failures')}"
    params: list[Any] = []
    if status:
        query += " WHERE status = %s"
        params.append(status)
    query += " ORDER BY last_attempt_at DESC LIMIT %s"
    params.append(max(limit, 1))
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall()
    return [_projection_failure_row_to_dict(row) or {} for row in rows]


def read_projection_failure_summary(settings: Settings) -> dict[str, Any]:
    ensure_schema(settings)
    with connect_db(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT status, COUNT(*) AS total, MAX(last_attempt_at) AS last_attempt_at
                FROM {_table(settings, 'projection_failures')}
                GROUP BY status
                """
            )
            rows = cursor.fetchall()
    counts = {str(row["status"]): int(row["total"] or 0) for row in rows}
    latest_attempt = max((str(row["last_attempt_at"] or "") for row in rows), default="") or None
    return {
        "active": sum(counts.values()),
        "retrying": counts.get("retrying", 0),
        "dead_lettered": counts.get("dead_lettered", 0),
        "last_attempt_at": latest_attempt,
    }


class PostgresOperationalStore(OperationalStore):
    def backend_name(self) -> str:
        return "postgres"

    def database_path(self, settings: Settings) -> str:
        return database_path(settings)

    def connect_db(self, settings: Settings) -> Any:
        return connect_db(settings)

    def ensure_schema(self, settings: Settings) -> None:
        ensure_schema(settings)

    def replace_sensors(self, settings: Settings, sensors: pd.DataFrame) -> None:
        replace_sensors(settings, sensors)

    def replace_observations(self, settings: Settings, observations: pd.DataFrame) -> None:
        replace_observations(settings, observations)

    def upsert_observations(self, settings: Settings, observations: pd.DataFrame) -> int:
        return upsert_observations(settings, observations)

    def append_raw_messages(self, settings: Settings, rows: list[dict[str, Any]]) -> int:
        return append_raw_messages(settings, rows)

    def replace_snapshots(self, settings: Settings, snapshots: pd.DataFrame) -> None:
        replace_snapshots(settings, snapshots)

    def read_sensors(self, settings: Settings) -> pd.DataFrame:
        return read_sensors(settings)

    def read_observations(self, settings: Settings) -> pd.DataFrame:
        return read_observations(settings)

    def read_snapshots(self, settings: Settings) -> pd.DataFrame:
        return read_snapshots(settings)

    def read_snapshot_timestamps(self, settings: Settings, pollutant: str) -> list[str]:
        return read_snapshot_timestamps(settings, pollutant)

    def read_snapshot(self, settings: Settings, pollutant: str, timestamp: str | pd.Timestamp) -> pd.DataFrame:
        return read_snapshot(settings, pollutant, timestamp)

    def read_sensor_snapshot(self, settings: Settings, sensor_id: str, timestamp: str | pd.Timestamp) -> pd.DataFrame:
        return read_sensor_snapshot(settings, sensor_id, timestamp)

    def read_recent_observations(self, settings: Settings, since_timestamp: str | None = None) -> pd.DataFrame:
        return read_recent_observations(settings, since_timestamp)

    def read_sensor_observations(self, settings: Settings, sensor_id: str) -> pd.DataFrame:
        return read_sensor_observations(settings, sensor_id)

    def read_sensor_timeseries(self, settings: Settings, pollutant: str, sensor_name: str) -> pd.DataFrame:
        return read_sensor_timeseries(settings, pollutant, sensor_name)

    def read_raw_messages(self, settings: Settings) -> pd.DataFrame:
        return read_raw_messages(settings)

    def read_raw_message_count(self, settings: Settings) -> int:
        return read_raw_message_count(settings)

    def upsert_job_run(self, settings: Settings, job: dict[str, Any]) -> None:
        upsert_job_run(settings, job)

    def read_job_run(self, settings: Settings, job_id: str) -> dict[str, Any] | None:
        return read_job_run(settings, job_id)

    def read_job_runs(self, settings: Settings, limit: int = 20) -> list[dict[str, Any]]:
        return read_job_runs(settings, limit)

    def write_ingestion_run(self, settings: Settings, metadata: dict[str, Any], status: str = "completed") -> None:
        write_ingestion_run(settings, metadata, status=status)

    def write_metadata(self, settings: Settings, key: str, value: Any) -> None:
        write_metadata(settings, key, value)

    def read_metadata(self, settings: Settings) -> dict[str, Any]:
        return read_metadata(settings)

    def append_operational_event(
        self,
        settings: Settings,
        event_type: str,
        payload: dict[str, Any],
        *,
        aggregate_type: str | None = None,
        aggregate_id: str | None = None,
        occurred_at: str | None = None,
    ) -> int:
        return append_operational_event(
            settings,
            event_type,
            payload,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            occurred_at=occurred_at,
        )

    def read_operational_events(
        self,
        settings: Settings,
        *,
        after_event_id: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return read_operational_events(settings, after_event_id=after_event_id, limit=limit)

    def read_latest_event_id(self, settings: Settings) -> int:
        return read_latest_event_id(settings)

    def upsert_projection_failure(self, settings: Settings, failure: dict[str, Any]) -> None:
        upsert_projection_failure(settings, failure)

    def read_projection_failure(self, settings: Settings, event_id: int) -> dict[str, Any] | None:
        return read_projection_failure(settings, event_id)

    def delete_projection_failure(self, settings: Settings, event_id: int) -> None:
        delete_projection_failure(settings, event_id)

    def read_projection_failures(
        self,
        settings: Settings,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return read_projection_failures(settings, status=status, limit=limit)

    def read_projection_failure_summary(self, settings: Settings) -> dict[str, Any]:
        return read_projection_failure_summary(settings)
