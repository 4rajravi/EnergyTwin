from __future__ import annotations

import plistlib
import sys
from dataclasses import dataclass
from pathlib import Path

from .forecasting import MODEL_TRAINED_REGRESSION
from .mlops import LOCAL_RUNS_DIR
from .sources import PROJECT_ROOT
from .storage import LOCAL_DB_PATH


DEFAULT_LAUNCHD_LABEL = "com.energytwin.daily"


@dataclass(frozen=True)
class LaunchdJobConfig:
    label: str = DEFAULT_LAUNCHD_LABEL
    hour: int = 7
    minute: int = 0
    source_key: str = "demo"
    scenario_key: str = "price"
    model_name: str = MODEL_TRAINED_REGRESSION
    train_model: bool = True
    force_promote_model: bool = False
    min_promotion_improvement_pct: float = 0.02
    python_executable: str = sys.executable
    project_root: Path | str = PROJECT_ROOT
    output_dir: Path | str = LOCAL_RUNS_DIR
    db_path: Path | str = LOCAL_DB_PATH


def build_launchd_plist(config: LaunchdJobConfig) -> dict:
    if not 0 <= config.hour <= 23:
        raise ValueError("hour must be between 0 and 23")
    if not 0 <= config.minute <= 59:
        raise ValueError("minute must be between 0 and 59")

    project_root = Path(config.project_root).resolve()
    script = project_root / "scripts" / "schedule_local_pipeline.py"
    logs_dir = project_root / "logs"
    args = [
        config.python_executable,
        str(script),
        "--source",
        config.source_key,
        "--scenario",
        config.scenario_key,
        "--model",
        config.model_name,
        "--max-runs",
        "1",
        "--interval-minutes",
        "0",
        "--output-dir",
        str(Path(config.output_dir)),
        "--db-path",
        str(Path(config.db_path)),
        "--min-improvement-pct",
        str(config.min_promotion_improvement_pct),
    ]
    if config.train_model:
        args.append("--train-model")
    if config.force_promote_model:
        args.append("--force-promote")

    return {
        "Label": config.label,
        "ProgramArguments": args,
        "WorkingDirectory": str(project_root),
        "StartCalendarInterval": {"Hour": config.hour, "Minute": config.minute},
        "StandardOutPath": str(logs_dir / "daily-mlops.out.log"),
        "StandardErrorPath": str(logs_dir / "daily-mlops.err.log"),
        "RunAtLoad": False,
    }


def write_launchd_plist(config: LaunchdJobConfig, path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    plist = build_launchd_plist(config)
    with target.open("wb") as file:
        plistlib.dump(plist, file, sort_keys=True)
    return target


def launch_agents_path(label: str = DEFAULT_LAUNCHD_LABEL) -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{label}.plist"
