import { api, showToast, escapeHtml, fmtMs, fmtNum, fmtClock, hasCharts } from './utils.js';

if (hasCharts) Chart.defaults.font.family = "'Inter', sans-serif";

const telemetryModal = document.getElementById('telemetryModal');
const telemetryBody = document.getElementById('telemetryBody');
const telemetryStatus = document.getElementById('telemetryStatus');
const telemetryRefresh = document.getElementById('telemetryRefresh');
const telemetryClear = document.getElementById('telemetryClear');
const telemetryModalClose = document.getElementById('telemetryModalClose');
const analyticsBtn = document.getElementById('analyticsBtn');

let currentTelemetryEvent = null;

export function openTelemetryModal() {
  telemetryModal.hidden = false;
  currentTelemetryEvent = null;
  loadTelemetry();
}
export function closeTelemetryModal() { telemetryModal.hidden = true; currentTelemetryEvent = null; }

let activeCharts = [];

function destroyCharts() {
  activeCharts.forEach(c => { try { c.destroy(); } catch (_) {} });
  activeCharts = [];
}

const CHART_TEXT = '#9a9a9d';
const CHART_GRID = 'rgba(255,255,255,0.06)';
const CHART_LINE = 'rgba(255,255,255,0.85)';
const CHART_DANGER = '#e5645f';
const CHART_TOOLTIP = {
  backgroundColor: '#141416',
  borderColor: 'rgba(255,255,255,0.14)',
  borderWidth: 1,
  titleColor: '#ededed',
  bodyColor: '#dcdcde',
};

// last 24 whole hours ending at the current hour, so the line is continuous
// instead of jumping between sparse buckets. backend hours are naive UTC, so
// labels use UTC too.
function build24hSeries(timeline, key) {
  const byHour = new Map((timeline || []).map(t => [t.hour, t]));
  const labels = [];
  const values = [];
  const now = new Date();
  now.setMinutes(0, 0, 0);
  for (let i = 23; i >= 0; i--) {
    const d = new Date(now.getTime() - i * 3600 * 1000);
    labels.push(d.toLocaleString(undefined, { hour: '2-digit', timeZone: 'UTC' }));
    const iso = d.toISOString().slice(0, 13) + ':00:00';
    const bucket = byHour.get(iso);
    values.push(bucket ? bucket[key] : (key === 'count' || key === 'failures' ? 0 : null));
  }
  return { labels, values };
}

function makeLineChart(canvasId, labels, datasets) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  activeCharts.push(new Chart(canvas, {
    type: 'line',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { labels: { color: CHART_TEXT, font: { size: 11 }, usePointStyle: true, boxWidth: 8 } },
        tooltip: CHART_TOOLTIP,
      },
      scales: {
        x: {
          grid: { color: CHART_GRID },
          ticks: { color: '#66666b', font: { size: 10 }, maxTicksLimit: 7, maxRotation: 0 },
        },
        y: {
          beginAtZero: true,
          grid: { color: CHART_GRID },
          ticks: { color: '#66666b', font: { size: 10 } },
        },
      },
    },
  }));
}

function makeDoughnutChart(canvasId, labels, data) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const palette = [
    'rgba(255,255,255,0.9)', 'rgba(255,255,255,0.6)', 'rgba(255,255,255,0.38)',
    'rgba(255,255,255,0.22)', 'rgba(255,255,255,0.12)', CHART_DANGER,
  ];
  activeCharts.push(new Chart(canvas, {
    type: 'doughnut',
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: labels.map((_, i) => palette[i % palette.length]),
        borderColor: 'rgba(10,10,11,0.9)',
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '62%',
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: CHART_TEXT, font: { size: 11 }, usePointStyle: true, boxWidth: 8 },
        },
        tooltip: CHART_TOOLTIP,
      },
    },
  }));
}

function makeBarChart(canvasId, labels, data) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  activeCharts.push(new Chart(canvas, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'calls',
        data,
        backgroundColor: 'rgba(255,255,255,0.5)',
        hoverBackgroundColor: 'rgba(255,255,255,0.75)',
        borderRadius: 4,
        maxBarThickness: 26,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: CHART_TOOLTIP },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: '#66666b', font: { size: 10 }, maxRotation: 0, autoSkip: true },
        },
        y: {
          beginAtZero: true,
          grid: { color: CHART_GRID },
          ticks: { color: '#66666b', font: { size: 10 }, precision: 0 },
        },
      },
    },
  }));
}

/* ---- section builders ---- */

function kpiCards(cards) {
  return `<div class="stats-grid">${
    cards.map(([value, label, cls = '']) =>
      `<div class="stat-card"><div class="stat-value ${cls}">${value}</div><div class="stat-label">${label}</div></div>`
    ).join('')
  }</div>`;
}

// horizontal bars for a {name: count} split (effort, intent, sources…)
function mixRows(mix, emptyText) {
  const entries = Object.entries(mix || {});
  if (!entries.length) return `<div class="kv-row"><div class="k">no data yet</div><div class="v">${emptyText}</div></div>`;
  const max = Math.max(1, ...entries.map(([, v]) => v));
  const total = entries.reduce((sum, [, v]) => sum + v, 0);
  return entries.sort((a, b) => b[1] - a[1]).map(([name, count]) => `
    <div class="route-row">
      <div class="route-name" title="${escapeHtml(name)}">${escapeHtml(name)}</div>
      <div class="route-meta">${fmtNum(count)} · ${Math.round((count / total) * 100)}%</div>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.round((count / max) * 100)}%"></div></div>
    </div>`).join('');
}

// stage / tool rows: name, run count, average duration bar
function spanRows(spans, kind, emptyText) {
  const entries = Object.entries((spans || {})[kind] || {});
  if (!entries.length) return `<div class="kv-row"><div class="k">no data yet</div><div class="v">${emptyText}</div></div>`;
  const sorted = entries.sort((a, b) => b[1].avg_ms - a[1].avg_ms);
  const maxMs = Math.max(1, ...sorted.map(([, v]) => v.avg_ms));
  return sorted.map(([name, info]) => `
    <div class="route-row">
      <div class="route-name" title="${escapeHtml(name)}">${escapeHtml(name)}</div>
      <div class="route-meta">${fmtNum(info.count)} run${info.count === 1 ? '' : 's'} · ${fmtMs(info.avg_ms)} avg</div>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.round((info.avg_ms / maxMs) * 100)}%"></div></div>
    </div>`).join('');
}

function kvRows(pairs) {
  return pairs
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([key, value]) => `<div class="kv-row"><div class="k">${escapeHtml(key)}</div><div class="v">${value}</div></div>`)
    .join('');
}

function toolCountOf(event) {
  return (event.spans || []).filter(s => s.span_type === 'TOOL').length;
}

async function loadTelemetry() {
  telemetryStatus.textContent = 'Loading…';
  try {
    const [summaryRes, eventsRes] = await Promise.all([
      api('/telemetry/summary'),
      api('/telemetry/events?limit=100'),
    ]);
    const summary = await summaryRes.json();
    const { events } = await eventsRes.json();
    telemetryStatus.textContent = `${summary.total} event${summary.total === 1 ? '' : 's'} recorded`;
    renderTelemetry(summary, events);
  } catch (err) {
    telemetryStatus.textContent = 'Failed to load';
    telemetryBody.innerHTML = `<div class="dash-empty">Could not load analytics: ${escapeHtml(err.message)}</div>`;
  }
}

function renderTelemetry(summary, events) {
  destroyCharts();
  if (currentTelemetryEvent) { renderTelemetryDetail(currentTelemetryEvent, summary, events); return; }
  if (summary.total === 0) {
    telemetryBody.innerHTML = '<div class="dash-empty">No telemetry recorded yet. Send a message or upload a document to start logging.</div>';
    return;
  }

  const avg = summary.metric_averages || {};
  const tags = summary.tags || {};
  const spans = summary.spans || {};
  const avgOf = key => (avg[key] != null ? fmtNum(avg[key]) : '—');

  const overview = kpiCards([
    [fmtNum(summary.total), 'Runs'],
    [summary.success_rate + '%', 'Success rate', 'ok'],
    [fmtNum(summary.failures), 'Failures', summary.failures > 0 ? 'err' : ''],
    [fmtMs(summary.avg_duration_ms), 'Avg response'],
  ]);

  const agent = kpiCards([
    [avgOf('tool_calls'), 'Avg tools / run'],
    [avgOf('total_tokens'), 'Avg tokens / run'],
    [avgOf('stage_runs'), 'Avg research stages'],
    [avgOf('replans'), 'Avg replans'],
  ]);

  const effortMix = tags.effort || {};
  const intentMix = tags.intent || {};
  const toolMix = spans.TOOL || {};
  const toolLabels = Object.keys(toolMix).sort((a, b) => toolMix[b].count - toolMix[a].count);
  const effortLabels = Object.keys(effortMix);
  const intentLabels = Object.keys(intentMix);

  const routes = summary.routes || {};
  const maxRouteCount = Math.max(1, ...Object.values(routes).map(r => r.count));
  const routeRows = Object.keys(routes).sort().map(route => {
    const r = routes[route];
    const pct = Math.round((r.count / maxRouteCount) * 100);
    return `
      <div class="route-row">
        <div class="route-name" title="${escapeHtml(route)}">${escapeHtml(route)}</div>
        <div class="route-meta">${r.count} req · ${fmtMs(r.avg_duration_ms)} avg</div>
        <div class="bar-track"><div class="bar-fill" style="width:${pct}%"></div></div>
      </div>`;
  }).join('');

  const hasTimeline = (summary.timeline || []).length > 0;
  let chartsHtml = '';
  let req = null, fail = null, lat = null, routeLabels = [], routeCounts = [];
  if (hasCharts && hasTimeline) {
    req = build24hSeries(summary.timeline, 'count');
    fail = build24hSeries(summary.timeline, 'failures');
    lat = build24hSeries(summary.timeline, 'avg_duration_ms');
    routeLabels = Object.keys(routes).sort();
    routeCounts = routeLabels.map(r => routes[r].count);
    chartsHtml = `
      <div class="charts-grid">
        <div class="chart-card"><div class="chart-head">Runs · last 24h</div><div class="chart-box"><canvas id="chartRequests"></canvas></div></div>
        <div class="chart-card"><div class="chart-head">Avg response · last 24h</div><div class="chart-box"><canvas id="chartLatency"></canvas></div></div>
        <div class="chart-card"><div class="chart-head">Routes</div><div class="chart-box"><canvas id="chartRoutes"></canvas></div></div>
        <div class="chart-card"><div class="chart-head">Response effort</div><div class="chart-box"><canvas id="chartEffort"></canvas></div></div>
        <div class="chart-card"><div class="chart-head">Router decisions</div><div class="chart-box"><canvas id="chartIntent"></canvas></div></div>
        <div class="chart-card"><div class="chart-head">Tool calls</div><div class="chart-box"><canvas id="chartTools"></canvas></div></div>
      </div>`;
  }

  const tokens = kvRows([
    ['input tokens', avg.input_tokens != null ? fmtNum(avg.input_tokens) : null],
    ['output tokens', avg.output_tokens != null ? fmtNum(avg.output_tokens) : null],
    ['total tokens', avg.total_tokens != null ? fmtNum(avg.total_tokens) : null],
    ['answer chars', avg.answer_chars != null ? fmtNum(avg.answer_chars) : null],
    ['sources cited', avg.sources_count != null ? fmtNum(avg.sources_count) : null],
  ]);

  const reruns = kvRows([
    ['replans', avg.replans != null ? fmtNum(avg.replans) : null],
    ['quality revisions', avg.quality_revisions != null ? fmtNum(avg.quality_revisions) : null],
    ['tool failures', avg.tool_failures != null ? fmtNum(avg.tool_failures) : null],
    ['stream errors', avg.agent_errors != null ? fmtNum(avg.agent_errors) : null],
  ]);

  const errorMix = tags.error_type && Object.keys(tags.error_type).length
    ? `<div class="sec-title">Failure reasons</div>${mixRows(tags.error_type, '')}`
    : '';

  const table = `
    <table class="dash-table">
      <thead><tr><th>Time</th><th>Effort</th><th>Intent</th><th>Route</th><th>Tools</th><th>Status</th><th style="text-align:right">Duration</th></tr></thead>
      <tbody>
        ${events.map(e => `
          <tr data-id="${e.id}">
            <td class="tt">${fmtClock(e.started_at)}</td>
            <td>${escapeHtml((e.tags || {}).effort || '—')}</td>
            <td>${escapeHtml((e.tags || {}).intent || '—')}</td>
            <td class="route">${escapeHtml(e.route)}</td>
            <td>${toolCountOf(e) || '—'}</td>
            <td><span class="dot ${e.success ? 'ok' : 'err'}"></span>${e.success ? 'ok' : (escapeHtml(e.error_type) || 'error')}</td>
            <td class="tt" style="text-align:right">${fmtMs(e.duration_ms)}</td>
          </tr>`).join('')}
      </tbody>
    </table>`;

  telemetryBody.innerHTML = `
    <div>${overview}</div>
    ${chartsHtml}
    <div class="sec-title">Agent</div>
    ${agent}
    <div class="charts-grid" style="margin-top:10px">
      <div class="chart-card">
        <div class="chart-head">Router decisions</div>
        ${mixRows(intentMix, 'no routed runs yet')}
      </div>
      <div class="chart-card">
        <div class="chart-head">Response effort</div>
        ${mixRows(effortMix, 'no effort tag yet')}
      </div>
    </div>
    <div class="sec-title">Tool usage</div>
    ${spanRows(spans, 'TOOL', 'no tools called yet')}
    <div class="sec-title">Stage timing</div>
    ${spanRows(spans, 'STAGE', 'no research stages yet')}
    ${tokens ? `<div class="sec-title">Tokens &amp; output</div>${tokens}` : ''}
    ${reruns ? `<div class="sec-title">Replanning &amp; failures</div>${reruns}` : ''}
    ${errorMix}
    <div class="sec-title">Routes</div>
    ${routeRows}
    <div class="sec-title">Recent runs</div>
    ${table}`;

  if (chartsHtml) {
    makeLineChart('chartRequests', req.labels, [
      { label: 'runs', data: req.values, borderColor: CHART_LINE, backgroundColor: 'rgba(255,255,255,0.08)', fill: true, tension: 0.35, pointRadius: 2, borderWidth: 2 },
      { label: 'failed', data: fail.values, borderColor: CHART_DANGER, backgroundColor: 'rgba(229,100,95,0.08)', fill: true, tension: 0.35, pointRadius: 2, borderWidth: 2 },
    ]);
    makeLineChart('chartLatency', lat.labels, [
      { label: 'avg ms', data: lat.values, borderColor: CHART_LINE, backgroundColor: 'rgba(255,255,255,0.08)', fill: true, tension: 0.35, spanGaps: true, pointRadius: 2, borderWidth: 2 },
    ]);
    makeDoughnutChart('chartRoutes', routeLabels, routeCounts);
    if (effortLabels.length) makeDoughnutChart('chartEffort', effortLabels, effortLabels.map(l => effortMix[l]));
    if (intentLabels.length) makeDoughnutChart('chartIntent', intentLabels, intentLabels.map(l => intentMix[l]));
    if (toolLabels.length) {
      makeBarChart('chartTools', toolLabels, toolLabels.map(l => toolMix[l].count));
    }
  }

  telemetryBody.querySelectorAll('tr[data-id]').forEach(row => {
    row.addEventListener('click', async () => {
      try {
        const res = await api(`/telemetry/events/${row.dataset.id}`);
        currentTelemetryEvent = await res.json();
        renderTelemetry(summary, events);
      } catch (err) {
        showToast(err.message || 'Could not load event');
      }
    });
  });
}

function renderTelemetryDetail(event, summary, events) {
  const metrics = event.metrics || {};
  const tags = event.tags || {};
  const spans = event.spans || [];

  const groupSpans = kind => spans.filter(s => (s.span_type || 'UNKNOWN') === kind);
  const spanBlock = (kind, title) => {
    const rows = groupSpans(kind);
    if (!rows.length) return '';
    return `<div class="sec-title">${title}</div>` + rows.map(s => `
      <div class="span-row">
        <div class="s-name">${escapeHtml(s.name)}</div>
        <div class="s-ms">${fmtMs(s.duration_ms)}</div>
      </div>`).join('');
  };

  const metricRows = Object.keys(metrics).sort().map(k =>
    `<div class="kv-row"><div class="k">${escapeHtml(k)}</div><div class="v">${fmtNum(metrics[k])}</div></div>`).join('');
  const tagRows = Object.keys(tags).sort()
    .filter(k => k !== 'request_id')
    .map(k => `<div class="kv-row"><div class="k">${escapeHtml(k)}</div><div class="v">${escapeHtml(String(tags[k]))}</div></div>`).join('');

  telemetryBody.innerHTML = `
    <button class="icon-btn back-btn" id="telemetryBack" title="Back" aria-label="Back">← Back</button>
    <div class="sec-title">Run #${event.id} · ${escapeHtml(event.route)} · ${event.success ? 'ok' : 'failed'}</div>
    ${kvRows([
      ['effort', tags.effort],
      ['intent', tags.intent],
      ['tools allowed', tags.tools_allowed],
      ['started', event.started_at],
      ['duration', fmtMs(event.duration_ms)],
      ['conversation', event.conversation_id],
      ['model', event.model],
      ['error', event.error_type],
    ])}
    ${spanBlock('STAGE', 'Research stages')}
    ${spanBlock('TOOL', 'Tool calls')}
    ${spanBlock('NODE', 'Node timings')}
    ${spanBlock('AGENT', 'Whole run')}
    ${metricRows ? `<div class="sec-title">Metrics</div>${metricRows}` : ''}
    ${tagRows ? `<div class="sec-title">Tags</div>${tagRows}` : ''}`;

  telemetryBody.querySelector('#telemetryBack').addEventListener('click', () => {
    currentTelemetryEvent = null;
    loadTelemetry();
  });
}

async function clearTelemetry() {
  if (!window.confirm('Clear all recorded telemetry logs?')) return;
  try {
    const res = await api('/telemetry/events', { method: 'DELETE' });
    const data = await res.json();
    showToast(`${data.deleted} event${data.deleted === 1 ? '' : 's'} cleared`);
    currentTelemetryEvent = null;
    loadTelemetry();
  } catch (err) {
    showToast(err.message || 'Could not clear logs');
  }
}

/* ---- wiring ---- */

analyticsBtn.addEventListener('click', openTelemetryModal);
telemetryModalClose.addEventListener('click', closeTelemetryModal);
telemetryRefresh.addEventListener('click', loadTelemetry);
telemetryClear.addEventListener('click', clearTelemetry);
telemetryModal.addEventListener('click', (e) => { if (e.target === telemetryModal) closeTelemetryModal(); });
