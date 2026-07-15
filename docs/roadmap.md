# AI Energy Twin Roadmap

This document is the project map. Before each major build step, we should update this file so it is clear what exists, what is next, and what decisions are still open.

For component-level architecture, see [system-design.md](system-design.md).

## What We Are Building

AI Energy Twin is a non-RL digital twin for a building. It predicts energy demand and solar generation, simulates energy-control decisions, and compares baseline vs optimized operation.

The first serious version is:

- one commercial building
- hourly data
- 24-hour forecast horizon
- solar + battery + grid import/export simulation
- baseline, rule-based, and optimized controllers
- dashboard for forecast, scenario lab, policy comparison, and MLOps/data health

TD-MPC2/RL comes later after the simulator and data layer are stable.

## Current System Diagram

```mermaid
flowchart LR
    A[Demo data or imported CSV] --> B[Ingestion validation]
    B --> C[Forecast contract]
    C --> D[Digital twin simulator]
    D --> E[Controller comparison]
    E --> F[Dashboard]

    B --> G[Data health API]
    C --> H[Forecast API]
    D --> I[Simulation API]
    E --> J[Optimization API]

    K[Future: Building Data Genome] -.-> B
    L[Future: NASA POWER weather] -.-> B
    M[Future: TFT model] -.-> C
    N[Future: MLflow/Prefect/Evidently] -.-> G
```

## Build Timeline

```mermaid
flowchart TD
    P0[Phase 0: Local MVP skeleton] --> P1[Phase 1: Data import and validation]
    P1 --> P2[Phase 2: Real public meter data adapter]
    P2 --> P3[Phase 3: Weather and solar enrichment]
    P3 --> P4[Phase 4: Forecasting upgrade]
    P4 --> P5[Phase 5: Better simulator and optimizer]
    P5 --> P6[Phase 6: MLOps pipeline]
    P6 --> P7[Phase 7: Database and cache]
    P7 --> P8[Phase 8: Streaming if needed]
    P8 --> P9[Phase 9: RL-ready environment]
```

## Phase Status

| phase | status | what it means |
| --- | --- | --- |
| 0. Local MVP skeleton | Done | Dashboard, APIs, forecast contract, simulator, optimizer, tests |
| 1. Data import and validation | Done | CSV import, schema validation, data-health UI |
| 2. Real public meter data adapter | Downloader + preparation ready | Download direct CSV/ZIP public data and convert one building into our schema |
| 3. Weather and solar enrichment | NASA POWER adapter ready | Add weather/solar/price/carbon columns by timestamp |
| 4. Forecasting upgrade | Regression + local MLP ready | DL model must beat promoted regression benchmark |
| 5. Simulator and optimizer upgrade | Configurable economics ready | More realistic battery, tariff, comfort, HVAC behavior |
| 6. MLOps pipeline | MLflow/Prefect/drift hooks ready | Optional registry, orchestration, and drift reports |
| 7. Database and cache | Postgres + Redis adapters ready | Opt-in production run storage and API response caching |
| 8. Streaming | Deferred | Kafka/Flink only if live telemetry needs it |
| 9. RL-ready environment | Deferred | Gymnasium-style interface for future TD-MPC2 |
| 10. Auth/deployment | Docker + token auth ready | Bearer-token API auth and Docker run path |

## Decision Log

| decision | options | current choice | why |
| --- | --- | --- | --- |
| First data layer | demo only, CSV, DuckDB, Postgres | CSV + validation | Teaches schema discipline without infrastructure overhead |
| Forecast model now | coded baseline, local artifact, TFT immediately | regression + local MLP artifacts | Stronger local benchmark plus first dependency-free DL model |
| Streaming now | none, Kafka, Kafka + Flink | none | No live telemetry yet |
| Database now | files, SQLite, DuckDB, Postgres/TimescaleDB | SQLite locally, Postgres optional | Keep laptop workflow simple while enabling production run storage |
| Cache now | none, in-process, Redis | Redis optional | Cache expensive API responses only when a Redis URL is configured |
| Public meter data | downloader, adapter, manual CSV only | downloader + adapter | Supports real data shape while keeping dataset choice explicit |
| Public dataset prep | manual import, one preparation command, auto downloader | downloader + preparation command | Automates local public CSV/ZIP fetch and conversion |
| Weather enrichment | NASA POWER first, manual join, placeholders | manual join | Teaches the join contract before adding an external API |
| Forecasting upgrade | jump to deep learning, measured baseline first | measured baseline | Gives us metrics before adding heavier ML |
| Simulator economics | energy cost only, demand charge, battery wear | demand charge + battery wear | Makes peak reduction and cycling tradeoffs visible |
| Economic assumptions | hardcoded, API params, dashboard controls | dashboard controls | Lets users test policy sensitivity without code changes |
| Scenario assumptions | fixed presets, API params, dashboard controls | dashboard controls | Lets users tune weather, price, EV, and comfort assumptions |
| Optimizer economics | fixed schedule scoring, tariff-aware schedule | tariff-aware schedule | Policy actions now respond to tariff and wear assumptions |
| Weather source | manual CSV only, NASA POWER adapter | NASA POWER adapter | Automates temperature and solar enrichment while preserving CSV join path |
| MLOps first step | no tracking, local JSON, MLflow now | local JSON | Establishes run contract before adding MLflow/Prefect |
| Run history | latest file only, SQLite, MLflow | SQLite | Lets dashboard/API compare recent local runs without new services |
| Scheduler | manual command, cron, Prefect | project-owned scheduler script | Gives repeatable local automation before installing system cron or adding Prefect |
| Retraining first step | no retraining, local artifact, MLflow registry | local artifact + promotion gate | Makes retraining concrete without a service dependency |
| Daily monitoring | none, dashboard summary, Evidently | dashboard summary | Daily runs need trend visibility, not heavy monitoring infrastructure yet |
| Daily automation | manual, launchd, cron, Prefect | launchd generator | macOS can run one local pipeline per day without a long-running loop |
| First DL model | no DL, dependency-free MLP, PyTorch TFT | dependency-free MLP | Teaches real backprop training before adding heavy model infrastructure |
| Multi-building | one imported building, dynamic Genome selector, separate app | dynamic Genome selector | Uses the downloaded public dataset without changing forecast/sim contracts |
| MLflow | none, local JSON only, MLflow registry | optional MLflow | Logs runs/artifacts when tracking URI is configured |
| Orchestration | local scheduler, launchd, Prefect | local plus optional Prefect | Prefect wraps the same pipeline instead of replacing it |
| Drift | none, simple trend, Evidently | dependency-free drift report | Gives drift signal now and leaves room for native Evidently reports |
| Auth/deploy | local only, token auth, full OAuth | token auth + Docker | Enough for private deployment without user accounts |

## Next Step

Recommended next step: harden the production integrations.

That means:

1. Replace the dependency-free drift JSON with native Evidently HTML/JSON reports.
2. Add normalized Postgres tables for meter readings, forecasts, simulations, and optimization schedules.
3. Add stronger deployment auth if this becomes more than a private demo.

Options:

- **Native Evidently**: richer drift diagnostics and shareable reports.
- **Normalized DB tables**: query historical forecasts/simulations without reading JSON payloads.
- **Stronger auth**: needed for user accounts, roles, or public deployment.

My recommendation: add normalized forecast/simulation tables next, because they make the dashboard, MLOps, and reporting more useful.
