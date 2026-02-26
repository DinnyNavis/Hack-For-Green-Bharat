# FinLog Monitor — Real-Time Log Monitoring & Anomaly Detection

A production‑style, fully containerised real‑time log monitoring and anomaly detection system for financial services. Built with **Apache Kafka**, **Pathway**, **LLM-powered RAG**, **FastAPI**, and a **live web dashboard**.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Docker Compose Stack                          │
│                                                                  │
│  ┌─────────────┐     ┌──────────────────┐     ┌─────────────┐  │
│  │ Log Producer│────▶│  Apache Kafka    │────▶│  Pathway    │  │
│  │ (4 services)│     │  service-logs    │     │  Pipeline   │  │
│  └─────────────┘     └──────────────────┘     └──────┬──────┘  │
│                                                       │         │
│                                              ┌────────▼───────┐ │
│  ┌─────────────┐     ┌──────────────────┐   │ anomaly alerts │ │
│  │  Dashboard  │◀────│  FastAPI + WS    │◀──│ alerts.jsonl   │ │
│  │  :3000      │     │  :8000           │   └────────┬───────┘ │
│  └─────────────┘     └──────────────────┘            │         │
│                                                       │         │
│                                              ┌────────▼───────┐ │
│                                              │   Notifier     │ │
│                                              │ Slack / Email  │ │
│                                              └────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| `kafka` | 9092 | Apache Kafka message broker |
| `log-producer` | — | Simulates 4 financial service log streams |
| `pathway-pipeline` | — | Streaming engine: windowing, detection, LLM enrichment |
| `api` | **8000** | FastAPI REST + WebSocket endpoints |
| `notifier` | — | Slack webhook + SMTP email alerts |
| `dashboard` | **3000** | Live web dashboard (Nginx) |

---

## Quick Start

### Prerequisites
- **Docker Desktop** with WSL2 backend (required for Pathway on Windows)
- A free [Google Gemini API key](https://aistudio.google.com/) (optional — works without one)

### 1. Configure environment
```bash
cd d:\pathway-log-monitor
copy .env.example .env
# Edit .env — add your GEMINI_API_KEY (and optionally SLACK_WEBHOOK_URL / SMTP settings)
```

### 2. Start all services
```bash
docker-compose up --build -d
```

### 3. Watch it work
- **Dashboard**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs
- **Alert feed**: http://localhost:8000/alerts

### 4. Monitor logs
```bash
# Pipeline anomaly detection output
docker-compose logs -f pathway-pipeline

# All services
docker-compose logs -f
```

### 5. Stop
```bash
docker-compose down -v
```

---

## Anomaly Detection Rules

- **HIGH_ERROR_RATE**: rate > 10% (WARNING) / 25% (CRITICAL)
- **HIGH_LATENCY**: avg > 500 ms or P95 > 2000 ms
- **FRAUD_SPIKE**: payment errors > 3× baseline (60-second tumbling window)
- **AUTH_STORM**: auth failures > 50 per window (auth-service)

---

## Future Enhancements
- **Persistent Storage**: Store alerts and metrics in MongoDB/PostgreSQL for long‑term analytics.
- **Interactive Config**: UI-based threshold adjustment.
- **Scaled RAG**: Integration with vector databases like Pinecone.

---

## API Endpoints

```
GET  /health                    # Liveness check
GET  /alerts                    # All alerts (newest first)
GET  /alerts?service=X          # Filter by service
GET  /alerts?severity=CRITICAL  # Filter by severity
GET  /alerts/{alert_id}         # Single alert detail
GET  /services                  # Service health status
GET  /metrics                   # Per-service anomaly counts
WS   /ws/live                   # Real-time alert push (WebSocket)
```

---

## Project Structure

```
pathway-log-monitor/
├── producer/           # Kafka log producer (4 financial services)
├── pipeline/           # Pathway streaming pipeline
│   ├── main.py         # Entry point: Kafka → window → detect → LLM → output
│   ├── schemas.py      # pw.Schema definitions
│   ├── anomaly_detector.py  # Rule-based detection logic
│   └── llm_rag.py      # Gemini/OpenAI RAG enrichment
├── api/                # FastAPI backend + WebSocket
├── notifier/           # Slack + email alert dispatcher
├── dashboard/          # Live web dashboard (Nginx)
│   ├── index.html
│   ├── app.js          # WebSocket client + Chart.js
│   └── styles.css      # Premium dark-mode UI
├── data/
│   ├── runbooks/       # 5 remediation guides (used by RAG)
│   └── incident_reports/  # Post-mortem examples
├── output/             # Auto-generated: alerts.jsonl
├── .env.example        # Configuration template
└── docker-compose.yml  # Full stack orchestration
```

---

## Configuration

All settings in `.env` (copy from `.env.example`):

| Variable | Description | Required |
|----------|-------------|----------|
| `GEMINI_API_KEY` | Google Gemini API key for LLM analysis | No (uses rule-based fallback) |
| `OPENAI_API_KEY` | OpenAI alternative | No |
| `LLM_PROVIDER` | `gemini` or `openai` | No (default: `gemini`) |
| `SLACK_WEBHOOK_URL` | Incoming webhook URL for Slack alerts | No |
| `SMTP_HOST/USER/PASS` | Email alert credentials | No |
| `ALERT_EMAIL_TO` | SRE team email address | No |
| `WINDOW_SECONDS` | Aggregation window size (default: 60) | No |
| `LLM_PROVIDER` | `gemini` or `openai` (default: `gemini`) | No |

---

## LLM Integration

The system works **without any API key** using rule-based analysis. To enable LLM-powered root cause analysis:

1. Get a free Gemini API key at [aistudio.google.com](https://aistudio.google.com/)
2. Set `GEMINI_API_KEY=your_key` in `.env`
3. Restart: `docker-compose restart pathway-pipeline`

The LLM receives:
- Live anomaly metrics (error rate, latency, request counts)
- Relevant runbook content (RAG retrieval from `data/runbooks/`)
- Historical incident context (from `data/incident_reports/`)

---

## Anomaly Simulation

The log producer automatically injects anomaly scenarios every 1–2 minutes:

| Scenario | Services | Duration | Effect |
|----------|---------|---------|--------|
| `db_timeout_storm` | trading, banking | 45s | 75% error rate, 8× latency |
| `fraud_spike` | payments | 30s | 60% error rate |
| `auth_storm` | auth | 60s | 80% error rate |
| `cascade_failure` | all | 20s | 50% error rate everywhere |
