from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from energytwin.data import generate_history
from energytwin.domain import BatterySpec
from energytwin.forecasting import build_forecast
from energytwin.ingestion import DataValidationError, data_health, load_meter_csv, validate_rows, write_demo_csv
from energytwin.simulator import simulate


class EnergyTwinTests(unittest.TestCase):
    def test_forecast_returns_24_hours(self) -> None:
        history = generate_history()
        forecast = build_forecast(history)
        self.assertEqual(len(forecast), 24)
        self.assertTrue(all(point.demand_p10_kw <= point.demand_kw <= point.demand_p90_kw for point in forecast))
        self.assertTrue(all(point.solar_p10_kw <= point.solar_kw <= point.solar_p90_kw for point in forecast))

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

    def test_demo_csv_roundtrip(self) -> None:
        target = ROOT / "data" / "processed" / "test-demo.csv"
        try:
            write_demo_csv(target, hours=4)
            rows = load_meter_csv(target)
            self.assertEqual(len(rows), 4)
            self.assertEqual(data_health(rows, source=str(target)).invalid_rows, 0)
        finally:
            target.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
