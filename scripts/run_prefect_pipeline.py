from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))
os.environ.setdefault("PREFECT_HOME", str(ROOT / "data" / "local" / "prefect"))

from energytwin.forecasting import MODEL_TRAINED_REGRESSION  # noqa: E402
from energytwin.mlops import LocalRunConfig, run_local_experiment  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Energy Twin pipeline through Prefect.")
    parser.add_argument("--source", default="demo", choices=("demo", "imported", "genome"))
    parser.add_argument("--scenario", default="normal")
    parser.add_argument("--building", help="Building Data Genome building id when --source genome.")
    parser.add_argument("--model", default=MODEL_TRAINED_REGRESSION)
    parser.add_argument("--train-model", action="store_true")
    args = parser.parse_args()

    try:
        from prefect import flow, task  # type: ignore
    except ImportError:
        print("Prefect is not installed. Run: python3 -m pip install prefect", file=sys.stderr)
        return 1

    @task
    def run_experiment_task() -> dict:
        return run_local_experiment(
            LocalRunConfig(
                source_key=args.source,
                scenario_key=args.scenario,
                building_id=args.building,
                model_name=args.model,
                train_model=args.train_model,
            )
        )

    @flow(name="energytwin-local-pipeline")
    def energytwin_flow() -> dict:
        return run_experiment_task()

    report = energytwin_flow()
    print(json.dumps({"run_id": report["run_id"], "source": report["source"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
