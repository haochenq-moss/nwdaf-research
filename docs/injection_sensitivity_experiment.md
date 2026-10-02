# Injection-Sensitivity Experiment

This experiment measures how often the NWDAF detector identifies an anomaly as
the number of injected anomalous events increases. It is designed to produce
the bar charts shown in the experiment figures: one chart with 10 injection
levels and a second chart with 30 injection levels.

The existing pilot archive remains immutable. Store this campaign separately,
for example under `data/injection_campaign/` and `evaluation/injection/`.

## Experimental question

For an otherwise identical five-second run, does detector sensitivity change
as the number of injected anomalous events changes?

The independent variable is `injection_count`, the number of attack/anomaly
events deliberately introduced during one run. The dependent variable is the
percentage of repeated runs that the detector labels anomalous:

```text
anomaly_percentage = 100 * anomalous_predictions / completed_trials
```

This is a detection-rate chart, not a claim about model accuracy. Accuracy,
precision, recall, and false-positive rate must be reported separately using
ground truth.

## Campaigns

Run two campaigns with the same workload, duration, collector configuration,
detector version, and randomization policy:

| Campaign | Injection levels | Recommended repetitions | Purpose |
| --- | ---: | ---: | --- |
| `short` | 1 through 10 | 20 per level | Reproduce the first compact figure |
| `extended` | 1 through 30 | 20 per level | Reproduce the second figure |

Include a zero-injection control with at least 20 repetitions in each campaign.
The control estimates the false-positive rate and should be shown in the data
even if it is omitted from the figure's x-axis.

Twenty repetitions gives a useful first plot, but the final paper should use
at least 30 repetitions per level when runtime permits. Use a fixed seed list
for reproducibility, for example `1000` through `1019`, and randomize trial
order so that time drift is not confounded with injection count.

## One trial

Each trial should follow this sequence:

1. Reset the free5GC/UE testbed and verify that the expected NFs and `ueTun*`
   interface are available.
2. Start a clean five-second baseline workload.
3. Inject exactly `injection_count` events at uniformly spaced timestamps.
4. Collect Linux, eBPF, SBI, PFCP, and free5GC telemetry with the existing
   collectors.
5. Run the frozen detector artifact, such as `models/rf-v1`, once on the
   completed run.
6. Record the detector prediction, score, ground-truth injection count, and
   any failed or incomplete trial. Do not silently convert a failed trial into
   a negative prediction.

An injection must have a stable definition. Record its mechanism and timing,
for example `sbi_error_burst`, `pfcp_delay`, or `cpu_load_spike`, rather than
mixing mechanisms in a single series. If multiple mechanisms are required,
stratify the output by `mechanism` and generate one chart per mechanism.

## Data file

Write one row per attempted trial to
`data/injection_campaign/<campaign>.csv`. The minimum schema is:

```text
campaign,trial_id,seed,injection_count,mechanism,scenario_id,run_id,
duration_sec,detector_version,anomaly_score,predicted_anomalous,
ground_truth_anomalous,status,started_at
```

Use `status=complete` only when all required telemetry streams and the
detector result are present. Keep `status=failed` rows for auditability, but
exclude them from the denominator and report their count. `run_id` must be
unique per trial.

The train/validation/test split remains whole-run. The detector must be
trained only on pre-campaign training data or on the campaign's training runs;
never train on a test trial and then plot that same trial as evidence.

## Analysis output

For every `(campaign, mechanism, injection_count)` group, calculate:

- `completed_trials`
- `failed_trials`
- `anomalous_predictions`
- `anomaly_percentage`
- a binomial 95% confidence interval
- `true_positive_rate`, `precision`, and `false_positive_rate` when ground
  truth labels are available

Save the aggregated table as
`evaluation/injection/injection_sensitivity_summary.csv`. The chart should use
`injection_count` on the x-axis, `anomaly_percentage` on the y-axis, one bar
per injection level, and error bars for the confidence interval. Use a fixed
y-axis policy: either `0..100%` for both panels, or clearly label a truncated
axis. Do not choose the axis independently to exaggerate differences.

## Reproduction commands

The collection command is intentionally deployment-specific because the
injector runs on the Ubuntu testbed, while analytics may run on the GPU host:

```bash
# Ubuntu/testbed: replace with the approved injector/controller entry point.
uv run python scripts/run_injection_campaign.py \
  --campaign short \
  --levels 0-10 \
  --repetitions 20 \
  --seed 1000 \
  --output data/injection_campaign/short.csv

# GPU-dependent training or inference must be submitted through Slurm.
# CPU-only aggregation and plotting can run locally.
uv run python scripts/summarize_injection_campaign.py \
  --input data/injection_campaign/short.csv \
  --output evaluation/injection/injection_sensitivity_summary.csv
```

The `run_injection_campaign.py` command above is the planned collection
interface; it should not be added until the exact injector mechanism and
testbed reset procedure are approved. This keeps the experiment design honest
while making the expected data contract and chart reproducible.

## Interpretation safeguards

- Do not fabricate chart values before the campaign has produced complete
  trial rows.
- Keep the detector threshold and model artifact fixed across injection
  levels.
- Report zero-injection false positives separately.
- Report missing/failed trials and confidence intervals.
- Repeat the campaign for each injection mechanism instead of pooling unlike
  mechanisms.
- Treat the result as controlled testbed sensitivity evidence, not production
  generalization.