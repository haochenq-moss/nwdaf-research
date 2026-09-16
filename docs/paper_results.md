# Measured Live Results

This report is generated from measured artifacts and does not claim causal mitigation benefit.

## B0/B1 Repeated Trials

Number of sequential trials: 10

| Metric | B0 | B1 |
| --- | ---: | ---: |
| RTT mean (ms) | 0.0486 +/- 0.0084 | 0.0749 +/- 0.0600 |
| Packet loss (%) | 0.0000 +/- 0.0000 | 0.0000 +/- 0.0000 |
| Throughput sent (bit/s) | 9917934001.3549 +/- 3260286086.4548 | 11130662918.8729 +/- 2667303664.5890 |
| Throughput received (bit/s) | 9665481591.0798 +/- 3172241917.0234 | 10881886016.7313 +/- 2616440122.6780 |
| Detection latency (ms) | not applicable | 17.5197 +/- 0.6907 |

Throughput was measured on the local `ueTun0` to Ubuntu-host path. The sequential design does not support a causal claim that B1 changed network performance.

## B2 Alert-Only Trial

Decision: `b2-alert-4a650e51a22d`; prediction: `ANOMALY` with probability `0.885`.
Detection latency: `20.56 ms`; response latency: `24.89 ms`.
Before/after RTT: `0.040` / `0.042 ms`; packet loss remained `0.0%` / `0.0%`.
The action was `alert_operator`, which does not alter network state. These before/after values therefore do not establish recovery caused by mitigation.

## Limitations

- B0/B1 trials were sequential rather than randomized.
- B2 has one alert-only trial; repeated B2 trials are needed for uncertainty estimates.
- `tc` rate limiting remains disabled because Ubuntu requires an interactive sudo password.
- No causal recovery, availability improvement, or mitigation effectiveness claim is made.
