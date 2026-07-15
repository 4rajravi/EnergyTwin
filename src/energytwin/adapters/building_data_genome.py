from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from energytwin.ingestion import validate_rows


@dataclass(frozen=True)
class AdapterDefaults:
    solar_kw: float = 0.0
    outside_temp_c: float = 22.0
    price_usd_per_kwh: float = 0.18
    carbon_kg_per_kwh: float = 0.38


def convert_bdg_wide_csv(
    path: Path | str,
    building_column: str,
    timestamp_column: str = "timestamp",
    defaults: AdapterDefaults | None = None,
) -> list[dict[str, float | int | str]]:
    defaults = defaults or AdapterDefaults()
    source = Path(path)
    rows: list[dict[str, float | int | str]] = []

    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for line_number, row in enumerate(reader, start=2):
            if building_column not in row:
                raise ValueError(f"{source} is missing building column {building_column!r}")
            rows.append(
                _to_energytwin_row(
                    timestamp_value=row.get(timestamp_column),
                    demand_value=row.get(building_column),
                    defaults=defaults,
                    line_number=line_number,
                )
            )

    validate_rows(rows, source=str(source))
    return rows


def convert_bdg_long_csv(
    path: Path | str,
    building_id: str,
    timestamp_column: str = "timestamp",
    building_id_column: str = "building_id",
    meter_column: str = "meter_reading",
    defaults: AdapterDefaults | None = None,
) -> list[dict[str, float | int | str]]:
    defaults = defaults or AdapterDefaults()
    source = Path(path)
    rows: list[dict[str, float | int | str]] = []

    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for line_number, row in enumerate(reader, start=2):
            if row.get(building_id_column) != building_id:
                continue
            rows.append(
                _to_energytwin_row(
                    timestamp_value=row.get(timestamp_column),
                    demand_value=row.get(meter_column),
                    defaults=defaults,
                    line_number=line_number,
                )
            )

    if not rows:
        raise ValueError(f"{source} has no rows for building {building_id!r}")

    validate_rows(rows, source=str(source))
    return rows


def _to_energytwin_row(
    timestamp_value: str | None,
    demand_value: str | None,
    defaults: AdapterDefaults,
    line_number: int,
) -> dict[str, float | int | str]:
    if not timestamp_value:
        raise ValueError(f"row {line_number}: missing timestamp")
    if demand_value is None or demand_value == "":
        raise ValueError(f"row {line_number}: missing meter reading")

    timestamp = datetime.fromisoformat(timestamp_value)
    demand_kw = float(demand_value)
    return {
        "timestamp": timestamp.isoformat(),
        "hour": timestamp.hour,
        "demand_kw": demand_kw,
        "solar_kw": defaults.solar_kw,
        "outside_temp_c": defaults.outside_temp_c,
        "price_usd_per_kwh": defaults.price_usd_per_kwh,
        "carbon_kg_per_kwh": defaults.carbon_kg_per_kwh,
        "_line_number": line_number,
    }
