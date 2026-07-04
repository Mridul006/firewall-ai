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

---

## ADR-019 — candidate_rules.id is generated app-side, not a DB default
**Decision:** `sandbox/promoter.py` generates `id = uuid.uuid4()` in Python and passes it explicitly on INSERT, rather than relying on a database default.
**Reason:** `layer1_design.md`'s schema sketch shows `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`, but `backend/models/rule.py`'s SQLAlchemy column only ever set a Python-side `default=uuid.uuid4` — never a `server_default`. The live table (created via SQLAlchemy's `create_all`) genuinely has no DB-level default, confirmed via `\d candidate_rules`. Matching that in `promoter.py` avoids a NOT NULL violation on insert; the design doc has been corrected to describe reality instead of the original intent.
**Revisit when:** If a real Alembic migration is introduced (build order still has no migration tooling) — add a proper `server_default=text("gen_random_uuid()")` then, and this app-side workaround can be dropped.

---

## ADR-020 — veth pair (not lo, not dummy) for tcpreplay packet injection
**Decision:** The sandbox container creates its own veth pair (`veth-out`/`veth-in`) inside its own network namespace. `tcpreplay` injects onto `veth-out`; the candidate flow's destination IP is aliased as a `/32` onto `veth-in` so the kernel treats replayed packets as locally destined, which is what actually makes them traverse the iptables INPUT chain.
**Reason:** Empirically tested three approaches before finding one that works. `lo` (the obvious first choice, and what an earlier draft of this design assumed): tcpreplay warns "Unsupported physical layer type 0x0304 on lo" and packets never reached netfilter (0 iptables hits) despite tcpreplay reporting successful sends — a documented tcpreplay/loopback limitation. `dummy0`: packets sent to a dummy interface are transmitted-and-discarded by design (that's what a dummy interface is for) — they never loop back to the receive path, so iptables INPUT never saw them either. A veth pair is a genuine point-to-point link — whatever exits one end is received on the other — which is exactly what let a real DROP rule's packet counter increment. A broadcast destination MAC (`ff:ff:ff:ff:ff:ff`) is also required, or the peer interface silently drops frames not addressed to its own MAC. Confirmed via a live smoke test with real containers before touching tester.py's production code.
**Revisit when:** Never expected for the MVP's single-flow replay model — this is a standard, well-established technique for isolated firewall-rule testing.

---

## ADR-021 — Synthetic per-flow pcaps (scapy), not raw packet capture
**Decision:** `sandbox/tester.py` reconstructs Ethernet-framed packets from each `traffic_events` row's flow summary (src/dst IP and port, protocol, byte/packet counts, duration) using `scapy`, rather than replaying an original packet capture.
**Reason:** `traffic_events` stores Zeek conn-log-derived flow summaries (bytes, packets, duration), not raw packets — the ingestion pipeline (ADR from the ingestion build) never stored pcap data, so there is no original capture to replay. Packet count is capped at 50 and total replay duration at 2 seconds per flow to bound sandbox runtime; packets are evenly spaced across that window so simple single-flow rate-limit rules (`-m limit`) are still meaningfully exercised, even though cross-flow timing/interleaving isn't reproduced.
**Revisit when:** If ingestion starts storing genuine pcap captures (not just Zeek logs) — replay those directly instead of reconstructing. Also see layer1_design.md's MVP-vs-future table: "extended simulation with adversarial traffic" is already flagged as future work, consistent with this being an MVP-scoped approximation.

---

## ADR-022 — mitre_technique widened from VARCHAR(20) to VARCHAR(64)
**Decision:** `candidate_rules.mitre_technique` is `VARCHAR(64)`, both in the live table (via `ALTER TABLE`) and in `backend/models/rule.py`.
**Reason:** `knowledge/prompts/rule_gen.txt` instructs the LLM to return the full "T-number and name" (e.g. `"T1046 Network Service Discovery"`, 32 characters) — but the schema only allowed 20, so the very first real end-to-end insert failed with `StringDataRightTruncation`. Widening preserves the analyst-facing technique name (firewall_rules.md's validation checklist requires rules be "Tagged" with the MITRE ID) rather than truncating it or changing the prompt to ask for a bare code.
**Revisit when:** Never expected — 64 chars comfortably fits any current MITRE ATT&CK technique name.

---

## ADR-023 — Invalid rule syntax is a REJECTED verdict, not a sandbox infra failure
**Decision:** `sandbox/tester.py` distinguishes `InvalidRuleError` (the candidate rule itself doesn't load into iptables) from `SandboxTestError` (the sandbox's own container/image/veth setup failed). The former results in a clean `REJECTED` status with the parse error as the reason; the latter propagates uncaught, leaving the rule stuck in `SANDBOX_TESTING` for an operator to investigate.
**Reason:** Discovered via a real end-to-end run: a locally-generated (mistral/Ollama) candidate rule used `--dport 20-24` (hyphen), which is invalid iptables syntax — iptables port ranges require a colon (`20:24`). This is exactly the "syntax valid — rule parses without error" item on firewall_rules.md's validation checklist, and a rule failing that check must be rejected like any other failed test, not conflated with an environment problem. The original design treated all sandbox exceptions the same way, which would have left a badly-generated rule stuck in limbo indefinitely instead of cleanly rejected.
**Revisit when:** Never expected — this distinction (rule-content failure vs. infra failure) is the correct permanent model.