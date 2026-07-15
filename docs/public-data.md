# Public Data Adapters

This project does not download public datasets automatically yet. The current step is an offline adapter: take a public-data CSV you already have and convert one building into the internal Energy Twin schema.

## Building Data Genome-Style Imports

Two common meter CSV shapes are supported.

### Wide Format

One timestamp column and one column per building:

```csv
timestamp,building_a,building_b
2026-07-07T00:00:00,120.5,98.1
2026-07-07T01:00:00,121.5,97.2
```

Import one building:

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

Import one building:

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

Not yet. The adapter is ready for public data, but we can keep building and testing with local sample files.

When we decide to use real public data, download the meter CSV into `data/raw/`, then run one of the import commands above.
