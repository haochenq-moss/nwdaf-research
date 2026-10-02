# Fuzz-to-NWDAF Stage 1: Offline NAS Parser Harness

## Scope

Stage 1 adds Go-native fuzz targets around the free5GC NAS library decoders used
by the existing NAS test builders:

- `message.ParseGMM`
- `message.ParseGSM`

The fuzz targets accept arbitrary bytes up to 4 KiB and treat parser errors as
normal outcomes. A panic or timeout is an execution observation, not a confirmed
bug or vulnerability. The target deliberately does not start free5GC, connect to
an NF, mutate a registry, send traffic, or invoke NWDAF mitigation.

This checkout uses Go 1.26.2 in `vendor/free5gc/test/go.mod`. Go-native fuzzing
is the initial engine because the target is Go code and this module already
imports the NAS package. AFL++ is not assumed to instrument Go; evaluate it only
if a separate harness and reliable coverage path are demonstrated.

## Authorization and Isolation Gate

Before fuzzing, an operator must confirm that the selected checkout and machine
are an authorized isolated lab, that no production/shared network is attached,
and that CPU, memory, input-size, and duration limits are acceptable. This
repository change does not grant authorization and does not run a campaign.

The Go fuzz target can write discovered regression inputs under Go's fuzz cache
or the package's `testdata/fuzz` directory when actually run. Review and copy
accepted findings into a new campaign-owned corpus; do not put generated files
in the historical pilot dataset or vendor history without review.

## Offline Compile and Fuzz Commands

Use the Go version declared by the test module and disable module-network access
for the offline compile check:

```bash
cd free5gc-security-lab/vendor/free5gc/test
GOTOOLCHAIN=local GOPROXY=off go test ./nasTestpacket -run '^$'
```

Only after the isolation gate is approved, a bounded Go-native fuzz trial can be
started explicitly:

```bash
GOTOOLCHAIN=local GOPROXY=off go test ./nasTestpacket \
  -run '^$' -fuzz '^FuzzParseGMM$' -fuzztime=30s -parallel=1
```

Run `FuzzParseGSM` as a separate trial with a separate run ID. Do not run both
campaigns in parallel during this pilot. Record the exact command, environment,
limits, exit status, and output artifacts. These commands are instructions only;
they were not run while authoring this stage.

## Provenance Contract

`schemas/fuzz-run.schema.json` defines `fuzz-run-v1`; the Python runtime
counterpart is `FuzzRunProvenance` in `input_testing/fuzz_provenance.py`. A run
links campaign/run/input IDs and hashes to the pinned free5GC commit, harness
hash, Go/toolchain environment, configuration hash, seed and resource limits.
It stores these concepts independently:

- Execution: `completed`, `crash`, `hang`, `timeout`, or `error`.
- Coverage: collected counts/delta/artifact, unavailable, or collection error.
- Reproduction: not attempted, reproduced, not reproduced, expected rejection,
  or inconclusive, with oracle and replay artifact references.
- Bug review: unreviewed, needs more evidence, confirmed bug, or not a bug.
- Security review: not assessed, not a vulnerability, potential vulnerability,
  or confirmed vulnerability.

A confirmed vulnerability requires a human-confirmed underlying bug and
reviewer/evidence references. LLM provenance is mandatory for LLM-suggested
inputs. A crash, hang, new edge, or LLM explanation alone cannot populate a
confirmed bug or vulnerability state.

## Deferred Stages

After Stage 1 is approved and validated, later stages may add reviewed LLM input
generation, deterministic replay/minimization, telemetry collection during an
isolated replay, and NWDAF analysis. Those are not implemented or run by this
stage. Any analyst decision should cite the fuzz artifact, reproduction oracle,
telemetry run, and analytics artifact. Mitigation remains out of scope until a
separate human-approval gate, audit record, and verified rollback procedure are
designed and tested.

## NAS Fuzzing Lab Handoff

The separate `free5gc-security-lab` repository implements offline GMM/GSM parser
fuzzing through Go/AFL++ harnesses. These parser runs do not start free5GC NFs or
produce network SBI/PFCP traffic. NWDAF's fixed read-only NRF discovery helper
tests a different interface and is not a NAS replay adapter. Do not equate a
parser fuzz result, an NRF GET result, or a parser crash with network-level
evidence or a vulnerability.

The cross-repository handoff is specified in
[`free5gc-security-lab/docs/fuzz_to_nwdaf_handoff.md`](https://github.com/haochenq-moss/free5gc-security-lab/blob/master/docs/fuzz_to_nwdaf_handoff.md).
Use a stable `input_id`, exact SHA-256, and pinned `free5gc_commit` to join the
lab's `fuzz-run-v1` sidecar with an NWDAF `InputCase`. The offline fuzz record,
deterministic reproduction result, human bug/security review, network replay
outcome, and telemetry-derived assessment remain separate evidence objects.

To stage verified seed bytes from an AFL matrix into the NWDAF campaign schema,
run the importer from the NWDAF repository:

```bash
PYTHONPATH=src python scripts/import_fuzz_campaign.py \
  --source-campaign /path/to/free5gc-security-lab/data/results/<afl-campaign> \
  --campaign-dir data/input_testing/<new-campaign-id>
```

The importer validates every seed's manifest hash and size, copies exact bytes
into campaign-relative `corpus/ordinary/` or `corpus/llm/`, writes
`input_cases.jsonl`, and records the source AFL campaign/corpus links in
`fuzz_source_manifest.json`. It refuses an existing destination. It does not
write outcomes, run labels, or `runs/`: corpus membership is not evidence that a
seed was replayed against the network or detected by NWDAF. `fuzz-run-v1` remains
for an actual bounded fuzz execution and its execution/coverage/review evidence;
do not fabricate a per-seed execution record from aggregate AFL statistics.

An initial import from the completed structured AFL campaign is staged locally
at `data/input_testing/nas-afl-structured-20261002/` with 48 unique cases. It
contains 16 ordinary and 32 LLM-generated exact seed cases. One subsequent
single-case replay was recorded for a derived GMM security-capability truncated
PDU using synthetic SUPI `208930000000002`; its exact SHA-256 is
`49532803b6dd390d756842cf17aa830f0117e2262ec26f85e333d1c097e1b53a`. Local
`ParseGMM` accepted/dissected the message through `UESecCapability`, while the
AMF returned Registration Reject cause 22 after UDR returned 404 for that
synthetic subscriber's authentication subscription. This is a test-fixture
authentication failure, not a parser-vulnerability result. The probe did not
confirm an NGAP UE Context Release handshake; AMF logs showed SCTP shutdown and
RAN-context removal, and a read-only follow-up found no matching AMF access
context. No campaign-local NWDAF Linux/SBI/PFCP run bundle was collected. The
campaign therefore remains ineligible for NWDAF classifier evaluation until
telemetry runs and normal controls are added.

No NAS PDU replay adapter currently exists. Network replay remains blocked until
an adapter is reviewed to enforce testbed isolation, synthetic identities,
bounded inputs/resources, timestamps, and reset/rollback. After such a replay,
use its own NWDAF run ID and time window, capture only observed Linux/SBI/PFCP
data, and split complete runs into train/held-out partitions. Classifying an
`input_test` run is not vulnerability detection; mitigation requires a separate
authorization and rollback gate.

## Historical Data Boundary

Keep `data/pilot_raw.tar.gz`, `data/raw`, the frozen split manifest, existing
processed campaign results, model artifacts, and paper-result placeholders
unchanged. New fuzz corpora, logs, telemetry runs, and reports belong under a
new campaign directory with its own manifest and hashes.
