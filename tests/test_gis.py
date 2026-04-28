from __future__ import annotations

import pandas as pd

from unisa_air_twin.gis import build_interpolation_grid, sensor_snapshot


def test_interpolation_grid_has_cells_and_values() -> None:
    sensors = pd.DataFrame(
        [
            {"sensor_id": "a", "lat": 40.771, "lon": 14.790, "estimated_value": 10.0},
            {"sensor_id": "b", "lat": 40.775, "lon": 14.795, "estimated_value": 20.0},
        ]
    )
    grid = build_interpolation_grid(sensors, resolution=6)
    assert len(grid) == 36
    assert grid["estimated_value"].between(10.0, 20.0).all()
    assert grid["polygon"].map(len).eq(4).all()


def test_sensor_snapshot_filters_pollutant_and_timestamp() -> None:
    estimates = pd.DataFrame(
        [
            {"timestamp": pd.Timestamp("2026-04-27 08:00"), "pollutant": "pm10", "estimated_value": 12},
            {"timestamp": pd.Timestamp("2026-04-27 09:00"), "pollutant": "pm10", "estimated_value": 14},
            {"timestamp": pd.Timestamp("2026-04-27 08:00"), "pollutant": "no2", "estimated_value": 20},
        ]
    )
    snapshot = sensor_snapshot(estimates, "pm10", pd.Timestamp("2026-04-27 08:00"))
    assert len(snapshot) == 1
    assert snapshot.iloc[0]["estimated_value"] == 12
