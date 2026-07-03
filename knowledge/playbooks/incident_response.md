# Incident Response Playbooks

How the platform responds to each threat type. 
Reference when building detection logic and alert tiers.

---

## Playbook 001 — Port scan detected

**Trigger:** Isolation Forest flags SYN rate > 50/sec from single source IP over 60 seconds.

**Automated response (Layer 1):**
1. Generate rate-limiting rule: allow max 10 SYN/sec from src IP
2. Sandbox test against last 10 min of traffic
3. If FP rate < 5%: submit for human approval
4. If FP rate ≥ 5%: discard, log, alert analyst

**Human action required:**
- Review rule in dashboard
- Check if src IP is internal security scanner (whitelist if so)
- Approve or reject

**Resolution:** Rule promoted → source rate-limited. If scan continues: escalate to full block.

---

## Playbook 002 — DNS tunneling suspected

**Trigger:** DNS query entropy > 3.5 bits/char OR query length > 100 chars OR query rate > 100/min to single external resolver.

**Automated response (Layer 1):**
1. Capture last 50 DNS queries from src IP
2. Generate block rule for high-entropy DNS to external resolvers
3. Allow DNS to internal/whitelisted resolvers only
4. Sandbox test
5. Submit for human approval

**Human action required:**
- Verify the flagged DNS queries are not legitimate (DNSSEC, CDN, etc.)
- Check if src IP is known internal tool using DNS-based service discovery
- Approve or reject

---

## Playbook 003 — Lateral movement detected (Layer 4)

**Trigger:** Workstation initiates SMB connection to another workstation (baseline violation). Or: authentication from new IP for existing user at anomalous hour.

**Alert tier:** HIGH — immediate SOC notification.

**Automated response:**
1. Flag session in dashboard with HIGH severity
2. Log full packet capture of the lateral connection
3. Generate firewall rule to block workstation-to-workstation SMB
4. Notify security team via WebSocket alert (real-time)

**Human action required:**
- Investigate src workstation immediately
- Check if user is currently at work or credential may be compromised
- If confirmed malicious: isolate src workstation from network
- Revoke credentials

---

## Playbook 004 — Data staging detected (Layer 4)

**Trigger:** Machine writes > 10GB to single directory within 30 minutes (baseline: < 1GB/hour).
OR: Large internal transfer to previously unaccessed file server.

**Alert tier:** CRITICAL — automatic session flag + notify SOC.

**Automated response:**
1. Flag user/machine session immediately
2. Generate firewall rule to block outbound traffic from src IP > 100MB/hour
3. Alert SOC via WebSocket with CRITICAL severity
4. Log full transfer metadata (src, dst, volume, file types if accessible)

**Human action required:**
- Determine if transfer is legitimate (backup job, migration)
- If malicious: kill session, isolate machine, preserve forensic evidence
- Begin incident response process

---

## Alert severity tiers

| Tier | Colour | Response time | Auto-action |
|---|---|---|---|
| INFO | Blue | Review next business day | Log only |
| LOW | Yellow | Review within 24 hours | Log + queue rule |
| MEDIUM | Orange | Review within 4 hours | Log + queue rule + notify |
| HIGH | Red | Review within 1 hour | Log + queue rule + notify SOC |
| CRITICAL | Purple | Immediate | Log + session flag + notify SOC + block outbound |