# NWDAF Research Baseline and Wrapper Report

## Scope
This report covers the verified offline analytics pipeline for the transferred dataset. It intentionally excludes NWDAF runtime implementation, live free5GC integration, agent workflows, and NEMOIR logic.

## Data and model constraints
- Source of truth: the extracted dataset under `data/raw`
- Archive integrity: the original `data/pilot_raw.tar.gz` remains unchanged
- Split policy: run-level train/val/test assignments are preserved from `split_manifest.json`
- Telemetry basis: verified Linux host and process signals only
- Excluded signals: unsupported PFCP/SBI/free5GC telemetry in the transferred dataset

## Baseline result
The validated anomaly baseline uses run-level aggregated Linux features and a RandomForest classifier.

Observed metrics on the held-out test split:
- accuracy: 0.9
- F1: 0.9411764705882353
- test_count: 10
- positive_rate: 0.9

## Scenario baseline result
A secondary scenario-classification baseline was also evaluated using the same run-level features:
- accuracy: 0.7
- macro_f1: 0.6
- test_count: 10

## Research wrapper result
The NWDAF-style wrapper in `src/nwdaf_research/analytics/nwdaf.py` reuses the same validated anomaly model and exposes:
- `score_run(run_id)` for per-run anomaly scoring
- `batch_score_runs(run_ids)` for batch scoring
- `export_batch_scores(output_path)` for JSON export
- `evaluate()` for the baseline metrics

## Evidence summary
The full validation command run in the project was:

```bash
cd /home/msai/qinh0007/nwdaf-research && uv run python -m unittest discover -s tests -v
```

The fresh result was:
- 11 tests passed
- 0 failures

## Conclusion
The anomaly baseline is the strongest verified signal in the current transferred dataset. This is the appropriate stable foundation for later research extensions, while remaining fully grounded in the extracted dataset and the observed telemetry evidence.
