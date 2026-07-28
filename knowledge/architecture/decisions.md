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

---

## ADR-038 — Claude (claude-sonnet-4-6) produces syntactically valid iptables — but exposed a real sandbox gap
**Decision:** Ran the Claude/OpenAI comparison test that ADR-037 called for, using `claude-sonnet-4-6` (real paid API call). Recording the outcome; also added permanent timing instrumentation (`AnomalyContext.detected_at` in `ml/rule_gen.py`, `pipeline_duration_seconds` computed in `sandbox/tester.py`) so "time to generate and validate" is now logged and stored end to end (detection → APPROVED_PENDING/REJECTED) for every run, not just this one.
**Reason:** Against the same real ClickHouse anomaly (`10.0.0.99 → 10.0.0.9` port scan) both local models had already failed on, Claude produced a fully valid `iptables` command on the first attempt — it loaded into the sandbox container without error, something neither `mistral` nor `llama3.1` ever achieved (ADR-036, ADR-037). Full pipeline latency (detection to `APPROVED_PENDING`): **25.5 seconds**, dramatically faster than the local models' multi-minute-with-retries generations.

However, the resulting `APPROVED_PENDING` **should not be read as a genuinely validated rule**, and this is a real, newly-discovered gap, not a nitpick: Claude's rule inserted into the **`FORWARD`** chain (`iptables -I FORWARD ... -m recent ... -j DROP`) — a reasonable, arguably more architecturally correct choice for traffic between two other hosts (10.0.0.99 and 10.0.0.9 are both simulated *other* machines, not the box itself) — but `sandbox/tester.py`'s `_replay_and_check()` only zeroes and reads the **`INPUT`** chain's counters (hardcoded `iptables -Z INPUT` / `iptables -L INPUT ...`). Worse, the sandbox's network model (aliasing the flow's `dst_ip` as a `/32` onto the container's own `veth-in`, per ADR-020) makes the kernel treat replayed packets as **locally destined**, which routes them through `INPUT`, not `FORWARD`, regardless of which chain we check — `FORWARD` only ever sees packets being routed *through* the box to somewhere else, which our host-based sandbox model never simulates. Net effect: this rule's actual blocking behavior was **never exercised** by the replay. `blocked_anomalous_packets: 0` and `fp_rate: 0.0` are both real numbers, but they mean "nothing was checked," not "the rule correctly distinguishes attack traffic from legitimate traffic." The sandbox currently only meaningfully validates `INPUT`-chain rules.
**Revisit when:** Before trusting any `APPROVED_PENDING` verdict for a rule targeting `FORWARD` (or any chain other than `INPUT`). Two independent fixes are needed, not one: (1) check counters on whichever chain(s) the candidate rule actually modifies, not just `INPUT`; (2) redesign the sandbox's network model so `FORWARD`-chain rules are genuinely exercisable — likely requires simulating the sandbox as a router/gateway between two *un-aliased* hosts with IP forwarding enabled, rather than the box being the destination itself. This is a bigger change than (1) alone and wasn't attempted here — flagged for explicit user decision rather than silently redesigning sandbox network topology mid-task.
**Status: RESOLVED — see ADR-039.** Router-mode testing (attacker → firewall → target, genuine Docker-network routing) now exercises `FORWARD`-chain rules for real. The exact rule this ADR flagged was re-tested honestly: 40/40 anomalous packets correctly blocked, 0/85 legitimate packets blocked — a genuine pass, not a hollow one.
---

## ADR-039 — Router-mode sandbox: genuine attacker → firewall → target routing for FORWARD-chain rules
**Decision:** Added a second sandbox testing mode alongside the existing host mode (untouched), auto-selected by `sandbox/tester.py`'s `_detect_chain()` — never a manual toggle. Host mode (single isolated container, `--network none`, internal veth pair) still tests `INPUT`-chain rules exactly as before. Router mode stands up three containers — `attacker`, `firewall` (multi-homed, where the candidate rule is actually loaded, on its `FORWARD` chain), `target` — connected via two real Docker bridge networks, and replays traffic from `attacker` through `firewall`'s genuine routing/netfilter decision toward `target`.

**Reason:** ADR-038 established that `FORWARD`-chain rules can't be meaningfully tested by aliasing a destination IP onto one container's own interface (host mode's trick) — that always produces local delivery (`INPUT`), never forwarding. `FORWARD` only means something when a packet genuinely arrives on one interface addressed to somewhere reachable only via a *different* interface, in the *same* netns — which requires at least two other network endpoints the sandbox doesn't own.

**How it works (each piece proven empirically before being wired into `tester.py`, mirroring how the original host-mode veth/broadcast-MAC recipe was discovered):**
- Two Docker bridge networks (`attacker_net`, `target_net`); `firewall` connects to both via `docker.network.connect()` after creation, giving it `eth0` (attacker-facing) and `eth1` (target-facing).
- `ip_forward` is already `1` by default under Docker Desktop's networking backend (writing to `/proc/sys/net/ipv4/ip_forward` is read-only in this environment, but the value already reads `1` — inherited from the host/VM level).
- The candidate rule loads onto `firewall`'s `FORWARD` chain via the exact same `_load_rule()` used by host mode — no changes needed, it's already just `container.exec_run(["sh", "-c", command])` against whichever container is passed in.
- Per flow: `firewall` gets an explicit `ip route replace <dst_ip>/32 via <target's real Docker-assigned IP>` (idempotent, same pattern as host mode's `ip addr replace`), then `attacker` injects via `tcpreplay --intf1=eth0`.
- **A `dst_mac` parameter was added to `_build_flow_pcap()` (default `BROADCAST_MAC`, so host mode's one call site is byte-for-byte unchanged).** Router mode passes the firewall's *real* MAC address instead — broadcast destination MACs are silently dropped somewhere in Docker's bridge delivery path (confirmed: identical packets addressed to the firewall's real MAC traversed `FORWARD` correctly; addressed to broadcast, they never arrived at all). This is the opposite of host mode's veth pair, where broadcast was *required* (ADR-020) — a real, non-obvious platform difference between a bare veth pair and a real Docker bridge.
- **`internal=True` on the two Docker networks was tried first and does not work**: it silently blocks inter-container `FORWARD`-chain traffic through a multi-homed container under Docker Desktop's networking backend, even though internal networks are documented as only blocking *external* routing (confirmed: a catch-all `LOG` rule on `FORWARD` stayed at 0 packets with `internal=True`, and started counting immediately the moment it was removed — nothing else changed). Isolation from the real network — the same guarantee host mode gets from `--network none` — is instead enforced by deleting each container's default route after it starts (`_strip_default_route`). Verified both properties hold simultaneously: `FORWARD`-chain forwarding works via the explicit static route, and a real connection attempt to `8.8.8.8:53` fails with "Network is unreachable."
- `fp_scorer.py` needed **no changes at all** — `score_replay()` already only reads `FlowResult.blocked`/`anomaly_score`/`packets`, agnostic to which chain produced the boolean. Verified this deliberately rather than assuming it.
- `run_sandbox_test()` now records `sandbox_result["mode"]` (`"host"` or `"router"`) for every test, so any future audit of a rule's history shows which mode validated it — not implicit/undiscoverable.
- Both container-creation (`_start_router_topology`) and per-test-run replay are now defensively try/finally-wrapped so a partial failure (e.g. the third container fails to start) cleans up whatever was already created — three containers and two networks is meaningfully more to leak than host mode's one container, so this got more defensive handling than host mode has (host mode's own container-creation step is not similarly guarded — a pre-existing gap, left as-is per "do not modify host-mode logic").

**Re-tested the exact rule ADR-038 flagged**, live, after building this: Claude's `FORWARD`-chain port-scan rule (`412abe6e-2d7f-4654-b041-638297d03b33`) now genuinely blocks 40/40 anomalous packets and 0/85 legitimate packets — a real pass, not a hollow one. **Side effect worth flagging explicitly**: this rule had, in the meantime, been approved by a human via the dashboard and moved to `LIVE` — based on the fabricated `fp_rate: 0.0` from ADR-038. Re-running it through `promoter.approve()` set it back to `APPROVED_PENDING` (that function doesn't know a rule was previously promoted further), since the instruction was to update status based on the real test regardless of current state. The result is good news (the rule holds up under genuine testing), but a rule a human had already approved is now sitting back in the review queue awaiting a fresh, honestly-informed approval — this is a real state change, not a silent no-op, and is being surfaced clearly rather than buried in a "still passes" summary.

**Regression-checked host mode is unaffected**: re-ran both the original PASS scenario (block only the scanner IP, FP rate 0.0) and REJECT scenario (block all traffic to the target, FP rate 92.5%) — both dispatch to `mode: "host"` via `_detect_chain()` and produce identical behavior to before this change.

**Revisit when:** If Docker Desktop's networking backend changes (e.g. a future version where `internal: true` behaves differently) — re-verify the `internal=True` limitation still holds before assuming the default-route-stripping workaround is still necessary.

**Status: RESOLVED (the `OUTPUT` gap) — see ADR-040.** `_detect_chain()` now distinguishes all three chains (`FORWARD`, `OUTPUT`, `INPUT`) instead of lumping `OUTPUT` into "everything else."
---

## ADR-040 — Output mode: genuine locally-originated traffic for OUTPUT-chain rules

**Decision:** Extended `_detect_chain()` to return `"OUTPUT"` as its own case (checked after `FORWARD`, before falling through to the `INPUT` default) instead of silently treating every non-`FORWARD` rule as host/`INPUT` mode. Added a third sandbox testing mode, **output mode**, auto-selected the same way router mode is — never a manual toggle. Neither host mode nor router mode's code changed.

**Reason:** A rule targeting `OUTPUT` (traffic *leaving* the firewall/protected host itself — e.g. blocking a host from beaconing to a C2 server) was previously indistinguishable from an `INPUT` rule to `_detect_chain()`, so it silently got tested in host mode against `INPUT`'s counters — a rule that would never match anything the replay generated, the same category of hollow-pass bug ADR-038 found for `FORWARD`. Found by inspection this time (re-reading `_detect_chain()` against ADR-039's own "not exhaustive" note), not by an LLM generating a live `OUTPUT` rule and failing — verification was still fully empirical, just proactive rather than reactive.

**How it works (mechanism confirmed empirically before being wired into `tester.py`):**
- Output mode reuses host mode's exact container/veth setup **unchanged** — `_start_container`, `_load_rule`, `_any_drop_matched` are all called verbatim, no new topology needed (a much lighter change than router mode's three-container build). This works because `OUTPUT` fires for any packet the container's own kernel constructs, *including* one addressed to an IP aliased onto its own interface — confirmed directly: a real connection attempt to a locally-aliased address traverses `OUTPUT` before the kernel short-circuits it to local delivery.
- What has to differ from host mode is purely how traffic is generated. `tcpreplay`'s injected frames are inbound by construction — they can only ever hit `INPUT` or `FORWARD`, never `OUTPUT`, because `OUTPUT` only fires for packets the local kernel itself originates. Genuine egress traffic instead comes from real socket connections made from inside the container, via bash's `/dev/tcp` and `/dev/udp` — confirmed against real `OUTPUT` chain counters for both a DROP-matching case (packets counted, matched) and a non-matching case (packets counted against the default ACCEPT policy instead, confirming legitimate traffic isn't falsely blocked).
- Per flow: alias `dst_ip` onto the container's interface (`ip addr replace`, same idempotent pattern host mode already uses), zero the `OUTPUT` counters, run a small shell loop attempting `count` connections, then read `OUTPUT`'s counters back.
- **ICMP has no real egress-generation mechanism in this sandbox** and this is an honest, currently-unresolved gap, not a hidden one: there's no `ping`-equivalent tool installed in the sandbox image, and `--network none` blocks any `apt-get install` to add one. `_build_egress_script()` raises `SandboxTestError` for any protocol other than `TCP`/`UDP`; the replay loop treats this the same as any other skippable-flow error (log a warning, continue). This means an `OUTPUT`-chain rule's true behavior against ICMP traffic — if any exists in the replay window — is **never validated**, and the resulting `fp_rate`/pass verdict is silently computed over TCP/UDP flows only. This is the same category of honest limitation ADR-038 originally flagged for `FORWARD`, just narrower in scope.

**A real bug was found and fixed during testing, not just before it**: the first automated end-to-end run hung for 27+ minutes instead of completing. Root cause: a `DROP`ped SYN produces no RST, so an unbounded `/dev/tcp` connect() blocks on the kernel's own SYN-retry timeout — confirmed via `docker top` (a `bash` process stuck for 27 minutes on a single flow's connection loop) and `/proc/net/tcp` (socket in `SYN_SENT`, 9+ retransmits and still going, no cap in sight). The manual proof-of-concept that validated the underlying mechanism had wrapped each attempt in `timeout 2` and this got lost translating that into `_build_egress_script()` — a real oversight, not a platform quirk. Fixed by wrapping every individual connection attempt (not just the whole flow) in `timeout ${EGRESS_CONNECT_TIMEOUT_SECONDS}` (2s), bounding worst case to `count × 2s` per flow (≤100s at `MAX_PACKETS_PER_FLOW`). Re-ran clean after the fix: same rule, same traffic, completed in seconds instead of hanging indefinitely.

**Tested with a realistic scenario**: seeded ClickHouse with 20 legitimate outbound flows (`10.0.0.9` → `93.184.216.34:443/80`, `8.8.8.8:53`, `anomaly_score` 0.0–0.3) and 8 anomalous egress flows mimicking exfiltration/C2 beaconing (`10.0.0.9` → `203.0.113.77:4444`, `anomaly_score` 0.85–0.97). Candidate rule: `iptables -A OUTPUT -d 203.0.113.77 -j DROP`. `_detect_chain()` correctly returned `"OUTPUT"` (not the previous silent fallthrough to `INPUT`); `run_sandbox_test()` correctly dispatched to `mode: "output"`. Result: all 28 flows genuinely tested (not hollow), **0/166 legitimate packets blocked, 48/48 anomalous packets blocked**, `fp_rate: 0.0000` — a real pass, mirroring the same "genuine, not hollow" bar ADR-039 set for router mode.

**Regression-checked both existing modes are unaffected**: re-seeded fresh INPUT-scenario traffic (15 legit inbound + 8 anomalous from a bad source) and FORWARD-scenario traffic (15 legit forwarded + 8 anomalous to a bad destination), each with its own new candidate rule. `_detect_chain()` correctly returned `"INPUT"` / `"FORWARD"` respectively; `run_sandbox_test()` dispatched to `mode: "host"` / `mode: "router"` respectively; both passed with `fp_rate: 0.0000` and blocked exactly the packet counts belonging to their own targeted traffic (32/32 and 48/48) — host mode and router mode's own logic was not touched by this change and both still behave identically to ADR-039's regression check.

**Revisit when:** If ICMP-based `OUTPUT` rules ever need real validation — would require either installing a ping-equivalent tool into the sandbox image at build time (before `--network none` takes effect) or constructing raw ICMP sockets directly, neither attempted here. Also revisit the `EGRESS_CONNECT_TIMEOUT_SECONDS = 2` constant if a legitimate flow's real destination is slow to accept connections beyond 2s — currently untested against anything but near-instant local-alias delivery.
---

## ADR-041 — `scripts/seed_demo_data.py`: self-serve demo traffic, since there's still no live ingestion pipeline

**Decision:** Added a standalone, dependency-light script (`scripts/seed_demo_data.py`) that inserts realistic `traffic_events` rows into ClickHouse with **current timestamps**, on demand, via one command. Documented in `scripts/README.md`. Not wired into any service — a manual operational tool, run before demos.

**Reason:** The "dashboard traffic chart shows no data" issue has now come up multiple times in this project's history (most recently: `GET /api/v1/traffic/`'s default 60-minute window found nothing because the newest `traffic_events` row was ~6.5 hours old). The root cause is structural, not a bug: **Zeek → Kafka → ClickHouse ingestion (build order step 3) has never run continuously** — every row in `traffic_events` so far has come from one-off manual seed scripts (mine, written ad hoc per task, backdated or not depending on what that task needed), so data reliably goes stale between sessions. Building the real continuous pipeline is out of scope for a quick fix and isn't next in the build order (Celery + Redis async jobs is); a small self-serve script closes the immediate demo-readiness gap without pulling that forward.

**What it does:**
- Inserts ~120 rows of believable background traffic (3 internal hosts, HTTPS/HTTP/DNS-shaped flows to a handful of external services, `anomaly_score` 0.0–0.25) spread across the last ~50 minutes.
- Inserts two distinct, clearly-anomalous scenarios, both timestamped in the last 1–3 minutes so they show as a clear recent spike: a port scan (`198.51.100.66` → `10.0.0.9`, 8 ports, `anomaly_score` 0.85–0.95) and an exfiltration/beaconing pattern (`10.0.0.9` → `203.0.113.99:4444`, large bursts, `anomaly_score` 0.9–0.98).
- All timestamps are `datetime.now(timezone.utc)`-relative, never backdated — the explicit point is that the dashboard's *default* 60-minute view (no query params) shows data immediately after running it, matching what `frontend/src/hooks/useTraffic.js` actually calls.
- Reuses `ingestion/clickhouse.py`'s existing `get_client()` / `ensure_table()` / `insert_traffic_events()` unchanged — no new ClickHouse-writing code path, just a new caller.
- Idempotent to re-run: each run only inserts new rows; nothing is deleted or reset. Old rows age out of the dashboard's default view on their own and out of ClickHouse via the table's existing 30-day TTL.

**Verified live**: ran the script, then confirmed `GET /api/v1/traffic/` (default `minutes=60`, no params — the same call the frontend makes) returned all 134 seeded rows, and `GET /api/v1/traffic/anomalies` returned exactly the 14 anomalous ones (8 scan + 6 exfiltration).

**Revisit when:** If/when the real Zeek/Kafka ingestion pipeline is finally built and run continuously, this script becomes redundant for normal operation — but likely still useful for deterministic demo data (a live pipeline's traffic is whatever's actually happening on the network, not guaranteed to include a clean anomaly for a demo). Not removing it preemptively.
---

## ADR-042 — Output mode's self-IP gap: rules with `-s <this-host-ip>` were silently never tested

**Decision:** Fixed `sandbox/tester.py`'s `_replay_and_check_output()` to pin each flow's real `src_ip` as the actual source address of the sandbox's generated egress traffic, not just alias `dst_ip` as ADR-040 originally did. Found via a genuine production-pipeline run, not contrived: the first real end-to-end test of `ml/rule_gen.py` for an OUTPUT-chain rule (see the request that produced this ADR) had Claude generate `iptables -I OUTPUT ... -s 10.0.0.9 -d 203.0.113.99 -p tcp --dport 4444 -j DROP` for a 10.0.0.9-is-exfiltrating scenario — a completely natural rule for an LLM to write given "this host itself (10.0.0.9) is sending suspicious traffic." The sandbox reported **PASS, fp_rate 0.0000** — but **blocked 0 of 6 anomalous packets**. A rule that blocks nothing still passed.

**Reason:** ADR-040's design only ever aliased the flow's `dst_ip` onto the container (`ip addr replace <dst_ip>/32 dev veth-in`), which is what makes traffic traverse `OUTPUT` at all. It never gave the container the flow's `src_ip` in any form. `fp_scorer.py`'s `fp_rate` metric only measures legitimate traffic wrongly blocked — it has no check for whether anomalous traffic gets blocked at all — so a rule that matches nothing (because its `-s` clause can never be satisfied) sails through with a perfect 0.0 fp_rate and reaches `APPROVED_PENDING` having been validated against nothing. This is a correctness gap, not just a coverage gap like the already-documented ICMP limitation: it produces false confidence in a specific, very plausible rule shape rather than an honestly-flagged unknown.

**Root cause, confirmed empirically (not by reasoning alone) with a standalone container mirroring the sandbox's exact setup:**
- After `ip addr replace 203.0.113.99/32 dev veth-in` (dst_ip aliasing, ADR-040's existing step), `ip route get 203.0.113.99` reported `src 203.0.113.99` — the kernel had picked the *destination* address as the source. This is expected once dst_ip becomes a locally-owned address: the route becomes an `RTN_LOCAL` entry in the `local` routing table, and the kernel's default local-delivery source-selection just uses the destination's own address.
- Adding a normal `ip route replace <dst>/32 dev veth-in src <src_ip>` (a `main`-table route) had **no effect at all** — `ip route get` still reported `src <dst_ip>`. The `local` table has strictly higher priority in the routing policy database and is consulted first; a `main`-table route for the same prefix is never reached.
- The fix needs two things together, confirmed by testing each in isolation:
  1. `ip addr replace <src_ip>/32 dev veth-out` — without this, `ip route replace local ... src <src_ip> table local` fails outright with `Error: Invalid prefsrc address` (the kernel requires a route's `src` to be a locally-assigned address).
  2. `ip route replace local <dst_ip> dev veth-in src <src_ip> table local` — explicitly overwrites the *auto-generated* `local`-table entry itself (not a `main`-table addition) with the desired source.
- With both applied, `ip route get <dst_ip>` correctly reported `src <src_ip>`, and a live connection through a `-s <src_ip> -d <dst_ip> ... -j DROP` rule correctly matched and incremented the `OUTPUT` counters — confirmed directly, not inferred.

**Verified with the exact rule that exposed this**: re-seeded the identical scenario (6 anomalous exfiltration flows `10.0.0.9 → 203.0.113.99:4444`, 15 legitimate flows `10.0.0.9 → 93.184.216.34`/`8.8.8.8`) and re-ran the exact Claude-generated rule (no new LLM call — reusing the already-generated, already-paid-for command). Result: `blocked_anomalous_packets` went from **0 → 112** (all anomalous packets across all 6 flows), `blocked_non_anomalous_packets` stayed at **0**, `fp_rate` stayed **0.0000** — the rule now genuinely blocks what it was designed to block, and the false-positive check is unaffected.

**Regression-checked host and router mode are unaffected**: this fix only touches `_replay_and_check_output()` and its one caller (`_replay_all_flows_output_mode()`) — no other function was modified. Re-seeded fresh INPUT-scenario and FORWARD-scenario traffic and re-ran the same rules used in ADR-040's own regression check: both still dispatch correctly (`mode: "host"` / `mode: "router"`) and block the identical packet counts as before this change (32/32 and 48/48) — byte-for-byte the same behavior.

**Revisit when:** The `local` routing table override (`ip route replace local ... table local`) is a somewhat unusual technique — if a future Docker/kernel networking change alters how the `local` table is populated or prioritized for veth pairs, re-verify this still works the same way ADR-039 flagged for `internal=True` networks. Also note this fix doesn't touch the still-open ICMP gap (ADR-040) — ICMP flows remain untested in output mode regardless.
---

## ADR-043 — Detection rate: `fp_scorer.py` now also checks whether a rule blocks anything at all

**Decision:** Added a second metric, `detection_rate`, to `sandbox/fp_scorer.py`'s `score_replay()`, alongside the existing `fp_rate`. A candidate rule must now clear **both** an acceptable false-positive rate (`fp_rate <= SANDBOX_FP_THRESHOLD`, unchanged, default 5%) **and** a minimum detection rate (`detection_rate >= SANDBOX_DETECTION_THRESHOLD`, new, default 10%) to reach `APPROVED_PENDING`. `promoter.py` needed **no changes** — it is a pure persistence layer that writes whatever verdict `run_sandbox_test()` hands it; the actual pass/fail gate has only ever lived in `fp_scorer.py`'s `score_replay()`, and that is where this check was added. `tester.py`'s rejection-reason string was also fixed in the same change — it previously hardcoded "FP rate exceeds threshold" regardless of the real cause, which would have misreported a detection-rate failure as an FP-rate failure.

**Reason:** ADR-042, discovered one turn earlier via a genuine production-pipeline run, found a rule that reached `APPROVED_PENDING` with a perfect `fp_rate: 0.0` while blocking **0 of 6** anomalous packets it was generated specifically to stop. `fp_rate` only ever measured legitimate traffic wrongly blocked — it had no way to notice a rule that matches nothing at all. That specific bug (the sandbox's self-IP gap) is now fixed, but the scorer itself had no defense against a *different* rule that's simply wrong in some other way — mismatched port, wrong protocol, a typo'd IP, anything that makes the rule never match its target. This is a structural gap, not a one-off: any future rule shape that happens to match nothing would sail through the same way ADR-042's rule did, silently.

**Design decision — the threshold is deliberately low (10%), not close to 100%:** a naive "must block ≥90%" gate would have rejected two real, already-approved, legitimately-designed rules from this project's own history. Both the INPUT-chain and FORWARD-chain rules Claude generated in the production-pipeline test (ADR-042's sibling runs) use `iptables -m recent` sliding-window rate-limiting — deliberately letting the first few SYNs from a source through before dropping later ones, so a single retried legitimate connection isn't punished. Measured against their own seeded traffic, both blocked exactly **3 of 8** anomalous packets — a real, intentional **37.5%** detection rate, not a bug. A high threshold would have rejected genuinely good rules for the "crime" of being a rate limiter instead of a hard block. `SANDBOX_DETECTION_THRESHOLD=0.1` was picked specifically to sit well below that real 37.5% observed value while still catching a true 0% (nothing-blocked) case — verified against actual data, not chosen arbitrarily.

**Also decided: an empty anomalous-traffic window does not gate the rule.** If `total_anomalous_packets == 0` (the specific anomaly that triggered rule generation aged out of the 10-minute replay window before the sandbox test ran — something this project has hit repeatedly, e.g. ADR-040's first OUTPUT-mode test run), `detection_rate` is stored as `None` and the check is skipped entirely rather than treated as an automatic 0%-and-reject. Mirrors the existing precedent for `fp_rate`'s own zero-denominator case (`total_non_anomalous_packets == 0` → treated permissively, not as a failure).

**Verified across all three modes, using real rule shapes, not synthetic edge cases:**
- **INPUT (host mode)**, basic outright-`DROP` rule: `detection_rate: 1.0000` — PASS.
- **INPUT (host mode)**, the real rate-limiting Claude rule re-run verbatim (no new LLM call): `detection_rate: 0.3750` — **correctly still PASSES**, confirming the threshold doesn't punish intentional partial-blocking designs.
- **FORWARD (router mode)**, the real rate-limiting Claude rule re-run verbatim: `detection_rate: 0.3750` — **correctly still PASSES**.
- **OUTPUT (output mode)**, the ADR-042-fixed rule re-run: `detection_rate: 1.0000` — PASS, `blocked_anomalous_packets: 114/114`.
- **OUTPUT (output mode)**, a rule deliberately constructed to match none of the seeded anomalous traffic (wrong destination IP, standing in for "a rule that's simply wrong"): `detection_rate: 0.0000` — **correctly REJECTED**, with reason `"detection rate 0.0000 below threshold 0.1000"` (confirming the fixed rejection-reason string correctly attributes the cause, not the old hardcoded FP-rate message).

**Revisit when:** If a future rule intentionally blocks an even smaller fraction than 37.5% for good reason (a very conservative rate limiter), `SANDBOX_DETECTION_THRESHOLD=0.1` may need lowering — it was picked against the two real data points available at the time, not a theoretical worst case. Also revisit alongside ADR-042's own open item: this still doesn't validate ICMP flows in output mode, so a rule targeting only ICMP traffic will always show `detection_rate: None` (untested, not failing) rather than a real measured value.
---

## ADR-044 — Audit logging: implemented from scratch, and a real frozen-timestamp bug found along the way

**Decision:** `layer1_design.md` has documented an `audit_log` table schema since early in this project, but it was never actually implemented — no SQLAlchemy model, no writes, no table in Postgres at all (`\d audit_log` returned "did not find any relation"). Built it for real: `backend/models/audit_log.py` (`AuditLog` ORM model, `AuditAction` enum, a `record()` helper), wired into `routes/rules.py`'s `approve_rule`/`reject_rule`/`revoke_rule` so every status change writes an entry in the **same transaction** as the status change itself (added to the session, committed together — an audit entry can never exist for a status change that failed to save, or vice versa). Added `GET /api/v1/audit/` (`routes/audit.py`), filterable by `rule_id` and `action`, joined against `users` so each entry returns a human-readable `actor_email` alongside the raw `actor_id`.

**A real, active bug was found while building this, not a theoretical one:** the model's first draft copied this codebase's existing pattern — `mapped_column(DateTime(timezone=True), server_default="now()")`, exactly as `models/user.py`'s `created_at` and `models/rule.py`'s `created_at`/`updated_at` already do. Testing it immediately exposed the problem: a brand-new test user, registered fresh, showed `created_at: "2026-07-03T20:47:42"` — the date the `users` table was first created, weeks earlier, not the actual registration moment. Confirmed the mechanism directly via `information_schema.columns`: SQLAlchemy quotes a bare Python string passed to `server_default`, producing `DEFAULT 'now()'` (a string literal) rather than `DEFAULT now()` (a live function call). Postgres casts that string literal to a timestamp **once, at the moment the column's DDL is executed**, and then reuses that same frozen value as the default for every row inserted afterward, forever. This is a well-known Postgres pitfall (quoted vs. unquoted default expressions), not a SQLAlchemy bug, but it's real and it's been silently affecting `users.created_at` and `candidate_rules.created_at`/`updated_at`'s initial value in this codebase since those tables were first created.

**Fixed in `audit_log.py`** with a Python-side default instead (`default=lambda: datetime.now(timezone.utc)`), which sidesteps the DDL-quoting pitfall entirely and matches this project's own established UTC-everywhere convention (ADR-034) — the ORM computes and supplies a correct value before every INSERT, regardless of what the column's server-side default happens to be. Also dropped the already-created table's stale frozen default at the DB level (`ALTER TABLE audit_log ALTER COLUMN timestamp DROP DEFAULT`) for hygiene, since the Python-side default makes it dead weight, not because it was still doing anything wrong going forward.

**Deliberately not fixed**: `users.created_at` and `candidate_rules.created_at`/`updated_at` have the identical bug and are still frozen. Out of scope for an audit-logging task — flagged here explicitly rather than silently left for someone to rediscover later, per this project's standing transparency convention.

**One naming note**: the documented schema's `metadata` column could not be a Python attribute named `metadata` — `Base.metadata` is reserved on every SQLAlchemy declarative model (it's the schema's own `MetaData` object). Mapped as `event_metadata` in Python, `metadata` in the actual DB column (`mapped_column("metadata", JSON, ...)`), so the on-disk schema still matches what `layer1_design.md` documents.

**`GET /api/v1/audit/` requires authentication**, unlike most other GET routes in this API (`GET /api/v1/rules/` and `/api/v1/traffic/` are both open) — a deliberate deviation, not an oversight: an accountability log readable by anyone without logging in undercuts its own purpose.

**Verified live with real data**: registered a throwaway test account (`audit-test@firewallai.dev`), inserted three test rules at `APPROVED_PENDING`, then via real authenticated API calls: approved one (→ `LIVE`), rejected one (→ `REJECTED`), approved-then-revoked the third (→ `LIVE` → `REVOKED`). All four resulting audit entries appeared correctly in `GET /api/v1/audit/`, each with a correct, genuinely-current `timestamp` (not frozen), correct `actor_email`, and `event_metadata` capturing `from_status`/`to_status`/`command`. Also verified: `rule_id`/`action` query filters both work correctly; unauthenticated access to `GET /api/v1/audit/` returns 401; revoking a non-`LIVE` rule still correctly returns 400 (pre-existing check, unaffected).

**Revisit when:** If the `users.created_at`/`candidate_rules.created_at` frozen-default bug ever needs fixing for its own sake — same fix (a Python-side `default=`) would apply, just not done here since it wasn't part of this task's scope.
---

## ADR-045 — Rollback (revoke): verified working, frontend UI added (it didn't exist)

**Decision:** Verified `POST /api/v1/rules/{id}/revoke`'s backend logic — it already existed and already worked correctly (status guard requiring `LIVE`, transition to `REVOKED`) before this task; no backend bug was found in the endpoint itself. What genuinely was broken: **the frontend had no way to call it at all.** `useRules.js` only exposed `approveRule`/`rejectRule`; `RuleCard.jsx` only ever rendered Approve/Reject buttons, gated on `status === 'APPROVED_PENDING'` — there was no code path, button, or hook function that could reach the revoke endpoint from the dashboard. A human could not have revoked a live rule through the UI before this change, despite the endpoint working fine.

**Fixed**: added `revokeRule()` to `useRules.js` (same pattern as `approveRule`/`rejectRule` — POST, refetch, return success boolean), a `Revoke` button in `RuleCard.jsx` rendered only when `status === 'LIVE'` (behind a `window.confirm()` prompt, since this is a live-traffic-affecting action with no undo path back to `LIVE` from `REVOKED`), and threaded `onRevoke` through `RuleList.jsx` and `Rules.jsx` the same way `onApprove`/`onReject` already flow.

**Verified live with real data** (same test-rule lifecycle as ADR-044): approved a test rule to `LIVE`, called revoke via a real authenticated API call, confirmed the response showed `status: "REVOKED"` and the correct `RULE_REVOKED` audit entry was written. **Frontend caveat, stated plainly**: no browser automation tool (Playwright or equivalent) was available this session, unlike earlier phases of this project that verified frontend changes by actually clicking through them. What was verified instead: `npm run build` and `npm run lint` both pass clean with the new code, the API contract the new button depends on (`POST .../revoke` → `RuleResponse` with updated `status`) is confirmed correct via direct API calls, and the component wiring (prop threading from `Rules.jsx` → `RuleList.jsx` → `RuleCard.jsx` → `useRules.js`) was read and matches the existing Approve/Reject pattern exactly. The button was not clicked in an actual running browser this session — that gap is real and stated here rather than silently claimed as fully verified.

**Revisit when:** If a Playwright/browser tool becomes available, actually click the new Revoke button end-to-end to close the one remaining unverified piece.
---

## ADR-046 — Policy conflict checking: flagged for human review, never auto-rejected

**Decision:** Added `sandbox/conflict_checker.py`, wired into `tester.py`'s `run_sandbox_test()` right after `score_replay()` and before the approve/reject branch. Every candidate rule is now compared against every currently-`LIVE` rule (`promoter.get_live_rules()`, new) for two conflict types: **duplicate** (another `LIVE` rule matches identical traffic with the same effective action) and **contradictory** (another `LIVE` rule matches identical traffic with an opposing action — one `ACCEPT`s what the other `DROP`/`REJECT`s). Results land in `sandbox_result["policy_conflicts"]` (empty list if none) — **this never affects `passed`/`fp_rate`/`detection_rate` in any way**, per the explicit requirement: a human reviewer sees the conflict and decides, the system never silently auto-rejects on this basis alone. A conflict-check failure (e.g. a transient DB error) is caught and logged, not allowed to block an otherwise-earned verdict — this is an advisory check, not part of the core "no untested rule reaches the live firewall" guarantee.

**How matching works**: regex field extraction from the iptables `command` string (`-s`, `-d`, `--dport`, `-p`, and the *last non-`LOG`* `-j` target as the rule's "effective action") — not a full iptables grammar, mirroring `_detect_chain()`'s own established precedent for lightweight command parsing in this codebase. A multi-statement command (the LOG-before-DROP pattern every real generated rule uses, per `rule_gen.txt`'s own instructions) is read as one logical rule.

**Known limitation, found and left in deliberately, not hidden**: matching is **exact-tuple equality** on `(src, dst, dport, protocol)`, not semantic overlap. A rule with `-p tcp` and a rule with no `-p` at all (meaning "any protocol" in real iptables semantics) are treated as *different* traffic and won't be flagged as conflicting, even though the protocol-unrestricted rule's match set actually subsumes the TCP-only one. Confirmed directly: a real rate-limited TCP rule (`-p tcp --syn -m recent ...`) was NOT flagged as a duplicate of an existing plain `-s <ip> -j DROP` rule matching the same source, purely because one specifies a protocol and the other doesn't. This is a conservative simplification, not an oversight — for an advisory, human-reviewed feature, missing a conflict (false negative) is the safer failure mode than spamming false alarms (false positive) that erode trust in the warning. Proper CIDR-overlap and protocol-wildcard-subsumption reasoning would be a meaningfully larger undertaking, not attempted here.

**Frontend**: `RuleCard.jsx` renders an amber warning banner (distinct from the existing red `actionError` styling) listing every conflict's human-readable `message`, reading directly from `rule.sandbox_result.policy_conflicts` — no new API field or backend response-model change needed, since `sandbox_result` was already a passthrough JSON blob. Same frontend-verification caveat as ADR-045: build and lint pass, the data contract was confirmed correct via a real API call, but it was not clicked through in an actual browser this session.

**Verified live through the real sandbox pipeline** (not a unit test in isolation): with a real `LIVE` rule already in Postgres (`iptables -A INPUT -s 203.0.113.10 -j DROP`), ran three genuine `run_sandbox_test()` calls against real seeded traffic —
- An exact duplicate candidate → `policy_conflicts: [{"type": "duplicate", ...}]`, and the rule still **PASSED** its sandbox test (`fp_rate: 0.0`, `detection_rate: 1.0`) — confirming conflicts don't block a pass.
- A contradictory `ACCEPT` for the identical traffic → `policy_conflicts: [{"type": "contradictory", ...}]`; this rule was separately **REJECTED**, but for an unrelated, independently-correct reason (an `ACCEPT` rule against anomalous traffic naturally blocks 0% of it, failing ADR-043's detection-rate gate on its own merits) — proving the conflict check and the pass/fail gate are fully decoupled, not that conflicts caused the rejection.
- An unrelated source → `policy_conflicts: []`, confirming no false positives when traffic genuinely doesn't overlap.

Also confirmed the conflict data survives the full round trip to the real `GET /api/v1/rules/{id}` API response (not just present in the sandbox's own in-memory result) — the exact same JSON the frontend banner reads.

**Revisit when:** If exact-tuple matching's false-negative rate turns out to matter in practice (e.g. an LLM starts habitually omitting `-p` on rules that should be compared against protocol-specific `LIVE` rules), implement real overlap/subsumption logic instead of equality. Also revisit if this project ever supports `pf` syntax rules alongside `iptables` — `conflict_checker.py`'s regex patterns are iptables-specific.
