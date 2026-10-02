# Lab Input-Testing Campaign

## Current Status

This campaign contains 4 ordinary NRF requests, 24 LLM-suggested trials (8 each from `qwen2.5-coder:7b`, `qwen2.5-coder:3b`, and `llama3.2:3b`), and 4 passive normal runs. Each 3B model contributed 4 template groups with 2 replicates each. Input-test request hashes are grouped across a 14-train/14-held-out split; each partition also has 2 normal runs. All candidate queries were fixed, allowlisted, read-only NRF GETs and all completed with HTTP 200. No crashes or timeouts occurred.

The saved pilot classifier scores 16/16 held-out runs correctly, including perfect Linux-only and no-duration ablations. This is not general detection evidence: normal windows contain 9 Linux samples over about 2.1 seconds and no SBI request, while input-test windows contain 1-6 Linux samples, have widely varying duration, and include the SBI request under test. The score is strongly confounded by collection procedure. Treat it as a pipeline smoke test only; use duration- and background-SBI-matched controls before making detection claims.

Repeated same-hash ordinary/LLM timings vary substantially. Do not infer an LLM performance difference from these small samples.

Do not invent records to make evaluation run. Populate the JSONL manifests only from actual reviewed inputs and completed test runs. A crash or rejection is an observation, not a vulnerability determination.

## Files

- `input_cases.jsonl`: one JSON object per ordinary or LLM-suggested input. Required fields: `input_id`, `input_source`, `component`, `input_sha256`, `corpus_path`, and `free5gc_commit`. Optional `auth_context` contains non-secret protocol context; LLM-suggested records also require `generator_model`.
- `outcomes.jsonl`: one JSON object per completed input test, with `outcome_id`, `input_id`, `run_id`, timezone-aware `window_start` / `window_end`, and outcome `status`; optional `http_status` / `duration_ms` record HTTP results, while `exit_code` / `signal` record process outcomes.
- `run_labels.jsonl`: one JSON object per NWDAF run, labeled `normal` or `input_test` and assigned to `train` or `held_out`. Keep all observations from a run in one split, and include both classes in both splits before evaluation.
- `corpus/ordinary/` and `corpus/llm/`: preserve exact input bytes here; records refer to these files by campaign-relative `corpus_path` and SHA-256 digest.
- `llm_candidates.jsonl`: 24 schema-validated NRF GET trials across `qwen2.5-coder:7b`, `qwen2.5-coder:3b`, and `llama3.2:3b`; all have completed outcomes. Each added 3B model has four template groups with two replicates per group. This is candidate provenance; cases/outcomes remain in their own manifests.
- `runs/`: NWDAF-format run directories. `RLAB008` and `RLLM001`-`RLLM024` have Linux and SBI event streams; some also have PFCP events. Missing event types are not fabricated. See `runs/README.md`.

The capture command appends contextual snapshots to `live_observations.jsonl`; those snapshots do not replace input records, outcomes, labels, or full run telemetry. The live NRF has OAuth enabled: an unauthenticated GET returned HTTP 401, and the same read-only query returned HTTP 200 with a registered AMF client-credentials token. See `docs/input_testing.md` for the token flow. Keep tokens out of this campaign.

To execute a newly generated candidate after review, use a fresh run ID. This
sends one OAuth-authenticated read-only GET and records its result and
telemetry; it does not run a fuzzing campaign:

```bash
PYTHONPATH=src python scripts/run_llm_nrf_candidates.py \
  --campaign-dir data/input_testing/lab-campaign \
  --nf-instance-id b455d3f3-f92d-4f48-adc7-993e1beb1921 \
  --candidate-id llm-nrf-001
```

Candidate records change to `executed` only after a successful runner invocation. Compare outcomes without waiting for a held-out set using:

```bash
PYTHONPATH=src python scripts/compare_input_outcomes.py \
  --campaign-dir data/input_testing/lab-campaign
```

Generate a further batch from two local models using fixed safe templates and
two repetitions per selected template. New candidate IDs include a batch number
to avoid overwriting prior trials; generated candidates remain `not_run` until
the execution CLI is deliberately invoked:

```bash
PYTHONPATH=src python scripts/generate_model_trials.py \
  --campaign-dir data/input_testing/lab-campaign \
  --model qwen2.5-coder:3b --model llama3.2:3b \
  --template-count 4 --repeats 2
```

Materialize each new, unmaterialized input run before feature evaluation. `RLAB003` is already materialized; do not rerun this command for it:

```bash
PYTHONPATH=src python scripts/materialize_input_testing_runs.py \
  --campaign-dir data/input_testing/lab-campaign
```

Input-test runs are split by request hash so byte-identical inputs cannot leak across partitions:

```bash
PYTHONPATH=src python scripts/assign_input_testing_splits.py \
  --campaign-dir data/input_testing/lab-campaign --seed 42
```

Passive normal windows are collected without sending NRF requests or starting traffic/scenarios:

```bash
PYTHONPATH=src python scripts/capture_normal_baselines.py \
  --campaign-dir data/input_testing/lab-campaign \
  --train-count 2 --held-out-count 2 --duration-sec 2
```

The current pilot report is saved in `evaluation.json`. The perfect held-out score is collection-procedure-confounded. For stronger conclusions, collect substantially more normal runs with durations and background SBI activity matched to the input-test windows. Ollama is installed on the workspace host; it is not installed on Ubuntu because that host had only 1.3 GB free disk and no non-interactive sudo. Rerun evaluation with:

```bash
PYTHONPATH=src python scripts/evaluate_input_testing_campaign.py \
  --campaign-dir data/input_testing/lab-campaign
```
