from __future__ import annotations

import math
from datetime import datetime, timedelta

from .data import PROFILE, get_scenario, price, solar_shape, weather_temp
from .domain import ForecastMetrics, ForecastPoint, Scenario
from .model_artifacts import (
    TRAINED_HOURLY_MODEL,
    TRAINED_MLP_MODEL,
    TRAINED_REGRESSION_MODEL,
    forecast_model_summary,
    is_trainable_model,
    load_forecast_model,
    predict_mlp_demand,
    predict_mlp_solar,
    predict_regression_demand,
    predict_regression_solar,
    train_forecast_model_artifact,
)


MODEL_SEASONAL = "seasonal"
MODEL_WEIGHTED = "weighted-baseline-v1"
MODEL_TRAINED_HOURLY = TRAINED_HOURLY_MODEL
MODEL_TRAINED_REGRESSION = TRAINED_REGRESSION_MODEL
MODEL_TRAINED_MLP = TRAINED_MLP_MODEL


def _hourly_average(history: list[dict], field: str, hour: int) -> float:
    values = [float(row[field]) for row in history if int(row["hour"]) == hour]
    return sum(values) / len(values) if values else 0.0


def build_forecast(
    history: list[dict],
    scenario_key: str = "normal",
    horizon_hours: int = 24,
    scenario: Scenario | None = None,
    model_name: str = MODEL_WEIGHTED,
    model_artifact: dict | None = None,
) -> list[ForecastPoint]:
    scenario = scenario or get_scenario(scenario_key)
    if is_trainable_model(model_name) and model_artifact is None:
        loaded_artifact = load_forecast_model()
        model_artifact = loaded_artifact if loaded_artifact and loaded_artifact.get("model_name") == model_name else train_forecast_model_artifact(history, model_name)
    last_ts = datetime.fromisoformat(str(history[-1]["timestamp"]))
    points: list[ForecastPoint] = []

    for step in range(1, horizon_hours + 1):
        ts = last_ts + timedelta(hours=step)
        hour = ts.hour
        day_index = (len(history) + step) // 24
        temp = weather_temp(hour, day_index, scenario)
        scenario_solar = PROFILE.solar_kwp * solar_shape(hour) * (1 - scenario.cloud_cover * 0.82)
        baseline = _predict_demand(history, hour, temp, model_name, model_artifact=model_artifact, scenario_solar_kw=scenario_solar)
        cooling_delta = max(0.0, temp - 22.0) * 9.5
        ev = scenario.ev_spike_kw if 17 <= hour <= 20 else 0.0
        demand = max(PROFILE.base_kw, baseline + _scenario_demand_adjustment(model_name, cooling_delta) + ev)
        solar = _predict_solar(history, hour, scenario.cloud_cover, model_name, model_artifact=model_artifact)
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
    max_evaluation_points: int | None = None,
) -> ForecastMetrics:
    errors: list[float] = []
    squared_errors: list[float] = []
    smape_terms: list[float] = []
    covered = 0
    evaluated = 0

    if len(history) <= min_train_hours:
        return ForecastMetrics(model_name, horizon_hours, 0, 0.0, 0.0, 0.0, 0.0, 0.0)

    indices = _evaluation_indices(min_train_hours, len(history), max_evaluation_points or _default_evaluation_limit(model_name))
    if not indices:
        return ForecastMetrics(model_name, horizon_hours, 0, 0.0, 0.0, 0.0, 0.0, 0.0)
    if model_name == MODEL_TRAINED_MLP and len(history) > 1000:
        return _evaluate_holdout(history, model_name, min(len(indices), horizon_hours), min_train_hours)
    for index in indices:
        train = history[:index]
        actual = float(history[index]["demand_kw"])
        artifact = train_forecast_model_artifact(train, model_name) if is_trainable_model(model_name) else None
        prediction = build_forecast(train, horizon_hours=1, model_name=model_name, model_artifact=artifact)[0]
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


def _evaluate_holdout(
    history: list[dict],
    model_name: str,
    horizon_hours: int,
    min_train_hours: int,
) -> ForecastMetrics:
    if len(history) <= min_train_hours + horizon_hours:
        return ForecastMetrics(model_name, horizon_hours, 0, 0.0, 0.0, 0.0, 0.0, 0.0)
    train = history[:-horizon_hours]
    actual_rows = history[-horizon_hours:]
    artifact = train_forecast_model_artifact(train, model_name) if is_trainable_model(model_name) else None
    predictions = build_forecast(train, horizon_hours=horizon_hours, model_name=model_name, model_artifact=artifact)
    errors: list[float] = []
    squared_errors: list[float] = []
    smape_terms: list[float] = []
    covered = 0
    for prediction, actual_row in zip(predictions, actual_rows):
        actual = float(actual_row["demand_kw"])
        error = prediction.demand_kw - actual
        errors.append(error)
        squared_errors.append(error * error)
        denominator = (abs(prediction.demand_kw) + abs(actual)) / 2
        if denominator:
            smape_terms.append(abs(error) / denominator)
        if prediction.demand_p10_kw <= actual <= prediction.demand_p90_kw:
            covered += 1

    evaluated = len(errors)
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


def _default_evaluation_limit(model_name: str) -> int | None:
    if model_name == MODEL_TRAINED_MLP:
        return 24
    return None


def _evaluation_indices(min_train_hours: int, history_length: int, max_points: int | None) -> list[int]:
    indices = list(range(min_train_hours, history_length))
    if max_points is None or len(indices) <= max_points:
        return indices
    if max_points <= 0:
        return []
    step = (len(indices) - 1) / (max_points - 1) if max_points > 1 else len(indices)
    return [indices[round(position * step)] for position in range(max_points)]


def model_status(history_rows: int, metrics: ForecastMetrics | None = None) -> dict[str, object]:
    metrics = metrics or ForecastMetrics(MODEL_WEIGHTED, 24, 0, 0.0, 0.0, 0.0, 0.0, 0.0)
    return {
        "active_model": metrics.model_name,
        "target_model": "Temporal Fusion Transformer",
        "stage": "Measured baseline, regression artifact, local MLP, TFT-ready contract",
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
        "registry": "local-json-artifact" if is_trainable_model(metrics.model_name) else "pending-mlflow",
        "artifact": forecast_model_summary(),
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


def _predict_demand(
    history: list[dict],
    hour: int,
    forecast_temp: float,
    model_name: str,
    model_artifact: dict | None = None,
    scenario_solar_kw: float | None = None,
) -> float:
    if model_name == MODEL_TRAINED_REGRESSION and model_artifact is not None:
        scenario_solar = PROFILE.solar_kwp * solar_shape(hour) if scenario_solar_kw is None else scenario_solar_kw
        return predict_regression_demand(model_artifact, hour, forecast_temp, scenario_solar)

    if model_name == MODEL_TRAINED_MLP and model_artifact is not None:
        scenario_solar = PROFILE.solar_kwp * solar_shape(hour) if scenario_solar_kw is None else scenario_solar_kw
        return predict_mlp_demand(model_artifact, hour, forecast_temp, scenario_solar)

    if model_name == MODEL_TRAINED_HOURLY and model_artifact is not None:
        hourly = model_artifact.get("hourly", {}).get(str(hour), {})
        global_stats = model_artifact.get("global", {})
        seasonal = float(hourly.get("demand_kw", global_stats.get("demand_kw", PROFILE.base_kw)))
        historical_temp = float(hourly.get("outside_temp_c", global_stats.get("outside_temp_c", forecast_temp)))
        sensitivity = float(global_stats.get("temp_sensitivity_kw_per_c", 0.0))
        return seasonal + sensitivity * (forecast_temp - historical_temp)

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


def _predict_solar(
    history: list[dict],
    hour: int,
    cloud_cover: float,
    model_name: str,
    model_artifact: dict | None = None,
) -> float:
    scenario_solar = PROFILE.solar_kwp * solar_shape(hour) * (1 - cloud_cover * 0.82)
    if model_name == MODEL_SEASONAL:
        return scenario_solar
    if model_name == MODEL_TRAINED_REGRESSION and model_artifact is not None:
        return predict_regression_solar(model_artifact, hour, scenario_solar)
    if model_name == MODEL_TRAINED_MLP and model_artifact is not None:
        return predict_mlp_solar(model_artifact, hour, scenario_solar)
    if model_name == MODEL_TRAINED_HOURLY and model_artifact is not None:
        hourly = model_artifact.get("hourly", {}).get(str(hour), {})
        historical = float(hourly.get("solar_kw", scenario_solar))
        return max(0.0, historical * 0.65 + scenario_solar * 0.35)

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
    if model_name in {MODEL_TRAINED_HOURLY, MODEL_TRAINED_REGRESSION, MODEL_TRAINED_MLP}:
        return 0.0
    return cooling_delta * 0.35
