from __future__ import annotations

from dataclasses import replace
from typing import Any

from .domain import BatterySpec, ForecastPoint, Scenario, TariffSpec, serialize
from .forecasting import MODEL_WEIGHTED, build_forecast
from .simulator import compare_policies, simulate
from .sources import DEFAULT_GENOME_BUILDING_ID, load_history


DEFAULT_DISTRICT_BUILDINGS = (
    DEFAULT_GENOME_BUILDING_ID,
    "Hog_office_Gustavo",
    "Hog_office_Shawnna",
)


def district_forecast(
    building_ids: list[str] | tuple[str, ...] = DEFAULT_DISTRICT_BUILDINGS,
    scenario_key: str = "normal",
    scenario: Scenario | None = None,
    model_name: str = MODEL_WEIGHTED,
    horizon_hours: int = 24,
) -> dict[str, Any]:
    forecasts: list[tuple[str, list[ForecastPoint]]] = []
    for building_id in building_ids:
        history, _ = load_history("genome", scenario_key=scenario_key, scenario=scenario, building_id=building_id)
        forecasts.append(
            (
                building_id,
                build_forecast(
                    history,
                    scenario_key=scenario_key,
                    scenario=scenario,
                    model_name=model_name,
                    horizon_hours=horizon_hours,
                ),
            )
        )
    aggregate = aggregate_forecasts(forecasts)
    return {
        "building_ids": list(building_ids),
        "building_count": len(building_ids),
        "forecast": serialize(aggregate),
    }


def district_optimize(
    building_ids: list[str] | tuple[str, ...] = DEFAULT_DISTRICT_BUILDINGS,
    scenario_key: str = "normal",
    scenario: Scenario | None = None,
    model_name: str = MODEL_WEIGHTED,
    battery: BatterySpec | None = None,
    tariff: TariffSpec | None = None,
) -> dict[str, Any]:
    forecast_payload = district_forecast(
        building_ids=building_ids,
        scenario_key=scenario_key,
        scenario=scenario,
        model_name=model_name,
    )
    forecast = [ForecastPoint(**point) for point in forecast_payload["forecast"]]
    comparison = compare_policies(forecast, battery=battery, tariff=tariff)
    _, optimized_metrics = simulate(forecast, "optimized", battery=battery, tariff=tariff)
    return {
        "building_ids": forecast_payload["building_ids"],
        "building_count": forecast_payload["building_count"],
        "comparison": comparison,
        "optimized_metrics": serialize(optimized_metrics),
        "forecast": forecast_payload["forecast"],
    }


def aggregate_forecasts(forecasts: list[tuple[str, list[ForecastPoint]]]) -> list[ForecastPoint]:
    if not forecasts:
        return []
    horizon = min(len(points) for _, points in forecasts)
    aggregate: list[ForecastPoint] = []
    for index in range(horizon):
        points = [building_forecast[index] for _, building_forecast in forecasts]
        first = points[0]
        demand = sum(point.demand_kw for point in points)
        solar = sum(point.solar_kw for point in points)
        aggregate.append(
            replace(
                first,
                demand_kw=round(demand, 2),
                demand_p10_kw=round(sum(point.demand_p10_kw for point in points), 2),
                demand_p90_kw=round(sum(point.demand_p90_kw for point in points), 2),
                solar_kw=round(solar, 2),
                solar_p10_kw=round(sum(point.solar_p10_kw for point in points), 2),
                solar_p90_kw=round(sum(point.solar_p90_kw for point in points), 2),
                outside_temp_c=round(sum(point.outside_temp_c for point in points) / len(points), 2),
                price_usd_per_kwh=round(sum(point.price_usd_per_kwh for point in points) / len(points), 4),
                carbon_kg_per_kwh=round(sum(point.carbon_kg_per_kwh for point in points) / len(points), 4),
                peak_risk=round(max(point.peak_risk for point in points), 3),
            )
        )
    return aggregate
