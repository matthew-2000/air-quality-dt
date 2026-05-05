from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unisa_air_twin.config import load_settings
from unisa_air_twin.product_jobs import prepare_context_layers


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare GIS layers and real UNISA sensor metadata.")
    parser.add_argument("--force", action="store_true", help="Redownload OSM layers even if cached.")
    args = parser.parse_args()

    settings = load_settings()
    result = prepare_context_layers(settings, force=args.force)
    print(f"Prepared {result['sensors']:,} sensors and context layers: {result['layers']}")


if __name__ == "__main__":
    main()
