from __future__ import annotations

import pandas as pd

from unisa_air_twin.config import load_settings
from unisa_air_twin.model import estimate_campus_air_quality, estimate_spatial_uncertainty, idw_interpolation, traffic_index


def test_traffic_index_by_hour_and_day() -> None:
    assert traffic_index(pd.Timestamp("2026-04-27 08:00"), "UNISA_A1_RETTORATO") == 1.0
    assert traffic_index(pd.Timestamp("2026-04-27 12:00"), "UNISA_A1_RETTORATO") == 0.55
    assert traffic_index(pd.Timestamp("2026-04-26 08:00"), "UNISA_A1_RETTORATO") == 0.2
    assert traffic_index(pd.Timestamp("2026-04-27 12:00"), "UNISA_TERMINAL_BUS") == 0.7


def test_idw_interpolation_returns_sensible_values() -> None:
    value = idw_interpolation([10.0, 30.0], [1.0, 3.0], power=2.0)
    assert 10.0 < value < 20.0
    assert idw_interpolation([42.0, 10.0], [0.0, 5.0], power=2.0) == 42.0


def test_spatial_uncertainty_increases_for_synthetic_or_sparse_data() -> None:
    open_score, open_label = estimate_spatial_uncertainty([2.0, 5.0, 8.0], 3, is_synthetic=False, radius_km=40)
    synthetic_score, synthetic_label = estimate_spatial_uncertainty([2.0, 5.0, 8.0], 3, is_synthetic=True, radius_km=40)
    sparse_score, sparse_label = estimate_spatial_uncertainty([35.0], 1, is_synthetic=False, radius_km=40)
    assert open_score < synthetic_score
    assert sparse_score > open_score
    assert open_label in {"alta", "media", "bassa"}
    assert synthetic_label in {"alta", "media", "bassa"}
    assert sparse_label in {"alta", "media", "bassa"}


def test_model_handles_missing_pollutant_columns_gracefully(tmp_path) -> None:
    settings = load_settings()
    settings.raw_dir = tmp_path / "raw"
    settings.processed_dir = tmp_path / "processed"
    settings.raw_dir.mkdir()
    settings.processed_dir.mkdir()
    pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-04-27", periods=2, freq="h"),
            "station_id": ["S1", "S1"],
            "station_name": ["Station", "Station"],
            "source": ["test", "test"],
            "source_url": ["", ""],
            "downloaded_at": ["now", "now"],
            "is_synthetic": [False, False],
        }
    ).to_csv(settings.processed_dir / "air_quality_observations.csv", index=False)
    estimates = estimate_campus_air_quality(settings)
    assert not estimates.empty
    assert set(estimates["pollutant"]).issuperset({"pm10", "no2"})
    assert estimates["is_synthetic"].any()
