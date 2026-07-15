from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from energytwin.mlops import LOCAL_RUNS_DIR, LocalRunConfig  # noqa: E402
from energytwin.forecasting import MODEL_TRAINED_REGRESSION  # noqa: E402
from energytwin.scheduler import LocalScheduleConfig, run_local_schedule  # noqa: E402
from energytwin.storage import LOCAL_DB_PATH  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Energy Twin MLOps pipeline on a schedule.")
    parser.add_argument("--source", default="demo", choices=("demo", "imported"))
    parser.add_argument("--scenario", default="normal")
    parser.add_argument("--model", default=MODEL_TRAINED_REGRESSION)
    parser.add_argument("--demand-charge", type=float, default=3.2)
    parser.add_argument("--export-credit", type=float, default=0.32)
    parser.add_argument("--battery-wear", type=float, default=0.018)
    parser.add_argument("--output-dir", default=str(LOCAL_RUNS_DIR))
    parser.add_argument("--db-path", default=str(LOCAL_DB_PATH))
    parser.add_argument("--interval-minutes", type=float, default=60.0)
    parser.add_argument("--max-runs", type=int, default=1, help="Use 1 for a single run. Omit with --forever for continuous scheduling.")
    parser.add_argument("--forever", action="store_true", help="Run until interrupted.")
    parser.add_argument("--train-model", action="store_true", help="Retrain and save the local forecast model artifact before each run.")
    parser.add_argument("--force-promote", action="store_true", help="Promote the trained model even if it does not beat the reference metric.")
    parser.add_argument("--min-improvement-pct", type=float, default=0.02)
    args = parser.parse_args()

    schedule = LocalScheduleConfig(
        run_config=LocalRunConfig(
            source_key=args.source,
            scenario_key=args.scenario,
            model_name=args.model,
            demand_charge_usd_per_kw_day=args.demand_charge,
            export_credit_fraction=args.export_credit,
            battery_wear_cost_usd_per_kwh=args.battery_wear,
            train_model=args.train_model,
            force_promote_model=args.force_promote,
            min_promotion_improvement_pct=args.min_improvement_pct,
        ),
        interval_seconds=args.interval_minutes * 60,
        max_runs=None if args.forever else args.max_runs,
        output_dir=args.output_dir,
        db_path=args.db_path,
    )

    def print_run(report: dict) -> None:
        print(
            json.dumps(
                {
                    "run_id": report["run_id"],
                    "created_at": report["created_at"],
                    "scenario": report["config"]["scenario_key"],
                    "mae_kw": report["forecast_metrics"]["mae_kw"],
                    "optimized_savings_pct": report["policy_comparison"]["optimized"]["cost_savings_pct"],
                    "db_path": args.db_path,
                },
                sort_keys=True,
            ),
            flush=True,
        )

    try:
        run_local_schedule(schedule, on_run=print_run)
    except KeyboardInterrupt:
        print("Scheduler stopped.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
