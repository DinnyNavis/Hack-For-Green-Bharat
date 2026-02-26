# 🚀 Pathway FinLog Monitor: Real-Time GenAI Anomaly Detection

Pathway FinLog Monitor is an end-to-end, real-time log monitoring and anomaly detection system tailored for financial services. It leverages [Pathway](https://pathway.com/) for high-throughput stream processing, Kafka for message brokering, and Large Language Models (LLMs) with Retrieval-Augmented Generation (RAG) to instantly provide root-cause analysis and remediation steps for detected incidents.

## ✨ Key Features

* **Real-Time Stream Processing**: Uses Pathway to process log streams with rolling windows (default 60s) to instantly calculate metrics like error rates and P95 latency.
* **GenAI Root Cause Analysis (RAG)**: Automatically analyzes detected anomalies against service runbooks using Google Gemini or OpenAI (with fallback to rule-based analysis) to suggest immediate remediation steps.
* **Multi-Service Simulation**: Includes a robust mock log producer that simulates traffic for `trading-service`, `payments-service`, `banking-app`, and `auth-service`, complete with periodic anomaly injections.
* **Live Dashboard & API**: A FastAPI backend provides REST endpoints and a WebSocket connection (`/ws/live`) to stream live alerts to an Nginx-served web dashboard.
* **Multi-Channel Alerting**: A dedicated notifier service dispatches alerts to Slack (for WARNING/CRITICAL) and SMTP Email (for CRITICAL) to ensure rapid incident response.

---

## 🏗️ System Architecture

The project is fully containerized using Docker Compose and consists of the following interconnected microservices:

1.  **Kafka (`kafka`, `kafka-init`)**: Acts as the central message broker running in KRaft mode (no Zookeeper needed), managing the `service-logs` topic.
2.  **Log Producer (`log-producer`)**: A Python application that continuously pushes simulated JSON log events into Kafka, injecting coordinated anomaly scenarios.
3.  **Pathway Pipeline (`pathway-pipeline`)**: The core engine. It ingests Kafka logs, applies temporal rolling windows, detects threshold breaches, queries the LLM/RAG module for context, and outputs enriched alerts to a JSONL file.
4.  **FastAPI Backend (`api`)**: Serves historical alerts, aggregated metrics, and runbook contents via REST, while using WebSockets to push new alerts in real-time.
5.  **Notifier (`notifier`)**: Polls the output alerts file (`alerts.jsonl`) and routes notifications to external systems like Slack and email, preventing alert storms by tracking seen Alert IDs.
6.  **Dashboard (`dashboard`)**: A frontend UI hosted on port 3000 to visualize service health and active alerts.

---

## 🚦 Built-In Anomaly Scenarios

To demonstrate the pipeline's capabilities, the producer automatically cycles through the following incident scenarios:
* **`db_timeout_storm`**: 8x latency spike and 75% error rate across trading and banking services.
* **`fraud_spike`**: 60% transaction failure rate and 3x latency isolated to the payments service.
* **`auth_storm`**: 80% error rate on authentication endpoints simulating credential stuffing/brute force attacks.
* **`cascade_failure`**: A massive system-wide failure affecting all services simultaneously with a 50% error rate.

---

## 🚀 Getting Started

### Prerequisites
* Docker and Docker Compose installed.
* An API Key for either Google Gemini (Recommended/Free Tier available) or OpenAI.

### 1. Configuration
Clone the repository and set up your environment variables by copying the example file:
```bash
cp .env.example .env
