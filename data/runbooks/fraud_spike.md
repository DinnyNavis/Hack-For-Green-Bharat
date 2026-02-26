# Runbook: Fraud / Payments Error Spike

**Severity:** CRITICAL  
**Applies to:** payments-service  
**Trigger:** Error count >3× rolling median in 60-second window  
**Last Updated:** 2026-02-01  

---

## Symptoms
- Sudden spike in payment transaction failures
- `Error: Fraud detection triggered` appearing repeatedly
- Alert: `FRAUD_SPIKE` from anomaly detector
- Customer complaints about declined legitimate transactions

---

## Immediate Actions

### Step 1 — Triage (0–2 min)
Determine if this is a **fraud attack** or a **false positive** from the fraud engine:
- Check fraud dashboard for flagged transaction patterns
- Are the declined cards from a single BIN range or geographic location?
- Is this affecting VIP/verified accounts? (More likely false positive)

### Step 2 — Contain the Attack (if genuine fraud)
```bash
# Block suspicious IP ranges via WAF rule
# Example: Cloudflare API
curl -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/firewall/rules" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -d '{"filter":{"expression":"ip.src in {10.0.0.0/8}"},"action":"block"}'
```

1. Enable enhanced 3DS authentication for **all** transactions
2. Rate-limit transactions to max 3/minute per user account
3. Block transactions from flagged IP CIDR ranges
4. Pause auto-approval for transactions above $500

### Step 3 — Reduce False Positives (if fraud engine over-triggering)
1. Temporarily raise fraud score threshold from 0.7 → 0.9
2. Add manual review queue for borderline scores (0.8–0.9)
3. Check if fraud model was recently retrained with bad data

### Step 4 — Notify Stakeholders
- **Immediately**: Fraud Operations team via `#fraud-ops` Slack
- **Within 5 min**: Finance team if transaction volume drop >$100K/hour
- **Within 10 min**: Compliance officer if regulatory reporting required

---

## Investigation Queries
```sql
-- Top declined transaction reasons in last hour
SELECT decline_reason, count(*) 
FROM transactions 
WHERE status = 'DECLINED' AND created_at > NOW() - INTERVAL '1 hour'
GROUP BY decline_reason ORDER BY count DESC;

-- Geographic distribution of failures by country
SELECT country_code, count(*) FROM transactions
WHERE status = 'DECLINED' AND created_at > NOW() - INTERVAL '30 minutes'
GROUP BY country_code ORDER BY count DESC;
```

---

## Escalation
- Confirmed fraud attack → P0 Security Incident → CISO notification
- Estimated loss >$50K → Executive notification required
- Customer complaints on social media → PR team alert
