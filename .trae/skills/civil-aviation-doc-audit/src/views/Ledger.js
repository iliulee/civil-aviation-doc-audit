// src/views/Ledger.js —— 台账三本（SheetJS 导出；见 Task 5）
export default function renderLedger(container) {
  container.innerHTML = `
    <div class="wb-section">
      <div class="wb-section-hdr"><h3>台账三本</h3></div>
      <div class="wb-empty">
        <div class="wb-empty-icon">📒</div>
        <div class="wb-empty-title">台账三本模块（实现中）</div>
        <div class="wb-empty-sub">此处将实现材料/送检/报验三本台账登记与导出。</div>
      </div>
    </div>`;
}