# Attack Techniques Reference

Key attack patterns this platform is designed to detect and defend against.
Update as new techniques are researched. Reference when building detection logic.

---

## Network reconnaissance

### Port scanning
**What it is:** Attacker systematically probes ports to map open services.
**Tools used:** Nmap, Masscan, Zmap
**Signatures:** High volume of SYN packets to sequential or random ports from single source. Low TTL values. ICMP unreachable responses at high rate.
**How Layer 1 catches it:** Isolation Forest flags abnormal SYN rate from single IP. Rule generated to rate-limit or block source.
**How Layer 2 defends:** Port rotation means scan results are stale within minutes. Attacker maps port 443 → service moves to port 51234.

### OS fingerprinting
**What it is:** Attacker identifies OS and service versions to select targeted exploits.
**Tools used:** Nmap -O, p0f, Xprobe2
**Signatures:** Unusual TCP flag combinations (FIN probe, NULL probe, XMAS probe). Specific ICMP echo request patterns.
**How Layer 2 defends:** Service fingerprint rotation spoofs OS/banner. Attacker detects "Ubuntu 22.04 + Apache 2.4" → system presents "Windows Server 2019 + IIS 10".

---

## Lateral movement (east-west)

### Pass the Hash
**What it is:** Attacker reuses captured NTLM hash to authenticate without knowing plaintext password.
**Signatures:** Authentication from unusual source IP. Same credential used from multiple machines simultaneously. Authentication at unusual hours.
**How Layer 4 catches it:** Behavioral baseline per user — authentication from new IP or at 3am triggers alert.

### SMB lateral movement
**What it is:** Attacker uses SMB protocol to move between Windows machines inside network.
**Tools used:** PsExec, CobaltStrike, Impacket
**Signatures:** SMB connections between workstations (not workstation → server). Admin share access (C$, ADMIN$). Service creation via SMB.
**How Layer 4 catches it:** Baseline shows workstations never connect to each other via SMB. Deviation triggers high-severity alert.

### Living off the land (LotL)
**What it is:** Attacker uses legitimate built-in tools (PowerShell, WMI, certutil) to avoid detection.
**Tools used:** PowerShell, WMIC, certutil, mshta, regsvr32
**Signatures:** PowerShell executing encoded commands. WMI remote process creation. certutil downloading files.
**How Layer 4 catches it:** Process execution baseline per machine. Encoded PowerShell from unexpected process parent triggers alert.

---

## Exfiltration

### DNS tunneling
**What it is:** Attacker encodes data inside DNS queries to exfiltrate without triggering data loss prevention.
**Tools used:** dnscat2, iodine, dns2tcp
**Signatures:** Abnormally long DNS query names. High volume of TXT record queries. DNS queries to unusual domains. DNS query entropy significantly above baseline.
**How Layer 1 catches it:** Isolation Forest flags DNS query volume and entropy anomalies. Rule blocks high-entropy DNS to unknown resolvers.

### Data staging
**What it is:** Attacker aggregates target data in one location before exfiltration.
**Signatures:** Sudden large internal file transfers. Compression activity (zip, rar, 7z) on unusual machines. Large writes to a single directory over short period.
**How Layer 4 catches it:** Volume anomaly detection — machine suddenly writing 50GB to a directory it never accessed before.

---

## Firewall evasion

### IP fragmentation
**What it is:** Attacker splits malicious payload across multiple IP fragments to bypass inspection.
**Signatures:** Abnormal fragment sizes. Overlapping fragments. Fragments arriving out of order.
**How Layer 1 catches it:** Rule generated to reassemble and inspect fragmented packets before allowing through.

### Slow-rate attacks
**What it is:** Attacker spreads attack traffic over long time period to stay below per-minute detection thresholds.
**Tools used:** Slowloris, R-U-Dead-Yet (RUDY)
**Signatures:** Long-lived HTTP connections with minimal data. Open connections that never complete.
**How Layer 1 catches it:** Isolation Forest trained on connection duration and throughput ratio — slow connections with no data flagged as anomalous.

---

## Key frameworks to understand

### MITRE ATT&CK
The industry standard taxonomy for attacker tactics, techniques, and procedures.
Reference: https://attack.mitre.org
Every detection rule should be tagged with its ATT&CK technique ID (e.g., T1046 for port scanning).

### Cyber Kill Chain (Lockheed Martin)
7 stages: Reconnaissance → Weaponization → Delivery → Exploitation → Installation → C2 → Actions on Objectives.
Layers 1-5 map roughly to disrupting stages 1, 3, 5, 6, and 7.

### Diamond Model
Framework for analyzing intrusions: Adversary, Capability, Infrastructure, Victim.
Useful for structuring honeypot intelligence reports (Layer 5).