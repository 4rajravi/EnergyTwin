from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from energytwin.data import generate_history, get_scenario
from energytwin.adapters.building_data_genome import convert_bdg_long_csv, convert_bdg_wide_csv
from energytwin.adapters.nasa_power import NasaPowerRequest, build_nasa_power_url, nasa_power_json_to_enrichment_rows, write_enrichment_csv
from energytwin.automation import LaunchdJobConfig, build_launchd_plist, write_launchd_plist
from energytwin.domain import BatterySpec, TariffSpec
from energytwin.enrichment import enrich_rows_from_csv
from energytwin.forecasting import MODEL_TRAINED_HOURLY, MODEL_TRAINED_REGRESSION, build_forecast, evaluate_forecast_baseline
from energytwin.ingestion import DataValidationError, data_health, load_meter_csv, validate_rows, write_demo_csv
from energytwin.mlops import LocalRunConfig, local_monitoring_summary, read_latest_local_run, run_local_experiment
from energytwin.model_artifacts import (
    PromotionPolicy,
    decide_model_promotion,
    load_forecast_model,
    save_forecast_model,
    train_hourly_forecast_model,
    train_regression_forecast_model,
)
from energytwin.public_pipeline import PublicDatasetConfig, prepare_public_dataset
from energytwin.scheduler import LocalScheduleConfig, run_local_schedule
from energytwin.simulator import compare_policies, schedule_for, simulate
from energytwin.sources import load_history
from energytwin.storage import latest_run_report, list_run_summaries, save_run_report


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

    def test_trained_hourly_model_artifact_preserves_forecast_contract(self) -> None:
        history = generate_history()
        target = ROOT / "models" / "test-forecast-model.json"
        try:
            artifact = train_hourly_forecast_model(history)
            save_forecast_model(artifact, target)
            loaded = load_forecast_model(target)
            self.assertIsNotNone(loaded)
            forecast = build_forecast(history, model_name=MODEL_TRAINED_HOURLY, model_artifact=loaded)
            metrics = evaluate_forecast_baseline(history, model_name=MODEL_TRAINED_HOURLY)
            self.assertEqual(len(forecast), 24)
            self.assertEqual(loaded["training_rows"], len(history))
            self.assertGreater(metrics.evaluated_points, 0)
            self.assertGreater(metrics.mae_kw, 0)
        finally:
            target.unlink(missing_ok=True)

    def test_trained_regression_model_artifact_preserves_forecast_contract(self) -> None:
        history = generate_history()
        target = ROOT / "models" / "test-regression-forecast-model.json"
        try:
            artifact = train_regression_forecast_model(history)
            save_forecast_model(artifact, target)
            loaded = load_forecast_model(target)
            self.assertIsNotNone(loaded)
            forecast = build_forecast(history, model_name=MODEL_TRAINED_REGRESSION, model_artifact=loaded)
            metrics = evaluate_forecast_baseline(history, model_name=MODEL_TRAINED_REGRESSION)
            self.assertEqual(len(forecast), 24)
            self.assertEqual(loaded["training_rows"], len(history))
            self.assertEqual(loaded["model_name"], MODEL_TRAINED_REGRESSION)
            self.assertGreater(metrics.evaluated_points, 0)
        finally:
            target.unlink(missing_ok=True)

    def test_model_promotion_requires_metric_improvement(self) -> None:
        promoted = decide_model_promotion(
            {"mae_kw": 90.0, "smape": 0.1},
            {"mae_kw": 100.0, "smape": 0.1},
            PromotionPolicy(min_improvement_pct=0.05),
        )
        rejected = decide_model_promotion(
            {"mae_kw": 99.0, "smape": 0.1},
            {"mae_kw": 100.0, "smape": 0.1},
            PromotionPolicy(min_improvement_pct=0.05),
        )
        self.assertTrue(promoted["promoted"])
        self.assertFalse(rejected["promoted"])

    def test_custom_scenario_overrides_affect_forecast(self) -> None:
        base = get_scenario("normal")
        custom = get_scenario("normal", {"temperature_delta_c": 8.0, "cloud_cover": 0.9, "ev_spike_kw": 150.0})
        base_forecast = build_forecast(generate_history(scenario=base), scenario=base)
        custom_forecast = build_forecast(generate_history(scenario=custom), scenario=custom)
        self.assertGreater(max(point.demand_kw for point in custom_forecast), max(point.demand_kw for point in base_forecast))
        self.assertLess(max(point.solar_kw for point in custom_forecast), max(point.solar_kw for point in base_forecast))

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

    def test_simulation_cost_breakdown_includes_tariff_and_battery_wear(self) -> None:
        forecast = build_forecast(generate_history(), "price")
        _, baseline = simulate(forecast, "baseline", tariff=TariffSpec(demand_charge_usd_per_kw_day=5.0))
        _, optimized = simulate(forecast, "optimized", tariff=TariffSpec(demand_charge_usd_per_kw_day=5.0))
        self.assertGreater(baseline.demand_charge_usd, 0)
        self.assertEqual(baseline.battery_wear_cost_usd, 0)
        self.assertGreater(optimized.battery_wear_cost_usd, 0)
        expected = (
            optimized.energy_cost_usd
            + optimized.demand_charge_usd
            + optimized.battery_wear_cost_usd
            - optimized.export_credit_usd
        )
        self.assertAlmostEqual(optimized.total_cost_usd, round(expected, 2), delta=0.02)

    def test_policy_comparison_uses_custom_economics(self) -> None:
        forecast = build_forecast(generate_history(), "price")
        low_demand_charge = compare_policies(forecast, tariff=TariffSpec(demand_charge_usd_per_kw_day=0.0))
        high_demand_charge = compare_policies(forecast, tariff=TariffSpec(demand_charge_usd_per_kw_day=10.0))
        self.assertGreater(high_demand_charge["baseline"]["total_cost_usd"], low_demand_charge["baseline"]["total_cost_usd"])
        self.assertGreater(high_demand_charge["optimized"]["demand_charge_usd"], low_demand_charge["optimized"]["demand_charge_usd"])

    def test_optimized_schedule_responds_to_economic_assumptions(self) -> None:
        forecast = build_forecast(generate_history(), "price")
        battery = BatterySpec()
        low_charge_schedule = schedule_for(
            "optimized",
            forecast,
            battery,
            tariff=TariffSpec(demand_charge_usd_per_kw_day=0.0),
        )
        high_charge_schedule = schedule_for(
            "optimized",
            forecast,
            battery,
            tariff=TariffSpec(demand_charge_usd_per_kw_day=10.0),
        )
        self.assertNotEqual(low_charge_schedule, high_charge_schedule)

    def test_high_battery_wear_reduces_optimized_throughput(self) -> None:
        forecast = build_forecast(generate_history(), "price")
        _, low_wear = simulate(forecast, "optimized", battery=BatterySpec(wear_cost_usd_per_kwh_throughput=0.0))
        _, high_wear = simulate(forecast, "optimized", battery=BatterySpec(wear_cost_usd_per_kwh_throughput=0.2))
        self.assertLessEqual(high_wear.battery_cycles, low_wear.battery_cycles)

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

    def test_nasa_power_url_builder_targets_hourly_point_json(self) -> None:
        url = build_nasa_power_url(NasaPowerRequest(latitude=40.0, longitude=-105.0, start="20260701", end="20260702"))
        self.assertIn("/api/temporal/hourly/point", url)
        self.assertIn("parameters=T2M%2CALLSKY_SFC_SW_DWN", url)
        self.assertIn("format=JSON", url)
        self.assertIn("time-standard=UTC", url)

    def test_nasa_power_json_converts_to_enrichment_rows(self) -> None:
        payload = {
            "properties": {
                "parameter": {
                    "T2M": {"2026070100": 18.4, "2026070101": 18.1},
                    "ALLSKY_SFC_SW_DWN": {"2026070100": 0.0, "2026070101": 0.05},
                }
            }
        }
        rows = nasa_power_json_to_enrichment_rows(payload, solar_kwp=100.0, performance_ratio=0.8)
        self.assertEqual(rows[0]["timestamp"], "2026-07-01T00:00:00")
        self.assertEqual(rows[0]["outside_temp_c"], 18.4)
        self.assertEqual(rows[1]["solar_kw"], 4.0)

    def test_nasa_power_enrichment_csv_roundtrip(self) -> None:
        target = ROOT / "data" / "processed" / "test-nasa-enrichment.csv"
        try:
            rows = [
                {"timestamp": "2026-07-01T00:00:00", "outside_temp_c": 18.4, "solar_kw": 0.0},
                {"timestamp": "2026-07-01T01:00:00", "outside_temp_c": 18.1, "solar_kw": 4.0},
            ]
            write_enrichment_csv(target, rows)
            meter_rows = generate_history(hours=2)
            meter_rows[0]["timestamp"] = "2026-07-01T00:00:00"
            meter_rows[1]["timestamp"] = "2026-07-01T01:00:00"
            enriched = enrich_rows_from_csv(meter_rows, target, require_match=True)
            self.assertEqual(enriched[1]["solar_kw"], 4.0)
        finally:
            target.unlink(missing_ok=True)

    def test_prepare_public_dataset_converts_and_enriches_bdg_wide(self) -> None:
        source = ROOT / "data" / "processed" / "test-public-wide.csv"
        enrichment = ROOT / "data" / "processed" / "test-public-enrichment.csv"
        output = ROOT / "data" / "processed" / "test-current-meter.csv"
        try:
            source.write_text(
                "timestamp,building_a,building_b\n"
                "2026-07-07T00:00:00,120.5,98.1\n"
                "2026-07-07T01:00:00,121.5,97.2\n",
                encoding="utf-8",
            )
            enrichment.write_text(
                "timestamp,outside_temp_c,solar_kw,price_usd_per_kwh,carbon_kg_per_kwh\n"
                "2026-07-07T00:00:00,18.5,0.0,0.22,0.41\n"
                "2026-07-07T01:00:00,18.2,0.0,0.20,0.40\n",
                encoding="utf-8",
            )
            summary = prepare_public_dataset(
                PublicDatasetConfig(
                    input_path=source,
                    input_format="bdg-wide",
                    output_path=output,
                    building_column="building_a",
                    enrichment_csv=enrichment,
                    require_enrichment_match=True,
                )
            )
            rows = load_meter_csv(output)
            self.assertEqual(summary["row_count"], 2)
            self.assertEqual(rows[0]["demand_kw"], 120.5)
            self.assertEqual(rows[0]["outside_temp_c"], 18.5)
            self.assertEqual(rows[1]["price_usd_per_kwh"], 0.2)
        finally:
            source.unlink(missing_ok=True)
            enrichment.unlink(missing_ok=True)
            output.unlink(missing_ok=True)

    def test_local_mlops_run_writes_report(self) -> None:
        output_dir = ROOT / "mlruns" / "test-local"
        db_path = ROOT / "data" / "processed" / "test-local-runs.sqlite3"
        report_path = output_dir / "latest.json"
        try:
            report = run_local_experiment(LocalRunConfig(scenario_key="price"), output_dir=output_dir, db_path=db_path)
            self.assertEqual(report["config"]["scenario_key"], "price")
            self.assertIn("forecast_metrics", report)
            self.assertIn("policy_comparison", report)
            self.assertTrue(report_path.exists())
            latest = read_latest_local_run(output_dir=output_dir, db_path=db_path)
            self.assertIsNotNone(latest)
            self.assertEqual(latest["run_id"], report["run_id"])
            summaries = list_run_summaries(db_path=db_path)
            self.assertEqual(summaries[0]["run_id"], report["run_id"])
            self.assertEqual(summaries[0]["scenario_key"], "price")
        finally:
            db_path.unlink(missing_ok=True)
            for path in output_dir.glob("*.json"):
                path.unlink(missing_ok=True)
            output_dir.rmdir()

    def test_local_mlops_run_can_train_model_artifact(self) -> None:
        output_dir = ROOT / "mlruns" / "test-train-model"
        db_path = ROOT / "data" / "processed" / "test-train-model-runs.sqlite3"
        active_model = ROOT / "models" / "test-active-forecast-model.json"
        candidate_model = ROOT / "models" / "test-candidate-forecast-model.json"
        try:
            report = run_local_experiment(
                LocalRunConfig(
                    scenario_key="normal",
                    model_name=MODEL_TRAINED_REGRESSION,
                    train_model=True,
                    active_model_path=str(active_model),
                    candidate_model_path=str(candidate_model),
                ),
                output_dir=output_dir,
                db_path=db_path,
            )
            self.assertEqual(report["model_candidate"]["artifact_training_rows"], 168)
            self.assertTrue(candidate_model.exists())
            self.assertEqual(active_model.exists(), report["model_candidate"]["promotion"]["promoted"])
            self.assertEqual(load_forecast_model(candidate_model)["model_name"], MODEL_TRAINED_REGRESSION)
        finally:
            active_model.unlink(missing_ok=True)
            candidate_model.unlink(missing_ok=True)
            db_path.unlink(missing_ok=True)
            for path in output_dir.glob("*.json"):
                path.unlink(missing_ok=True)
            output_dir.rmdir()

    def test_storage_roundtrips_run_report(self) -> None:
        db_path = ROOT / "data" / "processed" / "test-storage-runs.sqlite3"
        report = run_local_experiment(
            LocalRunConfig(scenario_key="normal"),
            output_dir=ROOT / "mlruns" / "test-storage",
            db_path=None,
        )
        try:
            save_run_report(report, db_path=db_path)
            latest = latest_run_report(db_path=db_path)
            self.assertIsNotNone(latest)
            self.assertEqual(latest["run_id"], report["run_id"])
            summaries = list_run_summaries(limit=5, db_path=db_path)
            self.assertEqual(len(summaries), 1)
            self.assertEqual(summaries[0]["model_name"], "weighted-baseline-v1")
            self.assertGreater(summaries[0]["mae_kw"], 0)
        finally:
            db_path.unlink(missing_ok=True)
            output_dir = ROOT / "mlruns" / "test-storage"
            for path in output_dir.glob("*.json"):
                path.unlink(missing_ok=True)
            output_dir.rmdir()

    def test_monitoring_summary_reports_forecast_trend_and_promotion(self) -> None:
        db_path = ROOT / "data" / "processed" / "test-monitoring-runs.sqlite3"
        first = {
            "run_id": "run-1",
            "created_at": "2026-07-15T00:00:00+00:00",
            "config": {"source_key": "demo", "scenario_key": "normal", "model_name": "weighted-baseline-v1"},
            "forecast_metrics": {"model_name": "weighted-baseline-v1", "mae_kw": 50.0, "rmse_kw": 60.0, "smape": 0.12},
            "policy_comparison": {"optimized": {"cost_savings_pct": 4.0, "carbon_reduction_pct": 2.0, "peak_reduction_pct": 1.0}},
            "model_candidate": {},
        }
        second = {
            "run_id": "run-2",
            "created_at": "2026-07-16T00:00:00+00:00",
            "config": {"source_key": "demo", "scenario_key": "normal", "model_name": "trained-hourly-v1"},
            "forecast_metrics": {"model_name": "trained-hourly-v1", "mae_kw": 45.0, "rmse_kw": 55.0, "smape": 0.11},
            "policy_comparison": {"optimized": {"cost_savings_pct": 5.0, "carbon_reduction_pct": 2.5, "peak_reduction_pct": 1.4}},
            "model_candidate": {"promotion": {"promoted": True, "reason": "candidate improved mae_kw by 10.00%"}},
        }
        try:
            save_run_report(first, db_path=db_path)
            save_run_report(second, db_path=db_path)
            monitoring = local_monitoring_summary(db_path=db_path)
            self.assertEqual(monitoring["run_count"], 2)
            self.assertEqual(monitoring["status"], "improving")
            self.assertEqual(monitoring["latest"]["run_id"], "run-2")
            self.assertEqual(monitoring["best"]["mae_kw"], 45.0)
            self.assertEqual(monitoring["promotion"]["promoted"], 1)
        finally:
            db_path.unlink(missing_ok=True)

    def test_local_scheduler_runs_pipeline_multiple_times(self) -> None:
        output_dir = ROOT / "mlruns" / "test-scheduler"
        db_path = ROOT / "data" / "processed" / "test-scheduler-runs.sqlite3"
        slept = []
        try:
            reports = run_local_schedule(
                LocalScheduleConfig(
                    run_config=LocalRunConfig(scenario_key="price"),
                    interval_seconds=0.01,
                    max_runs=2,
                    output_dir=output_dir,
                    db_path=db_path,
                ),
                sleep_fn=lambda seconds: slept.append(seconds),
            )
            self.assertEqual(len(reports), 2)
            self.assertEqual(slept, [0.01])
            self.assertNotEqual(reports[0]["run_id"], reports[1]["run_id"])
            self.assertEqual(len(list_run_summaries(db_path=db_path)), 2)
        finally:
            db_path.unlink(missing_ok=True)
            for path in output_dir.glob("*.json"):
                path.unlink(missing_ok=True)
            output_dir.rmdir()

    def test_launchd_plist_runs_daily_one_shot_pipeline(self) -> None:
        plist = build_launchd_plist(
            LaunchdJobConfig(
                label="com.energytwin.test",
                hour=6,
                minute=30,
                source_key="demo",
                scenario_key="price",
                project_root=ROOT,
                python_executable="/usr/bin/python3",
            )
        )
        args = plist["ProgramArguments"]
        self.assertEqual(plist["Label"], "com.energytwin.test")
        self.assertEqual(plist["StartCalendarInterval"], {"Hour": 6, "Minute": 30})
        self.assertIn("scripts/schedule_local_pipeline.py", args[1])
        self.assertIn("--train-model", args)
        self.assertIn("--max-runs", args)
        self.assertEqual(args[args.index("--max-runs") + 1], "1")

    def test_launchd_plist_writer_creates_file(self) -> None:
        target = ROOT / "launchd" / "test-energytwin.plist"
        try:
            written = write_launchd_plist(
                LaunchdJobConfig(label="com.energytwin.test", project_root=ROOT),
                target,
            )
            self.assertEqual(written, target)
            self.assertTrue(target.exists())
            self.assertIn(b"com.energytwin.test", target.read_bytes())
        finally:
            target.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
