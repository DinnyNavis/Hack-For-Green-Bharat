# Post-Mortem: Payments Service Outage — 2026-01-15

**Incident ID:** INC-2026-001  
**Severity:** P1  
**Duration:** 47 minutes (09:14 – 10:01 UTC)  
**Services Affected:** payments-service, trading-service (partial)  
**Revenue Impact:** ~$2.3M in delayed transactions  

---

## Summary
A database connection pool exhaustion event caused the payments-service to return 503 errors for 47 minutes. The root cause was a missing index on the `transactions` table introduced in deployment v2.4.1, causing queries to perform full table scans under load.

---

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 09:12 | Deployment v2.4.1 pushed to production |
| 09:14 | Error rate begins climbing (5% → 30% over 3 minutes) |
| 09:17 | Anomaly detection alert sent to `#sre-alerts` |
| 09:22 | On-call engineer acknowledges — begins investigation |
| 09:35 | Root cause identified: slow query on `transactions.created_at` |
| 09:42 | `CONCURRENTLY` index creation started |
| 10:01 | Index creation complete, query times normalise, error rate returns to baseline |
| 10:15 | All-clear declared |

---

## Root Cause
New analytics query introduced in `payments-service` v2.4.1 performed a filter on `transactions.created_at` without an index. Under production load (~800 req/s), this caused:
1. Full sequential scans on 50M-row table
2. Query times increasing from 10ms → 45,000ms
3. Connection pool (50 connections) fully held by blocking queries
4. New requests timing out → 503 errors

---

## Contributing Factors
- No query performance testing in staging (staging has 10K rows vs 50M in prod)
- Deployment occurred during peak trading hours (09:00–11:00 UTC not blacklisted)
- Circuit breaker not configured for database timeouts above 5s

---

## Resolution
```sql
CREATE INDEX CONCURRENTLY idx_transactions_created_at 
ON transactions(created_at DESC);
```
This reduced query time from 45,000ms → 8ms, restoring normal operation.

---

## Action Items

| Action | Owner | Due Date | Status |
|--------|-------|----------|--------|
| Add query performance CI check with production-scale data sample | Platform Team | 2026-01-22 | Done |
| Blacklist 09:00–11:00 UTC as deployment window | DevOps | 2026-01-17 | Done |
| Configure circuit breaker with 5s DB timeout | payments-service team | 2026-01-20 | Done |
| Add index coverage check to database migration linting | DB Team | 2026-01-29 | In Progress |
| Reduce anomaly detection window from 5 min to 60s | SRE | 2026-01-18 | Done |

---

## What Went Well
- Anomaly detection alerted within 3 minutes of error rate increase
- On-call engineer had correct runbook available
- Database team resolved quickly once root cause was identified

## What Could Be Improved
- Anomaly detection was previously 5-minute windows — now reduced to 60s
- Need canary deployment strategy for database-touching changes
