// src/main.js —— 资料员工作台外壳入口
// 职责：渲染顶栏/导航；七模块注册表 + hash 路由（动态 import）；与数据层联动
import { WB, autoLoad, restoreLastHandle, pickProjectFolder } from './data.js';
import './styles/tokens.css';

const MODULES = [
  { id: 'overview',  icon: '📊', label: '项目总览',    render: () => import('./views/Overview.js') },
  { id: 'verify',    icon: '✏️', label: '数据核对',    render: () => import('./views/Verify.js') },
  { id: 'board',     icon: '🗂️', label: '资料进度看板', render: () => import('./views/Board.js') },
  { id: 'ledger',    icon: '📒', label: '台账三本',    render: () => import('./views/Ledger.js') },
  { id: 'quality',   icon: '🔍', label: '数据概览导出', render: () => import('./views/Quality.js') },
  { id: 'closing',   icon: '✅', label: '整改销号',    render: () => import('./views/Closing.js') },
  { id: 'external',  icon: '🔌', label: '规则与反馈',  render: () => import('./views/External.js') },
];

let mainEl = null;
let statusEl = null;
let currentId = null;

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function readHash() {
  const h = location.hash.replace(/^#\/?/, '');
  return MODULES.some(m => m.id === h) ? h : 'overview';
}

function render(id) {
  const m = MODULES.find(x => x.id === id) || MODULES[0];
  currentId = id = m.id;
  document.querySelectorAll('.wb-module-btn').forEach(b => b.classList.toggle('active', b.dataset.module === id));
  mainEl.innerHTML = '<div class="wb-empty"><div class="wb-empty-icon">⏳</div><div class="wb-empty-title">加载中…</div></div>';
  m.render().then(mod => {
    if (currentId !== id) return; // 防竞态：期间用户切换了模块
    mainEl.innerHTML = '';
    const view = document.createElement('div');
    view.className = 'wb-view';
    mainEl.appendChild(view);
    (mod.default || mod)(view, { WB, MODULES, render });
  }).catch(err => {
    mainEl.innerHTML =
      `<div class="wb-empty"><div class="wb-empty-icon">⚠️</div>` +
      `<div class="wb-empty-title">模块加载失败</div>` +
      `<div class="wb-empty-sub">${escapeHtml(err && err.message ? err.message : '未知错误')}</div></div>`;
  });
}

function navigate(id) {
  const h = '#/' + id;
  if (location.hash === h) { render(id); } else { location.hash = h; }
}

function updateStatus(text, cls) {
  if (!statusEl) return;
  statusEl.textContent = text;
  statusEl.className = 'wb-project-status ' + (cls || 'empty');
}

function projectName() {
  return (WB.index && WB.index.project_name) || '';
}

function mount() {
  const app = document.getElementById('app');
  app.innerHTML = `
    <header class="wb-topbar">
      <div class="wb-brand">📚 资料员工作台</div>
      <div class="wb-project">
        <button class="wb-btn" id="wb-open-project" title="通过 File System Access API 选择数据底座目录">打开项目</button>
        <span class="wb-project-status empty" id="wb-status">未加载项目</span>
      </div>
    </header>
    <nav class="wb-nav" id="wb-nav"></nav>
    <main class="wb-main" id="wb-main"></main>
  `;
  statusEl = document.getElementById('wb-status');
  mainEl = document.getElementById('wb-main');

  const navEl = document.getElementById('wb-nav');
  MODULES.forEach(m => {
    const b = document.createElement('button');
    b.className = 'wb-module-btn';
    b.dataset.module = m.id;
    b.textContent = `${m.icon} ${m.label}`;
    b.addEventListener('click', () => navigate(m.id));
    navEl.appendChild(b);
  });

  document.getElementById('wb-open-project').addEventListener('click', onOpenProject);
  window.addEventListener('hashchange', () => render(readHash()));
}

async function onOpenProject() {
  const ok = await pickProjectFolder();
  if (ok) { updateStatus('已连接项目', 'ok'); render(currentId || readHash()); }
}

async function init() {
  mount();
  // 数据源优先级：恢复上次授权目录句柄（IndexedDB）> HTTP fetch（dev/部署）
  const restored = await restoreLastHandle();
  if (restored) { updateStatus('已恢复项目：' + projectName(), 'ok'); }
  else {
    const fetched = await autoLoad();
    if (fetched) { updateStatus('HTTP 已加载：' + projectName(), 'ok'); }
    else { updateStatus('未加载项目', 'empty'); }
  }
  render(readHash());
}

// 数据就绪后（异步选目录/HTPP）刷新当前模块
WB.onDataLoaded = () => {
  updateStatus((WB.loadMode === 'fsapi' ? '已连接项目' : 'HTTP 已加载') + '：' + projectName(), 'ok');
  if (currentId) render(currentId);
};

init();