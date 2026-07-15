from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


NASA_POWER_HOURLY_ENDPOINT = "https://power.larc.nasa.gov/api/temporal/hourly/point"
DEFAULT_PARAMETERS = ("T2M", "ALLSKY_SFC_SW_DWN")


@dataclass(frozen=True)
class NasaPowerRequest:
    latitude: float
    longitude: float
    start: str
    end: str
    community: str = "SB"
    time_standard: str = "UTC"
    parameters: tuple[str, ...] = DEFAULT_PARAMETERS


def build_nasa_power_url(request: NasaPowerRequest) -> str:
    query = {
        "parameters": ",".join(request.parameters),
        "community": request.community,
        "longitude": request.longitude,
        "latitude": request.latitude,
        "start": request.start,
        "end": request.end,
        "format": "JSON",
        "time-standard": request.time_standard,
    }
    return f"{NASA_POWER_HOURLY_ENDPOINT}?{urlencode(query)}"


def fetch_nasa_power_json(request: NasaPowerRequest, timeout_seconds: int = 30) -> dict:
    with urlopen(build_nasa_power_url(request), timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def nasa_power_json_to_enrichment_rows(
    payload: dict,
    solar_kwp: float,
    performance_ratio: float = 0.82,
) -> list[dict[str, float | str]]:
    parameters = payload.get("properties", {}).get("parameter", {})
    temp = parameters.get("T2M", {})
    irradiance = parameters.get("ALLSKY_SFC_SW_DWN", {})
    timestamps = sorted(set(temp.keys()) | set(irradiance.keys()))
    rows: list[dict[str, float | str]] = []

    for key in timestamps:
        row: dict[str, float | str] = {"timestamp": _power_hour_to_iso(key)}
        if key in temp:
            row["outside_temp_c"] = round(float(temp[key]), 3)
        if key in irradiance:
            irradiance_kw_per_m2 = max(0.0, float(irradiance[key])) / 1000
            row["solar_kw"] = round(irradiance_kw_per_m2 * solar_kwp * performance_ratio, 3)
        rows.append(row)

    if not rows:
        raise ValueError("NASA POWER payload has no hourly parameter rows")
    return rows


def write_enrichment_csv(path: Path | str, rows: list[dict[str, float | str]]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["timestamp", "outside_temp_c", "solar_kw"]
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})
    return target


def _power_hour_to_iso(value: str) -> str:
    return datetime.strptime(value, "%Y%m%d%H").isoformat()
