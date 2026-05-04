from __future__ import annotations

import json

from unisa_air_twin.config import load_settings
from unisa_air_twin.ui_data import TwinDataService


def test_summary_read_path_does_not_rebuild_operational_artifacts(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    raw_dir.mkdir()
    processed_dir.mkdir()
    metadata_path = raw_dir / "sensor_catalog.json"
    metadata_path.write_text(
        json.dumps([{"ID": "ITTEST123456", "lat": 40.771, "lon": 14.79}]),
        encoding="utf-8",
    )

    settings = load_settings()
    settings.raw_dir = raw_dir
    settings.processed_dir = processed_dir
    settings.live_sensors["raw"] = {
        "sensor_metadata_path": str(metadata_path),
        "mqtt_csv_path": str(raw_dir / "missing.csv"),
        "mqtt_jsonl_path": str(raw_dir / "missing.jsonl"),
    }

    summary = TwinDataService(settings).summary()

    assert summary["sensors"] == 1
    assert summary["rows"] == 0
    assert summary["raw_message_rows"] == 0
    assert summary["observation_rows"] == 0
    assert summary["pollutants"] == []
    assert not (processed_dir / "campus_air_quality_estimates.parquet").exists()
