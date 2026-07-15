from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from energytwin.forecasting import MODEL_TRAINED_REGRESSION, MODEL_WEIGHTED, evaluate_forecast_baseline  # noqa: E402
from energytwin.model_artifacts import (  # noqa: E402
    DEFAULT_CANDIDATE_FORECAST_MODEL_PATH,
    DEFAULT_FORECAST_MODEL_PATH,
    PromotionPolicy,
    decide_model_promotion,
    is_trainable_model,
    save_forecast_model,
    train_forecast_model_artifact,
)
from energytwin.sources import load_history  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Train and save a local Energy Twin forecast model artifact.")
    parser.add_argument("--source", default="demo", choices=("demo", "imported"))
    parser.add_argument("--scenario", default="normal")
    parser.add_argument("--model", default=MODEL_TRAINED_REGRESSION)
    parser.add_argument("--candidate-output", default=str(DEFAULT_CANDIDATE_FORECAST_MODEL_PATH))
    parser.add_argument("--active-output", default=str(DEFAULT_FORECAST_MODEL_PATH))
    parser.add_argument("--min-improvement-pct", type=float, default=0.02)
    parser.add_argument("--force-promote", action="store_true")
    args = parser.parse_args()

    history, source_label = load_history(source_key=args.source, scenario_key=args.scenario)
    if not is_trainable_model(args.model):
        raise SystemExit(f"model is not trainable: {args.model}")
    artifact = train_forecast_model_artifact(history, args.model)
    candidate_target = save_forecast_model(artifact, args.candidate_output)
    candidate_metrics = evaluate_forecast_baseline(history, model_name=args.model)
    reference_metrics = evaluate_forecast_baseline(history, model_name=MODEL_WEIGHTED)
    promotion = decide_model_promotion(
        candidate_metrics,
        reference_metrics,
        PromotionPolicy(min_improvement_pct=args.min_improvement_pct),
    )
    if args.force_promote:
        promotion["promoted"] = True
        promotion["reason"] = "forced promotion requested"
    active_target = save_forecast_model(artifact, args.active_output) if promotion["promoted"] else None
    print(
        json.dumps(
            {
                "model_name": artifact["model_name"],
                "source": source_label,
                "training_rows": artifact["training_rows"],
                "candidate_output": str(candidate_target),
                "active_output": str(active_target) if active_target else None,
                "candidate_mae_kw": candidate_metrics.mae_kw,
                "reference_model": MODEL_WEIGHTED,
                "reference_mae_kw": reference_metrics.mae_kw,
                "promotion": promotion,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
