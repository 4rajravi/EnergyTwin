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

## MVP Architecture

- `src/energytwin/data.py`: deterministic demo data and scenario generation.
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
