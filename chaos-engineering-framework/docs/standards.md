# Standards alignment (how the project maps to them)

| Standard | Requirement area | Where in this project |
|---|---|---|
| NIST Cybersecurity Framework (Respond / Recover, Identify) | detect events, recover, improve | anomaly detection + automated remediation; v1 -> v2 improvement; experiments document risks |
| NIST SP 800-160 Vol. 2 (cyber resiliency) | anticipate, withstand, recover, adapt | chaos experiments (anticipate), redundancy/failover (withstand), self-healing + MTTR (recover), AI feedback loop (adapt) |
| NIST SP 800-53 CP-4 | contingency plan testing | the four repeatable experiments are scheduled-style failure tests with recorded results |
| ISO/IEC 27001:2022 Annex A.5.29 / A.5.30 | information security during disruption, ICT readiness for continuity | node-failure and outage experiments; replicas, PDBs, probes |
| ISO/IEC 27001:2022 A.8.14 | redundancy of processing facilities | multiple replicas spread over nodes |
| ISO/IEC 27001:2022 A.8.15 / A.8.16 | logging, monitoring activities | Loki logs, Prometheus metrics, Jaeger traces, Grafana dashboard |
| High-availability best practice | no single point of failure, health checks, graceful degradation | v2: replicas, topology spread, readiness/liveness probes, retries with timeouts, PodDisruptionBudget, HPA |

This is an alignment mapping for a lab, not a certification claim.
