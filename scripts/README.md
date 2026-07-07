# scripts/

Standalone operational scripts. Not part of any service — run manually.

## seed_demo_data.py

Seeds ClickHouse's `traffic_events` table with fresh, realistic traffic
using **current timestamps**, so the dashboard's default 60-minute view
shows data immediately.

**Why this exists:** the dashboard queries `GET /api/v1/traffic/` with a
default 60-minute lookback window. Without a live Zeek/Kafka ingestion
pipeline running continuously (not yet built — see CLAUDE.md's build
order), `traffic_events` only gets written to when something explicitly
seeds it. Once that data ages past 60 minutes, the dashboard's traffic
chart and anomaly feed silently go empty. This script is the one-command
fix — run it before any demo, no need to ask for help each time.

### Usage

From the repo root, using the `ingestion` venv (it already has the
ClickHouse driver installed):

```
# Windows
.\ingestion\venv\Scripts\python.exe scripts\seed_demo_data.py

# macOS/Linux
./ingestion/venv/bin/python scripts/seed_demo_data.py
```

Optional flags:

```
--normal-count N     Number of normal traffic rows to insert (default: 120)
--minutes-back N     Spread normal traffic over the last N minutes (default: 50)
```

### What it inserts

- **Normal traffic**: HTTPS/HTTP/DNS-shaped flows from 3 internal hosts
  (`10.0.0.5`, `10.0.0.7`, `10.0.0.9`) to a handful of external services,
  low `anomaly_score` (0.0–0.25), spread across the last ~50 minutes.
- **Anomaly 1 — port scan**: `198.51.100.66` probing 8 ports on
  `10.0.0.9` in the last 3 minutes, `anomaly_score` 0.85–0.95.
- **Anomaly 2 — exfiltration/beaconing**: `10.0.0.9` sending large bursts
  to a suspicious external IP (`203.0.113.99:4444`) in the last 2 minutes,
  `anomaly_score` 0.9–0.98.

Safe to re-run any time — every run just inserts new rows with current
timestamps. Older rows fall out of the dashboard's default 60-minute view
on their own and out of ClickHouse entirely after the table's 30-day TTL.
It does not touch PostgreSQL, generate rules, or run the sandbox — traffic
seeding only.

See `knowledge/architecture/decisions.md` (ADR-041) for the full context
on why this recurring issue kept coming up and why a script (not a fix to
the ingestion pipeline) was the right call for now.
