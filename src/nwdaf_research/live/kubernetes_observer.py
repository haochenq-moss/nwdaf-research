from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class RuntimeObservation:
    observed_at: str
    source: str
    status: str
    workloads: list[dict[str, Any]]
    evidence: dict[str, Any]
    unavailable_reason: str | None = None


class KubernetesObserver:
    """Read-only Kubernetes observer; no pod mutation or command execution."""

    def __init__(self, kubectl: str = "kubectl", timeout: float = 5.0):
        self.kubectl = kubectl
        self.timeout = timeout

    def observe(self, namespace: str | None = None) -> RuntimeObservation:
        if shutil.which(self.kubectl) is None:
            return RuntimeObservation(
                datetime.now(timezone.utc).isoformat(), "kubernetes", "unavailable", [], {},
                "kubectl is not installed",
            )
        command = [self.kubectl, "get", "pods", "-o", "json"]
        if namespace:
            command.extend(["-n", namespace])
        else:
            command.append("-A")
        try:
            completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=self.timeout)
            payload = json.loads(completed.stdout)
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
            return RuntimeObservation(
                datetime.now(timezone.utc).isoformat(), "kubernetes", "unavailable", [], {}, str(error)
            )
        workloads = []
        for item in payload.get("items", []):
            metadata = item.get("metadata", {})
            status = item.get("status", {})
            workloads.append(
                {
                    "name": metadata.get("name"),
                    "namespace": metadata.get("namespace"),
                    "uid": metadata.get("uid"),
                    "phase": status.get("phase"),
                    "node": (status.get("hostIP") or ""),
                    "restart_count": sum(
                        int(container.get("restartCount", 0) or 0)
                        for container in status.get("containerStatuses", [])
                    ),
                    "images": [
                        container.get("image")
                        for container in item.get("spec", {}).get("containers", [])
                    ],
                }
            )
        return RuntimeObservation(
            datetime.now(timezone.utc).isoformat(), "kubernetes", "measured", workloads,
            {"pod_count": len(workloads), "namespace": namespace or "all"},
        )


class ContainerRuntimeObserver:
    """Read-only Docker/Podman/CRI workload observer."""

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    def observe(self) -> RuntimeObservation:
        for runtime in ("docker", "podman", "crictl"):
            if shutil.which(runtime) is None:
                continue
            command = [runtime, "ps", "--format", "{{json .}}"] if runtime != "crictl" else [runtime, "ps", "-o", "json"]
            try:
                completed = subprocess.run(command, check=True, capture_output=True, text=True, timeout=self.timeout)
                rows = []
                if runtime == "crictl":
                    rows = json.loads(completed.stdout).get("containers", [])
                else:
                    rows = [json.loads(line) for line in completed.stdout.splitlines() if line.strip()]
                return RuntimeObservation(
                    datetime.now(timezone.utc).isoformat(), runtime, "measured", rows,
                    {"container_count": len(rows)},
                )
            except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as error:
                return RuntimeObservation(
                    datetime.now(timezone.utc).isoformat(), runtime, "unavailable", [], {}, str(error)
                )
        return RuntimeObservation(
            datetime.now(timezone.utc).isoformat(), "container_runtime", "unavailable", [], {},
            "docker, podman, and crictl are not installed",
        )