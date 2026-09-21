from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class OVSObservation:
    observed_at: str
    status: str
    bridges: list[str]
    ports: list[str]
    flows: list[str]
    evidence: dict[str, Any]
    unavailable_reason: str | None = None


class OVSObserver:
    """Read-only OVS inventory observer; never changes bridges or flows."""

    def __init__(self, timeout: float = 5.0):
        self.timeout = timeout

    def _run(self, command: list[str]) -> str:
        return subprocess.run(command, check=True, capture_output=True, text=True, timeout=self.timeout).stdout

    def observe(self) -> OVSObservation:
        if shutil.which("ovs-vsctl") is None:
            return OVSObservation(
                datetime.now(timezone.utc).isoformat(), "unavailable", [], [], [], {},
                "ovs-vsctl is not installed",
            )
        try:
            show = self._run(["ovs-vsctl", "show"])
            bridge_output = self._run(["ovs-vsctl", "--format=bare", "--columns=name", "list", "Bridge"])
            port_output = self._run(["ovs-vsctl", "--format=bare", "--columns=name", "list", "Port"])
            bridges = [line.strip() for line in bridge_output.splitlines() if line.strip()]
            ports = [line.strip() for line in port_output.splitlines() if line.strip()]
            flows: list[str] = []
            for bridge in bridges:
                if shutil.which("ovs-ofctl") is not None:
                    flows.extend(self._run(["ovs-ofctl", "dump-flows", bridge]).splitlines()[1:])
            return OVSObservation(
                datetime.now(timezone.utc).isoformat(), "measured", bridges, ports, flows,
                {"show_bytes": len(show), "bridge_count": len(bridges), "port_count": len(ports), "flow_count": len(flows)},
            )
        except (OSError, subprocess.SubprocessError) as error:
            return OVSObservation(
                datetime.now(timezone.utc).isoformat(), "unavailable", [], [], [], {}, str(error)
            )