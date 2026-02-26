"""
LLM + RAG integration for anomaly root cause analysis.
Uses Pathway's DocumentStore for semantic retrieval of runbooks,
then calls Google Gemini (default) or OpenAI for explanation generation.
Falls back to rule-based text when no API key is configured.
"""
from __future__ import annotations

import os
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ─── Rule-based fallbacks (used when no API key is set) ─────────────────────
RULE_BASED_ANALYSIS: dict[str, dict] = {
    "HIGH_ERROR_RATE": {
        "root_cause": (
            "Elevated error rate detected. Common causes include: database connection "
            "pool exhaustion, downstream service degradation, recent deployment with "
            "regression, or infrastructure resource pressure (CPU/memory)."
        ),
        "remediation": (
            "1. Check database connection pool metrics and increase pool size if needed.\n"
            "2. Review recent deployments (last 2 hours) and consider rollback.\n"
            "3. Inspect downstream service health dashboards.\n"
            "4. Scale out the affected service pods if under load.\n"
            "5. Enable circuit breaker to prevent cascading failures."
        ),
    },
    "HIGH_LATENCY": {
        "root_cause": (
            "Response latency has exceeded acceptable thresholds. Likely causes: "
            "slow database queries (missing indexes or lock contention), external API "
            "timeouts, GC pressure in the JVM/Python runtime, or network congestion."
        ),
        "remediation": (
            "1. Run EXPLAIN on slow queries and add missing indexes.\n"
            "2. Check connection pool wait times and increase timeouts.\n"
            "3. Profile the service for hot code paths or memory leaks.\n"
            "4. Review external API SLAs and add caching where possible.\n"
            "5. Consider async processing for non-critical operations."
        ),
    },
    "FRAUD_SPIKE": {
        "root_cause": (
            "Abnormal spike in payment errors detected — 3× above rolling median. "
            "Potential fraud attack vector: card-testing bots, account takeover attempts, "
            "or a compromised merchant integration sending invalid transactions."
        ),
        "remediation": (
            "1. Immediately review fraud detection dashboard for flagged transaction patterns.\n"
            "2. Enable enhanced 3DS authentication for all transactions above risk threshold.\n"
            "3. Block suspicious IP ranges and rate-limit repeat failed attempts.\n"
            "4. Notify fraud operations team for manual review of flagged accounts.\n"
            "5. Check merchant integration logs for misconfigured payment flows."
        ),
    },
    "AUTH_STORM": {
        "root_cause": (
            "Authentication failure count exceeds threshold — indicative of a brute-force "
            "attack, credential stuffing campaign, or a client-side bug causing retry loops "
            "with invalid credentials."
        ),
        "remediation": (
            "1. Enable CAPTCHA / bot detection on the login endpoint immediately.\n"
            "2. Apply IP-based rate limiting (max 10 attempts per minute per IP).\n"
            "3. Check if a bot network is operating — block CIDR ranges if needed.\n"
            "4. Review auth-service logs for common usernames being targeted.\n"
            "5. Alert security team and consider temporary geo-blocking if attack is localised."
        ),
    },
}

# ─── Runbook document loader (simple in-process for non-Pathway contexts) ───
_RUNBOOK_DIR = Path(os.getenv("RUNBOOK_DIR", "/app/data/runbooks"))
_runbook_cache: dict[str, str] = {}


def _load_runbook(filename: str) -> str:
    if filename not in _runbook_cache:
        path = _RUNBOOK_DIR / filename
        if path.exists():
            _runbook_cache[filename] = path.read_text(encoding="utf-8")
        else:
            _runbook_cache[filename] = ""
    return _runbook_cache[filename]


def _call_gemini(prompt: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-pro")
    response = model.generate_content(prompt)
    return response.text.strip()


def _call_openai(prompt: str) -> str:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are an expert SRE for a financial services platform."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=600,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def analyze(
    service: str,
    anomaly_type: str,
    severity: str,
    metrics_json: str,
    runbook_name: str,
) -> tuple[str, str]:
    """
    Returns (root_cause, remediation) strings.
    Tries LLM first; falls back to rule-based analysis on any error.
    """
    runbook_content = _load_runbook(runbook_name)
    metrics = json.loads(metrics_json)

    # Build LLM prompt
    prompt = f"""You are an expert Site Reliability Engineer (SRE) for a financial services platform.

An anomaly has been detected:
- Service: {service}
- Anomaly Type: {anomaly_type}
- Severity: {severity}
- Metrics:
  - Error Rate: {metrics.get('error_rate_pct', 0)}%
  - Avg Latency: {metrics.get('avg_latency_ms', 0)} ms
  - P95 Latency: {metrics.get('p95_latency_ms', 0)} ms
  - Error Count: {metrics.get('error_count', 0)} / {metrics.get('total_requests', 0)} requests

Relevant Runbook:
---
{runbook_content[:3000] if runbook_content else 'No runbook found.'}
---

Provide:
1. A concise ROOT CAUSE analysis (2-3 sentences) of what likely caused this anomaly.
2. A numbered REMEDIATION STEPS list (max 5 steps) the on-call engineer should take RIGHT NOW.

Format your response as:
ROOT CAUSE: <text>
REMEDIATION:
1. <step>
2. <step>
...
"""

    try:
        if LLM_PROVIDER == "gemini" and GEMINI_API_KEY:
            raw = _call_gemini(prompt)
        elif LLM_PROVIDER == "openai" and OPENAI_API_KEY:
            raw = _call_openai(prompt)
        else:
            raise ValueError("No LLM API key configured")

        # Parse response
        raw_upper = raw.upper()
        root_cause = ""
        remediation = ""

        if "ROOT CAUSE:" in raw_upper:
            # Split by the uppercase version but slice the original casing
            rc_idx = raw_upper.find("ROOT CAUSE:") + len("ROOT CAUSE:")
            rem_idx = raw_upper.find("REMEDIATION:")
            
            if rem_idx != -1:
                root_cause = raw[rc_idx:rem_idx].strip()
                remediation = raw[rem_idx + len("REMEDIATION:"):].strip()
            else:
                root_cause = raw[rc_idx:].strip()

        if not root_cause:
            root_cause = raw[:300].strip()

        return root_cause or RULE_BASED_ANALYSIS[anomaly_type]["root_cause"], \
               remediation or RULE_BASED_ANALYSIS[anomaly_type]["remediation"]

    except Exception as e:
        print(f"[LLM] ⚠️  Falling back to rule-based analysis ({e})")
        fallback = RULE_BASED_ANALYSIS.get(anomaly_type, RULE_BASED_ANALYSIS["HIGH_ERROR_RATE"])
        return fallback["root_cause"], fallback["remediation"]
