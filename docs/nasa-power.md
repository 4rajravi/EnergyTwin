# NASA POWER Weather Adapter

The project can create an enrichment CSV from NASA POWER hourly weather data.

NASA POWER's Hourly API returns analysis-ready hourly solar and meteorological data. The official docs show point requests under:

```text
https://power.larc.nasa.gov/api/temporal/hourly/point
```

The adapter requests:

- `T2M` for air temperature at 2 meters
- `ALLSKY_SFC_SW_DWN` for all-sky surface shortwave downward irradiance

It writes this Energy Twin enrichment shape:

```csv
timestamp,outside_temp_c,solar_kw
2026-07-01T00:00:00,18.4,0.0
2026-07-01T01:00:00,18.1,4.0
```

## Fetch From NASA POWER

```bash
python3 scripts/fetch_nasa_power.py \
  --latitude 40.0 \
  --longitude -105.0 \
  --start 20260701 \
  --end 20260707 \
  --solar-kwp 260 \
  --output data/raw/nasa-power-enrichment.csv
```

Then import a meter file with that enrichment:

```bash
python3 scripts/import_dataset.py data/raw/building-meter.csv \
  --format bdg-wide \
  --building-column building_a \
  --enrichment-csv data/raw/nasa-power-enrichment.csv \
  --output data/processed/current-meter.csv
```

## Offline Testing

Use `--from-json` with a saved NASA POWER response:

```bash
python3 scripts/fetch_nasa_power.py \
  --latitude 40.0 \
  --longitude -105.0 \
  --start 20260701 \
  --end 20260707 \
  --from-json data/raw/nasa-power-response.json \
  --output data/raw/nasa-power-enrichment.csv
```

## Solar Estimate

`solar_kw` is estimated as:

```text
solar_kw = irradiance * solar_kwp * performance_ratio
```

Default `performance_ratio` is `0.82`. This is a simple first approximation; later we can improve it with panel orientation, inverter limits, and local site assumptions.
