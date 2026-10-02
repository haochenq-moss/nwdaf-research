# Project Status and TODOs

## Paper Campaign Preflight (2026-09-25)

The historical completion entries below describe pilot work, not completion of
the fresh campaign required by `SecureNWDAF_free5GC_Forum2026_12page_draft.tex`.
Preserve prior archives and artifacts, but exclude their measurements and model
checkpoints from new-campaign results. Keep paper result placeholders unchanged
until new evidence is collected and validated.

- [x] Read the paper and two-machine reproduction runbook.
- [x] Verify local Python: `.venv/bin/python` reports 3.11.16.
- [x] Record inspected HEAD: `85be44f44bd2d6e7e58fa95da7e8d40ddd06dbd3`.
	Existing uncommitted changes remain in place; HEAD alone does not identify the
	complete working-tree state for a future campaign freeze.
- [x] Verify immutable pilot archive SHA-256:
	`8cefce33e78fecb6786895c1ce9f153937a6624d969940ea11b55b32660cfe57`.
- [x] Run 12 selected CPU-only regression tests: loader, features, model
	provenance, policy predicates, and the non-executing Mock NF adapter. All pass.
	The provenance test creates a temporary pilot-based model solely for regression
	verification; it is not a new-campaign artifact or scientific result.
- [x] Initial port check found no listeners on 2222, 9090, or 8000.
- [x] Subsequent check confirms reverse-tunnel listeners on loopback ports 2222
	and 9090. Authenticated SSH reaches Ubuntu host `free5gc`, kernel
	`5.15.0-139-generic`; the response-agent `/health` returns HTTP 200 and `ok`.
- [x] Observe running AMF, SMF, UPF, NRF, UDM, UDR, PCF, NSSF, and AUSF
	processes plus two `free-ran-ue` processes. `ueTun0` is UP with
	`10.60.0.1/32`; `upfgtp` is also present. These checks establish process and
	interface liveness, not successful packet delivery or service recovery.
- [x] Record remote HEAD revisions: free5GC
	`4aa237be57404dea5b49ca8f332c6e25ede052de`, free-ran-ue
	`afcb79dd6a8bedef34c6f8b2015ee99bd1e3e832`. Remote free5GC has existing
	changes to `README.md` and `cert/nrf.pem`; preserve both. The free-ran-ue
	working tree subsequently reported no changes via `git status --short`.
- [x] Verify executable roles: PID 4873 is one gNB and PID 5499 is one UE.
	The baseline probe reports two UE command-line matches, but that is not an
	actual UE count. Only one addressed UE tunnel was observed.
- [x] Attempt bounded user-plane verification via
	`ping -n -I ueTun0 -c 3 -W 2 -w 8 8.8.8.8`: exit 1, no replies.
	The command reported eight transmitted packets despite `-c 3`; retain that
	observed result, not a claim that exactly three packets were sent.
	The route lookup selects `ueTun0`; subsequent cumulative interface counters
	show TX 17 packets and RX 0. This does not locate the packet-loss cause.
- [x] Inspect host routing and forwarding without changing network state:
	default route is via `10.0.2.2` on `enp0s3`; UE pools `10.60.0.0/16` and
	`10.61.0.0/16` route to `upfgtp`. Host `net.ipv4.ip_forward` and per-interface
	forwarding on `enp0s3`, `upfgtp`, and `ueTun0` are all 0. UPF configuration
	uses N3 address `10.0.2.15`, NAT interface `enp0s3`, and
	`ipForwardEnable: true`; configuration intent is not proof of active rules.
	Reading the UPF process network namespace was permission-denied, so its
	namespace identity remains unverified.
- [x] Compare host connectivity using bounded probes: one gateway ping to
	`10.0.2.2` succeeded (13.306 ms), one host-interface ping to `8.8.8.8`
	received no reply, and a TCP connection to `1.1.1.1:443` timed out after
	4 seconds. These failures do not establish that all outbound access is blocked.
- [x] Review user-provided privileged firewall output: FORWARD policy ACCEPT,
	UE-subnet outbound/established-return ACCEPT rules, and POSTROUTING
	MASQUERADE rules for both UE pools on `enp0s3`. Rule counters were not supplied.
- [x] Recheck after the user-side forwarding change: `net.ipv4.ip_forward = 1`.
	UE-to-gateway ping still failed with 3 sent and 0 received. Enabling forwarding
	alone did not restore connectivity. The assistant made no network changes.
- [x] Inspect same-host routing: `ip route get 10.60.0.1` resolves as local via
	`lo`, and the local table assigns that address to `ueTun0`. Both all-interface
	and `upfgtp` `accept_local` are 0; both `rp_filter` values are 2. A forwarded
	route lookup to the gateway from the UE address with `iif upfgtp` failed with
	`Invalid argument`. These observations suggest local-source filtering and
	return-path conflicts, but do not prove the packet drop location.
- [x] Review user-provided bounded captures: `any` captured six request records
	(two per sequence) and no replies; a subsequent `enp0s3` capture reported
	zero captured packets during another failed three-packet UE ping. The first
	capture did not identify interfaces, so duplicate records alone do not prove
	where packets traveled.
- [x] Review user-executed temporary `upfgtp.accept_local=1` test: forwarded
	route lookup changed to `Invalid cross-device link`, and ping still reported
	3 sent / 0 received. The user restored `accept_local=0`. Local-source
	acceptance alone is insufficient; reverse-path validation remains a hypothesis.
- [x] Prepare a UE-only namespace setup and rollback procedure in
	[the reproduction guide](docs/reproduction.md#prepared-single-ue-namespace-recovery).
	Reviewed the upstream namespace script, tunnel creation, transport binding,
	and current launch/configuration. Keep gNB/core unchanged; use a dedicated
	private veth transport and a tunnel-only gateway probe route. The upstream
	script's teardown/RAN changes are not used. New shell blocks pass `bash -n`,
	and read-only configuration assertions pass against the current Ubuntu UE YAML.
- [x] With user approval, verify original UE shutdown and removal of its
	host-local tunnel/address while gNB PID 4873 remains. The user created the
	UE-only namespace and reported 3/3 transport replies from `10.0.2.15`.
	The restarted UE (observed PID 27269) has namespace `ueTun0` at `10.60.0.2/32`.
- [x] Test isolated PDU routing: user output selects `ueTun0`, source `10.60.0.2`,
	for gateway `10.0.2.2`, but ping still reports 3 sent / 0 received. Host
	forwarded lookup now selects `enp0s3` without error, and the return lookup
	selects `upfgtp`, not local delivery. Forwarding is 1; `accept_local` is 0.
	A subsequent cumulative UPF snapshot shows RX 27 packets, TX 3 packets,
	and TX errors 10; without before/after deltas these cannot identify this
	probe's failure. Namespace isolation corrected route lookups, not connectivity.
- [x] Captured new-topology egress via `enp0s3` during a bounded window: two of
	three ICMP requests appeared as `10.0.2.15 > 10.0.2.2` with immediate replies,
	confirming external NAT/round-trip succeeds; the UE still received nothing.
- [x] Captured loopback GTP-U (UDP 2152/2162) during a repeat ping: uplink
	packets correctly go `10.0.2.15:2162 > 10.0.2.15:2152` (gNB to UPF), but the
	paired downlink packets are `10.0.2.15:2152 > 10.0.2.15:2152` — sent back to
	the UPF's own N3 port instead of the gNB's configured N3 port `2162`. Session
	logs show only routine PFCP heartbeat/usage-report activity, no explicit
	F-TEID value or error. This is the most likely root cause of UE downlink
	loss: a probable co-located gNB/UPF port-negotiation issue, not a routing,
	NAT, or namespace defect. Not yet confirmed against a decoded GTP-U header.
- [ ] This is a deeper simulator/session-negotiation issue, out of scope for
	further routing changes. Rollback of the diagnostic UE namespace remains
	untested and unexecuted; host-only observers are not namespace-aware.
	E4/E5 (service-level impact and response verification) remain blocked on a
	working service path. E1-E3 do not require it; see the current preparation
	work below.
- [x] Test existing SBI/PFCP parsers on the last 500 lines per file across 143
	existing log files: 354 SBI and 1961 PFCP records parsed. These are historical
	log samples, not a live collector test or fresh-campaign observations.
- [ ] Verify RAN/UE roles, session health, and actual collector availability.
	Roles are verified; successful packet delivery, live capture, and current
	eBPF availability remain unverified. A successful baseline probe establishes
	process/interface presence only and must not override the failed ping.
	Response-agent health alone does not establish authorization or rollback safety.
- [ ] Inventory supported stimulus IDs and their safe bounds on the testbed.
	Historical dataset labels alone do not establish current stimulus support.
- [x] Read the full remote scenario registry (all 10 IDs: NORMAL, S01, S04, S07,
	S08, S10, S11, S12, S13, S14), `config/scenarios.yaml` (bounds 30-60s except
	NORMAL 3600s, all `reversible: true`, `required_components` only `linux` or
	`sbi`), the full `experiment_controller.py`, `run_metadata.py`,
	`throughput.py`, and `validation/checks.py`. Every scenario's required
	modality matches what is currently functioning (host Linux telemetry and
	SBI control-plane logs); none require the broken service/data path.
- [x] Confirmed `next_run_id`/`run_path.mkdir(exist_ok=False)` make sequential
	single-controller run allocation collision-safe; no locking exists for
	concurrent controllers, so only run one controller process at a time.
	`--require-baseline` is optional and off by default; the fresh campaign
	driver always passes it explicitly. `ground_truth.json` hardcodes
	`service_impact: "none"` and a two-valued `attack_phase`; report this as a
	labeling limitation rather than a measured service-impact signal.
	`config/testbed.yaml` is a stale snapshot from `2026-09-15`; it must be
	regenerated from a live inventory before it is embedded in fresh-run metadata.
- [x] Defined a fresh E1-E3 campaign matrix and local orchestration driver
	entirely in this repository, without modifying the remote research code:
	[configs/campaign_e1e3.yaml](configs/campaign_e1e3.yaml) and
	[scripts/run_e1e3_campaign.py](scripts/run_e1e3_campaign.py). Repetitions
	within a cell reuse one fixed seed (5 repetitions x 10 scenarios x 2
	partitions = 100 cells); `dev`/`held_out` seed ranges are disjoint. Load is
	fixed to `L0` for every cell, with the L1/L2 and service-modality
	limitations recorded, not silently worked around. E4/E5 remain excluded.
- [x] Validated the driver in default dry-run mode (no SSH/network calls): 100
	cells generated, one fixed seed per (partition, scenario), zero seed overlap
	between partitions, and a correctly formed example remote command. Confirmed
	`--execute` refuses to run without `NWDAF_CAMPAIGN_CONFIRM=I_UNDERSTAND`.
- [x] Rolled back the diagnostic UE namespace: confirmed `ip netns pids nwdaf-ue`
	empty, deleted `nwue-host`/`nwdaf-ue`, and restarted the original single-host
	UE (new PID, new tunnel address `10.60.0.3/32`). Re-verified
	`baseline_verified: true`, `ran_verified: true`, `pdu_session_verified: true`,
	and original routes restored with no lingering namespace/veth resources.
- [x] Regenerated `config/testbed.yaml` from a live inventory via the existing
	read-only `research.controller.inventory` module: commit now matches current
	HEAD `4aa237be...`, current interfaces, and current NF/component status.
	Only `README.md`, `cert/nrf.pem`, and this refreshed file are dirty.
- [ ] Remaining precondition before real execution: explicit user approval to
	run live scenario stimulus cells from
	[configs/campaign_e1e3.yaml](configs/campaign_e1e3.yaml) via
	[scripts/run_e1e3_campaign.py](scripts/run_e1e3_campaign.py) `--execute`.
- [x] User approved. Executed all 100 cells: 100/100 `status: complete`, 0
	failures, 100 unique remote run IDs (`R00001`-`R00100` under
	`~/free5gc/dataset/raw/campaign_20260925_e1e3`). All scenarios present with
	10 runs each (5 dev + 5 held-out). Traffic controller started cleanly in
	every run (ping itself still fails per the known GTP downlink issue).
- [x] Pulled the fresh dataset locally (rsync, ~20 MB) into
	[data/raw/campaign_20260925_e1e3](data/raw/campaign_20260925_e1e3), isolated
	from the pilot archive. Built `split_manifest.json` directly from the
	recorded dev/held_out partitions (50/50). The existing, tested
	`DatasetLoader`/`RunFeatureBuilder` work unmodified on this data.
- [x] Ran E1/E3 baseline detection in
	[scripts/evaluate_e1_e3.py](scripts/evaluate_e1_e3.py): B0 threshold and B1
	Random Forest both fit on `dev` only, evaluated once on `held_out`. Full
	results in
	[data/processed/campaign_20260925_e1e3_e1_e3_results.json](data/processed/campaign_20260925_e1e3_e1_e3_results.json).
	**Honest finding, not a success to report uncritically:**
	- Using the `anomalous` label (scenario != NORMAL, severely imbalanced at
		45/50 positive in held_out): both B0 and B1 reach F1 0.936, but with
		**0% specificity** (every one of the 5 held-out NORMAL runs is
		misclassified) and B1's ROC AUC is only 0.624. The high F1 is a class-
		imbalance artifact, not evidence of real detection.
	- Using the more balanced `security` label (true attack S01/S04/S07/S08/S10
		vs normal+benign-hard-negative, 25/25 in held_out): B0 collapses to
		near-constant positive (F1 0.649, 0% specificity again); B1's confusion
		matrix is close to chance (TN9/FP16/FN13/TP12, ROC AUC 0.474).
	- Conclusion to date: with the current fixed `L0`, 20s-duration, single
		dev/held-out split, **neither B0 nor B1 is reliably distinguishing
		scenarios from Linux/SBI/PFCP features**. Do not present these numbers as
		a working detector. Plausible causes to investigate before drawing
		further conclusions: too few NORMAL repetitions, too-short run duration,
		or genuinely weak signal from the currently available modalities alone.
	- E2 (host/5G modality ablation) is not yet computed.
- [x] Ran a v2 diagnostic campaign to test whether v1's weak result was a
	small-sample artifact: 10 repetitions/cell (up from 5), duration 28s (up
	from 20s, still under the shared 30s hard cap), same 10 scenarios, disjoint
	seed ranges from v1. [configs/campaign_e1e3_v2.yaml](configs/campaign_e1e3_v2.yaml).
	First execution attempt failed all 200 cells because the reverse SSH tunnel
	had gone down (confirmed via `ss` showing no listeners on 2222/9090; the
	testbed itself was untouched, no partial runs were created). After the user
	restarted the tunnel, re-execution completed 197/200; the remaining 3
	(`dev`/`NORMAL` reps 0-2) failed on a transient SSH banner-exchange timeout
	at the very start of the retry and were re-run directly and merged into the
	manifest. Final: 200/200 unique remote runs, verified via `probe_baseline()`
	before restart.
- [x] Pulled v2 data (49 MB, 200 runs) into
	[data/raw/campaign_20260925_e1e3_v2](data/raw/campaign_20260925_e1e3_v2)
	(isolated from v1), built its split manifest from the recorded partitions,
	and re-ran the (now parameterized)
	[scripts/evaluate_e1_e3.py](scripts/evaluate_e1_e3.py) with 100/100
	dev/held-out. Full results in
	[data/processed/campaign_20260925_e1e3_v2_e1_e3_results.json](data/processed/campaign_20260925_e1e3_v2_e1_e3_results.json).
	**This rules out "v1 was just underpowered" as the explanation:**
	- `anomalous` label (90/10 imbalance in held_out): B0 F1 0.9 (still only
		1/10 true negatives correct); B1 F1 0.925 but **ROC AUC dropped to
		0.303 - worse than random ranking**, a possible sign of overfitting with
		~100 training runs against dozens of features.
	- `security` label (50/50 balanced): B0 F1 0.623 (16/50 true negatives, still
		poor); B1 F1 0.440, ROC AUC 0.548 - still essentially chance.
	- With double the data and a longer observation window, detection quality
		did not improve and in one case got worse. Do not attribute v1's result to
		sample size; the more likely explanations are (a) genuinely weak signal
		from bounded/reversible/safe-by-design stimuli in Linux/SBI/PFCP count
		features, or (b) too many features relative to sample size causing
		overfitting. Next diagnostic step, not yet done: inspect per-feature
		separability (e.g., simple univariate tests) and consider feature
		selection or dimensionality reduction before concluding the modalities
		themselves carry no usable signal.
- [x] Ran a diagnostic-only univariate feature-separability check
	([scripts/inspect_feature_separability.py](scripts/inspect_feature_separability.py))
	over all 200 v2 runs combined (dev+held_out; this is exploratory analysis
	for maximum statistical power, not a frozen evaluation, and was not used to
	select features/thresholds for the reported B0/B1 comparison). Full results
	in
	[data/processed/campaign_20260925_e1e3_v2_feature_separability.json](data/processed/campaign_20260925_e1e3_v2_feature_separability.json).
	**This rules out overfitting as the primary explanation:** the single best
	feature for the `anomalous` label (`linux_memory_available_mean`/
	`memory_available_ratio_mean`) reaches only AUC 0.752, and the single best
	feature for the more meaningful `security` label
	(`sbi_telemetry_available`) reaches only AUC 0.60. No feature shows strong
	discriminative power. **Conclusion to date: the current Linux/SBI/PFCP
	count-based features genuinely carry only weak signal for distinguishing
	these bounded, safe-by-design scenarios on this co-located single-host
	testbed** - this is not simply a matter of collecting more data or
	reducing the RF's feature count. Do not report a working detector without
	either (a) adding genuinely new modalities (e.g., the currently-broken
	service/data path once fixed, or eBPF if available), or (b) explicitly
	scoping the paper's detection claim to this honest, weak-signal finding.
- [ ] Execute E1 detection, E2 modality ablation, and E3 held-out evaluation with
	fresh evidence and training artifacts; fit preprocessing only on training data
	and select thresholds/hyperparameters without using test results.
- [ ] Execute E4 online timing and matched overhead measurements on the real
	testbed; execute E5 paired trials only with explicit target/rate/duration bounds,
	authenticated policy approval, and verified rollback readiness.
- [ ] Generate paper tables from frozen new-campaign manifests and report
	unavailable measurements explicitly. GPU workloads must use Slurm.

Reproduce the selected offline checks from the repository root:

```bash
PATH="$PWD/.venv/bin:$PATH" PYTHONPATH="$PWD/tests:$PWD/src" \
	.venv/bin/python -m unittest test_loader test_features test_provenance \
	test_policy_and_mitigation.PolicyEngineTests \
	test_policy_and_mitigation.MockNFAdapterTests -v
sha256sum data/pilot_raw.tar.gz
ss -ltn '( sport = :2222 or sport = :9090 or sport = :8000 )'
```

## Phase 1 — Dataset reconnaissance and documentation
- [x] Inspect repository state and archive contents
- [x] Verify archive structure and run count
- [x] Confirm available telemetry sources and file formats
- [x] Verify metadata, ground truth, timeline, and split manifest
- [x] Determine the first valid ML task based on actual dataset evidence
- [x] Create data/raw extraction workflow without modifying the original archive
- [x] Write data/README.md from verified facts only
- [x] Add a machine-readable schema for actual fields in the dataset

## Phase 2 — Data ingestion and validation
- [x] Implement a minimal loader for run metadata, ground truth, timeline, linux events, and split assignments
- [x] Validate missing/empty telemetry streams and record warnings clearly
- [x] Preserve run ID, timestamp, and provenance fields
- [x] Design reproducible run-level train/val/test splitting logic

## Phase 3 — Preprocessing and features
- [x] Build a preprocessing module for timestamp normalization and missing-value handling
- [x] Aggregate Linux telemetry to run-level features
- [x] Add feature provenance tracking (source -> transform -> output)
- [x] Keep all transformations reproducible and separate from raw data

## Phase 4 — Baseline ML
- [x] Train a baseline anomaly detector on run-level features
- [x] Evaluate on the provided whole-run splits
- [x] Report class-wise and overall metrics on the verified labels
- [x] Record model config, seed, and dataset version for reproducibility

## Phase 5 — NWDAF-like analytics
- [x] Wrap the best validated baseline in a research NWDAF-style API
- [x] Keep analytics model-agnostic and dataset-driven
- [x] Avoid claiming live free5GC/NWDAF integration before the offline pipeline is validated
- [x] Add the NWDAF-style run scoring pipeline and batch export workflow
- [x] Validate feature ablation on the same whole-run split to confirm the full feature set remains strongest

## Completed Architecture and Response
- [x] Prototype DCCF normalization/correlation module
- [x] Prototype MFAF model registry
- [x] Prototype ADRF durable evidence store
- [x] Prototype SecIR typed workflow compiler
- [x] Prototype VFL operational reporting
- [x] Non-executing evidence-grounded NemoIR workflow renderer
- [x] Policy engine, authenticated Ubuntu response-agent, audit, and replay protection
- [x] Real reversible `tc` rate-limit trial with automatic `fq_codel` restoration
- [x] Kubernetes/container, OVS, and runtime-socket read-only observers
- [x] Optional CUDA MLP and temporal GRU backends with Slurm jobs
- [x] Pilot, supplemental SBI/PFCP, multi-load, randomized-live, and GPU experiments
- [x] 71 automated tests

## Remaining Deployment-Level Work
- [ ] Kubernetes NetworkPolicy/pod quarantine enforcement
- [ ] Container-runtime socket abuse generation in a disposable runtime
- [ ] OVS flow mutation and rollback adapter
- [ ] Clean NF replacement and re-registration
- [ ] UPF failover with matched service-state verification
- [ ] Real OAM/OSS/BOSS platform integration
- [ ] Causal attack/recovery experiment with matched no-response control
- [ ] Strict dedicated response-agent service account with no broader sudo access
- [ ] Full 3GPP NWDAF conformance and interoperability testing

## Research Extensions
- [ ] Expand scenarios and unseen attack seeds
- [ ] Add load/topology conditions and collector overhead measurements
- [ ] Add calibration plots and confidence intervals to all public result tables
- [ ] Evaluate GPU/CPU cost and throughput at larger scale

## Guardrails
- [x] Never modify or delete the raw archive
- [x] Never fabricate telemetry, labels, or free5GC behavior
- [x] Never mix observed fact, model prediction, agent hypothesis, and NEMOIR reasoning
- [x] Keep all work dataset-first and evidence-based
