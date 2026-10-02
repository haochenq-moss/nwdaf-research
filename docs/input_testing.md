# Offline Input Testing Prototype

This prototype records bounded free5GC input-test evidence and evaluates whether
run-level NWDAF telemetry distinguishes input-test runs from normal runs. It is
an offline research workflow, not a vulnerability detector and not a testbed
controller. A `crash` outcome is an observation to reproduce and investigate;
it does not establish a vulnerability.

## Safety and Scope

- Run tests only in an authorized, isolated free5GC lab.
- Pin the free5GC commit and preserve exact input bytes in a campaign-owned
  corpus. Records store SHA-256 digests and relative paths, not payloads.
- Use synthetic identifiers. Do not store subscriber credentials, authentication
  vectors, or raw secrets in campaign artifacts.
- Start with bounded, reviewed inputs and one test case per recorded time window.
  Do not enable response, mitigation, or configuration-changing behavior.
- The record/evaluation functions and unit tests do not invoke Go tests or
  access the testbed. The optional capture command makes only a read-only SSH
  snapshot; it does not send test inputs or change testbed state.
- The live lab NRF has OAuth enabled. An unauthenticated discovery GET returns
  HTTP 401 with `verify OAuth Authorization header invalid`; the same read-only
  request returned HTTP 200 when sent with a short-lived token for the
  registered AMF and `nnrf-disc` scope. The 401 was an authentication
  requirement, not a vulnerability finding.

## NRF OAuth Baseline

On the Ubuntu testbed, use a registered NF identity to obtain a short-lived
client-credentials token. The NRF validates the registered profile and its
per-instance certificate. This example requests only NRF discovery scope and
prints only the HTTP result; it does not print or persist the bearer token:

```bash
set -euo pipefail
AMF_NF_INSTANCE_ID=$(mongosh --quiet "mongodb://127.0.0.1:27017/free5gc" \
  --eval 'print(db.NfProfile.findOne({nfType:"AMF",nfStatus:"REGISTERED"}).nfInstanceId)')
TOKEN_RESPONSE=$(curl --silent --show-error --fail --max-time 5 \
  --request POST "http://127.0.0.10:8000/oauth2/token" \
  --data-urlencode "grant_type=client_credentials" \
  --data-urlencode "nfInstanceId=$AMF_NF_INSTANCE_ID" \
  --data-urlencode "nfType=AMF" \
  --data-urlencode "targetNfType=NRF" \
  --data-urlencode "scope=nnrf-disc")
TOKEN=$(printf '%s' "$TOKEN_RESPONSE" | \
  sed -n 's/.*"access_token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')
unset TOKEN_RESPONSE
if [[ -z "$TOKEN" ]]; then
  echo "NRF did not return an access token" >&2
  exit 1
fi
curl --silent --show-error --max-time 5 --output /dev/null \
  --write-out 'discovery_http_status=%{http_code}\n' \
  --header "Authorization: Bearer $TOKEN" \
  "http://127.0.0.10:8000/nnrf-disc/v1/nf-instances?requester-nf-type=AMF&target-nf-type=AUSF&service-names=nausf-auth"
unset TOKEN AMF_NF_INSTANCE_ID
```

Do not enable shell tracing (`set -x`), echo the token, or save it in campaign
files. Keep OAuth enabled; do not work around the 401 by disabling authorization.

From the NWDAF workspace, the fixed NRF case can be run and recorded through the
reverse SSH tunnel with:

```bash
PYTHONPATH=src python scripts/run_nrf_discovery_case.py \
  --campaign-dir data/input_testing/lab-campaign \
  --run-id RLAB007 --input-id nrf-disc-ordinary-006 \
  --nf-instance-id b455d3f3-f92d-4f48-adc7-993e1beb1921
```

The command creates a corpus file and appends input, outcome, train-label, and
before/after snapshot records. It runs passive Linux, SBI, and PFCP collectors
only for the authenticated request window, then stores allowlisted metadata
events in the NWDAF run directory; raw payloads, client addresses, and session
identifiers are excluded. It records the request target/hash, free5GC commit,
HTTP status, duration, and non-secret OAuth scope context; it never stores the
token. The NF instance UUID is not a secret, but NRF validates it against its
registered profile and corresponding certificate. Choose new unique IDs for
each run.

Materialize the observed Linux samples into the NWDAF run layout with:

```bash
PYTHONPATH=src python scripts/materialize_input_testing_runs.py \
  --campaign-dir data/input_testing/lab-campaign
```

This writes `metadata.json`, `ground_truth.json`, `timeline.json`, measured
`linux/events.jsonl` samples, and a run-local snapshot sidecar. When produced by
the fixed NRF runner, the run also contains newly observed SBI/PFCP event
metadata. A run created from snapshots alone has no SBI/PFCP event stream and
keeps rolling log-tail counts explicitly as summary evidence. Even with event
capture, one run does not make the campaign large or balanced enough for
held-out evaluation.

## Campaign Files

Store each campaign outside existing raw datasets, for example:

```text
data/input_testing/<campaign-id>/
  corpus/ordinary/
  corpus/llm/
  input_cases.jsonl
  outcomes.jsonl
  run_labels.jsonl
  evaluation.json
```

Input-case records identify the source (`ordinary` or `llm_suggested`), target
component, content hash, relative corpus path, pinned free5GC commit, optional
non-secret `auth_context`, and generator model when applicable. Outcome records
link each input to an NWDAF `run_id` and timezone-aware start/end timestamps;
HTTP cases can also include `http_status` and `duration_ms`. Accepted, rejected,
error, timeout, and crash are execution outcomes only.

Run labels independently identify `normal` or `input_test` runs and assign each
whole run to `train` or `held_out`. Keep all observations from a run in one
partition. The record utilities validate paths, hashes, timestamps,
cross-references, and unique run assignments, and read/write JSON Lines without
changing existing datasets.

## Live Snapshot Capture

With the reverse SSH tunnel active, capture one read-only snapshot immediately
before and after a separately selected input test. Use a new campaign output
directory and the same run/input IDs for both captures:

```bash
export PYTHONPATH=src
python scripts/capture_input_observation.py \
  --run-id RLAB001 --input-id case-001 --phase before \
  --output data/input_testing/lab-campaign/live_observations.jsonl
# Run the separately reviewed, bounded test in the isolated lab.
python scripts/capture_input_observation.py \
  --run-id RLAB001 --input-id case-001 --phase after \
  --output data/input_testing/lab-campaign/live_observations.jsonl
```

The command does not run the input test. Snapshots are appended as JSONL records
with host, features, evidence, and collection time. The observer's PFCP/SBI
values count matching lines in a rolling tail of at most 2,000 free5GC log
lines; they are contextual counts, not per-test event counts or rates. The UE
namespace probe uses `sudo -n` and never prompts. If that read-only permission is
unavailable, namespace telemetry is marked unavailable rather than reported as
a measured zero. Do not broaden sudo permissions just for this observer.

## Feature Evaluation

Use `features_for_runs` with the existing `RunFeatureBuilder`, then pass the
result and run labels to `evaluate_run_detection`. The evaluator fits only on
training runs and scores held-out runs once. It uses an explicit numeric
allowlist of Linux, SBI, PFCP, free5GC, and eBPF measurements; run IDs, scenario
metadata, input-source metadata, and ground-truth fields are excluded.

This is a new supervised probe over the existing feature pipeline, not the
current security-anomaly model. Existing detection results are weak and do not
establish that these features can distinguish input-test runs from normal runs.
Report class counts, confusion matrix, false-positive rate, precision, recall,
F1, and ROC AUC; interpret small held-out results as exploratory and do not tune
using held-out outcomes.

The evaluator requires a run directory for each labeled run, including
`metadata.json`, `ground_truth.json`, `timeline.json`, and any available source
event streams under `linux/`, `sbi/`, `pfcp/`, and `free5gc/`. The fixed NRF
runner now invokes the existing passive Linux/SBI/PFCP collectors and writes
sanitized event metadata into the run bundle. An empty PFCP stream means none
was observed during that run window. A snapshot-only run has Linux samples but
does not fabricate network event rows.

Evaluate a completed campaign from the repository root with:

```bash
PYTHONPATH=src python scripts/evaluate_input_testing_campaign.py \
  --campaign-dir data/input_testing/<campaign-id>
```

The evaluator reads `input_cases.jsonl`, `outcomes.jsonl`, and
`run_labels.jsonl`, defaults to run data in `<campaign-dir>/runs`, and writes
`evaluation.json` within the campaign directory. Existing datasets and reports
are not used or overwritten by default.

`tests/test_input_testing.py` uses temporary records and synthetic feature rows.
It does not execute free5GC or contact a network.

## Multi-Model Repeated Trials

The current campaign compares `qwen2.5-coder:7b`, `qwen2.5-coder:3b`, and
`llama3.2:3b`. For each additional 3B model, Ollama selected four distinct
templates from a fixed allowlist of read-only NRF discovery GETs; each template
was executed twice. Candidate records include the model, template choice, trial
group, and replicate index. The 7B seed batch contains one observation per
template and should not be described as replicated.

Generate another local candidate batch with:

```bash
PYTHONPATH=src python scripts/generate_model_trials.py \
  --campaign-dir data/input_testing/lab-campaign \
  --model qwen2.5-coder:3b --model llama3.2:3b \
  --template-count 4 --repeats 2
```

Generation only appends fixed-template candidates marked `not_run`; it sends no
requests. After reviewing the batch, execute it sequentially with
`run_llm_nrf_candidates.py`, then run `assign_input_testing_splits.py` again.
That splitter groups identical request SHA-256 values so repeated bytes cannot
cross train and held-out partitions. Re-run the evaluator and compare report
artifacts only after the split has been frozen.

The current 16-run held-out score is a smoke test only. The normal baselines
have no SBI requests and consistently contain 9 Linux samples over about 2.1
seconds, while input-test windows contain SBI requests and variable Linux sample
counts/durations. A perfect score, including Linux-only, therefore indicates
collection-procedure leakage. Future controls should match observation duration,
collector cadence, and normal background SBI activity before any detector claim.