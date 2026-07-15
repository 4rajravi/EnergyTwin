from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from energytwin.data import generate_history
from energytwin.domain import BatterySpec
from energytwin.forecasting import build_forecast
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


if __name__ == "__main__":
    unittest.main()
