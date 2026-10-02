# Imported NAS Fuzz Inputs

This campaign stages 48 verified seed inputs from the
`afl_multimodel_structured_20261002_v1` AFL++ campaign for the Fuzz-to-NWDAF
evidence workflow.

One controlled live replay was recorded for `nas-gmm-security-cut-supi0002-live-20261002`
using the separate synthetic SUPI `208930000000002` and test gNB ID `000315`.
The probe PDU hash is `49532803b6dd390d756842cf17aa830f0117e2262ec26f85e333d1c097e1b53a`.
The local `ParseGMM` dissection succeeded and reached `UESecCapability`. On the
network path, NG Setup was accepted, but the AMF returned Registration Reject
cause 22 after UDR returned HTTP 404 for that synthetic subscriber's
authentication subscription. This is an authentication-data/test-fixture
failure, not evidence that the malformed IE caused the reject.

The probe did not receive a confirmed UE Context Release Command/Complete
handshake. AMF logs recorded SCTP shutdown and removal of the temporary RAN
context, and a read-only follow-up query found no matching AMF access-context
record; record this as observed cleanup, not a confirmed NGAP release handshake.
No NWDAF-format Linux/SBI/PFCP run bundle was collected. The case has a
`TestOutcome` and train-side `input_test` label, but this campaign is **not ready
for evaluation** until real telemetry run data and normal controls are present.
This one replay does not establish a bug or vulnerability.

`input_cases.jsonl` links each case to an exact corpus file and SHA-256;
`outcomes.jsonl` and `run_labels.jsonl` contain the single observed replay.
`network_replay_observations.jsonl` stores the NAS response and cleanup/log
evidence separately from the corpus and result label. `fuzz_source_manifest.json`
preserves the source matrix manifest, free5GC commit, harness, seed arm, and
generator model. `runs/RNAS0001/` is intentionally absent because no NWDAF
telemetry bundle was collected during the replay.