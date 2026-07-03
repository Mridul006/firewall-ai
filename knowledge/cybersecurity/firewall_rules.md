# Firewall Rule Syntax Reference

Reference for the rule formats Layer 1 generates.
The AI rule generator must output valid syntax from these formats.

---

## iptables (Linux)

### Basic structure
```
iptables -[A/I/D] [CHAIN] [MATCHES] -j [TARGET]
```

### Common chains
- INPUT — traffic destined for the local machine
- OUTPUT — traffic originating from the local machine
- FORWARD — traffic passing through (router mode)

### Common targets
- ACCEPT — allow the packet
- DROP — silently discard
- REJECT — discard and send error back to sender
- LOG — log to syslog then continue to next rule

### Example rules our AI should generate

```bash
# Block port scan from specific IP
iptables -A INPUT -s 192.168.1.100 -j DROP

# Rate limit SYN packets (anti-scan)
iptables -A INPUT -p tcp --syn -m limit --limit 1/s --limit-burst 3 -j ACCEPT
iptables -A INPUT -p tcp --syn -j DROP

# Block DNS tunneling (high-entropy DNS to external)
iptables -A OUTPUT -p udp --dport 53 -m string --algo bm --string "AAAAAAAAAA" -j DROP

# Allow established connections only (stateful)
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -m state --state NEW -j DROP

# Log and drop suspicious fragmented packets
iptables -A INPUT -f -j LOG --log-prefix "FRAGMENT: "
iptables -A INPUT -f -j DROP

# Rate limit ICMP (anti-ping flood)
iptables -A INPUT -p icmp --icmp-type echo-request -m limit --limit 1/s -j ACCEPT
iptables -A INPUT -p icmp --icmp-type echo-request -j DROP
```

### Rule output format from Claude API
When the AI generates a rule, it must output:
```json
{
  "syntax": "iptables",
  "command": "iptables -A INPUT -s {src_ip} -p tcp --dport {port} -j DROP",
  "description": "Block suspicious SYN flood from {src_ip} targeting port {port}",
  "mitre_technique": "T1498.001",
  "confidence": 0.87,
  "false_positive_risk": "low"
}
```

---

## pf (BSD / macOS)

### Basic structure
```
[action] [direction] [interface] [protocol] [source] [destination] [options]
```

### Example rules

```
# Block port scanner
block in quick from 192.168.1.100

# Rate limit SYN (scrub + limit)
scrub in all
block in quick proto tcp from any to any flags S/SA keep state \
  (max-src-conn-rate 100/10)

# Allow established only
pass in proto tcp from any to any flags S/SA keep state
block in proto tcp from any to any

# Block DNS tunneling
block out proto udp to any port 53 \
  payload-size > 512
```

---

## Rule validation checklist (used by FP scorer)

Before promoting any generated rule to production, verify:

1. **Syntax valid** — rule parses without error in test environment
2. **Not overly broad** — rule does not block entire subnets without justification
3. **False positive rate < 5%** — tested against 10 minutes of real traffic replay
4. **Legitimate traffic unaffected** — HTTP/HTTPS, DNS, internal services still pass
5. **Reversible** — rule can be removed with single command (no persistent state side effects)
6. **Logged** — rule includes LOG target before DROP for audit trail
7. **Tagged** — rule description includes MITRE ATT&CK technique ID

---

## Common false positive patterns to watch for

- Blocking legitimate port scanners (security teams run their own scans)
- Rate limiting that affects video conferencing (high UDP volume is normal for Zoom/Teams)
- Blocking high-entropy DNS that is actually DNSSEC traffic
- Fragment rules that break legitimate large packet applications (NFS, iSCSI)
- Rules targeting private IP ranges that are used legitimately internally