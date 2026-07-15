# Advanced Operations

This document covers the larger production-oriented pieces.

## Multi-Building Support

The dashboard can use Building Data Genome 2 directly.

Use the source selector:

```text
Building Genome
```

Then choose a building from the building selector. The backend prepares a per-building CSV cache under:

```text
data/processed/buildings/
```

The default building remains:

```text
Hog_office_Betsy
```

The API accepts:

```text
source=genome
building=Hog_office_Betsy
```

Example:

```bash
curl 'http://127.0.0.1:8787/api/forecast?source=genome&building=Hog_office_Betsy&scenario=price'
```

District aggregation endpoints:

```bash
curl 'http://127.0.0.1:8787/api/district-forecast?buildings=Hog_office_Betsy,Hog_office_Gustavo,Hog_office_Shawnna&scenario=price'

curl 'http://127.0.0.1:8787/api/district-optimize?buildings=Hog_office_Betsy,Hog_office_Gustavo,Hog_office_Shawnna&scenario=price'
```

## MLflow Registry

Set:

```bash
export ENERGYTWIN_MLFLOW_TRACKING_URI='file:./mlruns/mlflow'
export ENERGYTWIN_MLFLOW_EXPERIMENT='energytwin'
```

Run:

```bash
python3 scripts/run_local_pipeline.py --source genome --building Hog_office_Betsy --scenario price --model trained-mlp-v1 --train-model
```

The run logs params, forecast metrics, optimization metrics, and the candidate model artifact.

Optional model registration:

```bash
export ENERGYTWIN_MLFLOW_REGISTER=1
export ENERGYTWIN_MLFLOW_MODEL_NAME='EnergyTwinForecast'
```

## Prefect Orchestration

Install:

```bash
python3 -m pip install prefect
```

Run:

```bash
python3 scripts/run_prefect_pipeline.py --source genome --building Hog_office_Betsy --scenario price --train-model
```

This wraps the same pipeline in a Prefect flow. It is intentionally thin so the source of truth remains `run_local_experiment`.

## Drift Reports

Enable:

```bash
export ENERGYTWIN_EVIDENTLY_REPORTS=1
```

Run a pipeline. Drift JSON is written to:

```text
mlruns/drift/latest.json
```

An HTML summary is also written to:

```text
mlruns/drift/latest.html
```

The current report compares the first half of the selected history to the second half across demand, solar, weather, price, and carbon fields. It is Evidently-ready but dependency-free. The next step is replacing the internal summary with a native Evidently HTML/JSON report once the Evidently package is installed and pinned.

## Authentication

Enable bearer-token auth for API endpoints:

```bash
export ENERGYTWIN_AUTH_TOKEN='change-me'
```

Or store only a SHA-256 hash of the token:

```bash
export ENERGYTWIN_AUTH_TOKEN_SHA256="$(printf 'change-me' | shasum -a 256 | awk '{print $1}')"
```

API calls must include:

```text
Authorization: Bearer change-me
```

The browser dashboard prompts for the token and stores it in local storage.

## Deployment

A basic Dockerfile is included.

Build:

```bash
docker build -t energytwin .
```

Start the full local production stack:

```bash
docker compose up --build
```

Run:

```bash
docker run --rm -p 8787:8787 \
  -e ENERGYTWIN_AUTH_TOKEN='change-me' \
  -e ENERGYTWIN_DATABASE_URL='postgresql://energytwin:password@host.docker.internal:5432/energytwin' \
  -e ENERGYTWIN_REDIS_URL='redis://host.docker.internal:6379/0' \
  -v "$PWD/data:/app/data" \
  energytwin
```

Check:

```bash
curl http://127.0.0.1:8787/api/system-status
```
