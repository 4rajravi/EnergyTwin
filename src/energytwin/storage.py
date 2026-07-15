from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from .sources import PROJECT_ROOT


LOCAL_DB_PATH = PROJECT_ROOT / "data" / "local" / "energytwin.sqlite3"
DATABASE_URL_ENV = "ENERGYTWIN_DATABASE_URL"


def init_db(db_path: Path | str = LOCAL_DB_PATH) -> Path:
    database_url = _production_database_url(db_path)
    if database_url:
        from .production_db import init_postgres

        init_postgres(database_url)
        return Path("postgres")

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                source_key TEXT,
                scenario_key TEXT,
                model_name TEXT,
                mae_kw REAL,
                rmse_kw REAL,
                smape REAL,
                cost_savings_pct REAL,
                carbon_reduction_pct REAL,
                peak_reduction_pct REAL,
                payload_json TEXT NOT NULL
            )
            """
        )
    return path


def save_run_report(report: dict[str, Any], db_path: Path | str = LOCAL_DB_PATH) -> Path:
    database_url = _production_database_url(db_path)
    if database_url:
        from .production_db import save_run_report_postgres

        save_run_report_postgres(report, database_url)
        return Path("postgres")

    path = init_db(db_path)
    config = report.get("config", {})
    forecast_metrics = report.get("forecast_metrics", {})
    optimized = report.get("policy_comparison", {}).get("optimized", {})

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO runs (
                run_id,
                created_at,
                source_key,
                scenario_key,
                model_name,
                mae_kw,
                rmse_kw,
                smape,
                cost_savings_pct,
                carbon_reduction_pct,
                peak_reduction_pct,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                created_at = excluded.created_at,
                source_key = excluded.source_key,
                scenario_key = excluded.scenario_key,
                model_name = excluded.model_name,
                mae_kw = excluded.mae_kw,
                rmse_kw = excluded.rmse_kw,
                smape = excluded.smape,
                cost_savings_pct = excluded.cost_savings_pct,
                carbon_reduction_pct = excluded.carbon_reduction_pct,
                peak_reduction_pct = excluded.peak_reduction_pct,
                payload_json = excluded.payload_json
            """,
            (
                report["run_id"],
                report["created_at"],
                config.get("source_key"),
                config.get("scenario_key"),
                config.get("model_name"),
                forecast_metrics.get("mae_kw"),
                forecast_metrics.get("rmse_kw"),
                forecast_metrics.get("smape"),
                optimized.get("cost_savings_pct"),
                optimized.get("carbon_reduction_pct"),
                optimized.get("peak_reduction_pct"),
                json.dumps(report, sort_keys=True),
            ),
        )
    return path


def latest_run_report(db_path: Path | str = LOCAL_DB_PATH) -> dict[str, Any] | None:
    database_url = _production_database_url(db_path)
    if database_url:
        from .production_db import latest_run_report_postgres

        return latest_run_report_postgres(database_url)

    path = Path(db_path)
    if not path.exists():
        return None
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT payload_json FROM runs ORDER BY created_at DESC, run_id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    return json.loads(row[0])


def list_run_summaries(limit: int = 20, db_path: Path | str = LOCAL_DB_PATH) -> list[dict[str, Any]]:
    database_url = _production_database_url(db_path)
    if database_url:
        from .production_db import list_run_summaries_postgres

        return list_run_summaries_postgres(limit, database_url)

    path = Path(db_path)
    if not path.exists():
        return []
    bounded_limit = max(1, min(int(limit), 100))
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT
                run_id,
                created_at,
                source_key,
                scenario_key,
                model_name,
                mae_kw,
                rmse_kw,
                smape,
                cost_savings_pct,
                carbon_reduction_pct,
                peak_reduction_pct
            FROM runs
            ORDER BY created_at DESC, run_id DESC
            LIMIT ?
            """,
            (bounded_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_run_reports(limit: int = 20, db_path: Path | str = LOCAL_DB_PATH) -> list[dict[str, Any]]:
    database_url = _production_database_url(db_path)
    if database_url:
        from .production_db import list_run_reports_postgres

        return list_run_reports_postgres(limit, database_url)

    path = Path(db_path)
    if not path.exists():
        return []
    bounded_limit = max(1, min(int(limit), 100))
    with sqlite3.connect(path) as connection:
        rows = connection.execute(
            """
            SELECT payload_json
            FROM runs
            ORDER BY created_at DESC, run_id DESC
            LIMIT ?
            """,
            (bounded_limit,),
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def active_storage_backend(db_path: Path | str = LOCAL_DB_PATH) -> dict[str, str]:
    database_url = _production_database_url(db_path)
    if database_url:
        return {"backend": "postgres", "target": _redacted_database_url(database_url)}
    return {"backend": "sqlite", "target": str(db_path)}


def _production_database_url(db_path: Path | str) -> str | None:
    if str(db_path) != str(LOCAL_DB_PATH):
        return None
    return os.getenv(DATABASE_URL_ENV)


def _redacted_database_url(url: str) -> str:
    if "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    host = rest.split("@", 1)[1]
    return f"{scheme}://***@{host}"
