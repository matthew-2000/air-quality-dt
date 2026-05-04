from __future__ import annotations

import pandas as pd

from unisa_air_twin.analytics import analytics_payload, zone_summary


def _zones() -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[[14.0, 40.0], [15.0, 40.0], [15.0, 41.0], [14.0, 41.0], [14.0, 40.0]]]},
                "properties": {"zone": "didattica", "name": "Didattica", "traffic_sensitivity": 0.4, "green_capacity": 0.5},
            }
        ],
    }


def test_zone_summary_assigns_points_to_campus_zones() -> None:
    snapshot = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-05-04 14:00:00"),
                "received_at": pd.Timestamp("2026-05-04 14:00:01"),
                "sensor_id": "A",
                "lat": 40.5,
                "lon": 14.5,
                "pollutant": "pm10",
                "estimated_value": 12.0,
                "temperature": 20.0,
                "humidity": 40.0,
            }
        ]
    )

    summary = zone_summary(snapshot, _zones())

    assert summary["zone"].iloc[0] == "didattica"
    assert summary["zone_name"].iloc[0] == "Didattica"
    assert summary["sensors"].iloc[0] == 1


def test_analytics_payload_includes_quality_zone_and_trend() -> None:
    observations = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-05-04 14:00:00"),
                "received_at": pd.Timestamp("2026-05-04 14:00:01"),
                "sensor_id": "A",
                "lat": 40.5,
                "lon": 14.5,
                "pollutant": "pm10",
                "estimated_value": 12.0,
                "temperature": 20.0,
                "humidity": 40.0,
            }
        ]
    )
    estimates = observations.copy()

    payload = analytics_payload(observations, estimates, _zones(), "pm10", "2026-05-04T14:00:00")

    assert payload["quality"]["rows"] == 1
    assert payload["zone_summary"][0]["zone"] == "didattica"
    assert payload["trend"][0]["mean_value"] == 12.0
