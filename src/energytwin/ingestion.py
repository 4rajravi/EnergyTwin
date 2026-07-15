from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .data import generate_history


REQUIRED_COLUMNS = (
    "timestamp",
    "hour",
    "demand_kw",
    "solar_kw",
    "outside_temp_c",
    "price_usd_per_kwh",
    "carbon_kg_per_kwh",
)


@dataclass(frozen=True)
class DataHealth:
    source: str
    row_count: int
    valid_rows: int
    invalid_rows: int
    start_timestamp: str | None
    end_timestamp: str | None
    columns: list[str]
    issues: list[str]


class DataValidationError(ValueError):
    pass


def load_meter_csv(path: Path | str) -> list[dict[str, float | int | str]]:
    source = Path(path)
    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = [_normalize_row(row, index + 2) for index, row in enumerate(reader)]
    validate_rows(rows, source=str(source))
    return rows


def write_demo_csv(path: Path | str, scenario_key: str = "normal", hours: int = 168) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = generate_history(hours=hours, scenario_key=scenario_key)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REQUIRED_COLUMNS))
        writer.writeheader()
        writer.writerows(rows)
    return target


def data_health(rows: Iterable[dict], source: str = "memory") -> DataHealth:
    row_list = list(rows)
    issues = _validation_issues(row_list)
    timestamps = sorted(str(row["timestamp"]) for row in row_list if "timestamp" in row)
    columns = sorted({column for row in row_list for column in row.keys() if not column.startswith("_")})
    return DataHealth(
        source=source,
        row_count=len(row_list),
        valid_rows=max(0, len(row_list) - len(issues)),
        invalid_rows=len(issues),
        start_timestamp=timestamps[0] if timestamps else None,
        end_timestamp=timestamps[-1] if timestamps else None,
        columns=columns,
        issues=issues[:25],
    )


def validate_rows(rows: Iterable[dict], source: str = "memory") -> None:
    health = data_health(rows, source=source)
    if health.invalid_rows:
        detail = "; ".join(health.issues[:5])
        raise DataValidationError(f"{source} failed validation: {detail}")


def _normalize_row(row: dict[str, str | None], line_number: int) -> dict[str, float | int | str]:
    normalized: dict[str, float | int | str] = {}
    for column in REQUIRED_COLUMNS:
        value = row.get(column)
        if value is None or value == "":
            normalized[column] = ""
        elif column == "timestamp":
            normalized[column] = value
        elif column == "hour":
            normalized[column] = int(value)
        else:
            normalized[column] = float(value)
    normalized["_line_number"] = line_number
    return normalized


def _validation_issues(rows: list[dict]) -> list[str]:
    issues: list[str] = []
    if not rows:
        return ["dataset has no rows"]

    previous_timestamp: datetime | None = None
    for index, row in enumerate(rows, start=1):
        label = f"row {row.get('_line_number', index)}"
        missing = [column for column in REQUIRED_COLUMNS if column not in row or row[column] == ""]
        if missing:
            issues.append(f"{label}: missing {', '.join(missing)}")
            continue

        try:
            timestamp = datetime.fromisoformat(str(row["timestamp"]))
        except ValueError:
            issues.append(f"{label}: invalid timestamp")
            continue

        if previous_timestamp and timestamp <= previous_timestamp:
            issues.append(f"{label}: timestamp must increase")
        previous_timestamp = timestamp

        hour = int(row["hour"])
        if hour < 0 or hour > 23:
            issues.append(f"{label}: hour must be 0-23")

        for column in ("demand_kw", "solar_kw", "price_usd_per_kwh", "carbon_kg_per_kwh"):
            if float(row[column]) < 0:
                issues.append(f"{label}: {column} must be non-negative")

        temp = float(row["outside_temp_c"])
        if temp < -60 or temp > 70:
            issues.append(f"{label}: outside_temp_c is outside expected range")
    return issues
