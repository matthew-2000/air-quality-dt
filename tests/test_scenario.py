from __future__ import annotations

import pandas as pd

from unisa_air_twin.config import load_settings
from unisa_air_twin.scenario import apply_scenario


def test_scenario_traffic_reduction_lowers_no2() -> None:
    settings = load_settings()
    estimates = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-04-27 08:00"),
                "sensor_id": "UNISA_TERMINAL_BUS",
                "sensor_name": "Terminal Bus",
                "pollutant": "no2",
                "estimated_value": 50.0,
                "traffic_index": 1.0,
                "wind_speed_10m": 2.0,
                "precipitation": 0.0,
            }
        ]
    )
    scenario = apply_scenario(estimates, settings, traffic_reduction=0.5)
    assert scenario.loc[0, "scenario_value"] == 46.0
    assert scenario.loc[0, "delta"] == -4.0


def test_scenario_rain_reduces_pm10() -> None:
    settings = load_settings()
    estimates = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-04-27 08:00"),
                "sensor_id": "UNISA_A1_RETTORATO",
                "sensor_name": "Rettorato",
                "pollutant": "pm10",
                "estimated_value": 30.0,
                "traffic_index": 0.0,
                "wind_speed_10m": 2.0,
                "precipitation": 0.0,
            }
        ]
    )
    scenario = apply_scenario(estimates, settings, rain_event=True)
    assert scenario.loc[0, "scenario_value"] == 27.0


def test_scenario_focus_zone_changes_selected_zone_more() -> None:
    settings = load_settings()
    estimates = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-04-27 08:00"),
                "sensor_id": "UNISA_TERMINAL_BUS",
                "sensor_name": "Terminal Bus",
                "zone": "mobilita",
                "pollutant": "no2",
                "estimated_value": 50.0,
                "traffic_index": 1.0,
                "wind_speed_10m": 2.0,
                "precipitation": 0.0,
            },
            {
                "timestamp": pd.Timestamp("2026-04-27 08:00"),
                "sensor_id": "UNISA_AREA_VERDE",
                "sensor_name": "Area verde",
                "zone": "verde",
                "pollutant": "no2",
                "estimated_value": 40.0,
                "traffic_index": 1.0,
                "wind_speed_10m": 2.0,
                "precipitation": 0.0,
            },
        ]
    )
    scenario = apply_scenario(estimates, settings, traffic_reduction=0.5, focus_zone="mobilita")
    assert scenario.loc[0, "delta"] < scenario.loc[1, "delta"]
