from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..enrichment import load_enrichment_csv
from ..ingestion import REQUIRED_COLUMNS, data_health, validate_rows
from ..sources import PROCESSED_CURRENT, PROJECT_ROOT


BDG2_ROOT = PROJECT_ROOT / "data" / "raw" / "buildingdatagenomeproject2"
BDG2_PROCESSED_ROOT = PROJECT_ROOT / "data" / "processed" / "buildings"


@dataclass(frozen=True)
class BuildingDataGenome2Config:
    root_path: Path | str = BDG2_ROOT
    building_id: str = "Hog_office_Betsy"
    output_path: Path | str = PROCESSED_CURRENT
    electricity_filename: str = "electricity_cleaned.csv"
    metadata_filename: str = "metadata.csv"
    weather_filename: str = "weather.csv"
    solar_filename: str = "solar_cleaned.csv"
    nasa_enrichment_csv: Path | str | None = None
    default_temp_c: float = 22.0
    default_price: float = 0.18
    default_carbon: float = 0.38
    default_solar: float = 0.0
    require_nasa_match: bool = False


def prepare_building_data_genome2(config: BuildingDataGenome2Config) -> dict[str, Any]:
    root = Path(config.root_path)
    metadata = metadata_for_building(root / config.metadata_filename, config.building_id)
    weather = load_site_weather(root / config.weather_filename, str(metadata["site_id"]))
    solar = load_solar_meter(root / config.solar_filename, config.building_id)
    nasa = load_enrichment_csv(config.nasa_enrichment_csv) if config.nasa_enrichment_csv else {}
    rows = _build_rows(config, metadata, weather, solar, nasa)
    validate_rows(rows)
    output = write_energytwin_csv(config.output_path, rows)
    health = data_health(rows, source=str(output))
    return {
        "input": str(root),
        "building_id": config.building_id,
        "site_id": metadata["site_id"],
        "primaryspaceusage": metadata.get("primaryspaceusage"),
        "lat": metadata.get("lat"),
        "lng": metadata.get("lng"),
        "output": str(output),
        "row_count": health.row_count,
        "valid_rows": health.valid_rows,
        "invalid_rows": health.invalid_rows,
        "start_timestamp": health.start_timestamp,
        "end_timestamp": health.end_timestamp,
        "weather_rows": len(weather),
        "solar_rows": len(solar),
        "nasa_rows": len(nasa),
    }


def building_data_genome2_available(root_path: Path | str = BDG2_ROOT) -> bool:
    root = Path(root_path)
    return all((root / name).exists() for name in ("electricity_cleaned.csv", "metadata.csv", "weather.csv"))


def list_building_data_genome2_buildings(root_path: Path | str = BDG2_ROOT, limit: int = 500) -> list[dict[str, Any]]:
    root = Path(root_path)
    if not building_data_genome2_available(root):
        return []
    with (root / "electricity_cleaned.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        electricity_columns = set(next(reader)[1:])

    buildings: list[dict[str, Any]] = []
    with (root / "metadata.csv").open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            building_id = row.get("building_id", "")
            if building_id not in electricity_columns:
                continue
            buildings.append(
                {
                    "building_id": building_id,
                    "site_id": row.get("site_id", ""),
                    "primaryspaceusage": row.get("primaryspaceusage", ""),
                    "sqm": _optional_float(row.get("sqm")),
                    "lat": _optional_float(row.get("lat")),
                    "lng": _optional_float(row.get("lng")),
                    "has_solar": row.get("solar") == "Yes",
                }
            )

    buildings.sort(key=lambda item: (item["site_id"], item["primaryspaceusage"], item["building_id"]))
    return buildings[: max(1, min(limit, 2000))]


def prepared_building_path(building_id: str, output_dir: Path | str = BDG2_PROCESSED_ROOT) -> Path:
    return Path(output_dir) / f"{_safe_building_id(building_id)}.csv"


def ensure_building_data_genome2_csv(
    building_id: str,
    root_path: Path | str = BDG2_ROOT,
    output_dir: Path | str = BDG2_PROCESSED_ROOT,
) -> Path:
    target = prepared_building_path(building_id, output_dir=output_dir)
    if target.exists():
        return target
    prepare_building_data_genome2(
        BuildingDataGenome2Config(
            root_path=root_path,
            building_id=building_id,
            output_path=target,
        )
    )
    return target


def metadata_for_building(metadata_path: Path | str, building_id: str) -> dict[str, str]:
    source = Path(metadata_path)
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("building_id") == building_id:
                return row
    raise ValueError(f"building_id not found in metadata: {building_id}")


def meter_date_range(electricity_path: Path | str, building_id: str) -> tuple[datetime, datetime]:
    source = Path(electricity_path)
    first: datetime | None = None
    last: datetime | None = None
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or building_id not in reader.fieldnames:
            raise ValueError(f"{source} is missing building column {building_id!r}")
        for line_number, row in enumerate(reader, start=2):
            value = row.get(building_id)
            if not value:
                continue
            try:
                demand = float(value)
            except ValueError:
                continue
            if demand < 0:
                continue
            timestamp = _parse_timestamp(row.get("timestamp"), source, line_number)
            first = first or timestamp
            last = timestamp
    if first is None or last is None:
        raise ValueError(f"{source} has no usable rows for {building_id}")
    return first, last


def load_site_weather(weather_path: Path | str, site_id: str) -> dict[str, float]:
    source = Path(weather_path)
    weather: dict[str, float] = {}
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for line_number, row in enumerate(reader, start=2):
            if row.get("site_id") != site_id:
                continue
            raw_temp = row.get("airTemperature")
            if not raw_temp:
                continue
            timestamp = _parse_timestamp(row.get("timestamp"), source, line_number).isoformat()
            weather[timestamp] = float(raw_temp)
    if not weather:
        raise ValueError(f"{source} has no weather rows for site_id {site_id}")
    return weather


def load_solar_meter(solar_path: Path | str, building_id: str) -> dict[str, float]:
    source = Path(solar_path)
    if not source.exists():
        return {}
    solar: dict[str, float] = {}
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or building_id not in reader.fieldnames:
            return {}
        for line_number, row in enumerate(reader, start=2):
            raw_value = row.get(building_id)
            if not raw_value:
                continue
            timestamp = _parse_timestamp(row.get("timestamp"), source, line_number).isoformat()
            solar[timestamp] = max(0.0, float(raw_value))
    return solar


def write_energytwin_csv(path: Path | str, rows: list[dict[str, float | int | str]]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REQUIRED_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row[column] for column in REQUIRED_COLUMNS})
    return target


def _build_rows(
    config: BuildingDataGenome2Config,
    metadata: dict[str, str],
    weather: dict[str, float],
    solar: dict[str, float],
    nasa: dict[str, dict[str, float]],
) -> list[dict[str, float | int | str]]:
    source = Path(config.root_path) / config.electricity_filename
    rows: list[dict[str, float | int | str]] = []
    nasa_matches = 0
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or config.building_id not in reader.fieldnames:
            raise ValueError(f"{source} is missing building column {config.building_id!r}")
        for line_number, row in enumerate(reader, start=2):
            raw_demand = row.get(config.building_id)
            if not raw_demand:
                continue
            demand_kw = float(raw_demand)
            if demand_kw < 0:
                continue
            timestamp = _parse_timestamp(row.get("timestamp"), source, line_number)
            timestamp_key = timestamp.isoformat()
            nasa_values = nasa.get(timestamp_key, {})
            if nasa_values:
                nasa_matches += 1
            next_row: dict[str, float | int | str] = {
                "timestamp": timestamp_key,
                "hour": timestamp.hour,
                "demand_kw": round(demand_kw, 4),
                "solar_kw": round(nasa_values.get("solar_kw", solar.get(timestamp_key, config.default_solar)), 4),
                "outside_temp_c": round(nasa_values.get("outside_temp_c", weather.get(timestamp_key, config.default_temp_c)), 4),
                "price_usd_per_kwh": config.default_price,
                "carbon_kg_per_kwh": config.default_carbon,
            }
            rows.append(next_row)

    if config.require_nasa_match and nasa and nasa_matches != len(rows):
        raise ValueError(f"NASA enrichment matched {nasa_matches} of {len(rows)} meter rows")
    if not rows:
        raise ValueError(f"{source} has no usable rows for {config.building_id}")
    return rows


def _parse_timestamp(value: str | None, source: Path, line_number: int) -> datetime:
    if not value:
        raise ValueError(f"{source} row {line_number}: missing timestamp")
    return datetime.fromisoformat(value)


def _safe_building_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


def _optional_float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None
