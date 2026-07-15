from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from energytwin.public_pipeline import PublicDatasetConfig, prepare_public_dataset  # noqa: E402
from energytwin.sources import PROCESSED_CURRENT  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a local public building dataset for EnergyTwin.")
    parser.add_argument("input", help="Local public meter CSV, usually under data/raw.")
    parser.add_argument("--format", choices=("bdg-wide", "bdg-long"), required=True)
    parser.add_argument("--output", default=str(PROCESSED_CURRENT))
    parser.add_argument("--timestamp-column", default="timestamp")
    parser.add_argument("--building-column", help="Building meter column for bdg-wide format.")
    parser.add_argument("--building-id", help="Building id value for bdg-long format.")
    parser.add_argument("--building-id-column", default="building_id")
    parser.add_argument("--meter-column", default="meter_reading")
    parser.add_argument("--default-temp-c", type=float, default=22.0)
    parser.add_argument("--default-price", type=float, default=0.18)
    parser.add_argument("--default-carbon", type=float, default=0.38)
    parser.add_argument("--default-solar", type=float, default=0.0)
    parser.add_argument("--enrichment-csv", help="Optional weather/solar/price/carbon enrichment CSV.")
    parser.add_argument("--enrichment-timestamp-column", default="timestamp")
    parser.add_argument("--require-enrichment-match", action="store_true")
    args = parser.parse_args()

    try:
        summary = prepare_public_dataset(
            PublicDatasetConfig(
                input_path=args.input,
                input_format=args.format,
                output_path=args.output,
                timestamp_column=args.timestamp_column,
                building_column=args.building_column,
                building_id=args.building_id,
                building_id_column=args.building_id_column,
                meter_column=args.meter_column,
                default_temp_c=args.default_temp_c,
                default_price=args.default_price,
                default_carbon=args.default_carbon,
                default_solar=args.default_solar,
                enrichment_csv=args.enrichment_csv,
                enrichment_timestamp_column=args.enrichment_timestamp_column,
                require_enrichment_match=args.require_enrichment_match,
            )
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"prepare failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, indent=2, sort_keys=True))
    print("Next: run scripts/run_local_pipeline.py --source imported --scenario price --model trained-regression-v1 --train-model")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
