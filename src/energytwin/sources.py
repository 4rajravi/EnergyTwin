from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .data import generate_history
from .domain import Scenario
from .ingestion import data_health, load_meter_csv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_CURRENT = PROJECT_ROOT / "data" / "processed" / "current-meter.csv"
DEFAULT_GENOME_BUILDING_ID = "Hog_office_Betsy"


@dataclass(frozen=True)
class DataSource:
    key: str
    label: str
    kind: str
    available: bool
    detail: str


def available_data_sources() -> list[DataSource]:
    imported_available = PROCESSED_CURRENT.exists()
    genome_available = _genome_available()
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
        DataSource(
            key="genome",
            label="Building Genome",
            kind="public-dataset",
            available=genome_available,
            detail="Building Data Genome 2" if genome_available else "Place Kaggle files under data/raw/buildingdatagenomeproject2",
        ),
    ]


def load_history(
    source_key: str = "demo",
    scenario_key: str = "normal",
    scenario: Scenario | None = None,
    building_id: str | None = None,
) -> tuple[list[dict], str]:
    if source_key == "genome":
        from .adapters.building_data_genome2 import ensure_building_data_genome2_csv

        selected = building_id or DEFAULT_GENOME_BUILDING_ID
        path = ensure_building_data_genome2_csv(selected)
        return load_meter_csv(path), f"genome:{selected}"
    if source_key == "imported" and PROCESSED_CURRENT.exists():
        return load_meter_csv(PROCESSED_CURRENT), f"csv:{PROCESSED_CURRENT.name}"
    return generate_history(scenario_key=scenario_key, scenario=scenario), f"demo:{scenario_key}"


def current_data_health(
    source_key: str = "demo",
    scenario_key: str = "normal",
    scenario: Scenario | None = None,
    building_id: str | None = None,
):
    rows, source = load_history(
        source_key=source_key,
        scenario_key=scenario_key,
        scenario=scenario,
        building_id=building_id,
    )
    return data_health(rows, source=source)


def available_buildings(limit: int = 500) -> list[dict]:
    from .adapters.building_data_genome2 import list_building_data_genome2_buildings

    return list_building_data_genome2_buildings(limit=limit)


def _genome_available() -> bool:
    from .adapters.building_data_genome2 import building_data_genome2_available

    return building_data_genome2_available()
