# Imported NAS Fuzz Inputs

This campaign stages 48 verified seed inputs from the `afl_multimodel_structured_phase4_20261002_n5_600s` AFL++ campaign for the Fuzz-to-NWDAF evidence workflow.

This is input/provenance staging only. No network replay was performed; no `outcomes.jsonl`, `run_labels.jsonl`, or NWDAF `runs/` were created. Do not run campaign evaluation until actual authorized replay records and observed telemetry bundles have been added. A parser crash or fuzz coverage increase is not by itself a bug or vulnerability finding.

`input_cases.jsonl` links each case to an exact corpus file and SHA-256. `fuzz_source_manifest.json` preserves the source matrix manifest, run configuration/results hashes when present, free5GC commit, harness, seed arm, and generator model.
