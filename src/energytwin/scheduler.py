from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .mlops import LOCAL_RUNS_DIR, LocalRunConfig, run_local_experiment
from .storage import LOCAL_DB_PATH


@dataclass(frozen=True)
class LocalScheduleConfig:
    run_config: LocalRunConfig
    interval_seconds: float = 3600.0
    max_runs: int | None = 1
    output_dir: Path | str = LOCAL_RUNS_DIR
    db_path: Path | str | None = LOCAL_DB_PATH


def run_local_schedule(
    config: LocalScheduleConfig,
    sleep_fn: Callable[[float], None] = time.sleep,
    on_run: Callable[[dict], None] | None = None,
) -> list[dict]:
    if config.interval_seconds < 0:
        raise ValueError("interval_seconds must be non-negative")
    if config.max_runs is not None and config.max_runs < 1:
        raise ValueError("max_runs must be at least 1 or None")

    reports = []
    completed = 0
    while config.max_runs is None or completed < config.max_runs:
        report = run_local_experiment(config.run_config, output_dir=config.output_dir, db_path=config.db_path)
        reports.append(report)
        completed += 1
        if on_run is not None:
            on_run(report)
        if config.max_runs is not None and completed >= config.max_runs:
            break
        sleep_fn(config.interval_seconds)
    return reports
