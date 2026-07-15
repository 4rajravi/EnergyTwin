from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from energytwin.downloads import DownloadConfig, download_public_dataset, summary_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a public meter dataset into the Energy Twin data folder.")
    parser.add_argument("--url", required=True, help="Direct URL to a CSV or ZIP file. file:// URLs are supported for tests.")
    parser.add_argument("--output", default=str(ROOT / "data" / "raw" / "building-meter.csv"))
    parser.add_argument("--sha256", help="Optional expected SHA-256 hash of the downloaded file.")
    parser.add_argument("--max-mb", type=float, default=512.0, help="Refuse downloads larger than this size.")
    parser.add_argument("--extract-zip", action="store_true", help="Treat the downloaded file as a ZIP archive.")
    parser.add_argument("--extract-member", help="ZIP member to extract to --output.")
    args = parser.parse_args()

    summary = download_public_dataset(
        DownloadConfig(
            url=args.url,
            output_path=args.output,
            sha256=args.sha256,
            max_bytes=int(args.max_mb * 1024 * 1024),
            extract_zip=args.extract_zip,
            extract_member=args.extract_member,
        )
    )
    print(summary_json(summary))
    print()
    print("Next: run scripts/prepare_public_dataset.py with the downloaded output file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
