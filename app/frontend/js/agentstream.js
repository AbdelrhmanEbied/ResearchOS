// Live execution panel for the agent run.
//
// The backend streams one normalized event per line between EVENT_MARKER
// frames (see app/backend/services/agent_events.py). This module renders those
// events as a Claude Code style tree: the root agent, each sub-graph, every
// step inside it and every tool call with expandable input/output.
//
// Nothing here invents progress: rows appear when the server reports a start,
// finish when it reports an end, and durations come from the server.

import { fmtMs } from './utils.js';

const ICON_RUNNING = '<span class="ar-spin" aria-hidden="true"></span>';
const ICON_DONE = '<span class="ar-check" aria-hidden="true">✓</span>';
const ICON_FAILED = '<span class="ar-x" aria-hidden="true">✕</span>';
const ICON_STOPPED = '<span class="ar-stop" aria-hidden="true">■</span>';
const ICON_PENDING = '<span class="ar-dot" aria-hidden="true"></span>';
const ICON_TOOL = '<span class="ar-tool-ico" aria-hidden="true">⚙</span>';
const ICON_SUB = '<span class="ar-sub-ico" aria-hidden="true">◇</span>';

const MAX_DETAIL_CHARS = 4000;

function detailText(value) {
  if (value == null) return '';
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  if (text.length <= MAX_DETAIL_CHARS) return text;
  return `${text.slice(0, MAX_DETAIL_CHARS)}\n… [+${text.length - MAX_DETAIL_CHARS} chars]`;
}

function depthOf(el) {
  return Number(el.style.getPropertyValue('--depth')) || 0;
}

export function createExecutionPanel(row) {
  const panel = document.createElement('div');
  // collapsed until clicked: the header keeps the live badge + timer, the
  // step/tool tree only shows on demand (Claude-style)
  panel.className = 'agent-panel';

  const head = document.createElement('button');
  head.className = 'agent-head';
  head.type = 'button';
  head.setAttribute('aria-expanded', 'false');
  head.innerHTML =
    '<span class="agent-badge running">working</span>' +
    '<span class="agent-title">Research Agent</span>' +
    '<span class="agent-time">0.0s</span>' +
    '<span class="agent-chev" aria-hidden="true">›</span>';

  const body = document.createElement('div');
  body.className = 'agent-body';
  body.hidden = true;

  const rowsEl = document.createElement('div');
  rowsEl.className = 'agent-rows';
  body.appendChild(rowsEl);

  panel.appendChild(head);
  panel.appendChild(body);

  const inner = row.querySelector('.row-inner') || row;
  row.insertBefore(panel, inner);

  const badge = head.querySelector('.agent-badge');
  const timeEl = head.querySelector('.agent-time');
  const rowsById = new Map();
  const depths = new Map();

  let startedAt = Date.now();
  let ticker = null;
  let ended = false;

  const depthFor = (scope) => (scope && depths.has(scope) ? depths.get(scope) : -1) + 1;

  head.addEventListener('click', () => {
    const open = panel.classList.toggle('open');
    head.setAttribute('aria-expanded', String(open));
    body.hidden = !open;
  });

  function startTicker() {
    if (ticker) return;
    ticker = setInterval(() => {
      if (ended) return;
      timeEl.textContent = ((Date.now() - startedAt) / 1000).toFixed(1) + 's';
    }, 200);
  }

  function stopTicker() {
    if (ticker) clearInterval(ticker);
    ticker = null;
  }

  function setHead(state, durationMs) {
    stopTicker();
    badge.className = `agent-badge ${state}`;
    badge.textContent =
      state === 'done'
        ? 'done'
        : state === 'failed'
          ? 'failed'
          : state === 'stopped'
            ? 'stopped'
            : 'working';
    if (durationMs != null) timeEl.textContent = fmtMs(durationMs);
    else timeEl.textContent = ((Date.now() - startedAt) / 1000).toFixed(1) + 's';
  }

  function toggleSubtree(rec) {
    const collapsed = rec.el.classList.toggle('collapsed');
    let sibling = rec.el.nextElementSibling;
    while (sibling) {
      if (depthOf(sibling) <= rec.depth) break;
      sibling.hidden = collapsed;
      sibling = sibling.nextElementSibling;
    }
  }

  function makeRow({ id, depth, cls, icon, label }) {
    let rec = rowsById.get(id);
    if (rec) return rec;

    const el = document.createElement('div');
    el.className = `agent-row ${cls}`;
    el.dataset.id = id;
    el.style.setProperty('--depth', String(depth));

    const headEl = document.createElement('div');
    headEl.className = 'ar-head';

    const iconEl = document.createElement('span');
    iconEl.className = 'ar-icon';
    iconEl.innerHTML = icon || ICON_PENDING;

    const labelEl = document.createElement('span');
    labelEl.className = 'ar-label';
    labelEl.textContent = label;

    const metaEl = document.createElement('span');
    metaEl.className = 'ar-meta';

    headEl.appendChild(iconEl);
    headEl.appendChild(labelEl);
    headEl.appendChild(metaEl);
    el.appendChild(headEl);
    rowsEl.appendChild(el);

    rec = { id, depth, el, iconEl, labelEl, metaEl };
    rowsById.set(id, rec);
    depths.set(id, depth);

    el.addEventListener('click', (e) => {
      if (e.target.closest('a')) return;
      if (el.classList.contains('subgraph')) {
        toggleSubtree(rec);
        return;
      }
      const detail = el.querySelector('.ar-detail');
      if (!detail) return;
      const open = (detail.hidden = !detail.hidden);
      el.classList.toggle('open', open);
    });

    return rec;
  }

  function markRunning(rec, meta) {
    rec.el.classList.remove('done', 'failed', 'stopped');
    rec.el.classList.add('running');
    rec.iconEl.innerHTML = ICON_RUNNING;
    if (meta != null) rec.metaEl.textContent = meta;
  }

  function markDone(rec, meta) {
    rec.el.classList.remove('running', 'failed', 'stopped');
    rec.el.classList.add('done');
    rec.iconEl.innerHTML = ICON_DONE;
    rec.metaEl.textContent = meta || '';
  }

  function markFailed(rec, message) {
    rec.el.classList.remove('running', 'done', 'stopped');
    rec.el.classList.add('failed');
    rec.iconEl.innerHTML = ICON_FAILED;
    if (message) rec.el.title = message;
  }

  function addErrorNote(rec, message) {
    if (rec.el.querySelector('.ar-error')) return;
    const note = document.createElement('div');
    note.className = 'ar-error';
    note.textContent = message || 'Step failed';
    rec.el.appendChild(note);
    rec.el.classList.add('expandable');
  }

  function attachDetail(rec, sections) {
    let detail = rec.el.querySelector('.ar-detail');
    if (!detail) {
      detail = document.createElement('div');
      detail.className = 'ar-detail';
      detail.hidden = true;
      rec.el.appendChild(detail);
      rec.el.classList.add('expandable');
    }
    detail.innerHTML = '';
    for (const [title, value] of sections) {
      const text = detailText(value);
      if (!text) continue;
      const sec = document.createElement('div');
      sec.className = 'ar-sec';
      const t = document.createElement('div');
      t.className = 'ar-sec-title';
      t.textContent = title;
      const pre = document.createElement('pre');
      pre.className = 'ar-pre';
      pre.textContent = text;
      sec.appendChild(t);
      sec.appendChild(pre);
      detail.appendChild(sec);
    }
  }

  function toolMeta(ev) {
    const parts = [];
    if (ev.summary) parts.push(ev.summary);
    if (ev.duration_ms != null) parts.push(fmtMs(ev.duration_ms));
    return parts.join(' · ');
  }

  function apply(ev) {
    if (!ev || typeof ev !== 'object') return;

    switch (ev.type) {
      case 'agent_started': {
        startedAt = Date.now();
        ended = false;
        setHead('running');
        startTicker();
        break;
      }

      case 'agent_status': {
        const rec = makeRow({
          id: ev.id,
          depth: depthFor(ev.scope),
          cls: 'node',
          icon: ICON_PENDING,
          label: ev.label || ev.node,
        });
        const parts = [];
        if (ev.state) parts.push(String(ev.state));
        if (ev.duration_ms != null) parts.push(fmtMs(ev.duration_ms));
        const meta = parts.join(' · ');
        if (ev.status === 'done') markDone(rec, meta);
        else markRunning(rec, meta || '…');
        break;
      }

      case 'subgraph_started': {
        const rec = makeRow({
          id: ev.id,
          depth: depthFor(ev.scope),
          cls: 'subgraph',
          icon: ICON_SUB,
          label: ev.label || ev.name,
        });
        markRunning(rec, '…');
        break;
      }

      case 'subgraph_finished': {
        const rec = rowsById.get(ev.id);
        if (rec) markDone(rec, ev.duration_ms != null ? fmtMs(ev.duration_ms) : '');
        break;
      }

      case 'tool_started': {
        const rec = makeRow({
          id: ev.id,
          depth: depthFor(ev.scope),
          cls: 'tool',
          icon: ICON_TOOL,
          label: ev.label || ev.name,
        });
        rec.input = ev.input;
        markRunning(rec, '…');
        attachDetail(rec, [['Input', ev.input]]);
        break;
      }

      case 'tool_finished': {
        const rec = rowsById.get(ev.id);
        if (!rec) break;
        if (ev.ok === false) {
          markFailed(rec, ev.error);
          addErrorNote(rec, ev.error);
        } else {
          markDone(rec, toolMeta(ev));
          attachDetail(rec, [
            ['Input', rec.input],
            ['Output', ev.output],
          ]);
        }
        break;
      }

      case 'error': {
        ended = true;
        stopTicker();
        const rec = ev.id ? rowsById.get(ev.id) : null;
        if (rec) {
          markFailed(rec, ev.message);
          addErrorNote(rec, ev.message);
        } else {
          const fallback = makeRow({
            id: ev.id || `error-${Date.now()}`,
            depth: depthFor(ev.scope),
            cls: 'error',
            icon: ICON_FAILED,
            label: ev.label || 'Failed',
          });
          fallback.el.classList.add('failed');
          addErrorNote(fallback, ev.message);
        }
        setHead('failed');
        break;
      }

      case 'agent_finished': {
        ended = true;
        setHead('done', ev.duration_ms);
        break;
      }

      default:
        break;
    }
  }

  function finish({ error, stopped } = {}) {
    stopTicker();
    if (ended) return;
    ended = true;
    if (error) {
      setHead('failed');
      return;
    }
    setHead(stopped ? 'stopped' : 'done');
    if (stopped) {
      rowsEl.querySelectorAll('.agent-row.running').forEach((el) => {
        el.classList.remove('running');
        el.classList.add('stopped');
        const icon = el.querySelector('.ar-icon');
        if (icon) icon.innerHTML = ICON_STOPPED;
      });
    }
  }

  startTicker();

  return { el: panel, apply, finish };
}
