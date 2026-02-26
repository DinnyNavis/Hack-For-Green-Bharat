/**
 * FinLog Monitor — Dashboard Application
 * Connects to the FastAPI WebSocket for live alert push,
 * polls REST endpoints on startup, and renders all UI components.
 */

const API_BASE = `${location.protocol}//${location.hostname}:8000`;
const WS_URL = `ws://${location.hostname}:8000/ws/live`;
const POLL_MS = 10_000;  // fallback REST poll interval

// ── State ──────────────────────────────────────────────────────────────────
const State = {
    alerts: [],           // all loaded alerts (newest first)
    serviceFilter: 'all',
    severityFilter: 'all',
    selectedAlertId: null,
    serviceStatus: {},
    stats: { critical: 0, warning: 0, total: 0, healthyCount: 4 },
};

// ── Chart references ────────────────────────────────────────────────────────
let chartErrorRate, chartSeverityDonut, chartVolume, chartAnomalyTypes;

const SERVICE_COLORS = {
    'trading-service': '#388bfd',
    'payments-service': '#a371f7',
    'banking-app': '#3fb950',
    'auth-service': '#d29922',
};

const TYPE_COLORS = {
    'HIGH_ERROR_RATE': '#f85149',
    'HIGH_LATENCY': '#d29922',
    'FRAUD_SPIKE': '#a371f7',
    'AUTH_STORM': '#388bfd',
};

const TYPE_LABELS = {
    'HIGH_ERROR_RATE': 'High Error Rate',
    'HIGH_LATENCY': 'High Latency',
    'FRAUD_SPIKE': 'Fraud Spike',
    'AUTH_STORM': 'Auth Storm',
};

// ── Helpers ─────────────────────────────────────────────────────────────────
function formatTime(isoStr) {
    const d = new Date(isoStr);
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
function formatRelative(isoStr) {
    const diffSec = Math.floor((Date.now() - new Date(isoStr).getTime()) / 1000);
    if (diffSec < 60) return `${diffSec}s ago`;
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    return `${Math.floor(diffSec / 3600)}h ago`;
}
function parseMetrics(a) {
    try { return JSON.parse(a.metrics_json || '{}'); } catch { return {}; }
}

// ── Charts Setup ────────────────────────────────────────────────────────────
function initCharts() {
    const gridColor = 'rgba(255,255,255,0.03)';
    const textColor = '#8b949e';
    const accentColor = '#00d4ff';
    const baseOpts = {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
            x: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 10 } } },
            y: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 10 } } },
        },
    };

    // Error rate bar chart
    chartErrorRate = new Chart(document.getElementById('chartErrorRate'), {
        type: 'bar',
        data: {
            labels: ['trading', 'payments', 'banking', 'auth'],
            datasets: [{
                data: [0, 0, 0, 0],
                backgroundColor: Object.values(SERVICE_COLORS).map(c => c + '88'),
                borderColor: Object.values(SERVICE_COLORS),
                borderWidth: 2, borderRadius: 4,
            }],
        },
        options: {
            ...baseOpts,
            plugins: { ...baseOpts.plugins, tooltip: { callbacks: { label: ctx => ` ${ctx.raw.toFixed(1)}%` } } },
        },
    });

    // Severity donut
    chartSeverityDonut = new Chart(document.getElementById('chartSeverityDonut'), {
        type: 'doughnut',
        data: {
            labels: ['Critical', 'Warning'],
            datasets: [{ data: [0, 0], backgroundColor: ['#f85149', '#d29922'], borderWidth: 0, hoverOffset: 4 }],
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            plugins: {
                legend: { display: true, position: 'bottom', labels: { color: '#8b949e', font: { size: 11 }, padding: 12 } },
            },
            cutout: '65%',
        },
    });

    // Volume line chart (rolling 20 windows)
    const volumeLabels = Array.from({ length: 20 }, () => '');
    chartVolume = new Chart(document.getElementById('chartVolume'), {
        type: 'line',
        data: {
            labels: volumeLabels,
            datasets: [{
                data: Array(20).fill(0),
                borderColor: '#388bfd', borderWidth: 2,
                backgroundColor: 'rgba(56,139,253,0.08)',
                fill: true, tension: 0.4, pointRadius: 0,
            }],
        },
        options: { ...baseOpts },
    });

    // Anomaly type breakdown bar
    chartAnomalyTypes = new Chart(document.getElementById('chartAnomalyTypes'), {
        type: 'bar',
        data: {
            labels: Object.values(TYPE_LABELS),
            datasets: [{
                data: [0, 0, 0, 0],
                backgroundColor: Object.values(TYPE_COLORS).map(c => c + '88'),
                borderColor: Object.values(TYPE_COLORS),
                borderWidth: 2, borderRadius: 4,
            }],
        },
        options: {
            ...baseOpts, indexAxis: 'y',
            scales: {
                x: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 10 } } },
                y: { grid: { display: false }, ticks: { color: textColor, font: { size: 10 } } },
            },
        },
    });
}

// ── Chart Update ─────────────────────────────────────────────────────────────
function updateCharts() {
    const all = State.alerts;
    const services = ['trading-service', 'payments-service', 'banking-app', 'auth-service'];

    // Error rate: avg from recent alerts per service
    const errRates = services.map(svc => {
        const svcAlerts = all.filter(a => a.service === svc);
        if (!svcAlerts.length) return 0;
        const recent = svcAlerts.slice(0, 5);
        const avg = recent.reduce((s, a) => s + (parseMetrics(a).error_rate_pct || 0), 0) / recent.length;
        return +avg.toFixed(1);
    });
    chartErrorRate.data.datasets[0].data = errRates;
    chartErrorRate.update('none');

    // Severity donut
    const critical = all.filter(a => a.severity === 'CRITICAL').length;
    const warning = all.filter(a => a.severity === 'WARNING').length;
    chartSeverityDonut.data.datasets[0].data = [critical, warning];
    chartSeverityDonut.update('none');

    // Anomaly type counts
    const typeCounts = Object.keys(TYPE_LABELS).map(t => all.filter(a => a.anomaly_type === t).length);
    chartAnomalyTypes.data.datasets[0].data = typeCounts;
    chartAnomalyTypes.update('none');

    // Volume — push new count (last minute)
    const recentMin = all.filter(a => (Date.now() - new Date(a.detected_at).getTime()) < 60_000).length;
    const vData = chartVolume.data.datasets[0].data;
    vData.push(recentMin);
    if (vData.length > 20) vData.shift();
    chartVolume.data.datasets[0].data = vData;
    chartVolume.update('none');
}

// ── Service Status Update ────────────────────────────────────────────────────
async function refreshServiceStatus() {
    try {
        const res = await fetch(`${API_BASE}/services`);
        if (!res.ok) return;
        const services = await res.json();
        services.forEach(svc => {
            State.serviceStatus[svc.service] = svc;
            const dot = document.getElementById(`dot-${svc.service}`);
            const count = document.getElementById(`count-${svc.service}`);
            if (dot) { dot.className = `pill-dot ${svc.status}`; }
            if (count) { count.textContent = svc.recent_alerts; }
        });
        const healthyCount = services.filter(s => s.status === 'healthy').length;
        document.getElementById('statHealthy').textContent = healthyCount;
    } catch (_) { }
}

// ── Stats Update ─────────────────────────────────────────────────────────────
function updateStats() {
    const all = State.alerts;
    const critical = all.filter(a => a.severity === 'CRITICAL').length;
    const warning = all.filter(a => a.severity === 'WARNING').length;
    document.getElementById('statCritical').textContent = critical;
    document.getElementById('statWarning').textContent = warning;
    document.getElementById('statTotal').textContent = all.length;
}

// ── Feed Rendering ────────────────────────────────────────────────────────────
function getFilteredAlerts() {
    return State.alerts.filter(a => {
        if (State.serviceFilter !== 'all' && a.service !== State.serviceFilter) return false;
        if (State.severityFilter !== 'all' && a.severity !== State.severityFilter) return false;
        return true;
    });
}

function renderFeed() {
    const list = document.getElementById('feedList');
    const empty = document.getElementById('emptyFeed');
    const filtered = getFilteredAlerts();

    document.getElementById('feedCount').textContent = `${filtered.length} alert${filtered.length !== 1 ? 's' : ''}`;

    if (!filtered.length) {
        list.innerHTML = '';
        list.appendChild(empty);
        empty.style.display = 'flex';
        return;
    }
    empty.style.display = 'none';

    // Only re-render if needed
    const existingIds = new Set([...list.querySelectorAll('.alert-card')].map(el => el.dataset.id));
    const newIds = new Set(filtered.map(a => a.alert_id));

    // Remove stale cards
    list.querySelectorAll('.alert-card').forEach(el => {
        if (!newIds.has(el.dataset.id)) el.remove();
    });

    // Prepend new cards with staggered animation
    filtered.forEach((alert, index) => {
        if (existingIds.has(alert.alert_id)) return;
        const card = buildAlertCard(alert);
        card.style.animationDelay = `${index * 0.05}s`;
        list.insertBefore(card, list.firstChild);
    });
}

function buildAlertCard(alert) {
    const metrics = parseMetrics(alert);
    const card = document.createElement('div');
    card.className = `alert-card severity-${alert.severity}${alert.alert_id === State.selectedAlertId ? ' selected' : ''}`;
    card.dataset.id = alert.alert_id;
    card.onclick = () => App.selectAlert(alert.alert_id);

    card.innerHTML = `
    <div class="alert-card-header">
      <div class="alert-left">
        <span class="severity-badge ${alert.severity}">${alert.severity}</span>
        <span class="alert-service">${alert.service}</span>
      </div>
      <span class="alert-time">${formatRelative(alert.detected_at)}</span>
    </div>
    <div class="alert-type">${TYPE_LABELS[alert.anomaly_type] || alert.anomaly_type}</div>
    <div class="alert-metrics">
      <div class="metric-chip">ERR <span>${metrics.error_rate_pct ?? '–'}%</span></div>
      <div class="metric-chip">LAT <span>${metrics.avg_latency_ms ?? '–'}ms</span></div>
      <div class="metric-chip">REQ <span>${metrics.total_requests ?? '–'}</span></div>
    </div>
  `;
    return card;
}

// ── Detail Panel ──────────────────────────────────────────────────────────────
function renderDetail(alertId) {
    const alert = State.alerts.find(a => a.alert_id === alertId);
    const panel = document.getElementById('detailPanel');
    if (!alert) { panel.innerHTML = '<div class="detail-placeholder"><div class="icon">📋</div><p style="font-weight:600">Select an alert</p></div>'; return; }

    const metrics = parseMetrics(alert);
    const errClass = alert.severity === 'CRITICAL' ? 'critical' : 'warning';

    panel.innerHTML = `
    <div class="detail-header">
      <div class="detail-service">${alert.service}</div>
      <div class="detail-badges">
        <span class="severity-badge ${alert.severity}">${alert.severity}</span>
        <span style="font-size:12px;color:var(--accent-blue);font-weight:500">${TYPE_LABELS[alert.anomaly_type] || alert.anomaly_type}</span>
      </div>
      <div class="detail-time">${new Date(alert.detected_at).toLocaleString()}</div>
      <div class="detail-alert-id">ID: ${alert.alert_id}</div>
    </div>

    <div class="detail-metrics-grid">
      <div class="detail-metric">
        <div class="detail-metric-label">Error Rate</div>
        <div class="detail-metric-value ${errClass}">${metrics.error_rate_pct ?? '–'}%</div>
      </div>
      <div class="detail-metric">
        <div class="detail-metric-label">Avg Latency</div>
        <div class="detail-metric-value ${metrics.avg_latency_ms > 500 ? errClass : ''}">${metrics.avg_latency_ms ?? '–'} ms</div>
      </div>
      <div class="detail-metric">
        <div class="detail-metric-label">P95 Latency</div>
        <div class="detail-metric-value">${metrics.p95_latency_ms ?? '–'} ms</div>
      </div>
      <div class="detail-metric">
        <div class="detail-metric-label">Errors / Total</div>
        <div class="detail-metric-value" style="font-size:14px">${metrics.error_count ?? '–'} / ${metrics.total_requests ?? '–'}</div>
      </div>
    </div>

    <div class="detail-section">
      <div class="detail-section-title">🔍 Root Cause Analysis</div>
      <div class="detail-text">${alert.root_cause || 'Analysing…'}</div>
    </div>

    <div class="detail-section">
      <div class="detail-section-title">🛠 Remediation Steps</div>
      <div class="detail-remediation">${alert.remediation || 'No remediation steps available.'}</div>
    </div>

    <div class="detail-section">
      <div class="detail-section-title">📖 Runbook</div>
      <div class="detail-runbook-section">
          <p style="font-size: 12px; color: var(--text-500); margin-bottom: 12px;">Access the official troubleshooting guide for this anomaly:</p>
          <button class="runbook-link" onclick="App.openRunbook('${alert.runbook_name}')" title="Open Runbook">
            📄 ${alert.runbook_name || 'N/A'}
          </button>
      </div>
    </div>
  `;
}

// ── Toast Notifications ───────────────────────────────────────────────────────
function showToast(alert) {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${alert.severity.toLowerCase()}`;
    toast.innerHTML = `
    <div style="font-size:20px">${alert.severity === 'CRITICAL' ? '🔴' : '🟡'}</div>
    <div>
      <div class="toast-title">${alert.service} — ${TYPE_LABELS[alert.anomaly_type] || alert.anomaly_type}</div>
      <div class="toast-body">${alert.severity} · ${formatTime(alert.detected_at)}</div>
    </div>
  `;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 6000);
}

// ── WebSocket ─────────────────────────────────────────────────────────────────
let wsRetryDelay = 2000;

function connectWS() {
    const dot = document.getElementById('wsDot');
    const label = document.getElementById('wsLabel');
    const badge = document.getElementById('liveStatusBadge');

    dot.className = 'ws-dot';
    label.textContent = 'CONNECTING';
    badge.className = 'live-badge';

    const ws = new WebSocket(WS_URL);

    ws.onopen = () => {
        dot.className = 'ws-dot connected';
        label.textContent = 'LIVE MONITOR';
        badge.className = 'live-badge connected';
        wsRetryDelay = 2000;
    };

    ws.onmessage = (ev) => {
        try {
            const alert = JSON.parse(ev.data);
            addAlert(alert);
            showToast(alert);
        } catch (_) { }
    };

    ws.onclose = () => {
        dot.className = 'ws-dot error';
        label.textContent = `OFFLINE`;
        badge.className = 'live-badge';
        setTimeout(connectWS, wsRetryDelay);
        wsRetryDelay = Math.min(wsRetryDelay * 1.5, 30000);
    };

    ws.onerror = () => ws.close();
}

function addAlert(alert) {
    const exists = State.alerts.find(a => a.alert_id === alert.alert_id);
    if (!exists) {
        State.alerts.unshift(alert);   // prepend (newest first)
        updateStats();
        updateCharts();
        renderFeed();
        refreshServiceStatus();
    }
}

// ── Initial REST Load ─────────────────────────────────────────────────────────
async function loadInitialAlerts() {
    try {
        const res = await fetch(`${API_BASE}/alerts?limit=100`);
        if (!res.ok) return;
        const alerts = await res.json();
        alerts.forEach(a => {
            if (!State.alerts.find(x => x.alert_id === a.alert_id)) State.alerts.push(a);
        });
        updateStats();
        updateCharts();
        renderFeed();
    } catch (_) { }
}

// ── App public API ────────────────────────────────────────────────────────────
const App = {
    filterService(service, el) {
        State.serviceFilter = service;
        document.querySelectorAll('.service-pill').forEach(p => p.classList.remove('active'));
        el.classList.add('active');
        renderFeed();
    },
    setSeverityFilter(severity, el) {
        State.severityFilter = severity;
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        el.classList.add('active');
        renderFeed();
    },
    selectAlert(alertId) {
        State.selectedAlertId = alertId;
        document.querySelectorAll('.alert-card').forEach(c => {
            c.classList.toggle('selected', c.dataset.id === alertId);
        });
        renderDetail(alertId);
    },
    async openRunbook(filename) {
        if (!filename || filename === 'N/A') return;
        try {
            const res = await fetch(`${API_BASE}/runbooks/${filename}`);
            if (!res.ok) throw new Error("Runbook not found");
            const data = await res.json();

            const formatMarkdown = (md) => {
                // Remove raw symbols and replace with professional HTML
                return md
                    .replace(/^# (.*$)/gim, '<h1>$1</h1>')
                    .replace(/^## (.*$)/gim, '<h2>$1</h2>')
                    .replace(/^### (.*$)/gim, '<h3>$1</h3>')
                    .replace(/\*\*(.*?)\*\*/gim, '<b>$1</b>')
                    .replace(/^---/gim, '<hr>')
                    .replace(/^- (.*$)/gim, '<ul><li>$1</li></ul>') // Basic list conversion
                    .replace(/^1\. (.*$)/gim, '<ol><li>$1</li></ol>')
                    .replace(/\[ \] (.*$)/gim, '<div class="check">❌ $1</div>') // Checklist
                    .replace(/\[x\] (.*$)/gim, '<div class="check">✅ $1</div>')
                    .replace(/```(bash|json|python)?([\s\S]*?)```/gim, '<pre><code>$2</code></pre>')
                    .replace(/`(.*?)`/gim, '<code class="inline">$1</code>');
            };

            const renderedContent = formatMarkdown(data.content);

            const win = window.open("", "_blank");
            const html = `
                <!DOCTYPE html>
                <html lang="en">
                <head>
                    <meta charset="UTF-8">
                    <title>Runbook Viewer — ${filename}</title>
                    <style>
                        @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
                        
                        :root {
                            --accent-cyan: #00d4ff;
                            --accent-purple: #9d50ff;
                            --bg-dark: #020408;
                            --text-primary: #ffffff;
                            --text-secondary: #c9d1d9;
                            --glass-bg: rgba(13, 17, 23, 0.85);
                            --glass-border: rgba(255, 255, 255, 0.1);
                        }

                        body { 
                            margin: 0; padding: 0; min-height: 100vh;
                            background: var(--bg-dark); color: var(--text-secondary); 
                            font-family: 'Outfit', sans-serif; line-height: 1.8;
                            overflow-x: hidden;
                        }

                        body::before {
                            content: ""; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                            background: 
                                radial-gradient(circle at 80% 20%, rgba(0, 212, 255, 0.08) 0%, transparent 40%),
                                radial-gradient(circle at 20% 80%, rgba(157, 80, 255, 0.08) 0%, transparent 40%);
                            z-index: -1;
                        }

                        .container {
                            max-width: 900px; margin: 60px auto; padding: 60px;
                            background: var(--glass-bg); backdrop-filter: blur(30px);
                            border: 1px solid var(--glass-border); border-radius: 24px;
                            box-shadow: 0 40px 100px rgba(0,0,0,0.5);
                        }

                        h1 { color: var(--accent-cyan); font-size: 38px; font-weight: 800; margin-bottom: 20px; letter-spacing: -1.5px; }
                        h2 { color: var(--text-primary); font-size: 24px; font-weight: 700; margin-top: 45px; border-bottom: 1px solid var(--glass-border); padding-bottom: 10px; }
                        h3 { color: var(--accent-purple); font-size: 18px; margin-top: 25px; }
                        
                        hr { border: none; height: 1px; background: var(--glass-border); margin: 40px 0; }
                        
                        pre { 
                            background: rgba(0, 0, 0, 0.6); padding: 25px; border-radius: 12px; 
                            color: #ddd; font-family: 'JetBrains Mono', monospace; font-size: 14px;
                            border: 1px solid rgba(0, 212, 255, 0.2); margin: 20px 0;
                            box-shadow: inset 0 0 30px rgba(0,0,0,0.5);
                        }
                        
                        code.inline { background: rgba(0, 212, 255, 0.1); color: var(--accent-cyan); padding: 2px 6px; border-radius: 4px; font-family: 'JetBrains Mono'; }
                        
                        ul, ol { padding-left: 20px; margin: 15px 0; }
                        li { margin-bottom: 10px; }
                        
                        .check { display: flex; align-items: center; gap: 10px; margin: 8px 0; font-weight: 500; }

                        .footer {
                            margin-top: 60px; padding-top: 20px; border-top: 1px solid var(--glass-border);
                            font-size: 11px; color: var(--text-500); display: flex; justify-content: space-between;
                            text-transform: uppercase; letter-spacing: 1px;
                        }
                    </style>
                </head>
                <body>
                    <div class="container">
                        <div class="content">
                            ${renderedContent}
                        </div>
                        <div class="footer">
                            <span>FinLog Monitor — Digital Operations Runbook</span>
                            <span>Confidential — Internal Use Only</span>
                        </div>
                    </div>
                </body>
                </html>
            `;
            win.document.write(html);
            win.document.close();
        } catch (err) {
            console.error(err);
        }
    }
};

// ── Initialise ────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    loadInitialAlerts();
    connectWS();

    // Periodic REST fallback poll + service status refresh
    setInterval(() => {
        loadInitialAlerts();
        refreshServiceStatus();
    }, POLL_MS);

    // Refresh relative timestamps in feed
    setInterval(() => {
        document.querySelectorAll('.alert-time').forEach(el => {
            const card = el.closest('.alert-card');
            const alert = card && State.alerts.find(a => a.alert_id === card.dataset.id);
            if (alert) el.textContent = formatRelative(alert.detected_at);
        });
    }, 30_000);
});
