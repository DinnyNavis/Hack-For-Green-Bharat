"""
Pydantic models for FastAPI request/response schemas.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class AlertResponse(BaseModel):
    alert_id: str
    detected_at: str
    service: str
    anomaly_type: str
    severity: str
    metrics_json: str
    root_cause: str
    remediation: str
    runbook_name: str


class ServiceStatus(BaseModel):
    service: str
    status: str           # healthy | warning | critical | unknown
    last_seen: str
    recent_alerts: int


class HealthResponse(BaseModel):
    status: str
    alerts_file_exists: bool
    total_alerts: int
    version: str = "1.0.0"
