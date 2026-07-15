from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class BuildingProfile:
    building_id: str
    name: str
    building_type: str
    floor_area_m2: float
    peak_kw: float
    base_kw: float
    solar_kwp: float


@dataclass(frozen=True)
class BatterySpec:
    capacity_kwh: float = 320.0
    max_kw: float = 80.0
    roundtrip_efficiency: float = 0.92
    initial_soc_kwh: float = 160.0
    min_soc_kwh: float = 32.0
    max_soc_kwh: float = 304.0


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    temperature_delta_c: float = 0.0
    cloud_cover: float = 0.25
    price_multiplier: float = 1.0
    ev_spike_kw: float = 0.0
    comfort_strictness: float = 0.5


@dataclass(frozen=True)
class ForecastPoint:
    timestamp: str
    hour: int
    demand_kw: float
    demand_p10_kw: float
    demand_p90_kw: float
    solar_kw: float
    solar_p10_kw: float
    solar_p90_kw: float
    outside_temp_c: float
    price_usd_per_kwh: float
    carbon_kg_per_kwh: float
    peak_risk: float


@dataclass(frozen=True)
class ForecastMetrics:
    model_name: str
    horizon_hours: int
    evaluated_points: int
    mae_kw: float
    rmse_kw: float
    smape: float
    bias_kw: float
    coverage_p10_p90: float


@dataclass(frozen=True)
class SimulationPoint:
    timestamp: str
    demand_kw: float
    adjusted_demand_kw: float
    solar_kw: float
    battery_kw: float
    battery_soc_kwh: float
    grid_import_kw: float
    grid_export_kw: float
    price_usd_per_kwh: float
    carbon_kg_per_kwh: float
    comfort_risk: float


@dataclass(frozen=True)
class SimulationMetrics:
    total_cost_usd: float
    carbon_kg: float
    peak_grid_kw: float
    comfort_violation_hours: float
    battery_cycles: float
    grid_import_kwh: float
    grid_export_kwh: float


def serialize(value):
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: serialize(item) for key, item in value.items()}
    return value
