from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .data import get_scenario
from .domain import BatterySpec, TariffSpec, serialize
from .forecasting import MODEL_TRAINED_HOURLY, MODEL_WEIGHTED, build_forecast, evaluate_forecast_baseline
from .ingestion import data_health
from .model_artifacts import (
    DEFAULT_CANDIDATE_FORECAST_MODEL_PATH,
    DEFAULT_FORECAST_MODEL_PATH,
    PromotionPolicy,
    decide_model_promotion,
    save_forecast_model,
    train_hourly_forecast_model,
)
from .simulator import compare_policies
from .sources import PROJECT_ROOT, load_history
from .storage import LOCAL_DB_PATH, latest_run_report, list_run_reports, list_run_summaries, save_run_report


LOCAL_RUNS_DIR = PROJECT_ROOT / "mlruns" / "local"


@dataclass(frozen=True)
class LocalRunConfig:
    source_key: str = "demo"
    scenario_key: str = "normal"
    model_name: str = "weighted-baseline-v1"
    demand_charge_usd_per_kw_day: float = 3.2
    export_credit_fraction: float = 0.32
    battery_wear_cost_usd_per_kwh: float = 0.018
    train_model: bool = False
    force_promote_model: bool = False
    min_promotion_improvement_pct: float = 0.02
    active_model_path: str = str(DEFAULT_FORECAST_MODEL_PATH)
    candidate_model_path: str = str(DEFAULT_CANDIDATE_FORECAST_MODEL_PATH)


def run_local_experiment(
    config: LocalRunConfig,
    output_dir: Path | str = LOCAL_RUNS_DIR,
    db_path: Path | str | None = LOCAL_DB_PATH,
) -> dict:
    scenario = get_scenario(config.scenario_key)
    history, source_label = load_history(source_key=config.source_key, scenario_key=config.scenario_key, scenario=scenario)
    trained_artifact = None
    candidate_model_path = None
    active_model_path = None
    candidate_metrics = None
    reference_metrics = None
    promotion = None
    if config.train_model:
        trained_artifact = train_hourly_forecast_model(history)
        candidate_model_path = save_forecast_model(trained_artifact, config.candidate_model_path)
        candidate_metrics = evaluate_forecast_baseline(history, model_name=MODEL_TRAINED_HOURLY)
        reference_metrics = evaluate_forecast_baseline(history, model_name=MODEL_WEIGHTED)
        promotion = decide_model_promotion(
            candidate_metrics,
            reference_metrics,
            PromotionPolicy(min_improvement_pct=config.min_promotion_improvement_pct),
        )
        if config.force_promote_model:
            promotion["promoted"] = True
            promotion["reason"] = "forced promotion requested"
        if promotion["promoted"]:
            active_model_path = save_forecast_model(trained_artifact, config.active_model_path)
    forecast_artifact = trained_artifact if config.train_model and config.model_name == MODEL_TRAINED_HOURLY else None
    forecast = build_forecast(
        history,
        scenario_key=config.scenario_key,
        scenario=scenario,
        model_name=config.model_name,
        model_artifact=forecast_artifact,
    )
    battery = BatterySpec(wear_cost_usd_per_kwh_throughput=config.battery_wear_cost_usd_per_kwh)
    tariff = TariffSpec(
        demand_charge_usd_per_kw_day=config.demand_charge_usd_per_kw_day,
        export_credit_fraction=config.export_credit_fraction,
    )
    forecast_metrics = evaluate_forecast_baseline(history, model_name=config.model_name)
    policy_comparison = compare_policies(forecast, battery=battery, tariff=tariff)
    health = data_health(history, source=source_label)

    report = {
        "run_id": _run_id(config),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": serialize(config),
        "source": source_label,
        "scenario": serialize(scenario),
        "data_health": serialize(health),
        "forecast_metrics": serialize(forecast_metrics),
        "policy_comparison": policy_comparison,
        "model_candidate": {
            "current": config.model_name,
            "target": "Temporal Fusion Transformer",
            "promotion_ready": bool(promotion and promotion["promoted"]),
            "reason": promotion["reason"] if promotion else "local baseline record only; no registry configured",
            "candidate_artifact_path": str(candidate_model_path) if candidate_model_path else None,
            "active_artifact_path": str(active_model_path) if active_model_path else None,
            "artifact_training_rows": trained_artifact["training_rows"] if trained_artifact else None,
            "candidate_metrics": serialize(candidate_metrics) if candidate_metrics else None,
            "reference_metrics": serialize(reference_metrics) if reference_metrics else None,
            "promotion": promotion,
        },
    }
    write_local_run(report, output_dir=output_dir, db_path=db_path)
    return report


def write_local_run(
    report: dict,
    output_dir: Path | str = LOCAL_RUNS_DIR,
    db_path: Path | str | None = LOCAL_DB_PATH,
) -> Path:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{report['run_id']}.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    latest = target_dir / "latest.json"
    latest.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    if db_path is not None:
        save_run_report(report, db_path=db_path)
    return target


def read_latest_local_run(
    output_dir: Path | str = LOCAL_RUNS_DIR,
    db_path: Path | str | None = LOCAL_DB_PATH,
) -> dict | None:
    if db_path is not None:
        stored = latest_run_report(db_path=db_path)
        if stored is not None:
            return stored
    latest = Path(output_dir) / "latest.json"
    if not latest.exists():
        return None
    return json.loads(latest.read_text(encoding="utf-8"))


def list_local_runs(limit: int = 20, db_path: Path | str = LOCAL_DB_PATH) -> list[dict]:
    return list_run_summaries(limit=limit, db_path=db_path)


def local_monitoring_summary(limit: int = 20, db_path: Path | str = LOCAL_DB_PATH) -> dict:
    reports = list_run_reports(limit=limit, db_path=db_path)
    if not reports:
        return {
            "run_count": 0,
            "status": "no-runs",
            "trend": [],
            "latest": None,
            "best": None,
            "promotion": {"candidate_runs": 0, "promoted": 0, "rejected": 0, "latest": None},
        }

    chronological = list(reversed(reports))
    trend = [_trend_point(report) for report in chronological]
    latest = trend[-1]
    previous = trend[-2] if len(trend) > 1 else None
    best = min(trend, key=lambda item: item["mae_kw"])
    delta_kw = round(latest["mae_kw"] - previous["mae_kw"], 2) if previous else 0.0
    delta_pct = round(delta_kw / previous["mae_kw"], 4) if previous and previous["mae_kw"] else 0.0
    status = _monitoring_status(delta_pct, len(trend))
    promotion = _promotion_summary(reports)

    return {
        "run_count": len(reports),
        "status": status,
        "latest": latest,
        "previous": previous,
        "best": best,
        "mae_delta_kw": delta_kw,
        "mae_delta_pct": delta_pct,
        "trend": trend,
        "promotion": promotion,
    }


def _run_id(config: LocalRunConfig) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}-{config.source_key}-{config.scenario_key}-{config.model_name}"


def _trend_point(report: dict) -> dict:
    metrics = report.get("forecast_metrics", {})
    promotion = report.get("model_candidate", {}).get("promotion") or {}
    return {
        "run_id": report["run_id"],
        "created_at": report["created_at"],
        "source_key": report.get("config", {}).get("source_key"),
        "scenario_key": report.get("config", {}).get("scenario_key"),
        "model_name": metrics.get("model_name", report.get("config", {}).get("model_name")),
        "mae_kw": float(metrics.get("mae_kw", 0.0)),
        "rmse_kw": float(metrics.get("rmse_kw", 0.0)),
        "smape": float(metrics.get("smape", 0.0)),
        "promoted": bool(promotion.get("promoted", False)),
        "promotion_reason": promotion.get("reason"),
    }


def _monitoring_status(delta_pct: float, run_count: int) -> str:
    if run_count < 2:
        return "insufficient-history"
    if delta_pct <= -0.02:
        return "improving"
    if delta_pct >= 0.02:
        return "degrading"
    return "stable"


def _promotion_summary(reports: list[dict]) -> dict:
    decisions = [
        report.get("model_candidate", {}).get("promotion")
        for report in reports
        if report.get("model_candidate", {}).get("promotion") is not None
    ]
    promoted = sum(1 for decision in decisions if decision.get("promoted"))
    rejected = sum(1 for decision in decisions if not decision.get("promoted"))
    latest = decisions[0] if decisions else None
    return {
        "candidate_runs": len(decisions),
        "promoted": promoted,
        "rejected": rejected,
        "latest": latest,
    }
