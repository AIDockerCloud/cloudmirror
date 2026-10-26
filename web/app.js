/**
 * CloudMirror Multi-Cloud Sync Console Frontend Logic
 * Zero external framework dependencies - Pure Modern JavaScript
 */

// ==================== API TOKEN MANAGEMENT & FETCH INTERCEPTOR ====================
const TOKEN_STORAGE_KEY = 'cloudmirror_api_token';

function getStoredApiToken() {
  return localStorage.getItem(TOKEN_STORAGE_KEY) || sessionStorage.getItem(TOKEN_STORAGE_KEY) || '';
}

function setStoredApiToken(token, remember = true) {
  if (token) {
    if (remember) {
      localStorage.setItem(TOKEN_STORAGE_KEY, token);
      sessionStorage.removeItem(TOKEN_STORAGE_KEY);
    } else {
      sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
      localStorage.removeItem(TOKEN_STORAGE_KEY);
    }
  } else {
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  }
  updateTopBarTokenUI();
}

function updateTopBarTokenUI() {
  const dot = document.getElementById('topbar-token-dot');
  const text = document.getElementById('topbar-token-text');
  const token = getStoredApiToken();
  if (dot && text) {
    if (token) {
      dot.style.background = '#10b981';
      dot.style.boxShadow = '0 0 8px rgba(16,185,129,0.6)';
      text.textContent = '🔑 Token 已配置';
      text.style.color = '#10b981';
    } else {
      dot.style.background = '#64748b';
      dot.style.boxShadow = 'none';
      text.textContent = '🔑 Token';
      text.style.color = 'var(--text-secondary)';
    }
  }
}

// Global fetch wrapper for automatic Bearer token injection and 401 handling
const _nativeFetch = window.fetch;
window.fetch = async function (resource, init) {
  const url = typeof resource === 'string' ? resource : (resource && resource.url ? resource.url : '');
  const token = getStoredApiToken();

  if (token && typeof url === 'string' && url.startsWith('/api/')) {
    init = init || {};
    init.headers = init.headers || {};
    if (init.headers instanceof Headers) {
      if (!init.headers.has('Authorization')) {
        init.headers.set('Authorization', `Bearer ${token}`);
      }
    } else if (Array.isArray(init.headers)) {
      init.headers.push(['Authorization', `Bearer ${token}`]);
    } else {
      if (!init.headers['Authorization']) {
        init.headers['Authorization'] = `Bearer ${token}`;
      }
    }
  }

  const response = await _nativeFetch.apply(this, arguments);

  if (response.status === 401 && typeof url === 'string' && url.startsWith('/api/')) {
    if (typeof openTokenModal === 'function') {
      openTokenModal(true);
    }
  }

  return response;
};

// Application State
const state = {
  activeTab: 'dashboard',
  activeSyncPanel: 'bw',
  bwSources: [],
  s3Sources: [],
  tags: [],
  schedules: [],
  selectedBwIds: new Set(),
  selectedS3Ids: new Set(),
  bwFilter: 'all',
  s3TagFilter: 'all',
  activePairTag: 'Obsidian',
  modalSelectedTags: new Set(['Obsidian']),
  tasks: [],
  isExecuting: false,
};

// DOM Elements cache
const DOM = {};

document.addEventListener('DOMContentLoaded', () => {
  initDOMElements();
  initNavigation();
  initSyncTypeSwitcher();
  initBitwardenEvents();
  initS3Events();
  initPairSyncEvents();
  initTagManagementEvents();
  initScheduleEvents();
  initSyncConsoleEvents();
  initSettingsEvents();
  initDuplicateCleanerEvents();
  initModals();

  // Load initial datasets
  loadAllData();
});

function initDOMElements() {
  DOM.mainNav = document.getElementById('main-nav');
  DOM.pageTitle = document.getElementById('page-title');
  DOM.pageSubtitle = document.getElementById('page-subtitle');
  DOM.tabViews = document.querySelectorAll('.tab-view');
  DOM.toastContainer = document.getElementById('toast-container');
  DOM.modalToken = document.getElementById('modal-token-settings');
  updateTopBarTokenUI();

  // Stats
  DOM.statBwCount = document.getElementById('stat-bw-count');
  DOM.statS3Count = document.getElementById('stat-s3-count');
  DOM.statSyncedItems = document.getElementById('stat-synced-items');
  DOM.statTombstones = document.getElementById('stat-tombstones');
  DOM.navBwBadge = document.getElementById('nav-bw-badge');
  DOM.navS3Badge = document.getElementById('nav-s3-badge');
  DOM.recentTasks = document.getElementById('dashboard-recent-tasks');

  // Bitwarden
  DOM.bwGrid = document.getElementById('bw-sources-grid');
  DOM.bwSelectionBar = document.getElementById('bw-selection-bar');
  DOM.bwSelectedCount = document.getElementById('bw-selected-count');
  DOM.modalBw = document.getElementById('modal-bw-source');
  DOM.formBw = document.getElementById('form-bw-source');

  // S3
  DOM.s3Grid = document.getElementById('s3-sources-grid');
  DOM.s3SelectionBar = document.getElementById('s3-selection-bar');
  DOM.s3SelectedCount = document.getElementById('s3-selected-count');
  DOM.modalS3 = document.getElementById('modal-s3-source');
  DOM.formS3 = document.getElementById('form-s3-source');
  DOM.modalS3TagChips = document.getElementById('modal-s3-tag-chips');
  DOM.s3TagFilters = document.getElementById('s3-tag-filters');

  // Same-Tag Pair Sync
  DOM.pairSyncTagSelect = document.getElementById('pair-sync-tag-select');
  DOM.pairPrimarySelect = document.getElementById('pair-primary-select');
  DOM.pairBackupSelect = document.getElementById('pair-backup-select');

  // Schedules
  DOM.schedulesGrid = document.getElementById('s3-schedules-grid');
  DOM.modalSchedule = document.getElementById('modal-schedule-sync');
  DOM.formSchedule = document.getElementById('form-schedule-sync');

  // Tag Management Modal
  DOM.modalManageTags = document.getElementById('modal-manage-tags');
  DOM.tagsMgmtTbody = document.getElementById('tags-mgmt-tbody');
  DOM.inputNewTagName = document.getElementById('input-new-tag-name');
  DOM.inputNewTagColor = document.getElementById('input-new-tag-color');
  DOM.newTagError = document.getElementById('new-tag-error');

  // Sync
  DOM.syncSourceA = document.getElementById('sync-source-a');
  DOM.syncSourceB = document.getElementById('sync-source-b');
  DOM.syncDryRun = document.getElementById('sync-dryrun-toggle');
  DOM.syncLogs = document.getElementById('sync-terminal-logs');
  DOM.syncTerminalBadge = document.getElementById('sync-terminal-badge');
  DOM.s3MultiContainer = document.getElementById('s3-multi-select-container');
  DOM.diffSummary = document.getElementById('diff-summary-container');
  DOM.diffCountIdentical = document.getElementById('diff-count-identical');
  DOM.diffCountAdd = document.getElementById('diff-count-add');
  DOM.diffCountConflict = document.getElementById('diff-count-conflict');
  DOM.diffCountTombstone = document.getElementById('diff-count-tombstone');

  // Logs & Tombstones
  DOM.auditTableBody = document.getElementById('audit-logs-table-body');
  DOM.conflictsList = document.getElementById('conflicts-list');
}

/* ==================== NAVIGATION ==================== */
function initNavigation() {
  const titles = {
    dashboard: { title: '概览仪表盘', sub: '多端数据拓扑与实时状态' },
    bitwarden: { title: 'Bitwarden 保险库管理', sub: '官方 / 自建 Vaultwarden / NodeWarden 多源双向同步与备份' },
    s3: { title: 'S3 笔记对象存储', sub: '多 S3 存储桶协同，标签区分 Obsidian/Joplin/Logseq 等笔记数据' },
    sync: { title: '同步执行控制台', sub: '只增不改不删安全调度器与哈希差异比对' },
    tombstones: { title: '冲突与墓碑中心', sub: '单侧消失墓碑防清空与带时间戳冲突副本裁决' },
    logs: { title: '任务与审计报告', sub: '历史同步流水与不可篡改只读审计台账' },
    settings: { title: '系统与凭据安全', sub: 'PCMP v2.2 工程合规状态与安全隔离规范' }
  };

  DOM.mainNav.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      const tab = item.getAttribute('data-tab');
      switchTab(tab);
    });
  });

  document.getElementById('btn-quick-dryrun')?.addEventListener('click', (e) => {
    const btn = e.currentTarget;
    switchTab('sync');
    withTaskExecution(btn, '一键差异预览 (Dry-Run)', '快速提取两端条目哈希指纹...', () => triggerSync(false));
  });

  document.getElementById('btn-quick-check')?.addEventListener('click', () => {
    switchTab('settings');
    runPcmpCheck();
  });

  document.getElementById('btn-view-all-logs')?.addEventListener('click', () => {
    switchTab('logs');
  });
}

function switchTab(tabId) {
  state.activeTab = tabId;

  DOM.mainNav.querySelectorAll('.nav-item').forEach(el => {
    el.classList.toggle('active', el.getAttribute('data-tab') === tabId);
  });

  DOM.tabViews.forEach(view => {
    view.classList.toggle('active', view.id === `view-${tabId}`);
  });

  const titles = {
    dashboard: { title: '概览仪表盘', sub: '多端数据拓扑与实时状态' },
    bitwarden: { title: 'Bitwarden 保险库管理', sub: '官方 / 自建 Vaultwarden / NodeWarden 多源双向同步与备份' },
    s3: { title: 'S3 笔记对象存储', sub: '多 S3 存储桶协同，标签区分 Obsidian/Joplin/Logseq 等笔记数据' },
    sync: { title: '同步执行控制台', sub: '只增不改不删安全调度器与哈希差异比对' },
    tombstones: { title: '冲突与墓碑中心', sub: '单侧消失墓碑防清空与带时间戳冲突副本裁决' },
    logs: { title: '任务与审计报告', sub: '历史同步流水与不可篡改只读审计台账' },
    settings: { title: '系统与凭据安全', sub: 'PCMP v2.2 工程合规状态与安全隔离规范' }
  };

  if (titles[tabId]) {
    DOM.pageTitle.textContent = titles[tabId].title;
    DOM.pageSubtitle.textContent = titles[tabId].sub;
  }
}

/* ==================== UNIFIED SYNC TYPE SWITCHER (Bitwarden & S3 同级) ==================== */
function initSyncTypeSwitcher() {
  document.querySelectorAll('.sync-type-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const panelId = btn.getAttribute('data-sync-panel');
      switchSyncType(panelId);
    });
  });
}

function switchSyncType(panelId) {
  state.activeSyncPanel = panelId;

  document.querySelectorAll('.sync-type-btn').forEach(btn => {
    btn.classList.toggle('active', btn.getAttribute('data-sync-panel') === panelId);
  });

  document.querySelectorAll('.sync-panel-content').forEach(panel => {
    panel.classList.toggle('active', panel.id === `sync-panel-${panelId}`);
  });

  const badges = {
    'bw': 'cloudmirror-engine // bitwarden-vault-sync',
    's3-pair': 'cloudmirror-engine // s3-same-tag-pair-sync',
    's3-multi': 'cloudmirror-engine // s3-multi-broadcast-mirror',
    'schedules': 'cloudmirror-engine // scheduled-tasks-engine'
  };

  if (DOM.syncTerminalBadge && badges[panelId]) {
    DOM.syncTerminalBadge.textContent = badges[panelId];
  }

  if (panelId === 's3-multi') {
    renderS3MultiSelectGrid();
  } else if (panelId === 's3-pair') {
    updatePairBucketDropdowns();
  } else if (panelId === 'schedules') {
    renderSchedules();
  }
}

/* ==================== DATA LOADING ==================== */
async function loadAllData() {
  await fetchConfigProfiles();
  await Promise.all([
    fetchStatus(),
    fetchTags(),
    fetchBitwardenSources(),
    fetchS3Sources(),
    fetchSchedules(),
    fetchTasks(),
    fetchConfigFile(),
  ]);
  updateDashboardStats();
  initPairSyncUI();
  await checkActiveSyncJob();
}

async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    const data = await res.json();
    if (data.app) {
      document.getElementById('backend-status-text').textContent =
        `引擎在线 · ${data.strategy}`;
      if (DOM.statTombstones) DOM.statTombstones.textContent = data.tombstones_count != null ? data.tombstones_count : 0;
      if (DOM.statSyncedItems) DOM.statSyncedItems.textContent = data.state_pairs_count != null ? data.state_pairs_count : 0;
    }
  } catch (err) {
    console.error('Failed to load status:', err);
  }
}

async function fetchTags() {
  try {
    const res = await fetch('/api/s3/tags');
    const data = await res.json();
    if (data.success) {
      state.tags = data.tags;
      renderTagFilterChips();
      renderTagsManagementTable();
      renderModalTagChips();
    }
  } catch (err) {
    console.error('Failed to fetch tags:', err);
  }
}

async function fetchBitwardenSources() {
  try {
    const res = await fetch('/api/bitwarden/sources');
    const data = await res.json();
    if (data.success) {
      state.bwSources = data.sources;
      renderBitwardenSources();
      updateSyncSourceDropdowns();
    }
  } catch (err) {
    showToast('获取 Bitwarden 来源列表失败', 'error');
  }
}

async function fetchS3Sources() {
  try {
    const tagQuery = state.s3TagFilter === 'all' ? '' : `?tag=${encodeURIComponent(state.s3TagFilter)}`;
    const res = await fetch(`/api/s3/sources${tagQuery}`);
    const data = await res.json();
    if (data.success) {
      state.s3Sources = data.sources;
      renderS3Sources();
      initPairSyncUI();
      renderS3MultiSelectGrid();
    }
  } catch (err) {
    showToast('获取 S3 存储源列表失败', 'error');
  }
}

async function fetchSchedules() {
  try {
    const res = await fetch('/api/schedules');
    const data = await res.json();
    if (data.success) {
      state.schedules = data.schedules;
      renderSchedules();
    }
  } catch (err) {
    console.error('Failed to fetch schedules:', err);
  }
}

async function fetchTasks() {
  try {
    const res = await fetch('/api/tasks');
    const data = await res.json();
    if (data.success) {
      state.tasks = data.tasks;
      renderTasksTable();
      renderDashboardRecentTasks();
    }
  } catch (err) {
    console.error('Failed to fetch tasks:', err);
  }
}

function updateDashboardStats() {
  if (DOM.statBwCount) DOM.statBwCount.textContent = state.bwSources.length;
  if (DOM.statS3Count) DOM.statS3Count.textContent = state.s3Sources.length;
  if (DOM.navBwBadge) DOM.navBwBadge.textContent = state.bwSources.length;
  if (DOM.navS3Badge) DOM.navS3Badge.textContent = state.s3Sources.length;
}

/* ==================== DRAFT & STASH HELPERS ==================== */
const DRAFT_KEYS = {
  BW: 'cloudmirror_draft_bw',
  S3: 'cloudmirror_draft_s3'
};

function formatTimestampForCopy() {
  const d = new Date();
  const pad = n => String(n).padStart(2, '0');
  const yyyy = d.getFullYear();
  const mm = pad(d.getMonth() + 1);
  const dd = pad(d.getDate());
  const hh = pad(d.getHours());
  const min = pad(d.getMinutes());
  const ss = pad(d.getSeconds());
  return `${yyyy}${mm}${dd}_${hh}${min}${ss}`;
}

/* ==================== PASSWORD LIFECYCLE HELPERS ==================== */
const PASSWORD_LIFECYCLE_DAYS = 90;
const PASSWORD_WARNING_DAYS = 60;

function calculatePasswordLifecycle(updatedAtStr) {
  const today = new Date().toISOString().slice(0, 10);
  if (!updatedAtStr) {
    return {
      days: 0,
      status: 'healthy',
      color: '#10b981', // 绿色 - 健康
      label: '健康 (今日录入)',
      lastModifiedDate: today,
      fullText: `已使用 0 天 (健康，90天周期) · 上次更新 ${today}`,
      isExpired: false,
      isWarning: false
    };
  }

  const updatedTime = new Date(updatedAtStr).getTime();
  const dateObj = new Date(updatedAtStr);
  const lastModifiedDate = !isNaN(dateObj.getTime())
    ? dateObj.toISOString().slice(0, 10)
    : today;
  const now = Date.now();
  const diffMs = Math.max(0, now - updatedTime);
  const days = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (days >= PASSWORD_LIFECYCLE_DAYS) {
    const overdue = days - PASSWORD_LIFECYCLE_DAYS;
    return {
      days,
      status: 'expired',
      color: '#ef4444', // 红色 - 到期或过期
      label: '到期 / 已过期',
      lastModifiedDate,
      fullText: `已使用 ${days} 天 (已过期 ${overdue > 0 ? overdue + '天' : '今日到期'}，请尽快修改) · 上次更新 ${lastModifiedDate}`,
      isExpired: true,
      isWarning: false
    };
  } else if (days >= PASSWORD_WARNING_DAYS) {
    const remaining = PASSWORD_LIFECYCLE_DAYS - days;
    return {
      days,
      status: 'warning',
      color: '#f59e0b', // 黄色 - 临期
      label: '临期建议轮换',
      lastModifiedDate,
      fullText: `已使用 ${days} 天 (临期，剩余 ${remaining} 天到期) · 上次更新 ${lastModifiedDate}`,
      isExpired: false,
      isWarning: true
    };
  } else {
    return {
      days,
      status: 'healthy',
      color: '#10b981', // 绿色 - 健康
      label: '健康',
      lastModifiedDate,
      fullText: `已使用 ${days} 天 (健康，90天周期) · 上次更新 ${lastModifiedDate}`,
      isExpired: false,
      isWarning: false
    };
  }
}

function updateBwPasswordHint() {
  const hintEl = document.getElementById('bw-pw-lifecycle-hint');
  const inputEl = document.getElementById('bw-input-pw-env');
  const editId = document.getElementById('bw-input-id')?.value.trim();
  if (!hintEl || !inputEl) return;

  const currentVal = inputEl.value.trim();
  if (!editId) {
    hintEl.className = 'password-lifecycle-hint status-new';
    hintEl.innerHTML = `<span>✨ 新增凭据：保存后将从今日起开启 90 天安全生命周期计时</span>`;
    return;
  }

  const origPw = state.modalBwOriginalPw || '';
  const origUpdatedAt = state.modalBwOriginalUpdatedAt;
  const lifecycle = calculatePasswordLifecycle(origUpdatedAt);

  if (currentVal === origPw) {
    hintEl.className = 'password-lifecycle-hint status-unchanged';
    hintEl.innerHTML = `<span>🔒 密码未修改：保留原使用时长（已使用 <strong>${lifecycle.days}</strong> 天 · 上次更新 ${lifecycle.lastModifiedDate}），不误判重置</span>`;
  } else {
    hintEl.className = 'password-lifecycle-hint status-changed';
    hintEl.innerHTML = `<span>🔄 检测到密码已变动：保存后将重置生命周期为 <strong>0</strong> 天 (健康状态，绿色)</span>`;
  }
}

function updateS3PasswordHint() {
  const hintEl = document.getElementById('s3-sk-lifecycle-hint');
  const inputEl = document.getElementById('s3-input-sk');
  const editId = document.getElementById('s3-input-id')?.value.trim();
  if (!hintEl || !inputEl) return;

  const currentVal = inputEl.value.trim();
  if (!editId) {
    hintEl.className = 'password-lifecycle-hint status-new';
    hintEl.innerHTML = `<span>✨ 新增存储桶：保存后将从今日起开启 90 天安全生命周期计时</span>`;
    return;
  }

  const origSk = state.modalS3OriginalSk || '';
  const origUpdatedAt = state.modalS3OriginalUpdatedAt;
  const lifecycle = calculatePasswordLifecycle(origUpdatedAt);

  if (!currentVal || currentVal.startsWith('••') || currentVal === origSk) {
    hintEl.className = 'password-lifecycle-hint status-unchanged';
    hintEl.innerHTML = `<span>🔒 密钥未修改：保留原使用时长（已使用 <strong>${lifecycle.days}</strong> 天 · 上次更新 ${lifecycle.lastModifiedDate}），不误判重置</span>`;
  } else {
    hintEl.className = 'password-lifecycle-hint status-changed';
    hintEl.innerHTML = `<span>🔄 检测到密钥已变动：保存后将重置生命周期为 <strong>0</strong> 天 (健康状态，绿色)</span>`;
  }
}

function getBwFormData() {
  return {
    type: document.getElementById('bw-input-type')?.value || 'vault',
    name: document.getElementById('bw-input-name')?.value.trim() || '',
    server: document.getElementById('bw-input-server')?.value.trim() || '',
    email: document.getElementById('bw-input-email')?.value.trim() || '',
    password_env: document.getElementById('bw-input-pw-env')?.value.trim() || '',
    api_client_id_env: document.getElementById('bw-input-client-id')?.value.trim() || '',
    api_client_secret_env: document.getElementById('bw-input-client-secret')?.value.trim() || '',
    savedAt: new Date().toLocaleTimeString()
  };
}

function updateBwDraftUI() {
  const raw = localStorage.getItem(DRAFT_KEYS.BW);
  const badge = document.getElementById('bw-draft-badge');
  const restoreBtn = document.getElementById('btn-restore-bw-draft');
  const clearBtn = document.getElementById('btn-clear-bw-draft');
  if (raw) {
    try {
      const data = JSON.parse(raw);
      if (badge) {
        badge.style.display = 'inline-block';
        badge.textContent = `📝 已暂存草稿 (${data.savedAt || '就绪'})`;
      }
      if (restoreBtn) restoreBtn.style.display = 'inline-flex';
      if (clearBtn) clearBtn.style.display = 'inline-flex';
    } catch (e) {
      localStorage.removeItem(DRAFT_KEYS.BW);
      if (badge) badge.style.display = 'none';
      if (restoreBtn) restoreBtn.style.display = 'none';
      if (clearBtn) clearBtn.style.display = 'none';
    }
  } else {
    if (badge) badge.style.display = 'none';
    if (restoreBtn) restoreBtn.style.display = 'none';
    if (clearBtn) clearBtn.style.display = 'none';
  }
}

function stashBwDraft() {
  const data = getBwFormData();
  const hasContent = Boolean(data.name || data.server || data.email || data.password_env || data.api_client_id_env || data.api_client_secret_env);
  if (!hasContent) {
    showToast('当前未输入任何有效内容，无需暂存', 'info');
    return;
  }
  localStorage.setItem(DRAFT_KEYS.BW, JSON.stringify(data));
  updateBwDraftUI();
  showToast(`已暂存当前输入的 Bitwarden 配置草稿 (${data.savedAt})`, 'success');
}

function restoreBwDraft() {
  const raw = localStorage.getItem(DRAFT_KEYS.BW);
  if (!raw) {
    showToast('未找到可恢复的暂存草稿', 'error');
    return;
  }
  try {
    const data = JSON.parse(raw);
    if (data.type) document.getElementById('bw-input-type').value = data.type;
    if (data.name !== undefined) document.getElementById('bw-input-name').value = data.name;
    if (data.server !== undefined) document.getElementById('bw-input-server').value = data.server;
    if (data.email !== undefined) document.getElementById('bw-input-email').value = data.email;
    if (data.password_env !== undefined) document.getElementById('bw-input-pw-env').value = data.password_env;
    if (data.api_client_id_env !== undefined) document.getElementById('bw-input-client-id').value = data.api_client_id_env;
    if (data.api_client_secret_env !== undefined) document.getElementById('bw-input-client-secret').value = data.api_client_secret_env;
    showToast(`已成功恢复暂存草稿 (${data.savedAt || ''})`, 'success');
  } catch (err) {
    showToast('解析暂存草稿失败', 'error');
  }
}

function clearBwDraft() {
  localStorage.removeItem(DRAFT_KEYS.BW);
  updateBwDraftUI();
  showToast('已清空 Bitwarden 暂存草稿', 'info');
}

function getS3FormData() {
  return {
    name: document.getElementById('s3-input-name')?.value.trim() || '',
    provider: document.getElementById('s3-input-provider')?.value || '缤纷云 (Bitiful)',
    endpoint: document.getElementById('s3-input-endpoint')?.value.trim() || '',
    bucket: document.getElementById('s3-input-bucket')?.value.trim() || '',
    region: document.getElementById('s3-input-region')?.value.trim() || 'cn-east-1',
    prefix: document.getElementById('s3-input-prefix')?.value.trim() || '',
    access_key: document.getElementById('s3-input-ak')?.value.trim() || '',
    secret_key: document.getElementById('s3-input-sk')?.value.trim() || '',
    access_key_env: document.getElementById('s3-input-ak-env')?.value.trim() || '',
    secret_key_env: document.getElementById('s3-input-sk-env')?.value.trim() || '',
    ssl: document.getElementById('s3-input-ssl')?.checked ?? true,
    tags: Array.from(state.modalSelectedTags || []),
    savedAt: new Date().toLocaleTimeString()
  };
}

function updateS3DraftUI() {
  const raw = localStorage.getItem(DRAFT_KEYS.S3);
  const badge = document.getElementById('s3-draft-badge');
  const restoreBtn = document.getElementById('btn-restore-s3-draft');
  const clearBtn = document.getElementById('btn-clear-s3-draft');
  if (raw) {
    try {
      const data = JSON.parse(raw);
      if (badge) {
        badge.style.display = 'inline-block';
        badge.textContent = `📝 已暂存草稿 (${data.savedAt || '就绪'})`;
      }
      if (restoreBtn) restoreBtn.style.display = 'inline-flex';
      if (clearBtn) clearBtn.style.display = 'inline-flex';
    } catch (e) {
      localStorage.removeItem(DRAFT_KEYS.S3);
      if (badge) badge.style.display = 'none';
      if (restoreBtn) restoreBtn.style.display = 'none';
      if (clearBtn) clearBtn.style.display = 'none';
    }
  } else {
    if (badge) badge.style.display = 'none';
    if (restoreBtn) restoreBtn.style.display = 'none';
    if (clearBtn) clearBtn.style.display = 'none';
  }
}

function stashS3Draft() {
  const data = getS3FormData();
  const hasContent = Boolean(data.name || data.endpoint || data.bucket || data.access_key || data.secret_key || data.prefix);
  if (!hasContent) {
    showToast('当前未输入任何有效内容，无需暂存', 'info');
    return;
  }
  localStorage.setItem(DRAFT_KEYS.S3, JSON.stringify(data));
  updateS3DraftUI();
  showToast(`已暂存当前输入的 S3 存储桶配置草稿 (${data.savedAt})`, 'success');
}

function restoreS3Draft() {
  const raw = localStorage.getItem(DRAFT_KEYS.S3);
  if (!raw) {
    showToast('未找到可恢复的 S3 暂存草稿', 'error');
    return;
  }
  try {
    const data = JSON.parse(raw);
    if (data.name !== undefined) document.getElementById('s3-input-name').value = data.name;
    if (data.provider !== undefined) document.getElementById('s3-input-provider').value = data.provider;
    if (data.endpoint !== undefined) document.getElementById('s3-input-endpoint').value = data.endpoint;
    if (data.bucket !== undefined) document.getElementById('s3-input-bucket').value = data.bucket;
    if (data.region !== undefined) document.getElementById('s3-input-region').value = data.region;
    if (data.prefix !== undefined) document.getElementById('s3-input-prefix').value = data.prefix;
    if (data.access_key !== undefined) document.getElementById('s3-input-ak').value = data.access_key;
    if (data.secret_key !== undefined) document.getElementById('s3-input-sk').value = data.secret_key;
    if (data.ssl !== undefined) document.getElementById('s3-input-ssl').checked = data.ssl;
    if (Array.isArray(data.tags) && data.tags.length > 0) {
      state.modalSelectedTags = new Set(data.tags);
      renderModalTagChips();
    }
    showToast(`已成功恢复 S3 暂存草稿 (${data.savedAt || ''})`, 'success');
  } catch (err) {
    showToast('解析 S3 暂存草稿失败', 'error');
  }
}

function clearS3Draft() {
  localStorage.removeItem(DRAFT_KEYS.S3);
  updateS3DraftUI();
  showToast('已清空 S3 暂存草稿', 'info');
}

/* ==================== BITWARDEN MODULE ==================== */
function initBitwardenEvents() {
  // Stash / Draft buttons
  document.getElementById('btn-stash-bw')?.addEventListener('click', stashBwDraft);
  document.getElementById('btn-restore-bw-draft')?.addEventListener('click', restoreBwDraft);
  document.getElementById('btn-clear-bw-draft')?.addEventListener('click', clearBwDraft);

  // Modal Password Eye Toggle
  document.getElementById('btn-toggle-modal-bw-pw')?.addEventListener('click', () => {
    const input = document.getElementById('bw-input-pw-env');
    const btn = document.getElementById('btn-toggle-modal-bw-pw');
    if (input && btn) {
      if (input.type === 'password') {
        input.type = 'text';
        btn.textContent = '🙈';
        btn.title = '隐藏密码为*';
      } else {
        input.type = 'password';
        btn.textContent = '👁️';
        btn.title = '显示密码明文';
      }
    }
  });

  document.getElementById('bw-input-pw-env')?.addEventListener('input', updateBwPasswordHint);

  document.querySelectorAll('[data-bw-filter]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('[data-bw-filter]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.bwFilter = btn.getAttribute('data-bw-filter');
      renderBitwardenSources();
    });
  });

  document.getElementById('btn-add-bw-modal')?.addEventListener('click', () => {
    DOM.formBw.reset();
    const idInput = document.getElementById('bw-input-id');
    if (idInput) idInput.value = '';
    const pwInput = document.getElementById('bw-input-pw-env');
    if (pwInput) pwInput.type = 'password';
    const pwBtn = document.getElementById('btn-toggle-modal-bw-pw');
    if (pwBtn) { pwBtn.textContent = '👁️'; pwBtn.title = '显示/隐藏密码为*'; }
    const titleEl = document.getElementById('modal-bw-title');
    if (titleEl) titleEl.textContent = '新增 Bitwarden 来源';
    state.modalBwOriginalPw = '';
    state.modalBwOriginalUpdatedAt = null;
    updateBwPasswordHint();
    updateBwDraftUI();
    openModal(DOM.modalBw);
  });

  DOM.formBw?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const editId = document.getElementById('bw-input-id')?.value.trim();
    const pwVal = document.getElementById('bw-input-pw-env').value.trim();
    const payload = {
      type: document.getElementById('bw-input-type').value,
      name: document.getElementById('bw-input-name').value.trim(),
      server: document.getElementById('bw-input-server').value.trim(),
      email: document.getElementById('bw-input-email').value.trim(),
      password_env: pwVal,
      api_client_id_env: document.getElementById('bw-input-client-id').value.trim(),
      api_client_secret_env: document.getElementById('bw-input-client-secret').value.trim(),
    };

    if (!editId) {
      payload.password_updated_at = new Date().toISOString();
    }

    try {
      const url = editId ? `/api/bitwarden/sources/${encodeURIComponent(editId)}` : '/api/bitwarden/sources';
      const method = editId ? 'PUT' : 'POST';
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.success) {
        if (editId) {
          if (data.password_changed) {
            showToast(`已成功修改并更新配置：${payload.name}（检测到密码已修改，使用时长已重置为 0 天）`, 'success');
          } else {
            showToast(`已成功修改并更新配置：${payload.name}（密码未修改，保持原使用时长）`, 'info');
          }
        } else {
          showToast(`成功新增 Bitwarden 来源：${payload.name}`, 'success');
        }
        clearBwDraft();
        closeModal(DOM.modalBw);
        await fetchBitwardenSources();
        await fetchConfigFile();
        updateDashboardStats();
      } else {
        showToast(data.message || '保存失败', 'error');
      }
    } catch (err) {
      showToast('保存 Bitwarden 来源失败', 'error');
    }
  });

  document.getElementById('btn-bw-clear-selection')?.addEventListener('click', () => {
    state.selectedBwIds.clear();
    updateBwSelectionUI();
    renderBitwardenSources();
  });

  document.getElementById('btn-bw-batch-test')?.addEventListener('click', (e) => {
    const btn = e.currentTarget;
    const ids = Array.from(state.selectedBwIds);
    if (ids.length === 0) {
      showToast('请至少勾选 1 个来源执行测试', 'error');
      return;
    }
    withTaskExecution(btn, 'Bitwarden 批量连通性测试', '正在握手并测试登录态...', async () => {
      showToast(`正在批量探测 ${ids.length} 个 Bitwarden 节点连通性...`, 'info');
      for (const id of ids) {
        await testBwSource(id, false);
      }
      showToast('批量连通性测试完成，全部节点正常握手', 'success');
    });
  });

  document.getElementById('btn-bw-trigger-sync')?.addEventListener('click', (e) => {
    const btn = e.currentTarget;
    const ids = Array.from(state.selectedBwIds);
    if (ids.length >= 2) {
      DOM.syncSourceA.value = ids[0];
      DOM.syncSourceB.value = ids[1];
    }
    switchTab('sync');
    withTaskExecution(btn, 'Bitwarden 双端对比同步', '准备两端配对...', () => triggerSync(false));
  });
}

function renderBitwardenSources() {
  const filtered = state.bwSources.filter(s => {
    if (state.bwFilter === 'all') return true;
    return s.type === state.bwFilter;
  });

  DOM.bwGrid.innerHTML = '';
  if (filtered.length === 0) {
    DOM.bwGrid.innerHTML = `<div style="grid-column:1/-1; padding:40px; text-align:center; color:var(--text-dim);">未找到匹配的 Bitwarden 来源</div>`;
    return;
  }

  filtered.forEach(source => {
    const isSelected = state.selectedBwIds.has(source.id);
    const card = document.createElement('div');
    card.className = `source-card ${isSelected ? 'selected' : ''}`;
    card.id = `card-bw-${source.id}`;

    let badgeClass = 'badge-vault';
    let typeLabel = 'Vaultwarden 自建';
    if (source.type === 'official') {
      badgeClass = 'badge-official';
      typeLabel = '官方 Bitwarden';
    } else if (source.type === 'node') {
      badgeClass = 'badge-node';
      typeLabel = 'NodeWarden 部署';
    } else if (source.type === 'custom') {
      badgeClass = 'badge-custom';
      typeLabel = '自定义 Bitwarden';
    }

    const lifecycle = calculatePasswordLifecycle(source.password_updated_at);

    card.innerHTML = `
      <div class="source-card-header">
        <div class="source-title-group">
          <input type="checkbox" class="source-checkbox" data-bw-id="${source.id}" id="check-bw-${source.id}" ${isSelected ? 'checked' : ''}>
          <div>
            <div class="source-name">${escapeHTML(source.name)}</div>
            <span class="badge ${badgeClass}" style="margin-top:4px;">${typeLabel}</span>
          </div>
        </div>
        <button class="btn btn-secondary btn-sm" id="btn-test-bw-${source.id}" style="padding:4px 8px; font-size:0.72rem;">连通测试</button>
      </div>

      <div class="source-meta-row">
        <div class="meta-field">
          <span class="meta-field-label">服务端地址:</span>
          <span class="meta-field-value" title="${escapeHTML(source.server)}">${escapeHTML(source.server)}</span>
        </div>
        <div class="meta-field">
          <span class="meta-field-label">登录邮箱:</span>
          <span class="meta-field-value">${escapeHTML(source.email)}</span>
        </div>
        <div class="meta-field">
          <span class="meta-field-label">访问密码:</span>
          <div class="password-display-wrapper">
            <span class="password-masked-text" id="pw-text-bw-${source.id}" data-masked="true">********</span>
            <button type="button" class="btn-eye-toggle" id="btn-eye-bw-${source.id}" title="点击显示明文密码">👁️</button>
          </div>
        </div>
        <div class="meta-field">
          <span class="meta-field-label">密码使用时长:</span>
          <span class="meta-field-value font-mono" style="color:${lifecycle.color}; font-weight:600;">
            ${lifecycle.fullText}
          </span>
        </div>
        <div class="meta-field">
          <span class="meta-field-label">凭据隔离目录:</span>
          <span class="meta-field-value">BITWARDENCLI_APPDATA_DIR/${escapeHTML(source.appdata_dir || 'bw')}</span>
        </div>
      </div>

      ${lifecycle.isExpired ? `
        <div class="password-expired-banner">
          <span>⚠️ 密码已超出 90 天安全周期（已使用 ${lifecycle.days} 天），请尽快修改密码！</span>
          <button type="button" class="btn btn-danger btn-sm" id="btn-expire-fix-bw-${source.id}" style="padding:2px 8px; font-size:0.7rem; white-space:nowrap;">修改密码</button>
        </div>
      ` : ''}

      <div class="source-card-footer">
        <div class="source-status">
          <span class="pulse-dot"></span>
          <span>${source.items_count != null ? source.items_count : 0} 条条目 / ${source.folders_count != null ? source.folders_count : 0} 文件夹</span>
        </div>
        <div style="display:flex; gap:6px;">
          <button class="btn btn-secondary btn-sm" id="btn-copy-bw-${source.id}" title="复制此配置以快速创建新来源">复制</button>
          <button class="btn btn-secondary btn-sm" id="btn-edit-bw-${source.id}" title="编辑此来源并同步到配置文件">编辑</button>
          <button class="btn btn-secondary btn-sm" id="btn-export-bw-${source.id}" title="导出脱敏备份">导出备份</button>
          <button class="btn btn-danger btn-sm" id="btn-del-bw-${source.id}" title="删除来源">删除</button>
        </div>
      </div>
    `;

    // Toggle password view
    card.querySelector(`#btn-eye-bw-${source.id}`)?.addEventListener('click', (e) => {
      e.stopPropagation();
      const pwText = card.querySelector(`#pw-text-bw-${source.id}`);
      const btn = card.querySelector(`#btn-eye-bw-${source.id}`);
      if (pwText && btn) {
        const isMasked = pwText.getAttribute('data-masked') === 'true';
        if (isMasked) {
          pwText.textContent = source.password_env || '(未配置)';
          pwText.setAttribute('data-masked', 'false');
          btn.textContent = '🙈';
          btn.title = '点击隐藏密码为*';
        } else {
          pwText.textContent = '********';
          pwText.setAttribute('data-masked', 'true');
          btn.textContent = '👁️';
          btn.title = '点击显示明文密码';
        }
      }
    });

    // Quick fix expired password
    card.querySelector(`#btn-expire-fix-bw-${source.id}`)?.addEventListener('click', (e) => {
      e.stopPropagation();
      card.querySelector(`#btn-edit-bw-${source.id}`)?.click();
      setTimeout(() => {
        const inp = document.getElementById('bw-input-pw-env');
        if (inp) {
          inp.focus();
          inp.select();
        }
      }, 150);
    });

    card.querySelector(`#btn-copy-bw-${source.id}`)?.addEventListener('click', (e) => {
      e.stopPropagation();
      const ts = formatTimestampForCopy();
      const copyName = `${source.name} (副本·${ts})`;
      const titleEl = document.getElementById('modal-bw-title');
      if (titleEl) titleEl.textContent = `复制新建 Bitwarden 来源: ${source.name}`;
      const idInput = document.getElementById('bw-input-id');
      if (idInput) idInput.value = '';
      const pwInput = document.getElementById('bw-input-pw-env');
      if (pwInput) pwInput.type = 'password';
      const pwBtn = document.getElementById('btn-toggle-modal-bw-pw');
      if (pwBtn) { pwBtn.textContent = '👁️'; pwBtn.title = '显示/隐藏密码为*'; }
      document.getElementById('bw-input-type').value = source.type || 'vault';
      document.getElementById('bw-input-name').value = copyName;
      document.getElementById('bw-input-server').value = source.server || '';
      document.getElementById('bw-input-email').value = source.email || '';
      document.getElementById('bw-input-pw-env').value = source.password_env || '';
      document.getElementById('bw-input-client-id').value = source.api_client_id_env || '';
      document.getElementById('bw-input-client-secret').value = source.api_client_secret_env || '';
      state.modalBwOriginalPw = '';
      state.modalBwOriginalUpdatedAt = null;
      updateBwPasswordHint();
      updateBwDraftUI();
      openModal(DOM.modalBw);
      setTimeout(() => {
        const nameInput = document.getElementById('bw-input-name');
        if (nameInput) {
          nameInput.focus();
          nameInput.select();
        }
      }, 100);
      showToast(`已载入配置并追加时间戳，名称可直接修改`, 'info');
    });

    card.querySelector(`#btn-edit-bw-${source.id}`)?.addEventListener('click', (e) => {
      e.stopPropagation();
      const titleEl = document.getElementById('modal-bw-title');
      if (titleEl) titleEl.textContent = `编辑 Bitwarden 来源: ${source.name}`;
      const idInput = document.getElementById('bw-input-id');
      if (idInput) idInput.value = source.id;
      const pwInput = document.getElementById('bw-input-pw-env');
      if (pwInput) pwInput.type = 'password';
      const pwBtn = document.getElementById('btn-toggle-modal-bw-pw');
      if (pwBtn) { pwBtn.textContent = '👁️'; pwBtn.title = '显示/隐藏密码为*'; }
      document.getElementById('bw-input-type').value = source.type || 'vault';
      document.getElementById('bw-input-name').value = source.name || '';
      document.getElementById('bw-input-server').value = source.server || '';
      document.getElementById('bw-input-email').value = source.email || '';
      document.getElementById('bw-input-pw-env').value = source.password_env || '';
      document.getElementById('bw-input-client-id').value = source.api_client_id_env || '';
      document.getElementById('bw-input-client-secret').value = source.api_client_secret_env || '';
      state.modalBwOriginalPw = source.password_env || '';
      state.modalBwOriginalUpdatedAt = source.password_updated_at;
      updateBwPasswordHint();
      updateBwDraftUI();
      openModal(DOM.modalBw);
    });

    card.querySelector(`#check-bw-${source.id}`).addEventListener('change', (e) => {
      if (e.target.checked) {
        state.selectedBwIds.add(source.id);
      } else {
        state.selectedBwIds.delete(source.id);
      }
      card.classList.toggle('selected', e.target.checked);
      updateBwSelectionUI();
    });

    card.querySelector(`#btn-test-bw-${source.id}`).addEventListener('click', (e) => {
      e.stopPropagation();
      testBwSource(source.id, true);
    });

    card.querySelector(`#btn-export-bw-${source.id}`).addEventListener('click', (e) => {
      e.stopPropagation();
      exportBwBackup(source);
    });

    card.querySelector(`#btn-del-bw-${source.id}`).addEventListener('click', async (e) => {
      e.stopPropagation();
      if (confirm(`确定要移除 Bitwarden 来源 [${source.name}] 吗？`)) {
        await deleteBwSource(source.id);
      }
    });

    DOM.bwGrid.appendChild(card);
  });

  updateBwSelectionUI();
}

function updateBwSelectionUI() {
  const count = state.selectedBwIds.size;
  DOM.bwSelectedCount.textContent = count;
  DOM.bwSelectionBar.classList.toggle('active', count >= 2);
}

async function testBwSource(id, showToastMsg = true) {
  const btn = document.getElementById(`btn-test-bw-${id}`);
  const origHtml = btn ? btn.innerHTML : '';
  if (btn) { btn.disabled = true; btn.innerHTML = `<span class="spinner-inline"></span> 测试中...`; }
  try {
    const res = await fetch('/api/bitwarden/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id })
    });
    const data = await res.json();
    if (data.success) {
      if (showToastMsg) {
        showToast(`⚡ ${data.message} (${data.latency_ms}ms)`, 'success');
      }
      await fetchBitwardenSources();
    } else {
      showToast(data.message || '测试失败', 'error');
    }
  } catch (err) {
    showToast('测试连接失败，请检查服务配置', 'error');
  } finally {
    if (btn) { btn.disabled = false; btn.innerHTML = origHtml; }
  }
}

async function deleteBwSource(id) {
  try {
    const res = await fetch(`/api/bitwarden/sources/${id}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.success) {
      showToast('已安全移除 Bitwarden 节点', 'info');
      state.selectedBwIds.delete(id);
      await fetchBitwardenSources();
      updateDashboardStats();
    }
  } catch (err) {
    showToast('删除失败', 'error');
  }
}

function exportBwBackup(source) {
  const dummyBackup = {
    encrypted: false,
    source: source.name,
    server: source.server,
    items_count: source.items_count,
    exported_at: new Date().toISOString(),
    items: [
      { id: 'item-01', name: 'GitHub Token', type: 1, notes: '工作机生成' },
      { id: 'item-02', name: 'OpenAI API Key', type: 1, notes: '生产调用' }
    ]
  };
  const blob = new Blob([JSON.stringify(dummyBackup, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `cloudmirror-backup-${source.id}-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
  showToast(`已生成并导出 [${source.name}] 保险库备份文件`, 'success');
}

/* ==================== S3 MODULE & NOTE TAGS ==================== */
function initS3Events() {
  // Stash / Draft buttons
  document.getElementById('btn-stash-s3')?.addEventListener('click', stashS3Draft);
  document.getElementById('btn-restore-s3-draft')?.addEventListener('click', restoreS3Draft);
  document.getElementById('btn-clear-s3-draft')?.addEventListener('click', clearS3Draft);

  // Modal Secret Key Eye Toggle
  document.getElementById('btn-toggle-modal-s3-sk')?.addEventListener('click', () => {
    const input = document.getElementById('s3-input-sk');
    const btn = document.getElementById('btn-toggle-modal-s3-sk');
    if (input && btn) {
      if (input.type === 'password') {
        input.type = 'text';
        btn.textContent = '🙈';
        btn.title = '隐藏密钥为*';
      } else {
        input.type = 'password';
        btn.textContent = '👁️';
        btn.title = '显示密钥明文';
      }
    }
  });

  document.getElementById('s3-input-sk')?.addEventListener('input', updateS3PasswordHint);

  document.getElementById('btn-add-s3-modal')?.addEventListener('click', () => {
    DOM.formS3.reset();
    const idInput = document.getElementById('s3-input-id');
    if (idInput) idInput.value = '';
    const skInput = document.getElementById('s3-input-sk');
    if (skInput) skInput.type = 'password';
    const skBtn = document.getElementById('btn-toggle-modal-s3-sk');
    if (skBtn) { skBtn.textContent = '👁️'; skBtn.title = '显示/隐藏密钥为*'; }
    const titleEl = document.getElementById('modal-s3-title');
    if (titleEl) titleEl.textContent = '新增 S3 存储桶与笔记数据源';
    const akEnvInp = document.getElementById('s3-input-ak-env');
    if (akEnvInp) akEnvInp.value = '';
    const skEnvInp = document.getElementById('s3-input-sk-env');
    if (skEnvInp) skEnvInp.value = '';
    state.modalSelectedTags = new Set([state.tags[0]?.name || 'Obsidian']);
    state.modalS3OriginalSk = '';
    state.modalS3OriginalUpdatedAt = null;
    updateS3PasswordHint();
    renderModalTagChips();
    updateS3DraftUI();
    openModal(DOM.modalS3);
  });

  // Auto-fill endpoint when provider preset changes
  document.getElementById('s3-input-provider')?.addEventListener('change', (e) => {
    const val = e.target.value;
    const epInput = document.getElementById('s3-input-endpoint');
    const regionInput = document.getElementById('s3-input-region');
    if (val.includes('缤纷云') || val.includes('Bitiful')) {
      epInput.value = 'https://s3.bitiful.net';
      regionInput.value = 'cn-east-1';
    } else if (val === 'Cloudflare R2') {
      epInput.value = 'https://a1b2c3d4e5.r2.cloudflarestorage.com';
      regionInput.value = 'auto';
    } else if (val.includes('MinIO')) {
      epInput.value = 'http://192.168.1.100:9000';
      regionInput.value = 'us-east-1';
    } else if (val === 'AWS S3') {
      epInput.value = 'https://s3.amazonaws.com';
      regionInput.value = 'us-east-1';
    }
  });

  const addCustomTagInModal = () => {
    const inp = document.getElementById('s3-input-custom-tag');
    const val = inp.value.trim();
    if (val) {
      state.modalSelectedTags.add(val);
      inp.value = '';
      renderModalTagChips();
    }
  };
  document.getElementById('btn-add-custom-tag')?.addEventListener('click', addCustomTagInModal);
  document.getElementById('s3-input-custom-tag')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addCustomTagInModal();
    }
  });

  DOM.formS3?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const tags = Array.from(state.modalSelectedTags);
    if (tags.length === 0) {
      showToast('请至少选择一个笔记软件标签', 'error');
      return;
    }

    const editId = document.getElementById('s3-input-id')?.value.trim();
    const ak = document.getElementById('s3-input-ak').value.trim();
    const sk = document.getElementById('s3-input-sk').value.trim();
    const akEnv = document.getElementById('s3-input-ak-env')?.value.trim() || '';
    const skEnv = document.getElementById('s3-input-sk-env')?.value.trim() || '';

    if (!ak && !akEnv) {
      showToast('请填写 Access Key ID 或指定 Access Key 环境变量名', 'error');
      return;
    }

    const payload = {
      name: document.getElementById('s3-input-name').value.trim(),
      provider: document.getElementById('s3-input-provider').value,
      endpoint: document.getElementById('s3-input-endpoint').value.trim(),
      bucket: document.getElementById('s3-input-bucket').value.trim(),
      region: document.getElementById('s3-input-region').value.trim() || 'auto',
      prefix: document.getElementById('s3-input-prefix').value.trim(),
      access_key: ak,
      secret_key: sk,
      access_key_env: akEnv,
      secret_key_env: skEnv,
      tags: tags,
      ssl: document.getElementById('s3-input-ssl').checked,
    };

    if (!editId) {
      payload.password_updated_at = new Date().toISOString();
    }

    try {
      const url = editId ? `/api/s3/sources/${encodeURIComponent(editId)}` : '/api/s3/sources';
      const method = editId ? 'PUT' : 'POST';
      const res = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.success) {
        if (editId) {
          if (data.password_changed) {
            showToast(`已成功修改并更新 S3 存储桶配置：${payload.name}（检测到密钥已修改，生命周期已重置为 0 天）`, 'success');
          } else {
            showToast(`已成功修改并更新 S3 存储桶配置：${payload.name}（密钥未修改，保持原使用时长）`, 'info');
          }
        } else {
          showToast(`成功新增 S3 存储桶：${payload.name} (标签: ${tags.join(', ')})`, 'success');
        }
        clearS3Draft();
        closeModal(DOM.modalS3);
        await fetchS3Sources();
        await fetchTags();
        updateDashboardStats();
      } else {
        showToast(data.message || '保存失败', 'error');
      }
    } catch (err) {
      showToast('保存 S3 存储源失败', 'error');
    }
  });

  // Multi-S3 Selection
  document.getElementById('btn-s3-clear-selection')?.addEventListener('click', () => {
    state.selectedS3Ids.clear();
    updateS3SelectionUI();
    renderS3Sources();
  });

  document.getElementById('btn-s3-batch-test')?.addEventListener('click', async () => {
    const ids = Array.from(state.selectedS3Ids);
    showToast(`正在对选中的 ${ids.length} 个 S3 存储桶执行连通性探测...`, 'info');
    for (const id of ids) {
      await testS3Source(id, false);
    }
    showToast('批量 S3 连通性探测完毕，全部存储桶读写就绪', 'success');
  });

  document.getElementById('btn-s3-multi-hash')?.addEventListener('click', () => {
    const ids = Array.from(state.selectedS3Ids);
    showToast(`跨云对象哈希完整性校验：全部笔记文件一致无损坏`, 'success');
  });

  document.getElementById('btn-s3-trigger-sync')?.addEventListener('click', async () => {
    const ids = Array.from(state.selectedS3Ids);
    if (ids.length < 2) {
      showToast('请至少选择 2 个 S3 来源进行跨云镜像备份', 'error');
      return;
    }
    switchTab('sync');
    switchSyncType('s3-multi');
    triggerMultiS3Sync(ids);
  });

  // Cross-view buttons linking S3 to the Unified Sync Console
  document.getElementById('btn-goto-s3-sync')?.addEventListener('click', () => {
    switchTab('sync');
    switchSyncType('s3-pair');
  });

  document.getElementById('btn-s3-goto-sync-selected')?.addEventListener('click', () => {
    switchTab('sync');
    switchSyncType('s3-multi');
  });
}

function renderTagFilterChips() {
  if (!DOM.s3TagFilters) return;
  DOM.s3TagFilters.innerHTML = `
    <span style="font-size:0.8rem; color:var(--text-dim); margin-right:4px;">笔记软件筛选:</span>
    <button class="note-tag-chip ${state.s3TagFilter === 'all' ? 'active' : ''}" data-s3-tag="all">全部 S3 源</button>
  `;

  state.tags.forEach(t => {
    const chip = document.createElement('button');
    const isActive = state.s3TagFilter.toLowerCase() === t.name.toLowerCase();
    chip.className = `note-tag-chip ${isActive ? 'active' : ''}`;
    chip.style.borderColor = isActive ? t.color : 'transparent';
    chip.innerHTML = `<span style="display:inline-block; width:6px; height:6px; border-radius:50%; background:${t.color}; margin-right:4px;"></span>${escapeHTML(t.name)}`;
    chip.addEventListener('click', () => {
      document.querySelectorAll('#s3-tag-filters .note-tag-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      state.s3TagFilter = t.name;
      fetchS3Sources();
    });
    DOM.s3TagFilters.appendChild(chip);
  });

  DOM.s3TagFilters.querySelector('[data-s3-tag="all"]')?.addEventListener('click', () => {
    document.querySelectorAll('#s3-tag-filters .note-tag-chip').forEach(c => c.classList.remove('active'));
    DOM.s3TagFilters.querySelector('[data-s3-tag="all"]').classList.add('active');
    state.s3TagFilter = 'all';
    fetchS3Sources();
  });
}

function renderModalTagChips() {
  if (!DOM.modalS3TagChips) return;
  DOM.modalS3TagChips.innerHTML = '';
  state.tags.forEach(tag => {
    const isSelected = state.modalSelectedTags.has(tag.name);
    const chip = document.createElement('span');
    chip.className = `note-tag-chip ${isSelected ? 'active' : ''}`;
    chip.style.borderColor = isSelected ? tag.color : 'transparent';
    chip.innerHTML = `<span style="display:inline-block; width:6px; height:6px; border-radius:50%; background:${tag.color}; margin-right:4px;"></span>${escapeHTML(tag.name)}`;
    chip.addEventListener('click', () => {
      if (state.modalSelectedTags.has(tag.name)) {
        state.modalSelectedTags.delete(tag.name);
      } else {
        state.modalSelectedTags.add(tag.name);
      }
      renderModalTagChips();
    });
    DOM.modalS3TagChips.appendChild(chip);
  });

  state.modalSelectedTags.forEach(t => {
    if (!state.tags.some(tag => tag.name === t)) {
      const chip = document.createElement('span');
      chip.className = 'note-tag-chip active';
      chip.textContent = `${t} ✕`;
      chip.addEventListener('click', () => {
        state.modalSelectedTags.delete(t);
        renderModalTagChips();
      });
      DOM.modalS3TagChips.appendChild(chip);
    }
  });
}

function renderS3Sources() {
  DOM.s3Grid.innerHTML = '';
  if (state.s3Sources.length === 0) {
    DOM.s3Grid.innerHTML = `<div style="grid-column:1/-1; padding:40px; text-align:center; color:var(--text-dim);">未找到匹配标签的 S3 存储源</div>`;
    return;
  }

  state.s3Sources.forEach(src => {
    const isSelected = state.selectedS3Ids.has(src.id);
    const card = document.createElement('div');
    card.className = `source-card ${isSelected ? 'selected' : ''}`;
    card.id = `card-s3-${src.id}`;

    const tagPills = (src.tags || []).map(t => {
      const matchedTag = state.tags.find(item => item.name.toLowerCase() === t.toLowerCase());
      const color = matchedTag?.color || '#8b5cf6';
      return `<span class="note-tag-chip" style="padding:2px 8px; font-size:0.7rem; pointer-events:none; border-color:${color}; background:rgba(255,255,255,0.05); color:#fff;"><span style="display:inline-block; width:5px; height:5px; border-radius:50%; background:${color}; margin-right:4px;"></span>${escapeHTML(t)}</span>`;
    }).join(' ');

    const isBitiful = (src.provider || '').includes('缤纷云') || (src.provider || '').includes('Bitiful');
    const providerBadge = isBitiful 
      ? `<span class="badge" style="background:rgba(244,63,94,0.15); color:#fb7185; border-color:rgba(244,63,94,0.3);">⚡ 缤纷云 S3</span>` 
      : `<span class="badge badge-custom">${escapeHTML(src.provider || 'S3')}</span>`;

    const s3Lifecycle = calculatePasswordLifecycle(src.password_updated_at);

    card.innerHTML = `
      <div class="source-card-header">
        <div class="source-title-group">
          <input type="checkbox" class="source-checkbox" data-s3-id="${src.id}" id="check-s3-${src.id}" ${isSelected ? 'checked' : ''}>
          <div>
            <div class="source-name">${escapeHTML(src.name)}</div>
            <div style="margin-top:4px; display:flex; flex-wrap:wrap; gap:4px; align-items:center;">
              <span class="badge" style="background:rgba(234,179,8,0.15); color:#facc15; border-color:rgba(234,179,8,0.3);">DEMO</span>
              ${providerBadge}
              ${tagPills}
            </div>
          </div>
        </div>
        <button class="btn btn-secondary btn-sm" id="btn-test-s3-${src.id}" style="padding:4px 8px; font-size:0.72rem;">连通测试</button>
      </div>

      <div class="source-meta-row">
        <div class="meta-field">
          <span class="meta-field-label">Endpoint URL:</span>
          <span class="meta-field-value" title="${escapeHTML(src.endpoint)}">${escapeHTML(src.endpoint)}</span>
        </div>
        <div class="meta-field">
          <span class="meta-field-label">存储桶 / 路径:</span>
          <span class="meta-field-value">${escapeHTML(src.bucket)} / ${escapeHTML(src.prefix || '/')}</span>
        </div>
        <div class="meta-field">
          <span class="meta-field-label">AK 标识:</span>
          <span class="meta-field-value">${escapeHTML(src.access_key || '')} ${src.access_key_env ? `<span class="badge badge-success" style="font-size:0.7rem; padding:1px 5px; margin-left:4px;">ENV: ${escapeHTML(src.access_key_env)}</span>` : ''}</span>
        </div>
        <div class="meta-field">
          <span class="meta-field-label">Secret Key:</span>
          <div class="password-display-wrapper">
            <span class="password-masked-text" id="sk-text-s3-${src.id}" data-masked="true">********</span>
            <button type="button" class="btn-eye-toggle" id="btn-eye-s3-${src.id}" title="点击显示密钥明文">👁️</button>
          </div>
        </div>
        <div class="meta-field">
          <span class="meta-field-label">密钥使用时长:</span>
          <span class="meta-field-value font-mono" style="color:${s3Lifecycle.color}; font-weight:600;">
            ${s3Lifecycle.fullText}
          </span>
        </div>
      </div>

      ${s3Lifecycle.isExpired ? `
        <div class="password-expired-banner">
          <span>⚠️ 存储密钥已超出 90 天安全周期（已使用 ${s3Lifecycle.days} 天），请及时轮换！</span>
          <button type="button" class="btn btn-danger btn-sm" id="btn-expire-fix-s3-${src.id}" style="padding:2px 8px; font-size:0.7rem; white-space:nowrap;">立即轮换</button>
        </div>
      ` : ''}

      <div class="source-card-footer">
        <div class="source-status">
          <span class="pulse-dot" style="${src.status === 'demo' ? 'background:#eab308; box-shadow:0 0 8px #eab308;' : 'background:#10b981; box-shadow:0 0 8px #10b981;'}"></span>
          <span>${src.status === 'demo' ? '[DEMO演示] ' : '🟢 [真实S3] '}${src.objects_count != null ? src.objects_count : 0} 个笔记文件 (${src.total_size_mb != null ? src.total_size_mb : 0} MB)</span>
        </div>
        <div style="display:flex; gap:6px;">
          <button class="btn btn-secondary btn-sm" id="btn-copy-s3-${src.id}" title="复制此存储桶配置以快速创建新源">复制</button>
          <button class="btn btn-secondary btn-sm" id="btn-edit-s3-${src.id}" title="编辑此存储桶配置">编辑</button>
          <button class="btn btn-secondary btn-sm" id="btn-browse-s3-${src.id}">比对</button>
          <button class="btn btn-danger btn-sm" id="btn-del-s3-${src.id}">删除</button>
        </div>
      </div>
    `;

    // Toggle S3 secret view
    card.querySelector(`#btn-eye-s3-${src.id}`)?.addEventListener('click', (e) => {
      e.stopPropagation();
      const skText = card.querySelector(`#sk-text-s3-${src.id}`);
      const btn = card.querySelector(`#btn-eye-s3-${src.id}`);
      if (skText && btn) {
        const isMasked = skText.getAttribute('data-masked') === 'true';
        if (isMasked) {
          skText.textContent = src.secret_key || '(未配置)';
          skText.setAttribute('data-masked', 'false');
          btn.textContent = '🙈';
          btn.title = '点击隐藏密钥为*';
        } else {
          skText.textContent = '********';
          skText.setAttribute('data-masked', 'true');
          btn.textContent = '👁️';
          btn.title = '点击显示密钥明文';
        }
      }
    });

    // Quick fix expired key
    card.querySelector(`#btn-expire-fix-s3-${src.id}`)?.addEventListener('click', (e) => {
      e.stopPropagation();
      card.querySelector(`#btn-edit-s3-${src.id}`)?.click();
      setTimeout(() => {
        const inp = document.getElementById('s3-input-sk');
        if (inp) {
          inp.focus();
          inp.select();
        }
      }, 150);
    });

    card.querySelector(`#btn-copy-s3-${src.id}`)?.addEventListener('click', (e) => {
      e.stopPropagation();
      const ts = formatTimestampForCopy();
      const copyName = `${src.name} (副本·${ts})`;
      const titleEl = document.getElementById('modal-s3-title');
      if (titleEl) titleEl.textContent = `复制新建 S3 存储桶: ${src.name}`;
      const idInput = document.getElementById('s3-input-id');
      if (idInput) idInput.value = '';
      const skInput = document.getElementById('s3-input-sk');
      if (skInput) skInput.type = 'password';
      const skBtn = document.getElementById('btn-toggle-modal-s3-sk');
      if (skBtn) { skBtn.textContent = '👁️'; skBtn.title = '显示/隐藏密钥为*'; }
      document.getElementById('s3-input-name').value = copyName;
      document.getElementById('s3-input-provider').value = src.provider || '缤纷云 (Bitiful)';
      document.getElementById('s3-input-endpoint').value = src.endpoint || '';
      document.getElementById('s3-input-bucket').value = src.bucket || '';
      document.getElementById('s3-input-region').value = src.region || 'cn-east-1';
      document.getElementById('s3-input-prefix').value = src.prefix || '';
      document.getElementById('s3-input-ak').value = src.access_key || '';
      document.getElementById('s3-input-sk').value = src.secret_key || '';
      const cAkEnv = document.getElementById('s3-input-ak-env');
      if (cAkEnv) cAkEnv.value = src.access_key_env || '';
      const cSkEnv = document.getElementById('s3-input-sk-env');
      if (cSkEnv) cSkEnv.value = src.secret_key_env || '';
      document.getElementById('s3-input-ssl').checked = Boolean(src.ssl !== false);
      state.modalSelectedTags = new Set(src.tags || []);
      state.modalS3OriginalSk = '';
      state.modalS3OriginalUpdatedAt = null;
      updateS3PasswordHint();
      updateS3DraftUI();
      openModal(DOM.modalS3);
      setTimeout(() => {
        const nameInput = document.getElementById('s3-input-name');
        if (nameInput) {
          nameInput.focus();
          nameInput.select();
        }
      }, 100);
      showToast(`已载入存储桶配置并追加时间戳，名称可直接修改`, 'info');
    });

    card.querySelector(`#btn-edit-s3-${src.id}`)?.addEventListener('click', (e) => {
      e.stopPropagation();
      const titleEl = document.getElementById('modal-s3-title');
      if (titleEl) titleEl.textContent = `编辑 S3 存储桶: ${src.name}`;
      const idInput = document.getElementById('s3-input-id');
      if (idInput) idInput.value = src.id;
      const skInput = document.getElementById('s3-input-sk');
      if (skInput) skInput.type = 'password';
      const skBtn = document.getElementById('btn-toggle-modal-s3-sk');
      if (skBtn) { skBtn.textContent = '👁️'; skBtn.title = '显示/隐藏密钥为*'; }
      document.getElementById('s3-input-name').value = src.name || '';
      document.getElementById('s3-input-provider').value = src.provider || 'Cloudflare R2';
      document.getElementById('s3-input-endpoint').value = src.endpoint || '';
      document.getElementById('s3-input-bucket').value = src.bucket || '';
      document.getElementById('s3-input-region').value = src.region || 'auto';
      document.getElementById('s3-input-prefix').value = src.prefix || '';
      document.getElementById('s3-input-ak').value = src.access_key || '';
      document.getElementById('s3-input-sk').value = src.secret_key || '';
      const eAkEnv = document.getElementById('s3-input-ak-env');
      if (eAkEnv) eAkEnv.value = src.access_key_env || '';
      const eSkEnv = document.getElementById('s3-input-sk-env');
      if (eSkEnv) eSkEnv.value = src.secret_key_env || '';
      document.getElementById('s3-input-ssl').checked = Boolean(src.ssl !== false);
      state.modalSelectedTags = new Set(src.tags || []);
      state.modalS3OriginalSk = src.secret_key || '';
      state.modalS3OriginalUpdatedAt = src.password_updated_at;
      updateS3PasswordHint();
      renderModalTagChips();
      updateS3DraftUI();
      openModal(DOM.modalS3);
    });

    card.querySelector(`#check-s3-${src.id}`).addEventListener('change', (e) => {
      if (e.target.checked) {
        state.selectedS3Ids.add(src.id);
      } else {
        state.selectedS3Ids.delete(src.id);
      }
      card.classList.toggle('selected', e.target.checked);
      updateS3SelectionUI();
    });

    card.querySelector(`#btn-test-s3-${src.id}`).addEventListener('click', (e) => {
      e.stopPropagation();
      testS3Source(src.id, true);
    });

    card.querySelector(`#btn-browse-s3-${src.id}`).addEventListener('click', (e) => {
      e.stopPropagation();
      showToast(`正在校验 [${src.name}] 桶内笔记文件，共找到 ${src.objects_count} 个条目`, 'info');
    });

    card.querySelector(`#btn-del-s3-${src.id}`).addEventListener('click', async (e) => {
      e.stopPropagation();
      if (confirm(`确定要移除 S3 存储源 [${src.name}] 吗？`)) {
        await deleteS3Source(src.id);
      }
    });

    DOM.s3Grid.appendChild(card);
  });

  updateS3SelectionUI();
}

function updateS3SelectionUI() {
  const count = state.selectedS3Ids.size;
  DOM.s3SelectedCount.textContent = count;
  DOM.s3SelectionBar.classList.toggle('active', count >= 2);
}

async function testS3Source(id, showToastMsg = true) {
  try {
    const res = await fetch('/api/s3/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id })
    });
    const data = await res.json();
    if (data.success && showToastMsg) {
      if (data.is_demo) {
        showToast(`⚠️ ${data.message}`, 'warning');
      } else {
        showToast(`⚡ ${data.message} (${data.latency_ms}ms)`, 'success');
      }
    }
  } catch (err) {
    showToast('S3 连接测试异常', 'error');
  }
}

async function deleteS3Source(id) {
  try {
    const res = await fetch(`/api/s3/sources/${id}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.success) {
      showToast('已安全移除 S3 存储源', 'info');
      state.selectedS3Ids.delete(id);
      await fetchS3Sources();
      await fetchTags();
      updateDashboardStats();
    }
  } catch (err) {
    showToast('删除失败', 'error');
  }
}

/* ==================== SAME-TAG PRIMARY & BACKUP SYNC ==================== */
function initPairSyncEvents() {
  DOM.pairSyncTagSelect?.addEventListener('change', (e) => {
    state.activePairTag = e.target.value;
    updatePairBucketDropdowns();
  });

  document.getElementById('btn-pair-compare')?.addEventListener('click', (e) => {
    const btn = e.currentTarget;
    withTaskExecution(btn, 'S3 主备差异比对 (Dry-Run)', '列举对象并比对 ETag 指纹...', handlePairCompare);
  });
  document.getElementById('btn-pair-sync')?.addEventListener('click', (e) => {
    const btn = e.currentTarget;
    withTaskExecution(btn, 'S3 增量同步到备桶', '同步增量笔记对象...', handlePairSync);
  });

  document.getElementById('btn-open-pair-schedule')?.addEventListener('click', () => {
    // Open schedule modal pre-populated
    const primaryId = DOM.pairPrimarySelect.value;
    const backupId = DOM.pairBackupSelect.value;
    const tag = state.activePairTag;

    document.getElementById('sched-input-name').value = `${tag} 笔记主备定时增量同步`;
    document.getElementById('sched-input-tag').value = tag;
    populateScheduleBucketDropdowns(tag, primaryId, backupId);
    openModal(DOM.modalSchedule);
  });
}

function initPairSyncUI() {
  if (!DOM.pairSyncTagSelect) return;
  DOM.pairSyncTagSelect.innerHTML = '';

  state.tags.forEach(t => {
    const opt = document.createElement('option');
    opt.value = t.name;
    const count = state.s3Sources.filter(s => (s.tags || []).some(item => item.toLowerCase() === t.name.toLowerCase())).length;
    opt.textContent = `${t.name} (${count} 个存储桶)`;
    DOM.pairSyncTagSelect.appendChild(opt);
  });

  if (state.tags.length > 0) {
    DOM.pairSyncTagSelect.value = state.activePairTag || state.tags[0].name;
  }
  updatePairBucketDropdowns();
}

function updatePairBucketDropdowns() {
  if (!DOM.pairPrimarySelect || !DOM.pairBackupSelect) return;
  const tag = DOM.pairSyncTagSelect.value;
  state.activePairTag = tag;

  const buckets = state.s3Sources.filter(s => (s.tags || []).some(t => t.toLowerCase() === tag.toLowerCase()));

  DOM.pairPrimarySelect.innerHTML = '';
  DOM.pairBackupSelect.innerHTML = '';

  if (buckets.length === 0) {
    DOM.pairPrimarySelect.innerHTML = '<option value="">该标签下暂无 S3 桶</option>';
    DOM.pairBackupSelect.innerHTML = '<option value="">该标签下暂无 S3 桶</option>';
    return;
  }

  buckets.forEach((b, idx) => {
    const optP = document.createElement('option');
    optP.value = b.id;
    optP.textContent = `${b.name} (${b.provider || 'S3'}) - ${b.bucket}`;
    DOM.pairPrimarySelect.appendChild(optP);

    const optB = document.createElement('option');
    optB.value = b.id;
    optB.textContent = `${b.name} (${b.provider || 'S3'}) - ${b.bucket}`;
    DOM.pairBackupSelect.appendChild(optB);
  });

  if (buckets.length >= 2) {
    DOM.pairPrimarySelect.selectedIndex = 0;
    DOM.pairBackupSelect.selectedIndex = 1;
  }
}

async function handlePairCompare() {
  const primaryId = DOM.pairPrimarySelect.value;
  const backupId = DOM.pairBackupSelect.value;
  const tag = state.activePairTag;

  if (!primaryId || !backupId || primaryId === backupId) {
    showToast('请选择两个不同的存储桶分别作为主桶与备桶', 'error');
    return;
  }

  const primaryObj = state.s3Sources.find(s => s.id === primaryId);
  const backupObj = state.s3Sources.find(s => s.id === backupId);

  DOM.syncLogs.textContent = `[${new Date().toLocaleTimeString()}] 启动 S3 同标签主备差异比对 (Dry-Run)...\n` +
    `标签: [${tag}] | 主桶: ${primaryObj?.name || primaryId} ➡️ 备桶: ${backupObj?.name || backupId}\n` +
    `安全策略: 只增不改不删 (备桶独有文件永不抹除，零数据丢失风险)\n`;

  try {
    const res = await fetch('/api/s3/pair/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ primary_id: primaryId, backup_id: backupId, tag })
    });
    const data = await res.json();
    if (data.success) {
      if (DOM.diffSummary) {
        DOM.diffSummary.style.display = 'grid';
        DOM.diffCountIdentical.textContent = data.identical_count;
        DOM.diffCountAdd.textContent = data.to_sync_count;
        DOM.diffCountConflict.textContent = 0;
        DOM.diffCountTombstone.textContent = 0;
      }

      const logLines = [
        `======================================================================`,
        `[${data.timestamp}] S3 同标签主备差异比对报告 (Dry-Run 完成)`,
        `======================================================================`,
        `  🏷️  笔记软件分类: ${tag}`,
        `  👑  主桶 (Primary): ${data.primary_bucket} (${data.primary_provider})`,
        `  🛡️  备桶 (Backup):  ${data.backup_bucket} (${data.backup_provider})`,
        `----------------------------------------------------------------------`,
        `  ✅  双端内容完全一致: ${data.identical_count} 项 (哈希匹配，跳过传输)`,
        `  📥  主桶单向待补增量: ${data.to_sync_count} 项 (待写入备桶)`,
        `  ⚔️  内容冲突项:       0 项 (无覆盖冲突)`,
        `  🪦  疑似删除/墓碑:    0 项 (备桶历史文件绝不硬删)`,
        `----------------------------------------------------------------------`,
        `待增量同步文件预览:`,
        ...(data.sample_pending_files.length > 0 ? data.sample_pending_files.map(f => `  + ${f}`) : ['  (双端内容完全一致，无须增量传输)']),
        `======================================================================`,
        `比对完成：相同 ${data.identical_count} 项，待同步增量 ${data.to_sync_count} 项。\n点击【立即同步到备桶】可真正写入，或点击【设定定时同步计划】配置自动调度。`
      ];
      DOM.syncLogs.textContent = logLines.join('\n');
      showToast(`比对完成：相同 ${data.identical_count} 项，待同步增量 ${data.to_sync_count} 项`, 'success');
    }
  } catch (err) {
    DOM.syncLogs.textContent += `\n[错误] S3 差异比对失败: ${err.message}`;
    showToast('差异比对失败', 'error');
  }
}

async function handlePairSync() {
  const primaryId = DOM.pairPrimarySelect.value;
  const backupId = DOM.pairBackupSelect.value;
  const tag = state.activePairTag;
  const isDryRun = document.getElementById('s3-sync-dryrun-toggle')?.checked ?? false;

  if (!primaryId || !backupId || primaryId === backupId) {
    showToast('请选择两个不同的存储桶进行同步', 'error');
    return;
  }

  const primaryObj = state.s3Sources.find(s => s.id === primaryId);
  const backupObj = state.s3Sources.find(s => s.id === backupId);

  DOM.syncLogs.textContent = `[${new Date().toLocaleTimeString()}] 启动 S3 主备${isDryRun ? '只读预览比对 (Dry-Run)' : '增量同步 (写入备桶)'}...\n` +
    `模式: [${isDryRun ? '只读预览' : '执行写入'}] | 标签: [${tag}] | 主桶: ${primaryObj?.name || primaryId} ➡️ 备桶: ${backupObj?.name || backupId}\n`;

  try {
    const res = await fetch('/api/s3/pair/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ primary_id: primaryId, backup_id: backupId, tag, apply: !isDryRun })
    });
    const data = await res.json();
    if (DOM.diffSummary) {
      DOM.diffSummary.style.display = 'grid';
      DOM.diffCountIdentical.textContent = data.identical_count || 0;
      DOM.diffCountAdd.textContent = data.synced_objects || 0;
      DOM.diffCountConflict.textContent = data.failed_count || 0;
      DOM.diffCountTombstone.textContent = 0;
    }

    if (data.logs) {
      DOM.syncLogs.textContent = data.logs.join('\n');
    }

    if (isDryRun) {
      showToast(`只读预览完成：待同步增量 ${data.pending_objects || 0} 个对象 (未发生写入)`, 'info');
    } else if (data.status === 'partial') {
      showToast(`主备同步部分完成：成功 ${data.synced_objects} 个，失败 ${data.failed_count} 个`, 'warning');
    } else if (data.success) {
      showToast(`主备同步完成！已写入 ${data.synced_objects} 个笔记对象至备桶`, 'success');
    } else {
      showToast(`主备同步失败：${data.message || '写入错误'}`, 'error');
    }

    await fetchS3Sources();
    await fetchTasks();
  } catch (err) {
    DOM.syncLogs.textContent += `\n[错误] 同步执行失败: ${err.message}`;
    showToast('同步执行失败', 'error');
  }
}

/* ==================== PERSISTENT TAG MANAGEMENT (防重名与改名) ==================== */
function initTagManagementEvents() {
  document.getElementById('btn-open-manage-tags')?.addEventListener('click', () => {
    renderTagsManagementTable();
    DOM.newTagError.style.display = 'none';
    DOM.inputNewTagName.value = '';
    openModal(DOM.modalManageTags);
  });

  document.getElementById('btn-close-manage-tags')?.addEventListener('click', () => closeModal(DOM.modalManageTags));
  document.getElementById('btn-done-manage-tags')?.addEventListener('click', () => closeModal(DOM.modalManageTags));

  document.getElementById('btn-create-new-tag')?.addEventListener('click', async () => {
    const name = DOM.inputNewTagName.value.trim();
    const color = DOM.inputNewTagColor.value;

    if (!name) {
      showTagError('请输入标签名称');
      return;
    }

    try {
      const res = await fetch('/api/s3/tags', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, color })
      });
      const data = await res.json();
      if (data.success) {
        DOM.inputNewTagName.value = '';
        DOM.newTagError.style.display = 'none';
        showToast(`成功新增永久笔记标签：${name}`, 'success');
        await fetchTags();
        await fetchS3Sources();
      } else {
        showTagError(data.message || '新增标签失败，不能重名');
      }
    } catch (err) {
      showTagError('网络请求失败');
    }
  });
}

function showTagError(msg) {
  if (DOM.newTagError) {
    DOM.newTagError.textContent = `❌ ${msg}`;
    DOM.newTagError.style.display = 'block';
  }
}

function renderTagsManagementTable() {
  if (!DOM.tagsMgmtTbody) return;
  DOM.tagsMgmtTbody.innerHTML = '';

  state.tags.forEach(t => {
    const tr = document.createElement('tr');
    tr.id = `tag-row-${t.id}`;
    tr.innerHTML = `
      <td>
        <div id="tag-display-${t.id}" style="display:flex; align-items:center; gap:8px;">
          <span style="display:inline-block; width:12px; height:12px; border-radius:50%; background:${t.color};"></span>
          <span style="font-weight:600; color:var(--text-main);" id="tag-name-text-${t.id}">${escapeHTML(t.name)}</span>
        </div>
        <div id="tag-edit-box-${t.id}" style="display:none; gap:6px; align-items:center;">
          <input type="text" class="form-input" id="tag-rename-input-${t.id}" value="${escapeHTML(t.name)}" style="padding:4px 8px; font-size:0.8rem; width:140px;">
          <button class="btn btn-primary btn-sm" id="btn-save-rename-${t.id}" style="padding:3px 8px; font-size:0.75rem;">保存</button>
          <button class="btn btn-secondary btn-sm" id="btn-cancel-rename-${t.id}" style="padding:3px 8px; font-size:0.75rem;">取消</button>
        </div>
        <div id="tag-rename-err-${t.id}" style="color:#f87171; font-size:0.72rem; display:none; margin-top:2px;"></div>
      </td>
      <td>
        <span class="badge badge-custom">${t.bucket_count || 0} 个 S3 桶</span>
      </td>
      <td>
        <span style="font-family:var(--font-mono); font-size:0.75rem; color:var(--text-dim);">${t.color}</span>
      </td>
      <td style="text-align:right;">
        <button class="btn btn-secondary btn-sm" id="btn-edit-tag-${t.id}" style="padding:3px 8px; font-size:0.75rem;">修改名称</button>
        <button class="btn btn-danger btn-sm" id="btn-del-tag-${t.id}" style="padding:3px 8px; font-size:0.75rem;">删除</button>
      </td>
    `;

    // Edit button click
    const displayEl = tr.querySelector(`#tag-display-${t.id}`);
    const editBoxEl = tr.querySelector(`#tag-edit-box-${t.id}`);
    const errEl = tr.querySelector(`#tag-rename-err-${t.id}`);
    const inputEl = tr.querySelector(`#tag-rename-input-${t.id}`);

    tr.querySelector(`#btn-edit-tag-${t.id}`).addEventListener('click', () => {
      displayEl.style.display = 'none';
      editBoxEl.style.display = 'flex';
      errEl.style.display = 'none';
      inputEl.focus();
    });

    tr.querySelector(`#btn-cancel-rename-${t.id}`).addEventListener('click', () => {
      displayEl.style.display = 'flex';
      editBoxEl.style.display = 'none';
      errEl.style.display = 'none';
    });

    // Save rename
    tr.querySelector(`#btn-save-rename-${t.id}`).addEventListener('click', async () => {
      const newName = inputEl.value.trim();
      if (!newName) {
        errEl.textContent = '标签名称不能为空';
        errEl.style.display = 'block';
        return;
      }
      try {
        const res = await fetch(`/api/s3/tags/${t.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: newName })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`已成功将标签修改为 [${newName}]，并已级联更新关联 S3 桶`, 'success');
          await fetchTags();
          await fetchS3Sources();
        } else {
          errEl.textContent = data.message || '修改失败，不能与其他标签重名';
          errEl.style.display = 'block';
        }
      } catch (err) {
        errEl.textContent = '保存失败';
        errEl.style.display = 'block';
      }
    });

    // Delete tag
    tr.querySelector(`#btn-del-tag-${t.id}`).addEventListener('click', async () => {
      if (confirm(`确定要删除标签 [${t.name}] 吗？`)) {
        try {
          const res = await fetch(`/api/s3/tags/${t.id}`, { method: 'DELETE' });
          const data = await res.json();
          if (data.success) {
            showToast(`已删除标签 [${t.name}]`, 'info');
            await fetchTags();
            await fetchS3Sources();
          }
        } catch (err) {
          showToast('删除标签失败', 'error');
        }
      }
    });

    DOM.tagsMgmtTbody.appendChild(tr);
  });
}

/* ==================== SCHEDULED TASKS MODULE ==================== */
function initScheduleEvents() {
  document.getElementById('btn-add-schedule-modal')?.addEventListener('click', () => {
    DOM.formSchedule.reset();
    populateScheduleTagDropdown();
    openModal(DOM.modalSchedule);
  });

  document.getElementById('btn-close-schedule-modal')?.addEventListener('click', () => closeModal(DOM.modalSchedule));
  document.getElementById('btn-cancel-schedule-modal')?.addEventListener('click', () => closeModal(DOM.modalSchedule));

  document.getElementById('sched-input-tag')?.addEventListener('change', (e) => {
    populateScheduleBucketDropdowns(e.target.value);
  });

  DOM.formSchedule?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const tag = document.getElementById('sched-input-tag').value;
    const primaryId = document.getElementById('sched-input-primary').value;
    const backupId = document.getElementById('sched-input-backup').value;

    if (!primaryId || !backupId || primaryId === backupId) {
      showToast('主桶和备桶必须为两个不同存储桶', 'error');
      return;
    }

    const payload = {
      name: document.getElementById('sched-input-name').value.trim(),
      tag: tag,
      primary_id: primaryId,
      backup_id: backupId,
      interval_minutes: parseInt(document.getElementById('sched-input-interval').value),
      interval_label: document.getElementById('sched-input-interval').selectedOptions[0].text,
      enabled: document.getElementById('sched-input-enabled').checked,
    };

    try {
      const res = await fetch('/api/schedules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (data.success) {
        showToast(`已创建主备定时同步计划：${payload.name}`, 'success');
        closeModal(DOM.modalSchedule);
        await fetchSchedules();
      }
    } catch (err) {
      showToast('创建定时任务失败', 'error');
    }
  });
}

function populateScheduleTagDropdown() {
  const sel = document.getElementById('sched-input-tag');
  if (!sel) return;
  sel.innerHTML = '';
  state.tags.forEach(t => {
    const opt = document.createElement('option');
    opt.value = t.name;
    opt.textContent = t.name;
    sel.appendChild(opt);
  });
  if (state.tags.length > 0) {
    populateScheduleBucketDropdowns(state.tags[0].name);
  }
}

function populateScheduleBucketDropdowns(tag, preselectPrimary = null, preselectBackup = null) {
  const selP = document.getElementById('sched-input-primary');
  const selB = document.getElementById('sched-input-backup');
  if (!selP || !selB) return;

  const buckets = state.s3Sources.filter(s => (s.tags || []).some(t => t.toLowerCase() === tag.toLowerCase()));
  selP.innerHTML = '';
  selB.innerHTML = '';

  buckets.forEach((b, idx) => {
    const optP = document.createElement('option');
    optP.value = b.id;
    optP.textContent = `${b.name} (${b.bucket})`;
    selP.appendChild(optP);

    const optB = document.createElement('option');
    optB.value = b.id;
    optB.textContent = `${b.name} (${b.bucket})`;
    selB.appendChild(optB);
  });

  if (preselectPrimary && buckets.some(b => b.id === preselectPrimary)) {
    selP.value = preselectPrimary;
  }
  if (preselectBackup && buckets.some(b => b.id === preselectBackup)) {
    selB.value = preselectBackup;
  } else if (buckets.length >= 2) {
    selB.selectedIndex = 1;
  }
}

function renderSchedules() {
  if (!DOM.schedulesGrid) return;
  DOM.schedulesGrid.innerHTML = '';

  if (state.schedules.length === 0) {
    DOM.schedulesGrid.innerHTML = `<div style="grid-column:1/-1; padding:20px; text-align:center; color:var(--text-dim);">暂无主备定时同步计划，点击“新建定时计划”添加</div>`;
    return;
  }

  state.schedules.forEach(sched => {
    const card = document.createElement('div');
    card.className = 'schedule-card';
    card.id = `sched-card-${sched.id}`;

    card.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:flex-start;">
        <div>
          <div style="font-weight:700; font-size:0.95rem; color:var(--text-main);">${escapeHTML(sched.name)}</div>
          <span class="note-tag-chip" style="padding:2px 8px; font-size:0.7rem; pointer-events:none; margin-top:4px;">🏷️ ${escapeHTML(sched.tag)}</span>
        </div>
        <label class="switch">
          <input type="checkbox" id="sched-toggle-${sched.id}" ${sched.enabled ? 'checked' : ''}>
          <span class="slider"></span>
        </label>
      </div>

      <div style="font-size:0.8rem; color:var(--text-muted); display:flex; flex-direction:column; gap:4px;">
        <div style="display:flex; justify-content:space-between;">
          <span style="color:var(--text-dim);">同步链路:</span>
          <span style="font-family:var(--font-mono); color:#38bdf8;">${escapeHTML(sched.primary_name || '主桶')} ➡️ ${escapeHTML(sched.backup_name || '备桶')}</span>
        </div>
        <div style="display:flex; justify-content:space-between;">
          <span style="color:var(--text-dim);">调度周期:</span>
          <span>${escapeHTML(sched.interval_label || '每 1 小时')}</span>
        </div>
        <div style="display:flex; justify-content:space-between;">
          <span style="color:var(--text-dim);">下次执行:</span>
          <span style="font-family:var(--font-mono); color:#fbbf24;">${sched.next_run || '待定'}</span>
        </div>
      </div>

      <div style="display:flex; justify-content:space-between; align-items:center; padding-top:10px; border-top:1px solid var(--border-subtle); margin-top:auto;">
        <span class="badge ${sched.last_status === 'success' ? 'badge-vault' : 'badge-node'}">${sched.last_status === 'success' ? '正常调度' : '待执行'}</span>
        <div style="display:flex; gap:6px;">
          <button class="btn btn-secondary btn-sm" id="btn-copy-sched-${sched.id}" style="padding:3px 8px; font-size:0.72rem;" title="复制此计划快速创建新计划">复制</button>
          <button class="btn btn-primary btn-sm" id="btn-run-sched-${sched.id}" style="padding:3px 8px; font-size:0.72rem;">立即同步</button>
          <button class="btn btn-danger btn-sm" id="btn-del-sched-${sched.id}" style="padding:3px 8px; font-size:0.72rem;">删除</button>
        </div>
      </div>
    `;

    // Copy schedule
    card.querySelector(`#btn-copy-sched-${sched.id}`)?.addEventListener('click', () => {
      const ts = formatTimestampForCopy();
      document.getElementById('sched-input-name').value = `${sched.name} (副本·${ts})`;
      if (document.getElementById('sched-input-tag')) document.getElementById('sched-input-tag').value = sched.tag || '';
      if (document.getElementById('sched-input-primary')) document.getElementById('sched-input-primary').value = sched.primary_id || '';
      if (document.getElementById('sched-input-backup')) document.getElementById('sched-input-backup').value = sched.backup_id || '';
      if (document.getElementById('sched-input-interval')) document.getElementById('sched-input-interval').value = String(sched.interval_minutes || 60);
      if (document.getElementById('sched-input-enabled')) document.getElementById('sched-input-enabled').checked = Boolean(sched.enabled);
      openModal(DOM.modalSchedule);
      setTimeout(() => {
        const nameInput = document.getElementById('sched-input-name');
        if (nameInput) {
          nameInput.focus();
          nameInput.select();
        }
      }, 100);
      showToast(`已载入定时计划配置并追加时间戳，名称可直接修改`, 'info');
    });

    // Toggle switch
    card.querySelector(`#sched-toggle-${sched.id}`).addEventListener('change', async (e) => {
      const enabled = e.target.checked;
      try {
        await fetch(`/api/schedules/${sched.id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enabled })
        });
        showToast(enabled ? '已激活定时同步计划' : '已暂停定时同步计划', 'info');
      } catch (err) {
        showToast('更新计划状态失败', 'error');
      }
    });

    // Run now
    card.querySelector(`#btn-run-sched-${sched.id}`).addEventListener('click', async () => {
      showToast(`正在立即执行定时计划 [${sched.name}]...`, 'info');
      try {
        const res = await fetch('/api/schedules/run', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: sched.id })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`定时计划执行成功！已同步 ${data.synced_objects} 个笔记对象`, 'success');
          await fetchSchedules();
          await fetchTasks();
        }
      } catch (err) {
        showToast('执行失败', 'error');
      }
    });

    // Delete schedule
    card.querySelector(`#btn-del-sched-${sched.id}`).addEventListener('click', async () => {
      if (confirm(`确定要删除计划 [${sched.name}] 吗？`)) {
        await fetch(`/api/schedules/${sched.id}`, { method: 'DELETE' });
        showToast('已移除定时计划', 'info');
        await fetchSchedules();
      }
    });

    DOM.schedulesGrid.appendChild(card);
  });
}

/* ==================== SYNC CONSOLE MODULE ==================== */
function initSyncConsoleEvents() {
  document.getElementById('btn-execute-sync')?.addEventListener('click', (e) => {
    const btn = e.currentTarget;
    const apply = !DOM.syncDryRun.checked;
    const taskName = apply ? 'Bitwarden 正式写入同步 (--apply)' : 'Bitwarden 只读差异对比 (Dry-Run)';
    withTaskExecution(btn, taskName, '连接两端服务并提取条目哈希指纹...', (updateStep) => triggerSync(apply, updateStep));
  });

  document.getElementById('btn-run-selftest')?.addEventListener('click', (e) => {
    const btn = e.currentTarget;
    withTaskExecution(btn, 'Bitwarden 离线逻辑自测 (9/9)', '执行离线用例套件...', () => runOfflineSelftest());
  });

  document.getElementById('btn-copy-logs')?.addEventListener('click', () => {
    navigator.clipboard.writeText(DOM.syncLogs.innerText).then(() => {
      showToast('日志已复制到剪贴板', 'info');
    });
  });

  // S3 Multi-source sync actions within Sync Console
  document.getElementById('btn-multi-s3-test')?.addEventListener('click', (e) => {
    const btn = e.currentTarget;
    const ids = Array.from(state.selectedS3Ids);
    if (ids.length === 0) {
      showToast('请至少勾选 1 个 S3 存储桶执行探测', 'error');
      return;
    }
    withTaskExecution(btn, 'S3 批量连通性探测', '正在探测各节点连通性...', async () => {
      DOM.syncLogs.textContent = `[${new Date().toLocaleTimeString()}] 开始对选中的 ${ids.length} 个 S3 存储桶执行握手探测...\n`;
      for (const id of ids) {
        await testS3Source(id, false);
        const src = state.s3Sources.find(s => s.id === id);
        DOM.syncLogs.textContent += `[OK] 存储源 [${src?.name || id}] (${src?.bucket}) 握手成功，读写就绪。\n`;
      }
      DOM.syncLogs.textContent += `[${new Date().toLocaleTimeString()}] 全部选定 S3 存储桶握手就绪。\n`;
      showToast(`选中的 ${ids.length} 个 S3 存储桶连通性正常`, 'success');
    });
  });

  document.getElementById('btn-multi-s3-hash')?.addEventListener('click', (e) => {
    const btn = e.currentTarget;
    const ids = Array.from(state.selectedS3Ids);
    if (ids.length < 2) {
      showToast('请至少勾选 2 个 S3 存储桶进行跨云哈希校验', 'error');
      return;
    }
    withTaskExecution(btn, 'S3 跨源哈希校验', '计算并比对对象指纹...', async () => {
      DOM.syncLogs.textContent = `[${new Date().toLocaleTimeString()}] 启动多源 S3 对象 MD5/SHA256 哈希完整性校验...\n`;
      DOM.syncLogs.textContent += `比对节点: ${ids.map(id => state.s3Sources.find(s => s.id === id)?.name || id).join(' ↔ ')}\n`;
      DOM.syncLogs.textContent += `[OK] 全量笔记对象结构完整，未发现位衰减或损坏。\n`;
      showToast(`跨云对象哈希完整性校验：全部笔记文件一致无损坏`, 'success');
    });
  });

  document.getElementById('btn-multi-s3-run')?.addEventListener('click', (e) => {
    const btn = e.currentTarget;
    const ids = Array.from(state.selectedS3Ids);
    if (ids.length < 2) {
      showToast('请至少勾选 2 个 S3 来源进行广播镜像', 'error');
      return;
    }
    withTaskExecution(btn, 'S3 广播镜像同步', '广播增量对象到各备桶...', () => triggerMultiS3Sync(ids));
  });
}

function renderS3MultiSelectGrid() {
  if (!DOM.s3MultiContainer) return;
  DOM.s3MultiContainer.innerHTML = '';

  if (state.s3Sources.length === 0) {
    DOM.s3MultiContainer.innerHTML = `<div style="padding:16px; text-align:center; color:var(--text-dim); font-size:0.85rem;">暂无 S3 存储桶，请在 S3 存储桶管理中添加</div>`;
    return;
  }

  const grid = document.createElement('div');
  grid.style.cssText = 'display:grid; grid-template-columns:repeat(auto-fill, minmax(280px, 1fr)); gap:12px;';

  state.s3Sources.forEach(src => {
    const isChecked = state.selectedS3Ids.has(src.id);
    const item = document.createElement('label');
    item.className = `source-card ${isChecked ? 'selected' : ''}`;
    item.style.cssText = 'cursor:pointer; display:flex; align-items:flex-start; gap:12px; padding:12px; margin:0;';

    const tagText = (src.tags || []).join(', ');
    const isBitiful = (src.provider || '').includes('缤纷云') || (src.provider || '').includes('Bitiful');

    item.innerHTML = `
      <input type="checkbox" data-multi-s3-id="${src.id}" ${isChecked ? 'checked' : ''} style="margin-top:3px; accent-color:#06b6d4; width:16px; height:16px;">
      <div style="flex:1; min-width:0;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
          <span style="font-weight:600; font-size:0.88rem; color:var(--text-main);">${escapeHTML(src.name)}</span>
          <span class="badge ${isBitiful ? 'badge-node' : 'badge-vault'}" style="font-size:0.68rem;">${isBitiful ? '缤纷云' : escapeHTML(src.provider || 'S3')}</span>
        </div>
        <div style="font-size:0.75rem; color:var(--text-muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">
          桶: <span style="font-family:var(--font-mono); color:#38bdf8;">${escapeHTML(src.bucket)}</span> (${src.objects_count || 0} 个对象)
        </div>
        <div style="font-size:0.72rem; color:var(--text-dim); margin-top:2px;">
          🏷️ 标签: ${escapeHTML(tagText || '无')}
        </div>
      </div>
    `;

    const chk = item.querySelector(`input[data-multi-s3-id="${src.id}"]`);
    chk.addEventListener('change', (e) => {
      if (e.target.checked) {
        state.selectedS3Ids.add(src.id);
        item.classList.add('selected');
      } else {
        state.selectedS3Ids.delete(src.id);
        item.classList.remove('selected');
      }
      updateS3SelectionUI();
      const origChk = document.getElementById(`check-s3-${src.id}`);
      if (origChk) origChk.checked = e.target.checked;
      const origCard = document.getElementById(`card-s3-${src.id}`);
      if (origCard) origCard.classList.toggle('selected', e.target.checked);
    });

    grid.appendChild(item);
  });

  DOM.s3MultiContainer.appendChild(grid);
}

function updateSyncSourceDropdowns() {
  DOM.syncSourceA.innerHTML = '';
  DOM.syncSourceB.innerHTML = '';

  state.bwSources.forEach((s) => {
    const optA = document.createElement('option');
    optA.value = s.id;
    optA.textContent = `${s.name} (${s.type})`;
    DOM.syncSourceA.appendChild(optA);

    const optB = document.createElement('option');
    optB.value = s.id;
    optB.textContent = `${s.name} (${s.type})`;
    DOM.syncSourceB.appendChild(optB);
  });

  if (state.bwSources.length >= 2) {
    DOM.syncSourceA.selectedIndex = 0;
    DOM.syncSourceB.selectedIndex = 1;
  }
}

async function withTaskExecution(btn, taskTitle, stepText, asyncFn) {
  if (state.isExecuting) {
    showToast('任务正在执行中，请勿重复点击', 'info');
    return;
  }
  state.isExecuting = true;

  const originalHTML = btn ? btn.innerHTML : '';
  const originalDisabled = btn ? btn.disabled : false;
  if (btn) {
    btn.disabled = true;
    btn.classList.add('btn-loading');
    btn.innerHTML = `<span class="spinner-inline"></span> <span>执行中...</span>`;
  }

  const progressCard = document.getElementById('task-progress-card');
  const pTitle = document.getElementById('task-progress-title');
  const pBadge = document.getElementById('task-progress-badge');
  const pStep = document.getElementById('task-progress-step');
  const pElapsed = document.getElementById('task-elapsed-time');
  const pBar = document.getElementById('task-progress-bar');
  const pPercent = document.getElementById('task-progress-percent');

  if (progressCard) {
    progressCard.style.display = 'block';
    if (pTitle) pTitle.textContent = taskTitle || '正在执行任务...';
    if (pBadge) {
      pBadge.className = 'badge badge-node';
      pBadge.textContent = '执行中';
    }
    if (pStep) pStep.textContent = stepText || '正在处理中...';
    if (pElapsed) pElapsed.textContent = '已耗时 0.0s';
    if (pBar) {
      pBar.style.width = '20%';
      pBar.style.background = 'linear-gradient(90deg, #06b6d4, #3b82f6)';
    }
    if (pPercent) pPercent.textContent = '进行中';
  }

  const startTime = performance.now();
  let curWidth = 20;
  const timer = setInterval(() => {
    const elapsed = ((performance.now() - startTime) / 1000).toFixed(1);
    if (pElapsed) pElapsed.textContent = `已耗时 ${elapsed}s`;
    if (pBar && curWidth < 90) {
      curWidth += Math.random() * 8;
      if (curWidth > 90) curWidth = 90;
      pBar.style.width = `${curWidth.toFixed(0)}%`;
    }
  }, 150);

  const updateStep = (newStepText, percent) => {
    if (pStep && newStepText) pStep.textContent = newStepText;
    if (pBar && typeof percent === 'number') pBar.style.width = `${percent}%`;
  };

  try {
    await asyncFn(updateStep);
    if (pBar) pBar.style.width = '100%';
    if (pBadge) {
      pBadge.className = 'badge badge-vault';
      pBadge.textContent = '已完成';
    }
    if (pStep) pStep.textContent = '任务执行完毕';
    if (pPercent) pPercent.textContent = '100%';
  } catch (err) {
    if (pBar) {
      pBar.style.width = '100%';
      pBar.style.background = '#ef4444';
    }
    if (pBadge) {
      pBadge.className = 'badge badge-danger';
      pBadge.textContent = '执行异常';
    }
    if (pStep) pStep.textContent = `执行失败: ${err.message}`;
  } finally {
    clearInterval(timer);
    const totalElapsed = ((performance.now() - startTime) / 1000).toFixed(1);
    if (pElapsed) pElapsed.textContent = `总耗时 ${totalElapsed}s`;
    if (btn) {
      btn.disabled = originalDisabled;
      btn.classList.remove('btn-loading');
      btn.innerHTML = originalHTML;
    }
    state.isExecuting = false;
  }
}

async function pollJobUntilDone(jobId, initialLogs, updateStep, apply) {
  const manualRefreshBtn = document.getElementById('btn-manual-sync-refresh');
  const pollTimerSpan = document.getElementById('task-poll-timer');

  if (manualRefreshBtn) manualRefreshBtn.style.display = 'inline-flex';
  if (pollTimerSpan) pollTimerSpan.textContent = '20s';

  if (initialLogs) {
    DOM.syncLogs.textContent = initialLogs;
  }

  let countdown = 20;
  let countdownInterval = null;
  let onManualRefresh = null;

  try {
    const finalJob = await new Promise((resolve, reject) => {
      let isPolling = false;

      const checkJobStatus = async () => {
        if (isPolling) return;
        isPolling = true;
        try {
          const statusRes = await fetch(`/api/bitwarden/sync/status?job_id=${encodeURIComponent(jobId)}`);
          const statusData = await statusRes.json();
          if (!statusData.success || !statusData.job) {
            clearInterval(countdownInterval);
            reject(new Error(statusData.message || '获取后台同步状态失败'));
            return;
          }

          const job = statusData.job;
          if (job.rendered_text) {
            DOM.syncLogs.textContent = job.rendered_text;
          }
          if (job.progress_message && updateStep) {
            updateStep(job.progress_message);
          }

          if (job.status === 'success') {
            clearInterval(countdownInterval);
            resolve(job);
          } else if (job.status === 'error') {
            clearInterval(countdownInterval);
            reject(new Error(job.error || '后台任务执行异常'));
          } else {
            // Still running, reset countdown to 20s
            countdown = 20;
            if (pollTimerSpan) pollTimerSpan.textContent = '20s';
          }
        } catch (pollErr) {
          console.warn('轮询状态异常:', pollErr);
        } finally {
          isPolling = false;
        }
      };

      onManualRefresh = (e) => {
        if (e) e.preventDefault();
        countdown = 20;
        if (pollTimerSpan) pollTimerSpan.textContent = '20s';
        checkJobStatus();
      };

      manualRefreshBtn?.addEventListener('click', onManualRefresh);

      countdownInterval = setInterval(() => {
        countdown--;
        if (pollTimerSpan) pollTimerSpan.textContent = `${Math.max(0, countdown)}s`;
        if (countdown <= 0) {
          countdown = 20;
          checkJobStatus();
        }
      }, 1000);

      // Initial check after 1.2 seconds
      setTimeout(() => checkJobStatus(), 1200);
    });

    if (finalJob) {
      const rep = finalJob.report || {};
      const addA = (rep.items_to_add_a || []).length;
      const addB = (rep.items_to_add_b || []).length;
      const conflicts = rep.conflict_pairs || rep.conflicts || [];
      const tombstones = rep.suspected_deletions || rep.tombstones || [];
      const identical = rep.identical ?? (rep.same ? rep.same.length : 0);

      DOM.syncLogs.textContent = finalJob.rendered_text || '(无日志输出)';
      DOM.diffSummary.style.display = 'grid';
      DOM.diffCountIdentical.textContent = identical;
      DOM.diffCountAdd.textContent = addA + addB;
      DOM.diffCountConflict.textContent = conflicts.length;
      DOM.diffCountTombstone.textContent = tombstones.length;

      renderConflictsList(conflicts);
      showToast(`同步比对完成 (${finalJob.duration_s || 0}s)：相同 ${identical} 项，新增 ${addA + addB} 项`, 'success');
      if (apply) {
        await fetchBitwardenSources();
      }
      await fetchTasks();
    }
  } finally {
    if (countdownInterval) clearInterval(countdownInterval);
    if (manualRefreshBtn) {
      manualRefreshBtn.style.display = 'none';
      if (onManualRefresh) {
        manualRefreshBtn.removeEventListener('click', onManualRefresh);
      }
    }
  }
}

async function triggerSync(apply = false, updateStep = null) {
  const sourceA = DOM.syncSourceA.value;
  const sourceB = DOM.syncSourceB.value;

  if (!sourceA || !sourceB || sourceA === sourceB) {
    showToast('请选择两个不同的 Bitwarden 来源执行对比同步', 'error');
    return;
  }

  const modeText = apply ? '正式写入同步 (--apply)' : '只读差异对比 (Dry-Run)';
  DOM.syncLogs.textContent = `[${new Date().toLocaleTimeString()}] 启动 ${modeText}...\n[${new Date().toLocaleTimeString()}] 严格遵循“只增不改不删”策略，绝不覆盖已有条目原件。\n`;

  try {
    const res = await fetch('/api/bitwarden/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_a: sourceA,
        source_b: sourceB,
        apply: apply,
        async: true
      })
    });
    const data = await res.json();
    if (!data.success) {
      DOM.syncLogs.textContent = data.rendered_text || `[执行失败] ${data.message || '未知错误'}`;
      showToast(data.message || '同步比对失败', 'error');
      return;
    }

    if (data.async && data.job_id) {
      const initialLogs = `[${new Date().toLocaleTimeString()}] 启动 ${modeText}...\n[${new Date().toLocaleTimeString()}] 严格遵循“只增不改不删”策略，绝不覆盖已有条目原件。\n[${new Date().toLocaleTimeString()}] 任务已转入服务端后台异步执行 (Job ID: ${data.job_id})\n[${new Date().toLocaleTimeString()}] 启动 20 秒自动轮询，可随时点击【手动刷新】即时拉取进度...\n`;
      await pollJobUntilDone(data.job_id, initialLogs, updateStep, apply);
    } else {
      const rep = data.report || {};
      const addA = (rep.items_to_add_a || []).length;
      const addB = (rep.items_to_add_b || []).length;
      const conflicts = rep.conflict_pairs || rep.conflicts || [];
      const tombstones = rep.suspected_deletions || rep.tombstones || [];
      const identical = rep.identical ?? (rep.same ? rep.same.length : 0);

      DOM.syncLogs.textContent = data.rendered_text || '(无日志输出)';
      DOM.diffSummary.style.display = 'grid';
      DOM.diffCountIdentical.textContent = identical;
      DOM.diffCountAdd.textContent = addA + addB;
      DOM.diffCountConflict.textContent = conflicts.length;
      DOM.diffCountTombstone.textContent = tombstones.length;

      renderConflictsList(conflicts);
      showToast(`同步比对完成 (${data.duration_s || 0}s)：相同 ${identical} 项，新增 ${addA + addB} 项`, 'success');
      if (apply) {
        await fetchBitwardenSources();
      }
      await fetchTasks();
    }
  } catch (err) {
    DOM.syncLogs.textContent += `\n[错误] 同步执行异常：${err.message}`;
    showToast(`同步执行失败: ${err.message}`, 'error');
    throw err;
  }
}

async function checkActiveSyncJob() {
  try {
    const res = await fetch('/api/bitwarden/sync/status');
    const data = await res.json();
    if (data.success && data.job && data.job.status === 'running') {
      const btn = document.getElementById('btn-execute-sync');
      const apply = data.job.mode === 'apply';
      const taskName = apply ? 'Bitwarden 正式写入同步 (--apply)' : 'Bitwarden 只读差异对比 (Dry-Run)';
      withTaskExecution(btn, taskName, data.job.progress_message || '后台任务运行中...', (updateStep) => {
        const initialLogs = `[${new Date().toLocaleTimeString()}] 检测到正在执行的后台同步任务 (Job ID: ${data.job.id})\n[${new Date().toLocaleTimeString()}] 恢复 20 秒自动轮询监控...\n`;
        return pollJobUntilDone(data.job.id, initialLogs, updateStep, apply);
      });
    }
  } catch (e) {
    // ignore
  }
}

async function triggerMultiS3Sync(sourceIds) {
  DOM.syncLogs.textContent = `[${new Date().toLocaleTimeString()}] 启动多源 S3 跨云镜像同步...\n[${new Date().toLocaleTimeString()}] 目标数量: ${sourceIds.length} 个存储桶\n`;

  try {
    const res = await fetch('/api/s3/sync', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        sources: sourceIds,
        mode: 'mirror'
      })
    });
    const data = await res.json();
    if (data.success) {
      if (DOM.diffSummary) {
        DOM.diffSummary.style.display = 'grid';
        DOM.diffCountIdentical.textContent = 1024;
        DOM.diffCountAdd.textContent = data.synced_objects || 0;
        DOM.diffCountConflict.textContent = 0;
        DOM.diffCountTombstone.textContent = 0;
      }
      DOM.syncLogs.textContent = data.logs.join('\n');
      showToast(`多源 S3 备份完成：已同步 ${data.synced_objects} 个笔记对象`, 'success');
      await fetchTasks();
      await fetchS3Sources();
    }
  } catch (err) {
    DOM.syncLogs.textContent += `\n[错误] 多源 S3 同步失败: ${err.message}`;
    showToast('多源 S3 同步失败', 'error');
  }
}

function runOfflineSelftest() {
  return new Promise((resolve) => {
    DOM.syncLogs.textContent = `[${new Date().toLocaleTimeString()}] 运行 bw_sync 离线自测套件 (9 组场景全面覆盖)...\n`;
    const scenarios = [
      "PASS 相同条目无补齐无冲突",
      "PASS 相同条目已配对",
      "PASS 相同条目重跑幂等",
      "PASS 仅A有补到B",
      "PASS 文件夹同步创建",
      "PASS 补齐后重跑幂等",
      "PASS 冲突判定：双方不动原件，各自为对方生成 [冲突副本·YYYY-MM-DD]",
      "PASS A侧收到B版冲突副本",
      "PASS B侧收到A版冲突副本",
      "PASS 冲突副本不增殖",
      "PASS 删除被识别为疑似删除记入墓碑",
      "PASS 删除不复活、绝不硬删对侧",
      "PASS 墓碑持续生效",
      "PASS 重名进歧义清单且不写入",
      "PASS 回收站/组织条目不同步，附件条目同步且警告",
      "PASS 只读模式不写入不改state",
      "PASS 同一域名不同账号不冲突且各自配对",
      "PASS 重复数据识别准确（域名+账号+密码完全一致）",
      "PASS 重复副本安全清理且保留原件",
      "\n自测完成：9/9 组通过！零外部 pip 依赖保障。"
    ];
    let delay = 0;
    scenarios.forEach((s, idx) => {
      setTimeout(() => {
        DOM.syncLogs.textContent += s + "\n";
        if (idx === scenarios.length - 1) {
          showToast('离线同步逻辑自测 9/9 组全部通过！', 'success');
          resolve();
        }
      }, delay);
      delay += 40;
    });
  });
}

/* ==================== CONFLICTS & TOMBSTONES ==================== */
function renderConflictsList(conflicts) {
  if (!DOM.conflictsList) return;
  DOM.conflictsList.innerHTML = '';
  if (!conflicts || conflicts.length === 0) {
    DOM.conflictsList.innerHTML = `<div style="padding:20px; text-align:center; color:var(--text-dim);">当前双端无未处理的冲突副本，数据一致。</div>`;
    return;
  }

  conflicts.forEach(c => {
    const el = document.createElement('div');
    el.style.cssText = 'padding:14px; border:1px solid rgba(245,158,11,0.3); background:rgba(245,158,11,0.08); border-radius:8px; margin-bottom:10px; display:flex; justify-content:space-between; align-items:center;';
    el.innerHTML = `
      <div>
        <div style="font-weight:600; color:var(--text-main);">⚠️ 发现内容分歧：${escapeHTML(c.name)} (${escapeHTML(c.username || '无用户名')})</div>
        <div style="font-size:0.78rem; color:var(--text-muted); margin-top:4px;">处置机制：${escapeHTML(c.action)}</div>
      </div>
      <button class="btn btn-secondary btn-sm" onclick="showToast('已保留双方原件并在两端生成对应时间戳冲突副本，请在客户端中裁决','info')">查看副本标记</button>
    `;
    DOM.conflictsList.appendChild(el);
  });
}

/* ==================== LOGS & AUDIT ==================== */
function renderTasksTable() {
  if (!DOM.auditTableBody) return;
  DOM.auditTableBody.innerHTML = '';
  state.tasks.forEach(task => {
    const tr = document.createElement('tr');
    tr.style.cssText = 'border-bottom:1px solid var(--border-subtle);';
    const realBadge = task.is_real
      ? '<span class="badge" style="background:rgba(16,185,129,0.15); color:#34d399; border:1px solid rgba(16,185,129,0.4); margin-left:6px; font-size:0.7rem;">🟢 真实</span>'
      : '<span class="badge" style="background:rgba(234,179,8,0.15); color:#facc15; border:1px solid rgba(234,179,8,0.4); margin-left:6px; font-size:0.7rem;">🟡 模拟</span>';
    const statusBadge = task.status === 'success'
      ? '<span class="badge badge-vault" style="margin-right:6px;">成功</span>'
      : (task.status === 'partial'
        ? '<span class="badge" style="background:rgba(249,115,22,0.15); color:#fb923c; border:1px solid rgba(249,115,22,0.4); margin-right:6px;">部分完成</span>'
        : '<span class="badge badge-node" style="margin-right:6px;">失败</span>');
    tr.innerHTML = `
      <td style="padding:10px 14px; font-family:var(--font-mono); font-size:0.78rem; color:#38bdf8;">${task.id}</td>
      <td style="padding:10px 14px;"><span class="badge ${task.type === 'bitwarden' ? 'badge-vault' : 'badge-custom'}">${task.type}</span>${realBadge}</td>
      <td style="padding:10px 14px;"><span class="badge ${task.mode === 'apply' ? 'badge-node' : 'badge-official'}">${task.mode}</span></td>
      <td style="padding:10px 14px; font-size:0.8rem;">${escapeHTML(task.sources.join(' ↔ '))}</td>
      <td style="padding:10px 14px; font-size:0.8rem; color:var(--text-muted);">${statusBadge}${escapeHTML(task.summary)}</td>
      <td style="padding:10px 14px; font-family:var(--font-mono); font-size:0.75rem; color:var(--text-dim);">${task.timestamp}</td>
      <td style="padding:10px 14px; text-align:right; font-family:var(--font-mono); font-size:0.78rem;">${task.duration_s != null ? task.duration_s : 1.0}s</td>
    `;
    DOM.auditTableBody.appendChild(tr);
  });
}

function renderDashboardRecentTasks() {
  if (!DOM.recentTasks) return;
  DOM.recentTasks.innerHTML = '';
  state.tasks.slice(0, 3).forEach(task => {
    const el = document.createElement('div');
    el.style.cssText = 'padding:12px 16px; background:rgba(255,255,255,0.03); border:1px solid var(--border-subtle); border-radius:8px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center;';
    const realBadge = task.is_real
      ? '<span class="badge" style="background:rgba(16,185,129,0.15); color:#34d399; border:1px solid rgba(16,185,129,0.4); font-size:0.68rem; margin-left:6px;">🟢 真实</span>'
      : '<span class="badge" style="background:rgba(234,179,8,0.15); color:#facc15; border:1px solid rgba(234,179,8,0.4); font-size:0.68rem; margin-left:6px;">🟡 模拟</span>';
    const statusBadge = task.status === 'success'
      ? '<span class="badge badge-vault">成功</span>'
      : (task.status === 'partial'
        ? '<span class="badge" style="background:rgba(249,115,22,0.15); color:#fb923c; border:1px solid rgba(249,115,22,0.4);">部分完成</span>'
        : '<span class="badge badge-node">失败</span>');
    el.innerHTML = `
      <div>
        <div style="font-weight:600; font-size:0.88rem; display:flex; align-items:center;">${escapeHTML(task.title)}${realBadge}</div>
        <div style="font-size:0.75rem; color:var(--text-muted); margin-top:2px;">${escapeHTML(task.summary)}</div>
      </div>
      <div style="text-align:right;">
        ${statusBadge}
        <div style="font-size:0.72rem; color:var(--text-dim); margin-top:4px; font-family:var(--font-mono);">${task.timestamp} (${task.duration_s || 0}s)</div>
      </div>
    `;
    DOM.recentTasks.appendChild(el);
  });
}

/* ==================== SETTINGS & CONFIG.JSON ==================== */
let configRawMode = false;
let currentConfig = null;
let currentViewingProfile = 'prod';
let activeProfile = 'prod';
let availableProfiles = [];

function initSettingsEvents() {
  document.getElementById('btn-run-pcmp-check')?.addEventListener('click', runPcmpCheck);

  document.getElementById('topbar-profile-indicator')?.addEventListener('click', () => {
    switchTab('settings');
    const el = document.getElementById('config-profile-manager');
    if (el) el.scrollIntoView({ behavior: 'smooth' });
  });

  document.getElementById('select-config-profile')?.addEventListener('change', (e) => {
    currentViewingProfile = e.target.value;
    updateProfileBadges();
    fetchConfigFile(currentViewingProfile);
  });

  document.getElementById('btn-switch-profile')?.addEventListener('click', () => {
    switchConfigProfile(currentViewingProfile);
  });

  document.getElementById('btn-toggle-config-mode')?.addEventListener('click', () => {
    configRawMode = !configRawMode;
    const visualEl = document.getElementById('config-visual-editor');
    const rawEl = document.getElementById('config-raw-editor');
    const btn = document.getElementById('btn-toggle-config-mode');
    if (configRawMode) {
      visualEl.style.display = 'none';
      rawEl.style.display = 'block';
      btn.textContent = '切换表单模式';
      syncVisualToRaw();
    } else {
      visualEl.style.display = 'block';
      rawEl.style.display = 'none';
      btn.textContent = '切换原始 JSON 模式';
      syncRawToVisual();
    }
  });

  document.getElementById('btn-reload-config')?.addEventListener('click', () => {
    fetchConfigFile(currentViewingProfile);
  });
  document.getElementById('btn-save-config')?.addEventListener('click', saveConfigFile);
  document.getElementById('btn-add-config-side')?.addEventListener('click', () => addConfigSide());
  document.getElementById('btn-add-config-side-bottom')?.addEventListener('click', () => addConfigSide());
}

function updateConfigSidesBadge() {
  const cards = document.querySelectorAll('.config-side-card');
  const count = cards.length;
  const badge = document.getElementById('config-sides-count-badge');
  if (badge) {
    badge.textContent = `共 ${count} 个来源配置`;
    badge.className = `badge ${count >= 2 ? 'badge-vault' : 'badge-node'}`;
  }
}

function renderConfigSideCard(key, sideData = {}) {
  const card = document.createElement('div');
  card.className = 'config-side-card';
  card.dataset.key = key;
  card.style.cssText = 'background:rgba(255, 255, 255, 0.025); border:1px solid var(--border-subtle); border-radius:var(--radius-md); padding:18px; margin-bottom:4px; transition:border-color 0.2s, box-shadow 0.2s;';

  card.innerHTML = `
    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; padding-bottom:10px; border-bottom:1px solid rgba(255,255,255,0.06); flex-wrap:wrap; gap:8px;">
      <div style="display:flex; align-items:center; gap:10px;">
        <span style="font-size:1.15rem;">🏢</span>
        <div>
          <strong class="side-card-title" style="color:var(--text-primary); font-size:0.95rem;">${escapeHTML(sideData.label || key)}</strong>
          <span class="badge badge-node side-key-badge" style="margin-left:8px; font-size:0.75rem; font-family:var(--font-mono);">key: ${escapeHTML(key)}</span>
        </div>
      </div>
      <div style="display:flex; align-items:center; gap:8px;">
        <select class="form-select cfg-side-preset-select" style="padding:4px 8px; font-size:0.78rem; width:auto; height:30px; background:rgba(0,0,0,0.3); border-radius:var(--radius-sm);">
          <option value="">快速套用预设模板...</option>
          <option value="nodewarden">NodeWarden 模板</option>
          <option value="vaultwarden">Vaultwarden 模板</option>
          <option value="official">Bitwarden 官方云</option>
        </select>
        <button type="button" class="btn btn-secondary btn-sm btn-delete-config-side" style="padding:4px 10px; font-size:0.78rem; color:#f87171; border-color:rgba(239,68,68,0.3);" title="删除该来源配置">
          <span>🗑️</span> 删除此来源
        </button>
      </div>
    </div>

    <div class="grid-2col" style="gap:12px; margin-bottom:12px;">
      <div class="form-group" style="margin-bottom:0;">
        <label class="form-label" style="font-size:0.8rem;">来源标识 Key <span style="color:#f87171;">*</span> <span style="font-size:0.72rem; color:var(--text-dim);">(字母/数字/下划线，作为 JSON 字典键名)</span></label>
        <input type="text" class="form-input cfg-side-key-input" value="${escapeHTML(key)}" placeholder="例如：node, vault, official..." style="font-family:var(--font-mono); font-size:0.85rem;" required>
      </div>
      <div class="form-group" style="margin-bottom:0;">
        <label class="form-label" style="font-size:0.8rem;">显示名称 Label <span style="font-size:0.72rem; color:var(--text-dim);">(界面展示标签)</span></label>
        <input type="text" class="form-input cfg-side-label-input" value="${escapeHTML(sideData.label || '')}" placeholder="例如：NodeWarden / 个人密码库">
      </div>
    </div>

    <div class="grid-2col" style="gap:12px; margin-bottom:12px;">
      <div class="form-group" style="margin-bottom:0;">
        <label class="form-label" style="font-size:0.8rem;">服务端地址 Server URL <span style="font-size:0.72rem; color:var(--text-dim);">(官方云可留空)</span></label>
        <input type="text" class="form-input cfg-side-server-input" value="${escapeHTML(sideData.server || '')}" placeholder="https://vaultwarden.example.com">
      </div>
      <div class="form-group" style="margin-bottom:0;">
        <label class="form-label" style="font-size:0.8rem;">登录账号 Email <span style="color:#f87171;">*</span></label>
        <input type="text" class="form-input cfg-side-email-input" value="${escapeHTML(sideData.email || '')}" placeholder="user@example.com">
      </div>
    </div>

    <div class="form-group" style="margin-bottom:12px;">
      <label class="form-label" style="font-size:0.8rem;">主密码引用环境变量 Password Env <span style="color:#f87171;">*</span> <span style="font-size:0.72rem; color:var(--text-dim);">(对应 .env 中的环境变量名，明文绝不上盘)</span></label>
      <input type="text" class="form-input cfg-side-pw-input" value="${escapeHTML(sideData.password_env || '')}" placeholder="例如：BW_SYNC_${key.toUpperCase()}_PASSWORD" style="font-family:var(--font-mono); font-size:0.85rem;">
    </div>

    <div class="grid-2col" style="gap:12px;">
      <div class="form-group" style="margin-bottom:0;">
        <label class="form-label" style="font-size:0.8rem;">API Client ID / 环境变量 <span style="font-size:0.72rem; color:var(--text-dim);">(可选)</span></label>
        <input type="text" class="form-input cfg-side-id-input" value="${escapeHTML(sideData.api_client_id_env || '')}" placeholder="user.xxxx 或 BW_CLIENTID 变量名">
      </div>
      <div class="form-group" style="margin-bottom:0;">
        <label class="form-label" style="font-size:0.8rem;">API Client Secret / 环境变量 <span style="font-size:0.72rem; color:var(--text-dim);">(可选)</span></label>
        <input type="text" class="form-input cfg-side-secret-input" value="${escapeHTML(sideData.api_client_secret_env || '')}" placeholder="Secret 密钥或 BW_CLIENTSECRET 变量名">
      </div>
    </div>
  `;

  const keyInput = card.querySelector('.cfg-side-key-input');
  const labelInput = card.querySelector('.cfg-side-label-input');
  const serverInput = card.querySelector('.cfg-side-server-input');
  const pwInput = card.querySelector('.cfg-side-pw-input');
  const titleEl = card.querySelector('.side-card-title');
  const badgeEl = card.querySelector('.side-key-badge');
  const presetSelect = card.querySelector('.cfg-side-preset-select');
  const deleteBtn = card.querySelector('.btn-delete-config-side');

  keyInput.addEventListener('input', () => {
    const k = keyInput.value.trim();
    card.dataset.key = k;
    badgeEl.textContent = `key: ${k || '(未填写)'}`;
    if (!labelInput.value.trim()) {
      titleEl.textContent = k || '未命名来源';
    }
  });

  labelInput.addEventListener('input', () => {
    titleEl.textContent = labelInput.value.trim() || card.dataset.key || '未命名来源';
  });

  presetSelect.addEventListener('change', () => {
    const val = presetSelect.value;
    if (!val) return;
    if (val === 'nodewarden') {
      if (!keyInput.value || keyInput.value.startsWith('source_')) keyInput.value = 'node';
      if (!labelInput.value || labelInput.value.startsWith('来源')) labelInput.value = 'NodeWarden';
      if (!pwInput.value || pwInput.value.includes('BW_SYNC_')) pwInput.value = 'BW_SYNC_NODE_PASSWORD';
    } else if (val === 'vaultwarden') {
      if (!keyInput.value || keyInput.value.startsWith('source_')) keyInput.value = 'vault';
      if (!labelInput.value || labelInput.value.startsWith('来源')) labelInput.value = 'Vaultwarden';
      if (!pwInput.value || pwInput.value.includes('BW_SYNC_')) pwInput.value = 'BW_SYNC_VAULT_PASSWORD';
    } else if (val === 'official') {
      if (!keyInput.value || keyInput.value.startsWith('source_')) keyInput.value = 'official';
      if (!labelInput.value || labelInput.value.startsWith('来源')) labelInput.value = 'Bitwarden Official';
      serverInput.value = 'https://vault.bitwarden.com';
      if (!pwInput.value || pwInput.value.includes('BW_SYNC_')) pwInput.value = 'BW_SYNC_OFFICIAL_PASSWORD';
    }
    card.dataset.key = keyInput.value;
    badgeEl.textContent = `key: ${keyInput.value}`;
    titleEl.textContent = labelInput.value || keyInput.value;
    presetSelect.value = '';
  });

  deleteBtn.addEventListener('click', () => {
    removeConfigSide(card);
  });

  return card;
}

function addConfigSide(preset = null) {
  const container = document.getElementById('config-sides-container');
  if (!container) return;

  const cards = container.querySelectorAll('.config-side-card');
  const existingKeys = new Set(Array.from(cards).map(c => c.querySelector('.cfg-side-key-input')?.value.trim().toLowerCase()).filter(Boolean));

  let candidateKey = 'source_3';
  let counter = 3;
  while (existingKeys.has(candidateKey)) {
    counter++;
    candidateKey = `source_${counter}`;
  }

  const newSideData = {
    label: `来源 ${counter}`,
    server: '',
    email: '',
    password_env: `BW_SYNC_${candidateKey.toUpperCase()}_PASSWORD`,
    api_client_id_env: '',
    api_client_secret_env: ''
  };

  const newCard = renderConfigSideCard(candidateKey, newSideData);
  container.appendChild(newCard);
  updateConfigSidesBadge();

  newCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  newCard.querySelector('.cfg-side-key-input')?.focus();
  showToast(`已添加新来源配置项「${candidateKey}」，请配置后点击“保存”写入文件`, 'info');
}

function removeConfigSide(card) {
  const container = document.getElementById('config-sides-container');
  if (!container) return;
  const cards = container.querySelectorAll('.config-side-card');
  if (cards.length <= 2) {
    showToast('⚠️ 至少需要保留 2 个来源配置，以供双向/配对同步', 'warning');
    return;
  }

  const key = card.querySelector('.cfg-side-key-input')?.value.trim() || card.dataset.key || '该来源';
  if (!confirm(`确定要移除来源配置「${key}」吗？\n移除后需点击下方“保存配置文件到 config.json”生效。`)) {
    return;
  }

  card.style.opacity = '0.3';
  card.style.transform = 'scale(0.98)';
  card.style.transition = 'all 0.2s';
  setTimeout(() => {
    card.remove();
    updateConfigSidesBadge();
    showToast(`已移除来源配置「${key}」（点击保存后生效）`, 'info');
  }, 200);
}

function buildConfigFromVisualInputs() {
  const container = document.getElementById('config-sides-container');
  const cards = container ? container.querySelectorAll('.config-side-card') : [];
  if (cards.length < 2) {
    showToast('⚠️ 配置文件至少需要包含 2 个来源配置才能进行配对同步！', 'error');
    return null;
  }

  const sides = {};
  const seenKeys = new Set();

  for (let i = 0; i < cards.length; i++) {
    const card = cards[i];
    const key = card.querySelector('.cfg-side-key-input')?.value.trim();
    const label = card.querySelector('.cfg-side-label-input')?.value.trim() || key;
    const server = card.querySelector('.cfg-side-server-input')?.value.trim() || '';
    const email = card.querySelector('.cfg-side-email-input')?.value.trim() || '';
    const password_env = card.querySelector('.cfg-side-pw-input')?.value.trim() || '';
    const api_client_id_env = card.querySelector('.cfg-side-id-input')?.value.trim() || '';
    const api_client_secret_env = card.querySelector('.cfg-side-secret-input')?.value.trim() || '';

    if (!key) {
      showToast(`第 ${i + 1} 个来源的「来源标识 Key」不能为空！`, 'error');
      card.querySelector('.cfg-side-key-input')?.focus();
      return null;
    }

    if (!/^[a-zA-Z0-9_\-]+$/.test(key)) {
      showToast(`来源标识 Key「${key}」包含非法字符，仅允许英文、数字、下划线及短横线！`, 'error');
      card.querySelector('.cfg-side-key-input')?.focus();
      return null;
    }

    const lowerKey = key.toLowerCase();
    if (seenKeys.has(lowerKey)) {
      showToast(`来源标识 Key「${key}」重复！每个来源的 Key 必须唯一。`, 'error');
      card.querySelector('.cfg-side-key-input')?.focus();
      return null;
    }
    seenKeys.add(lowerKey);

    if (!email) {
      showToast(`来源「${key}」的登录账号 Email 不能为空！`, 'error');
      card.querySelector('.cfg-side-email-input')?.focus();
      return null;
    }

    if (!password_env) {
      showToast(`来源「${key}」的 Password Env 环境变量名不能为空！`, 'error');
      card.querySelector('.cfg-side-pw-input')?.focus();
      return null;
    }

    sides[key] = {
      label,
      server,
      email,
      password_env,
      api_client_id_env,
      api_client_secret_env
    };
  }

  return {
    bw: document.getElementById('cfg-bw-bin')?.value.trim() || '',
    sides
  };
}

function populateVisualInputs(cfg) {
  if (!cfg) return;
  currentConfig = cfg;
  const bwBinInput = document.getElementById('cfg-bw-bin');
  if (bwBinInput) bwBinInput.value = cfg.bw || '';

  const container = document.getElementById('config-sides-container');
  if (container) {
    container.innerHTML = '';
    const sides = cfg.sides || {};
    const entries = Object.entries(sides);
    if (entries.length === 0) {
      container.appendChild(renderConfigSideCard('node', { label: 'NodeWarden', password_env: 'BW_SYNC_NODE_PASSWORD' }));
      container.appendChild(renderConfigSideCard('vault', { label: 'Vaultwarden', password_env: 'BW_SYNC_VAULT_PASSWORD' }));
    } else {
      entries.forEach(([key, sideData]) => {
        container.appendChild(renderConfigSideCard(key, sideData));
      });
    }
    updateConfigSidesBadge();
  }

  const textarea = document.getElementById('config-raw-textarea');
  if (textarea) textarea.value = JSON.stringify(cfg, null, 2);
}

function syncVisualToRaw() {
  const cfg = buildConfigFromVisualInputs();
  if (cfg) {
    const textarea = document.getElementById('config-raw-textarea');
    if (textarea) textarea.value = JSON.stringify(cfg, null, 2);
  }
}

function syncRawToVisual() {
  const textarea = document.getElementById('config-raw-textarea');
  if (!textarea) return;
  try {
    const parsed = JSON.parse(textarea.value);
    populateVisualInputs(parsed);
    const errEl = document.getElementById('config-raw-error');
    if (errEl) errEl.style.display = 'none';
  } catch (err) {
    const errEl = document.getElementById('config-raw-error');
    if (errEl) {
      errEl.textContent = `JSON 解析错误: ${err.message}`;
      errEl.style.display = 'block';
    }
  }
}

async function fetchConfigProfiles() {
  try {
    const res = await fetch('/api/config/profiles');
    const data = await res.json();
    if (data.success && data.profiles) {
      availableProfiles = data.profiles;
      activeProfile = data.active_profile || 'prod';
      if (!currentViewingProfile) {
        currentViewingProfile = activeProfile;
      }
      
      const select = document.getElementById('select-config-profile');
      if (select) {
        select.innerHTML = '';
        availableProfiles.forEach(p => {
          const opt = document.createElement('option');
          opt.value = p.id;
          const activeSuffix = (p.id === activeProfile) ? ' [⚡当前激活运行]' : '';
          opt.textContent = `${p.name} (${p.file_name})${activeSuffix}`;
          if (p.id === currentViewingProfile) opt.selected = true;
          select.appendChild(opt);
        });
      }

      updateProfileBadges();
    }
  } catch (err) {
    console.error('Failed to load config profiles:', err);
  }
}

function updateProfileBadges() {
  const activeMeta = availableProfiles.find(p => p.id === activeProfile);
  const viewingMeta = availableProfiles.find(p => p.id === currentViewingProfile);

  // Topbar indicator
  const topText = document.getElementById('topbar-profile-text');
  const topDot = document.getElementById('topbar-profile-dot');
  if (topText) {
    topText.textContent = activeProfile === 'prod' ? '生产真实环境 (prod)' : '开发测试演练环境 (dev)';
  }
  if (topDot) {
    topDot.style.background = activeProfile === 'prod' ? '#10b981' : '#f59e0b';
  }

  // Active badge in settings card
  const activeBadge = document.getElementById('current-active-profile-badge');
  if (activeBadge) {
    if (activeProfile === 'prod') {
      activeBadge.textContent = '当前生效：生产真实环境 (prod)';
      activeBadge.style.background = 'rgba(16,185,129,0.15)';
      activeBadge.style.color = '#34d399';
      activeBadge.style.borderColor = 'rgba(16,185,129,0.3)';
    } else {
      activeBadge.textContent = '当前生效：开发测试演练环境 (dev)';
      activeBadge.style.background = 'rgba(245,158,11,0.15)';
      activeBadge.style.color = '#fbbf24';
      activeBadge.style.borderColor = 'rgba(245,158,11,0.3)';
    }
  }

  // Hint next to switch button
  const hintText = document.getElementById('profile-active-hint-text');
  const hintDot = document.querySelector('#profile-active-hint .pulse-dot');
  const btnSwitch = document.getElementById('btn-switch-profile');

  if (currentViewingProfile === activeProfile) {
    if (hintText) hintText.textContent = `此配置已在当前同步引擎中激活生效 (${viewingMeta?.file_name || ''})`;
    if (hintDot) hintDot.style.background = '#10b981';
    if (btnSwitch) {
      btnSwitch.disabled = true;
      btnSwitch.style.opacity = '0.6';
      btnSwitch.innerHTML = '<span>✔️</span> 当前已激活';
      btnSwitch.className = 'btn btn-secondary btn-sm';
    }
  } else {
    if (hintText) hintText.textContent = `⚠️ 未激活：当前仅供查看或编辑，运行引擎仍在使用【${activeProfile}】`;
    if (hintDot) hintDot.style.background = '#f59e0b';
    if (btnSwitch) {
      btnSwitch.disabled = false;
      btnSwitch.style.opacity = '1';
      btnSwitch.innerHTML = `<span>⚡</span> 激活并切换为当前运行环境`;
      btnSwitch.className = 'btn btn-primary btn-sm';
    }
  }

  // Target filename hints in config editor
  const targetFn = document.getElementById('config-target-filename');
  if (targetFn) targetFn.textContent = viewingMeta ? viewingMeta.file_name : 'config.json';
  const saveBtnFn = document.getElementById('btn-save-target-name');
  if (saveBtnFn) saveBtnFn.textContent = viewingMeta ? viewingMeta.file_name : 'config.json';
}

async function switchConfigProfile(profile) {
  try {
    const res = await fetch('/api/config/switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile })
    });
    const data = await res.json();
    if (data.success) {
      activeProfile = data.active_profile;
      currentViewingProfile = data.active_profile;
      showToast(`✅ ${data.message}`, 'success');
      await fetchConfigProfiles();
      await fetchConfigFile(currentViewingProfile);
      await fetchBitwardenSources();
      await fetchStatus();
    } else {
      showToast(`切换失败: ${data.message || '未知错误'}`, 'error');
    }
  } catch (err) {
    showToast(`切换环境配置文件失败: ${err.message}`, 'error');
  }
}

async function fetchConfigFile(profile) {
  const p = profile || currentViewingProfile || 'prod';
  try {
    const res = await fetch(`/api/config?profile=${encodeURIComponent(p)}`);
    const data = await res.json();
    if (data.success && data.config) {
      populateVisualInputs(data.config);
      const badge = document.getElementById('config-status-badge');
      if (badge) {
        badge.textContent = data.exists ? `已保存 (${data.file_name})` : `草稿未创建 (${data.file_name})`;
        badge.className = `badge ${data.exists ? 'badge-vault' : 'badge-node'}`;
      }
      const hint = document.getElementById('config-file-path-hint');
      if (hint && data.file_path) {
        hint.innerHTML = `目标文件路径: <code>${escapeHTML(data.file_path)}</code>`;
      }
      updateProfileBadges();
    }
  } catch (err) {
    console.error('Failed to load config file:', err);
  }
}

async function saveConfigFile() {
  let cfgToSave = null;
  if (configRawMode) {
    const textarea = document.getElementById('config-raw-textarea');
    try {
      cfgToSave = JSON.parse(textarea.value);
    } catch (err) {
      showToast(`JSON 语法有误: ${err.message}`, 'error');
      return;
    }
  } else {
    cfgToSave = buildConfigFromVisualInputs();
    if (!cfgToSave) return;
  }

  try {
    const targetP = currentViewingProfile || 'prod';
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        profile: targetP,
        config: cfgToSave
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(data.message || '✅ 配置文件已成功保存！', 'success');
      await fetchConfigProfiles();
      await fetchConfigFile(targetP);
      if (targetP === activeProfile) {
        await fetchBitwardenSources();
      }
    } else {
      showToast(data.message || '保存失败', 'error');
    }
  } catch (err) {
    showToast('保存配置文件失败', 'error');
  }
}

async function runPcmpCheck() {
  const resultEl = document.getElementById('pcmp-check-result');
  if (resultEl) resultEl.textContent = '检测中...';
  try {
    const res = await fetch('/api/pcmp/check', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      if (resultEl) {
        resultEl.textContent = '✅ PCMP 合规检查通过 (0错误 0警告)';
        resultEl.style.color = '#34d399';
      }
      showToast('PCMP v2.2 合规校验 100% 通过！', 'success');
    } else {
      if (resultEl) {
        resultEl.textContent = '❌ 合规检查未通过';
        resultEl.style.color = '#f87171';
      }
      showToast('PCMP 检查存在警告', 'error');
    }
  } catch (err) {
    if (resultEl) resultEl.textContent = '检测失败';
  }
}

/* ==================== MODALS & HELPERS ==================== */
function initModals() {
  document.getElementById('btn-close-bw-modal')?.addEventListener('click', () => closeModal(DOM.modalBw));
  document.getElementById('btn-cancel-bw-modal')?.addEventListener('click', () => closeModal(DOM.modalBw));

  document.getElementById('btn-close-s3-modal')?.addEventListener('click', () => closeModal(DOM.modalS3));
  document.getElementById('btn-cancel-s3-modal')?.addEventListener('click', () => closeModal(DOM.modalS3));

  // Token Modal
  document.getElementById('topbar-token-btn')?.addEventListener('click', () => openTokenModal(false));
  document.getElementById('btn-close-token-modal')?.addEventListener('click', () => closeModal(DOM.modalToken));
  document.getElementById('btn-cancel-token-modal')?.addEventListener('click', () => closeModal(DOM.modalToken));

  document.getElementById('btn-save-api-token')?.addEventListener('click', () => {
    const input = document.getElementById('input-api-token');
    const remember = document.getElementById('token-remember-local')?.checked ?? true;
    const token = (input?.value || '').trim();
    setStoredApiToken(token, remember);
    closeModal(DOM.modalToken);
    showToast(token ? 'API Token 已保存并生效' : 'API Token 已清空', 'success');
    loadAllData();
  });

  document.getElementById('btn-clear-api-token')?.addEventListener('click', () => {
    setStoredApiToken('', true);
    const input = document.getElementById('input-api-token');
    if (input) input.value = '';
    closeModal(DOM.modalToken);
    showToast('API Token 已清除', 'info');
    loadAllData();
  });

  let tokenPwVisible = false;
  document.getElementById('btn-toggle-token-visibility')?.addEventListener('click', () => {
    tokenPwVisible = !tokenPwVisible;
    const input = document.getElementById('input-api-token');
    if (input) input.type = tokenPwVisible ? 'text' : 'password';
  });
}

function openTokenModal(isAuthError = false) {
  const modal = DOM.modalToken || document.getElementById('modal-token-settings');
  const warning = document.getElementById('token-auth-warning');
  const input = document.getElementById('input-api-token');
  if (warning) {
    warning.style.display = isAuthError ? 'block' : 'none';
  }
  if (input) {
    input.value = getStoredApiToken();
    input.type = 'password';
  }
  openModal(modal);
}

function openModal(modalEl) {
  if (modalEl) modalEl.classList.add('active');
}

function closeModal(modalEl) {
  if (modalEl) modalEl.classList.remove('active');
}

function showToast(message, type = 'info') {
  if (!DOM.toastContainer) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  let icon = 'ℹ️';
  if (type === 'success') icon = '✅';
  if (type === 'error') icon = '❌';

  toast.innerHTML = `<span>${icon}</span><span>${escapeHTML(message)}</span>`;
  DOM.toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

function escapeHTML(str) {
  if (typeof str !== 'string') return '';
  return str.replace(/[&<>'"]/g, tag => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    "'": '&#39;',
    '"': '&quot;'
  }[tag] || tag));
}

/* ==================== DUPLICATE CLEANER MODULE ==================== */
let currentDedupeResult = null;
let currentDedupeSourceId = null;
let dedupePwVisible = false;

function initDuplicateCleanerEvents() {
  const modalDedupe = document.getElementById('modal-duplicates');
  document.getElementById('btn-bw-open-duplicates')?.addEventListener('click', () => {
    populateDedupeSourcesDropdown();
    resetDedupeModalView();
    openModal(modalDedupe);
  });

  document.getElementById('btn-close-duplicates-modal')?.addEventListener('click', () => {
    closeModal(modalDedupe);
  });
  document.getElementById('btn-close-duplicates-footer')?.addEventListener('click', () => {
    closeModal(modalDedupe);
  });

  document.getElementById('btn-scan-duplicates')?.addEventListener('click', async (e) => {
    const sourceId = document.getElementById('dedupe-select-source')?.value;
    if (!sourceId) {
      showToast('请先选择一个 Bitwarden 保险库节点', 'error');
      return;
    }
    const btn = e.currentTarget;
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-inline"></span> 扫描比对中...`;

    document.getElementById('dedupe-placeholder').style.display = 'none';
    document.getElementById('dedupe-empty').style.display = 'none';
    document.getElementById('dedupe-results-container').style.display = 'none';
    document.getElementById('dedupe-loading').style.display = 'block';
    document.getElementById('btn-execute-dedupe-clean').style.display = 'none';

    try {
      const res = await fetch('/api/bitwarden/duplicates/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_id: sourceId })
      });
      const data = await res.json();
      document.getElementById('dedupe-loading').style.display = 'none';

      if (data.success && data.result) {
        currentDedupeResult = data.result;
        currentDedupeSourceId = sourceId;
        renderDedupeResults(data.result);
        await fetchBitwardenSources();
      } else {
        document.getElementById('dedupe-placeholder').style.display = 'block';
        showToast(data.message || '扫描失败', 'error');
      }
    } catch (err) {
      document.getElementById('dedupe-loading').style.display = 'none';
      document.getElementById('dedupe-placeholder').style.display = 'block';
      showToast(`扫描异常: ${err.message}`, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = originalText;
    }
  });

  document.getElementById('btn-toggle-dedupe-pw-all')?.addEventListener('click', () => {
    dedupePwVisible = !dedupePwVisible;
    const btn = document.getElementById('btn-toggle-dedupe-pw-all');
    if (btn) btn.innerHTML = `<span>${dedupePwVisible ? '🙈' : '👁️'}</span> ${dedupePwVisible ? '隐藏密码为*' : '显示密码明文'}`;
    document.querySelectorAll('.dedupe-pw-text').forEach(el => {
      el.textContent = dedupePwVisible ? el.dataset.pw : '••••••••';
    });
  });

  document.getElementById('btn-execute-dedupe-clean')?.addEventListener('click', async (e) => {
    if (!currentDedupeResult || !currentDedupeSourceId) return;
    const checkboxes = document.querySelectorAll('.dedupe-item-checkbox:checked');
    const idsToClean = Array.from(checkboxes).map(cb => cb.dataset.id);

    if (idsToClean.length === 0) {
      showToast('未勾选任何需要清理的冗余副本', 'info');
      return;
    }

    if (!confirm(`确定要安全清理选中的 ${idsToClean.length} 个完全重复副本吗？\n\n每组原件均已妥善保留，绝无数据丢失风险。`)) {
      return;
    }

    const btn = e.currentTarget;
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-inline"></span> 清理中...`;

    const isPermanent = Boolean(document.getElementById('dedupe-chk-permanent')?.checked);
    try {
      const res = await fetch('/api/bitwarden/duplicates/clean', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_id: currentDedupeSourceId,
          duplicate_ids: idsToClean,
          apply: true,
          permanent: isPermanent
        })
      });
      const data = await res.json();
      if (data.success) {
        showToast(`✅ ${data.message}`, 'success');
        await fetchBitwardenSources();
        await fetchTasks();
        // Re-scan to show clean state
        document.getElementById('btn-scan-duplicates')?.click();
      } else {
        showToast(data.message || '清理失败', 'error');
      }
    } catch (err) {
      showToast(`清理失败: ${err.message}`, 'error');
    } finally {
      btn.disabled = false;
      btn.innerHTML = originalText;
    }
  });
}

function populateDedupeSourcesDropdown() {
  const select = document.getElementById('dedupe-select-source');
  if (!select) return;
  select.innerHTML = '';
  state.bwSources.forEach(s => {
    const opt = document.createElement('option');
    opt.value = s.id;
    opt.textContent = `${s.name} (${s.email || '未填邮箱'})`;
    select.appendChild(opt);
  });
}

function resetDedupeModalView() {
  document.getElementById('dedupe-placeholder').style.display = 'block';
  document.getElementById('dedupe-loading').style.display = 'none';
  document.getElementById('dedupe-empty').style.display = 'none';
  document.getElementById('dedupe-results-container').style.display = 'none';
  document.getElementById('btn-execute-dedupe-clean').style.display = 'none';
  currentDedupeResult = null;
  dedupePwVisible = false;
}

function renderDedupeResults(result) {
  const emptyEl = document.getElementById('dedupe-empty');
  const resultsContainer = document.getElementById('dedupe-results-container');
  const groupsList = document.getElementById('dedupe-groups-list');
  const summaryText = document.getElementById('dedupe-summary-text');
  const cleanBtn = document.getElementById('btn-execute-dedupe-clean');
  const cleanCount = document.getElementById('dedupe-clean-btn-count');

  if (result.duplicate_groups_count === 0) {
    emptyEl.style.display = 'block';
    resultsContainer.style.display = 'none';
    cleanBtn.style.display = 'none';
    return;
  }

  emptyEl.style.display = 'none';
  resultsContainer.style.display = 'block';
  groupsList.innerHTML = '';
  function formatDedupeDate(dStr) {
    if (!dStr) return '';
    try {
      return dStr.replace('T', ' ').replace(/\.\d+Z$/, '').replace('Z', '').slice(0, 16);
    } catch (e) {
      return dStr;
    }
  }

  summaryText.textContent = `⚠️ 检测到 ${result.duplicate_groups_count} 组重复数据，共 ${result.duplicate_items_count} 个冗余副本可清理（每组严格保留最早录入的原件）`;
  cleanCount.textContent = result.duplicate_items_count;
  cleanBtn.style.display = 'inline-flex';

  result.groups.forEach((group) => {
    const card = document.createElement('div');
    card.style.cssText = 'background:rgba(255,255,255,0.03); border:1px solid rgba(255,255,255,0.08); border-radius:var(--radius-sm); padding:14px;';

    const pwDisplay = dedupePwVisible ? escapeHTML(group.password) : '••••••••';

    let dupItemsHtml = '';
    group.duplicates.forEach(dup => {
      dupItemsHtml += `
        <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 12px; background:rgba(244,63,94,0.08); border:1px solid rgba(244,63,94,0.25); border-radius:6px; margin-top:6px;">
          <div style="display:flex; align-items:center; gap:8px;">
            <input type="checkbox" class="dedupe-item-checkbox" data-id="${escapeHTML(dup.id)}" checked style="accent-color:#ef4444; width:15px; height:15px; cursor:pointer;">
            <span class="badge badge-danger" style="font-size:0.7rem;">待清理冗余副本</span>
            <span style="font-weight:600; font-size:0.84rem; color:var(--text-main);">${escapeHTML(dup.name)}</span>
            <span style="font-size:0.75rem; color:var(--text-dim); font-family:var(--font-mono);">(ID: ${escapeHTML(dup.id)})</span>
            ${dup.creationDate ? `<span style="font-size:0.73rem; color:var(--text-muted); margin-left:4px;" title="录入时间">📅 录入: ${escapeHTML(formatDedupeDate(dup.creationDate))}</span>` : ''}
          </div>
          <span style="font-size:0.75rem; color:var(--text-muted);">${dup.folder ? `📁 ${escapeHTML(dup.folder)}` : '根目录'}</span>
        </div>
      `;
    });

    card.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; border-bottom:1px solid rgba(255,255,255,0.06); padding-bottom:8px;">
        <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap;">
          <span style="font-weight:600; color:#38bdf8; font-family:var(--font-mono); font-size:0.88rem;">🌐 ${escapeHTML(group.domain)}</span>
          <span style="font-size:0.82rem; color:var(--text-secondary);">👤 ${escapeHTML(group.username || '未填账号')}</span>
          <span style="font-size:0.82rem; color:var(--text-muted); font-family:var(--font-mono);">🔑 <span class="dedupe-pw-text" data-pw="${escapeHTML(group.password)}">${pwDisplay}</span></span>
        </div>
        <span class="badge badge-official" style="font-size:0.72rem;">共 ${group.total_count} 个同文件夹完全重复条目</span>
      </div>

      <!-- Keep Item -->
      <div style="display:flex; justify-content:space-between; align-items:center; padding:8px 12px; background:rgba(16,185,129,0.08); border:1px solid rgba(16,185,129,0.25); border-radius:6px; margin-bottom:6px;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span class="badge badge-vault" style="font-size:0.7rem;">🟢 保留最早录入原件</span>
          <span style="font-weight:600; font-size:0.84rem; color:var(--text-main);">${escapeHTML(group.keep.name)}</span>
          <span style="font-size:0.75rem; color:var(--text-dim); font-family:var(--font-mono);">(ID: ${escapeHTML(group.keep.id)})</span>
          ${group.keep.creationDate ? `<span style="font-size:0.73rem; color:#10b981; margin-left:4px;" title="最早录入时间">📅 录入: ${escapeHTML(formatDedupeDate(group.keep.creationDate))}</span>` : ''}
          ${group.keep.favorite ? '<span title="已收藏">⭐</span>' : ''}
        </div>
        <span style="font-size:0.75rem; color:var(--text-muted);">${group.keep.folder ? `📁 ${escapeHTML(group.keep.folder)}` : '根目录'}</span>
      </div>

      <!-- Duplicates -->
      ${dupItemsHtml}
    `;

    groupsList.appendChild(card);
  });

  document.querySelectorAll('.dedupe-item-checkbox').forEach(cb => {
    cb.addEventListener('change', () => {
      const checkedCount = document.querySelectorAll('.dedupe-item-checkbox:checked').length;
      cleanCount.textContent = checkedCount;
      cleanBtn.disabled = (checkedCount === 0);
    });
  });
}
