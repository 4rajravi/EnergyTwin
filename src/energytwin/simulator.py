from __future__ import annotations

import math

from .domain import BatterySpec, ForecastPoint, SimulationMetrics, SimulationPoint
from .optimizer import baseline_schedule, demand_response_factor, optimized_schedule, rule_schedule


def schedule_for(controller: str, forecast: list[ForecastPoint], battery: BatterySpec) -> list[float]:
    if controller == "rule":
        return rule_schedule(forecast, battery)
    if controller == "optimized":
        return optimized_schedule(forecast, battery)
    return baseline_schedule(forecast, battery)


def simulate(
    forecast: list[ForecastPoint],
    controller: str = "baseline",
    battery: BatterySpec | None = None,
) -> tuple[list[SimulationPoint], SimulationMetrics]:
    battery = battery or BatterySpec()
    schedule = schedule_for(controller, forecast, battery)
    soc = battery.initial_soc_kwh
    points: list[SimulationPoint] = []
    total_cost = 0.0
    carbon = 0.0
    peak = 0.0
    comfort_hours = 0.0
    throughput = 0.0
    import_kwh = 0.0
    export_kwh = 0.0

    for point, requested_battery_kw in zip(forecast, schedule):
        adjusted_demand = point.demand_kw * demand_response_factor(point, controller)
        comfort_risk = _comfort_risk(point, adjusted_demand, controller)
        if comfort_risk >= 0.7:
            comfort_hours += 1

        battery_kw = _bounded_battery_kw(requested_battery_kw, soc, battery)
        if battery_kw < 0:
            soc += abs(battery_kw) * battery.roundtrip_efficiency
        else:
            soc -= battery_kw
        soc = min(battery.max_soc_kwh, max(battery.min_soc_kwh, soc))

        net = adjusted_demand - point.solar_kw - battery_kw
        grid_import = max(0.0, net)
        grid_export = max(0.0, -net)
        total_cost += grid_import * point.price_usd_per_kwh - grid_export * point.price_usd_per_kwh * 0.32
        carbon += grid_import * point.carbon_kg_per_kwh
        peak = max(peak, grid_import)
        import_kwh += grid_import
        export_kwh += grid_export
        throughput += abs(battery_kw)

        points.append(
            SimulationPoint(
                timestamp=point.timestamp,
                demand_kw=point.demand_kw,
                adjusted_demand_kw=round(adjusted_demand, 2),
                solar_kw=point.solar_kw,
                battery_kw=round(battery_kw, 2),
                battery_soc_kwh=round(soc, 2),
                grid_import_kw=round(grid_import, 2),
                grid_export_kw=round(grid_export, 2),
                price_usd_per_kwh=point.price_usd_per_kwh,
                carbon_kg_per_kwh=point.carbon_kg_per_kwh,
                comfort_risk=round(comfort_risk, 3),
            )
        )

    metrics = SimulationMetrics(
        total_cost_usd=round(total_cost, 2),
        carbon_kg=round(carbon, 2),
        peak_grid_kw=round(peak, 2),
        comfort_violation_hours=round(comfort_hours, 2),
        battery_cycles=round(throughput / (2 * battery.capacity_kwh), 3),
        grid_import_kwh=round(import_kwh, 2),
        grid_export_kwh=round(export_kwh, 2),
    )
    return points, metrics


def compare_policies(forecast: list[ForecastPoint]) -> dict[str, dict]:
    _, baseline = simulate(forecast, "baseline")
    _, rule = simulate(forecast, "rule")
    _, optimized = simulate(forecast, "optimized")
    return {
        "baseline": _metrics_dict(baseline, baseline),
        "rule": _metrics_dict(rule, baseline),
        "optimized": _metrics_dict(optimized, baseline),
    }


def _bounded_battery_kw(requested_kw: float, soc: float, battery: BatterySpec) -> float:
    requested_kw = max(-battery.max_kw, min(battery.max_kw, requested_kw))
    if requested_kw < 0:
        available_room = max(0.0, battery.max_soc_kwh - soc) / battery.roundtrip_efficiency
        return -min(abs(requested_kw), available_room)
    available_energy = max(0.0, soc - battery.min_soc_kwh)
    return min(requested_kw, available_energy)


def _comfort_risk(point: ForecastPoint, adjusted_demand: float, controller: str) -> float:
    curtailment = max(0.0, point.demand_kw - adjusted_demand) / max(1.0, point.demand_kw)
    heat_stress = max(0.0, point.outside_temp_c - 27.0) / 10.0
    controller_penalty = 0.12 if controller == "optimized" and curtailment > 0 else 0.0
    return min(1.0, heat_stress * 0.55 + curtailment * 3.1 + controller_penalty)


def _metrics_dict(metrics: SimulationMetrics, baseline: SimulationMetrics) -> dict[str, float]:
    return {
        "total_cost_usd": metrics.total_cost_usd,
        "carbon_kg": metrics.carbon_kg,
        "peak_grid_kw": metrics.peak_grid_kw,
        "comfort_violation_hours": metrics.comfort_violation_hours,
        "battery_cycles": metrics.battery_cycles,
        "grid_import_kwh": metrics.grid_import_kwh,
        "grid_export_kwh": metrics.grid_export_kwh,
        "cost_savings_pct": _pct_delta(baseline.total_cost_usd, metrics.total_cost_usd),
        "carbon_reduction_pct": _pct_delta(baseline.carbon_kg, metrics.carbon_kg),
        "peak_reduction_pct": _pct_delta(baseline.peak_grid_kw, metrics.peak_grid_kw),
    }


def _pct_delta(before: float, after: float) -> float:
    if math.isclose(before, 0.0):
        return 0.0
    return round((before - after) / before * 100, 2)
