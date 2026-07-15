from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .sources import PROJECT_ROOT


DRIFT_DIR = PROJECT_ROOT / "mlruns" / "drift"
EVIDENTLY_ENV = "ENERGYTWIN_EVIDENTLY_REPORTS"
DRIFT_FIELDS = ("demand_kw", "solar_kw", "outside_temp_c", "price_usd_per_kwh", "carbon_kg_per_kwh")


def drift_reports_enabled() -> bool:
    return os.getenv(EVIDENTLY_ENV) == "1"


def write_drift_report(
    history: list[dict],
    output_dir: Path | str = DRIFT_DIR,
    enabled: bool | None = None,
) -> dict[str, Any] | None:
    if enabled is None:
        enabled = drift_reports_enabled()
    if not enabled:
        return None
    report = build_drift_report(history)
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{report['report_id']}.json"
    target.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    html_target = target_dir / f"{report['report_id']}.html"
    html_target.write_text(render_drift_html(report), encoding="utf-8")
    latest = target_dir / "latest.json"
    latest.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    latest_html = target_dir / "latest.html"
    latest_html.write_text(render_drift_html(report), encoding="utf-8")
    return report


def build_drift_report(history: list[dict]) -> dict[str, Any]:
    if len(history) < 48:
        return {
            "report_id": _report_id(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "insufficient-data",
            "fields": {},
        }
    midpoint = len(history) // 2
    reference = history[:midpoint]
    current = history[midpoint:]
    fields = {field: _field_drift(reference, current, field) for field in DRIFT_FIELDS}
    max_relative = max(abs(item["relative_mean_change"]) for item in fields.values())
    status = "drifted" if max_relative >= 0.20 else "stable"
    return {
        "report_id": _report_id(),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "method": "reference-first-half-vs-current-second-half",
        "evidently_ready": True,
        "fields": fields,
    }


def _field_drift(reference: list[dict], current: list[dict], field: str) -> dict[str, float]:
    reference_mean = _mean(reference, field)
    current_mean = _mean(current, field)
    denominator = abs(reference_mean) if abs(reference_mean) > 1e-9 else 1.0
    return {
        "reference_mean": round(reference_mean, 4),
        "current_mean": round(current_mean, 4),
        "absolute_mean_change": round(current_mean - reference_mean, 4),
        "relative_mean_change": round((current_mean - reference_mean) / denominator, 4),
    }


def _mean(rows: list[dict], field: str) -> float:
    return sum(float(row[field]) for row in rows) / len(rows)


def render_drift_html(report: dict[str, Any]) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{field}</td>"
        f"<td>{values['reference_mean']}</td>"
        f"<td>{values['current_mean']}</td>"
        f"<td>{values['absolute_mean_change']}</td>"
        f"<td>{values['relative_mean_change']}</td>"
        "</tr>"
        for field, values in report.get("fields", {}).items()
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>EnergyTwin Drift Report</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 32px; color: #17201b; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccd5cf; padding: 8px 10px; text-align: right; }}
    th:first-child, td:first-child {{ text-align: left; }}
    th {{ background: #eef5f1; }}
  </style>
</head>
<body>
  <h1>EnergyTwin Drift Report</h1>
  <p>Status: <strong>{report.get("status")}</strong></p>
  <p>Created: {report.get("created_at")}</p>
  <table>
    <thead>
      <tr><th>Field</th><th>Reference mean</th><th>Current mean</th><th>Absolute change</th><th>Relative change</th></tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</body>
</html>
"""


def _report_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ-drift")
