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

---

## ADR-011 — psycopg (v3, async) over asyncpg for the Postgres driver
**Decision:** Use `psycopg[binary]` (v3) with SQLAlchemy's `postgresql+psycopg` async dialect instead of `asyncpg`.
**Reason:** `asyncpg` ships no prebuilt Windows wheel for Python 3.14 yet, and the dev machine has no MSVC Build Tools to compile it from source. `psycopg[binary]` has a cp314 Windows wheel and SQLAlchemy 2.0 supports it as a first-class async driver.
**Revisit when:** asyncpg publishes a Python 3.14 Windows wheel, or dev moves to Linux/WSL with build tools available.

---

## ADR-012 — Manual SelectorEventLoop wiring for uvicorn on Windows
**Decision:** `backend/main.py` runs via `python main.py`, driving `uvicorn.Server.serve()` through `asyncio.run(server.serve(), loop_factory=asyncio.SelectorEventLoop)` instead of the `uvicorn` CLI or `uvicorn.run()`.
**Reason:** uvicorn hardcodes `ProactorEventLoop` on Windows regardless of event loop policy, which psycopg's async mode cannot use (raises `InterfaceError`). uvicorn passes an explicit `loop_factory` into `asyncio.run()`, which bypasses `asyncio.set_event_loop_policy()` entirely — that fix doesn't work here.
**Revisit when:** uvicorn exposes a way to override its Windows loop_factory default, or dev/deploy moves off Windows.

---

## ADR-013 — bcrypt directly instead of passlib
**Decision:** Hash passwords with the `bcrypt` package directly (`bcrypt.hashpw` / `bcrypt.checkpw`), not `passlib.CryptContext`.
**Reason:** `passlib` is unmaintained since 2020; its bcrypt backend self-test crashes under `bcrypt>=4.1`, which removed the silent-truncation behavior passlib's wrap-bug detector depends on (`ValueError: password cannot be longer than 72 bytes`). Calling `bcrypt` directly avoids the dependency and the bug.
**Revisit when:** Never expected — bcrypt is actively maintained.

---

## ADR-014 — clickhouse-driver (native protocol, port 9000) over HTTP (port 8123)
**Decision:** `ingestion/clickhouse.py` uses `clickhouse-driver`, which speaks ClickHouse's native protocol on port 9000, not the HTTP interface on port 8123.
**Reason:** `clickhouse-driver` only supports the native protocol — pointing it at 8123 fails outright. Port 8123 is the more commonly known "ClickHouse port," so it's an easy mismatch to reintroduce; both ports are exposed in docker-compose for whichever client library a future service needs.
**Revisit when:** A future service needs HTTP access (e.g. browser-based queries) — add `clickhouse-connect` alongside this, don't replace it.

---

## ADR-015 — Named volumes required for Postgres and ClickHouse (amends ADR-008)
**Decision:** `infra/docker-compose.yml` mounts named volumes (`postgres_data`, `clickhouse_data`) for both stateful services.
**Reason:** Without a named volume, container data lives in the writable layer and is lost on `docker compose down` or container recreation — discovered when a stale Postgres container (created before the compose file's current credentials existed) caused an auth mismatch after a plain restart. Named volumes make data survive container recreation, per the coding_rules requirement.
**Revisit when:** Never for dev — production uses managed volumes/services per ADR-008.

---

## ADR-016 — Native PostgreSQL Windows service must stay stopped
**Decision:** Any native PostgreSQL Windows service (found: `postgresql-x64-18`) must be stopped/disabled on dev machines; only the Docker container may bind port 5432.
**Reason:** A native service silently intercepted TCP connections meant for the Docker Postgres container, causing password-authentication failures with no useful signal (connecting into the container directly worked fine — the failing connection was never reaching it). Directly violates the "all infrastructure via Docker" hard rule.
**Revisit when:** Never — stop and flag any native DB service found on a dev machine going forward.

---

## ADR-017 — Swappable LLM provider interface, Ollama as the default
**Decision:** Rule generation goes through an `LLMProvider` abstract interface (`generate(prompt: str) -> str`) with interchangeable backends — Ollama, Claude, OpenAI — selected at runtime by the `LLM_PROVIDER` env var via `ml/providers/factory.py`. `rule_gen.py` never imports a specific provider; it only calls the factory. Ollama (model `llama3.1`) is the default.
**Reason:** A solo founder building an MVP shouldn't have paid-API cost or vendor risk on the critical path just to run and demo the product — Ollama is free, runs fully local/on-prem, and needs no API key, which also matters for security-conscious buyers who don't want raw traffic summaries leaving their network to a third-party LLM API. Making the interface swappable means Claude or OpenAI (generally higher quality, worth it for paying customers or harder cases) can be enabled per-deployment with one env var, with no code changes and no risk of `rule_gen.py` accidentally coupling to one vendor's SDK or error types.
**Revisit when:** A design partner needs higher rule-generation quality than local models provide, or an enterprise deployment specifically requires (or specifically forbids) sending data to a hosted LLM API.

---

## ADR-018 — Prompt template braces must be escaped for str.format()
**Decision:** The literal JSON schema block in `knowledge/prompts/rule_gen.txt` uses doubled braces (`{{ }}`) around the example object, while the actual substitution placeholders (`{traffic_summary}`, `{anomaly_score}`, etc.) stay single-braced.
**Reason:** `rule_gen.py` loads this file and renders it with `str.format()`, per the coding_rules convention for prompt templates. `str.format()` treats every `{...}` as a substitution field, so the unescaped example JSON in the prompt raised `KeyError` on the first real run. Discovered by actually executing the rule generation flow against a local Ollama model, not just by reading the code.
**Revisit when:** If the templating mechanism ever changes away from `str.format()` (e.g. to Jinja2), remove the brace-doubling — it's specific to this substitution method.