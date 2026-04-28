from __future__ import annotations

import pandas as pd

from unisa_air_twin.utils import first_existing_column, normalize_column_name, normalize_columns


def test_column_normalization_handles_accents_spaces_and_pollutants() -> None:
    assert normalize_column_name("Biossido di Azoto") == "biossido_di_azoto"
    assert normalize_column_name("PM2.5") == "pm25"
    assert normalize_column_name(" Data Misura ") == "data_misura"


def test_first_existing_column_uses_normalized_candidates() -> None:
    df = normalize_columns(pd.DataFrame({"Data Misura": ["2026-01-01"], "PM2.5": [10]}))
    assert first_existing_column(df.columns, ["timestamp", "data_misura"]) == "data_misura"
    assert first_existing_column(df.columns, ["pm_2_5", "pm25"]) == "pm25"

