// src/views/Verify.js —— 数据核对入口（v1 跳转；见 Task 8）
export default function renderVerify(container) {
  container.innerHTML = `
    <div class="wb-section">
      <div class="wb-section-hdr"><h3>数据核对</h3></div>
      <div class="wb-empty">
        <div class="wb-empty-icon">✏️</div>
        <div class="wb-empty-title">数据核对模块（实现中）</div>
        <div class="wb-empty-sub">此处将列出待核对清单并跳转独立核对编辑器。</div>
      </div>
    </div>`;
}