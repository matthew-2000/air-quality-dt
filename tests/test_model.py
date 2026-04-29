from __future__ import annotations

import pandas as pd

from unisa_air_twin.model import (
    estimate_spatial_uncertainty,
    idw_interpolation,
    traffic_index,
)


def test_traffic_index_by_hour_and_day() -> None:
    assert traffic_index(pd.Timestamp("2026-04-27 08:00")) == 1.0
    assert traffic_index(pd.Timestamp("2026-04-27 12:00")) == 0.55
    assert traffic_index(pd.Timestamp("2026-04-26 08:00")) == 0.2
    assert traffic_index(pd.Timestamp("2026-04-27 12:00"), devices_sniffed=40) == 0.5


def test_idw_interpolation_returns_sensible_values() -> None:
    value = idw_interpolation([10.0, 30.0], [1.0, 3.0], power=2.0)
    assert 10.0 < value < 20.0
    assert idw_interpolation([42.0, 10.0], [0.0, 5.0], power=2.0) == 42.0


def test_spatial_uncertainty_increases_for_sparse_data() -> None:
    open_score, open_label = estimate_spatial_uncertainty([2.0, 5.0, 8.0], 3, radius_km=40)
    sparse_score, sparse_label = estimate_spatial_uncertainty([35.0], 1, radius_km=40)
    assert sparse_score > open_score
    assert open_label in {"alta", "media", "bassa"}
    assert sparse_label in {"alta", "media", "bassa"}
