from __future__ import annotations

import argparse
import plistlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from energytwin.automation import DEFAULT_LAUNCHD_LABEL, LaunchdJobConfig, build_launchd_plist, launch_agents_path, write_launchd_plist  # noqa: E402
from energytwin.forecasting import MODEL_TRAINED_REGRESSION  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a macOS launchd job for the daily Energy Twin MLOps run.")
    parser.add_argument("--label", default=DEFAULT_LAUNCHD_LABEL)
    parser.add_argument("--hour", type=int, default=7)
    parser.add_argument("--minute", type=int, default=0)
    parser.add_argument("--source", default="demo", choices=("demo", "imported"))
    parser.add_argument("--scenario", default="price")
    parser.add_argument("--model", default=MODEL_TRAINED_REGRESSION)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output", default=str(ROOT / "launchd" / f"{DEFAULT_LAUNCHD_LABEL}.plist"))
    parser.add_argument("--no-train-model", action="store_true")
    parser.add_argument("--force-promote", action="store_true")
    parser.add_argument("--min-improvement-pct", type=float, default=0.02)
    parser.add_argument("--install", action="store_true", help="Write to ~/Library/LaunchAgents instead of the project launchd directory.")
    parser.add_argument("--print", action="store_true", help="Print the plist XML to stdout after writing it.")
    args = parser.parse_args()

    config = LaunchdJobConfig(
        label=args.label,
        hour=args.hour,
        minute=args.minute,
        source_key=args.source,
        scenario_key=args.scenario,
        model_name=args.model,
        train_model=not args.no_train_model,
        force_promote_model=args.force_promote,
        min_promotion_improvement_pct=args.min_improvement_pct,
        python_executable=args.python,
        project_root=ROOT,
    )
    target = launch_agents_path(args.label) if args.install else Path(args.output)
    write_launchd_plist(config, target)
    print(f"Wrote {target}")
    if args.install:
        print(f"Load with: launchctl bootstrap gui/$(id -u) {target}")
        print(f"Unload with: launchctl bootout gui/$(id -u) {target}")
    if args.print:
        sys.stdout.buffer.write(plistlib.dumps(build_launchd_plist(config), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
