from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from energytwin.adapters.nasa_power import (  # noqa: E402
    NasaPowerRequest,
    fetch_nasa_power_json,
    nasa_power_json_to_enrichment_rows,
    write_enrichment_csv,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch NASA POWER hourly weather and write an Energy Twin enrichment CSV.")
    parser.add_argument("--latitude", type=float, required=True)
    parser.add_argument("--longitude", type=float, required=True)
    parser.add_argument("--start", required=True, help="Start date as YYYYMMDD.")
    parser.add_argument("--end", required=True, help="End date as YYYYMMDD.")
    parser.add_argument("--solar-kwp", type=float, default=260.0, help="Installed solar capacity used to estimate solar_kw.")
    parser.add_argument("--performance-ratio", type=float, default=0.82)
    parser.add_argument("--time-standard", choices=("UTC", "LST"), default="UTC")
    parser.add_argument("--output", default="data/raw/nasa-power-enrichment.csv")
    parser.add_argument("--from-json", help="Use a local NASA POWER JSON response instead of fetching.")
    args = parser.parse_args()

    if args.from_json:
        payload = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
    else:
        payload = fetch_nasa_power_json(
            NasaPowerRequest(
                latitude=args.latitude,
                longitude=args.longitude,
                start=args.start,
                end=args.end,
                time_standard=args.time_standard,
            )
        )

    rows = nasa_power_json_to_enrichment_rows(payload, solar_kwp=args.solar_kwp, performance_ratio=args.performance_ratio)
    output = write_enrichment_csv(args.output, rows)
    print(f"wrote {output}")
    print(f"rows={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
