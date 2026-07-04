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

---

## ADR-024 — Two extra hooks beyond the requested list: useDashboardStats, useWebSocket
**Decision:** `frontend/src/hooks/` includes `useDashboardStats.js` and `useWebSocket.js` in addition to the three originally specified (`useRules`, `useTraffic`, `useAuth`).
**Reason:** coding_rules.md requires "custom hooks for all data fetching" (unconditional) and separately "WebSocket connection managed in a single useWebSocket hook" (explicit). Dashboard.jsx needs `/api/v1/dashboard/stats` data and AlertBanner.jsx needs the WebSocket alert stream — fetching either inline in a component would violate those rules. Both hooks follow the exact same shape (`{ data, loading, error, refetch }`) as `useRules`/`useTraffic` for consistency.
**Revisit when:** Never expected — this is filling a gap in the original spec against an explicit existing rule, not scope creep.

---

## ADR-025 — JWT in localStorage (not React state/context only)
**Decision:** `frontend/src/api.js` stores the JWT in `localStorage`, read fresh on each request via an axios request interceptor.
**Reason:** The brief allowed either approach depending on runtime: React state/context only for an artifact-style sandboxed environment, or localStorage for a standalone Vite app "running in the browser normally." This is unambiguously the latter — a real `npm create vite` project with its own `package.json`/`vite.config.js`, run via `npm run dev` on port 5173, not an Artifact. Storing the token in React state alone would lose the session on every page refresh, which is poor UX for a dashboard an analyst keeps open. localStorage is vulnerable to XSS-based token theft; a production deployment should prefer an httpOnly cookie set by the backend instead — noted as a comment in `api.js`.
**Revisit when:** Before any real production deployment — swap for httpOnly cookie-based sessions set by the backend.

---

## ADR-026 — createElement instead of JSX in useAuth.js
**Decision:** `AuthProvider` in `useAuth.js` builds its returned element with `React.createElement(AuthContext.Provider, { value }, children)` instead of `<AuthContext.Provider value={value}>{children}</AuthContext.Provider>` JSX syntax.
**Reason:** This project's Vite version (8.x) uses the newer rolldown-based build engine, which — unlike the classic esbuild+Babel `@vitejs/plugin-react` pipeline — refuses to parse JSX syntax in a `.js` file (`npm run build` failed with "Unexpected JSX expression... JSX syntax is disabled"). coding_rules.md's "Hook files: useCamelCase.js" convention means renaming to `.jsx` isn't the right fix; avoiding JSX syntax in the one file that needs a Provider component satisfies both the naming rule and the build. Found by actually running `npm run build`, not by inspecting the toolchain docs.
**Revisit when:** If a future Vite/plugin upgrade parses JSX in `.js` files again, this could be simplified back to JSX — low priority, `createElement` works fine indefinitely.

---

## ADR-027 — Tailwind CSS v4 via `@tailwindcss/vite`
**Decision:** The frontend uses Tailwind v4 with the `@tailwindcss/vite` plugin (a single `@import "tailwindcss";` in `index.css`), not the v3 `tailwind.config.js` + PostCSS setup.
**Reason:** Fewer config files, less surface for PostCSS misconfiguration, and v4 is the current stable major as of this build. coding_rules.md mandates Tailwind for all styling but doesn't pin a version.
**Revisit when:** Never expected unless a future Tailwind v5 changes the recommended Vite integration.

---

## ADR-028 — Frontend has no WebSocket backend to connect to yet
**Decision:** `useWebSocket.js` is written against the documented `/api/v1/ws/alerts` contract (layer1_design.md) and degrades gracefully (shows "disconnected," retries on a 5s timer) rather than crashing when the connection fails.
**Reason:** The FastAPI backend has no WebSocket route implemented anywhere (confirmed via `grep -rn "websocket" backend/` — zero matches) — only the four REST routers (auth, rules, traffic, dashboard) exist. `layer1_design.md` documents the endpoint but it was never built in the backend skeleton phase. This is a pre-existing gap from an earlier build, not something introduced now; building the actual backend WS endpoint is out of scope for the frontend task and is a natural candidate for the Celery/Redis phase (build order step 7) or a dedicated follow-up.
**Revisit when:** When a backend WebSocket endpoint is actually built — verify `useWebSocket.js`'s message shape assumption (`JSON.parse(event.data)`) against whatever the real endpoint emits.
**Status: CLOSED** — see ADR-029 through ADR-033. `/api/v1/ws/alerts` now exists and the message shape (`{type, message, ...}`) matches what `useWebSocket.js` already expected.

---

## ADR-029 — Sync clickhouse-driver in FastAPI via run_in_threadpool, not async
**Decision:** `backend/core/clickhouse.py`, `routes/traffic.py`, `routes/dashboard.py`, and `routes/websocket.py` all wrap their `clickhouse-driver` calls in `starlette.concurrency.run_in_threadpool` rather than calling them directly in an `async def` route.
**Reason:** `clickhouse-driver` has no async client (unlike `psycopg` for Postgres). coding_rules.md's "never block the event loop with synchronous I/O" rule means a raw synchronous call inside an `async def` route would stall every other concurrent request for the query's duration. `run_in_threadpool` is FastAPI/Starlette's standard idiom for this exact situation — same pattern already used for `psycopg`'s sync mode in `sandbox/promoter.py` and `ml/`'s scripts, which don't run inside an event loop at all and so don't need it, but the backend does.
**Revisit when:** If ClickHouse query volume ever becomes high enough that threadpool contention matters — consider `aiochclient` or similar, an async ClickHouse client.

---

## ADR-030 — ANOMALY_ALERT_THRESHOLD is separate from ANOMALY_CONTAMINATION
**Decision:** A new env var `ANOMALY_ALERT_THRESHOLD` (default `0.5`) decides which ClickHouse rows count as "anomalous" for `/api/v1/traffic/anomalies`, the dashboard's `anomalies_24h` count, and the WebSocket anomaly alerts — not `ANOMALY_CONTAMINATION`.
**Reason:** They're different kinds of numbers entirely. `ANOMALY_CONTAMINATION` (`0.01`) is `ml/anomaly.py`'s IsolationForest training hyperparameter — the *expected fraction* of traffic that's anomalous, used to fit the model. `ANOMALY_ALERT_THRESHOLD` is a *score cutoff* (0.0–1.0 scale) applied to the already-computed `anomaly_score` column. Reusing the contamination value as a score threshold would have been a type/unit mismatch that happened to not crash (both are small floats) but would be semantically wrong. `0.5` matches the convention already established by `ml/anomaly.py`'s `detect_anomalies()` default and `sandbox/fp_scorer.py`'s `ANOMALY_SCORE_THRESHOLD`.
**Revisit when:** If per-deployment tuning of the alert threshold becomes a product feature (e.g. an analyst-configurable slider in the dashboard) rather than an env var.

---

## ADR-031 — Cross-process alerts via DB/ClickHouse polling, not pub/sub
**Decision:** `backend/routes/websocket.py`'s `poll_and_broadcast_alerts()` background task polls Postgres (`candidate_rules.updated_at`) and ClickHouse (`traffic_events`) every 3 seconds and broadcasts alerts for anything new, rather than using a push-based mechanism.
**Reason:** The processes that actually change this data — `sandbox/promoter.py` (sets APPROVED_PENDING/REJECTED after a sandbox test) and the ML/ingestion pipeline — run as separate OS processes with no in-memory link to this FastAPI process's WebSocket connections. Options considered: Postgres `LISTEN`/`NOTIFY` (real push, but requires modifying `sandbox/promoter.py` too, and adds async-`LISTEN` complexity); Redis pub/sub (Redis is already provisioned but Celery/Redis integration is explicitly build order phase 7, still future work — "do not build features not in the current build order phase"). Polling every 3s is simple, requires touching only `backend/`, and a few seconds of latency is a non-issue for a human-in-the-loop security dashboard.
**Revisit when:** Build order phase 7 (Celery + Redis) lands — Redis pub/sub would be strictly better (instant, no poll overhead) and should replace this.

---

## ADR-032 — WebSocket alert endpoint is unauthenticated (MVP)
**Decision:** `WS /api/v1/ws/alerts` accepts any connection with no JWT check, unlike every REST route.
**Reason:** Browsers' native `WebSocket` API doesn't support custom headers, so passing a JWT would require either a query-string token (leaks into server logs/proxies) or a cookie-based auth scheme — neither of which the frontend (`useWebSocket.js`, built in the previous session) was written to do. Alert content today is low-sensitivity (rule IDs, statuses, IPs already visible to any authenticated dashboard user). Fixing this properly means touching the already-built frontend's `useWebSocket.js` too, beyond this task's backend-focused scope.
**Revisit when:** Before any real deployment — add query-token or cookie-based WS auth, whichever the eventual session model uses.

---

## ADR-033 — AlertBanner moved from Dashboard-only to the persistent Layout
**Decision:** `<AlertBanner />` now renders in `App.jsx`'s `Layout` (alongside `NavBar`, wrapping every protected page), not inside `Dashboard.jsx` alone.
**Reason:** Found by actually testing the full flow, not by inspecting the code: approving a rule while on the Rules page, then navigating to Dashboard, showed no alert — because `AlertBanner` (and its WebSocket connection) only existed while `Dashboard` was mounted. Navigating away closed the socket; navigating back opened a new one *after* the alert had already been broadcast to the old (by-then-closed) connection, so it was silently missed. There is no message replay/queue for a client that wasn't connected at broadcast time. Moving it to the persistent `Layout` keeps one WebSocket connection alive for the analyst's whole session regardless of which page they're on.
**Revisit when:** Never expected — this is the correct permanent placement for a real-time, session-wide alert stream.

---

## ADR-034 — Timezone convention: store UTC everywhere, convert to local only at display time
**Decision:** Every timestamp is stored and passed between services as UTC — ClickHouse's `traffic_events.timestamp`, Postgres's `TIMESTAMPTZ` columns, every Python `datetime` written by `ingestion/`, `ml/`, `sandbox/`, and `backend/`. The **only** place a timestamp is ever converted to a human's local timezone is the last possible moment: the browser, via `new Date(isoString).toLocaleTimeString()` in `TrafficChart.jsx`. No service in between ever converts to or reasons about a local timezone.
**Reason:** Found via a real user-reported bug, not a hypothetical. The Dashboard's traffic chart showed timestamps roughly 5.5 hours behind the real time in India (IST, UTC+5:30) — e.g. showing ~1:27–2:17 PM when it was actually ~7:58 PM IST. Root-caused layer by layer:
- **ClickHouse (storage):** correct. `SHOW timezone` / `SELECT now()` confirmed the container's session timezone is `UTC`, and every write path (`ingestion/zeek_parser.py`'s `datetime.fromtimestamp(ts, tz=timezone.utc)`, and every seed script's `datetime.now(timezone.utc)`) already wrote genuine UTC instants. Not the bug.
- **Backend (serialization) — this was the actual bug:** `clickhouse-driver` returns **naive** Python `datetime` objects for ClickHouse `DateTime` columns (the column type itself carries no timezone metadata). `backend/routes/traffic.py` passed these naive values straight into the `TrafficEvent` Pydantic model, which serializes a naive datetime to JSON *without* a `Z`/offset suffix (e.g. `"2026-07-04T14:37:49"`, not `"...Z"`). The value was correct UTC; the JSON just never said so.
- **Frontend (display):** also correct, once given correct input. `new Date(str).toLocaleTimeString()` *is* the right pattern — it converts a properly-tagged instant to the browser's local wall-clock time. But per the JS/ECMA-262 `Date` parsing rules, a date-time string **without** a timezone designator is parsed as **local** time, not UTC. So the frontend was silently and "correctly" (per spec) misinterpreting an untagged UTC value as if it were already local — which is exactly the ~5.5-hour IST offset observed.
- **Fix:** added `core/clickhouse.py:to_aware_utc()` — attaches `tzinfo=UTC` to any naive datetime clickhouse-driver returns — and call it on every ClickHouse timestamp before it reaches a Pydantic response model (`routes/traffic.py`) or a WebSocket message (`routes/websocket.py`, which already had its own copy of this exact function for a different reason — bookkeeping comparisons — and now shares the one in `core/clickhouse.py` instead of duplicating it). Pydantic then correctly serializes with a `Z` suffix, and the existing frontend code works unmodified.
**Revisit when:** Layer 4 (east-west insider threat monitoring, build order phase 2 in `docs/PROJECT.md`) is timestamp-heavy by nature — behavioral baselines, access-time-anomaly detection ("3am DB query"), and session correlation all depend on correct, consistent instants. **Any new service that reads a ClickHouse `DateTime` column and hands it to an API response, a WebSocket message, or a log line must call `to_aware_utc()` first** — this is the one recurring gotcha this ADR exists to prevent from being reintroduced ad hoc. If Postgres columns are ever read as naive datetimes too (they haven't been so far — `TIMESTAMPTZ` + psycopg return aware values), the same function applies there as well.

---

## ADR-035 — rule_gen.py's JSON extraction must handle prose-wrapped responses, not just fences
**Decision:** `ml/rule_gen.py`'s `_extract_json()` now falls back to a brace-counting scan (`_find_json_object()`) that locates the first balanced `{...}` object anywhere in the LLM's raw text, if a direct parse and a markdown-fence-stripped parse both fail.
**Reason:** Found while re-running the full pipeline with `llama3.1` (previously only tested with `mistral`, which always either returned bare JSON or fenced it). `llama3.1` instead narrated around the JSON with no fence at all — `"Here is the required output:\n\n{...}\n\nThis rule uses iptables syntax..."` — which crashed `generate_rule()` with `RuleGenerationError: LLM response was not valid JSON`, before the rule ever reached the sandbox. This wasn't a sandbox-safety-net case (an invalid *rule*); it was rule_gen.py's own parser being too strict about a formatting convention different local models don't share. Brace-counting (ignoring braces inside string literals) finds the object regardless of what prose surrounds it.
**Revisit when:** Never expected to need further generalization — this handles the three shapes seen so far (bare JSON, fenced JSON, prose-wrapped JSON) and should generalize to most instruction-following variance across future providers/models.

---

## ADR-036 — llama3.1 is not more reliable than mistral at producing valid iptables commands
**Decision:** No code change from this entry — recorded as an operational finding. `LLM_PROVIDER=ollama` / `OLLAMA_MODEL=llama3.1` remains the configured default per ADR-017; this is not a recommendation to switch.
**Reason:** Re-ran the full `rule_gen.py` → `tester.py` → `promoter.py` pipeline against a real ClickHouse anomaly, specifically to check whether switching from `mistral` to the configured-default `llama3.1` (8B) produced syntactically valid `iptables` commands more reliably. It did not. Across 4 completed generations (a 5th crashed on JSON parsing — see ADR-035, fixed and excluded from this count), `llama3.1` produced a genuinely invalid `command` in every case the sandbox got to test: a comma-separated port list passed to `--dport` (needs `-m multiport --dports` instead), and — a distinct, novel failure mode not seen with `mistral` — the `iptables` binary name itself omitted from the `command` string twice (`"-A INPUT -s ..."` instead of `"iptables -A INPUT -s ..."`), which `sh -c` rejects outright as `Illegal option -A`. One generation appeared to "pass," but only because ClickHouse had no traffic left in `tester.py`'s 10-minute replay window at that moment — re-run with fresh traffic, the same missing-binary-name defect was caught and correctly rejected. Every invalid rule was correctly caught by the sandbox and never reached `LIVE` — the core guarantee held throughout.
**Revisit when:** Evaluating whether any local model is reliable enough to skip the sandbox's syntax check (unlikely to ever be a good idea) — or when comparing against Claude/OpenAI's reliability on this same task, which hasn't been tested yet.

---

## ADR-037 — Current status: rule generation is safety-verified, not yet demonstrated working end-to-end
**Decision:** No code change — this is a status marker for whoever picks up Layer 1 next. Treat rule generation as **"safety-verified but not yet demonstrated working end-to-end with a passing rule."**
**Reason:** Both local, CPU-only Ollama models tried so far — `mistral` (ADR from the sandbox-build session) and `llama3.1` (ADR-036) — fail to reliably produce syntactically valid `iptables` commands. Every invalid attempt has been correctly caught and rejected by the sandbox (`tester.py`'s `InvalidRuleError` → `REJECTED` path), so the core guarantee ("no untested rule ever reaches the live firewall") has held in every real run. What hasn't happened yet, in any run to date, is the actual **happy path**: a generated rule that is syntactically valid, gets genuinely replayed against real traffic by the sandbox, passes the FP-rate check, and reaches `APPROVED_PENDING` on its own merits (as opposed to a hollow pass caused by an empty replay window, which doesn't count — see ADR-036). The pipeline's plumbing (rule_gen → tester → fp_scorer → promoter → Postgres → frontend) is fully verified working; the LLM's ability to reliably produce a *good* rule is not.
**Next step:** When ready to spend API budget, test with the `claude` or `openai` provider (already built and swappable via `LLM_PROVIDER` per ADR-017 — no code change needed, just the env var and a real API key) on this same real-anomaly pipeline. That determines whether this is a **local-model capability ceiling** (small CPU-bound models struggling with precise `iptables` syntax) or a **deeper issue** (e.g. a prompt template gap, a `rule_gen.py`/sandbox bug not yet surfaced, or a fundamental limit of LLM-generated firewall rules generally). Until that test happens, don't assume a hosted-model swap is a fix, and don't report Layer 1's rule generation as "working" beyond the safety net.
**Revisit when:** Immediately upon running the Claude/OpenAI comparison test — update this entry (or superseding it with a new ADR) with that result either way.