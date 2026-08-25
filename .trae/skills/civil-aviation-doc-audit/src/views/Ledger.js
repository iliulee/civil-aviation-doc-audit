// src/views/Ledger.js —— 台账三本（Task 5, D6）
// 材料/送检/报验三本；手工登记存 localStorage；导出走 SheetJS（不手写 CSV）
import * as XLSX from 'xlsx';

const LEDGERS = [
  { id: 'material', title: '材料台账', columns: ['日期', '材料名称', '规格型号', '数量', '单位', '备注'] },
  { id: 'testing',  title: '送检台账', columns: ['送检日期', '试件/样品', '检测项目', '委托单位', '状态', '备注'] },
  { id: 'inspect',  title: '报验台账', columns: ['报验日期', '工程部位', '报验内容', '检验批', '结论', '备注'] },
];

function loadRows(id) {
  try { return JSON.parse(localStorage.getItem('wb_ledger_' + id)) || []; } catch { return []; }
}
function saveRows(id, rows) {
  try { localStorage.setItem('wb_ledger_' + id, JSON.stringify(rows)); } catch (e) {}
}

export default function renderLedger(container) {
  container.innerHTML =
    '<div class="wb-section-hdr"><h3>台账三本</h3>' +
    '<span class="wb-badge neutral">数据保存在本机浏览器，导出为 Excel</span></div>' +
    '<div class="wb-stats" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">' +
    LEDGERS.map(l => `<div class="wb-stat-card" style="cursor:pointer" data-open="${l.id}">` +
      `<div class="wb-stat-label">${l.title}</div>` +
      `<div class="wb-stat-value" id="cnt-${l.id}">${loadRows(l.id).length}</div>` +
      `<div class="wb-stat-hint">点击登记 / 导出</div></div>`).join('') +
    '</div><div id="ledger-panel"></div>';

  container.querySelectorAll('[data-open]').forEach(card => {
    card.addEventListener('click', () => openLedger(card.dataset.open));
  });
}

function openLedger(id) {
  const led = LEDGERS.find(l => l.id === id);
  const panel = document.getElementById('ledger-panel');
  const rows = loadRows(id);
  panel.innerHTML =
    `<div class="wb-card"><div class="wb-section-hdr"><h3>${led.title}</h3>` +
    `<div><button class="wb-btn primary" id="ldr-add">＋ 新增</button> ` +
    `<button class="wb-btn" id="ldr-export">导出 Excel</button></div></div>` +
    `<div style="overflow-x:auto"><table class="wb-table" id="ldr-table"><thead><tr>` +
    led.columns.map(c => `<th>${c}</th>`).join('') + `<th></th></tr></thead>` +
    `<tbody>${rows.map((r, i) => rowHTML(led, r, i)).join('') || emptyRow(led.columns.length)}</tbody></table></div></div>`;

  document.getElementById('ldr-add').addEventListener('click', () => addRow(led));
  document.getElementById('ldr-export').addEventListener('click', () => exportLedger(led, rows));
  panel.querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', e => {
    const i = +e.target.dataset.del;
    const r = loadRows(id); r.splice(i, 1); saveRows(id, r);
    openLedger(id); refreshCards();
  }));
}

function addRow(led) {
  const row = prompt(`新增${led.title}记录，请用"${led.columns.join('|')}"填写`);
  if (!row) return;
  const cells = row.split('|');
  const record = {};
  led.columns.forEach((c, i) => record[c] = (cells[i] || '').trim());
  const rows = loadRows(led.id); rows.push(record); saveRows(led.id, rows);
  openLedger(led.id); refreshCards();
}

function rowHTML(led, r, i) {
  const cells = led.columns.map(c =>
    `<td>${escapeHtml(r[c] !== undefined ? r[c] : '')}</td>`).join('');
  return `<tr>${cells}<td><button class="wb-btn" data-del="${i}" style="padding:2px 8px">删</button></td></tr>`;
}
function emptyRow(colSpan) {
  return `<tr><td colspan="${colSpan + 1}"><div class="wb-empty" style="padding:20px"><div class="wb-empty-sub">暂无记录，点击"新增"登记</div></div></td></tr>`;
}

function exportLedger(led, rows) {
  const ws = XLSX.utils.json_to_sheet(rows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, led.title);
  XLSX.writeFile(wb, led.title + '_' + new Date().toISOString().slice(0, 10) + '.xlsx');
}

function refreshCards() {
  LEDGERS.forEach(l => {
    const el = document.getElementById('cnt-' + l.id);
    if (el) el.textContent = loadRows(l.id).length;
  });
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}