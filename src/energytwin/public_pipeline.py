from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .adapters.building_data_genome import AdapterDefaults, convert_bdg_long_csv, convert_bdg_wide_csv
from .enrichment import enrich_rows_from_csv
from .ingestion import REQUIRED_COLUMNS, data_health, validate_rows
from .sources import PROCESSED_CURRENT


@dataclass(frozen=True)
class PublicDatasetConfig:
    input_path: Path | str
    input_format: str
    output_path: Path | str = PROCESSED_CURRENT
    timestamp_column: str = "timestamp"
    building_column: str | None = None
    building_id: str | None = None
    building_id_column: str = "building_id"
    meter_column: str = "meter_reading"
    default_temp_c: float = 22.0
    default_price: float = 0.18
    default_carbon: float = 0.38
    default_solar: float = 0.0
    enrichment_csv: Path | str | None = None
    enrichment_timestamp_column: str = "timestamp"
    require_enrichment_match: bool = False


def prepare_public_dataset(config: PublicDatasetConfig) -> dict:
    rows = _convert_rows(config)
    if config.enrichment_csv:
        rows = enrich_rows_from_csv(
            rows,
            config.enrichment_csv,
            timestamp_column=config.enrichment_timestamp_column,
            require_match=config.require_enrichment_match,
        )
    validate_rows(rows)
    output = _write_energytwin_csv(config.output_path, rows)
    health = data_health(rows, source=str(output))
    return {
        "input": str(config.input_path),
        "input_format": config.input_format,
        "output": str(output),
        "row_count": health.row_count,
        "valid_rows": health.valid_rows,
        "invalid_rows": health.invalid_rows,
        "start_timestamp": health.start_timestamp,
        "end_timestamp": health.end_timestamp,
        "columns": health.columns,
        "enriched": bool(config.enrichment_csv),
    }


def _convert_rows(config: PublicDatasetConfig) -> list[dict]:
    defaults = AdapterDefaults(
        solar_kw=config.default_solar,
        outside_temp_c=config.default_temp_c,
        price_usd_per_kwh=config.default_price,
        carbon_kg_per_kwh=config.default_carbon,
    )
    if config.input_format == "bdg-wide":
        if not config.building_column:
            raise ValueError("building_column is required for bdg-wide")
        return convert_bdg_wide_csv(
            config.input_path,
            building_column=config.building_column,
            timestamp_column=config.timestamp_column,
            defaults=defaults,
        )
    if config.input_format == "bdg-long":
        if not config.building_id:
            raise ValueError("building_id is required for bdg-long")
        return convert_bdg_long_csv(
            config.input_path,
            building_id=config.building_id,
            timestamp_column=config.timestamp_column,
            building_id_column=config.building_id_column,
            meter_column=config.meter_column,
            defaults=defaults,
        )
    raise ValueError(f"unsupported public dataset format: {config.input_format}")


def _write_energytwin_csv(path: Path | str, rows: list[dict]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REQUIRED_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in REQUIRED_COLUMNS})
    return target
