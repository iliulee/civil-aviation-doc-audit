// src/views/Overview.js —— 项目总览（Task 3）
// 移植自 templates/project-dashboard.html：统计卡 / 文档明细 / 断档检测 / 建议重扫 TOP 10
// 数据源统一走 WB.index（一次加载，模块共享）
export default function renderOverview(container, ctx) {
  const { WB } = ctx;

  function draw() {
    const data = WB.index;
    if (!data) {
      container.innerHTML =
        '<div class="wb-section"><div class="wb-section-hdr"><h3>项目总览</h3></div>' +
        '<div class="wb-empty"><div class="wb-empty-icon">📂</div>' +
        '<div class="wb-empty-title">尚未加载项目数据</div>' +
        '<div class="wb-empty-sub">切换到"项目总览"前，请先通过右上角选择项目文件夹，或确认 index.json 已部署就绪。</div></div></div>';
      return;
    }

    const docs = data.documents || [];
    const total = docs.length;
    const completed = docs.filter(d => d.ocr_status === 'completed').length;
    const needsReview = docs.filter(d => d.ocr_status === 'needs_review').length;
    const ocrDone = completed + needsReview;
    const alerts = docs.reduce((s, d) => s + (d.quality_alerts || 0), 0);
    const suspects = docs.reduce((s, d) => s + (d.confusion_suspects || 0), 0);
    const verified = docs.filter(d => d.human_verified).length;
    const pending = total - verified;
    const ocrPct = total > 0 ? Math.round((ocrDone / total) * 100) + '%' : '—';
    const gaps = data.gaps || [];

    const stats = [
      { label: '文档总数', value: total, hint: 'audited + reference' },
      { label: 'OCR 完成', value: ocrDone, hint: ocrPct },
      { label: '已核对', value: verified + '/' + total, hint: 'human_verified' },
      { label: '待核对', value: pending, hint: '= 总数 - 已核对' },
      { label: '质量告警', value: alerts, hint: 'quality_alerts 累计' },
      { label: 'OCR 存疑', value: suspects, hint: 'confusion_suspects 累计' },
    ];

    const statCards = stats.map(s =>
      `<div class="wb-stat-card"><div class="wb-stat-label">${s.label}</div>` +
      `<div class="wb-stat-value">${s.value}</div>` +
      `<div class="wb-stat-hint">${s.hint}</div></div>`
    ).join('');

    // 文档明细表
    const rows = docs.length === 0
      ? '<tr><td colspan="8"><div class="wb-empty" style="padding:24px"><div class="wb-empty-sub">数据底座中尚无文档</div></div></td></tr>'
      : docs.map(d => {
          const ocrStatus = d.ocr_status || 'pending';
          const verBadge = d.human_verified
            ? '<span class="wb-badge ok">已核对</span>'
            : '<span class="wb-badge warn">未核对</span>';
          const pc = alertCount => alertCount > 0 ? '<span class="wb-badge danger">' + alertCount + '</span>' : '<span class="wb-badge neutral">0</span>';
          const sc = s => s > 0 ? '<span class="wb-badge warn">' + s + '</span>' : '<span class="wb-badge neutral">0</span>';
          const ocrCell = (() => {
            const m = d.extraction_mode;
            if (m === 'meta_xlsx' || m === 'text_pdf' || m === 'docx' || m === 'reference_skip') return '免OCR';
            return typeof d.ocr_confidence === 'number' ? (d.ocr_confidence * 100).toFixed(1) + '%' : '—';
          })();
          return `<tr>
            <td class="wb-mono">${d.id || '—'}</td>
            <td title="${d.original_file || ''}">${d.original_file || '—'}</td>
            <td>${d.professional || '—'}</td>
            <td>${d.doc_type || '—'}</td>
            <td>${d.pages || '—'}</td>
            <td>${ocrCell}</td>
            <td>${ocrStatus}</td>
            <td>${verBadge}</td>
            <td>${pc(d.quality_alerts)} ${sc(d.confusion_suspects)}</td>
          </tr>`;
        }).join('');

    // 断档
    const gapBlock = gaps.length === 0
      ? ''
      : `<div class="wb-card"><div class="wb-section-hdr"><h3>断档检测（${gaps.length} 项）</h3></div>
         <ul class="wb-list">${gaps.map(g =>
           `<li><span class="wb-badge danger">!</span><span>${g.description || g.type || '未知断档'}</span>` +
           `<span style="color:var(--color-text-tertiary)">${g.professional || ''} ${g.type || ''}</span></li>`
         ).join('')}</ul></div>`;

    // 建议重扫 TOP 10
    const rescanItems = renderRescanTop10(docs);
    const rescanBlock = rescanItems.length === 0
      ? ''
      : `<div class="wb-card"><div class="wb-section-hdr"><h3>建议重扫 TOP ${rescanItems.length}</h3></div>
         <ul class="wb-list">${rescanItems.join('')}</ul></div>`;

    container.innerHTML =
      `<div class="wb-section-hdr"><h3>项目总览</h3>` +
      `<span class="wb-badge neutral">${data.project_name || '未命名项目'} · ${(data.stage || '').replace(/_/g, ' ')}</span></div>` +
      `<div class="wb-stats" style="grid-template-columns:repeat(auto-fit,minmax(140px,1fr))">${statCards}</div>` +
      gapBlock +
      `<div class="wb-card"><div class="wb-section-hdr"><h3>文档明细（${total}）</h3></div>` +
      `<div style="overflow-x:auto"><table class="wb-table"><thead><tr>` +
      `<th>ID</th><th>原文件名</th><th>专业</th><th>类型</th><th>页数</th><th>OCR%</th><th>状态</th><th>核对</th><th>告警/存疑</th>` +
      `</tr></thead><tbody>${rows}</tbody></table></div></div>` +
      rescanBlock;
  }

  // 渲染一次；数据重载后的统一重绘由外壳（main.js）管理
  draw();
}

// ===== v7.2 C4：建议重扫 TOP 10（纯文字提示，不强制） =====
function renderRescanTop10(docs) {
  // 仅 extraction_mode="ocr"（缺失默认 "ocr"）
  const ocrDocs = docs.filter(d => (d.extraction_mode || 'ocr') === 'ocr');
  // 仅 ocr_confidence < 0.85（缺失默认 1.0）
  const lowConf = ocrDocs.filter(d => (typeof d.ocr_confidence === 'number' ? d.ocr_confidence : 1.0) < 0.85);
  if (lowConf.length === 0) return [];
  // 排序分 = (1 - conf) * (quality_alerts + confusion_suspects)
  const ranked = lowConf.map(d => {
    const conf = typeof d.ocr_confidence === 'number' ? d.ocr_confidence : 1.0;
    const fatalEstimate = (d.quality_alerts || 0) + (d.confusion_suspects || 0);
    return { d, conf, score: (1 - conf) * fatalEstimate };
  }).sort((a, b) => b.score - a.score).slice(0, 10);

  return ranked.map(it => {
    const d = it.d;
    const confPct = (it.conf * 100).toFixed(1);
    const sub = [d.doc_type, d.professional].filter(Boolean).join(' · ');
    return `<li><span class="wb-badge warn">${confPct}%</span>` +
      `<span title="${d.original_file || ''}">${d.original_file || d.id || '—'}</span>` +
      `<span style="color:var(--color-text-tertiary)">${sub}</span></li>`;
  });
}