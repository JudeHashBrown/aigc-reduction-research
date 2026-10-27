'use strict';

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const editor = $('#editor');

const state = {
  source: '',
  current: '',
  report: null,
  view: 'source',
  panel: 'issues',
  issueFilter: 'all',
  activeIssue: null,
  strength: 'conservative',
  config: null,
  doc: null,
  notices: [],
  documentNotices: [],
  guard: null,
  rewriteRunning: false,
  analyzeRunning: false,
  safeFixRunning: false,
  billing: null,
  plans: [],
  paymentInfo: null,
  billingBusy: false,
  composerStarted: false,
  documentRevision: 0,
  openModal: null,
  modalReturn: null,
  progressOpen: false,
  pendingRequestId: null,
  pollFailures: 0,
  trialMode: null,
  authenticated: false,
  user: null,
  csrfToken: '',
  sessionReady: false,
  workspaceUserId: null,
  sessionRecoveryPromise: null,
};

const SAMPLE = `在数字化技术不断快速发展的时代背景下，人工智能写作工具逐渐进入高校学习场景。本文将深入探讨一个至关重要的问题：学生应当如何合理使用这些工具。

这不仅是一次工具更新，更是学习方式的深刻变革。系统可以提供资料整理、语句润色和格式检查。部分未具名的专家认为，这些功能可能在一定程度上或许能够提升写作效率，充分彰显了技术赋能教育的重要价值。

本次调查共收到 126 份问卷，其中 18 份没有完成全部题目。数据只说明受访者的使用情况，不能代表所有高校学生。后续研究计划在获得新的授权后扩大样本，目前尚未开始。

总而言之，让我们拭目以待，期待更多可能。

It was found that AI writing tools may improve editing efficiency. This study delves into a pivotal realm and provides robust, comprehensive, and valuable insights. In conclusion, future research could examine how students use these tools in different courses.`;

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function toast(message, type = 'success') {
  const element = $('#toast');
  element.textContent = message;
  element.setAttribute('role', type === 'error' ? 'alert' : 'status');
  element.classList.add('show');
  clearTimeout(element._hideTimer);
  element._hideTimer = setTimeout(() => element.classList.remove('show'), 3200);
}

function setPersistent(message, kind = 'info') {
  const box = $('#persistentMessage');
  $('#persistentText').textContent = message;
  box.className = `inline-status ${kind === 'info' ? '' : kind}`.trim();
  box.hidden = false;
  box.setAttribute('role', kind === 'error' ? 'alert' : 'status');
}

function clearPersistent() {
  $('#persistentMessage').hidden = true;
  $('#persistentText').textContent = '';
}

function sessionPayload(data) {
  return data && typeof data.session === 'object' ? data.session : (data || {});
}

function trialUserName(user) {
  if (!user || typeof user !== 'object') return '匿名访客';
  return String(user.display_name || user.name || user.label || user.id || '匿名访客');
}

function renderSessionUI() {
  const managedAccess = state.trialMode === true;
  document.body.classList.toggle('trial-mode', managedAccess);
  const userBox = $('#trialUser');
  userBox.hidden = !(managedAccess && state.authenticated);
  $('#trialUserName').textContent = trialUserName(state.user);
  $('#trialUserMode').textContent = '匿名试用';
  $('#openAccessNotice').hidden = !managedAccess;
  $('#upgradeBtn').hidden = managedAccess;
  if (managedAccess) {
    $('#billingTitle').textContent = '我的试用额度';
    $('#billingNotice').textContent = '匿名试用不提供自助购买，访客额度由管理员统一设置。';
  } else {
    $('#billingTitle').textContent = '套餐与文字额度';
  }
}

function handleUnauthorized(message) {
  if (state.trialMode === false) return;
  state.csrfToken = '';
  state.authenticated = false;
  renderSessionUI();
  if (state.progressOpen) showProgress(false);
  setPersistent(message || '匿名会话已失效，正在尝试重建。', 'warn');
}

function applySession(data) {
  const session = sessionPayload(data);
  const nextUser = session.user && typeof session.user === 'object' ? session.user : null;
  const nextUserId = nextUser ? String(nextUser.id || nextUser.account_id || nextUser.name || '') : '';
  state.trialMode = Boolean(session.trial_mode);
  state.authenticated = state.trialMode ? Boolean(session.authenticated) : true;
  if (state.authenticated && state.workspaceUserId && nextUserId && state.workspaceUserId !== nextUserId) {
    clearLocalWorkspace();
  }
  state.user = nextUser;
  if (state.authenticated && nextUserId) state.workspaceUserId = nextUserId;
  if (session.csrf_token) state.csrfToken = String(session.csrf_token);
  else if (!state.authenticated) state.csrfToken = '';
  state.sessionReady = true;
  renderSessionUI();
  if (state.trialMode && !state.authenticated) {
    setPersistent('无法建立匿名访客会话，请刷新页面重试。', 'error');
  }
  return state.authenticated;
}

function bytesToB64(buffer) {
  let encoded = '';
  const bytes = new Uint8Array(buffer);
  for (let i = 0; i < bytes.length; i += 0x8000) {
    encoded += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(encoded);
}

async function responseJson(response) {
  let data;
  try {
    data = await response.json();
  } catch (_error) {
    const error = new Error(`服务返回异常（HTTP ${response.status}）`);
    error.status = response.status;
    error.data = null;
    throw error;
  }
  if (data && typeof data === 'object' && data.csrf_token) {
    state.csrfToken = String(data.csrf_token);
  }
  if (!response.ok) {
    const error = new Error(data.error || `请求失败（HTTP ${response.status}）`);
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

function requestHeaders(json = false) {
  const headers = {};
  if (json) headers['Content-Type'] = 'application/json';
  if (state.csrfToken) headers['X-CSRF-Token'] = state.csrfToken;
  return headers;
}

async function recoverTrialSession() {
  if (!state.trialMode) throw new Error('当前不是匿名试用模式');
  if (state.sessionRecoveryPromise) return state.sessionRecoveryPromise;
  const recovery = (async () => {
    const response = await fetch('/api/session', {
      cache: 'no-store',
      credentials: 'same-origin',
      headers: requestHeaders(false),
    });
    const data = await responseJson(response);
    const session = sessionPayload(data);
    if (!session.trial_mode || !session.authenticated) {
      throw new Error('无法重建匿名访客会话');
    }
    applySession(data);
    return data;
  })();
  state.sessionRecoveryPromise = recovery;
  try {
    return await recovery;
  } finally {
    if (state.sessionRecoveryPromise === recovery) state.sessionRecoveryPromise = null;
  }
}

async function api(path, body, retrySession = true) {
  let response;
  try {
    response = await fetch(path, {
      method: 'POST',
      credentials: 'same-origin',
      headers: requestHeaders(true),
      body: JSON.stringify(body),
    });
  } catch (_error) {
    const error = new Error('无法连接本地服务');
    error.status = 0;
    error.data = null;
    throw error;
  }
  try {
    return await responseJson(response);
  } catch (error) {
    if (error.status === 401) {
      if (state.trialMode && retrySession && !path.startsWith('/api/session')) {
        try {
          await recoverTrialSession();
          return api(path, body, false);
        } catch (recoveryError) {
          handleUnauthorized(`匿名访客会话续期失败：${recoveryError.message}`);
          throw recoveryError;
        }
      }
      handleUnauthorized(error.message);
    }
    throw error;
  }
}

async function getApi(path, retrySession = true) {
  let response;
  try {
    response = await fetch(path, {
      cache: 'no-store',
      credentials: 'same-origin',
      headers: requestHeaders(false),
    });
  } catch (_error) {
    const error = new Error('无法连接本地服务');
    error.status = 0;
    error.data = null;
    throw error;
  }
  try {
    return await responseJson(response);
  } catch (error) {
    if (error.status === 401) {
      if (state.trialMode && retrySession && !path.startsWith('/api/session')) {
        try {
          await recoverTrialSession();
          return getApi(path, false);
        } catch (recoveryError) {
          handleUnauthorized(`匿名访客会话续期失败：${recoveryError.message}`);
          throw recoveryError;
        }
      }
      handleUnauthorized(error.message);
    }
    throw error;
  }
}

function showInspectorState(kind = 'default', title, description) {
  const empty = $('#inspectorEmpty');
  const icon = empty.querySelector('.empty-icon');
  const steps = $('#inspectorSteps');
  $('#results').style.display = 'none';
  empty.style.display = 'grid';

  if (kind === 'loading') {
    icon.textContent = '◎';
    icon.classList.add('loading-orb');
    $('#inspectorTitle').textContent = title || '正在检查表达与事实边界';
    $('#inspectorDescription').textContent = description || '分析不会消耗改写额度，完成后可逐条回到原文。';
    steps.innerHTML = '<div class="skeleton"></div><div class="skeleton"></div><div class="skeleton short"></div>';
    return;
  }

  icon.classList.remove('loading-orb');
  if (kind === 'error') {
    icon.textContent = '!';
    $('#inspectorTitle').textContent = title || '分析没有完成';
    $('#inspectorDescription').textContent = description || '文本仍保留在编辑器中，可以直接重试。';
    steps.innerHTML = '<button class="btn primary" id="retryAnalyzeBtn">重新分析</button>';
    $('#retryAnalyzeBtn').onclick = analyze;
    return;
  }

  icon.textContent = '◎';
  $('#inspectorTitle').textContent = title || '先分析，再决定怎么改';
  $('#inspectorDescription').textContent = description || '分析不消耗改写额度，每条结论都可回到原文复核。';
  steps.innerHTML = [
    '<div class="empty-step"><i>1</i><span>先定位模板化、空泛和需人工判断的表达</span></div>',
    '<div class="empty-step"><i>2</i><span>确认数字、引用、专名与语义边界</span></div>',
    '<div class="empty-step"><i>3</i><span>只在需要时选择安全清理或保真改写</span></div>',
  ].join('');
}

function invalidateReport({ preserveMessage = false } = {}) {
  state.report = null;
  state.guard = null;
  state.activeIssue = null;
  state.issueFilter = 'all';
  $('#issueCount').textContent = '0';
  $('#mobileIssueCount').textContent = '0';
  $('#inspectorIssueCount').textContent = '0';
  $('#safeBtn').disabled = true;
  $('#rewriteSuccess').hidden = true;
  $$('.issue-filter').forEach((button) => {
    const isActive = button.dataset.filter === 'all';
    button.classList.toggle('active', isActive);
    button.setAttribute('aria-pressed', String(isActive));
  });
  showInspectorState();
  if (!preserveMessage) clearPersistent();
  syncRewriteButton();
  updateWorkflow();
}

function localBillableChars(text) {
  const whitespace = /^[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]$/u;
  const latin = /\p{Script=Latin}/u;
  const letter = /\p{Letter}/u;
  const digit = /\p{Decimal_Number}/u;
  const mark = /\p{Mark}/u;
  const punctuation = /\p{Punctuation}/u;
  const chars = Array.from(String(text || '')).filter((char) =>
    whitespace.test(char) || !(/\p{Cf}/u.test(char)
      || /[\uFE00-\uFE0F\u{E0100}-\u{E01EF}]/u.test(char)
      || /\p{Cc}/u.test(char)));
  let units = 0;
  let inWord = false;
  for (let index = 0; index < chars.length; index += 1) {
    const char = chars[index];
    const isWord = (latin.test(char) && letter.test(char)) || digit.test(char);
    if (isWord) {
      if (!inWord) units += 1;
      inWord = true;
    } else if (mark.test(char) && inWord) {
      continue;
    } else if ((char === "'" || char === '’') && inWord
      && ((latin.test(chars[index + 1] || '') && letter.test(chars[index + 1] || '')) || digit.test(chars[index + 1] || ''))) {
      continue;
    } else {
      inWord = false;
      if (!whitespace.test(char) && !punctuation.test(char)) units += 1;
    }
  }
  return units;
}

function updateComposer() {
  const hasText = Boolean((state.current || state.source).trim());
  const showGuide = !hasText && !state.composerStarted;
  $('#emptyGuide').hidden = !showGuide;
  $('#editorWrap').classList.toggle('is-empty', showGuide);
}

let sourcePreviewCache = { text: null, range: null };

function renderSourcePreview() {
  const preview = $('#sourcePreview');
  const text = String(state.source || '');
  const finding = Number.isInteger(state.activeIssue) ? state.report?.findings?.[state.activeIssue] : null;
  let highlightStart = -1;
  let highlightEnd = -1;
  if (finding) {
    const matched = String(finding.matched || '');
    const reportedStart = codePointToCodeUnit(text, Number(finding.start || 0));
    const reportedEnd = codePointToCodeUnit(text, Number(finding.end || 0));
    if (matched && text.slice(reportedStart, reportedEnd) === matched) {
      highlightStart = reportedStart;
      highlightEnd = reportedEnd;
    } else if (matched) {
      const sourceMatch = text.indexOf(matched);
      if (sourceMatch >= 0) {
        highlightStart = sourceMatch;
        highlightEnd = sourceMatch + matched.length;
      }
    }
  }
  const range = finding ? `${highlightStart}:${highlightEnd}:${String(finding.matched || '')}` : '';
  if (sourcePreviewCache.text === text && sourcePreviewCache.range === range) return;
  sourcePreviewCache = { text, range };
  if (!text.trim()) {
    preview.className = 'source-preview is-empty';
    preview.textContent = '原稿会在导入后显示在这里。';
    return;
  }

  preview.className = 'source-preview';
  let offset = 0;
  preview.innerHTML = text.split('\n').map((line) => {
    const lineStart = offset;
    const lineEnd = lineStart + line.length;
    offset = lineEnd + 1;
    const overlapStart = Math.max(lineStart, highlightStart);
    const overlapEnd = Math.min(lineEnd, highlightEnd);
    let content;
    if (overlapStart < overlapEnd) {
      const localStart = overlapStart - lineStart;
      const localEnd = overlapEnd - lineStart;
      content = `${esc(line.slice(0, localStart))}<mark>${esc(line.slice(localStart, localEnd))}</mark>${esc(line.slice(localEnd))}`;
    } else {
      content = esc(line);
    }
    return `<div class="doc-line"><span>${content || '&nbsp;'}</span></div>`;
  }).join('');
}

function updateWorkflow() {
  const hasText = Boolean((state.current || state.source).trim());
  const hasReport = Boolean(state.report);
  const changed = hasText && state.current !== state.source;
  const active = !hasText ? 'input' : !hasReport ? 'analyze' : changed ? 'review' : 'optimize';
  const order = ['input', 'analyze', 'optimize', 'review'];
  const activeIndex = order.indexOf(active);

  $$('.flow-step').forEach((step) => {
    const index = order.indexOf(step.dataset.flow);
    step.classList.toggle('active', step.dataset.flow === active);
    step.classList.toggle('done', index < activeIndex);
    if (step.dataset.flow === active) step.setAttribute('aria-current', 'step');
    else step.removeAttribute('aria-current');
  });

  const badge = $('#documentState');
  badge.className = 'document-state';
  if (!hasText) {
    badge.textContent = '待导入';
  } else if (!hasReport) {
    badge.textContent = '待分析';
    badge.classList.add('changed');
  } else if (changed) {
    badge.textContent = '已优化 · 待复核';
    badge.classList.add('changed');
  } else {
    badge.textContent = '已分析';
    badge.classList.add('ready');
  }
}

const STRENGTH_LABELS = {
  conservative: ['保守', '1 候选', 1],
  balanced: ['平衡', '2 候选', 1],
  deep: ['深度', '3 候选', 1.5],
};

function estimateCost() {
  const chars = localBillableChars(state.current);
  const [label, candidates, multiplier] = STRENGTH_LABELS[state.strength] || STRENGTH_LABELS.conservative;
  const required = Math.ceil(chars * multiplier);
  const balance = state.billing && Number.isFinite(Number(state.billing.balance))
    ? Number(state.billing.balance)
    : null;
  $('#costEstimate').textContent = `${required.toLocaleString('zh-CN')} 额度`;
  $('#costBalance').textContent = balance === null ? '—' : `${balance.toLocaleString('zh-CN')} 额度`;
  $('#costMode').textContent = `${label}模式 · ${multiplier}×`;
  $('#confirmChars').textContent = `${chars.toLocaleString('zh-CN')} 计费单位`;
  $('#confirmMode').textContent = `${label} · ${candidates}`;
  $('#confirmRequired').textContent = `${required.toLocaleString('zh-CN')} 额度`;
  $('#confirmBalance').textContent = balance === null ? '—' : `${balance.toLocaleString('zh-CN')} 额度`;
  return { chars, required, balance, label, multiplier };
}

function updateCounts() {
  const text = state.view === 'source' ? state.source : state.current;
  const chars = localBillableChars(text);
  const sourceChars = localBillableChars(state.source);
  const currentChars = localBillableChars(state.current);
  const paragraphs = text.split(/\n\s*\n|\n/).filter((part) => part.trim()).length;
  $('#count').textContent = `${chars.toLocaleString('zh-CN')} 计费单位`;
  $('#editorMeta').textContent = `${chars.toLocaleString('zh-CN')} 计费单位 · ${paragraphs} 段`;
  $('#sourceCount').textContent = `${sourceChars.toLocaleString('zh-CN')} 计费单位`;
  $('#currentCount').textContent = `${currentChars.toLocaleString('zh-CN')} 计费单位`;
  const delta = currentChars - sourceChars;
  $('#currentDelta').textContent = delta > 0 ? `+${delta.toLocaleString('zh-CN')}` : delta < 0 ? delta.toLocaleString('zh-CN') : '±0';
  $('#currentDelta').classList.toggle('negative', delta < 0);
  $('#copyBtn').disabled = !text.trim();
  $('#restoreBtn').hidden = state.source === state.current;

  const hasText = Boolean(state.current.trim());
  $('#analyzeBtn').disabled = !hasText || state.analyzeRunning;
  $('#analyzeBtnText').textContent = state.analyzeRunning
    ? '分析中…'
    : hasText
      ? `免费分析 · ${localBillableChars(state.current).toLocaleString('zh-CN')} 计费单位`
      : '请先导入文本';
  updateComposer();
  renderSourcePreview();
  updateWorkflow();
  estimateCost();
}

function setTexts(text, { reset = true } = {}) {
  state.source = String(text || '');
  state.current = String(text || '');
  state.documentRevision += 1;
  state.composerStarted = Boolean(state.current);
  if (reset) invalidateReport({ preserveMessage: true });
  state.view = 'source';
  $$('.view-tabs button').forEach((button) => {
    const selected = button.dataset.view === 'source';
    button.classList.toggle('active', selected);
    button.setAttribute('aria-selected', String(selected));
  });
  editor.style.display = 'block';
  $('#diffView').style.display = 'none';
  editor.value = state.source;
  updateCounts();
}

function switchView(view) {
  if (!['source', 'result', 'diff'].includes(view)) return;
  if (state.view !== 'diff' && editor.style.display !== 'none') {
    if (state.view === 'source') state.source = editor.value;
    else state.current = editor.value;
  }
  state.view = view;
  $$('.view-tabs button').forEach((button) => {
    const selected = button.dataset.view === view;
    button.classList.toggle('active', selected);
    button.setAttribute('aria-selected', String(selected));
  });
  if (view === 'diff') {
    editor.style.display = 'none';
    $('#diffView').style.display = 'block';
    $('#diffView').innerHTML = state.source === state.current
      ? '<div class="empty-diff">还没有产生修改。分析本身不会改动原稿。</div>'
      : diffHtml(state.source, state.current);
  } else {
    editor.style.display = 'block';
    $('#diffView').style.display = 'none';
    editor.value = view === 'source' ? state.source : state.current;
  }
  updateCounts();
}

function diffCore(a, b) {
  const n = a.length;
  const m = b.length;
  if (!a) return b ? [[1, b]] : [];
  if (!b) return [[-1, a]];
  if (n * m > 1800000) return [[-1, a], [1, b]];
  const dp = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  let i = 0;
  let j = 0;
  const output = [];
  const push = (operation, text) => {
    const last = output[output.length - 1];
    if (last && last[0] === operation) last[1] += text;
    else output.push([operation, text]);
  };
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      push(0, a[i]);
      i += 1;
      j += 1;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      push(-1, a[i]);
      i += 1;
    } else {
      push(1, b[j]);
      j += 1;
    }
  }
  while (i < n) push(-1, a[i++]);
  while (j < m) push(1, b[j++]);
  return output;
}

function greedyTokenDiff(a, b) {
  const positions = new Map();
  b.forEach((token, index) => {
    if (!positions.has(token)) positions.set(token, []);
    positions.get(token).push(index);
  });
  let last = -1;
  const anchors = [];
  for (let i = 0; i < a.length; i += 1) {
    const indexes = positions.get(a[i]);
    if (!indexes) continue;
    let low = 0;
    let high = indexes.length;
    while (low < high) {
      const middle = (low + high) >> 1;
      if (indexes[middle] <= last) low = middle + 1;
      else high = middle;
    }
    if (low < indexes.length) {
      last = indexes[low];
      anchors.push([i, last]);
    }
  }
  let ai = 0;
  let bi = 0;
  const output = [];
  const push = (operation, text) => {
    if (!text) return;
    const item = output[output.length - 1];
    if (item && item[0] === operation) item[1] += text;
    else output.push([operation, text]);
  };
  anchors.forEach(([i, j]) => {
    push(-1, a.slice(ai, i).join(''));
    push(1, b.slice(bi, j).join(''));
    push(0, a[i]);
    ai = i + 1;
    bi = j + 1;
  });
  push(-1, a.slice(ai).join(''));
  push(1, b.slice(bi).join(''));
  return output;
}

function diffTokens(a, b) {
  const n = a.length;
  const m = b.length;
  if (n * m > 180000) return greedyTokenDiff(a, b);
  const dp = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  let i = 0;
  let j = 0;
  const output = [];
  const push = (operation, text) => {
    const item = output[output.length - 1];
    if (item && item[0] === operation) item[1] += text;
    else output.push([operation, text]);
  };
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      push(0, a[i]);
      i += 1;
      j += 1;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      push(-1, a[i++]);
    } else {
      push(1, b[j++]);
    }
  }
  while (i < n) push(-1, a[i++]);
  while (j < m) push(1, b[j++]);
  return output;
}

function diff(a, b) {
  let prefixLength = 0;
  while (prefixLength < a.length && prefixLength < b.length && a[prefixLength] === b[prefixLength]) prefixLength += 1;
  let suffixLength = 0;
  while (
    suffixLength < a.length - prefixLength
    && suffixLength < b.length - prefixLength
    && a[a.length - 1 - suffixLength] === b[b.length - 1 - suffixLength]
  ) suffixLength += 1;
  const prefix = a.slice(0, prefixLength);
  const suffix = suffixLength ? a.slice(a.length - suffixLength) : '';
  const aMiddle = a.slice(prefixLength, a.length - suffixLength);
  const bMiddle = b.slice(prefixLength, b.length - suffixLength);
  let middle;
  if (aMiddle.length * bMiddle.length <= 1800000) {
    middle = diffCore(aMiddle, bMiddle);
  } else {
    const split = (text) => text.match(/[^。！？；\n]+[。！？；]?|\n+/g) || [];
    const coarse = diffTokens(split(aMiddle), split(bMiddle));
    middle = [];
    let removed = '';
    let inserted = '';
    const flush = () => {
      if (removed || inserted) middle.push(...diffCore(removed, inserted));
      removed = '';
      inserted = '';
    };
    coarse.forEach(([operation, text]) => {
      if (operation === 0) {
        flush();
        middle.push([0, text]);
      } else if (operation < 0) removed += text;
      else inserted += text;
    });
    flush();
  }
  return (prefix ? [[0, prefix]] : []).concat(middle, suffix ? [[0, suffix]] : []);
}

function diffHtml(a, b) {
  return diff(a, b).map(([operation, text]) => {
    if (operation < 0) return `<del class="del">${esc(text)}</del>`;
    if (operation > 0) return `<ins class="ins">${esc(text)}</ins>`;
    return esc(text);
  }).join('');
}

function mergeNotices(...lists) {
  const seen = new Set();
  return lists.flat().filter((notice) => {
    if (!notice) return false;
    const key = `${notice.level || 'info'}|${notice.text}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function renderNotices(list = []) {
  state.notices = list;
  $('#notices').innerHTML = list.map((notice) => (
    `<div class="notice ${notice.level === 'warn' ? 'warn' : ''}">${esc(notice.text)}</div>`
  )).join('');
}

function statusLetter(status) {
  if (status === 'clear') return '✓';
  if (status === 'review') return '!';
  return '↗';
}

function renderReport(report) {
  state.report = report;
  $('#inspectorEmpty').style.display = 'none';
  $('#results').style.display = 'flex';
  const summary = report.summary || { status: 'review', status_label: '需要复核', checks: 0, findings: 0, safe_fixes: 0, affected_paragraphs: 0 };
  const anchors = report.anchors || {};
  const anchorTotal = ['numbers', 'citations', 'proper_names', 'constraints']
    .reduce((total, key) => total + (Array.isArray(anchors[key]) ? anchors[key].length : 0), 0);
  const findingCount = Number(summary.findings || 0);
  if (findingCount && !Number.isInteger(state.activeIssue)) state.activeIssue = 0;
  $('#summary').innerHTML = `<div class="summary-head"><b>${esc(summary.status_label || '分析完成')}</b><span>结论均可回到原文复核</span></div><div class="metric-grid"><div class="metric"><b>${Number(summary.checks || 0)}</b><span>项检查完成</span></div><div class="metric"><b>${findingCount}</b><span>条可核对问题</span></div><div class="metric"><b>${Number(summary.safe_fixes || 0)}</b><span>处可安全清理</span></div><div class="metric"><b>${anchorTotal} / ${anchorTotal}</b><span>事实锚点未变</span></div></div>`;
  $('#issueCount').textContent = String(Number(summary.findings || 0));
  $('#mobileIssueCount').textContent = String(Number(summary.findings || 0));
  $('#inspectorIssueCount').textContent = String(findingCount);
  renderIssues(report.findings || []);
  renderAnchors(anchors);
  $('#safeBtn').disabled = state.safeFixRunning || !Number(summary.safe_fixes || 0);
  renderNotices(report.notices || state.notices || []);
  updateWorkflow();
  estimateCost();
  syncRewriteButton();
}

function handlingLabel(handling) {
  if (handling === 'safe') return ['可安全清理', 'safe'];
  if (handling === 'rewrite') return ['需要改写', 'rewrite'];
  return ['人工判断', 'review'];
}

function renderIssues(findings = []) {
  const severityOrder = { high: 0, medium: 1, low: 2 };
  const filtered = findings
    .map((finding, index) => ({ finding, index }))
    .filter(({ finding }) => state.issueFilter === 'all' || finding.handling === state.issueFilter)
    .sort((a, b) => (
      (severityOrder[a.finding.severity] ?? 9) - (severityOrder[b.finding.severity] ?? 9)
      || Number(a.finding.start || 0) - Number(b.finding.start || 0)
    ));
  const groups = {};
  filtered.forEach((item) => {
    const category = item.finding.category_name || '其他问题';
    if (!groups[category]) groups[category] = [];
    groups[category].push(item);
  });
  if (filtered.length && !filtered.some(({ index }) => index === state.activeIssue)) {
    state.activeIssue = filtered[0].index;
  } else if (!filtered.length) {
    state.activeIssue = null;
  }

  let html = '';
  Object.entries(groups).forEach(([category, items]) => {
    html += `<div class="category">${esc(category)} · ${items.length}</div>`;
    items.forEach(({ finding, index }) => {
      const mode = handlingLabel(finding.handling);
      const reason = finding.reason || finding.explanation || finding.suggestion || '该表达需要结合上下文核验。';
      const boundary = finding.handling === 'safe'
        ? '仅执行确定性修改，原意与事实锚点保持不变。'
        : finding.handling === 'rewrite'
          ? '仅在候选通过事实守卫后采纳。'
          : '需人工判断，不自动删除或改写。';
      html += `<button type="button" class="issue ${state.activeIssue === index ? 'active' : ''}" aria-expanded="${state.activeIssue === index}" data-index="${index}" data-start="${Number(finding.start || 0)}" data-end="${Number(finding.end || 0)}"><div class="issue-top"><span class="pid ${esc(finding.severity)}">${esc(finding.pattern_id)}</span><span class="issue-name">${esc(finding.name)}</span><span class="mode ${mode[1]}">${mode[0]}</span></div><div class="issue-detail"><div class="evidence-row"><b>命中原文</b><div class="quote">${esc(finding.matched)}</div></div><div class="evidence-row"><b>为什么提示</b><span>${esc(reason)}</span></div><div class="evidence-row"><b>处理边界</b><span>${esc(boundary)}</span></div></div></button>`;
    });
  });
  if (!html) {
    html = state.issueFilter === 'all'
      ? '<div class="anchor-note">没有发现明显的模板化表达。不要为了产生改动而强行重写已经清楚的文字。</div>'
      : '<div class="anchor-note">这个筛选条件下没有问题。</div>';
  }
  $('#issues').innerHTML = html;
  renderSourcePreview();
  $$('.issue').forEach((element) => {
    element.onclick = () => {
      state.activeIssue = Number(element.dataset.index);
      $$('.issue').forEach((item) => {
        const isActive = item === element;
        item.classList.toggle('active', isActive);
        item.setAttribute('aria-expanded', String(isActive));
      });
      renderSourcePreview();
      focusSpan(Number(element.dataset.start), Number(element.dataset.end));
    };
  });
}

function renderAnchors(anchors) {
  const rows = [
    ['数字与范围', anchors.numbers || []],
    ['引用', anchors.citations || []],
    ['专名与术语', anchors.proper_names || []],
    ['否定／条件／状态', anchors.constraints || []],
  ];
  $('#anchors').innerHTML = '<div class="anchor-note">这些内容是改写硬边界。候选若新增、删除或改变关键关系，将被拦截或标记复核。</div>'
    + rows.map(([label, values]) => `<div class="anchor-group"><h4>${label} · ${values.length}</h4><div class="chips">${values.length ? values.slice(0, 30).map((value) => `<span class="chip">${esc(value)}</span>`).join('') : '<span class="chip empty">未提取到</span>'}</div></div>`).join('')
    + (state.guard ? guardHtml(state.guard) : '');
}

function guardHtml(guard) {
  const needsReview = guard.status === 'review' || guard.fabricated;
  return `<div class="guard-box ${needsReview ? 'warn' : ''}"><b>${needsReview ? '需要人工复核' : '机械检查未发现冲突'}</b>${esc(guard.detail || '未发现数字、引用、专名或已知语义边界变化；请仍按修改对照人工确认。')}${(guard.warnings || []).map((warning) => `<br>${esc(warning)}`).join('')}</div>`;
}

function codePointToCodeUnit(text, pointIndex) {
  let points = 0;
  let units = 0;
  for (const char of text) {
    if (points >= pointIndex) break;
    units += char.length;
    points += 1;
  }
  return units;
}

function focusSpan(start, end) {
  switchView('result');
  setMobilePane('editor');
  requestAnimationFrame(() => {
    const text = editor.value;
    const unitStart = codePointToCodeUnit(text, start);
    const unitEnd = codePointToCodeUnit(text, end);
    editor.focus();
    editor.setSelectionRange(unitStart, unitEnd);
    const before = text.slice(0, unitStart);
    editor.scrollTop = Math.max(0, (before.split('\n').length - 3) * 27);
  });
}

async function analyze() {
  if (state.analyzeRunning) return;
  if (state.view !== 'diff') {
    if (state.view === 'source') {
      state.source = editor.value;
      state.current = editor.value;
    } else {
      state.current = editor.value;
    }
  }
  if (!state.current.trim()) {
    state.composerStarted = true;
    updateComposer();
    editor.focus();
    toast('请先粘贴或上传文本', 'error');
    return;
  }

  const snapshot = state.current;
  const revision = state.documentRevision;
  state.guard = null;
  state.analyzeRunning = true;
  clearPersistent();
  showInspectorState('loading');
  updateCounts();

  try {
    const report = await api('/api/v1/analyze', { text: snapshot });
    if (revision !== state.documentRevision || snapshot !== state.current) {
      setPersistent('分析期间文本已发生变化，这份旧结果没有覆盖当前内容。请重新分析。', 'warn');
      showInspectorState('default', '文本已更新', '为了避免把旧结论套到新文本上，请重新分析当前版本。');
      return;
    }
    report.notices = mergeNotices(state.documentNotices, report.notices || []);
    const truncated = report.notices.some((notice) => /只处理了前|超过.*上限/.test(notice.text || ''));
    if (!truncated && typeof report.text === 'string') state.current = report.text;
    renderReport(report);
    switchView('result');
    setMobilePane('results');
    if (truncated) {
      setPersistent('文本超过本地单次分析上限，报告只覆盖前 120,000 字。请按章节处理后再优化。', 'warn');
    } else {
      setPersistent(`分析完成：找到 ${Number(report.summary?.findings || 0)} 个可核对问题，未消耗改写额度。`, 'success');
    }
    if (window.matchMedia('(max-width: 680px)').matches) $('#summary').focus();
  } catch (error) {
    setPersistent(`分析失败：${error.message}`, 'error');
    showInspectorState('error', '分析没有完成', '文本仍安全保留在左侧。检查本地服务后可直接重试。');
    toast(error.message, 'error');
  } finally {
    state.analyzeRunning = false;
    updateCounts();
  }
}

async function safeFix() {
  if (state.safeFixRunning || !state.report) return;
  if (Array.from(state.current).length > 120000) {
    setPersistent('安全清理的单次上限为 120,000 字，请按章节处理，避免只修改前半篇。', 'error');
    return;
  }
  const snapshot = state.current;
  const revision = state.documentRevision;
  state.safeFixRunning = true;
  $('#safeBtn').disabled = true;
  $('#safeBtn').textContent = '清理中…';
  clearPersistent();
  try {
    const result = await api('/api/v1/autofix', { text: snapshot });
    if (revision !== state.documentRevision || snapshot !== state.current) {
      setPersistent('清理期间文本已变化，旧结果没有覆盖当前版本。', 'warn');
      return;
    }
    state.current = result.text;
    state.documentRevision += 1;
    state.guard = {
      status: result.guard.semantic_changed || result.guard.n_removed ? 'review' : 'passed',
      detail: result.guard.fabricated || result.guard.n_removed || result.guard.semantic_changed
        ? '候选触碰事实边界，相关修改已回滚。'
        : '机械检查未发现事实冲突；请在修改对照中人工确认。',
      warnings: [],
    };
    result.after.notices = mergeNotices(state.documentNotices, result.notices || []);
    renderReport(result.after);
    switchView('diff');
    setPersistent(result.changed ? '安全清理完成。请在“修改对照”中复核后再导出。' : '没有发现适合机械清理的内容，原稿未改动。', result.changed ? 'success' : 'info');
    toast(result.changed ? '已完成安全清理' : '没有可安全自动修改的内容');
  } catch (error) {
    setPersistent(`安全清理失败：${error.message}`, 'error');
    toast(error.message, 'error');
  } finally {
    state.safeFixRunning = false;
    $('#safeBtn').textContent = '安全清理';
    $('#safeBtn').disabled = !(state.report && Number(state.report.summary?.safe_fixes || 0));
    updateCounts();
  }
}

function billingSummary(data) {
  return (data && data.summary) || (data && data.billing) || data || {};
}

function setPlans(data) {
  if (state.trialMode) {
    state.plans = [];
    state.paymentInfo = {};
    $('#billingNotice').textContent = '匿名试用不提供自助购买，访客额度由管理员统一设置。';
    renderPlans();
    return;
  }
  const list = Array.isArray(data) ? data : (data.plans || data.products || data.catalog || []);
  state.plans = Array.isArray(list) ? list : [];
  state.paymentInfo = Array.isArray(data) ? {} : (data.payment || data);
  const provider = state.paymentInfo.provider || state.paymentInfo.payment_provider || 'mock';
  const notice = state.paymentInfo.notice || '本地演示使用模拟支付，点击购买不会扣款。Stripe 或易支付待正式上线前配置。';
  $('#billingNotice').innerHTML = `${esc(notice)}<br>英文按单词、中文按汉字计费，每个单词或汉字各计 1 个额度；保守/平衡 1×，深度 1.5×。任务失败或零候选采纳时，预占额度会自动退回。${provider !== 'mock' ? ` 当前支付通道：${esc(provider)}。` : ''}`;
  renderPlans();
}

function allowedStrengths() {
  const allowed = state.billing && state.billing.allowed_strengths;
  return Array.isArray(allowed) && allowed.length ? allowed : ['conservative'];
}

function syncEntitlements() {
  const allowed = allowedStrengths();
  if (!allowed.includes(state.strength)) state.strength = 'conservative';
  $$('.strength').forEach((button) => {
    const isAllowed = allowed.includes(button.dataset.strength);
    const isSelected = button.dataset.strength === state.strength;
    button.disabled = false;
    button.classList.toggle('active', isSelected);
    button.classList.toggle('locked', !isAllowed);
    button.setAttribute('aria-checked', String(isSelected));
    button.removeAttribute('aria-disabled');
    if (isAllowed) button.removeAttribute('aria-label');
    else button.setAttribute('aria-label', state.trialMode
      ? `${button.textContent.trim()}，当前内测权益未开通，点击查看额度说明`
      : `${button.textContent.trim()}，当前套餐未解锁，点击查看升级方案`);
    button.title = isAllowed
      ? '候选会继续经过事实守卫'
      : state.trialMode
        ? `当前内测权益不支持${button.textContent.split('·')[0].trim()}模式`
        : `当前套餐不支持${button.textContent.split('·')[0].trim()}模式，点击查看升级方案`;
  });
  estimateCost();
  syncRewriteButton();
}

function syncRewriteButton() {
  const button = $('#rewriteBtn');
  const hint = $('#actionHint');
  const allowed = allowedStrengths().includes(state.strength);
  if (state.rewriteRunning) {
    button.disabled = true;
    button.textContent = '改写处理中…';
    hint.textContent = '任务正在后台生成候选并执行事实守卫';
  } else if (!state.report) {
    button.disabled = true;
    button.textContent = '请先分析';
    hint.textContent = '免费分析完成后，再选择是否需要改写';
  } else if (!allowed) {
    button.disabled = false;
    button.textContent = state.trialMode ? '联系管理员开通' : '升级后使用此模式';
    hint.textContent = state.trialMode ? '试用额度与可用模式由管理员统一发放' : '点击查看可解锁该强度的套餐';
  } else if (!(state.config && state.config.llm_configured)) {
    button.disabled = false;
    button.textContent = 'AI 服务暂不可用';
    hint.textContent = '规则分析仍可使用；平台改写服务恢复后即可继续';
  } else {
    button.disabled = false;
    button.textContent = '保真改写';
    hint.textContent = '点击后会先显示本次计费单位、模式与预计预占额度';
  }
}

function updateBilling(data) {
  const next = billingSummary(data);
  if (!next || typeof next !== 'object') return;
  state.billing = { ...(state.billing || {}), ...next };
  const balance = Number(state.billing.balance || 0);
  const limit = Number(state.billing.max_chars_per_job || 0);
  $('#billingBtn').textContent = `剩余 ${balance.toLocaleString('zh-CN')} 额度`;
  $('#billingSummary').innerHTML = `<div><strong>${balance.toLocaleString('zh-CN')} 额度</strong><span>可用改写额度</span></div><div class="summary-plan">${esc(state.billing.plan_name || '免费体验')}<br>单次上限 ${limit.toLocaleString('zh-CN')} 计费单位</div>`;
  syncEntitlements();
  renderPlans();
}

function formatPrice(fen) {
  const amount = Number(fen || 0);
  return `¥${(amount / 100).toFixed(amount % 100 ? 2 : 0)}`;
}

function renderPlans() {
  const box = $('#planGrid');
  if (state.trialMode) {
    box.hidden = false;
    box.innerHTML = '<div class="trial-credit-panel"><div><strong>测试额度由管理员发放</strong><span>内测阶段不会发起付款，也无法在此购买套餐。<br>如需要增加额度，请将页面右上角的测试者名称发给管理员。</span></div></div>';
    return;
  }
  box.hidden = false;
  if (!state.plans.length) {
    box.innerHTML = '<div class="anchor-note">暂未读取到套餐，请稍后重试。</div>';
    return;
  }
  const active = state.billing && state.billing.plan_id;
  box.innerHTML = state.plans.map((plan) => {
    const free = plan.id === 'free' || plan.kind === 'free';
    const current = active === plan.id;
    const kind = free ? '体验' : plan.kind === 'subscription' ? '月卡' : '字数包';
    const price = free ? '¥0' : formatPrice(plan.price_fen);
    const suffix = plan.kind === 'subscription' ? '/ 30天' : ' / 份';
    const action = free
      ? `<button class="btn current-plan" disabled>${current ? '当前基础权益' : '已包含'}</button>`
      : `<button class="btn ${current ? '' : 'primary'}" data-buy="${esc(plan.id)}" ${state.billingBusy || (state.paymentInfo?.provider === 'stripe' && !state.paymentInfo?.checkout_enabled) ? 'disabled' : ''}>${state.billingBusy ? '处理中…' : state.paymentInfo?.provider === 'stripe' ? (state.paymentInfo?.live ? '前往 Stripe 支付' : '前往 Stripe 测试支付') : current ? (plan.kind === 'subscription' ? '模拟续一期' : '再购一份') : '模拟购买'}</button>`;
    return `<section class="plan-card ${current ? 'current' : ''}"><h4>${esc(plan.name)}</h4><span class="plan-kind">${kind}</span><div class="plan-price">${price}<small>${free ? '' : suffix}</small></div><div class="plan-credit">${Number(plan.credits || 0).toLocaleString('zh-CN')} 额度 · 单次 ${Number(plan.max_chars_per_job || 0).toLocaleString('zh-CN')} 计费单位</div><div class="plan-desc">${esc(plan.description || '')}</div>${action}</section>`;
  }).join('');
  $$('[data-buy]').forEach((button) => {
    button.onclick = () => buyPlan(button.dataset.buy);
  });
}

function requestId(prefix) {
  if (globalThis.crypto && crypto.randomUUID) return `${prefix}_${crypto.randomUUID().replaceAll('-', '')}`;
  return `${prefix}_${Date.now().toString(36)}${Math.random().toString(36).slice(2)}`;
}

async function refreshBilling(quiet = false) {
  try {
    const summary = await getApi('/api/billing/summary');
    updateBilling(summary);
    return state.billing;
  } catch (error) {
    if (!quiet) toast(error.message, 'error');
    return null;
  }
}

function appBlockingState() {
  const blocked = Boolean(state.openModal || state.progressOpen);
  $('.app').inert = blocked;
  document.body.style.overflow = blocked ? 'hidden' : '';
}

function openModal(id, trigger = document.activeElement) {
  if (state.openModal && state.openModal !== id) closeModal(state.openModal, false);
  const modal = document.getElementById(id);
  if (!modal) return;
  state.openModal = id;
  state.modalReturn = trigger instanceof HTMLElement ? trigger : null;
  modal.style.display = 'grid';
  appBlockingState();
  requestAnimationFrame(() => {
    const focusTarget = modal.querySelector('.close, button:not([disabled]), input, select, textarea');
    (focusTarget || modal).focus();
  });
}

function closeModal(id = state.openModal, restore = true) {
  if (!id) return;
  const modal = document.getElementById(id);
  if (modal) modal.style.display = 'none';
  if (state.openModal === id) state.openModal = null;
  appBlockingState();
  if (restore && state.modalReturn && document.contains(state.modalReturn)) state.modalReturn.focus();
  if (restore) state.modalReturn = null;
}

async function openBilling() {
  openModal('billingModal');
  try {
    if (state.trialMode) {
      const summary = await getApi('/api/billing/summary');
      updateBilling(summary);
      renderPlans();
      return;
    }
    const [plans, summary] = await Promise.all([getApi('/api/billing/plans'), getApi('/api/billing/summary')]);
    setPlans(plans);
    updateBilling(summary);
  } catch (error) {
    setPersistent(`套餐读取失败：${error.message}`, 'error');
    toast(error.message, 'error');
  }
}

async function buyPlan(productId) {
  if (state.trialMode) {
    toast('内测额度由管理员发放，当前不开放购买。', 'error');
    renderPlans();
    return;
  }
  if (state.billingBusy) return;
  state.billingBusy = true;
  renderPlans();
  try {
    const result = await api('/api/billing/checkout', {
      product_id: productId,
      idempotency_key: requestId('checkout'),
    });
    if (result?.provider === 'stripe' && result.checkout_url) {
      const target = new URL(result.checkout_url);
      if (target.protocol !== 'https:' || target.hostname !== 'checkout.stripe.com') throw new Error('Stripe 收银台地址无效');
      window.location.assign(target.href);
      return;
    }
    if (result?.provider !== 'mock' || result.status !== 'paid') throw new Error('支付仍在确认，请在新版订单页查看状态');
    if (result && result.summary) updateBilling(result.summary);
    await refreshBilling(true);
    setPersistent('模拟支付完成，额度已经到账；本地测试没有发生真实扣款。', 'success');
    toast('模拟支付完成，额度已到账');
  } catch (error) {
    setPersistent(`购买流程未完成：${error.message}`, 'error');
    toast(error.message, 'error');
  } finally {
    state.billingBusy = false;
    renderPlans();
  }
}

function needsUpgrade(error) {
  const data = (error && error.data) || {};
  const details = data.details || data;
  return Boolean((error && error.status === 402) || details.upgrade_required === true);
}

function rewrite() {
  if (state.rewriteRunning) {
    toast('已有改写任务正在运行');
    return;
  }
  if (!state.report) return;
  if (!(state.config && state.config.llm_configured)) {
    openConfig();
    return;
  }
  if (!allowedStrengths().includes(state.strength)) {
    openBilling();
    return;
  }
  estimateCost();
  openModal('rewriteConfirmModal');
}

async function startRewrite() {
  if (state.rewriteRunning) return;
  closeModal('rewriteConfirmModal');
  const snapshot = state.current;
  state.rewriteRunning = true;
  state.pendingRequestId = state.pendingRequestId || requestId('rewrite');
  clearPersistent();
  syncRewriteButton();
  try {
    const response = await api('/api/v1/rewrite-jobs', {
      text: snapshot,
      strength: state.strength,
      request_id: state.pendingRequestId,
    });
    const jobId = response.job || response.job_id;
    if (!jobId) throw new Error('服务未返回任务编号');
    if (response.billing && Number.isFinite(Number(response.billing.balance_after))) {
      updateBilling({ ...(state.billing || {}), balance: Number(response.billing.balance_after) });
    }
    sessionStorage.setItem('pendingRewriteJob', JSON.stringify({ jobId, startedAt: Date.now() }));
    showProgress(true);
    await pollJob(jobId);
    state.pendingRequestId = null;
  } catch (error) {
    showProgress(false);
    await refreshBilling(true);
    if (needsUpgrade(error)) await openBilling();
    setPersistent(`改写未完成：${error.message}`, 'error');
    toast(error.message, 'error');
    if (error.status && error.status !== 0) state.pendingRequestId = null;
  } finally {
    state.rewriteRunning = false;
    syncRewriteButton();
  }
}

async function pollJob(id) {
  const startedAt = Date.now();
  state.pollFailures = 0;
  for (;;) {
    await delay(850);
    let job;
    try {
      job = await getApi(`/api/job/${encodeURIComponent(id)}`);
      state.pollFailures = 0;
    } catch (error) {
      state.pollFailures += 1;
      if (state.pollFailures > 6) throw new Error(`任务状态连续读取失败：${error.message}`);
      $('#progressStep').textContent = `连接中断，正在重试 ${state.pollFailures} / 6`;
      setPersistent('改写任务仍在后台运行，状态连接暂时中断，正在自动重试。', 'warn');
      await delay(Math.min(5000, state.pollFailures * 700));
      continue;
    }

    if (!['running', 'done', 'error'].includes(job.state)) throw new Error('任务返回未知状态');
    const elapsed = Math.round((Date.now() - startedAt) / 1000);
    const total = Number(job.total || 0);
    const done = Number(job.done || 0);
    const progress = total ? Math.max(7, (done / total) * 100) : 7;
    $('#progressTime').textContent = `${elapsed}s`;
    $('#progressBar').style.width = `${progress}%`;
    $('#progressStep').textContent = total ? `正在处理 ${done} / ${total} 个文本块` : '正在生成候选…';

    if (job.state === 'error') {
      sessionStorage.removeItem('pendingRewriteJob');
      throw new Error(job.error || '改写失败');
    }
    if (job.state !== 'done') continue;

    sessionStorage.removeItem('pendingRewriteJob');
    showProgress(false);
    const result = job.result;
    state.current = result.text;
    state.documentRevision += 1;
    state.guard = result.guard;
    result.after.notices = mergeNotices(state.documentNotices, result.notices || []);
    renderReport(result.after);
    switchView('diff');
    setMobilePane('editor');
    if (result.billing && Number.isFinite(Number(result.billing.balance))) {
      updateBilling({ ...(state.billing || {}), balance: Number(result.billing.balance) });
    } else {
      await refreshBilling(true);
    }
    const charged = Number(result.billing?.charged || 0);
    const released = Number(result.billing?.released || 0);
    const balance = Number(result.billing?.balance ?? state.billing?.balance ?? 0);
    const success = $('#rewriteSuccess');
    success.hidden = false;
    if (charged) {
      success.textContent = `已采纳 ${result.n_accepted} / ${result.n_chunks} 个候选，扣除 ${charged.toLocaleString('zh-CN')} 额度，余额 ${balance.toLocaleString('zh-CN')} 额度。`;
    } else if (result.changed) {
      success.textContent = `已产生修改并退回 ${released.toLocaleString('zh-CN')} 预占额度。请在修改对照中人工复核。`;
    } else {
      success.textContent = `${result.no_change_reason || '未采纳候选，原稿保持不变。'}${released.toLocaleString('zh-CN')} 预占额度已退回。`;
    }
    setPersistent(result.changed
      ? '修改完成。请逐条查看“修改对照”，人工确认后再复制或导出。'
      : (result.no_change_reason || '未找到通过事实守卫的有效修改，原稿保持不变。'),
    result.changed ? 'success' : 'warn');
    toast(result.changed ? `已采纳 ${result.n_accepted} / ${result.n_chunks} 个候选` : '没有可采纳的修改');
    return;
  }
}

function showProgress(on) {
  state.progressOpen = Boolean(on);
  $('#progress').style.display = on ? 'grid' : 'none';
  if (on) {
    $('#progressBar').style.width = '7%';
    $('#progressStep').textContent = '准备任务…';
    $('#progressTime').textContent = '0s';
  }
  appBlockingState();
}

async function onFile(file) {
  if (!file) return;
  const extension = (file.name.split('.').pop() || '').toLowerCase();
  $('#fileTitle').textContent = file.name;
  $('#fileKind').textContent = extension.toUpperCase();
  setPersistent(`正在读取 ${file.name}…`, 'info');
  try {
    if (extension === 'txt') {
      state.doc = null;
      state.documentNotices = [];
      renderNotices([]);
      $('#exportBtn').hidden = true;
      setTexts(await file.text());
      await analyze();
      return;
    }
    if (!['docx', 'pdf'].includes(extension)) throw new Error('目前支持 DOCX、PDF 和 TXT');
    const data = bytesToB64(await file.arrayBuffer());
    const result = await api(extension === 'pdf' ? '/api/pdf/extract' : '/api/docx/extract', { file: data });
    state.doc = { name: file.name, kind: extension, data, meta: result.meta };
    state.documentNotices = result.notices || [];
    setTexts(result.text);
    renderNotices(state.documentNotices);
    $('#exportBtn').hidden = extension !== 'docx';
    await analyze();
  } catch (error) {
    setPersistent(`文件读取失败：${error.message}`, 'error');
    toast(error.message, 'error');
  } finally {
    $('#fileInput').value = '';
  }
}

async function exportDocx() {
  if (!state.doc || state.doc.kind !== 'docx') return;
  try {
    const result = await api('/api/docx/export', { file: state.doc.data, text: state.current });
    const link = document.createElement('a');
    link.href = `data:application/vnd.openxmlformats-officedocument.wordprocessingml.document;base64,${result.file}`;
    link.download = state.doc.name.replace(/\.docx$/i, '') + '-优化稿.docx';
    link.click();
    toast('DOCX 已导出');
  } catch (error) {
    setPersistent(`导出失败：${error.message}`, 'error');
    toast(error.message, 'error');
  }
}

function openConfig() {
  openModal('configModal');
}

function setMobilePane(pane) {
  const normalized = pane === 'results' ? 'results' : 'editor';
  $('#workspace').classList.toggle('mobile-editor', normalized === 'editor');
  $('#workspace').classList.toggle('mobile-results', normalized === 'results');
  $$('[data-mobile-pane]').forEach((button) => {
    const selected = button.dataset.mobilePane === normalized;
    button.classList.toggle('active', selected);
    button.setAttribute('aria-selected', String(selected));
  });
}

function setResultPanel(panel) {
  state.panel = panel === 'anchors' ? 'anchors' : 'issues';
  $$('.result-tabs button').forEach((button) => {
    const selected = button.dataset.panel === state.panel;
    button.classList.toggle('active', selected);
    button.setAttribute('aria-selected', String(selected));
  });
  $('#issues').style.display = state.panel === 'issues' ? 'block' : 'none';
  $('#anchors').style.display = state.panel === 'anchors' ? 'block' : 'none';
  $('#issueFilters').hidden = state.panel !== 'issues';
}

function loadSample() {
  $('#fileTitle').textContent = '中英双语测试示例';
  $('#fileKind').textContent = 'TEXT';
  state.doc = null;
  state.documentNotices = [];
  $('#exportBtn').hidden = true;
  setTexts(SAMPLE);
  renderNotices([]);
  analyze();
}

let initRetry = null;
async function loadWorkspaceData() {
  const [configResult, plansResult, summaryResult] = await Promise.allSettled([
    getApi('/api/config'),
    state.trialMode ? Promise.resolve({ plans: [] }) : getApi('/api/billing/plans'),
    getApi('/api/billing/summary'),
  ]);

  if (configResult.status === 'fulfilled') {
    const config = configResult.value;
    state.config = config;
    $('#configBtn').textContent = config.llm_configured ? 'AI 服务就绪' : 'AI 服务暂不可用';
    $('#modelDot').className = `dot ${config.llm_configured ? 'ok' : ''}`;
    $('#modelText').innerHTML = config.llm_configured
      ? '<b>平台改写服务已连接</b>'
      : '<b>平台改写服务暂不可用</b>';
    const checks = config.checks || { zh: 31, en: 13 };
    $('#engineVersion').textContent = `${config.policy || 'Humanizer 中英双语'} · ${Number(checks.zh || 0) + Number(checks.en || 0)} 项规则覆盖`;
  } else {
    state.config = { llm_configured: false };
    $('#configBtn').textContent = 'AI 服务状态未知';
  }
  if (plansResult.status === 'fulfilled') setPlans(plansResult.value);
  if (summaryResult.status === 'fulfilled') updateBilling(summaryResult.value);
  if (plansResult.status === 'rejected' || summaryResult.status === 'rejected') {
    setPersistent('本地服务已连接，但套餐信息暂时读取失败；免费分析仍可使用。', 'warn');
  } else if (!$('#persistentMessage').classList.contains('success')) {
    clearPersistent();
  }
  syncRewriteButton();
}

function clearLocalWorkspace() {
  sessionStorage.removeItem('pendingRewriteJob');
  state.doc = null;
  state.notices = [];
  state.documentNotices = [];
  state.guard = null;
  state.billing = null;
  state.plans = [];
  state.pendingRequestId = null;
  state.composerStarted = false;
  $('#fileTitle').textContent = '未命名文本';
  $('#fileKind').textContent = 'TEXT';
  $('#exportBtn').hidden = true;
  $('#billingBtn').textContent = '额度载入中…';
  renderNotices([]);
  setTexts('');
  showInspectorState();
  setMobilePane('editor');
}

async function init() {
  try {
    await getApi('/health');
    clearTimeout(initRetry);
    initRetry = null;
    $('#connDot').className = 'dot ok';
    $('#connText').textContent = '本地服务已连接';
  } catch (_error) {
    $('#connDot').className = 'dot bad';
    $('#connText').textContent = '正在重连本地服务…';
    setPersistent('无法连接本地服务，页面会自动重试。请确认终端中的服务仍在运行。', 'error');
    clearTimeout(initRetry);
    initRetry = setTimeout(init, 2000);
    return;
  }

  try {
    const session = await getApi('/api/session');
    if (!applySession(session)) {
      if (!state.trialMode) throw new Error('服务未返回可用会话');
      await recoverTrialSession();
    }
    if (state.trialMode) {
      $('#connText').textContent = '匿名试用已连接';
    }
  } catch (error) {
    if (error.status === 404) {
      applySession({ trial_mode: false, authenticated: true });
    } else {
      $('#connText').textContent = '访客会话建立失败';
      setPersistent(`无法建立匿名访客会话：${error.message}`, 'error');
      return;
    }
  }

  await loadWorkspaceData();
}

function trapModalFocus(event) {
  if (event.key === 'Escape' && state.openModal) {
    event.preventDefault();
    closeModal();
    return;
  }
  if (event.key !== 'Tab' || !state.openModal) return;
  const modal = document.getElementById(state.openModal);
  const focusable = [...modal.querySelectorAll('button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])')]
    .filter((element) => element.offsetParent !== null);
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

editor.addEventListener('input', () => {
  if (state.view === 'source') {
    state.source = editor.value;
    state.current = editor.value;
  } else {
    state.current = editor.value;
  }
  state.composerStarted = true;
  state.documentRevision += 1;
  invalidateReport();
  updateCounts();
});

editor.addEventListener('keydown', (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
    event.preventDefault();
    analyze();
  }
});

$$('.view-tabs button').forEach((button) => {
  button.onclick = () => switchView(button.dataset.view);
});

$$('.result-tabs button').forEach((button) => {
  button.onclick = () => setResultPanel(button.dataset.panel);
});

$$('.issue-filter').forEach((button) => {
  button.onclick = () => {
    state.issueFilter = button.dataset.filter;
    $$('.issue-filter').forEach((item) => {
      const isActive = item === button;
      item.classList.toggle('active', isActive);
      item.setAttribute('aria-pressed', String(isActive));
    });
    renderIssues(state.report?.findings || []);
  };
});

$$('.strength').forEach((button) => {
  button.onclick = () => {
    if (!allowedStrengths().includes(button.dataset.strength)) {
      openBilling();
      return;
    }
    state.strength = button.dataset.strength;
    syncEntitlements();
  };
});

$$('[data-mobile-pane]').forEach((button) => {
  button.onclick = () => setMobilePane(button.dataset.mobilePane);
});

$('#analyzeBtn').onclick = analyze;
$('#safeBtn').onclick = safeFix;
$('#rewriteBtn').onclick = rewrite;
$('#confirmRewriteBtn').onclick = startRewrite;
$('#cancelRewriteConfirm').onclick = () => closeModal('rewriteConfirmModal');
$('#closeRewriteConfirm').onclick = () => closeModal('rewriteConfirmModal');
$('#fileInput').onchange = (event) => onFile(event.target.files[0]);
$('#uploadBtn').onclick = () => $('#fileInput').click();
$('#emptyUploadBtn').onclick = () => $('#fileInput').click();
$('#navDocs').onclick = () => $('#fileInput').click();
$('#sampleBtn').onclick = loadSample;
$('#emptySampleBtn').onclick = loadSample;
$('#startPasteBtn').onclick = () => {
  state.composerStarted = true;
  updateComposer();
  requestAnimationFrame(() => editor.focus());
};
$('#copyBtn').onclick = async () => {
  try {
    await navigator.clipboard.writeText(state.view === 'source' ? state.source : state.current);
    toast('已复制当前文本');
  } catch (_error) {
    toast('复制失败，请手动选择文本', 'error');
  }
};
$('#restoreBtn').onclick = async () => {
  state.current = state.source;
  state.documentRevision += 1;
  invalidateReport({ preserveMessage: true });
  switchView('source');
  setPersistent('已恢复原稿，正在重新分析当前版本。', 'info');
  await analyze();
};
$('#exportBtn').onclick = exportDocx;
$('#configBtn').onclick = openConfig;
$('#mobileSettingsBtn').onclick = openConfig;
$('#settings').onclick = openConfig;
$('#billingBtn').onclick = () => openBilling();
$('#upgradeBtn').onclick = () => openBilling();
$('#closeModal').onclick = () => closeModal('configModal');
$('#closeBilling').onclick = () => closeModal('billingModal');
$('#dismissStatus').onclick = clearPersistent;

['configModal', 'billingModal', 'rewriteConfirmModal'].forEach((id) => {
  const modal = document.getElementById(id);
  modal.addEventListener('click', (event) => {
    if (event.target === modal) closeModal(id);
  });
});

document.addEventListener('keydown', trapModalFocus);

const editorWrap = $('#editorWrap');
const sourcePreviewWrap = $('#sourcePreviewWrap');
const diffView = $('#diffView');
let syncingDocumentScroll = false;

function syncDocumentScroll(from, to) {
  if (syncingDocumentScroll || !from || !to) return;
  const fromRange = from.scrollHeight - from.clientHeight;
  const toRange = to.scrollHeight - to.clientHeight;
  if (fromRange <= 0 || toRange <= 0) return;
  syncingDocumentScroll = true;
  to.scrollTop = (from.scrollTop / fromRange) * toRange;
  requestAnimationFrame(() => { syncingDocumentScroll = false; });
}

editor.addEventListener('scroll', () => syncDocumentScroll(editor, sourcePreviewWrap));
diffView.addEventListener('scroll', () => syncDocumentScroll(diffView, sourcePreviewWrap));
sourcePreviewWrap.addEventListener('scroll', () => {
  syncDocumentScroll(sourcePreviewWrap, editor.style.display === 'none' ? diffView : editor);
});

editorWrap.addEventListener('dragover', (event) => {
  event.preventDefault();
  editorWrap.classList.add('dragging');
});
editorWrap.addEventListener('dragleave', () => editorWrap.classList.remove('dragging'));
editorWrap.addEventListener('drop', (event) => {
  event.preventDefault();
  editorWrap.classList.remove('dragging');
  const file = event.dataTransfer.files && event.dataTransfer.files[0];
  if (file) onFile(file);
});

syncEntitlements();
showInspectorState();
setResultPanel('issues');
updateCounts();
init();
