from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from energytwin.mlops import LOCAL_RUNS_DIR, LocalRunConfig, run_local_experiment  # noqa: E402
from energytwin.forecasting import MODEL_WEIGHTED  # noqa: E402
from energytwin.storage import LOCAL_DB_PATH  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local Energy Twin experiment and write an MLOps-style JSON report.")
    parser.add_argument("--source", default="demo", choices=("demo", "imported"))
    parser.add_argument("--scenario", default="normal")
    parser.add_argument("--model", default=MODEL_WEIGHTED)
    parser.add_argument("--demand-charge", type=float, default=3.2)
    parser.add_argument("--export-credit", type=float, default=0.32)
    parser.add_argument("--battery-wear", type=float, default=0.018)
    parser.add_argument("--output-dir", default=str(LOCAL_RUNS_DIR))
    parser.add_argument("--db-path", default=str(LOCAL_DB_PATH))
    parser.add_argument("--train-model", action="store_true", help="Train and save the local forecast model artifact before forecasting.")
    parser.add_argument("--force-promote", action="store_true", help="Promote the trained model even if it does not beat the reference metric.")
    parser.add_argument("--min-improvement-pct", type=float, default=0.02)
    args = parser.parse_args()

    report = run_local_experiment(
        LocalRunConfig(
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
        output_dir=args.output_dir,
        db_path=args.db_path,
    )
    print(json.dumps({"run_id": report["run_id"], "output_dir": args.output_dir, "db_path": args.db_path}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
