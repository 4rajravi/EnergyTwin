# AI Energy Twin Architecture

## Build Sequence

1. Ship the local MVP with deterministic data, a 24-hour forecast contract, simulator, optimizer, and dashboard.
2. Replace demo data with Building Data Genome meter data and NASA POWER weather/solar enrichment.
3. Add the training pipeline and register a Temporal Fusion Transformer model with MLflow.
4. Persist forecasts, simulations, metrics, and model metadata in Postgres/TimescaleDB.
5. Add Redis caching for repeated scenario and forecast requests.
6. Add Kafka only when live device, meter, weather, price, or carbon feeds need durable stream ingestion.
7. Add Flink only when stream features must be computed continuously with low latency.
8. Add a Gymnasium-style environment for TD-MPC2 or other RL controllers after the non-RL simulator is stable.

## Current Boundaries

- `forecasting.build_forecast` is the inference boundary. A TFT model should keep this response contract.
- `simulator.simulate` is the digital twin boundary. It accepts forecast points and a controller name.
- `optimizer.optimized_schedule` is the non-RL controller boundary.
- `server.EnergyTwinHandler` is replaceable with FastAPI without changing the core modules.

## Why Kafka And Flink Are Later

Kafka and Flink are useful when the system has multiple live streams, strict recovery semantics, event-time joins, and low-latency feature materialization. This MVP does not need that yet. A simpler batch-plus-API design is faster to validate and still leaves clean migration points.
