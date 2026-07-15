from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from .ingestion import REQUIRED_COLUMNS, validate_rows


ENRICHABLE_COLUMNS = (
    "solar_kw",
    "outside_temp_c",
    "price_usd_per_kwh",
    "carbon_kg_per_kwh",
)


def load_enrichment_csv(
    path: Path | str,
    timestamp_column: str = "timestamp",
) -> dict[str, dict[str, float]]:
    source = Path(path)
    enrichment: dict[str, dict[str, float]] = {}

    with source.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            raise ValueError(f"{source} has no header")

        available_columns = [column for column in ENRICHABLE_COLUMNS if column in reader.fieldnames]
        if timestamp_column not in reader.fieldnames:
            raise ValueError(f"{source} is missing timestamp column {timestamp_column!r}")
        if not available_columns:
            raise ValueError(f"{source} has no enrichable columns")

        for line_number, row in enumerate(reader, start=2):
            timestamp = _normalize_timestamp(row.get(timestamp_column), source, line_number)
            values: dict[str, float] = {}
            for column in available_columns:
                raw_value = row.get(column)
                if raw_value not in (None, ""):
                    values[column] = float(raw_value)
            if values:
                enrichment[timestamp] = values

    if not enrichment:
        raise ValueError(f"{source} has no enrichment rows")
    return enrichment


def enrich_rows(
    rows: list[dict],
    enrichment: dict[str, dict[str, float]],
    require_match: bool = False,
) -> list[dict[str, float | int | str]]:
    enriched: list[dict[str, float | int | str]] = []
    matched = 0

    for row in rows:
        next_row = dict(row)
        values = enrichment.get(str(row["timestamp"]))
        if values:
            matched += 1
            for column, value in values.items():
                if column in ENRICHABLE_COLUMNS:
                    next_row[column] = value
        enriched.append(next_row)

    if require_match and matched != len(rows):
        raise ValueError(f"enrichment matched {matched} of {len(rows)} rows")

    validate_rows(enriched)
    return enriched


def enrich_rows_from_csv(
    rows: list[dict],
    path: Path | str,
    timestamp_column: str = "timestamp",
    require_match: bool = False,
) -> list[dict[str, float | int | str]]:
    enrichment = load_enrichment_csv(path, timestamp_column=timestamp_column)
    return enrich_rows(rows, enrichment, require_match=require_match)


def _normalize_timestamp(value: str | None, source: Path, line_number: int) -> str:
    if not value:
        raise ValueError(f"{source} row {line_number}: missing timestamp")
    return datetime.fromisoformat(value).isoformat()
