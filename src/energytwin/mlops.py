from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .data import get_scenario
from .domain import BatterySpec, TariffSpec, serialize
from .forecasting import build_forecast, evaluate_forecast_baseline
from .ingestion import data_health
from .simulator import compare_policies
from .sources import PROJECT_ROOT, load_history
from .storage import LOCAL_DB_PATH, latest_run_report, list_run_summaries, save_run_report


LOCAL_RUNS_DIR = PROJECT_ROOT / "mlruns" / "local"


@dataclass(frozen=True)
class LocalRunConfig:
    source_key: str = "demo"
    scenario_key: str = "normal"
    model_name: str = "weighted-baseline-v1"
    demand_charge_usd_per_kw_day: float = 3.2
    export_credit_fraction: float = 0.32
    battery_wear_cost_usd_per_kwh: float = 0.018


def run_local_experiment(
    config: LocalRunConfig,
    output_dir: Path | str = LOCAL_RUNS_DIR,
    db_path: Path | str | None = LOCAL_DB_PATH,
) -> dict:
    scenario = get_scenario(config.scenario_key)
    history, source_label = load_history(source_key=config.source_key, scenario_key=config.scenario_key, scenario=scenario)
    forecast = build_forecast(history, scenario_key=config.scenario_key, scenario=scenario, model_name=config.model_name)
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
            "promotion_ready": False,
            "reason": "local baseline record only; no registry configured",
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


def _run_id(config: LocalRunConfig) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{stamp}-{config.source_key}-{config.scenario_key}-{config.model_name}"
