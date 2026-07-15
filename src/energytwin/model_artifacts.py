from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .sources import PROJECT_ROOT


TRAINED_HOURLY_MODEL = "trained-hourly-v1"
TRAINED_REGRESSION_MODEL = "trained-regression-v1"
TRAINED_MLP_MODEL = "trained-mlp-v1"
DEFAULT_FORECAST_MODEL_PATH = PROJECT_ROOT / "models" / "active-forecast-model.json"
DEFAULT_CANDIDATE_FORECAST_MODEL_PATH = PROJECT_ROOT / "models" / "candidate-forecast-model.json"


@dataclass(frozen=True)
class PromotionPolicy:
    metric: str = "mae_kw"
    min_improvement_pct: float = 0.02
    max_smape_regression_pct: float = 0.01


def train_hourly_forecast_model(history: list[dict], model_name: str = TRAINED_HOURLY_MODEL) -> dict[str, Any]:
    if not history:
        raise ValueError("cannot train forecast model with empty history")

    hourly: dict[str, dict[str, float]] = {}
    for hour in range(24):
        rows = [row for row in history if int(row["hour"]) == hour]
        if not rows:
            continue
        hourly[str(hour)] = {
            "demand_kw": _average(rows, "demand_kw"),
            "solar_kw": _average(rows, "solar_kw"),
            "outside_temp_c": _average(rows, "outside_temp_c"),
        }

    return {
        "model_name": model_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "training_rows": len(history),
        "features": ["hour", "outside_temp_c", "solar_kw"],
        "target": "demand_kw",
        "global": {
            "demand_kw": _average(history, "demand_kw"),
            "solar_kw": _average(history, "solar_kw"),
            "outside_temp_c": _average(history, "outside_temp_c"),
            "temp_sensitivity_kw_per_c": _temperature_sensitivity(history),
        },
        "hourly": hourly,
    }


def train_regression_forecast_model(history: list[dict], model_name: str = TRAINED_REGRESSION_MODEL) -> dict[str, Any]:
    if not history:
        raise ValueError("cannot train forecast model with empty history")

    feature_names = _regression_feature_names()
    x_rows = [_regression_features(int(row["hour"]), float(row["outside_temp_c"]), float(row["solar_kw"])) for row in history]
    y_values = [float(row["demand_kw"]) for row in history]
    coefficients = _ridge_regression(x_rows, y_values, regularization=0.08)
    residuals = [sum(coef * value for coef, value in zip(coefficients, features)) - actual for features, actual in zip(x_rows, y_values)]
    residual_mae = sum(abs(error) for error in residuals) / len(residuals)
    residual_rmse = math.sqrt(sum(error * error for error in residuals) / len(residuals))

    return {
        "model_name": model_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "training_rows": len(history),
        "features": feature_names,
        "target": "demand_kw",
        "coefficients": [round(value, 8) for value in coefficients],
        "residual_mae_kw": round(residual_mae, 4),
        "residual_rmse_kw": round(residual_rmse, 4),
        "solar_hourly": _hourly_stats(history, "solar_kw"),
        "global": {
            "demand_kw": _average(history, "demand_kw"),
            "solar_kw": _average(history, "solar_kw"),
            "outside_temp_c": _average(history, "outside_temp_c"),
        },
    }


def train_mlp_forecast_model(history: list[dict], model_name: str = TRAINED_MLP_MODEL) -> dict[str, Any]:
    if not history:
        raise ValueError("cannot train forecast model with empty history")

    training_rows = _sample_training_rows(history, max_rows=2000)
    feature_rows = [
        _mlp_features(int(row["hour"]), float(row["outside_temp_c"]), float(row["solar_kw"]))
        for row in training_rows
    ]
    y_values = [float(row["demand_kw"]) for row in training_rows]
    feature_means, feature_stds = _column_scaler(feature_rows)
    target_mean = sum(y_values) / len(y_values)
    target_std = _std(y_values, target_mean) or 1.0
    x_rows = [_scale_row(row, feature_means, feature_stds) for row in feature_rows]
    targets = [(value - target_mean) / target_std for value in y_values]

    hidden_1 = 8
    hidden_2 = 4
    w1 = _init_matrix(len(x_rows[0]), hidden_1, 0.18)
    b1 = [0.0 for _ in range(hidden_1)]
    w2 = _init_matrix(hidden_1, hidden_2, 0.16)
    b2 = [0.0 for _ in range(hidden_2)]
    w3 = _init_matrix(hidden_2, 1, 0.14)
    b3 = [0.0]

    training_epochs = 45
    for epoch in range(training_epochs):
        learning_rate = 0.018 / (1 + epoch / 45)
        for features, target in zip(x_rows, targets):
            h1_raw = [_dot(features, [w1[index][unit] for index in range(len(features))]) + b1[unit] for unit in range(hidden_1)]
            h1 = [math.tanh(value) for value in h1_raw]
            h2_raw = [_dot(h1, [w2[index][unit] for index in range(hidden_1)]) + b2[unit] for unit in range(hidden_2)]
            h2 = [math.tanh(value) for value in h2_raw]
            prediction = _dot(h2, [w3[index][0] for index in range(hidden_2)]) + b3[0]
            error = max(-4.0, min(4.0, prediction - target))

            d_w3 = [error * value for value in h2]
            d_b3 = error
            d_h2 = [error * w3[unit][0] * (1 - h2[unit] * h2[unit]) for unit in range(hidden_2)]
            d_w2 = [[d_h2[unit] * h1[index] for unit in range(hidden_2)] for index in range(hidden_1)]
            d_b2 = d_h2
            d_h1 = []
            for unit in range(hidden_1):
                downstream = sum(d_h2[next_unit] * w2[unit][next_unit] for next_unit in range(hidden_2))
                d_h1.append(downstream * (1 - h1[unit] * h1[unit]))
            d_w1 = [[d_h1[unit] * features[index] for unit in range(hidden_1)] for index in range(len(features))]
            d_b1 = d_h1

            for index in range(hidden_2):
                w3[index][0] -= learning_rate * d_w3[index]
            b3[0] -= learning_rate * d_b3
            for index in range(hidden_1):
                for unit in range(hidden_2):
                    w2[index][unit] -= learning_rate * d_w2[index][unit]
            for unit in range(hidden_2):
                b2[unit] -= learning_rate * d_b2[unit]
            for index in range(len(features)):
                for unit in range(hidden_1):
                    w1[index][unit] -= learning_rate * d_w1[index][unit]
            for unit in range(hidden_1):
                b1[unit] -= learning_rate * d_b1[unit]

    residuals = [
        predict_mlp_demand_from_weights(features, target_mean, target_std, w1, b1, w2, b2, w3, b3) - actual
        for features, actual in zip(x_rows, y_values)
    ]
    residual_mae = sum(abs(error) for error in residuals) / len(residuals)
    residual_rmse = math.sqrt(sum(error * error for error in residuals) / len(residuals))

    return {
        "model_name": model_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "training_rows": len(history),
        "fit_rows": len(training_rows),
        "architecture": {"type": "mlp", "hidden_layers": [hidden_1, hidden_2], "activation": "tanh"},
        "training_epochs": training_epochs,
        "features": _mlp_feature_names(),
        "target": "demand_kw",
        "feature_means": [round(value, 8) for value in feature_means],
        "feature_stds": [round(value, 8) for value in feature_stds],
        "target_mean": round(target_mean, 8),
        "target_std": round(target_std, 8),
        "weights": {
            "w1": _round_matrix(w1),
            "b1": _round_vector(b1),
            "w2": _round_matrix(w2),
            "b2": _round_vector(b2),
            "w3": _round_matrix(w3),
            "b3": _round_vector(b3),
        },
        "residual_mae_kw": round(residual_mae, 4),
        "residual_rmse_kw": round(residual_rmse, 4),
        "solar_hourly": _hourly_stats(history, "solar_kw"),
        "global": {
            "demand_kw": _average(history, "demand_kw"),
            "solar_kw": _average(history, "solar_kw"),
            "outside_temp_c": _average(history, "outside_temp_c"),
        },
    }


def train_forecast_model_artifact(history: list[dict], model_name: str) -> dict[str, Any]:
    if model_name == TRAINED_MLP_MODEL:
        return train_mlp_forecast_model(history)
    if model_name == TRAINED_REGRESSION_MODEL:
        return train_regression_forecast_model(history)
    if model_name == TRAINED_HOURLY_MODEL:
        return train_hourly_forecast_model(history)
    raise ValueError(f"unsupported trainable forecast model: {model_name}")


def is_trainable_model(model_name: str) -> bool:
    return model_name in {TRAINED_HOURLY_MODEL, TRAINED_REGRESSION_MODEL, TRAINED_MLP_MODEL}


def predict_regression_demand(artifact: dict[str, Any], hour: int, outside_temp_c: float, solar_kw: float) -> float:
    coefficients = [float(value) for value in artifact.get("coefficients", [])]
    features = _regression_features(hour, outside_temp_c, solar_kw)
    if len(coefficients) != len(features):
        return float(artifact.get("global", {}).get("demand_kw", 0.0))
    return sum(coef * value for coef, value in zip(coefficients, features))


def predict_regression_solar(artifact: dict[str, Any], hour: int, scenario_solar_kw: float) -> float:
    hourly = artifact.get("solar_hourly", {})
    historical = float(hourly.get(str(hour), artifact.get("global", {}).get("solar_kw", scenario_solar_kw)))
    return max(0.0, historical * 0.55 + scenario_solar_kw * 0.45)


def predict_mlp_demand(artifact: dict[str, Any], hour: int, outside_temp_c: float, solar_kw: float) -> float:
    means = [float(value) for value in artifact.get("feature_means", [])]
    stds = [float(value) for value in artifact.get("feature_stds", [])]
    raw_features = _mlp_features(hour, outside_temp_c, solar_kw)
    weights = artifact.get("weights", {})
    if len(means) != len(raw_features) or len(stds) != len(raw_features):
        return float(artifact.get("global", {}).get("demand_kw", 0.0))
    try:
        scaled = _scale_row(raw_features, means, stds)
        prediction = predict_mlp_demand_from_weights(
            scaled,
            float(artifact.get("target_mean", 0.0)),
            float(artifact.get("target_std", 1.0)),
            weights["w1"],
            weights["b1"],
            weights["w2"],
            weights["b2"],
            weights["w3"],
            weights["b3"],
        )
    except (KeyError, TypeError, ValueError):
        return float(artifact.get("global", {}).get("demand_kw", 0.0))
    return max(0.0, prediction)


def predict_mlp_solar(artifact: dict[str, Any], hour: int, scenario_solar_kw: float) -> float:
    return predict_regression_solar(artifact, hour, scenario_solar_kw)


def save_forecast_model(artifact: dict[str, Any], path: Path | str = DEFAULT_FORECAST_MODEL_PATH) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(artifact, indent=2, sort_keys=True), encoding="utf-8")
    return target


def load_forecast_model(path: Path | str = DEFAULT_FORECAST_MODEL_PATH) -> dict[str, Any] | None:
    target = Path(path)
    if not target.exists():
        return None
    return json.loads(target.read_text(encoding="utf-8"))


def forecast_model_summary(path: Path | str = DEFAULT_FORECAST_MODEL_PATH) -> dict[str, Any]:
    artifact = load_forecast_model(path)
    if artifact is None:
        return {"available": False, "path": str(path)}
    return {
        "available": True,
        "path": str(path),
        "model_name": artifact.get("model_name"),
        "created_at": artifact.get("created_at"),
        "training_rows": artifact.get("training_rows"),
        "features": artifact.get("features", []),
    }


def decide_model_promotion(
    candidate_metrics: Any,
    reference_metrics: Any,
    policy: PromotionPolicy = PromotionPolicy(),
) -> dict[str, Any]:
    candidate_value = _metric_value(candidate_metrics, policy.metric)
    reference_value = _metric_value(reference_metrics, policy.metric)
    candidate_smape = _metric_value(candidate_metrics, "smape")
    reference_smape = _metric_value(reference_metrics, "smape")

    if reference_value <= 0:
        improvement_pct = 1.0 if candidate_value < reference_value else 0.0
    else:
        improvement_pct = (reference_value - candidate_value) / reference_value

    smape_regression_pct = 0.0
    if reference_smape > 0:
        smape_regression_pct = max(0.0, (candidate_smape - reference_smape) / reference_smape)

    promoted = (
        improvement_pct >= policy.min_improvement_pct
        and smape_regression_pct <= policy.max_smape_regression_pct
    )
    if promoted:
        reason = f"candidate improved {policy.metric} by {improvement_pct:.2%}"
    elif improvement_pct < policy.min_improvement_pct:
        reason = f"candidate did not meet {policy.min_improvement_pct:.2%} {policy.metric} improvement threshold"
    else:
        reason = f"candidate sMAPE regression {smape_regression_pct:.2%} exceeded threshold"

    return {
        "promoted": promoted,
        "reason": reason,
        "metric": policy.metric,
        "min_improvement_pct": policy.min_improvement_pct,
        "candidate_value": round(candidate_value, 4),
        "reference_value": round(reference_value, 4),
        "improvement_pct": round(improvement_pct, 4),
        "candidate_smape": round(candidate_smape, 4),
        "reference_smape": round(reference_smape, 4),
        "smape_regression_pct": round(smape_regression_pct, 4),
    }


def _average(rows: list[dict], field: str) -> float:
    return round(sum(float(row[field]) for row in rows) / len(rows), 4)


def _hourly_stats(history: list[dict], field: str) -> dict[str, float]:
    stats: dict[str, float] = {}
    for hour in range(24):
        rows = [row for row in history if int(row["hour"]) == hour]
        if rows:
            stats[str(hour)] = _average(rows, field)
    return stats


def _metric_value(metrics: Any, name: str) -> float:
    if isinstance(metrics, dict):
        return float(metrics[name])
    return float(getattr(metrics, name))


def _temperature_sensitivity(history: list[dict]) -> float:
    xs = [max(0.0, float(row["outside_temp_c"]) - 22.0) for row in history]
    ys = [float(row["demand_kw"]) for row in history]
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    variance = sum((x - x_mean) ** 2 for x in xs)
    if variance <= 1e-9:
        return 0.0
    covariance = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    return round(max(0.0, min(30.0, covariance / variance)), 4)


def _regression_feature_names() -> list[str]:
    return [
        "intercept",
        "hour_sin",
        "hour_cos",
        "hour_2_sin",
        "hour_2_cos",
        "outside_temp_c",
        "cooling_degree_c",
        "solar_kw",
        "morning_peak",
        "afternoon_peak",
        "evening_peak",
    ]


def _regression_features(hour: int, outside_temp_c: float, solar_kw: float) -> list[float]:
    radians = 2 * math.pi * hour / 24
    double_radians = 2 * radians
    return [
        1.0,
        math.sin(radians),
        math.cos(radians),
        math.sin(double_radians),
        math.cos(double_radians),
        outside_temp_c,
        max(0.0, outside_temp_c - 22.0),
        solar_kw,
        math.exp(-((hour - 10) ** 2) / 20),
        math.exp(-((hour - 15) ** 2) / 12),
        math.exp(-((hour - 19) ** 2) / 10),
    ]


def _mlp_feature_names() -> list[str]:
    return _regression_feature_names()[1:]


def _mlp_features(hour: int, outside_temp_c: float, solar_kw: float) -> list[float]:
    return _regression_features(hour, outside_temp_c, solar_kw)[1:]


def _sample_training_rows(rows: list[dict], max_rows: int) -> list[dict]:
    if len(rows) <= max_rows:
        return rows
    step = (len(rows) - 1) / (max_rows - 1)
    return [rows[round(index * step)] for index in range(max_rows)]


def _column_scaler(rows: list[list[float]]) -> tuple[list[float], list[float]]:
    width = len(rows[0])
    means = [sum(row[index] for row in rows) / len(rows) for index in range(width)]
    stds = [_std([row[index] for row in rows], means[index]) or 1.0 for index in range(width)]
    return means, stds


def _scale_row(row: list[float], means: list[float], stds: list[float]) -> list[float]:
    return [(value - mean) / std if std else 0.0 for value, mean, std in zip(row, means, stds)]


def _std(values: list[float], mean: float) -> float:
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _init_matrix(rows: int, columns: int, scale: float) -> list[list[float]]:
    return [
        [math.sin((row + 1) * (column + 3)) * scale for column in range(columns)]
        for row in range(rows)
    ]


def _dot(left: list[float], right: list[float]) -> float:
    return sum(left_value * right_value for left_value, right_value in zip(left, right))


def predict_mlp_demand_from_weights(
    features: list[float],
    target_mean: float,
    target_std: float,
    w1: list[list[float]],
    b1: list[float],
    w2: list[list[float]],
    b2: list[float],
    w3: list[list[float]],
    b3: list[float],
) -> float:
    hidden_1 = len(b1)
    hidden_2 = len(b2)
    h1 = [
        math.tanh(_dot(features, [float(w1[index][unit]) for index in range(len(features))]) + float(b1[unit]))
        for unit in range(hidden_1)
    ]
    h2 = [
        math.tanh(_dot(h1, [float(w2[index][unit]) for index in range(hidden_1)]) + float(b2[unit]))
        for unit in range(hidden_2)
    ]
    scaled_prediction = _dot(h2, [float(w3[index][0]) for index in range(hidden_2)]) + float(b3[0])
    return scaled_prediction * target_std + target_mean


def _round_matrix(values: list[list[float]]) -> list[list[float]]:
    return [[round(value, 8) for value in row] for row in values]


def _round_vector(values: list[float]) -> list[float]:
    return [round(value, 8) for value in values]


def _ridge_regression(x_rows: list[list[float]], y_values: list[float], regularization: float) -> list[float]:
    width = len(x_rows[0])
    xtx = [[0.0 for _ in range(width)] for _ in range(width)]
    xty = [0.0 for _ in range(width)]
    for row, target in zip(x_rows, y_values):
        for i, value_i in enumerate(row):
            xty[i] += value_i * target
            for j, value_j in enumerate(row):
                xtx[i][j] += value_i * value_j
    for index in range(width):
        xtx[index][index] += regularization
    return _solve_linear_system(xtx, xty)


def _solve_linear_system(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [row[:] + [value] for row, value in zip(matrix, vector)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row_index: abs(augmented[row_index][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            continue
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        pivot_value = augmented[column][column]
        augmented[column] = [value / pivot_value for value in augmented[column]]
        for row_index in range(size):
            if row_index == column:
                continue
            factor = augmented[row_index][column]
            augmented[row_index] = [
                current - factor * pivot_current
                for current, pivot_current in zip(augmented[row_index], augmented[column])
            ]
    return [augmented[index][-1] for index in range(size)]
