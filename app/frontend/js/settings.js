import { api, showToast } from './utils.js';
import { setAgentMode } from './chat.js';
import { closeModal, openModal, staggerIn } from './motion.js';

const settingsModal = document.getElementById('settingsModal');
const settingsModalClose = document.getElementById('settingsModalClose');
const settingsBtn = document.getElementById('settingsBtn');
const setProvider = document.getElementById('setProvider');
const setModel = document.getElementById('setModel');
const setApiKey = document.getElementById('setApiKey');
const setLlmSave = document.getElementById('setLlmSave');
const setSearchType = document.getElementById('setSearchType');
const setSearchDepth = document.getElementById('setSearchDepth');
const setRetrieveLimit = document.getElementById('setRetrieveLimit');
const setRerank = document.getElementById('setRerank');
const setRerankTopK = document.getElementById('setRerankTopK');
const setRetrievalSave = document.getElementById('setRetrievalSave');
const setResultsPerPage = document.getElementById('setResultsPerPage');
const setPagesFetched = document.getElementById('setPagesFetched');
const setWebSave = document.getElementById('setWebSave');
const setRecursionLimit = document.getElementById('setRecursionLimit');
const setIterations = document.getElementById('setIterations');
const setEffort = document.getElementById('setEffort');
const setAgentSave = document.getElementById('setAgentSave');
const settingsStatus = document.getElementById('settingsStatus');

let bootApplied = false;

function num(input, min, max) {
  const n = Number(input.value);
  if (Number.isNaN(n) || n < min || n > max) {
    showToast(`Value must be between ${min} and ${max}`);
    input.focus();
    return null;
  }
  return n;
}

function put(path, body, okMessage) {
  return api(path, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then((res) => {
    if (!res.ok) throw new Error(`${res.status}`);
    showToast(okMessage);
    loadSettings();
    return true;
  }).catch(() => {
    showToast(`Failed to save ${okMessage}`);
    return false;
  });
}

async function loadSettings() {
  try {
    const res = await api('/settings/');
    const s = await res.json();

    setProvider.value = s.llm.default_provider;
    setModel.value = s.llm.default_model;
    const hasKey = s.providers && s.providers[s.llm.default_provider]
      && s.providers[s.llm.default_provider].has_api_key;
    setApiKey.placeholder = hasKey ? 'Stored — leave blank to keep' : 'Uses .env';

    setSearchType.value = s.retrieval.search_type;
    setRetrieveLimit.value = s.retrieval.limit;
    setRerankTopK.value = s.retrieval.rerank_top_k;
    setRerank.checked = !!s.retrieval.rerank;

    setResultsPerPage.value = s.web.results_per_query;
    setPagesFetched.value = s.web.pages_fetched;
    setSearchDepth.value = s.web.search_depth;

    setRecursionLimit.value = s.agent.recursion_limit;
    setIterations.value = s.agent.max_research_iterations;
    setEffort.value = s.agent.default_effort;

    // only the first load of the session applies the default effort, so
    // opening settings never stomps the effort picked in the composer
    if (!bootApplied) {
      bootApplied = true;
      setAgentMode(s.agent.default_effort);
    }

    settingsStatus.textContent = `${s.llm.default_provider} · ${s.llm.default_model}`;
  } catch (_) {
    settingsStatus.textContent = 'Could not load settings';
  }
}

export function openSettingsModal() {
  openModal(settingsModal);
  staggerIn(settingsModal.querySelectorAll('.modal-body > *'), { y: 8, amount: 0.4 });
  loadSettings();
}
export function closeSettingsModal() { closeModal(settingsModal); }

setLlmSave.addEventListener('click', async () => {
  const model = setModel.value.trim();
  const provider = setProvider.value;
  if (!model) { showToast('Enter a model name first'); setModel.focus(); return; }
  try {
    await api('/settings/llm', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, model_provider: provider }),
    });
    const key = setApiKey.value.trim();
    if (key) {
      await api('/settings/api-keys', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, api_key: key }),
      });
      setApiKey.value = '';
    }
    showToast('Model settings saved');
    loadSettings();
  } catch (_) {
    showToast('Failed to save model settings');
  }
});

setRetrievalSave.addEventListener('click', () => {
  const limit = num(setRetrieveLimit, 1, 50);
  const topK = num(setRerankTopK, 1, 50);
  if (limit === null || topK === null) return;
  put('/settings/retrieval', {
    search_type: setSearchType.value,
    limit,
    rerank: setRerank.checked,
    rerank_top_k: topK,
  }, 'Retrieval settings saved');
});

setWebSave.addEventListener('click', () => {
  const perQuery = num(setResultsPerPage, 1, 10);
  const pages = num(setPagesFetched, 1, 10);
  if (perQuery === null || pages === null) return;
  put('/settings/web', {
    results_per_query: perQuery,
    pages_fetched: pages,
    search_depth: setSearchDepth.value,
  }, 'Web search settings saved');
});

setAgentSave.addEventListener('click', () => {
  const recursion = num(setRecursionLimit, 25, 500);
  const iterations = num(setIterations, 1, 6);
  if (recursion === null || iterations === null) return;
  put('/settings/agent', {
    recursion_limit: recursion,
    max_research_iterations: iterations,
    default_effort: setEffort.value,
  }, 'Agent settings saved').then((saved) => { if (saved) setAgentMode(setEffort.value); });
});

settingsBtn.addEventListener('click', openSettingsModal);
settingsModalClose.addEventListener('click', closeSettingsModal);
settingsModal.addEventListener('click', (e) => { if (e.target === settingsModal) closeSettingsModal(); });

// pull defaults at boot so the composer starts on the configured effort
loadSettings();
