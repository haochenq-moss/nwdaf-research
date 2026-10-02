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

## Historical Data Boundary

Keep `data/pilot_raw.tar.gz`, `data/raw`, the frozen split manifest, existing
processed campaign results, model artifacts, and paper-result placeholders
unchanged. New fuzz corpora, logs, telemetry runs, and reports belong under a
new campaign directory with its own manifest and hashes.
