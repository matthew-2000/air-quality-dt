from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unisa_air_twin.config import load_settings
from unisa_air_twin.product_jobs import prepare_context_layers, rebuild_operational_dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the UNISA real-sensor pipeline.")
    parser.add_argument("--force", action="store_true", help="Redownload OSM layers even if cached.")
    args = parser.parse_args()

    settings = load_settings()
    print("1/3 Downloading OSM campus layers and preparing real sensors...")
    context = prepare_context_layers(settings, force=args.force)
    print(f"   Sensors: {context['sensors']:,} · layers: {context['layers']}")
    print("2/3 Building observations from UNISA MQTT exports...")
    result = rebuild_operational_dataset(settings)
    print(f"   Snapshot rows available: {result['snapshot_rows']:,}")
    print("3/3 Pipeline complete. Start the cockpit with `make dev`.")


if __name__ == "__main__":
    main()
