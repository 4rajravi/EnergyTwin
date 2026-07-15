from __future__ import annotations

import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import urlopen


DEFAULT_MAX_DOWNLOAD_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True)
class DownloadConfig:
    url: str
    output_path: Path | str
    sha256: str | None = None
    max_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES
    extract_zip: bool = False
    extract_member: str | None = None


def download_public_dataset(config: DownloadConfig) -> dict[str, Any]:
    output_path = Path(config.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    download_path = _archive_path(output_path) if config.extract_zip else output_path
    digest, bytes_downloaded = _download_url(config.url, download_path, max_bytes=config.max_bytes)
    if config.sha256 and digest.lower() != config.sha256.lower():
        download_path.unlink(missing_ok=True)
        raise ValueError(f"sha256 mismatch: expected {config.sha256}, got {digest}")

    extracted_member = None
    if config.extract_zip:
        extracted_member = _extract_zip_member(download_path, output_path, config.extract_member)

    return {
        "url": config.url,
        "output_path": str(output_path),
        "downloaded_path": str(download_path),
        "bytes": bytes_downloaded,
        "sha256": digest,
        "extracted": bool(config.extract_zip),
        "extract_member": extracted_member,
    }


def summary_json(summary: dict[str, Any]) -> str:
    return json.dumps(summary, indent=2, sort_keys=True)


def _download_url(url: str, output_path: Path, max_bytes: int) -> tuple[str, int]:
    temporary = output_path.with_suffix(output_path.suffix + ".part")
    sha256 = hashlib.sha256()
    bytes_downloaded = 0
    with urlopen(url) as response, temporary.open("wb") as target:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            bytes_downloaded += len(chunk)
            if bytes_downloaded > max_bytes:
                temporary.unlink(missing_ok=True)
                raise ValueError(f"download exceeded max bytes: {max_bytes}")
            sha256.update(chunk)
            target.write(chunk)
    temporary.replace(output_path)
    return sha256.hexdigest(), bytes_downloaded


def _extract_zip_member(download_path: Path, output_path: Path, member: str | None) -> str:
    with zipfile.ZipFile(download_path) as archive:
        names = [name for name in archive.namelist() if not name.endswith("/")]
        selected = member or _single_zip_member(names)
        if selected not in names:
            raise ValueError(f"zip member not found: {selected}")
        temporary = output_path.with_suffix(output_path.suffix + ".part")
        with archive.open(selected) as source, temporary.open("wb") as target:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                target.write(chunk)
        temporary.replace(output_path)
        return selected


def _single_zip_member(names: list[str]) -> str:
    if len(names) != 1:
        raise ValueError("zip archive has multiple files; pass --extract-member")
    return names[0]


def _archive_path(output_path: Path) -> Path:
    suffix = output_path.suffix or ".csv"
    return output_path.with_suffix(suffix + ".zip")
