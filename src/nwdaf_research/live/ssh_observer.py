from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


REMOTE_SNAPSHOT = r"""
set -eu
load_1m=$(awk '{print $1}' /proc/loadavg)
mem_total=$(awk '/^MemTotal:/ {print $2 * 1024}' /proc/meminfo)
mem_available=$(awk '/^MemAvailable:/ {print $2 * 1024}' /proc/meminfo)
process_count=$(ps -e --no-headers | wc -l)
ue_tunnel_count=$(ip -br addr | awk '$1 ~ /^ueTun/ {count += 1} END {print count + 0}')
listening_socket_count=$(ss -lntupH 2>/dev/null | wc -l)
latest_log=$(find "$HOME/free5gc/log" -maxdepth 2 -type f -name '*.log' -printf '%T@ %p\n' 2>/dev/null | sort -nr | head -1 | cut -d' ' -f2-)
pfcp_recent=0
sbi_recent=0
if [ -n "$latest_log" ]; then
    pfcp_recent=$(tail -n 2000 "$latest_log" | grep -c 'CAT="PFCP"' || true)
    sbi_recent=$(tail -n 2000 "$latest_log" | grep -c 'CAT="GIN"' || true)
fi
printf '{"load_1m":%s,"memory_total":%s,"memory_available":%s,"process_count":%s,"ue_tunnel_count":%s,"listening_socket_count":%s,"pfcp_recent_log_events":%s,"sbi_recent_log_events":%s}\n' "$load_1m" "$mem_total" "$mem_available" "$process_count" "$ue_tunnel_count" "$listening_socket_count" "$pfcp_recent" "$sbi_recent"
""".strip()


@dataclass(frozen=True)
class LiveObservation:
    observed_at: str
    host: str
    features: dict[str, float]
    evidence: dict[str, Any]
    unavailable_features: list[str]

    @property
    def complete_for_autonomous_response(self) -> bool:
        """A snapshot is observation evidence, not enough for autonomous action."""
        return not self.unavailable_features


class SSHLiveObserver:
    """Read-only live observation over an existing SSH/reverse-SSH path."""

    def __init__(
        self,
        *,
        host: str = "127.0.0.1",
        port: int = 2222,
        user: str = "haochenqin-moss",
        identity_file: str | None = "~/.ssh/id_ecdsa",
        timeout: float = 10.0,
    ):
        self.host = host
        self.port = port
        self.user = user
        self.identity_file = identity_file
        self.timeout = timeout

    def _ssh_command(self) -> list[str]:
        command = [
            "ssh",
            "-p",
            str(self.port),
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={max(1, int(self.timeout))}",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]
        if self.identity_file:
            command.extend(["-i", self.identity_file])
        command.extend([f"{self.user}@{self.host}", REMOTE_SNAPSHOT])
        return command

    def observe(self) -> LiveObservation:
        completed = subprocess.run(
            self._ssh_command(),
            check=True,
            capture_output=True,
            text=True,
            timeout=self.timeout + 2,
        )
        snapshot = json.loads(completed.stdout.strip())
        memory_total = float(snapshot["memory_total"])
        memory_available = float(snapshot["memory_available"])
        load_1m = float(snapshot["load_1m"])
        features = {
            "linux_load_1m_mean": load_1m,
            "linux_load_1m_std": 0.0,
            "linux_load_1m_max": load_1m,
            "linux_load_1m_min": load_1m,
            "linux_memory_total_mean": memory_total,
            "linux_memory_available_mean": memory_available,
            "memory_available_ratio_mean": (
                memory_available / memory_total if memory_total > 0 else 0.0
            ),
        }
        unavailable_features = [
            "linux_event_count",
            "process_event_count",
            "linux_load_1m_std_over_window",
            "sbi_event_rate",
            "pfcp_message_rate",
            "service_latency",
        ]
        return LiveObservation(
            observed_at=datetime.now(timezone.utc).isoformat(),
            host=self.host,
            features=features,
            evidence={
                "source": "remote_proc_ip_ss",
                "collection": "single_read_only_snapshot",
                "process_count": int(snapshot["process_count"]),
                "ue_tunnel_count": int(snapshot["ue_tunnel_count"]),
                "listening_socket_count": int(snapshot["listening_socket_count"]),
                "pfcp_recent_log_events": int(snapshot["pfcp_recent_log_events"]),
                "sbi_recent_log_events": int(snapshot["sbi_recent_log_events"]),
                "event_count_window": "tail-2000-log-lines",
            },
            unavailable_features=unavailable_features,
        )