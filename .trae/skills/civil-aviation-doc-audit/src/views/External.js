// src/views/External.js —— 规则与反馈（Task 9, v10）
// 规则管理：内嵌 iframe 加载 8765 规则面板 + 存活探测降级提示
// 反馈 / 规则编辑器保持可点开（rule-editor.html 由 8765 服务托管）
const RULE_ORIGIN = 'http://localhost:8765';

export default function renderExternal(container, ctx) {
  mountExternal(container, ctx);
}

export function mountExternal(container) {
  container.innerHTML =
    `<div class="wb-section-hdr"><h3>规则管理</h3>` +
    `<span class="wb-badge neutral" id="ext-state">检测中…</span></div>` +
    `<div class="wb-card" style="height:72vh;position:relative;overflow:hidden;padding:0">` +
      `<iframe id="ext-frame" style="width:100%;height:100%;border:0;display:none" src="about:blank"></iframe>` +
      `<div id="ext-fallback" style="display:none;position:absolute;inset:0;flex-direction:column;align-items:center;justify-content:center;gap:14px;padding:24px;text-align:center">` +
        `<div class="wb-empty-icon">🔌</div>` +
        `<div class="wb-empty-title">规则服务未启动</div>` +
        `<div class="wb-empty-sub" style="max-width:420px">请先启动一站式启动器：双击项目文件夹里的<b>「启动工作台.bat」</b>，等服务起来后回到本页<b>重新检测</b>。</div>` +
        `<a class="wb-btn primary" href="javascript:void(0)" id="ext-retry">重新检测</a>` +
      `</div>` +
    `</div>`;

  probe(container);
}

// 探测 8765 是否存活；不依赖 CORS（no-cors：连不上才 reject）。
function probe(container) {
  const state = container.querySelector('#ext-state');
  const frame = container.querySelector('#ext-frame');
  const fallback = container.querySelector('#ext-fallback');
  // 每次 probe 前重置 retry 按钮（去掉旧监听），避免反复点击导致监听累加
  const rawBtn = container.querySelector('#ext-retry');
  const retryBtn = rawBtn.cloneNode(true);
  rawBtn.replaceWith(retryBtn);

  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 2500);
  fetch(RULE_ORIGIN + '/api/rules', { mode: 'no-cors', signal: ctrl.signal })
    .then(() => {
      clearTimeout(timer);
      state.textContent = '已连接';
      state.className = 'wb-badge ok';
      frame.src = RULE_ORIGIN + '/';
      frame.style.display = 'block';
      fallback.style.display = 'none';
    })
    .catch(() => {
      clearTimeout(timer);
      state.textContent = '未连接';
      state.className = 'wb-badge warn';
      fallback.style.display = 'flex';
      retryBtn.addEventListener('click', () => probe(container));
    });
}