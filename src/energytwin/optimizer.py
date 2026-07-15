from __future__ import annotations

from .domain import BatterySpec, ForecastPoint


def baseline_schedule(forecast: list[ForecastPoint], battery: BatterySpec) -> list[float]:
    return [0.0 for _ in forecast]


def rule_schedule(forecast: list[ForecastPoint], battery: BatterySpec) -> list[float]:
    schedule: list[float] = []
    for point in forecast:
        net_load = point.demand_kw - point.solar_kw
        if point.solar_kw > point.demand_kw * 0.55 and point.hour in range(9, 16):
            schedule.append(-min(battery.max_kw, max(15.0, point.solar_kw - point.demand_kw * 0.35)))
        elif point.price_usd_per_kwh >= 0.30 or point.peak_risk > 0.65:
            schedule.append(min(battery.max_kw, max(20.0, net_load * 0.18)))
        else:
            schedule.append(0.0)
    return schedule


def optimized_schedule(forecast: list[ForecastPoint], battery: BatterySpec) -> list[float]:
    schedule = [0.0 for _ in forecast]
    soc = battery.initial_soc_kwh
    charge_hours = sorted(
        range(len(forecast)),
        key=lambda i: (forecast[i].price_usd_per_kwh - forecast[i].solar_kw / 1000, forecast[i].carbon_kg_per_kwh),
    )
    discharge_hours = sorted(
        range(len(forecast)),
        key=lambda i: (forecast[i].price_usd_per_kwh + forecast[i].peak_risk * 0.18 + forecast[i].carbon_kg_per_kwh * 0.08),
        reverse=True,
    )

    for i in charge_hours[:8]:
        if soc >= battery.max_soc_kwh:
            break
        amount = min(battery.max_kw, battery.max_soc_kwh - soc)
        if amount > 5:
            schedule[i] = -amount
            soc += amount * battery.roundtrip_efficiency

    for i in discharge_hours[:8]:
        if soc <= battery.min_soc_kwh:
            break
        amount = min(battery.max_kw, soc - battery.min_soc_kwh)
        if amount > 5:
            schedule[i] = amount
            soc -= amount

    return schedule


def demand_response_factor(point: ForecastPoint, controller: str) -> float:
    if controller != "optimized":
        return 1.0
    if point.price_usd_per_kwh >= 0.32 or point.peak_risk >= 0.7:
        return 0.94
    if point.carbon_kg_per_kwh >= 0.49 and 18 <= point.hour <= 22:
        return 0.97
    return 1.0
