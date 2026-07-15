# Public Data Adapters

This project does not download large public datasets automatically yet. The current workflow is automated after you place a public-data CSV under `data/raw/`: choose one building, convert it into the internal Energy Twin schema, optionally join enrichment, then train using `--source imported`.

## One Command Preparation

Wide-format example:

```bash
python3 scripts/prepare_public_dataset.py data/raw/building-meter.csv \
  --format bdg-wide \
  --building-column building_a \
  --output data/processed/current-meter.csv
```

Long-format example:

```bash
python3 scripts/prepare_public_dataset.py data/raw/building-meter.csv \
  --format bdg-long \
  --building-id bldg-1 \
  --output data/processed/current-meter.csv
```

With enrichment:

```bash
python3 scripts/prepare_public_dataset.py data/raw/building-meter.csv \
  --format bdg-wide \
  --building-column building_a \
  --enrichment-csv data/processed/weather-enrichment.csv \
  --require-enrichment-match \
  --output data/processed/current-meter.csv
```

Then train and record an MLOps run:

```bash
python3 scripts/run_local_pipeline.py \
  --source imported \
  --scenario price \
  --model trained-regression-v1 \
  --train-model
```

The dashboard will show the imported source when `data/processed/current-meter.csv` exists.

## Building Data Genome-Style Imports

Two common meter CSV shapes are supported.

### Wide Format

One timestamp column and one column per building:

```csv
timestamp,building_a,building_b
2026-07-07T00:00:00,120.5,98.1
2026-07-07T01:00:00,121.5,97.2
```

Import one building directly:

```bash
python3 scripts/import_dataset.py data/raw/building-meter.csv \
  --format bdg-wide \
  --building-column building_a \
  --output data/processed/current-meter.csv
```

### Long Format

One row per building per timestamp:

```csv
timestamp,building_id,meter_reading
2026-07-07T00:00:00,bldg-1,120.5
2026-07-07T00:00:00,bldg-2,98.1
2026-07-07T01:00:00,bldg-1,121.5
```

Import one building directly:

```bash
python3 scripts/import_dataset.py data/raw/building-meter.csv \
  --format bdg-long \
  --building-id bldg-1 \
  --output data/processed/current-meter.csv
```

## Default Enrichment Values

Building meter files usually contain demand only. The adapter fills the other required columns with defaults:

| field | default |
| --- | --- |
| `solar_kw` | `0.0` |
| `outside_temp_c` | `22.0` |
| `price_usd_per_kwh` | `0.18` |
| `carbon_kg_per_kwh` | `0.38` |

Override them if needed:

```bash
python3 scripts/import_dataset.py data/raw/building-meter.csv \
  --format bdg-wide \
  --building-column building_a \
  --default-temp-c 24 \
  --default-price 0.21 \
  --default-carbon 0.42
```

## Do You Need To Download Data Now?

Yes, before real-data training. Download a public meter CSV into `data/raw/`, then run `scripts/prepare_public_dataset.py`.

The script prepares local files only. It does not fetch large datasets because those sources vary in size, license, and download mechanism.
