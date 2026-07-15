from __future__ import annotations

import math
from datetime import datetime, timedelta

from .domain import BuildingProfile, Scenario


PROFILE = BuildingProfile(
    building_id="bldg-commercial-001",
    name="North Loop Commercial Hub",
    building_type="commercial-office",
    floor_area_m2=18400,
    peak_kw=620,
    base_kw=145,
    solar_kwp=260,
)


SCENARIOS: dict[str, Scenario] = {
    "normal": Scenario("normal", "Normal day", cloud_cover=0.25),
    "hot": Scenario("hot", "Hotter day", temperature_delta_c=7.0, cloud_cover=0.18, comfort_strictness=0.8),
    "cloudy": Scenario("cloudy", "Cloudy day", temperature_delta_c=-1.0, cloud_cover=0.78),
    "price": Scenario("price", "High price day", price_multiplier=1.65, cloud_cover=0.32),
    "ev": Scenario("ev", "EV charging spike", ev_spike_kw=110.0, cloud_cover=0.25),
    "carbon": Scenario("carbon", "Carbon-heavy grid", cloud_cover=0.4, price_multiplier=1.15),
}


def get_scenario(key: str | None, overrides: dict[str, float] | None = None) -> Scenario:
    base = SCENARIOS.get(key or "normal", SCENARIOS["normal"])
    if not overrides:
        return base
    return Scenario(
        key=base.key,
        label=base.label,
        temperature_delta_c=overrides.get("temperature_delta_c", base.temperature_delta_c),
        cloud_cover=overrides.get("cloud_cover", base.cloud_cover),
        price_multiplier=overrides.get("price_multiplier", base.price_multiplier),
        ev_spike_kw=overrides.get("ev_spike_kw", base.ev_spike_kw),
        comfort_strictness=overrides.get("comfort_strictness", base.comfort_strictness),
    )


def available_scenarios() -> list[dict[str, str]]:
    return [{"key": scenario.key, "label": scenario.label} for scenario in SCENARIOS.values()]


def demand_shape(hour: int) -> float:
    morning = math.exp(-((hour - 10) ** 2) / 20)
    afternoon = math.exp(-((hour - 15) ** 2) / 12)
    evening = 0.35 * math.exp(-((hour - 19) ** 2) / 10)
    return 0.2 + 0.45 * morning + 0.55 * afternoon + evening


def solar_shape(hour: int) -> float:
    if hour < 6 or hour > 19:
        return 0.0
    return max(0.0, math.sin((hour - 6) / 13 * math.pi))


def weather_temp(hour: int, day_index: int, scenario: Scenario) -> float:
    daily = 23 + 7 * math.sin((hour - 7) / 24 * 2 * math.pi)
    weekly = 2.5 * math.sin(day_index / 7 * 2 * math.pi)
    return daily + weekly + scenario.temperature_delta_c


def price(hour: int, scenario: Scenario) -> float:
    base = 0.16
    if 16 <= hour <= 20:
        base = 0.34
    elif 7 <= hour <= 10:
        base = 0.23
    elif 0 <= hour <= 5:
        base = 0.11
    return base * scenario.price_multiplier


def carbon_intensity(hour: int, scenario: Scenario) -> float:
    carbon = 0.38
    if 11 <= hour <= 15:
        carbon -= 0.09
    if 18 <= hour <= 22:
        carbon += 0.12
    if scenario.key == "carbon":
        carbon += 0.18
    return max(0.12, carbon)


def generate_history(
    hours: int = 168,
    scenario_key: str = "normal",
    scenario: Scenario | None = None,
) -> list[dict[str, float | int | str]]:
    scenario = scenario or get_scenario(scenario_key)
    start = datetime(2026, 7, 7, 0, 0)
    rows: list[dict[str, float | int | str]] = []
    for offset in range(hours):
        ts = start + timedelta(hours=offset)
        hour = ts.hour
        day = offset // 24
        temp = weather_temp(hour, day, scenario)
        cooling_load = max(0.0, temp - 22.0) * 12.5
        occupancy = demand_shape(hour)
        deterministic_noise = 16 * math.sin((offset * 5.3) % (2 * math.pi))
        ev = scenario.ev_spike_kw if 17 <= hour <= 20 else 0.0
        demand = PROFILE.base_kw + PROFILE.peak_kw * occupancy + cooling_load + deterministic_noise + ev
        solar = PROFILE.solar_kwp * solar_shape(hour) * (1 - scenario.cloud_cover * 0.82)
        rows.append(
            {
                "timestamp": ts.isoformat(),
                "hour": hour,
                "demand_kw": round(max(PROFILE.base_kw, demand), 2),
                "solar_kw": round(max(0.0, solar), 2),
                "outside_temp_c": round(temp, 2),
                "price_usd_per_kwh": round(price(hour, scenario), 4),
                "carbon_kg_per_kwh": round(carbon_intensity(hour, scenario), 4),
            }
        )
    return rows
