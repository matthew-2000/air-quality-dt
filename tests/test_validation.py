from __future__ import annotations

import pandas as pd

from unisa_air_twin.config import load_settings
from unisa_air_twin.storage import write_table
from unisa_air_twin.validation import leave_one_station_out_validation, summarize_validation


def test_leave_one_station_out_validation_creates_error_metrics(tmp_path) -> None:
    settings = load_settings()
    settings.raw_dir = tmp_path / "raw"
    settings.processed_dir = tmp_path / "processed"
    settings.raw_dir.mkdir()
    settings.processed_dir.mkdir()
    write_table(
        pd.DataFrame(
            {
                "timestamp": [pd.Timestamp("2026-04-27 08:00")] * 3,
                "station_id": ["S1", "S2", "S3"],
                "station_name": ["Station 1", "Station 2", "Station 3"],
                "pm10": [10.0, 20.0, 30.0],
                "no2": [40.0, 42.0, 44.0],
                "source": ["arpac"] * 3,
                "source_url": [""] * 3,
                "downloaded_at": ["now"] * 3,
                "is_synthetic": [False] * 3,
            }
        ),
        settings.processed_dir / "air_quality_observations.parquet",
    )
    write_table(
        pd.DataFrame(
            {
                "station_id": ["S1", "S2", "S3"],
                "station_name": ["Station 1", "Station 2", "Station 3"],
                "lat": [40.0, 40.1, 40.2],
                "lon": [14.0, 14.1, 14.2],
            }
        ),
        settings.processed_dir / "arpac_station_metadata.parquet",
    )

    validation = leave_one_station_out_validation(settings)
    summary = summarize_validation(validation)

    assert not validation.empty
    assert {"observed", "predicted", "error", "absolute_error"}.issubset(validation.columns)
    assert summary["rows"] == len(validation)
    assert summary["overall"]["mae"] is not None
