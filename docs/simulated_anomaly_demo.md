# Offline Synthetic Anomaly Demonstration

## Executed Demo

The user requested simulated data to exercise the pipeline despite missing
historical measurements. The demo is completely separate from real NAS evidence:
[fuzz_anomaly_demo_20261003](../data/simulation/fuzz_anomaly_demo_20261003/README.md).
It does not fill missing fields in RNAS0001 or substitute later/live values.
Every generated scenario, window, mock review, plan and result is explicitly
marked `simulation_only`. Input files are text identifiers, not NAS payloads.

Executed stages:

```text
Synthetic input identity and scenario outcome
  -> mock protocol/cleanup/review evidence
  -> generated healthy Linux/SBI/PFCP snapshots
  -> sixteen recomputed window features
  -> Random Forest fitting on 36 synthetic runs
  -> prediction/evaluation on 18 separate synthetic runs
  -> six local non-executing simulated review alerts
```

The three generator-defined labels are normal, expected rejection, and anomalous.
The generated anomalous scenario has higher load and lower available-memory
ratio. No actual free5GC crash, service anomaly, independent human approval,
fuzz reproduction, or live collector health is represented. Virtual dates and
all-zero revision placeholders exist only to exercise the evidence checks;
they are not observations or preregistered research dates.

## Results: Simulation Only

| Measurement | Synthetic Result |
| --- | ---: |
| Train runs | 36 |
| Held-out synthetic runs | 18 |
| Features | 16 |
| Precision / recall / F1 / ROC AUC | 1.0 / 1.0 / 1.0 / 1.0 |
| False-positive rate | 0.0 |
| Confusion matrix TN / FP / FN / TP | 12 / 0 / 0 / 6 |
| Local simulated alerts | 6 |

These perfect scores reflect deliberately easy synthetic separation. They are
plumbing verification, **not detection efficacy or paper results**. The generator
label is fixed before model scoring; model output is not used as ground truth.
The resulting distributions are not calibrated to the real testbed.

## Inspect and Reproduce

- [Demo summary](../data/simulation/fuzz_anomaly_demo_20261003/demo_summary.json)
- [Evaluation details](../data/simulation/fuzz_anomaly_demo_20261003/results.json)
- [Simulated alerts](../data/simulation/fuzz_anomaly_demo_20261003/simulated_alerts.json)
- [Dataset manifest](../data/simulation/fuzz_anomaly_demo_20261003/dataset.json)

Run again into a new directory:

```bash
PYTHONPATH=src .venv/bin/python scripts/run_simulated_anomaly_demo.py \
  --output-dir data/simulation/<new-demo-directory> --seed 42
```

Existing output directories are refused. The script performs no SSH, live NAS,
NRF, model deployment, notification delivery or mitigation. Mock approvals are
explicitly not independent review and use `independence_declared: false`.

The real anomaly-data loader defaults to `allow_simulation=False`. The demo
must opt in explicitly, retains simulation markers in evaluation results and
cannot silently satisfy the real independent-outcome-label requirement. Do not
remove markers or merge these artifacts into a research dataset. Real historical
training readiness remains blocked until its actual evidence is available.