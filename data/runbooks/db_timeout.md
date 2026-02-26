# Runbook: Database Connection Timeout

**Severity:** CRITICAL  
**Applies to:** trading-service, banking-app, payments-service  
**Last Updated:** 2026-02-01  

---

## Symptoms
- `Error: Database connection timeout after 30s` appearing in logs
- Error rate spike on affected service (>10%)
- Average latency exceeds 2000ms
- Health checks returning 503

---

## Immediate Actions (First 5 minutes)

1. **Check connection pool exhaustion**
   ```bash
   # Check active connections vs pool limit
   SELECT count(*), state FROM pg_stat_activity GROUP BY state;
   ```
   - If `active` count equals pool max → increase pool size or terminate long-running queries

2. **Kill long-running queries blocking connections**
   ```sql
   SELECT pid, now() - pg_stat_activity.query_start AS duration, query
   FROM pg_stat_activity
   WHERE state != 'idle' AND (now() - pg_stat_activity.query_start) > interval '30 seconds';
   
   SELECT pg_terminate_backend(pid) FROM pg_stat_activity 
   WHERE duration > interval '60 seconds';
   ```

3. **Check database host resource utilisation**
   - CPU > 90%? → Scale up database instance
   - Disk I/O saturated? → Check for missing indexes

4. **Increase connection timeout temporarily** (config hot-reload if supported)
   ```yaml
   db:
     pool_timeout: 60  # increase from 30
     pool_size: 50     # increase from 20
   ```

5. **Activate read replica for non-write traffic**
   - Route `SELECT` queries to replica endpoint
   - Update `DB_READ_HOST` environment variable + rolling restart

---

## Escalation
- **5 min — no improvement**: Page database team (PagerDuty: `#db-oncall`)
- **10 min — service down**: Declare P1 incident, notify VP Engineering
- **15 min — no ETA**: Initiate failover to DR database cluster

---

## Root Cause Categories

| Pattern | Likely Cause |
|---------|-------------|
| Spike correlates with deploy | New query introduced without index |
| Gradual increase | Connection leak in application code |
| Sudden spike, all services | Database host failure / network partition |
| Single service only | Service-level config or code regression |

---

## Post-Incident
- Add database connection pool metrics to alerting
- Review slow query log (`pg_stat_statements`)
- File post-mortem within 24 hours
