"""
Multi-service financial log producer for Kafka.
Simulates realistic log traffic for: trading-service, payments-service,
banking-app, and auth-service — including periodic anomaly bursts.
"""
import json
import os
import random
import time
import uuid
from datetime import datetime, timezone

from confluent_kafka import Producer
from dotenv import load_dotenv

load_dotenv()

KAFKA_BROKER = os.getenv("KAFKA_BROKER", "localhost:9092")
TOPIC = "service-logs"

SERVICES = {
    "trading-service": {
        "endpoints": ["/api/trade/execute", "/api/trade/quote", "/api/market/data", "/api/portfolio"],
        "normal_latency_ms": (20, 150),
        "error_codes": [500, 503, 504],
        "normal_messages": [
            "Trade executed successfully",
            "Market data fetched",
            "Portfolio updated",
            "Order book snapshot retrieved",
            "Trade limit validated",
        ],
        "error_messages": [
            "Error: Database connection timeout after 30s",
            "Error: Market data feed disconnected",
            "Error: Order routing service unavailable",
            "Error: Risk engine response timeout",
        ],
    },
    "payments-service": {
        "endpoints": ["/api/payment/process", "/api/payment/verify", "/api/refund", "/api/transfer"],
        "normal_latency_ms": (30, 200),
        "error_codes": [400, 500, 502, 503],
        "normal_messages": [
            "Payment processed successfully",
            "Transaction verified",
            "Refund initiated",
            "Fund transfer completed",
            "Payment gateway acknowledged",
        ],
        "error_messages": [
            "Error: Payment gateway timeout",
            "Error: Fraud detection triggered - transaction blocked",
            "Error: Insufficient funds validation failed",
            "Error: Card tokenisation service unavailable",
            "Error: 3DS authentication failed",
        ],
    },
    "banking-app": {
        "endpoints": ["/api/account/balance", "/api/account/statement", "/api/loan/apply", "/api/deposit"],
        "normal_latency_ms": (40, 300),
        "error_codes": [500, 503, 504],
        "normal_messages": [
            "Account balance retrieved",
            "Statement generated",
            "Deposit processed",
            "Loan eligibility computed",
            "Customer profile loaded",
        ],
        "error_messages": [
            "Error: Core banking system timeout",
            "Error: Database cluster failover in progress",
            "Error: Account service unresponsive",
            "Error: Statement generation failed - data inconsistency",
        ],
    },
    "auth-service": {
        "endpoints": ["/api/auth/login", "/api/auth/refresh", "/api/auth/logout", "/api/auth/mfa"],
        "normal_latency_ms": (10, 80),
        "error_codes": [401, 403, 500],
        "normal_messages": [
            "User authenticated successfully",
            "Token refreshed",
            "Session established",
            "MFA verification passed",
            "User logged out",
        ],
        "error_messages": [
            "Error: Invalid credentials - authentication failed",
            "Error: JWT validation failed - token expired",
            "Error: MFA service timeout",
            "Error: Brute-force protection triggered - IP blocked",
            "Error: Session store unavailable",
        ],
    },
}

# Anomaly scenario catalogue
ANOMALY_SCENARIOS = [
    {
        "name": "db_timeout_storm",
        "services": ["trading-service", "banking-app"],
        "duration_s": 45,
        "error_rate": 0.75,
        "latency_multiplier": 8,
    },
    {
        "name": "fraud_spike",
        "services": ["payments-service"],
        "duration_s": 30,
        "error_rate": 0.60,
        "latency_multiplier": 3,
    },
    {
        "name": "auth_storm",
        "services": ["auth-service"],
        "duration_s": 60,
        "error_rate": 0.80,
        "latency_multiplier": 2,
    },
    {
        "name": "cascade_failure",
        "services": ["trading-service", "payments-service", "banking-app", "auth-service"],
        "duration_s": 20,
        "error_rate": 0.50,
        "latency_multiplier": 5,
    },
]


def make_producer() -> Producer:
    conf = {
        "bootstrap.servers": KAFKA_BROKER,
        "client.id": "financial-log-producer",
        "acks": "1",
        "retries": 5,
        "retry.backoff.ms": 500,
    }
    return Producer(conf)


def delivery_report(err, msg):
    if err:
        print(f"[Producer] ❌ Delivery failed: {err}")


def build_log_event(service: str, anomaly: dict | None = None) -> dict:
    cfg = SERVICES[service]
    now = datetime.now(timezone.utc).isoformat()
    trace_id = str(uuid.uuid4())[:8]

    is_error = False
    if anomaly and service in anomaly["services"]:
        is_error = random.random() < anomaly["error_rate"]
        lat_low, lat_high = cfg["normal_latency_ms"]
        latency_ms = round(
            random.uniform(lat_low, lat_high) * anomaly["latency_multiplier"], 2
        )
    else:
        # Normal traffic — occasional baseline 2% error
        is_error = random.random() < 0.02
        lat_low, lat_high = cfg["normal_latency_ms"]
        latency_ms = round(random.uniform(lat_low, lat_high), 2)

    if is_error:
        level = random.choice(["ERROR", "CRITICAL"])
        status_code = random.choice(cfg["error_codes"])
        message = random.choice(cfg["error_messages"])
    else:
        level = random.choice(["INFO", "INFO", "INFO", "WARN"])
        status_code = 200
        message = random.choice(cfg["normal_messages"])

    return {
        "timestamp": now,
        "service": service,
        "level": level,
        "status_code": status_code,
        "latency_ms": latency_ms,
        "message": message,
        "trace_id": trace_id,
        "endpoint": random.choice(cfg["endpoints"]),
    }


def run():
    print(f"[Producer] 🚀 Starting — broker: {KAFKA_BROKER}, topic: {TOPIC}")
    producer = make_producer()

    active_anomaly: dict | None = None
    anomaly_end_time: float = 0.0
    next_anomaly_time = time.time() + random.uniform(5, 15)

    while True:
        now = time.time()

        # Decide whether to start a new anomaly scenario
        if active_anomaly is None and now >= next_anomaly_time:
            active_anomaly = random.choice(ANOMALY_SCENARIOS)
            anomaly_end_time = now + active_anomaly["duration_s"]
            print(
                f"[Producer] ⚠️  Anomaly scenario: {active_anomaly['name']} "
                f"on {active_anomaly['services']} for {active_anomaly['duration_s']}s"
            )

        if active_anomaly and now >= anomaly_end_time:
            print(f"[Producer] ✅ Anomaly scenario ended: {active_anomaly['name']}")
            active_anomaly = None
            next_anomaly_time = now + random.uniform(10, 30)

        # Produce logs for all services
        for service in SERVICES:
            event = build_log_event(service, active_anomaly)
            producer.produce(
                TOPIC,
                key=service,
                value=json.dumps(event).encode("utf-8"),
                callback=delivery_report,
            )

        producer.poll(0)
        time.sleep(0.1)  # Increased volume to ~40 events/sec total


if __name__ == "__main__":
    run()
