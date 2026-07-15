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

This does not retrain a model yet. It reruns the current forecasting contract and records whether it is performing well. Retraining comes after a real trainable model artifact exists under `models/`.

The API exposes the latest local run and recent run summaries:

```text
/api/mlops-run
/api/mlops-runs
```

`/api/model-status` also includes `latest_local_run` when a local run exists.

The dashboard MLOps panel shows both:

- live metrics computed from the currently selected source/scenario
- latest persisted local run metrics from `/api/mlops-run`
- recent persisted run summaries from `/api/mlops-runs`

## Why SQLite Now

SQLite is the smallest useful persistence layer for run history. JSON files remain easy to inspect, while SQLite lets the API list, sort, and summarize past runs. This is a stepping stone toward Postgres/TimescaleDB, not a separate product direction.

## Why This Exists Before MLflow

This gives the project a stable experiment-report contract before adding heavier infrastructure. Later, the same fields can be logged to MLflow and scheduled through Prefect.
