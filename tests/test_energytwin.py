from __future__ import annotations

import hashlib
import os
import re
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from energytwin.data import generate_history, get_scenario
from energytwin.adapters.building_data_genome import convert_bdg_long_csv, convert_bdg_wide_csv
from email.message import Message

from energytwin.adapters.building_data_genome2 import (
    BuildingDataGenome2Config,
    ensure_building_data_genome2_csv,
    list_building_data_genome2_buildings,
    prepare_building_data_genome2,
)
from energytwin.adapters.nasa_power import NasaPowerRequest, build_nasa_power_url, nasa_power_json_to_enrichment_rows, write_enrichment_csv
from energytwin.auth import request_authorized
from energytwin.automation import LaunchdJobConfig, build_launchd_plist, write_launchd_plist
from energytwin.cache import api_cache_key, cache_status
from energytwin.district import aggregate_forecasts
from energytwin.drift_reports import build_drift_report, render_drift_html
from energytwin.domain import BatterySpec, ForecastPoint, TariffSpec
from energytwin.downloads import DownloadConfig, download_public_dataset
from energytwin.enrichment import enrich_rows_from_csv
from energytwin.forecasting import (
    MODEL_TRAINED_HOURLY,
    MODEL_TRAINED_MLP,
    MODEL_TRAINED_REGRESSION,
    build_forecast,
    evaluate_forecast_baseline,
)
from energytwin.ingestion import DataValidationError, data_health, load_meter_csv, validate_rows, write_demo_csv
from energytwin.mlops import LocalRunConfig, local_monitoring_summary, read_latest_local_run, run_local_experiment
from energytwin.model_artifacts import (
    PromotionPolicy,
    decide_model_promotion,
    load_forecast_model,
    save_forecast_model,
    train_hourly_forecast_model,
    train_mlp_forecast_model,
    train_regression_forecast_model,
)
from energytwin.public_pipeline import PublicDatasetConfig, prepare_public_dataset
from energytwin.production_db import RUNS_INDEX_SQL, RUNS_TABLE_SQL
from energytwin.real_data_defaults import DEFAULT_REAL_DATA_CONFIG
from energytwin.scheduler import LocalScheduleConfig, run_local_schedule
from energytwin.simulator import compare_policies, schedule_for, simulate
from energytwin.sources import load_history
from energytwin.storage import active_storage_backend, latest_run_report, list_run_summaries, save_run_report


class EnergyTwinTests(unittest.TestCase):
    def test_forecast_returns_24_hours(self) -> None:
        history = generate_history()
        forecast = build_forecast(history)
        self.assertEqual(len(forecast), 24)
        self.assertTrue(all(point.demand_p10_kw <= point.demand_kw <= point.demand_p90_kw for point in forecast))
        self.assertTrue(all(point.solar_p10_kw <= point.solar_kw <= point.solar_p90_kw for point in forecast))

    def test_dashboard_static_html_has_unique_ids(self) -> None:
        html = (ROOT / "src" / "energytwin" / "app" / "static" / "index.html").read_text(encoding="utf-8")
        ids = re.findall(r'\bid="([^"]+)"', html)
        duplicates = sorted({value for value in ids if ids.count(value) > 1})
        self.assertEqual(duplicates, [])

    def test_redis_cache_key_is_stable_and_opt_in(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(api_cache_key("/api/forecast", {"b": ["2"], "a": ["1"]}))

        with patch.dict(os.environ, {"ENERGYTWIN_REDIS_URL": "redis://localhost:6379/0"}, clear=True):
            first = api_cache_key("/api/forecast", {"b": ["2"], "a": ["1"]})
            second = api_cache_key("/api/forecast", {"a": ["1"], "b": ["2"]})
            self.assertEqual(first, second)
            self.assertIn("/api/forecast?a=1&b=2", first)
            self.assertIsNone(api_cache_key("/api/mlops-run", {}))
            self.assertTrue(cache_status()["enabled"])

    def test_production_db_schema_targets_postgres_jsonb(self) -> None:
        self.assertIn("CREATE TABLE IF NOT EXISTS runs", RUNS_TABLE_SQL)
        self.assertIn("payload_json JSONB NOT NULL", RUNS_TABLE_SQL)
        self.assertIn("CREATE INDEX IF NOT EXISTS runs_created_at_idx", RUNS_INDEX_SQL)

    def test_active_storage_backend_switches_with_database_url(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(active_storage_backend()["backend"], "sqlite")

        with patch.dict(os.environ, {"ENERGYTWIN_DATABASE_URL": "postgresql://user:secret@localhost:5432/energytwin"}, clear=True):
            backend = active_storage_backend()
            self.assertEqual(backend["backend"], "postgres")
            self.assertEqual(backend["target"], "postgresql://***@localhost:5432/energytwin")

    def test_auth_token_accepts_bearer_or_query_token(self) -> None:
        headers = Message()
        with patch.dict(os.environ, {"ENERGYTWIN_AUTH_TOKEN": "secret"}, clear=True):
            self.assertFalse(request_authorized(headers, {}))
            headers["Authorization"] = "Bearer secret"
            self.assertTrue(request_authorized(headers, {}))
            headers.replace_header("Authorization", "Bearer wrong")
            self.assertTrue(request_authorized(headers, {"token": ["secret"]}))

    def test_auth_token_accepts_sha256_env(self) -> None:
        headers = Message()
        headers["Authorization"] = "Bearer secret"
        digest = hashlib.sha256(b"secret").hexdigest()
        with patch.dict(os.environ, {"ENERGYTWIN_AUTH_TOKEN_SHA256": digest}, clear=True):
            self.assertTrue(request_authorized(headers, {}))

    def test_drift_report_compares_reference_and_current_windows(self) -> None:
        rows = generate_history(hours=96)
        for row in rows[48:]:
            row["demand_kw"] = float(row["demand_kw"]) * 1.5
        report = build_drift_report(rows)
        self.assertEqual(report["status"], "drifted")
        self.assertGreater(report["fields"]["demand_kw"]["relative_mean_change"], 0.2)
        self.assertIn("<table>", render_drift_html(report))

    def test_district_aggregate_forecast_sums_building_loads(self) -> None:
        point_a = ForecastPoint("2026-07-01T00:00:00", 0, 100, 90, 110, 10, 8, 12, 20, 0.2, 0.4, 0.2)
        point_b = ForecastPoint("2026-07-01T00:00:00", 0, 50, 40, 60, 5, 4, 6, 22, 0.3, 0.5, 0.4)
        aggregate = aggregate_forecasts([("a", [point_a]), ("b", [point_b])])
        self.assertEqual(aggregate[0].demand_kw, 150)
        self.assertEqual(aggregate[0].solar_kw, 15)
        self.assertEqual(aggregate[0].outside_temp_c, 21)
        self.assertEqual(aggregate[0].peak_risk, 0.4)

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

    def test_trained_mlp_model_artifact_preserves_forecast_contract(self) -> None:
        history = generate_history()
        target = ROOT / "models" / "test-mlp-forecast-model.json"
        try:
            artifact = train_mlp_forecast_model(history)
            save_forecast_model(artifact, target)
            loaded = load_forecast_model(target)
            self.assertIsNotNone(loaded)
            forecast = build_forecast(history, model_name=MODEL_TRAINED_MLP, model_artifact=loaded)
            self.assertEqual(len(forecast), 24)
            self.assertEqual(loaded["model_name"], MODEL_TRAINED_MLP)
            self.assertEqual(loaded["architecture"]["type"], "mlp")
            self.assertTrue(all(point.demand_kw >= 0 for point in forecast))
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
        self.assertEqual(rows[1]["solar_kw"], 0.004)

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

    def test_building_data_genome2_adapter_uses_metadata_weather_and_nasa(self) -> None:
        root = ROOT / "data" / "processed" / "test-bdg2"
        output = ROOT / "data" / "processed" / "test-bdg2-current-meter.csv"
        try:
            root.mkdir(parents=True, exist_ok=True)
            (root / "metadata.csv").write_text(
                "building_id,site_id,primaryspaceusage,lat,lng\n"
                "Hog_office_Betsy,Hog,Office,44.97,-93.25\n",
                encoding="utf-8",
            )
            (root / "electricity_cleaned.csv").write_text(
                "timestamp,Hog_office_Betsy,Other\n"
                "2016-01-01 00:00:00,100.0,1\n"
                "2016-01-01 01:00:00,110.0,2\n",
                encoding="utf-8",
            )
            (root / "weather.csv").write_text(
                "timestamp,site_id,airTemperature\n"
                "2016-01-01 00:00:00,Hog,-5.0\n"
                "2016-01-01 01:00:00,Hog,-4.5\n"
                "2016-01-01 00:00:00,Other,20.0\n",
                encoding="utf-8",
            )
            (root / "solar_cleaned.csv").write_text("timestamp\n2016-01-01 00:00:00\n", encoding="utf-8")
            nasa = root / "nasa.csv"
            nasa.write_text(
                "timestamp,outside_temp_c,solar_kw\n"
                "2016-01-01T00:00:00,-6.0,12.0\n",
                encoding="utf-8",
            )
            summary = prepare_building_data_genome2(
                BuildingDataGenome2Config(root_path=root, building_id="Hog_office_Betsy", output_path=output, nasa_enrichment_csv=nasa)
            )
            buildings = list_building_data_genome2_buildings(root_path=root)
            cached = ensure_building_data_genome2_csv("Hog_office_Betsy", root_path=root, output_dir=root / "prepared")
            rows = load_meter_csv(output)
            self.assertEqual(buildings[0]["building_id"], "Hog_office_Betsy")
            self.assertTrue(cached.exists())
            self.assertEqual(summary["row_count"], 2)
            self.assertEqual(rows[0]["demand_kw"], 100.0)
            self.assertEqual(rows[0]["outside_temp_c"], -6.0)
            self.assertEqual(rows[0]["solar_kw"], 12.0)
            self.assertEqual(rows[1]["outside_temp_c"], -4.5)
        finally:
            output.unlink(missing_ok=True)
            if root.exists():
                for path in sorted(root.rglob("*"), reverse=True):
                    if path.is_dir():
                        path.rmdir()
                    else:
                        path.unlink(missing_ok=True)
                root.rmdir()

    def test_default_real_data_config_points_to_expected_local_files(self) -> None:
        config = DEFAULT_REAL_DATA_CONFIG
        self.assertEqual(config.dataset_root, ROOT / "data" / "raw" / "buildingdatagenomeproject2")
        self.assertEqual(config.meter_input_path, ROOT / "data" / "raw" / "buildingdatagenomeproject2" / "electricity_cleaned.csv")
        self.assertEqual(config.enrichment_csv, ROOT / "data" / "raw" / "nasa-power-enrichment.csv")
        self.assertEqual(config.prepared_output_path, ROOT / "data" / "processed" / "current-meter.csv")
        self.assertEqual(config.building_column, "Hog_office_Betsy")

    def test_download_public_dataset_copies_file_url_with_sha(self) -> None:
        source = ROOT / "data" / "processed" / "test-download-source.csv"
        output = ROOT / "data" / "processed" / "test-download-output.csv"
        try:
            payload = b"timestamp,building_a\n2026-07-07T00:00:00,120.5\n"
            source.write_bytes(payload)
            summary = download_public_dataset(
                DownloadConfig(
                    url=source.resolve().as_uri(),
                    output_path=output,
                    sha256=hashlib.sha256(payload).hexdigest(),
                    max_bytes=1024,
                )
            )
            self.assertEqual(output.read_bytes(), payload)
            self.assertEqual(summary["bytes"], len(payload))
            self.assertFalse(summary["extracted"])
        finally:
            source.unlink(missing_ok=True)
            output.unlink(missing_ok=True)

    def test_download_public_dataset_extracts_zip_member(self) -> None:
        archive = ROOT / "data" / "processed" / "test-download-source.zip"
        output = ROOT / "data" / "processed" / "test-download-output.csv"
        downloaded_archive = ROOT / "data" / "processed" / "test-download-output.csv.zip"
        try:
            with zipfile.ZipFile(archive, "w") as zipped:
                zipped.writestr("meters/building.csv", "timestamp,building_a\n2026-07-07T00:00:00,120.5\n")
            summary = download_public_dataset(
                DownloadConfig(
                    url=archive.resolve().as_uri(),
                    output_path=output,
                    max_bytes=4096,
                    extract_zip=True,
                    extract_member="meters/building.csv",
                )
            )
            self.assertIn(b"building_a", output.read_bytes())
            self.assertTrue(summary["extracted"])
            self.assertEqual(summary["extract_member"], "meters/building.csv")
        finally:
            archive.unlink(missing_ok=True)
            output.unlink(missing_ok=True)
            downloaded_archive.unlink(missing_ok=True)

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
