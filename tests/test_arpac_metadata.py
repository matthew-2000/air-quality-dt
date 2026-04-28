from __future__ import annotations

from pathlib import Path

import pandas as pd

from unisa_air_twin.arpac import _clean_single_observation_file, _read_station_metadata_file


def test_station_metadata_reader_preserves_address_commas(tmp_path) -> None:
    metadata = tmp_path / "metadati.csv"
    metadata.write_text(
        "\n".join(
            [
                "Rete,Zona,Nome Stazione,Codice Europeo,Codice Nazionale ,Codice Arpac,Provincia,indirizzo,Tipo,Latitudine,Longitudine,Slm",
                "RRMQA,IT1507,Acerra scuola Caporale,IT2219A,1506370,IT2219A,Napoli,Acerra - P.za Falcone, Via Carlo Petrella,TRAFFICO,40.94046,14.37019,27",
            ]
        ),
        encoding="utf-8",
    )

    frame = _read_station_metadata_file(Path(metadata))

    assert frame.loc[0, "codice_europeo"] == "IT2219A"
    assert frame.loc[0, "indirizzo"] == "Acerra - P.za Falcone, Via Carlo Petrella"
    assert frame.loc[0, "latitudine"] == "40.94046"
    assert frame.loc[0, "longitudine"] == "14.37019"


def test_observation_cleaner_drops_implausible_pollutant_values(tmp_path) -> None:
    observations = tmp_path / "observations.csv"
    observations.write_text(
        "\n".join(
            [
                "data,stazione,pm10,no2,o3",
                "2026-04-27 08:00,IT2219A,42,9999,-1",
            ]
        ),
        encoding="utf-8",
    )

    frame, warnings = _clean_single_observation_file(observations)

    assert not warnings
    assert frame.loc[0, "pm10"] == 42
    assert pd.isna(frame.loc[0, "no2"])
    assert pd.isna(frame.loc[0, "o3"])
