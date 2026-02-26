# Runbook: Authentication Failure Storm

**Severity:** CRITICAL  
**Applies to:** auth-service  
**Trigger:** >50 authentication failures in a 60-second window  
**Last Updated:** 2026-02-01  

---

## Symptoms
- Massive spike in 401/403 errors on auth-service
- `Error: Brute-force protection triggered` in logs
- `Error: Invalid credentials` repeated from many IP addresses
- Alert: `AUTH_STORM` from anomaly detector

---

## Immediate Actions

### 1 — Rate-limit the Login Endpoint (0–1 min)
```nginx
# Nginx rate limiting (apply immediately if not in place)
limit_req_zone $binary_remote_addr zone=login:10m rate=5r/m;
limit_req zone=login burst=10 nodelay;
```
Or via API Gateway (Kong/AWS API GW):
```bash
# Kong rate-limit plugin
curl -X POST "http://localhost:8001/services/auth-service/plugins" \
  --data "name=rate-limiting" \
  --data "config.minute=10" \
  --data "config.policy=local"
```

### 2 — Identify Attack Source
```bash
# Top attacking IPs from auth-service logs
docker-compose logs auth-service | grep "Invalid credentials" \
  | grep -oP '\d+\.\d+\.\d+\.\d+' | sort | uniq -c | sort -rn | head -20
```

### 3 — Block Malicious IPs
```bash
# Block top offending IPs at the firewall level
for IP in 1.2.3.4 5.6.7.8; do
  iptables -A INPUT -s $IP -j DROP
done
# OR add to WAF blocklist
```

### 4 — Enable CAPTCHA / Bot Detection
- Redirect `/api/auth/login` to CAPTCHA-gated endpoint
- Enable Cloudflare Bot Management or AWS WAF bot control

### 5 — Check for Credential Stuffing
- Are attackers using known leaked credential lists?
- Check haveibeenpwned API for breached email patterns
- Consider forcing password reset for targeted accounts

---

## Credential Stuffing Pattern Recognition

| Pattern | Indicator |
|---------|-----------|
| Same password, many users | Credential stuffing |
| Many passwords, one user | Brute force |
| Distributed IPs, one user | Botnet account takeover |
| Spike then stop | Probing / reconnaissance |

---

## Escalation
- If accounts show signs of successful compromise → Security Incident P0
- If attack persists >15 min despite rate limiting → Engage DDoS mitigation service
- Notify Security team within 2 minutes of confirmation
- Regulatory notification if PII breach suspected (GDPR: 72h window)

---

## Post-Incident
- Enforce MFA for all user accounts
- Implement passwordless login (WebAuthn)
- Subscribe to breach notification feeds
- File incident report within 24h
