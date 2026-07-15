# Data Import

The app can run on generated demo data or a validated local CSV.

## Current Command

Create a valid demo import file:

```bash
python3 scripts/import_dataset.py --make-demo --output data/processed/current-meter.csv
```

Import your own CSV:

```bash
python3 scripts/import_dataset.py data/raw/my-building.csv --output data/processed/current-meter.csv
```

After import, restart the dashboard and choose `Imported CSV` from the data-source selector.

## Required Columns

| column | meaning | example |
| --- | --- | --- |
| `timestamp` | ISO timestamp, hourly and increasing | `2026-07-07T00:00:00` |
| `hour` | hour of day | `0` |
| `demand_kw` | building electricity demand | `273.46` |
| `solar_kw` | solar generation | `0.0` |
| `outside_temp_c` | outdoor temperature | `16.24` |
| `price_usd_per_kwh` | electricity import price | `0.1815` |
| `carbon_kg_per_kwh` | grid carbon intensity | `0.38` |

## Validation Rules

- all required columns must exist
- timestamps must parse as ISO datetimes
- timestamps must be strictly increasing
- `hour` must be from `0` to `23`
- demand, solar, price, and carbon must be non-negative
- outside temperature must be between `-60` and `70` Celsius

## Public Data

You do not need to download public data yet.

When we are ready, the next public-data step is to adapt Building Data Genome meter readings into this schema, then enrich the rows with NASA POWER weather and solar variables.
