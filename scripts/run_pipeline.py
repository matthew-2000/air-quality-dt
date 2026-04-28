from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unisa_air_twin.arpac import clean_air_quality, download_arpac
from unisa_air_twin.config import load_settings
from unisa_air_twin.model import estimate_campus_air_quality
from unisa_air_twin.osm import download_osm
from unisa_air_twin.sensors import create_virtual_sensors
from unisa_air_twin.validation import leave_one_station_out_validation
from unisa_air_twin.weather import download_weather
from unisa_air_twin.zones import ensure_twin_layers


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full UNISA Air Quality Digital Twin MVP pipeline.")
    parser.add_argument("--force", action="store_true", help="Redownload raw files even if cached.")
    parser.add_argument("--months", type=int, default=None, help="CSV resources per ARPAC dataset to download.")
    args = parser.parse_args()

    settings = load_settings()
    print("1/5 Downloading ARPAC data...")
    download_arpac(settings, force=args.force, months=args.months)
    print("2/5 Downloading weather data...")
    download_weather(settings, force=args.force)
    print("3/5 Downloading OSM campus layers and creating virtual sensors...")
    download_osm(settings, force=args.force)
    create_virtual_sensors(settings)
    ensure_twin_layers(settings)
    print("4/6 Cleaning ARPAC datasets...")
    observations = clean_air_quality(settings)
    print(f"   Air-quality rows available: {len(observations):,}")
    print("5/6 Estimating campus air quality...")
    estimates = estimate_campus_air_quality(settings)
    print(f"   Campus estimate rows available: {len(estimates):,}")
    print("6/6 Validating open-data model against ARPAC stations...")
    validation = leave_one_station_out_validation(settings)
    print(f"   Validation rows available: {len(validation):,}")
    print("Pipeline complete. Run: streamlit run app/streamlit_app.py")


if __name__ == "__main__":
    main()
