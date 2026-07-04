# CLAUDE.md

## Project
Firewall AI — an autonomous cybersecurity platform with 5 defense layers that actively mutates and adapts its defenses in real time. Built as a SaaS product by a solo founder (B.Tech student, graduating 2027) with an ML/AI background. Provisional patent V2 filed.

## Current focus
Building Layer 1 MVP — AI-driven sandboxed firewall rule generation engine.
Backend skeleton, data ingestion pipeline, ML core, and sandbox testing are built;
next up is the frontend dashboard.

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
- Frontend: React + Vite + Tailwind + Recharts + WebSocket

## Build order
1. Dev environment ← done
2. FastAPI backend skeleton ← done
3. Data ingestion (Zeek → Kafka → ClickHouse) ← done
4. ML core (Isolation Forest + swappable LLM rule gen) ← done
5. Sandbox testing (Docker + tcpreplay + FP scorer, incl. firewall syntax validation) ← done
6. Frontend dashboard (React + WebSocket alerts) ← current
7. Celery + Redis async jobs

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