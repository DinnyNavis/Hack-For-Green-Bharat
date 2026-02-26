"""
Rule-based and statistical anomaly detector for windowed log metrics.
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict, deque
from typing import NamedTuple

from schemas import Thresholds


class DetectionResult(NamedTuple):
    is_anomaly: bool
    anomaly_type: str   # empty string if not anomaly
    severity: str       # WARNING | CRITICAL | ""
    runbook_name: str   # filename hint for RAG lookup


# Rolling baseline per service: keep last N window error-rate samples
_BASELINE_WINDOW = 10
_baselines: dict[str, deque] = defaultdict(lambda: deque(maxlen=_BASELINE_WINDOW))


def detect(
    service: str,
    total_requests: int,
    error_count: int,
    error_rate: float,
    avg_latency_ms: float,
    p95_latency_ms: float,
) -> DetectionResult:
    """
    Apply threshold rules + rolling-median z-score to classify anomalies.
    Priority order: AUTH_STORM > FRAUD_SPIKE > HIGH_ERROR_RATE > HIGH_LATENCY
    """
    t = Thresholds

    # ── 1. Auth failure storm ─────────────────────────────────────────────────
    if service == "auth-service" and error_count >= t.AUTH_FAILURE_THRESHOLD:
        severity = "CRITICAL" if error_count >= t.AUTH_FAILURE_THRESHOLD * 2 else "WARNING"
        return DetectionResult(True, "AUTH_STORM", severity, "auth_failures.md")

    # ── 2. Fraud spike (payments-service error surge vs rolling median) ────────
    if service == "payments-service":
        baseline = _baselines[service]
        if len(baseline) >= 3:
            median_errors = statistics.median(baseline)
            if median_errors > 0 and error_count > median_errors * 3:
                return DetectionResult(True, "FRAUD_SPIKE", "CRITICAL", "fraud_spike.md")

    # ── 3. High error rate ────────────────────────────────────────────────────
    if error_rate >= t.ERROR_RATE_CRITICAL:
        return DetectionResult(True, "HIGH_ERROR_RATE", "CRITICAL", "high_error_rate.md")
    if error_rate >= t.ERROR_RATE_WARNING:
        return DetectionResult(True, "HIGH_ERROR_RATE", "WARNING", "high_error_rate.md")

    # ── 4. High latency ───────────────────────────────────────────────────────
    if avg_latency_ms >= t.LATENCY_CRITICAL_MS or p95_latency_ms >= t.LATENCY_CRITICAL_MS * 1.5:
        return DetectionResult(True, "HIGH_LATENCY", "CRITICAL", "high_latency.md")
    if avg_latency_ms >= t.LATENCY_WARNING_MS or p95_latency_ms >= t.LATENCY_WARNING_MS * 2:
        return DetectionResult(True, "HIGH_LATENCY", "WARNING", "high_latency.md")

    # Update rolling baseline after checks
    _baselines[service].append(error_count)
    return DetectionResult(False, "", "", "")


def metrics_to_json(
    service: str,
    window_start: str,
    total_requests: int,
    error_count: int,
    error_rate: float,
    avg_latency_ms: float,
    p95_latency_ms: float,
) -> str:
    return json.dumps(
        {
            "service": service,
            "window_start": window_start,
            "total_requests": total_requests,
            "error_count": error_count,
            "error_rate_pct": round(error_rate, 2),
            "avg_latency_ms": round(avg_latency_ms, 2),
            "p95_latency_ms": round(p95_latency_ms, 2),
        }
    )
