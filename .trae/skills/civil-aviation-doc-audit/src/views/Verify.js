// src/views/Verify.js —— 数据核对入口（Task 8, D1）
// v1：列出待核对文档 + 跳转独立核对编辑器；v2：注册 message 监听，为 iframe 并入铺路

// v2 并入埋点监听：模块级只注册一次，避免每次 render 累加（意见#5）
let _msgBound = false;

export default function renderVerify(container, ctx) {
  const { WB } = ctx;
  if (!_msgBound) {
    window.addEventListener('message', (e) => {
      const m = e.data;
      if (m && m.wbVersion) {
        console.log('[Verify] 收到编辑器握手:', m.wbVersion);
        // v2 阶段：用 e.source.postMessage 回传 WB.foundationDirHandle
        if (e.source && WB.foundationDirHandle) {
          try { e.source.postMessage({ type: 'wb:dirhandle-ready' }, '*'); } catch (err) { console.warn(err); }
        }
      }
    });
    _msgBound = true;
  }

  const data = WB.index;
  const docs = (data && data.documents) || [];
  const pending = docs.filter(d => !d.human_verified);
  const suspects = docs.filter(d => (!d.human_verified) && ((d.confusion_suspects || 0) > 0 || (d.quality_alerts || 0) > 0));

  const editorHref = '数据核对编辑器.html';

  container.innerHTML =
    `<div class="wb-section-hdr"><h3>数据核对</h3>` +
    `<span class="wb-badge ${pending.length ? 'warn' : 'ok'}">${pending.length} 份待核对</span></div>` +
    `<div class="wb-card" style="margin-bottom:14px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">` +
    `<div><div style="font-weight:600">核对编辑器（v1 独立窗口）</div>` +
    `<div style="font-size:12px;color:var(--color-text-tertiary)">本期编辑器保持独立打开；v2 将并入工作台标签页。</div></div>` +
    `<a class="wb-btn primary" href="${editorHref}" target="_blank" rel="noopener" id="verify-open">🚀 打开数据核对编辑器</a></div>` +
    `<div class="wb-card"><div class="wb-section-hdr"><h3>待核对清单（${pending.length}）</h3></div>` +
    (pending.length === 0
      ? `<div class="wb-empty" style="padding:30px"><div class="wb-empty-icon">✔️</div><div class="wb-empty-sub">已全部核对</div></div>`
      : `<table class="wb-table"><thead><tr><th>ID</th><th>原文件名</th><th>专业</th><th>存疑/告警</th><th>状态</th></tr></thead><tbody>` +
        pending.map(d =>
          `<tr><td>${d.id || '—'}</td><td>${d.original_file || '—'}</td><td>${d.professional || '—'}</td>` +
          `<td>${(d.confusion_suspects || 0)}/${(d.quality_alerts || 0)}</td>` +
          `<td>${(d.ocr_status || 'pending')}</td></tr>`).join('') +
        `</tbody></table>`) +
    `</div>` +
    (suspects.length ? `<div class="wb-card" style="margin-top:14px"><div class="wb-section-hdr"><h3>建议优先核对（存疑 ${suspects.length}）</h3></div>` +
      `<ul class="wb-list">${suspects.map(d => `<li>${d.id || ''} · ${d.original_file || '—'}</li>`).join('')}</ul></div>` : '');
}