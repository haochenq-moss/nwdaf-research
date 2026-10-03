# Overnight AFL Phase-4 Check: 2026-10-03

Read-only inspection of Slurm accounting and the existing merged campaign
artifacts. Times below are as reported by the cluster; no timezone conversion
was applied. No jobs were queued or running for this user at the inspection.

| Job | Name | Start | End | Elapsed | State | Exit |
| --- | --- | --- | --- | --- | --- | --- |
| 39139 | afl-p4-a | Oct 2 17:51:48 | Oct 2 21:13:25 | 03:21:37 | COMPLETED | 0:0 |
| 39140 | afl-p4-b | Oct 2 21:13:25 | Oct 3 00:35:15 | 03:21:50 | COMPLETED | 0:0 |

Both jobs ran on `TC2N01` with two allocated CPUs. Earlier job `39138`
(`afl-phase4`) was cancelled before starting; it did not execute the benchmark.

## Preserved Source Evidence

The source directory is
`free5gc-security-lab/data/results/afl_multimodel_structured_phase4_20261002_n5_600s/`.
Its `logs/slurm-39139.out` and `logs/slurm-39140.out` show AFL++ QEMU execution
and configured time-limit termination. `matrix_results.csv` contains all 40
runs: two models, two parsers, two seed arms, and five repetitions, with a
600-second budget per run. Reported execution totals are 257,824, with zero
saved crashes, saved hangs, and timeouts.

`coverage_analysis.json` reports all 20 expected paired AUC comparisons,
103-106 plot observations per run (median 105), and no insufficient-sample
runs. `crash_triage.json` reports 3,474 unique frontier input hashes and one
exact match to the previously documented GMM security-capability cut-mid-value
candidate. That match came from an ordinary-seed run and is not a new reviewed
bug or vulnerability. Parser errors are not automatically findings.

## Results and Limits

These are median paired deltas, LLM minus ordinary, from `matrix_report.md`:

| Model | Parser | Final reported edges | AUC mean-edge delta |
| --- | --- | ---: | ---: |
| llama3.2:3b | GMM | +76 | +23.541 |
| llama3.2:3b | GSM | -137 | -215.783 |
| qwen2.5-coder:3b | GMM | -76 | -44.493 |
| qwen2.5-coder:3b | GSM | -170 | -40.333 |

The results are mixed, not general evidence that LLM seeds outperform ordinary
seeds. Llama GMM's AUC delta range crosses zero. Five repetitions are modest.
Go runtime/linker coverage and observed QEMU calibration instability limit
parser-specific interpretation. The logs also show CPU-affinity retries and
slow-target warnings; these did not prevent completion.

The external core-dump handler warning was bypassed with
`AFL_I_DONT_CARE_ABOUT_MISSING_CRASHES=1`. Consequently, zero saved crashes is
not proof that the parser is defect-free or that crash reporting was complete.
No privileged host settings were changed during this inspection.

## NWDAF Handoff

The existing hash-verifying importer staged 48 seed cases into the new campaign
[nas-afl-phase4-20261003](../data/input_testing/nas-afl-phase4-20261003/README.md).
This copies manifest seeds, not all mutated AFL queue inputs. The sidecar links
the source manifest/configuration/results through SHA-256 hashes. The source
campaign and earlier NWDAF campaign were not modified.

Read-only preflight passes corpus integrity but reports missing outcomes,
run labels, and normal/input-test controls. No network replay, telemetry bundle,
detector evaluation, or mitigation was performed. Follow the
[integration runbook](fuzz_to_nwdaf_integration.md) for the remaining gates.