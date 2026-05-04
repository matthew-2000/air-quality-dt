from __future__ import annotations

import pandas as pd

from unisa_air_twin.data_quality import annotate_quality, quality_summary


def test_quality_flags_capture_missing_context_and_latency() -> None:
    frame = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-05-04 14:00:00"),
                "received_at": pd.Timestamp("2026-05-04 14:08:00"),
                "pollutant": "pm10",
                "estimated_value": 10.0,
                "temperature": None,
                "humidity": 40.0,
            }
        ]
    )

    annotated = annotate_quality(frame)

    assert annotated["quality_label"].iloc[0] == "watch"
    assert "late_arrival" in annotated["quality_flags"].iloc[0]
    assert "missing_temperature" in annotated["quality_flags"].iloc[0]


def test_quality_summary_counts_critical_rows() -> None:
    frame = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-05-04 14:00:00"),
                "received_at": pd.Timestamp("2026-05-04 14:00:01"),
                "pollutant": "pm10",
                "estimated_value": -1.0,
                "temperature": 20.0,
                "humidity": 40.0,
            }
        ]
    )

    summary = quality_summary(annotate_quality(frame))

    assert summary["critical_rows"] == 1
    assert summary["flags"][0]["flag"] == "outside_operational_range"
