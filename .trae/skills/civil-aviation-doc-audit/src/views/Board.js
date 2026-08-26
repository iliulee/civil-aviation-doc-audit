// src/views/Board.js —— 资料进度看板（Task 4, D6）
// 拖拽用 SortableJS（不手写）；拖拽结果写 localStorage 覆盖层（不改 index.json 真值）
// ECharts 核对环只读展示 human_verified 占比
import Sortable from 'sortablejs';
import * as echarts from 'echarts';

const OVERLAY_KEY = 'wb_board_overlay'; // { cardId: columnId }

// 模块级状态：跨多次 render 复用，避免监听累加 / ECharts 实例泄漏（意见#5）
let _chart = null;
let _resizeBound = false;

// 8 节点进度轴（行业习惯：开检隐分竣验交档）
const STEPS = ['开工', '检查', '隐蔽', '分部', '竣工', '验收', '移交', '归档'];
const STAGE_INDEX = { noted: 0, ongoing: 1, hidden: 2, subdivision: 3, completed: 4, inspected: 5, handover: 6, archived: 7 };

function loadOverlay() {
  try { return JSON.parse(localStorage.getItem(OVERLAY_KEY)) || {}; } catch { return {}; }
}
function saveOverlay(o) {
  try { localStorage.setItem(OVERLAY_KEY, JSON.stringify(o)); } catch (e) {}
}

export default function renderBoard(container, ctx) {
  const { WB } = ctx;
  const data = WB.index;
  const docs = (data && data.documents) || [];

  if (!data) {
    container.innerHTML =
      '<div class="wb-section"><div class="wb-empty"><div class="wb-empty-icon">🗂️</div>' +
      '<div class="wb-empty-title">尚未加载项目数据</div></div></div>';
    return;
  }

  // 四状态列（排序优先级：存疑 > 已核对 > 待核对 > 待处理）
  const columns = [
    { id: 'todo',   title: '待处理',  cls: 'neutral', match: d => !d.human_verified && !hasIssues(d) && d.ocr_status !== 'completed' },
    { id: 'review', title: '待核对',  cls: 'accent',  match: d => !d.human_verified && !hasIssues(d) && d.ocr_status === 'completed' },
    { id: 'doubt',  title: '存疑',    cls: 'warn',    match: d => !d.human_verified && hasIssues(d) },
    { id: 'done',   title: '已核对',  cls: 'ok',      match: d => !!d.human_verified },
  ];
  function hasIssues(d) { return (d.quality_alerts || 0) > 0 || (d.confusion_suspects || 0) > 0; }

  // 布局
  container.innerHTML =
    `<div class="wb-section-hdr"><h3>资料进度看板</h3>` +
    `<span class="wb-badge neutral">${docs.length} 份文档 · 拖拽卡片到目标列（仅本地记录）</span></div>` +
    `<div class="wb-card">` + renderProgressAxis(data) + `</div>` +
    `<div class="wb-board" id="wb-board"></div>`;

  // 核对环
  const ringEl = document.createElement('div');
  container.appendChild(ringEl).outerHTML = '<div id="wb-ring" style="height:220px;margin-top:14px"></div>';

  const boardEl = document.getElementById('wb-board');
  const overlay = loadOverlay();

  columns.forEach(col => {
    const colEl = document.createElement('div');
    colEl.className = 'wb-board-col';
    const membership = docs.filter(d =>
      (overlay[d.id] === col.id) || (overlay[d.id] === undefined && col.match(d))
    );
    colEl.innerHTML =
      `<div class="wb-board-col-hdr"><span>${col.title}</span>` +
      `<span class="wb-badge ${col.cls}">${membership.length}</span></div>` +
      `<div class="wb-board-list" data-col="${col.id}">` +
      membership.map(cardHTML).join('') + `</div>`;
    boardEl.appendChild(colEl);
  });

  // SortableJS 跨容器拖拽
  document.querySelectorAll('.wb-board-list').forEach(list => {
    Sortable.create(list, {
      group: 'wb', animation: 150, ghostClass: 'sortable-ghost', dragClass: 'sortable-drag',
      onEnd(evt) {
        const id = evt.item.dataset.id;
        const toCol = evt.to.dataset.col;
        if (!id || !toCol) return;
        overlay[id] = toCol;
        saveOverlay(overlay);
        refreshCounts();
      },
    });
  });

  function refreshCounts() {
    const o = loadOverlay();
    // 重新统计每列卡片数（含覆盖层）
    document.querySelectorAll('.wb-board-col').forEach(colEl => {
      const colId = colEl.querySelector('.wb-board-list').dataset.col;
      const count = docs.filter(d =>
        (o[d.id] === colId) || (o[d.id] === undefined && (columns.find(c => c.id === colId) || {}).match(d))
      ).length;
      colEl.querySelector('.wb-badge').textContent = count;
    });
  }

  // ===== ECharts 核对环 =====
  if (_chart) _chart.dispose();              // 复用前释放旧实例，防多次导航泄漏（意见#5）
  const verified = docs.filter(d => d.human_verified).length;
  const pending = docs.length - verified;
  _chart = echarts.init(document.getElementById('wb-ring'));
  _chart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} 份 ({d}%)' },
    series: [{
      type: 'pie', radius: ['54%', '78%'], avoidLabelOverlap: false,
      label: { show: true, formatter: '{b}\n{c}' },
      data: [
        { value: pending, name: '待核对', itemStyle: { color: '#2563eb' } },
        { value: verified, name: '已核对', itemStyle: { color: '#0d9488' } },
      ],
    }],
  });

  // resize 监听在模块级只绑一次，回调始终指向最新实例（意见#5）
  if (!_resizeBound) {
    window.addEventListener('resize', () => { if (_chart) _chart.resize(); });
    _resizeBound = true;
  }
}

function renderProgressAxis(data) {
  const cur = data.stage || 'ongoing';
  const nowIdx = Math.max(0, Math.min(STEPS.length - 1, (STAGE_INDEX[cur] !== undefined ? STAGE_INDEX[cur] : 1)));
  return `<div class="wb-progress-axis" id="wb-axis">` +
    STEPS.map((s, i) => {
      const cls = i < nowIdx ? 'done' : (i === nowIdx ? 'now' : '');
      return `<div class="wb-pa-step ${cls}"><span class="dot" data-idx="${i}">${cls === 'done' ? '✔' : (i + 1)}</span>${s}</div>` +
        (i < STEPS.length - 1 ? `<div class="wb-pa-line${i < nowIdx ? ' done' : ''}"></div>` : '');
    }).join('') + `</div>`;
}

function cardHTML(d) {
  const issues = [];
  if ((d.quality_alerts || 0) > 0) issues.push('⚠质量');
  if ((d.confusion_suspects || 0) > 0) issues.push('?存疑');
  const badge = issues.length ? `<span class="wb-badge danger" style="margin-top:4px">${issues.join(' ')}</span>` : '';
  return `<div class="wb-board-card" data-id="${d.id || ''}">` +
    `<div style="font-weight:600">${d.original_file || d.id || '—'}</div>` +
    `<div style="color:var(--color-text-tertiary);font-size:12px">${[d.professional, d.doc_type].filter(Boolean).join(' · ')}</div>` +
    badge + `</div>`;
}