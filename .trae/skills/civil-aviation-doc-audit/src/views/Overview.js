// src/views/Overview.js —— 项目总览（实现见 Task 3）
export default function renderOverview(container) {
  container.innerHTML = `
    <div class="wb-section">
      <div class="wb-section-hdr"><h3>项目总览</h3></div>
      <div class="wb-empty">
        <div class="wb-empty-icon">📊</div>
        <div class="wb-empty-title">项目总览模块（实现中）</div>
        <div class="wb-empty-sub">此处将展示统计卡 / 断档 / 重扫 TOP10。</div>
      </div>
    </div>`;
}