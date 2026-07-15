# Manual Weather And Enrichment Join

The project can join a second CSV onto imported meter rows by timestamp.

This is the offline-first version of weather enrichment. Later, a NASA POWER adapter can produce the same enrichment CSV shape.

## Enrichment Columns

The enrichment CSV must have a timestamp column and at least one of:

| column | meaning |
| --- | --- |
| `outside_temp_c` | outdoor temperature |
| `solar_kw` | solar production or estimate |
| `price_usd_per_kwh` | electricity import price |
| `carbon_kg_per_kwh` | grid carbon intensity |

Example:

```csv
timestamp,outside_temp_c,solar_kw,price_usd_per_kwh,carbon_kg_per_kwh
2026-07-07T00:00:00,18.5,0.0,0.22,0.41
2026-07-07T01:00:00,18.2,0.0,0.20,0.40
```

## Import With Enrichment

Energy Twin schema input:

```bash
python3 scripts/import_dataset.py data/raw/my-building.csv \
  --enrichment-csv data/raw/my-weather.csv \
  --output data/processed/current-meter.csv
```

Building Data Genome-style wide input:

```bash
python3 scripts/import_dataset.py data/raw/building-meter.csv \
  --format bdg-wide \
  --building-column building_a \
  --enrichment-csv data/raw/my-weather.csv \
  --output data/processed/current-meter.csv
```

Require every meter row to have matching enrichment:

```bash
python3 scripts/import_dataset.py data/raw/building-meter.csv \
  --format bdg-wide \
  --building-column building_a \
  --enrichment-csv data/raw/my-weather.csv \
  --require-enrichment-match \
  --output data/processed/current-meter.csv
```

## Why This Comes Before NASA POWER

The core problem is joining external features to meter data by timestamp. A manual CSV join is easy to test locally. Once that is stable, NASA POWER can become a data producer that emits this same enrichment shape.
