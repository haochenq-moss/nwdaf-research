#!/usr/bin/env python3
"""Reproducibly extract the transferred dataset into data/raw.

This script does not modify the source archive at data/pilot_raw.tar.gz.
It creates a derived copy under data/raw and leaves the original archive intact.
"""

from __future__ import annotations

import argparse
import shutil
import tarfile
from pathlib import Path


def extract_archive(archive_path: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)

    if not archive_path.exists():
        raise FileNotFoundError(f"Archive not found: {archive_path}")

    with tarfile.open(archive_path, "r:gz") as tf:
        tf.extractall(destination)

    print(f"Extracted {archive_path} -> {destination}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract the pilot dataset into a derived data/raw directory.")
    parser.add_argument(
        "--archive",
        type=Path,
        default=Path("data/pilot_raw.tar.gz"),
        help="Path to the original archive (left unchanged).",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        default=Path("data/raw"),
        help="Destination directory for the extracted dataset.",
    )
    args = parser.parse_args()

    extract_archive(args.archive.resolve(), args.dest.resolve())


if __name__ == "__main__":
    main()
