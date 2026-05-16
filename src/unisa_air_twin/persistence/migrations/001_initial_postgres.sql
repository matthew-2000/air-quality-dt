CREATE SCHEMA IF NOT EXISTS "__AQDT_SCHEMA__";

CREATE TABLE IF NOT EXISTS "__AQDT_SCHEMA__".sensors (
    sensor_id TEXT PRIMARY KEY,
    name TEXT,
    type TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    zone TEXT,
    description TEXT,
    coordinate_quality TEXT,
    source TEXT,
    source_url TEXT,
    downloaded_at TEXT,
    is_real BOOLEAN
);

CREATE TABLE IF NOT EXISTS "__AQDT_SCHEMA__".raw_mqtt_messages (
    received_at TEXT NOT NULL,
    topic TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (received_at, topic, payload)
);

CREATE TABLE IF NOT EXISTS "__AQDT_SCHEMA__".observations (
    timestamp TEXT NOT NULL,
    received_at TEXT NOT NULL,
    sensor_id TEXT NOT NULL,
    sensor_name TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    zone TEXT,
    pollutant TEXT NOT NULL,
    base_value DOUBLE PRECISION,
    estimated_value DOUBLE PRECISION,
    temperature DOUBLE PRECISION,
    humidity DOUBLE PRECISION,
    num_devices_sniffed INTEGER,
    traffic_index DOUBLE PRECISION,
    green_index DOUBLE PRECISION,
    wind_speed_10m DOUBLE PRECISION,
    precipitation DOUBLE PRECISION,
    traffic_component DOUBLE PRECISION,
    green_component DOUBLE PRECISION,
    wind_component DOUBLE PRECISION,
    rain_component DOUBLE PRECISION,
    background_value DOUBLE PRECISION,
    background_source TEXT,
    station_count INTEGER,
    nearest_station_km DOUBLE PRECISION,
    mean_station_distance_km DOUBLE PRECISION,
    uncertainty_score DOUBLE PRECISION,
    confidence_label TEXT,
    source TEXT,
    source_url TEXT,
    downloaded_at TEXT,
    is_real BOOLEAN,
    PRIMARY KEY (timestamp, sensor_id, pollutant, received_at)
);

CREATE INDEX IF NOT EXISTS idx_observations_pollutant_timestamp
ON "__AQDT_SCHEMA__".observations (pollutant, timestamp);

CREATE INDEX IF NOT EXISTS idx_observations_sensor_timestamp
ON "__AQDT_SCHEMA__".observations (sensor_id, timestamp);

CREATE TABLE IF NOT EXISTS "__AQDT_SCHEMA__".operational_snapshots (
    timestamp TEXT NOT NULL,
    received_at TEXT NOT NULL,
    sensor_id TEXT NOT NULL,
    sensor_name TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    zone TEXT,
    pollutant TEXT NOT NULL,
    base_value DOUBLE PRECISION,
    estimated_value DOUBLE PRECISION,
    temperature DOUBLE PRECISION,
    humidity DOUBLE PRECISION,
    num_devices_sniffed INTEGER,
    traffic_index DOUBLE PRECISION,
    green_index DOUBLE PRECISION,
    wind_speed_10m DOUBLE PRECISION,
    precipitation DOUBLE PRECISION,
    traffic_component DOUBLE PRECISION,
    green_component DOUBLE PRECISION,
    wind_component DOUBLE PRECISION,
    rain_component DOUBLE PRECISION,
    background_value DOUBLE PRECISION,
    background_source TEXT,
    station_count INTEGER,
    nearest_station_km DOUBLE PRECISION,
    mean_station_distance_km DOUBLE PRECISION,
    uncertainty_score DOUBLE PRECISION,
    confidence_label TEXT,
    source TEXT,
    source_url TEXT,
    downloaded_at TEXT,
    is_real BOOLEAN,
    measured_at TEXT,
    reading_age_seconds INTEGER,
    snapshot_bucket_minutes INTEGER,
    snapshot_freshness_minutes INTEGER,
    capable_sensor_count INTEGER,
    coverage_ratio DOUBLE PRECISION,
    PRIMARY KEY (timestamp, sensor_id, pollutant, received_at)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_pollutant_timestamp
ON "__AQDT_SCHEMA__".operational_snapshots (pollutant, timestamp);

CREATE INDEX IF NOT EXISTS idx_snapshots_sensor_timestamp
ON "__AQDT_SCHEMA__".operational_snapshots (sensor_id, timestamp);

CREATE TABLE IF NOT EXISTS "__AQDT_SCHEMA__".store_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS "__AQDT_SCHEMA__".ingestion_runs (
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

CREATE TABLE IF NOT EXISTS "__AQDT_SCHEMA__".operational_events (
    event_id BIGSERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    aggregate_type TEXT,
    aggregate_id TEXT,
    occurred_at TEXT,
    payload TEXT NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_operational_events_type_id
ON "__AQDT_SCHEMA__".operational_events (event_type, event_id DESC);

CREATE TABLE IF NOT EXISTS "__AQDT_SCHEMA__".job_runs (
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
ON "__AQDT_SCHEMA__".job_runs (started_at DESC);

INSERT INTO "__AQDT_SCHEMA__".store_metadata (key, value)
VALUES ('schema_version', '1')
ON CONFLICT (key) DO NOTHING;
