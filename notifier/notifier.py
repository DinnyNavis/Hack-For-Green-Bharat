"""
Alert notifier — polls the alerts JSONL file for new CRITICAL / WARNING alerts
and dispatches them via Slack webhook and SMTP email.
Deduplicates by alert_id to avoid repeat notifications.
"""
from __future__ import annotations

import json
import os
import smtplib
import time
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ALERTS_PATH = Path(os.getenv("ALERTS_PATH", "/app/output/alerts.jsonl"))
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_CHANNEL = os.getenv("SLACK_CHANNEL", "#sre-alerts")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO", "")
POLL_INTERVAL_S = 3

# Severity → notification channel mapping
NOTIFY_SLACK = {"CRITICAL", "WARNING"}
NOTIFY_EMAIL = {"CRITICAL"}

_seen_alert_ids: set[str] = set()

SEVERITY_EMOJI = {
    "CRITICAL": "🔴",
    "WARNING": "🟡",
}

ANOMALY_TYPE_LABEL = {
    "HIGH_ERROR_RATE": "High Error Rate",
    "HIGH_LATENCY": "High Latency",
    "FRAUD_SPIKE": "Fraud Spike ⚠️",
    "AUTH_STORM": "Auth Failure Storm",
}


def _send_slack(alert: dict) -> bool:
    if not SLACK_WEBHOOK_URL or SLACK_WEBHOOK_URL.startswith("https://hooks.slack.com/services/YOUR"):
        print(f"[Notifier] ⏭️  Slack not configured — skipping {alert['alert_id']}")
        return False

    emoji = SEVERITY_EMOJI.get(alert["severity"], "⚪")
    atype = ANOMALY_TYPE_LABEL.get(alert["anomaly_type"], alert["anomaly_type"])
    metrics = json.loads(alert.get("metrics_json", "{}"))

    payload = {
        "channel": SLACK_CHANNEL,
        "username": "FinLog Anomaly Monitor",
        "icon_emoji": ":rotating_light:",
        "attachments": [
            {
                "color": "#FF0000" if alert["severity"] == "CRITICAL" else "#FFA500",
                "title": f"{emoji} {alert['severity']}: {atype} — {alert['service']}",
                "text": alert.get("root_cause", "")[:500],
                "fields": [
                    {"title": "Error Rate", "value": f"{metrics.get('error_rate_pct', 0)}%", "short": True},
                    {"title": "Avg Latency", "value": f"{metrics.get('avg_latency_ms', 0)} ms", "short": True},
                    {"title": "Errors", "value": f"{metrics.get('error_count', 0)} / {metrics.get('total_requests', 0)}", "short": True},
                    {"title": "Runbook", "value": alert.get("runbook_name", "N/A"), "short": True},
                ],
                "footer": f"Alert ID: {alert['alert_id']} | {alert['detected_at']}",
            }
        ],
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            SLACK_WEBHOOK_URL,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status == 200:
                print(f"[Notifier] 💬 Slack notification sent for {alert['alert_id']}")
                return True
            return False
    except Exception as e:
        print(f"[Notifier] ❌ Slack send failed: {e}")
        return False


def _send_email(alert: dict) -> bool:
    if not all([SMTP_USER, SMTP_PASS, ALERT_EMAIL_TO]):
        print(f"[Notifier] ⏭️  Email not configured — skipping {alert['alert_id']}")
        return False

    emoji = SEVERITY_EMOJI.get(alert["severity"], "⚪")
    atype = ANOMALY_TYPE_LABEL.get(alert["anomaly_type"], alert["anomaly_type"])
    metrics = json.loads(alert.get("metrics_json", "{}"))

    subject = f"{emoji} [{alert['severity']}] {atype} on {alert['service']}"
    body_html = f"""
    <html><body style="font-family:sans-serif;background:#0d1117;color:#e6edf3;padding:20px">
      <div style="max-width:600px;margin:auto;background:#161b22;border-radius:8px;padding:24px;
                  border-left:4px solid {'#ff4444' if alert['severity'] == 'CRITICAL' else '#ffa500'}">
        <h2 style="margin:0 0 16px">{emoji} {alert['severity']}: {atype}</h2>
        <table style="width:100%;border-collapse:collapse">
          <tr><td style="padding:6px;color:#8b949e">Service</td><td style="padding:6px"><b>{alert['service']}</b></td></tr>
          <tr><td style="padding:6px;color:#8b949e">Detected At</td><td style="padding:6px">{alert['detected_at']}</td></tr>
          <tr><td style="padding:6px;color:#8b949e">Error Rate</td><td style="padding:6px">{metrics.get('error_rate_pct', 0)}%</td></tr>
          <tr><td style="padding:6px;color:#8b949e">Avg Latency</td><td style="padding:6px">{metrics.get('avg_latency_ms', 0)} ms</td></tr>
          <tr><td style="padding:6px;color:#8b949e">Errors</td><td style="padding:6px">{metrics.get('error_count', 0)} / {metrics.get('total_requests', 0)}</td></tr>
          <tr><td style="padding:6px;color:#8b949e">Runbook</td><td style="padding:6px">{alert.get('runbook_name', 'N/A')}</td></tr>
        </table>
        <hr style="border-color:#30363d;margin:16px 0">
        <h3 style="color:#f0883e">Root Cause</h3>
        <p style="line-height:1.6">{alert.get('root_cause', '')}</p>
        <h3 style="color:#3fb950">Remediation Steps</h3>
        <pre style="background:#0d1117;padding:12px;border-radius:6px;white-space:pre-wrap;font-size:13px">{alert.get('remediation', '')}</pre>
        <p style="color:#8b949e;font-size:12px;margin-top:16px">Alert ID: {alert['alert_id']}</p>
      </div>
    </body></html>
    """

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = SMTP_USER
        msg["To"] = ALERT_EMAIL_TO
        msg.attach(MIMEText(body_html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.sendmail(SMTP_USER, [ALERT_EMAIL_TO], msg.as_string())
        print(f"[Notifier] 📧 Email sent for {alert['alert_id']}")
        return True
    except Exception as e:
        print(f"[Notifier] ❌ Email send failed: {e}")
        return False


def _read_new_alerts(last_pos: int) -> tuple[list[dict], int]:
    if not ALERTS_PATH.exists():
        return [], last_pos
    new_alerts = []
    try:
        with ALERTS_PATH.open("r", encoding="utf-8") as f:
            f.seek(last_pos)
            for line in f:
                line = line.strip()
                if line:
                    try:
                        new_alerts.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            last_pos = f.tell()
    except Exception as e:
        print(f"[Notifier] ❌ Read error: {e}")
    return new_alerts, last_pos


def run():
    print(f"[Notifier] 🚀 Starting — polling {ALERTS_PATH} every {POLL_INTERVAL_S}s")
    
    # Pre-seed seen IDs to avoid alert storm on restart
    if ALERTS_PATH.exists():
        try:
            with ALERTS_PATH.open("r", encoding="utf-8") as f:
                for line in f:
                    try:
                        alert = json.loads(line)
                        if "alert_id" in alert:
                            _seen_alert_ids.add(alert["alert_id"])
                    except: continue
            print(f"[Notifier] ✅ Pre-seeded {len(_seen_alert_ids)} historical alerts")
        except Exception as e:
            print(f"[Notifier] ⚠️  Pre-seed failed: {e}")

    last_pos = 0
    if ALERTS_PATH.exists():
        last_pos = ALERTS_PATH.stat().st_size
        print(f"[Notifier] 📍 Starting poll from position: {last_pos}")

    while True:
        try:
            new_alerts, new_pos = _read_new_alerts(last_pos)
            if new_alerts:
                print(f"[Notifier] 📈 Found {len(new_alerts)} new alerts. Pos: {last_pos} -> {new_pos}")
                for alert in new_alerts:
                    alert_id = alert.get("alert_id", "")
                    severity = alert.get("severity", "")

                    if alert_id in _seen_alert_ids:
                        continue
                    _seen_alert_ids.add(alert_id)

                    print(f"[Notifier] 🔔 Dispatching Alert: {severity} {alert.get('anomaly_type')} on {alert.get('service')}")

                    if severity in NOTIFY_SLACK:
                        _send_slack(alert)
                    if severity in NOTIFY_EMAIL:
                        _send_email(alert)
                
                last_pos = new_pos
            elif ALERTS_PATH.exists() and ALERTS_PATH.stat().st_size < last_pos:
                # File was truncated/reset?
                print("[Notifier] 🔄 Alert file truncated. Resetting position.")
                last_pos = 0
            
        except Exception as e:
            print(f"[Notifier] ❌ Loop error: {e}")

        time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    run()
