# CLAUDE.md

## Project
Firewall AI — an autonomous cybersecurity platform with 5 defense layers that actively mutates and adapts its defenses in real time. Built as a SaaS product by a solo founder (B.Tech student, graduating 2027) with an ML/AI background. Not yet patented — filing is a planned future step.

## Current focus
Building Layer 1 MVP — AI-driven sandboxed firewall rule generation engine.
Backend skeleton, data ingestion pipeline, ML core, sandbox testing, and the frontend
dashboard are built. The two backend gaps this left (traffic endpoints were stubs, no
WebSocket route existed) are now closed — Layer 1 is functional end-to-end. The sandbox
now has three testing modes, auto-dispatched by chain: host mode (INPUT), router mode
(FORWARD), and output mode (OUTPUT, for traffic leaving the firewall/host itself, e.g.
blocking exfiltration/C2 beaconing) — each verified to genuinely block bad traffic and
pass legitimate traffic, not just load without error. Output mode has one known gap:
ICMP flows can't be tested (no ping-equivalent tool available under `--network none`).
Next up is Celery + Redis async jobs.

## Repo structure
```
firewall-ai/
├── .ai/                  ← AI instructions (you are here)
├── backend/              ← FastAPI REST API
├── ml/                   ← Isolation Forest + swappable LLM rule gen (Ollama default)
├── sandbox/              ← Docker sandbox + tcpreplay + FP scorer
├── ingestion/            ← Zeek + Kafka + ClickHouse pipeline
├── frontend/             ← React + Vite + Tailwind dashboard
├── infra/                ← docker-compose for all infrastructure
├── knowledge/            ← Research, architecture decisions, playbooks
├── docs/                 ← Full specs (read PROJECT.md for deep context)
└── .env                  ← Never commit this
```

## Tech stack (Layer 1)
- Traffic capture: Zeek / Suricata
- Stream broker: Kafka
- Time-series store: ClickHouse
- Anomaly detection: Isolation Forest (scikit-learn)
- Rule generation: swappable LLM provider (LLM_PROVIDER env var) — Ollama/llama3.1 default (local, free, on-prem capable), Claude (claude-sonnet-4-6) and OpenAI (gpt-4o) available
- Rule syntax: iptables / pf format
- Sandbox: Docker + tcpreplay
- Backend: FastAPI + PostgreSQL + Celery + Redis
- Frontend: React + Vite (rolldown) + Tailwind v4 + Recharts + react-router-dom + WebSocket

## Build order
1. Dev environment ← done
2. FastAPI backend skeleton ← done
3. Data ingestion (Zeek → Kafka → ClickHouse) ← done
4. ML core (Isolation Forest + swappable LLM rule gen) ← done
5. Sandbox testing (Docker + tcpreplay + FP scorer, incl. firewall syntax validation) ← done
6. Frontend dashboard (React + WebSocket alerts) ← done, incl. backend
   /api/v1/traffic/* (real ClickHouse queries) and WS /api/v1/ws/alerts
7. Celery + Redis async jobs ← current

## Hard rules (never break these)
- No untested rule ever reaches the live firewall
- Human-in-the-loop mode first — AI suggests, human approves
- All secrets from .env only — never hardcode
- All infrastructure via Docker — never install services natively
- Read coding_rules.md before writing any code
- Read docs/PROJECT.md for full architecture context

## Key reference files
- .ai/coding_rules.md — all coding conventions
- docs/PROJECT.md — full 5-layer architecture + patent context
- knowledge/architecture/ — every design decision made so far
- infra/docker-compose.yml — all infrastructure definitions