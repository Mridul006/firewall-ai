# Competitive Analysis

Reference when pitching, writing copy, or making product decisions.
Update as new competitors or features are discovered.

---

## Direct competitors

### Darktrace
**What they do:** AI-powered network anomaly detection and threat response.
**Strength:** Well-known brand, strong enterprise sales, "Enterprise Immune System" concept.
**Weakness:** Reactive only — detects and alerts but doesn't mutate defenses. No MTD. No AI rule generation. Expensive ($50k+ annually).
**Our edge:** We actively mutate the attack surface (Layer 2). Darktrace watches; we move.

### Vectra AI
**What they do:** Network detection and response (NDR) — detects attacker behaviors post-breach.
**Strength:** Strong east-west detection, good cloud coverage.
**Weakness:** No active defense mutation. No firewall rule automation. No MTD. Detection only.
**Our edge:** Layer 1 automates the response (rule generation), not just detection. Layer 2 prevents reconnaissance from succeeding in the first place.

### SentinelOne
**What they do:** AI-powered endpoint detection and response (EDR).
**Strength:** Strong endpoint agent, autonomous response at endpoint level.
**Weakness:** Endpoint-focused — doesn't operate at network layer. No MTD. No firewall rule gen.
**Our edge:** Network-layer defense. Complements SentinelOne rather than competing directly — potential integration opportunity.

### Morphisec
**What they do:** Moving target defense at the endpoint level — randomizes memory layout to prevent exploit execution.
**Strength:** First mover in MTD, strong patent portfolio.
**Weakness:** Single-layer MTD (memory only). No network-level MTD. No AI rule generation. No honeypot intelligence.
**Our edge:** Multi-layer independent rotation (Temporal Defense Layering) vs. their single-layer approach. Our MTD operates at network layer, not just endpoint.

### QuSecure
**What they do:** Post-quantum encryption — migrating enterprise crypto to quantum-resistant algorithms.
**Strength:** First mover in post-quantum space, strong government contracts.
**Weakness:** Encryption only — no detection, no response, no MTD, no behavioral monitoring.
**Our edge:** Layer 3 (mutable encryption) covers the post-quantum angle as one component of a full-stack defense platform. QuSecure sells a single layer; we sell five.

---

## Adjacent tools (not direct competitors but relevant)

### Snort / Suricata (open source IDS/IPS)
These are what we build ON TOP of, not compete with. Suricata is used in our ingestion layer for traffic capture. We add AI-driven rule generation on top of what these tools do manually.

### pfSense / OPNsense (open source firewall)
Target customer's existing firewall. Our product generates rules FOR these firewalls. Integration opportunity — not competition.

### CrowdStrike Falcon
EDR + threat intelligence. Strong brand. Competes with SentinelOne at endpoint. Our network-layer positioning complements rather than competes.

---

## Positioning statement
"Where Darktrace detects and alerts, we detect, generate, test, and deploy — autonomously. Where Morphisec moves one target, we move four simultaneously on independent schedules, compounding unpredictability exponentially."

---

## Pricing benchmarks
- Darktrace: $30,000–$150,000/year (enterprise)
- Vectra AI: $50,000–$200,000/year (enterprise)
- SentinelOne: $6–$15/endpoint/month
- Morphisec: $8–$20/endpoint/month

**Our target MVP pricing:** $500–$2,000/month per customer (SME tier). Enterprise tier post-seed: $20,000–$80,000/year.