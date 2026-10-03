import { dom, state } from './state.js';
import { api, showToast } from './utils.js';
import { ensureConversation, loadConversations } from './conversations.js';
import { addRow, showTypingIndicator, createTypewriter, parseTail, renderMessageActions, renderSources, createThinkingPanel, setThinkingText } from './render.js';
import { createExecutionPanel } from './agentstream.js';
import { typesetMath, highlightCode } from './markdown.js';
import { popIn, popOut, revealBlock, sendPulse, staggerIn } from './motion.js';

const inputEl = dom.input;
const sendBtn = dom.sendBtn;
const modeMenuEl = document.getElementById('modeMenu');
const modeMenuBtn = document.getElementById('modeMenuBtn');
const modeMenuPop = document.getElementById('modeMenuPop');
const modeMenuLabelEl = document.getElementById('modeMenuLabel');
const MODE_LABELS = { instant: 'Instant', thinking: 'Thinking' };
const composerEl = document.querySelector('.composer');

export function autoResize() {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 170) + 'px';
}

export function updateSendState() {
  // spins the ring around the composer while a response is coming in
  composerEl.classList.toggle('busy', state.isStreaming);
  if (state.isStreaming) {
    sendBtn.classList.add('stop');
    sendBtn.disabled = false;
    sendBtn.title = 'Stop generating';
    sendBtn.setAttribute('aria-label', 'Stop generating');
  } else {
    sendBtn.classList.remove('stop');
    sendBtn.disabled = inputEl.value.trim().length === 0;
    sendBtn.title = 'Send';
    sendBtn.setAttribute('aria-label', 'Send message');
  }
}

// streams a chat or regenerate response into an assistant bubble and wires
// up the sources / details / regenerate affordances on completion
async function streamInto(contentEl, row, { path, body }) {
  const controller = new AbortController();
  state.currentController = controller;

  state.isStreaming = true;
  state.userStopped = false;
  updateSendState();

  const thinkingMode = body.agent_mode === 'thinking';
  let thinkingPanel = null;
  let execPanel = null;
  let appliedEvents = 0;

  let res;
  try {
    res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
    if (!res.ok) {
      const errText = await res.text().catch(() => '');
      throw new Error(`${res.status} ${res.statusText}: ${errText}`);
    }
  } catch (err) {
    state.isStreaming = false;
    state.currentController = null;
    updateSendState();
    if (err.name === 'AbortError' || controller.signal.aborted) {
      finishStream(contentEl, '', null, null, null, state.userStopped, false, null, thinkingPanel, execPanel);
      return;
    }
    finishStream(contentEl, '', null, null, err, false, false, null, thinkingPanel, execPanel);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  const typer = createTypewriter(contentEl);
  let full = '';
  let networkBroken = false;

  while (true) {
    let done = false;
    let piece = null;
    try {
      const r = await reader.read();
      done = r.done;
      piece = r.done ? null : decoder.decode(r.value, { stream: true });
    } catch (_) {
      networkBroken = true;
      break;
    }
    if (done) break;
    if (!piece) continue;
    full += piece;
    const parsed = parseTail(full);
    // events arrive interleaved with the answer text; only the new tail is
    // applied so replaying the whole buffer can't duplicate a row
    if (parsed.events.length > appliedEvents) {
      if (!execPanel) execPanel = createExecutionPanel(row);
      for (let i = appliedEvents; i < parsed.events.length; i++) execPanel.apply(parsed.events[i]);
      appliedEvents = parsed.events.length;
    }
    typer.push(parsed.text);
    // create the thinking panel lazily on the first real content so a model
    // that exposes no thoughts doesn't show an empty/fake reasoning section
    if (thinkingMode && parsed.thinking) {
      if (!thinkingPanel) { thinkingPanel = createThinkingPanel(row); revealBlock(thinkingPanel); }
      setThinkingText(thinkingPanel, parsed.thinking);
    }
  }

  try { await typer.finish(); } catch (_) {}

  state.isStreaming = false;
  state.currentController = null;
  updateSendState();

  const parsed = parseTail(full);
  finishStream(
    contentEl,
    parsed.text,
    parsed.sources,
    parsed.details,
    parsed.error,
    state.userStopped,
    networkBroken,
    parsed.thinking,
    thinkingPanel,
    execPanel
  );
}

function finishStream(contentEl, text, sources, details, error, stopped, networkBroken, thinking, thinkingPanel, execPanel) {
  const row = contentEl.closest('.row');
  const bubble = contentEl;

  if (execPanel) {
    execPanel.finish({ error: Boolean(error || networkBroken), stopped: Boolean(stopped) });
  }

  if (error) {
    bubble.innerHTML = '';
    const errSpan = document.createElement('span');
    errSpan.style.color = 'var(--danger)';
    errSpan.textContent = `Error: ${error.message || 'Generation failed'}`;
    bubble.appendChild(errSpan);
    if (thinkingPanel) thinkingPanel.remove();
    renderMessageActions(row, { details: null, stopped: false });
  } else if (stopped && !text.trim()) {
    bubble.innerHTML = '<em style="color:var(--text-dim)">Generation stopped.</em>';
    if (thinkingPanel) thinkingPanel.remove();
    renderMessageActions(row, { details: null, stopped: true });
  } else if (networkBroken && !text.trim()) {
    bubble.innerHTML = '<em style="color:var(--danger)">Stream interrupted — the response did not complete.</em>';
    if (thinkingPanel) thinkingPanel.remove();
    renderMessageActions(row, { details: null, stopped: false });
  } else if (!text.trim()) {
    bubble.innerHTML = '<em style="color:var(--text-dim)">No response.</em>';
    if (thinkingPanel) thinkingPanel.remove();
    renderMessageActions(row, { details: null, stopped: false });
  } else {
    typesetMath(bubble);
    highlightCode(bubble);
    if (sources) {
      renderSources(bubble, sources);
      staggerIn(bubble.querySelectorAll('.sources-count, .source-item'), { y: 8 });
    }
    renderMessageActions(row, { details, stopped });
    scrollToBottom();
  }

  loadConversations();
}

function scrollToBottom() {
  dom.messages.scrollTop = dom.messages.scrollHeight;
}

export async function regenerateLast() {
  if (!state.currentConversationId || state.isStreaming) return;
  const rows = [...dom.messages.querySelectorAll('.row.assistant')];
  const row = rows[rows.length - 1];
  if (!row) return;
  const bubble = row.querySelector('.bubble-content');

  row.querySelectorAll('.msg-actions, .details-panel, .source-list, .sources-count, .thinking-panel, .agent-panel').forEach(n => n.remove());
  bubble.innerHTML = '';
  showTypingIndicator(bubble);

  const body = { conversation_id: state.currentConversationId, agent_mode: state.agentMode };

  await streamInto(bubble, row, { path: '/chat/regenerate', body });
}

export async function sendMessage() {
  const text = inputEl.value.trim();
  if (!text || state.isStreaming) return;

  const conversationId = await ensureConversation();

  sendPulse();
  inputEl.value = '';
  autoResize();
  addRow('user', text);
  const assistantContent = addRow('assistant', '');
  const row = assistantContent.closest('.row');
  showTypingIndicator(assistantContent);

  const body = { query: text, conversation_id: conversationId, agent_mode: state.agentMode };
  if (state.pendingMode) { body.mode = state.pendingMode; state.pendingMode = null; }

  await streamInto(assistantContent, row, { path: '/chat/', body });
}

/* ---- wiring ---- */

sendBtn.addEventListener('click', () => {
  if (state.isStreaming) {
    state.userStopped = true;
    if (state.currentController) state.currentController.abort();
  } else {
    sendMessage();
  }
});

inputEl.addEventListener('input', () => { autoResize(); updateSendState(); });
inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

/* response effort menu: collapsible, sits next to the send button */

// also used by settings.js, which applies the stored default effort
export function setAgentMode(mode) {
  if (!MODE_LABELS[mode]) return;
  state.agentMode = mode;
  modeMenuLabelEl.textContent = MODE_LABELS[mode];
  modeMenuPop.querySelectorAll('.mode-menu-item').forEach((b) => {
    const on = b.dataset.mode === mode;
    b.classList.toggle('active', on);
    b.setAttribute('aria-checked', String(on));
  });
}

// open state lives on aria-expanded, not .hidden: the popover stays
// un-hidden for the length of its exit tween
const modeMenuOpen = () => modeMenuBtn.getAttribute('aria-expanded') === 'true';

function closeModeMenu() {
  modeMenuBtn.setAttribute('aria-expanded', 'false');
  popOut(modeMenuPop);
}

modeMenuBtn.addEventListener('click', (e) => {
  e.stopPropagation();
  if (modeMenuOpen()) { closeModeMenu(); return; }
  modeMenuBtn.setAttribute('aria-expanded', 'true');
  popIn(modeMenuPop);
});

modeMenuPop.addEventListener('click', (e) => {
  const item = e.target.closest('.mode-menu-item');
  if (!item) return;
  setAgentMode(item.dataset.mode);
  closeModeMenu();
});

document.addEventListener('click', (e) => {
  if (!modeMenuOpen()) return;
  if (modeMenuEl.contains(e.target)) return;
  closeModeMenu();
});

// delegated, the empty state gets replaced wholesale on every remount
dom.messages.addEventListener('click', (e) => {
  const chip = e.target.closest('.chip');
  if (!chip) return;
  inputEl.value = chip.dataset.prompt;
  autoResize();
  updateSendState();
  inputEl.focus();
});
