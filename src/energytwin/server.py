from __future__ import annotations

import argparse
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .data import available_scenarios, generate_history, get_scenario
from .domain import serialize
from .forecasting import build_forecast, model_status
from .ingestion import data_health
from .simulator import compare_policies, simulate


STATIC_DIR = Path(__file__).resolve().parent / "app" / "static"


class EnergyTwinHandler(BaseHTTPRequestHandler):
    server_version = "EnergyTwin/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api(parsed.path, parse_qs(parsed.query))
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
        scenario_key = query.get("scenario", ["normal"])[0]
        controller = query.get("controller", ["baseline"])[0]
        history = generate_history(scenario_key=scenario_key)
        forecast = build_forecast(history, scenario_key=scenario_key)

        if path == "/api/scenarios":
            payload = {"scenarios": available_scenarios()}
        elif path == "/api/forecast":
            payload = {
                "profile": {
                    "name": "North Loop Commercial Hub",
                    "building_type": "commercial-office",
                    "floor_area_m2": 18400,
                },
                "scenario": serialize(get_scenario(scenario_key)),
                "forecast": serialize(forecast),
            }
        elif path == "/api/simulate":
            points, metrics = simulate(forecast, controller)
            payload = {
                "scenario": scenario_key,
                "controller": controller,
                "metrics": serialize(metrics),
                "points": serialize(points),
            }
        elif path == "/api/optimize":
            payload = {
                "scenario": scenario_key,
                "comparison": compare_policies(forecast),
            }
        elif path == "/api/model-status":
            payload = model_status(len(history))
        elif path == "/api/data-health":
            payload = serialize(data_health(history, source=f"demo:{scenario_key}"))
        else:
            self._json({"error": "not found"}, status=404)
            return

        self._json(payload)

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
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def _json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


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
