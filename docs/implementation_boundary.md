# Implementation Boundary

This matrix is the source of truth for claims about the current prototype.

| Capability | Status | Evidence or boundary |
| --- | --- | --- |
| Linux load and memory telemetry | Implemented | Run-level feature builder and live SSH observer |
| Linux process telemetry | Implemented | `linux/process_events.jsonl` and run-level features |
| SBI telemetry | Implemented | Real Ubuntu collector and supplemental campaigns |
| PFCP telemetry | Implemented | Real Ubuntu collector and supplemental campaigns |
| free5GC log telemetry | Implemented | Supplemental run outputs |
| eBPF telemetry | Conditional | Collector support exists; availability is recorded explicitly |
| OVS telemetry | Read-only adapter implemented | `live/ovs_observer.py` inventories bridges, ports, and flows when OVS tools exist |
| OVS enforcement | Not implemented | No flow mutation or path enforcement is performed |
| Kubernetes/container telemetry | Read-only adapter implemented | `live/kubernetes_observer.py` supports `kubectl`, Docker, Podman, or CRI inventory; no mutation or isolation action is implemented |
| Runtime socket telemetry | Read-only observer implemented | `live/runtime_socket_observer.py` checks socket metadata and process access without opening sockets |
| Runtime socket abuse scenario | Not implemented | Controlled abuse generation remains future scenario |
| Namespace/process/resource scenarios | Implemented | Controlled S01/S04/S07 and benign controls |
| SBI/cross-slice signaling scenarios | Implemented as approximations | S08/S10/S14; S10 is signaling-layer only |
| MTLF-style model training | Implemented as research scripts | CPU Random Forest training and model artifact |
| AnLF-style inference | Implemented as external wrapper | `NWDAFResearchAnalyzer` and FastAPI API |
| DCCF | Implemented as prototype processing | `architecture/dccf.py` normalizes and correlates run events; not a standardized 3GPP DCCF service |
| MFAF/MTLF model lifecycle | Implemented as prototype registry | `architecture/mfaf.py` registers approved model artifacts and manifests; training remains CPU Random Forest |
| ADRF | Implemented as prototype persistence | `architecture/adrf.py` stores analytics/evidence records in SQLite; not a standardized 3GPP ADRF service |
| SecIR workflow compilation | Implemented as prototype compiler | `architecture/secir.py` turns evidence-backed decisions into typed steps, preconditions, postconditions, and rollback; not a full SecIR platform |
| VFL/OAM reporting | Implemented as prototype reporting | `architecture/vfl.py` creates lifecycle/audit reports; no external BOSS platform |
| NemoIR narrative | Implemented as non-executing renderer | `nemoir.py` renders evidence-backed workflow summaries; it does not execute workflows |
| Policy decision point | Implemented | Allow-list, confidence, target, duration, and rollback checks |
| Operator alert | Implemented | Authenticated Ubuntu response-agent |
| Reversible `tc` rate limit | Implemented and trialed | `tbf` apply followed by `fq_codel` restoration |
| NF quarantine | Not implemented | Future controlled adapter |
| Clean NF replacement | Not implemented | Future deployment integration |
| UPF failover | Not implemented | Future deployment integration |
| OAM/OSS/BOSS integration | Partial | Experimental notification payload and optional callback; no BOSS platform |
| Full 3GPP NWDAF compliance | Not claimed | External NWDAF-like prototype only |
| GPU-accelerated ML | Implemented and measured as optional backends | CUDA MLP F1 0.9412; temporal GRU F1 0.8571; current Random Forest remains the CPU baseline |
| Causal recovery evaluation | Not established | Current B2 trials validate bounded execution and restoration |
