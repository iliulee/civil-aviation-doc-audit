// src/views/Closing.js —— 整改销号（Task 7）
// 问题登记 + open→fixed→closed 循环流转 + localStorage 持久化
const KEY = 'wb_closing_issues';
const STATUS = [
  { id: 'open',   label: '待整改', cls: 'danger' },
  { id: 'fixed',  label: '已整改', cls: 'warn' },
  { id: 'closed', label: '已销号', cls: 'ok' },
];
const NEXT = { open: 'fixed', fixed: 'closed', closed: 'open' };

function load() {
  try { return JSON.parse(localStorage.getItem(KEY)) || []; } catch { return []; }
}
function save(list) {
  try { localStorage.setItem(KEY, JSON.stringify(list)); } catch (e) {}
}

export default function renderClosing(container, ctx) {
  const data = ctx.WB.index;
  const project = (data && data.project_name) || '';
  container.innerHTML =
    `<div class="wb-section-hdr"><h3>整改销号</h3>` +
    `<span class="wb-badge neutral">${project} · 状态：待整改→已整改→已销号</span></div>` +
    `<div class="wb-card"><div class="wb-section-hdr"><h3>登记问题</h3></div>` +
    `<div style="display:flex;gap:8px;flex-wrap:wrap">` +
    `<input id="cl-title" class="wb-input" placeholder="问题标题（必填）" style="flex:1;min-width:180px">` +
    `<input id="cl-prof" class="wb-input" placeholder="专业 / 部位（可选）" style="min-width:140px">` +
    `<button class="wb-btn primary" id="cl-add">＋ 登记</button></div></div>` +
    `<div id="cl-list"></div>`;

  document.getElementById('cl-add').addEventListener('click', addIssue);
  renderList();

  function addIssue() {
    const title = document.getElementById('cl-title').value.trim();
    if (!title) { alert('请填写问题标题'); return; }
    const prof = document.getElementById('cl-prof').value.trim();
    const list = load();
    list.unshift({ id: 'ISS-' + Date.now(), title, prof, status: 'open', created: now() });
    save(list);
    document.getElementById('cl-title').value = '';
    document.getElementById('cl-prof').value = '';
    renderList();
  }

  function renderList() {
    const list = load();
    const box = document.getElementById('cl-list');
    if (list.length === 0) {
      box.innerHTML = '<div class="wb-empty" style="padding:40px"><div class="wb-empty-icon">✅</div><div class="wb-empty-sub">暂无登记问题</div></div>';
      return;
    }
    box.innerHTML = list.map(it => {
      const st = STATUS.find(s => s.id === it.status);
      return `<div class="wb-card" style="margin-top:10px;display:flex;align-items:center;gap:12px">` +
        `<span class="wb-badge ${st.cls}">${st.label}</span>` +
        `<div style="flex:1"><div style="font-weight:600">${escapeHtml(it.title)}</div>` +
        `<div style="font-size:12px;color:var(--color-text-tertiary)">${escapeHtml(it.prof || '')} · ${it.created}</div></div>` +
        `<button class="wb-btn" data-cycle="${it.id}">→ ${actionLabel(it)}</button>` +
        `<button class="wb-btn" data-del="${it.id}" style="padding:4px 8px">删</button></div>`;
    }).join('');

    box.querySelectorAll('[data-cycle]').forEach(b => b.addEventListener('click', e => cycle(e.target.dataset.cycle)));
    box.querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', e => {
      const list2 = load(); save(list2.filter(x => x.id !== e.target.dataset.del)); renderList();
    }));
  }

  function cycle(id) {
    const list = load();
    const it = list.find(x => x.id === id);
    if (!it) return;
    it.status = NEXT[it.status];
    if (it.status === 'closed') it.closed = now();
    save(list); renderList();
  }
}

function actionLabel(it) {
  const next = NEXT[it.status];
  if (next === 'closed') return '销号';
  if (next === 'fixed') return '标记已整改';
  return '重新打开';
}

function now() {
  const d = new Date();
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}