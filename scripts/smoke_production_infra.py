from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from energytwin.cache import REDIS_URL_ENV, cache_status  # noqa: E402
from energytwin.mlops import LocalRunConfig, run_local_experiment  # noqa: E402
from energytwin.storage import DATABASE_URL_ENV, active_storage_backend  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke-test optional production infrastructure.")
    parser.add_argument("--skip-run", action="store_true", help="Only check configured backends.")
    args = parser.parse_args()

    results = {
        "database_url_set": bool(os.getenv(DATABASE_URL_ENV)),
        "redis_url_set": bool(os.getenv(REDIS_URL_ENV)),
        "storage": active_storage_backend(),
        "cache": cache_status(),
        "pipeline": None,
    }

    if not args.skip_run:
        report = run_local_experiment(LocalRunConfig(source_key="demo", scenario_key="normal"))
        results["pipeline"] = {"run_id": report["run_id"], "source": report["source"]}

    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
