from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_revision(path: str | Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def build_model_manifest(
    *,
    repository_root: str | Path,
    raw_root: str | Path,
    feature_names: list[str],
    model_name: str,
    model_version: str,
    random_seed: int,
) -> dict[str, Any]:
    repository_root = Path(repository_root).resolve()
    raw_root = Path(raw_root).resolve()
    archive = repository_root / "data" / "pilot_raw.tar.gz"
    split_manifest = raw_root / "split_manifest.json"
    manifest: dict[str, Any] = {
        "model": {"name": model_name, "version": model_version},
        "feature_schema": {
            "name": "run-linux-v1",
            "features": feature_names,
            "source": "verified Linux host/process telemetry and run metadata",
        },
        "dataset": {
            "archive": str(archive.relative_to(repository_root)) if archive.exists() else None,
            "archive_sha256": sha256_file(archive) if archive.exists() else None,
            "split_manifest": str(split_manifest.relative_to(repository_root))
            if split_manifest.exists()
            else None,
            "split_manifest_sha256": sha256_file(split_manifest)
            if split_manifest.exists()
            else None,
        },
        "training": {"random_seed": random_seed, "split_policy": "whole-run"},
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "executable": sys.executable,
        },
        "code": {"git_revision": git_revision(repository_root)},
    }
    return manifest


def write_manifest(path: str | Path, manifest: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")