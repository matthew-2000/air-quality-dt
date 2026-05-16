from __future__ import annotations

SOURCE_NAME = "unisa_live_mqtt"
SOURCE_URL = "configured_mqtt_broker"

POLLUTANT_FIELDS = {
    "pm1": "pm1",
    "pm2_5": "pm25",
    "pm2.5": "pm25",
    "pm25": "pm25",
    "pm10": "pm10",
    "voc_index": "voc_index",
    "nox_index": "nox_index",
}

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
