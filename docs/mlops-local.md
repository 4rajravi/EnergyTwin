# Local MLOps Runs

The project now has a dependency-free local experiment record. It is not MLflow yet, but it is shaped like a future MLflow/Prefect run.

Run:

```bash
python3 scripts/run_local_pipeline.py \
  --source demo \
  --scenario price \
  --model weighted-baseline-v1 \
  --output-dir mlruns/local
```

Run it on a local schedule:

```bash
python3 scripts/schedule_local_pipeline.py \
  --source demo \
  --scenario price \
  --interval-minutes 60 \
  --forever
```

For a single scheduled-style run, omit `--forever`. This is the project-owned version of a cron job. Later, cron or Prefect can call the same command.

The command writes:

```text
mlruns/local/<run_id>.json
mlruns/local/latest.json
data/local/energytwin.sqlite3
```

Train a local forecast model artifact:

```bash
python3 scripts/train_forecast_model.py \
  --source demo \
  --scenario price \
  --candidate-output models/candidate-forecast-model.json \
  --active-output models/active-forecast-model.json
```

Run the pipeline with retraining:

```bash
python3 scripts/run_local_pipeline.py \
  --source demo \
  --scenario price \
  --model trained-regression-v1 \
  --train-model
```

The run report includes:

- source and scenario
- data health
- forecast backtest metrics
- policy comparison metrics
- model candidate metadata
- economic assumptions

## Scheduled Flow

```text
timer
→ load current source
→ validate data health
→ build forecast
→ evaluate forecast error
→ simulate and optimize
→ write JSON report
→ write SQLite run record
→ dashboard reads latest run and recent history
```

With `--train-model`, the run retrains the selected local artifact before prediction. Without that flag, it reruns the selected forecasting contract and records whether it is performing well.

Retraining now uses a promotion gate:

```text
train candidate
→ evaluate candidate model
→ evaluate reference weighted-baseline-v1
→ promote only if candidate MAE improves enough
```

The default threshold is 2 percent MAE improvement. Use `--force-promote` only when you intentionally want to overwrite the active local artifact despite worse metrics.

The API exposes the latest local run and recent run summaries:

```text
/api/mlops-run
/api/mlops-runs
/api/mlops-monitoring
```

`/api/model-status` also includes `latest_local_run` when a local run exists.

The dashboard MLOps panel shows both:

- live metrics computed from the currently selected source/scenario
- latest persisted local run metrics from `/api/mlops-run`
- recent persisted run summaries from `/api/mlops-runs`
- forecast error trend, best run, and promotion counts from `/api/mlops-monitoring`

## Daily Run Mode

For a daily local loop:

```bash
python3 scripts/schedule_local_pipeline.py \
  --source demo \
  --scenario price \
  --model trained-regression-v1 \
  --train-model \
  --interval-minutes 1440 \
  --forever
```

Daily is enough for the current project shape. The monitoring layer compares each run against prior run history and marks the trend as `improving`, `stable`, `degrading`, or `insufficient-history`.

## macOS Daily Automation

Generate a launchd plist for a daily one-shot run:

```bash
python3 scripts/make_daily_launchd.py \
  --hour 7 \
  --minute 0 \
  --source demo \
  --scenario price \
  --print
```

This writes:

```text
launchd/com.energytwin.daily.plist
```

To install it into macOS LaunchAgents, run:

```bash
python3 scripts/make_daily_launchd.py --hour 7 --minute 0 --install
```

Then load it with the command printed by the script. The generated job runs `scripts/schedule_local_pipeline.py --max-runs 1`, so launchd handles the daily schedule instead of keeping a forever loop alive.

## Why SQLite Now

SQLite is the smallest useful persistence layer for run history. JSON files remain easy to inspect, while SQLite lets the API list, sort, and summarize past runs. This is a stepping stone toward Postgres/TimescaleDB, not a separate product direction.

## Why This Model First

`trained-regression-v1` is the current strongest local model. It learns a small regression over hour, temperature, cooling load, solar, and peak-shape features. It is not deep learning, but it gives the project a real train/save/load/promote path and creates a stronger benchmark for N-HiTS, PatchTST, TFT, or MLflow model registry.

## Why This Exists Before MLflow

This gives the project a stable experiment-report contract before adding heavier infrastructure. Later, the same fields can be logged to MLflow and scheduled through Prefect.
