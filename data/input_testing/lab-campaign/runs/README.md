# Campaign Run Telemetry

Add one directory per actual run ID, for example `runs/RLAB001/`. Each run directory must use the NWDAF run layout consumed by `RunFeatureBuilder`:

- `metadata.json`
- `ground_truth.json`
- `timeline.json`
- available `linux/events.jsonl`, `sbi/events.jsonl`, `pfcp/events.jsonl`, and `free5gc/events.jsonl` streams

Use real collection output, timezone-aware timestamps, and synthetic identifiers. Do not copy the aggregate `live_observations.jsonl` snapshot here as though it were an event stream. Keep existing `data/raw` campaigns untouched. The evaluator will not work until every ID in `run_labels.jsonl` has a complete run directory and both labels appear in both the train and held-out partitions.
