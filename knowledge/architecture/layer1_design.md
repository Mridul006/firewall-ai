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

**No continuous ingestion pipeline runs yet** (Zeek/Suricata → Kafka → ClickHouse is
built but not deployed as a long-running service — Celery + Redis async jobs is next in
the build order, not this). Every row in `traffic_events` so far has come from manual or
scripted seeding. For demo purposes, use `scripts/seed_demo_data.py` — it inserts
realistic traffic with current timestamps in one command, so the dashboard's default
60-minute view shows data immediately without asking for help each time. See
`scripts/README.md` and ADR-041.

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

**Timezone convention (see ADR-034 in decisions.md): `timestamp` is always UTC.** ClickHouse's
`DateTime` column carries no timezone metadata, and `clickhouse-driver` returns it as a
**naive** Python `datetime` — every writer must put a genuine UTC instant in it
(`datetime.now(timezone.utc)` / `datetime.fromtimestamp(ts, tz=timezone.utc)`), and every
reader that hands it to an API response or WebSocket message must call
`backend/core/clickhouse.py`'s `to_aware_utc()` first, or the value silently loses its
timezone tag in JSON and gets misinterpreted as local time by the browser. Local-time
conversion happens in exactly one place: the browser, at final display
(`TrafficChart.jsx`'s `toLocaleTimeString()`). No service in between ever converts to or
reasons about a local timezone.

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
GET    /api/v1/traffic/            — recent traffic events with anomaly scores (?minutes=, default 60)
GET    /api/v1/traffic/anomalies   — only events with anomaly_score > ANOMALY_ALERT_THRESHOLD
GET    /api/v1/dashboard/stats     — summary stats for dashboard (rule counts + real ClickHouse 24h counts)
WS     /api/v1/ws/alerts           — real-time alerts: rule status changes + high-severity anomalies
```

`GET /api/v1/traffic/` and `/anomalies` are backed by real ClickHouse queries
(`backend/core/clickhouse.py` + `routes/traffic.py`), run via `run_in_threadpool` since
`clickhouse-driver` has no async client (ADR-029). `/api/v1/dashboard/stats` now also
queries ClickHouse for `traffic_events_24h`/`anomalies_24h` instead of hardcoded zeros.
Every timestamp these return is passed through `to_aware_utc()` before serialization —
see the timezone convention note under `traffic_events`'s schema above and ADR-034.

`WS /api/v1/ws/alerts` (`backend/routes/websocket.py`) is unauthenticated (ADR-032) and
broadcasts two alert types to every connected client:
- `{"type": "rule_status_change", "message": "Rule <id> is now <STATUS>", ...}` — for any
  `candidate_rules` status transition, especially APPROVED_PENDING and LIVE
- `{"type": "anomaly", "message": "High-severity anomaly from <src> to <dst> (score X)", ...}`
  — for new `traffic_events` rows above `ANOMALY_ALERT_THRESHOLD`

Both are detected by a background task polling Postgres and ClickHouse every 3 seconds
(ADR-031) — not a push mechanism — because the processes that actually cause these
changes (`sandbox/promoter.py`, the ML/ingestion pipeline) run as separate OS processes
with no in-memory link to this FastAPI process's WebSocket connections.

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

Implemented in `sandbox/` (Dockerfile, tester.py, fp_scorer.py, promoter.py). Three testing
modes, auto-selected — **never a manual toggle** — by `tester.py`'s `_detect_chain()`,
which inspects the candidate rule's `command` for `-A/-I/-D/-R FORWARD` or `-A/-I/-D/-R
OUTPUT` (checked in that order), falling back to host/`INPUT` mode for everything else:

```
sandbox/Dockerfile    — Ubuntu image with iptables + tcpreplay + iproute2 pre-installed
                        (shared by all three modes — no changes needed for router or
                        output mode)
sandbox/tester.py     — orchestrates: detect chain, dispatch to host, router, or output
                        mode, fetch traffic, replay per flow, collect results
sandbox/fp_scorer.py  — FP rate = blocked non-anomalous packets / total non-anomalous
                        packets (mode-agnostic — reads only FlowResult, unchanged)
sandbox/promoter.py   — PostgreSQL: PENDING -> SANDBOX_TESTING -> APPROVED_PENDING or REJECTED
```

### Host mode (INPUT chain) — the original design, unchanged

A single isolated container runs with `--network none` (no access to the real network)
and `--cap-add=NET_ADMIN --cap-add=NET_RAW`. Each traffic flow from ClickHouse's
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

Host mode only ever meaningfully validates `INPUT`-chain rules — aliasing the
destination IP onto the container's own interface makes the kernel treat traffic as
locally delivered, so `FORWARD` is never evaluated no matter which chain's counters get
checked (see ADR-038, the gap this originally exposed).

### Router mode (FORWARD chain) — added for rules that route traffic through the box

Three containers — **attacker**, **firewall** (multi-homed; the candidate rule loads
here, on its `FORWARD` chain), **target** — connected via two real Docker bridge
networks, so traffic genuinely routes attacker → firewall → target and `FORWARD` gets
evaluated for real:

1. `firewall` connects to both networks (`eth0` toward attacker, `eth1` toward target);
   `ip_forward` is already `1` under Docker Desktop's networking backend.
2. Per flow: `firewall` gets an explicit `ip route replace <dst_ip>/32 via <target's
   real IP>` (idempotent, same pattern as host mode's `ip addr replace`); packets are
   built with the same scapy helper as host mode, but addressed (L2) to the
   **firewall's real MAC** rather than broadcast — broadcast is silently dropped
   somewhere in Docker's bridge delivery path here, the opposite of host mode's veth
   pair, where broadcast is required.
3. `tcpreplay` injects from `attacker`'s `eth0`; zero + read `firewall`'s `FORWARD`
   chain counters, same DROP/REJECT-with-nonzero-packets check as host mode
   (`_any_drop_matched`, reused unchanged).

Isolation from the real network (equivalent to host mode's `--network none`) is
enforced by **deleting each container's default route** after it starts, not by
`internal=True` networks — Docker Desktop's networking backend was found to silently
block inter-container `FORWARD` traffic through a multi-homed container on internal
networks. See ADR-039 for the full empirical trail (what was tried, what didn't work,
and why) and ADR-020 for host mode's own equivalent discovery process.

### Output mode (OUTPUT chain) — traffic leaving the firewall/host itself

Reuses host mode's exact container/veth setup **unchanged** (`_start_container`,
`_load_rule`, `_any_drop_matched`) — no new topology, unlike router mode. `OUTPUT`
fires for any packet the container's own kernel constructs, including one addressed to
an IP aliased onto its own interface, confirmed empirically: a real connection attempt
to a locally-aliased address traverses `OUTPUT` before the kernel short-circuits it to
local delivery.

What differs from host mode is purely how traffic is generated: `tcpreplay`'s injected
frames are inbound by construction and can only ever hit `INPUT` or `FORWARD` — never
`OUTPUT`, since `OUTPUT` only fires for locally-originated packets. Genuine egress
traffic instead comes from real socket connections made from inside the container:

1. Alias the flow's `dst_ip` onto the container's interface (`ip addr replace`, same
   idempotent pattern host mode already uses).
2. **Pin the flow's `src_ip` as the actual source address of the generated traffic** —
   `ip addr replace <src_ip>/32 dev veth-out` plus an explicit
   `ip route replace local <dst_ip> dev veth-in src <src_ip> table local`. Both are
   required: aliasing dst_ip alone makes the kernel's auto-generated `local`-table route
   pick the *destination* address as the source, and a normal `main`-table route with
   `src` set has no effect since `local` takes priority. Without this, any rule with a
   `-s <this-host-ip>` clause — a completely natural thing for an LLM to write — silently
   never matched, and blocked 0 anomalous packets while still reporting a passing 0.0
   fp_rate. Found via a real production-pipeline run, fixed and re-verified with the same
   rule. See ADR-042.
3. Zero the `OUTPUT` chain counters.
4. Run a shell loop attempting `count` real connections via bash's `/dev/tcp` (TCP) or
   `/dev/udp` (UDP) — each individual attempt wrapped in `timeout 2s`. This is required,
   not cosmetic: a `DROP`ped SYN produces no RST, so an unbounded connect() blocks on the
   kernel's own SYN-retry timeout — this hung an early test run for 27+ minutes on a
   single flow before the per-attempt timeout was added. See ADR-040.
5. Read `OUTPUT`'s counters back — same DROP/REJECT-with-nonzero-packets check as the
   other two modes (`_any_drop_matched`, reused unchanged).

**Known limitation, not hidden**: ICMP flows have no real egress-generation mechanism
here — there's no `ping`-equivalent tool in the sandbox image, and `--network none`
blocks installing one. `_build_egress_script()` raises for any protocol other than
TCP/UDP; the replay loop skips that flow (same convention as any other skippable-flow
error) and logs a warning. An `OUTPUT` rule's behavior against ICMP traffic is therefore
never validated by the sandbox — the `fp_rate` verdict is silently computed over
TCP/UDP flows only.

A candidate rule that fails to even load into iptables (invalid syntax) is a rejected
verdict in all three modes, same as a rule that blocks too much legitimate traffic — not
an infrastructure failure. See ADR-023.

FP scorer measures **two** independent metrics (identically across all three modes) — a
rule must clear both to pass:
```
FP rate        = packets blocked by rule that are NOT anomalous / total non-anomalous packets
Detection rate = anomalous packets the rule actually blocked / total anomalous packets
```
"Anomalous" is decided by each flow's stored `anomaly_score` exceeding 0.5 (matching
`ml/anomaly.py`'s `detect_anomalies()` default threshold). For router and output mode
this is exactly "what percentage of legitimate traffic would have been wrongly
blocked" — the same formula applies unchanged since it only reads `FlowResult.blocked`,
agnostic to which chain produced that boolean.

Detection rate exists because FP rate alone can't catch a rule that matches nothing at
all — ADR-042 found exactly this happen for real (a rule reached `APPROVED_PENDING`
with a perfect 0.0 fp_rate while blocking 0% of its target traffic). See ADR-043.

Thresholds:
- FP rate > 5% → reject. Configurable via `SANDBOX_FP_THRESHOLD`.
- Detection rate < 10% → reject. Configurable via `SANDBOX_DETECTION_THRESHOLD`. Kept
  deliberately low — real `-m recent` rate-limiting rules this project has generated
  intentionally block well under 100% (37.5% observed) by design, and must not be
  rejected for that.
- If there's no anomalous traffic in the replay window at all (it aged out before the
  test ran), `detection_rate` is `None` and this check is skipped rather than
  auto-rejecting an untestable rule — mirrors FP rate's own zero-denominator handling.

`sandbox_result["mode"]` (`"host"`, `"router"`, or `"output"`) is recorded for every
test, so a rule's stored history always shows which mode validated it.

`sandbox_result["mode"]` (`"host"`, `"router"`, or `"output"`) is recorded for every
test, so a rule's stored history always shows which mode validated it.

---

## Frontend dashboard

Implemented in `frontend/` (React + Vite + Tailwind v4 + Recharts + react-router-dom):

```
src/api.js                      — central axios client; JWT interceptor, 401 -> logout
src/hooks/useAuth.js            — AuthContext/AuthProvider, login/logout, current user
src/hooks/useRules.js           — fetch + filter rules by status, approve/reject actions
src/hooks/useTraffic.js         — fetch traffic events / anomalies
src/hooks/useDashboardStats.js  — fetch dashboard stats (added — see ADR-024)
src/hooks/useWebSocket.js       — manage the alert WebSocket connection (added — ADR-024)
src/components/                 — RuleCard, RuleList, TrafficChart, AlertBanner, StatCards
src/pages/                      — Login, Dashboard, Rules, Traffic
```

This is a human-in-the-loop review UI for a security analyst: the Rules page has
PENDING/APPROVED_PENDING/LIVE/REJECTED tabs, and Approve/Reject buttons on a RuleCard
only render when `status === 'APPROVED_PENDING'` — matching the HITL hard rule (AI
suggests, human approves) exactly.

The JWT lives in `localStorage` (see ADR-025) since this is a standalone Vite app, not
a sandboxed artifact. Protected routes redirect to `/login` when unauthenticated.
`<AlertBanner />` renders in the persistent `Layout` (not inside `Dashboard`) so its
WebSocket connection survives navigation between pages — see ADR-033.

Verified end-to-end with a real backend and real Postgres/ClickHouse data (not just
`npm run build` succeeding): logged in, saw real stat-card numbers, the Traffic page
rendering a real chart, `AlertBanner` showing "connected," clicked a real Approve
button, confirmed the rule moved from APPROVED_PENDING to LIVE in Postgres, and watched
the resulting WebSocket alert appear live in the banner regardless of which page was
open at the time. The traffic/WebSocket gaps flagged in the previous version of this doc
are closed — see the API endpoints section above and ADR-029 through ADR-033.

---

## MVP vs future releases

| Feature | MVP (HITL) | Future (autonomous) |
|---|---|---|
| Rule generation | AI generates, human approves | AI generates, auto-promotes if FP < threshold |
| Sandbox | Docker + tcpreplay | Extended simulation with adversarial traffic |
| Anomaly detection | Isolation Forest | Ensemble: IF + LSTM autoencoder |
| Rule syntax | iptables / pf only | Cisco ASA, Palo Alto, Fortinet |
| Deployment | Single network | Multi-tenant, per-customer isolation |