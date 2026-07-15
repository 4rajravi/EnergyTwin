# AI Energy Twin

A non-RL energy digital twin for a commercial building. It forecasts 24-hour demand and solar production, simulates battery/grid behavior, and compares baseline, rule-based, and optimized control policies in a browser dashboard.

This first build is intentionally shippable without cloud services. The core is real-data-ready: public CSV/ZIP download, ingestion, local neural forecasting, MLOps, cache, database, Kafka, and Flink can be added behind the current module boundaries.

## Run

```bash
python run.py
```

Open `http://127.0.0.1:8787`.

## Test

```bash
python -m unittest discover -s tests
```

## Verify, Commit, And Push

Run checks, stage all current changes, and commit:

```bash
python scripts/ship.py -m "your commit message"
```

Run checks, commit, and push the current branch:

```bash
python scripts/ship.py -m "your commit message" --push
```

## Import Data

Create a validated demo CSV:

```bash
python scripts/import_dataset.py --make-demo --output data/processed/current-meter.csv
```

Import a local CSV:

```bash
python scripts/import_dataset.py data/raw/my-building.csv --output data/processed/current-meter.csv
```

Prepare the downloaded Building Data Genome 2 dataset:

```bash
python scripts/prepare_default_real_data.py
```

Or prepare it manually:

```bash
python scripts/prepare_public_dataset.py data/raw/building-meter.csv \
  --format bdg-wide \
  --building-column building_a \
  --output data/processed/current-meter.csv
```

See [docs/data-import.md](docs/data-import.md) for the required schema.
See [docs/public-data.md](docs/public-data.md) for Building Data Genome-style adapter examples.
See [docs/weather-enrichment.md](docs/weather-enrichment.md) for joining weather, solar, price, or carbon CSV data.
See [docs/nasa-power.md](docs/nasa-power.md) for NASA POWER weather enrichment.
See [docs/mlops-local.md](docs/mlops-local.md) for local experiment reports.
See [docs/production-infra.md](docs/production-infra.md) for Postgres/TimescaleDB and Redis setup.
See [docs/advanced-ops.md](docs/advanced-ops.md) for multi-building, MLflow, Prefect, drift reports, auth, and Docker deployment.

Run a scheduled local MLOps loop:

```bash
python scripts/schedule_local_pipeline.py --source demo --scenario price --interval-minutes 60 --forever
```

Train the local forecast artifact:

```bash
python scripts/train_forecast_model.py --source demo --scenario price
```

Training writes a candidate model first and promotes it to `models/active-forecast-model.json` only if it beats the weighted baseline by the configured metric threshold.
The current default trainable model is `trained-regression-v1`. To train the local neural network model, pass `--model trained-mlp-v1`.

The MLOps dashboard also shows recent run history, forecast error trend, best run, and candidate promotion counts from SQLite.

Generate a macOS daily launchd job:

```bash
python scripts/make_daily_launchd.py --hour 7 --minute 0 --print
```

## Project Map

See [docs/roadmap.md](docs/roadmap.md) for the current system diagram, build phases, and decision log.

See [docs/system-design.md](docs/system-design.md) for component design, data flow, API design, storage, cache, streaming, and MLOps architecture.

## MVP Architecture

- `src/energytwin/data.py`: deterministic demo data and scenario generation.
- `src/energytwin/ingestion.py`: local CSV ingestion, schema checks, and data-health validation.
- `src/energytwin/sources.py`: data-source selection between demo data and imported CSV.
- `src/energytwin/enrichment.py`: timestamp-based joins for weather, solar, price, and carbon data.
- `src/energytwin/adapters/nasa_power.py`: NASA POWER hourly weather-to-enrichment adapter.
- `src/energytwin/automation.py`: macOS launchd plist generation for daily local runs.
- `src/energytwin/downloads.py`: direct CSV/ZIP public dataset downloader.
- `src/energytwin/real_data_defaults.py`: hard-coded default public-meter and NASA POWER profile.
- `src/energytwin/public_pipeline.py`: public dataset preparation into the internal schema.
- `src/energytwin/mlops.py`: local experiment report generation.
- `src/energytwin/model_artifacts.py`: train/save/load support for local forecast artifacts.
- `src/energytwin/scheduler.py`: interval-based local MLOps scheduler.
- `src/energytwin/storage.py`: SQLite persistence for local experiment history.
- `src/energytwin/production_db.py`: optional Postgres-backed run history.
- `src/energytwin/cache.py`: optional Redis API response cache.
- `src/energytwin/mlflow_registry.py`: optional MLflow experiment/model registry logging.
- `src/energytwin/drift_reports.py`: optional drift report generation.
- `src/energytwin/auth.py`: optional bearer-token API authentication.
- `src/energytwin/forecasting.py`: 24-hour multi-output forecast contract with uncertainty bands.
- `/api/forecast-evaluation`: local backtest metrics for the active baseline.
- `src/energytwin/simulator.py`: battery, grid import/export, tariff cost breakdown, carbon, and comfort simulation.
- `src/energytwin/optimizer.py`: baseline, rule, and optimized controller schedules.
- `src/energytwin/server.py`: dependency-free HTTP API and static dashboard server.
- `src/energytwin/app/static`: control-room dashboard.

Scenario Lab controls expose weather, cloud cover, price multiplier, EV spike, comfort strictness, demand charge, export credit, and battery wear assumptions in the UI.

## Service Roadmap

For the MVP, use local files, a small SQLite run-history database, and in-memory computation.

- Cache: add Redis for forecast and scenario result caching once API traffic or repeated simulations matter.
- DB: add Postgres/TimescaleDB for meter readings, forecasts, simulations, model metadata, and audit trails.
- Kafka: add only when ingesting multiple live telemetry streams, device events, or market feeds.
- Flink: add only when low-latency stream feature computation becomes necessary.
- MLOps: add MLflow for experiment tracking/model registry, Prefect for pipelines, and Evidently for monitoring.

TD-MPC2 is not in the critical path. The simulator and controller interfaces are shaped so a Gymnasium-style RL environment can be added later.

## Learning Checkpoints

Decision 1: Data layer.

- Fast MVP: local CSV files and strict validation. This is what the project uses now.
- Strong local analytics: DuckDB over Parquet files.
- Production path: Postgres/TimescaleDB for meter readings, forecasts, simulation runs, and model metadata.

Recommendation: start with local CSV validation, then move to DuckDB or TimescaleDB after real public data is wired in.
