from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .sources import PROJECT_ROOT, PROCESSED_CURRENT


@dataclass(frozen=True)
class DefaultRealDataConfig:
    dataset_name: str = "Building Data Genome Project 2"
    dataset_root: Path = PROJECT_ROOT / "data" / "raw" / "buildingdatagenomeproject2"
    meter_input_path: Path = PROJECT_ROOT / "data" / "raw" / "buildingdatagenomeproject2" / "electricity_cleaned.csv"
    metadata_path: Path = PROJECT_ROOT / "data" / "raw" / "buildingdatagenomeproject2" / "metadata.csv"
    weather_path: Path = PROJECT_ROOT / "data" / "raw" / "buildingdatagenomeproject2" / "weather.csv"
    solar_path: Path = PROJECT_ROOT / "data" / "raw" / "buildingdatagenomeproject2" / "solar_cleaned.csv"
    prepared_output_path: Path = PROCESSED_CURRENT
    input_format: str = "bdg-wide"
    timestamp_column: str = "timestamp"
    building_column: str = "Hog_office_Betsy"
    building_id: str | None = None
    building_id_column: str = "building_id"
    meter_column: str = "meter_reading"
    enrichment_csv: Path = PROJECT_ROOT / "data" / "raw" / "nasa-power-enrichment.csv"
    require_enrichment_match: bool = False
    nasa_latitude: float = 40.0
    nasa_longitude: float = -105.0
    nasa_start: str = "20160101"
    nasa_end: str = "20160107"
    nasa_time_standard: str = "UTC"
    solar_kwp: float = 260.0
    solar_performance_ratio: float = 0.82
    default_temp_c: float = 22.0
    default_price: float = 0.18
    default_carbon: float = 0.38
    default_solar: float = 0.0


DEFAULT_REAL_DATA_CONFIG = DefaultRealDataConfig()
