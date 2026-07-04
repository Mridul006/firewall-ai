# PROJECT.md — Full Technical Specification

## Vision
An autonomous cybersecurity platform that doesn't just detect threats — it actively mutates and adapts its own defenses in real time, making it nearly impossible for attackers to map and exploit. A living immune system rather than a static firewall.

---

## The 5-layer architecture

### Layer 1 — AI-driven sandboxed firewall rule generation (BUILD FIRST)
**What it does:** AI agent watches traffic, generates candidate rules, tests them in a sandbox, and only promotes rules that pass false-positive checks to the live firewall. No human writes a rule. No untested rule ever touches production.

**Flow:**
```
Live traffic
  → Zeek/Suricata (capture + parse)
  → Kafka (stream)
  → ClickHouse (store)
  → Isolation Forest (anomaly detection)
  → Claude API (generate candidate rule in iptables/pf syntax)
  → Docker sandbox + tcpreplay (replay traffic against candidate rule)
  → FP scorer (measure false positive rate)
  → If pass: promote to live firewall via FastAPI
  → If fail: discard, loop back to rule generator
```

**MVP mode:** Human-in-the-loop — AI suggests rule, human reviews and approves via dashboard. Full automation is a later release.

---

### Layer 2 — Multi-layer Moving Target Defense with CSPRNG rotation (BUILD THIRD)
**What it does:** Rotates IP addresses, ports, protocols, and service fingerprints simultaneously on independent cryptographically random schedules. Each layer has its own CSPRNG-driven rotation timeline.

**Core insight (Temporal Defense Layering — not yet patented; filing is a planned future step):** If each parameter rotates independently, an attacker who cracks one layer's rotation pattern still cannot predict the others. The unpredictability compounds exponentially across layers:
- Attacker must solve T1 (IP schedule) × T2 (port schedule) × T3 (protocol schedule) × T4 (fingerprint schedule) simultaneously
- Each Ti is driven by a CSPRNG — statistically unpredictable

**Rotation parameters:**
- IP rotation — virtual IP cycling via SDN or iptables NAT rules
- Port rotation — service port remapping on schedule T2
- Protocol rotation — protocol-level variation on schedule T3
- Service fingerprint rotation — OS/banner spoofing on schedule T4

---

### Layer 3 — Mutable encryption co-evolution (BUILD LAST)
**What it does:** Rotates the full encryption scheme — algorithm, key length, padding mode — based on threat intelligence signals and compute context. Not just key rotation — cipher scheme rotation.

**Why it matters:** Long-term adversaries intercepting ciphertext cannot build statistical attacks because what they captured yesterday (AES-256-GCM) is a different scheme than today (ChaCha20-Poly1305). Makes traffic analysis infeasible over time.

**Cipher selection inputs:**
- Threat intel feed (known attack patterns targeting specific ciphers)
- Compute context (CPU load, memory pressure, latency budget)
- Rotation schedule (independent of Layers 1 and 2)

**Cipher pool:**
- AES-256-GCM (default high-security)
- ChaCha20-Poly1305 (low-overhead mobile/edge)
- Post-quantum candidates (CRYSTALS-Kyber, NTRU)

---

### Layer 4 — East-west insider threat monitoring (BUILD SECOND)
**What it does:** Builds behavioral baselines per entity (user, service, machine) and monitors lateral movement inside the network — east-west traffic. Flags deviations: unusual access patterns, privilege escalation, data staging before exfiltration.

**Why east-west:** Most security tools only guard north-south (perimeter) traffic. Once an attacker breaches the perimeter or a malicious insider acts, they move laterally. This layer catches that.

**Detection signals:**
- Access time anomalies (3am DB query from user workstation)
- Volume anomalies (bulk file access from unexpected host)
- Privilege escalation (user accessing admin resources outside role)
- Data staging (large internal transfers before exfiltration)

**Baseline building:** Requires 2–3 weeks of traffic data per entity before alerting is meaningful. Start collecting logs during Layer 1 deployment.

**Alert tiers:**
- Unusual access → alert + session flag
- Privilege escalation → alert + log + notify SOC
- Data staging → alert + session kill

---

### Layer 5 — Adversarially isolated honeypot intelligence (BUILD FOURTH)
**What it does:** Fully airgapped decoy environment. Any interaction is definitionally malicious. Captures attacker TTPs (tactics, techniques, procedures) and feeds learned intelligence back into Layers 1 and 2 via a one-way intelligence pipeline.

**Adversarial isolation:** No network path exists from honeypot to real environment — not even read access. Intelligence export is one-way only (honeypot → intel processor → L1/L2). This ensures an attacker who detects the honeypot cannot use it to probe or poison real defenses.

**Feedback loop:**
- Honeypot captures attacker tool signatures, scan patterns, exploit attempts
- Threat intel processor distills TTPs into defense signals
- Layer 1 gets new firewall rules from captured attack patterns
- Layer 2 tightens rotation schedules based on observed reconnaissance timing

---

## Cross-layer feedback loops

```
L5 honeypot intel → L1 firewall rules (new rules from captured TTPs)
L5 honeypot intel → L2 MTD rotation (tighter schedules from recon patterns)
L4 insider alerts → L1 firewall rules (contain lateral movement in real time)
L2 rotation state → L3 cipher selection (high-rotation phase → lighter cipher)
All layers → configurable thresholds (per-enterprise tuning)
```

---

## Competitive positioning

| Competitor | What they do | Gap your platform fills |
|---|---|---|
| Darktrace | AI anomaly detection | Reactive only — doesn't mutate defenses |
| Vectra AI | Network detection & response | No MTD or active defense mutation |
| SentinelOne | Endpoint protection | Endpoint-focused, not network-layer |
| Morphisec | Moving target at endpoint level | Single-layer MTD only, no AI rule gen or honeypot feedback |
| QuSecure | Post-quantum encryption | Encryption only — no behavioral or MTD layers |

No competitor combines all five layers into a single co-evolving system.

---

## IP and patent status
- Not yet patented — filing is a planned future step
- 7 claim groups covering: full architecture, CSPRNG rotation mechanism, Temporal Defense Layering, adversarial isolation model, configurable threshold system, cross-layer feedback loops, mutable encryption co-evolution
- Key coined term: **Temporal Defense Layering** — multi-layer independent CSPRNG rotation where unpredictability compounds exponentially

---

## Build order and rationale

| Order | Layer | Reason |
|---|---|---|
| 1st | Layer 1 — AI firewall | Easiest to demo, solves a felt pain (manual rule writing), works from day 1 |
| 2nd | Layer 4 — Insider threat | High standalone value, expands TAM, start collecting baseline data during L1 |
| 3rd | Layer 2 — MTD rotation | Core IP and moat, but needs existing customers to sell into |
| 4th | Layer 5 — Honeypot intel | Needs real production deployments to be meaningful |
| 5th | Layer 3 — Mutable encryption | Hardest to explain and sell, needs full platform context |

---

## Go-to-market plan

**Phase 1 — Validate (now → month 3)**
- Talk to 20+ CISOs, IT managers, security leads
- Validate pain: firewall rule ops, insider threats, MTD interest
- Define MVP scope, write 1-page product brief

**Phase 2 — Build MVP (month 3–8)**
- Build Layer 1 with human-in-the-loop mode
- Get 1–2 design partners (college IT dept or startup network)
- Collect east-west traffic logs for Layer 4 baseline

**Phase 3 — Traction + funding (month 8–14)**
- 2–3 paying pilots (~$500/mo)
- Case studies from design partners
- Apply: NASSCOM DeepTech, iHub IIT programs, YC W/S26

**Phase 4 — Scale (month 14+)**
- Build remaining layers in order
- Technical co-founder (security or ML background)
- Seed round with traction evidence

---

## Deployment model
- Cloud-first SaaS for MVP (lower ops overhead for solo founder)
- On-prem/hybrid option added at enterprise tier post-seed
- Multi-tenancy via schema-per-tenant in PostgreSQL for MVP