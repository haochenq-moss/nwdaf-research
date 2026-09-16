from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone


REMOTE_BENCHMARK = r'''
set -u
target="$1"
count="$2"
iface=$(ip -br addr | awk '$1 ~ /^ueTun/ && $3 != "" {print $1; exit}')
if ! command -v ping >/dev/null 2>&1; then
  printf '{"status":"unavailable","reason":"ping is not installed","interface":"%s","target":"%s","throughput_status":"unavailable"}\n' "$iface" "$target"
  exit 0
fi
if [ -z "$iface" ]; then
  printf '{"status":"unavailable","reason":"no ueTun interface","interface":"","target":"%s","throughput_status":"unavailable"}\n' "$target"
  exit 0
fi
output=$(ping -I "$iface" -c "$count" -W 1 "$target" 2>&1 || true)
loss=$(printf '%s\n' "$output" | awk '/packet loss/ {gsub("%", "", $6); print $6}' | tail -1)
rtt=$(printf '%s\n' "$output" | awk -F= '/rtt|round-trip/ {split($2, values, "/"); print values[2]}' | tail -1)
[ -n "$loss" ] || loss=""
[ -n "$rtt" ] || rtt=""
throughput_status=unavailable
throughput_sent=""
throughput_received=""
throughput_reason="iperf3 is not installed"
if command -v iperf3 >/dev/null 2>&1; then
    host_ip=$(ip -4 -br addr | awk '$1 != "lo" && $1 !~ /^ueTun/ && $3 != "" {split($3, a, "/"); print a[1]; exit}')
    ue_ip=$(ip -4 -br addr show "$iface" | awk '{split($3, a, "/"); print a[1]}')
    if [ -n "$host_ip" ] && [ -n "$ue_ip" ]; then
        iperf3 -s -1 -B "$host_ip" -p 5301 >/tmp/nwdaf-iperf3-server.log 2>&1 &
        iperf_pid=$!
        iperf_output=$(iperf3 -c "$host_ip" -B "$ue_ip" -p 5301 -t 2 -J 2>&1 || true)
        kill "$iperf_pid" 2>/dev/null || true
        throughput_values=$(printf '%s' "$iperf_output" | python3 -c 'import json,sys; d=json.load(sys.stdin); s=d["end"]["sum_sent"]; r=d["end"]["sum_received"]; print(s.get("bits_per_second", ""), r.get("bits_per_second", ""))' 2>/dev/null || true)
        throughput_sent=$(printf '%s' "$throughput_values" | awk '{print $1}')
        throughput_received=$(printf '%s' "$throughput_values" | awk '{print $2}')
        if [ -n "$throughput_sent" ]; then throughput_status=measured; throughput_reason=""; else throughput_reason="iperf3 path unavailable"; fi
    else
        throughput_reason="could not determine UE and host IPv4 addresses"
    fi
fi
if [ -n "$loss" ]; then status=measured; else status=unavailable; fi
reason=""
[ "$status" = "measured" ] || reason="ping output did not contain packet-loss statistics"
printf '{"status":"%s","reason":"%s","interface":"%s","target":"%s","ping_count":%s,"packet_loss_percent":"%s","rtt_mean_ms":"%s","throughput_status":"%s","throughput_sent_bps":"%s","throughput_received_bps":"%s","throughput_reason":"%s"}\n' "$status" "$reason" "$iface" "$target" "$count" "$loss" "$rtt" "$throughput_status" "$throughput_sent" "$throughput_received" "$throughput_reason"
'''.strip()


@dataclass(frozen=True)
class BaselineMeasurement:
    measured_at: str
    host: str
    status: str
    interface: str
    target: str
    ping_count: int
    packet_loss_percent: float | None
    rtt_mean_ms: float | None
    throughput_status: str
    throughput_sent_bps: float | None = None
    throughput_received_bps: float | None = None
    throughput_reason: str | None = None
    reason: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "measured_at": self.measured_at,
            "host": self.host,
            "status": self.status,
            "interface": self.interface,
            "target": self.target,
            "ping_count": self.ping_count,
            "packet_loss_percent": self.packet_loss_percent,
            "rtt_mean_ms": self.rtt_mean_ms,
            "throughput": {
                "status": self.throughput_status,
                "sent_bps": self.throughput_sent_bps,
                "received_bps": self.throughput_received_bps,
                "reason": self.throughput_reason,
            },
            "reason": self.reason,
        }


class SSHBaselineBenchmark:
    """Run bounded, read-only B0 probes over the existing SSH tunnel."""

    def __init__(self, *, host: str = "127.0.0.1", port: int = 2222, user: str = "haochenqin-moss", identity_file: str = "~/.ssh/id_ecdsa", timeout: float = 20.0):
        self.host = host
        self.port = port
        self.user = user
        self.identity_file = identity_file
        self.timeout = timeout

    def measure(self, *, target: str = "8.8.8.8", count: int = 10) -> BaselineMeasurement:
        if count < 1 or count > 60:
            raise ValueError("count must be between 1 and 60")
        command = [
            "ssh", "-p", str(self.port), "-i", self.identity_file,
            "-o", "BatchMode=yes", "-o", f"ConnectTimeout={int(self.timeout)}",
            "-o", "StrictHostKeyChecking=accept-new", f"{self.user}@{self.host}",
            "sh", "-s", "--", target, str(count),
        ]
        completed = subprocess.run(
            command, input=REMOTE_BENCHMARK, capture_output=True, text=True,
            check=True, timeout=self.timeout + 5,
        )
        result = json.loads(completed.stdout.strip())
        return self._parse_result(result, target, count)

    def _parse_result(
        self, result: dict[str, object], target: str, count: int
    ) -> BaselineMeasurement:
        def number(value: object) -> float | None:
            try:
                return float(value) if value not in (None, "") else None
            except (TypeError, ValueError):
                return None

        return BaselineMeasurement(
            measured_at=datetime.now(timezone.utc).isoformat(), host=self.host,
            status=str(result.get("status", "unknown")),
            interface=str(result.get("interface", "")), target=target,
            ping_count=count, packet_loss_percent=number(result.get("packet_loss_percent")),
            rtt_mean_ms=number(result.get("rtt_mean_ms")),
            throughput_status=str(result.get("throughput_status", "unavailable")),
            throughput_sent_bps=number(result.get("throughput_sent_bps")),
            throughput_received_bps=number(result.get("throughput_received_bps")),
            throughput_reason=result.get("throughput_reason"),
            reason=result.get("reason"),
        )