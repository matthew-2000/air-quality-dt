from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unisa_air_twin.arpac import clean_air_quality
from unisa_air_twin.config import load_settings
from unisa_air_twin.model import estimate_campus_air_quality


def main() -> None:
    settings = load_settings()
    clean_air_quality(settings)
    estimates = estimate_campus_air_quality(settings)
    print(f"Created {len(estimates):,} campus air-quality estimate rows.")


if __name__ == "__main__":
    main()

