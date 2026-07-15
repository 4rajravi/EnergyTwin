from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .sources import PROJECT_ROOT


TRAINED_HOURLY_MODEL = "trained-hourly-v1"
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
