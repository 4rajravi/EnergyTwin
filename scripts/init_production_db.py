from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from energytwin.production_db import init_postgres  # noqa: E402
from energytwin.storage import DATABASE_URL_ENV  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize the Energy Twin production Postgres schema.")
    parser.add_argument("--database-url", default=os.getenv(DATABASE_URL_ENV), help=f"Defaults to ${DATABASE_URL_ENV}.")
    args = parser.parse_args()

    if not args.database_url:
        print(f"missing database URL: pass --database-url or set {DATABASE_URL_ENV}", file=sys.stderr)
        return 1

    init_postgres(args.database_url)
    print("initialized production database schema")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
