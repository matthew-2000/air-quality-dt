from __future__ import annotations

import pandas as pd

from unisa_air_twin.gis import (
    build_interpolation_grid,
    build_reliability_grid,
    color_zone_geojson,
    sensor_snapshot,
    timestamp_window,
    zone_delta_summary,
)


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


def test_reliability_grid_is_bounded() -> None:
    sensors = pd.DataFrame(
        [
            {"sensor_id": "a", "lat": 40.771, "lon": 14.790},
            {"sensor_id": "b", "lat": 40.775, "lon": 14.795},
        ]
    )
    grid = build_reliability_grid(sensors, resolution=4)
    assert len(grid) == 16
    assert grid["reliability"].between(0.0, 1.0).all()


def test_zone_delta_summary_and_geojson_coloring() -> None:
    scenario = pd.DataFrame(
        [
            {"sensor_id": "a", "zone": "mobilita", "delta": -2.0},
            {"sensor_id": "b", "zone": "mobilita", "delta": -1.0},
            {"sensor_id": "c", "zone": "verde", "delta": 0.5},
        ]
    )
    summary = zone_delta_summary(scenario)
    assert summary.loc[summary["zone"] == "mobilita", "mean_delta"].iloc[0] == -1.5
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": None, "properties": {"zone": "mobilita"}},
            {"type": "Feature", "geometry": None, "properties": {"zone": "verde"}},
        ],
    }
    colored = color_zone_geojson(geojson, summary, "mean_delta")
    assert all("fill_color" in feature["properties"] for feature in colored["features"])


def test_timestamp_window_selects_day_parts() -> None:
    timestamps = list(pd.date_range("2026-04-27 07:00", periods=14, freq="h"))
    selected = pd.Timestamp("2026-04-27 09:00")
    morning = timestamp_window(timestamps, selected, "Mattina")
    assert [ts.hour for ts in morning] == [8, 9, 10]
