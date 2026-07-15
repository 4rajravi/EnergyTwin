from __future__ import annotations

import os
from pathlib import Path
from typing import Any


MLFLOW_URI_ENV = "ENERGYTWIN_MLFLOW_TRACKING_URI"
MLFLOW_EXPERIMENT_ENV = "ENERGYTWIN_MLFLOW_EXPERIMENT"
MLFLOW_REGISTER_ENV = "ENERGYTWIN_MLFLOW_REGISTER"
MLFLOW_MODEL_NAME_ENV = "ENERGYTWIN_MLFLOW_MODEL_NAME"


def mlflow_enabled() -> bool:
    return bool(os.getenv(MLFLOW_URI_ENV))


def log_mlflow_run(report: dict[str, Any]) -> dict[str, Any]:
    if not mlflow_enabled():
        return {"enabled": False, "reason": f"{MLFLOW_URI_ENV} not set"}

    mlflow = _import_mlflow()
    mlflow.set_tracking_uri(os.environ[MLFLOW_URI_ENV])
    mlflow.set_experiment(os.getenv(MLFLOW_EXPERIMENT_ENV, "energytwin"))

    with mlflow.start_run(run_name=report["run_id"]) as run:
        config = report.get("config", {})
        metrics = report.get("forecast_metrics", {})
        optimized = report.get("policy_comparison", {}).get("optimized", {})
        for key, value in config.items():
            if isinstance(value, (str, int, float, bool)):
                mlflow.log_param(key, value)
        for key in ("mae_kw", "rmse_kw", "smape", "bias_kw", "coverage_p10_p90"):
            if metrics.get(key) is not None:
                mlflow.log_metric(key, float(metrics[key]))
        for key in ("cost_savings_pct", "carbon_reduction_pct", "peak_reduction_pct"):
            if optimized.get(key) is not None:
                mlflow.log_metric(key, float(optimized[key]))

        candidate_path = report.get("model_candidate", {}).get("candidate_artifact_path")
        if candidate_path and Path(candidate_path).exists():
            mlflow.log_artifact(candidate_path, artifact_path="candidate_model")
            if os.getenv(MLFLOW_REGISTER_ENV) == "1":
                name = os.getenv(MLFLOW_MODEL_NAME_ENV, "EnergyTwinForecast")
                mlflow.register_model(f"runs:/{run.info.run_id}/candidate_model", name)

    return {"enabled": True, "run_id": run.info.run_id, "tracking_uri": os.environ[MLFLOW_URI_ENV]}


def _import_mlflow():
    try:
        import mlflow  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "MLflow registry requires the optional dependency: python3 -m pip install mlflow"
        ) from exc
    return mlflow
