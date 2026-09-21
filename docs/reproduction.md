# Reproduction

This repository hosts an external **NWDAF-like Security Analytics Prototype**.
It is not a 3GPP-compliant NWDAF and does not contain the free5GC runtime.

## Two-Machine Setup

The Ubuntu testbed and GPU analytics server are separate machines.

### Ubuntu testbed repositories

Use the project forks used for the validated testbed:

- [free5GC fork](https://github.com/haochenq-moss/free5gc)
- [free-ran-ue fork](https://github.com/haochenq-moss/free-ran-ue)

On Ubuntu 20.04 or a compatible Linux host, install the dependencies required by
the upstream projects, including Go, MongoDB, gtp5g/kernel build dependencies,
Node.js/Yarn for the WebConsole, and standard build tools. The free5GC fork's
`quick-setup.sh` installs or configures the core dependencies; review it before
running because it may require `sudo`, network access, and host networking
changes.

Clone and build both repositories:

```bash
git clone https://github.com/haochenq-moss/free5gc.git ~/free5gc
git clone https://github.com/haochenq-moss/free-ran-ue.git ~/free-ran-ue

cd ~/free5gc
./quick-setup.sh
make all

cd ~/free-ran-ue
make
```

Before starting the system, verify that the IP addresses and identifiers in
`~/free-ran-ue/config/gnb.yaml` and `~/free-ran-ue/config/ue.yaml` match the
Ubuntu host and the free5GC configuration: N2/N3 addresses, PLMN, TAC, S-NSSAI,
DNN, subscriber identity, and authentication subscription. The UE configuration
creates the `ueTun*` user-plane tunnel when PDU-session setup succeeds.

### Ubuntu startup order

Run each long-lived process in its own Ubuntu terminal. Start the core first:

```bash
cd ~/free5gc
./run.sh
```

Start the WebConsole in another terminal:

```bash
cd ~/free5gc/webconsole
go run server.go
```

Use the WebConsole to create or verify the subscriber/user before starting the
UE. Then start the RAN simulator:

```bash
cd ~/free-ran-ue
./build/free-ran-ue gnb -c config/gnb.yaml
```

Finally start the UE in another terminal:

```bash
cd ~/free-ran-ue
sudo ./build/free-ran-ue ue -c config/ue.yaml
```

Validate the testbed before collecting data:

```bash
pgrep -a -f 'amf|smf|upf|nrf|udm|udr|pcf|nssf|ausf|free-ran-ue'
ip -br addr
ip -br link show | grep -i '^ueTun' || true
ss -lntup
```

The expected live evidence includes running free5GC NFs, one gNB, one or more
UE processes, and a configured `ueTun*` interface. The experiment controller
uses the existing Ubuntu collectors and writes run directories under its chosen
dataset output path.

### GPU server connection

The GPU server does not run free5GC. If Ubuntu is behind NAT, create a reverse
SSH tunnel from Ubuntu to the GPU server. One tunnel maps SSH and the response
agent:

```bash
ssh -N -T \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -R 127.0.0.1:2222:127.0.0.1:22 \
  -R 127.0.0.1:9090:127.0.0.1:9090 \
  qinh0007@<gpu-server-address>
```

The GPU server can then use the read-only live observer through port `2222` and
the authenticated Ubuntu response-agent through port `9090`.

## Local CPU workflow

The pilot archive is immutable. Its verified SHA-256 is:

```text
8cefce33e78fecb6786895c1ce9f153937a6624d969940ea11b55b32660cfe57
```

```bash
uv sync
uv run python scripts/data/extract_dataset.py
uv run python -m unittest discover -s tests -v
uv run python scripts/evaluate/baseline_anomaly.py
uv run python scripts/build_model_artifact.py --output models/rf-v1
uv run python scripts/evaluate_configurations.py
```

The existing split is run-level: 60 train, 20 validation, and 10 test. Rows
from one run must not be distributed across different splits.

## Analytics API

Run locally on a CPU node:

```bash
uv run python scripts/run_analytics.py --host 127.0.0.1 --port 8000
```

The service loads `models/rf-v1/model.pkl` when present, writes structured audit events to `logs/api_audit.jsonl`, and loads
action limits from `configs/policy.yaml`. Set `NWDAF_API_KEY` before startup to
require `X-API-Key` on analytics, subscription, and mitigation endpoints:

```bash
export NWDAF_API_KEY='local-development-key'
uv run python scripts/run_analytics.py
```

To use the separately deployed Ubuntu response-agent instead of Mock NF:

```bash
export RESPONSE_AGENT_ENDPOINT='http://127.0.0.1:9090'
export RESPONSE_AGENT_API_KEY='<same-key-configured-on-Ubuntu>'
uv run python scripts/run_analytics.py
```

The Ubuntu agent is installed at `~/nwdaf-response-agent/agent.py`. To run its
safe default mode as a user service, create `~/.nwdaf-response-agent/env` on
Ubuntu with a locally chosen key, install the service unit, and start it:

```bash
mkdir -p ~/.nwdaf-response-agent
chmod 700 ~/.nwdaf-response-agent
printf '%s\n' 'RESPONSE_AGENT_API_KEY=<choose-a-local-key>' > ~/.nwdaf-response-agent/env
chmod 600 ~/.nwdaf-response-agent/env
mkdir -p ~/.config/systemd/user
cp scripts/ubuntu-response-agent.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now ubuntu-response-agent.service
curl http://127.0.0.1:9090/health
```

The service is bound to loopback. Add a second reverse tunnel mapping
`-R 127.0.0.1:9090:127.0.0.1:9090` so the GPU server can reach it. Live `tc`
rate limiting remains disabled unless explicitly enabled after validating a
passwordless, narrowly scoped sudo rule. Any enabled rate limit schedules an
allow-listed `fq_codel` restoration after its bounded duration; arbitrary
commands are never allowed. The Ubuntu agent has now passed a real five-second
trial: `tbf 1mbit` was applied and automatically restored to `fq_codel`.
Because systemd `NoNewPrivileges` prevents sudo elevation, it is omitted from
this service; the user account still has broader sudo privileges than the
agent's allow-list and this residual risk must be disclosed.

Each request receives or echoes an `X-Request-ID`. Mitigation `decisionId`
values are single-use within one service process to provide replay protection.

The offline configuration report is written to
`evaluation/configurations.json`. B0 is a validation-selected load threshold,
B1 is the Random Forest detector, and B2 applies the policy confidence gate.
Live mitigation latency and recovery time remain explicitly unavailable until
the Ubuntu response timeline is collected.

## Live Ubuntu observation

Measure the B0 live baseline with bounded ICMP probes over the real UE tunnel:

```bash
uv run python scripts/measure_b0.py --count 10 --target 8.8.8.8
```

The report is written to `evaluation/b0_live.json`. Latency and packet loss are
measured when the target is reachable. Throughput is reported as unavailable
until `iperf3` is installed on Ubuntu; no throughput value is inferred.

Run the sequential live comparison harness:

```bash
uv run python scripts/measure_live_configurations.py
```

It records B0 network measurements, B1 real model inference latency, and B2
eligibility. B2 is skipped until a complete live event window and before/after
telemetry are available; the script never treats a prediction or HTTP response
as proof of recovery.

To validate the real B2 response path without changing network behavior, set the
response-agent key locally and run the alert-only trial:

```bash
export RESPONSE_AGENT_API_KEY='same-key-used-by-the-Ubuntu-agent'
uv run python scripts/run_live_b2_alert.py
```

This uses `alert_operator`, records response latency, and measures before/after
network values. It does not enable `tc` rate limiting and does not claim that an
operator alert caused service recovery.

For repeated reports, pass multiple persisted JSON files to the summarizer:

```bash
uv run python scripts/summarize_live_trials.py \
  --b0 evaluation/b0_live.json \
  --b2 evaluation/b2_alert_trial.json \
  --output evaluation/live_trial_summary.json
```

The summary includes mean, median, standard deviation, and sample count. It
keeps alert-only network differences descriptive rather than claiming causal
mitigation benefit.

With the reverse SSH tunnel and GPU public key configured, collect one real,
read-only snapshot from the Ubuntu testbed:

```bash
uv run python scripts/run_live_analytics.py \
  --host 127.0.0.1 --port 2222 --user haochenqin-moss
```

The same report is saved to `evaluation/live_latest.json` unless `--output` is
provided.

The command reads `/proc`, `ip`, `ss`, and recent PFCP/SBI lines from the
existing free5GC log remotely and runs the existing model. Recent log counts
are evidence counts over the last 2000 log lines, not event rates.
It reports unavailable window/event features explicitly. A single snapshot is
not eligible for autonomous mitigation; SBI/PFCP event windows and before/after
service measurements must be collected first.

The service exposes the experimental endpoints:

- `POST /nnwdaf-analyticsinfo/v1/security-analytics`
- `POST /nnwdaf-eventssubscription/v1/subscriptions`
- `GET /nnwdaf-eventssubscription/v1/subscriptions`
- `POST /nnwdaf-eventssubscription/v1/notifications`
- `POST /security/v1/mitigation`

Read-only architecture status is available at:

```http
GET /architecture/v1/status
```

It reports DCCF/MFAF/ADRF/SecIR/VFL module state, active model metadata, ADRF
storage path, and the response action vocabulary. It explicitly labels the
service as an external NWDAF-like prototype rather than a compliant NWDAF.

The current implementation boundary is listed in
`docs/implementation_boundary.md`; it distinguishes measured capabilities from
future OVS, Kubernetes, NF-replacement, UPF-failover, and full-NWDAF work.

Kubernetes/container inventory is available as a read-only optional observer:

```python
from nwdaf_research.live.kubernetes_observer import KubernetesObserver, ContainerRuntimeObserver

pods = KubernetesObserver().observe()
containers = ContainerRuntimeObserver().observe()
```

The observers report `measured` or `unavailable`; they never mutate pods,
containers, namespaces, or runtime sockets.

An optional read-only OVS observer is also available:

```python
from nwdaf_research.live.ovs_observer import OVSObserver

ovs = OVSObserver().observe()
```

It inventories bridges, ports, and flows when `ovs-vsctl`/`ovs-ofctl` are
installed. OVS flow mutation and enforcement remain disabled.

Runtime socket metadata can also be inspected without opening the socket:

```python
from nwdaf_research.live.runtime_socket_observer import RuntimeSocketObserver

runtime = RuntimeSocketObserver().observe()
```

This records socket mode, ownership, process accessibility, and world-writable
status. It does not perform runtime API calls or generate a socket-abuse event.

The notification endpoint generates experimental notification payloads for the
latest analytics result. Subscriptions and replay IDs are persisted in SQLite;
pass `deliver=true` to request an optional HTTP callback to `notificationUri`.
Delivery status and callback errors are returned in the notification payload.

## Closed-loop mock demonstration

This uses actual numeric features derived from a verified pilot run. It sends a
real model inference through the policy engine and controlled Mock SMF adapter.
Because no post-response telemetry is supplied, verification correctly reports
unavailable rather than claiming that mitigation succeeded.

```bash
uv run python scripts/run_closed_loop.py --run-id R00012
```

## Slurm GPU workflow

The login node is not a GPU allocation. Submit GPU-dependent commands through:

```bash
sbatch scripts/slurm/run_gpu_job.sbatch python -c \
  "import sys; print(sys.version)"
```

The wrapper requests one GPU from `MGPU-TC2`, uses `.venv/bin/python`, and logs
the allocated node and visible GPU. Do not install free5GC or modify the Ubuntu
testbed from this project.

## Optional CUDA ML Experiment

The validated baseline is a CPU Random Forest. An optional PyTorch CUDA MLP is
provided for an explicit CPU/GPU measurement; it is not silently substituted
into the primary result. On the cluster used for this prototype, prepare a
user-owned CUDA environment and then submit:

```bash
sbatch scripts/slurm/setup_gpu_env.sbatch
sbatch scripts/slurm/train_gpu_mlp.sbatch --epochs 100
```

If the CUDA PyTorch wheel is unavailable, try the compatible CUDA 12.4 wheel:

```bash
"$HOME/nwdaf-gpu-venv/bin/pip" install --force-reinstall torch \
  --index-url https://download.pytorch.org/whl/cu124
```

If no CUDA wheel can be installed, run the explicitly labeled CPU MLP fallback
for a model-family comparison only:

```bash
sbatch scripts/slurm/train_gpu_mlp.sbatch --backend cpu --epochs 100
```

The CPU fallback must not be reported as GPU acceleration. The primary paper
baseline remains the CPU Random Forest unless a result contains
`device: cuda` and a valid CUDA/PyTorch version.

The optional `TemporalGRUClassifier` uses real Linux event sequences and
validation early stopping when run in a CUDA-enabled environment. It is a model
research extension, not part of the frozen Random Forest result.

Run the temporal model on the supplemental split:

```bash
sbatch scripts/slurm/train_temporal_gru.sbatch \
  --root data/supplemental_large_raw \
  --epochs 100 --max-length 64
```

The verified temporal run produced test accuracy `0.7500` and test F1
`0.8571`. The verified CUDA MLP produced test accuracy `0.9000` and test F1
`0.9412`.

The job writes `$HOME/nwdaf-research-gpu-results/gpu_mlp-<job-id>.json` with the CUDA device, PyTorch/CUDA
versions, training time, inference time, accuracy, and F1. If PyTorch or CUDA is
missing, the job fails explicitly rather than reporting a CPU run as GPU work.