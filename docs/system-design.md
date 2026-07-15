# AI Energy Twin System Design

This document explains how the project should work as a system. The roadmap explains build order; this document explains architecture.

## 1. Goal

Build an energy digital twin for one building first, then make it extensible to multiple buildings.

The system should:

- ingest hourly building energy data
- validate and standardize the data
- forecast next 24 hours of demand and solar
- simulate battery, solar, grid import/export, cost, carbon, and comfort
- compare baseline, rule-based, and optimized control policies
- show everything in a dashboard
- leave clean extension points for MLOps, database, cache, streaming, and RL

## 2. High-Level Architecture

```mermaid
flowchart LR
    subgraph Sources
        A1[Demo generator]
        A2[Imported CSV]
        A3[Future: Building Data Genome]
        A4[Future: NASA POWER]
    end

    subgraph Data Layer
        B1[Source selector]
        B2[Schema validation]
        B3[Data health]
        B4[Future: feature store]
    end

    subgraph Intelligence
        C1[Forecasting contract]
        C2[Future: TFT / PatchTST]
        C3[Digital twin simulator]
        C4[Optimizer]
    end

    subgraph API
        D1["/api/data-sources"]
        D2["/api/data-health"]
        D3["/api/forecast"]
        D4["/api/simulate"]
        D5["/api/optimize"]
        D6["/api/model-status"]
        D7["/api/forecast-evaluation"]
        D8["/api/mlops-run(s)"]
    end

    subgraph UI
        E1[Live Twin]
        E2[Forecast]
        E3[Scenario Lab]
        E4[MLOps]
    end

    A1 --> B1
    A2 --> B1
    A3 -. "later" .-> B1
    A4 -. "later" .-> B4
    B1 --> B2
    B2 --> B3
    B2 --> C1
    C1 --> C3
    C3 --> C4
    C1 --> D3
    C1 --> D7
    C3 --> D4
    C4 --> D5
    B1 --> D1
    B3 --> D2
    D1 --> E4
    D2 --> E4
    D3 --> E2
    D4 --> E1
    D5 --> E3
    D6 --> E4
    D7 --> E4
    D8 --> E4
```

## 3. Current Runtime Design

The current system is intentionally simple.

```mermaid
sequenceDiagram
    participant Browser
    participant Server
    participant Sources
    participant Forecast
    participant Simulator
    participant Optimizer

    Browser->>Server: GET forecast API with source demo and scenario price
    Server->>Sources: load_history(source, scenario)
    Sources-->>Server: hourly rows
    Server->>Forecast: build_forecast(rows, scenario)
    Forecast-->>Server: 24h forecast
    Server-->>Browser: forecast JSON

    Browser->>Server: GET optimize API with source demo and scenario price
    Server->>Sources: load_history(source, scenario)
    Server->>Forecast: build_forecast(rows, scenario)
    Server->>Simulator: simulate baseline/rule/optimized
    Simulator->>Optimizer: schedules
    Simulator-->>Server: metrics
    Server-->>Browser: comparison JSON
```

## 4. Main Components

| component | current file | responsibility |
| --- | --- | --- |
| Data generator | `src/energytwin/data.py` | creates deterministic demo building data and scenarios |
| Ingestion | `src/energytwin/ingestion.py` | loads CSV, validates schema, reports data health |
| Source selector | `src/energytwin/sources.py` | chooses demo data or imported CSV |
| Public-data adapters | `src/energytwin/adapters` | converts external dataset shapes into the internal schema |
| Enrichment | `src/energytwin/enrichment.py` | joins weather, solar, price, and carbon data by timestamp |
| NASA POWER adapter | `src/energytwin/adapters/nasa_power.py` | converts hourly NASA POWER JSON into enrichment CSV rows |
| Local MLOps | `src/energytwin/mlops.py` | writes dependency-free local experiment reports |
| Local scheduler | `src/energytwin/scheduler.py` | repeats local MLOps runs on an interval |
| Local storage | `src/energytwin/storage.py` | stores local experiment history in SQLite |
| Production storage | `src/energytwin/production_db.py` | stores run history in Postgres/Timescale-compatible schema |
| Cache | `src/energytwin/cache.py` | optional Redis cache for expensive API responses |
| Model artifacts | `src/energytwin/model_artifacts.py` | trains, saves, and loads local forecast model artifacts |
| Forecasting | `src/energytwin/forecasting.py` | returns a 24-hour forecast contract |
| Simulator | `src/energytwin/simulator.py` | simulates grid import/export, battery, cost, carbon, comfort |
| Optimizer | `src/energytwin/optimizer.py` | creates baseline, rule, and optimized schedules |
| API server | `src/energytwin/server.py` | serves JSON APIs and static dashboard |
| Dashboard | `src/energytwin/app/static` | browser UI |
| Import script | `scripts/import_dataset.py` | validates and imports local CSV files |

## 5. Data Contract

Every data source should eventually emit rows shaped like this:

| column | type | required | notes |
| --- | --- | --- | --- |
| `timestamp` | ISO string | yes | hourly and increasing |
| `hour` | integer | yes | `0` to `23` |
| `demand_kw` | float | yes | building load |
| `solar_kw` | float | yes | generated solar |
| `outside_temp_c` | float | yes | outdoor temperature |
| `price_usd_per_kwh` | float | yes | electricity price |
| `carbon_kg_per_kwh` | float | yes | carbon intensity |

This contract matters because forecasting, simulation, and optimization should not care whether data came from demo generation, CSV, Building Data Genome, NASA POWER, manual weather files, or a future database.

## 6. API Design

Current API endpoints:

| endpoint | purpose |
| --- | --- |
| `/api/data-sources` | list available data sources |
| `/api/data-health` | show row count, valid rows, invalid rows, columns, date range |
| `/api/scenarios` | list scenario options |
| `/api/forecast` | return 24-hour demand/solar forecast |
| `/api/forecast-evaluation` | return local forecast backtest metrics |
| `/api/simulate` | simulate one controller |
| `/api/optimize` | compare baseline, rule, and optimized policies |
| `/api/model-status` | show model and MLOps state |
| `/api/mlops-run` | return the latest local experiment report |
| `/api/mlops-runs` | return recent local experiment summaries |
| `/api/mlops-monitoring` | return forecast error trend and promotion summary |
| `/api/system-status` | show active storage and cache backend |

Current query parameters:

| parameter | used by | example |
| --- | --- | --- |
| `source` | data-health, forecast, simulate, optimize | `demo`, `imported` |
| `scenario` | forecast, simulate, optimize | `normal`, `price`, `hot` |
| `controller` | simulate | `baseline`, `rule`, `optimized` |
| `temp_delta` | forecast, simulate, optimize | `7.0` |
| `cloud_cover` | forecast, simulate, optimize | `0.78` |
| `price_multiplier` | forecast, simulate, optimize | `1.65` |
| `ev_spike` | forecast, simulate, optimize | `110` |
| `comfort` | forecast, simulate, optimize | `0.8` |
| `demand_charge` | simulate, optimize | `3.2` |
| `export_credit` | simulate, optimize | `0.32` |
| `battery_wear` | simulate, optimize | `0.018` |
| `limit` | mlops-runs | `5` |

## 7. Storage Design

### Current

Use local files:

```text
data/raw/                 manually placed input files
data/processed/           validated project-ready files
data/local/energytwin.sqlite3
models/                   future trained model artifacts
mlruns/                   future MLflow runs
```

The local SQLite database stores MLOps run summaries and full report payloads. JSON reports are still written under `mlruns/local` for easy manual inspection.

### Production Available

Set `ENERGYTWIN_DATABASE_URL` to switch MLOps run history from SQLite to Postgres:

```text
ENERGYTWIN_DATABASE_URL=postgresql://energytwin:password@host:5432/energytwin
```

The current Postgres schema stores run summaries plus full JSONB run payloads. It is TimescaleDB-compatible, but it does not require TimescaleDB yet.

### Next

Add normalized production tables for:

- meter readings
- weather features
- forecasts
- simulation runs
- optimization outputs
- model metadata
- data quality records

Add DuckDB if local analytical queries across large imported meter datasets become painful.

The SQLite storage boundary now has a Postgres adapter. The next migration is moving more than run history into production tables.

## 8. Cache Design

Redis cache is now opt-in.

Set:

```text
ENERGYTWIN_REDIS_URL=redis://localhost:6379/0
ENERGYTWIN_REDIS_TTL_SECONDS=60
```

Redis becomes useful when:

- repeated scenarios are slow
- forecast inference becomes expensive
- multiple dashboard users hit the same endpoints
- we need short-lived API result caching

Likely cache keys later:

```text
forecast:{building_id}:{model_version}:{source}:{scenario}:{horizon}
simulate:{building_id}:{forecast_hash}:{controller}
optimize:{building_id}:{forecast_hash}:{policy_version}
```

Current cache keys are whole-response API keys for forecast, simulate, optimize, model status, forecast evaluation, and data health.

## 9. Streaming Design

Kafka and Flink are intentionally deferred.

Kafka becomes useful when we have:

- live meter telemetry
- live inverter/battery events
- price events
- carbon-intensity events
- weather forecast updates

Flink becomes useful when we need:

- event-time joins
- rolling features on live data
- low-latency anomaly detection
- continuous feature materialization

Until then, batch ingestion plus API simulation is the right shape.

Future streaming shape:

```mermaid
flowchart LR
    A[Smart meters / APIs] --> B[Kafka topics]
    B --> C[Flink feature jobs]
    C --> D[TimescaleDB / feature store]
    D --> E[Forecast service]
    E --> F[Simulator / optimizer]
    F --> G[Dashboard]
```

## 10. MLOps Design

Current model is a baseline forecast contract.

Current local MLOps:

- `scripts/run_local_pipeline.py` writes JSON run reports
- reports include data health, forecast metrics, and policy comparison
- `/api/mlops-run` exposes the latest local report

Future MLOps components:

| tool | role |
| --- | --- |
| MLflow | experiments, model registry, model version metadata |
| Prefect | scheduled ingest/train/evaluate pipelines |
| Evidently | drift and forecast-performance monitoring |
| DVC or object storage | dataset/model artifact versioning |

Current scheduled local flow:

```mermaid
flowchart LR
    A[Local timer script] --> B[Load source data]
    B --> C[Validate data health]
    C --> D{Retrain?}
    D -- "yes" --> E[Train candidate artifact]
    D -- "no" --> F[Use active model]
    E --> M{Better than reference?}
    M -- "yes" --> N[Promote active artifact]
    M -- "no" --> O[Keep candidate only]
    N --> F
    O --> F
    F --> G[Forecast]
    G --> H[Evaluate]
    G --> I[Simulate and optimize]
    H --> J[Write JSON report]
    I --> J
    J --> K[Write SQLite run history]
    K --> L[Build monitoring summary]
    L --> P[Dashboard MLOps panel]
```

The scheduler can retrain local artifacts such as `trained-regression-v1` and `trained-mlp-v1` with `--train-model`. Promotion compares the candidate against `weighted-baseline-v1`; the active artifact is overwritten only when the candidate clears the MAE improvement threshold.

The monitoring summary is intentionally small: latest MAE, previous-vs-latest delta, best historical run, promotion counts, and a trend label. This is enough for daily local operation without adding Evidently yet.

Training flow later:

```mermaid
flowchart TD
    A[Validated data] --> B[Feature builder]
    B --> C[Train baseline + TFT]
    C --> D[Evaluate MAE/RMSE/sMAPE/pinball]
    D --> E{Better than current?}
    E -- "yes" --> F[Register model]
    E -- "no" --> G[Keep current model]
    F --> H[Serve forecast]
    H --> I[Monitor error and drift]
```

## 11. Forecasting Design

Current model:

- measured weighted baseline
- trainable hourly artifact
- trainable regression artifact
- trainable local MLP artifact
- 24-hour forecast
- demand and solar outputs
- uncertainty bands
- local backtest metrics

Future options:

| option | why use it | tradeoff |
| --- | --- | --- |
| N-HiTS | strong deep-learning baseline | less interpretable than TFT |
| PatchTST | modern transformer for time series | needs more training setup |
| TFT | handles known future inputs and static metadata | heavier implementation |
| TimesFM/foundation model | quick strong baseline if suitable | dependency and fit uncertainty |

Recommended path:

1. keep `trained-regression-v1` as the current local benchmark
2. use `trained-mlp-v1` as the first dependency-free deep-learning model
3. add N-HiTS or PatchTST once public data is stable
4. add TFT once data/features are mature
5. add MLflow registry once multiple serious model families exist

## 12. Simulator Design

The simulator is the core “twin.”

Inputs:

- forecasted demand
- forecasted solar
- price
- carbon intensity
- battery spec
- tariff spec
- controller schedule

Outputs:

- grid import/export
- battery state of charge
- total cost
- energy cost
- demand charge
- export credit
- battery wear cost
- carbon emissions
- peak demand
- comfort risk
- battery cycles

The dashboard exposes the cost components and editable economic assumptions in the Scenario Lab so users can see whether a policy is saving money through energy arbitrage, peak reduction, or both. The optimized controller also uses those economics while choosing the battery schedule.

Future improvements:

- richer utility tariff structures
- richer battery degradation
- HVAC thermal model
- occupancy schedule
- solar inverter limits
- multi-building aggregation

## 13. Security And Safety

Current local-only assumptions:

- no authentication
- no user accounts
- no remote writes
- imported files stay local

Before deployment:

- add authentication
- restrict upload size and file type
- store import audit records
- protect model and simulation endpoints from expensive repeated calls
- validate all external API data

## 14. Build Discipline

Before each phase, we should answer:

1. What are we building?
2. Why does it matter?
3. What are the options?
4. What is the recommended option?
5. What files will change?
6. How will we verify it?

This keeps the project understandable while it grows.
