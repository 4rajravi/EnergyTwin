# Public Data Adapters

This project can download direct public CSV or ZIP URLs into `data/raw/`, then convert one building into the internal Energy Twin schema. You still choose the dataset and building column/id because public datasets differ in license, size, and CSV shape.

## Automatic Download

Direct CSV example:

```bash
python3 scripts/download_public_dataset.py \
  --url "https://example.org/path/to/public-meter-data.csv" \
  --output data/raw/building-meter.csv
```

ZIP example:

```bash
python3 scripts/download_public_dataset.py \
  --url "https://example.org/path/to/public-meter-data.zip" \
  --output data/raw/building-meter.csv \
  --extract-zip \
  --extract-member "meters/building-meter.csv"
```

Use `--sha256` when the dataset page provides a checksum. Use `--max-mb` to protect yourself from unexpectedly large files.

## Hard-Coded Default Profile

The project has one hard-coded real-data profile:

| setting | value |
| --- | --- |
| dataset folder | `data/raw/buildingdatagenomeproject2/` |
| meter CSV | `electricity_cleaned.csv` |
| metadata CSV | `metadata.csv` |
| weather CSV | `weather.csv` |
| selected building | `Hog_office_Betsy` |
| building type | office |
| NASA enrichment output | `data/raw/nasa-power-enrichment.csv` |
| prepared output | `data/processed/current-meter.csv` |

Run it:

```bash
python3 scripts/prepare_default_real_data.py
```

This derives the date range from the selected electricity meter, derives coordinates from `metadata.csv`, fetches NASA POWER weather/solar enrichment for the same dates, then prepares `data/processed/current-meter.csv`.

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
  --model trained-mlp-v1 \
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

Yes, before real-data training. Download a public meter CSV or ZIP member into `data/raw/`, then run `scripts/prepare_public_dataset.py`.

The downloader intentionally accepts a direct URL instead of hiding a dataset choice. That keeps you in control of license, file size, building selection, and checksum verification.
