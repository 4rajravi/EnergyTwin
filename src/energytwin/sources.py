from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .data import generate_history
from .ingestion import data_health, load_meter_csv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_CURRENT = PROJECT_ROOT / "data" / "processed" / "current-meter.csv"


@dataclass(frozen=True)
class DataSource:
    key: str
    label: str
    kind: str
    available: bool
    detail: str


def available_data_sources() -> list[DataSource]:
    imported_available = PROCESSED_CURRENT.exists()
    return [
        DataSource(
            key="demo",
            label="Demo profile",
            kind="generated",
            available=True,
            detail="Deterministic hourly building profile",
        ),
        DataSource(
            key="imported",
            label="Imported CSV",
            kind="csv",
            available=imported_available,
            detail=str(PROCESSED_CURRENT) if imported_available else "Run scripts/import_dataset.py first",
        ),
    ]


def load_history(source_key: str = "demo", scenario_key: str = "normal") -> tuple[list[dict], str]:
    if source_key == "imported" and PROCESSED_CURRENT.exists():
        return load_meter_csv(PROCESSED_CURRENT), f"csv:{PROCESSED_CURRENT.name}"
    return generate_history(scenario_key=scenario_key), f"demo:{scenario_key}"


def current_data_health(source_key: str = "demo", scenario_key: str = "normal"):
    rows, source = load_history(source_key=source_key, scenario_key=scenario_key)
    return data_health(rows, source=source)
