# Layer 1 — Detailed Design

Full technical design for the AI-driven sandboxed firewall rule generation engine.
Reference this when building any Layer 1 component.

---

## Core guarantee
**No untested rule ever reaches the live firewall.**
This is the product's foundational promise. Every component is designed around it.

---

## Data flow (end to end)

```
Network interface
  ↓
Zeek/Suricata (traffic capture + parse into structured logs)
  ↓
Kafka topic: raw-traffic (producer: Zeek, consumer: ingestion service)
  ↓
ClickHouse table: traffic_events (time-series storage)
  ↓
Isolation Forest (reads last N minutes, scores anomaly per flow)
  ↓ if anomaly_score > threshold
LLM provider (swappable — Ollama/llama3.1 default, Claude/OpenAI available — receives traffic summary, outputs candidate rule JSON)
  ↓
Rule parser (validates syntax, extracts fields)
  ↓
PostgreSQL table: candidate_rules (status: PENDING)
  ↓
Celery task: sandbox_test (async)
  ↓
Docker sandbox (isolated network namespace)
  ↓
tcpreplay (replays last 10 min of real traffic against candidate rule)
  ↓
FP scorer (measures: legitimate traffic blocked / total legitimate traffic)
  ↓
  ├─ FP rate > 5% → status: REJECTED, notify analyst
  └─ FP rate ≤ 5% → status: APPROVED_PENDING (awaits human approval in HITL mode)
                              ↓ human approves via dashboard
                           status: LIVE → push to firewall via iptables/pf API
```

---

## Database schemas

### traffic_events (ClickHouse)
```sql
CREATE TABLE traffic_events (
    timestamp    DateTime,
    src_ip       String,
    dst_ip       String,
    src_port     UInt16,
    dst_port     UInt16,
    protocol     String,
    bytes        UInt64,
    packets      UInt32,
    flags        String,
    duration     Float32,
    anomaly_score Float32
) ENGINE = MergeTree()
ORDER BY (timestamp, src_ip)
TTL timestamp + INTERVAL 30 DAY;
```

### candidate_rules (PostgreSQL)
```sql
CREATE TABLE candidate_rules (
    id              UUID PRIMARY KEY,   -- generated app-side (uuid.uuid4), not a DB default — see ADR-019
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW(),
    syntax          VARCHAR(20),        -- 'iptables' or 'pf'
    command         TEXT NOT NULL,
    description     TEXT,
    mitre_technique VARCHAR(64),        -- e.g. "T1046 Network Service Discovery" — code + name, per rule_gen.txt
    confidence      FLOAT,
    fp_rate         FLOAT,
    status          VARCHAR(30),        -- PENDING, SANDBOX_TESTING, REJECTED, APPROVED_PENDING, LIVE, REVOKED
    approved_by     UUID REFERENCES users(id),
    approved_at     TIMESTAMPTZ,
    trigger_event   JSONB,              -- the anomaly that triggered this rule
    sandbox_result  JSONB               -- full sandbox test output
);
```

### audit_log (PostgreSQL)
```sql
CREATE TABLE audit_log (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    timestamp   TIMESTAMPTZ DEFAULT NOW(),
    actor_id    UUID REFERENCES users(id),
    action      VARCHAR(50),            -- RULE_APPROVED, RULE_REJECTED, RULE_REVOKED
    rule_id     UUID REFERENCES candidate_rules(id),
    metadata    JSONB
);
```

---

## API endpoints (FastAPI)

```
GET    /api/v1/rules/              — list all rules with status filter
GET    /api/v1/rules/{id}          — get single rule with full details
POST   /api/v1/rules/{id}/approve  — human approves pending rule (HITL)
POST   /api/v1/rules/{id}/reject   — human rejects pending rule
POST   /api/v1/rules/{id}/revoke   — revoke a live rule
GET    /api/v1/traffic/            — recent traffic events with anomaly scores
GET    /api/v1/traffic/anomalies   — only anomalous events above threshold
GET    /api/v1/dashboard/stats     — summary stats for dashboard
WS     /api/v1/ws/alerts           — WebSocket for real-time alerts
```

---

## Isolation Forest configuration

```python
from sklearn.ensemble import IsolationForest

model = IsolationForest(
    n_estimators=100,
    contamination=0.01,   # expect 1% of traffic to be anomalous — configurable via env
    random_state=42,
    n_jobs=-1             # use all CPU cores
)

# Features extracted per flow for training
FEATURES = [
    "bytes_per_second",
    "packets_per_second",
    "avg_packet_size",
    "duration",
    "dst_port",
    "src_port",
    "flags_syn_ratio",
    "flags_rst_ratio",
    "unique_dst_ports_per_src",  # port scan indicator
    "dns_query_entropy"          # DNS tunneling indicator
]
```

---

## Rule generation: swappable LLM provider (prompt stored in knowledge/prompts/rule_gen.txt)

Rule generation goes through a provider-agnostic interface, not a hardcoded call to one
vendor's API:

```
ml/rule_gen.py            — builds the prompt, calls the factory, parses the JSON response
ml/providers/factory.py   — returns the right provider based on LLM_PROVIDER env var
ml/providers/base.py      — LLMProvider ABC: generate(prompt: str) -> str
ml/providers/ollama.py    — Ollama (DEFAULT — local, free, on-prem capable, model llama3.1)
ml/providers/claude.py    — Anthropic Claude (claude-sonnet-4-6)
ml/providers/openai.py    — OpenAI GPT (gpt-4o)
```

`rule_gen.py` never imports a specific provider — only `providers.factory`. Swapping
providers is a one-line env var change (`LLM_PROVIDER=ollama|claude|openai`), never a
code change. See ADR-017 in decisions.md for the reasoning (cost, on-prem privacy,
vendor independence).

The prompt template itself (`knowledge/prompts/rule_gen.txt`) is loaded from disk, never
hardcoded inline, and is identical regardless of which provider renders it. Key elements
the prompt must include:
- Traffic summary (src IP, dst IP, ports, protocol, anomaly score, anomaly type)
- Target firewall syntax (iptables or pf)
- Required output JSON schema
- Instructions to minimize false positives
- MITRE ATT&CK technique classification requirement
- Instruction to prefer rate-limiting over outright blocking when uncertain

Note: the JSON schema block in the prompt file uses doubled braces (`{{ }}`) since the
file is rendered with `str.format()` — see ADR-018.

---

## Sandbox design

Implemented in `sandbox/` (Dockerfile, tester.py, fp_scorer.py, promoter.py):

```
sandbox/Dockerfile    — Ubuntu image with iptables + tcpreplay + iproute2 pre-installed
sandbox/tester.py     — orchestrates: fetch traffic, replay per flow, collect results
sandbox/fp_scorer.py  — FP rate = blocked non-anomalous packets / total non-anomalous packets
sandbox/promoter.py   — PostgreSQL: PENDING -> SANDBOX_TESTING -> APPROVED_PENDING or REJECTED
```

The sandbox container runs with `--network none` (no access to the real network) and
`--cap-add=NET_ADMIN --cap-add=NET_RAW`. Each traffic flow from ClickHouse's
`traffic_events` is replayed **independently** against the loaded candidate rule:

1. Reconstruct that flow's packets with scapy (traffic_events stores flow summaries,
   not raw captures — see ADR-021), capped at 50 packets / 2 seconds per flow so total
   runtime stays bounded.
2. Alias the flow's destination IP as a `/32` onto a **veth pair's peer interface**
   (`veth-in`), then `tcpreplay` injects onto the other end (`veth-out`).
3. Zero the INPUT chain counters, replay, then read `iptables -L INPUT -v -n -x` for
   any DROP/REJECT rule with a nonzero packet count → that flow was blocked.

The veth pair (not `lo`, not a `dummy` interface) is required — see ADR-020 for why
both alternatives silently fail to reach netfilter at all. Destination MAC must be
broadcast (`ff:ff:ff:ff:ff:ff`) or the receiving interface drops the frame at L2.

A candidate rule that fails to even load into iptables (invalid syntax) is a rejected
verdict, same as a rule that blocks too much legitimate traffic — not an infrastructure
failure. See ADR-023.

FP scorer measures:
```
FP rate = packets blocked by rule that are NOT anomalous / total non-anomalous packets
```
"Anomalous" is decided by each flow's stored `anomaly_score` exceeding 0.5 (matching
`ml/anomaly.py`'s `detect_anomalies()` default threshold).

Threshold: FP rate > 5% → reject rule.
Configurable via SANDBOX_FP_THRESHOLD env var.

---

## MVP vs future releases

| Feature | MVP (HITL) | Future (autonomous) |
|---|---|---|
| Rule generation | AI generates, human approves | AI generates, auto-promotes if FP < threshold |
| Sandbox | Docker + tcpreplay | Extended simulation with adversarial traffic |
| Anomaly detection | Isolation Forest | Ensemble: IF + LSTM autoencoder |
| Rule syntax | iptables / pf only | Cisco ASA, Palo Alto, Fortinet |
| Deployment | Single network | Multi-tenant, per-customer isolation |