"""
Schema definitions and detection threshold constants.
(Pathway-free — plain Python dataclasses used for type documentation.)
"""
import os
from dataclasses import dataclass


# ─── Raw log event arriving from Kafka ──────────────────────────────────────
@dataclass
class RawLogSchema:
    timestamp: str
    service: str
    level: str          # INFO | WARN | ERROR | CRITICAL
    status_code: int
    latency_ms: float
    message: str
    trace_id: str
    endpoint: str


# ─── Per-service windowed metrics (output of aggregation) ────────────────────
@dataclass
class WindowMetricsSchema:
    window_start: str
    service: str
    total_requests: int
    error_count: int
    error_rate: float       # 0.0–100.0
    avg_latency_ms: float
    p95_latency_ms: float


# ─── Anomaly alert produced by the detector ──────────────────────────────────
@dataclass
class AnomalyAlertSchema:
    alert_id: str
    detected_at: str
    service: str
    anomaly_type: str   # HIGH_ERROR_RATE | HIGH_LATENCY | FRAUD_SPIKE | AUTH_STORM
    severity: str       # WARNING | CRITICAL
    metrics_json: str   # serialised WindowMetrics snapshot
    root_cause: str     # LLM / rule-based analysis
    remediation: str    # RAG + LLM recommended steps
    runbook_name: str   # name of matched runbook file


# ─── Detection thresholds (overridable via environment) ──────────────────────
class Thresholds:
    ERROR_RATE_WARNING  = float(os.getenv("ERROR_RATE_WARNING_PCT",  "10"))
    ERROR_RATE_CRITICAL = float(os.getenv("ERROR_RATE_CRITICAL_PCT", "25"))
    LATENCY_WARNING_MS  = float(os.getenv("LATENCY_WARNING_MS",  "500"))
    LATENCY_CRITICAL_MS = float(os.getenv("LATENCY_CRITICAL_MS", "2000"))
    AUTH_FAILURE_THRESHOLD = int(os.getenv("AUTH_FAILURE_THRESHOLD", "50"))
    WINDOW_SECONDS      = int(os.getenv("WINDOW_SECONDS", "60"))
