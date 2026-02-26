# Runbook: High Error Rate

**Severity:** WARNING / CRITICAL  
**Applies to:** All services  
**Threshold:** WARNING >10% | CRITICAL >25%  
**Last Updated:** 2026-02-01  

---

## Symptoms
- Error rate spike detected in monitoring window
- Increased 5xx status codes in access logs
- Customer-facing transactions failing
- Alert: `HIGH_ERROR_RATE` from anomaly detector

---

## Immediate Actions

1. **Identify error scope** — is it one service or cascade?
   ```bash
   # Check last 5 minutes of errors per service
   docker-compose logs --since 5m | grep -E "ERROR|CRITICAL" | awk '{print $3}' | sort | uniq -c
   ```

2. **Check for recent deployments** (most common cause)
   ```bash
   kubectl rollout history deployment/<service-name>
   # If recent deploy → immediate rollback:
   kubectl rollout undo deployment/<service-name>
   ```

3. **Check downstream dependencies**
   - Is the database reachable? (see `db_timeout.md`)
   - Are external APIs (payment gateways, market data) healthy?
   - Check dependency health dashboards

4. **Enable circuit breaker** to stop cascading failures
   - Set service to return cached/fallback responses
   - Reduce error propagation to client-facing endpoints

5. **Scale horizontally** if under load
   ```bash
   kubectl scale deployment/<service> --replicas=10
   ```

---

## Escalation Triggers
- Error rate >25% for >5 minutes → P1 Incident
- Multiple services affected simultaneously → Cascade failure protocol
- Payment service affected → Immediate fraud/finance team notification

---

## Investigation Checklist
- [ ] Recent code deployment in last 2 hours?
- [ ] Infrastructure changes (node restart, network update)?
- [ ] Third-party service incident (check status pages)?
- [ ] Database degradation?
- [ ] Traffic spike (DDoS or organic)?

---

## Key Logs to Review
```bash
# Pathway anomaly output
cat output/alerts.jsonl | jq 'select(.anomaly_type == "HIGH_ERROR_RATE")'

# Service error patterns
docker-compose logs <service-name> | grep "ERROR" | tail -50
```
