from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from energytwin.ingestion import DataValidationError, data_health, load_meter_csv, write_demo_csv  # noqa: E402
from energytwin.adapters.building_data_genome import (  # noqa: E402
    AdapterDefaults,
    convert_bdg_long_csv,
    convert_bdg_wide_csv,
)
from energytwin.enrichment import enrich_rows_from_csv  # noqa: E402
from energytwin.sources import PROCESSED_CURRENT  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and import an hourly meter CSV.")
    parser.add_argument("input", nargs="?", help="CSV file to import.")
    parser.add_argument("--output", default=str(PROCESSED_CURRENT), help="Processed CSV output path.")
    parser.add_argument(
        "--format",
        choices=("energytwin", "bdg-wide", "bdg-long"),
        default="energytwin",
        help="Input schema to import.",
    )
    parser.add_argument("--make-demo", action="store_true", help="Create a valid demo CSV at --output.")
    parser.add_argument("--scenario", default="normal", help="Demo scenario used with --make-demo.")
    parser.add_argument("--timestamp-column", default="timestamp", help="Timestamp column for adapter formats.")
    parser.add_argument("--building-column", help="Building meter column for bdg-wide format.")
    parser.add_argument("--building-id", help="Building id value for bdg-long format.")
    parser.add_argument("--building-id-column", default="building_id", help="Building id column for bdg-long format.")
    parser.add_argument("--meter-column", default="meter_reading", help="Meter column for bdg-long format.")
    parser.add_argument("--default-temp-c", type=float, default=22.0)
    parser.add_argument("--default-price", type=float, default=0.18)
    parser.add_argument("--default-carbon", type=float, default=0.38)
    parser.add_argument("--default-solar", type=float, default=0.0)
    parser.add_argument("--enrichment-csv", help="Optional CSV with timestamp plus weather/solar/price/carbon columns.")
    parser.add_argument("--enrichment-timestamp-column", default="timestamp")
    parser.add_argument(
        "--require-enrichment-match",
        action="store_true",
        help="Fail if the enrichment CSV does not match every imported meter row.",
    )
    args = parser.parse_args()

    output = Path(args.output)
    if args.make_demo:
        write_demo_csv(output, scenario_key=args.scenario)
        rows = load_meter_csv(output)
        health = data_health(rows, source=str(output))
        print(f"created {output}")
        print(f"rows={health.row_count} valid={health.valid_rows} invalid={health.invalid_rows}")
        return 0

    if not args.input:
        parser.error("input is required unless --make-demo is used")

    try:
        rows = _load_rows(args)
        if args.enrichment_csv:
            rows = enrich_rows_from_csv(
                rows,
                args.enrichment_csv,
                timestamp_column=args.enrichment_timestamp_column,
                require_match=args.require_enrichment_match,
            )
    except (DataValidationError, FileNotFoundError, ValueError) as exc:
        print(f"import failed: {exc}", file=sys.stderr)
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    _write_rows(output, rows)
    health = data_health(rows, source=str(output))
    print(f"imported {args.input} -> {output}")
    print(f"rows={health.row_count} valid={health.valid_rows} invalid={health.invalid_rows}")
    return 0


def _load_rows(args: argparse.Namespace) -> list[dict]:
    if args.format == "energytwin":
        return load_meter_csv(args.input)

    defaults = AdapterDefaults(
        solar_kw=args.default_solar,
        outside_temp_c=args.default_temp_c,
        price_usd_per_kwh=args.default_price,
        carbon_kg_per_kwh=args.default_carbon,
    )

    if args.format == "bdg-wide":
        if not args.building_column:
            raise ValueError("--building-column is required for --format bdg-wide")
        return convert_bdg_wide_csv(
            args.input,
            building_column=args.building_column,
            timestamp_column=args.timestamp_column,
            defaults=defaults,
        )

    if not args.building_id:
        raise ValueError("--building-id is required for --format bdg-long")
    return convert_bdg_long_csv(
        args.input,
        building_id=args.building_id,
        timestamp_column=args.timestamp_column,
        building_id_column=args.building_id_column,
        meter_column=args.meter_column,
        defaults=defaults,
    )


def _write_rows(path: Path, rows: list[dict]) -> None:
    import csv

    from energytwin.ingestion import REQUIRED_COLUMNS

    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REQUIRED_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in REQUIRED_COLUMNS})


if __name__ == "__main__":
    raise SystemExit(main())
