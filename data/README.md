# Dataset documentation

## Source archive
- Source archive: data/pilot_raw.tar.gz
- Original archive is treated as immutable source data and was not modified.

## Extraction
- Extraction is performed into a derived directory: data/raw
- Reproducible extraction script: scripts/data/extract_dataset.py
- Command:
  ```bash
  python scripts/data/extract_dataset.py
  ```

## Verified directory structure
The extracted dataset contains a top-level `raw/` directory and a root `split_manifest.json` file.

Example structure:
```text
data/raw/
├── split_manifest.json
└── raw/
    ├── R00001/
    ├── R00002/
    └── ...
        ├── metadata.json
        ├── ground_truth.json
        ├── timeline.json
        ├── linux/
        │   ├── events.jsonl
        │   └── process_events.jsonl
        ├── free5gc/
        │   └── events.jsonl
        ├── pfcp/
        │   └── events.jsonl
        └── sbi/
            └── events.jsonl
```

## Verified file formats
- JSON files: metadata.json, ground_truth.json, timeline.json
- JSON Lines: events.jsonl and process_events.jsonl

## Verified run structure
- 90 valid runs: R00001 through R00090
- Run-level metadata, ground truth, and event streams are organized per run directory.

## Verified telemetry sources
- Linux host telemetry: present and populated
- Linux process telemetry: present
- free5gc events: archive entry exists, but the matched event streams inspected in the transferred dataset are empty
- pfcp events: archive entry exists, but the matched event streams inspected in the transferred dataset are empty
- sbi events: archive entry exists, but the matched event streams inspected in the transferred dataset are empty

## Verified labels and ground truth
Ground truth is provided at run level in each run's `ground_truth.json`.

Observed keys include:
- `run_id`
- `scenario_id`
- `class`
- `anomalous`
- `security`
- `service_impact`
- `severity`
- `attack_phase`
- `action`

Observed scenario values include:
- NORMAL
- S01, S04, S07, S08, S10, S11, S12, S13, S14

Observed class values include:
- normal
- administrative_operation
- namespace_anomaly
- process_anomaly
- resource_exhaustion
- sbi_anomaly
- cross_slice_anomaly
- service_degradation

## Verified metadata and provenance
The per-run `metadata.json` includes fields such as:
- run_id
- created_at
- scenario_id
- host_id
- load_profile
- duration_sec
- provenance
- testbed
- kernel
- os
- python
- research_commit
- throughput
- traffic
- deployment
- status
- baseline

The metadata indicates that the dataset was generated in a free5GC testbed context and records a `collector_version`, kernel version, OS, and research commit metadata.

## Verified timestamps
- `created_at` is present in metadata.json
- `timeline.json` contains run-level timestamps under keys such as `T0`, `T1`, `T2`, `T3`, `T4`
- Linux event records include `event_time` and `collection_time`

## Split information
A whole-run split manifest is present at `data/raw/split_manifest.json`.

Verified counts:
- train: 60
- val: 20
- test: 10

This is a run-level split, not a record-level split; it should be preserved for model evaluation.

## Verified limitations and missing information
- PFCP, SBI, and free5gc JSONL streams are present as files but are empty in the transferred dataset inspected so far.
- eBPF telemetry is explicitly reported as unavailable in metadata because `bpftrace` requires root/CAP_BPF on the host.
- No live access to the original free5GC testbed is available in this GPU server environment.
- No additional raw packet capture or iperf3 logs were verified in this archive.

## ML-ready observations
The strongest verified ML inputs are:
- per-run metadata
- per-run ground truth
- per-run timeline
- linux host metrics and process events

The first defensible ML task from this dataset is run-level anomaly classification using Linux telemetry and metadata, with the provided whole-run split preserved.

## Data handling rules
- Do not modify the original archive at data/pilot_raw.tar.gz.
- Keep all derived work under data/raw or later processed directories.
- Treat all transformations as reproducible and separate from the raw source data.
