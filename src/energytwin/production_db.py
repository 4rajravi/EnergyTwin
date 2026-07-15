from __future__ import annotations

import json
from typing import Any


RUNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    source_key TEXT,
    scenario_key TEXT,
    model_name TEXT,
    mae_kw DOUBLE PRECISION,
    rmse_kw DOUBLE PRECISION,
    smape DOUBLE PRECISION,
    cost_savings_pct DOUBLE PRECISION,
    carbon_reduction_pct DOUBLE PRECISION,
    peak_reduction_pct DOUBLE PRECISION,
    payload_json JSONB NOT NULL
)
"""

RUNS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS runs_created_at_idx
ON runs (created_at DESC, run_id DESC)
"""


def init_postgres(url: str) -> str:
    psycopg = _import_psycopg()
    with psycopg.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(RUNS_TABLE_SQL)
            cursor.execute(RUNS_INDEX_SQL)
    return url


def save_run_report_postgres(report: dict[str, Any], url: str) -> str:
    psycopg = _import_psycopg()
    init_postgres(url)
    config = report.get("config", {})
    forecast_metrics = report.get("forecast_metrics", {})
    optimized = report.get("policy_comparison", {}).get("optimized", {})
    payload_json = json.dumps(report, sort_keys=True)

    with psycopg.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
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
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
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
                    payload_json,
                ),
            )
    return url


def latest_run_report_postgres(url: str) -> dict[str, Any] | None:
    psycopg = _import_psycopg()
    init_postgres(url)
    with psycopg.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT payload_json FROM runs ORDER BY created_at DESC, run_id DESC LIMIT 1")
            row = cursor.fetchone()
    return _payload(row)


def list_run_summaries_postgres(limit: int, url: str) -> list[dict[str, Any]]:
    psycopg = _import_psycopg()
    init_postgres(url)
    bounded_limit = max(1, min(int(limit), 100))
    with psycopg.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
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
                LIMIT %s
                """,
                (bounded_limit,),
            )
            rows = cursor.fetchall()
            columns = [column.name for column in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def list_run_reports_postgres(limit: int, url: str) -> list[dict[str, Any]]:
    psycopg = _import_psycopg()
    init_postgres(url)
    bounded_limit = max(1, min(int(limit), 100))
    with psycopg.connect(url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT payload_json FROM runs ORDER BY created_at DESC, run_id DESC LIMIT %s",
                (bounded_limit,),
            )
            rows = cursor.fetchall()
    return [report for row in rows if (report := _payload(row)) is not None]


def _payload(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    value = row[0]
    if isinstance(value, dict):
        return value
    return json.loads(value)


def _import_psycopg():
    try:
        import psycopg  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "Postgres storage requires the optional production dependency: "
            "python3 -m pip install 'psycopg[binary]'"
        ) from exc
    return psycopg
