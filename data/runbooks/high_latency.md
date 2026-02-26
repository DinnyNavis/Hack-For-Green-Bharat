# Runbook: High Latency

**Severity:** WARNING / CRITICAL  
**Applies to:** All services  
**Threshold:** WARNING avg >500ms | CRITICAL avg >2000ms  
**Last Updated:** 2026-02-01  

---

## Symptoms
- Response times exceed SLA thresholds
- P95 latency charts trending upward
- Clients experiencing slow transactions
- Alert: `HIGH_LATENCY` from anomaly detector

---

## Immediate Actions

1. **Identify latency source** — application, database, or network?
   ```bash
   # Check database query times
   SELECT query, mean_exec_time, calls 
   FROM pg_stat_statements 
   ORDER BY mean_exec_time DESC LIMIT 10;
   ```

2. **Check for GC / memory pressure**
   ```bash
   # Check container resource usage
   docker stats --no-stream
   # Look for containers with high MEM % or frequent GC pauses in logs
   ```

3. **Profile active requests** (if APM is available)
   - Open Jaeger/Zipkin for distributed traces
   - Find spans with unusually long durations
   - Check which service segment is slowest

4. **Enable response caching** for idempotent endpoints
   - Add `Cache-Control` headers for read-heavy routes
   - Enable Redis caching tier if configured

5. **Add database indexes** for slow queries
   ```sql
   -- Find missing indexes
   SELECT schemaname, tablename, attname, n_distinct, correlation
   FROM pg_stats WHERE tablename = '<slow_table>';
   
   CREATE INDEX CONCURRENTLY idx_<table>_<column> ON <table>(<column>);
   ```

---

## Service-Specific Notes

| Service | Common Cause | Quick Fix |
|---------|-------------|-----------|
| trading-service | Market data feed backlog | Restart market data connector |
| payments-service | Gateway timeout | Retry with exponential backoff |
| banking-app | Complex account queries | Use read replica |
| auth-service | Token validation overhead | Enable JWT caching |

---

## Escalation
- P95 > 5000ms for any customer-facing endpoint → P1
- Latency increase correlates with revenue drop → Notify finance team
