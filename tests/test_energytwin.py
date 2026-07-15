from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from energytwin.data import generate_history
from energytwin.adapters.building_data_genome import convert_bdg_long_csv, convert_bdg_wide_csv
from energytwin.domain import BatterySpec
from energytwin.enrichment import enrich_rows_from_csv
from energytwin.forecasting import build_forecast, evaluate_forecast_baseline
from energytwin.ingestion import DataValidationError, data_health, load_meter_csv, validate_rows, write_demo_csv
from energytwin.simulator import simulate
from energytwin.sources import load_history


class EnergyTwinTests(unittest.TestCase):
    def test_forecast_returns_24_hours(self) -> None:
        history = generate_history()
        forecast = build_forecast(history)
        self.assertEqual(len(forecast), 24)
        self.assertTrue(all(point.demand_p10_kw <= point.demand_kw <= point.demand_p90_kw for point in forecast))
        self.assertTrue(all(point.solar_p10_kw <= point.solar_kw <= point.solar_p90_kw for point in forecast))

    def test_forecast_baseline_evaluation_reports_metrics(self) -> None:
        metrics = evaluate_forecast_baseline(generate_history())
        self.assertGreater(metrics.evaluated_points, 0)
        self.assertGreater(metrics.mae_kw, 0)
        self.assertGreater(metrics.rmse_kw, 0)
        self.assertGreaterEqual(metrics.coverage_p10_p90, 0)
        self.assertLessEqual(metrics.coverage_p10_p90, 1)

    def test_weighted_forecast_model_preserves_forecast_contract(self) -> None:
        history = generate_history()
        weighted = build_forecast(history, model_name="weighted-baseline-v1")
        seasonal = build_forecast(history, model_name="seasonal")
        self.assertEqual(len(weighted), len(seasonal))
        self.assertTrue(all(point.demand_kw >= 0 for point in weighted))

    def test_simulation_respects_battery_bounds(self) -> None:
        forecast = build_forecast(generate_history(), "price")
        battery = BatterySpec()
        points, _ = simulate(forecast, "optimized", battery)
        self.assertTrue(all(battery.min_soc_kwh <= point.battery_soc_kwh <= battery.max_soc_kwh for point in points))
        self.assertTrue(all(abs(point.battery_kw) <= battery.max_kw for point in points))

    def test_optimized_policy_improves_cost_against_baseline(self) -> None:
        forecast = build_forecast(generate_history(), "price")
        _, baseline = simulate(forecast, "baseline")
        _, optimized = simulate(forecast, "optimized")
        self.assertLessEqual(optimized.total_cost_usd, baseline.total_cost_usd)
        self.assertLessEqual(optimized.peak_grid_kw, baseline.peak_grid_kw)

    def test_data_health_accepts_generated_rows(self) -> None:
        rows = generate_history()
        health = data_health(rows)
        self.assertEqual(health.row_count, 168)
        self.assertEqual(health.invalid_rows, 0)
        validate_rows(rows)

    def test_data_validation_rejects_bad_rows(self) -> None:
        rows = generate_history(hours=2)
        rows[1]["timestamp"] = rows[0]["timestamp"]
        with self.assertRaises(DataValidationError):
            validate_rows(rows)

    def test_data_validation_rejects_empty_dataset(self) -> None:
        with self.assertRaises(DataValidationError):
            validate_rows([])

    def test_demo_csv_roundtrip(self) -> None:
        target = ROOT / "data" / "processed" / "test-demo.csv"
        try:
            write_demo_csv(target, hours=4)
            rows = load_meter_csv(target)
            self.assertEqual(len(rows), 4)
            self.assertEqual(data_health(rows, source=str(target)).invalid_rows, 0)
        finally:
            target.unlink(missing_ok=True)

    def test_unknown_data_source_falls_back_to_demo(self) -> None:
        rows, source = load_history(source_key="unknown", scenario_key="normal")
        self.assertEqual(len(rows), 168)
        self.assertEqual(source, "demo:normal")

    def test_bdg_wide_adapter_converts_one_building_column(self) -> None:
        target = ROOT / "data" / "processed" / "test-bdg-wide.csv"
        try:
            target.write_text(
                "timestamp,building_a,building_b\n"
                "2026-07-07T00:00:00,120.5,98.1\n"
                "2026-07-07T01:00:00,121.5,97.2\n",
                encoding="utf-8",
            )
            rows = convert_bdg_wide_csv(target, building_column="building_a")
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["demand_kw"], 120.5)
            self.assertEqual(rows[0]["hour"], 0)
            validate_rows(rows)
        finally:
            target.unlink(missing_ok=True)

    def test_bdg_long_adapter_filters_building_id(self) -> None:
        target = ROOT / "data" / "processed" / "test-bdg-long.csv"
        try:
            target.write_text(
                "timestamp,building_id,meter_reading\n"
                "2026-07-07T00:00:00,bldg-1,120.5\n"
                "2026-07-07T00:00:00,bldg-2,98.1\n"
                "2026-07-07T01:00:00,bldg-1,121.5\n",
                encoding="utf-8",
            )
            rows = convert_bdg_long_csv(target, building_id="bldg-1")
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["demand_kw"], 121.5)
            validate_rows(rows)
        finally:
            target.unlink(missing_ok=True)

    def test_enrichment_csv_updates_matching_weather_rows(self) -> None:
        enrichment = ROOT / "data" / "processed" / "test-weather.csv"
        try:
            rows = generate_history(hours=2)
            enrichment.write_text(
                "timestamp,outside_temp_c,solar_kw,price_usd_per_kwh,carbon_kg_per_kwh\n"
                "2026-07-07T00:00:00,18.5,0.0,0.22,0.41\n"
                "2026-07-07T01:00:00,18.2,0.0,0.20,0.40\n",
                encoding="utf-8",
            )
            enriched = enrich_rows_from_csv(rows, enrichment, require_match=True)
            self.assertEqual(enriched[0]["outside_temp_c"], 18.5)
            self.assertEqual(enriched[0]["price_usd_per_kwh"], 0.22)
            validate_rows(enriched)
        finally:
            enrichment.unlink(missing_ok=True)

    def test_enrichment_can_require_full_timestamp_match(self) -> None:
        enrichment = ROOT / "data" / "processed" / "test-weather-partial.csv"
        try:
            rows = generate_history(hours=2)
            enrichment.write_text(
                "timestamp,outside_temp_c\n"
                "2026-07-07T00:00:00,18.5\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                enrich_rows_from_csv(rows, enrichment, require_match=True)
        finally:
            enrichment.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
