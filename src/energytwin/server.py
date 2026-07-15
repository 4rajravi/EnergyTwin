from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .auth import auth_status, request_authorized
from .cache import api_cache_key, cache_get_json, cache_set_json, cache_status
from .data import available_scenarios, get_scenario
from .district import DEFAULT_DISTRICT_BUILDINGS, district_forecast, district_optimize
from .domain import BatterySpec, TariffSpec, serialize
from .forecasting import MODEL_WEIGHTED, build_forecast, evaluate_forecast_baseline, model_status
from .mlops import list_local_runs, local_monitoring_summary, read_latest_local_run
from .model_artifacts import forecast_model_summary
from .simulator import compare_policies, simulate
from .sources import available_buildings, available_data_sources, current_data_health, load_history
from .storage import active_storage_backend


STATIC_DIR = Path(__file__).resolve().parent / "app" / "static"


class EnergyTwinHandler(BaseHTTPRequestHandler):
    server_version = "EnergyTwin/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            query = parse_qs(parsed.query)
            if not request_authorized(self.headers, query):
                self._json({"error": "unauthorized"}, status=401)
                return
            self._handle_api(parsed.path, query)
            return
        self._serve_static(parsed.path)

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self.send_response(405)
            self.send_header("Allow", "GET")
            self.end_headers()
            return
        self._serve_static(parsed.path, send_body=False)

    def log_message(self, format: str, *args) -> None:
        return

    def _handle_api(self, path: str, query: dict[str, list[str]]) -> None:
        cache_key = api_cache_key(path, query)
        cached_payload = cache_get_json(cache_key)
        if cached_payload is not None:
            self._json(cached_payload, cache_status="HIT")
            return

        scenario_key = query.get("scenario", ["normal"])[0]
        controller = query.get("controller", ["baseline"])[0]
        source_key = query.get("source", ["demo"])[0]
        building_id = query.get("building", [None])[0]
        battery, tariff = _economics_from_query(query)
        scenario = get_scenario(scenario_key, _scenario_overrides_from_query(query))
        history, source_label = load_history(
            source_key=source_key,
            scenario_key=scenario_key,
            scenario=scenario,
            building_id=building_id,
        )
        model_name = query.get("model", [_default_model_name(len(history))])[0]
        forecast = build_forecast(history, scenario_key=scenario_key, scenario=scenario, model_name=model_name)

        if path == "/api/scenarios":
            payload = {"scenarios": available_scenarios()}
        elif path == "/api/data-sources":
            payload = {"sources": serialize(available_data_sources())}
        elif path == "/api/buildings":
            payload = {"buildings": available_buildings(limit=_int_query(query, "limit", 500, 1, 2000))}
        elif path == "/api/forecast":
            payload = {
                "profile": {
                    "name": "North Loop Commercial Hub",
                    "building_type": "commercial-office",
                    "floor_area_m2": 18400,
                },
                "scenario": serialize(scenario),
                "source": source_label,
                "forecast": serialize(forecast),
            }
        elif path == "/api/simulate":
            points, metrics = simulate(forecast, controller, battery=battery, tariff=tariff)
            payload = {
                "scenario": scenario_key,
                "controller": controller,
                "economics": serialize({"battery": battery, "tariff": tariff}),
                "metrics": serialize(metrics),
                "points": serialize(points),
            }
        elif path == "/api/optimize":
            payload = {
                "scenario": scenario_key,
                "economics": serialize({"battery": battery, "tariff": tariff}),
                "comparison": compare_policies(forecast, battery=battery, tariff=tariff),
            }
        elif path == "/api/model-status":
            metrics = evaluate_forecast_baseline(history, model_name=model_name)
            payload = model_status(len(history), metrics)
            payload["latest_local_run"] = read_latest_local_run()
        elif path == "/api/mlops-run":
            payload = read_latest_local_run() or {"error": "no local run found"}
        elif path == "/api/mlops-runs":
            payload = {"runs": list_local_runs(limit=_int_query(query, "limit", 20, 1, 100))}
        elif path == "/api/mlops-monitoring":
            payload = local_monitoring_summary(limit=_int_query(query, "limit", 20, 1, 100))
        elif path == "/api/system-status":
            payload = {
                "storage": active_storage_backend(),
                "cache": cache_status(),
                "auth": auth_status(),
            }
        elif path == "/api/district-forecast":
            payload = district_forecast(
                building_ids=_building_list_query(query),
                scenario_key=scenario_key,
                scenario=scenario,
                model_name=model_name,
            )
        elif path == "/api/district-optimize":
            payload = district_optimize(
                building_ids=_building_list_query(query),
                scenario_key=scenario_key,
                scenario=scenario,
                model_name=model_name,
                battery=battery,
                tariff=tariff,
            )
        elif path == "/api/forecast-evaluation":
            payload = serialize(evaluate_forecast_baseline(history, model_name=model_name))
        elif path == "/api/data-health":
            payload = serialize(
                current_data_health(
                    source_key=source_key,
                    scenario_key=scenario_key,
                    scenario=scenario,
                    building_id=building_id,
                )
            )
        else:
            self._json({"error": "not found"}, status=404)
            return

        cache_set_json(cache_key, payload)
        self._json(payload, cache_status="MISS" if cache_key else None)

    def _serve_static(self, path: str, send_body: bool = True) -> None:
        target = STATIC_DIR / "index.html" if path in ("", "/") else STATIC_DIR / path.lstrip("/")
        try:
            target = target.resolve()
            target.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self.send_error(403)
            return

        if not target.exists() or target.is_dir():
            self.send_error(404)
            return

        body = target.read_bytes()
        mime = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def _json(self, payload: object, status: int = 200, cache_status: str | None = None) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        if cache_status:
            self.send_header("X-EnergyTwin-Cache", cache_status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _economics_from_query(query: dict[str, list[str]]) -> tuple[BatterySpec, TariffSpec]:
    battery = BatterySpec(
        wear_cost_usd_per_kwh_throughput=_float_query(query, "battery_wear", BatterySpec().wear_cost_usd_per_kwh_throughput, 0.0, 1.0)
    )
    tariff = TariffSpec(
        demand_charge_usd_per_kw_day=_float_query(query, "demand_charge", TariffSpec().demand_charge_usd_per_kw_day, 0.0, 100.0),
        export_credit_fraction=_float_query(query, "export_credit", TariffSpec().export_credit_fraction, 0.0, 1.0),
    )
    return battery, tariff


def _scenario_overrides_from_query(query: dict[str, list[str]]) -> dict[str, float]:
    return {
        key: value
        for key, value in {
            "temperature_delta_c": _optional_float_query(query, "temp_delta"),
            "cloud_cover": _optional_float_query(query, "cloud_cover"),
            "price_multiplier": _optional_float_query(query, "price_multiplier"),
            "ev_spike_kw": _optional_float_query(query, "ev_spike"),
            "comfort_strictness": _optional_float_query(query, "comfort"),
        }.items()
        if value is not None
    }


def _optional_float_query(query: dict[str, list[str]], key: str) -> float | None:
    if key not in query:
        return None
    return _float_query(
        query,
        key,
        0.0,
        {
            "temp_delta": -20.0,
            "cloud_cover": 0.0,
            "price_multiplier": 0.1,
            "ev_spike": 0.0,
            "comfort": 0.0,
        }[key],
        {
            "temp_delta": 20.0,
            "cloud_cover": 1.0,
            "price_multiplier": 5.0,
            "ev_spike": 500.0,
            "comfort": 1.0,
        }[key],
    )


def _float_query(query: dict[str, list[str]], key: str, default: float, minimum: float, maximum: float) -> float:
    raw = query.get(key, [str(default)])[0]
    try:
        value = float(raw)
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _int_query(query: dict[str, list[str]], key: str, default: int, minimum: int, maximum: int) -> int:
    raw = query.get(key, [str(default)])[0]
    try:
        value = int(raw)
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def _building_list_query(query: dict[str, list[str]]) -> list[str]:
    raw_values = query.get("buildings", [])
    if not raw_values:
        return list(DEFAULT_DISTRICT_BUILDINGS)
    buildings: list[str] = []
    for raw in raw_values:
        buildings.extend(item.strip() for item in raw.split(",") if item.strip())
    return buildings[:20] if buildings else list(DEFAULT_DISTRICT_BUILDINGS)


def _default_model_name(history_rows: int) -> str:
    artifact = forecast_model_summary()
    if not artifact.get("available"):
        return MODEL_WEIGHTED
    artifact_rows = artifact.get("training_rows")
    if not isinstance(artifact_rows, int):
        return MODEL_WEIGHTED
    if abs(artifact_rows - history_rows) > max(24, int(history_rows * 0.10)):
        return MODEL_WEIGHTED
    return str(artifact.get("model_name") or MODEL_WEIGHTED)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AI Energy Twin dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8787, type=int)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), EnergyTwinHandler)
    print(f"AI Energy Twin running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
