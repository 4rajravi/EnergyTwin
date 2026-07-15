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

The default real-data path is now hard-coded:

```bash
python3 scripts/prepare_default_real_data.py
```

That command fetches NASA POWER enrichment if needed and writes `data/processed/current-meter.csv`.
The hard-coded Building Data Genome 2 profile expects:

```text
data/raw/buildingdatagenomeproject2/electricity_cleaned.csv
data/raw/buildingdatagenomeproject2/metadata.csv
data/raw/buildingdatagenomeproject2/weather.csv
```

It selects `Hog_office_Betsy`, an office building with complete 2016-2017 electricity data and metadata coordinates for NASA POWER.
