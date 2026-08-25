// src/views/Board.js —— 资料进度看板（SortableJS 拖拽；见 Task 4）
export default function renderBoard(container) {
  container.innerHTML = `
    <div class="wb-section">
      <div class="wb-section-hdr"><h3>资料进度看板</h3></div>
      <div class="wb-empty">
        <div class="wb-empty-icon">🗂️</div>
        <div class="wb-empty-title">资料进度看板模块（实现中）</div>
        <div class="wb-empty-sub">此处将实现 8 节点进度轴 + 看板列 + 拖拽。</div>
      </div>
    </div>`;
}