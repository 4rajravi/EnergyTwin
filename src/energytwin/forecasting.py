from __future__ import annotations

import math
from datetime import datetime, timedelta

from .data import PROFILE, get_scenario, price, solar_shape, weather_temp
from .domain import ForecastMetrics, ForecastPoint, Scenario


MODEL_SEASONAL = "seasonal"
MODEL_WEIGHTED = "weighted-baseline-v1"


def _hourly_average(history: list[dict], field: str, hour: int) -> float:
    values = [float(row[field]) for row in history if int(row["hour"]) == hour]
    return sum(values) / len(values) if values else 0.0


def build_forecast(
    history: list[dict],
    scenario_key: str = "normal",
    horizon_hours: int = 24,
    scenario: Scenario | None = None,
    model_name: str = MODEL_WEIGHTED,
) -> list[ForecastPoint]:
    scenario = scenario or get_scenario(scenario_key)
    last_ts = datetime.fromisoformat(str(history[-1]["timestamp"]))
    points: list[ForecastPoint] = []

    for step in range(1, horizon_hours + 1):
        ts = last_ts + timedelta(hours=step)
        hour = ts.hour
        day_index = (len(history) + step) // 24
        temp = weather_temp(hour, day_index, scenario)
        baseline = _predict_demand(history, hour, temp, model_name)
        cooling_delta = max(0.0, temp - 22.0) * 9.5
        ev = scenario.ev_spike_kw if 17 <= hour <= 20 else 0.0
        demand = max(PROFILE.base_kw, baseline + _scenario_demand_adjustment(model_name, cooling_delta) + ev)
        solar = _predict_solar(history, hour, scenario.cloud_cover, model_name)
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


def evaluate_forecast_baseline(
    history: list[dict],
    model_name: str = MODEL_WEIGHTED,
    horizon_hours: int = 24,
    min_train_hours: int = 72,
) -> ForecastMetrics:
    errors: list[float] = []
    squared_errors: list[float] = []
    smape_terms: list[float] = []
    covered = 0
    evaluated = 0

    if len(history) <= min_train_hours:
        return ForecastMetrics(model_name, horizon_hours, 0, 0.0, 0.0, 0.0, 0.0, 0.0)

    for index in range(min_train_hours, len(history)):
        train = history[:index]
        actual = float(history[index]["demand_kw"])
        prediction = build_forecast(train, horizon_hours=1, model_name=model_name)[0]
        error = prediction.demand_kw - actual
        errors.append(error)
        squared_errors.append(error * error)
        denominator = (abs(prediction.demand_kw) + abs(actual)) / 2
        if denominator:
            smape_terms.append(abs(error) / denominator)
        if prediction.demand_p10_kw <= actual <= prediction.demand_p90_kw:
            covered += 1
        evaluated += 1

    mae = sum(abs(error) for error in errors) / evaluated
    rmse = math.sqrt(sum(squared_errors) / evaluated)
    bias = sum(errors) / evaluated
    smape = sum(smape_terms) / len(smape_terms) if smape_terms else 0.0

    return ForecastMetrics(
        model_name=model_name,
        horizon_hours=horizon_hours,
        evaluated_points=evaluated,
        mae_kw=round(mae, 2),
        rmse_kw=round(rmse, 2),
        smape=round(smape, 4),
        bias_kw=round(bias, 2),
        coverage_p10_p90=round(covered / evaluated, 4),
    )


def model_status(history_rows: int, metrics: ForecastMetrics | None = None) -> dict[str, object]:
    metrics = metrics or ForecastMetrics(MODEL_WEIGHTED, 24, 0, 0.0, 0.0, 0.0, 0.0, 0.0)
    return {
        "active_model": metrics.model_name,
        "target_model": "Temporal Fusion Transformer",
        "stage": "Measured baseline, TFT-ready contract",
        "forecast_horizon_hours": 24,
        "training_rows": history_rows,
        "evaluated_points": metrics.evaluated_points,
        "last_training_run": "local-backtest",
        "freshness": "local",
        "mae_kw": metrics.mae_kw,
        "rmse_kw": metrics.rmse_kw,
        "smape": metrics.smape,
        "bias_kw": metrics.bias_kw,
        "coverage_p10_p90": metrics.coverage_p10_p90,
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


def _predict_demand(history: list[dict], hour: int, forecast_temp: float, model_name: str) -> float:
    seasonal = _hourly_average(history, "demand_kw", hour)
    if model_name == MODEL_SEASONAL:
        return seasonal

    same_hour_values = [float(row["demand_kw"]) for row in history if int(row["hour"]) == hour]
    recent_same_hour = same_hour_values[-1] if same_hour_values else seasonal
    recent_window = history[-24:] if len(history) >= 24 else history
    recent_level = sum(float(row["demand_kw"]) for row in recent_window) / len(recent_window)
    long_level = sum(float(row["demand_kw"]) for row in history) / len(history)
    level_adjustment = recent_level - long_level
    temp_sensitivity = _temperature_sensitivity(history)
    historical_temp = _hourly_average(history, "outside_temp_c", hour)
    weather_adjustment = temp_sensitivity * (forecast_temp - historical_temp)
    return seasonal * 0.62 + recent_same_hour * 0.28 + (seasonal + level_adjustment) * 0.10 + weather_adjustment


def _predict_solar(history: list[dict], hour: int, cloud_cover: float, model_name: str) -> float:
    scenario_solar = PROFILE.solar_kwp * solar_shape(hour) * (1 - cloud_cover * 0.82)
    if model_name == MODEL_SEASONAL:
        return scenario_solar

    historical = _hourly_average(history, "solar_kw", hour)
    if historical <= 0 and scenario_solar <= 0:
        return 0.0
    return max(0.0, historical * 0.55 + scenario_solar * 0.45)


def _temperature_sensitivity(history: list[dict]) -> float:
    xs = [max(0.0, float(row["outside_temp_c"]) - 22.0) for row in history]
    ys = [float(row["demand_kw"]) for row in history]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    variance = sum((x - x_mean) ** 2 for x in xs)
    if variance <= 1e-9:
        return 0.0
    covariance = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    return max(0.0, min(25.0, covariance / variance))


def _scenario_demand_adjustment(model_name: str, cooling_delta: float) -> float:
    if model_name == MODEL_SEASONAL:
        return cooling_delta
    return cooling_delta * 0.35
