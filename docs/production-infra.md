# Production Infrastructure

The project now has opt-in production infrastructure adapters.

Local development still works with:

```text
SQLite run history
no cache
local CSV files
```

Production mode is activated with environment variables.

## Install Production Dependencies

```bash
python3 -m pip install 'psycopg[binary]' redis
```

Or install the project extra:

```bash
python3 -m pip install '.[prod]'
```

## Postgres / TimescaleDB

Set:

```bash
export ENERGYTWIN_DATABASE_URL='postgresql://energytwin:password@localhost:5432/energytwin'
```

Initialize schema:

```bash
python3 scripts/init_production_db.py
```

When `ENERGYTWIN_DATABASE_URL` is set, MLOps run history uses Postgres instead of:

```text
data/local/energytwin.sqlite3
```

The current production table stores:

- run id and timestamp
- source, scenario, model name
- forecast metrics
- optimized policy metrics
- full JSONB run payload

TimescaleDB is still compatible because this is standard Postgres SQL. Add hypertables later when meter readings and forecasts are persisted as time-series tables.

## Redis Cache

Set:

```bash
export ENERGYTWIN_REDIS_URL='redis://localhost:6379/0'
export ENERGYTWIN_REDIS_TTL_SECONDS=60
```

Cached endpoints:

```text
/api/forecast
/api/simulate
/api/optimize
/api/model-status
/api/forecast-evaluation
/api/data-health
```

The API response includes:

```text
X-EnergyTwin-Cache: HIT
X-EnergyTwin-Cache: MISS
```

Run status check:

```bash
curl http://127.0.0.1:8787/api/system-status
```

## What Is Still Local

Raw/processed data is still file-based:

```text
data/raw/
data/processed/current-meter.csv
```

Next production DB step is storing meter readings, forecast rows, simulation points, and optimization schedules as normalized tables.
