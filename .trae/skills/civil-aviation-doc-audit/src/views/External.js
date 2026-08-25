// src/views/External.js —— 规则与反馈（Task 9）
// 8765 规则面板外链 + 反馈页链接 + 启动引导提示
export default function renderExternal(container) {
  mountExternal(container);
}

export function mountExternal(container) {
  const links = [
    { href: 'http://localhost:8765', label: '规则管理面板', desc: '启动 rule-manager 后打开（端口 8765）', id: 'ext-api' },
    { href: 'feedback.html', label: '意见反馈', desc: '提交审核规则与体验反馈', id: 'ext-feedback' },
    { href: 'rule-editor.html', label: '规则编辑器', desc: '在线新增 / 编辑规则', id: 'ext-editor' },
  ];

  container.innerHTML =
    `<div class="wb-section-hdr"><h3>规则与反馈</h3></div>` +
    `<div class="wb-stats" style="grid-template-columns:repeat(auto-fit,minmax(220px,1fr))">` +
    links.map(l =>
      `<a class="wb-card" href="${l.href}" target="_blank" rel="noopener" id="${l.id}" style="display:block;text-decoration:none;color:inherit">` +
      `<div class="wb-stat-label">${l.label}</div><div class="wb-stat-hint" style="margin-top:6px">${l.desc}</div></a>`).join('') +
    `</div>` +
    `<div class="wb-card" style="margin-top:14px"><div class="wb-section-hdr"><h3>启动引导</h3></div>` +
    `<ul class="wb-list">` +
    `<li>① 先启动规则服务器：双击 <code>rule-manager.bat</code></li>` +
    `<li>② 在浏览器打开 <code>http://localhost:8765</code> 进入规则管理</li>` +
    `<li>③ 再回到本工作台，各模块独立可用；外部页面未启动时点击也不会崩溃</li>` +
    `</ul></div>`;
}