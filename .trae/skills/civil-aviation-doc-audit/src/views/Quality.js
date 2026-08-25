// src/views/Quality.js —— 数据概览导出（Task 6, D6）
// 6 维度口径概览 + 文档明细表格 + SheetJS 导出全部核对结果
import * as XLSX from 'xlsx';

const DIMENSIONS = [
  { id: 'professional', label: '按专业', key: d => d.professional || '未分类' },
  { id: 'doc_type',     label: '按文档类型', key: d => d.doc_type || '未分类' },
  { id: 'ocr_status',   label: '按OCR状态', key: d => d.ocr_status || 'pending' },
  { id: 'verified',     label: '按核对状态', key: d => d.human_verified ? '已核对' : '未核对' },
  { id: 'suspects',     label: '按存疑',   key: d => (d.confusion_suspects || 0) > 0 ? '有存疑' : '无存疑' },
  { id: 'alerts',       label: '按告警',   key: d => (d.quality_alerts || 0) > 0 ? '有告警' : '无告警' },
];

export default function renderQuality(container, ctx) {
  const data = ctx.WB.index;
  if (!data) {
    container.innerHTML = '<div class="wb-section"><div class="wb-empty"><div class="wb-empty-icon">🔍</div><div class="wb-empty-title">尚未加载项目数据</div></div></div>';
    return;
  }
  const docs = data.documents || [];

  container.innerHTML =
    `<div class="wb-section-hdr"><h3>数据概览导出</h3>` +
    `<span class="wb-badge neutral">${docs.length} 份文档</span></div>` +
    `<div class="wb-card"><div class="wb-section-hdr"><h3>六维口径概览</h3>` +
    `<button class="wb-btn primary" id="q-export">导出全部核对结果</button></div>` +
    `<div id="q-dim"></div></div>` +
    `<div class="wb-card" style="margin-top:14px"><div class="wb-section-hdr"><h3>明细说明</h3>` +
    `<p style="margin:0;font-size:13px;color:var(--color-text-secondary)">导出文件包含每份文档的核对/存疑/OCR 全量字段，列头为中文。</p></div></div>`;

  renderDims(DIMENSIONS[0]);
  document.getElementById('q-export').addEventListener('click', () => exportAll(docs));
  container.querySelector('#q-dim').parentElement.querySelector('.wb-section-hdr').insertAdjacentHTML('afterbegin',
    `<div style="display:flex;gap:6px;flex-wrap:wrap">` +
    DIMENSIONS.map(d => `<button class="wb-btn" data-dim="${d.id}">${d.label}</button>`).join('') +
    `</div>`);

  container.querySelectorAll('[data-dim]').forEach(b => b.addEventListener('click', () => {
    const dim = DIMENSIONS.find(x => x.id === b.dataset.dim);
    renderDims(dim);
  }));

  function renderDims(dim) {
    const buckets = {};
    docs.forEach(d => { const k = dim.key(d); buckets[k] = (buckets[k] || 0) + 1; });
    const group = document.getElementById('q-dim');
    group.innerHTML = `<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px">` +
      Object.entries(buckets).map(([k, n]) =>
        `<div class="wb-stat-card"><div class="wb-stat-label">${escapeHtml(k)}</div>` +
        `<div class="wb-stat-value">${n}</div></div>`).join('') +
      `</div>`;
  }
}

function exportAll(docs) {
  const fields = [
    ['id', 'ID'], ['original_file', '原文件名'], ['professional', '专业'], ['doc_type', '文档类型'],
    ['pages', '页数'], ['extraction_mode', '提取方式'], ['ocr_status', 'OCR状态'],
    ['ocr_confidence', 'OCR置信度'], ['human_verified', '已核对'], ['quality_alerts', '质量告警数'],
    ['confusion_suspects', '存疑数'], ['subdivision_code', '分部'], ['updated_at', '更新时间'],
  ];
  const rows = docs.map(d => {
    const o = {};
    fields.forEach(([key, zh]) => {
      let v = d[key];
      if (key === 'human_verified') v = v ? '是' : '否';
      if (key === 'ocr_confidence' && typeof v === 'number') v = +(v * 100).toFixed(1);
      o[zh] = v !== undefined && v !== null ? v : '';
    });
    return o;
  });
  const ws = XLSX.utils.json_to_sheet(rows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, '核对结果');
  const name = (typeof document !== 'undefined' && document.title) || '项目';
  XLSX.writeFile(wb, `核对结果_${name}_${new Date().toISOString().slice(0, 10)}.xlsx`);
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}