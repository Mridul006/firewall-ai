# Architecture Decisions

Every major design decision made in this project, with reasoning.
Update this file whenever a significant decision is made.

---

## ADR-001 — Monorepo over polyrepo
**Decision:** Single repository with clear folder boundaries per component.
**Reason:** Solo founder with few hours/week. One git clone, one CI pipeline, easy code sharing between layers. Split into separate repos when a team member owns a specific layer.
**Revisit when:** First engineer joins and owns a specific service.

---

## ADR-002 — Layer 1 built before Layer 2 (MTD)
**Decision:** AI firewall rule generation is the MVP, not Moving Target Defense.
**Reason:** Layer 1 solves a felt pain (manual firewall rule writing) that a CISO can immediately understand and budget for. MTD is the stronger IP but harder to demo and sell without an existing product relationship. Layer 1 gets us in the door.
**Revisit when:** First paying pilots are signed.

---

## ADR-003 — Human-in-the-loop mode for MVP
**Decision:** AI suggests firewall rules, human approves via dashboard. Full automation is a later release.
**Reason:** Enterprise buyers are risk-averse. No CISO will let an AI autonomously modify production firewall rules on day one. Trust is built incrementally. HITL mode removes the blocker to initial adoption.
**Revisit when:** Design partners have used the product for 60+ days with zero false promotions.

---

## ADR-004 — FastAPI over Django or Flask
**Decision:** FastAPI for the backend API.
**Reason:** Native async support, automatic OpenAPI docs, Pydantic integration, fastest Python web framework for IO-bound workloads. Django is too heavy. Flask lacks native async.
**Revisit when:** Never — FastAPI scales to production without replacement.

---

## ADR-005 — ClickHouse for traffic storage
**Decision:** ClickHouse as the time-series store for network traffic logs.
**Reason:** Columnar storage makes time-range queries on traffic data 10-100x faster than PostgreSQL. Handles millions of rows per second insert throughput. Essential for real-time anomaly detection on high-volume traffic.
**Revisit when:** If traffic volume is low enough that PostgreSQL suffices in early pilots (reconsider at design partner stage).

---

## ADR-006 — Isolation Forest for anomaly detection
**Decision:** Isolation Forest (scikit-learn) as the primary anomaly detection model.
**Reason:** Unsupervised — no labeled attack data needed to start. Fast inference. Interpretable anomaly scores. Well-understood behavior. Can be replaced with a deep learning model later once labeled data exists from real deployments.
**Revisit when:** After 3+ months of real deployment data — consider LSTM autoencoder or transformer-based detector.

---

## ADR-007 — Claude API for rule generation (not fine-tuned model)
**Decision:** Use Claude API (claude-sonnet-4-6) directly with prompt engineering for firewall rule generation. No fine-tuning.
**Reason:** Fine-tuning requires labeled training data (input traffic → correct rule pairs) which we don't have yet. Prompt engineering with Claude gives good results immediately. Fine-tuning becomes viable after collecting rule approval/rejection data from real usage.
**Revisit when:** After 500+ human-approved rule examples are collected from design partners.

---

## ADR-008 — Docker for all infrastructure, never native install
**Decision:** Kafka, PostgreSQL, Redis, ClickHouse all run via docker-compose. Never installed natively.
**Reason:** Reproducible environment across machines. Easy onboarding for future team members (one command: docker compose up). No "works on my machine" issues. Clean teardown and reset.
**Revisit when:** Production deployment — use managed cloud services (RDS, ElastiCache, MSK) instead of self-hosted Docker.

---

## ADR-009 — No LangChain or agent frameworks
**Decision:** Call Claude API directly. No LangChain, LlamaIndex, AutoGen, or CrewAI.
**Reason:** Adding a framework layer between our code and the Claude API adds hidden complexity, makes debugging harder, and creates dependency on a fast-moving third-party library. Direct API calls are transparent, debuggable, and fully controlled.
**Revisit when:** Never for the core product. Evaluate for internal tooling only.

---

## ADR-010 — PostgreSQL for rule and audit storage
**Decision:** PostgreSQL for rules, audit logs, user data, and metadata.
**Reason:** Relational structure suits rule management well (rules have states, history, approvers, timestamps). ACID compliance essential for audit trails. ClickHouse handles traffic volume; PostgreSQL handles structured business data.
**Revisit when:** Never — PostgreSQL scales to our needs for years.