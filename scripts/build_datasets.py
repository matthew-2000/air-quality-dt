from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unisa_air_twin.config import load_settings
from unisa_air_twin.product_jobs import rebuild_operational_dataset


def main() -> None:
    settings = load_settings()
    result = rebuild_operational_dataset(settings)
    print(f"Created {result['snapshot_rows']:,} operational snapshot rows from real UNISA sensors.")


if __name__ == "__main__":
    main()
