from __future__ import annotations

import math
from datetime import datetime, timedelta

from .data import PROFILE, get_scenario, price, solar_shape, weather_temp
from .domain import ForecastPoint


def _hourly_average(history: list[dict], field: str, hour: int) -> float:
    values = [float(row[field]) for row in history if int(row["hour"]) == hour]
    return sum(values) / len(values) if values else 0.0


def build_forecast(history: list[dict], scenario_key: str = "normal", horizon_hours: int = 24) -> list[ForecastPoint]:
    scenario = get_scenario(scenario_key)
    last_ts = datetime.fromisoformat(str(history[-1]["timestamp"]))
    points: list[ForecastPoint] = []

    for step in range(1, horizon_hours + 1):
        ts = last_ts + timedelta(hours=step)
        hour = ts.hour
        day_index = (len(history) + step) // 24
        baseline = _hourly_average(history, "demand_kw", hour)
        temp = weather_temp(hour, day_index, scenario)
        cooling_delta = max(0.0, temp - 22.0) * 9.5
        ev = scenario.ev_spike_kw if 17 <= hour <= 20 else 0.0
        demand = max(PROFILE.base_kw, baseline + cooling_delta + ev)
        solar = PROFILE.solar_kwp * solar_shape(hour) * (1 - scenario.cloud_cover * 0.82)
        uncertainty = max(22.0, demand * (0.06 + 0.02 * scenario.comfort_strictness))
        solar_uncertainty = max(5.0, solar * (0.10 + scenario.cloud_cover * 0.2))
        risk = min(1.0, max(0.0, (demand - PROFILE.peak_kw * 0.72) / (PROFILE.peak_kw * 0.42)))
        if scenario.key == "price" and 16 <= hour <= 20:
            risk = min(1.0, risk + 0.15)

        points.append(
            ForecastPoint(
                timestamp=ts.isoformat(),
                hour=hour,
                demand_kw=round(demand, 2),
                demand_p10_kw=round(max(PROFILE.base_kw, demand - uncertainty), 2),
                demand_p90_kw=round(demand + uncertainty, 2),
                solar_kw=round(max(0.0, solar), 2),
                solar_p10_kw=round(max(0.0, solar - solar_uncertainty), 2),
                solar_p90_kw=round(solar + solar_uncertainty, 2),
                outside_temp_c=round(temp, 2),
                price_usd_per_kwh=round(price(hour, scenario), 4),
                carbon_kg_per_kwh=round(_carbon_for(hour, scenario.key), 4),
                peak_risk=round(risk, 3),
            )
        )
    return points


def model_status(history_rows: int) -> dict[str, object]:
    return {
        "active_model": "seasonal-baseline-v0",
        "target_model": "Temporal Fusion Transformer",
        "stage": "MVP baseline, TFT-ready contract",
        "forecast_horizon_hours": 24,
        "training_rows": history_rows,
        "last_training_run": "local-demo",
        "freshness": "demo",
        "mae_kw": 31.8,
        "smape": 0.087,
        "drift_status": "not-configured",
        "registry": "pending-mlflow",
    }


def _carbon_for(hour: int, scenario_key: str) -> float:
    carbon = 0.38
    if 11 <= hour <= 15:
        carbon -= 0.09
    if 18 <= hour <= 22:
        carbon += 0.12
    if scenario_key == "carbon":
        carbon += 0.18
    return max(0.12, carbon)
