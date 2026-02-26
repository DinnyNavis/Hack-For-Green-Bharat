"""
Pathway 0.15.x Pipeline - Stable Production Version
"""
import json
import logging
import os
import sys
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

import pathway as pw
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(__file__))
from anomaly_detector import detect, metrics_to_json
from llm_rag import analyze
from schemas import Thresholds

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
TOPIC        = "service-logs"
OUTPUT_PATH  = os.getenv("OUTPUT_PATH", "/app/output/alerts.jsonl")
WINDOW_S     = Thresholds.WINDOW_SECONDS

# State managed within the process
_windows: dict[str, deque] = defaultdict(deque)
_last_emit: dict[str, datetime] = {}

@pw.udf
def process_event(data: bytes) -> pw.Json:
    try:
        msg = json.loads(data.decode("utf-8"))
    except:
        return {"is_alert": False}

    service = msg.get("service", "unknown")
    level = msg.get("level", "INFO")
    latency = float(msg.get("latency_ms", 0))
    now = datetime.now(timezone.utc)

    # Rolling Window
    win = _windows[service]
    cutoff = now - timedelta(seconds=WINDOW_S)
    while win and win[0]["ts"] < cutoff: win.popleft()
    win.append({"ts": now, "level": level, "latency": latency})

    # Alert Cooldown (Restored to 60s for stability)
    last = _last_emit.get(service, datetime.min.replace(tzinfo=timezone.utc))
    if (now - last).total_seconds() < 60: return {"is_alert": False}
    if len(win) < 5: return {"is_alert": False}

    # Stat Computation
    errors = sum(1 for e in win if e["level"] in ("ERROR", "CRITICAL"))
    lats = sorted(e["latency"] for e in win)
    avg_lat = sum(lats) / len(lats)
    p95_lat = float(lats[max(0, int(len(lats) * 0.95) - 1)])
    err_rate = errors / len(win) * 100.0
    
    res = detect(service, len(win), errors, err_rate, avg_lat, p95_lat)
    if not res.is_anomaly: return {"is_alert": False}

    _last_emit[service] = now
    m_json = metrics_to_json(service, win[0]["ts"].isoformat(), len(win), errors, err_rate, avg_lat, p95_lat)
    
    log.info("🚨 ALERT DETECTED: %s | %s", service, res.anomaly_type)

    try:
        rc, rm = analyze(service, res.anomaly_type, res.severity, m_json, res.runbook_name)
    except:
        rc, rm = "LLM Enrichment Failed", f"Refer to {res.runbook_name}"

    return {
        "is_alert": True,
        "alert_id": str(uuid.uuid4()),
        "detected_at": now.isoformat(),
        "service": service,
        "anomaly_type": res.anomaly_type,
        "severity": res.severity,
        "metrics_json": m_json,
        "root_cause": rc,
        "remediation": rm,
        "runbook_name": res.runbook_name
    }

def run_pipeline():
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    try:
        # 1. Source
        logs = pw.io.kafka.read(
            rdkafka_settings={
                "bootstrap.servers":  KAFKA_BROKER,
                "group.id":           "finlog-monitor-consumer",
                "auto.offset.reset":  "latest",
            },
            topic=TOPIC,
            format="raw"
        )

        # 2. Process
        t_processed = logs.select(res=process_event(pw.this.data))
        
        # 3. Filter
        # CRITICAL FIX: Coalesce the Optional(BOOL) from JSON into a strict BOOL
        t_alerts = t_processed.filter(pw.coalesce(t_processed.res["is_alert"].as_bool(), False))

        # 4. Final Table
        t_final = t_alerts.select(
            alert_id     = t_alerts.res["alert_id"].as_str(),
            detected_at  = t_alerts.res["detected_at"].as_str(),
            service      = t_alerts.res["service"].as_str(),
            anomaly_type = t_alerts.res["anomaly_type"].as_str(),
            severity     = t_alerts.res["severity"].as_str(),
            metrics_json = t_alerts.res["metrics_json"].as_str(),
            root_cause   = t_alerts.res["root_cause"].as_str(),
            remediation  = t_alerts.res["remediation"].as_str(),
            runbook_name = t_alerts.res["runbook_name"].as_str()
        )

        # 5. Sink
        pw.io.jsonlines.write(t_final, OUTPUT_PATH)
        
        log.info("🚀 Pipeline components initialized. Starting pw.run()...")
        pw.run(monitoring_level=pw.MonitoringLevel.NONE)
    except Exception as e:
        log.error("CRITICAL ERROR IN PIPELINE:\n%s", str(e))
        sys.exit(1)

if __name__ == "__main__":
    run_pipeline()
