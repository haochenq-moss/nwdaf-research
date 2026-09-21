from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_SOCKETS = (
    "/var/run/docker.sock",
    "/run/podman/podman.sock",
    "/var/run/crio/crio.sock",
    "/run/containerd/containerd.sock",
)


@dataclass(frozen=True)
class RuntimeSocketObservation:
    observed_at: str
    status: str
    sockets: list[dict[str, Any]]
    evidence: dict[str, Any]


class RuntimeSocketObserver:
    """Read-only socket metadata observer; never opens a runtime socket."""

    def __init__(self, paths: tuple[str, ...] = DEFAULT_SOCKETS):
        self.paths = paths

    def observe(self) -> RuntimeSocketObservation:
        records: list[dict[str, Any]] = []
        for value in self.paths:
            path = Path(value)
            if not path.exists():
                continue
            try:
                metadata = path.stat()
                records.append(
                    {
                        "path": str(path),
                        "mode": stat.filemode(metadata.st_mode),
                        "owner_uid": metadata.st_uid,
                        "owner_gid": metadata.st_gid,
                        "world_writable": bool(metadata.st_mode & stat.S_IWOTH),
                        "readable_by_process": os.access(path, os.R_OK),
                        "writable_by_process": os.access(path, os.W_OK),
                    }
                )
            except OSError as error:
                records.append({"path": str(path), "error": str(error)})
        return RuntimeSocketObservation(
            observed_at=datetime.now(timezone.utc).isoformat(),
            status="measured" if records else "unavailable",
            sockets=records,
            evidence={"socket_count": len(records), "opened_socket": False},
        )