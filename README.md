# AI Energy Twin

A non-RL energy digital twin for a commercial building. It forecasts 24-hour demand and solar production, simulates battery/grid behavior, and compares baseline, rule-based, and optimized control policies in a browser dashboard.

This first build is intentionally shippable without cloud services or external data downloads. The core is real-data-ready: ingestion, deep forecasting, MLOps, cache, database, Kafka, and Flink can be added behind the current module boundaries.

## Run

```bash
python3 run.py
```

Open `http://127.0.0.1:8787`.

## Test

```bash
python3 -m unittest discover -s tests
```

## Import Data

Create a validated demo CSV:

```bash
python3 scripts/import_dataset.py --make-demo --output data/processed/current-meter.csv
```

Import a local CSV:

```bash
python3 scripts/import_dataset.py data/raw/my-building.csv --output data/processed/current-meter.csv
```

See [docs/data-import.md](docs/data-import.md) for the required schema.

## Project Map

See [docs/roadmap.md](docs/roadmap.md) for the current system diagram, build phases, and decision log.

See [docs/system-design.md](docs/system-design.md) for component design, data flow, API design, storage, cache, streaming, and MLOps architecture.

## MVP Architecture

- `src/energytwin/data.py`: deterministic demo data and scenario generation.
- `src/energytwin/ingestion.py`: local CSV ingestion, schema checks, and data-health validation.
- `src/energytwin/sources.py`: data-source selection between demo data and imported CSV.
- `src/energytwin/forecasting.py`: 24-hour multi-output forecast contract with uncertainty bands.
- `src/energytwin/simulator.py`: battery, grid import/export, cost, carbon, and comfort simulation.
- `src/energytwin/optimizer.py`: baseline, rule, and optimized controller schedules.
- `src/energytwin/server.py`: dependency-free HTTP API and static dashboard server.
- `src/energytwin/app/static`: control-room dashboard.

## Service Roadmap

For the MVP, use local files and in-memory computation.

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
