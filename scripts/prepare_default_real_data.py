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
from energytwin.adapters.building_data_genome2 import (  # noqa: E402
    BuildingDataGenome2Config,
    metadata_for_building,
    meter_date_range,
    prepare_building_data_genome2,
)
from energytwin.real_data_defaults import DEFAULT_REAL_DATA_CONFIG  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare the hard-coded default real-data profile.")
    parser.add_argument("--skip-nasa", action="store_true", help="Use Building Data Genome weather and skip NASA solar enrichment.")
    parser.add_argument("--refresh-nasa", action="store_true", help="Fetch NASA POWER even if the enrichment CSV exists.")
    parser.add_argument("--from-nasa-json", help="Use a local NASA POWER JSON payload instead of fetching.")
    args = parser.parse_args()

    config = DEFAULT_REAL_DATA_CONFIG
    required = [config.meter_input_path, config.metadata_path, config.weather_path]
    missing = [path for path in required if not path.exists()]
    if missing:
        print(
            "missing Building Data Genome files:\n"
            + "\n".join(f"- {path}" for path in missing)
            + "\nPut the Kaggle files under data/raw/buildingdatagenomeproject2/.",
            file=sys.stderr,
        )
        return 1

    if not args.skip_nasa and (args.refresh_nasa or args.from_nasa_json or not config.enrichment_csv.exists()):
        try:
            _write_default_nasa_enrichment(args.from_nasa_json)
        except Exception as exc:
            print(f"NASA POWER enrichment failed: {exc}", file=sys.stderr)
            return 1

    enrichment_csv = config.enrichment_csv if config.enrichment_csv.exists() and not args.skip_nasa else None
    try:
        summary = prepare_building_data_genome2(
            BuildingDataGenome2Config(
                root_path=config.dataset_root,
                building_id=config.building_column,
                output_path=config.prepared_output_path,
                default_temp_c=config.default_temp_c,
                default_price=config.default_price,
                default_carbon=config.default_carbon,
                default_solar=config.default_solar,
                nasa_enrichment_csv=enrichment_csv,
            )
        )
    except (FileNotFoundError, ValueError) as exc:
        print(f"prepare failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps({"config": _config_summary(), "summary": summary}, indent=2, sort_keys=True))
    print("Next: run scripts/run_local_pipeline.py --source imported --scenario price --model trained-mlp-v1 --train-model")
    return 0


def _write_default_nasa_enrichment(from_json: str | None = None) -> Path:
    config = DEFAULT_REAL_DATA_CONFIG
    metadata = metadata_for_building(config.metadata_path, config.building_column)
    if not metadata.get("lat") or not metadata.get("lng"):
        raise ValueError(f"metadata for {config.building_column} has no lat/lng")
    start, end = meter_date_range(config.meter_input_path, config.building_column)
    if from_json:
        payload = json.loads(Path(from_json).read_text(encoding="utf-8"))
    else:
        payload = fetch_nasa_power_json(
            NasaPowerRequest(
                latitude=float(metadata["lat"]),
                longitude=float(metadata["lng"]),
                start=start.strftime("%Y%m%d"),
                end=end.strftime("%Y%m%d"),
                time_standard=config.nasa_time_standard,
            )
        )
    rows = nasa_power_json_to_enrichment_rows(
        payload,
        solar_kwp=config.solar_kwp,
        performance_ratio=config.solar_performance_ratio,
    )
    return write_enrichment_csv(config.enrichment_csv, rows)


def _config_summary() -> dict:
    config = DEFAULT_REAL_DATA_CONFIG
    return {
        "dataset_name": config.dataset_name,
        "dataset_root": str(config.dataset_root),
        "meter_input_path": str(config.meter_input_path),
        "building_column": config.building_column,
        "enrichment_csv": str(config.enrichment_csv),
        "prepared_output_path": str(config.prepared_output_path),
    }


if __name__ == "__main__":
    raise SystemExit(main())
