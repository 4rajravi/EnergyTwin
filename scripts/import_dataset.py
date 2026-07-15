from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from energytwin.ingestion import DataValidationError, data_health, load_meter_csv, write_demo_csv  # noqa: E402
from energytwin.sources import PROCESSED_CURRENT  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and import an hourly meter CSV.")
    parser.add_argument("input", nargs="?", help="CSV file to import.")
    parser.add_argument("--output", default=str(PROCESSED_CURRENT), help="Processed CSV output path.")
    parser.add_argument("--make-demo", action="store_true", help="Create a valid demo CSV at --output.")
    parser.add_argument("--scenario", default="normal", help="Demo scenario used with --make-demo.")
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
        rows = load_meter_csv(args.input)
    except (DataValidationError, FileNotFoundError, ValueError) as exc:
        print(f"import failed: {exc}", file=sys.stderr)
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    _write_rows(output, rows)
    health = data_health(rows, source=str(output))
    print(f"imported {args.input} -> {output}")
    print(f"rows={health.row_count} valid={health.valid_rows} invalid={health.invalid_rows}")
    return 0


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
