from __future__ import annotations

from .domain import BatterySpec, ForecastPoint, TariffSpec


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


def optimized_schedule(
    forecast: list[ForecastPoint],
    battery: BatterySpec,
    tariff: TariffSpec | None = None,
) -> list[float]:
    tariff = tariff or TariffSpec()
    schedule = [0.0 for _ in forecast]
    soc = battery.initial_soc_kwh
    wear_penalty = battery.wear_cost_usd_per_kwh_throughput
    demand_weight = min(0.35, tariff.demand_charge_usd_per_kw_day / 40.0)
    charge_hours = sorted(
        range(len(forecast)),
        key=lambda i: (
            forecast[i].price_usd_per_kwh - tariff.export_credit_fraction * forecast[i].solar_kw / 1000,
            forecast[i].carbon_kg_per_kwh,
        ),
    )
    discharge_hours = sorted(
        range(len(forecast)),
        key=lambda i: _discharge_value(forecast[i], demand_weight, wear_penalty),
        reverse=True,
    )

    charge_slots = 6 if wear_penalty >= 0.08 else 8
    discharge_slots = 6 if wear_penalty >= 0.08 else 8
    for i in charge_hours[:charge_slots]:
        if soc >= battery.max_soc_kwh:
            break
        amount = min(battery.max_kw, battery.max_soc_kwh - soc)
        if amount > 5:
            schedule[i] = -amount
            soc += amount * battery.roundtrip_efficiency

    for i in discharge_hours[:discharge_slots]:
        if soc <= battery.min_soc_kwh:
            break
        if _discharge_value(forecast[i], demand_weight, wear_penalty) <= wear_penalty:
            continue
        amount = min(battery.max_kw, soc - battery.min_soc_kwh)
        if tariff.demand_charge_usd_per_kw_day >= 6.0:
            projected_net = max(0.0, forecast[i].demand_kw - forecast[i].solar_kw)
            target_net = _target_peak_kw(forecast)
            amount = min(amount, max(0.0, projected_net - target_net))
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


def _discharge_value(point: ForecastPoint, demand_weight: float, wear_penalty: float) -> float:
    return (
        point.price_usd_per_kwh
        + point.peak_risk * (0.18 + demand_weight)
        + point.carbon_kg_per_kwh * 0.08
        - wear_penalty * 0.35
    )


def _target_peak_kw(forecast: list[ForecastPoint]) -> float:
    net_loads = sorted((max(0.0, point.demand_kw - point.solar_kw) for point in forecast), reverse=True)
    if len(net_loads) < 4:
        return net_loads[-1] if net_loads else 0.0
    return net_loads[3]
