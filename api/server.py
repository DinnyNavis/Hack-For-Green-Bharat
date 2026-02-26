"""
FastAPI backend for the log monitoring system.
Provides REST endpoints for alerts and metrics, plus a WebSocket
endpoint that pushes new anomaly alerts to the live dashboard.
"""
from __future__ import annotations

import asyncio
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from models import AlertResponse, ServiceStatus, HealthResponse

app = FastAPI(
    title="FinLog Anomaly Monitor API",
    description="Real-time financial log anomaly detection and alerting system",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ALERTS_PATH = Path(os.getenv("ALERTS_PATH", "/app/output/alerts.jsonl"))
SERVICES = ["trading-service", "payments-service", "banking-app", "auth-service"]

# ─── WebSocket connection manager ────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)

    async def broadcast(self, message: str):
        dead = []
        for ws in self.active:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


def _load_alerts(
    service: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 100,
) -> list[dict]:
    if not ALERTS_PATH.exists():
        return []
    alerts = []
    try:
        with ALERTS_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    alert = json.loads(line)
                    if service and alert.get("service") != service:
                        continue
                    if severity and alert.get("severity") != severity:
                        continue
                    alerts.append(alert)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    # Return newest-first, limited
    return alerts[-limit:][::-1]


# ─── REST Endpoints ──────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    alerts = _load_alerts(limit=10000)
    return HealthResponse(
        status="ok",
        alerts_file_exists=ALERTS_PATH.exists(),
        total_alerts=len(alerts),
    )


@app.get("/alerts", response_model=list[AlertResponse], tags=["Alerts"])
async def get_alerts(
    service: Optional[str] = Query(None, description="Filter by service name"),
    severity: Optional[str] = Query(None, description="WARNING or CRITICAL"),
    limit: int = Query(50, ge=1, le=500),
):
    """Return recent anomaly alerts, newest first."""
    return _load_alerts(service=service, severity=severity, limit=limit)


@app.get("/alerts/{alert_id}", response_model=AlertResponse, tags=["Alerts"])
async def get_alert_by_id(alert_id: str):
    """Return a single alert by its ID."""
    for alert in _load_alerts(limit=10000):
        if alert.get("alert_id") == alert_id:
            return alert
    return JSONResponse(status_code=404, content={"detail": "Alert not found"})


@app.get("/runbooks/{filename}", tags=["System"])
async def get_runbook(filename: str):
    """Serve runbook markdown content."""
    runbook_path = Path("/app/data/runbooks") / filename
    if not runbook_path.exists():
        return JSONResponse(status_code=404, content={"detail": "Runbook not found"})
    
    with open(runbook_path, "r", encoding="utf-8") as f:
        content = f.read()
    return {"content": content}


@app.get("/services", response_model=list[ServiceStatus], tags=["Services"])
async def get_services():
    """Return current status of all monitored services."""
    all_alerts = _load_alerts(limit=500)
    now = datetime.now(timezone.utc).isoformat()

    service_alerts = defaultdict(list)
    for a in all_alerts:
        service_alerts[a.get("service", "unknown")].append(a)

    result = []
    for svc in SERVICES:
        alerts = service_alerts.get(svc, [])
        recent = [a for a in alerts[:10]]  # last 10 alerts

        if not recent:
            status = "healthy"
        elif any(a["severity"] == "CRITICAL" for a in recent[:3]):
            status = "critical"
        elif any(a["severity"] == "WARNING" for a in recent[:5]):
            status = "warning"
        else:
            status = "healthy"

        last_seen = recent[0]["detected_at"] if recent else now
        result.append(
            ServiceStatus(
                service=svc,
                status=status,
                last_seen=last_seen,
                recent_alerts=len(recent),
            )
        )
    return result


@app.get("/metrics", tags=["Metrics"])
async def get_metrics(service: Optional[str] = Query(None)):
    """Return aggregated metrics per service from recent alerts."""
    alerts = _load_alerts(service=service, limit=200)
    service_data: dict[str, dict] = defaultdict(
        lambda: {"critical": 0, "warning": 0, "types": defaultdict(int)}
    )
    for a in alerts:
        svc = a.get("service", "unknown")
        sev = a.get("severity", "")
        atype = a.get("anomaly_type", "")
        if sev == "CRITICAL":
            service_data[svc]["critical"] += 1
        elif sev == "WARNING":
            service_data[svc]["warning"] += 1
        service_data[svc]["types"][atype] += 1

    return {
        svc: {
            "critical_count": data["critical"],
            "warning_count": data["warning"],
            "anomaly_type_breakdown": dict(data["types"]),
        }
        for svc, data in service_data.items()
    }


# ─── WebSocket — live alert push ─────────────────────────────────────────────

@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    """Push new alerts to connected dashboard clients in real time."""
    await manager.connect(ws)
    last_size = ALERTS_PATH.stat().st_size if ALERTS_PATH.exists() else 0
    try:
        while True:
            await asyncio.sleep(2)
            if not ALERTS_PATH.exists():
                continue
            current_size = ALERTS_PATH.stat().st_size
            if current_size > last_size:
                # Read new lines
                new_alerts = []
                with ALERTS_PATH.open("r", encoding="utf-8") as f:
                    f.seek(last_size)
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                new_alerts.append(json.loads(line))
                            except json.JSONDecodeError:
                                pass
                last_size = current_size
                for alert in new_alerts:
                    await manager.broadcast(json.dumps(alert))
    except WebSocketDisconnect:
        manager.disconnect(ws)


# ─── Startup ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
